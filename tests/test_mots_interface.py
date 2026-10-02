"""V2, lot 5 (§7.5, §7.11) : les mots dans le moteur de dessin (mot actif, états, fond qui glisse,
agrandissement compté dans la place) et l'onglet « Mots » du studio."""

from dataclasses import replace

import pytest

from ugc_studio.sous_titres import MotAffiche, ReglagesSousTitres, SousTitre
from ugc_studio.style_sous_titres import (
    ACCENTUES,
    ACTIF,
    A_VENIR,
    DITS,
    JAUNE_ACTIF,
    Couleur,
    EtatMot,
    FondMot,
    Mots,
    Ombre,
    StyleTexte,
    appliquer_raccourci,
)

SANS_OMBRE = StyleTexte(ombre=Ombre(active=False), taille_pct=6.0)
TEXTES = ["Mais", "ce", "sérum", "Glowzy"]


def _mots(accentues: tuple[int, ...] = ()) -> list[MotAffiche]:
    return [MotAffiche(t, t, 1.0 + i * 0.5, 1.0 + i * 0.5 + 0.4, accentue=i in accentues) for i, t in enumerate(TEXTES)]


SOUS_TITRE = SousTitre(0.8, 3.2, ["Mais ce", "sérum Glowzy"], 0, len(TEXTES))


def _moteur(mots: Mots, texte: StyleTexte = SANS_OMBRE):
    from ugc_studio.rendu.moteur import Moteur

    return Moteur(ReglagesSousTitres(texte=texte, mots=mots), 1080, 1920)


def _couleur_au_centre(moteur, image, index: int, mots) -> tuple[int, int, int, int]:
    """Couleur la plus présente parmi les pixels opaques du mot (son remplissage)."""
    bloc = moteur.bloc(SOUS_TITRE, mots)
    place = next(p for p in bloc.mots if p.index == index)
    base = bloc.lignes[place.ligne].base
    comptes: dict = {}
    for x in range(round(place.x), round(place.x + place.largeur)):
        for y in range(round(base - moteur.metriques.ascendante * 0.6), round(base)):
            c = image.pixelColor(x, y)
            if c.alpha() > 0:
                cle = (c.red(), c.green(), c.blue(), c.alpha())
                comptes[cle] = comptes.get(cle, 0) + 1
    return max(comptes, key=comptes.get) if comptes else (0, 0, 0, 0)


def test_mot_actif_au_fil_du_temps(app_configuree):
    moteur = _moteur(appliquer_raccourci(Mots(), "surlignage"))
    mots = _mots()
    assert moteur.instant(SOUS_TITRE, mots, 0.9).actif is None  # avant le premier mot : aucun
    assert moteur.instant(SOUS_TITRE, mots, 1.0).actif == 0
    assert moteur.instant(SOUS_TITRE, mots, 1.45).actif == 0  # petit silence : le dernier dit reste allumé
    instant = moteur.instant(SOUS_TITRE, mots, 2.2)
    assert instant.actif == 2 and instant.depuis_s == pytest.approx(0.2)
    assert moteur.instant(SOUS_TITRE, mots, 3.1).actif == 3  # jusqu'à la fin du sous-titre
    assert moteur.instant(SOUS_TITRE, mots, None).actif is None
    # Avance de l'allumage : 200 ms plus tôt.
    en_avance = _moteur(appliquer_raccourci(Mots(avance_ms=200), "surlignage"))
    assert en_avance.instant(SOUS_TITRE, mots, 1.85).actif == 2
    # Sous-titre fixe : pas de mot actif (un seul dessin par sous-titre).
    assert _moteur(Mots()).instant(SOUS_TITRE, mots, 2.2).actif is None


def test_etats_des_mots(app_configuree):
    moteur = _moteur(Mots(accentues_actifs=True, actif=EtatMot(couleur=JAUNE_ACTIF)))
    mots = _mots(accentues=(3,))
    assert [moteur.etat_du_mot(i, mots, 2) for i in range(4)] == [DITS, DITS, ACTIF, ACCENTUES]
    assert [moteur.etat_du_mot(i, mots, None) for i in range(4)] == [A_VENIR, A_VENIR, A_VENIR, ACCENTUES]
    assert moteur.etat_du_mot(3, mots, 3) == ACTIF  # le mot actif l'emporte


def test_surlignage_colore_le_mot_actif(app_configuree):
    moteur = _moteur(appliquer_raccourci(Mots(), "surlignage"))
    mots = _mots()
    image = moteur.image(SOUS_TITRE, mots, 2.2)  # « sérum » actif
    assert _couleur_au_centre(moteur, image, 2, mots)[:3] == (255, 212, 59)
    assert _couleur_au_centre(moteur, image, 0, mots)[:3] == (255, 255, 255)
    assert _couleur_au_centre(moteur, image, 3, mots)[:3] == (255, 255, 255)
    # Rendus gardés en mémoire, un par mot actif.
    assert moteur.rendu(SOUS_TITRE, mots, 0.5, 1.0, 2) is moteur.rendu(SOUS_TITRE, mots, 0.5, 1.0, 2)
    assert moteur.rendu(SOUS_TITRE, mots, 0.5, 1.0, 3) is not moteur.rendu(SOUS_TITRE, mots, 0.5, 1.0, 2)


def test_apparition_et_opacite(app_configuree):
    mots = _mots()
    apparition = _moteur(appliquer_raccourci(Mots(), "apparition"))
    image = apparition.image(SOUS_TITRE, mots, 1.6)  # « ce » actif : « sérum » et « Glowzy » à venir, invisibles
    assert _couleur_au_centre(apparition, image, 1, mots)[3] == 255
    assert _couleur_au_centre(apparition, image, 3, mots) == (0, 0, 0, 0)
    attenue = _moteur(Mots(a_venir=EtatMot(opacite_pct=45.0), dits=EtatMot(opacite_pct=45.0), actif=EtatMot(opacite_pct=100.0)))
    image = attenue.image(SOUS_TITRE, mots, 2.2)
    assert _couleur_au_centre(attenue, image, 2, mots)[3] == 255
    assert _couleur_au_centre(attenue, image, 0, mots)[3] == pytest.approx(255 * 0.45, abs=3)


def test_agrandissement_compte_dans_la_place(app_configuree):
    normal = _moteur(Mots())
    agrandi = _moteur(Mots(actif=EtatMot(taille_pct=150.0)))
    largeur = normal.mesure.texte("Glowzy")
    assert agrandi.mesure("Mais Glowzy") == pytest.approx(normal.mesure("Mais Glowzy") + 0.5 * largeur)
    hauteur_texte = normal.metriques.ascendante + normal.metriques.descendante
    assert agrandi.metriques.debord_y == pytest.approx(normal.metriques.debord_y + 0.25 * hauteur_texte)
    # Le mot agrandi reste dans la boîte visible du sous-titre (rien ne sort des marges).
    mots = _mots()
    bloc = agrandi.bloc(SOUS_TITRE, mots)
    rendu = agrandi.rendu(SOUS_TITRE, mots, 1.0, 1.0, 3)
    from PySide6.QtCore import QRectF

    boite = QRectF(bloc.x, bloc.y, bloc.largeur, bloc.hauteur).adjusted(-2, -2, 2, 2)
    dessin = QRectF(rendu.x, rendu.y, rendu.image.width(), rendu.image.height()).adjusted(2, 2, -2, -2)
    assert boite.contains(dessin)


def test_fond_du_mot_actif_qui_glisse(app_configuree):
    fond = FondMot(Couleur(124, 58, 237), glisse=True, duree_glisse_ms=200)
    moteur = _moteur(Mots(actif=EtatMot(fond=fond)))
    mots = _mots()
    depart = moteur.fond_du_mot_actif(SOUS_TITRE, mots, moteur.instant(SOUS_TITRE, mots, 1.5))[0].boundingRect()
    arrivee = moteur.fond_du_mot_actif(SOUS_TITRE, mots, moteur.instant(SOUS_TITRE, mots, 1.9))[0].boundingRect()
    pendant = moteur.fond_du_mot_actif(SOUS_TITRE, mots, moteur.instant(SOUS_TITRE, mots, 1.6))[0].boundingRect()
    precedent = moteur.fond_du_mot_actif(SOUS_TITRE, mots, moteur.instant(SOUS_TITRE, mots, 1.2))[0].boundingRect()
    assert depart.left() == pytest.approx(precedent.left())  # « ce » commence : le fond part de « Mais »
    assert precedent.left() < pendant.left() < arrivee.left()
    assert moteur.en_mouvement(SOUS_TITRE, mots, 1.6)
    assert not moteur.en_mouvement(SOUS_TITRE, mots, 1.9)
    # Sur une autre ligne, le fond ne glisse pas (« sérum » commence la seconde ligne).
    saut = moteur.fond_du_mot_actif(SOUS_TITRE, mots, moteur.instant(SOUS_TITRE, mots, 2.05))[0].boundingRect()
    fixe = moteur.fond_du_mot_actif(SOUS_TITRE, mots, moteur.instant(SOUS_TITRE, mots, 2.4))[0].boundingRect()
    assert saut == fixe
    # Le fond est dessiné sous les lettres : le mot actif garde son texte blanc, sur le mauve.
    image = moteur.image(SOUS_TITRE, mots, 2.4)
    bloc = moteur.bloc(SOUS_TITRE, mots)
    place = next(p for p in bloc.mots if p.index == 2)
    marge = image.pixelColor(round(place.x - 5), round(bloc.lignes[1].base - 10))
    assert (marge.red(), marge.green(), marge.blue()) == (124, 58, 237)


def test_apercu_a_100_pour_cent_identique_a_l_export_avec_les_mots(app_configuree, qtbot):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPainter

    from ugc_studio.rendu.moteur import Moteur
    from ugc_studio.ui.composants.apercu import FOND_GRIS, ZOOM_REEL, ToileApercu, ZoneApercu
    from ugc_studio.ui.theme import CouleursApercu, qcolor

    mots_regles = replace(appliquer_raccourci(Mots(), "karaoke"), actif=EtatMot(taille_pct=112.0, fond=FondMot(glisse=True)))
    moteur = Moteur(ReglagesSousTitres(texte=SANS_OMBRE, mots=mots_regles), 540, 960)
    mots = _mots()
    toile = ToileApercu()
    zone = ZoneApercu(toile)
    qtbot.addWidget(zone)
    toile.definir(moteur, mots)
    toile.definir_fond(FOND_GRIS)
    toile.definir_reperes(False, False, False)
    zone.definir_zoom(ZOOM_REEL)
    toile.montrer(SOUS_TITRE)
    for temps in (1.55, 2.3):  # pendant le glissement, puis arrêté
        toile.definir_temps(temps)
        apercu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
        toile.render(apercu, QPoint(0, 0))
        attendu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
        attendu.fill(qcolor(CouleursApercu.FOND_NEUTRE))
        peintre = QPainter(attendu)
        peintre.drawImage(QPoint(0, 0), moteur.image(SOUS_TITRE, mots, temps))
        peintre.end()
        assert apercu == attendu


# --- Onglet « Mots » ------------------------------------------------------------------------------


def test_onglet_mots_raccourcis_et_comme_le_texte(app_configuree, qtbot):
    from ugc_studio.ui.pages.sous_titres.onglet_mots import PERSONNALISE, OngletMots

    onglet = OngletMots()
    qtbot.addWidget(onglet)
    changes = []
    onglet.change.connect(lambda: changes.append(onglet.mots()))
    texte = StyleTexte(couleur=Couleur(255, 255, 255))
    onglet.charger(Mots(), texte, 1920)
    assert onglet.raccourci.currentData() == "fixe"
    assert onglet.couleur.couleur() == Couleur(255, 255, 255)  # comme le texte
    remplissage = onglet.sections["Remplissage"]
    assert remplissage.retablir.isHidden()  # comme dans le préréglage (ici : tout « comme le texte ») : pas de ↺
    # Raccourci « Karaoké ».
    onglet.raccourci.setCurrentIndex(onglet.raccourci.findData("karaoke"))
    onglet.raccourci.activated.emit(onglet.raccourci.currentIndex())
    assert onglet.mots().dits.couleur is not None and changes
    # Une couleur changée sur le mot actif : réglage marqué, « Personnalisé ».
    onglet.etat.bouton(ACTIF).click()
    onglet.couleur.appliquer(Couleur(239, 68, 68))
    assert onglet.mots().actif.couleur == Couleur(239, 68, 68)
    assert onglet.raccourci.currentData() == PERSONNALISE
    etiquette = onglet.grilles[1].marques["couleur"]
    assert etiquette.property("role") == "legende-modifiee" and not remplissage.retablir.isHidden()
    # Karaoké agrandit aussi le mot actif (106 %) : le groupe « Taille et place » s'écarte du préréglage.
    changes_de_groupe = {titre for titre, section in onglet.sections.items() if not section.retablir.isHidden()}
    assert changes_de_groupe == {"Remplissage", "Taille et place"}
    # ↺ du groupe (V3.1, à côté de son titre) : comme dans le préréglage, donc « comme le texte ».
    remplissage.retablir.click()
    assert onglet.mots().actif.couleur is None and etiquette.property("role") == "legende"
    assert remplissage.retablir.isHidden()
    # Le fond surligné du mot actif, avec son glissement (réglage avancé du mot actif seulement).
    onglet.fond.setChecked(True)
    onglet.fond_glisse.setChecked(True)
    assert onglet.mots().actif.fond.glisse and not onglet.zone_glisse.isHidden()
    onglet.etat.bouton(DITS).click()
    assert onglet.zone_glisse.isHidden() and not onglet.fond.isChecked()


def test_onglet_mots_accentues(app_configuree, qtbot):
    from ugc_studio.ui.pages.sous_titres.onglet_mots import OngletMots

    onglet = OngletMots()
    qtbot.addWidget(onglet)
    onglet.charger(Mots(), StyleTexte(), 1920, accentues_du_script=2)
    onglet.etat.bouton(ACCENTUES).click()
    assert not onglet.zone_accentues.isHidden() and "2 mots accentués" in onglet.info_accentues.text()
    assert not onglet.zone_etat.isEnabled()  # état pas encore utilisé
    onglet.accentues_actifs.setChecked(True)
    assert onglet.mots().accentues_actifs and onglet.zone_etat.isEnabled()
    onglet.charger(Mots(), StyleTexte(), 1920, accentues_du_script=None)
    assert "ne viennent pas d'une prise" in onglet.info_accentues.text()


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.transcription import Mot, Transcription
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Sérum", tmp_path / "projets")
    services.projets.projet.transcription = Transcription(
        source=str(tmp_path / "pub.mp4"),
        audio="audio.wav",
        duree_s=5.0,
        infos={"video": True, "resolution": [1080, 1920]},
        langue="fr-FR",
        mots=[Mot(t, 1.0 + i * 0.5, 1.0 + i * 0.5 + 0.4) for i, t in enumerate(TEXTES)],
        date="2026-10-01T10:00:00+02:00",
    )
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.resize(1100, 900)
    page.show()
    page.atelier.rafraichir()
    return page.atelier


def test_studio_avec_l_onglet_mots(atelier, services):
    onglets = atelier.panneau.onglets
    assert [onglets.tabText(i) for i in range(onglets.count())] == ["Texte", "Mots", "Animations", "Position", "Écran"]
    mots = atelier.panneau.mots
    mots.raccourci.setCurrentIndex(mots.raccourci.findData("surlignage"))
    mots.raccourci.activated.emit(mots.raccourci.currentIndex())
    assert services.projets.projet.sous_titres.mots.actif.couleur == JAUNE_ACTIF
    # L'aperçu suit le temps : le mot actif change avec lui.
    atelier.lecteur.aller_a(2.2)
    atelier._actualiser_toile()
    assert atelier.toile._dessine[0] == 2
    services.projets.ouvrir(services.projets.projet.dossier)
    assert services.projets.projet.sous_titres.mots.actif.taille_pct == 108.0


def test_onglet_mots_par_rapport_au_prereglage(app_configuree, qtbot):
    """V3.1 : la référence est le préréglage du projet. Un état réglé dans le préréglage (le mot actif
    en jaune) n'est pas marqué ; le remettre « comme le texte » l'écarte du préréglage, et le ↺ y
    ramène. « Mot visible » et « Opacité » forment le groupe « Visibilité »."""
    from ugc_studio.ui.pages.sous_titres.onglet_mots import OngletMots

    onglet = OngletMots()
    qtbot.addWidget(onglet)
    prereglage = Mots(actif=EtatMot(couleur=JAUNE_ACTIF, taille_pct=108.0))
    onglet.charger(prereglage, StyleTexte(), 1920)
    onglet.definir_reference(prereglage, "Revenir au préréglage « Blanc contour noir »")
    onglet.etat.bouton(ACTIF).click()
    assert all(section.retablir.isHidden() for section in onglet.sections.values())
    assert onglet.grilles[1].marques["couleur"].property("role") == "legende"  # jaune comme le préréglage
    visibilite = onglet.sections["Visibilité"]
    assert onglet.visible.isVisibleTo(visibilite) and onglet.opacite.champ.isVisibleTo(visibilite)
    taille = onglet.sections["Taille et place"]
    onglet.taille.champ.setValue(120.0)
    assert not taille.retablir.isHidden() and taille.retablir.toolTip() == "Revenir au préréglage « Blanc contour noir »"
    taille.retablir.click()
    assert onglet.mots().actif.taille_pct == 108.0 and taille.retablir.isHidden()
    # Avance de l'allumage : son propre ↺, sur « Réglages avancés ».
    onglet.avance.setValue(40)
    assert not onglet.section_avancee.retablir.isHidden()
    onglet.section_avancee.retablir.click()
    assert onglet.mots().avance_ms == 0 and onglet.section_avancee.retablir.isHidden()
