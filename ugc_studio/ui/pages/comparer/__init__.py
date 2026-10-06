"""Module Comparer (V4.1, version 4.2.0 ; cahier des charges §8 bis.4) : deux vidéos ou deux images
comparées dans video-compare, logiciel libre lancé dans sa propre fenêtre, avec la copie de
l'utilisateur (décision du 06/10/2026). Le calcul et le lancement sont dans comparer/video_compare.py.

Le parcours, de haut en bas :
1. video-compare : trouvé tout seul (copie déjà installée, Téléchargements), sinon « Choisir
   video-compare… » (le zip téléchargé, ou video-compare.exe) ; un zip est décompressé par l'app.
2. Fichiers : deux vidéos ou deux images (glisser-déposer ou « Choisir les fichiers… ») ; celle de
   gauche sert de référence ; « Échanger », « Vider ».
3. Affichage : curseur, côte à côte ou l'une sous l'autre ; fenêtre ; décalage ; boucle ; différence.
4. « Comparer » : la fenêtre de video-compare s'ouvre (« Fermer la comparaison » la ferme) ; ses
   mesures (touche M) et ses captures (touche F) reviennent ici, en français.
5. Les touches utiles de video-compare, en français.

Ce module ne dépend pas d'un projet : ses réglages sont retenus dans les préférences de l'app.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from ....chemins import chemin_a_afficher, dossier_documents, dossier_telechargements
from ....comparer.video_compare import (
    CURSEUR,
    DECALAGE_MAX_MS,
    DISPOSITIONS,
    ECRAN,
    FENETRES,
    NOM_PROGRAMME,
    PAGE_OFFICIELLE,
    VERSION_TESTEE,
    Comparaison,
    Mesures,
    Reglages,
    Trouvaille,
    VideoCompare,
    VideoCompareIntrouvable,
    arguments,
    installer,
    lire_le_choix,
    lire_les_captures,
    lire_les_mesures,
    ouvrir,
    trouver,
)
from ....dossiers import EXTENSIONS_IMAGES
from ....exports.ffmpeg import preparer_ffmpeg
from ....services import Services
from ....topaz.upscale import EXTENSIONS_VIDEOS, duree_lisible, lire_la_video
from ... import taches
from ...composants.bouton import BoutonOccupe
from ...composants.depot_dossier import ZoneDepotDossier, fichiers_deposes
from ...composants.elements import (
    ChampNomme,
    afficher_message,
    bloc,
    bouton,
    case_a_cocher,
    champ_entier,
    libelle,
    liste_deroulante,
)
from ...composants.tableau import Colonne, Tableau
from ...ouvrir import ouvrir_dossier, ouvrir_page_web
from ...theme import Dimensions, Espacements, Hauteurs
from ..base import Page

journal = logging.getLogger(__name__)

TITRE = "Comparer"
SOUS_TITRE = "Deux vidéos ou deux images, comparées dans video-compare."

# Préférences (§10) : ce module ne dépend pas d'un projet.
PREF_PROGRAMME = "comparer_video_compare"  # la copie choisie : video-compare.exe (ou le zip, avant d'être installé)
PREF_DISPOSITION = "comparer_disposition"
PREF_FENETRE = "comparer_fenetre"
PREF_DECALAGE = "comparer_decalage_ms"
PREF_BOUCLE = "comparer_boucle"
PREF_DIFFERENCE = "comparer_difference"
PREF_DERNIER_DOSSIER = "comparer_dernier_dossier"

EXTENSIONS = (*EXTENSIONS_VIDEOS, *EXTENSIONS_IMAGES)
FORMATS_ACCEPTES = "MP4, MOV, MKV… ou PNG, JPG, WebP…"

AIDE_VIDEO_COMPARE = (
    "video-compare est un logiciel gratuit et libre (de Pixop, licence GPL v2) qui compare deux vidéos ou deux "
    "images, image par image, avec un curseur et un zoom au pixel. L'app le lance dans sa propre fenêtre, avec ta "
    "copie : le zip téléchargé sur sa page (l'app le décompresse dans son dossier de programmes ; ton zip ne bouge "
    "pas), ou video-compare.exe si tu l'as décompressé toi-même."
)
AIDE_FICHIERS = (
    "Deux vidéos, ou deux images. Celle de gauche sert de référence (par exemple l'original, ou l'export de "
    "Topaz). Si elles n'ont pas la même taille, video-compare les met à la même taille pour les comparer."
)
AIDE_AFFICHAGE = (
    "Curseur : une seule image, coupée par un trait que la souris déplace. Côte à côte, ou l'une sous l'autre : "
    "les deux en entier. Décalage : si la vidéo de droite ne démarre pas au même moment (positif : celle de "
    "gauche attend)."
)
AIDE_MESURES = (
    "Touche M dans video-compare : la ressemblance de l'image affichée (de la zone visible, après un zoom). "
    "SSIM : 1 si identiques (au-dessus de 0,99, aucune différence visible). PSNR : plus il est haut, plus elles "
    "se ressemblent (infini : identiques). VMAF : la note de Netflix, sur 100. Touche F : trois captures (gauche, "
    "droite, et l'écran tel que tu le vois), dans le dossier du fichier de gauche."
)
AIDE_TOUCHES = "Dans la fenêtre de video-compare (H y montre toutes ses touches, en anglais)."
DETAIL_INTROUVABLE = (
    "Télécharge « video-compare-…-win10-x86_64.zip » sur sa page, puis « Choisir video-compare… » ; ou "
    "laisse-le dans tes Téléchargements : l'app l'y trouve."
)

# Les touches utiles de video-compare (sa documentation, « Controls »), en français.
TOUCHES = (
    ("Espace", "lecture, pause"),
    ("A, D", "image précédente, suivante"),
    ("← →", "1 s en arrière, en avant"),
    ("↑ ↓", "15 s en avant, en arrière"),
    ("Souris", "déplacer le trait de séparation"),
    ("Clic gauche", "aller à ce moment"),
    ("Molette", "zoomer sur le pixel visé"),
    ("Clic droit maintenu", "déplacer la vue"),
    ("R", "revenir à 100 %, recentrer"),
    ("S", "échanger gauche et droite"),
    ("0", "mode différence"),
    ("Z, C", "loupe"),
    ("+, -", "décaler la droite d'une image"),
    ("F", "captures (PNG)"),
    ("M", "mesures de ressemblance"),
    ("Échap", "fermer"),
)

COLONNES_MESURES = (
    Colonne("Moment", texte=True, etiree=True),
    Colonne("SSIM", a_droite=True),
    Colonne("PSNR", a_droite=True),
    Colonne("VMAF", a_droite=True),
)


def _filtre_des_fichiers() -> str:
    return "Vidéos et images (" + " ".join(f"*{extension}" for extension in EXTENSIONS) + ")"


def lire_le_fichier(chemin: Path) -> str:
    """« 606 × 1080 · 21 s » (une vidéo), « 1080 × 1920 · image », ou ce qui ne va pas."""
    if chemin.suffix.lower() in EXTENSIONS_IMAGES:
        from PIL import Image

        try:
            with Image.open(chemin) as image:
                largeur, hauteur = image.size
        except OSError:
            return "image illisible"
        return f"{largeur} × {hauteur} · image"
    video = lire_la_video(chemin, preparer_ffmpeg())
    if video.erreur:
        return "vidéo illisible"
    return f"{video.largeur} × {video.hauteur} · {duree_lisible(video.duree_s)}"


class PageComparer(Page):
    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="comparer")
        self._preferences = services.preferences
        self._video_compare: VideoCompare | None = None
        self._trouvaille = Trouvaille()
        self._erreur_programme = ""  # pourquoi video-compare n'est pas utilisable (le détail)…
        self._titre_erreur = ""  # … et en bref (« video-compare ne démarre pas »)
        self._avancee_installation: float | None = None
        self._gauche: Path | None = None
        self._droite: Path | None = None
        self._infos: dict[Path, str] = {}
        self._lecture = 0  # numéro de la dernière lecture de fichiers (une plus ancienne est ignorée)
        self._comparaison: Comparaison | None = None
        self._dossier_des_captures: Path | None = None  # celui du fichier de gauche, à l'ouverture
        self._fermeture_demandee = False
        self._mesures: list[Mesures] = []
        self._occupe = False  # recherche, installation ou vérification de video-compare
        self._bouton_occupe = BoutonOccupe()
        self.setAcceptDrops(True)

        # --- video-compare ---
        self.cadre_programme, d = bloc("video-compare", aide=AIDE_VIDEO_COMPARE)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.M)
        textes = QVBoxLayout()
        textes.setContentsMargins(0, 0, 0, 0)
        textes.setSpacing(Espacements.XS)
        self.etat_programme = libelle("", "secondaire")
        textes.addWidget(self.etat_programme)
        self.detail_programme = libelle("", "legende")
        textes.addWidget(self.detail_programme)
        ligne.addLayout(textes, 1)
        self.bouton_installer = bouton("Installer", variante="contour", nom_icone="download", action=self.installer)
        ligne.addWidget(self.bouton_installer, 0, Qt.AlignmentFlag.AlignTop)
        self.bouton_choisir_programme = bouton("Choisir video-compare…", variante="contour", nom_icone="folder-open", action=self.choisir_video_compare)
        ligne.addWidget(self.bouton_choisir_programme, 0, Qt.AlignmentFlag.AlignTop)
        self.bouton_page = bouton("Sa page", variante="contour", nom_icone="external-link", action=lambda: ouvrir_page_web(PAGE_OFFICIELLE))
        self.bouton_page.setToolTip("La page des versions de video-compare : télécharge « video-compare-…-win10-x86_64.zip ».")
        ligne.addWidget(self.bouton_page, 0, Qt.AlignmentFlag.AlignTop)
        d.addLayout(ligne)
        self.contenu.addWidget(self.cadre_programme)

        # --- Fichiers ---
        self.cadre_fichiers, d = bloc("Fichiers", aide=AIDE_FICHIERS)
        self.zone_depot = ZoneDepotDossier("Glisse deux vidéos ou deux images ici", FORMATS_ACCEPTES, self.choisir_les_fichiers, "Choisir les fichiers…")
        d.addWidget(self.zone_depot)
        self.zone_fichiers = QWidget()
        grille = QGridLayout(self.zone_fichiers)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setHorizontalSpacing(Espacements.L)
        grille.setVerticalSpacing(Espacements.M)
        self.noms, self.infos, self.boutons_changer = {}, {}, {}
        for rang, (cote, titre) in enumerate((("gauche", "À gauche (référence)"), ("droite", "À droite"))):
            grille.addWidget(libelle(titre, "legende", retour_a_la_ligne=False), rang, 0, Qt.AlignmentFlag.AlignTop)
            textes = QVBoxLayout()
            textes.setContentsMargins(0, 0, 0, 0)
            textes.setSpacing(Espacements.XS)
            self.noms[cote] = libelle("", "secondaire")
            textes.addWidget(self.noms[cote])
            self.infos[cote] = libelle("", "legende")
            textes.addWidget(self.infos[cote])
            grille.addLayout(textes, rang, 1)
            self.boutons_changer[cote] = bouton("Changer…", variante="contour", nom_icone="folder-open", action=lambda c=cote: self.changer_le_fichier(c))
            grille.addWidget(self.boutons_changer[cote], rang, 2, Qt.AlignmentFlag.AlignTop)
        grille.setColumnStretch(1, 1)
        d.addWidget(self.zone_fichiers)
        self.ligne_fichiers = QWidget()
        boutons = QHBoxLayout(self.ligne_fichiers)
        boutons.setContentsMargins(0, 0, 0, 0)
        boutons.setSpacing(Espacements.S)
        self.bouton_echanger = bouton("Échanger", variante="contour", nom_icone="arrow-left-right", action=self.echanger)
        self.bouton_echanger.setToolTip("Celle de droite passe à gauche (la référence), et l'inverse.")
        boutons.addWidget(self.bouton_echanger)
        self.bouton_vider = bouton("Vider", variante="contour", nom_icone="eraser", action=self.vider)
        self.bouton_vider.setToolTip("Retire les deux fichiers de l'app ; ils ne bougent pas.")
        boutons.addWidget(self.bouton_vider)
        boutons.addStretch(1)
        d.addWidget(self.ligne_fichiers)
        self.contenu.addWidget(self.cadre_fichiers)

        # --- Affichage ---
        self.cadre_affichage, d = bloc("Affichage", aide=AIDE_AFFICHAGE)
        champs = QHBoxLayout()
        champs.setContentsMargins(0, 0, 0, 0)
        champs.setSpacing(Espacements.L)
        self.disposition = liste_deroulante()
        for cle, nom in DISPOSITIONS.items():
            self.disposition.addItem(nom, cle)
        self._choisir(self.disposition, self._preferences.lire(PREF_DISPOSITION, CURSEUR))
        champs.addWidget(ChampNomme("Disposition", self.disposition))
        self.fenetre = liste_deroulante()
        for cle, nom in FENETRES.items():
            self.fenetre.addItem(nom, cle)
        self._choisir(self.fenetre, self._preferences.lire(PREF_FENETRE, ECRAN))
        champs.addWidget(ChampNomme("Fenêtre", self.fenetre))
        self.decalage = champ_entier(-DECALAGE_MAX_MS, DECALAGE_MAX_MS, " ms")
        decalage = self._preferences.lire(PREF_DECALAGE, 0)
        self.decalage.setValue(decalage if isinstance(decalage, int) else 0)
        champs.addWidget(ChampNomme("Décalage de la droite", self.decalage))
        champs.addStretch(1)
        d.addLayout(champs)
        cases = QHBoxLayout()
        cases.setContentsMargins(0, 0, 0, 0)
        cases.setSpacing(Espacements.L)
        zone, self.boucle = case_a_cocher("Lecture en boucle", "La vidéo repart au début quand elle arrive à la fin (ou au bout de ce que video-compare garde en mémoire).")
        self.boucle.setChecked(self._preferences.lire(PREF_BOUCLE, False) is True)
        cases.addWidget(zone)
        zone, self.difference = case_a_cocher("Mode différence", "Commencer en mode différence : ce qui change entre les deux apparaît, le reste est noir (touche 0 pour revenir aux images).")
        self.difference.setChecked(self._preferences.lire(PREF_DIFFERENCE, False) is True)
        cases.addWidget(zone)
        cases.addStretch(1)
        d.addLayout(cases)
        self.contenu.addWidget(self.cadre_affichage)

        # --- Comparer ---
        action = QVBoxLayout()
        action.setSpacing(Espacements.S)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_comparer = bouton("Comparer", variante="principal", nom_icone="square-split-horizontal", action=self.comparer)
        boutons.addWidget(self.bouton_comparer)
        self.bouton_fermer = bouton("Fermer la comparaison", nom_icone="x", action=self.fermer_la_comparaison)
        self.bouton_fermer.hide()
        boutons.addWidget(self.bouton_fermer)
        self.bouton_captures = bouton("Ouvrir le dossier des captures", variante="contour", nom_icone="folder-open", action=self.ouvrir_le_dossier_des_captures)
        self.bouton_captures.hide()
        boutons.addWidget(self.bouton_captures)
        boutons.addStretch(1)
        action.addLayout(boutons)
        self.etat_comparaison = libelle("", "legende")
        self.etat_comparaison.hide()
        action.addWidget(self.etat_comparaison)
        self.statut = libelle("", "secondaire")
        action.addWidget(self.statut)
        self.contenu.addLayout(action)

        # --- Mesures et captures ---
        self.cadre_mesures, d = bloc("Mesures et captures", aide=AIDE_MESURES)
        self.tableau_mesures = Tableau(COLONNES_MESURES)
        d.addWidget(self.tableau_mesures)
        self.captures = libelle("", "secondaire")
        d.addWidget(self.captures)
        self.cadre_mesures.hide()
        self.contenu.addWidget(self.cadre_mesures)

        # --- Touches ---
        self.cadre_touches, d = bloc("Touches de video-compare", aide=AIDE_TOUCHES)
        grille = QGridLayout()
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setHorizontalSpacing(Espacements.L)
        grille.setVerticalSpacing(Espacements.S)
        moitie = (len(TOUCHES) + 1) // 2
        for rang, (touche, effet) in enumerate(TOUCHES):
            ligne_grille, colonne = rang % moitie, 2 * (rang // moitie)
            grille.addWidget(libelle(touche, "secondaire", retour_a_la_ligne=False), ligne_grille, colonne)
            grille.addWidget(libelle(effet, "legende"), ligne_grille, colonne + 1)  # passe à la ligne si la place manque
        grille.setColumnStretch(1, 1)
        grille.setColumnStretch(3, 1)
        d.addLayout(grille)
        self.contenu.addWidget(self.cadre_touches)

        self.disposition.currentIndexChanged.connect(lambda _index: self._preferences.ecrire(PREF_DISPOSITION, self.disposition.currentData()))
        self.fenetre.currentIndexChanged.connect(lambda _index: self._preferences.ecrire(PREF_FENETRE, self.fenetre.currentData()))
        self.decalage.valueChanged.connect(lambda valeur: self._preferences.ecrire(PREF_DECALAGE, valeur))
        self.boucle.toggled.connect(lambda coche: self._preferences.ecrire(PREF_BOUCLE, coche))
        self.difference.toggled.connect(lambda coche: self._preferences.ecrire(PREF_DIFFERENCE, coche))
        self._actualiser_fichiers()
        self.chercher_video_compare()

    @staticmethod
    def _choisir(liste, valeur) -> None:
        index = liste.findData(valeur)
        liste.setCurrentIndex(index if index >= 0 else 0)

    @property
    def occupe(self) -> bool:
        return self._occupe

    def showEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        super().showEvent(evenement)
        # video-compare a pu être téléchargé depuis : on le cherche à nouveau en revenant sur la page.
        if self._video_compare is None and not self._occupe:
            self.chercher_video_compare()

    # --- video-compare -----------------------------------------------------------------------

    def video_compare(self) -> VideoCompare | None:
        return self._video_compare

    def _choix_enregistre(self) -> Path | None:
        choisi = self._preferences.lire(PREF_PROGRAMME)
        return Path(choisi) if isinstance(choisi, str) and choisi else None

    def chercher_video_compare(self) -> None:
        """Où est video-compare (choisi, installé par l'app, Téléchargements), puis s'il démarre."""
        if self._occupe:
            return
        self._trouvaille = trouver(self._choix_enregistre(), dossier_telechargements())
        self._video_compare, self._erreur_programme, self._titre_erreur = None, "", ""
        if self._trouvaille.programme is not None:
            self._verifier(self._trouvaille.programme)
        else:
            self._actualiser_programme()

    def _verifier(self, programme: Path) -> None:
        """video-compare démarre-t-il ? (« -V » : sa version) En arrière-plan : la première fois,
        l'antivirus examine ses bibliothèques."""
        self._occuper(True, self.bouton_choisir_programme)
        self._actualiser_programme()
        taches.lancer(lambda: ouvrir(programme), self._verifie, self._verification_echouee)

    def _verifie(self, video_compare: VideoCompare) -> None:
        self._occuper(False)
        self.definir_video_compare(video_compare)

    def _verification_echouee(self, erreur: Exception) -> None:
        self._occuper(False)
        self._video_compare = None
        self._titre_erreur = "video-compare ne démarre pas"
        self._erreur_programme = str(erreur) if isinstance(erreur, VideoCompareIntrouvable) else f"video-compare ne démarre pas : {erreur}"
        self._actualiser_programme()

    def definir_video_compare(self, video_compare: VideoCompare | None) -> None:
        """La copie de video-compare à utiliser (vérifiée) ; pour les tests, un faux."""
        self._video_compare = video_compare
        self._erreur_programme = self._titre_erreur = ""
        self._actualiser_programme()

    def choisir_video_compare(self) -> None:
        """« Choisir video-compare… » : le zip téléchargé (installé aussitôt) ou video-compare.exe."""
        if self._occupe:
            return
        depart = self._choix_enregistre() or dossier_telechargements()
        filtre = f"video-compare (*.zip {NOM_PROGRAMME})"
        choix, _filtre = QFileDialog.getOpenFileName(self, "Choisir video-compare (le zip téléchargé, ou video-compare.exe)", str(depart), filtre)
        if choix:
            self.utiliser(Path(choix))

    def utiliser(self, chemin: Path) -> None:
        """Le choix de l'utilisateur : un zip est installé tout de suite, un .exe vérifié."""
        trouvaille = lire_le_choix(chemin)
        if not trouvaille.programme and not trouvaille.archive:
            self._trouvaille, self._video_compare = Trouvaille(), None
            self._titre_erreur = "Ce n'est pas video-compare"
            self._erreur_programme = f"Choisis le zip téléchargé sur sa page (« video-compare-…-win10-x86_64.zip »), ou {NOM_PROGRAMME}."
            self._actualiser_programme()
            return
        self._preferences.ecrire(PREF_PROGRAMME, str(chemin))
        self._trouvaille = trouvaille
        if trouvaille.archive is not None:
            self.installer()
        else:
            self._verifier(trouvaille.programme)

    def installer(self) -> bool:
        """Décompresse le zip trouvé ou choisi dans le dossier des programmes de l'app (en arrière-plan),
        puis vérifie que video-compare démarre. Renvoie True si l'installation commence."""
        archive = self._trouvaille.archive
        if archive is None or self._occupe:
            return False
        self._avancee_installation = 0.0
        self._occuper(True, self.bouton_installer)
        self._actualiser_programme()
        taches.lancer_avec_progres(
            lambda progres: installer(archive, progres),
            self._installe,
            self._installation_echouee,
            self._progres_installation,
        )
        return True

    def _progres_installation(self, fraction: float) -> None:
        self._avancee_installation = fraction
        self._actualiser_programme()

    def _installe(self, programme: Path) -> None:
        self._avancee_installation = None
        self._occuper(False)
        self._preferences.ecrire(PREF_PROGRAMME, str(programme))
        self._trouvaille = Trouvaille(programme=programme, ou="installé par l'app")
        self._verifier(programme)

    def _installation_echouee(self, erreur: Exception) -> None:
        self._avancee_installation = None
        self._occuper(False)
        self._titre_erreur = "Installation de video-compare impossible"
        self._erreur_programme = str(erreur) if isinstance(erreur, VideoCompareIntrouvable) else f"Impossible d'installer video-compare : {erreur}"
        self._actualiser_programme()

    def _actualiser_programme(self) -> None:
        """L'état de video-compare : prêt (vert), à installer (orange), introuvable ou en panne (rouge)."""
        video_compare, trouvaille = self._video_compare, self._trouvaille
        installer_visible = page_visible = False
        if self._avancee_installation is not None:
            etat, role = f"Installation de video-compare… {round(self._avancee_installation * 100)} %", "secondaire"
            detail = f"Décompressé depuis « {trouvaille.archive.name if trouvaille.archive else ''} », dans le dossier des programmes de l'app."
        elif self._occupe:
            etat, role, detail = "Vérification de video-compare…", "secondaire", ""
        elif video_compare is not None:
            etat, role = f"{video_compare.nom()} : prêt", "succes"
            detail = chemin_a_afficher(video_compare.chemin.parent)
            if video_compare.version != VERSION_TESTEE:
                detail += f" · version testée avec l'app : {VERSION_TESTEE}"
        elif self._erreur_programme:
            etat, role, detail = self._titre_erreur or "video-compare introuvable", "erreur", self._erreur_programme
            page_visible = True
        elif trouvaille.archive is not None:
            etat = f"video-compare trouvé {trouvaille.ou} : {trouvaille.archive.name}" if trouvaille.ou != "choisi" else f"video-compare : {trouvaille.archive.name}"
            role, detail = "avertissement", "« Installer » le décompresse dans le dossier des programmes de l'app ; ton zip ne bouge pas."
            installer_visible = True
        else:
            etat, role, detail = "video-compare introuvable", "erreur", DETAIL_INTROUVABLE
            page_visible = True
        self.etat_programme.setText(etat)
        self.etat_programme.setProperty("role", role)
        self.etat_programme.style().unpolish(self.etat_programme)
        self.etat_programme.style().polish(self.etat_programme)
        self.detail_programme.setText(detail)
        self.detail_programme.setVisible(bool(detail))
        self.bouton_installer.setVisible(installer_visible or self._bouton_occupe.est(self.bouton_installer))
        self.bouton_page.setVisible(page_visible)
        self._mettre_a_jour_les_boutons()

    # --- Fichiers ----------------------------------------------------------------------------

    def fichiers(self) -> tuple[Path | None, Path | None]:
        return self._gauche, self._droite

    def choisir_les_fichiers(self) -> None:
        depart = self._preferences.lire(PREF_DERNIER_DOSSIER) or str(dossier_documents())
        choix, _filtre = QFileDialog.getOpenFileNames(self, "Choisir deux vidéos ou deux images", depart, _filtre_des_fichiers())
        if choix:
            self.definir_les_fichiers([Path(chemin) for chemin in choix])

    def changer_le_fichier(self, cote: str) -> None:
        actuel = self._gauche if cote == "gauche" else self._droite
        depart = str(actuel.parent) if actuel else (self._preferences.lire(PREF_DERNIER_DOSSIER) or str(dossier_documents()))
        titre = "Fichier de gauche (la référence)" if cote == "gauche" else "Fichier de droite"
        choix, _filtre = QFileDialog.getOpenFileName(self, titre, depart, _filtre_des_fichiers())
        if choix:
            if cote == "gauche":
                self._gauche = Path(choix)
            else:
                self._droite = Path(choix)
            self._fichiers_changes()

    def definir_les_fichiers(self, chemins: list[Path]) -> None:
        """Deux fichiers ou plus : les deux premiers, à gauche puis à droite. Un seul : il prend la
        première place libre (à gauche, puis à droite), sinon celle de droite."""
        chemins = [chemin for chemin in dict.fromkeys(chemins) if chemin.suffix.lower() in EXTENSIONS]
        if not chemins:
            return
        if len(chemins) >= 2:
            self._gauche, self._droite = chemins[0], chemins[1]
        elif self._gauche is None:
            self._gauche = chemins[0]
        else:
            self._droite = chemins[0]
        self._fichiers_changes()

    def echanger(self) -> None:
        self._gauche, self._droite = self._droite, self._gauche
        self._actualiser_fichiers()

    def vider(self) -> None:
        self._gauche = self._droite = None
        self._actualiser_fichiers()

    def _fichiers_changes(self) -> None:
        """Les fichiers changent : leur taille (et durée) lue en arrière-plan, puis l'affichage."""
        presents = [chemin for chemin in (self._gauche, self._droite) if chemin is not None]
        if presents:
            self._preferences.ecrire(PREF_DERNIER_DOSSIER, str(presents[-1].parent))
        a_lire = [chemin for chemin in presents if chemin not in self._infos]
        self._actualiser_fichiers()
        if a_lire:
            self._lecture += 1
            numero = self._lecture
            taches.lancer(
                lambda: {chemin: lire_le_fichier(chemin) for chemin in a_lire},
                lambda infos, n=numero: self._fichiers_lus(n, infos),
                lambda erreur: journal.warning("Lecture des fichiers à comparer impossible : %s", erreur),
            )

    def _fichiers_lus(self, numero: int, infos: dict[Path, str]) -> None:
        self._infos.update(infos)
        if numero == self._lecture:
            self._actualiser_fichiers()

    def _actualiser_fichiers(self) -> None:
        avec = self._gauche is not None or self._droite is not None
        self.zone_depot.setVisible(not avec)
        self.zone_fichiers.setVisible(avec)
        self.ligne_fichiers.setVisible(avec)
        for cote, chemin in (("gauche", self._gauche), ("droite", self._droite)):
            if chemin is None:
                self.noms[cote].setText("Aucun fichier : « Changer… », ou glisse-le sur la page")
                self.infos[cote].setText("")
            else:
                self.noms[cote].setText(chemin.name)
                info = self._infos.get(chemin, "lecture…")
                self.infos[cote].setText(f"{info} · {chemin_a_afficher(chemin.parent)}")
            self.noms[cote].setToolTip(str(chemin) if chemin else "")
        self.bouton_echanger.setEnabled(self._gauche is not None and self._droite is not None)
        self._mettre_a_jour_les_boutons()

    def dragEnterEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        donnees = evenement.mimeData()
        if donnees.hasUrls() and fichiers_deposes(donnees, EXTENSIONS):
            evenement.acceptProposedAction()
            self.zone_depot.survol(True)

    def dragLeaveEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        super().dragLeaveEvent(evenement)

    def dropEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        chemins = fichiers_deposes(evenement.mimeData(), EXTENSIONS)
        if chemins:
            evenement.acceptProposedAction()
            self.definir_les_fichiers(chemins)

    # --- Comparer ----------------------------------------------------------------------------

    def reglages(self) -> Reglages:
        return Reglages(self.disposition.currentData(), self.fenetre.currentData(), self.decalage.value(), self.boucle.isChecked(), self.difference.isChecked())

    def comparaison_ouverte(self) -> bool:
        return self._comparaison is not None and self._comparaison.ouverte()

    def comparer(self) -> bool:
        """Ouvre la fenêtre de video-compare avec les deux fichiers. Renvoie True si elle s'ouvre."""
        video_compare, gauche, droite = self._video_compare, self._gauche, self._droite
        if video_compare is None or gauche is None or droite is None or self.comparaison_ouverte() or self._occupe:
            return False
        manquants = [chemin.name for chemin in (gauche, droite) if not chemin.is_file()]
        if manquants:
            self._afficher(f"Fichier introuvable : {', '.join(manquants)} (déplacé ou effacé ?).", "erreur")
            return False
        commande = arguments(video_compare, gauche, droite, self.reglages())
        try:
            comparaison = Comparaison(commande, gauche.parent)
        except OSError as erreur:
            self._afficher(f"Impossible de lancer video-compare : {erreur}", "erreur")
            return False
        journal.info("video-compare : %s", commande)
        self._comparaison, self._fermeture_demandee = comparaison, False
        self._dossier_des_captures = gauche.parent
        self._mesures = []
        self._remplir_les_mesures()
        self.captures.setText("")
        self.bouton_captures.hide()
        self._afficher("", "secondaire")
        taches.lancer_avec_progres(
            comparaison.lire,
            lambda code, c=comparaison: self._fermee(c, code),
            lambda erreur, c=comparaison: self._fermee(c, None, erreur),
            lambda ligne, c=comparaison: self._ligne_recue(c, ligne),
        )
        self._actualiser_comparaison()
        return True

    def fermer_la_comparaison(self) -> None:
        if self.comparaison_ouverte():
            self._fermeture_demandee = True
            self._comparaison.fermer()

    def arreter(self) -> None:
        """À la fermeture de l'app : la fenêtre de video-compare se ferme aussi."""
        self.fermer_la_comparaison()

    def _ligne_recue(self, comparaison: Comparaison, ligne: str) -> None:
        if comparaison is not self._comparaison:
            return
        mesures = lire_les_mesures(ligne)
        captures = lire_les_captures(ligne)
        if mesures is not None:
            self._mesures.append(mesures)
            self._remplir_les_mesures()
        elif captures is not None:
            dossier = comparaison.dossier_des_captures
            noms = " · ".join(captures)
            self.captures.setText(f"Captures enregistrées dans « {dossier.name} » : {noms}")
            self.captures.setToolTip(str(dossier))
            self.cadre_mesures.show()
            self.bouton_captures.show()
        else:
            journal.debug("video-compare : %s", ligne)

    def _fermee(self, comparaison: Comparaison, code: int | None, erreur: Exception | None = None) -> None:
        if comparaison is not self._comparaison:
            return
        self._comparaison = None
        if erreur is not None:
            self._afficher(f"video-compare : {erreur}", "erreur")
        elif code not in (0, None) and not self._fermeture_demandee:
            derniere = comparaison.dernieres_lignes[-1] if comparaison.dernieres_lignes else f"code {code}"
            self._afficher(f"video-compare s'est arrêté : {derniere}", "erreur")
        self._actualiser_comparaison()

    def ouvrir_le_dossier_des_captures(self) -> None:
        dossier = self._dossier_des_captures
        if dossier is not None and dossier.is_dir():
            ouvrir_dossier(dossier)

    def _remplir_les_mesures(self) -> None:
        self.tableau_mesures.setRowCount(len(self._mesures))
        for rang, mesures in enumerate(self._mesures):
            moment = mesures.moment() + (" (zone visible)" if mesures.zone else "")
            cases = (moment, mesures.ssim_lisible(), mesures.psnr_lisible(), mesures.vmaf_lisible())
            for colonne, texte in enumerate(cases):
                case = QTableWidgetItem(texte)
                if COLONNES_MESURES[colonne].a_droite:
                    case.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tableau_mesures.setItem(rang, colonne, case)
        self.tableau_mesures.contenu_change()
        self.tableau_mesures.setVisible(bool(self._mesures))
        hauteur = self.tableau_mesures.horizontalHeader().sizeHint().height() + len(self._mesures) * Hauteurs.LIGNE_TABLEAU
        self.tableau_mesures.setFixedHeight(min(Dimensions.TABLEAU_HAUTEUR_MIN, hauteur))
        if self._mesures:
            self.cadre_mesures.show()
            self.tableau_mesures.scrollToBottom()

    def _actualiser_comparaison(self) -> None:
        ouverte = self.comparaison_ouverte()
        self.bouton_fermer.setVisible(ouverte)
        self.etat_comparaison.setText("Comparaison ouverte dans la fenêtre de video-compare : Échap pour la fermer." if ouverte else "")
        self.etat_comparaison.setVisible(ouverte)
        self._mettre_a_jour_les_boutons()

    def _mettre_a_jour_les_boutons(self) -> None:
        actif = self._bouton_occupe.est
        pret = self._video_compare is not None and self._gauche is not None and self._droite is not None
        ouverte = self.comparaison_ouverte()
        self.bouton_comparer.setEnabled(pret and not ouverte and not self._occupe)
        if self._video_compare is None:
            self.bouton_comparer.setToolTip("Il faut d'abord video-compare (en haut de la page).")
        elif self._gauche is None or self._droite is None:
            self.bouton_comparer.setToolTip("Choisis deux vidéos ou deux images.")
        elif ouverte:
            self.bouton_comparer.setToolTip("Une comparaison est ouverte : ferme sa fenêtre (Échap) pour en lancer une autre.")
        else:
            self.bouton_comparer.setToolTip("")
        self.bouton_choisir_programme.setEnabled(not self._occupe or actif(self.bouton_choisir_programme))
        self.bouton_installer.setEnabled(not self._occupe or actif(self.bouton_installer))

    # --- Outils ------------------------------------------------------------------------------

    def _occuper(self, occupe: bool, bouton_occupe=None) -> None:
        """Pendant l'installation ou la vérification de video-compare : le cercle tourne dans le bouton
        qui a lancé le travail (V3.1)."""
        self._occupe = occupe
        if occupe:
            self._bouton_occupe.occuper(bouton_occupe)
        else:
            self._bouton_occupe.liberer()
        self._mettre_a_jour_les_boutons()

    def _afficher(self, message: str, role: str) -> None:
        # Vert, rouge ou orange : effacé après 8 s (V3.2) ; la ligne garde sa place.
        afficher_message(self.statut, message, role, cacher_vide=False)
