"""Écoute comparative des variantes (§5.6) : lecture enchaînée, ou bascule A/B instantanée au
même moment du texte.

Chaque variante a son propre lecteur, chargé à l'ouverture : passer de A à B ne demande donc pas
de recharger un fichier, seulement de se placer au bon endroit et de lancer la lecture.

« Au même moment du texte » : les variantes n'ont pas exactement la même durée (débit, pauses…).
On se place donc à la même proportion : à 40 % de A, on passe à 40 % de B.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

from .lecteur import VARIABLE_SANS_AUDIO

journal = logging.getLogger(__name__)

PAUSE_ENCHAINEMENT_MS = 600  # silence entre deux variantes pendant la lecture enchaînée


def position_equivalente(position_ms: int, duree_depart_ms: int, duree_arrivee_ms: int) -> int:
    """Même moment du texte dans une autre variante : même proportion de la durée."""
    if duree_depart_ms <= 0 or duree_arrivee_ms <= 0:
        return 0
    proportion = min(1.0, max(0.0, position_ms / duree_depart_ms))
    return round(proportion * duree_arrivee_ms)


class ComparateurAudio(QObject):
    """`fichiers` et `durees_ms` : une entrée par variante, dans l'ordre (A, B, C…)."""

    etat_change = Signal()  # variante écoutée, lecture ou pause, enchaînement
    position_change = Signal(int, int)  # (position, durée) de la variante écoutée, en ms

    def __init__(self, fichiers: list[Path], durees_ms: list[int], parent=None):
        super().__init__(parent)
        self._durees = list(durees_ms)
        self._actif = 0
        self._en_lecture = False
        self._enchainement = False
        self._positions = [0] * len(fichiers)  # sans audio (tests) : positions mémorisées
        self._lecteurs: list = []
        self._sorties: list = []
        self._suite = QTimer(self)
        self._suite.setSingleShot(True)
        self._suite.setInterval(PAUSE_ENCHAINEMENT_MS)
        self._suite.timeout.connect(self._variante_suivante)
        if os.environ.get(VARIABLE_SANS_AUDIO):
            return
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            journal.warning("Qt Multimedia indisponible : écoute comparative sans son", exc_info=True)
            return
        for index, fichier in enumerate(fichiers):
            lecteur = QMediaPlayer(self)
            sortie = QAudioOutput(self)
            lecteur.setAudioOutput(sortie)
            lecteur.setSource(QUrl.fromLocalFile(str(fichier)))
            lecteur.positionChanged.connect(lambda position, i=index: self._position_lue(i, position))
            lecteur.mediaStatusChanged.connect(lambda statut, i=index: self._statut(i, statut))
            lecteur.errorOccurred.connect(
                lambda _erreur, message: journal.warning("Lecture impossible : %s", message)
            )
            self._lecteurs.append(lecteur)
            self._sorties.append(sortie)

    # --- État --------------------------------------------------------------------------------

    @property
    def nombre(self) -> int:
        return len(self._durees)

    @property
    def actif(self) -> int:
        """Indice de la variante écoutée (0 = A)."""
        return self._actif

    @property
    def en_lecture(self) -> bool:
        return self._en_lecture

    @property
    def enchainement(self) -> bool:
        return self._enchainement

    def duree(self, index: int | None = None) -> int:
        return self._durees[self._actif if index is None else index]

    def position(self) -> int:
        if self._lecteurs:
            return int(self._lecteurs[self._actif].position())
        return self._positions[self._actif]

    # --- Commandes ---------------------------------------------------------------------------

    def basculer_lecture(self) -> None:
        """Lecture ↔ pause de la variante écoutée."""
        if self._en_lecture:
            self.pause()
        else:
            self.jouer()

    def jouer(self, index: int | None = None) -> None:
        """Joue une variante là où elle en est (depuis le début si elle était finie)."""
        if index is not None and index != self._actif:
            self.basculer(index)
        if self.position() >= self.duree() > 0:
            self._aller(self._actif, 0)
        self._en_lecture = True
        self._lire(self._actif)
        self.etat_change.emit()

    def pause(self) -> None:
        self._suite.stop()
        self._en_lecture = False
        self._pause(self._actif)
        self.etat_change.emit()

    def basculer(self, index: int) -> None:
        """Passe à une autre variante au même moment du texte, en lecture comme en pause."""
        if not 0 <= index < self.nombre or index == self._actif:
            return
        self._suite.stop()
        self._enchainement = False  # on compare à la main : la lecture enchaînée s'arrête
        position = position_equivalente(self.position(), self.duree(), self.duree(index))
        self._pause(self._actif)
        self._actif = index
        self._aller(index, position)
        if self._en_lecture:
            self._lire(index)
        self.etat_change.emit()
        self.position_change.emit(self.position(), self.duree())

    def enchainer(self) -> None:
        """Lecture enchaînée : A, puis B, puis C… chacune depuis le début."""
        self._suite.stop()
        self._pause(self._actif)
        self._actif = 0
        self._enchainement = True
        self._aller(0, 0)
        self._en_lecture = True
        self._lire(0)
        self.etat_change.emit()

    def aller_a(self, position_ms: int) -> None:
        self._aller(self._actif, position_ms)
        self.position_change.emit(self.position(), self.duree())

    def arreter(self) -> None:
        """Arrête tout et libère les fichiers (sinon Windows empêcherait de les supprimer)."""
        self._suite.stop()
        self._en_lecture = False
        self._enchainement = False
        for lecteur in self._lecteurs:
            lecteur.stop()
            lecteur.setSource(QUrl())
        self._lecteurs = []
        self.etat_change.emit()

    # --- Lecteurs ----------------------------------------------------------------------------

    def _lire(self, index: int) -> None:
        if self._lecteurs:
            self._lecteurs[index].play()

    def _pause(self, index: int) -> None:
        if self._lecteurs:
            self._lecteurs[index].pause()

    def _aller(self, index: int, position_ms: int) -> None:
        position_ms = max(0, min(position_ms, self._durees[index]))
        if self._lecteurs:
            self._lecteurs[index].setPosition(position_ms)
        else:
            self._positions[index] = position_ms

    def _position_lue(self, index: int, position_ms: int) -> None:
        if index == self._actif:
            self.position_change.emit(int(position_ms), self.duree())

    def _statut(self, index: int, statut) -> None:
        if index == self._actif and statut.name == "EndOfMedia":
            self.variante_finie()

    def variante_finie(self) -> None:
        """La variante écoutée est arrivée au bout : la suivante (lecture enchaînée) ou l'arrêt."""
        if self._enchainement and self._actif + 1 < self.nombre:
            self._suite.start()
            return
        self._en_lecture = False
        self._enchainement = False
        self.etat_change.emit()

    def _variante_suivante(self) -> None:
        if not self._enchainement:
            return
        self._actif += 1
        self._aller(self._actif, 0)
        self._lire(self._actif)
        self.etat_change.emit()
