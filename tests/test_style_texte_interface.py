"""V2, lot 4 (§7.4, §7.9) : style du texte dans le moteur de dessin (contour, fond, lueur, ombre,
dégradé, espaces, polices) et dans l'onglet « Texte » du studio (réglages, valeurs exactes,
« Rétablir », police absente ou importée, pipette)."""

from dataclasses import replace

import pytest

from ugc_studio.sous_titres import ReglagesSousTitres, calculer_sous_titres, ecran
from ugc_studio.style_sous_titres import (
    FOND_BLOC,
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


def _moteur(texte: StyleTexte, largeur: int = 1080, hauteur: int = 1920):
    from ugc_studio.rendu.moteur import Moteur

    return Moteur(ReglagesSousTitres(texte=texte), largeur, hauteur)


def _sous_titres(moteur):
    reglages = moteur.reglages
    decoupage = calculer_sous_titres(_mots(), reglages, "fr-FR", ecran(reglages, (moteur.largeur, moteur.hauteur)), moteur.mesure)
    return decoupage.mots, decoupage.sous_titres


SANS_OMBRE = StyleTexte(ombre=Ombre(active=False))


def _opaques(image) -> int:
    """Pixels visibles (un sur quatre), dans la moitié basse de l'image (là où est le sous-titre)."""
    return sum(
        1 for x in range(0, image.width(), 2) for y in range(image.height() // 2, image.height(), 2) if image.pixelColor(x, y).alpha() > 0
    )


# --- Moteur de dessin ----------------------------------------------------------------------------


def test_contour_autour_des_lettres(app_configuree):
    contour = Contour(True, Couleur(0, 0, 0), 0.5, "arrondis")  # 9,6 px
    sans, avec = _moteur(SANS_OMBRE), _moteur(replace(SANS_OMBRE, contour=contour))
    mots, sous_titres = _sous_titres(sans)
    texte = sous_titres[0].lignes[0]
    # La mesure du découpage compte le contour de chaque côté ; le texte seul ne change pas.
    assert avec.mesure.texte(texte) == pytest.approx(sans.mesure.texte(texte))
    assert avec.mesure(texte) == pytest.approx(sans.mesure(texte) + 2 * 1920 * 0.5 / 100)
    assert avec.metriques.debord_x == pytest.approx(9.6) and avec.metriques.debord_y == pytest.approx(9.6)
    image_sans, image_avec = sans.image(sous_titres[0], mots), avec.image(sous_titres[0], mots)
    assert _opaques(image_avec) > _opaques(image_sans)
    # Les lettres gardent leur épaisseur : leur blanc est toujours là, entouré de noir.
    bloc = avec.bloc(sous_titres[0], mots)
    couleurs = {
        (c.red(), c.green(), c.blue())
        for x in range(round(bloc.x), round(bloc.x + bloc.largeur), 2)
        for y in range(round(bloc.y), round(bloc.y + bloc.hauteur), 2)
        if (c := image_avec.pixelColor(x, y)).alpha() == 255
    }
    assert (255, 255, 255) in couleurs and (0, 0, 0) in couleurs


@pytest.mark.parametrize(("mode", "nombre"), [(FOND_MOT, None), (FOND_LIGNE, None), (FOND_BLOC, 1)])
def test_fond_par_mot_par_ligne_ou_en_bloc(app_configuree, mode, nombre):
    from PySide6.QtCore import QRectF

    from ugc_studio.sous_titres import MotAffiche, SousTitre

    fond = Fond(mode, Couleur(124, 58, 237), 1.0, 0.5, 0.6)
    moteur = _moteur(replace(SANS_OMBRE, fond=fond))
    textes = ["Mais", "ce", "sérum", "Glowzy"]
    mots = [MotAffiche(texte, texte, i * 0.3, i * 0.3 + 0.25) for i, texte in enumerate(textes)]
    sous_titre = SousTitre(0.0, 1.2, ["Mais ce", "sérum Glowzy"], 0, len(mots))  # deux lignes
    bloc = moteur.bloc(sous_titre, mots)
    rectangles = moteur._rectangles_du_fond(bloc)
    attendu = {FOND_MOT: len(bloc.mots), FOND_LIGNE: len(bloc.lignes), FOND_BLOC: nombre}[mode]
    assert len(rectangles) == attendu
    # Le bloc placé à l'écran est la boîte visible : il contient tout le fond (pile, en bloc).
    boite = QRectF(bloc.x, bloc.y, bloc.largeur, bloc.hauteur)
    assert all(boite.adjusted(-0.01, -0.01, 0.01, 0.01).contains(r) for r in rectangles)
    if mode == FOND_BLOC:
        (seul,) = rectangles
        assert (seul.x(), seul.y(), seul.width(), seul.height()) == pytest.approx((bloc.x, bloc.y, bloc.largeur, bloc.hauteur))
    image = moteur.image(sous_titre, mots)
    milieu = image.pixelColor(round(bloc.x + 3), round(bloc.y + bloc.hauteur / 2))  # dans la marge du fond
    assert (milieu.red(), milieu.green(), milieu.blue(), milieu.alpha()) == (124, 58, 237, 255)


def test_lueur_et_ombre_debordent_du_bloc(app_configuree):
    lueur = Lueur(True, Couleur(245, 158, 11), 1.5, 90.0)
    moteur_simple, moteur_lueur = _moteur(SANS_OMBRE), _moteur(replace(SANS_OMBRE, lueur=lueur))
    mots, sous_titres = _sous_titres(moteur_simple)
    simple = moteur_simple.rendu(sous_titres[0], mots, 1.0)
    halo = moteur_lueur.rendu(sous_titres[0], mots, 1.0)
    assert halo.image.width() > simple.image.width() and halo.x < simple.x  # le halo dépasse du texte
    # La lueur ne compte pas dans le découpage (floue et légère, comme l'ombre).
    assert moteur_lueur.mesure("Franchement,") == pytest.approx(moteur_simple.mesure("Franchement,"))
    orange = [
        c for x in range(halo.image.width()) for y in range(0, halo.image.height(), 3)
        if (c := halo.image.pixelColor(x, y)).alpha() > 0 and c.red() > c.blue() + 60
    ]
    assert orange  # des pixels orangés autour des lettres
    ombre = Ombre(True, Couleur(0, 0, 0, 60.0), 0.6, 0.0, 0.5, "fond")
    avec_ombre = _moteur(replace(SANS_OMBRE, ombre=ombre, fond=Fond(FOND_LIGNE)))
    rendu = avec_ombre.rendu(sous_titres[0], mots, 1.0)
    bloc = avec_ombre.bloc(sous_titres[0], mots)
    assert rendu.y + rendu.image.height() > bloc.y + bloc.hauteur  # ombre du fond, sous le fond


def test_degrade_de_deux_couleurs(app_configuree):
    degrade = Degrade(True, Couleur(250, 204, 21), "vertical")
    moteur = _moteur(replace(SANS_OMBRE, degrade=degrade, taille_pct=8.0))
    mots, sous_titres = _sous_titres(moteur)
    image = moteur.image(sous_titres[0], mots)
    bloc = moteur.bloc(sous_titres[0], mots)
    opaques = [
        (y, c)
        for x in range(round(bloc.x), round(bloc.x + bloc.largeur))
        for y in range(round(bloc.y), round(bloc.y + bloc.hauteur))
        if (c := image.pixelColor(x, y)).alpha() == 255
    ]
    haut = min(opaques, key=lambda element: element[0])[1]
    bas = max(opaques, key=lambda element: element[0])[1]
    assert haut.blue() > bas.blue() + 60  # en haut, presque blanc ; en bas, jaune


def test_espaces_entre_les_lettres_et_les_mots(app_configuree):
    normal = _moteur(SANS_OMBRE)
    espace = _moteur(replace(SANS_OMBRE, espaces=Espaces(100.0, 0.5, 1.0)))  # 9,6 px et 19,2 px
    # Espace après chaque lettre, sauf la dernière (la ligne reste centrée sur ses lettres).
    assert espace.mesure.texte("abc") == pytest.approx(normal.mesure.texte("abc") + 2 * 9.6, abs=0.5)
    assert espace.mesure.texte("a b") - espace.mesure.texte("ab") == pytest.approx(
        normal.mesure.texte("a b") - normal.mesure.texte("ab") + 19.2 + 9.6, abs=0.5
    )
    serre = _moteur(replace(SANS_OMBRE, espaces=Espaces(150.0)))
    assert serre.metriques.interligne == pytest.approx(normal.metriques.interligne * 1.5)


def test_police_fournie_ou_remplacee(app_configuree):
    from PySide6.QtGui import QFontInfo

    from ugc_studio.rendu.moteur import police_du_texte
    from ugc_studio.rendu.polices import POLICES_FOURNIES, familles, graisse_proche, graisses, police_remplacee

    assert familles()[: len(POLICES_FOURNIES)] == list(POLICES_FOURNIES)
    assert {500, 600, 700, 800, 900} <= set(graisses("Montserrat")) and graisses("Anton") == [400]
    assert graisse_proche("Anton", 800) == 400 and graisse_proche("Poppins", 650) == 600
    police, remplacee = police_du_texte(StyleTexte(police="Montserrat", graisse=800), 77)
    info = QFontInfo(police)
    assert not remplacee and info.family().startswith("Montserrat") and info.weight() == 800
    absente = StyleTexte(police="Une police disparue")
    assert police_remplacee(absente)
    moteur = _moteur(absente)
    assert moteur.police_remplacee and QFontInfo(moteur.police).family().startswith("Inter")


def test_importer_une_police(app_configuree, tmp_path):
    from ugc_studio.chemins import dossier_ressources
    from ugc_studio.rendu.polices import ErreurPolice, dossier_polices_importees, importer_police

    source = tmp_path / "Ma police.ttf"
    source.write_bytes((dossier_ressources() / "polices" / "BebasNeue-Regular.ttf").read_bytes())
    assert importer_police(source) == "Bebas Neue"
    assert (dossier_polices_importees() / "Ma police.ttf").read_bytes() == source.read_bytes()
    assert importer_police(source) == "Bebas Neue"  # déjà là : pas de seconde copie
    assert len(list(dossier_polices_importees().iterdir())) == 1
    fausse = tmp_path / "pas une police.ttf"
    fausse.write_bytes(b"rien a voir")
    with pytest.raises(ErreurPolice, match="pas une police lisible"):
        importer_police(fausse)
    assert not (dossier_polices_importees() / "pas une police.ttf").exists()
    with pytest.raises(ErreurPolice, match=".ttf ou .otf"):
        importer_police(tmp_path / "image.png")


def test_apercu_a_100_pour_cent_identique_a_l_export_avec_les_effets(app_configuree, qtbot):
    """Même avec contour, fond, lueur, ombre et dégradé, l'aperçu à 100 % est l'image de l'export."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPainter

    from ugc_studio.ui.composants.apercu import FOND_GRIS, ZOOM_REEL, ToileApercu, ZoneApercu
    from ugc_studio.ui.theme import CouleursApercu, qcolor

    style = StyleTexte(
        police="Poppins", graisse=800, degrade=Degrade(True, Couleur(250, 204, 21)), contour=Contour(True),
        ombre=Ombre(True, portee="fond"), lueur=Lueur(True), fond=Fond(FOND_LIGNE, bordure=True),
    )
    moteur = _moteur(style, 540, 960)
    mots, sous_titres = _sous_titres(moteur)
    toile = ToileApercu()
    zone = ZoneApercu(toile)
    qtbot.addWidget(zone)
    toile.definir(moteur, mots)
    toile.definir_fond(FOND_GRIS)
    toile.definir_reperes(False, False, False)
    zone.definir_zoom(ZOOM_REEL)
    toile.montrer(sous_titres[1])
    apercu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
    toile.render(apercu, QPoint(0, 0))
    attendu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
    attendu.fill(qcolor(CouleursApercu.FOND_NEUTRE))
    peintre = QPainter(attendu)
    peintre.drawImage(QPoint(0, 0), moteur.image(sous_titres[1], mots))
    peintre.end()
    assert apercu == attendu


# --- Onglet « Texte » ----------------------------------------------------------------------------


def _style_complet() -> StyleTexte:
    return StyleTexte(
        police="Poppins",
        graisse=700,
        taille_pct=4.13,  # deux chiffres après la virgule : gardés tant qu'on ne touche pas au champ
        degrade=Degrade(True, Couleur(250, 204, 21), "horizontal"),
        contour=Contour(True, Couleur(0, 0, 0), 0.4713, "nets"),
        ombre=Ombre(True, Couleur(0, 0, 0, 55.0), 0.94, 0.1, 0.31, "fond"),
        lueur=Lueur(True, Couleur(245, 158, 11), 2.2, 70.0),
        fond=Fond(FOND_LIGNE, Couleur(255, 255, 255, 90.0), 1.9, 0.6, 1.6, True, Couleur(17, 24, 39), 0.2),
        espaces=Espaces(152.0, 0.08, 1.9),
    )


def test_onglet_texte_montre_et_rend_le_style_exact(app_configuree, qtbot):
    from ugc_studio.ui.pages.sous_titres.onglet_texte import OngletTexte

    onglet = OngletTexte()
    qtbot.addWidget(onglet)
    style = _style_complet()
    onglet.charger(style, 1920, 79, False)
    assert onglet.style(StyleTexte()) == style
    assert onglet.police.currentText() == "Poppins" and onglet.graisse.currentData() == 700
    assert onglet.contour_epaisseur.champ.value() == pytest.approx(9.0)  # 0,4713 % de 1920 px, au dixième
    assert onglet.lueur_taille.texte() == "42,2 px"
    assert onglet.police_absente.isHidden()
    # Une valeur changée à la main est prise telle qu'affichée (en % de la hauteur, trois décimales).
    onglet.contour_epaisseur.champ.setValue(6.0)
    assert onglet.style(StyleTexte()).contour.epaisseur_pct == 0.312
    # V3.1 : plus de résumé à côté du titre des groupes repliés.
    assert all(not section.resume.text() for section in onglet.sections.values())


def test_reglages_d_un_effet_decoche_grises(app_configuree, qtbot):
    from ugc_studio.ui.pages.sous_titres.onglet_texte import OngletTexte

    onglet = OngletTexte()
    qtbot.addWidget(onglet)
    onglet.charger(style_de_depart(), 1920, 77, False)
    assert onglet.zone_contour.isEnabled() and not onglet.zone_ombre.isEnabled()
    assert not onglet.zone_degrade.isEnabled() and not onglet.zone_fond.isEnabled()
    onglet.ombre.setChecked(True)
    assert onglet.zone_ombre.isEnabled()
    onglet.fond.setCurrentIndex(onglet.fond.findData(FOND_MOT))
    assert onglet.zone_fond.isEnabled() and not onglet.zone_bordure.isEnabled()


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Sérum", tmp_path / "projets")
    services.projets.projet.transcription = Transcription(
        source=str(tmp_path / "pub.mp4"),
        audio="audio.wav",
        duree_s=5.0,
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
    return page.atelier


def test_nouveau_projet_en_poppins_avec_contour(atelier, services):
    """Le style de départ (V3.1 : celui du préréglage « Par défaut », Montserrat jusqu'à la 3.0.3)."""
    texte = atelier.panneau.texte
    assert texte.police.currentText() == "Poppins" and texte.graisse.currentData() == 800
    assert texte.contour.isChecked() and texte.contour_epaisseur.texte() == "5,8 px"
    assert "(Poppins Extra-grasse)" in atelier.infos_ecran.text()
    assert atelier._calcul.moteur.metriques.debord_x == pytest.approx(1920 * 0.3 / 100)


def test_changer_une_couleur_garde_le_reste_exact(atelier, services):
    avant = [s.lignes for s in atelier.sous_titres]
    atelier.panneau.texte.contour_couleur.appliquer(Couleur(239, 68, 68))
    texte = services.projets.projet.sous_titres.texte
    assert texte.contour == Contour(True, Couleur(239, 68, 68), 0.3, "arrondis")  # épaisseur exacte, pas 0,302
    assert texte.taille_pct == 4.0 and [s.lignes for s in atelier.sous_titres] == avant
    # Écrit dans le projet, relu à la réouverture.
    services.projets.ouvrir(services.projets.projet.dossier)
    assert services.projets.projet.sous_titres.texte.contour.couleur == Couleur(239, 68, 68)


def test_retablir_un_groupe(atelier, services):
    """V3.1 : le ↺ d'un groupe, une icône à côté de son titre, n'apparaît que si le groupe s'écarte du
    préréglage (sans préréglage : du style de départ) ; le nom du réglage changé passe en mauve."""
    texte = atelier.panneau.texte
    contour, fond = texte.sections["Contour"], texte.sections["Fond"]
    assert all(section.retablir.isHidden() for section in texte.sections.values())  # rien d'écarté au départ
    assert texte.contour.property("modifie") is not True
    texte.contour.setChecked(False)
    texte.fond.setCurrentIndex(texte.fond.findData(FOND_BLOC))
    assert not services.projets.projet.sous_titres.texte.contour.actif
    assert not contour.retablir.isHidden() and not fond.retablir.isHidden() and texte.sections["Ombre"].retablir.isHidden()
    assert contour.retablir.text() == "" and contour.retablir.toolTip() == "Revenir au style de départ"
    assert texte.contour.property("modifie") is True  # le texte de la case en mauve
    contour.retablir.click()
    style = services.projets.projet.sous_titres.texte
    assert style.contour == style_de_depart().contour and style.fond.mode == FOND_BLOC  # seul le contour revient
    assert contour.retablir.isHidden() and not fond.retablir.isHidden() and texte.contour.property("modifie") is not True


def test_police_absente_remplacee_par_inter(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Ancien", tmp_path / "projets")
    projet = services.projets.projet
    projet.sous_titres = replace(projet.sous_titres, texte=replace(projet.sous_titres.texte, police="Police Disparue"))
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.show()
    atelier = page.atelier
    atelier.rafraichir()
    texte = atelier.panneau.texte
    assert not texte.police_absente.isHidden() and "Police Disparue" in texte.police_absente.text()
    assert texte.police.currentText() == "Police Disparue (absente)"
    assert texte.style(projet.sous_titres.texte).police == "Police Disparue"  # le style garde son nom


def test_police_importee_choisie(atelier, services, tmp_path):
    from ugc_studio.chemins import dossier_ressources

    source = tmp_path / "Titre.ttf"
    source.write_bytes((dossier_ressources() / "polices" / "Anton-Regular.ttf").read_bytes())
    atelier.panneau.texte.importer_fichier(source)
    style = services.projets.projet.sous_titres.texte
    assert style.police == "Anton" and style.graisse == 400  # la seule graisse d'Anton
    atelier.panneau.texte.importer_fichier(tmp_path / "rien.ttf")  # fichier introuvable
    statut = atelier.panneau.texte.statut_police
    assert not statut.isHidden() and statut.text().startswith("Police non copiée")
    assert services.projets.projet.sous_titres.texte.police == "Anton"


def test_pipette_prend_une_couleur_dans_l_apercu(atelier, services, qtbot):
    from PySide6.QtCore import QPoint, Qt

    from ugc_studio.ui.composants.apercu import FOND_GRIS
    from ugc_studio.ui.theme import CouleursApercu, qcolor

    atelier.bloc_apercu.fond.bouton(FOND_GRIS).click()
    texte = atelier.panneau.texte
    atelier.prendre_une_couleur(texte.couleur)
    toile = atelier.toile
    assert toile.pipette_active and not atelier.bloc_apercu.info_pipette.isHidden()
    coin = toile.rect_video().topLeft().toPoint() + QPoint(6, 6)
    qtbot.mouseClick(toile, Qt.MouseButton.LeftButton, pos=coin)
    gris = qcolor(CouleursApercu.FOND_NEUTRE)
    assert services.projets.projet.sous_titres.texte.couleur == Couleur(gris.red(), gris.green(), gris.blue())
    assert not toile.pipette_active and atelier.bloc_apercu.info_pipette.isHidden()
    # Échap annule (la couleur ne change pas).
    atelier.prendre_une_couleur(texte.contour_couleur)
    qtbot.keyClick(texte.contour_couleur.code, Qt.Key.Key_Escape)
    assert not toile.pipette_active
    assert services.projets.projet.sous_titres.texte.contour.couleur == Couleur(0, 0, 0)


def test_studio_sur_une_colonne_quand_les_reglages_ne_tiennent_pas(atelier, qtbot):
    """Les réglages de l'onglet Texte demandent plus de place : le studio passe sur une colonne dès que
    les deux colonnes ne tiennent plus (pas seulement sous 880 px), et rien n'est coupé à droite."""
    from ugc_studio.ui.theme import Dimensions

    studio = atelier.studio
    limite = studio.largeur_deux_colonnes()
    assert limite >= Dimensions.STUDIO_DEUX_COLONNES_MIN and studio.cote_a_cote
    page = atelier.parentWidget()
    ecart = page.width() - studio.width()
    page.resize(limite + ecart - 30, 900)
    qtbot.waitUntil(lambda: not studio.cote_a_cote, timeout=2000)
    zone = atelier.defilement
    qtbot.waitUntil(lambda: zone.widget().width() <= zone.viewport().width(), timeout=2000)
