"""Autotest : lancé par la fabrication automatique (GitHub Actions), jamais par l'utilisateur.

Il démarre le vrai .exe sur une machine Windows, vérifie que tout est en place (police, icônes,
traduction, journal…), fait une capture d'écran de chaque module et de la galerie des composants,
puis écrit un rapport « autotest.json » et ferme l'app avec le code 0 (succès) ou 1 (échec).
"""

from __future__ import annotations

import json
import platform
import sys
import time
import traceback
from pathlib import Path

import PySide6
from PySide6.QtCore import QTimer, qVersion
from PySide6.QtGui import QFontDatabase, QFontInfo, QIcon, QImageReader
from PySide6.QtWidgets import QApplication, QScrollArea

from . import __version__
from .chemins import fichier_journal
from .demo import SCRIPT_DEMO
from .script import normaliser
from .ui.galerie import GalerieComposants
from .ui.icones import icones_feuille_de_style
from .ui.polices import police
from .ui.theme import Dimensions, Typo

DELAI_DEMARRAGE_MS = 1500  # laisse la fenêtre s'afficher complètement
DELAI_MAX_MS = 120_000  # sécurité : l'autotest ne peut pas bloquer la fabrication
PAUSE_AFFICHAGE_S = 0.4
CODE_DELAI_DEPASSE = 4

VERIFICATIONS_OBLIGATOIRES = (
    "police_inter_chargee",
    "police_inter_utilisee",
    "icones_navigation",
    "icones_feuille_de_style",
    "journal_ecrit",
    "feuille_de_style_appliquee",
    "coffre_windows",
    "editeur_badges",
    "lecture_audio",
    "captures",
)


def _laisser_afficher(secondes: float = PAUSE_AFFICHAGE_S) -> None:
    fin = time.monotonic() + secondes
    while time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.02)


def _formats_images() -> list[str]:
    return sorted(bytes(f).decode("ascii", "replace") for f in QImageReader.supportedImageFormats())


def _verifier_coffre_windows(rapport: dict) -> bool:
    """Écrit, relit puis efface une valeur de test dans le vrai coffre-fort de Windows.

    Vérifie que le .exe sait bien y ranger les clés (la bibliothèque keyring doit être
    correctement embarquée). Hors Windows, la vérification est sans objet.
    """
    if sys.platform != "win32":
        rapport["coffre_windows"] = "sans objet (pas Windows)"
        return True
    try:
        from .connexions import CoffreWindows

        coffre = CoffreWindows()
        compte = "autotest/verification"
        coffre.ecrire(compte, "valeur-de-test")
        relu = coffre.lire(compte)
        coffre.supprimer(compte)
        efface = coffre.lire(compte) is None
        rapport["coffre_windows"] = f"relu={relu == 'valeur-de-test'} efface={efface}"
        return relu == "valeur-de-test" and efface
    except Exception as erreur:  # noqa: BLE001
        rapport["coffre_windows"] = f"erreur : {erreur!r}"
        return False


def lancer_autotest(app, fenetre, dossier: Path, resume: dict, captures_taille_fixe: bool) -> None:
    def executer() -> None:
        rapport: dict = {
            "version_app": __version__,
            "python": platform.python_version(),
            "qt": qVersion(),
            "pyside6": PySide6.__version__,
            "systeme": platform.platform(),
            "plateforme_qt": app.platformName(),
            "echelle_ecran": fenetre.devicePixelRatioF(),
            "polices_chargees": resume.get("polices"),
            "formats_images": _formats_images(),
            "verifications": {},
            "captures": [],
            "erreurs": [],
        }
        verifs = rapport["verifications"]
        try:
            verifs["police_inter_chargee"] = Typo.FAMILLE in QFontDatabase.families()
            rapport["police_utilisee"] = QFontInfo(fenetre.font()).family()
            verifs["police_inter_utilisee"] = rapport["police_utilisee"] == Typo.FAMILLE
            rapport["familles_par_graisse"] = resume.get("familles_par_graisse")
            rapport["rendu_des_graisses"] = {
                graisse: f"{QFontInfo(police(Typo.COURANT, graisse)).family()} / "
                f"{QFontInfo(police(Typo.COURANT, graisse)).styleName()} / "
                f"{QFontInfo(police(Typo.COURANT, graisse)).weight()}"
                for graisse in (Typo.GRAISSE_NORMALE, Typo.GRAISSE_MOYENNE, Typo.GRAISSE_FORTE)
            }
            verifs["traduction_fr"] = bool(resume.get("traduction_fr"))
            verifs["icones_navigation"] = all(
                not b.icon().isNull() for b in fenetre.barre_laterale.boutons()
            )
            verifs["icones_feuille_de_style"] = all(
                not QIcon(chemin).isNull() and Path(chemin).exists()
                for chemin in icones_feuille_de_style().values()
            )
            verifs["journal_ecrit"] = fichier_journal().exists() and fichier_journal().stat().st_size > 0
            verifs["feuille_de_style_appliquee"] = len(app.styleSheet()) > 0

            verifs["coffre_windows"] = _verifier_coffre_windows(rapport)

            if captures_taille_fixe:
                fenetre.resize(Dimensions.FENETRE_LARGEUR, Dimensions.FENETRE_HAUTEUR)
            _laisser_afficher()
            rapport["taille_fenetre"] = [fenetre.width(), fenetre.height()]
            attendues = 0

            def capturer(widget, nom: str) -> None:
                nonlocal attendues
                attendues += 1
                _laisser_afficher()
                chemin = dossier / f"{nom}.png"
                if widget.grab().save(str(chemin)):
                    rapport["captures"].append(chemin.name)

            for identifiant in fenetre.identifiants_modules():
                fenetre.afficher_module(identifiant)
                capturer(fenetre, f"module-{identifiant}")

            # Page Voix (projet de démonstration) : bas de page (prises), puis vérification de l'éditeur.
            atelier = fenetre.page("voix").atelier
            fenetre.afficher_module("voix")
            defilement = atelier.findChild(QScrollArea)
            if defilement is not None:
                defilement.verticalScrollBar().setValue(defilement.verticalScrollBar().maximum())
                capturer(fenetre, "voix-prises")
                defilement.verticalScrollBar().setValue(0)
            verifs["editeur_badges"] = atelier.editeur.segments() == normaliser([dict(s) for s in SCRIPT_DEMO])
            rapport["texte_api_demo"] = atelier.editeur.texte_api()
            verifs["lecture_audio"] = atelier.lecteur._lecteur is not None  # Qt Multimedia embarqué

            # Chaque onglet des Réglages, puis le dialogue d'ajout de clé.
            reglages = fenetre.page("reglages")
            fenetre.afficher_module("reglages")
            for index in range(reglages.onglets.count()):
                reglages.onglets.setCurrentIndex(index)
                capturer(fenetre, f"reglages-{index + 1}")
            reglages.onglets.setCurrentIndex(0)
            dialogue = reglages.connexions.ajouter()
            capturer(dialogue, "dialogue-ajout-cle")
            dialogue.reject()

            galerie = GalerieComposants()
            galerie.show()
            capturer(galerie, "galerie-composants")
            galerie.close()
            verifs["captures"] = len(rapport["captures"]) == attendues
        except Exception:  # noqa: BLE001 — tout problème doit finir dans le rapport
            rapport["erreurs"].append(traceback.format_exc())

        rapport["succes"] = not rapport["erreurs"] and all(
            verifs.get(nom) for nom in VERIFICATIONS_OBLIGATOIRES
        )
        (dossier / "autotest.json").write_text(
            json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        app.exit(0 if rapport["succes"] else 1)

    QTimer.singleShot(DELAI_DEMARRAGE_MS, executer)
    QTimer.singleShot(DELAI_MAX_MS, lambda: app.exit(CODE_DELAI_DEPASSE))
