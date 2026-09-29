"""Page Réglages (§4). Étape 1 : journal d'erreurs, dossier de données et « À propos ».
Les connexions API, le catalogue des prix et le suivi des coûts arrivent à l'étape 2."""

from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout

from ... import NOM_APP, __version__
from ...chemins import dossier_donnees, dossier_journal, fichier_journal
from ..composants.elements import bloc, bouton, libelle, pastille
from ..theme import Espacements
from .base import Page


def ouvrir_journal() -> None:
    """Ouvre le journal d'erreurs dans l'éditeur de texte de Windows (Bloc-notes…)."""
    chemin = fichier_journal()
    if not chemin.exists():
        chemin.touch()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))


def ouvrir_dossier(chemin) -> None:
    """Ouvre un dossier dans l'Explorateur Windows."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))


class PageReglages(Page):
    def __init__(self):
        super().__init__("Réglages", "Connexions API, prix, suivi des coûts et informations sur l'app.")

        self.contenu.addWidget(
            self._bloc_a_venir(
                "Connexions API",
                "Étape 2",
                "Ajout, test et gestion de tes clés Google. Elles seront rangées dans le coffre-fort "
                "de Windows, jamais dans un fichier.",
            )
        )
        self.contenu.addWidget(
            self._bloc_a_venir(
                "Prix et suivi des coûts",
                "Étape 2",
                "Catalogue des modèles et de leurs prix, taux de change dollar → euro, "
                "historique des coûts par jour, projet et modèle.",
            )
        )

        # Journal d'erreurs
        cadre, disposition = bloc("Journal d'erreurs")
        disposition.addWidget(
            libelle(
                "Si quelque chose ne fonctionne pas, ce fichier indique ce qui s'est passé. "
                "Il ne contient jamais tes clés API.",
                "secondaire",
            )
        )
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addWidget(bouton("Ouvrir le journal", nom_icone="file-text", action=ouvrir_journal))
        boutons.addWidget(
            bouton(
                "Ouvrir le dossier",
                variante="discret",
                nom_icone="folder-open",
                action=lambda: ouvrir_dossier(dossier_journal()),
            )
        )
        boutons.addStretch(1)
        disposition.addLayout(boutons)
        self.contenu.addWidget(cadre)

        # Dossier de données
        cadre, disposition = bloc("Dossier de données")
        disposition.addWidget(
            libelle(
                "Styles, préréglages, prix, historique des coûts et préférences de l'app.",
                "secondaire",
            )
        )
        self.chemin_donnees = libelle(str(dossier_donnees()), "legende", selectionnable=True)
        disposition.addWidget(self.chemin_donnees)
        boutons = QHBoxLayout()
        boutons.addWidget(
            bouton(
                "Ouvrir le dossier",
                nom_icone="folder-open",
                action=lambda: ouvrir_dossier(dossier_donnees()),
            )
        )
        boutons.addStretch(1)
        disposition.addLayout(boutons)
        self.contenu.addWidget(cadre)

        # À propos
        cadre, disposition = bloc("À propos")
        disposition.addWidget(libelle(f"{NOM_APP} {__version__}"))
        disposition.addWidget(
            libelle(
                f"Python {platform.python_version()}  ·  Qt {qVersion()}  ·  PySide6 {PySide6.__version__}",
                "legende",
            )
        )
        self.contenu.addWidget(cadre)

    @staticmethod
    def _bloc_a_venir(titre: str, etape: str, description: str):
        cadre, disposition = bloc()
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        ligne.addWidget(libelle(titre, "titre-bloc", retour_a_la_ligne=False))
        ligne.addWidget(pastille(etape))
        ligne.addStretch(1)
        disposition.addLayout(ligne)
        disposition.addWidget(libelle(description, "secondaire"))
        return cadre
