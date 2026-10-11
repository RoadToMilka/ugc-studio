"""Doublons (V4.3) : l'analyse d'un lot de photos (sans interface), avec un faux modèle d'IA dont les
empreintes sont connues d'avance."""

import shutil
import threading

import numpy as np
import pytest
from PIL import PngImagePlugin

from photos_factices import miroir, photo_factice, plus_petite
from ugc_studio.doublons import analyse as module_analyse
from ugc_studio.doublons.analyse import COMPARAISON, IA, LECTURE, MODELE, AnalyseArretee, Memoire, analyser
from ugc_studio.doublons.paires import DANS_CHAQUE_DOSSIER, ENTRE_LES_DOSSIERS, IDENTIQUES, LES_DEUX, MEME_PHOTO, RESSEMBLANTES, note_de_l_ia
from ugc_studio.doublons.photos import lister_les_photos


class FauxModele:
    """Donne à chaque photo une empreinte choisie d'avance, d'après sa taille en pixels (chaque photo
    des tests a la sienne) ; une taille inconnue reçoit une empreinte au hasard (toujours la même)."""

    def __init__(self, empreintes: dict[tuple[int, int], np.ndarray] | None = None):
        self.empreintes = empreintes or {}
        self.appels = 0

    def decrire(self, image):
        self.appels += 1
        if image.size in self.empreintes:
            vecteur = self.empreintes[image.size]
        else:
            vecteur = np.random.default_rng(image.size[0] * 10_000 + image.size[1]).normal(size=768)
        return (vecteur / np.linalg.norm(vecteur)).astype(np.float32)


def _vecteurs_de_cosinus(cosinus: float):
    """Deux empreintes dont le cosinus vaut `cosinus`."""
    a = np.zeros(768)
    a[0] = 1.0
    b = np.zeros(768)
    b[0], b[1] = cosinus, np.sqrt(1 - cosinus**2)
    return a, b


@pytest.fixture
def lot(tmp_path):
    """Un dossier : une photo, sa copie exacte, la même plus petite, la même retournée (en PNG), une
    autre photo, et un fichier abîmé."""
    dossier = tmp_path / "Lot"
    dossier.mkdir()
    originale = photo_factice(1)
    originale.save(dossier / "a.jpg", quality=90)
    shutil.copyfile(dossier / "a.jpg", dossier / "a copie.jpg")
    plus_petite(originale).save(dossier / "a petite.jpg", quality=90)
    miroir(originale).save(dossier / "a miroir.png")
    photo_factice(2, (500, 640)).save(dossier / "b.jpg", quality=90)
    (dossier / "abimee.jpg").write_bytes(b"pas une image")
    return dossier


def _noms(resultat, selection):
    return [(resultat.photos[p.a].chemin.name, resultat.photos[p.b].chemin.name, p.genre, p.proximite, p.details) for p in selection.paires]


def test_sans_ia_copies_prouvees_et_photo_abimee(lot):
    evenements = []
    resultat = analyser(lister_les_photos([lot]), False, Memoire(), evenements.append)
    assert [photo.chemin.name for photo, _raison in resultat.illisibles] == ["abimee.jpg"]
    assert resultat.empreintes is None
    paires = _noms(resultat, resultat.paires(LES_DEUX, 50))
    assert paires[0][:4] == ("a copie.jpg", "a.jpg", IDENTIQUES, 100)
    # Une seule paire par groupe de copies identiques : a.jpg et sa copie ne doublent pas les paires.
    autres = {(a, b): (genre, note, details) for a, b, genre, note, details in paires[1:]}
    assert len(autres) == 3
    petite = autres[("a copie.jpg", "a petite.jpg")]
    assert petite[0] == MEME_PHOTO and petite[2] == ("autre taille",) and petite[1] == 99
    retournee = autres[("a copie.jpg", "a miroir.png")]
    assert retournee[0] == MEME_PHOTO and retournee[2] == ("autre format", "retournée") and retournee[1] == 98
    assert autres[("a miroir.png", "a petite.jpg")][0] == MEME_PHOTO
    assert all("b.jpg" not in paire[:2] for paire in paires)
    # Aucune paire « Ressemblantes » sans IA, quel que soit le seuil.
    assert resultat.paires(LES_DEUX, 50).compte(RESSEMBLANTES) == 0
    etapes = [(e.etape, e.faites, e.total) for e in evenements]
    assert etapes[0] == (LECTURE, 0, 6) and etapes[-2] == (LECTURE, 6, 6) and etapes[-1][0] == COMPARAISON
    assert MODELE not in [e.etape for e in evenements]


def test_memes_pixels_dans_deux_fichiers_differents(tmp_path):
    image = photo_factice(3, (300, 200))
    image.save(tmp_path / "un.png")
    infos = PngImagePlugin.PngInfo()
    infos.add_text("Commentaire", "enregistrée à nouveau")
    image.save(tmp_path / "deux.png", pnginfo=infos)
    assert (tmp_path / "un.png").read_bytes() != (tmp_path / "deux.png").read_bytes()
    resultat = analyser(lister_les_photos([tmp_path]), False, Memoire())
    paires = _noms(resultat, resultat.paires(LES_DEUX, 50))
    assert paires == [("deux.png", "un.png", IDENTIQUES, 100, ("mêmes pixels",))]


def test_avec_ia_paires_ressemblantes_et_notes(tmp_path):
    dossier = tmp_path / "Lot"
    dossier.mkdir()
    for graine, taille in ((10, (400, 600)), (11, (402, 600)), (12, (404, 600))):
        photo_factice(graine, taille).save(dossier / f"photo {graine}.jpg", quality=90)
    proche_a, proche_b = _vecteurs_de_cosinus(0.93)
    modele = FauxModele({(400, 600): proche_a, (402, 600): proche_b})
    evenements = []
    resultat = analyser(lister_les_photos([dossier]), True, Memoire(), evenements.append, descripteur_ia=lambda: modele)
    assert modele.appels == 3
    assert resultat.empreintes.shape == (3, 768)
    selection = resultat.paires(LES_DEUX, 85)
    assert _noms(resultat, selection) == [("photo 10.jpg", "photo 11.jpg", RESSEMBLANTES, note_de_l_ia(0.93), ())]
    assert selection.paires[0].ia == pytest.approx(0.93, abs=1e-5)
    assert [e.etape for e in evenements][:2] == [MODELE, IA]
    # La troisième (empreinte au hasard : sans rapport) ne ressort à aucun seuil.
    assert all("photo 12.jpg" not in paire[:2] for paire in _noms(resultat, resultat.paires(LES_DEUX, 50)))


def test_comparer_dans_chaque_dossier_ou_entre_les_dossiers(tmp_path):
    premier, second = tmp_path / "Premier", tmp_path / "Second"
    premier.mkdir()
    second.mkdir()
    photo_factice(20).save(premier / "p1.jpg", quality=90)
    photo_factice(20).save(second / "s1.jpg", quality=90)  # la même photo, dans l'autre dossier
    photo_factice(21, (500, 640)).save(premier / "p2.jpg", quality=90)
    photo_factice(22, (502, 640)).save(premier / "p3.jpg", quality=90)
    a, b = _vecteurs_de_cosinus(0.95)
    modele = FauxModele({(500, 640): a, (502, 640): b})
    resultat = analyser(lister_les_photos([premier, second]), True, Memoire(), descripteur_ia=lambda: modele)
    entre = {(x, y) for x, y, *_ in _noms(resultat, resultat.paires(ENTRE_LES_DOSSIERS, 85))}
    dans = {(x, y) for x, y, *_ in _noms(resultat, resultat.paires(DANS_CHAQUE_DOSSIER, 85))}
    tout = {(x, y) for x, y, *_ in _noms(resultat, resultat.paires(LES_DEUX, 85))}
    assert entre == {("p1.jpg", "s1.jpg")}
    assert dans == {("p2.jpg", "p3.jpg")}
    assert tout == entre | dans


def test_memoire_de_la_seance(lot):
    memoire = Memoire()
    photos = lister_les_photos([lot])
    lectures = []
    vraie_lecture = module_analyse._lire

    def compter(photo, signer):
        lectures.append((photo.chemin.name, signer))
        return vraie_lecture(photo, signer)

    module_analyse._lire = compter
    try:
        analyser(photos, False, memoire)
        assert len(lectures) == 6
        lectures.clear()
        analyser(photos, False, memoire)
        assert lectures == [("abimee.jpg", True)]  # seule la photo illisible est relue
        lectures.clear()
        modele = FauxModele()
        analyser(photos, True, memoire, descripteur_ia=lambda: modele)
        # Avec l'IA : relues pour leur empreinte visuelle, sans refaire leur signature.
        assert sorted(lectures) == sorted([(p.chemin.name, False) for p in photos if p.chemin.name != "abimee.jpg"] + [("abimee.jpg", True)])
        assert modele.appels == 5
        lectures.clear()
        analyser(photos, True, memoire, descripteur_ia=lambda: modele)
        assert lectures == [("abimee.jpg", True)] and modele.appels == 5
    finally:
        module_analyse._lire = vraie_lecture


def test_arreter(lot):
    arret = threading.Event()
    arret.set()
    with pytest.raises(AnalyseArretee):
        analyser(lister_les_photos([lot]), False, Memoire(), arret=arret)


def test_arreter_en_cours(lot):
    arret = threading.Event()

    def progres(avancement):
        if avancement.etape == LECTURE and avancement.faites == 2:
            arret.set()

    with pytest.raises(AnalyseArretee):
        analyser(lister_les_photos([lot]), False, Memoire(), progres, arret)


def test_lot_vide_ou_d_une_photo(tmp_path):
    resultat = analyser([], True, Memoire(), descripteur_ia=lambda: FauxModele())
    assert resultat.paires(LES_DEUX, 50).total == 0
    photo_factice(5).save(tmp_path / "seule.jpg")
    resultat = analyser(lister_les_photos([tmp_path]), True, Memoire(), descripteur_ia=lambda: FauxModele())
    assert resultat.paires(LES_DEUX, 50).total == 0


def test_copies_seulement_apres_une_analyse_avec_ia(tmp_path):
    photo_factice(30).save(tmp_path / "a.jpg", quality=90)
    plus_petite(photo_factice(30)).save(tmp_path / "a petite.jpg", quality=90)
    photo_factice(31, (500, 640)).save(tmp_path / "b.jpg", quality=90)
    photo_factice(32, (502, 640)).save(tmp_path / "c.jpg", quality=90)
    a, b = _vecteurs_de_cosinus(0.96)
    resultat = analyser(lister_les_photos([tmp_path]), True, Memoire(), descripteur_ia=lambda: FauxModele({(500, 640): a, (502, 640): b}))
    avec = _noms(resultat, resultat.paires(LES_DEUX, 85))
    sans = _noms(resultat, resultat.paires(LES_DEUX, 85, avec_ia=False))
    assert [genre for *_noms_, genre, _note, _details in avec] == [MEME_PHOTO, RESSEMBLANTES]
    assert [genre for *_noms_, genre, _note, _details in sans] == [MEME_PHOTO]
