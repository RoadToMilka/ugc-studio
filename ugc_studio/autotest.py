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
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, qVersion
from PySide6.QtGui import QColor, QFontDatabase, QFontInfo, QIcon, QImage, QImageReader, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QScrollArea, QWidget

from . import __version__
from .chemins import fichier_journal
from .conseils_des_pages import PAGES
from .demo import SCRIPT_DEMO
from .projets import RepliqueProjet
from .script import normaliser
from .ui.composants.bouton import Bouton
from .ui.composants.bulle import bulle as la_bulle
from .ui.composants.bulle import bulle_visible, cacher_bulle
from .ui.composants.conseils import DialogueConseils
from .ui.composants.defilement import ZoneDefilante
from .ui.composants.elements import BoutonInfo, Info
from .ui.composants.menu import position_du_menu
from .ui.composants.tableau import Tableau
from .ui.dialogues.assistant_style import DialogueAssistantStyle
from .ui.dialogues.assistant_voix import DialogueAssistantVoix
from .ui.dialogues.briefs import DialogueBibliothequeBriefs
from .ui.dialogues.choix_modeles import DialogueChoixModeles
from .ui.dialogues.comparaison import DialogueComparaison
from .ui.dialogues.comparer_scripts import DialogueComparerScripts
from .ui.dialogues.couleur import DialogueCouleur
from .ui.dialogues.meilleurs_scripts import DialogueAjoutExemple, DialogueMeilleursScripts
from .ui.dialogues.messages import DialogueMessage
from .ui.dialogues.projet import DialogueNouveauProjet
from .ui.dialogues.prononciation import DialoguePrononciation
from .ui.dialogues.retouche import DialogueRetouche
from .ui.dialogues.styles import DialogueBibliothequeStyles, DialogueStyle
from .ui.dialogues.variantes import ONGLET_MEMES_REGLAGES, ONGLET_PAR_VARIANTE, DialogueVariantes
from .ui.dialogues.variantes_script import ONGLET_ACCROCHES, DialogueVariantesScript
from .ui.dialogues.variantes_script import ONGLET_PAR_VARIANTE as ONGLET_SCRIPT_PAR_VARIANTE
from .ui.dialogues.voice_design import DialogueVoiceDesign
from .ui.dialogues.voix import DialogueBibliothequeVoix
from .ui.composants.choix_voix import choisir
from .ui.erreurs import erreurs_autotest
from .voice_design import assembler_description
from .ui.galerie import GalerieComposants
from .ui.icones import icones_feuille_de_style
from .ui.polices import police
from .ui.theme import Couleurs, Dimensions, Espacements, Hauteurs, Typo, qcolor

DELAI_DEMARRAGE_MS = 1500  # laisse la fenêtre s'afficher complètement
DELAI_MAX_MS = 240_000  # sécurité : l'autotest ne peut pas bloquer la fabrication (exports vidéo compris)
DELAI_EXPORT_S = 90  # un export de la vidéo de démonstration (7,4 s) : quelques secondes d'habitude
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
    "sous_titres",
    "reorganisation",
    "module_script",
    "script_lot2",
    "lecture_video",
    "studio",
    "style_texte",
    "mots_du_studio",
    "animations",
    "ffmpeg_integre",
    "calque",
    "video_avec_sous_titres",
    "video_hdr",
    "disposition_v31",
    "liste_deroulante",
    "aides_v31",
    "disposition_studio",
    "zone_source",
    "frise_et_prereglages",
    "bulle_v32",
    "menu_v32",
    "fenetres_v32",
)
ELEMENTS_SIGNALES_MAX = 6
# V3.1, lot 5 : la page Sous-titres en grande fenêtre (écran de 1080 px, fenêtre agrandie : la barre
# des tâches et le titre de Windows en moins), puis sur un grand écran (1440 px).
GRANDE_FENETRE = (1920, 1010)
TRES_GRANDE_FENETRE = (2560, 1400)
# V3.1 (§9.4 ter) : les seules phrases d'aide qui restent écrites dans les modules (leur début),
# celles qui disent quoi faire à ce moment ; toutes les autres sont dans une icône « i ». Une même
# phrase peut s'afficher plusieurs fois (ex. sur chaque carte d'un script TikTok).
PHRASES_INDISPENSABLES = (
    "Vidéo (MP4, MOV, MKV…) ou audio",
    "Clique sur un mot pour le corriger",
    "La langue du projet est",
    "Noms que la voix pourrait mal prononcer",
    "Coche celles qui te plaisent",
    "Voix générée par l'IA : active l'étiquette",
    "Un projet regroupe",
    "Pipette : clique dans l'aperçu",
    "Vidéo avec sous-titres : il faut une vidéo",
    "Ces sous-titres ne viennent pas d'une prise",
    "Le format suit la vidéo",
    "Taux de départ, à vérifier",
)


def _verifier_variantes_script(dialogue) -> bool:
    champs = dialogue.colonnes()[1].champs
    return all(bool(champs[nom].property("modifie")) for nom in ("angle", "duree_s", "accroche")) and not bool(
        champs["reseau"].property("modifie")
    )


def _verifier_comparaison(dialogue) -> bool:
    """Au départ : la retouche de démonstration (script 6) à côté de son original (script 1)."""
    noms = [colonne.script.nom() if colonne.script else "" for colonne in dialogue.colonnes()]
    return noms == ["Script 1", "Script 6", ""]


def _verifier_retouche(dialogue) -> bool:
    """« Plus court » : durée visée réduite d'un quart (25 s → 19 s), consigne complétée."""
    return dialogue.duree.value() == 19 and dialogue.texte_consigne() == "Plus court, plus drôle"


def _verifier_variantes_d_accroches(dialogue) -> bool:
    """Une variante par accroche : seule la réplique 1 change (surlignée en mauve)."""
    from .variantes import TEXTE, differences

    variantes = dialogue.variantes()
    return len(variantes) == 3 and all(differences(variantes[0], v) == {(TEXTE, 0)} for v in variantes[1:])


# Fenêtres du lot 2 vérifiées pendant leur capture (vérification « script_lot2 »).
VERIFIER_DANS_LA_FENETRE = {
    "dialogue-variantes-script": _verifier_variantes_script,
    "dialogue-comparer-scripts": _verifier_comparaison,
    "dialogue-retouche": _verifier_retouche,
    "dialogue-variantes-accroches": _verifier_variantes_d_accroches,
    "dialogue-bibliotheque-briefs": lambda dialogue: len(dialogue.lignes()) == 2,
    "dialogue-meilleurs-scripts": lambda dialogue: len(dialogue.lignes()) == 7,  # 2 gardés et 5 fournis
}


def _fenetre_comme_une_page(dialogue) -> dict:
    """V3.2, lot 3 (§9.6) : une fenêtre se présente comme une page. Le fond de l'app autour du bloc
    (mesuré sur la capture, au milieu de la marge), le bloc à 16 px des bords, les boutons du bas
    sous le bloc, sur le fond de l'app (et non dedans). La fenêtre des conseils n'a pas un bloc mais
    des cartes : seul son fond est vérifié."""
    image = dialogue.grab().toImage()
    marge = Dimensions.ESPACE_BLOCS
    milieu = round(marge / 2 * image.devicePixelRatio())
    resultat = {"fond": image.pixelColor(milieu, milieu).name().upper()}
    resultat["fond_de_l_app"] = resultat["fond"] == Couleurs.FOND.upper()
    cadre = getattr(dialogue, "cadre", None)
    if cadre is not None:
        resultat["bloc"] = [cadre.x(), cadre.y()]
        resultat["bloc_a_16_px"] = cadre.property("role") == "bloc" and (cadre.x(), cadre.y()) == (marge, marge)
        boutons = [b for b in dialogue.findChildren(Bouton) if b.parentWidget() is dialogue and b.isVisible()]
        resultat["boutons_du_bas"] = [b.text() for b in boutons]
        resultat["boutons_sous_le_bloc"] = bool(boutons) and all(
            b.geometry().top() >= cadre.geometry().bottom() + marge for b in boutons
        )
    # 3.2.1 : les fondus des zones qui défilent ont la couleur du fond derrière elles (le bloc, ou le
    # fond de l'app pour une zone posée sur la fenêtre, comme dans « Conseils »).
    zones = dialogue.findChildren(ZoneDefilante)
    attendues = [Couleurs.SURFACE if cadre is not None and cadre.isAncestorOf(zone) else Couleurs.FOND for zone in zones]
    resultat["fondus"] = [zone.fondus.couleur() for zone in zones]
    resultat["fondus_couleur_du_fond"] = resultat["fondus"] == attendues
    verifiees = ("fond_de_l_app", "bloc_a_16_px", "boutons_sous_le_bloc", "fondus_couleur_du_fond")
    resultat["ok"] = all(valeur for cle, valeur in resultat.items() if cle in verifiees)
    return resultat


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
    if not texte and element.property("role") == "bloc":
        # Un bloc : on le reconnaît à son titre (ex. bloc « Réglages »).
        titres = [e for e in element.findChildren(QLabel) if e.property("role") == "titre-bloc"]
        nom, texte = "bloc", titres[0].text() if titres else ""
    return f"{nom} « {texte[:40]} » (min. {minimum} px)" if texte else f"{nom} (min. {minimum} px)"


def _debordements(racine: QWidget, nom: str) -> list[str]:
    """Contenus plus larges que la place disponible, dans une fenêtre ou une page.

    - Zone défilante sans barre horizontale : si son contenu est plus large que la partie
      visible, le bord droit est coupé (rien ne permet de le voir).
    - Fenêtre dont la disposition demande plus de largeur qu'elle n'en a : les éléments sont
      écrasés (textes abrégés, chevauchements).
    - Fenêtre de dialogue plus haute que l'écran d'un portable : ses boutons du bas seraient
      inaccessibles.
    - Tableau (§9.4 septies) : colonne de dates, nombres ou montants coupée, ou colonnes cachées à
      droite sans barre de défilement pour aller les voir.
    Chaque problème cite les éléments qui dépassent, avec leur largeur minimale."""
    problemes = []
    if isinstance(racine, QDialog) and racine.height() > Dimensions.DIALOGUE_HAUTEUR_MAX:
        problemes.append(f"{nom} : {racine.height()} px de haut (au plus {Dimensions.DIALOGUE_HAUTEUR_MAX})")
    disposition = racine.layout() if racine.isWindow() else None
    if disposition is not None and disposition.minimumSize().width() > racine.width():
        problemes.append(
            f"{nom} : il faudrait {disposition.minimumSize().width()} px de large, la fenêtre en a {racine.width()}"
        )
    for tableau in racine.findChildren(Tableau):
        if not tableau.isVisible() or tableau.rowCount() == 0:
            continue
        coupees = tableau.colonnes_coupees()
        if coupees:
            problemes.append(f"{nom} : tableau, colonnes coupées : {', '.join(coupees)}")
        largeur, visible = tableau.horizontalHeader().length(), tableau.viewport().width()
        if largeur > visible and tableau.horizontalScrollBar().maximum() == 0:
            problemes.append(f"{nom} : tableau de {largeur} px dans {visible} px, sans barre de défilement")
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
        if not coupables:
            # Rien n'est encore coupé (la marge de droite a absorbé l'excès) : on cite les blocs
            # les plus larges (celui qui impose la largeur vient en premier), puis les éléments
            # visibles les plus larges (ex. une case à cocher au texte trop long).
            visibles = [e for e in interieur.findChildren(QWidget) if e.isVisible()]
            blocs = [e for e in visibles if e.property("role") == "bloc"]
            feuilles = [
                e
                for e in visibles
                if not any(enfant.isVisible() for enfant in e.findChildren(QWidget, "", Qt.FindChildOption.FindDirectChildrenOnly))
            ]
            blocs.sort(key=lambda e: e.minimumSizeHint().width(), reverse=True)
            feuilles.sort(key=lambda e: e.minimumSizeHint().width(), reverse=True)
            coupables = blocs[:2] + feuilles[: ELEMENTS_SIGNALES_MAX - 2]
        coupables.sort(key=lambda e: e.minimumSizeHint().width(), reverse=True)
        problemes.append(
            f"{nom} : contenu plus large que la partie visible de {exces} px : "
            + ", ".join(_description(e) for e in coupables[:ELEMENTS_SIGNALES_MAX])
        )
    return problemes


def _disposition_de_la_fenetre(fenetre) -> dict:
    """V3.1, lot 1 : dans chaque module, le bandeau montre l'en-tête de la page affichée, et le
    premier bloc est à 16 px de la barre latérale, du bandeau et du bord droit de la fenêtre (avec
    ou sans barre de défilement, qui est au bord de la fenêtre). Le titre du bandeau s'aligne sur le
    bord gauche des blocs, le coût de la session sur leur bord droit."""
    espace = Dimensions.ESPACE_BLOCS
    mesures: dict = {"largeur_fenetre": fenetre.width(), "barre_laterale": fenetre.barre_laterale.width(), "modules": {}}
    ecarts: list[str] = []
    cout = fenetre.entete.cout_session
    droite_cout = cout.mapTo(fenetre, QPoint(cout.width(), 0)).x()
    for identifiant in fenetre.identifiants_modules():
        fenetre.afficher_module(identifiant)
        _laisser_afficher()
        page = fenetre.page_affichee()
        page.defilement.verticalScrollBar().setValue(0)
        _laisser_afficher()
        premier = page.contenu.itemAt(0)
        colonne = page.contenu.parentWidget()
        cadre = premier.geometry()
        gauche = colonne.mapTo(fenetre, cadre.topLeft()).x()
        haut = colonne.mapTo(fenetre, cadre.topLeft()).y()
        droite = colonne.mapTo(fenetre, QPoint(cadre.x() + cadre.width(), 0)).x()
        barre = page.defilement.verticalScrollBar()
        entete = fenetre.entete.entete_affichee()
        titre = entete.titre.mapTo(fenetre, QPoint(0, 0)).x() if entete is not None else None
        module = {
            "bloc": [gauche, haut, fenetre.width() - droite],
            "barre_visible": barre.isVisible(),
            "barre_au_bord": barre.mapTo(fenetre, QPoint(barre.width(), 0)).x() if barre.isVisible() else None,
            "titre": entete.titre.text() if entete is not None else None,
            "conseils": entete.conseils.property("conseils") if entete is not None and entete.conseils else None,
            "x_titre": titre,
        }
        mesures["modules"][identifiant] = module
        attendu = (Dimensions.LARGEUR_BARRE_LATERALE + espace, Hauteurs.BANDEAU + espace, espace)
        if tuple(module["bloc"]) != attendu:
            ecarts.append(f"{identifiant} : bloc à {module['bloc']} (attendu {list(attendu)})")
        if entete is None or entete is not page.entete:
            ecarts.append(f"{identifiant} : le bandeau ne montre pas l'en-tête de la page")
        elif titre != gauche:
            ecarts.append(f"{identifiant} : titre à {titre} px, blocs à {gauche} px")
        if module["barre_au_bord"] not in (None, fenetre.width()):
            ecarts.append(f"{identifiant} : barre de défilement à {module['barre_au_bord']} px du bord gauche")
    mesures["droite_cout"] = fenetre.width() - droite_cout
    if fenetre.width() - droite_cout != espace:
        ecarts.append(f"coût de la session à {fenetre.width() - droite_cout} px du bord droit")
    if fenetre.barre_laterale.width() != Dimensions.LARGEUR_BARRE_LATERALE:
        ecarts.append(f"barre latérale de {fenetre.barre_laterale.width()} px")
    mesures["ecarts"] = ecarts
    return mesures


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
    dialogue.nom.setText("Léa, créatrice UGC")
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


def _attendre(condition, secondes: float = DELAI_DECODAGE_S) -> bool:
    fin = time.monotonic() + secondes
    while not condition() and time.monotonic() < fin:
        QApplication.processEvents()
        time.sleep(0.02)
    return bool(condition())


def _attendre_sans_pause(condition, secondes: float) -> bool:
    """Comme _attendre, mais la boucle de Qt tourne comme dans l'app, sans les petites pauses de
    _attendre : un export (dessiné par tranches dans la tâche principale) y va à sa vraie vitesse."""
    from PySide6.QtCore import QEventLoop

    if condition():
        return True
    boucle = QEventLoop()
    verification = QTimer()
    verification.timeout.connect(lambda: boucle.quit() if condition() else None)
    verification.start(50)
    limite = QTimer()
    limite.setSingleShot(True)
    limite.timeout.connect(boucle.quit)
    limite.start(round(secondes * 1000))
    boucle.exec()
    verification.stop()
    limite.stop()
    return bool(condition())


def _verifier_lecture_video(atelier) -> dict:
    """V2, lot 3 : le .exe lit-il une vidéo, image par image ? La vidéo de démonstration (AVI Motion
    JPEG, rendu/video_test.py) : première image reçue (taille, couleur du haut), puis 1,5 s de
    lecture : le temps des sous-titres avance avec les images."""
    from .rendu.video_test import COULEUR_HAUT

    resultat: dict = {"video": atelier.lecteur.video}
    if not _attendre(lambda: atelier.toile._image is not None):
        resultat["erreur"] = "aucune image reçue de la vidéo"
        resultat["ok"] = False
        return resultat
    image = atelier.toile._image.toImage()
    attendue = QColor(COULEUR_HAUT)
    couleur = image.pixelColor(image.width() // 2, 4)
    resultat["taille"] = [image.width(), image.height()]
    resultat["couleur_haut"] = [couleur.red(), couleur.green(), couleur.blue()]
    ecart = abs(couleur.red() - attendue.red()) + abs(couleur.green() - attendue.green()) + abs(couleur.blue() - attendue.blue())
    depart = atelier.lecteur.temps
    atelier.basculer_lecture()
    _laisser_afficher(1.5)
    resultat["en_lecture"] = atelier.lecteur.en_lecture()
    resultat["temps_avance_s"] = round(atelier.lecteur.temps - depart, 2)
    if atelier.lecteur.en_lecture():
        atelier.basculer_lecture()  # pause
    _laisser_afficher()
    resultat["ok"] = resultat["taille"] == [540, 960] and ecart < 90 and resultat["temps_avance_s"] > 0.5
    return resultat


def _variantes_remplies(services, atelier, parent, onglet: int) -> DialogueVariantes:
    """Variantes A/B : la B change de voix et de style (valeurs surlignées en mauve)."""
    dialogue = DialogueVariantes(services, atelier.reglages_de_base(), atelier._prononciations(), parent)
    dialogue.onglets.setCurrentIndex(onglet)
    colonne_b = dialogue.colonnes()[1]
    choisir(colonne_b.voix, "Puck")
    colonne_b.styles[0].setText("warm and confident, slower")
    return dialogue


def _variantes_script_remplies(services, ecriture, parent, onglet: int) -> DialogueVariantesScript:
    """Variantes de script : la B change d'angle, de durée et d'accroche (valeurs surlignées en mauve)."""
    brief = services.projets.projet.ecriture.brief
    dialogue = DialogueVariantesScript(
        services, brief, ecriture._texte_page(), ecriture._exemples(brief), ecriture._mots_par_seconde(), parent
    )
    dialogue.onglets.setCurrentIndex(onglet)
    colonne_b = dialogue.colonnes()[1].champs
    choisir(colonne_b["angle"], "pov")
    colonne_b["duree_s"].setValue(15)
    colonne_b["accroche"].setText("POV : ton teint a l'air d'avoir dormi huit heures.")
    return dialogue


def _retouche_remplie(services, ecriture, parent) -> DialogueRetouche:
    etat = services.projets.projet.ecriture
    dialogue = DialogueRetouche(
        services, etat.scripts[0], etat.brief, ecriture._texte_page(), ecriture._mots_par_seconde(), parent
    )
    dialogue.ajouter_suggestion("Plus court", -0.25)
    dialogue.ajouter_suggestion("Plus drôle", 0.0)
    return dialogue


def _variantes_d_accroches(services, atelier, parent) -> DialogueVariantes:
    """Voix : une variante par accroche de la série « Accroches seulement » de démonstration. Comme
    dans l'app, les réglages de base sont ceux de la variante A (son script est dans l'atelier)."""
    serie = [s for s in services.projets.projet.ecriture.scripts if s.serie]
    depart = atelier.reglages_de_base()
    variantes = []
    for script in serie:
        variante = depart.copie()
        premiere = script.repliques[0]
        variante.repliques[0] = RepliqueProjet([dict(s) for s in premiere.script], premiere.style, premiere.style_fr)
        variantes.append(variante)
    return DialogueVariantes(services, variantes[0], atelier._prononciations(), parent, atelier._nombres(), variantes)


def _studio(atelier, capturer, rapport: dict) -> bool:
    """V2, lot 3 : le studio des sous-titres. Fond damier et grille, zoom 100 %, chaque onglet des
    réglages, sous-titre en haut et aligné à gauche ; puis tout revient comme avant (la suite de
    l'autotest réorganise les sous-titres de démonstration)."""
    from .style_sous_titres import BAS, CENTRE, GAUCHE, HAUT
    from .ui.composants.apercu import FOND_DAMIER, FOND_VIDEO, ZOOM_AJUSTE, ZOOM_REEL
    from .ui.pages.sous_titres.reglages import ONGLET_POSITION

    bloc, panneau, toile = atelier.bloc_apercu, atelier.panneau, atelier.toile
    depart = atelier.reglages_du_projet()
    rapport["studio_disposition"] = atelier.studio.mode
    largeur, limite = atelier.studio.width(), atelier.studio.largeur_deux_colonnes()
    rapport["studio_largeur_deux_colonnes"] = limite
    if largeur < limite:
        colonnes_ok = not atelier.studio.cote_a_cote
    elif largeur >= limite + Dimensions.BARRE_DEFILEMENT + Espacements.S:
        colonnes_ok = atelier.studio.cote_a_cote
    else:
        colonnes_ok = True  # entre les deux : la disposition d'avant est gardée (voir DispositionStudio)
    etat = {
        # Aperçu et apparence côte à côte dans une fenêtre large, l'un sous l'autre dans une fenêtre
        # étroite (écran de la fabrication).
        "colonnes_selon_la_largeur": colonnes_ok,
        "sous_titre_affiche": toile.sous_titre is not None,
        "taille_video": list(toile.taille_video()),
        "video_en_fond": toile.montre_la_video(),
    }
    bloc.fond.bouton(FOND_DAMIER).click()
    bloc.repere_grille.setChecked(True)
    capturer(atelier.window(), "studio-damier-grille")
    bloc.zoom.bouton(ZOOM_REEL).click()
    capturer(atelier.window(), "studio-100")
    etat["zoom_100"] = (toile.width(), toile.height()) == tuple(round(c / toile.devicePixelRatioF()) for c in toile.taille_video())
    bloc.zoom.bouton(ZOOM_AJUSTE).click()
    bloc.repere_grille.setChecked(False)
    bloc.fond.bouton(FOND_VIDEO).click()
    for index in range(panneau.onglets.count()):
        panneau.onglets.setCurrentIndex(index)
        capturer(atelier.window(), f"studio-onglet-{index + 1}")
    panneau.onglets.setCurrentIndex(ONGLET_POSITION)
    panneau.verticale.bouton(HAUT).click()
    panneau.alignement.bouton(GAUCHE).click()
    rect, video = toile.rect_du_sous_titre(), toile.rect_video()
    etat["en_haut"] = rect is not None and rect.top() < video.center().y()
    etat["a_gauche"] = rect is not None and rect.left() < video.center().x() - rect.width() / 4
    capturer(atelier.window(), "studio-haut-gauche")
    panneau.alignement.bouton(CENTRE).click()
    panneau.verticale.bouton(BAS).click()
    etat["changements_appliques"] = (
        atelier.reglages_du_projet().position.verticale == BAS and atelier.reglages_du_projet().position.alignement == CENTRE
    )
    panneau.onglets.setCurrentIndex(0)
    _remettre_les_reglages(atelier, depart)
    etat["retour_au_depart"] = atelier.reglages_du_projet() == depart
    rapport["studio"] = etat
    return all(etat.values())


def _disposition_du_studio(fenetre, atelier, capturer, rapport: dict) -> bool:
    """V3.1, lot 5 : la page Sous-titres selon la taille de la fenêtre.

    - Taille de départ : la zone de l'aperçu a exactement la taille de la vidéo affichée (plus de
      bandes sombres) ; Source à gauche d'Exporter dès 880 px de page.
    - Grande fenêtre (1920 × 1010) : trois colonnes, Aperçu | Apparence | Sous-titres, à la même
      hauteur, la frise dessous sur toute la largeur, Source et Exporter au-dessus ; l'apparence
      défile seule (l'aperçu ne bouge pas). V3.2 : la vidéo fait 640 px de haut et le bloc de
      l'aperçu se voit en entier dans la page visible ; « Fond » et « Zoom » côte à côte, les trois
      repères sur une ligne. (Jusqu'à la 3.1.3 : la page défilait au plus de la hauteur de la bande du
      haut, et la vidéo n'avait que la place qui restait.)
    - Coins arrondis de l'aperçu (V3.2) : le coin de la zone a la couleur du bloc.
    - Très grande fenêtre (2560 × 1400) : tout se voit sans faire défiler la page, et la vidéo dépasse
      540 px de haut.
    Sur l'écran de la fabrication (1024 × 768), la fenêtre ne peut pas grandir autant : ces deux
    mesures-là sont notées « non mesurée » (les captures sans écran, elles, les font)."""
    from .ui.pages.sous_titres.disposition import GRANDE

    studio, apercu, toile = atelier.studio, atelier.bloc_apercu, atelier.toile
    page = atelier.defilement.verticalScrollBar()
    depart = fenetre.size()

    def position(element) -> QPoint:
        return element.mapTo(fenetre, QPoint(0, 0))

    def a_la_taille_de_la_video() -> bool:
        video, zone = toile.rect_video(), apercu.zone
        return abs(zone.width() - video.width()) <= 1 and abs(zone.height() - video.height()) <= 1

    def agrandir(taille: tuple[int, int]) -> bool:
        fenetre.resize(*taille)
        _laisser_afficher()
        _laisser_afficher()  # la disposition s'adapte en deux temps (largeur, puis hauteur des colonnes)
        page.setValue(0)
        _laisser_afficher()
        return fenetre.width() >= taille[0] and fenetre.height() >= taille[1]

    page.setValue(0)
    _laisser_afficher()
    source, export = atelier.cadre_source, atelier.cadre_export
    etat: dict = {"apercu_a_la_taille_de_la_video": a_la_taille_de_la_video()}
    image_zone = apercu.zone.grab().toImage()
    etat["coins_arrondis"] = image_zone.pixelColor(0, 0).name().upper() == Couleurs.SURFACE.upper()
    if studio.width() >= Dimensions.STUDIO_DEUX_COLONNES_MIN:
        etat["source_a_gauche_d_exporter"] = (
            position(source).y() == position(export).y() and position(source).x() < position(export).x()
        )
    mesures: dict = {"depart": {"disposition": studio.mode, "zone": [apercu.zone.width(), apercu.zone.height()]}}
    debordements: list[str] = []

    if agrandir(GRANDE_FENETRE):
        colonnes = (apercu, atelier.cadre_apparence, atelier.cadre_sous_titres)
        hauts = [position(colonne).y() for colonne in colonnes]
        gauches = [position(colonne).x() for colonne in colonnes]
        frise = atelier.cadre_frise
        etat["trois_colonnes"] = (
            studio.mode == GRANDE
            and gauches[0] < gauches[1] < gauches[2]
            and len(set(hauts)) == 1
            and len({colonne.height() for colonne in colonnes}) == 1
        )
        etat["frise_dessous_sur_toute_la_largeur"] = (
            position(frise).y() >= hauts[0] + apercu.height() and frise.width() == studio.width()
        )
        etat["source_et_exporter_au_dessus"] = position(source).y() == position(export).y() < hauts[0]
        etat["grande_apercu_a_la_taille_de_la_video"] = a_la_taille_de_la_video()
        # V3.2 : une vidéo de 640 px de haut, dont le bloc tient dans la page visible.
        bande = hauts[0] - position(source).y()
        visible = studio.hauteur_visible()
        etat["grande_video_de_640_px"] = abs(apercu.zone.height() - Dimensions.APERCU_HAUTEUR_GRANDE) <= 1
        etat["grande_apercu_entier_visible"] = apercu.height() <= visible
        etat["grande_fond_et_zoom_cote_a_cote"] = position(apercu.champ_fond).y() == position(apercu.champ_zoom).y()
        cases = (apercu.repere_zone, apercu.repere_marge, apercu.repere_grille)
        etat["grande_reperes_sur_une_ligne"] = len({position(case).y() for case in cases}) == 1
        capturer(fenetre, "sous-titres-grande-fenetre")
        debordements += _debordements(fenetre, "page Sous-titres en grande fenêtre")
        # L'apparence défile seule : l'aperçu reste où il est.
        colonne = atelier.colonne_apparence
        barre, avant = colonne.verticalScrollBar(), position(apercu.zone)
        barre.setValue(barre.maximum())
        _laisser_afficher()
        etat["apparence_defile_seule"] = colonne.defile and barre.maximum() > 0 and position(apercu.zone) == avant
        page.setValue(page.maximum())
        _laisser_afficher()
        capturer(fenetre, "sous-titres-grande-fenetre-bas")
        barre.setValue(0)
        mesures["grande"] = {
            "zone": [apercu.zone.width(), apercu.zone.height()],
            "colonnes": [[colonne.x(), colonne.width(), colonne.height()] for colonne in colonnes],
            "defilement_page": page.maximum(),
            "bande": bande,
            "page_visible": visible,
            "bloc_apercu": [apercu.width(), apercu.height()],
        }
    else:
        mesures["grande"] = f"non mesurée : fenêtre de {fenetre.width()} × {fenetre.height()} au plus sur cet écran"

    if agrandir(TRES_GRANDE_FENETRE):
        etat["tres_grande_tout_visible"] = studio.mode == GRANDE and page.maximum() == 0
        etat["tres_grande_video_plus_haute"] = apercu.zone.height() > Dimensions.APERCU_HAUTEUR_MAX and a_la_taille_de_la_video()
        capturer(fenetre, "sous-titres-tres-grande-fenetre")
        debordements += _debordements(fenetre, "page Sous-titres en très grande fenêtre")
        mesures["tres_grande"] = {"zone": [apercu.zone.width(), apercu.zone.height()], "defilement_page": page.maximum()}
    else:
        mesures["tres_grande"] = f"non mesurée : fenêtre de {fenetre.width()} × {fenetre.height()} au plus sur cet écran"

    fenetre.resize(depart)
    _laisser_afficher()
    _laisser_afficher()
    page.setValue(0)
    etat["retour_a_la_taille_de_depart"] = studio.mode == mesures["depart"]["disposition"]
    etat["sans_debordement"] = not debordements
    mesures["debordements"] = debordements
    rapport["disposition_studio"] = {"etat": etat, "mesures": mesures}
    return all(etat.values())


def _remettre_les_reglages(atelier, reglages) -> None:
    """Fin d'une étape : les réglages des sous-titres du projet de démonstration redeviennent ceux du
    début, exactement (la suite de l'autotest en dépend)."""
    atelier._projet.sous_titres = reglages
    atelier._services.projets.enregistrer()
    atelier.rafraichir()
    _laisser_afficher()


def _styles_proposes() -> dict:
    """Six styles proches de ceux de l'annexe B du document V2, faits avec les seuls réglages de
    l'onglet « Texte » (le mot actif viendra aux lots 5 et 6). Tailles en % de la hauteur de la
    vidéo : pour 1920 px, 1 % = 19,2 px."""
    from .style_sous_titres import (
        CASSE_MAJUSCULES,
        FOND_LIGNE,
        FOND_MOT,
        Contour,
        Couleur,
        Degrade,
        Espaces,
        Fond,
        Lueur,
        Ombre,
        StyleTexte,
        style_de_depart,
    )

    noir, sans_ombre = Couleur(0, 0, 0), Ombre(active=False)
    return {
        "style-1-contour": style_de_depart(),
        "style-2-fond-par-mot": StyleTexte(
            police="Poppins", graisse=700, taille_pct=4.1, ombre=Ombre(True, Couleur(0, 0, 0, 55.0), 0.94, 0.0, 0.31),
            fond=Fond(FOND_MOT, Couleur(124, 58, 237), 0.94, 0.16, 1.25),
        ),
        "style-3-degrade": StyleTexte(
            police="Poppins", graisse=800, taille_pct=4.1, degrade=Degrade(True, Couleur(250, 204, 21)),
            contour=Contour(True, noir, 0.31), ombre=sans_ombre,
        ),
        "style-4-grand-contour": StyleTexte(
            police="Anton", graisse=400, taille_pct=7.8, casse=CASSE_MAJUSCULES, contour=Contour(True, noir, 0.47),
            ombre=Ombre(True, Couleur(0, 0, 0, 45.0), 1.56, 0.0, 0.94),
        ),
        "style-5-bandeau": StyleTexte(
            police="Montserrat", graisse=700, taille_pct=3.4, couleur=Couleur(17, 24, 39), ombre=sans_ombre,
            fond=Fond(FOND_LIGNE, Couleur(255, 255, 255), 1.875, 0.625, 1.5625), espaces=Espaces(interligne_pct=152.0),
        ),
        "style-6-lueur": StyleTexte(
            police="Bebas Neue", graisse=400, taille_pct=6.3, casse=CASSE_MAJUSCULES,
            ombre=Ombre(True, Couleur(0, 0, 0, 60.0), 0.625, 0.0, 0.31), lueur=Lueur(True, Couleur(245, 158, 11), 2.19, 80.0),
            espaces=Espaces(lettres_pct=0.078),
        ),
    }


def _image_du_sous_titre(toile) -> QImage | None:
    """Le sous-titre affiché, à la taille réelle de la vidéo (l'image de l'export de la V3), posé sur
    l'image de la vidéo, recadré sur lui : pour juger la netteté et les effets."""
    from .ui.theme import CouleursApercu, qcolor

    moteur, sous_titre, mots = toile._moteur, toile.sous_titre, toile._mots
    if moteur is None or sous_titre is None:
        return None
    temps = toile._temps
    image = QImage(moteur.largeur, moteur.hauteur, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(qcolor(CouleursApercu.FOND_NEUTRE))
    peintre = QPainter(image)
    if toile._image is not None:
        cadre = toile._image.toImage()
        if not cadre.isNull():
            peintre.drawImage(QRect(0, 0, moteur.largeur, moteur.hauteur), cadre)
    peintre.drawImage(QPoint(0, 0), moteur.image(sous_titre, mots, temps))
    peintre.end()
    bloc = moteur.bloc(sous_titre, mots)
    marge = round(moteur.hauteur * 0.04)
    haut = max(0, round(bloc.y) - marge)
    return image.copy(0, haut, moteur.largeur, min(moteur.hauteur - haut, round(bloc.hauteur) + 2 * marge))


def _style_texte(atelier, capturer, capturer_image, rapport: dict) -> bool:
    """V2, lot 4 : le style du texte. Polices fournies à la bonne graisse, style de départ du projet
    de démonstration, onglet « Texte » avec tous ses groupes ouverts, six styles (une image à la
    taille de la vidéo, recadrée sur le sous-titre), pipette ; puis le style de départ revient."""
    from .prereglages import appliquer as appliquer_le_prereglage
    from .rendu.moteur import police_du_texte
    from .rendu.polices import POLICES_FOURNIES, familles
    from .style_sous_titres import StyleTexte
    from .ui.composants.apercu import FOND_GRIS, FOND_VIDEO
    from .ui.composants.section_repliable import SectionRepliable
    from .ui.theme import CouleursApercu, qcolor

    panneau, texte, toile, bloc = atelier.panneau, atelier.panneau.texte, atelier.toile, atelier.bloc_apercu
    etat: dict = {}
    # 1. Polices fournies : chacune à la graisse demandée (pas une autre graisse « approchante »).
    rendus, justes = {}, []
    for famille, graisse in (("Montserrat", 800), ("Montserrat", 700), ("Poppins", 700), ("Poppins", 800), ("Anton", 400), ("Bebas Neue", 400)):
        qpolice, remplacee = police_du_texte(StyleTexte(police=famille, graisse=graisse), Typo.TITRE_PAGE)
        info = QFontInfo(qpolice)
        rendus[f"{famille} {graisse}"] = f"{info.family()} / {info.styleName()} / {info.weight()}"
        justes.append(not remplacee and info.family().startswith(famille) and info.weight() == graisse)
    rapport["polices_sous_titres"] = rendus
    etat["polices_fournies"] = familles()[: len(POLICES_FOURNIES)] == list(POLICES_FOURNIES) and all(justes)
    depart = atelier.reglages_du_projet().texte
    # Le projet de démonstration a le style de son préréglage (« Blanc contour noir », V3.1 : choisi
    # pour montrer le mot actif ; le préréglage ★ des nouveaux projets est « Par défaut »).
    origine = atelier._services.prereglages.prereglage(atelier.reglages_du_projet().prereglage)
    etat["style_du_prereglage"] = origine is not None and depart == appliquer_le_prereglage(atelier.reglages_du_projet(), origine).texte

    # 2. Onglet « Texte », tous les groupes ouverts (le panneau entier, même la partie à faire défiler).
    panneau.onglets.setCurrentIndex(0)
    sections = list(texte.sections.values()) + [s for s in texte.findChildren(SectionRepliable) if s not in texte.sections.values()]
    ouvertes = [section.est_ouverte() for section in sections]
    for section in sections:
        section.ouvrir()
    _laisser_afficher()
    capturer(panneau, "studio-texte-reglages")
    etat["onglet_texte_tient_dans_sa_colonne"] = panneau.minimumSizeHint().width() <= panneau.width()
    for section, ouverte in zip(sections, ouvertes, strict=True):
        section.ouvrir(ouverte)

    # 3. Six styles, appliqués comme depuis l'onglet (le projet est enregistré, le découpage refait).
    hauteur = toile.taille_video()[1]
    appliques = []
    for nom, style in _styles_proposes().items():
        texte.charger(style, hauteur, round(hauteur * style.taille_pct / 100), False)
        texte.change.emit()
        _laisser_afficher()
        appliques.append(
            atelier.reglages_du_projet().texte == style and not toile._moteur.police_remplacee and toile.sous_titre is not None
        )
        capturer_image(_image_du_sous_titre(toile), nom)
    rapport["styles_appliques"] = appliques
    etat["styles_appliques"] = all(appliques)
    texte.charger(depart, hauteur, round(hauteur * depart.taille_pct / 100), False)
    texte.change.emit()
    _laisser_afficher()
    capturer(atelier.window(), "studio-texte")

    # 4. Pipette : sur le fond gris, elle prend le gris (et pas les repères dessinés par-dessus).
    bloc.fond.bouton(FOND_GRIS).click()
    atelier.prendre_une_couleur(texte.couleur)
    _laisser_afficher()
    capturer(atelier.window(), "studio-pipette")
    gris = qcolor(CouleursApercu.FOND_NEUTRE)
    prise = toile.couleur_affichee(toile.rect_video().topLeft() + QPointF(Espacements.S, Espacements.S))
    attente = toile.pipette_active and not bloc.info_pipette.isHidden()
    toile.finir_pipette()
    etat["pipette"] = attente and prise == (gris.red(), gris.green(), gris.blue()) and not toile.pipette_active
    bloc.fond.bouton(FOND_VIDEO).click()
    etat["retour_au_style_de_depart"] = atelier.reglages_du_projet().texte == depart
    rapport["style_texte"] = etat
    return all(etat.values())


def _mots_du_studio(atelier, capturer, capturer_image, rapport: dict) -> bool:
    """V2, lot 5 : l'onglet Mots. Raccourcis Surlignage, Karaoké et Apparition, puis un fond qui
    glisse d'un mot à l'autre : chacun appliqué depuis l'onglet, l'aperçu placé pendant « Sérum »
    (une image à la taille de la vidéo, recadrée sur le sous-titre) ; puis le sous-titre fixe revient."""
    from dataclasses import replace

    from .style_sous_titres import ACTIF, Couleur, EtatMot, FondMot, Mots, appliquer_raccourci
    from .ui.pages.sous_titres.reglages import ONGLET_MOTS

    panneau, onglet, toile, lecteur = atelier.panneau, atelier.panneau.mots, atelier.toile, atelier.lecteur
    etat: dict = {}
    panneau.onglets.setCurrentIndex(ONGLET_MOTS)
    depart = atelier.reglages_du_projet().mots
    hauteur = toile.taille_video()[1]

    def appliquer(mots: Mots) -> None:
        onglet.charger(mots, atelier.reglages_du_projet().texte, hauteur)
        onglet.change.emit()
        _laisser_afficher()

    # « Sérum » : mot de la démonstration (demo.py), prononcé de 2,48 à 2,72 s.
    serum = next((i for i, mot in enumerate(atelier.mots) if mot.texte.casefold().startswith("sérum")), None)
    moment = atelier.mots[serum].debut + 0.12 if serum is not None else 0.0
    lecteur.aller_a(moment)
    _attendre(lambda: abs(lecteur.temps - moment) < 0.06, 3)
    actifs = {}
    for nom in ("surlignage", "karaoke", "apparition"):
        appliquer(appliquer_raccourci(Mots(), nom))
        atelier._actualiser_toile()
        actifs[nom] = toile._dessine[0] if toile._dessine else None
        capturer_image(_image_du_sous_titre(toile), f"mots-{nom}")
        if nom == "surlignage":
            capturer(atelier.window(), "studio-mots")
    etat["mot_actif"] = all(actif == serum for actif in actifs.values()) and serum is not None
    etat["raccourci_enregistre"] = atelier.reglages_du_projet().mots == appliquer_raccourci(Mots(), "apparition")
    # Fond surligné du mot actif, qui glisse depuis le mot précédent, sur la même ligne (« Sérum » →
    # « Glowzy ») : capture au milieu du glissement.
    glisse = replace(Mots(), actif=EtatMot(couleur=Couleur(255, 255, 255), fond=FondMot(glisse=True, duree_glisse_ms=400)))
    appliquer(glisse)
    glowzy = serum + 1 if serum is not None and serum + 1 < len(atelier.mots) else None
    lecteur.aller_a(atelier.mots[glowzy].debut + 0.1 if glowzy is not None else 0.0)
    atelier._actualiser_toile()
    etat["fond_qui_glisse"] = bool(toile.sous_titre and toile._moteur.en_mouvement(toile.sous_titre, toile._mots, toile._temps))
    capturer_image(_image_du_sous_titre(toile), "mots-fond-qui-glisse")
    rapport["mots_actifs"] = actifs
    appliquer(depart)
    panneau.onglets.setCurrentIndex(0)
    etat["retour_au_depart"] = atelier.reglages_du_projet().mots == depart and onglet._nom == ACTIF
    rapport["mots_du_studio"] = etat
    return all(etat.values())


def _animations(atelier, capturer, capturer_image, rapport: dict) -> bool:
    """V2, lot 6 : l'onglet Animations. Un pop sur le mot qui devient actif et un fondu à
    l'apparition du sous-titre, appliqués depuis l'onglet : captures au milieu de chaque animation
    (images à la taille de la vidéo, recadrées sur le sous-titre) ; puis plus d'animation."""
    from .style_sous_titres import AnimationMot, Animations
    from .ui.pages.sous_titres.reglages import ONGLET_ANIMATIONS

    panneau, onglet, toile, lecteur = atelier.panneau, atelier.panneau.animations, atelier.toile, atelier.lecteur
    etat: dict = {}
    panneau.onglets.setCurrentIndex(ONGLET_ANIMATIONS)
    depart = atelier.reglages_du_projet().animations
    voulues = Animations(AnimationMot("pop", 400), apparition="fondu", apparition_duree_ms=400)
    onglet.charger(voulues, toile.taille_video()[1])
    onglet.change.emit()
    _laisser_afficher()
    capturer(atelier.window(), "studio-animations")
    etat["enregistrees"] = atelier.reglages_du_projet().animations == voulues
    serum = next((i for i, mot in enumerate(atelier.mots) if mot.texte.casefold().startswith("sérum")), None)
    moments = {}
    if serum is not None:
        moments["animation-pop"] = atelier.mots[serum].debut + 0.2  # au sommet du pop (400 ms)
        sous_titre = next((s for s in atelier.sous_titres if s.premier_mot <= serum < s.dernier_mot), None)
        if sous_titre is not None:
            moments["animation-apparition"] = sous_titre.debut + 0.1
    bouge = []
    for nom, moment in moments.items():
        lecteur.aller_a(moment)
        atelier._actualiser_toile()
        bouge.append(bool(toile.sous_titre and toile._moteur.en_mouvement(toile.sous_titre, toile._mots, toile._temps)))
        capturer_image(_image_du_sous_titre(toile), nom)
    etat["en_mouvement"] = len(bouge) == 2 and all(bouge)
    onglet.charger(depart, toile.taille_video()[1])
    onglet.change.emit()
    _laisser_afficher()
    panneau.onglets.setCurrentIndex(0)
    etat["retour_au_depart"] = atelier.reglages_du_projet().animations == depart
    rapport["animations"] = etat
    return all(etat.values())


def _frise_et_prereglages(atelier, capturer, capturer_image, rapport: dict) -> bool:
    """V2, lot 7 : la frise et les préréglages.

    - Frise : un bloc par sous-titre ; un clic sur un bloc le choisit aussi dans la liste ; le bord
      commun de deux sous-titres glissé d'un mot (capture pendant le glissement), le mot passe de
      l'un à l'autre ; puis le découpage automatique est rétabli.
    - Préréglages : la ★ sur « Par défaut » (V3.1) ; le projet de démonstration part de son
      préréglage, sans « (modifié) » ni ↺ ; les 7 fournis appliqués l'un après l'autre (une image à
      la taille de la vidéo, recadrée sur le sous-titre, pendant « Sérum ») ; un réglage changé
      affiche « (modifié) », son nom en mauve et le ↺ de son groupe, qui le remet comme dans le
      préréglage (V3.1) ; la fenêtre « Préréglages de sous-titres » et ses vignettes (les 2 premières
      rangées visibles sans faire défiler, chaque nom écrit en entier) ; puis tout revient comme au
      début."""
    from .prereglages import DEFAUT_FOURNI, modifie
    from .ui.dialogues.prereglages import DialoguePrereglages
    from .ui.pages.sous_titres.reglages import ONGLET_TEXTE

    services, panneau, toile, lecteur = atelier._services, atelier.panneau, atelier.toile, atelier.lecteur
    frise = atelier.frise.toile
    bibliotheque = services.prereglages
    depart = atelier.reglages_du_projet()
    origine = bibliotheque.prereglage(depart.prereglage)
    groupes = [*panneau.texte.sections.values(), *panneau.mots.sections.values(), *panneau.animations.sections.values()]
    groupes += [panneau.mots.section_avancee, panneau.section_position, panneau.section_decoupage]
    etat: dict = {
        "etoile_sur_par_defaut": bibliotheque.par_defaut == DEFAUT_FOURNI,
        "projet_avec_son_prereglage": origine is not None
        and not modifie(depart, origine)
        and panneau.prereglage.currentText() == origine.nom,
        "aucun_retablir_au_depart": all(groupe.retablir.isHidden() for groupe in groupes),
    }

    # 1. Frise.
    atelier.defilement.ensureWidgetVisible(atelier.cadre_frise)
    etat["un_bloc_par_sous_titre"] = len(frise._sous_titres) == len(atelier.sous_titres) > 2
    frise.sous_titre_clique.emit(2, atelier.sous_titres[2].debut)
    etat["clic_choisit_dans_la_liste"] = atelier.tableau.currentRow() == 2 and frise._choisi == 2
    capturer(atelier.cadre_frise, "frise")
    glisse = None
    for index in frise.bords_communs():
        mot = atelier.sous_titres[index + 1].premier_mot + 1  # le premier mot du suivant monte
        if mot < atelier.sous_titres[index + 1].dernier_mot and not atelier._verifier_la_limite(index, mot):
            glisse = (index, mot)
            break
    if glisse is not None:
        index, mot = glisse
        frise.commencer_glissement(index)
        frise.viser(mot)
        capturer(atelier.cadre_frise, "frise-glissement")
        frise.finir_glissement()
        _laisser_afficher()
        etat["bord_glisse"] = atelier.sous_titres[index].dernier_mot == mot and atelier.sous_titres[index].ajuste
        rapport["frise_message"] = atelier.statut_frise.text()
        atelier.retablir(tous=True)
    else:
        etat["bord_glisse"] = False
    etat["decoupage_automatique_retabli"] = not any(s.ajuste for s in atelier.sous_titres)

    # 2. Les 7 préréglages fournis, appliqués depuis la liste « Préréglage ».
    serum = next((i for i, mot in enumerate(atelier.mots) if mot.texte.casefold().startswith("sérum")), 0)
    appliques = []
    for numero, prereglage in enumerate([p for p in bibliotheque.prereglages if p.fourni], 1):
        panneau.prereglage_choisi.emit(prereglage.identifiant)
        _laisser_afficher()
        lecteur.aller_a(atelier.mots[serum].debut + 0.25)
        atelier._actualiser_toile()
        reglages = atelier.reglages_du_projet()
        appliques.append(
            reglages.prereglage == prereglage.identifiant
            and not modifie(reglages, prereglage)
            and all(groupe.retablir.isHidden() for groupe in groupes)  # juste après l'avoir choisi : aucun ↺
        )
        nom = prereglage.identifiant.removeprefix("fourni-")
        capturer_image(_image_du_sous_titre(toile), f"prereglage-{numero}-{nom}")
    rapport["prereglages_appliques"] = appliques
    etat["prereglages_appliques"] = len(appliques) == 7 and all(appliques)
    # Un réglage changé (V3.1) : « (modifié) », son nom en mauve, le ↺ de son groupe (et lui seul). Le
    # découpage est en haut du bloc Sous-titres (lot 5), replié au départ.
    decoupage = panneau.section_decoupage
    etat["decoupage_dans_sous_titres"] = atelier.cadre_sous_titres.isAncestorOf(decoupage) and not decoupage.est_ouverte()
    decoupage.ouvrir()
    panneau.caracteres.setValue(panneau.caracteres.value() + 1)
    _laisser_afficher()
    nom = panneau._marques_decoupage[0][0]
    etat["modifie_affiche"] = panneau.prereglage.currentText().endswith("(modifié)")
    etat["nom_en_mauve"] = nom.property("role") == "legende-modifiee"
    etat["retablir_du_groupe_seul"] = not decoupage.retablir.isHidden() and all(
        groupe.retablir.isHidden() for groupe in groupes if groupe is not decoupage
    )
    capturer(atelier.cadre_sous_titres, "studio-decoupage-modifie")
    atelier.montrer(panneau.prereglage)  # la ligne « Préréglage (modifié) » sur la capture
    _laisser_afficher()
    capturer(atelier.window(), "studio-prereglage-modifie")
    decoupage.retablir.click()
    _laisser_afficher()
    etat["retablir_remet_le_prereglage"] = (
        not panneau.prereglage.currentText().endswith("(modifié)")
        and decoupage.retablir.isHidden()
        and nom.property("role") == "legende"
    )
    decoupage.ouvrir(False)
    # Onglet Texte : une taille changée, le ↺ à côté de « Taille et casse » (capture du panneau).
    panneau.onglets.setCurrentIndex(ONGLET_TEXTE)
    taille = panneau.texte.sections["Taille et casse"]
    panneau.texte.taille.champ.setValue(panneau.texte.taille.champ.value() + 0.5)
    _laisser_afficher()
    etat["retablir_texte_visible"] = not taille.retablir.isHidden()
    capturer(panneau, "studio-retablir-groupe")
    taille.retablir.click()
    _laisser_afficher()
    actuel = bibliotheque.prereglage(atelier.reglages_du_projet().prereglage)  # le dernier appliqué
    etat["retablir_texte_remet"] = taille.retablir.isHidden() and actuel is not None and not modifie(atelier.reglages_du_projet(), actuel)

    # 3. La fenêtre des préréglages, ses vignettes au milieu de « sérum ».
    fenetre = DialoguePrereglages(services, atelier.window(), atelier.reglages_du_projet().prereglage)
    fenetre.show()
    _laisser_afficher()
    fenetre.montrer_temps(1.0)
    capturer(fenetre, "dialogue-prereglages")
    problemes = _debordements(fenetre, "fenêtre préréglages")
    rapport["prereglages_debordements"] = problemes
    etat["fenetre_prereglages"] = len(fenetre.cartes) == len(bibliotheque.prereglages) == 7 and not problemes
    # Les 2 premières rangées (6 des 7 fournis) visibles d'un coup, chaque nom écrit en entier, ★ compris.
    sixieme = fenetre.cartes[5]
    etat["deux_rangees_sans_defiler"] = sixieme.mapTo(fenetre.zone.viewport(), QPoint(0, sixieme.height())).y() <= fenetre.zone.viewport().height()
    etat["noms_entiers"] = not any(carte.nom.est_abrege() for carte in fenetre.cartes)
    fenetre.reject()

    _remettre_les_reglages(atelier, depart)
    etat["retour_au_depart"] = atelier.reglages_du_projet() == depart and panneau.prereglage.currentText() == origine.nom
    rapport["frise_et_prereglages"] = etat
    return all(etat.values())


def _ffmpeg_integre(rapport: dict) -> bool:
    """V3, lot 1 : FFmpeg est bien dans le .exe, à sa version (9.0.2 de gyan.dev), avec les encodeurs
    des exports (ProRes, x264, x265, FFV1, AAC) ; x265 sait encoder en 10 bits (HDR, lot 3).

    Dans le .exe, FFmpeg voyage dans une ressource Windows, pas avec les fichiers recopiés à chaque
    démarrage : sa copie (dossier temporaire de l'autotest) est effacée, puis refaite comme au premier
    export (durée mesurée, empreinte vérifiée)."""
    import hashlib
    import shutil

    from .exports.ffmpeg import (
        EMPREINTE_DU_PROGRAMME,
        VERSION_INTEGREE,
        copie_de_ffmpeg,
        ffmpeg_a_preparer,
        ffmpeg_dans_le_exe,
        infos_ffmpeg,
        preparer_ffmpeg,
        programme_ffmpeg,
        programme_integre,
        version_de_x265,
    )

    gele = bool(getattr(sys, "frozen", False))
    dans_le_exe = ffmpeg_dans_le_exe()
    etat: dict = {"dans_le_exe": dans_le_exe, "pas_recopie_au_demarrage": not programme_integre().exists()}
    if dans_le_exe:
        shutil.rmtree(copie_de_ffmpeg().parent, ignore_errors=True)
        etat["a_preparer"] = ffmpeg_a_preparer() and programme_ffmpeg() is None
        debut = time.monotonic()
        try:
            chemin = preparer_ffmpeg()
        except Exception as erreur:  # noqa: BLE001 (le rapport dit pourquoi)
            etat["erreur"] = str(erreur)
            chemin = None
        etat["preparation_s"] = round(time.monotonic() - debut, 2)
        etat["empreinte_verifiee"] = bool(
            chemin and hashlib.sha256(chemin.read_bytes()).hexdigest() == EMPREINTE_DU_PROGRAMME
        )
        etat["pret_ensuite"] = not ffmpeg_a_preparer() and programme_ffmpeg() == chemin == copie_de_ffmpeg()
    else:
        chemin = programme_ffmpeg()
    infos = infos_ffmpeg(chemin) if chemin is not None else None
    voulus = ("prores_ks", "libx264", "libx265", "ffv1", "aac")
    rapport["ffmpeg"] = {
        "chemin": str(chemin),
        **etat,
        "version": infos.version if infos else "",
        "encodeurs": {nom: nom in infos.encodeurs for nom in voulus} if infos else {},
        "x265_10_bits": bool(infos and infos.x265_10_bits),
        "x265_dolby_vision": bool(infos and infos.dolby_vision_x265),  # lot 3 : Dolby Vision repris
        "x265_version": version_de_x265(chemin) if chemin is not None else "",
        "poids_mo": round(chemin.stat().st_size / 1024**2, 1) if chemin is not None and chemin.is_file() else None,
    }
    bon_endroit = (
        dans_le_exe and etat["pas_recopie_au_demarrage"] and etat["a_preparer"] and etat["empreinte_verifiee"] and etat["pret_ensuite"]
        if gele
        else chemin == programme_integre()
    )
    return bool(
        infos and bon_endroit and infos.version.startswith(VERSION_INTEGREE)
        and all(nom in infos.encodeurs for nom in voulus) and infos.x265_10_bits
    )


def _damier_sous(image: QImage) -> QImage:
    """L'image posée sur un damier (comme le fond « Damier » de l'aperçu) : on voit sa transparence."""
    from .ui.theme import CouleursApercu, qcolor

    fond = QImage(image.width(), image.height(), QImage.Format.Format_ARGB32_Premultiplied)
    peintre = QPainter(fond)
    case = Dimensions.DAMIER_CASE
    for y in range(0, image.height(), case):
        for x in range(0, image.width(), case):
            clair = (x // case + y // case) % 2 == 0
            peintre.fillRect(x, y, case, case, qcolor(CouleursApercu.DAMIER_CLAIR if clair else CouleursApercu.DAMIER_FONCE))
    peintre.drawImage(QPoint(0, 0), image)
    peintre.end()
    return fond


def _ecarts_rgba64(a: bytes, b: bytes, largeur: int, zone: QRect) -> tuple[int, int]:
    """Deux images RGBA 16 bits (transparence droite) comparées dans `zone` : plus grand écart de
    transparence, et de couleur là où les deux sont presque opaques (sur 255)."""
    import struct

    alpha = couleur = 0
    for y in range(zone.top(), zone.bottom() + 1):
        debut, fin = (y * largeur + zone.left()) * 8, (y * largeur + zone.right() + 1) * 8
        for p, q in zip(struct.iter_unpack("<4H", a[debut:fin]), struct.iter_unpack("<4H", b[debut:fin]), strict=True):
            alpha = max(alpha, abs(p[3] - q[3]))
            if p[3] > 0xF000 and q[3] > 0xF000:
                couleur = max(couleur, abs(p[0] - q[0]), abs(p[1] - q[1]), abs(p[2] - q[2]))
    return round(alpha / 257), round(couleur / 257)


def _calque(atelier, capturer, capturer_image, rapport: dict) -> bool:
    """V3, lot 1 : le calque transparent de la vidéo de démonstration, exporté depuis sa fenêtre.

    - La fenêtre (réglages et résumé avant export), pendant l'export (avancement) et à la fin.
    - Le fichier relu par FFmpeg : ProRes, autant d'images que la vidéo, à sa fréquence, à sa taille.
    - Une image relue (pendant « Sérum ») comparée à celle envoyée (fidélité du ProRes) et à l'aperçu
      (le moteur à 8 bits) : transparence et couleurs, à quelques niveaux sur 255 près.
    - Un export arrêté ne laisse rien. Les fichiers exportés sont ensuite effacés (rapport léger)."""
    from PySide6.QtGui import QImage

    from .exports.calque import ImagesDuCalque
    from .exports.ffmpeg import analyser, commande_lire_une_image, executer, programme_ffmpeg

    etat: dict = {}
    dialogue = atelier.dialogue_calque()
    dialogue.show()
    etat["analyse_finie"] = _attendre(lambda: dialogue.analyse_finie, 30)
    _laisser_afficher()
    capturer(dialogue, "dialogue-export-calque")
    problemes = _debordements(dialogue, "fenêtre d'export du calque")
    rapport["calque_debordements"] = problemes
    etat["sans_debordement"] = not problemes
    plan = dialogue.plan()
    source = dialogue.source
    rapport["calque_plan"] = {
        "sortie": plan.sortie.name, "taille": [plan.largeur, plan.hauteur], "frequence": str(plan.frequence),
        "images": plan.nombre_images, "source_images": source.nombre_images, "source_codec": source.codec_video,
        "messages": dialogue.messages_affiches(),
    }
    # La vidéo de démonstration : 74 images à 10 par seconde (comptées par FFmpeg) ; le projet est en
    # 1080 × 1920 (la vidéo, deux fois plus petite, y est agrandie, comme dans l'aperçu).
    etat["plan_de_la_video"] = (plan.largeur, plan.hauteur) == (atelier.toile.taille_video()) and plan.nombre_images == source.nombre_images == 74
    debut = time.monotonic()
    dialogue.exporter()
    _attendre(lambda: dialogue.barre.avancee() > 0.05 or not dialogue.en_cours(), 30)
    capturer(dialogue, "dialogue-export-calque-avancement")
    etat["export_fini"] = _attendre_sans_pause(lambda: not dialogue.en_cours(), DELAI_EXPORT_S)
    rapport["calque_duree_s"] = round(time.monotonic() - debut, 2)
    rapport["calque_dessin_s"] = round(dialogue.dessin_s, 2)  # temps passé à dessiner les images (le reste : FFmpeg)
    rapport["calque_images_dessinees"] = dialogue.images_dessinees
    _laisser_afficher()
    capturer(dialogue, "dialogue-export-calque-fin")
    rapport["calque_message"] = dialogue.statut.text()
    fichier = dialogue.fichier
    etat["fichier_ecrit"] = fichier is not None and fichier.is_file() and not plan.en_cours.exists()
    if etat["fichier_ecrit"]:
        rapport["calque_poids_mo"] = round(fichier.stat().st_size / 1024**2, 2)
        rapport["calque_poids_max_mo"] = round(plan.poids_max / 1024**2, 2)
        analyse = analyser(fichier)
        images = analyse.images if analyse else None
        couleurs = analyse.couleurs if analyse else None
        rapport["calque_relu"] = {
            "codec": images.codec if images else "", "images": images.nombre if images else 0,
            "frequence": str(images.frequence) if images else "", "taille": [images.largeur, images.hauteur] if images else [],
            "son": analyse.son is not None if analyse else None,
            "couleurs": [couleurs.format_pixels, couleurs.matrice, couleurs.primaires, couleurs.transfert] if couleurs else [],
        }
        etat["fichier_relu"] = bool(
            images and images.codec == "prores" and images.nombre == plan.nombre_images and images.frequence == plan.frequence
            and (images.largeur, images.hauteur) == (plan.largeur, plan.hauteur) and analyse.son is None
            and couleurs is not None and (couleurs.matrice, couleurs.primaires, couleurs.transfert) == ("bt709", "bt709", "bt709")
        )
        # Une image pendant « Sérum » : relue, envoyée, et celle de l'aperçu.
        serum = next((i for i, mot in enumerate(atelier.mots) if mot.texte.casefold().startswith("sérum")), 0)
        numero = int((atelier.mots[serum].debut + 0.15) * plan.frequence)
        temps = plan.temps(numero)
        contenu = atelier.contenu_a_exporter()
        envoyee = ImagesDuCalque(contenu.reglages, plan.largeur, plan.hauteur, contenu.sous_titres, contenu.mots).image(temps)
        lue = executer(commande_lire_une_image(programme_ffmpeg(), fichier, numero), binaire=True).stdout
        moteur = atelier.toile._moteur
        index = next(i for i, s in enumerate(contenu.sous_titres) if s.debut <= temps < s.fin)
        apercu = moteur.image(contenu.sous_titres[index], contenu.mots, temps).convertToFormat(QImage.Format.Format_RGBA64)
        apercu_octets = bytes(apercu.constBits())
        bloc = moteur.bloc(contenu.sous_titres[index], contenu.mots)
        marge = round(plan.hauteur * 0.03)
        zone = QRect(0, max(0, round(bloc.y) - marge), plan.largeur, min(plan.hauteur - max(0, round(bloc.y) - marge), round(bloc.hauteur) + 2 * marge))
        if len(lue) == len(envoyee) == len(apercu_octets):
            relu_alpha, relu_couleur = _ecarts_rgba64(envoyee, lue, plan.largeur, zone)
            apercu_alpha, apercu_couleur = _ecarts_rgba64(envoyee, apercu_octets, plan.largeur, zone)
            rapport["calque_ecarts_sur_255"] = {
                "relu_transparence": relu_alpha, "relu_couleur": relu_couleur,
                "apercu_transparence": apercu_alpha, "apercu_couleur": apercu_couleur,
            }
            # ProRes 10 bits : 3 niveaux sur 255 au plus. Aperçu (8 bits) : les lettres à 3 niveaux près,
            # les ombres et lueurs floues à quelques niveaux (le 16 bits y garde plus de nuances).
            etat["image_relue_fidele"] = relu_alpha <= 2 and relu_couleur <= 3
            etat["image_comme_l_apercu"] = apercu_alpha <= 6 and apercu_couleur <= 3
            relue = QImage(lue, plan.largeur, plan.hauteur, plan.largeur * 8, QImage.Format.Format_RGBA64).copy()
            capturer_image(_damier_sous(relue.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)).copy(zone), "calque-relu-sur-damier")
            capturer_image(_damier_sous(apercu.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)).copy(zone), "calque-apercu-sur-damier")
        else:
            rapport["calque_ecarts_sur_255"] = f"tailles différentes : {len(lue)}, {len(envoyee)}, {len(apercu_octets)}"
            etat["image_relue_fidele"] = etat["image_comme_l_apercu"] = False
        fichier.unlink(missing_ok=True)
    dialogue.accept()

    # « Arrêter » : rien n'est gardé.
    dialogue = atelier.dialogue_calque()
    dialogue.show()
    _attendre(lambda: dialogue.analyse_finie, 30)
    plan = dialogue.plan()
    dialogue.exporter()
    _attendre(lambda: dialogue.barre.avancee() > 0 or not dialogue.en_cours(), 30)
    dialogue.arreter()
    _laisser_afficher()
    etat["arreter_ne_garde_rien"] = not plan.sortie.exists() and not plan.en_cours.exists() and dialogue.statut.text().startswith("Export arrêté")
    dialogue.reject()
    rapport["calque"] = etat
    return all(etat.values())


def _point_dans_le_jaune(image: QImage, jaune: tuple[int, int, int], marge: int = 3) -> tuple[int, int] | None:
    """Un point de l'image (8 bits, transparence droite) entouré de jaune opaque sur 5 × 5 pixels : la
    couleur y est la même après le 4:2:0 de la vidéo (pas de bord tout près)."""
    def jaune_opaque(x: int, y: int) -> bool:
        couleur = image.pixelColor(x, y)
        return couleur.alpha() == 255 and all(abs(a - b) <= marge for a, b in zip((couleur.red(), couleur.green(), couleur.blue()), jaune, strict=True))

    for y in range(2, image.height() - 2, 2):
        for x in range(2, image.width() - 2, 2):
            if jaune_opaque(x, y) and all(jaune_opaque(x + dx, y + dy) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)):
                return x, y
    return None


def _video_avec_sous_titres(atelier, capturer, rapport: dict) -> bool:
    """V3, lot 2 : la vidéo de démonstration avec ses sous-titres, exportée depuis sa fenêtre (MP4,
    H.264, deux passages).

    - La fenêtre (réglages et résumé avant export, choix ProRes grisé en MP4, avertissement du MKV),
      pendant l'export (étapes) et à la fin (« Lire la vidéo »).
    - La vidéo relue par FFmpeg : H.264, autant d'images que la source, aux mêmes moments, à sa taille,
      étiquettes de couleurs de la vidéo source (celle de démonstration : BT.601), en plage limitée.
    - Le jaune du mot actif (« Sérum ») : dans la vidéo, la couleur de l'aperçu, à quelques niveaux près.
    - Un export arrêté ne laisse rien (ni fichier, ni dossier provisoire). Les fichiers exportés sont
      ensuite effacés (rapport léger)."""
    from .exports.composition import CalqueDeLaVideo
    from .exports.ffmpeg import analyser, executer, lecture_en_rgb, programme_ffmpeg
    from .exports.video import MKV, MOV, MP4, PRORES

    etat: dict = {}
    dialogue = atelier.dialogue_video()
    if dialogue is None:
        rapport["video_avec_sous_titres"] = {"fenetre": False}
        return False
    dialogue.show()
    etat["analyse_finie"] = _attendre(lambda: dialogue.analyse_finie, 30)
    _laisser_afficher()
    capturer(dialogue, "dialogue-export-video")
    problemes = _debordements(dialogue, "fenêtre d'export de la vidéo")
    rapport["video_debordements"] = problemes
    etat["sans_debordement"] = not problemes
    etat["prores_grise_en_mp4"] = dialogue.choix_conteneur.valeur() == MP4 and not dialogue.choix_codec.bouton(PRORES).isEnabled()
    dialogue.choix_conteneur.bouton(MKV).click()
    etat["avertissement_mkv"] = any("ne lit pas le MKV" in m for m in dialogue.messages_affiches()) and dialogue.texte_extension.text() == ".mkv"
    dialogue.choix_conteneur.bouton(MOV).click()
    etat["prores_possible_en_mov"] = dialogue.choix_codec.bouton(PRORES).isEnabled()
    dialogue.choix_conteneur.bouton(MP4).click()
    plan = dialogue.plan()
    source = dialogue.source
    images_source = source.analyse.images if source.analyse is not None else None
    rapport["video_plan"] = {
        "sortie": plan.sortie.name if plan else "", "taille": [plan.largeur, plan.hauteur] if plan else [],
        "debit": plan.debit if plan else None, "son": plan.son if plan else None, "images": plan.nombre_images if plan else 0,
        "messages": dialogue.messages_affiches(),
        "resume": [[ligne.titre, ligne.source, ligne.export] for ligne in dialogue.resume().lignes],
    }
    etat["plan"] = bool(plan and images_source and plan.nombre_images == images_source.nombre == 74 and plan.conteneur == MP4)
    debut = time.monotonic()
    dialogue.exporter()
    _attendre(lambda: dialogue.barre.avancee() > 0.3 or not dialogue.en_cours(), 30)
    capturer(dialogue, "dialogue-export-video-avancement")
    etat["export_fini"] = _attendre_sans_pause(lambda: not dialogue.en_cours(), DELAI_EXPORT_S)
    rapport["video_duree_s"] = round(time.monotonic() - debut, 2)
    rapport["video_dessin_s"] = round(dialogue.dessin_s, 2)
    rapport["video_images_dessinees"] = dialogue.images_dessinees
    _laisser_afficher()
    capturer(dialogue, "dialogue-export-video-fin")
    rapport["video_message"] = dialogue.statut.text()
    fichier = dialogue.fichier
    etat["fichier_ecrit"] = bool(plan) and fichier is not None and fichier.is_file() and not plan.en_cours.exists()
    etat["lire_la_video"] = dialogue.bouton_lire.isVisible()
    if etat["fichier_ecrit"]:
        rapport["video_poids_mo"] = round(fichier.stat().st_size / 1024**2, 2)
        analyse = analyser(fichier)
        images = analyse.images if analyse else None
        couleurs = analyse.couleurs if analyse else None
        moments = [m * images.base_de_temps for m in images.moments] if images else []
        moments_source = [m * images_source.base_de_temps for m in images_source.moments]
        rapport["video_relue"] = {
            "codec": images.codec if images else "", "images": images.nombre if images else 0,
            "taille": list(analyse.taille_affichee) if analyse else [], "son": analyse.son is not None if analyse else None,
            "couleurs": [couleurs.format_pixels, couleurs.plage, couleurs.matrice, couleurs.primaires, couleurs.transfert] if couleurs else [],
            "memes_moments": moments == moments_source,
        }
        etat["fichier_relu"] = bool(
            images and images.codec == "h264" and images.nombre == images_source.nombre and moments == moments_source
            and analyse.taille_affichee == (plan.largeur, plan.hauteur)
            # Les étiquettes prévues : la norme de la vidéo (Motion JPEG : BT.601, « bt470bg »), en plage limitée.
            and couleurs is not None
            and (couleurs.plage, couleurs.matrice, couleurs.primaires, couleurs.transfert)
            == ("tv", plan.couleurs.matrice, plan.couleurs.primaires, plan.couleurs.transfert)
        )
        # Le jaune du mot actif pendant « Sérum » : celui de l'aperçu, dans la vidéo.
        serum = next((i for i, mot in enumerate(atelier.mots) if mot.texte.casefold().startswith("sérum")), 0)
        temps = atelier.mots[serum].debut + 0.15
        numero = min(range(images_source.nombre), key=lambda n: abs(float(moments_source[n]) - temps))
        contenu = atelier.contenu_a_exporter()
        calque = CalqueDeLaVideo(contenu.reglages, plan.largeur, plan.hauteur, contenu.sous_titres, contenu.mots, False)
        temps_image = float(moments_source[numero])
        image = calque.image(calque.cle(temps_image), temps_image)
        actif = contenu.reglages.mots.actif.couleur  # le jaune du mot actif (« Blanc contour noir » : #FFD43B)
        jaune = (actif.rouge, actif.vert, actif.bleu) if actif is not None else (0xFF, 0xD4, 0x3B)
        point = _point_dans_le_jaune(image, jaune)
        rapport["video_jaune"] = {
            "attendu": list(jaune), "point": list(point) if point else None, "image": numero, "norme": plan.couleurs.matrice,
        }
        if point is not None:
            brut = executer(
                [str(programme_ffmpeg()), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(fichier),
                 "-vf", f"select=eq(n\\,{numero}),{lecture_en_rgb(plan.couleurs.matrice)},format=gbrp,format=rgb24",
                 "-frames:v", "1", "-f", "rawvideo", "-"],
                60, binaire=True,
            ).stdout
            if len(brut) == plan.largeur * plan.hauteur * 3:
                position = (point[1] * plan.largeur + point[0]) * 3
                lu = tuple(brut[position : position + 3])
                rapport["video_jaune"]["lu"] = list(lu)
                etat["jaune_exact"] = all(abs(a - b) <= 8 for a, b in zip(lu, jaune, strict=True))
            else:
                etat["jaune_exact"] = False
        else:
            etat["jaune_exact"] = False
        fichier.unlink(missing_ok=True)
    dialogue.accept()

    # « Arrêter » : rien n'est gardé, ni la vidéo, ni le dossier provisoire.
    dialogue = atelier.dialogue_video()
    dialogue.show()
    _attendre(lambda: dialogue.analyse_finie, 30)
    plan = dialogue.plan()
    dialogue.exporter()
    _attendre(lambda: dialogue.barre.avancee() > 0 or not dialogue.en_cours(), 30)
    export = dialogue._export
    provisoire = export.calque_provisoire.parent if export is not None and export.calque_provisoire is not None else None
    dialogue.arreter()
    _laisser_afficher()
    etat["arreter_ne_garde_rien"] = (
        plan is not None and not plan.sortie.exists() and not plan.en_cours.exists()
        and (provisoire is None or not provisoire.exists()) and dialogue.statut.text().startswith("Export arrêté")
    )
    dialogue.reject()
    rapport["video_avec_sous_titres"] = etat
    return all(etat.values())


def _video_hlg_de_demonstration(source: Path, ffmpeg: Path) -> Path | None:
    """La vidéo de démonstration (Motion JPEG, BT.601, plage complète) convertie en HDR comme celles d'un
    iPhone (H.265, 10 bits, BT.2020, HLG), son blanc au blanc de référence ; mêmes images, mêmes moments."""
    from .exports.ffmpeg import executer

    chemin = source.with_name(f"{source.stem}-hlg.mov")
    resultat = executer(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(source),
         "-vf", "zscale=rin=full:min=bt470bg:pin=bt709:tin=bt709:p=bt2020:t=arib-std-b67:m=bt2020nc:r=limited:npl=203,"
                "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc:range=tv",
         "-fps_mode", "passthrough", "-c:v", "libx265", "-x265-params", "log-level=error", "-tag:v", "hvc1", "-an", str(chemin)],
        120,
    )
    return chemin if resultat.returncode == 0 and chemin.is_file() else None


def _image_du_calque_8_bits(atelier, plan, temps: float) -> QImage:
    """L'image des sous-titres à ce moment, à la taille de la vidéo (8 bits, transparence droite)."""
    from .exports.composition import CalqueDeLaVideo

    contenu = atelier.contenu_a_exporter()
    calque = CalqueDeLaVideo(contenu.reglages, plan.largeur, plan.hauteur, contenu.sous_titres, contenu.mots, False)
    return calque.image(calque.cle(temps), temps)


def _plan_y_10_bits(ffmpeg: Path, video: Path, numero: int, largeur: int, hauteur: int) -> bytes:
    """La luminance (Y, 10 bits, 2 octets par point) de l'image `numero` d'une vidéo."""
    from .exports.ffmpeg import executer

    brut = executer(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video),
         "-vf", f"select=eq(n\\,{numero}),format=yuv420p10le", "-frames:v", "1", "-f", "rawvideo", "-"],
        60, binaire=True,
    ).stdout
    return brut[: largeur * hauteur * 2]


def _rgb_ramene_en_sdr(ffmpeg: Path, video: Path, numero: int, point: tuple[int, int], largeur: int) -> list[int]:
    """Un point d'une vidéo HDR ramené en SDR (BT.709) avec le même blanc de référence : la couleur des
    sous-titres d'origine."""
    from .exports.ffmpeg import executer

    brut = executer(
        [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video),
         "-vf", f"select=eq(n\\,{numero}),zscale=p=bt709:t=bt709:m=bt709:r=full:npl=203,format=rgb24",
         "-frames:v", "1", "-f", "rawvideo", "-"],
        60, binaire=True,
    ).stdout
    position = (point[1] * largeur + point[0]) * 3
    return list(brut[position : position + 3])


def _video_hdr(atelier, capturer, capturer_image, rapport: dict) -> bool:
    """V3, lot 3 : une vidéo HDR comme celles d'un iPhone (la vidéo de démonstration convertie en HLG,
    10 bits, par FFmpeg) à la place de celle du projet, le temps de cette vérification.

    - Fenêtre de la vidéo : « Convertir en SDR » proposé (décoché), H.264 grisé, H.265 en 10 bits ;
      résumé « HDR (HLG), 10 bits ».
    - Export gardé en HDR : H.265, 10 bits, étiquettes HLG, mêmes images aux mêmes moments ; le blanc
      des sous-titres au blanc de référence (75 % du signal : 721 sur 1 023), et leur jaune redevient
      celui de l'aperçu une fois ramené en SDR.
    - « Convertir en SDR » : H.264, 8 bits, BT.709 ; le jaune et le blanc des sous-titres exacts.
    - Calque d'une vidéo HDR : ProRes 4444 aux étiquettes HLG, blanc à 721.
    Les fichiers sont ensuite effacés, et le projet retrouve sa vidéo."""
    from .exports.ffmpeg import analyser, executer, lecture_en_rgb, programme_ffmpeg
    from .exports.video import H264, H265

    etat: dict = {}
    ffmpeg = programme_ffmpeg()
    projet = atelier._projet
    transcription = projet.transcription if projet is not None else None
    if ffmpeg is None or transcription is None or not transcription.source:
        rapport["video_hdr"] = {"preparation": False}
        return False
    origine, infos_origine = transcription.source, transcription.infos
    hlg = _video_hlg_de_demonstration(Path(origine), ffmpeg)
    etat["video_hlg_fabriquee"] = hlg is not None
    if hlg is None:
        rapport["video_hdr"] = etat
        return False
    transcription.source = str(hlg)
    transcription.infos = dict(infos_origine or {}, format="QuickTime", codec_video="H265", hdr=True)
    fichiers: list[Path] = [hlg]
    try:
        dialogue = atelier.dialogue_video()
        dialogue.show()
        etat["analyse_finie"] = _attendre(lambda: dialogue.analyse_finie, 30)
        dialogue.choix_debit.bouton("conseille").click()  # de la marge : le blanc mesuré au plus près
        _laisser_afficher()
        capturer(dialogue, "dialogue-export-video-hdr")
        problemes = _debordements(dialogue, "fenêtre d'export d'une vidéo HDR")
        rapport["video_hdr_debordements"] = problemes
        etat["sans_debordement"] = not problemes
        plan = dialogue.plan()
        resume = {ligne.titre: [ligne.source, ligne.export] for ligne in dialogue.resume().lignes}
        rapport["video_hdr_plan"] = {
            "codec": plan.codec if plan else "", "bits": plan.bits if plan else 0, "debit": plan.debit if plan else None,
            "couleurs": resume.get("Couleurs"), "messages": dialogue.messages_affiches(),
            "info": dialogue.info_hdr.text() if dialogue.info_hdr is not None else "",
        }
        etat["fenetre"] = bool(
            plan and dialogue.zone_sdr.isVisible() and not dialogue.case_sdr.isChecked()
            and not dialogue.choix_codec.bouton(H264).isEnabled() and plan.codec == H265 and plan.bits == 10
            and resume.get("Couleurs") == ["HDR (HLG), 10 bits", "HDR (HLG), 10 bits"]
        )
        images_source = dialogue.source.analyse.images if dialogue.source.analyse is not None else None
        if plan is None or images_source is None:
            etat["source_lue"] = False
            rapport["video_hdr"] = etat
            dialogue.reject()
            return False
        # Pendant « Sérum » : un point dans un mot blanc (blanc de référence), un dans le mot actif jaune.
        moments_source = [m * images_source.base_de_temps for m in images_source.moments]
        serum = next((i for i, mot in enumerate(atelier.mots) if mot.texte.casefold().startswith("sérum")), 0)
        temps = atelier.mots[serum].debut + 0.15
        numero = min(range(images_source.nombre), key=lambda n: abs(float(moments_source[n]) - temps))
        actif = atelier.contenu_a_exporter().reglages.mots.actif.couleur
        jaune = (actif.rouge, actif.vert, actif.bleu) if actif is not None else (0xFF, 0xD4, 0x3B)
        dialogue.exporter()
        etat["export_hdr_fini"] = _attendre_sans_pause(lambda: not dialogue.en_cours(), DELAI_EXPORT_S)
        rapport["video_hdr_duree_s"] = round(dialogue.duree_s or 0, 2)
        _laisser_afficher()
        capturer(dialogue, "dialogue-export-video-hdr-fin")
        fichier = dialogue.fichier
        etat["fichier_hdr_ecrit"] = fichier is not None and fichier.is_file()
        if etat["fichier_hdr_ecrit"]:
            fichiers.append(fichier)
            analyse = analyser(fichier)
            images, couleurs = analyse.images, analyse.couleurs
            moments = [m * images.base_de_temps for m in images.moments]
            rapport["video_hdr_relue"] = {
                "codec": images.codec, "images": images.nombre, "memes_moments": moments == moments_source,
                "couleurs": [couleurs.format_pixels, couleurs.plage, couleurs.matrice, couleurs.primaires, couleurs.transfert],
            }
            etat["fichier_hdr_relu"] = (
                images.codec == "hevc" and moments == moments_source
                and (couleurs.format_pixels, couleurs.matrice, couleurs.primaires, couleurs.transfert)
                == ("yuv420p10le", "bt2020nc", "bt2020", "arib-std-b67")
            )
            image = _image_du_calque_8_bits(atelier, plan, float(moments_source[numero]))
            blanc, dans_le_jaune = _point_dans_le_jaune(image, (255, 255, 255)), _point_dans_le_jaune(image, jaune)
            mesures: dict = {"image": numero, "point_blanc": blanc, "point_jaune": dans_le_jaune}
            if blanc is not None and dans_le_jaune is not None:
                luminance = _plan_y_10_bits(ffmpeg, fichier, numero, plan.largeur, plan.hauteur)
                mesures["y_blanc"] = int.from_bytes(luminance[(blanc[1] * plan.largeur + blanc[0]) * 2 :][:2], "little")
                mesures["jaune_ramene_en_sdr"] = _rgb_ramene_en_sdr(ffmpeg, fichier, numero, dans_le_jaune, plan.largeur)
                mesures["jaune_attendu"] = list(jaune)
                # L'image exportée, ramenée en SDR, pour la relire des yeux dans le rapport.
                image_relue = executer(
                    [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(fichier),
                     "-vf", f"select=eq(n\\,{numero}),zscale=p=bt709:t=bt709:m=bt709:r=full:npl=203,format=rgb24",
                     "-frames:v", "1", "-f", "rawvideo", "-"],
                    60, binaire=True,
                ).stdout
                if len(image_relue) == plan.largeur * plan.hauteur * 3:
                    capturer_image(
                        QImage(image_relue, plan.largeur, plan.hauteur, plan.largeur * 3, QImage.Format.Format_RGB888).copy(),
                        "video-hdr-relue-en-sdr",
                    )
                etat["blanc_de_reference"] = abs(mesures["y_blanc"] - 721) <= 8
                etat["jaune_hdr"] = all(abs(a - b) <= 8 for a, b in zip(mesures["jaune_ramene_en_sdr"], jaune, strict=True))
            else:
                etat["blanc_de_reference"] = etat["jaune_hdr"] = False
            rapport["video_hdr_mesures"] = mesures
        dialogue.accept()

        # « Convertir en SDR » : H.264 (le codec retenu) revient ; le jaune et le blanc sont exacts.
        dialogue = atelier.dialogue_video()
        dialogue.show()
        _attendre(lambda: dialogue.analyse_finie, 30)
        dialogue.case_sdr.setChecked(True)
        _laisser_afficher()
        capturer(dialogue, "dialogue-export-video-hdr-en-sdr")
        plan = dialogue.plan()
        etat["conversion_prevue"] = bool(plan and plan.codec == H264 and plan.bits == 8 and not plan.couleurs.hdr)
        dialogue.exporter()
        etat["export_sdr_fini"] = _attendre_sans_pause(lambda: not dialogue.en_cours(), DELAI_EXPORT_S)
        fichier = dialogue.fichier
        if fichier is not None and fichier.is_file() and plan is not None:
            fichiers.append(fichier)
            couleurs = analyser(fichier).couleurs
            image = _image_du_calque_8_bits(atelier, plan, float(moments_source[numero]))
            mesures = {}
            etat["fichier_sdr_relu"] = (couleurs.bits, couleurs.matrice, couleurs.transfert) == (8, "bt709", "bt709")
            brut = executer(
                [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(fichier),
                 "-vf", f"select=eq(n\\,{numero}),{lecture_en_rgb()},format=gbrp,format=rgb24",
                 "-frames:v", "1", "-f", "rawvideo", "-"],
                60, binaire=True,
            ).stdout
            for nom, couleur in (("blanc", (255, 255, 255)), ("jaune", jaune)):
                point = _point_dans_le_jaune(image, couleur)
                lu = list(brut[(point[1] * plan.largeur + point[0]) * 3 :][:3]) if point is not None and brut else []
                mesures[nom] = {"attendu": list(couleur), "lu": lu}
                etat[f"{nom}_sdr_exact"] = len(lu) == 3 and all(abs(a - b) <= 8 for a, b in zip(lu, couleur, strict=True))
            rapport["video_hdr_en_sdr"] = mesures
        else:
            etat["fichier_sdr_relu"] = False
        dialogue.accept()

        # Calque d'une vidéo HDR : HLG aussi, blanc au blanc de référence.
        dialogue = atelier.dialogue_calque()
        dialogue.show()
        _attendre(lambda: dialogue.analyse_finie, 30)
        _laisser_afficher()
        capturer(dialogue, "dialogue-export-calque-hdr")
        plan_calque = dialogue.plan()
        etat["calque_hdr_prevu"] = plan_calque.hdr is not None and plan_calque.hdr.nom == "HLG" and dialogue.zone_sdr.isVisible()
        dialogue.exporter()
        etat["calque_hdr_fini"] = _attendre_sans_pause(lambda: not dialogue.en_cours(), DELAI_EXPORT_S)
        fichier = dialogue.fichier
        if fichier is not None and fichier.is_file():
            fichiers.append(fichier)
            couleurs = analyser(fichier).couleurs
            numero_calque = int(temps * plan_calque.frequence)
            contenu = atelier.contenu_a_exporter()
            from .exports.calque import ImagesDuCalque

            octets = ImagesDuCalque(contenu.reglages, plan_calque.largeur, plan_calque.hauteur, contenu.sous_titres, contenu.mots).image(
                plan_calque.temps(numero_calque)
            )
            image = QImage(octets, plan_calque.largeur, plan_calque.hauteur, plan_calque.largeur * 8, QImage.Format.Format_RGBA64).copy()
            point = _point_dans_le_jaune(image, (255, 255, 255))
            y_blanc = None
            if point is not None:
                brut = executer(
                    [str(ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(fichier),
                     "-vf", f"select=eq(n\\,{numero_calque})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "yuva444p10le", "-"],
                    60, binaire=True,
                ).stdout
                position = (point[1] * plan_calque.largeur + point[0]) * 2
                y_blanc = int.from_bytes(brut[position : position + 2], "little") if len(brut) >= position + 2 else None
            rapport["calque_hdr"] = {
                "couleurs": [couleurs.matrice, couleurs.primaires, couleurs.transfert], "point_blanc": point, "y_blanc": y_blanc,
            }
            etat["calque_hdr_relu"] = (
                (couleurs.matrice, couleurs.primaires, couleurs.transfert) == ("bt2020nc", "bt2020", "arib-std-b67")
                and y_blanc is not None and abs(y_blanc - 721) <= 3
            )
        else:
            etat["calque_hdr_relu"] = False
        dialogue.accept()
    finally:
        transcription.source, transcription.infos = origine, infos_origine
        for fichier in fichiers:
            fichier.unlink(missing_ok=True)
    rapport["video_hdr"] = etat
    return all(etat.values())


def _zone_source(fenetre, atelier, capturer, rapport: dict) -> bool:
    """V3.1, lot 6 : la zone « Source » de la page Sous-titres (§7.14).

    - Au départ (projet de démonstration) : la vidéo et les mots du module Transcription, et la ligne
      qui dit d'où viennent les mots.
    - Les sous-titres de démonstration, enregistrés en fichier SRT puis importés : ils deviennent les
      mots importés, choisis (autant de sous-titres), le module Transcription garde les siens, et « La
      voix commence à » s'affiche (la vidéo du module, des mots d'un autre enregistrement). La fenêtre
      « Corriger les mots » s'ouvre sur le mot demandé (sans lecture : un fichier SRT n'a pas de son).
    - Les mots d'une prise sous la vidéo de démonstration importée, muette, la voix commençant à 1 s :
      la fenêtre d'export prévoit la voix de la prise ; la vidéo exportée a un son AAC, silencieux
      avant 1 s, avec la voix ensuite, qui s'arrête avec la dernière image.
    - Retour aux sources du départ : les mêmes sous-titres qu'avant, rien de perdu."""
    import tempfile
    from array import array
    from dataclasses import replace

    from .exports.ffmpeg import analyser, executer, programme_ffmpeg
    from .exports.video import SON_VOIX
    from .sources import SOURCE_IMPORTEE, SOURCE_TRANSCRIPTION, ChoixDesSources
    from .sous_titres import ecrire_srt
    from .style_sous_titres import VideoApercu
    from .transcription import Transcription, resolution_video
    from .ui.pages.sous_titres.source import ONGLET_MOTS, ONGLET_VIDEO

    projet, source = atelier._projet, atelier.source
    page = atelier.defilement.verticalScrollBar()
    atelier.rafraichir()  # la page telle que la voit l'utilisateur (après les exports vidéo)
    page.setValue(0)
    module = projet.transcription
    depart = [s.texte for s in atelier.sous_titres]
    etat: dict = {
        "depart_du_module": projet.sources == ChoixDesSources()
        and source.texte_mots.text().startswith("Les sous-titres viennent de la transcription de"),
    }
    mesures: dict = {"mots": source.texte_mots.text(), "video": source.texte_video.text()}
    debordements: list[str] = []
    try:
        capturer(fenetre, "source-module")
        source.onglets.setCurrentIndex(ONGLET_VIDEO)
        capturer(fenetre, "source-module-video")
        source.onglets.setCurrentIndex(ONGLET_MOTS)

        # Les sous-titres de démonstration, en fichier SRT, importés.
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "sous-titres-demo.srt"
            ecrire_srt(chemin, atelier.sous_titres)
            atelier.importer_srt_depuis(chemin)
        importes = projet.sous_titres_importes
        etat["srt_importe"] = (
            projet.sources.sous_titres == SOURCE_IMPORTEE
            and projet.transcription is module
            and importes is not None
            and importes.infos.get("sous_titres") == len(depart)
            and bool(atelier.sous_titres)
            and "sous-titres-demo.srt" in source.texte_mots.text()
        )
        etat["srt_voix_a_caler"] = source.ligne_decalage.isVisible()
        mesures["srt"] = {"message": atelier.statut.text(), "sous_titres": [s.texte for s in atelier.sous_titres]}
        capturer(fenetre, "source-srt")
        debordements += _debordements(fenetre, "page Sous-titres, sous-titres d'un fichier SRT")

        # « Corriger les mots » : la fenêtre s'affiche sans attendre de clic (elle est fermée aussitôt).
        ouvertes: list = []

        def montrer(fenetre_correction) -> bool:
            fenetre_correction.show()
            _laisser_afficher()
            ouvertes.append(
                [fenetre_correction.windowTitle(), fenetre_correction.correcteur.mot_choisi, fenetre_correction.zone_lecture.isVisible()]
            )
            capturer(fenetre_correction, "dialogue-corriger-mots")
            debordements.extend(_debordements(fenetre_correction, "fenêtre « Corriger les mots »"))
            fenetre_correction.reject()
            return False

        atelier._corriger = montrer
        try:
            atelier.corriger_les_mots(2)
        finally:
            del atelier._corriger
        mesures["corriger"] = ouvertes
        etat["fenetre_corriger"] = ouvertes == [["Corriger les mots", 2, False]]

        # Les mots d'une prise, sous la vidéo de démonstration importée, muette ; la voix commence à 1 s.
        prise = projet.prises[0]
        voix = projet.chemin(prise.fichier)
        projet.sous_titres_importes = Transcription(
            source=prise.nom, audio=prise.fichier, duree_s=prise.duree_s, langue=projet.langue, prise=prise.identifiant,
            mots=[replace(mot) for mot in module.mots],
        )
        largeur, hauteur = resolution_video(module.infos) or (0, 0)
        atelier._definir_video_apercu(VideoApercu(module.source, 1.0, largeur, hauteur, son_de_la_video=False), choisie=True)
        source.onglets.setCurrentIndex(ONGLET_VIDEO)
        _laisser_afficher()
        etat["video_importee_muette"] = (
            projet.sources == ChoixDesSources(SOURCE_IMPORTEE, SOURCE_IMPORTEE)
            and source.zone_son_video.isVisible()
            and not source.son_video.isChecked()
            and source.ligne_decalage.isVisible()
            and source.decalage.value() == 1.0
        )
        capturer(fenetre, "source-video-importee")
        debordements += _debordements(fenetre, "page Sous-titres, vidéo importée")

        dialogue = atelier.dialogue_video()
        if dialogue is None:
            etat["export_prevoit_la_voix"] = False
        else:
            dialogue.show()
            _attendre(lambda: dialogue.analyse_finie, 30)
            plan = dialogue.plan()
            son = next((ligne for ligne in dialogue.resume().lignes if ligne.titre == "Son"), None)
            mesures["export_plan"] = {
                "son": plan.son if plan else None, "voix": str(plan.voix) if plan and plan.voix else None,
                "decalage": plan.decalage_voix if plan else None, "resume_son": [son.source, son.export] if son else None,
            }
            etat["export_prevoit_la_voix"] = (
                plan is not None and plan.son == SON_VOIX and plan.voix == voix and plan.decalage_voix == 1.0
                and son is not None and son.export.startswith("voix des sous-titres")
            )
            capturer(dialogue, "dialogue-export-video-voix")
            dialogue.exporter()
            etat["export_voix_fini"] = _attendre_sans_pause(lambda: not dialogue.en_cours(), DELAI_EXPORT_S)
            fichier = dialogue.fichier
            if fichier is not None and fichier.is_file():
                analyse = analyser(fichier)
                brut = executer(
                    [str(programme_ffmpeg()), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(fichier),
                     "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                    60, binaire=True,
                ).stdout
                echantillons = array("h", brut[: len(brut) // 2 * 2])

                def niveau(debut: float, fin: float) -> float:
                    morceau = echantillons[round(debut * 48_000) : round(fin * 48_000)]
                    return sum(abs(e) for e in morceau) / max(len(morceau), 1)

                duree = float(analyse.images.duree) if analyse is not None and analyse.images is not None else 0.0
                mesures["export_relu"] = {
                    "son": analyse.son.codec if analyse is not None and analyse.son is not None else None,
                    "duree_video_s": round(duree, 3), "duree_son_s": round(len(echantillons) / 48_000, 3),
                    "niveau_avant_la_voix": round(niveau(0.0, 0.8)), "niveau_de_la_voix": round(niveau(1.5, 3.0)),
                }
                etat["export_voix_au_bon_moment"] = (
                    analyse is not None and analyse.son is not None and analyse.son.codec == "aac"
                    and abs(len(echantillons) / 48_000 - duree) < 0.15
                    and niveau(0.0, 0.8) < 50 and niveau(1.5, 3.0) > 1000
                )
                fichier.unlink(missing_ok=True)
            else:
                etat["export_voix_au_bon_moment"] = False
            dialogue.accept()
    finally:
        # Retour aux sources du départ.
        atelier.choisir_les_mots(SOURCE_TRANSCRIPTION)
        atelier.choisir_la_video(SOURCE_TRANSCRIPTION)
        atelier._definir_video_apercu(VideoApercu())
        projet.sous_titres_importes = None
        atelier._services.projets.enregistrer()
        source.onglets.setCurrentIndex(ONGLET_MOTS)
        atelier.rafraichir()
        page.setValue(0)
    etat["retour_au_depart"] = projet.sources == ChoixDesSources() and [s.texte for s in atelier.sous_titres] == depart
    etat["sans_debordement"] = not debordements
    mesures["debordements"] = debordements
    rapport["zone_source"] = {"etat": etat, "mesures": mesures}
    return all(etat.values())


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

            def capturer_avec_liste(liste, nom: str) -> None:
                """Capture de la fenêtre avec la liste déroulante ouverte : la liste est une petite
                fenêtre à part, posée ici par-dessus, à sa place."""
                nonlocal attendues
                attendues += 1
                _laisser_afficher()
                image = fenetre.grab()
                conteneur = liste.view().window()
                peintre = QPainter(image)
                peintre.drawPixmap(fenetre.mapFromGlobal(conteneur.mapToGlobal(QPoint(0, 0))), conteneur.grab())
                peintre.end()
                chemin = dossier / f"{nom}.png"
                if image.save(str(chemin)):
                    rapport["captures"].append(chemin.name)

            def capturer_par_dessus(nom: str, *petites_fenetres) -> None:
                """Capture de la fenêtre avec une bulle ou un menu ouvert : ce sont de petites fenêtres
                à part, posées ici par-dessus, à leur place (coins arrondis compris)."""
                nonlocal attendues
                attendues += 1
                _laisser_afficher()
                image = fenetre.grab()
                peintre = QPainter(image)
                for petite in petites_fenetres:
                    if petite.isVisible():
                        peintre.drawPixmap(fenetre.mapFromGlobal(petite.mapToGlobal(QPoint(0, 0))), petite.grab())
                peintre.end()
                chemin = dossier / f"{nom}.png"
                if image.save(str(chemin)):
                    rapport["captures"].append(chemin.name)

            def capturer_image(image, nom: str) -> None:
                """Image faite par l'app (ex. un sous-titre à la taille de la vidéo)."""
                nonlocal attendues
                attendues += 1
                chemin = dossier / f"{nom}.png"
                if image is not None and image.save(str(chemin)):
                    rapport["captures"].append(chemin.name)

            for identifiant in fenetre.identifiants_modules():
                fenetre.afficher_module(identifiant)
                capturer(fenetre, f"module-{identifiant}")
            # V3.1, lot 1 : barre latérale, bandeau et espaces de 16 px, à la taille des captures.
            disposition = {"standard": _disposition_de_la_fenetre(fenetre)}

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
            # Liste déroulante ouverte (V3.1, lot 2) : 8 px sous le champ (ou au-dessus), coins arrondis,
            # tous les choix (favoris, voix créées, voix de base, séparés d'une ligne), l'actuel en mauve.
            atelier.voix.showPopup()
            capturer_avec_liste(atelier.voix, "liste-deroulante-ouverte")
            conteneur = atelier.voix.view().window()
            haut_liste = conteneur.mapToGlobal(QPoint(0, 0)).y()
            haut_champ = atelier.voix.mapToGlobal(QPoint(0, 0)).y()
            dessous = haut_liste >= haut_champ
            ecart = haut_liste - (haut_champ + atelier.voix.height()) if dessous else haut_champ - (haut_liste + conteneur.height())
            rapport["liste_ouverte"] = {
                "choix_actuel_visible": not atelier.voix.view().isRowHidden(atelier.voix.currentIndex()),
                "ouverte_vers": "le bas" if dessous else "le haut",
                "ecart_avec_le_champ": ecart,
                "coins_arrondis": conteneur.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground),
            }
            verifs["liste_deroulante"] = (
                rapport["liste_ouverte"]["choix_actuel_visible"] and ecart == Dimensions.ECART_LISTE and rapport["liste_ouverte"]["coins_arrondis"]
            )
            atelier.voix.hidePopup()

            # V3.1, lot 3 : les phrases d'aide encore écrites dans chaque module (seulement les
            # indispensables), les icônes « i » ; une bulle ouverte ; un bouton occupé (cercle).
            aides = {}
            for identifiant in fenetre.identifiants_modules():
                fenetre.afficher_module(identifiant)
                page = fenetre.page_affichee()
                aides[identifiant] = {
                    "phrases_visibles": [
                        i.text() for i in page.findChildren(Info) if i.isVisible() and i.ampoule.isVisible() and i.text()
                    ],
                    "icones_i_visibles": sum(1 for b in page.findChildren(BoutonInfo) if b.isVisible()),
                }
            fenetre.afficher_module("sous-titres")
            page_sous_titres = fenetre.page("sous-titres").atelier
            frise = page_sous_titres.cadre_frise
            page_sous_titres.defilement.ensureWidgetVisible(frise.aide)  # l'icône à l'écran, et sa bulle avec
            _laisser_afficher()
            frise.aide.montrer()
            bulle = _attendre(bulle_visible, 2.0)
            # V3.2, lot 2 : la bulle de l'app, coins arrondis (transparents autour), fond des blocs,
            # 16 px autour du texte.
            image_bulle = la_bulle().grab().toImage()
            echelle = image_bulle.width() / max(1, la_bulle().width())
            milieu = QPoint(round(Espacements.XS * echelle), image_bulle.height() // 2)
            rapport["bulle_v32"] = {
                "marges": [la_bulle().etiquette.x(), la_bulle().etiquette.y()],
                "coin_transparent": image_bulle.pixelColor(0, 0).alpha() == 0,
                "fond": image_bulle.pixelColor(milieu).name(),
            }
            verifs["bulle_v32"] = (
                rapport["bulle_v32"]["marges"] == [Espacements.L, Espacements.L]
                and rapport["bulle_v32"]["coin_transparent"]
                and rapport["bulle_v32"]["fond"].upper() == Couleurs.SURFACE.upper()
            )
            capturer_par_dessus(f"bulle-{frise.titre.text().lower()}", la_bulle())
            cacher_bulle()
            page_sous_titres.defilement.verticalScrollBar().setValue(0)
            fenetre.afficher_module("script")
            produit = fenetre.page("script").atelier.produit
            produit.bouton_lire.definir_occupe(True)
            capturer(produit.cadre, "bouton-occupe")
            occupe = produit.bouton_lire.est_occupe() and produit.bouton_lire.isEnabled()
            produit.bouton_lire.definir_occupe(False)
            # Chaque phrase encore écrite est l'une des indispensables (comptée une fois : celle d'un script
            # TikTok est sur chaque carte).
            imprevues = sorted(
                {
                    phrase
                    for a in aides.values()
                    for phrase in a["phrases_visibles"]
                    if not phrase.startswith(PHRASES_INDISPENSABLES)
                }
            )
            rapport["aides_v31"] = {
                "modules": aides, "phrases_imprevues": imprevues, "bulle_visible": bulle, "bouton_occupe": occupe
            }
            verifs["aides_v31"] = bulle and occupe and not imprevues
            fenetre.afficher_module("voix")
            verifs["editeur_badges"] = atelier.editeur.segments() == normaliser([dict(s) for s in SCRIPT_DEMO])
            rapport["texte_api_demo"] = atelier.editeur.texte_api()
            # V2, lot 2 : nombres dits (projet en français) et durée estimée avec la vitesse mesurée.
            rapport["voix_lot2"] = {
                "nombres_visibles": not atelier.zone_nombres.isHidden(),
                "nombres": atelier.nombres.currentText(),
                "estimation": atelier.estimation.text(),
                "aide_estimation": atelier.estimation.toolTip(),
            }
            verifs["lecture_audio"] = atelier.lecteur._lecteur is not None  # Qt Multimedia embarqué

            # Page Script (V2, lot 1) : brief pré-rempli d'après la page, accroches, deux scripts relus.
            # Toutes les sections du brief sont ouvertes (elles le restent pour le test à 960 px).
            ecriture = fenetre.page("script").atelier
            fenetre.afficher_module("script")
            for section in ecriture.formulaire.sections:
                section.ouvrir()
            ecriture.produit.section_fiche.ouvrir()
            _laisser_afficher()  # la page s'allonge : la barre de défilement doit le savoir avant les captures
            champ_produit = ecriture.formulaire.champs["produit"]
            rapport["script_demo"] = {
                "produit": champ_produit.valeur(),
                "marque_d_apres_la_page": not champ_produit.marque.isHidden(),
                "accroches": len(ecriture.accroches.lignes()),
                "scripts": [f"{carte.titre.text()} : {carte.details.text()}" for carte in ecriture.scripts.cartes()],
                "origines": [carte.origine.text() for carte in ecriture.scripts.cartes()],
                "bouton_ecrire": ecriture.bouton_ecrire.text(),
                "duree_et_vitesse": ecriture.formulaire.info_duree.text(),
            }
            # Lot 2 : 6 scripts (dont une série « Accroches seulement » et une retouche), la vitesse
            # de la voix du projet mesurée sur les prises de démonstration.
            verifs["module_script"] = (
                champ_produit.valeur() == "Sérum éclat Glowzy"
                and not champ_produit.marque.isHidden()
                and len(ecriture.accroches.lignes()) == 6
                and len(ecriture.scripts.cartes()) == 6
                and ecriture.bouton_ecrire.text() == "Écrire les 2 scripts"
                and not ecriture.barre_scripts.isHidden()
                and "vitesse de Kore mesurée sur 3 prises" in ecriture.formulaire.info_duree.text()
            )
            defilement = ecriture.findChild(QScrollArea)
            if defilement is not None:
                barre = defilement.verticalScrollBar()
                for numero, position in enumerate(range(barre.pageStep(), barre.maximum() + barre.pageStep(), barre.pageStep()), 2):
                    barre.setValue(min(position, barre.maximum()))
                    capturer(fenetre, f"script-{numero}")
                barre.setValue(0)

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

            # Page Sous-titres (étape 8, studio de la V2) : la vidéo de démonstration est lue, puis un
            # sous-titre choisi (aperçu), une capture par hauteur d'écran.
            sous_titres = fenetre.page("sous-titres").atelier
            fenetre.afficher_module("sous-titres")
            rapport["lecture_video"] = _verifier_lecture_video(sous_titres)
            verifs["lecture_video"] = rapport["lecture_video"]["ok"]
            sous_titres.choisir_sous_titre(2)
            _attendre(lambda: sous_titres.toile._image is not None)
            capturer(fenetre, "studio-video")
            rapport["sous_titres_demo"] = [s.texte for s in sous_titres.sous_titres]
            verifs["sous_titres"] = bool(sous_titres.sous_titres)
            verifs["studio"] = _studio(sous_titres, capturer, rapport)
            verifs["style_texte"] = _style_texte(sous_titres, capturer, capturer_image, rapport)
            verifs["mots_du_studio"] = _mots_du_studio(sous_titres, capturer, capturer_image, rapport)
            verifs["animations"] = _animations(sous_titres, capturer, capturer_image, rapport)
            verifs["frise_et_prereglages"] = _frise_et_prereglages(sous_titres, capturer, capturer_image, rapport)
            verifs["disposition_studio"] = _disposition_du_studio(fenetre, sous_titres, capturer, rapport)
            # V3, lot 1 : FFmpeg intégré, puis le calque transparent de la vidéo de démonstration.
            verifs["ffmpeg_integre"] = _ffmpeg_integre(rapport)
            verifs["calque"] = _calque(sous_titres, capturer, capturer_image, rapport)
            # V3, lot 2 : la vidéo de démonstration avec ses sous-titres.
            verifs["video_avec_sous_titres"] = _video_avec_sous_titres(sous_titres, capturer, rapport)
            # V3, lot 3 : une vidéo HDR (HLG, comme un iPhone), gardée en HDR ou convertie en SDR.
            verifs["video_hdr"] = _video_hdr(sous_titres, capturer, capturer_image, rapport)
            # V3.1, lot 6 : la zone Source (fichier SRT importé, fenêtre « Corriger les mots », mots d'une
            # prise sous une vidéo importée muette, exportée avec la voix), puis retour au départ.
            verifs["zone_source"] = _zone_source(fenetre, sous_titres, capturer, rapport)
            defilement = sous_titres.defilement  # la page (ses colonnes ont aussi des zones qui défilent)
            if defilement is not None:
                barre = defilement.verticalScrollBar()
                for numero, position in enumerate(range(barre.pageStep(), barre.maximum() + barre.pageStep(), barre.pageStep()), 2):
                    barre.setValue(min(position, barre.maximum()))
                    capturer(fenetre, f"sous-titres-{numero}")
                barre.setValue(0)

            # V1.1, lot 6 : réorganiser à la main. Le premier mot du 4e sous-titre (« a ») monte au 3e
            # (« Mais ce Sérum Glowzy a ») ; puis descendre « ma » au 5e est refusé (26 caractères,
            # pour 24 au plus), avec la raison affichée.
            sous_titres.choisir_sous_titre(3)
            sous_titres.monter_premier_mot()
            ajustes = [s.texte for s in sous_titres.sous_titres if s.ajuste]
            sous_titres.choisir_sous_titre(3)
            sous_titres.descendre_dernier_mot()
            rapport["sous_titres_reorganises"] = {
                "sous_titres": [s.texte for s in sous_titres.sous_titres],
                "ajustes": ajustes,
                "message": sous_titres.statut_ajustements.text(),
            }
            verifs["reorganisation"] = len(ajustes) == 2 and sous_titres.statut_ajustements.text().startswith(
                "Impossible : "
            )
            if defilement is not None:
                barre = defilement.verticalScrollBar()
                haut = sous_titres.titre_reorganiser.mapTo(defilement.widget(), QPoint(0, 0)).y()
                barre.setValue(min(max(0, haut - Espacements.L), barre.maximum()))
                capturer(fenetre, "sous-titres-reorganises")
                # Menu « Couper » : un choix par mot qui peut commencer le nouveau sous-titre.
                bouton_couper, menu_couper = sous_titres.bouton_couper, sous_titres.menu_couper
                menu_couper.popup(position_du_menu(bouton_couper, menu_couper))
                capturer_par_dessus("menu-couper", menu_couper)
                menu_couper.hide()
                barre.setValue(0)

            # Chaque onglet des Réglages, puis le dialogue d'ajout de clé.
            reglages = fenetre.page("reglages")
            fenetre.afficher_module("reglages")
            for index in range(reglages.onglets.count()):
                reglages.onglets.setCurrentIndex(index)
                capturer(fenetre, f"reglages-{index + 1}")
                # Onglet plus haut que la fenêtre : capture du bas de la page aussi (V3.1 : la page
                # défile comme les autres, d'une seule barre au bord de la fenêtre).
                barre = reglages.defilement.verticalScrollBar()
                if barre.maximum() > 0:
                    barre.setValue(barre.maximum())
                    capturer(fenetre, f"reglages-{index + 1}-bas")
                    barre.setValue(0)
            reglages.onglets.setCurrentIndex(0)

            # Menu « Projet » (haut de la barre latérale) : icônes et texte, avec le même écart que partout.
            bouton_projet, menu_projet = fenetre.barre_laterale.bouton_projet, fenetre.barre_laterale.menu_projet
            menu_projet.popup(position_du_menu(bouton_projet, menu_projet))
            _laisser_afficher()
            # V3.2, lot 2 : 8 px sous le bouton, coins arrondis (transparents autour), comme une liste.
            image_menu = menu_projet.grab().toImage()
            rapport["menu_v32"] = {
                "ecart_avec_le_bouton": menu_projet.mapToGlobal(QPoint(0, 0)).y()
                - bouton_projet.mapToGlobal(QPoint(0, bouton_projet.height())).y(),
                "coin_transparent": image_menu.pixelColor(0, 0).alpha() == 0,
            }
            verifs["menu_v32"] = (
                rapport["menu_v32"]["ecart_avec_le_bouton"] == Dimensions.ECART_LISTE and rapport["menu_v32"]["coin_transparent"]
            )
            capturer_par_dessus("menu-projet", menu_projet)
            menu_projet.hide()

            fenetres_v32: dict = {}
            dialogue = reglages.connexions.ajouter()
            capturer(dialogue, "dialogue-ajout-cle")
            fenetres_v32["dialogue-ajout-cle"] = _fenetre_comme_une_page(dialogue)
            dialogue.reject()

            # Fenêtres de l'étape 4 : bibliothèque de styles, style, assistant, prononciation.
            services = fenetre.services
            lot2: dict = {}
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
                # V1.1, lot 3 : fenêtres « Conseils » (un module, une fenêtre).
                ("conseils-voix", DialogueConseils(PAGES["voix"], fenetre)),
                ("conseils-script", DialogueConseils(PAGES["script"], fenetre)),
                # V2, lot 1 : noms repérés sur la page produit, proposés au dictionnaire de prononciation.
                (
                    "dialogue-prononciation-noms",
                    DialoguePrononciation(services, None, fenetre, mots_proposes=["Glowzy", "Sérum éclat"]),
                ),
                ("conseils-creer-une-voix", DialogueConseils(PAGES["creer-une-voix"], fenetre)),
                # V1.1, lot 5 : modèles chargés.
                ("dialogue-choix-modeles", DialogueChoixModeles(services, fenetre)),
                # V2, lot 2 : variantes de script (deux onglets), comparaison, retouche, briefs, exemples,
                # accroches envoyées en variantes de voix.
                ("dialogue-variantes-script", _variantes_script_remplies(services, ecriture, fenetre, ONGLET_SCRIPT_PAR_VARIANTE)),
                ("dialogue-variantes-script-accroches", _variantes_script_remplies(services, ecriture, fenetre, ONGLET_ACCROCHES)),
                ("dialogue-comparer-scripts", DialogueComparerScripts(services.projets.projet.ecriture.scripts, None, ecriture._mots_par_seconde(), fenetre)),
                ("dialogue-retouche", _retouche_remplie(services, ecriture, fenetre)),
                ("dialogue-bibliotheque-briefs", DialogueBibliothequeBriefs(services, fenetre)),
                ("dialogue-meilleurs-scripts", DialogueMeilleursScripts(services, services.projets.projet.ecriture.brief, fenetre)),
                ("dialogue-ajout-exemple", DialogueAjoutExemple(services.projets.projet.ecriture.brief, fenetre)),
                ("dialogue-variantes-accroches", _variantes_d_accroches(services, atelier, fenetre)),
                ("conseils-variantes-script", DialogueConseils(PAGES["variantes-script"], fenetre)),
                # V3.2, lot 3 : toutes les fenêtres comme une page, questions et « Autre couleur » comprises.
                ("dialogue-nouveau-projet", DialogueNouveauProjet(services.projets, fenetre)),
                (
                    "message-question",
                    DialogueMessage(
                        fenetre, "Supprimer la prise", "Supprimer « Prise 1 » ?",
                        "Le fichier audio sera effacé du dossier du projet.",
                        action="Supprimer", icone_action="trash", annuler="Annuler",
                    ),
                ),
                (
                    "message-nom",
                    DialogueMessage(
                        fenetre, "Renommer la clé", action="Renommer", annuler="Annuler", champ=("Nouveau nom", "Google perso")
                    ),
                ),
                (
                    "message-erreur",
                    DialogueMessage(
                        fenetre, "Erreur inattendue", "Une erreur inattendue s'est produite.",
                        "Les détails sont enregistrés dans le journal d'erreurs (Réglages → Journal d'erreurs). "
                        "L'app peut continuer à fonctionner.",
                        autre="Ouvrir le journal", erreur=True,
                    ),
                ),
                ("dialogue-autre-couleur", DialogueCouleur(qcolor(Couleurs.AVERTISSEMENT), fenetre)),
            ):
                fenetre_dialogue.show()
                capturer(fenetre_dialogue, nom)
                fenetres_v32[nom] = _fenetre_comme_une_page(fenetre_dialogue)
                debordements += _debordements(fenetre_dialogue, f"fenêtre {nom}")
                if nom in VERIFIER_DANS_LA_FENETRE:
                    lot2[nom] = VERIFIER_DANS_LA_FENETRE[nom](fenetre_dialogue)
                fenetre_dialogue.reject()
            rapport["script_lot2"] = lot2
            verifs["script_lot2"] = all(lot2.get(nom) is True for nom in VERIFIER_DANS_LA_FENETRE)
            rapport["fenetres_v32"] = fenetres_v32
            verifs["fenetres_v32"] = bool(fenetres_v32) and all(f["ok"] for f in fenetres_v32.values())

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
                if reglages.onglets.widget(index) is reglages.couts:
                    capturer(fenetre, "reglages-couts-etroit")  # tableau à la plus petite largeur
            reglages.onglets.setCurrentIndex(0)
            fenetre.afficher_module("sous-titres")
            defilement = sous_titres.defilement  # la page (ses colonnes ont aussi des zones qui défilent)
            if defilement is not None:
                defilement.ensureWidgetVisible(sous_titres.tableau)
                capturer(fenetre, "sous-titres-etroit")
                defilement.verticalScrollBar().setValue(0)
            # … et à la largeur minimale de la fenêtre.
            disposition["etroite"] = _disposition_de_la_fenetre(fenetre)
            rapport["disposition_v31"] = disposition
            verifs["disposition_v31"] = not disposition["standard"]["ecarts"] and not disposition["etroite"]["ecarts"]
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
        # Erreurs inattendues survenues ailleurs pendant l'autotest (ex. dans une réaction à un
        # signal de Qt) : elles comptent aussi.
        rapport["erreurs"] += erreurs_autotest

        rapport["succes"] = not rapport["erreurs"] and all(
            verifs.get(nom) for nom in VERIFICATIONS_OBLIGATOIRES
        )
        (dossier / "autotest.json").write_text(
            json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        app.exit(0 if rapport["succes"] else 1)

    QTimer.singleShot(DELAI_DEMARRAGE_MS, executer)
    QTimer.singleShot(DELAI_MAX_MS, lambda: app.exit(CODE_DELAI_DEPASSE))
