"""V3, lot 1 (§8.2, §8.5) : calque transparent. Moteur en 16 bits (identique à l'aperçu à 8 bits
près), images au moment exact, fenêtre d'export (réglages, résumé, avancement, « Arrêter »), bloc
« Exporter » de la page Sous-titres, et un vrai calque écrit par FFmpeg, relu image par image."""

import struct
import time
from dataclasses import replace
from fractions import Fraction

import pytest

from ugc_studio.exports.ffmpeg import analyser, commande_lire_une_image, executer, programme_ffmpeg
from ugc_studio.exports.plan import DOSSIER_AUTRE, DOSSIER_PROJET, SousTitresAExporter
from ugc_studio.projets import FICHIER_AUDIO
from ugc_studio.sous_titres import FORMAT_PERSONNALISE, ReglagesSousTitres, calculer_sous_titres, ecran
from ugc_studio.style_sous_titres import AnimationMot, Animations, Couleur, Lueur, Ombre, StyleTexte
from ugc_studio.transcription import Mot, Transcription

LARGEUR, HAUTEUR = 270, 480
MOTS = [("Mais", 0.10, 0.30), ("ce", 0.32, 0.40), ("sérum", 0.42, 0.80), ("Glowzy", 0.82, 1.20), ("a", 1.25, 1.30), ("tout", 1.32, 1.50), ("changé", 1.52, 1.90)]
FFMPEG = programme_ffmpeg()
avec_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")


def _reglages(**autres) -> ReglagesSousTitres:
    """Un style avec ombre et lueur (des transparences douces) et un pop sur le mot actif."""
    texte = StyleTexte(
        police="Montserrat", graisse=800, taille_pct=6.0,
        ombre=Ombre(True, Couleur(0, 0, 0, 60.0), 1.0, 0.0, 0.4), lueur=Lueur(True, Couleur(245, 158, 11), 2.0, 80.0),
    )
    return replace(
        ReglagesSousTitres(format=FORMAT_PERSONNALISE, largeur_perso=LARGEUR, hauteur_perso=HAUTEUR),
        texte=texte, animations=Animations(AnimationMot("pop", 180)), **autres,
    )


def _contenu(reglages: ReglagesSousTitres) -> SousTitresAExporter:
    from ugc_studio.rendu.moteur import Moteur

    moteur = Moteur(reglages, LARGEUR, HAUTEUR)
    mots = [Mot(t, d, f) for t, d, f in MOTS]
    decoupage = calculer_sous_titres(mots, reglages, "fr-FR", ecran(reglages, (LARGEUR, HAUTEUR)), moteur.mesure, duree_totale=2.0)
    return SousTitresAExporter(reglages, LARGEUR, HAUTEUR, decoupage.sous_titres, decoupage.mots, "Mon style")


def _pixels(image) -> list[tuple[int, int, int, int]]:
    """QImage → valeurs RGBA sur 16 bits, transparence droite."""
    from PySide6.QtGui import QImage

    image = image.convertToFormat(QImage.Format.Format_RGBA64)
    octets = bytes(image.constBits())
    par_ligne = image.bytesPerLine()
    return [
        struct.unpack_from("<4H", octets, y * par_ligne + x * 8) for y in range(image.height()) for x in range(image.width())
    ]


def _depuis_octets(octets: bytes) -> list[tuple[int, int, int, int]]:
    return list(struct.iter_unpack("<4H", octets))


def _ecarts(a, b) -> tuple[int, int]:
    """Plus grand écart de transparence, et de couleur là où le pixel est presque opaque (16 bits)."""
    alpha = max(abs(p[3] - q[3]) for p, q in zip(a, b, strict=True))
    couleurs = [max(abs(p[i] - q[i]) for i in range(3)) for p, q in zip(a, b, strict=True) if min(p[3], q[3]) > 0xF000]
    return alpha, max(couleurs, default=0)


# --- Moteur en 16 bits et images du calque -------------------------------------------------------


def test_moteur_16_bits_identique_a_l_apercu_a_8_bits_pres(app_configuree):
    """Aperçu = export : le dessin en 16 bits par couleur, ramené à 8 bits, est celui de l'aperçu
    (ombre, lueur et contour compris) à un niveau sur 255 près ; il garde seulement plus de nuances."""
    from PySide6.QtGui import QImage

    from ugc_studio.rendu.moteur import Moteur

    reglages = _reglages()
    contenu = _contenu(reglages)
    sous_titre = contenu.sous_titres[0]
    for temps in (sous_titre.debut + 0.05, sous_titre.debut + 0.35):  # pendant puis après le pop
        apercu = Moteur(reglages, LARGEUR, HAUTEUR).image(sous_titre, contenu.mots, temps)
        export = Moteur(reglages, LARGEUR, HAUTEUR, profondeur=16).image(sous_titre, contenu.mots, temps)
        assert apercu.format() == QImage.Format.Format_ARGB32_Premultiplied
        assert export.format() == QImage.Format.Format_RGBA64_Premultiplied
        alpha, couleur = _ecarts(_pixels(apercu), _pixels(export))
        assert alpha <= 2 * 257 and couleur <= 3 * 257, (temps, alpha / 257, couleur / 257)


def test_images_du_calque(app_configuree):
    """Chaque image est celle de l'aperçu à ce moment ; sans sous-titre, l'image est transparente ;
    une image où rien ne bouge n'est pas redessinée (la même repart)."""
    from ugc_studio.exports.calque import ImagesDuCalque
    from ugc_studio.rendu.moteur import Moteur

    reglages = _reglages()
    contenu = _contenu(reglages)
    images = ImagesDuCalque(reglages, LARGEUR, HAUTEUR, contenu.sous_titres, contenu.mots)
    assert images.image(0.0) is images.vide and len(images.vide) == LARGEUR * HAUTEUR * 8
    premier = contenu.sous_titres[0]
    pendant_le_pop = images.image(contenu.mots[0].debut + 0.05)
    assert pendant_le_pop != images.vide
    fixe = premier.debut + 0.25  # « Mais » actif, pop fini
    une = images.image(fixe)
    assert images.image(fixe + 0.01) is une  # rien n'a bougé : pas redessinée
    dessinees = images.dessinees
    images.image(fixe + 0.02)
    assert images.dessinees == dessinees
    attendue = _pixels(Moteur(reglages, LARGEUR, HAUTEUR, profondeur=16).image(premier, contenu.mots, fixe))
    assert _ecarts(_depuis_octets(une), attendue) == (0, 0)  # à sa place, pixel pour pixel
    assert images.image(10.0) is images.vide  # après le dernier sous-titre


# --- Fenêtre d'export ----------------------------------------------------------------------------


@pytest.fixture
def projet_prise(services, tmp_path):
    projet = services.projets.creer("Voix Glowzy", tmp_path / "projets")
    projet.sous_titres = _reglages()
    projet.transcription = Transcription(
        source="Prise 1", audio=FICHIER_AUDIO, duree_s=2.0, prise="prise-001", mots=[Mot(t, d, f) for t, d, f in MOTS]
    )
    services.projets.enregistrer()
    return projet


def _dialogue(services, projet, qtbot):
    from ugc_studio.ui.dialogues.export import DialogueExportCalque

    dialogue = DialogueExportCalque(services, projet, _contenu(projet.sous_titres))
    qtbot.addWidget(dialogue)
    dialogue.show()
    qtbot.waitUntil(lambda: dialogue.analyse_finie, timeout=20_000)
    return dialogue


def test_fenetre_du_calque_d_une_prise(app_configuree, qtbot, services, projet_prise, tmp_path):
    from ugc_studio.ui.composants.conseils import TEXTE_BOUTON

    dialogue = _dialogue(services, projet_prise, qtbot)
    assert dialogue.windowTitle() == "Exporter le calque transparent"
    assert any(b.text() == TEXTE_BOUTON for b in dialogue.findChildren(type(dialogue.bouton_exporter)))
    # Sans vidéo : 30 images par seconde au départ, ou 60, ou une valeur libre.
    assert dialogue.choix_frequence.valeur() == "30" and dialogue.plan().frequence == Fraction(30)
    assert dialogue.plan().nombre_images == 60
    dialogue.choix_frequence.bouton("60").click()
    assert dialogue.plan().frequence == Fraction(60) and dialogue.plan().nombre_images == 120
    dialogue.choix_frequence.bouton("autre").click()
    dialogue.frequence_libre.setValue(23.976)
    assert dialogue.plan().frequence == Fraction(24000, 1001) and dialogue.frequence_libre.isVisible()
    # Pas de vidéo source : le dossier du projet ; le nom vient du projet.
    assert dialogue.choix_dossier.valeur() == DOSSIER_PROJET
    assert dialogue.plan().sortie == projet_prise.dossier / "Voix Glowzy (calque).mov"
    autre = tmp_path / "exports"
    autre.mkdir()
    dialogue._demander_un_dossier = lambda _depart: autre
    dialogue.choix_dossier.bouton(DOSSIER_AUTRE).click()
    assert dialogue.dossier() == autre and dialogue.bouton_changer.isVisible()
    # Le résumé : source (une voix) et calque côte à côte.
    lignes = [dialogue.tableau.item(rang, 0).text() for rang in range(dialogue.tableau.rowCount())]
    assert lignes[:3] == ["Taille", "Images par seconde", "Format et codec"]
    assert dialogue.tableau.item(0, 1).text() == "son seul" and dialogue.tableau.item(0, 2).text() == f"{LARGEUR} × {HAUTEUR}"
    nombre = len(dialogue._contenu.sous_titres)
    assert dialogue.tableau.item(7, 2).text() == f"{nombre} sous-titre{'s' if nombre > 1 else ''}, préréglage « Mon style »"
    assert dialogue.bouton_exporter.isEnabled() == (programme_ffmpeg() is not None)
    dialogue.nom.setText("")
    assert not dialogue.bouton_exporter.isEnabled() and "Donne un nom au fichier." in dialogue.messages_affiches()


@avec_ffmpeg
def test_export_du_calque_puis_relu(app_configuree, qtbot, services, projet_prise, tmp_path):
    """Un vrai calque, depuis la fenêtre : le fichier a les images prévues, à la bonne fréquence, et
    chaque image relue est celle dessinée (transparence et couleurs) ; les choix sont retenus."""
    from ugc_studio.exports.calque import ImagesDuCalque

    dialogue = _dialogue(services, projet_prise, qtbot)
    dialogue.choix_frequence.bouton("autre").click()
    dialogue.frequence_libre.setValue(10)
    plan = dialogue.plan()
    assert plan.nombre_images == 20
    dialogue.exporter()
    assert dialogue.en_cours() and dialogue.bouton_arreter.isVisible() and not dialogue.reglages.isEnabled()
    qtbot.waitUntil(lambda: not dialogue.en_cours(), timeout=60_000)
    assert dialogue.fichier == plan.sortie and plan.sortie.is_file() and not plan.en_cours.exists()
    assert dialogue.statut.text().startswith("Calque enregistré en ") and dialogue.bouton_dossier.isVisible()
    analyse = analyser(plan.sortie)
    assert analyse.images.codec == "prores" and analyse.images.nombre == 20
    assert analyse.images.frequence == Fraction(10) and (analyse.images.largeur, analyse.images.hauteur) == (LARGEUR, HAUTEUR)
    contenu = _contenu(projet_prise.sous_titres)
    images = ImagesDuCalque(contenu.reglages, LARGEUR, HAUTEUR, contenu.sous_titres, contenu.mots)
    for numero in (0, 4, 9, 15):
        envoyee = _depuis_octets(images.image(plan.temps(numero)))
        lue = _depuis_octets(executer(commande_lire_une_image(FFMPEG, plan.sortie, numero), binaire=True).stdout)
        alpha, couleur = _ecarts(envoyee, lue)
        assert alpha <= 0x0080 and couleur <= 2 * 257, (numero, alpha, couleur)
    assert services.preferences.lire("export_calque_frequence") == "autre"
    assert services.preferences.lire("export_calque_frequence_libre") == 10


@avec_ffmpeg
def test_arreter_le_calque(app_configuree, qtbot, services, projet_prise):
    """« Arrêter » : rien n'est gardé, ni le fichier, ni son nom provisoire."""
    projet_prise.transcription.duree_s = 120.0  # 3 600 images : le temps d'arrêter
    dialogue = _dialogue(services, projet_prise, qtbot)
    plan = dialogue.plan()
    dialogue.exporter()
    qtbot.waitUntil(lambda: dialogue.barre.avancee() > 0, timeout=20_000)
    dialogue.arreter()
    assert not dialogue.en_cours() and not plan.sortie.exists() and not plan.en_cours.exists()
    assert dialogue.statut.text() == "Export arrêté : rien n'a été gardé." and dialogue.bouton_exporter.isVisible()


def test_fermer_pendant_l_export_l_arrete(app_configuree, qtbot, services, projet_prise):
    if FFMPEG is None:
        pytest.skip("FFmpeg absent de cet ordinateur")
    projet_prise.transcription.duree_s = 120.0
    dialogue = _dialogue(services, projet_prise, qtbot)
    plan = dialogue.plan()
    dialogue.exporter()
    time.sleep(0.2)
    dialogue.reject()
    assert not dialogue.en_cours() and not plan.en_cours.exists() and not plan.sortie.exists()


# --- Page Sous-titres : bloc « Exporter » ---------------------------------------------------------


def test_bloc_exporter_de_la_page(app_configuree, qtbot, services, projet_prise):
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.show()
    atelier = page.atelier
    atelier.rafraichir()
    assert atelier.cadre_export.isVisible()
    assert atelier.bouton_calque.text() == "Calque transparent…" and atelier.bouton_calque.isEnabled()
    assert atelier.bouton_exporter.text() == "Fichier SRT…"
    contenu = atelier.contenu_a_exporter()
    assert (contenu.largeur, contenu.hauteur) == (LARGEUR, HAUTEUR) and contenu.sous_titres == atelier.sous_titres
    dialogue = atelier.dialogue_calque()
    qtbot.addWidget(dialogue)
    assert dialogue.windowTitle() == "Exporter le calque transparent"
