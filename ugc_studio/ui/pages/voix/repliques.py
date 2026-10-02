"""Répliques du script (§5.3) : le script découpé en blocs, chacun avec son propre style.

Utile quand l'émotion change en cours de pub (ex. hook énergique → témoignage calme) : Google
conseille de découper en répliques avec un style court chacune, plutôt qu'une longue consigne.
Toutes les répliques partent ensemble dans la même génération.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ....projets import RepliqueProjet
from ....script import couper, est_vide
from ....services import Services
from ...composants.champ_style import ChampStyle
from ...composants.editeur_script import EditeurScript
from ...composants.elements import bouton, libelle, separateur
from ...composants.menu import Menu
from ...dialogues import messages
from ...icones import icone_menu
from ...theme import Couleurs, Espacements


class CarteReplique(QFrame):
    """Une réplique : titre et menu, champ style, éditeur à badges."""

    modifiee = Signal()
    activee = Signal(object)  # la carte dont l'éditeur vient de recevoir le focus
    action = Signal(str, object)  # (« decouper », « monter », « descendre », « supprimer », « bibliotheque »), carte

    def __init__(self, services: Services, replique: RepliqueProjet, parent=None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)

        entete = QHBoxLayout()
        entete.setSpacing(Espacements.S)
        self.titre = libelle("Réplique", "intitule", retour_a_la_ligne=False)
        entete.addWidget(self.titre)
        entete.addStretch(1)
        self.bouton_plus = bouton("", variante="icone", nom_icone="ellipsis")
        self.bouton_plus.setToolTip("Découper, déplacer ou supprimer la réplique")
        self.menu = Menu(self.bouton_plus)
        self.action_decouper = self.menu.addAction(icone_menu("scissors"), "Découper ici (au curseur)")
        self.action_decouper.triggered.connect(lambda: self.action.emit("decouper", self))
        self.action_monter = self.menu.addAction(icone_menu("arrow-up"), "Monter")
        self.action_monter.triggered.connect(lambda: self.action.emit("monter", self))
        self.action_descendre = self.menu.addAction(icone_menu("arrow-down"), "Descendre")
        self.action_descendre.triggered.connect(lambda: self.action.emit("descendre", self))
        self.menu.addSeparator()
        self.action_supprimer = self.menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer la réplique")
        self.action_supprimer.triggered.connect(lambda: self.action.emit("supprimer", self))
        self.bouton_plus.setMenu(self.menu)
        entete.addWidget(self.bouton_plus)
        disposition.addLayout(entete)

        # (Nom « champ_style » : « style » est déjà une fonction de tous les éléments Qt.)
        self.champ_style = ChampStyle(services)
        self.champ_style.definir(replique.style, replique.style_fr)
        self.champ_style.modifie.connect(self.modifiee.emit)
        self.champ_style.bibliotheque_demandee.connect(lambda: self.action.emit("bibliotheque", self))
        self.champ_style.balise_suggeree.connect(self.editeur_inserer_balise)
        disposition.addWidget(self.champ_style)

        self.editeur = EditeurScript(hauteur_auto=True)
        self.editeur.definir_segments(replique.script)
        self.editeur.script_modifie.connect(self.modifiee.emit)
        self.editeur.focus_recu.connect(lambda: self.activee.emit(self))
        disposition.addWidget(self.editeur)

    def replique(self) -> RepliqueProjet:
        return RepliqueProjet(self.editeur.segments(), self.champ_style.consigne(), self.champ_style.consigne_fr())

    def numeroter(self, numero: int, total: int) -> None:
        self.titre.setText(f"Réplique {numero}")
        self.action_monter.setEnabled(numero > 1)
        self.action_descendre.setEnabled(numero < total)
        self.action_supprimer.setEnabled(total > 1)

    def editeur_inserer_balise(self, nom: str) -> None:
        self.editeur.inserer_balise(nom)


class ListeRepliques(QWidget):
    """Les répliques du projet, l'une sous l'autre, séparées par un trait."""

    modifiee = Signal()
    bibliotheque_demandee = Signal(object)  # carte

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self._services = services
        self._cartes: list[CarteReplique] = []
        self._active: CarteReplique | None = None
        self._disposition = QVBoxLayout(self)
        self._disposition.setContentsMargins(0, 0, 0, 0)
        self._disposition.setSpacing(Espacements.L)

    # --- Contenu -----------------------------------------------------------------------------

    def definir(self, repliques: list[RepliqueProjet]) -> None:
        for carte in self._cartes:
            carte.hide()
            carte.deleteLater()
        self._cartes = []
        self._active = None
        for replique in repliques or [RepliqueProjet()]:
            self._cartes.append(self._nouvelle_carte(replique))
        self._reconstruire()

    def repliques(self) -> list[RepliqueProjet]:
        return [carte.replique() for carte in self._cartes]

    def cartes(self) -> list[CarteReplique]:
        return list(self._cartes)

    @property
    def carte_active(self) -> CarteReplique:
        """Carte où la palette insère les balises et où « Accentuer » agit (la dernière utilisée)."""
        return self._active if self._active in self._cartes else self._cartes[0]

    @property
    def editeur_actif(self) -> EditeurScript:
        return self.carte_active.editeur

    def ajouter(self, replique: RepliqueProjet | None = None, apres: CarteReplique | None = None) -> CarteReplique:
        carte = self._nouvelle_carte(replique or RepliqueProjet())
        index = self._cartes.index(apres) + 1 if apres in self._cartes else len(self._cartes)
        self._cartes.insert(index, carte)
        self._reconstruire()
        self._active = carte
        carte.editeur.setFocus()
        self.modifiee.emit()
        return carte

    # --- Actions du menu d'une réplique ------------------------------------------------------

    def _action(self, nom: str, carte: CarteReplique) -> None:
        if carte not in self._cartes:
            return
        index = self._cartes.index(carte)
        if nom == "bibliotheque":
            self._active = carte
            self.bibliotheque_demandee.emit(carte)
        elif nom == "decouper":
            self.decouper(carte)
        elif nom in ("monter", "descendre"):
            cible = index - 1 if nom == "monter" else index + 1
            if 0 <= cible < len(self._cartes):
                self._cartes[index], self._cartes[cible] = self._cartes[cible], self._cartes[index]
                self._reconstruire()
                self.modifiee.emit()
        elif nom == "supprimer":
            self.supprimer(carte)

    def decouper(self, carte: CarteReplique) -> CarteReplique | None:
        """La fin de la réplique (après le curseur) devient une nouvelle réplique, avec le même style."""
        avant, apres = couper(carte.editeur.segments(), carte.editeur.position_curseur())
        if est_vide(apres):
            return None
        carte.editeur.definir_segments(avant)
        style = carte.champ_style
        return self.ajouter(RepliqueProjet(apres, style.consigne(), style.consigne_fr()), apres=carte)

    def supprimer(self, carte: CarteReplique, confirmer: bool = True) -> None:
        if len(self._cartes) <= 1 or carte not in self._cartes:
            return
        if (
            confirmer
            and not est_vide(carte.editeur.segments())
            and not messages.confirmer(
                self.window(),
                "Supprimer la réplique",
                f"Supprimer la {carte.titre.text().lower()} et son texte ?",
                action="Supprimer",
                icone_action="trash",
            )
        ):
            return
        self._cartes.remove(carte)
        carte.hide()
        carte.deleteLater()
        if self._active is carte:
            self._active = None
        self._reconstruire()
        self.modifiee.emit()

    # --- Interne -----------------------------------------------------------------------------

    def _nouvelle_carte(self, replique: RepliqueProjet) -> CarteReplique:
        carte = CarteReplique(self._services, replique)
        carte.modifiee.connect(self.modifiee.emit)
        carte.activee.connect(self._activer)
        carte.action.connect(self._action)
        return carte

    def _activer(self, carte: CarteReplique) -> None:
        self._active = carte

    def _reconstruire(self) -> None:
        """Replace les cartes dans l'ordre, avec un trait entre deux répliques."""
        while self._disposition.count():
            element = self._disposition.takeAt(0)
            widget = element.widget()
            if widget is not None and not isinstance(widget, CarteReplique):
                widget.deleteLater()  # anciens traits
        for index, carte in enumerate(self._cartes):
            if index:
                self._disposition.addWidget(separateur())
            self._disposition.addWidget(carte)
            carte.numeroter(index + 1, len(self._cartes))
            carte.show()

