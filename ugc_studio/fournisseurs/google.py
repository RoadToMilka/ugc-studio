"""Adaptateur Google (API Gemini).

Références (septembre 2026) : API REST « generativelanguage.googleapis.com » version v1beta,
SDK officiel google-genai 2.25 et guides officiels du « Gemini API Cookbook »
(Get_started_TTS, Get_Started_Voices, Get_started_transcribe).

- Liste des modèles : GET /v1beta/models
- Voix (Gemini 3.8 TTS) : POST /v1beta/interactions (API « Interactions »), avec le texte dans
  `input`, la consigne de style dans une annotation `speech_metadata` et la voix dans
  `generation_config.speech_config`. La réponse contient l'audio en WAV (base64).
  Avec `stream: true`, la réponse arrive en flux (server-sent events) : des événements
  « step.delta » portent chacun un morceau d'audio (PCM brut « audio/l16 », 24 kHz, mono,
  16 bits little-endian, en base64), puis « interaction.completed » donne le statut et les
  nombres de tokens (`usage`) ; le flux finit par « [DONE] ».
- Texte (ex. Gemini 3.8 Flash) : même API ; la réponse contient des étapes (`steps`) dont la
  dernière « model_output » porte le texte. Niveau de réflexion dans
  `generation_config.thinking_level` (Gemini 3.8 Flash : « low », « medium » ou « high »).
- Transcription (ex. Gemini 3.5 Transcribe) : l'audio est d'abord déposé avec l'API Files
  (téléversement « resumable » : POST /upload/v1beta/files, puis envoi des octets à l'adresse
  donnée dans l'en-tête `x-goog-upload-url` ; fichier gardé 48 h), puis POST /v1beta/interactions
  avec `{"type": "audio", "uri": …}` et `generation_config.transcription_config` :
  `language_codes` (vide = détection automatique) et `mode` (« smart », ou
  `{"type": "verbatim", "timestamp_granularities": ["word"], "diarization_mode": "speaker"}`).
  Les mots arrivent en annotations « word_info » du texte (`start_offset`, `end_offset` au format
  « 1.250s », `speaker`). Le fichier déposé est supprimé ensuite.
- Voix (API « Voices ») : GET /v1beta/voices (bibliothèque étendue, filtres `type`,
  `language_code`… répétables, pages de `page_size` voix), GET/DELETE /v1beta/voices/{id},
  POST /v1beta/voices pour Voice Design (`store: true`, `voice.type: "prompted"`,
  `voice.prompted.input` = description). La réponse d'une création contient l'identifiant
  `voice_…`, la date d'expiration et un extrait audio (`sample_audio`).

La clé est envoyée dans l'en-tête « x-goog-api-key » (jamais dans l'adresse, pour qu'elle
n'apparaisse dans aucun historique).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlencode

from ..audio import FREQUENCE_TTS, duree_wav, en_wav, lire_wav, wav_depuis_pcm
from .base import Adaptateur, ErreurFournisseur, InfoModele
from .http import EvenementSse, ReponseHttp, ouvrir_flux, requete
from .stt import FichierTeleverse, MotTranscrit, RequeteTranscription, ResultatTranscription
from .texte import RequeteTexte, ResultatTexte
from .voix import (
    RecepteurAudio,
    RequeteVoiceDesign,
    RequeteVoix,
    ResultatVoix,
    VoixBibliotheque,
    VoixCreee,
)

journal = logging.getLogger(__name__)

URL_API = "https://generativelanguage.googleapis.com/v1beta"
TAILLE_PAGE_MODELES = 1000
TAILLE_PAGE_VOIX = 1000  # maximum accepté par l'API Voices
DELAI_CREATION_VOIX = 120  # secondes
DELAI_GENERATION = 300  # secondes : une longue voix off peut prendre du temps
DELAI_ENTRE_MORCEAUX = 120  # secondes : attente maximale entre deux morceaux d'une réponse en flux
DELAI_TELEVERSEMENT = 300  # secondes : envoi d'un fichier audio
DELAI_TRANSCRIPTION = 600  # secondes : une longue source peut prendre du temps
ATTENTE_FICHIER_PRET = 2  # secondes entre deux vérifications d'un fichier en cours de préparation
VERIFICATIONS_FICHIER_MAX = 60
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
        # Téléversement des fichiers : même adresse, préfixée de « /upload » (…/upload/v1beta/files).
        racine, version = self._url_api.rsplit("/", 1) if self._url_api.endswith("/v1beta") else (self._url_api, "")
        self._url_televersement = f"{racine}/upload/{version}".rstrip("/")

    # --- Appels ------------------------------------------------------------------------------

    def _appeler(
        self,
        methode: str,
        chemin: str,
        parametres: dict[str, Any] | list[tuple[str, Any]] | None = None,
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

    def generer_voix(self, requete_voix: RequeteVoix, recevoir_audio: RecepteurAudio | None = None) -> ResultatVoix:
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
        if recevoir_audio is None:
            return lire_resultat_voix(self._interaction(corps, DELAI_GENERATION))
        return self._voix_en_flux({**corps, "stream": True}, recevoir_audio)

    def _voix_en_flux(self, corps: dict, recevoir_audio: RecepteurAudio) -> ResultatVoix:
        """Même demande « en flux » (`stream: true`) : Google envoie l'audio par morceaux (PCM 16 bits,
        24 kHz, mono) pendant le calcul ; chaque morceau part aussitôt vers `recevoir_audio` (pour
        l'écouter), puis la prise complète est assemblée. Si Google est surchargé (erreur 5xx avant
        le premier morceau), un nouvel essai est fait après une pause."""
        for essai in range(1, ESSAIS_SI_SURCHARGE + 1):
            reponse = ouvrir_flux(
                "POST",
                f"{self._url_api}/interactions",
                entetes={"x-goog-api-key": self._cle},
                corps_json=corps,
                delai=DELAI_ENTRE_MORCEAUX,
            )
            if isinstance(reponse, ReponseHttp):
                erreur = traduire_erreur(reponse)
                if erreur.code != "serveur" or essai == ESSAIS_SI_SURCHARGE:
                    raise erreur
                journal.warning("Google surchargé, nouvel essai dans %s s", PAUSE_AVANT_NOUVEL_ESSAI)
                time.sleep(PAUSE_AVANT_NOUVEL_ESSAI)
                continue
            with reponse:
                return lire_flux_voix(reponse.evenements(), recevoir_audio)
        raise AssertionError("inaccessible")

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

    # --- Transcription (STT) et fichiers ----------------------------------------------------------

    def transcrire(self, requete: RequeteTranscription) -> ResultatTranscription:
        fichier = self.televerser(requete.audio, requete.type_mime, requete.nom)
        try:
            corps = {
                "model": requete.modele,
                "input": [{"type": "audio", "uri": fichier.uri, "mime_type": requete.type_mime}],
                "generation_config": {"transcription_config": config_transcription(requete)},
            }
            return lire_resultat_transcription(self._interaction(corps, DELAI_TRANSCRIPTION))
        finally:
            self.supprimer_fichier(fichier.nom)

    def televerser(self, donnees: bytes, type_mime: str, nom: str) -> FichierTeleverse:
        """Dépose un fichier avec l'API Files (téléversement « resumable » en une fois)."""
        depart = requete(
            "POST",
            f"{self._url_televersement}/files",
            entetes={
                "x-goog-api-key": self._cle,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(donnees)),
                "X-Goog-Upload-Header-Content-Type": type_mime,
            },
            corps_json={"file": {"display_name": nom}},
            delai=60,
        )
        if depart.statut >= 400:
            raise traduire_erreur(depart)
        adresse = next((v for k, v in depart.entetes.items() if k.lower() == "x-goog-upload-url"), "")
        if not adresse:
            raise ErreurFournisseur(
                "Google n'a pas donné d'adresse pour envoyer le fichier. Réessaie dans un instant.",
                "televersement",
                f"en-têtes reçus : {sorted(depart.entetes)}",
            )
        envoi = requete(
            "POST",
            adresse,
            entetes={"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"},
            donnees=donnees,
            delai=DELAI_TELEVERSEMENT,
        )
        if envoi.statut >= 400:
            raise traduire_erreur(envoi)
        try:
            fichier = lire_fichier((envoi.json() or {}).get("file") or {})
        except ValueError as erreur:
            raise ErreurFournisseur("Réponse de Google illisible.", "reponse_illisible", str(erreur)) from erreur
        for _ in range(VERIFICATIONS_FICHIER_MAX):
            if fichier.etat in ("", "ACTIVE"):
                return fichier
            if fichier.etat == "FAILED":
                raise ErreurFournisseur("Google n'a pas pu lire ce fichier audio.", "fichier_illisible", fichier.nom)
            time.sleep(ATTENTE_FICHIER_PRET)
            fichier = lire_fichier(self._appeler("GET", fichier.nom, delai=30))
        raise ErreurFournisseur("Google met trop de temps à préparer le fichier. Réessaie.", "televersement", fichier.nom)

    def supprimer_fichier(self, nom: str) -> None:
        """Supprime un fichier déposé (sinon Google l'efface de lui-même au bout de 48 h)."""
        try:
            self._appeler("DELETE", nom, delai=30)
        except ErreurFournisseur:
            journal.warning("Fichier déposé non supprimé (Google l'effacera dans 48 h) : %s", nom)

    # --- Voix : bibliothèque et Voice Design --------------------------------------------------

    def lister_voix(self, types: tuple[str, ...] = ("prebuilt",)) -> list[VoixBibliotheque]:
        voix: list[VoixBibliotheque] = []
        jeton: str | None = None
        while True:
            parametres: list[tuple[str, Any]] = [("page_size", TAILLE_PAGE_VOIX), *(("type", t) for t in types)]
            if jeton:
                parametres.append(("page_token", jeton))
            donnees = self._appeler("GET", "voices", parametres, delai=30)
            voix += [lire_voix(v) for v in donnees.get("voices") or [] if isinstance(v, dict)]
            jeton = _champ(donnees, "next_page_token")
            if not jeton:
                return [v for v in voix if v.identifiant]

    def obtenir_voix(self, identifiant: str) -> VoixBibliotheque:
        return lire_voix(self._appeler("GET", f"voices/{quote(identifiant, safe='')}", delai=30))

    def creer_voix(self, requete_voix: RequeteVoiceDesign) -> VoixCreee:
        voix: dict[str, Any] = {
            "model": requete_voix.modele,
            "type": "prompted",
            "display_name": requete_voix.nom,
            "prompted": {"input": requete_voix.description},
        }
        if requete_voix.langue:
            voix["language_code"] = requete_voix.langue
        if requete_voix.genre:
            voix["gender"] = requete_voix.genre
        try:
            donnees = self._appeler("POST", "voices", corps={"store": True, "voice": voix}, delai=DELAI_CREATION_VOIX)
        except ErreurFournisseur as erreur:
            if erreur.code == "quota":
                raise ErreurFournisseur(
                    "Google refuse de créer une voix de plus : soit le maximum de 200 voix créées est "
                    "atteint (supprime une voix inutile), soit trop de demandes ont été faites d'affilée "
                    "(réessaie dans quelques minutes).",
                    "quota_voix",
                    erreur.detail,
                ) from erreur
            raise
        entree, sortie = _tokens(donnees)
        return VoixCreee(lire_voix(donnees), entree, sortie)

    def supprimer_voix(self, identifiant: str) -> None:
        self._appeler("DELETE", f"voices/{quote(identifiant, safe='')}", delai=30)

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


def _champ(donnees: dict, nom: str, defaut: Any = None) -> Any:
    """Champ d'une réponse, écrit « display_name » ou « displayName » selon les API de Google."""
    if nom in donnees:
        return donnees[nom]
    morceaux = nom.split("_")
    return donnees.get(morceaux[0] + "".join(m.capitalize() for m in morceaux[1:]), defaut)


def lire_voix(donnees: dict) -> VoixBibliotheque:
    """Une voix de l'API Voices → VoixBibliotheque (extrait audio décodé s'il est présent)."""
    extrait = None
    audio = _champ(donnees, "sample_audio")
    if isinstance(audio, dict) and audio.get("data"):
        try:
            extrait = en_wav(base64.b64decode(audio["data"]), int(_champ(audio, "sample_rate") or FREQUENCE_TTS))
        except (binascii.Error, ValueError, EOFError):
            journal.warning("Extrait audio de la voix illisible", exc_info=True)
    identifiant = str(donnees.get("id") or "")
    return VoixBibliotheque(
        identifiant=identifiant,
        nom=str(_champ(donnees, "display_name") or identifiant),
        description=str(donnees.get("description") or _champ(donnees.get("prompted") or {}, "input") or ""),
        langue=str(_champ(donnees, "language_code") or ""),
        region=str(_champ(donnees, "region_code") or ""),
        accent=str(donnees.get("accent") or ""),
        genre=str(donnees.get("gender") or "").lower(),
        hauteur=str(donnees.get("pitch") or "").lower(),
        persona=str(donnees.get("persona") or ""),
        contexte=str(donnees.get("context") or ""),
        type=str(donnees.get("type") or "prebuilt").lower(),
        modele=str(donnees.get("model") or ""),
        expire_le=str(_champ(donnees, "expire_time") or ""),
        extrait_wav=extrait,
    )


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


def pcm_du_morceau(delta: dict) -> tuple[bytes, int]:
    """(échantillons PCM 16 bits, fréquence) d'un morceau d'audio reçu en flux.

    Par défaut, Google envoie du PCM brut (« audio/l16 », 24 kHz, mono, 16 bits little-endian) ;
    un morceau au format WAV (en-tête « RIFF ») est aussi accepté."""
    brut = base64.b64decode(delta.get("data") or "")
    if brut[:4] == b"RIFF":
        pcm, frequence, _canaux = lire_wav(brut)
        return pcm, frequence
    frequence = int(_champ(delta, "sample_rate") or delta.get("rate") or 0)
    if not frequence:
        # « audio/l16;rate=24000 » : la fréquence peut aussi être écrite dans le type.
        type_mime = str(_champ(delta, "mime_type") or "")
        _, _, suite = type_mime.partition("rate=")
        frequence = int(suite.split(";")[0]) if suite.split(";")[0].isdigit() else FREQUENCE_TTS
    return brut, frequence


def lire_flux_voix(evenements: Iterable[EvenementSse], recevoir_audio: RecepteurAudio) -> ResultatVoix:
    """Événements d'une interaction « en flux » → prise complète (WAV + tokens pour le coût).

    Événements utiles : « step.delta » (un morceau d'audio, transmis aussitôt à `recevoir_audio`),
    « interaction.completed » (statut final et nombres de tokens), « error » (génération
    interrompue). Le flux se termine par « [DONE] »."""
    morceaux: list[bytes] = []
    frequence = FREQUENCE_TTS
    finale: dict | None = None
    for evenement in evenements:
        if evenement.donnees.strip() == "[DONE]":
            break
        try:
            donnees = json.loads(evenement.donnees)
        except ValueError:
            journal.warning("Événement illisible ignoré : %s", evenement.donnees[:200])
            continue
        if not isinstance(donnees, dict):
            continue
        type_evenement = donnees.get("event_type") or evenement.type
        if type_evenement == "error":
            erreur = donnees.get("error") or {}
            message = str(erreur.get("message") or "").strip()
            raise ErreurFournisseur(
                "Google a interrompu la génération" + (f" : {message}" if message else ".") + " Réessaie.",
                "generation",
                json.dumps(erreur, ensure_ascii=False)[:1000],
            )
        if type_evenement == "step.delta":
            delta = donnees.get("delta") or {}
            if isinstance(delta, dict) and delta.get("type") == "audio" and delta.get("data"):
                try:
                    pcm, frequence = pcm_du_morceau(delta)
                except (binascii.Error, ValueError, EOFError) as erreur:
                    raise ErreurFournisseur("Audio reçu de Google illisible.", "audio_illisible", str(erreur)) from erreur
                morceaux.append(pcm)
                recevoir_audio(pcm, frequence)
        elif type_evenement == "interaction.completed":
            finale = donnees.get("interaction") if isinstance(donnees.get("interaction"), dict) else {}
    if finale is None:
        raise ErreurFournisseur(
            "La génération s'est arrêtée avant la fin (connexion coupée ?). Réessaie.",
            "reseau",
            f"{len(morceaux)} morceaux reçus, sans « interaction.completed »",
        )
    if not morceaux:
        # Rien reçu en route : l'audio est peut-être dans la réponse finale.
        return lire_resultat_voix(finale)
    _verifier_statut(finale, "la voix")
    wav = wav_depuis_pcm(b"".join(morceaux), frequence)
    tokens_entree, tokens_sortie = _tokens(finale)
    return ResultatVoix(
        wav,
        duree_wav(wav),
        tokens_entree,
        tokens_sortie,
        {"statut": finale.get("status"), "usage": finale.get("usage") or {}, "flux": len(morceaux)},
    )


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


def lire_fichier(donnees: dict) -> FichierTeleverse:
    """Fichier de l'API Files : `name`, `uri`, `mime_type` / `mimeType`, `state`."""
    fichier = FichierTeleverse(
        nom=str(donnees.get("name") or ""),
        uri=str(donnees.get("uri") or ""),
        type_mime=str(_champ(donnees, "mime_type") or ""),
        etat=str(donnees.get("state") or "").upper(),
    )
    if not fichier.nom or not fichier.uri:
        raise ValueError(f"fichier sans nom ni adresse : {json.dumps(donnees)[:300]}")
    return fichier


def config_transcription(requete_stt: RequeteTranscription) -> dict:
    """`generation_config.transcription_config` d'une demande de transcription."""
    config: dict[str, Any] = {"language_codes": [requete_stt.langue] if requete_stt.langue else []}
    if requete_stt.mode == "smart":
        config["mode"] = "smart"  # incompatible avec les temps et la séparation des voix
        return config
    mode: dict[str, Any] = {"type": "verbatim"}
    if requete_stt.horodatage:
        mode["timestamp_granularities"] = ["word"]
    if requete_stt.separation_voix:
        mode["diarization_mode"] = "speaker"
    config["mode"] = mode
    return config


def secondes(valeur: Any) -> float:
    """Durée de Google → secondes : « 1.250s », un nombre, ou {"seconds": 1, "nanos": 250000000}."""
    if isinstance(valeur, (int, float)):
        return float(valeur)
    if isinstance(valeur, dict):
        return float(valeur.get("seconds") or 0) + float(valeur.get("nanos") or 0) / 1e9
    texte = str(valeur or "").strip().removesuffix("s")
    try:
        return float(texte) if texte else 0.0
    except ValueError:
        return 0.0


def lire_mots(donnees: dict) -> list[MotTranscrit]:
    """Mots horodatés : annotations « word_info » des textes du modèle, dans l'ordre."""
    mots: list[MotTranscrit] = []
    for etape in donnees.get("steps") or []:
        if not isinstance(etape, dict) or etape.get("type") not in (None, "model_output"):
            continue
        for element in etape.get("content") or []:
            if not isinstance(element, dict) or element.get("type") != "text":
                continue
            for annotation in element.get("annotations") or []:
                if not isinstance(annotation, dict) or annotation.get("type") != "word_info":
                    continue
                texte = " ".join(str(annotation.get("text") or "").split())
                if texte:
                    mots.append(
                        MotTranscrit(
                            texte,
                            secondes(_champ(annotation, "start_offset")),
                            secondes(_champ(annotation, "end_offset")),
                            str(annotation.get("speaker") or ""),
                        )
                    )
    return mots


def lire_resultat_transcription(donnees: dict) -> ResultatTranscription:
    """Réponse de l'API Interactions → texte, mots horodatés et tokens (pour le coût)."""
    _verifier_statut(donnees, "la transcription")
    texte = trouver_texte(donnees).strip()
    mots = lire_mots(donnees)
    if not texte and mots:
        texte = " ".join(m.texte for m in mots)
    tokens_entree, tokens_sortie = _tokens(donnees)
    return ResultatTranscription(
        texte, mots, tokens_entree, tokens_sortie, {"statut": donnees.get("status"), "usage": donnees.get("usage") or {}}
    )


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
