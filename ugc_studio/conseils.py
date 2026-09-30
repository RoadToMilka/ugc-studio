"""Conseils Google et vérifications en direct (§5.4 bis, §5.5).

Chaque conseil est gardé en anglais d'origine avec sa traduction française ; l'app n'affiche que le
français, dans les fenêtres « Conseils » (voir conseils_des_pages.py). Les vérifications produisent
des avertissements non bloquants pendant la saisie d'un style ou d'une description de voix.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .balises import TOUTES


@dataclass(frozen=True)
class Conseil:
    anglais: str
    francais: str


# §5.5 — Conseils pour les styles (consignes de jeu)
CONSEILS_STYLE: tuple[Conseil, ...] = (
    Conseil(
        "Keep the style short (a few words): emotion, attitude, pace, volume, pitch.",
        "Style court (quelques mots) : émotion, attitude, rythme, volume, hauteur.",
    ),
    Conseil(
        "Try without any style first: most generations don't need one.",
        "Teste d'abord sans style : la plupart des générations n'en ont pas besoin.",
    ),
    Conseil(
        "For a consistent mood, reuse exactly the same instruction from one line to the next.",
        "Pour une ambiance constante, réutilise exactement la même consigne d'une réplique à l'autre.",
    ),
    Conseil(
        "If the emotion changes mid-text, split it into lines, each with its own short style.",
        "Si l'émotion change en cours de texte, découpe en répliques avec un style chacune.",
    ),
    Conseil(
        "No permanent traits in the style (age, gender, name, accent): they belong to the voice.",
        "Pas de traits permanents dans le style (âge, genre, nom, accent) : ils vont dans la voix.",
    ),
    Conseil(
        'Avoid meta-instructions such as "keep the same voice": they increase drift.',
        "Évite les méta-consignes du type « garde la même voix » : elles augmentent la dérive.",
    ),
    Conseil(
        "One-off events (laugh, sigh, pause) go in the text as tags, not in the style.",
        "Les événements ponctuels (rire, soupir, pause) se mettent en balises dans le texte, pas dans le style.",
    ),
)

# §5.4 bis — Conseils pour Voice Design (description de voix)
CONSEILS_VOIX: tuple[Conseil, ...] = (
    Conseil(
        "Describe permanent traits: age, gender, timbre, vocal texture, regional accent.",
        "Décris les traits permanents : âge, genre, timbre, texture vocale, accent régional.",
    ),
    Conseil("Keep it short and precise: 1 to 2 sentences.", "Description courte et précise : 1 à 2 phrases."),
    Conseil(
        "Avoid long paragraphs and contradictory descriptions.",
        "Évite les paragraphes longs et les descriptions contradictoires.",
    ),
    Conseil(
        "Emotion and delivery are set later with short styles, not in the description.",
        "L'émotion et le jeu se règlent ensuite avec des styles courts, pas dans la description.",
    ),
)

MOTS_MAX_STYLE = 10
MOTS_MAX_DESCRIPTION = 40
PHRASES_MAX_DESCRIPTION = 2

_TRAITS_PERMANENTS = (
    r"\d+\s*ans\b", r"\bans\b", r"\bhomme\b", r"\bfemme\b", r"\bgar[cç]on\b", r"\bfille\b", r"\baccent\b",
    r"\bvoix grave\b", r"\bvoix aigu[eë]\b", r"\byears? old\b", r"\bman\b", r"\bwoman\b", r"\bmale\b",
    r"\bfemale\b", r"\bboy\b", r"\bgirl\b", r"\bdeep voice\b", r"\bhigh[- ]pitched voice\b",
)
_META_CONSIGNES = (
    r"m[êe]me voix", r"garde[rz]? (le|la|son|sa) (timbre|voix)", r"ne change pas", r"same voice",
    r"keep the (same )?(voice|timbre|tone)", r"don'?t change", r"consistent voice",
)
# Sons ponctuels écrits dans un style → balise proposée à la place. (« Chuchoté » n'en fait pas
# partie : chuchoter tout le texte est une vraie manière de dire, donc un style valable.)
_SONS_PONCTUELS = {
    "rire": "laugh", "rit": "laugh", "rigole": "giggle", "soupir": "sigh", "soupire": "sigh",
    "pause": "short pause", "tousse": "cough", "toux": "cough", "halet": "pant",
    "laugh": "laugh", "sigh": "sigh", "gasp": "gasp", "cough": "cough",
}


# Mots courants d'un style écrit en français (et qui ne sont pas de l'anglais).
_MOTS_FRANCAIS = frozenset(
    """et avec très un une des les du peu voix débit rapide lent lente doux douce chaleureux chaleureuse
    enthousiaste sourire souriant souriante chuchoté chuchotée rythme joyeux joyeuse triste énergique posé
    posée dynamique sérieux sérieuse complice amusé amusée excité excitée fort forte comme pour ému émue
    énervé énervée rassurant rassurante confiant confiante détendu détendue mystérieux mystérieuse enjoué
    enjouée murmuré murmurée naturel naturelle percutant percutante légèrement plutôt""".split()
)
_ACCENTS = re.compile(r"[éèêëàâùûüôîïç]", re.IGNORECASE)


@dataclass(frozen=True)
class Avertissement:
    message: str
    balise_suggeree: str | None = None  # pour proposer « convertir en balise »
    en_francais: bool = False  # pour proposer « Traduire en anglais »


def semble_francais(texte: str) -> bool:
    """Le texte a-t-il l'air écrit en français ? (accents, ou mots français courants)"""
    if _ACCENTS.search(texte):
        return True
    return any(mot.lower() in _MOTS_FRANCAIS for mot in _mots(texte))


def _mots(texte: str) -> list[str]:
    return re.findall(r"[\w'’-]+", texte)


def verifier_style(texte: str) -> list[Avertissement]:
    """Vérifications en direct du champ style (§5.5), non bloquantes."""
    texte_min = texte.lower()
    avertissements: list[Avertissement] = []
    if semble_francais(texte):
        avertissements.append(
            Avertissement(
                "Style en français : Google conseille l'anglais. Clique sur « Traduire en anglais ».",
                en_francais=True,
            )
        )
    if len(_mots(texte)) > MOTS_MAX_STYLE:
        avertissements.append(Avertissement(f"Style long (plus de {MOTS_MAX_STYLE} mots) : un style court marche mieux."))
    if any(re.search(motif, texte_min) for motif in _TRAITS_PERMANENTS):
        avertissements.append(
            Avertissement("Trait permanent détecté (âge, genre, accent…) : il se règle dans la voix, pas dans le style.")
        )
    if any(re.search(motif, texte_min) for motif in _META_CONSIGNES):
        avertissements.append(
            Avertissement("Méta-consigne détectée (« même voix »…) : elle augmente la dérive, mieux vaut l'enlever.")
        )
    for mot, balise in _SONS_PONCTUELS.items():
        if re.search(rf"\b{mot}", texte_min) and balise in TOUTES:
            avertissements.append(
                Avertissement(
                    f"« {mot} » : un son ponctuel se met plutôt en balise dans le texte.", balise_suggeree=balise
                )
            )
            break
    return avertissements


def verifier_description_voix(texte: str) -> list[Avertissement]:
    """Vérifications en direct de la description Voice Design (§5.4 bis)."""
    avertissements = []
    if semble_francais(texte):
        avertissements.append(
            Avertissement(
                "Description en français : Google conseille l'anglais. Clique sur « Traduire en anglais ».",
                en_francais=True,
            )
        )
    phrases = [p for p in re.split(r"[.!?]+", texte) if p.strip()]
    if len(phrases) > PHRASES_MAX_DESCRIPTION or len(_mots(texte)) > MOTS_MAX_DESCRIPTION:
        avertissements.append(
            Avertissement(
                f"Description longue (plus de {PHRASES_MAX_DESCRIPTION} phrases ou ~{MOTS_MAX_DESCRIPTION} mots) : "
                "Google conseille 1 à 2 phrases."
            )
        )
    return avertissements
