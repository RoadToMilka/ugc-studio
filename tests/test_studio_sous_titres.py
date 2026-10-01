"""V2, lot 3 (§7.1, §7.3, §7.4, §7.7, §7.9) : moteur de dessin commun, aperçu fidèle et studio de la
page Sous-titres (onglets, format suivi de la vidéo, position, vidéo d'aperçu, vidéo introuvable)."""

import json
from dataclasses import replace

import pytest

from ugc_studio.projets import FICHIER_AUDIO
from ugc_studio.sous_titres import ReglagesSousTitres, calculer_sous_titres, ecran
from ugc_studio.style_sous_titres import BAS, CENTRE, GAUCHE, HAUT, Ombre, Position, StyleTexte, VideoApercu
from ugc_studio.transcription import Mot, Transcription

MOTS_PUB = [
    ("Franchement,", 0.1, 0.6),
    ("je", 0.7, 0.8),
    ("n'y", 0.8, 0.95),
    ("croyais", 0.95, 1.3),
    ("pas.", 1.3, 1.6),
    ("Mais", 2.0, 2.2),
    ("ce", 2.25, 2.35),
    ("sérum", 2.4, 2.8),
    ("Glowzy", 2.85, 3.3),
    ("a", 3.35, 3.4),
    ("vraiment", 3.45, 3.9),
    ("changé", 3.95, 4.3),
    ("ma", 4.35, 4.5),
    ("peau", 4.55, 4.9),
    ("!", 4.9, 4.95),
]


def _mots() -> list[Mot]:
    return [Mot(texte, debut, fin) for texte, debut, fin in MOTS_PUB]


# --- Moteur de dessin -------------------------------------------------------------------------


@pytest.fixture
def moteur_v1(app_configuree):
    from ugc_studio.rendu.moteur import Moteur

    return Moteur(ReglagesSousTitres(), 1080, 1920)


def test_mesure_identique_a_celle_de_la_v1(moteur_v1):
    """Un projet de la 1.1.0 garde exactement son découpage : même police, même taille, même mesure."""
    from PySide6.QtGui import QFontMetricsF

    from ugc_studio.ui.polices import police
    from ugc_studio.ui.theme import Typo

    v1 = QFontMetricsF(police(round(1920 * 4.0 / 100), Typo.GRAISSE_FORTE)).horizontalAdvance
    for texte in ("Mais ce Sérum Glowzy a", "Franchement,", "changé ma peau\u00a0!"):
        assert moteur_v1.mesure(texte) == v1(texte)
    assert moteur_v1.taille_px == 77


def test_decoupage_d_un_projet_de_la_v1_inchange(app_configuree):
    from PySide6.QtGui import QFontMetricsF

    from ugc_studio.rendu.moteur import Moteur
    from ugc_studio.ui.polices import police
    from ugc_studio.ui.theme import Typo

    for reglages in (
        ReglagesSousTitres(),
        ReglagesSousTitres(caracteres_max=40, mots_max=8),
        ReglagesSousTitres(caracteres_max=60, mots_max=12, lignes_max=1, texte=StyleTexte(taille_pct=6.0)),
    ):
        ecran_video = ecran(reglages, (1080, 1920))
        v1 = QFontMetricsF(police(max(1, round(ecran_video.taille_texte)), Typo.GRAISSE_FORTE)).horizontalAdvance
        moteur = Moteur(reglages, 1080, 1920)
        avant = calculer_sous_titres(_mots(), reglages, "fr-FR", ecran_video, v1)
        apres = calculer_sous_titres(_mots(), reglages, "fr-FR", ecran_video, moteur.mesure)
        assert [s.lignes for s in apres.sous_titres] == [s.lignes for s in avant.sous_titres]


def _sous_titres(moteur):
    reglages = moteur.reglages
    decoupage = calculer_sous_titres(_mots(), reglages, "fr-FR", ecran(reglages, (moteur.largeur, moteur.hauteur)), moteur.mesure)
    return decoupage.mots, decoupage.sous_titres


def test_image_transparente_a_la_taille_de_la_video(moteur_v1):
    """L'image de l'export (V3) : transparente, sauf le texte blanc et son ombre."""
    from PySide6.QtCore import QRectF

    mots, sous_titres = _sous_titres(moteur_v1)
    image = moteur_v1.image(sous_titres[0], mots)
    assert (image.width(), image.height()) == (1080, 1920)
    assert image.pixelColor(5, 5).alpha() == 0 and image.pixelColor(540, 300).alpha() == 0
    bloc = moteur_v1.bloc(sous_titres[0], mots)
    forme = moteur_v1.forme(bloc)
    boite = forme.boundingRect()
    # Le texte est dans son bloc (à la marge d'une lettre près), en bas de la zone de sécurité de TikTok.
    assert QRectF(bloc.x, bloc.y, bloc.largeur, bloc.hauteur).adjusted(-8, -8, 8, 8).contains(boite)
    assert bloc.y + bloc.hauteur == pytest.approx(1260)
    # Du blanc opaque sur les lettres : on cherche le pixel le plus clair le long de la ligne de base.
    base = round(bloc.lignes[0].base - moteur_v1.taille_px * 0.3)
    plus_clair = max((image.pixelColor(x, base) for x in range(round(boite.left()), round(boite.right()))), key=lambda c: c.alpha())
    assert plus_clair.alpha() == 255 and plus_clair.red() == 255
    # L'ombre légère : autour des lettres, des pixels en plus (sombres, à moitié transparents).
    from ugc_studio.rendu.moteur import Moteur

    sans_ombre = Moteur(replace(moteur_v1.reglages, texte=StyleTexte(ombre=Ombre(active=False))), 1080, 1920)
    image_sans_ombre = sans_ombre.image(sous_titres[0], mots)

    def visibles(une_image) -> int:
        return sum(
            1
            for x in range(round(boite.left()) - 12, round(boite.right()) + 12, 2)
            for y in range(round(boite.top()) - 12, round(boite.bottom()) + 16, 2)
            if une_image.pixelColor(x, y).alpha() > 0
        )

    assert visibles(image) > visibles(image_sans_ombre)


def test_rendu_garde_en_memoire_et_place_au_pixel_pres(moteur_v1):
    mots, sous_titres = _sous_titres(moteur_v1)
    premier = moteur_v1.rendu(sous_titres[0], mots, 0.3)
    assert moteur_v1.rendu(sous_titres[0], mots, 0.3) is premier  # pas redessiné
    assert isinstance(premier.x, int) and isinstance(premier.y, int)
    assert moteur_v1.rendu(sous_titres[0], mots, 0.5) is not premier  # autre taille d'affichage


def test_sans_ombre_ni_texte_hors_du_bloc(app_configuree):
    from ugc_studio.rendu.moteur import Moteur

    reglages = ReglagesSousTitres(texte=StyleTexte(ombre=Ombre(active=False)), position=Position(HAUT))
    moteur = Moteur(reglages, 1080, 1920)
    mots, sous_titres = _sous_titres(moteur)
    image = moteur.image(sous_titres[0], mots)
    bloc = moteur.bloc(sous_titres[0], mots)
    assert bloc.y == pytest.approx(240)  # « Haut » : juste sous la zone de sécurité de TikTok
    for y in (round(bloc.y) - 12, round(bloc.y + bloc.hauteur) + 12):
        assert all(image.pixelColor(x, y).alpha() == 0 for x in range(0, 1080, 7))


def test_apercu_a_100_pour_cent_identique_a_l_export(app_configuree, qtbot):
    """L'aperçu à 100 % et l'image de l'export sont identiques au pixel près (même moteur)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPainter

    from ugc_studio.rendu.moteur import Moteur
    from ugc_studio.ui.composants.apercu import FOND_GRIS, ZOOM_REEL, ToileApercu, ZoneApercu
    from ugc_studio.ui.theme import CouleursApercu, qcolor

    moteur = Moteur(ReglagesSousTitres(), 540, 960)
    mots, sous_titres = _sous_titres(moteur)
    toile = ToileApercu()
    zone = ZoneApercu(toile)
    qtbot.addWidget(zone)
    toile.definir(moteur, mots)
    toile.definir_fond(FOND_GRIS)
    toile.definir_reperes(False, False, False)
    zone.definir_zoom(ZOOM_REEL)
    toile.montrer(sous_titres[1])
    assert (toile.width(), toile.height()) == (540, 960)
    apercu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
    toile.render(apercu, QPoint(0, 0))
    attendu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
    attendu.fill(qcolor(CouleursApercu.FOND_NEUTRE))
    peintre = QPainter(attendu)
    peintre.drawImage(QPoint(0, 0), moteur.image(sous_titres[1], mots))
    peintre.end()
    assert apercu == attendu


# --- Page Sous-titres en studio ----------------------------------------------------------------


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Sérum", tmp_path / "projets")
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.resize(1100, 900)
    page.show()
    return page.atelier


def _video(services, tmp_path, existe: bool = True) -> Transcription:
    source = tmp_path / "pub.mp4"
    if existe:
        source.write_bytes(b"pas une vraie video")
    transcription = Transcription(
        source=str(source),
        audio=FICHIER_AUDIO,
        duree_s=5.0,
        infos={"video": True, "resolution": [1080, 1350]},
        langue="fr-FR",
        mots=_mots(),
        date="2026-10-01T10:00:00+02:00",
    )
    services.projets.projet.transcription = transcription
    return transcription


def _prise_sans_video(services) -> Transcription:
    transcription = Transcription(
        source="Prise 1", audio=FICHIER_AUDIO, duree_s=5.0, infos={"video": False}, langue="fr-FR", mots=_mots(),
        prise="abc", script="…",
    )
    services.projets.projet.transcription = transcription
    return transcription


def test_studio_avec_ses_onglets(atelier, services, tmp_path):
    _video(services, tmp_path)
    atelier.rafraichir()
    onglets = atelier.panneau.onglets
    assert [onglets.tabText(i) for i in range(onglets.count())] == ["Texte", "Mots", "Position", "Découpage", "Écran"]
    assert atelier.toile.sous_titre is atelier.sous_titres[0]  # le premier sous-titre est montré
    assert atelier.studio.deux_colonnes


def test_onglets_a_la_hauteur_de_l_onglet_affiche(app_configuree, qtbot):
    """Studio : un onglet court ne garde pas la hauteur du plus long (pas de grand vide dessous)."""
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    from ugc_studio.ui.composants.onglets import Onglets

    def page(lignes: int) -> QWidget:
        widget = QWidget()
        disposition = QVBoxLayout(widget)
        for numero in range(lignes):
            disposition.addWidget(QLabel(f"Ligne {numero}"))
        return widget

    ajustes, fixes = Onglets(hauteur_selon_l_onglet=True), Onglets()
    for onglets in (ajustes, fixes):
        qtbot.addWidget(onglets)
        onglets.addTab(page(1), "Court")
        onglets.addTab(page(12), "Long")
    court = ajustes.sizeHint().height()
    ajustes.setCurrentIndex(1)
    assert ajustes.sizeHint().height() > court
    ajustes.setCurrentIndex(0)
    assert ajustes.sizeHint().height() == court
    hauteur_fixe = fixes.sizeHint().height()
    fixes.setCurrentIndex(1)
    assert fixes.sizeHint().height() == hauteur_fixe  # sans l'option : celle du plus long, comme avant


def test_messages_d_etat_caches_quand_ils_sont_vides(atelier, services, tmp_path):
    _video(services, tmp_path)
    atelier.rafraichir()
    assert atelier.statut.isHidden() and atelier.statut_export.isHidden()
    atelier._afficher("Un message", "succes")
    assert not atelier.statut.isHidden()
    atelier._afficher("", "secondaire")
    assert atelier.statut.isHidden()


def test_format_suivi_de_la_video(atelier, services, tmp_path):
    _video(services, tmp_path)
    atelier.rafraichir()
    assert not atelier.format.isEnabled() and atelier.format.currentText() == "Celui de la vidéo (1080 × 1350)"
    # (Onglet Écran pas affiché : on vérifie ce qui est montré ou caché dedans.)
    assert not atelier.panneau.info_format.isHidden()
    assert atelier.toile.taille_video() == (1080, 1350)
    assert atelier.panneau.zone_video.isHidden()  # le projet a sa vidéo


def test_format_personnalise_sans_video(atelier, services):
    _prise_sans_video(services)
    atelier.rafraichir()
    assert atelier.format.isEnabled() and atelier.format.currentData() == "9:16"
    libelle_taille = atelier.panneau.grille_ecran.itemAtPosition(1, 0).widget()
    assert libelle_taille.text() == "Taille"
    assert atelier.panneau.zone_perso.isHidden() and libelle_taille.isHidden()  # pas de libellé seul
    atelier.panneau.largeur_perso.setValue(1201)
    atelier.panneau.hauteur_perso.setValue(1500)
    atelier.format.setCurrentIndex(atelier.format.findData("personnalise"))
    reglages = services.projets.projet.sous_titres
    assert (reglages.format, reglages.largeur_perso, reglages.hauteur_perso) == ("personnalise", 1202, 1500)
    assert not atelier.panneau.zone_perso.isHidden() and not libelle_taille.isHidden()
    assert atelier.toile.taille_video() == (1202, 1500)
    assert "Vidéo 1202 × 1500" in atelier.infos_ecran.text()


def test_position_ne_change_que_l_apercu(atelier, services, tmp_path):
    _video(services, tmp_path)
    atelier.rafraichir()
    avant = [s.lignes for s in atelier.sous_titres]
    tableau_avant = atelier.tableau.item(0, 2)
    atelier.panneau.verticale.bouton(HAUT).click()
    reglages = services.projets.projet.sous_titres
    assert reglages.position.verticale == HAUT
    assert [s.lignes for s in atelier.sous_titres] == avant and atelier.tableau.item(0, 2) is tableau_avant  # pas recalculé
    rect = atelier.toile.rect_du_sous_titre()
    assert rect is not None and rect.top() < atelier.toile.rect_video().center().y()
    # Réglage fin : limité pour que le plus grand sous-titre reste entre les marges maximum.
    glissiere = atelier.panneau.reglage_fin
    assert glissiere.minimum() <= 0 <= glissiere.maximum()
    glissiere.setValue(25)
    assert services.projets.projet.sous_titres.position.decalage_pct == 2.5
    assert atelier.panneau.valeur_reglage_fin.text() == "+2,5 %"


def test_alignement_refait_le_decoupage(atelier, services, tmp_path):
    _video(services, tmp_path)
    atelier.rafraichir()
    atelier.panneau.alignement.bouton(GAUCHE).click()
    reglages = services.projets.projet.sous_titres
    assert reglages.position.alignement == GAUCHE
    assert atelier._calcul.ecran.largeur_max == pytest.approx(1080 - 54 - 120)  # jusqu'à la marge de droite
    rect = atelier.toile.rect_du_sous_titre()
    video = atelier.toile.rect_video()
    assert rect.left() == pytest.approx(video.left() + 120 * video.width() / 1080, abs=1)


def test_glisser_le_sous_titre_dans_l_apercu(atelier, services, tmp_path, qtbot):
    from PySide6.QtCore import QPoint, Qt

    _video(services, tmp_path)
    atelier.rafraichir()
    toile = atelier.toile
    rect = toile.rect_du_sous_titre()
    depart = rect.center().toPoint()
    qtbot.mousePress(toile, Qt.MouseButton.LeftButton, pos=depart)
    qtbot.mouseMove(toile, QPoint(depart.x(), depart.y() - 40))
    qtbot.mouseRelease(toile, Qt.MouseButton.LeftButton, pos=QPoint(depart.x(), depart.y() - 40))
    decalage = services.projets.projet.sous_titres.position.decalage_pct
    assert decalage < 0  # remonté
    assert atelier.panneau.reglage_fin.value() == round(decalage * 10)


def test_video_introuvable_et_retrouvee(atelier, services, tmp_path, monkeypatch):
    transcription = _video(services, tmp_path, existe=False)
    atelier.rafraichir()
    bloc = atelier.bloc_apercu
    assert bloc.ligne_introuvable.isVisibleTo(bloc) and "Vidéo introuvable" in bloc.message_video.text()
    assert not bloc.fond.bouton("video").isEnabled()  # fond gris
    retrouvee = tmp_path / "rangee" / "pub.mp4"
    retrouvee.parent.mkdir()
    retrouvee.write_bytes(b"video")
    monkeypatch.setattr(atelier, "_demander_video", lambda _titre, _proposition: retrouvee)
    atelier.retrouver_la_video()
    assert transcription.source == str(retrouvee)
    assert not bloc.ligne_introuvable.isVisibleTo(bloc) and bloc.fond.bouton("video").isEnabled()
    assert atelier.lecteur.video == str(retrouvee)


def test_video_choisie_seulement_pour_l_apercu(atelier, services, tmp_path, monkeypatch):
    _prise_sans_video(services)
    atelier.rafraichir()
    panneau = atelier.panneau
    assert not panneau.zone_video.isHidden() and panneau.bouton_retirer_video.isHidden()
    montage = tmp_path / "montage.mp4"
    montage.write_bytes(b"video")
    monkeypatch.setattr(atelier, "_demander_video", lambda _titre, _proposition: montage)
    atelier.choisir_video_apercu()
    assert services.projets.projet.sous_titres.apercu.chemin == str(montage)
    assert panneau.nom_video.text().startswith("montage.mp4") and not panneau.bouton_retirer_video.isHidden()
    # Sa résolution (lue par Qt Multimedia dans l'app) impose son format.
    atelier._infos_video_lues({"resolution": [1080, 1350]})
    assert services.projets.projet.sous_titres.apercu.resolution == (1080, 1350)
    assert not atelier.format.isEnabled() and atelier.toile.taille_video() == (1080, 1350)
    # La voix commence à 2 s dans le montage ; son de la prise sous la vidéo muette.
    panneau.decalage_video.setValue(2.0)
    panneau.son_video.setChecked(False)
    apercu = services.projets.projet.sous_titres.apercu
    assert (apercu.decalage_s, apercu.son_de_la_video) == (2.0, False)
    # Enregistré dans le projet (format 7), retrouvé à la réouverture.
    services.projets.ouvrir(services.projets.projet.dossier)
    assert services.projets.projet.sous_titres.apercu == VideoApercu(str(montage), 2.0, 1080, 1350, False)
    atelier.retirer_video_apercu()
    assert services.projets.projet.sous_titres.apercu == VideoApercu()
    assert atelier.format.isEnabled()


def test_fond_zoom_et_reperes_retenus(atelier, services):
    from ugc_studio.ui.composants.apercu import FOND_DAMIER, ZOOM_REEL

    bloc = atelier.bloc_apercu
    bloc.fond.bouton(FOND_DAMIER).click()
    bloc.zoom.bouton(ZOOM_REEL).click()
    bloc.repere_grille.setChecked(True)
    bloc.repere_marge.setChecked(False)
    retenu = services.preferences.lire("apercu_sous_titres")
    assert retenu["fond"] == FOND_DAMIER and retenu["zoom"] == ZOOM_REEL and retenu["reperes"] == [True, False, True]
    assert atelier.bloc_apercu.zone.zoom == ZOOM_REEL


def test_studio_sur_une_colonne_quand_la_fenetre_est_etroite(atelier, services, tmp_path, qtbot):
    _video(services, tmp_path)
    atelier.rafraichir()
    page = atelier.parentWidget()
    page.resize(700, 900)
    qtbot.waitUntil(
        lambda: not atelier.studio.deux_colonnes and atelier.bloc_apercu.width() >= atelier.studio.width() - 1, timeout=2000
    )


def test_projet_au_format_6_garde_ses_sous_titres(app_configuree, qtbot, services, tmp_path):
    """Un projet de la 1.3.0 (format 6) s'ouvre avec l'apparence de la V1 et les mêmes sous-titres."""
    from PySide6.QtGui import QFontMetricsF

    from ugc_studio.ui.pages.sous_titres import PageSousTitres
    from ugc_studio.ui.polices import police
    from ugc_studio.ui.theme import Typo

    dossier = tmp_path / "Ancien"
    dossier.mkdir()
    transcription = Transcription(source="Prise 1", audio=FICHIER_AUDIO, duree_s=5.0, langue="fr-FR", mots=_mots(), prise="abc")
    anciens = {"caracteres_max": 20, "mots_max": 4, "majuscules": True, "taille_pct": 4.5, "plateforme": "meta"}
    (dossier / "projet.json").write_text(
        json.dumps({"version_format": 6, "nom": "Ancien", "transcription": transcription.en_dict(), "sous_titres": anciens}),
        encoding="utf-8",
    )
    services.projets.ouvrir(dossier)
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    atelier = page.atelier
    reglages = ReglagesSousTitres(caracteres_max=20, mots_max=4, plateforme="meta", texte=StyleTexte(taille_pct=4.5, casse="majuscules"))
    ecran_video = ecran(reglages)
    v1 = QFontMetricsF(police(round(ecran_video.taille_texte), Typo.GRAISSE_FORTE)).horizontalAdvance
    attendus = calculer_sous_titres(_mots(), reglages, "fr-FR", ecran_video, v1, duree_totale=5.0).sous_titres
    assert [s.lignes for s in atelier.sous_titres] == [s.lignes for s in attendus]
    assert atelier.casse.currentData() == "majuscules" and atelier.panneau.verticale.valeur() == BAS
    assert atelier.panneau.alignement.valeur() == CENTRE


def test_lecteur_sans_son_place_le_temps(app_configuree):
    """Tests : pas de lecture réelle, mais la position demandée donne le sous-titre affiché."""
    from ugc_studio.ui.composants.apercu import LecteurApercu

    lecteur = LecteurApercu()
    temps = []
    lecteur.temps_change.connect(temps.append)
    lecteur.charger("", "C:/inexistant.wav")
    lecteur.aller_a(2.5)
    assert lecteur.temps == 2.5 and temps == [2.5] and not lecteur.en_lecture()
    lecteur.basculer()  # sans lecteur réel : rien ne se passe
    assert not lecteur.en_lecture()


def test_video_de_test_ecrite(app_configuree, tmp_path):
    """La vidéo de test de l'autotest : un AVI dont chaque image est un JPEG de la bonne taille."""
    from PySide6.QtGui import QImage

    from ugc_studio.rendu.video_test import COULEUR_HAUT, ecrire_video_de_test

    chemin = ecrire_video_de_test(tmp_path / "videos" / "test.avi", 270, 480, 0.5, 10)
    donnees = chemin.read_bytes()
    assert donnees[:4] == b"RIFF" and donnees[8:12] == b"AVI "
    debut = donnees.index(b"00dc") + 8  # première image
    taille = int.from_bytes(donnees[debut - 4 : debut], "little")
    image = QImage.fromData(donnees[debut : debut + taille], "JPG")
    entete = donnees.index(b"avih") + 8
    assert (image.width(), image.height()) == (270, 480)
    assert int.from_bytes(donnees[entete + 16 : entete + 20], "little") == 5  # 0,5 s à 10 images par seconde
    haut = image.pixelColor(135, 2)
    from PySide6.QtGui import QColor

    attendue = QColor(COULEUR_HAUT)
    assert abs(haut.green() - attendue.green()) < 30 and abs(haut.blue() - attendue.blue()) < 30
