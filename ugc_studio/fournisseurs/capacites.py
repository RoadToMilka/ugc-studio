"""Tableau des capacités des modèles (§3.4).

Chaque modèle connu est décrit par ce qu'il sait faire (voix, balises, transcription mot par
mot…). L'app croise « modèles accessibles avec tes clés » × « capacités demandées par la tâche »
pour ne proposer que les modèles compatibles.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Capacite(StrEnum):
    TTS = "tts"
    TTS_BALISES = "tts_balises"
    TTS_VOICE_DESIGN = "tts_voice_design"
    TTS_MULTI_VOIX = "tts_multi_voix"
    STT = "stt"
    STT_MOTS_HORODATES = "stt_mots_horodates"
    STT_VOCABULAIRE = "stt_vocabulaire"
    TEXTE = "texte"


LIBELLES = {
    Capacite.TTS: "Voix",
    Capacite.TTS_BALISES: "Balises",
    Capacite.TTS_VOICE_DESIGN: "Voice Design",
    Capacite.TTS_MULTI_VOIX: "2 voix",
    Capacite.STT: "Transcription",
    Capacite.STT_MOTS_HORODATES: "Mots horodatés",
    Capacite.STT_VOCABULAIRE: "Vocabulaire",
    Capacite.TEXTE: "Texte",
}

_VOIX = frozenset(
    {Capacite.TTS, Capacite.TTS_BALISES, Capacite.TTS_VOICE_DESIGN, Capacite.TTS_MULTI_VOIX}
)


@dataclass(frozen=True)
class ModeleConnu:
    identifiant: str
    fournisseur: str
    nom: str
    capacites: frozenset[Capacite]
    # Prix par défaut, en dollars par million de tokens (modifiables dans Réglages → Modèles et prix).
    prix_entree: Decimal | None
    prix_sortie: Decimal | None
    note: str = ""


# Valeurs du cahier des charges (§4.2, §5.1, §6.1).
MODELES_CONNUS: tuple[ModeleConnu, ...] = (
    ModeleConnu(
        "gemini-3.8-flash-tts",
        "google",
        "Gemini 3.8 Flash TTS",
        _VOIX,
        Decimal("0.50"),
        Decimal("9.00"),
        note="Voix par défaut (qualité et jeu d'acteur maximum). Prix doublé à partir du 01/01/2027.",
    ),
    ModeleConnu(
        "gemini-3.8-flash-lite-tts",
        "google",
        "Gemini 3.8 Flash-Lite TTS",
        _VOIX,
        Decimal("0.50"),
        Decimal("6.00"),
        note="Plus rapide, moins cher.",
    ),
    ModeleConnu(
        "gemini-3.5-transcribe",
        "google",
        "Gemini 3.5 Transcribe",
        frozenset({Capacite.STT, Capacite.STT_MOTS_HORODATES, Capacite.STT_VOCABULAIRE}),
        None,
        None,
        note="Prix à renseigner d'après la page des tarifs Google.",
    ),
)


def modele_connu(identifiant: str) -> ModeleConnu | None:
    return next((m for m in MODELES_CONNUS if m.identifiant == identifiant), None)


def deviner_capacites(identifiant: str) -> frozenset[Capacite]:
    """Capacités probables d'un modèle inconnu du catalogue, d'après son nom.

    Permet de proposer automatiquement un nouveau modèle (ex. une future version « …-tts »).
    """
    connu = modele_connu(identifiant)
    if connu is not None:
        return connu.capacites
    nom = identifiant.lower()
    if nom.endswith("-tts") or "-tts-" in nom:
        return _VOIX
    if "transcribe" in nom:
        return frozenset({Capacite.STT, Capacite.STT_MOTS_HORODATES})
    return frozenset()


@dataclass(frozen=True)
class Choix:
    """Un modèle proposé pour une tâche."""

    identifiant: str
    nom: str
    compatible: bool
    raison: str = ""  # pourquoi il est incompatible (affiché à côté de son nom)


def modeles_pour(capacites_requises: set[Capacite], disponibles: set[str]) -> list[Choix]:
    """Modèles accessibles utiles pour une tâche, les compatibles en premier.

    Un modèle qui fait la bonne catégorie de tâche (ex. transcription) mais à qui il manque une
    capacité demandée (ex. horodatage par mot) est affiché, marqué incompatible.
    """
    familles = {c for c in capacites_requises if c in (Capacite.TTS, Capacite.STT, Capacite.TEXTE)}
    resultats: list[Choix] = []
    for identifiant in sorted(disponibles):
        capacites = deviner_capacites(identifiant)
        if not familles & capacites:
            continue
        connu = modele_connu(identifiant)
        manquantes = capacites_requises - capacites
        raison = ""
        if manquantes:
            if Capacite.STT_MOTS_HORODATES in manquantes:
                raison = "incompatible avec l'animation (pas d'horodatage par mot)"
            else:
                raison = "ne gère pas : " + ", ".join(LIBELLES[c] for c in sorted(manquantes))
        resultats.append(Choix(identifiant, connu.nom if connu else identifiant, not manquantes, raison))
    return sorted(resultats, key=lambda c: (not c.compatible, c.identifiant))
