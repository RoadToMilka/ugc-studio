"""Onglet « Connexions API » (§4.1) : ajouter, tester, renommer, remplacer, supprimer les clés."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QMenu, QMessageBox, QVBoxLayout, QWidget

from ....connexions import Connexion, ErreurConnexion
from ....fournisseurs import creer_adaptateur, nom_fournisseur
from ....fournisseurs.base import ResultatTest
from ....services import Services
from ... import taches
from ...composants.elements import bloc, bouton, info, libelle, pastille, vider_disposition
from ...dialogues.cle_api import DialogueCle
from ...icones import icone, icone_menu
from ...theme import Couleurs, Dimensions, Espacements
from ..base import zone_defilante


def date_lisible(texte_iso: str) -> str:
    """« 2026-09-29T20:15:03+02:00 » → « 29/09/2026 à 20:15 »."""
    try:
        return datetime.fromisoformat(texte_iso).strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        return texte_iso


class LigneConnexion(QFrame):
    """Une clé : voyant, nom, fournisseur, aperçu, résultat du dernier test, actions."""

    def __init__(self, onglet: OngletConnexions, connexion: Connexion, test_en_cours: bool):
        super().__init__()
        self.setProperty("role", "ligne")
        self.connexion = connexion
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.M)

        # Voyant : vert si le dernier test a réussi, rouge s'il a échoué, gris sinon.
        test = connexion.dernier_test
        role_voyant = "discret" if test is None else ("succes" if test.ok else "erreur")
        self.voyant = libelle("●", role_voyant, retour_a_la_ligne=False)
        disposition.addWidget(self.voyant)

        textes = QVBoxLayout()
        textes.setSpacing(Espacements.XS)
        ligne_nom = QHBoxLayout()
        ligne_nom.setSpacing(Espacements.S)
        ligne_nom.addWidget(libelle(connexion.nom, "titre-bloc", retour_a_la_ligne=False))
        if connexion.par_defaut:
            ligne_nom.addWidget(pastille("Par défaut"))
        ligne_nom.addStretch(1)
        textes.addLayout(ligne_nom)
        textes.addWidget(
            libelle(f"{nom_fournisseur(connexion.fournisseur)}  ·  {connexion.apercu}", "legende", retour_a_la_ligne=False)
        )
        if test_en_cours:
            etat = libelle("Test en cours…", "secondaire")
        elif test is None:
            etat = libelle("Pas encore testée.", "discret")
        else:
            etat = libelle(f"Testée le {date_lisible(test.date)} : {test.message}", "succes" if test.ok else "erreur")
        self.etat = etat
        textes.addWidget(etat)
        disposition.addLayout(textes, 1)

        self.bouton_tester = bouton("Tester", nom_icone="refresh-cw", action=lambda: onglet.tester(connexion.identifiant))
        self.bouton_tester.setEnabled(not test_en_cours)
        disposition.addWidget(self.bouton_tester)

        plus = bouton("", variante="icone")
        plus.setIcon(icone("ellipsis", Couleurs.TEXTE_SECONDAIRE))
        plus.setIconSize(QSize(Dimensions.ICONE, Dimensions.ICONE))
        plus.setToolTip("Plus d'actions")
        menu = QMenu(plus)
        action_defaut = menu.addAction(icone_menu("star"), "Définir par défaut")
        action_defaut.setEnabled(not connexion.par_defaut)
        action_defaut.triggered.connect(lambda: onglet.definir_par_defaut(connexion.identifiant))
        menu.addAction(icone_menu("pencil"), "Renommer…").triggered.connect(
            lambda: onglet.renommer(connexion.identifiant)
        )
        menu.addAction(icone_menu("key-round"), "Remplacer la clé…").triggered.connect(
            lambda: onglet.remplacer(connexion.identifiant)
        )
        menu.addSeparator()
        menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer…").triggered.connect(
            lambda: onglet.supprimer(connexion.identifiant)
        )
        plus.setMenu(menu)
        disposition.addWidget(plus)


class OngletConnexions(QWidget):
    def __init__(self, services: Services):
        super().__init__()
        self._services = services
        self._tests_en_cours: set[str] = set()

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        zone, contenu = zone_defilante(marges=(0, Espacements.XL, 0, Espacements.XXL))
        disposition.addWidget(zone)

        cadre, self._liste = bloc("Clés API")
        self._liste.addWidget(
            info(
                "Tes clés sont rangées dans le coffre-fort de Windows (Gestionnaire d'identification). "
                "L'app ne les réaffiche jamais en entier.",
                "secondaire",
            )
        )
        self._lignes = QVBoxLayout()
        self._lignes.setSpacing(0)
        self._liste.addLayout(self._lignes)
        actions = QHBoxLayout()
        actions.addWidget(bouton("Ajouter une clé", variante="principal", nom_icone="plus", action=self.ajouter))
        actions.addStretch(1)
        self._liste.addSpacing(Espacements.S)
        self._liste.addLayout(actions)
        contenu.addWidget(cadre)

        services.connexions.abonner(self.rafraichir)
        self.rafraichir()

    # --- Affichage ---------------------------------------------------------------------------

    def rafraichir(self) -> None:
        vider_disposition(self._lignes)
        connexions = self._services.connexions.lister()
        if not connexions:
            self._lignes.addWidget(
                libelle("Aucune clé pour l'instant. Ajoute ta clé Google pour commencer.", "discret")
            )
        for connexion in connexions:
            self._lignes.addWidget(LigneConnexion(self, connexion, connexion.identifiant in self._tests_en_cours))

    def lignes(self) -> list[LigneConnexion]:
        return [
            self._lignes.itemAt(i).widget()
            for i in range(self._lignes.count())
            if isinstance(self._lignes.itemAt(i).widget(), LigneConnexion)
        ]

    # --- Actions -----------------------------------------------------------------------------

    def ajouter(self) -> DialogueCle:
        dialogue = DialogueCle(self._services.connexions, self.window())
        dialogue.open()
        return dialogue

    def remplacer(self, identifiant: str) -> DialogueCle:
        dialogue = DialogueCle(
            self._services.connexions, self.window(), a_remplacer=self._services.connexions.connexion(identifiant)
        )
        dialogue.open()
        return dialogue

    def tester(self, identifiant: str) -> None:
        gestion = self._services.connexions
        try:
            connexion = gestion.connexion(identifiant)
            adaptateur = creer_adaptateur(connexion.fournisseur, gestion.lire_cle(identifiant))
        except ErreurConnexion as erreur:
            gestion.enregistrer_test(identifiant, False, str(erreur))
            return
        self._tests_en_cours.add(identifiant)
        self.rafraichir()

        def fin(resultat: ResultatTest) -> None:
            self._tests_en_cours.discard(identifiant)
            gestion.enregistrer_test(identifiant, resultat.ok, resultat.message, [m.identifiant for m in resultat.modeles])

        def echec(erreur: Exception) -> None:
            self._tests_en_cours.discard(identifiant)
            gestion.enregistrer_test(identifiant, False, f"Test interrompu : {erreur}")

        taches.lancer(adaptateur.tester_cle, fin, echec)

    def definir_par_defaut(self, identifiant: str) -> None:
        self._services.connexions.definir_par_defaut(identifiant)

    def renommer(self, identifiant: str) -> None:
        connexion = self._services.connexions.connexion(identifiant)
        nom, ok = QInputDialog.getText(self, "Renommer la clé", "Nouveau nom :", text=connexion.nom)
        if ok and nom.strip():
            self._services.connexions.renommer(identifiant, nom)

    def supprimer(self, identifiant: str) -> None:
        connexion = self._services.connexions.connexion(identifiant)
        boite = QMessageBox(self.window())
        boite.setIcon(QMessageBox.Icon.Warning)
        boite.setWindowTitle("Supprimer la clé")
        boite.setText(f"Supprimer la clé « {connexion.nom} » ?")
        boite.setInformativeText("Elle sera aussi retirée du coffre-fort de Windows. Cette action est définitive.")
        confirmer = boite.addButton("Supprimer", QMessageBox.ButtonRole.DestructiveRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.exec()
        if boite.clickedButton() is confirmer:
            self._services.connexions.supprimer(identifiant)
