"""Tableau de l'app (V1.1, §9.4 septies) : suivi des coûts, liste des sous-titres.

Règles, les mêmes pour tous les tableaux :
1. Une seule ligne par case : un texte trop long finit par « … », texte complet au survol. Seule
   exception : un texte écrit sur plusieurs lignes exprès (le texte d'un sous-titre sur 2 lignes,
   qui montre sa vraie mise en page).
2. Quand la place manque, les colonnes de texte (projet, modèle, opération…) se resserrent
   d'abord, jusqu'à une largeur minimum. Les dates, nombres et montants gardent toujours leur
   largeur complète.
3. Si ça ne suffit pas, une barre de défilement horizontale apparaît en bas du tableau : aucune
   colonne n'est jamais cachée sans moyen d'aller la voir.

Pourquoi ? Jusqu'à la 1.0.3, à la plus petite largeur de la fenêtre, la colonne « Modèle » du suivi
des coûts passait sur deux lignes qui n'affichaient que « … », et la colonne « Coût », la plus
utile, était cachée sans barre pour aller la voir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QToolTip

from ..theme import Dimensions, Espacements, Hauteurs


@dataclass(frozen=True)
class Colonne:
    """Une colonne. `texte` : colonne de texte, qui se resserre d'abord (texte abrégé par « … ») ;
    sinon, date, nombre ou montant, toujours en entier. `a_droite` : nombres et montants, alignés à
    droite. `etiree` : reçoit la place en trop quand le tableau est large (une seule colonne)."""

    titre: str
    texte: bool = False
    a_droite: bool = False
    etiree: bool = False
    aide: str = ""  # infobulle du titre de la colonne


class Tableau(QTableWidget):
    """Tableau en lecture seule, une ligne choisie à la fois. Après avoir rempli les cases
    (setItem, setCellWidget), appeler contenu_change() : les largeurs sont alors recalculées."""

    def __init__(self, colonnes: Sequence[Colonne], hauteur_ligne: int = Hauteurs.CONTROLE):
        super().__init__(0, len(colonnes))
        self.colonnes = tuple(colonnes)
        self.hauteur_ligne = hauteur_ligne  # hauteur d'une ligne (résumé avant export : plus serrée)
        self._naturelles = [0] * len(self.colonnes)
        self.setHorizontalHeaderLabels([colonne.titre for colonne in self.colonnes])
        for index, colonne in enumerate(self.colonnes):
            titre = self.horizontalHeaderItem(index)
            if colonne.a_droite:
                titre.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if colonne.aide:
                titre.setToolTip(colonne.aide)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(hauteur_ligne)
        self.setShowGrid(False)
        self.setWordWrap(False)  # une seule ligne par case (règle 1)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # règle 3
        entete = self.horizontalHeader()
        entete.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)  # largeurs calculées ici
        entete.setStretchLastSection(False)
        entete.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # --- Largeurs ------------------------------------------------------------------------------

    def contenu_change(self) -> None:
        """À appeler après avoir rempli le tableau : largeur « naturelle » de chaque colonne (celle
        de son titre ou de sa plus longue case), hauteur des lignes, puis répartition de la place.

        Les largeurs sont demandées au style de l'app (feuille de style comprise : marges des cases,
        graisse des montants…), pas recalculées ici : sinon, une date ou un nombre pouvait être
        abrégé de quelques pixels sous Windows."""
        self.ensurePolished()
        for rang in range(self.rowCount()):
            for colonne in range(self.columnCount()):
                element = self.cellWidget(rang, colonne)
                if element is not None:
                    element.ensurePolished()  # sa police (ex. montant en gras) vient de la feuille de style
        entete = self.horizontalHeader()
        for colonne in range(self.columnCount()):
            self._naturelles[colonne] = max(entete.sectionSizeHint(colonne), self.sizeHintForColumn(colonne), 0)
        self._ajuster_hauteurs()
        self.ajuster_colonnes()

    def showEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # Rempli pendant qu'il était caché (onglet pas encore ouvert) : les polices définitives ne
        # sont connues qu'à l'affichage, les largeurs sont donc recalculées.
        super().showEvent(evenement)
        if self.rowCount():
            self.contenu_change()

    def _ajuster_hauteurs(self) -> None:
        """Une ligne de texte par case ; une case écrite exprès sur plusieurs lignes (sous-titre sur
        2 lignes) agrandit sa rangée."""
        interligne = self.fontMetrics().lineSpacing()
        for rang in range(self.rowCount()):
            lignes = max(
                (self.item(rang, colonne).text().count("\n") + 1 for colonne in range(self.columnCount()) if self.item(rang, colonne)),
                default=1,
            )
            if lignes > 1:
                self.setRowHeight(rang, max(self.hauteur_ligne, lignes * interligne + 2 * Espacements.S))
            else:
                self.setRowHeight(rang, self.hauteur_ligne)

    def ajuster_colonnes(self) -> None:
        """Répartit la largeur visible entre les colonnes (règles 2 et 3)."""
        if not any(self._naturelles):
            return
        largeurs = list(self._naturelles)
        textes = [index for index, colonne in enumerate(self.colonnes) if colonne.texte]
        fixes = sum(largeurs[index] for index in range(len(largeurs)) if index not in textes)
        place = self.viewport().width() - fixes  # place pour les colonnes de texte
        naturelle_des_textes = sum(largeurs[index] for index in textes)
        if place >= naturelle_des_textes:
            # Assez de place : chaque colonne en entier, et le surplus à la colonne étirée.
            etiree = next((index for index, colonne in enumerate(self.colonnes) if colonne.etiree), None)
            if etiree is not None:
                largeurs[etiree] += place - naturelle_des_textes
        elif textes:
            minimums = {index: min(largeurs[index], Dimensions.COLONNE_TEXTE_MIN) for index in textes}
            cedable = {index: largeurs[index] - minimums[index] for index in textes}
            a_retirer = min(naturelle_des_textes - place, sum(cedable.values()))
            total = sum(cedable.values()) or 1
            for index in textes:
                # Chaque colonne de texte cède en proportion de ce qu'elle peut céder.
                largeurs[index] -= round(a_retirer * cedable[index] / total)
            if place >= sum(minimums.values()):
                largeurs[textes[-1]] += place - sum(largeurs[index] for index in textes)  # arrondis
            # Sinon, toutes les colonnes de texte sont à leur minimum : la barre horizontale apparaît.
        for index, largeur in enumerate(largeurs):
            self.setColumnWidth(index, largeur)

    def colonnes_coupees(self) -> list[str]:
        """Colonnes de dates, nombres ou montants plus étroites que leur contenu (ne devrait jamais
        arriver : l'autotest le vérifie à la plus petite largeur de la fenêtre)."""
        return [
            colonne.titre
            for index, colonne in enumerate(self.colonnes)
            if not colonne.texte and self.columnWidth(index) < self._naturelles[index]
        ]

    # --- Événements ----------------------------------------------------------------------------

    def resizeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().resizeEvent(evenement)
        self.ajuster_colonnes()

    def viewportEvent(self, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() == QEvent.Type.Resize:
            resultat = super().viewportEvent(evenement)
            self.ajuster_colonnes()  # la barre de défilement verticale est apparue (ou partie)
            return resultat
        if evenement.type() == QEvent.Type.ToolTip:
            self._infobulle(evenement)
            return True
        return super().viewportEvent(evenement)

    def _infobulle(self, evenement) -> None:
        """Au survol d'une case abrégée par « … » : son texte complet (et son infobulle, s'il y en a)."""
        index = self.indexAt(evenement.pos())
        if not index.isValid():
            QToolTip.hideText()
            return
        texte = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        infobulle = str(index.data(Qt.ItemDataRole.ToolTipRole) or "")
        if texte and self.sizeHintForIndex(index).width() > self.columnWidth(index.column()):
            infobulle = f"{texte}\n{infobulle}" if infobulle else texte
        if infobulle:
            QToolTip.showText(evenement.globalPos(), infobulle, self.viewport())
        else:
            QToolTip.hideText()
