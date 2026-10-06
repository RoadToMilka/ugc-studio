"""Préréglages Topaz enregistrés (V4, lot 3) : `prereglages_topaz.json`, dans le dossier de données de
l'app. Chacun garde la commande de Topaz comprise (sans les chemins de la vidéo d'origine) et son nom."""

from __future__ import annotations

from pathlib import Path

from ..stockage import ecrire_json, lire_json
from .commande import Prereglage

FICHIER = "prereglages_topaz.json"


class PrereglagesTopaz:
    def __init__(self, chemin: Path):
        self.chemin = chemin

    def liste(self) -> list[Prereglage]:
        donnees = lire_json(self.chemin, {})
        elements = donnees.get("prereglages", []) if isinstance(donnees, dict) else []
        return [p for p in (Prereglage.depuis(element) for element in elements if isinstance(element, dict)) if p is not None]

    def noms(self) -> list[str]:
        return [prereglage.nom for prereglage in self.liste()]

    def trouver(self, nom: str) -> Prereglage | None:
        return next((p for p in self.liste() if p.nom == nom), None)

    def _ecrire(self, liste: list[Prereglage]) -> None:
        ecrire_json(self.chemin, {"version": 1, "prereglages": [p.en_donnees() for p in liste]})

    def enregistrer(self, prereglage: Prereglage) -> None:
        """Ajoute le préréglage (ou remplace celui du même nom, à sa place)."""
        liste = self.liste()
        for rang, existant in enumerate(liste):
            if existant.nom == prereglage.nom:
                liste[rang] = prereglage
                break
        else:
            liste.append(prereglage)
        self._ecrire(liste)

    def supprimer(self, nom: str) -> None:
        self._ecrire([p for p in self.liste() if p.nom != nom])
