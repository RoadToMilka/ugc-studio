"""Balises d'expression du TTS Gemini (§5.2) : <laugh>, <sigh>, <short pause>…

Liste issue de la documentation officielle Gemini TTS ; les balises restent en anglais même
pour un texte français. Dans l'éditeur, elles s'affichent comme des badges colorés par famille.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Famille:
    identifiant: str  # sert aussi à choisir la couleur du badge (voir ui/theme.py)
    nom: str
    balises: tuple[str, ...]


FAMILLES: tuple[Famille, ...] = (
    Famille("pauses", "Pauses", ("short pause", "long pause")),
    Famille("rires", "Rires", ("laugh", "laughter", "giggle", "chuckle", "chuckles", "snicker", "cackle")),
    Famille(
        "souffle",
        "Souffle",
        ("breath", "heavy breath", "exhales", "sigh", "sighs", "phew", "pff", "pant", "yawn"),
    ),
    Famille(
        "reactions",
        "Réactions",
        ("gasp", "cheer", "shout", "scream", "shriek", "argh", "groan", "grunt", "tsk", "snort"),
    ),
    Famille("voix", "Voix", ("whispers", "whispering", "throat-clearing", "cough", "sneeze")),
    Famille("emotions", "Émotions fortes", ("cry", "sob", "whimper", "moan", "growl", "grr", "hiss")),
)

_FAMILLE_DE = {balise: famille for famille in FAMILLES for balise in famille.balises}
TOUTES = tuple(_FAMILLE_DE)

# « <laugh> », « < short pause > »… (espaces tolérés, majuscules ignorées)
MOTIF_BALISE = re.compile(r"<\s*([a-zA-Z][a-zA-Z -]*?)\s*>")


def famille_de(balise: str) -> Famille | None:
    return _FAMILLE_DE.get(balise)


def est_balise(texte: str) -> bool:
    return texte.lower() in _FAMILLE_DE
