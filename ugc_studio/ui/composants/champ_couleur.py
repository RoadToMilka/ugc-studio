"""Champ couleur des sous-titres (V2, lot 4 ; cahier des charges §7.4) : une couleur et son opacité.

Sur une ligne : la pastille de la couleur (un clic ouvre les couleurs proposées, « Autre couleur… »
et la pipette), le code « #RRGGBB », l'opacité (0 à 100 %) et la pipette, qui prend une couleur
dans l'aperçu (par exemple celle de ton produit sur la vidéo).

Ces couleurs sont des choix de la vidéo, pas de l'interface : elles viennent du style
(style_sous_titres.Couleur), pas de theme.py.
"""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import QColorDialog, QHBoxLayout, QLineEdit, QMenu, QWidget

from ...rendu.moteur import qcouleur
from ...style_sous_titres import Couleur
from ..theme import CouleursApercu, Dimensions, Espacements, qcolor
from .elements import bouton, champ_entier

# Couleurs proposées dans le menu de la pastille (celles des styles proposés, annexe B du document V2).
PASTILLES = (
    ("Blanc", Couleur(255, 255, 255)),
    ("Noir", Couleur(0, 0, 0)),
    ("Quasi noir", Couleur(17, 24, 39)),
    ("Jaune", Couleur(255, 212, 59)),
    ("Jaune doré", Couleur(250, 204, 21)),
    ("Orange", Couleur(245, 158, 11)),
    ("Mauve", Couleur(124, 58, 237)),
    ("Rose", Couleur(236, 72, 153)),
    ("Rouge", Couleur(239, 68, 68)),
    ("Vert", Couleur(34, 197, 94)),
    ("Bleu", Couleur(59, 130, 246)),
)


def icone_de_couleur(couleur: Couleur, cote: int = Dimensions.ICONE) -> QIcon:
    """Petit carré de la couleur (sur un damier si elle est transparente)."""
    image = QPixmap(cote, cote)
    image.fill(Qt.GlobalColor.transparent)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    demi = cote / 2
    peintre.fillRect(0, 0, cote, cote, qcolor(CouleursApercu.DAMIER_CLAIR))
    peintre.fillRect(0, 0, round(demi), round(demi), qcolor(CouleursApercu.DAMIER_FONCE))
    peintre.fillRect(round(demi), round(demi), cote - round(demi), cote - round(demi), qcolor(CouleursApercu.DAMIER_FONCE))
    peintre.fillRect(0, 0, cote, cote, qcouleur(couleur))
    peintre.end()
    return QIcon(image)


class ChampCouleur(QWidget):
    change = Signal()  # la couleur ou l'opacité a changé (pas avec definir())
    pipette_demandee = Signal(object)  # ce champ attend une couleur prise dans l'aperçu

    def __init__(self, info: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._couleur = Couleur(255, 255, 255)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)
        self.pastille = bouton("", variante="icone")
        self.pastille.setToolTip("Couleurs proposées, autre couleur, pipette")
        self.menu = QMenu(self.pastille)
        for nom, couleur in PASTILLES:
            action = self.menu.addAction(icone_de_couleur(couleur, Dimensions.ICONE_PETITE), nom)
            action.triggered.connect(lambda _coche=False, c=couleur: self.appliquer(Couleur(c.rouge, c.vert, c.bleu, self._couleur.opacite)))
        self.menu.addSeparator()
        self.menu.addAction("Autre couleur…").triggered.connect(self._autre_couleur)
        self.menu.addAction("Prendre une couleur dans l'aperçu").triggered.connect(lambda: self.pipette_demandee.emit(self))
        self.pastille.setMenu(self.menu)
        disposition.addWidget(self.pastille)
        self.code = QLineEdit()
        self.code.setValidator(QRegularExpressionValidator(QRegularExpression("#?[0-9A-Fa-f]{0,6}")))
        self.code.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
        self.code.setToolTip("Code de la couleur, ex. FFD43B")
        self.code.editingFinished.connect(self._code_saisi)
        disposition.addWidget(self.code)
        self.opacite = champ_entier(0, 100, " %", "Opacité : 100 % opaque, 0 % invisible")
        self.opacite.valueChanged.connect(self._opacite_changee)
        disposition.addWidget(self.opacite)
        self.pipette = bouton("", variante="icone", nom_icone="pipette", action=lambda: self.pipette_demandee.emit(self))
        self.pipette.setToolTip("Prendre une couleur dans l'aperçu")
        disposition.addWidget(self.pipette)
        disposition.addStretch(1)
        if info:
            self.setToolTip(info)
        self.definir(self._couleur)

    def couleur(self) -> Couleur:
        return self._couleur

    def definir(self, couleur: Couleur) -> None:
        """Montre cette couleur, sans prévenir (valeur relue dans le projet)."""
        self._couleur = couleur
        self.pastille.setIcon(icone_de_couleur(couleur))
        self.code.setText(couleur.code)
        self.opacite.blockSignals(True)
        self.opacite.setValue(round(couleur.opacite))
        self.opacite.blockSignals(False)

    def appliquer(self, couleur: Couleur) -> None:
        """Nouvelle couleur choisie (pastille, autre couleur, pipette) : montrée, puis signalée."""
        if couleur == self._couleur:
            return
        self.definir(couleur)
        self.change.emit()

    def _code_saisi(self) -> None:
        lue = Couleur.depuis(self.code.text())
        if lue is None:
            self.code.setText(self._couleur.code)  # code incomplet : la couleur ne change pas
            return
        self.appliquer(Couleur(lue.rouge, lue.vert, lue.bleu, self._couleur.opacite))

    def _opacite_changee(self, valeur: int) -> None:
        couleur = self._couleur
        self.appliquer(Couleur(couleur.rouge, couleur.vert, couleur.bleu, float(valeur)))

    def _autre_couleur(self) -> None:
        choisie = QColorDialog.getColor(qcouleur(self._couleur, opaque=True), self.window(), "Autre couleur")
        if choisie.isValid():
            self.appliquer(Couleur(choisie.red(), choisie.green(), choisie.blue(), self._couleur.opacite))

    def couleur_prise(self, rouge: int, vert: int, bleu: int) -> None:
        """Couleur prise dans l'aperçu avec la pipette (son opacité reste celle du champ)."""
        self.appliquer(Couleur(rouge, vert, bleu, self._couleur.opacite))
