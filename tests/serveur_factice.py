"""Petit serveur web local qui imite une API (pour tester les adaptateurs sans Internet ni clé)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ServeurFactice:
    """Chaque réponse programmée est un triplet (code HTTP, corps JSON ou bytes, en-têtes)."""

    def __init__(self):
        self.requetes: list[dict] = []
        self.reponses: list[tuple[int, object, dict]] = []
        serveur = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def _repondre(self):
                longueur = int(self.headers.get("Content-Length") or 0)
                corps = self.rfile.read(longueur) if longueur else b""
                serveur.requetes.append(
                    {
                        "methode": self.command,
                        "chemin": self.path,
                        # Noms d'en-têtes en minuscules : en HTTP, la casse ne compte pas.
                        "entetes": {k.lower(): v for k, v in self.headers.items()},
                        "corps": corps,
                    }
                )
                code, contenu, entetes = serveur.reponses.pop(0) if serveur.reponses else (404, {}, {})
                donnees = contenu if isinstance(contenu, bytes) else json.dumps(contenu).encode("utf-8")
                self.send_response(code)
                for nom, valeur in {"Content-Type": "application/json", **entetes}.items():
                    self.send_header(nom, valeur)
                self.send_header("Content-Length", str(len(donnees)))
                self.end_headers()
                self.wfile.write(donnees)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _repondre

            def log_message(self, *_args):
                pass  # silence

        self._serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        self.url = f"http://127.0.0.1:{self._serveur.server_address[1]}"
        self._fil = threading.Thread(target=self._serveur.serve_forever, daemon=True)
        self._fil.start()

    def programmer(self, code: int, contenu: object = None, entetes: dict | None = None) -> None:
        self.reponses.append((code, {} if contenu is None else contenu, entetes or {}))

    def arreter(self) -> None:
        self._serveur.shutdown()
        self._serveur.server_close()
