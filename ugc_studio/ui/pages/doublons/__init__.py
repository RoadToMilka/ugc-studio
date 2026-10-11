"""Module Doublons (V4.3 ; cahier des charges §8 bis.5 ; document « UGC Studio - V4.3 Doublons ») : les
photos en double ou trop proches, dans un ou plusieurs dossiers. Le calcul est dans ugc_studio/doublons.

Le parcours, de haut en bas :
1. Dossiers : glisser-déposer un ou plusieurs dossiers (ou des photos : leur dossier), ou « Ajouter un
   dossier… » ; × retire un dossier de la liste (les photos ne bougent pas). « Inclure les
   sous-dossiers », « Méthode » (copies seulement, sans IA, ou avec IA) et, à partir de deux dossiers,
   « Comparer » (dans chaque dossier, entre les dossiers, les deux).
2. « Analyser » : avancement et « Arrêter ». La première fois, l'app prépare ses bibliothèques de calcul ;
   avec l'IA, le modèle décrit chaque photo (droite et retournée).
3. Paires : le seuil (le tableau le suit tout de suite, sans refaire l'analyse), un résumé, le tableau
   (deux vignettes, proximité, type, les deux noms, leurs dossiers).
4. Comparaison : la paire choisie, à côté du tableau en grande fenêtre (dessous sinon) ; ↑ et ↓ ;
   « Agrandir » (ou double-clic) ; ⋯ : l'Explorateur, ou les deux dans le module Comparer.

Rien n'est modifié : au lot 1 (4.3.0), le module ne fait que lire les photos. Il ne dépend pas d'un projet :
ses réglages sont retenus dans les préférences de l'app. numpy et ONNX Runtime ne sont chargés qu'à la
première analyse (jamais au démarrage de l'app).
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QBoxLayout, QFileDialog, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget
from shiboken6 import isValid

from ....chemins import dossier_documents
from ....doublons.choix import (
    AVEC_IA,
    COMPARAISON,
    IA,
    IDENTIQUES,
    LECTURE,
    LES_DEUX,
    MAX_PAIRES,
    MEME_PHOTO,
    METHODE_DE_DEPART,
    METHODES,
    MODE_DE_DEPART,
    MODELE,
    MODES,
    NOMS_DES_CAS,
    PREPARATION,
    RESSEMBLANTES,
    SANS_IA,
    SEUIL_DE_DEPART,
    SEUIL_DES_COPIES,
    SEUIL_DES_VRAIS_DOUBLONS,
    SEUIL_MAX,
    SEUIL_MIN,
)
from ....doublons.photos import Photo, lister_les_photos
from ....dossiers import EXTENSIONS_IMAGES
from ....images.redimensionnement import quantite
from ....images.vignettes import faire_les_vignettes
from ....services import Services
from ... import taches
from ...composants.barre_avancement import BarreAvancement
from ...composants.bouton import BoutonOccupe
from ...composants.choix import ChoixEnBoutons
from ...composants.depot_dossier import ZoneDepotDossier
from ...composants.elements import (
    afficher_message,
    bloc,
    bouton,
    case_a_cocher,
    champ_entier,
    champ_nomme,
    glissiere,
    libelle,
    libelle_abrege,
    vider_disposition,
)
from ...composants.menu import Menu
from ...composants.tableau import Tableau
from ...icones import icone, icone_menu
from ...ouvrir import montrer_dans_l_explorateur
from ...theme import Dimensions, Espacements, Hauteurs
from ..base import Page
from ..renommer.grille import qimage_depuis_pillow
from .agrandir import FenetrePaireEnGrand
from .comparaison import DeuxPhotos, FichePhoto
from .tableau import (
    COLONNE_DOSSIERS,
    COLONNE_IMAGE_1,
    COLONNE_IMAGE_2,
    COLONNE_PHOTOS,
    COLONNE_PROXIMITE,
    COLONNE_TYPE,
    COLONNES,
    ROLE_PHOTOS,
    DelegueVignettes,
    cle,
    texte_des_dossiers,
    texte_du_type,
)

TITRE = "Doublons"
SOUS_TITRE = "Les photos en double ou trop proches, dans un ou plusieurs dossiers."

# Préférences (§10) : ce module ne dépend pas d'un projet.
PREF_DOSSIER = "doublons_dossier"  # le dernier dossier ajouté : point de départ de « Ajouter un dossier… »
PREF_SOUS_DOSSIERS = "doublons_sous_dossiers"
PREF_METHODE = "doublons_methode"
PREF_MODE = "doublons_mode"
PREF_SEUIL = "doublons_seuil"

FORMATS_ACCEPTES = "JPG, PNG, WebP, AVIF, TIFF ou BMP"

AIDE_DOSSIERS = (
    "Les photos de chaque dossier ajouté (JPG, PNG, WebP, AVIF, TIFF, BMP). L'analyse ne fait que lire tes "
    "photos : elle ne les modifie jamais."
)
AIDE_SOUS_DOSSIERS = "Aussi les photos de leurs sous-dossiers : elles comptent pour le dossier ajouté."
AIDE_METHODE = (
    "Copies seulement : les fichiers identiques et les copies d'une même photo (autre taille, compression, "
    "couleurs, miroir, bords ajoutés), prouvées sans IA, toutes montrées. Avec IA : aussi les photos que l'IA "
    "juge proches, au-dessus du seuil (la même photo rognée ou zoomée, des prises presque identiques)."
)
AIDE_COMPARER = (
    "Dans chaque dossier : les photos d'un même dossier entre elles. Entre les dossiers : chaque photo avec "
    "celles des autres dossiers. Les deux : toutes les paires."
)
AIDE_PAIRES = (
    "Une ligne par paire, les plus proches en haut. 100 % : identiques. 95 à 99 % : la même photo, modifiée "
    "(prouvé sans IA). 94 % au plus : des photos proches, estimé par l'IA."
)
AIDE_SEUIL = (
    "Avec l'IA, les paires moins proches que le seuil ne sont pas montrées. Le tableau suit le seuil tout de "
    f"suite. {SEUIL_DES_VRAIS_DOUBLONS} % : le plus bas pour ne trouver que de vrais doublons (réglé sur tes photos "
    "de clients) ; en dessous, surtout des photos qui se ressemblent sans être des doublons. Copies seulement : "
    "pas de seuil, toutes les copies sont montrées."
)
TEXTE_VRAIS_DOUBLONS = f"Vrais doublons : {SEUIL_DES_VRAIS_DOUBLONS} % au moins"
ALERTE_SOUS_LES_VRAIS_DOUBLONS = (
    f"Sous {SEUIL_DES_VRAIS_DOUBLONS} % : surtout des photos qui se ressemblent sans être des doublons, comme le "
    f"même produit chez un autre client. Remets {SEUIL_DES_VRAIS_DOUBLONS} % pour ne garder que les vrais doublons."
)
AIDE_COMPARAISON = (
    "La paire choisie dans le tableau. Flèches ↑ et ↓ : la paire précédente ou suivante. Double-clic sur une "
    "ligne, ou « Agrandir » : les deux photos en grand."
)

TEXTE_SANS_ANALYSE = "Clique « Analyser » pour chercher les doublons."
TEXTE_SANS_PAIRE_CHOISIE = "Choisis une paire dans le tableau."


def _pluriel(nombre: int, singulier: str, pluriel: str) -> str:
    return f"{nombre} {singulier if nombre == 1 else pluriel}"


def texte_du_resume(nombre_photos: int, nombre_dossiers: int, seuil: int | None, selection, copies_seulement: bool) -> str:
    """« 163 images dans 1 dossier · 43 paires à 85 % ou plus : 42 identiques, 1 même photo. » ; sans seuil
    (copies seulement) : « 163 images dans 1 dossier · 43 paires de copies : 42 identiques, 1 même photo. »"""
    debut = f"{quantite(nombre_photos, 'image')} dans {quantite(nombre_dossiers, 'dossier')}"
    if not selection.total:
        if seuil is None:
            return f"{debut} · Aucune copie."
        if copies_seulement:
            return f"{debut} · Aucune copie à {seuil} % ou plus."
        if seuil >= SEUIL_DES_VRAIS_DOUBLONS:
            return f"{debut} · Aucune paire à {seuil} % ou plus : pas de doublon."
        return f"{debut} · Aucune paire à {seuil} % ou plus."
    parties = []
    for genre, singulier, pluriel in (
        (IDENTIQUES, "identique", "identiques"),
        (MEME_PHOTO, "même photo", "mêmes photos"),
        (RESSEMBLANTES, "ressemblante", "ressemblantes"),
    ):
        nombre = selection.compte(genre)
        if nombre:
            parties.append(_pluriel(nombre, singulier, pluriel))
    if seuil is None:
        return f"{debut} · {quantite(selection.total, 'paire')} de copies : {', '.join(parties)}."
    return f"{debut} · {quantite(selection.total, 'paire')} à {seuil} % ou plus : {', '.join(parties)}."


def texte_des_illisibles(illisibles) -> str:
    """« 2 fichiers illisibles, ignorés : a.jpg, b.png. »"""
    if not illisibles:
        return ""
    noms = ", ".join(photo.chemin.name for photo, _raison in illisibles[:3])
    suite = "…" if len(illisibles) > 3 else ""
    pluriel = "s" if len(illisibles) > 1 else ""
    return f"{quantite(len(illisibles), 'fichier')} illisible{pluriel}, ignoré{pluriel} : {noms}{suite}."


def duree_lisible(secondes: float) -> str:
    """« moins d'une seconde », « 12 s », « 1 min 05 s »."""
    if secondes < 1:
        return "moins d'une seconde"
    entieres = round(secondes)
    if entieres < 60:
        return f"{entieres} s"
    return f"{entieres // 60} min {entieres % 60:02d} s"


def dossiers_deposes(donnees) -> list[Path]:
    """Les dossiers glissés sur la page, et ceux des photos glissées (chacun une fois, dans l'ordre)."""
    trouves: list[Path] = []
    for url in donnees.urls():
        if not url.isLocalFile():
            continue
        chemin = Path(url.toLocalFile())
        dossier = chemin if chemin.is_dir() else chemin.parent if chemin.suffix.lower() in EXTENSIONS_IMAGES else None
        if dossier is not None and dossier not in trouves:
            trouves.append(dossier)
    return trouves


class CoteACoteOuDessous(QWidget):
    """Deux blocs côte à côte quand la page est assez large, l'un sous l'autre sinon (fenêtre étroite).

    Assez large : au moins Dimensions.DOUBLONS_COTE_A_COTE_MIN, et au moins ce que demandent les deux
    blocs côte à côte (largeur_cote_a_cote). Comme pour le studio des sous-titres, la largeur minimale
    annoncée est celle des blocs l'un sous l'autre : sinon, côte à côte, la disposition ne pourrait pas
    devenir plus étroite que ses deux blocs, ne repasserait jamais l'un sous l'autre, et le bord droit de
    la page serait coupé (relu sur les captures à 125 et 150 % : 327 px de trop)."""

    def __init__(self, premier: QWidget, second: QWidget):
        super().__init__()
        self._premier, self._second = premier, second
        self._disposition = QBoxLayout(QBoxLayout.Direction.TopToBottom, self)
        self._disposition.setContentsMargins(0, 0, 0, 0)
        self._disposition.setSpacing(Dimensions.ESPACE_BLOCS)
        # Côte à côte, le tableau (cinq colonnes) reçoit un peu plus de place que la comparaison.
        self._disposition.addWidget(premier, 3)
        self._disposition.addWidget(second, 2)

    @property
    def cote_a_cote(self) -> bool:
        return self._disposition.direction() == QBoxLayout.Direction.LeftToRight

    def largeur_cote_a_cote(self) -> int:
        """La largeur qu'il faut pour les deux blocs côte à côte : leurs largeurs minimales et l'espace
        entre eux, et au moins DOUBLONS_COTE_A_COTE_MIN."""
        besoin = self._premier.minimumSizeHint().width() + self._disposition.spacing() + self._second.minimumSizeHint().width()
        return max(Dimensions.DOUBLONS_COTE_A_COTE_MIN, besoin)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 : nom imposé par Qt
        """Largeur minimale : celle des deux blocs l'un sous l'autre (voir la description de la classe)."""
        largeur = max(self._premier.minimumSizeHint().width(), self._second.minimumSizeHint().width())
        return QSize(largeur, super().minimumSizeHint().height())

    def resizeEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        super().resizeEvent(evenement)
        self._adapter()

    def _adapter(self) -> None:
        # Pour passer côte à côte, il faut un peu plus de place que pour y rester : sans cette marge, la
        # barre de défilement de la page, qui apparaît ou disparaît avec la disposition, pourrait la faire
        # changer en boucle autour de la limite.
        marge = 0 if self.cote_a_cote else Dimensions.BARRE_DEFILEMENT + Espacements.S
        voulue = QBoxLayout.Direction.LeftToRight if self.width() >= self.largeur_cote_a_cote() + marge else QBoxLayout.Direction.TopToBottom
        if self._disposition.direction() != voulue:
            self._disposition.setDirection(voulue)
            self.updateGeometry()  # la hauteur minimale change avec la disposition


class PageDoublons(Page):
    # « Ouvrir les deux dans Comparer » : la fenêtre ouvre le module Comparer sur les deux photos.
    comparer_demande = Signal(object)

    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="doublons")
        self._preferences = services.preferences
        self._dossiers: list[Path] = []
        self._resultat = None  # le dernier résultat (doublons/analyse.py : Resultat)
        self._memoire = None  # ce qui a été lu pendant la séance (doublons/analyse.py : Memoire)
        self._selection = None
        self._arret: threading.Event | None = None
        self._arret_vignettes: threading.Event | None = None
        self._vignettes: dict[str, QPixmap] = {}
        self._occupe = False
        self._bouton_occupe = BoutonOccupe()
        self._fenetre_en_grand: FenetrePaireEnGrand | None = None
        self._dernieres_paires: list = []  # les paires du tableau, pour y retrouver la paire choisie
        self.setAcceptDrops(True)

        # --- Dossiers ---
        self.cadre_dossiers, d = bloc("Dossiers", aide=AIDE_DOSSIERS)
        self.zone_depot = ZoneDepotDossier(
            "Glisse un ou plusieurs dossiers de photos ici", FORMATS_ACCEPTES, self.choisir_dossier, "Ajouter un dossier…"
        )
        d.addWidget(self.zone_depot)
        self.liste_dossiers = QWidget()
        self._lignes_dossiers = QVBoxLayout(self.liste_dossiers)
        self._lignes_dossiers.setContentsMargins(0, 0, 0, 0)
        self._lignes_dossiers.setSpacing(Espacements.S)
        d.addWidget(self.liste_dossiers)
        self.ligne_ajout = QWidget()
        ligne = QHBoxLayout(self.ligne_ajout)
        ligne.setContentsMargins(0, 0, 0, 0)
        self.bouton_ajouter = bouton("Ajouter un dossier…", variante="contour", nom_icone="folder-plus", action=self.choisir_dossier)
        ligne.addWidget(self.bouton_ajouter)
        ligne.addStretch(1)
        d.addWidget(self.ligne_ajout)
        self.zone_sous_dossiers, self.case_sous_dossiers = case_a_cocher("Inclure les sous-dossiers", AIDE_SOUS_DOSSIERS)
        self.case_sous_dossiers.setChecked(self._preferences.lire(PREF_SOUS_DOSSIERS, False) is True)
        d.addWidget(self.zone_sous_dossiers)
        self.methode = ChoixEnBoutons(METHODES)
        self.methode.definir(self._valeur(PREF_METHODE, METHODES, METHODE_DE_DEPART))
        self.champ_methode = champ_nomme("Méthode", self.methode, aide=AIDE_METHODE)
        d.addWidget(self.champ_methode)
        self.mode = ChoixEnBoutons(MODES)
        self.mode.definir(self._valeur(PREF_MODE, MODES, MODE_DE_DEPART))
        self.champ_mode = champ_nomme("Comparer", self.mode, aide=AIDE_COMPARER)
        d.addWidget(self.champ_mode)
        self.contenu.addWidget(self.cadre_dossiers)

        # --- Analyser ---
        action = QVBoxLayout()
        action.setSpacing(Espacements.S)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_analyser = bouton("Analyser", variante="principal", nom_icone="scan-search", action=self.analyser)
        boutons.addWidget(self.bouton_analyser)
        self.bouton_arreter = bouton("Arrêter", nom_icone="square", action=self.arreter)
        self.bouton_arreter.hide()
        boutons.addWidget(self.bouton_arreter)
        boutons.addStretch(1)
        action.addLayout(boutons)
        self.zone_avancement = QWidget()
        avancement = QVBoxLayout(self.zone_avancement)
        avancement.setContentsMargins(0, 0, 0, 0)
        avancement.setSpacing(Espacements.S)
        self.barre = BarreAvancement()
        avancement.addWidget(self.barre)
        self.avancee = libelle("", "legende")
        avancement.addWidget(self.avancee)
        self.zone_avancement.hide()
        action.addWidget(self.zone_avancement)
        self.statut = libelle("", "secondaire")
        action.addWidget(self.statut)
        self.contenu.addLayout(action)

        # --- Paires ---
        self.cadre_paires, d = bloc("Paires", aide=AIDE_PAIRES)
        seuil = QHBoxLayout()
        seuil.setSpacing(Espacements.M)
        self.barre_seuil = glissiere()
        self.barre_seuil.setRange(SEUIL_MIN, SEUIL_MAX)
        self.barre_seuil.setFixedWidth(Dimensions.DOUBLONS_SEUIL_LARGEUR)
        seuil.addWidget(self.barre_seuil)
        self.champ_seuil = champ_entier(SEUIL_MIN, SEUIL_MAX, " %")
        seuil.addWidget(self.champ_seuil)
        # Le rappel demandé par l'utilisateur (11/10/2026, 21 h 28) : ne pas descendre plus bas pour ne
        # trouver que de vrais doublons.
        self.rappel_seuil = libelle(TEXTE_VRAIS_DOUBLONS, "legende", retour_a_la_ligne=False)
        seuil.addWidget(self.rappel_seuil)
        seuil.addStretch(1)
        valeur = self._preferences.lire(PREF_SEUIL, SEUIL_DE_DEPART)
        valeur = valeur if isinstance(valeur, int) and SEUIL_MIN <= valeur <= SEUIL_MAX else SEUIL_DE_DEPART
        self.barre_seuil.setValue(valeur)
        self.champ_seuil.setValue(valeur)
        # Le seuil ne sert qu'avec l'IA : sans elle, toutes les paires sont des copies prouvées (95 à 100 %),
        # toutes montrées (question de l'utilisateur du 11/10/2026, 21 h 14).
        self.zone_seuil = champ_nomme("Seuil", seuil, aide=AIDE_SEUIL)
        d.addWidget(self.zone_seuil)
        self.resume = libelle(TEXTE_SANS_ANALYSE, "secondaire")
        d.addWidget(self.resume)
        self.alertes = libelle("", "avertissement")
        self.alertes.hide()
        d.addWidget(self.alertes)
        self.tableau = Tableau(COLONNES)
        self.tableau.setItemDelegateForColumn(COLONNE_PHOTOS, DelegueVignettes(self._vignettes, self.tableau))
        # Un clic sur une ligne donne la main au tableau : ↑ et ↓ passent alors d'une paire à l'autre.
        self.tableau.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        # Un nom trop long est abrégé au milieu : son numéro et son extension restent lisibles
        # (« TestCl…_42.jpg »), comme sous les vignettes de Renommer.
        self.tableau.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tableau.hide()
        d.addWidget(self.tableau)

        # --- Comparaison ---
        self.cadre_comparaison, d = bloc("Comparaison", aide=AIDE_COMPARAISON)
        self.description = libelle_abrege("", "secondaire")
        d.addWidget(self.description)
        self.deux_photos = DeuxPhotos()
        d.addWidget(self.deux_photos)
        self.vide = libelle(TEXTE_SANS_PAIRE_CHOISIE, "discret")
        d.addWidget(self.vide)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_precedente = bouton("Précédente", variante="contour", nom_icone="chevron-up", action=lambda: self.aller(-1))
        boutons.addWidget(self.bouton_precedente)
        self.bouton_suivante = bouton("Suivante", variante="contour", nom_icone="chevron-down", action=lambda: self.aller(1))
        boutons.addWidget(self.bouton_suivante)
        self.bouton_agrandir = bouton("Agrandir", variante="contour", nom_icone="maximize-2", action=self.agrandir)
        boutons.addWidget(self.bouton_agrandir)
        boutons.addStretch(1)
        self.bouton_plus = bouton("", variante="icone")
        self.bouton_plus.setIcon(icone("ellipsis"))
        self.bouton_plus.setIconSize(QSize(Dimensions.ICONE, Dimensions.ICONE))
        self.bouton_plus.setToolTip("Plus d'actions")
        menu = Menu(self.bouton_plus)
        menu.addAction(icone_menu("folder-open"), "Afficher l'image 1 dans l'Explorateur").triggered.connect(lambda: self.montrer_dans_l_explorateur(0))
        menu.addAction(icone_menu("folder-open"), "Afficher l'image 2 dans l'Explorateur").triggered.connect(lambda: self.montrer_dans_l_explorateur(1))
        menu.addAction(icone_menu("square-split-horizontal"), "Ouvrir les deux dans Comparer").triggered.connect(self.ouvrir_dans_comparer)
        self.bouton_plus.setMenu(menu)
        boutons.addWidget(self.bouton_plus)
        d.addLayout(boutons)

        self.resultats = CoteACoteOuDessous(self.cadre_paires, self.cadre_comparaison)
        self.contenu.addWidget(self.resultats)

        self.case_sous_dossiers.toggled.connect(self._sous_dossiers_change)
        self.methode.change.connect(self._methode_changee)
        self.mode.change.connect(self._mode_change)
        self.barre_seuil.valueChanged.connect(self._seuil_glisse)
        self.champ_seuil.valueChanged.connect(self._seuil_tape)
        self.tableau.currentCellChanged.connect(lambda rang, _colonne, _avant, _colonne_avant: self._paire_choisie(rang))
        self.tableau.cellDoubleClicked.connect(lambda rang, _colonne: self.agrandir(rang))
        self._actualiser_les_dossiers()
        self._actualiser_les_paires()

    def _valeur(self, preference: str, choix: dict, defaut: str) -> str:
        valeur = self._preferences.lire(preference, defaut)
        return valeur if valeur in choix else defaut

    @property
    def occupe(self) -> bool:
        return self._occupe

    @property
    def dossiers(self) -> list[Path]:
        return list(self._dossiers)

    @property
    def resultat(self):
        return self._resultat

    # --- Dossiers -----------------------------------------------------------------------------

    def choisir_dossier(self) -> None:
        if self._occupe:
            return
        depart = self._preferences.lire(PREF_DOSSIER) or str(dossier_documents())
        choix = QFileDialog.getExistingDirectory(self, "Ajouter un dossier de photos", str(depart))
        if choix:
            self.ajouter([Path(choix)])

    def ajouter(self, dossiers: list[Path]) -> int:
        """Ajoute ces dossiers à la liste (un dossier déjà présent ne l'est pas deux fois). Renvoie le
        nombre de dossiers ajoutés."""
        if self._occupe:
            return 0
        ajoutes = 0
        for dossier in dossiers:
            if dossier.is_dir() and not any(_meme_chemin(dossier, autre) for autre in self._dossiers):
                self._dossiers.append(dossier)
                ajoutes += 1
        if ajoutes:
            self._preferences.ecrire(PREF_DOSSIER, str(self._dossiers[-1]))
            self._dossiers_changes()
        return ajoutes

    def retirer(self, dossier: Path) -> None:
        """× : le dossier quitte la liste (ses photos ne bougent pas)."""
        if self._occupe or dossier not in self._dossiers:
            return
        self._dossiers.remove(dossier)
        self._dossiers_changes()

    def _dossiers_changes(self) -> None:
        """La liste a changé : le résultat de l'analyse précédente ne vaut plus (« Analyser » à nouveau)."""
        self._oublier_le_resultat()
        self._actualiser_les_dossiers()
        self._actualiser_les_paires()

    def _sous_dossiers_change(self, coche: bool) -> None:
        self._preferences.ecrire(PREF_SOUS_DOSSIERS, bool(coche))
        if self._dossiers:
            self._dossiers_changes()

    def _actualiser_les_dossiers(self) -> None:
        vider_disposition(self._lignes_dossiers)
        sous_dossiers = self.case_sous_dossiers.isChecked()
        for dossier in self._dossiers:
            self._lignes_dossiers.addWidget(self._ligne_de_dossier(dossier, len(lister_les_photos([dossier], sous_dossiers))))
        avec = bool(self._dossiers)
        self.zone_depot.setVisible(not avec)
        self.liste_dossiers.setVisible(avec)
        self.ligne_ajout.setVisible(avec)
        self.champ_mode.setVisible(len(self._dossiers) >= 2)
        self._mettre_a_jour_les_boutons()

    def _ligne_de_dossier(self, dossier: Path, nombre: int) -> QWidget:
        ligne = QWidget()
        disposition = QHBoxLayout(ligne)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.M)
        textes = QVBoxLayout()
        textes.setContentsMargins(0, 0, 0, 0)
        textes.setSpacing(Espacements.XS)
        nom = libelle_abrege(dossier.name or str(dossier), "intitule")
        textes.addWidget(nom)
        details = libelle_abrege(f"{quantite(nombre, 'image')} · {dossier}", "legende")
        details.setToolTip(str(dossier))
        textes.addWidget(details)
        disposition.addLayout(textes, 1)
        retirer = bouton("", variante="icone", nom_icone="x", action=lambda d=dossier: self.retirer(d))
        retirer.setToolTip("Retirer ce dossier de la liste (ses photos ne bougent pas)")
        retirer.setEnabled(not self._occupe)
        disposition.addWidget(retirer, 0, Qt.AlignmentFlag.AlignVCenter)
        return ligne

    def dragEnterEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        donnees = evenement.mimeData()
        if not self._occupe and donnees.hasUrls() and dossiers_deposes(donnees):
            evenement.acceptProposedAction()
            self.zone_depot.survol(True)

    def dragLeaveEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        super().dragLeaveEvent(evenement)

    def dropEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        dossiers = dossiers_deposes(evenement.mimeData())
        if dossiers:
            evenement.acceptProposedAction()
            self.ajouter(dossiers)

    # --- Méthode, Comparer, seuil ---------------------------------------------------------------

    def _methode_changee(self, valeur: str) -> None:
        self._preferences.ecrire(PREF_METHODE, valeur)
        self._actualiser_les_paires()

    def _mode_change(self, valeur: str) -> None:
        self._preferences.ecrire(PREF_MODE, valeur)
        self._actualiser_les_paires()

    def _seuil_glisse(self, valeur: int) -> None:
        if self.champ_seuil.value() != valeur:
            self.champ_seuil.blockSignals(True)
            self.champ_seuil.setValue(valeur)
            self.champ_seuil.blockSignals(False)
        self._seuil_change(valeur)

    def _seuil_tape(self, valeur: int) -> None:
        if self.barre_seuil.value() != valeur:
            self.barre_seuil.blockSignals(True)
            self.barre_seuil.setValue(valeur)
            self.barre_seuil.blockSignals(False)
        self._seuil_change(valeur)

    def _seuil_change(self, valeur: int) -> None:
        self._preferences.ecrire(PREF_SEUIL, valeur)
        self._actualiser_les_paires()

    def definir_le_seuil(self, valeur: int) -> None:
        self.barre_seuil.setValue(valeur)

    @property
    def seuil(self) -> int:
        return self.champ_seuil.value()

    # --- Analyser -----------------------------------------------------------------------------

    def analyser(self) -> bool:
        """Lance l'analyse des dossiers (en arrière-plan). Renvoie True si elle commence."""
        if self._occupe or not self._dossiers:
            return False
        self._arreter_les_vignettes()
        arret = threading.Event()
        self._arret = arret
        dossiers = list(self._dossiers)
        sous_dossiers = self.case_sous_dossiers.isChecked()
        avec_ia = self.methode.valeur() == AVEC_IA
        memoire = self._memoire

        def travail(progres):
            from ....doublons import bibliotheques

            if bibliotheques.bibliotheques_a_preparer():
                progres(PREPARATION)
            bibliotheques.preparer_les_bibliotheques()
            from ....doublons.analyse import Memoire, analyser

            utilisee = memoire if memoire is not None else Memoire()
            photos = lister_les_photos(dossiers, sous_dossiers)
            return analyser(photos, avec_ia, utilisee, progres, arret), utilisee

        self._afficher("", "secondaire")
        self.barre.definir(0)
        self.avancee.setText("Préparation…")
        self.zone_avancement.show()
        self.bouton_arreter.setEnabled(True)
        self.bouton_arreter.show()
        self._occuper(True, self.bouton_analyser)
        taches.lancer_avec_progres(travail, self._analyse_terminee, self._analyse_echouee, self._progres)
        return True

    def _progres(self, valeur) -> None:
        if not isValid(self):
            return
        if valeur == PREPARATION:
            self.avancee.setText("Préparation de l'analyse (la première fois seulement)…")
            return
        etape = getattr(valeur, "etape", "")
        if etape == MODELE:
            self.avancee.setText("Préparation du modèle d'IA…")
        elif etape in (IA, LECTURE):
            self.barre.definir(valeur.faites / max(1, valeur.total))
            self.avancee.setText(f"Analyse : {valeur.faites} sur {quantite(valeur.total, 'image')}")
        elif etape == COMPARAISON:
            self.barre.definir(1)
            self.avancee.setText("Comparaison des photos…")

    def arreter(self) -> None:
        """« Arrêter » : l'analyse s'arrête à la photo en cours (aussi à la fermeture de l'app)."""
        self._arreter_les_vignettes()
        if self._arret is not None and self._occupe:
            self._arret.set()
            self.bouton_arreter.setEnabled(False)
            self.avancee.setText("Arrêt en cours…")

    def _fin(self) -> None:
        self._occuper(False)
        self.zone_avancement.hide()
        self.bouton_arreter.hide()

    def _analyse_terminee(self, retour) -> None:
        if not isValid(self):
            return  # l'app se ferme
        resultat, memoire = retour
        self._fin()
        self._resultat, self._memoire = resultat, memoire
        self._actualiser_les_paires()
        self._faire_les_vignettes()
        self._afficher(f"Analyse terminée en {duree_lisible(resultat.duree_s)}.", "succes")

    def _analyse_echouee(self, erreur: Exception) -> None:
        if not isValid(self):
            return
        self._fin()
        if type(erreur).__name__ == "AnalyseArretee":
            self._afficher("Analyse arrêtée.", "avertissement")
        else:
            self._afficher(f"Impossible d'analyser ces photos : {erreur}", "erreur")
        self._actualiser_les_paires()

    def _oublier_le_resultat(self) -> None:
        self._arreter_les_vignettes()
        self._resultat = None
        self._selection = None

    # --- Paires -------------------------------------------------------------------------------

    @property
    def copies_seulement(self) -> bool:
        return self.methode.valeur() == SANS_IA

    def _actualiser_les_paires(self) -> None:
        """Le résumé et le tableau, selon le résultat, la méthode, « Comparer » et le seuil."""
        resultat = self._resultat
        alertes = []
        copies_seulement = self.copies_seulement
        self.zone_seuil.setVisible(not copies_seulement)
        if not copies_seulement and self.seuil < SEUIL_DES_VRAIS_DOUBLONS:
            alertes.append(ALERTE_SOUS_LES_VRAIS_DOUBLONS)
        if resultat is None:
            self._selection = None
            self.resume.setText(TEXTE_SANS_ANALYSE if self._dossiers else "Ajoute un ou plusieurs dossiers de photos.")
        else:
            mode = self.mode.valeur() if len(self._dossiers) >= 2 else LES_DEUX
            seuil = SEUIL_DES_COPIES if copies_seulement else self.seuil
            self._selection = resultat.paires(mode, seuil, avec_ia=not copies_seulement)
            nombre_dossiers = len({photo.dossier for photo in resultat.photos}) or len(self._dossiers)
            seuil_montre = None if copies_seulement else self.seuil
            self.resume.setText(texte_du_resume(len(resultat.photos), nombre_dossiers, seuil_montre, self._selection, copies_seulement or not resultat.avec_ia))
            if not copies_seulement and not resultat.avec_ia:
                alertes.append("Analysé sans IA : clique « Analyser » pour chercher aussi les photos proches.")
            if self._selection.tronquee:
                maximum = f"{MAX_PAIRES:,}".replace(",", " ")
                alertes.append(f"Plus de {maximum} paires : seules les {maximum} plus proches sont montrées. Monte le seuil pour n'en garder que les plus proches.")
            illisibles = texte_des_illisibles(resultat.illisibles)
            if illisibles:
                alertes.append(illisibles)
        self.alertes.setText("\n".join(alertes))
        self.alertes.setVisible(bool(alertes))
        self._remplir_le_tableau()

    def paires(self) -> list:
        """Les paires montrées dans le tableau (dans son ordre)."""
        return list(self._selection.paires) if self._selection is not None else []

    def _photo(self, numero: int) -> Photo:
        return self._resultat.photos[numero]

    def _nom_du_dossier(self, photo: Photo) -> str:
        dossier = self._dossiers[photo.dossier] if 0 <= photo.dossier < len(self._dossiers) else photo.chemin.parent
        return dossier.name or str(dossier)

    def _remplir_le_tableau(self) -> None:
        ancienne = self._paire_affichee()
        paires = self.paires()
        self._fermer_la_fenetre_en_grand()  # elle montrait les paires d'avant
        self.tableau.blockSignals(True)
        self.tableau.setRowCount(len(paires))
        plusieurs = len(self._dossiers) >= 2
        self.tableau.setColumnHidden(COLONNE_DOSSIERS, not plusieurs)
        nouveau_rang = 0
        for rang, paire in enumerate(paires):
            a, b = self._photo(paire.a), self._photo(paire.b)
            if ancienne is not None and (paire.a, paire.b) == ancienne:
                nouveau_rang = rang
            photos = QTableWidgetItem("")
            photos.setData(ROLE_PHOTOS, (cle(a.chemin), cle(b.chemin)))
            self.tableau.setItem(rang, COLONNE_PHOTOS, photos)
            proximite = QTableWidgetItem(f"{paire.proximite} %")
            proximite.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tableau.setItem(rang, COLONNE_PROXIMITE, proximite)
            # Le cas seul (le tableau reste lisible) ; ce qui change, au survol et dans la comparaison.
            cas = QTableWidgetItem(NOMS_DES_CAS.get(paire.genre, paire.genre))
            cas.setToolTip(texte_du_type(paire.genre, paire.details))
            self.tableau.setItem(rang, COLONNE_TYPE, cas)
            for colonne, photo in ((COLONNE_IMAGE_1, a), (COLONNE_IMAGE_2, b)):
                case = QTableWidgetItem(photo.chemin.name)
                case.setToolTip(str(photo.chemin))
                self.tableau.setItem(rang, colonne, case)
            self.tableau.setItem(rang, COLONNE_DOSSIERS, QTableWidgetItem(texte_des_dossiers(self._nom_du_dossier(a), self._nom_du_dossier(b))))
        self.tableau.blockSignals(False)
        self.tableau.contenu_change()
        self.tableau.setVisible(bool(paires))
        lignes = max(len(paires), 4)
        hauteur = self.tableau.horizontalHeader().sizeHint().height() + lignes * Hauteurs.LIGNE_TABLEAU + 2 * Dimensions.BORDURE
        self.tableau.setFixedHeight(min(Dimensions.DOUBLONS_TABLEAU_HAUTEUR, hauteur))
        # La même paire reste choisie si elle est encore là ; sinon, la première (la plus proche).
        self.tableau.blockSignals(True)
        if paires:
            self.tableau.selectRow(nouveau_rang)
            self.tableau.setCurrentCell(nouveau_rang, COLONNE_PROXIMITE)
        self.tableau.blockSignals(False)
        self._paire_choisie(nouveau_rang if paires else -1)

    def _paire_affichee(self) -> tuple[int, int] | None:
        rang = self.tableau.currentRow()
        if 0 <= rang < len(self._dernieres_paires):
            paire = self._dernieres_paires[rang]
            return paire.a, paire.b
        return None

    # --- Comparaison ----------------------------------------------------------------------------

    def fiche(self, numero: int) -> FichePhoto:
        photo = self._photo(numero)
        infos = self._resultat.infos[numero]
        return FichePhoto(photo.chemin, infos.largeur, infos.hauteur, infos.format, photo.octets, photo.modifiee, self._nom_du_dossier(photo))

    def description_de_la_paire(self, paire) -> str:
        """« 96 % · Même photo · autre taille » ; pour une paire estimée, la proximité vue par l'IA."""
        return f"{paire.proximite} % · {texte_du_type(paire.genre, paire.details)}"

    def _paire_choisie(self, rang: int) -> None:
        paires = self.paires()
        self._dernieres_paires = paires
        choisie = 0 <= rang < len(paires)
        self.deux_photos.setVisible(choisie)
        self.description.setVisible(choisie)
        self.vide.setVisible(not choisie)
        self.vide.setText(TEXTE_SANS_PAIRE_CHOISIE if paires else ("Aucune paire à montrer." if self._resultat is not None else TEXTE_SANS_ANALYSE))
        if choisie:
            paire = paires[rang]
            self.description.setText(f"Paire {rang + 1} sur {len(paires)} · {self.description_de_la_paire(paire)}")
            self.deux_photos.montrer(self.fiche(paire.a), self.fiche(paire.b))
        else:
            self.deux_photos.vider()
            self.description.setText("")
        self._mettre_a_jour_les_boutons()

    def rang_choisi(self) -> int:
        return self.tableau.currentRow()

    def choisir(self, rang: int) -> None:
        """Choisit la paire de ce rang dans le tableau (0 : la première)."""
        if 0 <= rang < self.tableau.rowCount():
            self.tableau.selectRow(rang)
            self.tableau.setCurrentCell(rang, COLONNE_PROXIMITE)

    def aller(self, pas: int) -> None:
        """La paire précédente (-1) ou suivante (+1)."""
        self.choisir(self.rang_choisi() + pas)

    def _paire_pour_la_fenetre(self, rang: int):
        paires = self.paires()
        if not 0 <= rang < len(paires):
            return None
        paire = paires[rang]
        return self.fiche(paire.a), self.fiche(paire.b), self.description_de_la_paire(paire)

    def agrandir(self, rang: int | None = None) -> FenetrePaireEnGrand | None:
        """Les deux photos de la paire en grand (non modale : la page suit la paire montrée)."""
        rang = self.rang_choisi() if rang is None else rang
        paires = self.paires()
        if not 0 <= rang < len(paires):
            return None
        self._fermer_la_fenetre_en_grand()
        fenetre = FenetrePaireEnGrand(self, self._paire_pour_la_fenetre, rang, len(paires))
        fenetre.rang_change.connect(self.choisir)
        fenetre.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        fenetre.destroyed.connect(self._fenetre_en_grand_fermee)
        self._fenetre_en_grand = fenetre
        fenetre.show()
        return fenetre

    def _fenetre_en_grand_fermee(self, *_arguments) -> None:
        self._fenetre_en_grand = None

    def _fermer_la_fenetre_en_grand(self) -> None:
        if self._fenetre_en_grand is not None:
            fenetre, self._fenetre_en_grand = self._fenetre_en_grand, None
            fenetre.close()

    def _chemins_de_la_paire(self) -> tuple[Path, Path] | None:
        paires, rang = self.paires(), self.rang_choisi()
        if not 0 <= rang < len(paires):
            return None
        return self._photo(paires[rang].a).chemin, self._photo(paires[rang].b).chemin

    def montrer_dans_l_explorateur(self, laquelle: int) -> None:
        chemins = self._chemins_de_la_paire()
        if chemins is not None:
            montrer_dans_l_explorateur(chemins[laquelle])

    def ouvrir_dans_comparer(self) -> None:
        chemins = self._chemins_de_la_paire()
        if chemins is not None:
            self.comparer_demande.emit(list(chemins))

    # --- Vignettes ------------------------------------------------------------------------------

    def _faire_les_vignettes(self) -> None:
        """Les vignettes de toutes les photos analysées, en arrière-plan : le tableau les montre dès
        qu'elles arrivent."""
        self._arreter_les_vignettes()
        if self._resultat is None:
            return
        chemins = [photo.chemin for photo in self._resultat.photos if cle(photo.chemin) not in self._vignettes]
        if not chemins:
            return
        arret = threading.Event()
        self._arret_vignettes = arret
        cote = round(Dimensions.DOUBLONS_VIGNETTE * self.devicePixelRatioF())
        taches.lancer_avec_progres(
            lambda progres: faire_les_vignettes(chemins, cote, qimage_depuis_pillow, progres, arret),
            lambda _nombre: None,
            lambda _erreur: None,
            self._vignette_faite,
        )

    def _vignette_faite(self, valeur) -> None:
        chemin, image = valeur
        if image is None or not isValid(self):
            return
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        self._vignettes[cle(chemin)] = pixmap
        self.tableau.viewport().update()

    def vignettes_faites(self) -> int:
        return len(self._vignettes)

    def _arreter_les_vignettes(self) -> None:
        if self._arret_vignettes is not None:
            self._arret_vignettes.set()
            self._arret_vignettes = None

    # --- Outils ---------------------------------------------------------------------------------

    def _mettre_a_jour_les_boutons(self) -> None:
        self.bouton_analyser.setEnabled((bool(self._dossiers) and not self._occupe) or self._bouton_occupe.est(self.bouton_analyser))
        rang, nombre = self.rang_choisi(), len(self.paires())
        choisie = 0 <= rang < nombre
        self.bouton_precedente.setEnabled(choisie and rang > 0)
        self.bouton_suivante.setEnabled(choisie and rang < nombre - 1)
        self.bouton_agrandir.setEnabled(choisie)
        self.bouton_plus.setEnabled(choisie)

    def _occuper(self, occupe: bool, bouton_occupe=None) -> None:
        """Pendant l'analyse : le cercle tourne dans « Analyser » ; les dossiers et leurs réglages sont
        grisés (V3.1). Le seuil et le tableau restent libres."""
        self._occupe = occupe
        if occupe:
            self._bouton_occupe.occuper(bouton_occupe)
        else:
            self._bouton_occupe.liberer()
        self.cadre_dossiers.setEnabled(not occupe)
        self._mettre_a_jour_les_boutons()

    def _afficher(self, message: str, role: str) -> None:
        # Vert, rouge ou orange : effacé après 8 s (V3.2) ; la ligne garde sa place.
        afficher_message(self.statut, message, role, cacher_vide=False)


def _meme_chemin(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a == b
