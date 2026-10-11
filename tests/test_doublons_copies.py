"""Doublons (V4.3) : les copies d'une même photo, prouvées sans IA (lot 1 : la photo entière)."""

import numpy as np
import pytest
from PIL import Image

from photos_factices import au_carre_avec_bords, autres_couleurs, en_jpeg, miroir, noir_et_blanc, photo_factice, plus_petite, recadree
from ugc_studio.doublons.copies import (
    SEUIL_CONTOURS,
    Preuve,
    paires_candidates,
    prouver,
    rogner_bords_unis,
    signature,
)

ORIGINAL = photo_factice(1)

DECLINAISONS = {
    "plus petite et recompressée": plus_petite(ORIGINAL),
    "autres couleurs": autres_couleurs(ORIGINAL),
    "noir et blanc": noir_et_blanc(ORIGINAL),
    "retournée": miroir(ORIGINAL),
    "retournée et recolorée": autres_couleurs(miroir(ORIGINAL)),
    "mise au carré, bords blancs": au_carre_avec_bords(ORIGINAL),
    "mise au carré, bords noirs, plus petite": plus_petite(au_carre_avec_bords(ORIGINAL, (0, 0, 0)), 0.4, 75),
}


@pytest.mark.parametrize("nom", DECLINAISONS)
def test_chaque_declinaison_entiere_est_prouvee(nom):
    preuve = prouver(signature(ORIGINAL), signature(DECLINAISONS[nom]))
    assert preuve is not None, nom
    assert preuve.contours >= SEUIL_CONTOURS
    assert preuve.miroir == ("retournée" in nom)
    assert preuve.bords == ("bords" in nom)
    assert 95 <= preuve.proximite() <= 99


def test_ce_qui_change_et_la_note():
    meme = prouver(signature(ORIGINAL), signature(en_jpeg(ORIGINAL, 85)))
    assert meme is not None and not meme.autres_couleurs and meme.proximite() == 99
    recoloree = prouver(signature(ORIGINAL), signature(DECLINAISONS["autres couleurs"]))
    assert recoloree.autres_couleurs and recoloree.proximite() < 99
    assert prouver(signature(ORIGINAL), signature(DECLINAISONS["retournée"])).proximite() == 98
    assert prouver(signature(ORIGINAL), signature(DECLINAISONS["mise au carré, bords blancs"])).proximite() == 98


def test_la_note_reste_dans_la_zone_meme_photo():
    assert Preuve(False, 0.99, 2.0, False).proximite() == 99
    assert Preuve(True, 0.99, 2.0, False).proximite() == 98
    assert Preuve(False, 0.99, 15.0, False).proximite() == 98
    assert Preuve(False, 0.99, 30.0, False).proximite() == 97
    assert Preuve(False, 0.99, 60.0, False).proximite() == 96
    assert Preuve(True, 0.99, 60.0, True).proximite() == 95  # jamais moins de 95 %


def test_photos_differentes_jamais_prouvees():
    signatures = [signature(photo_factice(graine)) for graine in range(2, 14)]
    for i, a in enumerate(signatures):
        for b in signatures[i + 1 :]:
            assert prouver(a, b) is None


def test_recadree_pas_encore_prouvee_au_lot_1():
    # Lot 2 (4.4.0) : la photo rognée ou recadrée sera prouvée elle aussi.
    assert prouver(signature(ORIGINAL), signature(recadree(ORIGINAL, 0.6))) is None


def test_bords_unis_retires_mais_pas_un_fond_de_photo():
    avec_bords = au_carre_avec_bords(ORIGINAL)
    rognee, retires = rogner_bords_unis(avec_bords)
    assert retires
    assert abs(rognee.size[0] / rognee.size[1] - ORIGINAL.size[0] / ORIGINAL.size[1]) < 0.02
    assert rogner_bords_unis(ORIGINAL) == (ORIGINAL, False)
    # Un mur clair éclairé de côté (ses nuances, son grain) n'est pas un bord ajouté.
    lumiere = Image.linear_gradient("L").rotate(90).resize((300, 400))
    mur = Image.composite(Image.new("RGB", (300, 400), (235, 225, 210)), Image.new("RGB", (300, 400), (185, 175, 160)), lumiere)
    mur = Image.blend(mur, Image.effect_noise((300, 400), 30).convert("RGB"), 0.15)
    assert rogner_bords_unis(mur)[1] is False


def test_paires_candidates_et_paires_permises():
    signatures = [signature(ORIGINAL), signature(photo_factice(7)), signature(plus_petite(ORIGINAL)), signature(miroir(ORIGINAL))]
    candidates = set(paires_candidates(signatures))
    assert {(0, 2), (0, 3), (2, 3)} <= candidates
    assert all(1 not in paire for paire in candidates)
    permises = np.ones((4, 4), dtype=bool)
    permises[0, 2] = permises[2, 0] = False
    assert (0, 2) not in set(paires_candidates(signatures, permises))
    assert paires_candidates(signatures[:1]) == []
