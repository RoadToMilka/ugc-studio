"""Tâches de fond : les appels réseau (tester une clé, générer une voix…) prennent du temps.

S'ils tournaient dans la tâche principale, la fenêtre serait figée (« Ne répond pas ») pendant
l'attente. On les lance donc sur un fil d'exécution séparé ; le résultat revient ensuite dans la
tâche principale, la seule autorisée à modifier l'interface.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

journal = logging.getLogger(__name__)

# Tâches en cours (on garde une référence pour que Python ne les efface pas avant la fin).
_en_cours: set[_Retour] = set()


class _Retour(QObject):
    """Objet créé dans la tâche principale : ses « slots » s'y exécutent donc toujours,
    même quand le signal est émis depuis le fil de la tâche de fond."""

    termine = Signal(object)
    echec = Signal(object)
    progres = Signal(object)

    def __init__(self, quand_termine, quand_echec, quand_progres=None):
        super().__init__()
        self._quand_termine = quand_termine
        self._quand_echec = quand_echec
        self._quand_progres = quand_progres
        self.termine.connect(self._sur_termine)
        self.echec.connect(self._sur_echec)
        self.progres.connect(self._sur_progres)

    @Slot(object)
    def _sur_progres(self, valeur) -> None:
        # Les nouvelles arrivent dans l'ordre, toujours avant le résultat final.
        if self._quand_progres is not None and self in _en_cours:
            self._quand_progres(valeur)

    @Slot(object)
    def _sur_termine(self, resultat) -> None:
        _en_cours.discard(self)
        self._quand_termine(resultat)

    @Slot(object)
    def _sur_echec(self, erreur) -> None:
        _en_cours.discard(self)
        if self._quand_echec is not None:
            self._quand_echec(erreur)


class _Tache(QRunnable):
    def __init__(self, fonction: Callable[[], Any], retour: _Retour):
        super().__init__()
        self._fonction = fonction
        self._retour = retour

    def run(self) -> None:
        try:
            resultat = self._fonction()
        except Exception as erreur:  # noqa: BLE001 — transmis à l'interface
            journal.warning("Tâche de fond en échec : %s", erreur, exc_info=True)
            self._retour.echec.emit(erreur)
        else:
            self._retour.termine.emit(resultat)


def lancer(
    fonction: Callable[[], Any],
    quand_termine: Callable[[Any], None],
    quand_echec: Callable[[Exception], None] | None = None,
) -> None:
    """Exécute `fonction()` en arrière-plan, puis appelle `quand_termine(resultat)` ou
    `quand_echec(erreur)` dans la tâche principale (où l'on peut toucher à l'interface)."""
    retour = _Retour(quand_termine, quand_echec)
    _en_cours.add(retour)
    QThreadPool.globalInstance().start(_Tache(fonction, retour))


def lancer_avec_progres(
    fonction: Callable[[Callable[[Any], None]], Any],
    quand_termine: Callable[[Any], None],
    quand_echec: Callable[[Exception], None] | None = None,
    quand_progres: Callable[[Any], None] | None = None,
) -> None:
    """Comme `lancer`, mais la tâche peut donner des nouvelles en cours de route : elle reçoit une
    fonction `progres`, et chaque `progres(valeur)` appelle `quand_progres(valeur)` dans la tâche
    principale (ex. un morceau d'audio à écouter pendant la génération)."""
    retour = _Retour(quand_termine, quand_echec, quand_progres)
    _en_cours.add(retour)
    QThreadPool.globalInstance().start(_Tache(lambda: fonction(retour.progres.emit), retour))


def en_cours() -> int:
    """Nombre de tâches dont le résultat n'est pas encore revenu."""
    return len(_en_cours)
