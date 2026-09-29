"""Adaptateur Google (API Gemini).

Référence : API REST « generativelanguage.googleapis.com », version v1beta, telle qu'utilisée
par le SDK officiel google-genai (v2.25, septembre 2026). La clé est envoyée dans l'en-tête
« x-goog-api-key » (jamais dans l'adresse, pour qu'elle n'apparaisse dans aucun historique).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .base import Adaptateur, ErreurFournisseur, InfoModele
from .http import ReponseHttp, requete

URL_API = "https://generativelanguage.googleapis.com/v1beta"
TAILLE_PAGE_MODELES = 1000


class AdaptateurGoogle(Adaptateur):
    identifiant = "google"
    nom = "Google (Gemini)"
    aide_cle = "Crée ta clé dans Google AI Studio (menu « Get API key »), puis colle-la ici."
    adresse_cles = "https://aistudio.google.com/apikey"

    def __init__(self, cle: str, url_api: str = URL_API):
        super().__init__(cle)
        self._url_api = url_api.rstrip("/")

    # --- Appels ------------------------------------------------------------------------------

    def _appeler(
        self,
        methode: str,
        chemin: str,
        parametres: dict[str, Any] | None = None,
        corps: Any = None,
        delai: float = 60,
    ) -> Any:
        url = f"{self._url_api}/{chemin}"
        if parametres:
            url += "?" + urlencode(parametres)
        reponse = requete(methode, url, entetes={"x-goog-api-key": self._cle}, corps_json=corps, delai=delai)
        if reponse.statut >= 400:
            raise traduire_erreur(reponse)
        try:
            return reponse.json()
        except ValueError as erreur:
            raise ErreurFournisseur(
                "Réponse de Google illisible. Réessaie dans un instant.", "reponse_illisible", str(erreur)
            ) from erreur

    # --- Fonctions communes à tous les adaptateurs -------------------------------------------

    def lister_modeles(self) -> list[InfoModele]:
        modeles: list[InfoModele] = []
        jeton: str | None = None
        while True:
            parametres: dict[str, Any] = {"pageSize": TAILLE_PAGE_MODELES}
            if jeton:
                parametres["pageToken"] = jeton
            donnees = self._appeler("GET", "models", parametres, delai=30)
            for modele in donnees.get("models", []):
                identifiant = str(modele.get("name", "")).removeprefix("models/")
                if not identifiant:
                    continue
                modeles.append(
                    InfoModele(
                        identifiant=identifiant,
                        nom=modele.get("displayName") or identifiant,
                        description=modele.get("description", ""),
                        methodes=tuple(modele.get("supportedGenerationMethods", [])),
                        limite_entree=modele.get("inputTokenLimit"),
                        limite_sortie=modele.get("outputTokenLimit"),
                    )
                )
            jeton = donnees.get("nextPageToken")
            if not jeton:
                return modeles


def traduire_erreur(reponse: ReponseHttp) -> ErreurFournisseur:
    """Transforme une réponse d'erreur de Google en message clair.

    Format des erreurs Google : {"error": {"code": 400, "message": "…", "status": "INVALID_ARGUMENT",
    "details": [{"reason": "API_KEY_INVALID", …}]}}
    """
    try:
        erreur = reponse.json().get("error", {}) or {}
    except (ValueError, AttributeError):
        erreur = {}
    statut = str(erreur.get("status", ""))
    message_google = str(erreur.get("message", "")).strip()
    raisons = {str(d.get("reason", "")) for d in erreur.get("details", []) if isinstance(d, dict)}
    detail = f"HTTP {reponse.statut} {statut} {message_google} {sorted(raisons)}".strip()

    if "API_KEY_INVALID" in raisons or "api key not valid" in message_google.lower():
        return ErreurFournisseur(
            "Google refuse cette clé : elle n'est pas valide. Vérifie qu'elle a été copiée en entier.",
            "cle_invalide",
            detail,
        )
    if "API_KEY_SERVICE_BLOCKED" in raisons or reponse.statut == 403 or statut == "PERMISSION_DENIED":
        return ErreurFournisseur(
            "Cette clé n'a pas accès à l'API Gemini. Vérifie dans Google AI Studio que la clé "
            "appartient bien à un projet où l'API Gemini est activée.",
            "acces_refuse",
            detail,
        )
    if reponse.statut == 429 or statut == "RESOURCE_EXHAUSTED":
        return ErreurFournisseur(
            "Limite d'utilisation atteinte chez Google (quota ou trop de demandes rapprochées). "
            "Réessaie dans quelques minutes, ou vérifie la facturation du projet Google.",
            "quota",
            detail,
        )
    if reponse.statut >= 500:
        return ErreurFournisseur(
            "Google rencontre un problème temporaire. Réessaie dans un instant.", "serveur", detail
        )
    suite = f" : {message_google}" if message_google else "."
    return ErreurFournisseur(f"Google a refusé la demande (code {reponse.statut}){suite}", "requete", detail)
