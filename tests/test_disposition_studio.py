"""V3.1, lot 5 : la page Sous-titres selon la place (cahier des charges §7.9 et §9.4 nonies).

Source et Exporter en haut ; l'aperçu, l'apparence et les sous-titres en trois colonnes qui défilent
chacune seule dans une grande fenêtre, aperçu et apparence côte à côte dans une fenêtre moyenne ; la
frise en bas ; le Découpage en haut du bloc Sous-titres ; l'aperçu à la taille de la vidéo."""

import pytest

from ugc_studio.projets import FICHIER_AUDIO
from ugc_studio.transcription import Mot, Transcription

TEXTE = (
    "Franchement je n'y croyais pas du tout mais ce sérum Glowzy a vraiment changé ma peau en deux "
    "semaines seulement et le lien est juste en dessous pour en profiter"
)


def _mots() -> list[Mot]:
    return [Mot(texte, rang * 0.4, rang * 0.4 + 0.35) for rang, texte in enumerate(TEXTE.split())]


@pytest.fixture
def page(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Sérum", tmp_path / "projets")
    services.projets.projet.transcription = Transcription(
        source=str(tmp_path / "pub.mp4"),
        audio=FICHIER_AUDIO,
        duree_s=12.0,
        infos={"video": True, "resolution": [1080, 1920]},
        langue="fr-FR",
        mots=_mots(),
        date="2026-10-01T10:00:00+02:00",
    )
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.resize(1100, 900)
    page.show()
    page.atelier.rafraichir()
    return page


def _position(element, repere):
    from PySide6.QtCore import QPoint

    return element.mapTo(repere, QPoint(0, 0))


def _a_la_taille_de_la_video(atelier) -> bool:
    video, zone = atelier.toile.rect_video(), atelier.bloc_apercu.zone
    return abs(zone.width() - video.width()) <= 1 and abs(zone.height() - video.height()) <= 1


def test_taille_de_la_zone_d_apercu(app_configuree):
    """La zone a la taille de la vidéo entière dans la place donnée, jamais moins de 200 px de haut."""
    from PySide6.QtCore import QSize

    from ugc_studio.ui.composants.apercu import ToileApercu, ZoneApercu
    from ugc_studio.ui.theme import Dimensions

    zone = ZoneApercu(ToileApercu())  # sans moteur : le format par défaut, 9:16 (1080 × 1920)
    assert zone.taille_pour(400, 540) == QSize(304, 540)
    assert zone.taille_pour(200, 540) == QSize(200, 356)
    assert zone.taille_pour(400, 100).height() == Dimensions.APERCU_HAUTEUR_MIN


def test_fenetre_moyenne(page):
    """1100 px : Source à gauche d'Exporter ; l'aperçu et l'apparence côte à côte ; la frise, puis la
    liste des sous-titres ; la zone de l'aperçu à la taille de la vidéo (304 × 540 pour du 9:16)."""
    from ugc_studio.ui.pages.sous_titres.disposition import MOYENNE

    atelier = page.atelier
    studio = atelier.studio
    assert studio.mode == MOYENNE and not atelier.colonne_apparence.defile
    source, export = _position(atelier.cadre_source, studio), _position(atelier.cadre_export, studio)
    assert source.y() == export.y() and source.x() < export.x()
    apercu, apparence = _position(atelier.bloc_apercu, studio), _position(atelier.cadre_apparence, studio)
    assert apercu.y() == apparence.y() and apercu.x() < apparence.x()
    frise, sous_titres = _position(atelier.cadre_frise, studio), _position(atelier.cadre_sous_titres, studio)
    assert apercu.y() < frise.y() < sous_titres.y()
    assert (atelier.bloc_apercu.zone.width(), atelier.bloc_apercu.zone.height()) == (304, 540)
    assert _a_la_taille_de_la_video(atelier)
    # La colonne de l'aperçu a la largeur de la vidéo (plus ses marges), pas 400 px comme avant.
    assert atelier.bloc_apercu.width() < 400


def test_trois_colonnes_en_grande_fenetre(page, qtbot):
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE
    from ugc_studio.ui.theme import Dimensions

    atelier = page.atelier
    studio = atelier.studio
    page.resize(1800, 1500)  # assez haute pour tout voir : les colonnes prennent la hauteur qui reste
    qtbot.waitUntil(lambda: studio.mode == GRANDE, timeout=3000)
    colonnes = (atelier.bloc_apercu, atelier.cadre_apparence, atelier.cadre_sous_titres)
    qtbot.waitUntil(lambda: len({colonne.height() for colonne in colonnes}) == 1, timeout=3000)
    positions = [_position(colonne, studio) for colonne in colonnes]
    assert positions[0].x() < positions[1].x() < positions[2].x()
    assert len({position.y() for position in positions}) == 1
    # La frise dessous, sur toute la largeur ; Source et Exporter au-dessus.
    frise = atelier.cadre_frise
    assert _position(frise, studio).y() >= positions[0].y() + colonnes[0].height()
    assert frise.width() == studio.width()
    assert _position(atelier.cadre_source, studio).y() < positions[0].y()
    # Chaque colonne défile seule ; la liste prend la place qui reste dans la sienne.
    assert atelier.colonne_apparence.defile and atelier.colonne_sous_titres.defile
    assert atelier.tableau.minimumHeight() == Dimensions.STUDIO_TABLEAU_HAUTEUR_MIN
    assert colonnes[0].height() >= Dimensions.STUDIO_COLONNES_HAUTEUR_MIN
    # Tout se voit sans faire défiler la page ; l'aperçu prend la hauteur de sa colonne, à la taille
    # de la vidéo (plus de 540 px de haut).
    qtbot.waitUntil(lambda: atelier.defilement.verticalScrollBar().maximum() == 0, timeout=3000)
    qtbot.waitUntil(lambda: _a_la_taille_de_la_video(atelier), timeout=3000)
    assert atelier.bloc_apercu.zone.height() > Dimensions.APERCU_HAUTEUR_MAX


def test_l_apparence_defile_seule(page, qtbot):
    """En grande fenêtre, faire défiler l'apparence ne bouge ni l'aperçu ni la page."""
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE

    atelier = page.atelier
    page.resize(1800, 1300)
    qtbot.waitUntil(lambda: atelier.studio.mode == GRANDE, timeout=3000)
    for section in atelier.panneau.texte.sections.values():
        section.ouvrir()  # l'onglet Texte devient plus long que sa colonne
    barre = atelier.colonne_apparence.verticalScrollBar()
    qtbot.waitUntil(lambda: barre.maximum() > 0, timeout=3000)
    avant, page_avant = _position(atelier.bloc_apercu.zone, page), atelier.defilement.verticalScrollBar().value()
    barre.setValue(barre.maximum())
    assert _position(atelier.bloc_apercu.zone, page) == avant
    assert atelier.defilement.verticalScrollBar().value() == page_avant


def test_fenetre_pas_assez_haute_la_bande_du_haut_part_en_haut(page, qtbot):
    """Grande fenêtre pas assez haute pour tout montrer avec des colonnes confortables : les colonnes
    et la frise remplissent la fenêtre, et la page défile juste de la hauteur de la bande du haut."""
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE
    from ugc_studio.ui.theme import Dimensions

    atelier = page.atelier
    studio = atelier.studio
    page.resize(1800, 1050)
    qtbot.waitUntil(lambda: studio.mode == GRANDE, timeout=3000)
    hauteur = studio.hauteur_des_colonnes(studio.width())
    assert hauteur is not None and hauteur >= Dimensions.STUDIO_COLONNES_HAUTEUR_MIN
    page_barre = atelier.defilement.verticalScrollBar()

    def bande() -> int:
        return _position(atelier.bloc_apercu, studio).y() - _position(atelier.cadre_source, studio).y()

    qtbot.waitUntil(lambda: page_barre.maximum() > 0 and abs(page_barre.maximum() - bande()) <= 2, timeout=3000)


def test_fenetre_trop_basse_pas_de_trois_colonnes(page, qtbot):
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE, MOYENNE

    atelier = page.atelier
    page.resize(1800, 1300)
    qtbot.waitUntil(lambda: atelier.studio.mode == GRANDE, timeout=3000)
    page.resize(1800, 650)
    qtbot.waitUntil(lambda: atelier.studio.mode == MOYENNE, timeout=3000)
    assert not atelier.colonne_apparence.defile and not atelier.colonne_sous_titres.defile


def test_decoupage_en_haut_des_sous_titres(page, services):
    """Le Découpage quitte les onglets de l'apparence : en haut du bloc Sous-titres, replié au départ,
    avec son ↺ ; « Masquer les hésitations » y est aussi, mais le ↺ ne le touche pas."""
    atelier = page.atelier
    panneau = atelier.panneau
    onglets = panneau.onglets
    assert [onglets.tabText(i) for i in range(onglets.count())] == ["Texte", "Mots", "Animations", "Position", "Écran"]
    decoupage = panneau.section_decoupage
    assert atelier.cadre_sous_titres.isAncestorOf(decoupage) and not decoupage.est_ouverte()
    assert decoupage.isAncestorOf(panneau.zone_masquer)
    decoupage.ouvrir()
    panneau.caracteres.setValue(panneau.caracteres.value() + 3)
    assert services.projets.projet.sous_titres.caracteres_max == panneau.caracteres.value()
    assert not decoupage.retablir.isHidden()
    masquer = panneau.masquer.isChecked()
    decoupage.retablir.click()
    assert decoupage.retablir.isHidden() and panneau.masquer.isChecked() == masquer


def test_une_colonne_qui_ne_defile_pas_suit_son_contenu(page, qtbot):
    """Fenêtre moyenne : ouvrir le Découpage agrandit le bloc Sous-titres (rien n'est coupé)."""
    atelier = page.atelier
    colonne = atelier.colonne_sous_titres
    avant = colonne.height()
    atelier.panneau.section_decoupage.ouvrir()
    qtbot.waitUntil(lambda: colonne.height() > avant, timeout=3000)
    qtbot.waitUntil(lambda: colonne.height() >= colonne.widget().heightForWidth(colonne.width()), timeout=3000)
