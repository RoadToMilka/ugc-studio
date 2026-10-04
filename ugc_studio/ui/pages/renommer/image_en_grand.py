"""Une image en grand (V4, lot 2 : double-clic sur une vignette du module Renommer), pour départager
deux images proches. Dessous : sa taille, son format et son poids. La fenêtre tient sur l'écran (au
plus 80 % de sa largeur et de sa hauteur) ; l'image n'y est jamais agrandie."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel

from ...composants.elements import bouton, libelle
from ...composants.fenetre import fenetre_en_bloc
from ...theme import Dimensions, Espacements, Hauteurs
from .grille import qimage_depuis_pillow

ORIENTATION = 0x0112  # étiquette EXIF de l'orientation
ORIENTATIONS_COUCHEES = (5, 6, 7, 8)  # la photo est à tourner d'un quart de tour

NOMS_DES_FORMATS = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WebP", "AVIF": "AVIF", "TIFF": "TIFF", "BMP": "BMP"}


def poids_lisible(octets: int) -> str:
    """1 234 567 → « 1,2 Mo » ; 84 000 → « 82 Ko »."""
    if octets >= 1024 * 1024:
        return f"{octets / (1024 * 1024):.1f} Mo".replace(".", ",")
    return f"{max(1, round(octets / 1024))} Ko"


class FenetreImageEnGrand(QDialog):
    def __init__(self, parent, chemin: Path):
        super().__init__(parent)
        self.setWindowTitle(chemin.name)
        fenetre, self.cadre, disposition = fenetre_en_bloc(self)
        disposition.setSpacing(Espacements.M)
        self.titre = libelle(chemin.name, "titre-bloc")
        disposition.addWidget(self.titre)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disposition.addWidget(self.image, 1)
        self.details = libelle("", "legende")
        disposition.addWidget(self.details)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        self.bouton_fermer = bouton("Fermer", variante="principal", action=self.accept)
        boutons.addWidget(self.bouton_fermer)
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)
        self.bouton_fermer.setFocus()
        self._montrer(chemin)
        self.adjustSize()

    def _place_pour_l_image(self) -> tuple[int, int]:
        """Largeur et hauteur disponibles pour l'image, en pixels de l'écran : 80 % de l'écran, moins
        les marges de la fenêtre, le titre, la ligne du dessous et le bouton."""
        ecran = self.screen() or QGuiApplication.primaryScreen()
        zone = ecran.availableGeometry()
        marges = 2 * (Dimensions.ESPACE_BLOCS + Espacements.XL + Dimensions.BORDURE)
        autour = 3 * Dimensions.ESPACE_BLOCS + 2 * Espacements.XL + 4 * Espacements.M + 3 * Hauteurs.CONTROLE
        largeur = int(zone.width() * Dimensions.IMAGE_EN_GRAND_PART_ECRAN) - marges
        hauteur = int(zone.height() * Dimensions.IMAGE_EN_GRAND_PART_ECRAN) - autour
        return max(Dimensions.RENOMMER_IMAGE, largeur), max(Dimensions.RENOMMER_IMAGE, hauteur)

    def _montrer(self, chemin: Path) -> None:
        largeur, hauteur = self._place_pour_l_image()
        ratio = self.devicePixelRatioF()
        try:
            with Image.open(chemin) as ouverte:
                nom_du_format = NOMS_DES_FORMATS.get(ouverte.format or "", ouverte.format or "")
                taille_reelle = _taille_dans_le_bon_sens(ouverte)  # avant de la décoder en petit
                ouverte.draft("RGB", (round(largeur * ratio), round(hauteur * ratio)))
                droite = ImageOps.exif_transpose(ouverte)
                droite.thumbnail((round(largeur * ratio), round(hauteur * ratio)), Image.Resampling.LANCZOS)
                image = qimage_depuis_pillow(droite)
        except Exception as erreur:  # noqa: BLE001 : fichier abîmé, format inconnu… : on le dit
            self.image.setText(f"Impossible d'afficher cette image : {erreur}")
            return
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(ratio)
        self.image.setPixmap(pixmap)
        poids = poids_lisible(chemin.stat().st_size) if chemin.exists() else ""
        details = [f"{taille_reelle[0]} × {taille_reelle[1]} px", nom_du_format, poids]
        self.details.setText(" · ".join(element for element in details if element))


def _taille_dans_le_bon_sens(image: Image.Image) -> tuple[int, int]:
    """Taille de l'image telle qu'on la voit : une photo enregistrée couchée (orientation EXIF 5 à 8)
    a sa largeur et sa hauteur échangées. À lire avant draft(), qui réduit la taille annoncée."""
    largeur, hauteur = image.size
    return (hauteur, largeur) if image.getexif().get(ORIENTATION, 1) in ORIENTATIONS_COUCHEES else (largeur, hauteur)
