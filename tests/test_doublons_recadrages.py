"""Doublons (V4.4, lot 2) : la même photo recadrée, zoomée, tournée ou retournée, prouvée
(doublons/recadrages.py). La géométrie et la superposition sont testées sans le modèle d'IA (des
carreaux factices, et un repérage un peu faux, comme celui que donnent les carreaux) ; le tout, avec le
vrai modèle quand il est là."""

import cmath
import math

import numpy as np
import pytest
from PIL import Image

from photos_factices import autres_couleurs, miroir, photo_factice, plus_petite, recadree
from ugc_studio.doublons import recadrages, vision
from ugc_studio.doublons.analyse import Memoire, analyser
from ugc_studio.doublons.choix import AVEC_IA, COPIES_IA, LES_DEUX, MEME_PHOTO, SANS_IA
from ugc_studio.doublons.photos import lister_les_photos
from ugc_studio.doublons.recadrages import Carreaux, PreuveRecadrage, Reperage, Similitude, _aire_dans, _ransac, paires_a_examiner

avec_le_modele = pytest.mark.skipif(not vision.fichier_du_modele().is_file(), reason="modèle d'IA absent (outils/preparer_modeles.py)")


# --- Géométrie ----------------------------------------------------------------------------------------


def test_ransac_retrouve_la_similitude_malgre_les_fausses_correspondances():
    hasard = np.random.default_rng(3)
    z = hasard.uniform(0, 300, 120) + 1j * hasard.uniform(0, 400, 120)
    vraie = Similitude(0.8 * cmath.exp(1j * math.radians(7)), complex(40, -25))
    w = vraie.appliquer(z) + hasard.normal(0, 2, 120) + 1j * hasard.normal(0, 2, 120)
    fausses = hasard.choice(120, 50, replace=False)
    w[fausses] = hasard.uniform(0, 300, 50) + 1j * hasard.uniform(0, 400, 50)
    trouvee, gardes = _ransac(z, w, tolerance=21, graine=0)
    assert trouvee is not None and gardes.sum() >= 65
    assert abs(trouvee.echelle - 0.8) < 0.02 and abs(trouvee.angle - 7) < 1 and abs(trouvee.t - vraie.t) < 5


def test_aire_dans_un_rectangle():
    carre = np.array([0, 100, 100 + 100j, 100j])
    assert _aire_dans(carre, 200, 200) == pytest.approx(10_000)
    assert _aire_dans(carre + 50 + 50j, 100, 100) == pytest.approx(2_500)
    assert _aire_dans(carre + 500, 100, 100) == 0
    losange = np.array([50, 100 + 50j, 50 + 100j, 50j])
    assert _aire_dans(losange, 100, 100) == pytest.approx(5_000)


def test_note_et_ce_qui_change():
    preuve = PreuveRecadrage(extrait=1, gardee=0.55, angle=-6.2, miroir=False, agrandie=False, contours=0.99, carreaux=1.0, ecart_de_couleurs=2.0, correspondances=90)
    assert preuve.proximite() == 96  # 99, deux de moins (moins de 60 % gardée), un de moins (tournée)
    assert preuve.details() == ("recadrée (55 % gardée)", "tournée de 6°")
    entiere = PreuveRecadrage(extrait=1, gardee=0.99, angle=0.2, miroir=False, agrandie=True, contours=0.99, carreaux=1.0, ecart_de_couleurs=1.0, correspondances=200)
    assert entiere.proximite() == 99 and entiere.details() == ("agrandie",)
    tout = PreuveRecadrage(extrait=0, gardee=0.4, angle=12, miroir=True, agrandie=False, contours=0.98, carreaux=0.9, ecart_de_couleurs=40, correspondances=60)
    assert tout.proximite() == 95  # jamais moins de 95 % : une copie prouvée reste au-dessus de l'IA
    assert tout.details() == ("recadrée (40 % gardée)", "tournée de 12°", "retournée", "autres couleurs")


def test_paires_a_examiner_les_plus_proches_d_un_autre_groupe():
    hasard = np.random.default_rng(5)
    base = hasard.normal(size=(6, 768))
    empreintes = base / np.linalg.norm(base, axis=1, keepdims=True)
    # 0 et 1 : deux copies identiques (un groupe) ; 2 : presque la même photo que 0 ; 3 : proche de 4.
    empreintes[1] = empreintes[0]
    empreintes[2] = empreintes[0] * 0.9 + empreintes[2] * 0.3
    empreintes[3] = empreintes[4] * 0.9 + empreintes[3] * 0.3
    empreintes /= np.linalg.norm(empreintes, axis=1, keepdims=True)
    groupes = [0, 0, 2, 3, 4, 5]
    paires = paires_a_examiner(empreintes.astype(np.float32), groupes, connues=set())
    assert (0, 2) in paires and (3, 4) in paires
    assert all(1 not in paire for paire in paires)  # une seule photo par groupe de copies
    assert all(empreintes[a] @ empreintes[b] >= recadrages.COSINUS_MIN for a, b in paires)
    assert (0, 2) not in paires_a_examiner(empreintes.astype(np.float32), groupes, connues={(0, 2)})


# --- Superposition, sans le modèle --------------------------------------------------------------------


def _taille_vue_par_le_modele(image: Image.Image) -> tuple[int, int]:
    pixels = vision.preparer_pour_le_modele(image)
    return pixels.shape[3], pixels.shape[2]


def _detail(image: Image.Image) -> recadrages.Detail:
    """Le détail d'une photo, avec des carreaux factices (seule leur taille sert à la superposition)."""
    vide = np.zeros((1, 384), dtype=np.float16)
    return recadrages.detail(image, Carreaux(vide, vide, np.zeros((1, 2), dtype=np.float32), _taille_vue_par_le_modele(image)))


def _transformee(image: Image.Image, echelle: float, angle: float, decalage: complex, taille: tuple[int, int]) -> tuple[Image.Image, Similitude]:
    """L'image vue à travers une similitude (comme une photo recadrée, zoomée, tournée), et cette
    similitude, des pixels de la nouvelle image vers ceux de l'image de départ."""
    m = echelle * cmath.exp(1j * math.radians(angle))
    coefficients = (m.real, -m.imag, decalage.real, m.imag, m.real, decalage.imag)
    return image.transform(taille, Image.Transform.AFFINE, coefficients, Image.Resampling.BICUBIC), Similitude(m, decalage)


def _dans_les_pixels_du_modele(vers_a: Similitude, a: Image.Image, b: Image.Image, erreur: bool = True) -> Similitude:
    """La similitude en pixels des images vues par le modèle, un peu faussée (comme un repérage par
    carreaux : 2 % d'échelle, 0,7°, quelques pixels)."""
    ka = _taille_vue_par_le_modele(a)[0] / a.width
    kb = _taille_vue_par_le_modele(b)[0] / b.width
    m, t = vers_a.m * ka / kb, vers_a.t * ka
    if erreur:
        m, t = m * 1.02 * cmath.exp(1j * math.radians(0.7)), t + complex(4, -3)
    return Similitude(m, t)


@pytest.mark.parametrize(
    ("echelle", "angle", "decalage", "taille", "gardee"),
    [
        (1.0, 0.0, complex(120, 160), (360, 480), 0.36),  # recadrée : 36 % de la photo gardée
        (0.5, 0.0, complex(150, 200), (600, 800), 0.25),  # zoomée (une partie agrandie deux fois)
        (1.0, 8.0, complex(170, 120), (300, 420), None),  # recadrée et tournée de 8°
    ],
)
def test_superposition_d_une_partie(echelle, angle, decalage, taille, gardee):
    a = photo_factice(21, (600, 800))
    b, vers_a = _transformee(a, echelle, angle, decalage, taille)
    preuve = recadrages._prouver_avec(_detail(a), _detail(b), a.size, b.size, Reperage(_dans_les_pixels_du_modele(vers_a, a, b), 80, False))
    assert preuve is not None and preuve.extrait == 1
    assert preuve.contours >= recadrages.SEUIL_CONTOURS and preuve.carreaux >= recadrages.SEUIL_CARREAUX
    assert abs(preuve.angle - angle) < 0.5  # l'angle exact, retrouvé malgré le repérage faussé
    if gardee is not None:
        assert preuve.gardee == pytest.approx(gardee, abs=0.01)  # d'après la superposition affinée
    assert preuve.agrandie == (echelle < 0.9)
    assert not preuve.miroir and not preuve.autres_couleurs


def test_superposition_retournee_et_recolorie():
    a = photo_factice(22, (600, 800))
    b, vers_a = _transformee(a, 1.0, 0.0, complex(90, 100), (420, 560))
    b = miroir(autres_couleurs(b))
    # Le repérage se fait avec les carreaux de b retourné : la similitude part de b retourné.
    preuve = recadrages._prouver_avec(_detail(a), _detail(b), a.size, b.size, Reperage(_dans_les_pixels_du_modele(vers_a, a, b), 80, True))
    assert preuve is not None and preuve.miroir and preuve.autres_couleurs
    assert "retournée" in preuve.details() and "autres couleurs" in preuve.details()


def test_l_extrait_peut_etre_la_premiere_photo():
    """La plus petite partie est la première de la paire : la superposition se fait dans l'autre sens."""
    a = photo_factice(23, (600, 800))
    b, vers_a = _transformee(a, 1.0, 0.0, complex(100, 100), (400, 500))
    reperage = Reperage(_dans_les_pixels_du_modele(vers_a, a, b).inverse(), 80, False)
    preuve = recadrages._prouver_avec(_detail(b), _detail(a), b.size, a.size, reperage)
    assert preuve is not None and preuve.extrait == 0


def test_deux_photos_differentes_jamais_superposees():
    for graine in range(30, 36):
        a, b = photo_factice(graine, (600, 800)), photo_factice(graine + 100, (600, 800))
        for vers_a in (Similitude(1, 0), Similitude(0.8, complex(60, 80)), Similitude(cmath.exp(1j * math.radians(5)), complex(20, -10))):
            assert recadrages._prouver_avec(_detail(a), _detail(b), a.size, b.size, Reperage(vers_a, 80, False)) is None


def test_un_mauvais_reperage_ne_prouve_rien():
    """La bonne photo, mais une similitude très fausse (décalée de la moitié de la photo) : la
    superposition ne la rattrape pas, et rien n'est prouvé."""
    a = photo_factice(24, (600, 800))
    b, vers_a = _transformee(a, 1.0, 0.0, complex(120, 160), (360, 480))
    faux = _dans_les_pixels_du_modele(vers_a, a, b, erreur=False)
    faux = Similitude(faux.m, faux.t + complex(0, 100))
    assert recadrages._prouver_avec(_detail(a), _detail(b), a.size, b.size, Reperage(faux, 80, False)) is None


# --- Avec le vrai modèle --------------------------------------------------------------------------------


@avec_le_modele
def test_le_vrai_modele_prouve_les_recadrages(tmp_path):
    scene = photo_factice(41, (600, 800))
    scene.save(tmp_path / "a.jpg", quality=92)
    recadree(scene, 0.7).save(tmp_path / "a recadree.jpg", quality=88)
    _transformee(scene, 1.0, 6.0, complex(110, 90), (420, 560))[0].save(tmp_path / "a tournee.jpg", quality=88)
    miroir(recadree(autres_couleurs(scene), 0.8)).save(tmp_path / "a retournee.png")
    plus_petite(scene).save(tmp_path / "a petite.jpg", quality=80)  # entière : prouvée sans IA (copies.py)
    for graine, taille in ((42, (600, 800)), (43, (800, 600)), (44, (600, 600))):
        photo_factice(graine, taille).save(tmp_path / f"autre {graine}.jpg", quality=90)
    resultat = analyser(lister_les_photos([tmp_path]), True, Memoire())
    nom = lambda numero: resultat.photos[numero].chemin.name  # noqa: E731
    prouvees = {frozenset((nom(a), nom(b))): preuve for (a, b), preuve in resultat.recadrages.items()}
    for declinaison in ("a recadree.jpg", "a tournee.jpg", "a retournee.png"):
        assert any(declinaison in paire and paire & {"a.jpg", "a petite.jpg"} for paire in prouvees), declinaison
    assert all(not any(n.startswith("autre") for n in paire) for paire in prouvees)
    retournee = next(preuve for paire, preuve in prouvees.items() if "a retournee.png" in paire and paire & {"a.jpg", "a petite.jpg"})
    assert retournee.miroir and retournee.autres_couleurs
    # Les méthodes : sans IA, la copie entière seulement ; toutes les copies, aussi les recadrées.
    sans = resultat.paires(LES_DEUX, 95, SANS_IA)
    toutes = resultat.paires(LES_DEUX, 95, COPIES_IA)
    proches = resultat.paires(LES_DEUX, 85, AVEC_IA)
    noms = lambda selection: {frozenset((nom(p.a), nom(p.b))) for p in selection.paires}  # noqa: E731
    assert noms(sans) == {frozenset(("a.jpg", "a petite.jpg"))}
    assert noms(sans) < noms(toutes) <= noms(proches)
    assert all(p.genre == MEME_PHOTO and 95 <= p.proximite <= 99 for p in toutes.paires)
    assert any(p.recadrage is not None and "recadrée" in p.details[0] for p in toutes.paires)
    # Chaque ressemblance une seule fois : les recadrées sont des copies, pas aussi des photos proches.
    assert all(p.genre == MEME_PHOTO for p in proches.paires if frozenset((nom(p.a), nom(p.b))) in noms(toutes))
