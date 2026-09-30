"""Écoute pendant la génération (§5.6) : la voix joue au fur et à mesure qu'elle arrive.

Google envoie l'audio par morceaux (voir fournisseurs/google.py). Chaque morceau est converti au
format accepté par la carte son (voir audio_flux.py), puis confié à Qt Multimedia (QAudioSink) en
« mode push » : toutes les 20 ms, l'app remplit la réserve de la carte son avec ce qui est arrivé.
La lecture commence dès qu'il y a un peu d'avance (0,3 s), pour ne pas couper si le morceau
suivant tarde un peu.

Sans sortie audio utilisable (pas de carte son, tests automatiques…), `commencer()` répond non :
la voix est alors générée d'un bloc et la prise est jouée à la fin, comme avant.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QObject, QTimer, Signal

from ...audio_flux import FORMAT_TTS, TYPES, Convertisseur, FormatAudio
from .lecteur import VARIABLE_SANS_AUDIO

journal = logging.getLogger(__name__)

INTERVALLE_REMPLISSAGE_MS = 20
AVANCE_AVANT_LECTURE_S = 0.3
# Types d'échantillons de Qt (QAudioFormat.SampleFormat) → noms utilisés par audio_flux.py
TYPES_QT = {"UInt8": "uint8", "Int16": "int16", "Int32": "int32", "Float": "float"}


class LecteurFlux(QObject):
    """`simulation` (tests) : tout se passe comme avec une carte son, sans rien jouer."""

    fini = Signal()  # la lecture est terminée (tout joué, ou arrêtée)

    def __init__(self, parent=None, simulation: bool = False):
        super().__init__(parent)
        self.simulation = simulation
        self._sortie = None  # QAudioSink
        self._appareil = None  # la réserve de la carte son, où l'on écrit
        self._convertisseur: Convertisseur | None = None
        self._tampon = bytearray()  # audio converti, pas encore confié à la carte son
        self._avance = 0
        self._trame = FORMAT_TTS.octets_par_trame
        self._termine = False
        self._a_joue = False
        self.octets_joues = 0  # en simulation : ce qui aurait été joué
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(INTERVALLE_REMPLISSAGE_MS)
        self._minuterie.timeout.connect(self._remplir)

    @property
    def actif(self) -> bool:
        """Une écoute est en cours (préparée, en attente d'avance ou en lecture)."""
        return self._convertisseur is not None

    @property
    def a_joue(self) -> bool:
        """La voix a-t-elle commencé à jouer pendant la dernière génération ?"""
        return self._a_joue

    # --- Préparation -------------------------------------------------------------------------

    def commencer(self) -> bool:
        """Prépare une nouvelle écoute ; renvoie False si aucune sortie audio n'est utilisable."""
        self.arreter()
        self._a_joue = False
        self.octets_joues = 0
        if self.simulation:
            format_sortie = FORMAT_TTS
        elif os.environ.get(VARIABLE_SANS_AUDIO):
            return False
        else:
            format_sortie = self._ouvrir_sortie()
            if format_sortie is None:
                return False
        self._convertisseur = Convertisseur(format_sortie)
        self._trame = format_sortie.octets_par_trame
        self._avance = int(format_sortie.octets_par_seconde() * AVANCE_AVANT_LECTURE_S)
        self._avance -= self._avance % self._trame
        self._termine = False
        return True

    def _ouvrir_sortie(self) -> FormatAudio | None:
        """Sortie audio par défaut de Windows, au format du TTS si elle l'accepte, sinon à son
        format préféré (l'audio sera converti)."""
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

            appareil = QMediaDevices.defaultAudioOutput()
            if appareil.isNull():
                journal.info("Écoute pendant la génération : aucune sortie audio")
                return None
            souhaite = QAudioFormat()
            souhaite.setSampleRate(FORMAT_TTS.frequence)
            souhaite.setChannelCount(FORMAT_TTS.canaux)
            souhaite.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            choisi = souhaite if appareil.isFormatSupported(souhaite) else appareil.preferredFormat()
            echantillon = TYPES_QT.get(choisi.sampleFormat().name, "")
            if echantillon not in TYPES or choisi.sampleRate() <= 0 or choisi.channelCount() <= 0:
                journal.warning("Écoute pendant la génération : format de sortie non pris en charge")
                return None
            self._sortie = QAudioSink(appareil, choisi, self)
            journal.info(
                "Écoute pendant la génération : %s Hz, %s canal(aux), %s",
                choisi.sampleRate(),
                choisi.channelCount(),
                echantillon,
            )
            return FormatAudio(choisi.sampleRate(), choisi.channelCount(), echantillon)
        except Exception:  # noqa: BLE001 — l'écoute est un confort : la génération continue sans elle
            journal.warning("Écoute pendant la génération impossible", exc_info=True)
            self._sortie = None
            return None

    # --- Morceaux reçus ----------------------------------------------------------------------

    def ajouter(self, pcm: bytes, frequence: int) -> None:
        """Un morceau de voix vient d'arriver (PCM 16 bits mono)."""
        if self._convertisseur is None:
            return
        try:
            self._tampon += self._convertisseur.convertir(pcm, frequence)
        except Exception:  # noqa: BLE001
            journal.warning("Morceau d'audio non converti : écoute arrêtée", exc_info=True)
            self.arreter()
            return
        if not self._a_joue and len(self._tampon) >= self._avance:
            self._demarrer()
        elif self.simulation and self._a_joue:
            self._remplir()

    def terminer(self) -> None:
        """Toute la voix est arrivée : la lecture continue jusqu'au bout de ce qui reste."""
        if self._convertisseur is None:
            return
        self._termine = True
        if not self._a_joue:
            if self._tampon:
                self._demarrer()
            else:
                self.arreter()
        elif self.simulation:
            self._remplir()

    # --- Lecture -----------------------------------------------------------------------------

    def _demarrer(self) -> None:
        self._a_joue = True
        if self.simulation:
            self._remplir()
            return
        try:
            self._appareil = self._sortie.start()
        except Exception:  # noqa: BLE001
            journal.warning("Écoute pendant la génération impossible", exc_info=True)
            self._appareil = None
        if self._appareil is None:
            self._a_joue = False
            self.arreter()
            return
        self._minuterie.start()
        self._remplir()

    def _remplir(self) -> None:
        """Confie à la carte son tout ce qu'elle peut prendre (en trames entières)."""
        if self.simulation:
            self.octets_joues += len(self._tampon)
            self._tampon.clear()
            if self._termine:
                self.arreter()
            return
        if self._sortie is None or self._appareil is None:
            return
        taille = min(self._sortie.bytesFree(), len(self._tampon))
        taille -= taille % self._trame
        if taille > 0:
            ecrit = self._appareil.write(bytes(self._tampon[:taille]))
            if ecrit > 0:
                del self._tampon[:ecrit]
        if self._sortie.error().name != "NoError":
            journal.warning("Écoute pendant la génération interrompue : %s", self._sortie.error().name)
            self.arreter()
        elif self._termine and not self._tampon and self._sortie.state().name == "IdleState":
            self.arreter()  # tout a été joué

    def arreter(self) -> None:
        """Arrête l'écoute (tout de suite) et libère la carte son."""
        self._minuterie.stop()
        etait_actif = self._convertisseur is not None
        if self._sortie is not None:
            try:
                self._sortie.reset()
                self._sortie.stop()
            except RuntimeError:
                pass
            self._sortie.deleteLater()
        self._sortie = None
        self._appareil = None
        self._convertisseur = None
        self._tampon.clear()
        self._termine = False
        if etait_actif:
            self.fini.emit()
