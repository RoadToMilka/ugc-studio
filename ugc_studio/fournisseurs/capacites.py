"""Tableau des capacités et des prix des modèles (§3.4, §4.2).

Chaque modèle connu est décrit par ce qu'il sait faire (voix, balises, transcription mot par
mot…). L'app croise « modèles accessibles avec tes clés » × « capacités demandées par la tâche »
pour ne proposer que les modèles compatibles.

Les prix viennent de la page officielle des tarifs Google (ADRESSE_TARIFS_GOOGLE) : tarif
« Standard » du niveau payant, vérifié le PRIX_VERIFIES_LE. Google annonce parfois un changement
de prix à une date donnée : chaque modèle a donc une liste de tarifs datés, et l'app applique
automatiquement celui qui est en vigueur le jour de l'appel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

ADRESSE_TARIFS_GOOGLE = "https://ai.google.dev/gemini-api/docs/pricing?hl=fr"
PRIX_VERIFIES_LE = date(2026, 9, 30)
HAUSSE_GOOGLE_2027 = date(2027, 1, 1)  # prix des modèles 3.8 doublés « à partir du 1er janvier 2027 »

# Page des tarifs : Google compte 25 tokens par seconde d'audio (en entrée comme en sortie :
# « 0,00225 $ pour 10 s d'audio » à 9 $ le million = 250 tokens pour 10 s), et environ
# 175 tokens de texte par minute de parole transcrite.
TOKENS_AUDIO_PAR_SECONDE = 25
TOKENS_TEXTE_PAR_MINUTE_TRANSCRITE = 175
# Texte d'une minute de voix off : ≈ 160 mots ≈ 1 000 caractères ≈ 250 tokens.
TOKENS_TEXTE_PAR_MINUTE_DE_VOIX = 250
# Traduction d'un style : consigne + quelques mots envoyés, quelques mots (et un peu de réflexion) reçus.
TOKENS_TRADUCTION_ENTREE = 150
TOKENS_TRADUCTION_SORTIE = 60


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
class Tarif:
    """Prix en dollars par million de tokens, en vigueur à partir d'une date."""

    entree: Decimal | None  # ce que l'on envoie (texte du script, audio à transcrire…)
    sortie: Decimal | None  # ce que le modèle produit (audio, texte), réflexion comprise
    depuis: date | None = None  # None : en vigueur depuis toujours


@dataclass(frozen=True)
class Reference:
    """Consommation typique, pour donner un ordre de grandeur parlant (ex. « par minute de voix »)."""

    tokens_entree: int
    tokens_sortie: int
    libelle: str


@dataclass(frozen=True)
class ModeleConnu:
    identifiant: str
    fournisseur: str
    nom: str
    capacites: frozenset[Capacite]
    # Prix par défaut (modifiables dans Réglages → Modèles et prix), du plus ancien au plus récent.
    tarifs: tuple[Tarif, ...]
    entree: str = "texte"  # nature de ce que l'on envoie
    sortie: str = "audio"  # nature de ce que le modèle produit
    reference: Reference | None = None
    note: str = ""
    # Modèle principal : toujours listé dans Réglages → Modèles et prix. Les autres (anciennes
    # versions, aperçus) n'y apparaissent que s'ils sont accessibles avec une de tes clés.
    principal: bool = True

    def tarif(self, le: date) -> Tarif:
        """Tarif en vigueur à cette date."""
        en_vigueur = self.tarifs[0]
        for tarif in self.tarifs:
            if tarif.depuis is None or tarif.depuis <= le:
                en_vigueur = tarif
        return en_vigueur

    def prochain_tarif(self, le: date) -> Tarif | None:
        """Prochain changement de prix annoncé après cette date, s'il y en a un."""
        return next((t for t in self.tarifs if t.depuis is not None and t.depuis > le), None)


_MINUTE_DE_VOIX = Reference(TOKENS_TEXTE_PAR_MINUTE_DE_VOIX, 60 * TOKENS_AUDIO_PAR_SECONDE, "par minute de voix")
_MINUTE_TRANSCRITE = Reference(
    60 * TOKENS_AUDIO_PAR_SECONDE, TOKENS_TEXTE_PAR_MINUTE_TRANSCRITE, "par minute transcrite"
)
_TRADUCTION = Reference(TOKENS_TRADUCTION_ENTREE, TOKENS_TRADUCTION_SORTIE, "par style traduit")

# Prix vérifiés sur la page officielle des tarifs Google le PRIX_VERIFIES_LE (§4.2).
MODELES_CONNUS: tuple[ModeleConnu, ...] = (
    ModeleConnu(
        "gemini-3.8-flash-tts",
        "google",
        "Gemini 3.8 Flash TTS",
        _VOIX,
        (
            Tarif(Decimal("0.50"), Decimal("9.00")),
            Tarif(Decimal("1.00"), Decimal("18.00"), HAUSSE_GOOGLE_2027),
        ),
        reference=_MINUTE_DE_VOIX,
        note="Voix par défaut : qualité et jeu d'acteur maximum.",
    ),
    ModeleConnu(
        "gemini-3.8-flash-lite-tts",
        "google",
        "Gemini 3.8 Flash-Lite TTS",
        _VOIX,
        (
            Tarif(Decimal("0.50"), Decimal("6.00")),
            Tarif(Decimal("1.00"), Decimal("12.00"), HAUSSE_GOOGLE_2027),
        ),
        reference=_MINUTE_DE_VOIX,
        note="Plus rapide, moins cher.",
    ),
    ModeleConnu(
        "gemini-3.5-transcribe",
        "google",
        "Gemini 3.5 Transcribe",
        frozenset({Capacite.STT, Capacite.STT_MOTS_HORODATES, Capacite.STT_VOCABULAIRE}),
        (Tarif(Decimal("2.00"), Decimal("12.00")),),
        entree="audio",
        sortie="texte",
        reference=_MINUTE_TRANSCRITE,
        note="Transcription mot par mot (sous-titres).",
    ),
    ModeleConnu(
        "gemini-3.8-flash",
        "google",
        "Gemini 3.8 Flash",
        frozenset({Capacite.TEXTE}),
        (
            Tarif(Decimal("0.75"), Decimal("3.75")),
            Tarif(Decimal("1.50"), Decimal("7.50"), HAUSSE_GOOGLE_2027),
        ),
        sortie="texte",
        reference=_TRADUCTION,
        note="Modèle de texte : traduit tes styles en anglais.",
    ),
    # Anciennes générations de voix (documentation Google : ni Voice Design ni balises).
    # Listées seulement si elles sont accessibles avec une clé.
    ModeleConnu(
        "gemini-3.1-flash-tts-preview",
        "google",
        "Gemini 3.1 Flash TTS (aperçu)",
        frozenset({Capacite.TTS, Capacite.TTS_MULTI_VOIX}),
        (Tarif(Decimal("1.00"), Decimal("20.00")),),
        reference=_MINUTE_DE_VOIX,
        note="Ancienne génération : plus chère, sans balises ni Voice Design.",
        principal=False,
    ),
    ModeleConnu(
        "gemini-2.5-pro-preview-tts",
        "google",
        "Gemini 2.5 Pro TTS (aperçu)",
        frozenset({Capacite.TTS, Capacite.TTS_MULTI_VOIX}),
        (Tarif(Decimal("1.00"), Decimal("20.00")),),
        reference=_MINUTE_DE_VOIX,
        note="Ancienne génération : plus chère, sans balises ni Voice Design.",
        principal=False,
    ),
    ModeleConnu(
        "gemini-2.5-flash-preview-tts",
        "google",
        "Gemini 2.5 Flash TTS (aperçu)",
        frozenset({Capacite.TTS, Capacite.TTS_MULTI_VOIX}),
        (Tarif(Decimal("0.50"), Decimal("10.00")),),
        reference=_MINUTE_DE_VOIX,
        note="Ancienne génération : sans balises ni Voice Design.",
        principal=False,
    ),
)
_RANG = {modele.identifiant: rang for rang, modele in enumerate(MODELES_CONNUS)}


def modele_connu(identifiant: str) -> ModeleConnu | None:
    return next((m for m in MODELES_CONNUS if m.identifiant == identifiant), None)


def deviner_capacites(identifiant: str) -> frozenset[Capacite]:
    """Capacités probables d'un modèle inconnu du catalogue, d'après son nom.

    Permet de proposer automatiquement un nouveau modèle (ex. une future version « …-tts »).
    Les modèles « Live » (conversation en temps réel, ex. « gemini-3.5-transcribe-live ») passent
    par une autre API que celle de l'app : ils ne sont jamais proposés.
    """
    connu = modele_connu(identifiant)
    if connu is not None:
        return connu.capacites
    nom = identifiant.lower()
    if "-live" in nom or "native-audio" in nom:
        return frozenset()
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
    # Les compatibles d'abord, dans l'ordre du catalogue (le modèle conseillé en premier).
    return sorted(resultats, key=lambda c: (not c.compatible, _RANG.get(c.identifiant, len(_RANG)), c.identifiant))
