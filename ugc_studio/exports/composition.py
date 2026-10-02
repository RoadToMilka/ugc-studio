"""Vidéo avec sous-titres (V3, lot 2, §8.3) : le calque dessiné au moment exact de chaque image de
la vidéo, écrit dans un fichier provisoire, puis posé sur la vidéo par FFmpeg.

Trois étapes, suivies dans la fenêtre d'export (avancement, « Arrêter ») :
1. **Dessin des sous-titres** : pour chaque image de la vidéo, l'image du calque à son moment exact,
   dessinée par le moteur de l'aperçu (mot actif, animations, fond qui glisse). Une image identique
   à la précédente n'est pas redessinée : la précédente dure plus longtemps. Chaque nouvelle image
   devient un PNG, dans deux fils à part (le dessin continue pendant ce temps), puis s'écrit à la
   suite dans le calque provisoire (mov_png.py).
2. **Encodage** : FFmpeg lit la vidéo et le calque, pose l'un sur l'autre et encode le tout (deux
   passages pour H.264 et H.265, un pour le ProRes).
3. Le fichier prend son vrai nom. Le dossier provisoire (dans le dossier temporaire de Windows) est
   effacé, comme après « Arrêter » ou une erreur : rien ne reste.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QObject, QTimer, Signal
from PySide6.QtGui import QImage, QImageWriter

from ..rendu.moteur import Moteur
from ..sous_titres import MotAffiche, ReglagesSousTitres, SousTitre
from .calque import cle_de_l_image, index_de_la_cle, meme_image
from .ffmpeg import COURBES_HDR, Processus
from .mov_png import EcritureMovPng
from .video import PlanVideo, commande_video

journal = logging.getLogger(__name__)

TRANCHE_S = 0.025  # travail fait d'un coup, entre deux moments où la fenêtre répond
ATTENTE_MS = 5  # les PNG en cours ne sont pas prêts : on revient peu après
SUIVI_MS = 100  # nouvelles de FFmpeg pendant l'encodage
PNG_EN_ATTENTE_MAX = 6  # images dessinées pas encore écrites (mémoire : ≈ 50 Mo en 1080 × 1920)
FILS_PNG = 2
COMPRESSION_PNG = 1  # zlib, de 0 à 9 : 1, la plus rapide ; le calque, surtout transparent, se compresse bien
NOM_DU_CALQUE = "calque.mov"
NOM_DU_JOURNAL = "passages"  # FFmpeg y ajoute « -0.log » (analyse du premier passage)


def png_de(image: QImage) -> bytes:
    """L'image en PNG, transparence comprise (16 bits par couleur pour une image en 16 bits)."""
    tampon = QBuffer()
    tampon.open(QIODevice.OpenModeFlag.WriteOnly)
    ecriture = QImageWriter(tampon, b"PNG")
    ecriture.setCompression(COMPRESSION_PNG)
    if not ecriture.write(image):
        raise OSError(f"image du calque impossible à écrire en PNG ({ecriture.errorString()})")
    return bytes(tampon.data())


class CalqueDeLaVideo:
    """Les images du calque posé sur la vidéo : l'image entière à chaque moment, en transparence
    « droite » (non prémultipliée, comme le lit FFmpeg), en 8 ou 16 bits par couleur."""

    def __init__(
        self, reglages: ReglagesSousTitres, largeur: int, hauteur: int, sous_titres: list[SousTitre], mots: list[MotAffiche],
        seize_bits: bool,
    ):
        self.moteur = Moteur(reglages, largeur, hauteur, profondeur=16 if seize_bits else 8)
        self.largeur, self.hauteur = largeur, hauteur
        self._sous_titres, self._mots = sous_titres, mots
        self._debuts = [s.debut for s in sous_titres]
        self._format = QImage.Format.Format_RGBA64 if seize_bits else QImage.Format.Format_ARGB32
        self.dessinees = 0

    def cle(self, temps: float) -> tuple | None:
        return cle_de_l_image(self.moteur, self._sous_titres, self._debuts, self._mots, temps)

    def image(self, cle: tuple | None, temps: float) -> QImage:
        sous_titre = None if cle is None else self._sous_titres[index_de_la_cle(cle)]
        image = self.moteur.image(sous_titre, self._mots, temps)
        if sous_titre is not None:
            self.dessinees += 1
        return image.convertToFormat(self._format)


class ExportVideo(QObject):
    """Fabrique la vidéo avec sous-titres : calque provisoire, puis encodage par FFmpeg."""

    etape = Signal(str, bool)  # nom de l'étape, et si c'est la dernière (« Finalisation du fichier… » à la fin)
    avance = Signal(int, int)  # fait, total (de l'étape en cours)
    termine = Signal(object)  # le fichier écrit (Path)
    echec = Signal(str)  # message clair
    arrete = Signal()

    def __init__(self, plan: PlanVideo, calque: CalqueDeLaVideo, ffmpeg: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.plan, self._calque, self._ffmpeg = plan, calque, ffmpeg
        self._etat: str | None = None  # « dessin », « encodage », ou rien
        self._dossier: Path | None = None
        self._mov: EcritureMovPng | None = None
        self._fils: ThreadPoolExecutor | None = None
        self._attente: deque[tuple[str, Future | None, int]] = deque()
        self._numero = 0
        self._cle_precedente: object = object()  # rien encore : la première image est toujours dessinée
        self._png_vide: Future | None = None  # l'image sans sous-titre, mise en PNG une seule fois
        self._processus: Processus | None = None
        self._passage = 0
        self.debut: float | None = None
        self.duree_s: float | None = None
        self.dessin_s = 0.0  # temps passé à dessiner les images (le reste : PNG et FFmpeg)
        self.images_du_calque = 0  # PNG écrits dans le calque provisoire
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.timeout.connect(self._travailler)

    @property
    def en_cours(self) -> bool:
        return self._etat is not None

    @property
    def images_dessinees(self) -> int:
        return self._calque.dessinees

    @property
    def calque_provisoire(self) -> Path | None:
        return self._dossier / NOM_DU_CALQUE if self._dossier is not None else None

    def demarrer(self) -> None:
        plan = self.plan
        try:
            plan.en_cours.unlink(missing_ok=True)
            self._dossier = Path(tempfile.mkdtemp(prefix="UGC Studio export "))
            # Le calque compte le temps dans l'unité de la vidéo (1/30 000 s, 1/600 s…) : mêmes moments, sans arrondi.
            echelle = plan.images.base_de_temps.denominator
            self._mov = EcritureMovPng(self._dossier / NOM_DU_CALQUE, plan.largeur, plan.hauteur, echelle)
        except (OSError, ValueError) as erreur:
            self._echouer(f"Export impossible : {erreur}")
            return
        self._fils = ThreadPoolExecutor(max_workers=FILS_PNG, thread_name_prefix="png")
        self._etat = "dessin"
        self.debut = time.monotonic()
        couleurs = plan.couleurs
        if couleurs.hdr:
            gamme = f"HDR ({COURBES_HDR[couleurs.transfert]}{', Dolby Vision' if plan.dolby_vision else ''})"
        else:
            gamme = "SDR, converti du HDR" if couleurs.hdr_converti is not None else "SDR"
        journal.info(
            "Export de la vidéo : %s (%d images, %s, %s, %s, %d bits)", plan.sortie, plan.nombre_images, plan.conteneur,
            plan.codec, gamme, plan.bits,
        )
        self.etape.emit("Dessin des sous-titres", False)
        self._minuterie.start(0)

    def _travailler(self) -> None:
        if self._etat == "dessin":
            self._dessiner()
        elif self._etat == "encodage":
            self._suivre()

    # --- 1. Dessin du calque provisoire ------------------------------------------------------------

    def _duree(self, numero: int) -> int:
        """Durée de l'image `numero` dans le calque : jusqu'à l'image suivante de la vidéo."""
        images = self.plan.images
        moments = images.moments
        if numero + 1 < len(moments):
            ecart = moments[numero + 1] - moments[numero]
        elif images.duree_derniere > 0:
            ecart = images.duree_derniere
        else:
            ecart = moments[numero] - moments[numero - 1] if numero > 0 else 1
        return ecart * images.base_de_temps.numerator

    def _dessiner(self) -> None:
        images = self.plan.images
        limite = time.monotonic() + TRANCHE_S
        try:
            self._ecrire_les_png_prets()
            while self._numero < images.nombre and time.monotonic() < limite and len(self._attente) < PNG_EN_ATTENTE_MAX:
                numero = self._numero
                self._numero += 1
                duree = self._duree(numero)
                if duree <= 0:
                    continue  # deux images au même moment (fichier abîmé) : la suivante compte
                temps = float(images.moments[numero] * images.base_de_temps)
                avant = time.monotonic()
                cle = self._calque.cle(temps)
                if meme_image(cle, self._cle_precedente):
                    self._attente.append(("prolonger", None, duree))
                elif cle is None:
                    if self._png_vide is None:
                        self._png_vide = self._fils.submit(png_de, self._calque.image(None, temps))
                    self._attente.append(("png", self._png_vide, duree))
                else:
                    self._attente.append(("png", self._fils.submit(png_de, self._calque.image(cle, temps)), duree))
                self._cle_precedente = cle
                self.dessin_s += time.monotonic() - avant
            self._ecrire_les_png_prets()
        except (OSError, RuntimeError, ValueError) as erreur:
            self._echouer(f"Dessin des sous-titres impossible : {erreur}")
            return
        self.avance.emit(self._numero, images.nombre)
        if self._numero >= images.nombre and not self._attente:
            try:
                self._mov.fermer()
            except OSError as erreur:
                self._echouer(f"Calque provisoire impossible à écrire : {erreur}")
                return
            self._mov = None
            journal.info(
                "Calque provisoire : %d PNG pour %d images, dessin %.1f s", self.images_du_calque, images.nombre, self.dessin_s
            )
            self._lancer_le_passage(1)
            return
        self._minuterie.start(0 if len(self._attente) < PNG_EN_ATTENTE_MAX else ATTENTE_MS)

    def _ecrire_les_png_prets(self) -> None:
        """Les PNG terminés s'écrivent dans l'ordre des images ; une image qui ne change pas allonge la
        précédente."""
        while self._attente:
            sorte, futur, duree = self._attente[0]
            if sorte == "prolonger":
                self._mov.prolonger(duree)
            else:
                if not futur.done():
                    return
                self._mov.ajouter(futur.result(), duree)  # une erreur d'écriture du PNG remonte ici
                self.images_du_calque += 1
            self._attente.popleft()

    # --- 2. Encodage par FFmpeg --------------------------------------------------------------------

    def _lancer_le_passage(self, passage: int) -> None:
        plan = self.plan
        self._passage = passage
        commande = commande_video(self._ffmpeg, plan, self._dossier / NOM_DU_CALQUE, passage, self._dossier / NOM_DU_JOURNAL)
        try:
            self._processus = Processus(commande, avec_images=False)
        except OSError as erreur:
            self._echouer(f"FFmpeg ne démarre pas : {erreur}")
            return
        self._etat = "encodage"
        nom = "Encodage" if plan.passages == 1 else f"Encodage, passage {passage} sur {plan.passages}"
        self.etape.emit(nom, passage == plan.passages)
        self.avance.emit(0, plan.nombre_images)
        self._minuterie.start(SUIVI_MS)

    def _suivre(self) -> None:
        processus, plan = self._processus, self.plan
        if processus is None:
            return
        self.avance.emit(min(processus.nouvelles.images, plan.nombre_images), plan.nombre_images)
        if not processus.termine():
            self._minuterie.start(SUIVI_MS)
            return
        code = processus.attendre(30)
        if code != 0:
            journal.warning("Encodage en échec (passage %d, code %s) : %s", self._passage, code, " | ".join(processus.erreurs()))
            detail = processus.erreur() or f"FFmpeg s'est arrêté (code {code})"
            message = f"L'encodage a échoué : {detail}"
            if plan.dolby_vision and "dolby" in " ".join(processus.erreurs()).casefold():
                # Dolby Vision repris de la source (lot 3) : sans lui, la vidéo reste en HDR.
                message += " Pour exporter sans Dolby Vision (la vidéo reste en HDR), choisis le format MOV."
            self._echouer(message)
            return
        self._processus = None
        if self._passage < plan.passages:
            self._lancer_le_passage(self._passage + 1)
            return
        self._conclure()

    # --- 3. Fin ------------------------------------------------------------------------------------

    def _conclure(self) -> None:
        plan = self.plan
        self._etat = None
        self.duree_s = time.monotonic() - (self.debut or time.monotonic())
        if not plan.en_cours.is_file() or plan.en_cours.stat().st_size == 0:
            self._echouer("L'encodage n'a pas écrit de fichier.")
            return
        try:
            os.replace(plan.en_cours, plan.sortie)
        except OSError as erreur:
            journal.warning("Vidéo non renommée : %s", erreur)
            self._nettoyer()
            self.echec.emit(
                f"La vidéo est prête, mais « {plan.sortie.name} » n'a pas pu être remplacé (est-il ouvert dans un "
                f"lecteur ?). Elle est gardée sous le nom « {plan.en_cours.name} »."
            )
            return
        self._nettoyer()
        journal.info(
            "Vidéo écrite en %.1f s (dessin : %.1f s, %d PNG) : %s", self.duree_s, self.dessin_s, self.images_du_calque, plan.sortie
        )
        self.termine.emit(plan.sortie)

    def arreter(self) -> None:
        """« Arrêter » : FFmpeg s'arrête tout de suite, et rien n'est gardé."""
        self._etat = None
        self._minuterie.stop()
        if self._processus is not None:
            self._processus.arreter()
            self._processus = None
        self._nettoyer(effacer_la_sortie=True)
        journal.info("Export de la vidéo arrêté : %s", self.plan.sortie)
        self.arrete.emit()

    def _echouer(self, message: str) -> None:
        self._etat = None
        self._minuterie.stop()
        if self._processus is not None:
            self._processus.arreter()
            self._processus = None
        self._nettoyer(effacer_la_sortie=True)
        journal.warning("Export de la vidéo en échec : %s", message)
        self.echec.emit(message)

    def _nettoyer(self, effacer_la_sortie: bool = False) -> None:
        """Les fils des PNG s'arrêtent ; le calque et le journal des passages (dossier provisoire) sont
        effacés ; après un arrêt ou une erreur, le fichier inachevé aussi."""
        if self._fils is not None:
            self._fils.shutdown(wait=False, cancel_futures=True)
            self._fils = None
        self._attente.clear()
        if self._mov is not None:
            self._mov.annuler()
            self._mov = None
        if effacer_la_sortie:
            try:
                self.plan.en_cours.unlink(missing_ok=True)
            except OSError:
                journal.warning("Fichier provisoire non effacé : %s", self.plan.en_cours, exc_info=True)
        if self._dossier is not None:
            shutil.rmtree(self._dossier, ignore_errors=True)
            self._dossier = None
