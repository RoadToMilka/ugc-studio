"""Section repliable (V2) : un titre cliquable, précédé d'une flèche, qui montre ou cache son contenu.

Pour garder un long formulaire lisible (ex. le brief du module Script : « Produit et offre »,
« Clientèle »…). Fermée, la section peut afficher un court résumé à côté du titre (ex. « 3 champs
remplis », seulement dans le brief depuis la V3.1). Le titre se dessine comme les boutons de l'app
(icône et texte centrés en hauteur, même écart entre les deux), sans cadre : c'est un titre, pas une
action. Une icône « i » (aide) se place entre la flèche et le texte (V3.2, comme sur une case à
cocher ; juste après le texte jusqu'à la 3.1.0) ; juste après le texte, dans le studio des
sous-titres, le ↺ du groupe.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetricsF, QIcon, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ..icones import icone
from ..polices import police
from ..theme import Couleurs, Dimensions, Espacements, Hauteurs, Typo, qcolor
from .bouton import Bouton, dessiner_icone_et_texte
from .elements import BoutonInfo, bouton, libelle


class TitreSection(QAbstractButton):
    """Titre cliquable d'une section : flèche à droite (fermée) ou vers le bas (ouverte), puis le texte.
    Avec une icône « i » (`aide`) : la flèche, 8 px, l'icône, 8 px, le texte (V3.2) ; l'icône est posée
    sur le titre, un clic sur elle montre l'explication sans ouvrir ni fermer la section."""

    def __init__(self, texte: str, parent=None, aide: str | None = None):
        super().__init__(parent)
        self.setText(texte)
        self.aide = BoutonInfo(aide, self) if aide else None
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

    def _debut_du_texte(self) -> int:
        """Où commence le texte : après la flèche (et l'icône « i » s'il y en a une)."""
        if self.aide is None:
            return Dimensions.ICONE_PETITE + Dimensions.ECART_ICONE_TEXTE
        return Dimensions.ICONE_PETITE + 2 * Dimensions.ECART_INFO + Dimensions.ICONE_INFO

    def sizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        largeur = self._debut_du_texte() + QFontMetricsF(self._police).horizontalAdvance(self.text())
        return QSize(math.ceil(largeur), Hauteurs.PETIT_BOUTON)

    def resizeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().resizeEvent(evenement)
        if self.aide is not None:  # entre la flèche et le texte, centrée en hauteur
            self.aide.move(Dimensions.ICONE_PETITE + Dimensions.ECART_INFO, (self.height() - self.aide.height()) // 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        return self.sizeHint()

    def enterEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        self.update()
        super().enterEvent(evenement)

    def leaveEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        self.update()
        super().leaveEvent(evenement)

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # La souris sur l'icône « i » n'éclaire pas le titre : un clic sur elle n'ouvre pas la section.
        sur_l_aide = self.aide is not None and self.aide.underMouse()
        survol = self.isEnabled() and ((self.underMouse() and not sur_l_aide) or self.hasFocus())
        couleur = Couleurs.ACCENT_SURVOL if survol else Couleurs.TEXTE
        image = self._fleches[(self.isChecked(), survol)].pixmap(
            QSize(Dimensions.ICONE_PETITE, Dimensions.ICONE_PETITE),
            self.devicePixelRatioF(),
            QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled,
        )
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        zone = QRectF(self.rect())
        dessiner_icone_et_texte(peintre, zone, image, Dimensions.ICONE_PETITE, "", self._police, qcolor(couleur), centrer=False)
        zone_texte = zone.adjusted(self._debut_du_texte(), 0, 0, 0)
        dessiner_icone_et_texte(peintre, zone_texte, None, 0, self.text(), self._police, qcolor(couleur), centrer=False)
        peintre.end()


class SectionRepliable(QWidget):
    """`contenu` : la disposition verticale où placer les éléments de la section. `aide` : explication
    de la section, dans une icône « i » entre la flèche et le texte du titre (V3.2), dans `self.aide`."""

    basculee = Signal(bool)  # ouverte ?

    def __init__(self, titre: str, ouverte: bool = False, parent=None, aide: str | None = None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.titre = TitreSection(titre, aide=aide)
        self.aide = self.titre.aide  # entre la flèche et le texte du titre (V3.2)
        # Le ↺ du groupe, 4 px après le titre (voir ajouter_retablir).
        self._ligne_titre = QHBoxLayout()
        self._ligne_titre.setSpacing(Espacements.XS)
        self._ligne_titre.addWidget(self.titre)
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
        un clic remet le groupe comme dans le préréglage, sans ouvrir la section. V3.2 : son dessin
        fait 16 px de haut (18 px jusqu'à la 3.1.0)."""
        self.retablir = bouton("", variante="icone", action=action)
        self.retablir.setIconSize(QSize(Dimensions.ICONE_RETABLIR, Dimensions.ICONE_RETABLIR))
        self.retablir.definir_icone("rotate-ccw")
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
