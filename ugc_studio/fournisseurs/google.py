"""Adaptateur Google (API Gemini).

Références (septembre 2026) : API REST « generativelanguage.googleapis.com » version v1beta,
SDK officiel google-genai 2.25 et guides officiels du « Gemini API Cookbook »
(Get_started_TTS, Get_Started_Voices, Get_started_transcribe).

- Liste des modèles : GET /v1beta/models
- Voix (Gemini 3.8 TTS) : POST /v1beta/interactions (API « Interactions »), avec le texte dans
  `input`, la consigne de style dans une annotation `speech_metadata` et la voix dans
  `generation_config.speech_config`. La réponse contient l'audio en WAV (base64).
- Texte (ex. Gemini 3.8 Flash) : même API ; la réponse contient des étapes (`steps`) dont la
  dernière « model_output » porte le texte. Niveau de réflexion dans
  `generation_config.thinking_level` (Gemini 3.8 Flash : « low », « medium » ou « high »).

La clé est envoyée dans l'en-tête « x-goog-api-key » (jamais dans l'adresse, pour qu'elle
n'apparaisse dans aucun historique).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

from ..audio import FREQUENCE_TTS, duree_wav, en_wav
from .base import Adaptateur, ErreurFournisseur, InfoModele
from .http import ReponseHttp, requete
from .texte import RequeteTexte, ResultatTexte
from .voix import RequeteVoix, ResultatVoix

journal = logging.getLogger(__name__)

URL_API = "https://generativelanguage.googleapis.com/v1beta"
TAILLE_PAGE_MODELES = 1000
DELAI_GENERATION = 300  # secondes : une longue voix off peut prendre du temps
DELAI_TEXTE = 60  # secondes
ESSAIS_SI_SURCHARGE = 2
PAUSE_AVANT_NOUVEL_ESSAI = 3  # secondes
STATUTS_EN_ECHEC = {"failed", "cancelled", "incomplete", "budget_exceeded"}


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

    # --- Voix (TTS) ----------------------------------------------------------------------------

    def generer_voix(self, requete_voix: RequeteVoix) -> ResultatVoix:
        entrees = []
        for replique in requete_voix.repliques:
            element: dict[str, Any] = {"type": "text", "text": replique.texte}
            if replique.style.strip():
                element["annotations"] = [{"type": "speech_metadata", "style": replique.style.strip()}]
            entrees.append(element)
        corps = {
            "model": requete_voix.modele,
            "input": entrees,
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": requete_voix.voix}]},
        }
        return lire_resultat_voix(self._interaction(corps, DELAI_GENERATION))

    # --- Texte -----------------------------------------------------------------------------------

    def generer_texte(self, requete_texte: RequeteTexte) -> ResultatTexte:
        corps: dict[str, Any] = {
            "model": requete_texte.modele,
            "input": [{"type": "text", "text": requete_texte.texte}],
            "generation_config": {"thinking_level": requete_texte.reflexion},
        }
        if requete_texte.consigne_systeme:
            corps["system_instruction"] = requete_texte.consigne_systeme
        return lire_resultat_texte(self._interaction(corps, DELAI_TEXTE))

    def _interaction(self, corps: dict, delai: float) -> dict:
        """POST /interactions ; si Google est surchargé (erreur 5xx), un nouvel essai après une pause."""
        for essai in range(1, ESSAIS_SI_SURCHARGE + 1):
            try:
                return self._appeler("POST", "interactions", corps=corps, delai=delai)
            except ErreurFournisseur as erreur:
                if erreur.code != "serveur" or essai == ESSAIS_SI_SURCHARGE:
                    raise
                journal.warning("Google surchargé, nouvel essai dans %s s", PAUSE_AVANT_NOUVEL_ESSAI)
                time.sleep(PAUSE_AVANT_NOUVEL_ESSAI)
        raise AssertionError("inaccessible")


def trouver_audio(donnees: dict) -> dict | None:
    """Bloc audio de la réponse : `output_audio`, ou le dernier audio des étapes (`steps`) du modèle."""
    if isinstance(donnees.get("output_audio"), dict):
        return donnees["output_audio"]
    for etape in reversed(donnees.get("steps") or []):
        if not isinstance(etape, dict) or etape.get("type") not in (None, "model_output"):
            continue
        for element in reversed(etape.get("content") or []):
            if isinstance(element, dict) and element.get("type") == "audio":
                return element
    return None


def _verifier_statut(donnees: dict, quoi: str) -> None:
    statut = donnees.get("status")
    if statut in STATUTS_EN_ECHEC:
        messages = "; ".join(
            str(e.get("message", "")) for e in donnees.get("errors") or [] if isinstance(e, dict)
        )
        raise ErreurFournisseur(
            f"Google n'a pas pu générer {quoi} (statut « {statut} »)" + (f" : {messages}" if messages else "."),
            "generation",
            json.dumps(donnees, ensure_ascii=False)[:1000],
        )


def _tokens(donnees: dict) -> tuple[int, int]:
    """(tokens d'entrée, tokens de sortie) ; la « réflexion » est facturée comme de la sortie."""
    usage = donnees.get("usage") or {}
    entree = int(usage.get("total_input_tokens") or 0)
    sortie = int(usage.get("total_output_tokens") or 0) + int(usage.get("total_thought_tokens") or 0)
    return entree, sortie


def trouver_texte(donnees: dict) -> str:
    """Texte de la réponse : les derniers blocs « text » des étapes « model_output » (les étapes de
    réflexion sont ignorées), comme le fait le SDK officiel pour `output_text`."""
    if isinstance(donnees.get("output_text"), str):
        return donnees["output_text"]
    morceaux: list[str] = []
    for etape in reversed(donnees.get("steps") or []):
        if not isinstance(etape, dict):
            continue
        if etape.get("type") == "user_input":
            break
        if etape.get("type") not in (None, "model_output"):
            if morceaux:
                break
            continue
        for element in reversed(etape.get("content") or []):
            if isinstance(element, dict) and element.get("type") == "text":
                morceaux.append(str(element.get("text") or ""))
            elif morceaux:
                return "".join(reversed(morceaux))
    return "".join(reversed(morceaux))


def lire_resultat_texte(donnees: dict) -> ResultatTexte:
    _verifier_statut(donnees, "le texte")
    texte = trouver_texte(donnees).strip()
    if not texte:
        raise ErreurFournisseur(
            "Google n'a renvoyé aucun texte. Réessaie dans un instant.",
            "sans_texte",
            json.dumps({k: v for k, v in donnees.items() if k != "input"}, ensure_ascii=False)[:1000],
        )
    entree, sortie = _tokens(donnees)
    return ResultatTexte(texte, entree, sortie, {"statut": donnees.get("status"), "usage": donnees.get("usage") or {}})


def lire_resultat_voix(donnees: dict) -> ResultatVoix:
    """Réponse de l'API Interactions → audio WAV + nombres de tokens (pour le coût)."""
    _verifier_statut(donnees, "la voix")
    statut = donnees.get("status")
    audio = trouver_audio(donnees)
    if not audio or not audio.get("data"):
        raise ErreurFournisseur(
            "Google n'a renvoyé aucun audio. Vérifie que le texte n'est pas vide, puis réessaie.",
            "sans_audio",
            json.dumps({k: v for k, v in donnees.items() if k != "input"}, ensure_ascii=False)[:1000],
        )
    try:
        brut = base64.b64decode(audio["data"])
        wav = en_wav(brut, int(audio.get("sample_rate") or FREQUENCE_TTS))
        duree = duree_wav(wav)
    except (binascii.Error, ValueError, EOFError) as erreur:
        raise ErreurFournisseur("Audio reçu de Google illisible.", "audio_illisible", str(erreur)) from erreur
    tokens_entree, tokens_sortie = _tokens(donnees)
    return ResultatVoix(wav, duree, tokens_entree, tokens_sortie, {"statut": statut, "usage": donnees.get("usage") or {}})


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
