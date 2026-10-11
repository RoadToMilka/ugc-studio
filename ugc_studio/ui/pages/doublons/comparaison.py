"""La paire choisie dans le tableau du module Doublons (V4.3), toujours visible : les deux photos côte à
côte, à la même hauteur, et sous chacune son nom, sa taille, son format, son poids, sa date et son
dossier ; ce qui la distingue de l'autre (la plus grande, la plus lourde) en mauve.

Les photos sont lues en arrière-plan, en petit (un JPG est décodé directement à la bonne taille) : passer
d'une paire à l'autre avec ↑ et ↓ reste immédiat."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from shiboken6 import isValid

from ....chemins import chemin_a_afficher
from ... import taches
from ...composants.elements import libelle, libelle_abrege
from ...theme import Dimensions, Espacements
from ..renommer.grille import qimage_depuis_pillow
from ..renommer.image_en_grand import poids_lisible

NOMS_DES_FORMATS = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WebP", "AVIF": "AVIF", "TIFF": "TIFF", "BMP": "BMP", "MPO": "JPG"}
TEXTE_ILLISIBLE = "Aperçu impossible"


@dataclass(frozen=True)
class FichePhoto:
    """Ce que la comparaison montre d'une photo."""

    chemin: Path
    largeur: int
    hauteur: int
    format: str
    octets: int
    modifiee: float
    dossier: str  # le dossier ajouté qui la contient (son nom)

    @property
    def pixels(self) -> int:
        return self.largeur * self.hauteur


def texte_des_details(fiche: FichePhoto) -> str:
    """« 600 × 800 px · JPG · 87 Ko »."""
    return f"{fiche.largeur} × {fiche.hauteur} px · {NOMS_DES_FORMATS.get(fiche.format, fiche.format)} · {poids_lisible(fiche.octets)}"


def texte_de_la_date(fiche: FichePhoto) -> str:
    """« Modifiée le 12/09/2025 à 14:03 »."""
    return f"Modifiée le {datetime.fromtimestamp(fiche.modifiee):%d/%m/%Y à %H:%M}"


def ce_qui_la_distingue(fiche: FichePhoto, autre: FichePhoto) -> str:
    """« La plus grande, la plus lourde » (en mauve sous la photo), ou « » si rien ne la distingue."""
    distinctions = []
    if fiche.pixels > autre.pixels:
        distinctions.append("la plus grande")
    if fiche.octets > autre.octets:
        distinctions.append("la plus lourde")
    texte = ", ".join(distinctions)
    return texte[:1].upper() + texte[1:]


def image_pour_l_ecran(chemin: Path, largeur: int, hauteur: int) -> QImage:
    """La photo, dans le bon sens, réduite pour tenir dans largeur × hauteur pixels (jamais agrandie).
    Faite dans un fil de travail (QImage le permet)."""
    with Image.open(chemin) as ouverte:
        ouverte.draft("RGB", (largeur, hauteur))
        droite = ImageOps.exif_transpose(ouverte)
        droite.thumbnail((largeur, hauteur), Image.Resampling.LANCZOS)
        return qimage_depuis_pillow(droite)


class ImageAjustee(QLabel):
    """Une image qui tient dans sa place, proportions gardées, centrée (jamais agrandie au-delà de la
    taille à laquelle elle a été lue). `hauteur` : une hauteur fixe ; None : elle prend toute la place
    qu'on lui donne (fenêtre « Agrandir »)."""

    def __init__(self, hauteur: int | None):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(Dimensions.DOUBLONS_IMAGE_LARGEUR_MIN)
        if hauteur is None:
            self.setMinimumHeight(Dimensions.DOUBLONS_IMAGE_HAUTEUR)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        else:
            self.setFixedHeight(hauteur)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._image: QImage | None = None

    def definir(self, image: QImage | None, texte: str = "") -> None:
        self._image = image
        if image is None:
            self.setPixmap(QPixmap())
            self.setText(texte)
        else:
            self.setText("")
            self._ajuster()

    def _ajuster(self) -> None:
        if self._image is None or self._image.isNull():
            return
        ratio = self.devicePixelRatioF()
        largeur, hauteur = max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio))
        image = self._image
        if image.width() > largeur or image.height() > hauteur:
            image = image.scaled(largeur, hauteur, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(ratio)
        self.setPixmap(pixmap)

    def resizeEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        super().resizeEvent(evenement)
        self._ajuster()


class PanneauPhoto(QWidget):
    """Une photo de la paire et ce qu'on en sait."""

    def __init__(self, hauteur_image: int = Dimensions.DOUBLONS_IMAGE_HAUTEUR):
        super().__init__()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.XS)
        self.image = ImageAjustee(hauteur_image)
        disposition.addWidget(self.image)
        disposition.addSpacing(Espacements.XS)
        self.nom = libelle_abrege("", "intitule")
        disposition.addWidget(self.nom)
        self.details = libelle_abrege("", "legende")
        disposition.addWidget(self.details)
        self.date = libelle_abrege("", "legende")
        disposition.addWidget(self.date)
        self.dossier = libelle_abrege("", "legende")
        disposition.addWidget(self.dossier)
        self.distinction = libelle_abrege("", "legende-modifiee")
        disposition.addWidget(self.distinction)
        disposition.addStretch(1)  # la place en trop en bas : les lignes des deux photos restent alignées
        self._demande = 0
        self.fiche: FichePhoto | None = None

    def montrer(self, fiche: FichePhoto, autre: FichePhoto) -> None:
        self.fiche = fiche
        self.nom.setText(fiche.chemin.name)
        self.nom.setToolTip(str(fiche.chemin))
        self.details.setText(texte_des_details(fiche))
        self.date.setText(texte_de_la_date(fiche))
        self.dossier.setText(f"Dossier : {chemin_a_afficher(fiche.chemin.parent)}")
        distinction = ce_qui_la_distingue(fiche, autre)
        self.distinction.setText(distinction)
        self.distinction.setVisible(bool(distinction))
        self._demande += 1
        demande = self._demande
        self.image.definir(None, "")
        ratio = self.devicePixelRatioF()
        largeur = round(Dimensions.DOUBLONS_IMAGE_HAUTEUR * 2 * ratio)
        hauteur = round(self.image.height() * ratio)
        taches.lancer(
            lambda chemin=fiche.chemin: image_pour_l_ecran(chemin, largeur, hauteur),
            lambda image, d=demande: self._image_lue(d, image),
            lambda _erreur, d=demande: self._image_lue(d, None),
        )

    def _image_lue(self, demande: int, image: QImage | None) -> None:
        if not isValid(self) or demande != self._demande:
            return  # une autre paire est montrée depuis (ou la page n'existe plus)
        self.image.definir(image, "" if image is not None else TEXTE_ILLISIBLE)

    def vider(self) -> None:
        self._demande += 1
        self.fiche = None
        self.image.definir(None, "")
        for etiquette in (self.nom, self.details, self.date, self.dossier, self.distinction):
            etiquette.setText("")
        self.distinction.hide()


class DeuxPhotos(QWidget):
    """Les deux photos de la paire, côte à côte, à la même hauteur."""

    def __init__(self):
        super().__init__()
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.L)
        self.premiere = PanneauPhoto()
        self.seconde = PanneauPhoto()
        disposition.addWidget(self.premiere, 1)
        disposition.addWidget(self.seconde, 1)

    def montrer(self, premiere: FichePhoto, seconde: FichePhoto) -> None:
        self.premiere.montrer(premiere, seconde)
        self.seconde.montrer(seconde, premiere)

    def vider(self) -> None:
        self.premiere.vider()
        self.seconde.vider()


def libelle_vide(texte: str) -> QLabel:
    """Le texte de la comparaison quand aucune paire n'est choisie (style des listes vides)."""
    return libelle(texte, "discret")
