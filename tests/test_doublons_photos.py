"""Doublons (V4.3) : les photos à comparer, et leur lecture (sans interface)."""

import hashlib
import os

from PIL import Image

from ugc_studio.doublons.photos import COTE_DE_LECTURE, Photo, lire_la_photo, lister_les_photos


def _photo(chemin, taille=(40, 30), couleur=(200, 60, 40), format_=None, **options):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", taille, couleur).save(chemin, format=format_, **options)
    return chemin


def test_formats_melanges_ordre_et_fichiers_ignores(tmp_path):
    for nom in ("photo10.jpg", "photo2.png", "Photo1.WEBP", "notes.txt", ".cachee.jpg"):
        if nom.endswith(".txt"):
            (tmp_path / nom).write_text("x")
        else:
            _photo(tmp_path / nom)
    (tmp_path / "desktop.ini").write_text("x")
    _photo(tmp_path / "sous-dossier" / "photo0.jpg")
    photos = lister_les_photos([tmp_path])
    assert [p.chemin.name for p in photos] == ["Photo1.WEBP", "photo2.png", "photo10.jpg"]
    assert all(p.dossier == 0 for p in photos)
    assert photos[0].octets == (tmp_path / "Photo1.WEBP").stat().st_size


def test_sous_dossiers_sur_demande(tmp_path):
    _photo(tmp_path / "b.jpg")
    _photo(tmp_path / "Sous 2" / "c.jpg")
    _photo(tmp_path / "Sous 10" / "d.jpg")
    _photo(tmp_path / "Sous 2" / "Plus bas" / "e.jpg")
    _photo(tmp_path / ".cache" / "f.jpg")  # dossier caché : ignoré
    assert [p.chemin.name for p in lister_les_photos([tmp_path])] == ["b.jpg"]
    noms = [p.chemin.name for p in lister_les_photos([tmp_path], sous_dossiers=True)]
    # D'abord le dossier lui-même, puis ses sous-dossiers dans l'ordre de l'Explorateur (2 avant 10).
    assert noms == ["b.jpg", "c.jpg", "e.jpg", "d.jpg"]


def test_plusieurs_dossiers_et_photo_trouvee_deux_fois(tmp_path):
    premier, second = tmp_path / "Premier", tmp_path / "Premier" / "Second"
    _photo(premier / "a.jpg")
    _photo(second / "b.jpg")
    _photo(tmp_path / "Autre" / "c.jpg")
    photos = lister_les_photos([premier, tmp_path / "Autre", second, premier], sous_dossiers=True)
    # b.jpg compte pour le premier dossier qui la contient (le Premier, avec ses sous-dossiers) ; le
    # Premier ajouté deux fois ne compte qu'une fois.
    assert [(p.chemin.name, p.dossier) for p in photos] == [("a.jpg", 0), ("b.jpg", 0), ("c.jpg", 1)]


def test_cle_change_quand_la_photo_change(tmp_path):
    chemin = _photo(tmp_path / "a.jpg")
    avant = lister_les_photos([tmp_path])[0]
    _photo(chemin, taille=(80, 60))
    os.utime(chemin, (avant.modifiee + 10, avant.modifiee + 10))
    apres = lister_les_photos([tmp_path])[0]
    assert isinstance(avant, Photo) and avant.cle != apres.cle


def test_lecture_empreinte_taille_et_format(tmp_path):
    chemin = _photo(tmp_path / "a.png", taille=(64, 48))
    lue = lire_la_photo(chemin)
    assert lue.empreinte == hashlib.sha256(chemin.read_bytes()).hexdigest()
    assert (lue.largeur, lue.hauteur, lue.format) == (64, 48, "PNG")
    assert lue.image.mode == "RGB" and lue.image.size == (64, 48)


def test_photo_de_telephone_remise_droite(tmp_path):
    image = Image.new("RGB", (60, 40), (10, 20, 30))
    exif = image.getexif()
    exif[0x0112] = 6  # enregistrée couchée : à tourner d'un quart de tour
    chemin = tmp_path / "telephone.jpg"
    image.save(chemin, exif=exif.tobytes())
    lue = lire_la_photo(chemin)
    assert (lue.largeur, lue.hauteur) == (40, 60)
    assert lue.image.size == (40, 60)


def test_transparence_posee_sur_du_blanc(tmp_path):
    image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), (5, 5, 15, 15))
    chemin = tmp_path / "detoure.png"
    image.save(chemin)
    lue = lire_la_photo(chemin)
    assert lue.image.getpixel((0, 0)) == (255, 255, 255)
    assert lue.image.getpixel((10, 10)) == (255, 0, 0)


def test_grande_photo_lue_en_plus_petit(tmp_path):
    jpg = _photo(tmp_path / "grande.jpg", taille=(4000, 3000), quality=70)
    png = _photo(tmp_path / "grande.png", taille=(3600, 2400))
    for chemin, taille in ((jpg, (4000, 3000)), (png, (3600, 2400))):
        lue = lire_la_photo(chemin)
        assert (lue.largeur, lue.hauteur) == taille  # la taille réelle du fichier
        assert COTE_DE_LECTURE <= min(lue.image.size) < 2 * COTE_DE_LECTURE  # l'image, réduite
