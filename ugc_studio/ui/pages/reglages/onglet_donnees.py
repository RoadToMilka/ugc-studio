"""Onglet « Journal et données » (§10) : journal d'erreurs, dossier de données, à propos (dont
FFmpeg, fourni avec l'app pour les exports vidéo : sa licence et l'adresse de son code source)."""

from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .... import NOM_APP, __version__
from ....chemins import dossier_donnees, dossier_journal, dossier_ressources
from ....exports.ffmpeg import DOSSIER_FFMPEG, VERSION_INTEGREE
from ...composants.elements import bloc, bouton, info, libelle
from ...ouvrir import ouvrir_dossier, ouvrir_fichier, ouvrir_journal
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
        # FFmpeg (V3) : programme fourni avec l'app pour les exports vidéo ; sa licence (GPL) et l'adresse
        # de son code source sont jointes à l'app (ressources/ffmpeg).
        d.addWidget(libelle(f"FFmpeg {VERSION_INTEGREE} (gyan.dev, licence GPL version 3) : écrit les fichiers vidéo des exports", "legende"))
        boutons = QHBoxLayout()
        boutons.addWidget(
            bouton(
                "Licence et code source de FFmpeg",
                variante="contour",
                nom_icone="file-text",
                action=lambda: ouvrir_fichier(dossier_ressources() / DOSSIER_FFMPEG / "A-PROPOS.txt"),
            )
        )
        boutons.addStretch(1)
        d.addLayout(boutons)
        contenu.addWidget(cadre)
