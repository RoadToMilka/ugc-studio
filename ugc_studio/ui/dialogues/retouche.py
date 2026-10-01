"""Retoucher un script (V2, lot 2, §10.9) : une consigne (« plus court », « plus drôle », « sans
tutoiement »…) donne un nouveau script, relu comme les autres ; l'ancien reste.

Les suggestions complètent la consigne en un clic. « Plus court » et « Plus long » changent aussi la
durée visée (d'un quart) : sinon, la relecture ramènerait le script à son ancienne durée. Le
tutoiement se choisit à part, pour la même raison (la relecture vérifie qu'il est constant).
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLayout, QPlainTextEdit, QVBoxLayout

from ...ecriture.affichage import titre_de_retouche
from ...ecriture.brief import DUREE_MAX, DUREE_MIN, Brief
from ...ecriture.redaction import estimer_retouche
from ...ecriture.scripts import ScriptEcrit
from ...estimation import MOTS_PAR_SECONDE
from ...fournisseurs.capacites import modele_connu
from ...services import Services
from ..composants.choix_voix import choisir
from ..composants.elements import bouton, champ_entier, info, libelle, liste_deroulante
from ..composants.montant_label import MontantLabel
from ..theme import Dimensions, Espacements

# (texte ajouté à la consigne, variation de la durée visée)
SUGGESTIONS = (
    ("Plus court", -0.25),
    ("Plus long", 0.25),
    ("Plus drôle", 0.0),
    ("Plus d'énergie", 0.0),
    ("Plus simple", 0.0),
    ("Plus naturel", 0.0),
)
TUTOIEMENTS_RETOUCHE = {"tu": "Tutoiement", "vous": "Vouvoiement"}


class DialogueRetouche(QDialog):
    """`brief` : le brief du projet (modèle, faits) ; la retouche garde le réseau et la langue du script."""

    def __init__(
        self,
        services: Services,
        script: ScriptEcrit,
        brief: Brief,
        page: str,
        mots_par_seconde: float = MOTS_PAR_SECONDE,
        parent=None,
    ):
        super().__init__(parent)
        self._services = services
        self._script = script
        self._brief = brief
        self._page = page
        self._mots_par_seconde = mots_par_seconde
        self.setWindowTitle("Retoucher le script")

        disposition = QVBoxLayout(self)
        # Jamais plus petite que son contenu : avec une simple largeur minimale (setMinimumWidth), Qt
        # ne protège plus la hauteur, et les champs se chevauchent sur un petit écran.
        disposition.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle(titre_de_retouche(script), "titre-bloc"))
        disposition.addWidget(
            info(
                "Ta consigne donne un nouveau script, relu avant d'arriver ; celui-ci reste tel quel.",
                "secondaire",
            )
        )
        disposition.addWidget(libelle(f"Accroche : « {script.accroche()} »", "legende"))

        disposition.addWidget(libelle("Consigne", "legende", retour_a_la_ligne=False))
        self.consigne = QPlainTextEdit()
        self.consigne.setFixedHeight(Dimensions.CHAMP_BRIEF_HAUTEUR)
        self.consigne.setTabChangesFocus(True)
        self.consigne.setPlaceholderText("ex. plus court, plus drôle, finis sur le code promo")
        self.consigne.textChanged.connect(self._actualiser)
        disposition.addWidget(self.consigne)
        suggestions = QGridLayout()
        suggestions.setHorizontalSpacing(Espacements.S)
        suggestions.setVerticalSpacing(Espacements.S)
        self.boutons_suggestions = []
        for rang, (texte, variation) in enumerate(SUGGESTIONS):
            suggestion = bouton(texte, variante="contour", nom_icone="plus")
            suggestion.clicked.connect(lambda _c=False, t=texte, v=variation: self.ajouter_suggestion(t, v))
            self.boutons_suggestions.append(suggestion)
            suggestions.addWidget(suggestion, rang // 3, rang % 3)
        suggestions.setColumnStretch(3, 1)
        disposition.addLayout(suggestions)

        reglages = QHBoxLayout()
        reglages.setSpacing(Espacements.L)
        colonne = QVBoxLayout()
        colonne.setSpacing(Espacements.XS)
        colonne.addWidget(libelle("Durée visée", "legende", retour_a_la_ligne=False))
        self.duree = champ_entier(DUREE_MIN, DUREE_MAX, " s", "Durée du nouveau script")
        self.duree.setValue(min(max(script.duree_visee_s or brief.duree_visee(), DUREE_MIN), DUREE_MAX))
        self.duree.valueChanged.connect(lambda _valeur: self._actualiser())
        colonne.addWidget(self.duree)
        reglages.addLayout(colonne)
        colonne = QVBoxLayout()
        colonne.setSpacing(Espacements.XS)
        colonne.addWidget(libelle("Tutoiement", "legende", retour_a_la_ligne=False))
        self.tutoiement = liste_deroulante("Façon de s'adresser à la personne qui regarde")
        for code, nom in TUTOIEMENTS_RETOUCHE.items():
            self.tutoiement.addItem(nom, code)
        choisir(self.tutoiement, script.tutoiement if script.tutoiement in TUTOIEMENTS_RETOUCHE else "tu")
        colonne.addWidget(self.tutoiement)
        reglages.addLayout(colonne)
        reglages.addStretch(1)
        disposition.addLayout(reglages)

        bas = QHBoxLayout()
        bas.setSpacing(Espacements.S)
        estimation = QHBoxLayout()
        estimation.setSpacing(Espacements.XS)
        connu = modele_connu(brief.modele)
        self.info_cout = libelle("Coût estimé ≈", "legende", retour_a_la_ligne=False)
        self.info_cout.setToolTip(f"Retouche, puis relecture du nouveau script, avec {connu.nom if connu else brief.modele}")
        estimation.addWidget(self.info_cout)
        self.cout = MontantLabel(0)
        self.cout.setProperty("role", "legende")
        estimation.addWidget(self.cout)
        bas.addLayout(estimation)
        bas.addStretch(1)
        bas.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_retoucher = bouton("Retoucher", variante="principal", nom_icone="wand-sparkles", action=self.accept)
        bas.addWidget(self.bouton_retoucher)
        disposition.addLayout(bas)
        self.resize(Dimensions.DIALOGUE_LARGEUR, 0)  # hauteur : celle du contenu
        self._actualiser()

    def ajouter_suggestion(self, texte: str, variation: float) -> None:
        """Ajoute la suggestion à la consigne ; « Plus court » et « Plus long » changent aussi la durée."""
        actuelle = self.texte_consigne()
        if texte.lower() not in actuelle.lower():
            self.consigne.setPlainText(f"{actuelle}, {texte.lower()}" if actuelle else texte)
        if variation:
            self.duree.setValue(round(self.duree.value() * (1 + variation)))

    def texte_consigne(self) -> str:
        return " ".join(self.consigne.toPlainText().split())

    def brief_de_retouche(self) -> Brief:
        """Le brief du projet, avec le réseau et la langue du script, la durée et le tutoiement choisis."""
        brief = Brief.depuis_dict(self._brief.en_dict())
        brief.reseau, brief.langue = self._script.reseau or brief.reseau, self._script.langue or brief.langue
        brief.duree_s = self.duree.value()
        brief.tutoiement = self.tutoiement.currentData() or brief.tutoiement
        return Brief.depuis_dict(brief.en_dict())  # valeurs revérifiées (langue connue…)

    def _actualiser(self) -> None:
        if not hasattr(self, "bouton_retoucher"):
            return  # construction en cours
        self.bouton_retoucher.setEnabled(bool(self.texte_consigne()))
        brief = self.brief_de_retouche()
        estimation = estimer_retouche(brief, self._page, self._script, self.texte_consigne() or "x", self._mots_par_seconde)
        cout = self._services.prix.cout_eur(brief.modele, estimation.tokens_entree, estimation.tokens_sortie)
        if cout is None:
            self.cout.setText("prix inconnu")
        else:
            self.cout.definir_montant(Decimal(cout))
