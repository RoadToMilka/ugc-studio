"""Accès au fournisseur d'IA depuis l'interface : l'adaptateur de la clé par défaut (§4.1)."""

from __future__ import annotations

from ..connexions import ErreurConnexion
from ..fournisseurs import creer_adaptateur
from ..fournisseurs.base import Adaptateur
from ..services import Services

FOURNISSEUR = "google"  # V1 : Google uniquement


def adaptateur_par_defaut(services: Services, fournisseur: str = FOURNISSEUR) -> Adaptateur:
    """Adaptateur prêt à l'emploi avec la clé par défaut du fournisseur.

    Lève ErreurConnexion (message clair) si aucune clé n'est enregistrée.
    """
    connexion = services.connexions.connexion_par_defaut(fournisseur)
    if connexion is None:
        raise ErreurConnexion("Ajoute d'abord ta clé Google dans Réglages → Connexions API.")
    return creer_adaptateur(fournisseur, services.connexions.lire_cle(connexion.identifiant))


def message_erreur(erreur: Exception) -> str:
    """Phrase à afficher pour une erreur de fournisseur ou de clé."""
    message = getattr(erreur, "message", None)
    if isinstance(message, str) and message:
        return message
    if isinstance(erreur, ErreurConnexion):
        return str(erreur)
    return f"Erreur inattendue : {erreur}"
