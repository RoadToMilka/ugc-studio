"""Requêtes HTTP vers les API des fournisseurs.

On utilise le module `urllib` fourni avec Python (aucune bibliothèque en plus) : il suit les
réglages de proxy de Windows et vérifie les certificats de sécurité avec ceux du système.

Deux façons de recevoir la réponse :
- `requete` : la réponse complète, d'un bloc ;
- `ouvrir_flux` : une réponse « en flux » (server-sent events), lue au fur et à mesure de son
  arrivée — ex. l'audio d'une voix off, morceau par morceau, pendant que Google la calcule.
"""

from __future__ import annotations

import http.client
import json
import logging
import socket
import ssl
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from .. import NOM_APP, __version__
from .base import ErreurFournisseur

journal = logging.getLogger(__name__)

DELAI_PAR_DEFAUT = 60  # secondes


@dataclass
class ReponseHttp:
    statut: int
    corps: bytes
    entetes: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.corps.decode("utf-8")) if self.corps else {}


def _preparer(
    methode: str, url: str, entetes: dict[str, str] | None, corps_json: Any, donnees: bytes | None
) -> urllib.request.Request:
    toutes_entetes = {"User-Agent": f"{NOM_APP.replace(' ', '-')}/{__version__}"}
    if corps_json is not None:
        donnees = json.dumps(corps_json).encode("utf-8")
        toutes_entetes["Content-Type"] = "application/json; charset=utf-8"
    toutes_entetes.update(entetes or {})
    # L'adresse est journalisée sans ses paramètres (ils pourraient contenir des informations privées).
    journal.info("%s %s", methode, url.split("?", 1)[0])
    return urllib.request.Request(url, data=donnees, headers=toutes_entetes, method=methode)


def _injoignable(erreur: Exception) -> ErreurFournisseur:
    raison = getattr(erreur, "reason", erreur)
    journal.warning("Serveur injoignable : %s", raison)
    return ErreurFournisseur(
        "Impossible de joindre le serveur. Vérifie ta connexion Internet, puis réessaie.",
        "reseau",
        str(raison),
    )


def _reponse_en_erreur(erreur: urllib.error.HTTPError) -> ReponseHttp:
    corps = erreur.read() if erreur.fp is not None else b""
    return ReponseHttp(erreur.code, corps, dict(erreur.headers.items()) if erreur.headers else {})


def requete(
    methode: str,
    url: str,
    *,
    entetes: dict[str, str] | None = None,
    corps_json: Any = None,
    donnees: bytes | None = None,
    delai: float = DELAI_PAR_DEFAUT,
) -> ReponseHttp:
    """Envoie une requête et renvoie la réponse, y compris quand le serveur répond par une erreur
    (code 400, 403…) : c'est à l'adaptateur de traduire l'erreur pour l'utilisateur.

    Lève ErreurFournisseur(code « reseau ») si le serveur est injoignable.
    """
    demande = _preparer(methode, url, entetes, corps_json, donnees)
    try:
        with urllib.request.urlopen(demande, timeout=delai, context=ssl.create_default_context()) as reponse:
            return ReponseHttp(reponse.status, reponse.read(), dict(reponse.headers.items()))
    except urllib.error.HTTPError as erreur:
        return _reponse_en_erreur(erreur)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as erreur:
        raise _injoignable(erreur) from erreur


# --- Réponses « en flux » (server-sent events) --------------------------------------------------


@dataclass(frozen=True)
class EvenementSse:
    """Un événement d'un flux « text/event-stream » : son type (ligne « event: ») et ses données
    (lignes « data: », réunies)."""

    type: str
    donnees: str


def lire_sse(lignes: Iterable[bytes]) -> Iterator[EvenementSse]:
    """Découpe un flux « text/event-stream » en événements.

    Format : des lignes « champ: valeur » ; une ligne vide termine un événement ; les lignes qui
    commencent par « : » sont des commentaires (le serveur s'en sert pour garder la connexion)."""
    type_evenement, donnees = "", []
    for brute in lignes:
        ligne = brute.decode("utf-8").rstrip("\r\n")
        if not ligne:
            if donnees or type_evenement:
                yield EvenementSse(type_evenement, "\n".join(donnees))
            type_evenement, donnees = "", []
            continue
        if ligne.startswith(":"):
            continue
        champ, _, valeur = ligne.partition(":")
        valeur = valeur.removeprefix(" ")
        if champ == "event":
            type_evenement = valeur
        elif champ == "data":
            donnees.append(valeur)
    if donnees or type_evenement:
        yield EvenementSse(type_evenement, "\n".join(donnees))


class ReponseFlux:
    """Réponse lue au fur et à mesure de son arrivée. À fermer après usage (`with`)."""

    def __init__(self, reponse):
        self._reponse = reponse
        self.statut: int = reponse.status

    def evenements(self) -> Iterator[EvenementSse]:
        try:
            yield from lire_sse(self._reponse)
        except (
            urllib.error.URLError,
            socket.timeout,
            TimeoutError,
            ConnectionError,
            http.client.IncompleteRead,
        ) as erreur:
            journal.warning("Flux interrompu : %s", erreur)
            raise ErreurFournisseur(
                "La connexion avec le serveur a été coupée pendant la génération. Réessaie.",
                "reseau",
                str(erreur),
            ) from erreur

    def fermer(self) -> None:
        self._reponse.close()

    def __enter__(self) -> ReponseFlux:
        return self

    def __exit__(self, *_details) -> None:
        self.fermer()


def ouvrir_flux(
    methode: str,
    url: str,
    *,
    entetes: dict[str, str] | None = None,
    corps_json: Any = None,
    delai: float = DELAI_PAR_DEFAUT,
) -> ReponseFlux | ReponseHttp:
    """Comme `requete`, mais la réponse (si le serveur accepte la demande) est renvoyée ouverte,
    pour être lue événement par événement. `delai` : attente maximale entre deux morceaux.

    Renvoie la ReponseHttp complète quand le serveur répond par une erreur (code 400, 500…)."""
    demande = _preparer(methode, url, {"Accept": "text/event-stream", **(entetes or {})}, corps_json, None)
    try:
        reponse = urllib.request.urlopen(demande, timeout=delai, context=ssl.create_default_context())
    except urllib.error.HTTPError as erreur:
        return _reponse_en_erreur(erreur)
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as erreur:
        raise _injoignable(erreur) from erreur
    return ReponseFlux(reponse)
