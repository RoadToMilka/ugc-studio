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


def ouvrir_fichier(chemin: Path) -> None:
    """Ouvre un fichier avec le programme que Windows lui associe (Bloc-notes pour un texte…)."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))


def ouvrir_page_web(adresse: str) -> None:
    QDesktopServices.openUrl(QUrl(adresse))


def montrer_dans_l_explorateur(chemin: Path) -> None:
    """Ouvre le dossier d'un fichier dans l'Explorateur Windows, ce fichier choisi (ex. un export
    tout juste écrit) ; ailleurs que sous Windows, ouvre simplement son dossier."""
    import subprocess
    import sys

    if sys.platform == "win32" and chemin.exists():
        try:
            # Un seul texte : l'Explorateur attend « /select,"chemin" », virgule collée au chemin.
            subprocess.Popen(f'explorer /select,"{chemin}"')  # noqa: S603 (programme de Windows)
            return
        except OSError:
            pass
    ouvrir_dossier(chemin.parent)
