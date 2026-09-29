"""Ce que tout adaptateur de fournisseur sait faire (§3.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from ..journal import declarer_secret


class ErreurFournisseur(Exception):
    """Problème lors d'un appel à un fournisseur.

    `message` : phrase claire en français, affichée à l'utilisateur.
    `code` : catégorie (« cle_invalide », « acces_refuse », « quota », « reseau », « serveur »…).
    `detail` : texte technique d'origine, écrit dans le journal d'erreurs.
    """

    def __init__(self, message: str, code: str = "inconnu", detail: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class InfoModele:
    """Un modèle accessible avec une clé, tel que le fournisseur le décrit."""

    identifiant: str  # ex. « gemini-3.8-flash-tts »
    nom: str = ""
    description: str = ""
    methodes: tuple[str, ...] = ()
    limite_entree: int | None = None
    limite_sortie: int | None = None


@dataclass
class ResultatTest:
    ok: bool
    message: str
    modeles: list[InfoModele] = field(default_factory=list)
    code: str = ""


class Adaptateur(ABC):
    identifiant: ClassVar[str]  # ex. « google »
    nom: ClassVar[str]  # ex. « Google (Gemini) »
    aide_cle: ClassVar[str] = ""  # où obtenir une clé
    adresse_cles: ClassVar[str] = ""  # page web de création des clés

    def __init__(self, cle: str):
        self._cle = cle.strip()
        declarer_secret(self._cle)  # la clé ne pourra jamais apparaître dans le journal

    @abstractmethod
    def lister_modeles(self) -> list[InfoModele]:
        """Modèles accessibles avec cette clé."""

    def tester_cle(self) -> ResultatTest:
        """La clé fonctionne-t-elle ? (Demander la liste des modèles est gratuit.)"""
        try:
            modeles = self.lister_modeles()
        except ErreurFournisseur as erreur:
            return ResultatTest(False, erreur.message, code=erreur.code)
        return ResultatTest(True, f"Clé valide — {len(modeles)} modèles accessibles.", modeles)
