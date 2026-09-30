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
from PySide6.QtCore import QPoint, Qt, QTimer, qVersion
from PySide6.QtGui import QFontDatabase, QFontInfo, QIcon, QImageReader
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QWidget

from . import __version__
from .chemins import fichier_journal
from .demo import SCRIPT_DEMO
from .script import normaliser
from .ui.dialogues.assistant_style import DialogueAssistantStyle
from .ui.dialogues.assistant_voix import DialogueAssistantVoix
from .ui.dialogues.comparaison import DialogueComparaison
from .ui.dialogues.prononciation import DialoguePrononciation
from .ui.dialogues.styles import DialogueBibliothequeStyles, DialogueStyle
from .ui.dialogues.variantes import ONGLET_MEMES_REGLAGES, ONGLET_PAR_VARIANTE, DialogueVariantes
from .ui.dialogues.voice_design import DialogueVoiceDesign
from .ui.dialogues.voix import DialogueBibliothequeVoix
from .ui.composants.choix_voix import choisir
from .voice_design import assembler_description
from .ui.galerie import GalerieComposants
from .ui.icones import icones_feuille_de_style
from .ui.polices import police
from .ui.theme import Dimensions, Typo

DELAI_DEMARRAGE_MS = 1500  # laisse la fenêtre s'afficher complètement
DELAI_MAX_MS = 120_000  # sécurité : l'autotest ne peut pas bloquer la fabrication
PAUSE_AFFICHAGE_S = 0.4
DELAI_DECODAGE_S = 15
CODE_DELAI_DEPASSE = 4

VERIFICATIONS_OBLIGATOIRES = (
    "decodage_audio",
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
    "sans_debordement",
)
ELEMENTS_SIGNALES_MAX = 6


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


def _description(element: QWidget) -> str:
    """« Bouton « Écouter » (min. 118 px) » : pour savoir quel élément corriger."""
    texte = ""
    for nom in ("text", "currentText"):
        methode = getattr(element, nom, None)
        if callable(methode):
            try:
                texte = methode()
            except TypeError:
                continue
            if isinstance(texte, str) and texte:
                break
            texte = ""
    minimum = element.minimumSizeHint().width()
    nom = type(element).__name__
    return f"{nom} « {texte[:40]} » (min. {minimum} px)" if texte else f"{nom} (min. {minimum} px)"


def _debordements(racine: QWidget, nom: str) -> list[str]:
    """Contenus plus larges que la place disponible, dans une fenêtre ou une page.

    - Zone défilante sans barre horizontale : si son contenu est plus large que la partie
      visible, le bord droit est coupé (rien ne permet de le voir).
    - Fenêtre dont la disposition demande plus de largeur qu'elle n'en a : les éléments sont
      écrasés (textes abrégés, chevauchements).
    - Fenêtre de dialogue plus haute que l'écran d'un portable : ses boutons du bas seraient
      inaccessibles.
    Chaque problème cite les éléments qui dépassent, avec leur largeur minimale."""
    problemes = []
    if isinstance(racine, QDialog) and racine.height() > Dimensions.DIALOGUE_HAUTEUR_MAX:
        problemes.append(f"{nom} : {racine.height()} px de haut (au plus {Dimensions.DIALOGUE_HAUTEUR_MAX})")
    disposition = racine.layout() if racine.isWindow() else None
    if disposition is not None and disposition.minimumSize().width() > racine.width():
        problemes.append(
            f"{nom} : il faudrait {disposition.minimumSize().width()} px de large, la fenêtre en a {racine.width()}"
        )
    for zone in racine.findChildren(QScrollArea):
        interieur = zone.widget()
        if (
            interieur is None
            or not zone.isVisible()
            or zone.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        ):
            continue
        visible = zone.viewport().width()
        exces = interieur.width() - visible
        if exces <= 0:
            continue

        def deborde(element: QWidget) -> bool:
            return element.isVisible() and element.mapTo(zone.viewport(), QPoint(element.width(), 0)).x() > visible

        # Les éléments « au bout de la chaîne » qui dépassent (pas leurs conteneurs).
        coupables = [
            element
            for element in interieur.findChildren(QWidget)
            if deborde(element)
            and not any(
                deborde(enfant)
                for enfant in element.findChildren(QWidget, "", Qt.FindChildOption.FindDirectChildrenOnly)
            )
        ]
        coupables.sort(key=lambda e: e.minimumSizeHint().width(), reverse=True)
        problemes.append(
            f"{nom} : contenu plus large que la partie visible de {exces} px — "
            + ", ".join(_description(e) for e in coupables[:ELEMENTS_SIGNALES_MAX])
        )
    return problemes


def _assistant_rempli(parent) -> DialogueAssistantStyle:
    """Assistant de style avec quelques choix faits, pour une capture parlante."""
    dialogue = DialogueAssistantStyle(parent)
    for liste, valeur in ((dialogue.emotion, "chaleureux"), (dialogue.emotion2, "enthousiaste"), (dialogue.rythme, "débit rapide")):
        liste.setCurrentIndex(liste.findData(valeur))
    return dialogue


def _assistant_voix_rempli(parent) -> DialogueAssistantVoix:
    dialogue = DialogueAssistantVoix(parent)
    for liste, valeur in (
        (dialogue.age, "environ 25 ans"),
        (dialogue.timbre, "chaleureuse"),
        (dialogue.texture, "légèrement voilée"),
        (dialogue.accent, "parisien"),
        (dialogue.persona, "créateur·rice UGC"),
    ):
        liste.setCurrentIndex(liste.findData(valeur))
    return dialogue


def _voice_design_rempli(services, atelier, parent) -> DialogueVoiceDesign:
    dialogue = DialogueVoiceDesign(services, atelier.ecoute, parent)
    dialogue.nom.setText("Léa — créatrice UGC")
    dialogue.description.definir(
        *assembler_description("femme", "environ 25 ans", "chaleureuse", "légèrement voilée", "parisien", "créateur·rice UGC")
    )
    return dialogue


def _verifier_decodage_audio(dossier: Path, rapport: dict) -> bool:
    """Décode un petit WAV avec Qt Multimedia (FFmpeg), comme pour une vidéo importée (§6.2) :
    vérifie que le décodeur audio est bien embarqué dans le .exe."""
    from .audio import FREQUENCE_TTS, lire_wav, wav_depuis_pcm
    from .ui.extraction import ExtracteurAudio

    source = dossier / "decodage-test.wav"
    source.write_bytes(wav_depuis_pcm(b"\x10\x00" * FREQUENCE_TTS))  # 1 s
    extracteur = ExtracteurAudio()
    resultat: dict = {}
    extracteur.termine.connect(lambda wav: resultat.setdefault("wav", wav))
    extracteur.echec.connect(lambda raison: resultat.setdefault("erreur", raison))
    extracteur._decoder(source)  # le chemin de Qt, même pour un WAV
    fin = time.monotonic() + DELAI_DECODAGE_S
    while not resultat and time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.02)
    if "wav" in resultat:
        pcm, frequence, canaux = lire_wav(resultat["wav"])
        rapport["decodage_audio"] = f"{len(pcm) // 2 / frequence:.2f} s, {frequence} Hz, {canaux} canal"
        return abs(len(pcm) // 2 / frequence - 1.0) < 0.1 and canaux == 1
    rapport["decodage_audio"] = f"erreur : {resultat.get('erreur', 'délai dépassé')}"
    extracteur.annuler()
    return False


def _variantes_remplies(services, atelier, parent, onglet: int) -> DialogueVariantes:
    """Variantes A/B : la B change de voix et de style (valeurs surlignées en mauve)."""
    dialogue = DialogueVariantes(services, atelier.reglages_de_base(), atelier._prononciations(), parent)
    dialogue.onglets.setCurrentIndex(onglet)
    colonne_b = dialogue.colonnes()[1]
    choisir(colonne_b.voix, "Puck")
    colonne_b.styles[0].setText("warm and confident, slower")
    return dialogue


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
            debordements: list[str] = []

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
                # La page défile : une capture par hauteur d'écran, jusqu'aux prises.
                barre = defilement.verticalScrollBar()
                for numero, position in enumerate(range(barre.pageStep(), barre.maximum() + barre.pageStep(), barre.pageStep()), 2):
                    barre.setValue(min(position, barre.maximum()))
                    capturer(fenetre, f"voix-{numero}")
                barre.setValue(0)
            verifs["editeur_badges"] = atelier.editeur.segments() == normaliser([dict(s) for s in SCRIPT_DEMO])
            rapport["texte_api_demo"] = atelier.editeur.texte_api()
            verifs["lecture_audio"] = atelier.lecteur._lecteur is not None  # Qt Multimedia embarqué

            # Page Transcription (étape 7) : un mot choisi, et une capture par hauteur d'écran.
            transcription = fenetre.page("transcription").atelier
            fenetre.afficher_module("transcription")
            transcription.choisir_mot(3)
            defilement = transcription.findChild(QScrollArea)
            if defilement is not None:
                barre = defilement.verticalScrollBar()
                for numero, position in enumerate(range(barre.pageStep(), barre.maximum() + barre.pageStep(), barre.pageStep()), 2):
                    barre.setValue(min(position, barre.maximum()))
                    capturer(fenetre, f"transcription-{numero}")
                barre.setValue(0)
            verifs["decodage_audio"] = _verifier_decodage_audio(dossier, rapport)

            # Chaque onglet des Réglages, puis le dialogue d'ajout de clé.
            reglages = fenetre.page("reglages")
            fenetre.afficher_module("reglages")
            for index in range(reglages.onglets.count()):
                reglages.onglets.setCurrentIndex(index)
                capturer(fenetre, f"reglages-{index + 1}")
                # Onglet plus haut que la fenêtre : capture du bas de l'onglet aussi.
                defilement = reglages.onglets.widget(index).findChild(QScrollArea)
                if defilement is not None and defilement.verticalScrollBar().maximum() > 0:
                    defilement.verticalScrollBar().setValue(defilement.verticalScrollBar().maximum())
                    capturer(fenetre, f"reglages-{index + 1}-bas")
                    defilement.verticalScrollBar().setValue(0)
            reglages.onglets.setCurrentIndex(0)

            # Menu « Projet » du bandeau : icônes et texte, avec le même écart que partout.
            bouton_projet, menu_projet = fenetre.entete.bouton_projet, fenetre.entete.menu_projet
            menu_projet.popup(bouton_projet.mapToGlobal(QPoint(0, bouton_projet.height())))
            capturer(menu_projet, "menu-projet")
            menu_projet.hide()

            dialogue = reglages.connexions.ajouter()
            capturer(dialogue, "dialogue-ajout-cle")
            dialogue.reject()

            # Fenêtres de l'étape 4 : bibliothèque de styles, style, assistant, prononciation.
            services = fenetre.services
            carte = atelier.repliques.cartes()[0]
            for nom, fenetre_dialogue in (
                (
                    "bibliotheque-styles",
                    DialogueBibliothequeStyles(
                        services, fenetre, cible="réplique 1",
                        style_actuel=(carte.champ_style.consigne(), carte.champ_style.consigne_fr()),
                    ),
                ),
                ("dialogue-style", DialogueStyle(services, services.styles.styles[0], fenetre, "Modifier le style")),
                ("assistant-style", _assistant_rempli(fenetre)),
                ("dialogue-prononciation", DialoguePrononciation(services, None, fenetre)),
                # Étape 5 : bibliothèque de voix (deux onglets), Voice Design et son assistant.
                ("bibliotheque-voix", DialogueBibliothequeVoix(services, atelier.lecteur, fenetre)),
                ("bibliotheque-voix-mes-voix", DialogueBibliothequeVoix(services, atelier.lecteur, fenetre, onglet=1)),
                ("dialogue-voice-design", _voice_design_rempli(services, atelier, fenetre)),
                ("assistant-voix", _assistant_voix_rempli(fenetre)),
                # Étape 6 : variantes A/B (deux onglets) et écoute comparative de la série de démonstration.
                ("dialogue-variantes", _variantes_remplies(services, atelier, fenetre, ONGLET_PAR_VARIANTE)),
                (
                    "dialogue-variantes-memes-reglages",
                    _variantes_remplies(services, atelier, fenetre, ONGLET_MEMES_REGLAGES),
                ),
                ("dialogue-comparaison", DialogueComparaison(services, 1, fenetre)),
            ):
                fenetre_dialogue.show()
                capturer(fenetre_dialogue, nom)
                debordements += _debordements(fenetre_dialogue, f"fenêtre {nom}")
                fenetre_dialogue.reject()

            # Fenêtre principale à sa largeur minimale : chaque page doit y tenir sans être coupée.
            fenetre.resize(Dimensions.FENETRE_LARGEUR_MIN, fenetre.height())
            for identifiant in fenetre.identifiants_modules():
                fenetre.afficher_module(identifiant)
                _laisser_afficher()
                debordements += _debordements(fenetre, f"page {identifiant}")
            fenetre.afficher_module("reglages")
            for index in range(reglages.onglets.count()):
                reglages.onglets.setCurrentIndex(index)
                _laisser_afficher()
                debordements += _debordements(fenetre, f"réglages, onglet « {reglages.onglets.tabText(index)} »")
            reglages.onglets.setCurrentIndex(0)
            fenetre.afficher_module("voix")
            rapport["debordements"] = debordements
            verifs["sans_debordement"] = not debordements

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
