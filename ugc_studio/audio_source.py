"""Audio d'une source à transcrire (§6.2, §6.3 bis).

Google transcrit un fichier audio. L'app prépare donc la piste son de la vidéo (ou l'audio
importé) en WAV 16 bits, mono, 16 kHz : sans perte pour la parole, et léger à envoyer.
- Un WAV 16 bits est préparé ici, en Python (mélange des canaux, changement de fréquence).
- Les autres formats (MP4, MOV, MP3, M4A…) sont décodés par Qt Multimedia (voir
  ui/extraction.py), puis passent par les mêmes fonctions.
- Une source trop longue pour Google est coupée en morceaux, chaque coupure étant placée dans un
  silence voisin (jamais au milieu d'un mot).
"""

from __future__ import annotations

import math
from array import array

from .audio import OCTETS_PAR_ECHANTILLON, lire_wav, wav_depuis_pcm
from .audio_flux import Convertisseur, FormatAudio

FREQUENCE_TRANSCRIPTION = 16_000  # Hz : suffisant pour la parole, fichier 3 fois plus léger qu'en 48 kHz
FENETRE_SILENCE_S = 10.0  # on cherche le silence jusqu'à 10 s avant ou après la coupure visée
PAS_SILENCE_S = 0.05  # le niveau sonore est mesuré par tranches de 50 ms


def en_mono(pcm: bytes, canaux: int) -> bytes:
    """Moyenne des canaux (stéréo → mono), échantillons 16 bits."""
    if canaux <= 1:
        return pcm
    echantillons = array("h")
    echantillons.frombytes(pcm[: len(pcm) - len(pcm) % (OCTETS_PAR_ECHANTILLON * canaux)])
    return array("h", (sum(echantillons[i : i + canaux]) // canaux for i in range(0, len(echantillons), canaux))).tobytes()


def reechantillonner(pcm_mono: bytes, frequence: int, cible: int = FREQUENCE_TRANSCRIPTION) -> bytes:
    """Change la fréquence d'un PCM 16 bits mono (interpolation linéaire)."""
    if frequence == cible:
        return pcm_mono
    return Convertisseur(FormatAudio(cible, 1, "int16")).convertir(pcm_mono, frequence)


def preparer_pcm(pcm: bytes, frequence: int, canaux: int) -> bytes:
    """PCM 16 bits quelconque → PCM 16 bits mono à 16 kHz."""
    return reechantillonner(en_mono(pcm, canaux), frequence)


def preparer_wav(donnees_wav: bytes) -> bytes:
    """WAV 16 bits (toute fréquence, mono ou stéréo) → WAV 16 kHz mono, prêt à transcrire."""
    pcm, frequence, canaux = lire_wav(donnees_wav)
    return wav_depuis_pcm(preparer_pcm(pcm, frequence, canaux), FREQUENCE_TRANSCRIPTION)


def niveau(pcm: bytes, debut: int, fin: int) -> float:
    """Niveau sonore (moyenne quadratique) des échantillons [debut, fin[ d'un PCM 16 bits mono."""
    echantillons = array("h")
    echantillons.frombytes(pcm[debut * OCTETS_PAR_ECHANTILLON : fin * OCTETS_PAR_ECHANTILLON])
    if not echantillons:
        return 0.0
    return math.sqrt(sum(e * e for e in echantillons) / len(echantillons))


def coupure_dans_un_silence(
    pcm: bytes, frequence: int, temps_vise: float, fenetre: float = FENETRE_SILENCE_S, pas: float = PAS_SILENCE_S
) -> float:
    """Moment le plus silencieux autour de `temps_vise` (± `fenetre` secondes) : c'est là qu'on
    coupe une longue source, pour ne pas couper un mot en deux."""
    total = len(pcm) // OCTETS_PAR_ECHANTILLON
    taille = max(1, int(pas * frequence))
    debut = max(0, int((temps_vise - fenetre) * frequence))
    fin = min(total, int((temps_vise + fenetre) * frequence))
    meilleur, meilleur_niveau = temps_vise, math.inf
    for position in range(debut, max(debut + 1, fin - taille + 1), taille):
        valeur = niveau(pcm, position, position + taille)
        # À niveau égal, on préfère le moment le plus proche de la coupure visée.
        ecart = abs(position / frequence - temps_vise)
        if valeur < meilleur_niveau or (valeur == meilleur_niveau and ecart < abs(meilleur - temps_vise)):
            meilleur, meilleur_niveau = (position + taille / 2) / frequence, valeur
    return max(0.0, min(meilleur, total / frequence))


def morceau_pcm(pcm: bytes, frequence: int, debut: float, fin: float) -> bytes:
    """Échantillons entre deux moments (en secondes) d'un PCM 16 bits mono."""
    return pcm[int(debut * frequence) * OCTETS_PAR_ECHANTILLON : int(fin * frequence) * OCTETS_PAR_ECHANTILLON]
