"""V2, lot 6 (§7.5, §7.12) : animations dans le moteur de dessin (mot qui devient actif, retour en
fondu, apparition et disparition du sous-titre, place comptée avec le sommet) et onglet
« Animations » du studio."""

import pytest

from ugc_studio.sous_titres import MotAffiche, ReglagesSousTitres, SousTitre
from ugc_studio.style_sous_titres import (
    AnimationMot,
    Animations,
    EtatMot,
    Mots,
    Ombre,
    StyleTexte,
    appliquer_raccourci,
)

SANS_OMBRE = StyleTexte(ombre=Ombre(active=False), taille_pct=6.0)
TEXTES = ["Mais", "ce", "sérum", "Glowzy"]
MOTS = [MotAffiche(t, t, 1.0 + i * 0.5, 1.0 + i * 0.5 + 0.4) for i, t in enumerate(TEXTES)]
SOUS_TITRE = SousTitre(0.8, 3.2, ["Mais ce", "sérum Glowzy"], 0, len(TEXTES))


def _moteur(animations: Animations, mots: Mots = Mots()):
    from ugc_studio.rendu.moteur import Moteur

    return Moteur(ReglagesSousTitres(texte=SANS_OMBRE, mots=mots, animations=animations), 1080, 1920)


def _opaques(image) -> int:
    return sum(1 for x in range(0, image.width(), 3) for y in range(900, image.height(), 3) if image.pixelColor(x, y).alpha() > 0)


def test_valeurs_du_mot_pendant_l_animation(app_configuree):
    pop = _moteur(Animations(AnimationMot("pop", 200)))
    assert pop.valeurs_du_mot(0.0) == pytest.approx((1.0, 1.0, 0.0))
    assert pop.valeurs_du_mot(0.5)[0] == pytest.approx(1.16)
    assert pop.valeurs_du_mot(1.0) == pytest.approx((1.0, 1.0, 0.0))
    fondu = _moteur(Animations(AnimationMot("fondu")))
    assert fondu.valeurs_du_mot(0.0)[1] == pytest.approx(0.0) and fondu.valeurs_du_mot(1.0)[1] == pytest.approx(1.0)
    glissement = _moteur(Animations(AnimationMot("glissement")))
    assert glissement.valeurs_du_mot(0.0)[2] == pytest.approx(1920 * 1.5 / 100)


def test_le_sommet_compte_dans_la_place(app_configuree):
    sans, pop = _moteur(Animations()), _moteur(Animations(AnimationMot("pop")))
    assert pop.metriques.croissance == pytest.approx(0.16) and sans.metriques.croissance == 0
    assert pop.mesure("Mais Glowzy") == pytest.approx(sans.mesure("Mais Glowzy") + 0.16 * sans.mesure.texte("Glowzy"))
    # Avec un mot actif déjà agrandi (108 %), le sommet s'y ajoute : 108 % × 116 %.
    surligne = _moteur(Animations(AnimationMot("pop")), appliquer_raccourci(Mots(), "surlignage"))
    assert surligne.metriques.croissance == pytest.approx(1.08 * 1.16 - 1)


def test_mot_actif_anime_puis_immobile(app_configuree):
    moteur = _moteur(Animations(AnimationMot("pop", 200)))
    assert moteur.instant(SOUS_TITRE, MOTS, 2.1).actif == 2  # une animation du mot suffit à le suivre
    assert moteur.en_mouvement(SOUS_TITRE, MOTS, 2.1)  # « sérum » commence à 2,0 s : animation de 0,2 s
    assert not moteur.en_mouvement(SOUS_TITRE, MOTS, 2.3)
    pendant, apres = moteur.image(SOUS_TITRE, MOTS, 2.1), moteur.image(SOUS_TITRE, MOTS, 2.3)
    assert pendant != apres and _opaques(pendant) > _opaques(apres)  # « sérum » plus grand au sommet
    assert apres == moteur.image(SOUS_TITRE, MOTS, 2.45)  # après l'animation : immobile


def test_retour_en_fondu(app_configuree):
    surligne = appliquer_raccourci(Mots(), "surlignage")
    moteur = _moteur(Animations(retour="fondu", retour_duree_ms=300), surligne)
    assert moteur.en_mouvement(SOUS_TITRE, MOTS, 2.1)
    assert not moteur.en_mouvement(SOUS_TITRE, MOTS, 2.35)
    instantane = _moteur(Animations(), surligne)
    assert moteur.image(SOUS_TITRE, MOTS, 2.1) != instantane.image(SOUS_TITRE, MOTS, 2.1)  # « ce » encore un peu jaune
    assert moteur.image(SOUS_TITRE, MOTS, 2.4) == instantane.image(SOUS_TITRE, MOTS, 2.4)


def test_apparition_et_disparition_du_sous_titre(app_configuree):
    moteur = _moteur(Animations(apparition="fondu", apparition_duree_ms=400, disparition="haut", disparition_duree_ms=400))
    normal = _moteur(Animations()).image(SOUS_TITRE, MOTS, 1.5)
    debut = moteur.image(SOUS_TITRE, MOTS, 0.81)  # 10 ms après le début : presque invisible
    alphas = [debut.pixelColor(x, y).alpha() for x in range(0, 1080, 3) for y in range(900, 1920, 3)]
    assert max(alphas) < 64
    assert moteur.image(SOUS_TITRE, MOTS, 1.5) == normal
    assert moteur.en_mouvement(SOUS_TITRE, MOTS, 3.0) and moteur.image(SOUS_TITRE, MOTS, 3.0) != normal  # disparition


def test_apercu_a_100_pour_cent_identique_a_l_export_avec_les_animations(app_configuree, qtbot):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPainter

    from ugc_studio.rendu.moteur import Moteur
    from ugc_studio.ui.composants.apercu import FOND_GRIS, ZOOM_REEL, ToileApercu, ZoneApercu
    from ugc_studio.ui.theme import CouleursApercu, qcolor

    reglages = ReglagesSousTitres(
        texte=SANS_OMBRE,
        mots=appliquer_raccourci(Mots(), "karaoke"),
        animations=Animations(AnimationMot("rebond", 300), "fondu", 200, "zoom", 300, "fondu", 300),
    )
    moteur = Moteur(reglages, 540, 960)
    toile = ToileApercu()
    zone = ZoneApercu(toile)
    qtbot.addWidget(zone)
    toile.definir(moteur, MOTS)
    toile.definir_fond(FOND_GRIS)
    toile.definir_reperes(False, False, False)
    zone.definir_zoom(ZOOM_REEL)
    toile.montrer(SOUS_TITRE)
    for temps in (0.9, 2.1, 3.0):  # apparition, mot animé (et retour du précédent), disparition
        toile.definir_temps(temps)
        apercu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
        toile.render(apercu, QPoint(0, 0))
        attendu = QImage(540, 960, QImage.Format.Format_ARGB32_Premultiplied)
        attendu.fill(qcolor(CouleursApercu.FOND_NEUTRE))
        peintre = QPainter(attendu)
        peintre.drawImage(QPoint(0, 0), moteur.image(SOUS_TITRE, MOTS, temps))
        peintre.end()
        # Même au milieu d'une animation : une seule image assemblée, posée telle quelle.
        assert apercu == attendu


def test_onglet_animations(app_configuree, qtbot):
    from ugc_studio.ui.pages.sous_titres.onglet_animations import OngletAnimations

    onglet = OngletAnimations()
    qtbot.addWidget(onglet)
    changes = []
    onglet.change.connect(lambda: changes.append(onglet.animations()))
    onglet.charger(Animations(), 1920)
    assert not onglet.duree.isEnabled()  # aucune animation : sa durée est grisée
    onglet.type.setCurrentIndex(onglet.type.findData("pop"))
    assert onglet.animations().mot.type == "pop" and onglet.duree.isEnabled() and changes
    assert onglet.taille_sommet.champ.value() == pytest.approx(116.0)  # valeur de l'animation choisie
    etiquette = onglet.grille_avancee.marques["taille_sommet_pct"]
    groupe = onglet.sections["Mot qui devient actif"]
    assert not groupe.retablir.isHidden()  # « Pop » s'écarte de la référence (aucune animation)
    onglet.definir_reference(onglet.animations(), "Revenir au préréglage « Mon style »")
    assert groupe.retablir.isHidden() and etiquette.property("role") == "legende"
    onglet.taille_sommet.champ.setValue(130.0)
    assert onglet.animations().mot.taille_sommet_pct == 130.0 and not groupe.retablir.isHidden()
    assert etiquette.property("role") == "legende-modifiee"
    # V3.1 : plus de ↺ au bout de la ligne ; celui du groupe remet l'animation du préréglage.
    groupe.retablir.click()
    assert onglet.animations().mot.taille_sommet_pct is None and onglet.animations().mot.type == "pop"
    assert groupe.retablir.isHidden() and etiquette.property("role") == "legende"
    onglet.retour.bouton("fondu").click()
    onglet.apparition.setCurrentIndex(onglet.apparition.findData("haut"))
    animations = onglet.animations()
    assert animations.retour == "fondu" and animations.apparition == "haut" and onglet.retour_duree.isEnabled()


def test_studio_avec_l_onglet_animations(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.transcription import Mot, Transcription
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Sérum", tmp_path / "projets")
    services.projets.projet.transcription = Transcription(
        source=str(tmp_path / "pub.mp4"), audio="audio.wav", duree_s=5.0, infos={"video": True, "resolution": [1080, 1920]},
        langue="fr-FR", mots=[Mot(t, 1.0 + i * 0.5, 1.0 + i * 0.5 + 0.4) for i, t in enumerate(TEXTES)],
        date="2026-10-01T10:00:00+02:00",
    )
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.resize(1100, 900)
    page.show()
    atelier = page.atelier
    atelier.rafraichir()
    onglets = atelier.panneau.onglets
    assert [onglets.tabText(i) for i in range(onglets.count())] == ["Texte", "Mots", "Animations", "Écran"]  # « Position » : dans l'onglet Texte (V3.3)
    animations = atelier.panneau.animations
    animations.type.setCurrentIndex(animations.type.findData("pop"))
    assert services.projets.projet.sous_titres.animations.mot.type == "pop"
    # Le sommet du pop compte dans la place : le moteur du calcul le sait.
    assert atelier._calcul.moteur.metriques.croissance == pytest.approx(0.16)
    services.projets.ouvrir(services.projets.projet.dossier)
    assert services.projets.projet.sous_titres.animations.mot == AnimationMot("pop")
    assert EtatMot() == services.projets.projet.sous_titres.mots.actif
