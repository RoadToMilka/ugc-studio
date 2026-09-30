"""Balises d'expression du TTS Gemini (§5.2) : <laugh>, <sigh>, <short pause>…

Chaque balise a deux noms :
- son **nom anglais** (« laugh »), le seul envoyé à Google et enregistré dans les projets. La
  documentation officielle de Gemini TTS demande de garder les balises en anglais même quand le
  texte est dans une autre langue (« continue to use English inline tags for best results ») ;
- son **nom français** (« rire »), le seul affiché dans l'app (palette, badges du script,
  menus, styles). Le nom anglais apparaît au survol.

Dans l'éditeur, les balises s'affichent comme des badges colorés par famille.
"""

from __future__ import annotations

import re
import unicodedata
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

# Nom affiché dans l'app pour chaque balise (validé le 30/09/2026, cahier des charges §5.2).
NOMS_FRANCAIS: dict[str, str] = {
    # Pauses
    "short pause": "pause courte",
    "long pause": "pause longue",
    # Rires
    "laugh": "rire",
    "laughter": "éclats de rire",
    "giggle": "gloussement",
    "chuckle": "petit rire",
    "chuckles": "rit doucement",
    "snicker": "ricanement",
    "cackle": "rire strident",
    # Souffle
    "breath": "respiration",
    "heavy breath": "respiration lourde",
    "exhales": "souffle",
    "sigh": "soupir",
    "sighs": "soupire",
    "phew": "ouf",
    "pff": "pff",
    "pant": "halètement",
    "yawn": "bâillement",
    # Réactions
    "gasp": "souffle coupé",
    "cheer": "cri de joie",
    "shout": "cri",
    "scream": "hurlement",
    "shriek": "cri perçant",
    "argh": "argh",
    "groan": "plainte",
    "grunt": "grognement",
    "tsk": "tss",
    "snort": "reniflement",
    # Voix
    "whispers": "chuchote",
    "whispering": "en chuchotant",
    "throat-clearing": "raclement de gorge",
    "cough": "toux",
    "sneeze": "éternuement",
    # Émotions fortes
    "cry": "pleurs",
    "sob": "sanglot",
    "whimper": "geignement",
    "moan": "gémissement",
    "growl": "grondement",
    "grr": "grr",
    "hiss": "sifflement",
}

_FAMILLE_DE = {balise: famille for famille in FAMILLES for balise in famille.balises}
TOUTES = tuple(_FAMILLE_DE)

# Balises écrites en anglais, comme dans le texte envoyé à Google : « <laugh> », « < short pause > »…
# (espaces tolérés, majuscules ignorées).
MOTIF_BALISE = re.compile(r"<\s*([a-zA-Z][a-zA-Z -]*?)\s*>")
# Balises écrites à la main ou collées, en anglais ou en français : « <laugh> », « <rire> »,
# « <éclats de rire> »… (lettres accentuées acceptées).
MOTIF_BALISE_SAISIE = re.compile(r"<\s*([^\W\d_](?:[^\W\d_]|[ -])*?)\s*>")


def _cle(nom: str) -> str:
    """Forme simplifiée d'un nom, pour le reconnaître quelle que soit son écriture :
    « Éclats  de Rire » → « eclats de rire » (sans accents ni majuscules, espaces réduits)."""
    sans_accents = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii")
    return " ".join(sans_accents.lower().split())


# Nom (anglais ou français, sous sa forme simplifiée) → nom anglais de la balise.
_BALISE_DE_NOM = {_cle(balise): balise for balise in TOUTES} | {
    _cle(francais): balise for balise, francais in NOMS_FRANCAIS.items()
}


def famille_de(balise: str) -> Famille | None:
    return _FAMILLE_DE.get(balise)


def est_balise(texte: str) -> bool:
    """Nom anglais d'une balise connue ?"""
    return texte.lower() in _FAMILLE_DE


def nom_affiche(balise: str) -> str:
    """Nom français d'une balise, tel qu'affiché dans l'app (« laugh » → « rire »)."""
    return NOMS_FRANCAIS.get(balise, balise)


def balise_depuis_nom(nom: str) -> str | None:
    """Nom anglais de la balise désignée par `nom`, écrit en anglais ou en français, avec ou sans
    accents ni majuscules (« rire », « Eclats de rire », « laugh »…). None si inconnue."""
    return _BALISE_DE_NOM.get(_cle(nom))


def info_balise(balise: str) -> str:
    """Texte de l'infobulle d'une balise : son vrai nom, celui envoyé à Google."""
    return f"Envoyé à Google : <{balise}>"
