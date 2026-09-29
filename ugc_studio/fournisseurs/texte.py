"""Types communs pour la génération de texte (ex. traduction d'un style en anglais, §5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequeteTexte:
    modele: str
    texte: str  # demande envoyée au modèle
    consigne_systeme: str = ""  # rôle et règles donnés au modèle (« tu traduis… »)
    reflexion: str = "low"  # niveau de « réflexion » du modèle : plus bas = plus rapide et moins cher


@dataclass
class ResultatTexte:
    texte: str
    tokens_entree: int = 0
    tokens_sortie: int = 0  # réflexion comprise (facturée comme de la sortie)
    details: dict = field(default_factory=dict)
