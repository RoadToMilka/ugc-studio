"""Frise des sous-titres (V2, lot 7 ; cahier des charges §7.13) : sous l'aperçu, toute la pub d'un
coup d'œil.

- En haut, les graduations du temps ; puis un bloc par sous-titre (de son début à sa fin,
  numéroté) ; en dessous, un petit trait par mot (son texte au survol).
- Le trait mauve : le moment lu. Un clic place la lecture à ce moment ; un clic sur un bloc le
  choisit (contour mauve, comme dans la liste) ; un double-clic sur un bloc : « Corriger les mots »,
  sur son premier mot.
- Bloc signalé (un mot rapetissé pour tenir dans l'écran) : en orange. Ajusté à la main : un point.
- Le **bord commun** de deux sous-titres voisins se glisse : il saute de mot en mot, et les mots
  qui vont changer de sous-titre se colorent (en mauve ; en rouge si une règle du découpage serait
  enfreinte, avec la raison au survol). Au relâchement, ils passent d'un sous-titre à l'autre, avec
  les règles de « Monter le premier mot » et « Descendre le dernier mot ». Les autres bords ne
  bougent pas : ils suivent le moment des mots, qui ne change jamais.
- Molette : défilement (frise agrandie) ; Ctrl + molette : zoom. Au départ, toute la pub tient dans
  la largeur.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QScrollBar, QSizePolicy, QVBoxLayout, QWidget

from ...sous_titres import ESPACE_INSECABLE, MotAffiche, SousTitre
from ..polices import police
from ..theme import Arrondis, Couleurs, Dimensions, Espacements, Opacites, Typo, qcolor
from .bulle import cacher_bulle, montrer_bulle
from .elements import minutes_secondes

PAS_DES_GRADUATIONS_S = (1, 2, 5, 10, 15, 30, 60, 120, 300)
MEME_INSTANT_S = 1e-3  # deux sous-titres qui se touchent : la fin de l'un est le début de l'autre
MILLISECONDES = 1000  # la barre de défilement compte en millisecondes


def _texte(mots: list[MotAffiche]) -> str:
    return " ".join(mot.texte for mot in mots).replace(ESPACE_INSECABLE, " ")


class ToileFrise(QWidget):
    """La frise dessinée (voir en haut du fichier)."""

    temps_demande = Signal(float)  # clic hors d'un bloc : la lecture va à ce moment
    sous_titre_clique = Signal(int, float)  # clic sur un bloc : (son indice, moment du clic)
    correction_demandee = Signal(int)  # double-clic sur un bloc : corriger ses mots
    limite_deplacee = Signal(int, int)  # bord glissé : (sous-titre de gauche, mot qui commence le suivant)
    vue_change = Signal()  # zoom ou défilement

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._sous_titres: list[SousTitre] = []
        self._mots: list[MotAffiche] = []
        self._duree = 0.0
        self._temps: float | None = None
        self._choisi = -1
        self._zoom = 1.0
        self._debut = 0.0  # premier instant visible
        self._verifier: Callable[[int, int], str] | None = None
        self._glisse: tuple[int, int] | None = None  # (sous-titre de gauche, mot visé)
        self._refus = ""
        self._bulle = ""
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # Échap annule un glissement
        self.setFixedHeight(self.hauteur())
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(Dimensions.APERCU_LARGEUR_MIN)

    @staticmethod
    def hauteur() -> int:
        return (
            Dimensions.FRISE_REGLE_HAUTEUR
            + Dimensions.FRISE_BLOC_HAUTEUR
            + Espacements.XS
            + Dimensions.FRISE_MOTS_HAUTEUR
            + Espacements.XS
        )

    # --- Contenu ----------------------------------------------------------------------------

    def definir(self, sous_titres: list[SousTitre], mots: list[MotAffiche], duree: float) -> None:
        """Nouveaux sous-titres (calcul refait) ; `duree` : celle de la pub (vidéo ou prise)."""
        self._sous_titres, self._mots = sous_titres, mots
        fins = [s.fin for s in sous_titres] + [m.fin for m in mots]
        self._duree = max([duree, *fins]) if fins or duree > 0 else 0.0
        self._glisse = None
        self._choisi = self._choisi if 0 <= self._choisi < len(sous_titres) else -1
        self._borner()
        self.vue_change.emit()
        self.update()

    def definir_temps(self, temps: float | None) -> None:
        """Le moment lu (trait mauve). Frise agrandie : elle suit la lecture."""
        self._temps = temps
        if temps is not None and self._zoom > 1 and not self._debut <= temps <= self._debut + self.duree_visible():
            self._debut = temps - self.duree_visible() / 10
            self._borner()
            self.vue_change.emit()
        self.update()

    def definir_choisi(self, index: int) -> None:
        self._choisi = index if 0 <= index < len(self._sous_titres) else -1
        self.update()

    def definir_verification(self, verifier: Callable[[int, int], str] | None) -> None:
        """Pendant le glissement d'un bord : (sous-titre de gauche, mot visé) → raison d'un refus
        (texte vide : possible)."""
        self._verifier = verifier

    # --- Vue : zoom et défilement -----------------------------------------------------------

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def debut(self) -> float:
        return self._debut

    @property
    def duree(self) -> float:
        return self._duree

    def duree_visible(self) -> float:
        return self._duree / self._zoom if self._duree > 0 else 0.0

    def zoomer(self, facteur: float, x: float | None = None) -> None:
        """Agrandit (facteur > 1) ou réduit la frise, autour du point `x` (sinon du milieu)."""
        if self._duree <= 0:
            return
        x = self.width() / 2 if x is None else x
        ancre = self.temps_du_x(x)
        self._zoom = min(max(self._zoom * facteur, 1.0), Dimensions.FRISE_ZOOM_MAX)
        self._debut = ancre - (x - Dimensions.FRISE_MARGE) / self._px_par_s()
        self._borner()
        self.vue_change.emit()
        self.update()

    def definir_debut(self, debut: float) -> None:
        self._debut = debut
        self._borner()
        self.update()

    def _borner(self) -> None:
        self._debut = min(max(self._debut, 0.0), max(self._duree - self.duree_visible(), 0.0))

    # --- Géométrie --------------------------------------------------------------------------

    def _px_par_s(self) -> float:
        largeur = max(1.0, self.width() - 2 * Dimensions.FRISE_MARGE)
        return largeur / max(self.duree_visible(), MEME_INSTANT_S)

    def x_du_temps(self, temps: float) -> float:
        return Dimensions.FRISE_MARGE + (temps - self._debut) * self._px_par_s()

    def temps_du_x(self, x: float) -> float:
        return self._debut + (x - Dimensions.FRISE_MARGE) / self._px_par_s()

    @staticmethod
    def _haut_des_blocs() -> float:
        return Dimensions.FRISE_REGLE_HAUTEUR

    @staticmethod
    def _haut_des_mots() -> float:
        return Dimensions.FRISE_REGLE_HAUTEUR + Dimensions.FRISE_BLOC_HAUTEUR + Espacements.XS

    def rect_du_bloc(self, index: int) -> QRectF:
        sous_titre = self._sous_titres[index]
        gauche, droite = self.x_du_temps(sous_titre.debut), self.x_du_temps(sous_titre.fin)
        return QRectF(gauche, self._haut_des_blocs(), max(droite - gauche, Dimensions.BORDURE), Dimensions.FRISE_BLOC_HAUTEUR)

    def bords_communs(self) -> list[int]:
        """Sous-titres dont la fin touche le début du suivant (leur bord se glisse)."""
        return [
            index
            for index in range(len(self._sous_titres) - 1)
            if abs(self._sous_titres[index].fin - self._sous_titres[index + 1].debut) < MEME_INSTANT_S
        ]

    def x_du_bord(self, index: int) -> float:
        return self.x_du_temps(self._sous_titres[index].fin)

    def _bord_sous(self, point: QPointF) -> int | None:
        if not self._haut_des_blocs() <= point.y() <= self._haut_des_mots() + Dimensions.FRISE_MOTS_HAUTEUR:
            return None
        proches = [(abs(point.x() - self.x_du_bord(i)), i) for i in self.bords_communs()]
        proches = [(ecart, i) for ecart, i in proches if ecart <= Dimensions.FRISE_POIGNEE]
        return min(proches)[1] if proches else None

    def _bloc_sous(self, point: QPointF) -> int:
        if not self._haut_des_blocs() <= point.y() <= self._haut_des_blocs() + Dimensions.FRISE_BLOC_HAUTEUR:
            return -1
        temps = self.temps_du_x(point.x())
        return next((i for i, s in enumerate(self._sous_titres) if s.debut <= temps <= s.fin), -1)

    def _mot_sous(self, point: QPointF) -> int:
        if not self._haut_des_mots() <= point.y() <= self._haut_des_mots() + Dimensions.FRISE_MOTS_HAUTEUR:
            return -1
        temps = self.temps_du_x(point.x())
        tolerance = Dimensions.FRISE_POIGNEE / self._px_par_s()
        return next((i for i, m in enumerate(self._mots) if m.debut - tolerance <= temps <= m.fin + tolerance), -1)

    def x_de_la_limite(self, mot: int) -> float:
        """Limite entre `mot - 1` et `mot` : au milieu du silence qui les sépare (ou de leur contact)."""
        avant, apres = self._mots[mot - 1], self._mots[mot]
        return self.x_du_temps((min(avant.fin, apres.debut) + apres.debut) / 2)

    def _mot_vise(self, index: int, x: float) -> int:
        """Pendant le glissement du bord `index` : le mot qui commencera le sous-titre suivant (le plus
        proche du pointeur ; chaque sous-titre garde au moins un mot)."""
        gauche, droite = self._sous_titres[index], self._sous_titres[index + 1]
        candidats = range(gauche.premier_mot + 1, droite.dernier_mot)
        return min(candidats, key=lambda mot: abs(self.x_de_la_limite(mot) - x))

    # --- Glissement d'un bord ---------------------------------------------------------------

    @property
    def glissement(self) -> tuple[int, int] | None:
        """(sous-titre de gauche, mot visé) pendant qu'un bord est glissé ; sinon None."""
        return self._glisse

    def commencer_glissement(self, index: int) -> None:
        self._glisse = (index, self._sous_titres[index + 1].premier_mot)
        self._refus = ""
        self.update()

    def viser(self, mot: int) -> None:
        """Le bord glissé vise ce mot (il commencera le sous-titre suivant)."""
        if self._glisse is None:
            return
        index = self._glisse[0]
        self._glisse = (index, mot)
        depart = self._sous_titres[index + 1].premier_mot
        self._refus = self._verifier(index, mot) if self._verifier is not None and mot != depart else ""
        self.update()

    def finir_glissement(self) -> None:
        if self._glisse is None:
            return
        index, mot = self._glisse
        self._glisse, self._refus = None, ""
        self.update()
        if mot != self._sous_titres[index + 1].premier_mot:
            self.limite_deplacee.emit(index, mot)

    def annuler_glissement(self) -> None:
        self._glisse, self._refus = None, ""
        self.update()

    def description_du_glissement(self) -> str:
        """Ce que fera le relâchement : « « Glowzy » passe au sous-titre 3. », ou la raison du refus."""
        if self._glisse is None:
            return ""
        index, mot = self._glisse
        depart = self._sous_titres[index + 1].premier_mot
        if mot == depart:
            return "Glisse vers la gauche ou la droite : le bord saute de mot en mot."
        if self._refus:
            return self._refus
        if mot < depart:
            deplaces, numero = self._mots[mot:depart], index + 2
        else:
            deplaces, numero = self._mots[depart:mot], index + 1
        verbe = "passe" if len(deplaces) == 1 else "passent"
        return f"« {_texte(deplaces)} » {verbe} au sous-titre {numero}."

    # --- Souris et clavier ------------------------------------------------------------------

    def mousePressEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        if evenement.button() != Qt.MouseButton.LeftButton or self._duree <= 0:
            super().mousePressEvent(evenement)
            return
        point = evenement.position()
        bord = self._bord_sous(point)
        if bord is not None:
            self.commencer_glissement(bord)
            return
        temps = min(max(self.temps_du_x(point.x()), 0.0), self._duree)
        index = self._bloc_sous(point)
        if index >= 0:
            self.sous_titre_clique.emit(index, temps)
        else:
            self.temps_demande.emit(temps)

    def mouseMoveEvent(self, evenement) -> None:  # noqa: N802
        point = evenement.position()
        if self._glisse is not None:
            mot = self._mot_vise(self._glisse[0], point.x())
            if mot != self._glisse[1]:
                self.viser(mot)
            self._bulle_a(evenement, self.description_du_glissement())
            return
        if self._bord_sous(point) is not None:
            self.setCursor(Qt.CursorShape.SplitHCursor)
            self._bulle_a(evenement, "Glisse ce bord : des mots passent d'un sous-titre à l'autre.")
            return
        self.unsetCursor()
        index, mot = self._bloc_sous(point), self._mot_sous(point)
        if index >= 0:
            sous_titre = self._sous_titres[index]
            texte = _texte(self._mots[sous_titre.premier_mot : sous_titre.dernier_mot])
            self._bulle_a(evenement, f"Sous-titre {index + 1} : {texte}")
        elif mot >= 0:
            self._bulle_a(evenement, self._mots[mot].texte.replace(ESPACE_INSECABLE, " "))
        else:
            self._bulle_a(evenement, "")

    def mouseReleaseEvent(self, evenement) -> None:  # noqa: N802
        if evenement.button() == Qt.MouseButton.LeftButton and self._glisse is not None:
            self.finir_glissement()
            self._bulle_a(evenement, "")
            return
        super().mouseReleaseEvent(evenement)

    def mouseDoubleClickEvent(self, evenement) -> None:  # noqa: N802
        index = self._bloc_sous(evenement.position())
        if evenement.button() == Qt.MouseButton.LeftButton and index >= 0:
            self.correction_demandee.emit(index)
            return
        super().mouseDoubleClickEvent(evenement)

    def keyPressEvent(self, evenement) -> None:  # noqa: N802
        if evenement.key() == Qt.Key.Key_Escape and self._glisse is not None:
            self.annuler_glissement()
            return
        super().keyPressEvent(evenement)

    def leaveEvent(self, evenement) -> None:  # noqa: N802
        self._bulle = ""
        cacher_bulle(self)
        super().leaveEvent(evenement)

    def wheelEvent(self, evenement) -> None:  # noqa: N802
        """Ctrl + molette : zoom ; molette : défilement de la frise agrandie. Sinon, la page défile."""
        delta = evenement.angleDelta()
        crans = (delta.y() or delta.x()) / 120
        if evenement.modifiers() & Qt.KeyboardModifier.ControlModifier and crans:
            self.zoomer(Dimensions.FRISE_PAS_DE_ZOOM**crans, evenement.position().x())
            evenement.accept()
            return
        if self._zoom > 1 and crans:
            self.definir_debut(self._debut - crans * self.duree_visible() / 10)
            self.vue_change.emit()
            evenement.accept()
            return
        evenement.ignore()

    def _bulle_a(self, evenement, texte: str) -> None:
        if texte == self._bulle:
            return
        self._bulle = texte
        if texte:
            montrer_bulle(texte, evenement.globalPosition().toPoint(), self)
        else:
            cacher_bulle(self)

    # --- Dessin -----------------------------------------------------------------------------

    def paintEvent(self, _evenement) -> None:  # noqa: N802
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.fillRect(self.rect(), qcolor(Couleurs.FOND))
        peintre.setFont(police(Typo.LEGENDE))
        if not self._sous_titres or self._duree <= 0:
            peintre.setPen(qcolor(Couleurs.TEXTE_DESACTIVE))
            peintre.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "Pas encore de sous-titres")
            peintre.end()
            return
        self._dessiner_regle(peintre)
        self._dessiner_blocs(peintre)
        self._dessiner_mots(peintre)
        self._dessiner_glissement(peintre)
        if self._temps is not None:
            x = self.x_du_temps(self._temps)
            peintre.setPen(QPen(qcolor(Couleurs.ACCENT), Dimensions.FRISE_CURSEUR))
            peintre.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        peintre.end()

    def _dessiner_regle(self, peintre: QPainter) -> None:
        pas = next((p for p in PAS_DES_GRADUATIONS_S if p * self._px_par_s() >= Dimensions.FRISE_GRADUATION_MIN), PAS_DES_GRADUATIONS_S[-1])
        peintre.setPen(qcolor(Couleurs.TEXTE_DESACTIVE))
        metriques = QFontMetricsF(peintre.font())
        temps = math.ceil(self._debut / pas) * pas
        fin = self._debut + self.duree_visible()
        while temps <= fin + MEME_INSTANT_S:
            x = self.x_du_temps(temps)
            peintre.drawLine(QPointF(x, Dimensions.FRISE_REGLE_HAUTEUR - Espacements.XS), QPointF(x, Dimensions.FRISE_REGLE_HAUTEUR))
            texte = minutes_secondes(temps)
            largeur = metriques.horizontalAdvance(texte)
            gauche = min(max(x - largeur / 2, 0.0), self.width() - largeur)
            peintre.drawText(QPointF(gauche, metriques.ascent()), texte)
            temps += pas

    def _dessiner_blocs(self, peintre: QPainter) -> None:
        metriques = QFontMetricsF(police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE))
        for index, sous_titre in enumerate(self._sous_titres):
            rect = self.rect_du_bloc(index)
            if rect.right() < 0 or rect.left() > self.width():
                continue
            choisi = index == self._choisi
            contour = Couleurs.ACCENT if choisi else (Couleurs.AVERTISSEMENT if sous_titre.signale else Couleurs.BORDURE)
            peintre.setPen(QPen(qcolor(contour), Dimensions.FRISE_CURSEUR if choisi or sous_titre.signale else Dimensions.BORDURE))
            peintre.setBrush(qcolor(Couleurs.ACCENT, Opacites.TEINTE_SELECTION) if choisi else qcolor(Couleurs.SURFACE_ELEVEE))
            peintre.drawRoundedRect(rect, Arrondis.PETIT, Arrondis.PETIT)
            numero = str(index + 1)
            if rect.width() >= metriques.horizontalAdvance(numero) + 2 * Espacements.XS:
                peintre.setFont(police(Typo.LEGENDE, Typo.GRAISSE_MOYENNE))
                peintre.setPen(qcolor(Couleurs.AVERTISSEMENT if sous_titre.signale else Couleurs.TEXTE_SECONDAIRE))
                peintre.drawText(rect, Qt.AlignmentFlag.AlignCenter, numero)
            if sous_titre.ajuste and rect.width() >= 2 * (Dimensions.FRISE_MARQUE_AJUSTE + Espacements.XS):
                rayon = Dimensions.FRISE_MARQUE_AJUSTE
                centre = QPointF(rect.right() - Espacements.XS - rayon, rect.top() + Espacements.XS + rayon)
                peintre.setPen(Qt.PenStyle.NoPen)
                peintre.setBrush(qcolor(Couleurs.ACCENT_SURVOL))
                peintre.drawEllipse(centre, rayon, rayon)
        peintre.setBrush(Qt.BrushStyle.NoBrush)

    def _mots_qui_changent(self) -> range:
        if self._glisse is None:
            return range(0)
        index, mot = self._glisse
        depart = self._sous_titres[index + 1].premier_mot
        return range(mot, depart) if mot < depart else range(depart, mot)

    def _dessiner_mots(self, peintre: QPainter) -> None:
        haut = self._haut_des_mots()
        choisi = self._sous_titres[self._choisi] if self._choisi >= 0 else None
        changent = self._mots_qui_changent()
        peintre.setPen(Qt.PenStyle.NoPen)
        for index, mot in enumerate(self._mots):
            gauche, droite = self.x_du_temps(mot.debut), self.x_du_temps(mot.fin)
            if droite < 0 or gauche > self.width():
                continue
            if index in changent:
                couleur = qcolor(Couleurs.ERREUR if self._refus else Couleurs.ACCENT)
            elif choisi is not None and choisi.premier_mot <= index < choisi.dernier_mot:
                couleur = qcolor(Couleurs.ACCENT_SURVOL)
            else:
                couleur = qcolor(Couleurs.TEXTE_SECONDAIRE, Opacites.POIGNEE_FINE_SURVOL)
            largeur = max(droite - gauche - Dimensions.BORDURE, Dimensions.FRISE_CURSEUR)
            peintre.setBrush(couleur)
            peintre.drawRoundedRect(QRectF(gauche, haut, largeur, Dimensions.FRISE_MOTS_HAUTEUR), Arrondis.PETIT / 2, Arrondis.PETIT / 2)
        peintre.setBrush(Qt.BrushStyle.NoBrush)

    def _dessiner_glissement(self, peintre: QPainter) -> None:
        if self._glisse is None:
            survol = None
        else:
            index, mot = self._glisse
            x = self.x_de_la_limite(mot)
            couleur = Couleurs.ERREUR if self._refus else Couleurs.ACCENT
            peintre.setPen(QPen(qcolor(couleur), Dimensions.FRISE_CURSEUR))
            peintre.drawLine(QPointF(x, self._haut_des_blocs()), QPointF(x, self._haut_des_mots() + Dimensions.FRISE_MOTS_HAUTEUR))
            survol = index
        # Les bords qui se glissent : un trait fin, plus visible pendant le glissement.
        for index in self.bords_communs():
            if index == survol:
                continue
            x = self.x_du_bord(index)
            peintre.setPen(QPen(qcolor(Couleurs.TEXTE_SECONDAIRE, Opacites.POIGNEE_FINE), Dimensions.BORDURE))
            haut = self._haut_des_blocs() + Espacements.S
            peintre.drawLine(QPointF(x, haut), QPointF(x, self._haut_des_blocs() + Dimensions.FRISE_BLOC_HAUTEUR - Espacements.S))


class FriseSousTitres(QWidget):
    """La frise et sa barre de défilement (visible quand la frise est agrandie)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.XS)
        self.toile = ToileFrise()
        disposition.addWidget(self.toile)
        self.barre = QScrollBar(Qt.Orientation.Horizontal)
        self.barre.hide()
        disposition.addWidget(self.barre)
        self.toile.vue_change.connect(self._actualiser_barre)
        self.barre.valueChanged.connect(lambda valeur: self.toile.definir_debut(valeur / MILLISECONDES))

    def _actualiser_barre(self) -> None:
        toile = self.toile
        visible = toile.duree_visible()
        agrandie = toile.zoom > 1 and toile.duree > visible
        self.barre.setVisible(agrandie)
        self.barre.blockSignals(True)
        self.barre.setRange(0, round((toile.duree - visible) * MILLISECONDES) if agrandie else 0)
        self.barre.setPageStep(max(1, round(visible * MILLISECONDES)))
        self.barre.setSingleStep(max(1, round(visible * MILLISECONDES / 10)))
        self.barre.setValue(round(toile.debut * MILLISECONDES))
        self.barre.blockSignals(False)
