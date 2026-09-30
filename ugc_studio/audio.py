"""Outils audio : fichiers WAV (format natif du TTS Gemini : 24 kHz, mono, 16 bits) et MP3."""

from __future__ import annotations

import io
import wave
from pathlib import Path

FREQUENCE_TTS = 24_000  # échantillons par seconde
CANAUX_TTS = 1
OCTETS_PAR_ECHANTILLON = 2  # 16 bits


def wav_depuis_pcm(pcm: bytes, frequence: int = FREQUENCE_TTS, canaux: int = CANAUX_TTS) -> bytes:
    """Ajoute l'en-tête WAV à des échantillons bruts (PCM 16 bits)."""
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as sortie:
        sortie.setnchannels(canaux)
        sortie.setsampwidth(OCTETS_PAR_ECHANTILLON)
        sortie.setframerate(frequence)
        sortie.writeframes(pcm)
    return tampon.getvalue()


def en_wav(donnees: bytes, frequence: int = FREQUENCE_TTS) -> bytes:
    """Renvoie un WAV complet : tel quel s'il en est déjà un (en-tête « RIFF »), sinon on l'enveloppe."""
    return donnees if donnees[:4] == b"RIFF" else wav_depuis_pcm(donnees, frequence)


def lire_wav(donnees: bytes) -> tuple[bytes, int, int]:
    """(échantillons PCM, fréquence, canaux) d'un WAV 16 bits."""
    with wave.open(io.BytesIO(donnees), "rb") as entree:
        if entree.getsampwidth() != OCTETS_PAR_ECHANTILLON:
            raise ValueError("Seuls les WAV 16 bits sont pris en charge.")
        return entree.readframes(entree.getnframes()), entree.getframerate(), entree.getnchannels()


def duree_wav(donnees: bytes) -> float:
    """Durée en secondes."""
    with wave.open(io.BytesIO(donnees), "rb") as entree:
        return entree.getnframes() / float(entree.getframerate())


def silence_pcm(secondes: float, frequence: int = FREQUENCE_TTS, canaux: int = CANAUX_TTS) -> bytes:
    """Échantillons PCM 16 bits d'un silence de cette durée."""
    return b"\x00" * int(secondes * frequence) * canaux * OCTETS_PAR_ECHANTILLON


def concatener_wav(morceaux: list[bytes], silence_s: float = 0.0) -> bytes:
    """Recolle plusieurs WAV de même format (ex. un script long généré en plusieurs fois)."""
    if not morceaux:
        raise ValueError("Aucun morceau à recoller.")
    _, frequence, canaux = lire_wav(morceaux[0])
    silence = silence_pcm(silence_s, frequence, canaux)
    pcm = []
    for index, morceau in enumerate(morceaux):
        echantillons, f, c = lire_wav(morceau)
        if (f, c) != (frequence, canaux):
            raise ValueError("Les morceaux audio n'ont pas le même format.")
        if index:
            pcm.append(silence)
        pcm.append(echantillons)
    return wav_depuis_pcm(b"".join(pcm), frequence, canaux)


def exporter_mp3(wav: Path, destination: Path, debit_kbps: int = 192) -> None:
    """Convertit un WAV en MP3 (encodeur LAME, via la petite bibliothèque « lameenc »)."""
    import lameenc

    pcm, frequence, canaux = lire_wav(wav.read_bytes())
    encodeur = lameenc.Encoder()
    encodeur.set_bit_rate(debit_kbps)
    encodeur.set_in_sample_rate(frequence)
    encodeur.set_channels(canaux)
    encodeur.set_quality(2)  # 2 = haute qualité (0 = meilleure, 9 = plus rapide)
    donnees = encodeur.encode(pcm) + encodeur.flush()
    destination.write_bytes(bytes(donnees))
