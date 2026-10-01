"""Types communs pour la génération de texte : traduction d'un style en anglais (§5.5), et module
Script (V2, §3.1) : lecture d'une page produit, accroches, écriture et relecture d'un script."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequeteTexte:
    modele: str
    texte: str  # demande envoyée au modèle
    consigne_systeme: str = ""  # rôle et règles donnés au modèle (« tu traduis… »)
    reflexion: str = "low"  # niveau de « réflexion » du modèle : plus bas = plus rapide et moins cher
    # « Réponse structurée » : le modèle répond par un objet JSON conforme à ce schéma (sous-ensemble
    # de JSON Schema : type, properties, required, items, enum, description, minItems, maxItems…).
    # L'app lit alors chaque case sans risque d'erreur de format.
    schema: dict | None = None
    # Outil « URL context » : le modèle lit lui-même les pages web dont l'adresse est dans la demande.
    lire_adresses: bool = False
    delai: float | None = None  # attente maximale en secondes (None : celle de l'adaptateur)


@dataclass(frozen=True)
class AdresseLue:
    """Une page lue par le modèle avec l'outil « URL context », et le résultat de la lecture."""

    adresse: str
    statut: str  # « success », « error », « paywall » (page payante), « unsafe » (jugée dangereuse)

    @property
    def reussie(self) -> bool:
        return self.statut == "success"


@dataclass
class ResultatTexte:
    texte: str
    tokens_entree: int = 0  # pages lues comprises (facturées comme du texte envoyé)
    tokens_sortie: int = 0  # réflexion comprise (facturée comme de la sortie)
    details: dict = field(default_factory=dict)
    adresses_lues: list[AdresseLue] = field(default_factory=list)
