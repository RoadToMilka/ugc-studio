"""Démarrage de l'application."""

from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
from pathlib import Path

from . import NOM_APP, __version__
from .chemins import VARIABLE_DOSSIER_DONNEES, dossier_ressources, fichier_journal, fichier_preferences
from .journal import configurer_journal

journal = logging.getLogger(__name__)

# Identifiant Windows de l'app : regroupe ses fenêtres sous sa propre icône dans la barre des tâches.
IDENTIFIANT_WINDOWS = "RoadToMilka.UGCStudio"


def analyser_arguments(arguments: list[str]) -> argparse.Namespace:
    """Options de lancement (réservées à la fabrication automatique ; l'utilisateur n'en a pas besoin)."""
    analyseur = argparse.ArgumentParser(prog="UGC-Studio", add_help=False)
    analyseur.add_argument("--autotest", metavar="DOSSIER")
    analyseur.add_argument("--captures-taille-fixe", action="store_true")
    options, _reste = analyseur.parse_known_args(arguments)
    return options


def _definir_identifiant_windows() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(IDENTIFIANT_WINDOWS)
    except (AttributeError, OSError):
        journal.warning("Identifiant Windows de l'app non défini", exc_info=True)


def installer_traduction_qt(app) -> bool:
    """Traduit en français les textes intégrés à Qt (boutons « OK / Annuler » des fenêtres…)."""
    import PySide6
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    traducteur = QTranslator(app)
    dossiers = [
        QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
        str(Path(PySide6.__file__).parent / "translations"),
    ]
    francais = QLocale(QLocale.Language.French, QLocale.Country.France)
    for dossier in dossiers:
        if traducteur.load(francais, "qtbase", "_", dossier):
            app.installTranslator(traducteur)
            return True
    journal.warning("Traduction française de Qt introuvable (dossiers : %s)", dossiers)
    return False


def configurer_application(app) -> dict:
    """Applique l'identité, la police Inter, les couleurs et la feuille de style à l'app Qt.

    Renvoie un petit résumé (utilisé par l'autotest).
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon

    from .ui import theme
    from .ui.icones import icones_feuille_de_style
    from .ui.polices import charger_polices, familles_par_graisse, police

    app.setApplicationName(NOM_APP)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")  # style de base neutre, que la feuille de style personnalise entièrement
    indications = app.styleHints()
    if hasattr(indications, "setColorScheme"):  # Qt 6.8+ : barre de titre Windows sombre
        indications.setColorScheme(Qt.ColorScheme.Dark)
    traduction = installer_traduction_qt(app)
    familles = charger_polices()
    app.setFont(police())
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.feuille_de_style(icones_feuille_de_style(), familles_par_graisse()))
    app.setWindowIcon(QIcon(str(dossier_ressources() / "app.png")))
    return {"polices": familles, "familles_par_graisse": familles_par_graisse(), "traduction_fr": traduction}


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    options = analyser_arguments(arguments)
    dossier_autotest = None
    if options.autotest:
        dossier_autotest = Path(options.autotest).absolute()
        dossier_autotest.mkdir(parents=True, exist_ok=True)
        # L'autotest travaille dans son propre dossier et ne touche pas aux vraies données.
        os.environ[VARIABLE_DOSSIER_DONNEES] = str(dossier_autotest / "donnees")

    configurer_journal(fichier_journal())
    journal.info(
        "Démarrage de %s %s (Python %s, %s)", NOM_APP, __version__, platform.python_version(), platform.platform()
    )
    _definir_identifiant_windows()

    from PySide6.QtWidgets import QApplication

    from .preferences import Preferences
    from .ui.erreurs import installer_gestion_erreurs
    from .ui.fenetre_principale import FenetrePrincipale
    from .ui.pages.page_reglages import ouvrir_journal

    app = QApplication([sys.argv[0], *arguments])
    resume = configurer_application(app)
    installer_gestion_erreurs(ouvrir_journal, mode_autotest=dossier_autotest is not None)

    fenetre = FenetrePrincipale(Preferences(fichier_preferences()))
    fenetre.show()

    if dossier_autotest is not None:
        from .autotest import lancer_autotest

        lancer_autotest(app, fenetre, dossier_autotest, resume, options.captures_taille_fixe)

    code = app.exec()
    journal.info("Fermeture de l'app (code %s)", code)
    return code
