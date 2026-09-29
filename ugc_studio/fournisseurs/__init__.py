"""Fournisseurs d'IA (§3.4).

Chaque fournisseur est géré par un « adaptateur » : un module isolé qui sait parler à son API.
Le reste de l'app ne connaît que les fonctions communes (tester_cle, lister_modeles, …) :
ajouter un fournisseur = écrire un nouvel adaptateur et l'inscrire ci-dessous.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Adaptateur
from .google import AdaptateurGoogle


@dataclass(frozen=True)
class FournisseurPrevu:
    """Fournisseur annoncé dans le cahier des charges mais pas encore disponible."""

    identifiant: str
    nom: str
    version: str


# Fournisseurs utilisables (V1 : Google uniquement).
ADAPTATEURS: dict[str, type[Adaptateur]] = {
    AdaptateurGoogle.identifiant: AdaptateurGoogle,
}

# Affichés dans la liste, mais grisés (§3.4 : prévus ensuite).
FOURNISSEURS_PREVUS = (
    FournisseurPrevu("openai", "OpenAI", "V4"),
    FournisseurPrevu("elevenlabs", "ElevenLabs", "V4"),
    FournisseurPrevu("anthropic", "Anthropic (texte uniquement)", "V4"),
)


def creer_adaptateur(fournisseur: str, cle: str) -> Adaptateur:
    """Adaptateur prêt à l'emploi pour ce fournisseur, avec cette clé."""
    return ADAPTATEURS[fournisseur](cle)


def nom_fournisseur(identifiant: str) -> str:
    if identifiant in ADAPTATEURS:
        return ADAPTATEURS[identifiant].nom
    for prevu in FOURNISSEURS_PREVUS:
        if prevu.identifiant == identifiant:
            return prevu.nom
    return identifiant
