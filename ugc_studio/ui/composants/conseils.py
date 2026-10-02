"""Bouton « Conseils » et fenêtre de conseils (V1.1, §9.4 quater).

Le bouton (ampoule, style contour) se place en haut à droite de chaque module, sur la ligne du
titre, et en haut à droite de chaque fenêtre qui a quelque chose à expliquer. Il ouvre les
conseils de la page, en français ; les textes sont dans conseils_des_pages.py.

Pourquoi une fenêtre ? Jusqu'à la 1.0.2, les conseils de Google restaient affichés sous le script
(module Voix) et à côté des formulaires (styles, Voice Design), en anglais avec leur traduction :
beaucoup de place pour une lecture qu'on ne fait qu'une fois. Ils sont maintenant réunis derrière
un bouton, avec ceux de chaque module et de chaque fenêtre.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ...conseils_des_pages import PAGES, PageDeConseils
from ...sous_titres import typographie
from ..theme import Dimensions, Espacements
from .bouton import Bouton
from .defilement import zone_defilante
from .elements import BoutonInfo, bouton, libelle, ligne_avec_aide, marge_haute_titre, titre_avec

TEXTE_BOUTON = "Conseils"


def titre_des_conseils(page: PageDeConseils) -> str:
    """« Voix • Conseils » : la page, puis « Conseils » (comme « Voix • Sérum Glowzy »)."""
    return titre_avec(page.titre, "Conseils")


def _francais(texte: str) -> str:
    """Espaces insécables à la française (avant « : ; ! ? », à l'intérieur des guillemets) : un
    « « » ou un « : » ne se retrouve jamais seul en début ou en fin de ligne."""
    return typographie(texte, "fr")


class _Conseil(QWidget):
    """Un conseil : une puce, puis le texte, qui passe à la ligne sous lui-même (pas sous la puce)."""

    def __init__(self, texte: str):
        super().__init__()
        self.source = texte  # le texte tel qu'écrit dans conseils_des_pages.py
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)
        # Même police pour la puce et le texte, calés en haut : la puce tombe sur la première ligne.
        disposition.addWidget(libelle("•", "secondaire", retour_a_la_ligne=False), 0, Qt.AlignmentFlag.AlignTop)
        self.texte = libelle(_francais(texte))
        disposition.addWidget(self.texte, 1)


class DialogueConseils(QDialog):
    """Fenêtre des conseils d'un module ou d'une fenêtre : des rubriques, chacune dans une carte (V3.1,
    §9.4 quater) : fond et contour d'un bloc, coins arrondis de 12 px, son titre en haut, ses conseils
    dessous, 12 px entre deux cartes. On voit d'un coup d'œil où commence et finit chaque sujet.
    V3.2 : la fenêtre a le fond de l'app (et non plus celui des menus), 16 px autour, comme une page :
    les cartes s'en détachent comme les blocs des pages."""

    def __init__(self, page: PageDeConseils, parent: QWidget | None = None):
        super().__init__(parent)
        self.page = page
        titre = titre_des_conseils(page)
        self.setWindowTitle(titre)
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)
        self.resize(Dimensions.DIALOGUE_CONSEILS_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        # Les cartes défilent jusqu'au bord droit de la fenêtre : la barre de défilement prend place
        # dans la marge de droite, comme dans les pages (les cartes ne bougent pas quand elle apparaît).
        # 16 px autour, comme les blocs d'une page (24 px jusqu'à la 3.1.2).
        marge = Dimensions.ESPACE_BLOCS
        marges = (marge, 0, marge, 0)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, marge, 0, marge)
        disposition.setSpacing(marge)
        haut = QHBoxLayout()
        haut.setContentsMargins(*marges)
        haut.addWidget(libelle(titre, "titre-bloc"))
        disposition.addLayout(haut)

        zone, contenu = zone_defilante(marges=marges, barre_dans_la_marge=True)
        contenu.setSpacing(Espacements.M)
        self.cartes: list[QFrame] = []
        for rubrique in page.rubriques:
            carte = QFrame()
            carte.setProperty("role", "bloc")
            partie = QVBoxLayout(carte)
            # Le haut des majuscules du titre à 16 px du bord, comme à gauche (V3.2, voir marge_haute_titre).
            partie.setContentsMargins(Espacements.L, marge_haute_titre(Espacements.L), Espacements.L, Espacements.L)
            partie.setSpacing(Espacements.S)
            partie.addWidget(libelle(_francais(rubrique.titre), "intitule"))
            for conseil in rubrique.conseils:
                partie.addWidget(_Conseil(conseil))
            contenu.addWidget(carte)
            self.cartes.append(carte)
        disposition.addWidget(zone, 1)

        bas = QHBoxLayout()
        bas.setContentsMargins(*marges)
        bas.addStretch(1)
        bas.addWidget(bouton("Fermer", action=self.accept))
        disposition.addLayout(bas)

    def conseils(self) -> list[str]:
        """Les conseils affichés, dans l'ordre, tels qu'écrits dans conseils_des_pages.py (pour les tests)."""
        return [element.source for element in self.findChildren(_Conseil)]


def bouton_conseils(cle: str) -> Bouton:
    """Bouton « Conseils » (ampoule, style contour) qui ouvre les conseils de la page `cle`
    (voir conseils_des_pages.PAGES)."""
    page = PAGES[cle]
    resultat = bouton(TEXTE_BOUTON, variante="contour", nom_icone="lightbulb")
    resultat.clicked.connect(lambda: DialogueConseils(page, resultat.window()).exec())
    resultat.setProperty("conseils", cle)  # pour les tests et l'autotest
    return resultat


def entete_de_fenetre(titre: str, conseils: str, aide: str | None = None) -> QHBoxLayout:
    """Titre d'une fenêtre, avec le bouton « Conseils » en haut à droite. `aide` : ce que fait la
    fenêtre, dans une icône « i » devant le titre (V3.2 ; V3.1 : plus de phrase d'explication
    toujours affichée sous le titre). Le titre reste accessible (`entete.titre`), comme l'icône
    (`entete.aide`, None sans aide) et le bouton (`entete.conseils`)."""
    entete = QHBoxLayout()
    entete.setContentsMargins(0, 0, 0, 0)
    entete.setSpacing(Espacements.S)
    entete.aide = BoutonInfo(aide) if aide else None
    if entete.aide is None:
        entete.titre = libelle(titre, "titre-bloc")
        entete.addWidget(entete.titre, 1)
    else:
        # Avec une icône, le titre garde sa largeur et l'icône le précède ; la place reste avant le bouton.
        entete.titre = libelle(titre, "titre-bloc", retour_a_la_ligne=False)
        entete.addLayout(ligne_avec_aide(entete.titre, entete.aide), 1)
    entete.conseils = bouton_conseils(conseils)
    entete.addWidget(entete.conseils)
    return entete
