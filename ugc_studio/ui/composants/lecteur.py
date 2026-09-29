"""Lecteur audio de l'app : une seule prise joue à la fois (§5.6 « lecture immédiate »).

Utilise Qt Multimedia. Si le module audio n'est pas disponible, la prise est ouverte avec le
lecteur audio de Windows.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices

journal = logging.getLogger(__name__)


class Lecteur(QObject):
    # (chemin du fichier en cours, en lecture ?)
    etat_change = Signal(str, bool)
    # (position, durée) en millisecondes
    position_change = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chemin = ""
        self._lecteur = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._lecteur = QMediaPlayer(self)
            self._sortie = QAudioOutput(self)
            self._lecteur.setAudioOutput(self._sortie)
            self._lecteur.playbackStateChanged.connect(self._etat_lecture)
            self._lecteur.positionChanged.connect(
                lambda position: self.position_change.emit(position, self._lecteur.duration())
            )
            self._lecteur.errorOccurred.connect(
                lambda _erreur, message: journal.warning("Lecture audio impossible : %s", message)
            )
        except ImportError:
            journal.warning("Qt Multimedia indisponible : lecture avec le lecteur de Windows", exc_info=True)

    @property
    def chemin(self) -> str:
        return self._chemin

    def en_lecture(self, chemin: str | Path | None = None) -> bool:
        if self._lecteur is None:
            return False
        from PySide6.QtMultimedia import QMediaPlayer

        lecture = self._lecteur.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        return lecture and (chemin is None or str(chemin) == self._chemin)

    def basculer(self, chemin: str | Path) -> None:
        """Lance la lecture de ce fichier, ou la met en pause s'il joue déjà."""
        chemin = str(chemin)
        if self._lecteur is None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(chemin))
            return
        if chemin == self._chemin and self.en_lecture():
            self._lecteur.pause()
            return
        if chemin != self._chemin:
            self._lecteur.stop()
            self._chemin = chemin
            self._lecteur.setSource(QUrl.fromLocalFile(chemin))
        self._lecteur.play()

    def aller_a(self, position_ms: int) -> None:
        if self._lecteur is not None:
            self._lecteur.setPosition(position_ms)

    def arreter(self) -> None:
        if self._lecteur is not None:
            self._lecteur.stop()
            # Libère le fichier (sinon Windows empêche de le supprimer).
            self._lecteur.setSource(QUrl())
        self._chemin = ""

    def _etat_lecture(self, _etat) -> None:
        self.etat_change.emit(self._chemin, self.en_lecture())
