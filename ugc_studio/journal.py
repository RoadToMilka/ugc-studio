"""Journal d'erreurs (cahier des charges §10) : lisible, et sans aucune clé API.

Tout ce que l'app écrit dans le journal passe par la fonction `masquer`, qui remplace
les clés et jetons par « [masqué] » avant l'écriture sur le disque. Deux protections :
1. des motifs reconnaissent les formats de clés connus (Google « AIza… », « Bearer … »,
   paramètres « key=… », etc.) ;
2. chaque clé chargée par l'app est « déclarée » avec `declarer_secret` : sa valeur exacte
   est alors masquée partout, quel que soit son format.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
import threading
from pathlib import Path

MASQUE = "[masqué]"

# Motifs de secrets connus. Le groupe « prefixe » (quand il existe) est conservé,
# seule la valeur secrète est remplacée.
_MOTIFS_COMPLETS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),  # clés d'API Google
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{16,}"),  # clés OpenAI / Anthropic
)
_MOTIFS_AVEC_PREFIXE = (
    # En-tête « Authorization: Bearer xxx »
    re.compile(r"(?P<prefixe>\bBearer\s+)[A-Za-z0-9._~+/=\-]{8,}", re.IGNORECASE),
    # « key=xxx », « api_key: xxx », « x-goog-api-key: xxx », « "token": "xxx" »…
    re.compile(
        r"(?P<prefixe>\b(?:x-goog-api-key|xi-api-key|api[_-]?key|access[_-]?token|token|key|secret)"
        r"[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;}]{6,}",
        re.IGNORECASE,
    ),
)

_secrets: set[str] = set()
_verrou = threading.Lock()
_gestionnaire: logging.Handler | None = None


def declarer_secret(valeur: str | None) -> None:
    """Déclare une valeur secrète (ex. une clé API) : elle sera masquée dans tout le journal."""
    if valeur and len(valeur) >= 6:
        with _verrou:
            _secrets.add(valeur)


def masquer(texte: str) -> str:
    """Renvoie le texte avec toutes les clés et jetons remplacés par « [masqué] »."""
    with _verrou:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        texte = texte.replace(secret, MASQUE)
    for motif in _MOTIFS_COMPLETS:
        texte = motif.sub(MASQUE, texte)
    for motif in _MOTIFS_AVEC_PREFIXE:
        texte = motif.sub(lambda m: m.group("prefixe") + MASQUE, texte)
    return texte


class FormateurMasque(logging.Formatter):
    """Met en forme une ligne du journal, puis masque les secrets.

    Le masquage s'applique au texte final complet, donc aussi aux détails
    techniques des erreurs (la « trace » Python).
    """

    def format(self, record: logging.LogRecord) -> str:
        return masquer(super().format(record))


def configurer_journal(fichier: Path, niveau: int = logging.INFO) -> logging.Handler:
    """Envoie tous les messages de l'app vers le fichier journal (3 fichiers de 1 Mo max en rotation)."""
    global _gestionnaire
    racine = logging.getLogger()
    if _gestionnaire is not None:
        racine.removeHandler(_gestionnaire)
        _gestionnaire.close()

    fichier.parent.mkdir(parents=True, exist_ok=True)
    gestionnaire = logging.handlers.RotatingFileHandler(
        fichier, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    gestionnaire.setFormatter(
        FormateurMasque("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    racine.addHandler(gestionnaire)
    racine.setLevel(niveau)
    _gestionnaire = gestionnaire

    # Filet de sécurité : toute erreur Python non prévue finit dans le journal.
    # (L'interface remplace ensuite ce crochet par un autre qui affiche aussi une fenêtre.)
    sys.excepthook = _journaliser_exception
    threading.excepthook = lambda args: _journaliser_exception(
        args.exc_type, args.exc_value, args.exc_traceback
    )
    return gestionnaire


def _journaliser_exception(type_exception, valeur, trace) -> None:
    if issubclass(type_exception, KeyboardInterrupt):
        sys.__excepthook__(type_exception, valeur, trace)
        return
    logging.getLogger("ugc_studio").critical(
        "Erreur inattendue", exc_info=(type_exception, valeur, trace)
    )
