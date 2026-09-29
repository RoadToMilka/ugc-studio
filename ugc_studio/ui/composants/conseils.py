"""Panneau « Conseils Google » (§5.4 bis, §5.5) : chaque conseil en anglais d'origine, avec sa traduction."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...conseils import Conseil
from ..theme import Espacements
from .elements import libelle


class ListeConseils(QWidget):
    """Liste de conseils : l'original anglais (texte courant), puis la traduction (légende)."""

    def __init__(self, conseils: tuple[Conseil, ...], parent=None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)
        for conseil in conseils:
            bloc_conseil = QVBoxLayout()
            bloc_conseil.setSpacing(0)
            bloc_conseil.addWidget(libelle(f"• {conseil.anglais}", "secondaire"))
            francais = libelle(conseil.francais, "legende")
            francais.setContentsMargins(Espacements.M, 0, 0, 0)
            bloc_conseil.addWidget(francais)
            disposition.addLayout(bloc_conseil)
