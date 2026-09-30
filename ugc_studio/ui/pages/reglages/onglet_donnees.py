"""Onglet « Journal et données » (§10) : journal d'erreurs, dossier de données, à propos."""

from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .... import NOM_APP, __version__
from ....chemins import dossier_donnees, dossier_journal
from ...composants.elements import bloc, bouton, info, libelle
from ...ouvrir import ouvrir_dossier, ouvrir_journal
from ...theme import Espacements
from ...composants.defilement import zone_defilante


class OngletDonnees(QWidget):
    def __init__(self):
        super().__init__()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        zone, contenu = zone_defilante(marges=(0, Espacements.XL, 0, Espacements.XXL))
        disposition.addWidget(zone)

        # Journal d'erreurs
        cadre, d = bloc("Journal d'erreurs")
        d.addWidget(
            info(
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
                variante="contour",
                nom_icone="folder-open",
                action=lambda: ouvrir_dossier(dossier_journal()),
            )
        )
        boutons.addStretch(1)
        d.addLayout(boutons)
        contenu.addWidget(cadre)

        # Dossier de données
        cadre, d = bloc("Dossier de données")
        d.addWidget(
            info(
                "Connexions (sans les clés), prix, historique des coûts, préférences de l'app.",
                "secondaire",
            )
        )
        self.chemin_donnees = libelle(str(dossier_donnees()), "legende", selectionnable=True)
        d.addWidget(self.chemin_donnees)
        boutons = QHBoxLayout()
        boutons.addWidget(
            bouton("Ouvrir le dossier", nom_icone="folder-open", action=lambda: ouvrir_dossier(dossier_donnees()))
        )
        boutons.addStretch(1)
        d.addLayout(boutons)
        contenu.addWidget(cadre)

        # À propos
        cadre, d = bloc("À propos")
        d.addWidget(libelle(f"{NOM_APP} {__version__}"))
        d.addWidget(
            libelle(
                f"Python {platform.python_version()}  ·  Qt {qVersion()}  ·  PySide6 {PySide6.__version__}",
                "legende",
            )
        )
        d.addWidget(libelle("Icônes Lucide (licence ISC) · Police Inter (licence SIL OFL 1.1).", "legende"))
        contenu.addWidget(cadre)
