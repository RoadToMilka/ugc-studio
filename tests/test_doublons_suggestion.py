"""Doublons (V4.5, lot 3) : la suggestion, celle des deux photos à garder."""

from photos_factices import au_carre_avec_bords, photo_factice, plus_petite
from ugc_studio.doublons.analyse import Memoire, analyser
from ugc_studio.doublons.choix import IDENTIQUES, MEME_PHOTO, RESSEMBLANTES
from ugc_studio.doublons.paires import LES_DEUX
from ugc_studio.doublons.photos import lister_les_photos
from ugc_studio.doublons.recadrages import PreuveRecadrage
from ugc_studio.doublons.suggestion import Suggestion, nom_de_copie, suggerer


def _suggerer(genre=MEME_PHOTO, pixels=(480_000, 480_000), formats=("JPEG", "JPEG"), octets=(90_000, 90_000), noms=("a.jpg", "b.jpg"), **autres):
    return suggerer(genre, pixels, formats, octets, noms, **autres)


def test_les_raisons_dans_l_ordre():
    assert _suggerer(RESSEMBLANTES) is None  # une question de goût
    assert _suggerer(IDENTIQUES) == Suggestion(None, "ce sont les mêmes pixels")
    assert _suggerer(IDENTIQUES, noms=("photo - Copie.jpg", "photo.jpg")) == Suggestion(1, "l'autre a un nom de copie")
    recadree = PreuveRecadrage(extrait=0, gardee=0.5, angle=0.0, miroir=False, agrandie=True, contours=0.99, carreaux=1.0, ecart_de_couleurs=1.0, correspondances=90)
    # La photo entière, même plus petite que la partie recadrée (agrandie).
    assert _suggerer(pixels=(2_000_000, 480_000), recadrage=recadree) == Suggestion(1, "la photo entière")
    tournee = PreuveRecadrage(extrait=0, gardee=0.99, angle=6.0, miroir=False, agrandie=False, contours=0.99, carreaux=1.0, ecart_de_couleurs=1.0, correspondances=90)
    assert _suggerer(pixels=(2_000_000, 480_000), recadrage=tournee) == Suggestion(0, "plus grande")  # pas recadrée : la taille compte
    assert _suggerer(pixels=(640_000, 480_000), bords_sur=0) == Suggestion(1, "sans les bords ajoutés")
    assert _suggerer(pixels=(120_000, 480_000)) == Suggestion(1, "plus grande")
    assert _suggerer(pixels=(480_000, 475_000)) is None  # 1 % de pixels en plus : la même taille
    assert _suggerer(formats=("JPEG", "PNG"), octets=(90_000, 600_000)) == Suggestion(1, "format sans perte, PNG")
    assert _suggerer(octets=(60_000, 90_000)) == Suggestion(1, "moins compressée")
    assert _suggerer(formats=("JPEG", "WEBP"), octets=(90_000, 60_000)) is None  # deux formats différents : les poids ne se comparent pas
    assert _suggerer(noms=("photo.jpg", "photo (1).jpg")) == Suggestion(0, "l'autre a un nom de copie")
    assert _suggerer() is None  # rien ne les départage
    assert _suggerer(pixels=(120_000, 480_000), autres_couleurs=True) == Suggestion(1, "plus grande", True)


def test_les_textes():
    assert Suggestion(0, "plus grande").texte() == "Suggestion : garder celle de gauche (plus grande)."
    assert Suggestion(1, "la photo entière", True).texte() == "Suggestion : garder celle de droite (la photo entière), si ses couleurs te conviennent."
    assert Suggestion(None, "ce sont les mêmes pixels").texte() == "Suggestion : garder l'une ou l'autre (ce sont les mêmes pixels)."


def test_les_noms_de_copies():
    for nom in ("photo - Copie.jpg", "photo - Copie (2).jpg", "photo - copy.png", "Copie de photo.jpg", "Copy of photo.jpg", "photo (1).jpg", "photo_copie.jpg"):
        assert nom_de_copie(nom), nom
    for nom in ("photo.jpg", "TestClaude_107.jpg", "copieur.jpg", "Recopie.jpg", "photo 1.jpg", "IMG_2041.JPG"):
        assert not nom_de_copie(nom), nom


def test_suggestions_d_une_vraie_analyse(tmp_path):
    originale = photo_factice(7, (600, 800))
    originale.save(tmp_path / "a.jpg", quality=92)
    plus_petite(originale).save(tmp_path / "a petite.jpg", quality=80)
    au_carre_avec_bords(originale).save(tmp_path / "a au carre.jpg", quality=92)
    resultat = analyser(lister_les_photos([tmp_path]), False, Memoire())
    noms = lambda paire: (resultat.photos[paire.a].chemin.name, resultat.photos[paire.b].chemin.name)  # noqa: E731
    suggestions = {noms(paire): resultat.suggestion(paire) for paire in resultat.paires(LES_DEUX, 95).paires}
    assert suggestions[("a au carre.jpg", "a petite.jpg")] == Suggestion(1, "sans les bords ajoutés")
    assert suggestions[("a au carre.jpg", "a.jpg")] == Suggestion(1, "sans les bords ajoutés")
    assert suggestions[("a petite.jpg", "a.jpg")] == Suggestion(1, "plus grande")
