"""Dialogue « Ajouter une clé API » (§4.1), aussi utilisé pour remplacer une clé existante.

La clé est d'abord testée auprès du fournisseur ; elle n'est enregistrée (dans le coffre-fort
de Windows) que si le test réussit. En cas de problème de connexion Internet, on peut
l'enregistrer sans test et la tester plus tard.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QStandardItemModel
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLineEdit

from ...connexions import Connexion, ErreurConnexion, GestionnaireConnexions, nettoyer_cle
from ...fournisseurs import ADAPTATEURS, FOURNISSEURS_PREVUS, creer_adaptateur
from ...fournisseurs.base import Adaptateur, ResultatTest
from .. import taches
from ..composants.bouton import activer_avec_entree, montrer_occupe
from ..composants.conseils import entete_de_fenetre
from ..composants.elements import ChampNomme, afficher_message, bouton, info, libelle, liste_deroulante
from ..composants.fenetre import fenetre_en_bloc
from ..icones import icone
from ..theme import Couleurs, Dimensions, Espacements

journal = logging.getLogger(__name__)

NOM_PAR_DEFAUT = "Google perso"


class DialogueCle(QDialog):
    def __init__(
        self,
        connexions: GestionnaireConnexions,
        parent=None,
        a_remplacer: Connexion | None = None,
        fabrique: Callable[[str, str], Adaptateur] = creer_adaptateur,
    ):
        super().__init__(parent)
        self._connexions = connexions
        self._a_remplacer = a_remplacer
        self._fabrique = fabrique
        self.connexion_enregistree: Connexion | None = None
        self._cle_en_test = ""

        remplacement = a_remplacer is not None
        self.setWindowTitle("Remplacer la clé" if remplacement else "Ajouter une clé API")
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)

        fenetre, self.cadre, disposition = fenetre_en_bloc(self, titre_avec_boutons=True)
        disposition.setSpacing(Espacements.M)
        titre = f"Remplacer la clé « {a_remplacer.nom} »" if remplacement else "Ajouter une clé API"
        disposition.addLayout(entete_de_fenetre(titre, "cle-api"))

        # Fournisseur (les fournisseurs prévus plus tard sont visibles mais grisés)
        self.fournisseur = liste_deroulante()
        for identifiant, classe in ADAPTATEURS.items():
            self.fournisseur.addItem(classe.nom, identifiant)
        modele = self.fournisseur.model()
        for prevu in FOURNISSEURS_PREVUS:
            self.fournisseur.addItem(f"{prevu.nom} (bientôt, {prevu.version})", prevu.identifiant)
            if isinstance(modele, QStandardItemModel):
                modele.item(self.fournisseur.count() - 1).setEnabled(False)
        if remplacement:
            self.fournisseur.setCurrentIndex(self.fournisseur.findData(a_remplacer.fournisseur))
        self._ajouter_champ(disposition, "Fournisseur", self.fournisseur, visible=not remplacement)

        self.nom = QLineEdit(NOM_PAR_DEFAUT)
        self.nom.setPlaceholderText("ex. « Google perso »")
        self._ajouter_champ(disposition, "Nom (libre, pour t'y retrouver)", self.nom, visible=not remplacement)

        self.cle = QLineEdit()
        self.cle.setEchoMode(QLineEdit.EchoMode.Password)
        self.cle.setPlaceholderText("Colle ta clé ici")
        self._action_voir = self.cle.addAction(
            icone("eye", Couleurs.TEXTE_SECONDAIRE), QLineEdit.ActionPosition.TrailingPosition
        )
        self._action_voir.setToolTip("Afficher la clé")
        self._action_voir.triggered.connect(self._basculer_affichage)
        self._ajouter_champ(disposition, "Clé API", self.cle)

        classe = ADAPTATEURS[self._fournisseur_choisi()]
        aide = QHBoxLayout()
        aide.setSpacing(Espacements.S)
        aide.addWidget(info(classe.aide_cle), 1)
        if classe.adresse_cles:
            aide.addWidget(
                bouton(
                    "Ouvrir Google AI Studio",
                    variante="contour",
                    nom_icone="external-link",
                    action=lambda: QDesktopServices.openUrl(QUrl(classe.adresse_cles)),
                )
            )
        disposition.addLayout(aide)

        self.statut = libelle("", "secondaire")
        self.statut.hide()
        disposition.addWidget(self.statut)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_sans_test = bouton("Enregistrer sans tester", variante="contour", action=self._enregistrer_sans_test)
        self.bouton_sans_test.hide()
        boutons.addWidget(self.bouton_sans_test)
        boutons.addStretch(1)
        self.bouton_annuler = bouton("Annuler", action=self.reject)
        boutons.addWidget(self.bouton_annuler)
        self.bouton_valider = bouton("Tester et enregistrer", variante="principal", nom_icone="key-round", action=self.valider)
        activer_avec_entree(self.bouton_valider, self)  # la touche Entrée valide
        boutons.addWidget(self.bouton_valider)
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)

        (self.cle if remplacement else self.nom).setFocus()

    # --- Construction ------------------------------------------------------------------------

    @staticmethod
    def _ajouter_champ(disposition, titre, champ, visible=True) -> None:
        """Un champ sous son nom, 8 px visibles au-dessus (V3.2), comme partout ; caché avec son nom
        (ex. le fournisseur d'une clé qu'on remplace)."""
        nomme = ChampNomme(titre, champ, etire=True)
        nomme.setVisible(visible)
        champ.setVisible(visible)
        disposition.addWidget(nomme)

    def _fournisseur_choisi(self) -> str:
        return self.fournisseur.currentData()

    def _basculer_affichage(self) -> None:
        visible = self.cle.echoMode() == QLineEdit.EchoMode.Password
        self.cle.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self._action_voir.setIcon(icone("eye-off" if visible else "eye", Couleurs.TEXTE_SECONDAIRE))
        self._action_voir.setToolTip("Masquer la clé" if visible else "Afficher la clé")

    def _afficher_statut(self, texte: str, role: str) -> None:
        afficher_message(self.statut, texte, role)  # vert ou rouge : effacé après 8 s (V3.2)

    def _occupe(self, occupe: bool) -> None:
        """Pendant le test : le cercle tourne dans « Tester et enregistrer » (V3.1), qui garde son
        aspect ; les champs sont grisés."""
        montrer_occupe(self.bouton_valider, occupe)
        for element in (self.fournisseur, self.nom, self.cle, self.bouton_sans_test):
            element.setEnabled(not occupe)

    # --- Test puis enregistrement ------------------------------------------------------------

    def valider(self) -> None:
        cle = nettoyer_cle(self.cle.text())
        if not cle:
            self._afficher_statut("Colle ta clé dans le champ « Clé API ».", "erreur")
            return
        self._cle_en_test = cle
        self._occupe(True)
        self.bouton_sans_test.hide()
        self._afficher_statut("Test de la clé en cours…", "secondaire")
        adaptateur = self._fabrique(self._fournisseur_choisi(), cle)
        taches.lancer(adaptateur.tester_cle, self._resultat_test, self._echec_test)

    def _resultat_test(self, resultat: ResultatTest) -> None:
        self._occupe(False)
        if resultat.ok:
            self._enregistrer(resultat)
            return
        self._afficher_statut(resultat.message, "erreur")
        if resultat.code == "reseau":
            self.bouton_sans_test.show()

    def _echec_test(self, erreur: Exception) -> None:
        self._occupe(False)
        self._afficher_statut(f"Le test n'a pas pu aller au bout : {erreur}", "erreur")

    def _enregistrer_sans_test(self) -> None:
        self._cle_en_test = nettoyer_cle(self.cle.text())
        if self._cle_en_test:
            self._enregistrer(None)

    def _enregistrer(self, resultat: ResultatTest | None) -> None:
        try:
            if self._a_remplacer is not None:
                self._connexions.remplacer_cle(self._a_remplacer.identifiant, self._cle_en_test)
                connexion = self._connexions.connexion(self._a_remplacer.identifiant)
            else:
                connexion = self._connexions.ajouter(self._fournisseur_choisi(), self.nom.text(), self._cle_en_test)
            if resultat is not None:
                self._connexions.enregistrer_test(
                    connexion.identifiant, True, resultat.message, [m.identifiant for m in resultat.modeles]
                )
        except ErreurConnexion as erreur:
            self._afficher_statut(f"Enregistrement impossible : {erreur}", "erreur")
            return
        except Exception:  # noqa: BLE001 — ex. coffre-fort de Windows indisponible
            journal.exception("Enregistrement de la clé impossible")
            self._afficher_statut(
                "Enregistrement impossible dans le coffre-fort de Windows. Détails dans le journal d'erreurs.",
                "erreur",
            )
            return
        self.connexion_enregistree = connexion
        self._cle_en_test = ""
        self.cle.clear()
        self.accept()
