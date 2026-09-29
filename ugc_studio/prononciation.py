"""Dictionnaire de prononciation (§5.2) : « mot écrit → façon de le prononcer ».

L'API n'a pas de réglage dédié aux noms de marque. L'app remplace donc, **uniquement dans le texte
envoyé au TTS**, chaque mot du dictionnaire par sa prononciation (ex. « Glowzy » → « Glo-zi »).
Le script affiché et les sous-titres gardent l'orthographe correcte.

Deux dictionnaires : un global (tous les projets) et un par projet ; celui du projet l'emporte.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .stockage import ecrire_json, lire_json


@dataclass
class Prononciation:
    mot: str  # tel qu'écrit dans le script (ex. « Glowzy »)
    dit: str  # tel qu'il doit être prononcé (ex. « Glo-zi »)


def nettoyer(entrees: list[Prononciation]) -> list[Prononciation]:
    """Retire les entrées vides et les doublons (le dernier gagne)."""
    par_mot: dict[str, Prononciation] = {}
    for entree in entrees:
        mot, dit = " ".join(entree.mot.split()), " ".join(entree.dit.split())
        if mot and dit:
            par_mot[mot.casefold()] = Prononciation(mot, dit)
    return list(par_mot.values())


def appliquer(texte: str, entrees: list[Prononciation]) -> str:
    """Remplace les mots du dictionnaire (mots entiers, sans tenir compte des majuscules).

    Les balises « <laugh> » ne sont jamais modifiées. Les mots les plus longs passent en premier,
    pour que « Glowzy Pro » l'emporte sur « Glowzy ».
    """
    entrees = sorted(nettoyer(entrees), key=lambda e: len(e.mot), reverse=True)
    if not entrees or not texte:
        return texte
    motif = re.compile(
        r"(<[^<>]*>)|(?<!\w)(" + "|".join(re.escape(e.mot) for e in entrees) + r")(?!\w)",
        re.IGNORECASE,
    )
    remplacements = {e.mot.casefold(): e.dit for e in entrees}

    def remplacer(trouve: re.Match) -> str:
        if trouve.group(1):
            return trouve.group(1)  # balise : inchangée
        return remplacements.get(trouve.group(2).casefold(), trouve.group(2))

    return motif.sub(remplacer, texte)


def fusionner(globales: list[Prononciation], projet: list[Prononciation]) -> list[Prononciation]:
    """Dictionnaire global + dictionnaire du projet (le projet l'emporte pour un même mot)."""
    return nettoyer([*globales, *projet])


class DictionnaireGlobal:
    """Dictionnaire commun à tous les projets, dans %APPDATA%\\UGC Studio\\prononciations.json."""

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        brutes = donnees.get("entrees", []) if isinstance(donnees, dict) else []
        self.entrees = nettoyer(
            [Prononciation(str(e.get("mot", "")), str(e.get("dit", ""))) for e in brutes if isinstance(e, dict)]
        )

    def enregistrer(self, entrees: list[Prononciation]) -> None:
        self.entrees = nettoyer(entrees)
        ecrire_json(self._chemin, {"version_format": 1, "entrees": [asdict(e) for e in self.entrees]})


def depuis_liste(brutes: list) -> list[Prononciation]:
    return nettoyer(
        [Prononciation(str(e.get("mot", "")), str(e.get("dit", ""))) for e in brutes or [] if isinstance(e, dict)]
    )
