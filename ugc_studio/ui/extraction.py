"""Importer une source à transcrire (§6.2) : extraire sa piste son et lire ses informations.

- Piste son : un WAV 16 bits (ex. une prise) est préparé en Python (audio_source.py), dans une
  tâche de fond. Les autres formats (MP4, MOV, MKV, MP3, M4A…) sont décodés par Qt Multimedia
  (QAudioDecoder, qui s'appuie sur FFmpeg, fourni avec Qt), directement en 16 kHz mono.
  Résultat : un WAV 16 kHz mono 16 bits, prêt à envoyer à Google.
- Informations de la source (durée, résolution, images par seconde, codecs, HDR) : lues par
  Qt Multimedia, et gardées dans le projet (elles serviront aux exports vidéo).
"""

from __future__ import annotations

import logging
import os
import wave
from array import array
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

from ..audio import OCTETS_PAR_ECHANTILLON, wav_depuis_pcm
from ..audio_source import FREQUENCE_TRANSCRIPTION, preparer_pcm, preparer_wav
from . import taches
from .composants.lecteur import VARIABLE_SANS_AUDIO

journal = logging.getLogger(__name__)

DUREE_MAX_PREPARATION_PYTHON_S = 5 * 60  # au-delà, Qt (plus rapide) décode aussi les WAV
DELAI_SANS_NOUVELLES_MS = 60_000  # décodage bloqué : abandon au bout d'une minute sans progrès
EXTENSIONS_ACCEPTEES = (
    ".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi",  # vidéos
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif", ".wma",  # audios
)
FILTRE_FICHIERS = "Vidéos et audios (" + " ".join(f"*{e}" for e in EXTENSIONS_ACCEPTEES) + ")"


def wav_16_bits_court(chemin: Path) -> bool:
    """WAV 16 bits assez court pour être préparé directement en Python ?"""
    try:
        with wave.open(str(chemin), "rb") as entree:
            duree = entree.getnframes() / float(entree.getframerate() or 1)
            return entree.getsampwidth() == OCTETS_PAR_ECHANTILLON and duree <= DUREE_MAX_PREPARATION_PYTHON_S
    except (wave.Error, EOFError, OSError):
        return False


def _en_entiers_16_bits(donnees: bytes, type_echantillon: str) -> bytes:
    """Échantillons reçus de Qt (entiers 8/16/32 bits ou nombres à virgule) → entiers 16 bits."""
    if type_echantillon == "Int16":
        return donnees
    if type_echantillon == "Float":
        valeurs = array("f")
        valeurs.frombytes(donnees[: len(donnees) - len(donnees) % 4])
        return array("h", (max(-32768, min(32767, int(v * 32767))) for v in valeurs)).tobytes()
    if type_echantillon == "Int32":
        valeurs = array("i")
        valeurs.frombytes(donnees[: len(donnees) - len(donnees) % 4])
        return array("h", (v >> 16 for v in valeurs)).tobytes()
    if type_echantillon == "UInt8":
        return array("h", ((v - 128) << 8 for v in donnees)).tobytes()
    raise ValueError(f"Type d'échantillon inconnu : {type_echantillon}")


class ExtracteurAudio(QObject):
    """Extrait la piste son d'une source ; un seul fichier à la fois."""

    progression = Signal(float)  # de 0 à 1
    termine = Signal(bytes)  # WAV 16 kHz mono 16 bits
    echec = Signal(str)  # message clair

    def __init__(self, parent=None):
        super().__init__(parent)
        self._decodeur = None
        self._pcm = bytearray()
        self._fini = False
        self._veille = QTimer(self)
        self._veille.setSingleShot(True)
        self._veille.setInterval(DELAI_SANS_NOUVELLES_MS)
        self._veille.timeout.connect(lambda: self._abandon("le décodage ne progresse plus"))

    def extraire(self, chemin: Path) -> None:
        self.annuler()
        if wav_16_bits_court(chemin):
            taches.lancer(lambda: preparer_wav(chemin.read_bytes()), self.termine.emit, self._echec_python)
            return
        self._decoder(chemin)

    def _echec_python(self, erreur: Exception) -> None:
        self.echec.emit(f"piste son illisible ({erreur})")

    # --- Décodage par Qt Multimedia (FFmpeg) --------------------------------------------------

    def _decoder(self, chemin: Path) -> None:
        try:
            from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
        except ImportError:
            self.echec.emit("le module audio de Qt est absent de l'app")
            return
        format_voulu = QAudioFormat()
        format_voulu.setSampleRate(FREQUENCE_TRANSCRIPTION)
        format_voulu.setChannelCount(1)
        format_voulu.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._decodeur = QAudioDecoder(self)
        self._decodeur.setAudioFormat(format_voulu)
        self._decodeur.bufferReady.connect(self._lire_tampons)
        self._decodeur.finished.connect(self._decodage_fini)
        self._decodeur.error.connect(lambda *_details: self._erreur_decodeur())
        self._pcm = bytearray()
        self._fini = False
        self._decodeur.setSource(QUrl.fromLocalFile(str(chemin)))
        self._decodeur.start()
        self._veille.start()

    def _lire_tampons(self) -> None:
        decodeur = self._decodeur
        if decodeur is None:
            return
        self._veille.start()  # le décodage avance
        while decodeur.bufferAvailable():
            tampon = decodeur.read()
            if not tampon.isValid():
                break
            format_recu = tampon.format()
            donnees = _en_entiers_16_bits(bytes(tampon.constData()), format_recu.sampleFormat().name)
            if (format_recu.sampleRate(), format_recu.channelCount()) != (FREQUENCE_TRANSCRIPTION, 1):
                # Le décodeur n'a pas suivi le format demandé : on convertit nous-mêmes.
                donnees = preparer_pcm(donnees, format_recu.sampleRate(), format_recu.channelCount())
            self._pcm += donnees
            duree = decodeur.duration()
            if duree > 0:
                self.progression.emit(min(1.0, tampon.startTime() / 1000 / duree))

    def _decodage_fini(self) -> None:
        self._lire_tampons()
        self._fini = True
        self._veille.stop()
        pcm = bytes(self._pcm)
        self._liberer()
        if not pcm:
            self.echec.emit("aucune piste son dans ce fichier")
            return
        self.progression.emit(1.0)
        self.termine.emit(wav_depuis_pcm(pcm, FREQUENCE_TRANSCRIPTION))

    def _erreur_decodeur(self) -> None:
        if self._decodeur is not None:
            self._abandon(self._decodeur.errorString())

    def _abandon(self, raison: str) -> None:
        if self._fini or self._decodeur is None:
            return
        journal.warning("Extraction de la piste son impossible : %s", raison)
        self._fini = True
        self._veille.stop()
        self._liberer()
        self.echec.emit(raison or "format non reconnu")

    def annuler(self) -> None:
        self._veille.stop()
        self._fini = True
        self._liberer()

    def _liberer(self) -> None:
        if self._decodeur is not None:
            self._decodeur.stop()
            self._decodeur.deleteLater()
            self._decodeur = None
        self._pcm = bytearray()


# --- Informations de la source ---------------------------------------------------------------------


def _lisible(valeur):
    """Valeur de Qt → texte ou nombre enregistrable dans le projet."""
    if valeur is None:
        return None
    if hasattr(valeur, "width") and hasattr(valeur, "height"):
        return [valeur.width(), valeur.height()]
    if hasattr(valeur, "name") and not isinstance(valeur, (str, int, float)):
        return str(valeur.name)
    if isinstance(valeur, (bool, int, float, str)):
        return valeur
    return str(valeur)


class LecteurInfos(QObject):
    """Lit les informations d'une vidéo ou d'un audio (sans le jouer)."""

    pretes = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lecteur = None

    def lire(self, chemin: Path) -> None:
        self._liberer()
        if os.environ.get(VARIABLE_SANS_AUDIO):
            return  # tests automatiques : pas de lecture des fichiers par Qt Multimedia
        try:
            from PySide6.QtMultimedia import QMediaPlayer
        except ImportError:
            return
        self._lecteur = QMediaPlayer(self)
        self._lecteur.mediaStatusChanged.connect(self._statut)
        self._lecteur.setSource(QUrl.fromLocalFile(str(chemin)))

    def _statut(self, statut) -> None:
        if self._lecteur is None or statut.name not in ("LoadedMedia", "InvalidMedia"):
            return
        infos: dict = {}
        if statut.name == "LoadedMedia":
            try:
                infos = self._infos()
            except Exception:  # noqa: BLE001 — les infos sont un plus : on continue sans
                journal.warning("Informations de la source illisibles", exc_info=True)
        self._liberer()
        if infos:
            self.pretes.emit(infos)

    def _infos(self) -> dict:
        from PySide6.QtMultimedia import QMediaMetaData

        lecteur = self._lecteur
        donnees = lecteur.metaData()
        cles = {
            "resolution": QMediaMetaData.Key.Resolution,
            "images_par_seconde": QMediaMetaData.Key.VideoFrameRate,
            "codec_video": QMediaMetaData.Key.VideoCodec,
            "debit_video": QMediaMetaData.Key.VideoBitRate,
            "codec_audio": QMediaMetaData.Key.AudioCodec,
            "debit_audio": QMediaMetaData.Key.AudioBitRate,
            "format": QMediaMetaData.Key.FileFormat,
        }
        hdr = getattr(QMediaMetaData.Key, "HasHdrContent", None)  # Qt 6.8 et plus
        if hdr is not None:
            cles["hdr"] = hdr
        infos = {"duree_s": round(lecteur.duration() / 1000, 3), "video": bool(lecteur.hasVideo())}
        for nom, cle in cles.items():
            valeur = _lisible(donnees.value(cle))
            if valeur not in (None, "", 0, [0, 0]):
                infos[nom] = valeur
        return infos

    def _liberer(self) -> None:
        if self._lecteur is not None:
            self._lecteur.stop()
            self._lecteur.setSource(QUrl())
            self._lecteur.deleteLater()
            self._lecteur = None
