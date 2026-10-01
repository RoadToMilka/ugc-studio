"""V2, lot 3 : fichier AVI « Motion JPEG » de la vidéo de test (structure RIFF lue en retour)."""

import struct

from ugc_studio.avi import avi_mjpeg

# Trois « images » factices (le contenu JPEG n'est pas décodé ici) : tailles paire et impaire.
IMAGES = [b"\xff\xd8image-1\xff\xd9", b"\xff\xd8img-2\xff\xd9", b"\xff\xd8image-trois\xff\xd9"]


def _morceaux(donnees: bytes, debut: int, fin: int):
    """Morceaux RIFF (code, données, position des données) entre debut et fin."""
    position = debut
    while position < fin:
        code, taille = donnees[position : position + 4], struct.unpack("<I", donnees[position + 4 : position + 8])[0]
        yield code, donnees[position + 8 : position + 8 + taille], position + 8
        position += 8 + taille + taille % 2


def test_structure_du_fichier_avi():
    donnees = avi_mjpeg(IMAGES, 540, 960, 10)
    assert donnees[:4] == b"RIFF" and donnees[8:12] == b"AVI "
    assert struct.unpack("<I", donnees[4:8])[0] == len(donnees) - 8
    morceaux = {code if code != b"LIST" else contenu[:4]: (contenu, position) for code, contenu, position in _morceaux(donnees, 12, len(donnees))}
    assert set(morceaux) == {b"hdrl", b"movi", b"idx1"}
    entetes = morceaux[b"hdrl"][0]
    (code, avih, _), *_suite = list(_morceaux(entetes, 4, len(entetes)))
    assert code == b"avih" and len(avih) == 56
    duree_image, _debit, _bourrage, drapeaux, nombre, _initiales, flux, _tampon, largeur, hauteur = struct.unpack("<10I", avih[:40])
    assert (duree_image, nombre, flux, largeur, hauteur) == (100_000, 3, 1, 540, 960) and drapeaux & 0x10

    movi, position_movi = morceaux[b"movi"]
    images = [(code, contenu) for code, contenu, _p in _morceaux(movi, 4, len(movi))]
    assert images == [(b"00dc", image) for image in IMAGES]

    # L'index donne, pour chaque image, sa position depuis le code « movi » et sa taille.
    index = morceaux[b"idx1"][0]
    for numero, image in enumerate(IMAGES):
        code, drapeaux, decalage, taille = struct.unpack("<4sIII", index[numero * 16 : numero * 16 + 16])
        assert code == b"00dc" and drapeaux == 0x10 and taille == len(image)
        debut = position_movi + decalage  # position du code « 00dc » dans le fichier
        assert donnees[debut : debut + 4] == b"00dc" and donnees[debut + 8 : debut + 8 + taille] == image
