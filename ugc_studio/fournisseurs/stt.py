"""Types communs pour la transcription (STT), quel que soit le fournisseur (§6)."""

from __future__ import annotations

from dataclasses import dataclass, field

MODE_VERBATIM = "verbatim"  # mot à mot, avec les temps (indispensable pour les sous-titres)
MODE_SMART = "smart"  # texte nettoyé (hésitations retirées, ponctuation soignée), sans temps


@dataclass(frozen=True)
class RequeteTranscription:
    modele: str
    audio: bytes = field(repr=False)  # fichier audio complet (ex. WAV 16 kHz mono)
    type_mime: str = "audio/wav"
    langue: str = ""  # code BCP-47 (ex. « fr-FR ») ; vide = détection automatique
    mode: str = MODE_VERBATIM
    horodatage: bool = True  # temps de chaque mot (mode verbatim seulement)
    separation_voix: bool = False  # chaque mot reçoit la personne qui parle (mode verbatim seulement)
    nom: str = "audio.wav"  # nom du fichier chez le fournisseur (pour s'y retrouver)


@dataclass(frozen=True)
class MotTranscrit:
    texte: str
    debut: float  # secondes
    fin: float
    locuteur: str = ""  # ex. « spk_1 »


@dataclass
class ResultatTranscription:
    texte: str
    mots: list[MotTranscrit] = field(default_factory=list)
    tokens_entree: int = 0
    tokens_sortie: int = 0
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FichierTeleverse:
    """Fichier déposé chez le fournisseur (API Files de Google : gardé 48 h)."""

    nom: str  # ex. « files/abc123 » (pour le retrouver ou le supprimer)
    uri: str  # adresse à donner dans une requête
    type_mime: str = ""
    etat: str = ""  # « ACTIVE » quand il est prêt
