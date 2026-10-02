"""Calque transparent (V3, lot 1, §8.2) : les images, dessinées par le moteur de l'aperçu, puis
confiées à FFmpeg qui écrit le ProRes 4444.

- Chaque image est celle de l'aperçu à ce moment exact (numéro de l'image ÷ fréquence) : sous-titre
  affiché, mot actif, animations, fond qui glisse compris.
- Le moteur dessine ici en 16 bits par couleur (finesse des ombres et des lueurs). L'image d'un
  sous-titre est convertie en transparence « droite » (non prémultipliée, la forme courante en
  ProRes), puis recopiée à sa place dans l'image entière, transparente ailleurs.
- Une image identique à la précédente (rien ne bouge : même sous-titre, même mot actif, aucune
  animation en cours) n'est pas redessinée : la même image repart.
- Le travail se fait par petites tranches dans la tâche principale (le moteur dessine avec Qt), en
  laissant la fenêtre répondre entre deux tranches ; FFmpeg encode en même temps, dans son propre
  programme. Le fichier s'écrit sous un nom provisoire (« … .mov.en-cours ») et ne prend son vrai
  nom qu'à la fin : « Arrêter », ou une erreur, n'en laisse rien.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage

from ..rendu.moteur import Moteur
from ..sous_titres import MotAffiche, ReglagesSousTitres, SousTitre, sous_titre_au_temps
from .ffmpeg import OCTETS_PAR_PIXEL, Processus, commande_calque
from .plan import PlanCalque

journal = logging.getLogger(__name__)

TRANCHE_S = 0.025  # travail fait d'un coup, entre deux moments où la fenêtre répond
ATTENTE_MS = 5  # FFmpeg n'a plus de place pour une image : on réessaie peu après
ATTENTE_FIN_MS = 50


def cle_de_l_image(moteur: Moteur, sous_titres: list[SousTitre], debuts: list[float], mots: list[MotAffiche], temps: float) -> tuple | None:
    """Ce qui décide de l'image à ce moment : le sous-titre et son mot actif. None : aucun
    sous-titre. Une image en mouvement (animation, fond qui glisse) a une clé unique : deux moments
    de même clé ont la même image (elle n'est dessinée qu'une fois)."""
    index = sous_titre_au_temps(sous_titres, temps, debuts)
    if index < 0:
        return None
    sous_titre = sous_titres[index]
    if moteur.en_mouvement(sous_titre, mots, temps):
        return ("en mouvement", index, temps)
    return (index, moteur.instant(sous_titre, mots, temps).actif)


def index_de_la_cle(cle: tuple) -> int:
    return cle[1] if cle[0] == "en mouvement" else cle[0]


def meme_image(cle: tuple | None, precedente: object) -> bool:
    """La même image que la précédente (rien ne bouge) ?"""
    return cle == precedente and (cle is None or cle[0] != "en mouvement")


class ImagesDuCalque:
    """Les images du calque, une par moment demandé : RGBA 16 bits, transparence droite, l'image
    entière (largeur × hauteur × 8 octets)."""

    def __init__(self, reglages: ReglagesSousTitres, largeur: int, hauteur: int, sous_titres: list[SousTitre], mots: list[MotAffiche]):
        self.moteur = Moteur(reglages, largeur, hauteur, profondeur=16)
        self.largeur, self.hauteur = largeur, hauteur
        self._sous_titres, self._mots = sous_titres, mots
        self._debuts = [s.debut for s in sous_titres]
        self.vide = bytes(largeur * hauteur * OCTETS_PAR_PIXEL)  # image entièrement transparente
        self._ligne_vide = bytes(largeur * OCTETS_PAR_PIXEL)
        self._image = bytearray(self.vide)
        self._zone: tuple[int, int, int, int] | None = None  # partie dessinée de self._image
        self._cle: object = None
        self._donnees = self.vide
        self.dessinees = 0  # images vraiment redessinées (les autres sont reprises telles quelles)

    def cle(self, temps: float) -> tuple | None:
        return cle_de_l_image(self.moteur, self._sous_titres, self._debuts, self._mots, temps)

    def image(self, temps: float) -> bytes:
        cle = self.cle(temps)
        if meme_image(cle, self._cle):
            return self._donnees
        self._cle = cle
        self._effacer()
        if cle is None:
            self._donnees = self.vide
            return self._donnees
        index = index_de_la_cle(cle)
        dessin, x, y = self.moteur.image_de_l_instant(self._sous_titres[index], self._mots, 1.0, 1.0, temps)
        self._poser(dessin.convertToFormat(QImage.Format.Format_RGBA64), x, y)
        self.dessinees += 1
        self._donnees = bytes(self._image)
        return self._donnees

    def _effacer(self) -> None:
        """La partie dessinée pour l'image précédente redevient transparente."""
        if self._zone is None:
            return
        gauche, haut, droite, bas = self._zone
        debut, longueur = gauche * OCTETS_PAR_PIXEL, (droite - gauche) * OCTETS_PAR_PIXEL
        for ligne in range(haut, bas):
            position = ligne * self.largeur * OCTETS_PAR_PIXEL + debut
            self._image[position : position + longueur] = self._ligne_vide[:longueur]
        self._zone = None

    def _poser(self, dessin: QImage, x: int, y: int) -> None:
        """Recopie l'image d'un sous-titre (déjà en transparence droite) à sa place, ligne par
        ligne ; ce qui dépasse de l'image entière (ombre au bord) est coupé."""
        gauche, haut = max(0, x), max(0, y)
        droite, bas = min(self.largeur, x + dessin.width()), min(self.hauteur, y + dessin.height())
        if droite <= gauche or bas <= haut:
            return
        octets = memoryview(dessin.constBits())
        par_ligne = dessin.bytesPerLine()
        longueur = (droite - gauche) * OCTETS_PAR_PIXEL
        for ligne in range(haut, bas):
            source = (ligne - y) * par_ligne + (gauche - x) * OCTETS_PAR_PIXEL
            cible = (ligne * self.largeur + gauche) * OCTETS_PAR_PIXEL
            self._image[cible : cible + longueur] = octets[source : source + longueur]
        self._zone = (gauche, haut, droite, bas)


class ExportDuCalque(QObject):
    """Fabrique le fichier du calque : les images partent vers FFmpeg au fil du dessin."""

    avance = Signal(int, int)  # images envoyées, images en tout
    termine = Signal(object)  # le fichier écrit (Path)
    echec = Signal(str)  # message clair
    arrete = Signal()

    def __init__(self, plan: PlanCalque, images: ImagesDuCalque, ffmpeg: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.plan, self._images, self._ffmpeg = plan, images, ffmpeg
        self._processus: Processus | None = None
        self._numero = 0
        self._fin_envoyee = False
        self.debut: float | None = None
        self.duree_s: float | None = None  # durée de l'export, une fois fini
        self.dessin_s = 0.0  # temps passé à dessiner les images (le reste : FFmpeg qui encode)
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.timeout.connect(self._travailler)

    @property
    def en_cours(self) -> bool:
        return self._processus is not None

    @property
    def images_dessinees(self) -> int:
        """Images vraiment redessinées (les autres, identiques à la précédente, sont reprises)."""
        return self._images.dessinees

    def demarrer(self) -> None:
        plan = self.plan
        try:
            plan.en_cours.unlink(missing_ok=True)
        except OSError as erreur:
            self.echec.emit(f"Fichier impossible à écrire dans ce dossier : {erreur}")
            return
        commande = commande_calque(self._ffmpeg, plan.largeur, plan.hauteur, plan.frequence, plan.nombre_images, plan.en_cours)
        try:
            self._processus = Processus(commande, avec_images=True)
        except OSError as erreur:
            self.echec.emit(f"FFmpeg ne démarre pas : {erreur}")
            return
        self._numero, self._fin_envoyee = 0, False
        self.debut = time.monotonic()
        journal.info("Export du calque : %s (%d images à %s i/s)", plan.sortie, plan.nombre_images, plan.frequence)
        self._minuterie.start(0)

    def _travailler(self) -> None:
        processus, plan = self._processus, self.plan
        if processus is None:
            return
        if not self._fin_envoyee:
            limite = time.monotonic() + TRANCHE_S
            while self._numero < plan.nombre_images and time.monotonic() < limite:
                if processus.tuyau_coupe or processus.termine():
                    self._conclure()  # FFmpeg s'est arrêté avant la fin : son message dira pourquoi
                    return
                if not processus.peut_recevoir():
                    break
                avant = time.monotonic()
                image = self._images.image(plan.temps(self._numero))
                self.dessin_s += time.monotonic() - avant
                processus.envoyer(image)
                self._numero += 1
            self.avance.emit(self._numero, plan.nombre_images)
            if self._numero >= plan.nombre_images:
                self._fin_envoyee = processus.fin_des_images()
            self._minuterie.start(0 if processus.peut_recevoir() and not self._fin_envoyee else ATTENTE_MS)
            return
        if processus.termine():
            self._conclure()
        else:
            self._minuterie.start(ATTENTE_FIN_MS)

    def _conclure(self) -> None:
        processus, plan = self._processus, self.plan
        self._processus = None
        self._minuterie.stop()
        code = processus.attendre(30)
        self.duree_s = time.monotonic() - (self.debut or time.monotonic())
        if code == 0 and self._fin_envoyee and plan.en_cours.is_file() and plan.en_cours.stat().st_size > 0:
            try:
                os.replace(plan.en_cours, plan.sortie)
            except OSError as erreur:
                journal.warning("Calque non renommé : %s", erreur)
                self.echec.emit(
                    f"Le calque est prêt, mais « {plan.sortie.name} » n'a pas pu être remplacé (est-il ouvert dans "
                    f"Premiere Pro ?). Il est gardé sous le nom « {plan.en_cours.name} »."
                )
                return
            journal.info(
                "Calque écrit en %.1f s (dessin : %.1f s) : %s (%d images redessinées sur %d)",
                self.duree_s, self.dessin_s, plan.sortie, self._images.dessinees, plan.nombre_images,
            )
            self.termine.emit(plan.sortie)
            return
        journal.warning("Export du calque en échec (code %s) : %s", code, " | ".join(processus.erreurs()))
        self._effacer_le_provisoire()
        detail = processus.erreur() or f"FFmpeg s'est arrêté (code {code})"
        self.echec.emit(f"L'export a échoué : {detail}")

    def arreter(self) -> None:
        """« Arrêter » : FFmpeg s'arrête tout de suite, et rien n'est gardé."""
        processus, self._processus = self._processus, None
        self._minuterie.stop()
        if processus is not None:
            processus.arreter()
        self._effacer_le_provisoire()
        journal.info("Export du calque arrêté : %s", self.plan.sortie)
        self.arrete.emit()

    def _effacer_le_provisoire(self) -> None:
        try:
            self.plan.en_cours.unlink(missing_ok=True)
        except OSError:
            journal.warning("Fichier provisoire non effacé : %s", self.plan.en_cours, exc_info=True)
