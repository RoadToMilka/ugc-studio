"""Section repliable (V2) : un titre cliquable, précédé d'une flèche, qui montre ou cache son contenu.

Pour garder un long formulaire lisible (ex. le brief du module Script : « Produit et offre »,
« Clientèle »…). Fermée, la section peut afficher un court résumé à côté du titre (ex. « 3 champs
remplis », seulement dans le brief depuis la V3.1). Le titre se dessine comme les boutons de l'app
(icône et texte centrés en hauteur, même écart entre les deux), sans cadre : c'est un titre, pas une
action. Juste après lui, une icône « i » (aide) et, dans le studio des sous-titres, le ↺ du groupe.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetricsF, QIcon, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ..icones import icone
from ..polices import police
from ..theme import Couleurs, Dimensions, Espacements, Hauteurs, Typo, qcolor
from .bouton import Bouton, dessiner_icone_et_texte, largeur_icone_et_texte
from .elements import BoutonInfo, bouton, libelle, ligne_avec_aide


class TitreSection(QAbstractButton):
    """Titre cliquable d'une section : flèche à droite (fermée) ou vers le bas (ouverte), puis le texte."""

    def __init__(self, texte: str, parent=None):
        super().__init__(parent)
        self.setText(texte)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._police = police(Typo.COURANT, Typo.GRAISSE_MOYENNE)
        # Flèches préparées une fois : (ouverte, survol) → icône.
        self._fleches = {
            (ouverte, survol): icone(
                "chevron-down" if ouverte else "chevron-right",
                Couleurs.ACCENT_SURVOL if survol else Couleurs.TEXTE,
                taille=Dimensions.ICONE_PETITE,
            )
            for ouverte in (False, True)
            for survol in (False, True)
        }
        self.toggled.connect(lambda _ouverte: self.update())

    def sizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        largeur = largeur_icone_et_texte(QFontMetricsF(self._police), self.text(), Dimensions.ICONE_PETITE)
        return QSize(math.ceil(largeur), Hauteurs.PETIT_BOUTON)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        return self.sizeHint()

    def enterEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        self.update()
        super().enterEvent(evenement)

    def leaveEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        self.update()
        super().leaveEvent(evenement)

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        survol = self.isEnabled() and (self.underMouse() or self.hasFocus())
        couleur = Couleurs.ACCENT_SURVOL if survol else Couleurs.TEXTE
        image = self._fleches[(self.isChecked(), survol)].pixmap(
            QSize(Dimensions.ICONE_PETITE, Dimensions.ICONE_PETITE),
            self.devicePixelRatioF(),
            QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled,
        )
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        dessiner_icone_et_texte(
            peintre, QRectF(self.rect()), image, Dimensions.ICONE_PETITE, self.text(), self._police, qcolor(couleur), centrer=False
        )
        peintre.end()


class SectionRepliable(QWidget):
    """`contenu` : la disposition verticale où placer les éléments de la section. `aide` : explication
    de la section, dans une icône « i » juste après le titre (V3.1), dans `self.aide`."""

    basculee = Signal(bool)  # ouverte ?

    def __init__(self, titre: str, ouverte: bool = False, parent=None, aide: str | None = None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.titre = TitreSection(titre)
        self.aide = BoutonInfo(aide) if aide else None
        self._ligne_titre = ligne_avec_aide(self.titre, self.aide, fin=False)
        ligne.addLayout(self._ligne_titre)
        self.retablir: Bouton | None = None  # ↺ du groupe (V3.1), voir ajouter_retablir()
        self.resume = libelle("", "legende", retour_a_la_ligne=False)
        ligne.addWidget(self.resume)
        ligne.addStretch(1)
        disposition.addLayout(ligne)
        self.zone = QWidget()
        self.contenu = QVBoxLayout(self.zone)
        # Le contenu est décalé sous le texte du titre (après la flèche) : on voit à quoi il appartient.
        self.contenu.setContentsMargins(Dimensions.ICONE_PETITE + Dimensions.ECART_ICONE_TEXTE, 0, 0, Espacements.S)
        self.contenu.setSpacing(Espacements.M)
        disposition.addWidget(self.zone)
        self.titre.toggled.connect(self._basculer)
        self.titre.setChecked(ouverte)
        self._basculer(ouverte)

    def ajouter_retablir(self, action, infobulle: str) -> Bouton:
        """Le ↺ du groupe (V3.1, studio des sous-titres) : une icône seule, juste après le titre
        (« Police ↺ »), visible seulement quand le groupe s'écarte du préréglage (montrer_retablir) ;
        un clic remet le groupe comme dans le préréglage, sans ouvrir la section."""
        self.retablir = bouton("", variante="icone", nom_icone="rotate-ccw", action=action)
        self.retablir.setToolTip(infobulle)
        self.retablir.hide()
        self._ligne_titre.addWidget(self.retablir, 0, Qt.AlignmentFlag.AlignVCenter)
        return self.retablir

    def montrer_retablir(self, visible: bool) -> None:
        if self.retablir is not None:
            self.retablir.setVisible(visible)

    def est_ouverte(self) -> bool:
        return self.titre.isChecked()

    def ouvrir(self, ouverte: bool = True) -> None:
        self.titre.setChecked(ouverte)

    def definir_resume(self, texte: str) -> None:
        """Court résumé affiché à côté du titre quand la section est fermée."""
        self.resume.setText(texte)
        self.resume.setVisible(bool(texte) and not self.est_ouverte())

    def _basculer(self, ouverte: bool) -> None:
        self.zone.setVisible(ouverte)
        self.resume.setVisible(bool(self.resume.text()) and not ouverte)
        self.basculee.emit(ouverte)
