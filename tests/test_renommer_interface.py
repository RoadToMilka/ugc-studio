"""Module Renommer (V4, lot 2) : la page, l'ordre par clics, l'aperçu, le renommage et son annulation."""

import os

from PIL import Image
from PySide6.QtCore import QPoint

from ugc_studio import renommage
from ugc_studio.renommage import DATE_MODIFICATION
from ugc_studio.ui.dialogues import messages
from ugc_studio.ui.pages.renommer import PREF_MASQUES_RECENTS, PageRenommer
from ugc_studio.ui.pages.renommer.grille import ROLE_CHOISIE, ROLE_NUMERO, ROLE_PROBLEME, ROLE_VIGNETTE
from ugc_studio.ui.pages.renommer.image_en_grand import FenetreImageEnGrand
from ugc_studio.ui.theme import Dimensions

NOMS = ("IMG_1.jpg", "IMG_2.png", "IMG_3.jpg", "IMG_10.webp")  # dans l'ordre de l'Explorateur


def _dossier(tmp_path):
    dossier = tmp_path / "NeMu"
    dossier.mkdir()
    for rang, nom in enumerate(NOMS):
        Image.new("RGB", (90, 120), (40 * rang, 80, 160)).save(dossier / nom)
    (dossier / "notes.txt").write_text("pas une image", encoding="utf-8")
    (dossier / "Sous-dossier").mkdir()
    return dossier


def _page(qtbot, services) -> PageRenommer:
    page = PageRenommer(services)
    qtbot.addWidget(page)
    page.resize(Dimensions.FENETRE_LARGEUR, Dimensions.FENETRE_HAUTEUR)
    page.show()
    return page


def _ouvrir(qtbot, page, dossier) -> None:
    page.ouvrir(dossier)
    qtbot.waitUntil(lambda: not page.occupe, timeout=10_000)


def _numeros(page, dossier) -> dict[str, tuple[str, bool]]:
    return {nom: (page.grille.case(dossier / nom).data(ROLE_NUMERO), bool(page.grille.case(dossier / nom).data(ROLE_CHOISIE))) for nom in NOMS}


def _tableau(page) -> list[list[str]]:
    return [[page.tableau.item(rang, colonne).text() for colonne in range(4)] for rang in range(page.tableau.rowCount())]


def test_renommer_dans_le_groupe_outils(app_configuree, qtbot, services):
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    fenetre.show()
    barre = fenetre.barre_laterale
    boutons = {b.text(): b for b in barre.boutons()}
    haut = lambda element: element.mapTo(barre, QPoint(0, 0)).y()  # noqa: E731
    assert haut(barre.titre_outils) < haut(boutons["Images"]) < haut(boutons["Renommer"]) < haut(boutons["Réglages"])
    fenetre.afficher_module("renommer")
    assert fenetre.entete.entete_affichee().titre.text() == "Renommer"


def test_l_ordre_par_clics(app_configuree, qtbot, services, tmp_path):
    dossier = _dossier(tmp_path)
    page = _page(qtbot, services)
    assert not page.cadre_ordre.isVisible() and not page.bouton_renommer.isEnabled()  # pas encore de dossier
    _ouvrir(qtbot, page, dossier)
    assert page.compte.text() == "4 images"  # ni le texte, ni le sous-dossier
    assert page.grille.chemins() == [dossier / nom for nom in NOMS]
    page.masque.setEditText("NeMu_JPG_%num%%ext%")
    # Sans clic : l'ordre de l'affichage, numéros gris.
    assert _numeros(page, dossier) == {"IMG_1.jpg": ("01", False), "IMG_2.png": ("02", False), "IMG_3.jpg": ("03", False), "IMG_10.webp": ("04", False)}
    page.cliquer(dossier / "IMG_10.webp")
    page.cliquer(dossier / "IMG_2.png")
    assert _numeros(page, dossier) == {"IMG_10.webp": ("01", True), "IMG_2.png": ("02", True), "IMG_1.jpg": ("03", False), "IMG_3.jpg": ("04", False)}
    assert page.cliquees.text() == "2 cliquées sur 4, les autres suivent"
    assert _tableau(page) == [
        ["01", "IMG_10.webp", "NeMu_JPG_01.webp", ""],
        ["02", "IMG_2.png", "NeMu_JPG_02.png", ""],
        ["03", "IMG_1.jpg", "NeMu_JPG_03.jpg", ""],
        ["04", "IMG_3.jpg", "NeMu_JPG_04.jpg", ""],
    ]
    assert page.resume.text() == "4 images : de « NeMu_JPG_01.webp » à « NeMu_JPG_04.jpg »."
    assert page.bouton_renommer.isEnabled()
    # Un nouveau clic retire le numéro : les suivantes remontent.
    page.cliquer(dossier / "IMG_10.webp")
    assert _numeros(page, dossier)["IMG_2.png"] == ("01", True) and _numeros(page, dossier)["IMG_10.webp"] == ("04", False)
    page.tout_effacer()
    assert not any(choisie for _numero, choisie in _numeros(page, dossier).values()) and not page.bouton_effacer.isEnabled()
    qtbot.waitUntil(lambda: all(page.grille.case(dossier / nom).data(ROLE_VIGNETTE) is not None for nom in NOMS), timeout=10_000)


def test_le_double_clic_ne_change_pas_l_ordre(app_configuree, qtbot, services, tmp_path):
    dossier = _dossier(tmp_path)
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, dossier)
    page.cliquer(dossier / "IMG_3.jpg")
    # Un double-clic : Qt donne d'abord un clic (l'image prend un numéro), puis le double-clic.
    page.cliquer(dossier / "IMG_1.jpg")
    page.grille.double_clic.emit(dossier / "IMG_1.jpg")
    assert page._choisies == [dossier / "IMG_3.jpg"]  # le clic du double-clic est défait
    grandes = page.findChildren(FenetreImageEnGrand)
    assert len(grandes) == 1 and grandes[0].isVisible()
    assert grandes[0].details.text().startswith("90 × 120 px · JPG · ") and grandes[0].details.text().endswith(" Ko")
    grandes[0].close()


def test_renommer_puis_annuler(app_configuree, qtbot, services, tmp_path, monkeypatch):
    dossier = _dossier(tmp_path)
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, dossier)
    page.masque.setEditText("NeMu_JPG_%num%%ext%")
    page.cliquer(dossier / "IMG_10.webp")
    assert not page.bouton_annuler.isEnabled()  # rien à annuler
    assert page.renommer()
    qtbot.waitUntil(lambda: not page.occupe, timeout=10_000)
    images = sorted(f.name for f in dossier.iterdir() if f.is_file() and f.suffix != ".txt")
    assert images == ["NeMu_JPG_01.webp", "NeMu_JPG_02.jpg", "NeMu_JPG_03.png", "NeMu_JPG_04.jpg"]
    assert page.statut.text() == "4 images renommées."
    assert page._choisies == [] and page.grille.chemins()[0] == dossier / "NeMu_JPG_01.webp"  # relu, dans l'ordre
    assert services.preferences.lire(PREF_MASQUES_RECENTS)[0] == "NeMu_JPG_%num%%ext%"
    assert page.bouton_annuler.isEnabled() and "4 images dans « NeMu »" in page.bouton_annuler.toolTip()
    questions = []
    monkeypatch.setattr(messages, "confirmer", lambda *args, **kwargs: questions.append(args[2]) or True)
    assert page.annuler_le_dernier()
    qtbot.waitUntil(lambda: not page.occupe, timeout=10_000)
    assert questions == ["Remettre les anciens noms de 4 images dans « NeMu » ?"]
    assert sorted(f.name for f in dossier.iterdir() if f.is_file() and f.suffix != ".txt") == sorted(NOMS)
    assert page.statut.text() == "Anciens noms remis : 4 images." and not page.bouton_annuler.isEnabled()


def test_masque_inutilisable_et_nom_impossible(app_configuree, qtbot, services, tmp_path):
    dossier = _dossier(tmp_path)
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, dossier)
    page.masque.setEditText("photo%ext%")
    assert page.resume.text().startswith("Le masque doit contenir %num%") and not page.bouton_renommer.isEnabled()
    assert _numeros(page, dossier)["IMG_1.jpg"] == ("01", False)  # les numéros restent visibles
    page.masque.setEditText("LPT%num%%ext%")
    page.depart.setValue(9)
    page.chiffres.setValue(1)
    assert page.grille.case(dossier / "IMG_1.jpg").data(ROLE_PROBLEME)  # LPT9.jpg : nom réservé
    assert _tableau(page)[0][3] == "« LPT9 » est un nom réservé par Windows."
    assert not page.bouton_renommer.isEnabled()
    page.masque.setEditText("NeMu_%num%")  # sans %ext% : permis, signalé en orange
    assert page.bouton_renommer.isEnabled() and page.alertes.isVisible()
    assert page.alertes.text().startswith("4 images sans extension")


def test_fichier_bloque(app_configuree, qtbot, services, tmp_path, monkeypatch):
    dossier = _dossier(tmp_path)
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, dossier)
    page.masque.setEditText("NeMu_%num%%ext%")
    page.cliquer(dossier / "IMG_3.jpg")
    vrai = os.rename

    def rename(source, cible):
        if str(source).endswith("IMG_2.png"):
            raise PermissionError(13, "Fichier ouvert dans une autre app", str(source))
        vrai(source, cible)

    monkeypatch.setattr(renommage.os, "rename", rename)
    assert page.renommer()
    qtbot.waitUntil(lambda: not page.occupe, timeout=10_000)
    assert page.statut.text().startswith("« IMG_2.png » est ouvert dans une autre app")
    assert sorted(f.name for f in dossier.iterdir() if f.is_file() and f.suffix != ".txt") == sorted(NOMS)
    assert page._choisies == [dossier / "IMG_3.jpg"]  # les clics sont gardés
    assert not page.bouton_annuler.isEnabled()


def test_affichage_par_date_et_reglages_retenus(app_configuree, qtbot, services, tmp_path):
    dossier = _dossier(tmp_path)
    for rang, nom in enumerate(reversed(NOMS)):  # IMG_10 la plus ancienne… IMG_1 la plus récente
        os.utime(dossier / nom, (1_700_000_000 + rang * 60, 1_700_000_000 + rang * 60))
    page = _page(qtbot, services)
    _ouvrir(qtbot, page, dossier)
    page.tri.setCurrentIndex(page.tri.findData(DATE_MODIFICATION))
    assert [chemin.name for chemin in page.grille.chemins()] == list(reversed(NOMS))
    page.depart.setValue(5)
    page.pas.setValue(10)
    page.masque.setEditText("promo_%num%%ext%")
    autre = _page(qtbot, services)
    assert autre.tri.currentData() == DATE_MODIFICATION and autre.masque_saisi() == "promo_%num%%ext%"
    assert (autre.depart.value(), autre.chiffres.value(), autre.pas.value()) == (5, 2, 10)


def test_trier_et_renommer_depuis_images(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    dossier = _dossier(tmp_path)
    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    fenetre.show()
    fenetre.afficher_module("images")
    fenetre.page("images").renommer_demande.emit(dossier)
    assert fenetre.module_actuel() == "renommer"
    page = fenetre.page("renommer")
    qtbot.waitUntil(lambda: not page.occupe, timeout=10_000)
    assert page.compte.text() == "4 images"
