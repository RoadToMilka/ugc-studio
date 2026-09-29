"""Ouvrir un fichier, un dossier ou une page web avec les programmes de Windows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ..chemins import fichier_journal


def ouvrir_journal() -> None:
    """Ouvre le journal d'erreurs dans l'éditeur de texte de Windows (Bloc-notes…)."""
    chemin = fichier_journal()
    if not chemin.exists():
        chemin.touch()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))


def ouvrir_dossier(chemin: Path) -> None:
    """Ouvre un dossier dans l'Explorateur Windows."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))


def ouvrir_page_web(adresse: str) -> None:
    QDesktopServices.openUrl(QUrl(adresse))
