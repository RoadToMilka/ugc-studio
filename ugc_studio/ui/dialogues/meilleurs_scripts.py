"""« Mes meilleurs scripts » (V2, lot 2, §10.9) : les exemples donnés au modèle quand il écrit.

- Tes scripts : gardés depuis l'app (« Garder comme exemple ») ou collés ici (« Ajouter un script qui
  a marché… »), chacun avec ta note libre (ex. « CPA 9 € »), lue par le modèle avec l'exemple.
- Les 5 scripts fournis avec l'app (produits imaginaires) : à retirer quand tu as assez de vrais
  scripts ; « Remettre les exemples fournis » les fait revenir.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from ...ecriture.affichage import nom_angle
from ...ecriture.brief import ANGLES, DUREE_MAX, LANGUES_ECRITURE, RESEAUX, Brief
from ...ecriture.exemples import ExempleScript, exemple_colle
from ...services import Services
from ..composants.choix_voix import choisir
from ..composants.conseils import entete_de_fenetre
from ..composants.defilement import zone_defilante
from ..composants.elements import (
    bouton,
    champ_entier,
    conteneur_vertical,
    info,
    libelle,
    liste_deroulante,
    pastille,
    separateur,
    vider_disposition,
)
from ..icones import icone_menu
from ..theme import Couleurs, Dimensions, Espacements, Hauteurs

TUTOIEMENTS_EXEMPLE = {"tu": "Tutoiement", "vous": "Vouvoiement"}


def details_de_l_exemple(exemple: ExempleScript) -> str:
    """« Français (France) · TikTok · Témoignage · 25 s · tutoiement »."""
    morceaux = [
        LANGUES_ECRITURE.get(exemple.langue, (exemple.langue,))[0],
        RESEAUX.get(exemple.reseau, exemple.reseau),
        nom_angle(exemple.angle) or "offre directe",
        f"{exemple.duree_s} s",
        "vouvoiement" if exemple.tutoiement == "vous" else "tutoiement",
    ]
    return "  ·  ".join(m for m in morceaux if m)


class LigneExemple(QFrame):
    def __init__(self, dialogue: DialogueMeilleursScripts, exemple: ExempleScript):
        super().__init__()
        self.setProperty("role", "ligne")
        self.exemple = exemple
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.M)
        textes = QVBoxLayout()
        textes.setSpacing(Espacements.XS)
        titre = QHBoxLayout()
        titre.setSpacing(Espacements.S)
        titre.addWidget(libelle(exemple.titre, "intitule", retour_a_la_ligne=False))
        if exemple.fourni:
            fourni = pastille("Fourni")
            fourni.setToolTip("Script fourni avec l'app, sur un produit imaginaire")
            titre.addWidget(fourni)
        titre.addStretch(1)
        textes.addLayout(titre)
        textes.addWidget(libelle(details_de_l_exemple(exemple), "legende"))
        repliques = "\n".join(str(r.get("texte") or "") for r in exemple.repliques)
        textes.addWidget(libelle(repliques, "secondaire", selectionnable=True))
        if exemple.pourquoi:
            textes.addWidget(libelle(f"Pourquoi il marche : {exemple.pourquoi}", "legende"))
        self.note: QLineEdit | None = None
        if not exemple.fourni:
            self.note = QLineEdit(exemple.note)
            self.note.setPlaceholderText("Ta note, lue par le modèle (ex. CPA 9 €, meilleur ROAS)")
            self.note.editingFinished.connect(lambda: dialogue.noter(exemple, self.note.text()))
            textes.addWidget(self.note)
        disposition.addLayout(textes, 1)
        plus = bouton("", variante="icone", nom_icone="ellipsis")
        plus.setToolTip("Plus d'actions")
        menu = QMenu(plus)
        menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Retirer des exemples…").triggered.connect(
            lambda: dialogue.retirer(exemple)
        )
        plus.setMenu(menu)
        disposition.addWidget(plus, 0, Qt.AlignmentFlag.AlignTop)


class DialogueMeilleursScripts(QDialog):
    """`brief` : le brief du projet ouvert (langue et réseau proposés pour un script collé)."""

    def __init__(self, services: Services, brief: Brief | None = None, parent=None):
        super().__init__(parent)
        self._services = services
        self._brief = brief or Brief()
        self.setWindowTitle("Mes meilleurs scripts")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre("Mes meilleurs scripts", "meilleurs-scripts"))
        disposition.addWidget(
            info(
                "Le modèle s'en inspire (ton, rythme) pour écrire tes scripts, sans les recopier : jusqu'à 3 par "
                "demande, les plus proches. Tes scripts passent avant les scripts fournis.",
                "secondaire",
            )
        )
        zone, contenu = zone_defilante(largeur_max=None)
        self._liste_widget, self._liste = conteneur_vertical(Espacements.XS)
        contenu.addWidget(self._liste_widget)
        disposition.addWidget(zone, 1)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addWidget(bouton("Ajouter un script qui a marché…", nom_icone="clipboard-paste", action=self.ajouter))
        self.bouton_remettre = bouton(
            "Remettre les exemples fournis", variante="contour", nom_icone="rotate-ccw", action=self.remettre
        )
        boutons.addWidget(self.bouton_remettre)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Fermer", action=self.reject))
        disposition.addLayout(boutons)
        self._lignes: list[LigneExemple] = []
        self.rafraichir()

    def lignes(self) -> list[LigneExemple]:
        return list(self._lignes)

    def rafraichir(self) -> None:
        vider_disposition(self._liste)
        self._lignes = []
        bibliotheque = self._services.exemples
        gardes = bibliotheque.gardes()
        fournis = [e for e in bibliotheque.exemples() if e.fourni]
        for rang, (titre, exemples, vide) in enumerate(
            (
                ("Tes scripts", gardes, "Aucun pour l'instant : « Garder comme exemple » (menu ⋯ d'un script), ou colle un script qui a marché."),
                ("Fournis avec l'app", fournis, "Tous retirés : « Remettre les exemples fournis » les fait revenir."),
            )
        ):
            if rang:
                self._liste.addSpacing(Espacements.M)
            self._liste.addWidget(libelle(titre, "legende"))
            self._liste.addWidget(separateur())
            if not exemples:
                self._liste.addWidget(libelle(vide, "discret"))
            for exemple in reversed(exemples) if rang == 0 else exemples:
                ligne = LigneExemple(self, exemple)
                self._lignes.append(ligne)
                self._liste.addWidget(ligne)
        self.bouton_remettre.setVisible(bool(bibliotheque.fournis_retires()))

    # --- Actions -----------------------------------------------------------------------------

    def noter(self, exemple: ExempleScript, note: str) -> None:
        if " ".join(note.split()) != exemple.note:
            self._services.exemples.noter(exemple.identifiant, note)

    def retirer(self, exemple: ExempleScript) -> None:
        if exemple.fourni:
            question = f"Retirer « {exemple.titre} » des exemples ? « Remettre les exemples fournis » le fera revenir."
        else:
            question = f"Retirer « {exemple.titre} » de tes exemples ? Le modèle ne s'en inspirera plus."
        reponse = QMessageBox.question(
            self,
            "Retirer l'exemple",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reponse == QMessageBox.StandardButton.Yes:
            self._services.exemples.retirer(exemple.identifiant)
            self.rafraichir()

    def remettre(self) -> None:
        self._services.exemples.remettre_fournis()
        self.rafraichir()

    def ajouter(self) -> None:
        dialogue = DialogueAjoutExemple(self._brief, self)
        if dialogue.exec() and dialogue.exemple is not None:
            self._services.exemples.ajouter(dialogue.exemple)
            self.rafraichir()


class DialogueAjoutExemple(QDialog):
    """« Ajouter un script qui a marché » : un script écrit ailleurs, collé avec sa langue, son réseau,
    son angle… Une réplique par paragraphe, l'accroche en premier. Après « Ajouter » : `exemple`."""

    def __init__(self, brief: Brief, parent=None):
        super().__init__(parent)
        self.exemple: ExempleScript | None = None
        self.setWindowTitle("Ajouter un script qui a marché")
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("Ajouter un script qui a marché", "titre-bloc"))
        disposition.addWidget(
            info("Une réplique par paragraphe (sépare-les par une ligne vide), l'accroche en premier.", "secondaire")
        )
        self.titre = QLineEdit(brief.produit.strip())
        self.titre.setPlaceholderText("ex. Gourde isotherme")
        self.texte = QPlainTextEdit()
        self.texte.setFixedHeight(Dimensions.CHAMP_TEXTE_COLLE_HAUTEUR)
        self.texte.setTabChangesFocus(True)
        self.texte.setPlaceholderText("Colle ici le texte du script")
        self.texte.textChanged.connect(self._actualiser)
        self.langue = liste_deroulante()
        for code, (nom, _anglais) in LANGUES_ECRITURE.items():
            self.langue.addItem(nom, code)
        choisir(self.langue, brief.langue)
        self.reseau = liste_deroulante()
        for code, nom in RESEAUX.items():
            self.reseau.addItem(nom, code)
        choisir(self.reseau, brief.reseau)
        self.angle = liste_deroulante()
        self.angle.addItem("Offre directe, ou autre", "")
        for code, nom in ANGLES.items():
            if code != "auto":
                self.angle.addItem(nom, code)
        self.tutoiement = liste_deroulante()
        for code, nom in TUTOIEMENTS_EXEMPLE.items():
            self.tutoiement.addItem(nom, code)
        choisir(self.tutoiement, brief.tutoiement_effectif())
        self.duree = champ_entier(0, DUREE_MAX, " s", "Durée de la pub. « Auto » : estimée d'après le texte")
        self.duree.setSpecialValueText("Auto")
        self.note = QLineEdit()
        self.note.setPlaceholderText("ex. CPA 9 €, meilleur ROAS du mois")

        formulaire = QGridLayout()
        formulaire.setHorizontalSpacing(Espacements.M)
        formulaire.setVerticalSpacing(Espacements.S)
        for rang, (titre, element) in enumerate(
            (
                ("Produit", self.titre),
                ("Script", self.texte),
                ("Langue", self.langue),
                ("Réseau", self.reseau),
                ("Angle", self.angle),
                ("Tutoiement", self.tutoiement),
                ("Durée", self.duree),
                ("Ta note", self.note),
            )
        ):
            etiquette = libelle(titre, "legende", retour_a_la_ligne=False)
            etiquette.setFixedHeight(Hauteurs.CONTROLE)
            formulaire.addWidget(etiquette, rang, 0, Qt.AlignmentFlag.AlignTop)
            formulaire.addWidget(element, rang, 1, Qt.AlignmentFlag.AlignTop if element is self.texte else Qt.AlignmentFlag.AlignVCenter)
        formulaire.setColumnStretch(1, 1)
        disposition.addLayout(formulaire, 1)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_ajouter = bouton("Ajouter", variante="principal", nom_icone="plus", action=self.valider)
        boutons.addWidget(self.bouton_ajouter)
        disposition.addLayout(boutons)
        self._actualiser()

    def _actualiser(self) -> None:
        self.bouton_ajouter.setEnabled(bool(self.texte.toPlainText().strip()))

    def valider(self) -> None:
        self.exemple = exemple_colle(
            self.titre.text(),
            self.texte.toPlainText(),
            self.langue.currentData() or "fr-FR",
            self.reseau.currentData() or "autre",
            self.angle.currentData() or "",
            self.tutoiement.currentData() or "tu",
            self.duree.value(),
            self.note.text(),
        )
        if self.exemple is not None:
            self.accept()
