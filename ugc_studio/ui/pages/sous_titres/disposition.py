"""Disposition de la page Sous-titres (V3.1, lot 5 ; cahier des charges §7.9 et §9.4 nonies).

Six blocs : Source et Exporter (la bande du haut), Aperçu, Apparence, Sous-titres, et la Frise. Trois
dispositions, selon la place :

- Grande fenêtre (page d'au moins STUDIO_TROIS_COLONNES_MIN de large, et assez haute) : Source à
  gauche et Exporter à droite ; dessous, trois colonnes, Aperçu | Apparence | Sous-titres, qui
  prennent la hauteur de la fenêtre et défilent chacune seule : l'aperçu reste visible pendant qu'on
  règle l'apparence en bas d'un long onglet, ou qu'on parcourt la liste. La frise en bas, sur toute
  la largeur. Quand la fenêtre n'est pas assez haute pour tout montrer avec des colonnes d'au moins
  STUDIO_COLONNES_HAUTEUR_CONFORT, les colonnes et la frise remplissent la fenêtre, et la bande du
  haut part en haut quand la page défile.
- Fenêtre moyenne : la bande du haut, puis l'aperçu et l'apparence côte à côte, puis la frise et la
  liste des sous-titres ; c'est la page qui défile.
- Petite fenêtre : tout l'un sous l'autre (Source et Exporter aussi, sous 880 px).

Les blocs restent tous enfants de cette disposition : seules leurs places changent (des dispositions
imbriquées). Changer un bloc de widget parent le ferait disparaître le temps de le replacer.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Signal
from PySide6.QtWidgets import QBoxLayout, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ...composants.defilement import ColonneDefilante
from ...theme import Dimensions, Espacements
from .apercu import BlocApercu

PETITE, MOYENNE, GRANDE = "petite", "moyenne", "grande"
# Places dans la disposition principale : la bande du haut, la rangée des colonnes, la frise, la
# liste des sous-titres quand elle est sous la frise, puis la place en trop.
BANDE, RANGEE, FRISE, BAS, RESTE = range(5)


class DispositionStudio(QWidget):
    mode_change = Signal(str)  # PETITE, MOYENNE ou GRANDE : la page adapte l'intérieur de ses blocs

    def __init__(
        self,
        source: QWidget,
        export: QWidget,
        apercu: BlocApercu,
        apparence: QWidget,
        sous_titres: QWidget,
        frise: QWidget,
        colonnes: tuple[ColonneDefilante, ...] = (),
        defilement: QScrollArea | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._source, self._export, self._apercu = source, export, apercu
        self._apparence, self._sous_titres, self._frise = apparence, sous_titres, frise
        self._colonnes = colonnes  # contenus des blocs qui défilent seuls en grande fenêtre
        self._defilement = defilement  # la page, qui défile ; sa hauteur visible compte en grande fenêtre
        espace = Dimensions.ESPACE_BLOCS  # 16 px entre deux blocs, dans les deux sens (V3.1)

        self._principale = QVBoxLayout(self)
        self._principale.setContentsMargins(0, 0, 0, 0)
        self._principale.setSpacing(espace)
        self._bande = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._bande.setSpacing(espace)
        self._bande.addWidget(source, 3)  # Source plus large qu'Exporter (3 pour 2)
        self._bande.addWidget(export, 2)
        self._rangee = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._rangee.setSpacing(espace)
        self._bas = QVBoxLayout()
        self._bas.setSpacing(espace)
        self._principale.addLayout(self._bande)
        self._principale.addLayout(self._rangee)
        self._principale.addWidget(frise)
        self._principale.addLayout(self._bas)
        self._principale.addStretch(1)

        self._mode: str | None = None
        self._en_cours = False  # pas d'adaptation dans une adaptation
        if defilement is not None:
            defilement.viewport().installEventFilter(self)  # la fenêtre change de hauteur
        self._adapter()

    # --- État ----------------------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode or PETITE

    @property
    def cote_a_cote(self) -> bool:
        """L'aperçu et l'apparence côte à côte (fenêtre moyenne ou grande)."""
        return self.mode in (MOYENNE, GRANDE)

    # --- Largeurs et hauteurs ----------------------------------------------------------------------

    def largeur_deux_colonnes(self) -> int:
        """Largeur qu'il faut pour l'aperçu et l'apparence côte à côte : la colonne de l'aperçu,
        l'espace entre les deux, et le minimum de l'apparence (il dépend de l'onglet affiché et des
        groupes ouverts). Sans cette vérification, une apparence plus large que sa colonne garderait
        deux colonnes trop larges pour la page : son bord droit serait coupé."""
        besoin = self._apercu.largeur_naturelle() + self._rangee.spacing() + self._apparence.minimumSizeHint().width()
        return max(Dimensions.STUDIO_DEUX_COLONNES_MIN, besoin)

    def largeur_trois_colonnes(self) -> int:
        """Largeur qu'il faut pour les trois colonnes : celle de l'aperçu (selon la hauteur des
        colonnes), les deux espaces, et au moins STUDIO_COLONNE_LARGEUR_MIN pour l'apparence et pour
        les sous-titres."""
        hauteur = self.hauteur_des_colonnes(self.width()) or Dimensions.STUDIO_COLONNES_HAUTEUR_MIN
        autres = sum(
            max(Dimensions.STUDIO_COLONNE_LARGEUR_MIN, bloc.minimumSizeHint().width()) for bloc in (self._apparence, self._sous_titres)
        )
        besoin = self._apercu.largeur_pour_hauteur(hauteur) + 2 * self._rangee.spacing() + autres
        return max(Dimensions.STUDIO_TROIS_COLONNES_MIN, besoin)

    def _hauteur_visible(self) -> int:
        """Hauteur de la page qui se voit d'un coup, pour cette disposition : la partie visible de la
        page, moins ce qui est au-dessus de la disposition (la marge, et l'en-tête quand la fenêtre ne
        l'a pas pris) et la marge du bas."""
        if self._defilement is None or self._defilement.widget() is None:
            return 0
        contenu = self._defilement.widget()
        if not contenu.isAncestorOf(self):
            return 0
        haut = self.mapTo(contenu, QPoint(0, 0)).y()
        bas = contenu.layout().contentsMargins().bottom() if contenu.layout() is not None else 0
        return self._defilement.viewport().height() - haut - bas

    @staticmethod
    def _hauteur(element, largeur: int) -> int:
        """Hauteur d'un bloc ou d'une disposition pour cette largeur (0 s'il est caché)."""
        if isinstance(element, QWidget) and element.isHidden():
            return 0
        hauteur = element.heightForWidth(largeur) if element.hasHeightForWidth() else -1
        return hauteur if hauteur >= 0 else element.sizeHint().height()

    def hauteur_des_colonnes(self, largeur: int) -> int | None:
        """Hauteur des trois colonnes en grande fenêtre, ou None si la fenêtre est trop basse (moins de
        STUDIO_COLONNES_HAUTEUR_MIN pour les colonnes, même en laissant partir la bande du haut).

        Tout se voit d'un coup quand il reste au moins STUDIO_COLONNES_HAUTEUR_CONFORT pour les
        colonnes ; sinon, les colonnes et la frise remplissent la fenêtre, et la bande du haut part en
        haut quand la page défile (l'aperçu garde une taille confortable)."""
        visible = self._hauteur_visible()
        espace = self._principale.spacing()
        frise = self._hauteur(self._frise, largeur)
        frise = frise + espace if frise else 0
        bande = self._hauteur(self._bande, largeur) + espace
        reste = visible - bande - frise
        if reste >= Dimensions.STUDIO_COLONNES_HAUTEUR_CONFORT:
            return reste
        collee = visible - frise
        return collee if collee >= Dimensions.STUDIO_COLONNES_HAUTEUR_MIN else None

    # --- Adaptation ----------------------------------------------------------------------------------

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — nom imposé par Qt
        """Largeur minimale : celle de la petite fenêtre (tout l'un sous l'autre). Sans cela, en deux
        ou trois colonnes, la disposition ne pourrait pas devenir plus étroite que ses colonnes : il
        n'y aurait jamais assez peu de place pour passer à une disposition plus étroite, et le bord
        droit de la page serait coupé."""
        blocs = (self._source, self._export, self._apparence, self._sous_titres, self._frise)
        largeur = max(self._apercu.largeur_min(), *(bloc.minimumSizeHint().width() for bloc in blocs))
        return QSize(largeur, super().minimumSizeHint().height())

    def resizeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().resizeEvent(evenement)
        self._adapter()

    def event(self, evenement) -> bool:
        if evenement.type() == QEvent.Type.LayoutRequest:
            self._adapter()  # un bloc demande une autre place (onglet, groupe ouvert, texte…)
        return super().event(evenement)

    def eventFilter(self, objet, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() == QEvent.Type.Resize:
            self._adapter()  # la page visible change de hauteur (fenêtre agrandie, réduite…)
        return False

    def _adapter(self) -> None:
        if self._en_cours:
            return
        self._en_cours = True
        try:
            largeur = self.width()
            # Source et Exporter côte à côte dès 880 px (avant le reste : leur hauteur compte).
            cote_a_cote = largeur >= Dimensions.STUDIO_DEUX_COLONNES_MIN
            direction = QBoxLayout.Direction.LeftToRight if cote_a_cote else QBoxLayout.Direction.TopToBottom
            if self._bande.direction() != direction:
                self._bande.setDirection(direction)
            mode = self._mode_voulu(largeur)
            if mode != self._mode:
                self._placer(mode)
                self._mode = mode
                self.mode_change.emit(mode)
            self._dimensionner(largeur)
        finally:
            self._en_cours = False

    def _mode_voulu(self, largeur: int) -> str:
        # Pour passer à une disposition plus large, il faut un peu plus de place : sans cette marge, une
        # barre de défilement qui apparaît ou disparaît pourrait faire changer la disposition en boucle
        # autour de la limite.
        marge = 0 if self._mode is None else Dimensions.BARRE_DEFILEMENT + Espacements.S
        trois = self.largeur_trois_colonnes() + (0 if self._mode == GRANDE else marge)
        if largeur >= trois and self.hauteur_des_colonnes(largeur) is not None:
            return GRANDE
        deux = self.largeur_deux_colonnes() + (0 if self._mode in (MOYENNE, GRANDE) else marge)
        return MOYENNE if largeur >= deux else PETITE

    def _placer(self, mode: str) -> None:
        """Chaque bloc à sa place pour cette disposition."""
        rangee, bas = self._rangee, self._bas
        for bloc in (self._apercu, self._apparence, self._sous_titres):
            rangee.removeWidget(bloc)
            bas.removeWidget(bloc)
        rangee.setDirection(QBoxLayout.Direction.TopToBottom if mode == PETITE else QBoxLayout.Direction.LeftToRight)
        rangee.addWidget(self._apercu, 0)
        rangee.addWidget(self._apparence, 0 if mode == PETITE else 1)
        if mode == GRANDE:
            rangee.addWidget(self._sous_titres, 1)
        else:
            bas.addWidget(self._sous_titres)
        # Grande fenêtre : la rangée prend la hauteur qui reste ; sinon, la place en trop va en bas.
        self._principale.setStretch(RANGEE, 1 if mode == GRANDE else 0)
        self._principale.setStretch(RESTE, 0 if mode == GRANDE else 1)
        # L'aperçu garde la largeur de sa vidéo à côté de l'apparence ; l'un sous l'autre, toute la largeur.
        horizontale = QSizePolicy.Policy.Preferred if mode == PETITE else QSizePolicy.Policy.Fixed
        self._apercu.setSizePolicy(horizontale, QSizePolicy.Policy.Preferred)
        for colonne in self._colonnes:
            colonne.definir_defilement(mode == GRANDE)

    def _dimensionner(self, largeur: int) -> None:
        """Grande fenêtre : la hauteur des colonnes, et la largeur de l'aperçu qui va avec ; sinon,
        l'aperçu à 540 px de haut au plus."""
        if self._mode == GRANDE:
            hauteur = self.hauteur_des_colonnes(largeur) or Dimensions.STUDIO_COLONNES_HAUTEUR_MIN
            self._apercu.definir_hauteur_imposee(hauteur)
            self._apercu.definir_largeur_voulue(self._apercu.largeur_pour_hauteur(hauteur))
            espace = self._principale.spacing()
            frise = self._hauteur(self._frise, largeur)
            total = self._hauteur(self._bande, largeur) + espace + hauteur + (frise + espace if frise else 0)
        else:
            self._apercu.definir_hauteur_imposee(None)
            self._apercu.definir_largeur_voulue(None)
            total = 0
        if self.minimumHeight() != total:
            self.setMinimumHeight(total)
