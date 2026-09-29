"""Erreurs inattendues : tout est écrit dans le journal, et une fenêtre claire prévient l'utilisateur.

Sans ce mécanisme, une erreur dans l'app ferait simplement disparaître la fenêtre, sans explication.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QMessageBox

journal = logging.getLogger("ugc_studio")

_NIVEAUX_QT = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}

# Code de sortie de l'app quand une erreur survient pendant l'autotest.
CODE_ERREUR_AUTOTEST = 3


def _message_qt(type_message, _contexte, message: str) -> None:
    """Les avertissements internes de Qt vont aussi dans le journal."""
    logging.getLogger("qt").log(_NIVEAUX_QT.get(type_message, logging.WARNING), message)


def installer_gestion_erreurs(ouvrir_journal: Callable[[], None], mode_autotest: bool = False) -> None:
    qInstallMessageHandler(_message_qt)
    fenetre_ouverte = False

    def crochet(type_exception, valeur, trace) -> None:
        nonlocal fenetre_ouverte
        if issubclass(type_exception, KeyboardInterrupt):
            sys.__excepthook__(type_exception, valeur, trace)
            return
        journal.critical("Erreur inattendue", exc_info=(type_exception, valeur, trace))
        app = QApplication.instance()
        if app is None:
            return
        if mode_autotest:
            # Pendant l'autotest, personne ne peut cliquer sur « OK » : on arrête l'app avec un code d'erreur.
            app.exit(CODE_ERREUR_AUTOTEST)
            return
        if fenetre_ouverte:
            return
        fenetre_ouverte = True
        try:
            boite = QMessageBox(app.activeWindow())
            boite.setIcon(QMessageBox.Icon.Critical)
            boite.setWindowTitle("Erreur inattendue")
            boite.setText("Une erreur inattendue s'est produite.")
            boite.setInformativeText(
                "Les détails sont enregistrés dans le journal d'erreurs "
                "(Réglages → Journal d'erreurs). L'app peut continuer à fonctionner."
            )
            bouton_journal = boite.addButton("Ouvrir le journal", QMessageBox.ButtonRole.ActionRole)
            boite.addButton(QMessageBox.StandardButton.Ok)
            boite.exec()
            if boite.clickedButton() is bouton_journal:
                ouvrir_journal()
        finally:
            fenetre_ouverte = False

    def crochet_fil(arguments) -> None:
        # Erreur dans une tâche de fond : on l'écrit dans le journal. (Une fenêtre ne peut être
        # ouverte que depuis la tâche principale de l'interface.)
        journal.critical(
            "Erreur inattendue dans une tâche de fond",
            exc_info=(arguments.exc_type, arguments.exc_value, arguments.exc_traceback),
        )

    sys.excepthook = crochet
    threading.excepthook = crochet_fil
