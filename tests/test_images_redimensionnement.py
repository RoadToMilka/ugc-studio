"""Module Images (V4, lot 1) : redimensionner toutes les images d'un dossier (sans interface)."""

import hashlib
import io
import threading

import pytest
from PIL import Image, ImageCms

from ugc_studio.dossiers import fichiers_du_dossier, images_du_dossier, trier_comme_l_explorateur
from ugc_studio.images.redimensionnement import (
    AGRANDIE,
    BILINEAIRE,
    COMME_L_ORIGINAL,
    HAUTEUR,
    INCHANGEE,
    LARGEUR,
    ORIENTATION,
    PLUS_GRAND_COTE,
    REDUITE,
    Bilan,
    Cible,
    lire_les_images,
    planifier,
    preparer_les_images,
    taille_visee,
    webp_sans_perte,
)


def _image(chemin, taille, format_=None, mode="RGB", couleur=(200, 60, 40), **options):
    image = Image.new(mode, taille, couleur)
    image.save(chemin, format=format_, **options)
    return chemin


def _empreinte(chemin) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


# --- Taille visée ---------------------------------------------------------------------------------


def test_taille_visee_garde_les_proportions():
    hauteur = Cible(HAUTEUR, 600)
    assert taille_visee(4000, 3000, hauteur) == (800, 600)
    assert taille_visee(1080, 1920, hauteur) == (338, 600)  # 337,5 arrondi au pixel le plus proche
    assert taille_visee(400, 300, hauteur) == (800, 600)  # plus petite : agrandie (décision du 04/10/2026)
    assert taille_visee(4000, 3000, Cible(LARGEUR, 1000)) == (1000, 750)
    plus_grand = Cible(PLUS_GRAND_COTE, 1200)
    assert taille_visee(3000, 4000, plus_grand) == (900, 1200)  # en hauteur : la hauteur
    assert taille_visee(4000, 3000, plus_grand) == (1200, 900)  # en largeur : la largeur
    assert taille_visee(5000, 2, hauteur) == (1_500_000, 600)  # l'autre côté suit, même très long
    assert taille_visee(2, 5000, hauteur)[0] == 1  # jamais moins d'un pixel


def test_nom_du_dossier_de_sortie():
    assert Cible(HAUTEUR, 600).nom_du_dossier() == "600 px de haut"
    assert Cible(LARGEUR, 1080).nom_du_dossier() == "1080 px de large"
    assert Cible(PLUS_GRAND_COTE, 1200).nom_du_dossier() == "1200 px (plus grand côté)"


# --- Fichiers du dossier --------------------------------------------------------------------------


def test_ordre_de_l_explorateur_et_fichiers_ignores(tmp_path):
    for nom in ("photo10.jpg", "photo2.jpg", "Photo1.JPG", "notes.txt", "desktop.ini", "Thumbs.db"):
        (tmp_path / nom).write_bytes(b"x")
    (tmp_path / "sous-dossier").mkdir()
    (tmp_path / "sous-dossier" / "photo0.jpg").write_bytes(b"x")
    noms = [chemin.name for chemin in images_du_dossier(tmp_path)]
    # Les nombres comptent comme des nombres (2 avant 10), sans tenir compte des majuscules ; ni le
    # texte, ni les fichiers de Windows, ni le sous-dossier.
    assert noms == ["Photo1.JPG", "photo2.jpg", "photo10.jpg"]
    assert [chemin.name for chemin in fichiers_du_dossier(tmp_path)] == ["notes.txt", "Photo1.JPG", "photo2.jpg", "photo10.jpg"]


def test_tri_naturel_avec_plusieurs_nombres(tmp_path):
    chemins = [tmp_path / nom for nom in ("pub 2 v10.png", "pub 10 v1.png", "pub 2 v9.png", "PUB 1 v3.png")]
    assert [c.name for c in trier_comme_l_explorateur(chemins)] == ["PUB 1 v3.png", "pub 2 v9.png", "pub 2 v10.png", "pub 10 v1.png"]


# --- Plan -----------------------------------------------------------------------------------------


def _dossier_de_trois(tmp_path):
    source = tmp_path / "Produits"
    source.mkdir()
    _image(source / "grande.jpg", (1200, 900), quality=80)
    _image(source / "petite.png", (400, 200))  # ×3 en hauteur : fortement agrandie
    _image(source / "exacte.webp", (800, 600))
    return source


def test_plan_reduit_agrandit_et_copie(tmp_path):
    source = _dossier_de_trois(tmp_path)
    images, illisibles = lire_les_images(source)
    assert [image.chemin.name for image in images] == ["exacte.webp", "grande.jpg", "petite.png"] and not illisibles
    plan = planifier(images, Cible(HAUTEUR, 600), source / "600 px de haut")
    changements = {image.infos.chemin.name: (image.changement, image.finale) for image in plan.images}
    assert changements == {
        "grande.jpg": (REDUITE, (800, 600)),
        "petite.png": (AGRANDIE, (1200, 600)),
        "exacte.webp": (INCHANGEE, (800, 600)),
    }
    assert [image.infos.chemin.name for image in plan.fortement_agrandies] == ["petite.png"]
    assert plan.resume() == "3 images à 600 px de haut : 1 réduite, 1 agrandie, 1 déjà à la bonne taille."
    assert not plan.existantes


def test_le_dossier_de_sortie_ne_peut_pas_etre_celui_des_originaux(tmp_path):
    source = _dossier_de_trois(tmp_path)
    images, _ = lire_les_images(source)
    with pytest.raises(ValueError):
        planifier(images, Cible(), source)
    with pytest.raises(ValueError):
        planifier(images, Cible(), source / "." / "")


def test_une_image_deja_dans_le_dossier_de_sortie_sera_remplacee(tmp_path):
    source = _dossier_de_trois(tmp_path)
    sortie = source / "600 px de haut"
    sortie.mkdir()
    (sortie / "grande.jpg").write_bytes(b"ancienne")
    images, _ = lire_les_images(source)
    plan = planifier(images, Cible(HAUTEUR, 600), sortie)
    assert [image.infos.chemin.name for image in plan.existantes] == ["grande.jpg"]


def test_fichier_illisible_signale(tmp_path):
    (tmp_path / "abimee.jpg").write_bytes(b"pas une image")
    _image(tmp_path / "bonne.jpg", (100, 100))
    images, illisibles = lire_les_images(tmp_path)
    assert [image.chemin.name for image in images] == ["bonne.jpg"]
    assert [(i.chemin.name, i.raison) for i in illisibles] == [("abimee.jpg", "format illisible")]


# --- Fabrication ----------------------------------------------------------------------------------


def test_toutes_a_la_taille_visee_originaux_intacts(tmp_path):
    source = _dossier_de_trois(tmp_path)
    avant = {chemin.name: _empreinte(chemin) for chemin in source.iterdir()}
    images, _ = lire_les_images(source)
    plan = planifier(images, Cible(HAUTEUR, 600), source / "600 px de haut")
    nouvelles = []
    bilan = preparer_les_images(plan, progres=nouvelles.append)
    assert (bilan.faites, bilan.erreurs, bilan.arrete) == (3, [], False)
    assert sorted(nouvelles)[-1] == (3, 3)
    for image in plan.images:
        with Image.open(image.destination) as resultat:
            assert resultat.size == image.finale
            assert resultat.format == image.infos.format
    assert {chemin.name: _empreinte(chemin) for chemin in source.iterdir() if chemin.is_file()} == avant
    assert not list((source / "600 px de haut").glob("*.en-cours*"))  # aucun fichier provisoire
    # Déjà à la bonne taille : copie exacte, sans recompression.
    assert _empreinte(source / "600 px de haut" / "exacte.webp") == avant["exacte.webp"]


def test_photo_couchee_tournee_avant_le_calcul(tmp_path):
    exif = Image.Exif()
    exif[ORIENTATION] = 6  # couchée : à tourner d'un quart de tour à l'affichage
    exif[0x010F] = "Apple"
    _image(tmp_path / "iphone.jpg", (400, 300), exif=exif.tobytes())
    images, _ = lire_les_images(tmp_path)
    assert (images[0].largeur, images[0].hauteur) == (300, 400)  # telle qu'on la voit
    plan = planifier(images, Cible(HAUTEUR, 600), tmp_path / "sortie")
    assert plan.images[0].finale == (450, 600)
    preparer_les_images(plan)
    with Image.open(tmp_path / "sortie" / "iphone.jpg") as resultat:
        assert resultat.size == (450, 600)
        assert resultat.getexif().get(ORIENTATION, 1) == 1  # orientation appliquée, plus de note
        assert resultat.getexif().get(0x010F) == "Apple"  # les autres informations restent


def test_profil_de_couleurs_garde(tmp_path):
    profil = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    _image(tmp_path / "p3.jpg", (1000, 800), icc_profile=profil)
    _image(tmp_path / "p3.png", (1000, 800), icc_profile=profil)
    images, _ = lire_les_images(tmp_path)
    preparer_les_images(planifier(images, Cible(HAUTEUR, 400), tmp_path / "sortie"))
    for nom in ("p3.jpg", "p3.png"):
        with Image.open(tmp_path / "sortie" / nom) as resultat:
            assert resultat.info.get("icc_profile") == profil


def test_qualite_jpg_comme_l_original_ou_choisie(tmp_path):
    _image(tmp_path / "web.jpg", (1000, 800), quality=70)
    with Image.open(tmp_path / "web.jpg") as original:
        tables = original.quantization
    images, _ = lire_les_images(tmp_path)
    plan = planifier(images, Cible(HAUTEUR, 400), tmp_path / "comme")
    preparer_les_images(plan, qualite=COMME_L_ORIGINAL)
    with Image.open(tmp_path / "comme" / "web.jpg") as resultat:
        assert resultat.quantization == tables  # même qualité que l'original
    plan = planifier(images, Cible(HAUTEUR, 400), tmp_path / "haute")
    preparer_les_images(plan, qualite=95)
    with Image.open(tmp_path / "haute" / "web.jpg") as resultat:
        assert resultat.quantization != tables


def test_png_en_palette_transparent_garde_sa_transparence(tmp_path):
    image = Image.new("P", (200, 100), 0)
    image.putpalette([255, 0, 0, 0, 0, 255] + [0] * 762)
    for x in range(100, 200):
        for y in range(100):
            image.putpixel((x, y), 1)
    image.save(tmp_path / "logo.png", transparency=0)  # moitié gauche (rouge) transparente
    images, _ = lire_les_images(tmp_path)
    preparer_les_images(planifier(images, Cible(HAUTEUR, 50), tmp_path / "sortie"))
    with Image.open(tmp_path / "sortie" / "logo.png") as resultat:
        assert resultat.mode == "RGBA" and resultat.size == (100, 50)
        assert resultat.getpixel((10, 25))[3] == 0  # transparent
        assert resultat.getpixel((90, 25)) == (0, 0, 255, 255)  # bleu opaque, sans liseré rouge


def test_webp_sans_perte_reste_sans_perte(tmp_path):
    _image(tmp_path / "sans-perte.webp", (400, 300), lossless=True)
    _image(tmp_path / "avec-perte.webp", (400, 300), quality=80)
    assert webp_sans_perte(tmp_path / "sans-perte.webp") and not webp_sans_perte(tmp_path / "avec-perte.webp")
    images, _ = lire_les_images(tmp_path)
    preparer_les_images(planifier(images, Cible(HAUTEUR, 150), tmp_path / "sortie"), filtre=BILINEAIRE)
    assert webp_sans_perte(tmp_path / "sortie" / "sans-perte.webp")
    assert not webp_sans_perte(tmp_path / "sortie" / "avec-perte.webp")


def test_arret_avant_le_debut(tmp_path):
    source = _dossier_de_trois(tmp_path)
    images, _ = lire_les_images(source)
    plan = planifier(images, Cible(HAUTEUR, 600), source / "sortie")
    arret = threading.Event()
    arret.set()
    bilan = preparer_les_images(plan, arret=arret)
    assert (bilan.faites, bilan.arrete) == (0, True)
    assert not list((source / "sortie").iterdir())


def test_messages_du_bilan(tmp_path):
    bilan = Bilan(tmp_path / "600 px de haut", total=50, faites=50, duree_s=6.2)
    assert bilan.message() == "50 images enregistrées en 6 s dans « 600 px de haut »."
    assert Bilan(tmp_path / "600 px de haut", total=1, faites=1, duree_s=0.2).message() == "1 image enregistrée en 1 s dans « 600 px de haut »."
    arrete = Bilan(tmp_path / "600 px de haut", total=50, faites=23, arrete=True)
    assert arrete.message() == "Arrêté : 23 images sur 50 enregistrées dans « 600 px de haut »."
    long = Bilan(tmp_path / "600 px de haut", total=50, faites=50, duree_s=72)
    assert long.message() == "50 images enregistrées en 1 min 12 s dans « 600 px de haut »."


def test_jpeg_cmjn_et_niveaux_de_gris(tmp_path):
    _image(tmp_path / "cmjn.jpg", (300, 200), mode="CMYK", couleur=(10, 20, 30, 40), quality=85)
    _image(tmp_path / "gris.jpg", (300, 200), mode="L", couleur=120, quality=85)
    images, _ = lire_les_images(tmp_path)
    bilan = preparer_les_images(planifier(images, Cible(HAUTEUR, 100), tmp_path / "sortie"))
    assert bilan.faites == 2 and not bilan.erreurs
    with Image.open(tmp_path / "sortie" / "cmjn.jpg") as cmjn, Image.open(tmp_path / "sortie" / "gris.jpg") as gris:
        assert (cmjn.mode, cmjn.size, gris.mode, gris.size) == ("CMYK", (150, 100), "L", (150, 100))


def test_lecture_rapide_sans_decoder(tmp_path):
    """La lecture du dossier ne décode pas les images (seulement leur en-tête) : un fichier tronqué
    après l'en-tête est lu, puis signalé à la fabrication, sans arrêter les autres."""
    _image(tmp_path / "bonne.png", (200, 100))
    contenu = io.BytesIO()
    Image.new("RGB", (200, 100), (1, 2, 3)).save(contenu, "PNG")
    (tmp_path / "tronquee.png").write_bytes(contenu.getvalue()[:60])
    images, illisibles = lire_les_images(tmp_path)
    plan = planifier(images, Cible(HAUTEUR, 50), tmp_path / "sortie", illisibles)
    bilan = preparer_les_images(plan)
    assert bilan.faites + len(bilan.erreurs) + len(illisibles) == 2
    assert (tmp_path / "sortie" / "bonne.png").exists()
