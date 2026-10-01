"""Petite vidéo de test (V2, lot 3) : elle sert à l'autotest du .exe (Qt Multimedia lit-il bien une
vidéo, image par image ?) et au fond « Vidéo » de l'aperçu dans les captures de démonstration.

Format : AVI « Motion JPEG » (chaque image du film est une image JPEG), écrit ici en quelques lignes,
sans outil extérieur ; FFmpeg, fourni avec Qt Multimedia, sait le lire. La scène : un dégradé
bleu-vert et une silhouette face caméra qui se balance doucement (comme une vidéo UGC).
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QLinearGradient, QPainter

from ..avi import avi_mjpeg

QUALITE_JPEG = 60
COULEUR_HAUT = Qt.GlobalColor.darkCyan  # vérifiée par l'autotest après décodage
COULEUR_BAS = Qt.GlobalColor.black


def _image(largeur: int, hauteur: int, numero: int, images_par_seconde: int) -> QImage:
    image = QImage(largeur, hauteur, QImage.Format.Format_RGB32)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    degrade = QLinearGradient(0, 0, 0, hauteur)
    degrade.setColorAt(0, COULEUR_HAUT)
    degrade.setColorAt(1, COULEUR_BAS)
    peintre.fillRect(QRectF(0, 0, largeur, hauteur), degrade)
    # Silhouette face caméra : elle se balance doucement (une période de 4 secondes).
    balancement = math.sin(2 * math.pi * numero / (4 * images_par_seconde)) * largeur / 30
    peintre.setPen(Qt.PenStyle.NoPen)
    peintre.setBrush(Qt.GlobalColor.darkGray)
    peintre.drawRoundedRect(
        QRectF(largeur * 0.18 + balancement, hauteur * 0.52, largeur * 0.64, hauteur * 0.6), largeur * 0.2, largeur * 0.2
    )
    peintre.setBrush(Qt.GlobalColor.gray)
    peintre.drawEllipse(QPointF(largeur / 2 + balancement, hauteur * 0.38), largeur * 0.17, largeur * 0.21)
    peintre.end()
    return image


def _jpeg(image: QImage) -> bytes:
    tampon = QBuffer(QByteArray())
    tampon.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(tampon, "JPG", QUALITE_JPEG)
    return bytes(tampon.data())


def ecrire_video_de_test(chemin: Path, largeur: int, hauteur: int, duree_s: float, images_par_seconde: int) -> Path:
    """Écrit la vidéo de test ; renvoie son chemin."""
    nombre = max(1, round(duree_s * images_par_seconde))
    images = [_jpeg(_image(largeur, hauteur, numero, images_par_seconde)) for numero in range(nombre)]
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(avi_mjpeg(images, largeur, hauteur, images_par_seconde))
    return chemin
