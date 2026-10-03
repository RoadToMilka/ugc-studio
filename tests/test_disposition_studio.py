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
    page.resize(1800, 1500)
    qtbot.waitUntil(lambda: studio.mode == GRANDE, timeout=3000)
    # Assez haute pour tout voir (V3.2) : la page visible a la place de la bande du haut, des colonnes
    # avec une vidéo de 640 px, et de la frise ; les colonnes prennent la hauteur qui reste.
    bande = max(atelier.cadre_source.height(), atelier.cadre_export.height())
    besoin = (
        bande + atelier.bloc_apercu.hauteur_pour_video(Dimensions.APERCU_HAUTEUR_GRANDE)
        + atelier.cadre_frise.height() + 2 * Dimensions.ESPACE_BLOCS + Dimensions.ESPACE_BLOCS
    )
    page.resize(1800, page.height() + besoin - studio.hauteur_visible())
    qtbot.waitUntil(lambda: studio.hauteur_visible() == besoin and studio.mode == GRANDE, timeout=3000)
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
    # de la vidéo (640 px de haut au moins, V3.2).
    qtbot.waitUntil(lambda: atelier.defilement.verticalScrollBar().maximum() == 0, timeout=3000)
    qtbot.waitUntil(lambda: _a_la_taille_de_la_video(atelier), timeout=3000)
    assert atelier.bloc_apercu.zone.height() >= Dimensions.APERCU_HAUTEUR_GRANDE


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


def test_fenetre_pas_assez_haute_la_video_garde_640_px(page, qtbot):
    """V3.2 : grande fenêtre pas assez haute pour tout montrer d'un coup (comme en plein écran sur un
    écran de 1080 px) : la vidéo de l'aperçu garde 640 px de haut, son bloc se voit en entier dans la
    page visible, et la frise passe sous les colonnes (la page défile jusqu'à elle). Jusqu'à la 3.1.3,
    les colonnes et la frise remplissaient la fenêtre, et la vidéo n'avait que la place qui restait."""
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE
    from ugc_studio.ui.theme import Dimensions

    atelier = page.atelier
    studio = atelier.studio
    page.resize(1800, 1300)
    qtbot.waitUntil(lambda: studio.mode == GRANDE, timeout=3000)
    apercu = atelier.bloc_apercu
    voulue = apercu.hauteur_pour_video(Dimensions.APERCU_HAUTEUR_GRANDE)
    # Une page visible un peu plus haute que le bloc de l'aperçu avec sa vidéo de 640 px, mais trop
    # basse pour la frise en plus.
    cible = voulue + (atelier.cadre_frise.height() + Dimensions.ESPACE_BLOCS) // 2
    page.resize(1800, page.height() + cible - studio.hauteur_visible())
    qtbot.waitUntil(lambda: studio.hauteur_visible() == cible and studio.mode == GRANDE, timeout=3000)
    assert studio.hauteur_des_colonnes(studio.width()) == voulue
    qtbot.waitUntil(lambda: apercu.height() == voulue and _a_la_taille_de_la_video(atelier), timeout=3000)
    assert abs(apercu.zone.height() - Dimensions.APERCU_HAUTEUR_GRANDE) <= 1
    frise = atelier.cadre_frise
    assert _position(frise, studio).y() >= _position(apercu, studio).y() + apercu.height()
    assert atelier.defilement.verticalScrollBar().maximum() > 0


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


# --- V3.2, lot 4 : commandes de l'aperçu, coins arrondis, préréglages, un réglage par ligne -----------


def test_commandes_de_l_apercu_sous_leur_nom(page, qtbot):
    """« Fond » et « Zoom » au-dessus de leur liste, comme le nom d'un champ (8 px visibles) ;
    « Repères » au-dessus de ses cases. En grande fenêtre, « Fond » et « Zoom » côte à côte, 16 px
    entre eux, et les trois repères sur une ligne (la vidéo, de 360 px, est assez large pour eux)."""
    from ugc_studio.ui.composants.elements import ChampNomme
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE
    from ugc_studio.ui.theme import Espacements

    atelier = page.atelier
    apercu = atelier.bloc_apercu
    for champ, choix in ((apercu.champ_fond, apercu.fond), (apercu.champ_zoom, apercu.zoom)):
        assert isinstance(champ, ChampNomme) and champ.isAncestorOf(choix)
        assert _position(champ.nom, apercu).y() < _position(choix, apercu).y()
        assert _position(champ.nom, apercu).x() == _position(choix, apercu).x()  # alignés à gauche
    cases = (apercu.repere_zone, apercu.repere_marge, apercu.repere_grille)
    nom = apercu.nom_reperes
    assert nom.text() == "Repères" and all(_position(nom, apercu).y() + nom.height() <= _position(c, apercu).y() for c in cases)
    page.resize(1800, 1050)
    qtbot.waitUntil(lambda: atelier.studio.mode == GRANDE, timeout=3000)
    qtbot.waitUntil(lambda: _position(apercu.champ_fond, apercu).y() == _position(apercu.champ_zoom, apercu).y(), timeout=3000)
    fond, zoom = apercu.champ_fond, apercu.champ_zoom
    assert _position(zoom, apercu).x() - (_position(fond, apercu).x() + fond.width()) == Espacements.L
    assert len({_position(case, apercu).y() for case in cases}) == 1  # les repères sur une ligne


def test_coins_arrondis_de_l_apercu_a_l_ecran_seulement(page, qtbot):
    """Coins arrondis de 8 px à l'écran : le coin de la zone a la couleur du bloc ; la toile, elle,
    reste entière (la pipette et les exports ne voient pas les coins)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage

    from ugc_studio.ui.composants.apercu import FOND_GRIS
    from ugc_studio.ui.theme import Arrondis, Couleurs, CouleursApercu

    atelier = page.atelier
    zone, toile = atelier.bloc_apercu.zone, atelier.toile
    atelier.bloc_apercu.fond.definir(FOND_GRIS)
    toile.definir_fond(FOND_GRIS)
    toile.definir_reperes(False, False, False)
    qtbot.waitUntil(lambda: zone.coins.geometry() == zone.viewport().geometry(), timeout=2000)
    image = zone.grab().toImage()
    echelle = image.width() / zone.width()

    def couleur(x: float, y: float) -> str:
        return image.pixelColor(round(x * echelle), round(y * echelle)).name().upper()

    assert couleur(0, 0) == Couleurs.SURFACE.upper()  # le coin : le fond du bloc
    assert couleur(Arrondis.APERCU, Arrondis.APERCU) == CouleursApercu.FOND_NEUTRE.upper()  # dans l'arrondi : la vidéo
    assert couleur(zone.width() - 1, zone.height() - 1) == Couleurs.SURFACE.upper()
    entiere = QImage(toile.size(), QImage.Format.Format_ARGB32_Premultiplied)
    toile.render(entiere, QPoint(0, 0))
    assert entiere.pixelColor(0, 0).name().upper() == CouleursApercu.FOND_NEUTRE.upper()


def test_bibliotheque_et_enregistrer_en_icones(page, qtbot):
    """Préréglage : la liste, puis la bibliothèque (son propre bouton : elle n'est plus dans le menu
    ⋯), « Enregistrer » en icône seule, et le menu ⋯."""
    from ugc_studio.ui.theme import Hauteurs

    panneau = page.atelier.panneau
    boutons = (panneau.bouton_bibliotheque, panneau.bouton_enregistrer_prereglage, panneau.bouton_plus_prereglage)
    gauches = [_position(element, panneau).x() for element in (panneau.prereglage, *boutons)]
    assert gauches == sorted(gauches)
    for element in boutons[:2]:
        assert element.text() == "" and (element.width(), element.height()) == (Hauteurs.CONTROLE, Hauteurs.CONTROLE)
        assert element.toolTip()
    # La page ouvrirait une fenêtre (qui attend une réponse) : le test s'en tient aux demandes.
    panneau.gerer_prereglages_demande.disconnect()
    panneau.enregistrer_prereglage_demande.disconnect()
    demandes = []
    panneau.gerer_prereglages_demande.connect(lambda: demandes.append("bibliotheque"))
    panneau.enregistrer_prereglage_demande.connect(lambda: demandes.append("enregistrer"))
    panneau.bouton_bibliotheque.click()
    panneau.bouton_enregistrer_prereglage.click()
    assert demandes == ["bibliotheque", "enregistrer"]
    textes = [action.text() for action in panneau.bouton_plus_prereglage.menu().actions()]
    assert not any("Gérer" in texte for texte in textes)


def test_un_reglage_par_ligne_dans_les_effets(page, qtbot):
    """Contour : la couleur, puis l'épaisseur dessous (côte à côte jusqu'à la 3.1.3) ; de même pour
    les autres effets."""
    texte = page.atelier.panneau.texte
    texte.sections["Contour"].ouvrir()
    texte.contour.setChecked(True)
    couleur, epaisseur = texte.contour_couleur, texte.contour_epaisseur.champ
    qtbot.waitUntil(lambda: _position(epaisseur, texte).y() > _position(couleur, texte).y() + couleur.height(), timeout=3000)
    assert _position(epaisseur, texte).x() == _position(couleur, texte).x()  # alignés à gauche


def _marges_de_l_apercu(apercu) -> tuple[int, int, int]:
    """Dans le bloc de l'aperçu : le bord gauche du titre, puis l'espace à gauche et à droite de la
    vidéo."""
    zone = _position(apercu.zone, apercu)
    return _position(apercu.titre, apercu).x(), zone.x(), apercu.width() - (zone.x() + apercu.zone.width())


def _aux_marges_du_titre(apercu) -> bool:
    titre, gauche, droite = _marges_de_l_apercu(apercu)
    return gauche == titre and abs(droite - gauche) <= 1


def _texte(element) -> str:
    texte = getattr(element, "text", None)
    return texte()[:60] if callable(texte) else ""


def _attendre_les_marges(qtbot, apercu, et_aussi=lambda: True) -> None:
    """Attend que la vidéo soit aux marges du titre (et `et_aussi`). Sinon, l'échec donne les mesures,
    et les éléments du bloc les plus larges : celui qui élargit la colonne est en tête."""
    from PySide6.QtWidgets import QWidget

    try:
        qtbot.waitUntil(lambda: _aux_marges_du_titre(apercu) and et_aussi(), timeout=3000)
    except Exception as erreur:  # pytestqt.exceptions.TimeoutError
        visibles = [enfant for enfant in apercu.findChildren(QWidget) if enfant.isVisibleTo(apercu)]
        larges = sorted(
            ((e.minimumSizeHint().width(), type(e).__name__, _texte(e)) for e in visibles),
            key=lambda mesure: mesure[0],
            reverse=True,
        )[:4]
        raise AssertionError(
            f"(titre, gauche, droite) = {_marges_de_l_apercu(apercu)} ; bloc {apercu.width()} px "
            f"(voulu {apercu.sizeHint().width()}, minimum {apercu.minimumSizeHint().width()}) ; vidéo "
            f"{apercu.zone.width()} × {apercu.zone.height()} ; les plus larges : {larges}"
        ) from erreur


def test_video_aux_memes_marges_que_le_titre(page, qtbot):
    """3.2.2 : la colonne de l'aperçu a la largeur de la vidéo, qui commence au bord gauche du titre et
    finit à la même distance du bord droit du bloc (en grande fenêtre comme en fenêtre moyenne).
    « Fond » et « Zoom », en listes déroulantes, sont côte à côte sous la vidéo, de son bord gauche à
    son bord droit. De la 3.2.0 à la 3.2.1, la colonne s'élargissait pour les boutons de « Fond » et
    « Zoom », et la vidéo flottait au milieu, avec plus d'espace sur les côtés qu'à gauche du titre."""
    from ugc_studio.ui.composants.choix import ChoixEnListe
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE
    from ugc_studio.ui.theme import Dimensions

    atelier = page.atelier
    apercu = atelier.bloc_apercu
    assert isinstance(apercu.fond, ChoixEnListe) and isinstance(apercu.zoom, ChoixEnListe)

    def fond_et_zoom_sous_la_video() -> bool:
        zone, fond, zoom = (_position(e, apercu) for e in (apercu.zone, apercu.champ_fond, apercu.champ_zoom))
        droite_de_la_video, droite_du_zoom = zone.x() + apercu.zone.width(), zoom.x() + apercu.champ_zoom.width()
        return fond.y() == zoom.y() and fond.x() == zone.x() and abs(droite_du_zoom - droite_de_la_video) <= 1

    _attendre_les_marges(qtbot, apercu)  # fenêtre moyenne : une vidéo de 304 px
    assert fond_et_zoom_sous_la_video()
    page.resize(1800, 1300)
    qtbot.waitUntil(lambda: atelier.studio.mode == GRANDE, timeout=3000)
    _attendre_les_marges(qtbot, apercu, lambda: apercu.zone.height() >= Dimensions.APERCU_HAUTEUR_GRANDE)
    assert fond_et_zoom_sous_la_video()


def test_un_long_chemin_introuvable_n_elargit_pas_l_apercu(page, qtbot, services):
    """3.2.2 : dans « Vidéo introuvable : … », le chemin passe à la ligne après chaque « \\ ». D'un
    seul tenant (Qt ne coupe une ligne qu'aux espaces et aux tirets), un long chemin élargissait la
    colonne de l'aperçu, et la vidéo n'était plus aux marges du titre."""
    atelier = page.atelier
    apercu = atelier.bloc_apercu
    services.projets.projet.transcription.source = (
        "C:\\Utilisateurs\\Coco\\Vidéos_de_la_marque_Glowzy\\Publicités_TikTok_et_Instagram\\Octobre_2026\\pub_v1.mp4"
    )
    atelier.rafraichir()
    assert apercu.ligne_introuvable.isVisibleTo(apercu) and "Publicités_TikTok" in apercu.message_video.text()
    _attendre_les_marges(qtbot, apercu)
    assert (apercu.zone.width(), apercu.zone.height()) == (304, 540)
