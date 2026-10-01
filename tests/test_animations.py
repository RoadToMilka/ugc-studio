"""V2, lot 6 (§7.5, §7.12) : animations (mot qui devient actif, retour à « déjà dit », apparition et
disparition du sous-titre) : profils, courbes, forme écrite. Sans interface."""

import json

import pytest

from ugc_studio.sous_titres import ReglagesSousTitres
from ugc_studio.style_sous_titres import (
    ANIMATIONS_DU_MOT,
    COURBE_DOUCE,
    COURBE_REBOND,
    COURBE_REGULIERE,
    GLISSEMENT_PCT,
    AnimationMot,
    Animations,
    courbe,
    en_dict,
    lire,
)


def test_sans_animation_au_depart():
    assert Animations().aucune and not AnimationMot().active
    assert ReglagesSousTitres().animations == Animations()
    # Projet de la 1.6.0 (sans « animations ») : aucune animation.
    assert ReglagesSousTitres.depuis_dict({"style": {"mots": {}}}).animations == Animations()


def test_profils_des_animations():
    pop = AnimationMot("pop").profil()
    assert (pop.depart, pop.sommet, pop.arrivee, pop.courbe) == (100.0, 116.0, 100.0, COURBE_DOUCE)
    assert pop.taille_max == 116.0 and pop.duree_s == pytest.approx(0.18)
    assert AnimationMot("rebond").profil().courbe == COURBE_REBOND
    zoom = AnimationMot("zoom", 140).profil()
    assert (zoom.depart, zoom.arrivee) == (92.0, 100.0)  # « Surligneur » : de 92 % à 100 %, 140 ms
    fondu = AnimationMot("fondu").profil()
    assert fondu.opacite_depart == 0.0 and fondu.taille_max == 100.0
    glissement = AnimationMot("glissement").profil()
    assert glissement.decalage_depart == GLISSEMENT_PCT and glissement.opacite_depart == 0.0
    # L'intensité agrandit ou réduit l'écart : pop à 50 % → sommet à 108 %.
    assert AnimationMot("pop", intensite_pct=50.0).profil().sommet == pytest.approx(108.0)
    assert AnimationMot("fondu", intensite_pct=50.0).profil().opacite_depart == pytest.approx(50.0)
    # Réglages avancés : « Mot par mot » (annexe B du document V2).
    mot_par_mot = AnimationMot("pop", 200, taille_depart_pct=60.0, taille_sommet_pct=112.0, opacite_depart_pct=0.0).profil()
    assert (mot_par_mot.depart, mot_par_mot.sommet, mot_par_mot.arrivee, mot_par_mot.opacite_depart) == (60.0, 112.0, 100.0, 0.0)
    assert set(ANIMATIONS_DU_MOT) == {"aucune", "pop", "rebond", "zoom", "fondu", "glissement"}


def test_courbes():
    for nom in (COURBE_DOUCE, COURBE_REBOND, COURBE_REGULIERE):
        assert courbe(nom, 0.0) == pytest.approx(0.0) and courbe(nom, 1.0) == pytest.approx(1.0)
    assert courbe(COURBE_REGULIERE, 0.25) == pytest.approx(0.25)
    assert courbe(COURBE_DOUCE, 0.25) > 0.25  # rapide au début, ralentit à l'arrivée
    assert max(courbe(COURBE_REBOND, t / 100) for t in range(101)) > 1.0  # dépasse un peu


def test_animations_ecrites_puis_relues():
    animations = Animations(
        AnimationMot("pop", 200, 120.0, taille_depart_pct=60.0, courbe=COURBE_REBOND),
        "fondu", 180, "haut", 250, "fondu", 150,
    )
    ecrit = ReglagesSousTitres(animations=animations).en_dict()["style"]["animations"]
    assert ecrit["mot"]["type"] == "pop" and ecrit["mot"]["taille_sommet_pct"] is None and ecrit["apparition"] == "haut"
    assert ReglagesSousTitres.depuis_dict(json.loads(json.dumps(ReglagesSousTitres(animations=animations).en_dict()))).animations == animations
    lu = lire(Animations, {"mot": {"type": "tourbillon", "duree_ms": 99999, "courbe": "folle"}, "retour": "lent", "apparition": "pop"})
    assert lu.mot == AnimationMot(duree_ms=2000) and lu.retour == "instantane" and lu.apparition == "pop"
    assert en_dict(AnimationMot())["courbe"] is None
