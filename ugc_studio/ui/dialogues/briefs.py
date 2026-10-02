"""Bibliothèque de briefs (V2, lot 2, §10.5) : les briefs enregistrés, à charger dans le projet ouvert.

« Charger » remplace le brief du projet (les options d'écriture, elles, ne changent pas) et, si la
case est cochée, reprend aussi la page produit lue et sa fiche. Menu ⋯ : renommer, supprimer.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout

from ...ecriture.affichage import date_lisible
from ...ecriture.briefs import BriefEnregistre
from ...services import Services
from ..composants.conseils import entete_de_fenetre
from ..composants.defilement import zone_defilante
from ..composants.elements import (
    bouton,
    case_a_cocher,
    conteneur_vertical,
    libelle,
    vider_disposition,
)
from ..composants.fenetre import fenetre_en_bloc
from ..composants.menu import Menu
from ..icones import icone_menu
from ..theme import Couleurs, Dimensions, Espacements
from . import messages


class LigneBrief(QFrame):
    def __init__(self, dialogue: DialogueBibliothequeBriefs, enregistre: BriefEnregistre):
        super().__init__()
        self.setProperty("role", "ligne")
        self.enregistre = enregistre
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.M)
        textes = QVBoxLayout()
        textes.setSpacing(0)
        textes.addWidget(libelle(enregistre.nom, "intitule"))
        textes.addWidget(libelle(enregistre.resume(), "secondaire"))
        page = enregistre.page
        if page is not None:
            adresse = enregistre.adresse or page.adresse
            textes.addWidget(libelle(f"Page produit : {adresse} (lue {date_lisible(page.lu_le)})", "legende"))
        textes.addWidget(libelle(f"Enregistré {date_lisible(enregistre.date)}", "legende"))
        disposition.addLayout(textes, 1)
        self.bouton_charger = bouton("Charger", nom_icone="folder-open", action=lambda: dialogue.charger(enregistre))
        self.bouton_charger.setToolTip("Remplace le brief du projet ouvert par celui-ci")
        disposition.addWidget(self.bouton_charger, 0, Qt.AlignmentFlag.AlignVCenter)
        plus = bouton("", variante="icone", nom_icone="ellipsis")
        plus.setToolTip("Plus d'actions")
        menu = Menu(plus)
        menu.addAction(icone_menu("pencil"), "Renommer…").triggered.connect(lambda: dialogue.renommer(enregistre))
        menu.addSeparator()
        menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer…").triggered.connect(
            lambda: dialogue.supprimer(enregistre)
        )
        plus.setMenu(menu)
        disposition.addWidget(plus, 0, Qt.AlignmentFlag.AlignVCenter)


class DialogueBibliothequeBriefs(QDialog):
    """Après « Charger » : `brief_choisi` et `reprendre_page` (la fenêtre est acceptée)."""

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self._services = services
        self.brief_choisi: BriefEnregistre | None = None
        self.reprendre_page = True
        self.setWindowTitle("Bibliothèque de briefs")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        fenetre, self.cadre, disposition = fenetre_en_bloc(self, titre_avec_boutons=True)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(
            entete_de_fenetre(
                "Bibliothèque de briefs",
                "bibliotheque-briefs",
                aide=(
                    "Tes briefs enregistrés (bouton « Enregistrer » du bloc Brief). « Charger » remplace le brief "
                    "du projet ouvert ; tes options d'écriture ne changent pas."
                ),
            )
        )
        zone, contenu = zone_defilante(largeur_max=None)
        self._liste_widget, self._liste = conteneur_vertical(Espacements.XS)
        contenu.addWidget(self._liste_widget)
        disposition.addWidget(zone, 1)
        zone_case, self.case_page = case_a_cocher(
            "Reprendre aussi la page produit lue",
            "La page et sa fiche reviennent avec le brief, sans relire la page ni repayer son analyse.",
        )
        self.case_page.setChecked(True)
        disposition.addWidget(zone_case)
        boutons = QHBoxLayout()
        boutons.addStretch(1)
        boutons.addWidget(bouton("Fermer", action=self.reject))
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)
        self._lignes: list[LigneBrief] = []
        self.rafraichir()

    def lignes(self) -> list[LigneBrief]:
        return list(self._lignes)

    def rafraichir(self) -> None:
        vider_disposition(self._liste)
        self._lignes = []
        briefs = self._services.briefs.briefs()
        if not briefs:
            self._liste.addWidget(
                libelle("Aucun brief enregistré pour l'instant : remplis un brief, puis « Enregistrer ».", "discret")
            )
        for enregistre in briefs:
            ligne = LigneBrief(self, enregistre)
            self._lignes.append(ligne)
            self._liste.addWidget(ligne)

    # --- Actions -----------------------------------------------------------------------------

    def charger(self, enregistre: BriefEnregistre) -> None:
        self.brief_choisi = enregistre
        self.reprendre_page = self.case_page.isChecked()
        self.accept()

    def renommer(self, enregistre: BriefEnregistre) -> None:
        nom = messages.demander_texte(self, "Renommer le brief", "Nouveau nom", enregistre.nom, action="Renommer")
        if not nom or not nom.strip():
            return
        if not self._services.briefs.renommer(enregistre.identifiant, nom):
            messages.prevenir(self, "Renommer le brief", "Un autre brief porte déjà ce nom.", "Choisis un autre nom.")
            return
        self.rafraichir()

    def supprimer(self, enregistre: BriefEnregistre) -> None:
        if messages.confirmer(
            self,
            "Supprimer le brief",
            f"Supprimer le brief « {enregistre.nom} » de la bibliothèque ?",
            "Les projets qui l'utilisent gardent le leur.",
            action="Supprimer",
            icone_action="trash",
        ):
            self._services.briefs.retirer(enregistre.identifiant)
            self.rafraichir()
