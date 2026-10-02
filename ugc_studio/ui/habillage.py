"""Habillage de ce que Qt dessine lui-même (V3.2) : un seul filtre posé sur toute l'app, qui voit
passer chaque événement avant les éléments de l'app.

- Bulles d'aide : celle de l'app (composants/bulle.py) à la place de celle de Qt.
- Clic droit dans un champ de texte : le menu standard de Qt (Copier, Coller…) dans un menu de l'app,
  aux coins arrondis (composants/menu.py).

Le filtre ne fait presque rien pour les autres événements : il regarde leur type et les laisse passer.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

from .composants.bulle import filtrer_pour_les_bulles
from .composants.menu import menu_contextuel_du_champ


class _Habillage(QObject):
    def eventFilter(self, objet, evenement) -> bool:  # noqa: N802 — nom imposé par Qt
        if evenement.type() == QEvent.Type.ContextMenu and isinstance(objet, QWidget):
            if menu_contextuel_du_champ(objet, evenement.globalPos()):
                return True
        return filtrer_pour_les_bulles(objet, evenement)


def installer_l_habillage(app: QApplication) -> None:
    """Pose le filtre sur l'app, une seule fois (les tests configurent l'app plusieurs fois)."""
    if getattr(app, "_habillage_ugc", None) is None:
        app._habillage_ugc = _Habillage(app)
        app.installEventFilter(app._habillage_ugc)
