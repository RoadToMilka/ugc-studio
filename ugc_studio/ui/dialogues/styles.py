"""Bibliothèque de styles personnalisés (§5.5) : la liste, et la fenêtre pour créer / modifier un style.

Un style enregistré = nom, catégorie, modèle, voix, consigne (en anglais, envoyée à Google) avec
sa traduction française, balises souvent utilisées, langue. « Appliquer » le met sur une réplique
en un clic (et choisit sa voix et son modèle).
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QVBoxLayout,
)

from ...balises import est_balise
from ...conseils import CONSEILS_STYLE
from ...fournisseurs.capacites import MODELES_CONNUS, Capacite, modele_connu
from ...fournisseurs.google_voix import VOIX_GOOGLE, voix_de_base
from ...projets import LANGUE_PAR_DEFAUT, LANGUES
from ...services import Services
from ...styles import Style
from ..composants.bouton import activer_avec_entree
from ..composants.champ_style import ChampStyle
from ..composants.conseils import ListeConseils
from ..composants.elements import bouton, conteneur_vertical, libelle, separateur, vider_disposition
from ..icones import icone_menu
from ..pages.base import zone_defilante
from ..theme import Couleurs, Dimensions, Espacements, Hauteurs


def description(style: Style) -> str:
    """« Kore · Gemini 3.8 Flash TTS · balises : laugh, short pause »."""
    connu = modele_connu(style.modele)
    morceaux = [style.voix, connu.nom if connu else style.modele]
    if style.balises:
        morceaux.append("balises : " + ", ".join(style.balises))
    return "  ·  ".join(morceaux)


def lire_balises(texte: str) -> tuple[list[str], list[str]]:
    """« laugh, short pause, truc » → (balises connues, noms inconnus)."""
    connues, inconnues = [], []
    for morceau in texte.replace("<", " ").replace(">", " ").split(","):
        nom = " ".join(morceau.lower().split())
        if nom:
            (connues if est_balise(nom) else inconnues).append(nom)
    return connues, inconnues


# ---------------------------------------------------------------------------------------------
# Créer / modifier un style
# ---------------------------------------------------------------------------------------------


class DialogueStyle(QDialog):
    def __init__(self, services: Services, style: Style, parent=None, titre: str = "Nouveau style"):
        super().__init__(parent)
        self._services = services
        self._style = style
        self.setWindowTitle(titre)
        self.setMinimumSize(Dimensions.DIALOGUE_STYLE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle(titre, "titre-bloc"))

        colonnes = QHBoxLayout()
        colonnes.setSpacing(Espacements.XL)
        formulaire = QGridLayout()
        formulaire.setHorizontalSpacing(Espacements.M)
        formulaire.setVerticalSpacing(Espacements.S)

        self.nom = QLineEdit(style.nom)
        self.nom.setPlaceholderText("ex. Hook énergique")
        self.categorie = QComboBox()
        self.categorie.setEditable(True)
        self.categorie.addItems(services.styles.categories())
        self.categorie.setCurrentText(style.categorie or services.styles.categories()[0])
        self.modele = QComboBox()
        for modele in MODELES_CONNUS:
            if Capacite.TTS in modele.capacites:
                self.modele.addItem(modele.nom, modele.identifiant)
        self._choisir(self.modele, style.modele)
        self.voix = QComboBox()
        for voix in VOIX_GOOGLE:
            self.voix.addItem(voix.libelle, voix.nom)
        self._choisir(self.voix, style.voix)
        self.langue = QComboBox()
        for code, nom in LANGUES.items():
            self.langue.addItem(nom, code)
        self._choisir(self.langue, style.langue or LANGUE_PAR_DEFAUT)
        self.champ_style = ChampStyle(services, avec_bibliotheque=False)
        self.champ_style.definir(style.consigne, style.consigne_fr)
        self.balises = QLineEdit(", ".join(style.balises))
        self.balises.setPlaceholderText("ex. laugh, short pause")

        for rang, (titre, element) in enumerate(
            (
                ("Nom", self.nom),
                ("Catégorie", self.categorie),
                ("Modèle", self.modele),
                ("Voix", self.voix),
                ("Langue", self.langue),
                ("Style", self.champ_style),
                ("Balises souvent utilisées", self.balises),
            )
        ):
            # Libellé centré sur la hauteur d'un champ (ligne du haut de l'élément).
            etiquette = libelle(titre, "legende", retour_a_la_ligne=False)
            etiquette.setFixedHeight(Hauteurs.CONTROLE)
            formulaire.addWidget(etiquette, rang, 0, Qt.AlignmentFlag.AlignTop)
            formulaire.addWidget(element, rang, 1, Qt.AlignmentFlag.AlignTop)
        formulaire.setColumnStretch(1, 1)
        formulaire.setRowStretch(formulaire.rowCount(), 1)  # l'espace libre va sous les champs
        colonnes.addLayout(formulaire, 1)

        # Conseils Google : colonne de largeur fixe, qui défile si besoin.
        zone, conseils = zone_defilante(largeur_max=None)
        zone.setFixedWidth(Dimensions.PANNEAU_CONSEILS_LARGEUR)
        conseils.setSpacing(Espacements.S)
        conseils.addWidget(libelle("Conseils Google", "intitule"))
        conseils.addWidget(ListeConseils(CONSEILS_STYLE))
        colonnes.addWidget(zone)
        disposition.addLayout(colonnes, 1)

        self.statut = libelle("", "erreur")
        self.statut.hide()
        disposition.addWidget(self.statut)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_enregistrer = bouton("Enregistrer le style", variante="principal", nom_icone="check", action=self.valider)
        activer_avec_entree(self.bouton_enregistrer, self)
        boutons.addWidget(self.bouton_enregistrer)
        disposition.addLayout(boutons)

    @staticmethod
    def _choisir(liste: QComboBox, valeur: str) -> None:
        index = liste.findData(valeur)
        if index >= 0:
            liste.setCurrentIndex(index)

    def style_saisi(self) -> Style:
        """Le style tel que rempli dans la fenêtre. (Pas « style() » : nom déjà pris par Qt.)"""
        connues, _inconnues = lire_balises(self.balises.text())
        return replace(
            self._style,
            nom=" ".join(self.nom.text().split()),
            categorie=" ".join(self.categorie.currentText().split()),
            consigne=self.champ_style.consigne(),
            consigne_fr=self.champ_style.consigne_fr(),
            modele=self.modele.currentData() or self._style.modele,
            voix=self.voix.currentData() or self._style.voix,
            balises=connues,
            langue=self.langue.currentData() or LANGUE_PAR_DEFAUT,
        )

    def valider(self) -> None:
        _connues, inconnues = lire_balises(self.balises.text())
        style = self.style_saisi()
        if not style.nom:
            erreur = "Donne un nom au style."
        elif not style.consigne:
            erreur = "Écris la consigne de style (en anglais), ou utilise l'assistant."
        elif inconnues:
            erreur = "Balises inconnues : " + ", ".join(inconnues) + ". Utilise les noms de la palette (ex. laugh)."
        else:
            self._services.styles.enregistrer_style(style)
            self.accept()
            return
        self.statut.setText(erreur)
        self.statut.show()


# ---------------------------------------------------------------------------------------------
# Liste des styles
# ---------------------------------------------------------------------------------------------


class LigneStyle(QFrame):
    def __init__(self, dialogue: DialogueBibliothequeStyles, style: Style, avec_appliquer: bool):
        super().__init__()
        self.setProperty("role", "ligne")
        self.style_enregistre = style
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.M)

        textes = QVBoxLayout()
        textes.setSpacing(0)
        textes.addWidget(libelle(style.nom, "intitule"))
        textes.addWidget(libelle(style.consigne, "secondaire", selectionnable=True))
        if style.consigne_fr:
            textes.addWidget(libelle(f"Traduction : {style.consigne_fr}", "legende"))
        textes.addWidget(libelle(description(style), "legende"))
        disposition.addLayout(textes, 1)

        if avec_appliquer:
            self.bouton_appliquer = bouton("Appliquer", action=lambda: dialogue.appliquer(style.identifiant))
            disposition.addWidget(self.bouton_appliquer, 0, Qt.AlignmentFlag.AlignVCenter)
        plus = bouton("", variante="icone", nom_icone="ellipsis")
        plus.setToolTip("Plus d'actions")
        menu = QMenu(plus)
        menu.addAction(icone_menu("square-pen"), "Modifier…").triggered.connect(
            lambda: dialogue.modifier(style.identifiant)
        )
        menu.addAction(icone_menu("copy"), "Dupliquer").triggered.connect(lambda: dialogue.dupliquer(style.identifiant))
        menu.addSeparator()
        menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer…").triggered.connect(
            lambda: dialogue.supprimer(style.identifiant)
        )
        plus.setMenu(menu)
        disposition.addWidget(plus, 0, Qt.AlignmentFlag.AlignVCenter)


class DialogueBibliothequeStyles(QDialog):
    """`cible` : la réplique à laquelle « Appliquer » donnera le style (None : simple gestion).
    `modele`, `voix`, `langue`, `style_actuel` : pour préremplir un nouveau style."""

    def __init__(
        self,
        services: Services,
        parent=None,
        cible: str | None = None,
        style_actuel: tuple[str, str] = ("", ""),
        modele: str = "gemini-3.8-flash-tts",
        voix: str = "Kore",
        langue: str = LANGUE_PAR_DEFAUT,
    ):
        super().__init__(parent)
        self._services = services
        self._cible = cible
        self._style_actuel = style_actuel
        self._reglages = (modele, voix, langue)
        self.style_choisi: Style | None = None
        self.setWindowTitle("Bibliothèque de styles")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        entete = QHBoxLayout()
        entete.setSpacing(Espacements.S)
        entete.addWidget(libelle("Bibliothèque de styles", "titre-bloc", retour_a_la_ligne=False))
        entete.addStretch(1)
        if style_actuel[0]:
            entete.addWidget(
                bouton("Enregistrer le style actuel", variante="discret", nom_icone="plus", action=self.enregistrer_actuel)
            )
        entete.addWidget(bouton("Nouveau style", nom_icone="plus", action=self.nouveau))
        disposition.addLayout(entete)
        explication = "Tes styles enregistrés, rangés par catégorie."
        if cible:
            explication += f" « Appliquer » met le style sur la {cible} et choisit sa voix et son modèle."
        disposition.addWidget(libelle(explication, "secondaire"))

        zone, contenu = zone_defilante(largeur_max=None)
        self._liste_widget, self._liste = conteneur_vertical(Espacements.XS)
        contenu.addWidget(self._liste_widget)
        disposition.addWidget(zone, 1)

        boutons = QHBoxLayout()
        boutons.addStretch(1)
        boutons.addWidget(bouton("Fermer", action=self.reject))
        disposition.addLayout(boutons)

        self._lignes: list[LigneStyle] = []
        services.styles.abonner(self.rafraichir)
        # Fenêtre détruite sans avoir été fermée normalement : on se désabonne quand même.
        rappel = self.rafraichir
        self.destroyed.connect(lambda: services.styles.desabonner(rappel))
        self.rafraichir()

    def done(self, resultat: int) -> None:
        # Fenêtre fermée : elle ne doit plus être prévenue des changements de la bibliothèque.
        self._services.styles.desabonner(self.rafraichir)
        super().done(resultat)

    def lignes(self) -> list[LigneStyle]:
        return list(self._lignes)

    def rafraichir(self) -> None:
        vider_disposition(self._liste)
        self._lignes = []
        par_categorie = self._services.styles.par_categorie()
        if not par_categorie:
            self._liste.addWidget(libelle("Aucun style pour l'instant : crée le premier avec « Nouveau style ».", "secondaire"))
            return
        for rang, (categorie, styles) in enumerate(par_categorie):
            if rang:
                self._liste.addSpacing(Espacements.M)
            self._liste.addWidget(libelle(categorie, "legende"))
            self._liste.addWidget(separateur())
            for style in styles:
                ligne = LigneStyle(self, style, avec_appliquer=self._cible is not None)
                self._lignes.append(ligne)
                self._liste.addWidget(ligne)

    # --- Actions -----------------------------------------------------------------------------

    def appliquer(self, identifiant: str) -> None:
        self.style_choisi = self._services.styles.style(identifiant)
        self.accept()

    def _modele_de_style(self) -> Style:
        modele, voix, langue = self._reglages
        return Style("", "", "", "", modele=modele, voix=voix if voix_de_base(voix) else "Kore", langue=langue)

    def nouveau(self) -> None:
        DialogueStyle(self._services, self._modele_de_style(), self, "Nouveau style").exec()

    def enregistrer_actuel(self) -> None:
        consigne, consigne_fr = self._style_actuel
        style = replace(self._modele_de_style(), consigne=consigne, consigne_fr=consigne_fr)
        DialogueStyle(self._services, style, self, "Enregistrer le style actuel").exec()

    def modifier(self, identifiant: str) -> None:
        style = self._services.styles.style(identifiant)
        if style is not None:
            DialogueStyle(self._services, style, self, "Modifier le style").exec()

    def dupliquer(self, identifiant: str) -> None:
        if self._services.styles.style(identifiant) is not None:
            self._services.styles.dupliquer(identifiant)

    def supprimer(self, identifiant: str) -> None:
        style = self._services.styles.style(identifiant)
        if style is None:
            return
        reponse = QMessageBox.question(
            self,
            "Supprimer le style",
            f"Supprimer le style « {style.nom} » de la bibliothèque ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reponse == QMessageBox.StandardButton.Yes:
            self._services.styles.supprimer(identifiant)

