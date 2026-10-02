"""Questions et avertissements de l'app (V3.2, lot 3, §9.6) : « Supprimer la prise », « Renommer la
clé », « Erreur inattendue »…

Ce sont des fenêtres de l'app comme les autres (voir composants/fenetre.py) : le fond de l'app, puis
un bloc avec le titre, la question et sa précision (ou le champ à remplir) ; les boutons sous le
bloc, à droite, le bouton de l'action en dernier. Jusqu'à la 3.1.2, c'étaient les petites fenêtres
toutes faites de Qt (QMessageBox, QInputDialog) : fond gris, sans bloc, boutons « Oui » et « Non ».

Pourquoi des boutons qui disent l'action (« Supprimer », « Remplacer ») plutôt que « Oui » ? On sait
ce qu'on fait sans relire la question. La touche Entrée choisit le bouton sans risque (« Annuler »,
« Garder le réglage actuel ») : un appui de trop n'efface rien ; dans une fenêtre avec un champ,
elle valide le texte tapé.

Les modules passent par ce fichier (messages.confirmer(…)) : les tests remplacent ces fonctions par
une réponse toute faite.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QWidget

from ...sous_titres import typographie
from ..composants.bouton import activer_avec_entree
from ..composants.elements import ChampNomme, bouton, libelle
from ..composants.fenetre import fenetre_en_bloc
from ..icones import icone
from ..theme import Couleurs, Dimensions, Espacements

ACTION, AUTRE = "action", "autre"  # le bouton cliqué (DialogueMessage.choix)


class _Pictogramme(QWidget):
    """Petite icône devant le titre d'une fenêtre d'erreur (cercle rouge barré d'une croix)."""

    def __init__(self, nom: str, couleur: str):
        super().__init__()
        self._icone = icone(nom, couleur, taille=Dimensions.ICONE_PETITE)
        self.setFixedSize(Dimensions.ICONE_PETITE, Dimensions.ICONE_PETITE)

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        self._icone.paint(peintre, self.rect(), Qt.AlignmentFlag.AlignCenter)
        peintre.end()


class DialogueMessage(QDialog):
    """Une question, un avertissement ou une demande de texte (voir en haut du fichier).

    `texte` : la question ou le message ; `precision` : ce qu'il faut savoir avant de choisir (en
    gris, dessous). Boutons, de gauche à droite : `autre` (ex. « Ouvrir le journal », seul à gauche),
    `annuler` (None : pas de bouton pour renoncer), puis `action`, le bouton principal, avec
    `icone_action`. `champ` : (nom du champ, texte proposé) pour demander un texte. `erreur` : une
    icône rouge devant le titre. Après exec(), `choix` vaut ACTION ou AUTRE selon le bouton cliqué, et
    None si la fenêtre a été fermée sans choisir (« Annuler », touche Échap, croix de la fenêtre)."""

    def __init__(
        self,
        parent: QWidget | None,
        titre: str,
        texte: str = "",
        precision: str = "",
        *,
        action: str = "OK",
        icone_action: str | None = None,
        annuler: str | None = None,
        autre: str | None = None,
        champ: tuple[str, str] | None = None,
        erreur: bool = False,
    ):
        super().__init__(parent)
        self.choix: str | None = None
        self.setWindowTitle(titre)
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)

        fenetre, self.cadre, disposition = fenetre_en_bloc(self)
        disposition.setSpacing(Espacements.M)
        self.titre = libelle(titre, "titre-bloc")
        if erreur:
            ligne = QHBoxLayout()
            ligne.setContentsMargins(0, 0, 0, 0)
            ligne.setSpacing(Dimensions.ECART_INFO)  # 8 px, comme l'icône « i » devant un titre
            self.pictogramme = _Pictogramme("circle-x", Couleurs.ERREUR)
            ligne.addWidget(self.pictogramme, 0, Qt.AlignmentFlag.AlignVCenter)
            ligne.addWidget(self.titre, 1)
            disposition.addLayout(ligne)
        else:
            self.pictogramme = None
            disposition.addWidget(self.titre)
        # Espaces insécables à la française : un « ? » ou un « » » ne commence jamais une ligne.
        self.texte = libelle(typographie(texte, "fr")) if texte else None
        if self.texte is not None:
            disposition.addWidget(self.texte)
        self.precision = libelle(typographie(precision, "fr"), "secondaire") if precision else None
        if self.precision is not None:
            disposition.addWidget(self.precision)
        self.champ: QLineEdit | None = None
        if champ is not None:
            nom, valeur = champ
            self.champ = QLineEdit(valeur)
            disposition.addWidget(ChampNomme(nom, self.champ, etire=True))

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_autre = bouton(autre, action=lambda: self._choisir(AUTRE)) if autre else None
        if self.bouton_autre is not None:
            boutons.addWidget(self.bouton_autre)
        boutons.addStretch(1)
        self.bouton_annuler = bouton(annuler, action=self.reject) if annuler else None
        if self.bouton_annuler is not None:
            boutons.addWidget(self.bouton_annuler)
        self.bouton_action = bouton(
            action, variante="principal", nom_icone=icone_action, action=lambda: self._choisir(ACTION)
        )
        boutons.addWidget(self.bouton_action)
        fenetre.addLayout(boutons)  # sous le bloc, sur le fond de l'app (V3.2)

        if self.champ is not None:
            activer_avec_entree(self.bouton_action, self)  # Entrée valide le texte tapé
            self.champ.selectAll()  # le texte proposé se remplace en tapant
            self.champ.setFocus()
        elif self.bouton_annuler is not None:
            self.bouton_annuler.setFocus()  # Entrée : le choix sans risque
        else:
            self.bouton_action.setFocus()
        # Hauteur : celle du contenu à cette largeur (les textes qui passent à la ligne comptent).
        self.resize(Dimensions.DIALOGUE_LARGEUR, self.heightForWidth(Dimensions.DIALOGUE_LARGEUR))

    def _choisir(self, choix: str) -> None:
        self.choix = choix
        self.accept()

    def texte_saisi(self) -> str:
        return self.champ.text() if self.champ is not None else ""


def confirmer(
    parent: QWidget | None,
    titre: str,
    question: str,
    precision: str = "",
    action: str = "OK",
    icone_action: str | None = None,
    annuler: str = "Annuler",
) -> bool:
    """Pose une question avant une action : True si on clique sur `action` (ex. « Supprimer »)."""
    dialogue = DialogueMessage(
        parent, titre, question, precision, action=action, icone_action=icone_action, annuler=annuler
    )
    dialogue.exec()
    return dialogue.choix == ACTION


def prevenir(
    parent: QWidget | None,
    titre: str,
    texte: str,
    precision: str = "",
    erreur: bool = False,
    autre: str | None = None,
) -> bool:
    """Un avertissement (ou une erreur, `erreur=True`), avec « OK ». `autre` : un second bouton, à
    gauche (ex. « Ouvrir le journal ») ; renvoie True si c'est lui qui a été cliqué."""
    dialogue = DialogueMessage(parent, titre, texte, precision, autre=autre, erreur=erreur)
    dialogue.exec()
    return dialogue.choix == AUTRE


def demander_texte(
    parent: QWidget | None,
    titre: str,
    nom_du_champ: str,
    texte: str = "",
    action: str = "OK",
    precision: str = "",
) -> str | None:
    """Demande un texte (ex. un nouveau nom) : le texte tapé, ou None si on annule."""
    dialogue = DialogueMessage(
        parent, titre, precision=precision, action=action, annuler="Annuler", champ=(nom_du_champ, texte)
    )
    dialogue.exec()
    return dialogue.texte_saisi() if dialogue.choix == ACTION else None
