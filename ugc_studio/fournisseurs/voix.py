"""Types communs pour la génération de voix (TTS), quel que soit le fournisseur."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Replique:
    """Un bloc du script, avec sa consigne de style facultative (§5.3)."""

    texte: str  # texte exact à prononcer (balises « <laugh> » comprises)
    style: str = ""  # ex. « chaleureux et enthousiaste, débit rapide »


@dataclass(frozen=True)
class RequeteVoix:
    modele: str
    voix: str  # voix de base (ex. « Kore ») ou identifiant d'une voix créée
    repliques: tuple[Replique, ...]


@dataclass
class ResultatVoix:
    audio_wav: bytes  # fichier WAV complet (24 kHz, mono, 16 bits)
    duree_s: float
    tokens_entree: int = 0
    tokens_sortie: int = 0
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VoixDeBase:
    nom: str
    caractere: str  # en français
    caractere_origine: str  # tel que décrit par Google
    genre: str  # « F » ou « M » (indicatif)

    @property
    def libelle(self) -> str:
        genre = {"F": "féminine", "M": "masculine"}.get(self.genre, "")
        return f"{self.nom} — {self.caractere}" + (f" · {genre}" if genre else "")
