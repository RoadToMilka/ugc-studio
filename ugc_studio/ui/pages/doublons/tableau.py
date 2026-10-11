"""Le tableau des paires du module Doublons (V4.3) : une ligne par paire, les plus proches en haut. Au
début de chaque ligne, les deux photos en tout petit, pour reconnaître la paire d'un coup d'œil sans lire
des noms comme « TestClaude_42.jpg » (accord de l'utilisateur du 11/10/2026) ; puis la proximité, le cas,
les deux noms et, avec plusieurs dossiers, leurs dossiers.

Les vignettes sont dessinées « à la main » (DelegueVignettes) au moment où la ligne s'affiche : un
tableau de milliers de paires reste rapide, et chaque vignette arrive dès qu'elle est faite."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate

from ....doublons.choix import IDENTIQUES, MEME_PHOTO, NOMS_DES_CAS
from ...composants.tableau import Colonne
from ...theme import Arrondis, Couleurs, Dimensions, Espacements, Hauteurs, qcolor

ROLE_PHOTOS = Qt.ItemDataRole.UserRole + 1  # les chemins des deux photos de la ligne (texte, texte)

COLONNES = (
    Colonne("Photos"),
    Colonne("Proximité", a_droite=True, aide="100 % : identiques. 95 à 99 % : la même photo, modifiée. 94 % au plus : estimé par l'IA."),
    # Le cas, toujours en entier (« Même photo », « Ressemblantes ») : ce sont les noms des images qui se
    # resserrent quand la place manque (abrégés au milieu, leur numéro et leur extension restent lisibles).
    Colonne("Type"),
    Colonne("Image 1", texte=True, etiree=True),
    Colonne("Image 2", texte=True),
    Colonne("Dossiers", texte=True),
)
COLONNE_PHOTOS, COLONNE_PROXIMITE, COLONNE_TYPE, COLONNE_IMAGE_1, COLONNE_IMAGE_2, COLONNE_DOSSIERS = range(len(COLONNES))


def texte_du_type(genre: str, details: tuple[str, ...]) -> str:
    """« Identiques », « Identiques · mêmes pixels », « Même photo · autre taille, retournée », « Ressemblantes »."""
    nom = NOMS_DES_CAS.get(genre, genre)
    if genre == MEME_PHOTO and details:
        return f"{nom} · {', '.join(details)}"
    if genre == IDENTIQUES and details and details != ("même fichier",):
        return f"{nom} · {', '.join(details)}"
    return nom


def texte_des_dossiers(dossier_a: str, dossier_b: str) -> str:
    """« Lot 1 » (même dossier) ou « Lot 1 · Lot 2 »."""
    return dossier_a if dossier_a == dossier_b else f"{dossier_a} · {dossier_b}"


class DelegueVignettes(QStyledItemDelegate):
    """Dessin de la case « Photos » : les deux vignettes côte à côte (proportions gardées, centrées dans
    leur carré), ou un carré gris le temps qu'elles arrivent. `vignettes` : chemin → QPixmap."""

    def __init__(self, vignettes: dict[str, QPixmap], parent=None):
        super().__init__(parent)
        self._vignettes = vignettes

    def sizeHint(self, _option, _index) -> QSize:  # noqa: N802 : nom imposé par Qt
        return QSize(Dimensions.DOUBLONS_COLONNE_VIGNETTES, Hauteurs.LIGNE_TABLEAU)

    def paint(self, peintre: QPainter, option, index) -> None:
        super().paint(peintre, option, index)  # fond de la ligne (choisie, survolée)
        chemins = index.data(ROLE_PHOTOS)
        if not chemins:
            return
        peintre.save()
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cote = Dimensions.DOUBLONS_VIGNETTE
        haut = option.rect.top() + (option.rect.height() - cote) / 2
        gauche = option.rect.left() + Espacements.S
        for rang, chemin in enumerate(chemins):
            carre = QRectF(gauche + rang * (cote + Espacements.XS), haut, cote, cote)
            vignette = self._vignettes.get(chemin)
            if isinstance(vignette, QPixmap) and not vignette.isNull():
                taille = vignette.deviceIndependentSize()
                place = QRectF(0, 0, min(taille.width(), cote), min(taille.height(), cote))
                place.moveCenter(carre.center())
                peintre.drawPixmap(place, vignette, QRectF(vignette.rect()))
            else:
                peintre.setPen(Qt.PenStyle.NoPen)
                peintre.setBrush(qcolor(Couleurs.SURFACE_ELEVEE))
                peintre.drawRoundedRect(carre, Arrondis.PETIT, Arrondis.PETIT)
        peintre.restore()


def cle(chemin: Path) -> str:
    """Le chemin d'une photo, tel que le tableau le garde (texte)."""
    return str(chemin)
