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
from .ui.composants.conseils import DialogueConseils
from .ui.composants.tableau import Tableau
from .ui.dialogues.assistant_style import DialogueAssistantStyle
from .ui.dialogues.assistant_voix import DialogueAssistantVoix
from .ui.dialogues.briefs import DialogueBibliothequeBriefs
from .ui.dialogues.choix_modeles import DialogueChoixModeles
from .ui.dialogues.comparaison import DialogueComparaison
from .ui.dialogues.comparer_scripts import DialogueComparerScripts
from .ui.dialogues.meilleurs_scripts import DialogueAjoutExemple, DialogueMeilleursScripts
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
from .ui.theme import Dimensions, Espacements, Typo

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
    "sous_titres",
    "reorganisation",
    "module_script",
    "script_lot2",
    "lecture_video",
    "studio",
    "style_texte",
)
ELEMENTS_SIGNALES_MAX = 6


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

    bloc, panneau, toile = atelier.bloc_apercu, atelier.panneau, atelier.toile
    rapport["studio_deux_colonnes"] = atelier.studio.deux_colonnes
    largeur, limite = atelier.studio.width(), Dimensions.STUDIO_DEUX_COLONNES_MIN
    if largeur < limite:
        colonnes_ok = not atelier.studio.deux_colonnes
    elif largeur >= limite + Dimensions.BARRE_DEFILEMENT + Espacements.S:
        colonnes_ok = atelier.studio.deux_colonnes
    else:
        colonnes_ok = True  # entre les deux : la disposition d'avant est gardée (voir DispositionStudio)
    etat = {
        # Deux colonnes dans une fenêtre large, l'une sous l'autre dans une fenêtre étroite (écran de la fabrication).
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
    panneau.onglets.setCurrentIndex(1)  # Position
    panneau.verticale.bouton(HAUT).click()
    panneau.alignement.bouton(GAUCHE).click()
    rect, video = toile.rect_du_sous_titre(), toile.rect_video()
    etat["en_haut"] = rect is not None and rect.top() < video.center().y()
    etat["a_gauche"] = rect is not None and rect.left() < video.center().x() - rect.width() / 4
    capturer(atelier.window(), "studio-haut-gauche")
    panneau.alignement.bouton(CENTRE).click()
    panneau.verticale.bouton(BAS).click()
    panneau.onglets.setCurrentIndex(0)
    etat["retour_au_depart"] = (
        atelier.reglages_du_projet().position.verticale == BAS and atelier.reglages_du_projet().position.alignement == CENTRE
    )
    rapport["studio"] = etat
    return all(etat.values())


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
    image = QImage(moteur.largeur, moteur.hauteur, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(qcolor(CouleursApercu.FOND_NEUTRE))
    peintre = QPainter(image)
    if toile._image is not None:
        cadre = toile._image.toImage()
        if not cadre.isNull():
            peintre.drawImage(QRect(0, 0, moteur.largeur, moteur.hauteur), cadre)
    peintre.drawImage(QPoint(0, 0), moteur.image(sous_titre, mots))
    peintre.end()
    bloc = moteur.bloc(sous_titre, mots)
    marge = round(moteur.hauteur * 0.04)
    haut = max(0, round(bloc.y) - marge)
    return image.copy(0, haut, moteur.largeur, min(moteur.hauteur - haut, round(bloc.hauteur) + 2 * marge))


def _style_texte(atelier, capturer, capturer_image, rapport: dict) -> bool:
    """V2, lot 4 : le style du texte. Polices fournies à la bonne graisse, style de départ du projet
    de démonstration, onglet « Texte » avec tous ses groupes ouverts, six styles (une image à la
    taille de la vidéo, recadrée sur le sous-titre), pipette ; puis le style de départ revient."""
    from .rendu.moteur import police_du_texte
    from .rendu.polices import POLICES_FOURNIES, familles
    from .style_sous_titres import StyleTexte, style_de_depart
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
    etat["style_de_depart"] = depart == style_de_depart()

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
            # Liste déroulante ouverte (V1.1, lot 4) : le choix actuel reste dans le champ, les autres
            # choix s'ouvrent dessous (favoris, voix créées, voix de base, séparés d'une ligne).
            atelier.voix.showPopup()
            capturer_avec_liste(atelier.voix, "liste-deroulante-ouverte")
            rapport["liste_ouverte"] = {
                "choix_actuel_cache": atelier.voix.view().isRowHidden(atelier.voix.currentIndex()),
                "sous_le_champ": atelier.voix.view().window().mapToGlobal(QPoint(0, 0)).y()
                - atelier.voix.mapToGlobal(QPoint(0, atelier.voix.height())).y(),
            }
            atelier.voix.hidePopup()
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
            defilement = sous_titres.findChild(QScrollArea)
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
                menu_couper.popup(bouton_couper.mapToGlobal(QPoint(0, bouton_couper.height())))
                capturer(menu_couper, "menu-couper")
                menu_couper.hide()
                barre.setValue(0)

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
            ):
                fenetre_dialogue.show()
                capturer(fenetre_dialogue, nom)
                debordements += _debordements(fenetre_dialogue, f"fenêtre {nom}")
                if nom in VERIFIER_DANS_LA_FENETRE:
                    lot2[nom] = VERIFIER_DANS_LA_FENETRE[nom](fenetre_dialogue)
                fenetre_dialogue.reject()
            rapport["script_lot2"] = lot2
            verifs["script_lot2"] = all(lot2.get(nom) is True for nom in VERIFIER_DANS_LA_FENETRE)

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
            defilement = sous_titres.findChild(QScrollArea)
            if defilement is not None:
                defilement.ensureWidgetVisible(sous_titres.tableau)
                capturer(fenetre, "sous-titres-etroit")
                defilement.verticalScrollBar().setValue(0)
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
