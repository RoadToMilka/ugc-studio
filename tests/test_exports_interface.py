"""V3, lots 1 à 3 (§8.2, §8.3, §8.5) : calque transparent. Moteur en 16 bits (identique à l'aperçu à
8 bits près), images au moment exact, fenêtre d'export (réglages, résumé, avancement, « Arrêter »),
bloc « Exporter » de la page Sous-titres, et un vrai calque écrit par FFmpeg, relu image par image ;
vidéo avec sous-titres (lot 2) ; vidéo HDR (lot 3) : « Convertir en SDR », codecs, vrai export."""

import struct
import time
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

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


def _ecart_moyen_de_transparence(a, b) -> float:
    return sum(abs(p[3] - q[3]) for p, q in zip(a, b, strict=True)) / len(a)


# --- Moteur en 16 bits et images du calque -------------------------------------------------------


def test_moteur_16_bits_identique_a_l_apercu_a_8_bits_pres(app_configuree):
    """Aperçu = export : le dessin en 16 bits par couleur est celui de l'aperçu à 8 bits. Les lettres
    (opaques) ont les mêmes couleurs à 3 niveaux sur 255 près ; les ombres et lueurs floues, plus
    fines en 16 bits, s'écartent de quelques niveaux au plus, et en moyenne de presque rien."""
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
        a, b = _pixels(apercu), _pixels(export)
        alpha, couleur = _ecarts(a, b)
        assert alpha <= 6 * 257 and couleur <= 3 * 257, (temps, alpha / 257, couleur / 257)
        assert _ecart_moyen_de_transparence(a, b) <= 0.25 * 257, temps


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
    serum = next(m for m in contenu.mots if m.texte == "sérum")
    fixe = serum.debut + 0.23  # « sérum » actif, son pop (180 ms) fini, « Glowzy » pas encore dit
    assert premier.debut <= fixe < premier.fin
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
    assert dialogue.zone_sdr.isHidden() and dialogue.plan().hdr is None  # sans vidéo : SDR, pas de choix
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


def test_premier_export_prepare_ffmpeg(app_configuree, qtbot, services, projet_prise, monkeypatch):
    """Premier export d'une version : FFmpeg est recopié depuis le .exe dans une tâche de fond. La
    fenêtre le dit, « Exporter » attend, et aucun message « introuvable » ne s'affiche entre-temps ;
    une préparation impossible le dit en rouge."""
    from ugc_studio.ui.dialogues import export as module_export
    from ugc_studio.ui.dialogues.export import DialogueExportCalque

    prepare = []

    def preparer():
        time.sleep(0.3)  # le temps de voir la fenêtre pendant la préparation
        prepare.append(True)
        return FFMPEG

    monkeypatch.setattr(module_export, "programme_ffmpeg", lambda: None)
    monkeypatch.setattr(module_export, "ffmpeg_a_preparer", lambda: not prepare)
    monkeypatch.setattr(module_export, "preparer_ffmpeg", preparer)
    dialogue = DialogueExportCalque(services, projet_prise, _contenu(projet_prise.sous_titres))
    qtbot.addWidget(dialogue)
    dialogue.show()
    assert dialogue.etat_analyse.text().startswith("Préparation de FFmpeg") and not dialogue.bouton_exporter.isEnabled()
    assert not any("FFmpeg" in message for message in dialogue.messages_affiches())
    qtbot.waitUntil(lambda: dialogue.analyse_finie, timeout=20_000)
    assert prepare and dialogue._ffmpeg == FFMPEG and dialogue.etat_analyse.isHidden()
    assert dialogue.bouton_exporter.isEnabled() == (FFMPEG is not None)

    def echoue():
        raise OSError("Il n'y a pas assez d'espace sur le disque")

    prepare.clear()
    monkeypatch.setattr(module_export, "preparer_ffmpeg", echoue)
    dialogue = DialogueExportCalque(services, projet_prise, _contenu(projet_prise.sous_titres))
    qtbot.addWidget(dialogue)
    dialogue.show()
    qtbot.waitUntil(lambda: dialogue.analyse_finie, timeout=20_000)
    assert not dialogue.bouton_exporter.isEnabled()
    assert "FFmpeg n'a pas pu être préparé : Il n'y a pas assez d'espace sur le disque. L'export est impossible." in dialogue.messages_affiches()


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
        assert alpha <= 0x0080 and couleur <= 3 * 257, (numero, alpha, couleur)  # ProRes 10 bits : 3 niveaux sur 255 au plus
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


# --- Vidéo avec sous-titres (V3, lot 2) ----------------------------------------------------------


@pytest.fixture
def projet_video(services, tmp_path):
    """Un projet dont les sous-titres viennent d'une vraie vidéo (270 × 480 à 29,97, avec son AAC)."""
    if FFMPEG is None:
        pytest.skip("FFmpeg absent de cet ordinateur")
    video = tmp_path / "Vidéos" / "Sérum Glowzy.mp4"
    video.parent.mkdir()
    resultat = executer(
        [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={LARGEUR}x{HAUTEUR}:rate=30000/1001",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2",
         "-vf", "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)],
        120,
    )
    assert resultat.returncode == 0, resultat.stderr
    projet = services.projets.creer("Sérum Glowzy", tmp_path / "projets")
    projet.sous_titres = _reglages()
    projet.transcription = Transcription(
        source=str(video), duree_s=2.0, mots=[Mot(t, d, f) for t, d, f in MOTS],
        infos={"duree_s": 2.0, "video": True, "resolution": [LARGEUR, HAUTEUR], "images_par_seconde": 29.97, "codec_video": "H264",
               "codec_audio": "AAC", "format": "MPEG4", "hdr": False},
    )
    services.projets.enregistrer()
    return projet


def _point_blanc(contenu: SousTitresAExporter, temps: float) -> tuple[int, int] | None:
    """Un point au milieu d'un mot blanc (3 × 3 points blancs opaques autour), dans l'image des
    sous-titres à ce moment, dessinée en 8 bits à la taille de la vidéo de test."""
    from PySide6.QtGui import QImage

    from ugc_studio.exports.composition import CalqueDeLaVideo

    calque = CalqueDeLaVideo(contenu.reglages, LARGEUR, HAUTEUR, contenu.sous_titres, contenu.mots, False)
    image = calque.image(calque.cle(temps), temps).convertToFormat(QImage.Format.Format_RGBA8888)
    octets, par_ligne = bytes(image.constBits()), image.bytesPerLine()

    def blanc(x: int, y: int) -> bool:
        rouge, vert, bleu, alpha = octets[y * par_ligne + x * 4 : y * par_ligne + x * 4 + 4]
        return alpha == 255 and min(rouge, vert, bleu) >= 250

    for y in range(1, HAUTEUR - 1):
        for x in range(1, LARGEUR - 1):
            if all(blanc(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                return x, y
    return None


def _luminances(video: Path, numero: int, bits: int) -> list[int]:
    """La luminance (Y) de chaque point de l'image `numero`, telle qu'elle est dans la vidéo (sans
    conversion : le premier plan de l'image en 4:2:0, de 8 ou 10 bits)."""
    format_ = "yuv420p" if bits == 8 else "yuv420p10le"
    brut = executer([str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video),
                     "-vf", f"select=eq(n\\,{numero})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", format_, "-"], 60, binaire=True).stdout
    if bits == 8:
        return list(brut[: LARGEUR * HAUTEUR])
    return [valeur for (valeur,) in struct.iter_unpack("<H", brut[: LARGEUR * HAUTEUR * 2])]


def _dialogue_video(services, projet, qtbot):
    from ugc_studio.ui.dialogues.export import DialogueExportVideo

    dialogue = DialogueExportVideo(services, projet, _contenu(projet.sous_titres))
    qtbot.addWidget(dialogue)
    dialogue.show()
    qtbot.waitUntil(lambda: dialogue.analyse_finie, timeout=20_000)
    return dialogue


def test_fenetre_de_la_video(app_configuree, qtbot, services, projet_video):
    """MP4 et H.264 au départ, débit identique à la source (+ 10 %) ; le ProRes seulement en MOV ; le
    MKV signalé ; l'extension suit le format ; le résumé compare la vidéo et l'export."""
    from ugc_studio.exports.video import DEBIT_CONSEILLE, DEBIT_IDENTIQUE, DEBIT_PERSONNALISE, H264, MKV, MOV, MP4, PRORES

    dialogue = _dialogue_video(services, projet_video, qtbot)
    assert dialogue.windowTitle() == "Exporter la vidéo avec sous-titres"
    assert (dialogue.choix_conteneur.valeur(), dialogue.choix_codec.valeur(), dialogue.choix_debit.valeur()) == (MP4, H264, DEBIT_IDENTIQUE)
    assert dialogue.plan().sortie.name == "Sérum Glowzy (sous-titres).mp4"
    assert not dialogue.choix_codec.bouton(PRORES).isEnabled() and dialogue.texte_extension.text() == ".mp4"
    lignes = [dialogue.tableau.item(rang, 0).text() for rang in range(dialogue.tableau.rowCount())]
    assert lignes == ["Taille", "Images par seconde", "Débit vidéo", "Format et codec", "Son", "Couleurs", "Durée", "Poids", "Sous-titres"]
    assert dialogue.tableau.item(0, 1).text() == f"{LARGEUR} × {HAUTEUR}" and dialogue.tableau.item(4, 2).text() == "copié tel quel"
    assert dialogue.bouton_exporter.isEnabled() and not dialogue.messages_affiches()
    dialogue.choix_conteneur.bouton(MKV).click()
    assert dialogue.texte_extension.text() == ".mkv" and any("ne lit pas le MKV" in m for m in dialogue.messages_affiches())
    dialogue.choix_conteneur.bouton(MOV).click()
    dialogue.choix_codec.bouton(PRORES).click()
    assert dialogue.choix_codec.bouton(PRORES).isEnabled() and dialogue.choix_debit.isHidden()
    assert dialogue.texte_debit.text().startswith("ProRes 422 HQ : débit fixé par le format")
    dialogue.choix_conteneur.bouton(MP4).click()
    assert dialogue.choix_codec.valeur() == H264  # le ProRes ne va pas dans un MP4
    dialogue.choix_debit.bouton(DEBIT_CONSEILLE).click()
    assert dialogue.plan().debit == 2_000_000 and "pour la publication" in dialogue.texte_debit.text()  # 360p : 2 × 1 Mb/s
    dialogue.choix_debit.bouton(DEBIT_PERSONNALISE).click()
    dialogue.debit_personnalise.setValue(7.5)
    assert dialogue.debit_personnalise.isVisible() and dialogue.plan().debit == 7_500_000


def test_export_de_la_video_puis_relue(app_configuree, qtbot, services, projet_video):
    """Une vraie vidéo, depuis la fenêtre : mêmes images aux mêmes moments, son copié, étiquettes
    BT.709 ; les sous-titres sont dans l'image ; « Lire la vidéo » à la fin ; les choix sont retenus."""
    dialogue = _dialogue_video(services, projet_video, qtbot)
    plan = dialogue.plan()
    dialogue.exporter()
    assert dialogue.en_cours() and dialogue.bouton_arreter.isVisible() and not dialogue.reglages.isEnabled()
    qtbot.waitUntil(lambda: not dialogue.en_cours(), timeout=120_000)
    assert dialogue.statut.text().startswith("Vidéo enregistrée en "), dialogue.statut.text()
    assert dialogue.fichier == plan.sortie and plan.sortie.is_file() and not plan.en_cours.exists()
    assert dialogue.bouton_lire.isVisible() and dialogue.bouton_dossier.isVisible()
    source, sortie = analyser(Path(projet_video.transcription.source)), analyser(plan.sortie)
    assert sortie.images.codec == "h264" and sortie.images.nombre == source.images.nombre == 60
    assert [m * sortie.images.base_de_temps for m in sortie.images.moments] == [m * source.images.base_de_temps for m in source.images.moments]
    assert sortie.son.codec == "aac" and (sortie.couleurs.matrice, sortie.couleurs.transfert) == ("bt709", "bt709")
    # Pendant « sérum » (0,42 à 0,80 s) : un point d'un mot blanc est blanc (235 sur 255, le blanc d'une
    # vidéo) dans l'image exportée ; le reste de l'image est celui de la vidéo.
    numero = 18  # 0,60 s
    point = _point_blanc(dialogue._contenu, float(source.images.moments[numero] * source.images.base_de_temps))
    assert point is not None
    avant, apres = _luminances(Path(projet_video.transcription.source), numero, 8), _luminances(plan.sortie, numero, 8)
    blanc = apres[point[1] * LARGEUR + point[0]]
    assert abs(blanc - 235) <= 6, (point, blanc, avant[point[1] * LARGEUR + point[0]])  # le blanc d'une vidéo : 235
    ecarts = sorted(abs(a - b) for a, b in zip(avant, apres, strict=True))
    assert ecarts[len(ecarts) // 2] < 6  # le reste de l'image intact
    assert services.preferences.lire("export_video_conteneur") == "mp4" and services.preferences.lire("export_video_debit") == "identique"


def test_arreter_la_video(app_configuree, qtbot, services, projet_video):
    """« Arrêter » : rien n'est gardé, ni la vidéo, ni son dossier provisoire."""
    dialogue = _dialogue_video(services, projet_video, qtbot)
    plan = dialogue.plan()
    dialogue.exporter()
    dossier = dialogue._export.calque_provisoire.parent
    assert dossier.is_dir()
    dialogue.arreter()
    assert not dialogue.en_cours() and not plan.sortie.exists() and not plan.en_cours.exists() and not dossier.exists()
    assert dialogue.statut.text() == "Export arrêté : rien n'a été gardé."


def test_bouton_video_grise_sans_video(app_configuree, qtbot, services, projet_prise):
    """Sous-titres d'une voix : « Vidéo avec sous-titres… » grisé, avec son explication."""
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.show()
    atelier = page.atelier
    atelier.rafraichir()
    assert atelier.bouton_video.text() == "Vidéo avec sous-titres…" and not atelier.bouton_video.isEnabled()
    assert atelier.info_video.isVisible() and atelier.dialogue_video() is None
    assert atelier.bouton_calque.isEnabled()


# --- Images du calque d'une vidéo en 10 bits : PNG de 16 bits écrits par Qt (V3, lot 3) ------------


def _morceaux_png(png: bytes) -> dict:
    morceaux, position = [], 8
    while position + 8 <= len(png):
        longueur, nom = struct.unpack_from(">I4s", png, position)
        morceaux.append(nom.decode("latin-1"))
        position += 12 + longueur
    return {"bits": png[24], "sorte": png[25], "morceaux": morceaux}


@avec_ffmpeg
def test_png_de_16_bits_relu_par_ffmpeg(app_configuree, tmp_path, record_property):
    """Pour une vidéo en 10 bits (HDR, ProRes), les images du calque partent en PNG de 16 bits par
    couleur, écrits par Qt : relus par FFmpeg, seuls ou dans le calque provisoire (MOV), ils ont la
    transparence et les couleurs de l'image dessinée (à un niveau sur 255 près)."""
    import json

    from PySide6.QtGui import QImage

    from ugc_studio.exports.composition import CalqueDeLaVideo, png_de
    from ugc_studio.exports.mov_png import EcritureMovPng

    reglages = _reglages()
    contenu = _contenu(reglages)
    calque = CalqueDeLaVideo(reglages, LARGEUR, HAUTEUR, contenu.sous_titres, contenu.mots, True)
    serum = next(m for m in contenu.mots if m.texte == "sérum")
    temps = serum.debut + 0.3  # le pop du mot actif est fini
    image = calque.image(calque.cle(temps), temps)
    assert image.format() == QImage.Format.Format_RGBA64
    png = png_de(image)
    record_property("png_16_bits", json.dumps(_morceaux_png(png)))
    assert (png[24], png[25]) == (16, 6)  # 16 bits, RGBA
    attendu = _pixels(image)

    def relu(commande: list[str], entree: bytes | None = None) -> list[tuple[int, int, int, int]]:
        import subprocess

        sortie = subprocess.run(commande, input=entree, capture_output=True, timeout=60).stdout
        assert len(sortie) == LARGEUR * HAUTEUR * 8
        return _depuis_octets(sortie)

    seul = relu([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-f", "png_pipe", "-i", "pipe:0", "-f", "rawvideo", "-pix_fmt", "rgba64le", "-"], png)
    alpha, couleur = _ecarts(attendu, seul)
    record_property("ecarts_png_seul", json.dumps([alpha, couleur]))
    assert alpha <= 257 and couleur <= 257, (alpha / 257, couleur / 257, _morceaux_png(png))
    vide = png_de(calque.image(None, 0.0))
    ecriture = EcritureMovPng(tmp_path / "calque.mov", LARGEUR, HAUTEUR, 600)
    for donnees in (vide, png, vide):
        ecriture.ajouter(donnees, 20)
    ecriture.fermer()
    dans_le_mov = relu([str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(tmp_path / "calque.mov"),
                        "-vf", "select=eq(n\\,1)", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba64le", "-"])
    alpha, couleur = _ecarts(attendu, dans_le_mov)
    record_property("ecarts_png_dans_le_mov", json.dumps([alpha, couleur]))
    assert alpha <= 257 and couleur <= 257, (alpha / 257, couleur / 257)


# --- Vidéo HDR (V3, lot 3) ---------------------------------------------------------------------------


@pytest.fixture
def projet_hdr(services, tmp_path):
    """Un projet dont les sous-titres viennent d'une vidéo HDR comme celles d'un iPhone (H.265, 10 bits,
    BT.2020, HLG), 270 × 480 à 30, avec son AAC."""
    if FFMPEG is None:
        pytest.skip("FFmpeg absent de cet ordinateur")
    video = tmp_path / "Vidéos" / "IMG_0420.mov"
    video.parent.mkdir()
    resultat = executer(
        [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={LARGEUR}x{HAUTEUR}:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2",
         "-vf", "zscale=rin=limited:pin=bt709:tin=bt709:min=bt709:p=bt2020:t=arib-std-b67:m=bt2020nc:r=limited:npl=203,"
                "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc:range=tv",
         "-c:v", "libx265", "-x265-params", "log-level=error", "-tag:v", "hvc1", "-c:a", "aac", str(video)],
        120,
    )
    assert resultat.returncode == 0, resultat.stderr
    projet = services.projets.creer("IMG 0420", tmp_path / "projets")
    projet.sous_titres = _reglages()
    projet.transcription = Transcription(
        source=str(video), duree_s=2.0, mots=[Mot(t, d, f) for t, d, f in MOTS],
        infos={"duree_s": 2.0, "video": True, "resolution": [LARGEUR, HAUTEUR], "images_par_seconde": 30, "codec_video": "H265",
               "codec_audio": "AAC", "format": "QuickTime", "hdr": True},
    )
    services.projets.enregistrer()
    return projet


def _lignes_du_resume(dialogue) -> dict[str, tuple[str, str]]:
    tableau = dialogue.tableau
    return {tableau.item(rang, 0).text(): (tableau.item(rang, 1).text(), tableau.item(rang, 2).text()) for rang in range(tableau.rowCount())}


def test_fenetre_de_la_video_hdr(app_configuree, qtbot, services, projet_hdr):
    """Vidéo HDR : « Convertir en SDR » apparaît, décoché (le HDR est gardé) ; H.264 est grisé (pas de
    HDR), H.265 choisi en 10 bits ; cochée, H.264 (le codec retenu) revient, en SDR 8 bits."""
    from ugc_studio.exports.video import DEBIT_CONSEILLE, H264, H265, MOV, MP4, PRORES

    dialogue = _dialogue_video(services, projet_hdr, qtbot)
    assert dialogue.zone_sdr.isVisible() and not dialogue.case_sdr.isChecked()
    assert dialogue.info_hdr.text().startswith("Ta vidéo est en HDR (HLG)")
    assert not dialogue.choix_codec.bouton(H264).isEnabled() and "Convertir en SDR" in dialogue.choix_codec.bouton(H264).toolTip()
    assert dialogue.choix_conteneur.valeur() == MP4 and dialogue.choix_codec.valeur() == H265
    plan = dialogue.plan()
    assert (plan.codec, plan.bits) == (H265, 10) and plan.couleurs.hdr
    assert _lignes_du_resume(dialogue)["Couleurs"] == ("HDR (HLG), 10 bits", "HDR (HLG), 10 bits")
    assert dialogue.bouton_exporter.isEnabled() and not dialogue.messages_affiches()
    dialogue.choix_debit.bouton(DEBIT_CONSEILLE).click()
    # 270 × 480 : YouTube ne donne pas de débit HDR sous la 720p, celui du SDR (2 × 1 Mb/s) sert.
    assert dialogue.plan().debit == 2_000_000 and dialogue.texte_debit.text().endswith("le double du débit conseillé par YouTube")
    dialogue.case_sdr.setChecked(True)
    assert dialogue.choix_codec.bouton(H264).isEnabled() and dialogue.choix_codec.valeur() == H264
    plan = dialogue.plan()
    assert (plan.codec, plan.bits) == (H264, 8) and not plan.couleurs.hdr
    assert _lignes_du_resume(dialogue)["Couleurs"] == ("HDR (HLG), 10 bits", "SDR (BT.709), 8 bits")
    dialogue.case_sdr.setChecked(False)
    assert dialogue.choix_codec.valeur() == H265
    dialogue.choix_conteneur.bouton(MOV).click()
    dialogue.choix_codec.bouton(PRORES).click()
    assert dialogue.plan().codec == PRORES and dialogue.plan().couleurs.hdr  # le ProRes garde aussi le HDR


def test_calque_d_une_video_hdr(app_configuree, qtbot, services, projet_hdr):
    """Le calque d'une vidéo HDR l'est aussi (sous-titres au blanc de référence) ; « Convertir en
    SDR » le remet en BT.709."""
    dialogue = _dialogue(services, projet_hdr, qtbot)
    assert dialogue.zone_sdr.isVisible() and "séquence HDR de Premiere Pro" in dialogue.info_hdr.text()
    assert dialogue.plan().hdr is not None and dialogue.plan().hdr.nom == "HLG"
    assert _lignes_du_resume(dialogue)["Couleurs"][1] == "HDR (HLG), 10 bits + transparence"
    dialogue.case_sdr.setChecked(True)
    assert dialogue.plan().hdr is None and _lignes_du_resume(dialogue)["Couleurs"][1].startswith("SDR (BT.709)")


def test_export_hdr_depuis_la_fenetre(app_configuree, qtbot, services, projet_hdr):
    """Une vraie vidéo HDR exportée depuis la fenêtre (dessin en 16 bits, deux passages) : H.265 10 bits,
    étiquettes HLG, mêmes images aux mêmes moments, son copié ; les sous-titres sont dans l'image."""
    dialogue = _dialogue_video(services, projet_hdr, qtbot)
    plan = dialogue.plan()
    assert plan.calque_16_bits
    dialogue.exporter()
    qtbot.waitUntil(lambda: not dialogue.en_cours(), timeout=180_000)
    assert dialogue.statut.text().startswith("Vidéo enregistrée en "), dialogue.statut.text()
    source, sortie = analyser(Path(projet_hdr.transcription.source)), analyser(plan.sortie)
    assert sortie.images.codec == "hevc" and sortie.images.nombre == source.images.nombre == 60
    assert [m * sortie.images.base_de_temps for m in sortie.images.moments] == [m * source.images.base_de_temps for m in source.images.moments]
    couleurs = sortie.couleurs
    assert (couleurs.format_pixels, couleurs.matrice, couleurs.primaires, couleurs.transfert) == ("yuv420p10le", "bt2020nc", "bt2020", "arib-std-b67")
    assert sortie.son.codec == "aac"
    numero = 18  # 0,60 s, pendant « sérum »
    point = _point_blanc(dialogue._contenu, float(source.images.moments[numero] * source.images.base_de_temps))
    assert point is not None
    avant = _luminances(Path(projet_hdr.transcription.source), numero, 10)
    apres = _luminances(plan.sortie, numero, 10)
    blanc = apres[point[1] * LARGEUR + point[0]]
    assert abs(blanc - 721) <= 8, (point, blanc, avant[point[1] * LARGEUR + point[0]])  # blanc de référence (HLG : 75 %)
    ecarts = sorted(abs(a - b) for a, b in zip(avant, apres, strict=True))
    assert ecarts[len(ecarts) // 2] < 24  # le reste de l'image intact (sur 1 023)