"""Requêtes HTTP vers les API des fournisseurs.

On utilise le module `urllib` fourni avec Python (aucune bibliothèque en plus) : il suit les
réglages de proxy de Windows et vérifie les certificats de sécurité avec ceux du système.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
import urllib.error
import urllib.request
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
    toutes_entetes = {"User-Agent": f"{NOM_APP.replace(' ', '-')}/{__version__}"}
    if corps_json is not None:
        donnees = json.dumps(corps_json).encode("utf-8")
        toutes_entetes["Content-Type"] = "application/json; charset=utf-8"
    toutes_entetes.update(entetes or {})
    demande = urllib.request.Request(url, data=donnees, headers=toutes_entetes, method=methode)
    # L'adresse est journalisée sans ses paramètres (ils pourraient contenir des informations privées).
    journal.info("%s %s", methode, url.split("?", 1)[0])
    try:
        with urllib.request.urlopen(demande, timeout=delai, context=ssl.create_default_context()) as reponse:
            return ReponseHttp(reponse.status, reponse.read(), dict(reponse.headers.items()))
    except urllib.error.HTTPError as erreur:
        corps = erreur.read() if erreur.fp is not None else b""
        return ReponseHttp(erreur.code, corps, dict(erreur.headers.items()) if erreur.headers else {})
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as erreur:
        raison = getattr(erreur, "reason", erreur)
        journal.warning("Serveur injoignable : %s", raison)
        raise ErreurFournisseur(
            "Impossible de joindre le serveur. Vérifie ta connexion Internet, puis réessaie.",
            "reseau",
            str(raison),
        ) from erreur
