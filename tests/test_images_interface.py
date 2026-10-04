"""Module Images (V4, lot 1) : la page, le groupe « Outils » de la barre latérale."""

from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QLabel

from ugc_studio.images.redimensionnement import BILINEAIRE, HAUTEUR, LARGEUR
from ugc_studio.ui.dialogues import messages
from ugc_studio.ui.pages.images import (
    AUTRE_DOSSIER,
    FORMATS_ACCEPTES,
    PREF_COTE,
    PREF_FILTRE,
    PREF_PIXELS,
    PREF_QUALITE,
    SOUS_DOSSIER,
    PageImages,
)
from ugc_studio.ui.theme import Dimensions


def _dossier(tmp_path):
    source = tmp_path / "Produits"
    source.mkdir()
    Image.new("RGB", (1200, 900), (200, 60, 40)).save(source / "grande.jpg", quality=80)
    Image.new("RGBA", (400, 200), (0, 0, 255, 128)).save(source / "petite.png")  # ×3 : fortement agrandie
    Image.new("RGB", (800, 600), (10, 200, 10)).save(source / "exacte.webp")
    (source / "notes.txt").write_text("pas une image", encoding="utf-8")
    return source


def _page(qtbot, services) -> PageImages:
    page = PageImages(services)
    qtbot.addWidget(page)
    page.resize(Dimensions.FENETRE_LARGEUR, Dimensions.FENETRE_HAUTEUR)
    page.show()
    return page


def _ouvrir(qtbot, page, dossier) -> None:
    page.ouvrir(dossier)
    qtbot.waitUntil(lambda: not page.occupe, timeout=10_000)


def test_groupe_outils_dans_la_barre_laterale(app_configuree, qtbot, services):
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    fenetre.show()
    barre = fenetre.barre_laterale
    assert barre.titre_outils is not None and barre.titre_outils.text() == "Outils"
    boutons = {b.text(): b for b in barre.boutons()}
    haut = lambda element: element.mapTo(barre, QPoint(0, 0)).y()  # noqa: E731
    # Le nom du groupe sous le dernier module d'une pub, au-dessus de son premier outil.
    assert haut(boutons["Sous-titres"]) < haut(barre.titre_outils) < haut(boutons["Images"]) < haut(boutons["Réglages"])
    fenetre.afficher_module("images")
    entete = fenetre.entete.entete_affichee()
    assert entete is fenetre.page("images").entete and entete.titre.text() == "Images"  # sans nom de projet


def test_textes_de_la_zone_de_depot_entiers(app_configuree, qtbot, services):
    """Les textes de la zone de dépôt, centrés, sont écrits en entier, même quand ils passent à la
    ligne : posés avec un alignement, Qt les coupait (« Glisse un dossier » au lieu de « Glisse un
    dossier d'images ici », vu sur les captures du lot 1)."""
    page = _page(qtbot, services)
    qtbot.waitExposed(page)
    etiquettes = [e for e in page.zone_depot.findChildren(QLabel) if e.wordWrap()]
    assert {e.text() for e in etiquettes} == {"Glisse un dossier d'images ici", FORMATS_ACCEPTES}
    for largeur in (Dimensions.FENETRE_LARGEUR, 300):  # 300 px (ou le minimum de la page) : à la ligne
        page.resize(largeur, Dimensions.FENETRE_HAUTEUR)
        qtbot.wait(50)
        utile = page.zone_depot.layout().contentsRect().width()
        for etiquette in etiquettes:
            assert etiquette.width() == utile  # toute la largeur, le texte centré dedans
            assert etiquette.height() >= etiquette.heightForWidth(etiquette.width())


def test_redimensionner_un_dossier(app_configuree, qtbot, services, tmp_path):
    source = _dossier(tmp_path)
    page = _page(qtbot, services)
    assert not page.cadre_resume.isVisible() and not page.bouton_redimensionner.isEnabled()  # pas encore de dossier
    _ouvrir(qtbot, page, source)
    # Les images dans l'ordre de l'Explorateur, leurs formats dans cet ordre ; le texte n'est pas une image.
    assert page.compte.text() == "3 images (WebP, JPG, PNG)"
    assert page.cadre_resume.isVisible() and page.tableau.rowCount() == 3
    page.cote.setCurrentIndex(page.cote.findData(HAUTEUR))
    page.pixels.setValue(600)
    assert page.resume.text() == "3 images à 600 px de haut : 1 réduite, 1 agrandie, 1 déjà à la bonne taille."
    assert page.alertes.text() == "1 image agrandie plus de 2 fois : elle paraîtra plus douce."
    assert page.sortie.itemText(0) == "Sous-dossier « 600 px de haut »"
    lignes = [[page.tableau.item(rang, colonne).text() for colonne in range(4)] for rang in range(3)]
    assert lignes == [
        ["exacte.webp", "800 × 600", "800 × 600", "inchangée"],
        ["grande.jpg", "1200 × 900", "800 × 600", "réduite (× 0,67)"],
        ["petite.png", "400 × 200", "1200 × 600", "agrandie (× 3,00)"],
    ]
    assert page.redimensionner()
    qtbot.waitUntil(lambda: not page.occupe, timeout=20_000)
    sortie = source / "600 px de haut"
    tailles = {}
    for nom in ("grande.jpg", "petite.png", "exacte.webp"):
        with Image.open(sortie / nom) as image:
            tailles[nom] = image.size
    assert tailles == {"grande.jpg": (800, 600), "petite.png": (1200, 600), "exacte.webp": (800, 600)}
    assert page.statut.text().startswith("3 images enregistrées en ") and page.statut.text().endswith(" dans « 600 px de haut ».")
    assert page.bouton_ouvrir.isVisible() and not page.zone_avancement.isVisible()
    assert page.bouton_renommer.isVisible()  # « Trier et renommer » (V4, lot 2)
    # Relancer : les images du même nom sont signalées (elles seraient remplacées).
    assert page.alertes.text().endswith("3 images du même nom déjà dans « 600 px de haut » : elles seront remplacées.")


def test_remplacer_demande_confirmation(app_configuree, qtbot, services, tmp_path, monkeypatch):
    source = _dossier(tmp_path)
    sortie = source / "600 px de haut"
    sortie.mkdir()
    (sortie / "grande.jpg").write_bytes(b"ancienne")
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, source)
    page.pixels.setValue(600)
    questions = []
    monkeypatch.setattr(messages, "confirmer", lambda *args, **kwargs: questions.append(args[2]) or False)
    assert not page.redimensionner()  # « Annuler » : rien n'est fait
    assert questions == ["1 image du même nom est déjà dans « 600 px de haut »."]
    assert (sortie / "grande.jpg").read_bytes() == b"ancienne"
    monkeypatch.setattr(messages, "confirmer", lambda *args, **kwargs: True)
    assert page.redimensionner()
    qtbot.waitUntil(lambda: not page.occupe, timeout=20_000)
    with Image.open(sortie / "grande.jpg") as image:
        assert image.size == (800, 600)


def test_autre_dossier_jamais_celui_des_originaux(app_configuree, qtbot, services, tmp_path):
    source = _dossier(tmp_path)
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, source)
    page.definir_autre_dossier(source)
    page.sortie.setCurrentIndex(page.sortie.findData(AUTRE_DOSSIER))
    assert page.ligne_autre.isVisible()
    assert page.resume.text() == "Choisis un autre dossier que celui des originaux : ils ne sont jamais remplacés."
    assert not page.bouton_redimensionner.isEnabled()
    ailleurs = tmp_path / "Ailleurs"
    ailleurs.mkdir()
    page.definir_autre_dossier(ailleurs)
    assert page.dossier_de_sortie() == ailleurs and page.bouton_redimensionner.isEnabled()
    page.sortie.setCurrentIndex(page.sortie.findData(SOUS_DOSSIER))
    assert not page.ligne_autre.isVisible()


def test_reglages_retenus(app_configuree, qtbot, services):
    page = _page(qtbot, services)
    page.cote.setCurrentIndex(page.cote.findData(LARGEUR))
    page.pixels.setValue(1080)
    page.filtre.setCurrentIndex(page.filtre.findData(BILINEAIRE))
    page.qualite.setCurrentIndex(page.qualite.findData(85))
    preferences = services.preferences
    assert (preferences.lire(PREF_COTE), preferences.lire(PREF_PIXELS)) == (LARGEUR, 1080)
    assert (preferences.lire(PREF_FILTRE), preferences.lire(PREF_QUALITE)) == (BILINEAIRE, 85)
    autre = _page(qtbot, services)
    assert (autre.cote.currentData(), autre.pixels.value(), autre.filtre.currentData(), autre.qualite.currentData()) == (
        LARGEUR,
        1080,
        BILINEAIRE,
        85,
    )
    assert autre.sortie.itemText(0) == "Sous-dossier « 1080 px de large »"


def test_dossier_sans_image(app_configuree, qtbot, services, tmp_path):
    vide = tmp_path / "Vide"
    vide.mkdir()
    (vide / "notes.txt").write_text("rien", encoding="utf-8")
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, vide)
    assert page.compte.text() == "Aucune image dans ce dossier (JPG, PNG, WebP, AVIF, TIFF ou BMP)"
    assert page.resume.text() == "Aucune image à redimensionner dans ce dossier."
    assert not page.tableau.isVisible() and not page.bouton_redimensionner.isEnabled()
