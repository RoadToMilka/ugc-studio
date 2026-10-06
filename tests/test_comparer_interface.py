"""Module Comparer (V4.1, 4.2.0) : la page, avec un faux video-compare (comparer/faux.py)."""

import sys
import zipfile
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint

from ugc_studio.comparer import faux
from ugc_studio.comparer.video_compare import COTE_A_COTE, NOM_PROGRAMME, VideoCompare
from ugc_studio.ui.pages import comparer as module_comparer
from ugc_studio.ui.pages.comparer import PREF_PROGRAMME, PageComparer
from ugc_studio.ui.theme import Dimensions

FAUX = VideoCompare((sys.executable, str(Path(faux.__file__))), "20261004-osaka")


def _page(qtbot, services, monkeypatch, telechargements: Path) -> PageComparer:
    monkeypatch.setattr(module_comparer, "dossier_telechargements", lambda: telechargements)
    page = PageComparer(services)
    qtbot.addWidget(page)
    page.resize(Dimensions.FENETRE_LARGEUR, Dimensions.FENETRE_HAUTEUR)
    page.show()
    return page


def _images(dossier: Path) -> tuple[Path, Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    gauche, droite = dossier / "Topaz.png", dossier / "App.png"
    Image.new("RGB", (108, 192), (200, 60, 40)).save(gauche)
    Image.new("RGB", (216, 384), (200, 60, 40)).save(droite)
    return gauche, droite


def test_comparer_dans_le_groupe_outils(app_configuree, qtbot, services):
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    fenetre.show()
    barre = fenetre.barre_laterale
    boutons = {b.text(): b for b in barre.boutons()}
    haut = lambda element: element.mapTo(barre, QPoint(0, 0)).y()  # noqa: E731
    assert haut(boutons["Renommer"]) < haut(boutons["Comparer"]) < haut(boutons["Réglages"])
    fenetre.afficher_module("comparer")
    assert fenetre.entete.entete_affichee().titre.text() == "Comparer"


def test_video_compare_trouve_puis_installe(app_configuree, qtbot, services, monkeypatch, tmp_path):
    telechargements = tmp_path / "Téléchargements"
    telechargements.mkdir()
    page = _page(qtbot, services, monkeypatch, telechargements)
    assert page.etat_programme.text() == "video-compare introuvable" and page.bouton_page.isVisible()
    assert not page.bouton_comparer.isEnabled() and not page.bouton_installer.isVisible()
    # Le zip téléchargé par l'utilisateur, laissé dans Téléchargements : trouvé, à installer.
    archive = telechargements / "video-compare-20261004-win10-x86_64.zip"
    with zipfile.ZipFile(archive, "w") as contenu:
        contenu.writestr(NOM_PROGRAMME, b"MZ")
        contenu.writestr("LICENSE.md", "GPL v2")
    page.chercher_video_compare()
    assert page.etat_programme.text() == "video-compare trouvé dans tes Téléchargements : video-compare-20261004-win10-x86_64.zip"
    assert page.bouton_installer.isVisible() and not page.bouton_page.isVisible()
    # Après l'installation, l'app vérifie qu'il démarre (ici, le faux).
    monkeypatch.setattr(module_comparer, "ouvrir", lambda _programme: FAUX)
    assert page.installer()
    qtbot.waitUntil(lambda: not page.occupe and page.video_compare() is not None, timeout=20_000)
    assert page.etat_programme.text() == "video-compare 20261004-osaka : prêt" and not page.bouton_installer.isVisible()
    installe = Path(services.preferences.lire(PREF_PROGRAMME))
    assert installe.name == NOM_PROGRAMME and installe.parent.name == "video-compare-20261004-win10-x86_64"
    assert archive.is_file()  # le zip ne bouge pas


def test_ce_n_est_pas_video_compare(app_configuree, qtbot, services, monkeypatch, tmp_path):
    page = _page(qtbot, services, monkeypatch, tmp_path)
    notes = tmp_path / "notes.txt"
    notes.write_text("non", encoding="utf-8")
    page.utiliser(notes)
    assert page.etat_programme.text() == "Ce n'est pas video-compare" and page.video_compare() is None
    abime = tmp_path / "vc" / NOM_PROGRAMME
    abime.parent.mkdir()
    abime.write_bytes(b"pas un programme")
    page.utiliser(abime)
    qtbot.waitUntil(lambda: not page.occupe, timeout=40_000)
    assert page.etat_programme.text() == "video-compare ne démarre pas" and page.video_compare() is None
    assert page.detail_programme.text().startswith("video-compare ne démarre pas")


def test_comparer_deux_images(app_configuree, qtbot, services, monkeypatch, tmp_path):
    monkeypatch.setenv("UGC_FAUX_VC_DUREE", "30")
    commande = tmp_path / "commande.txt"
    monkeypatch.setenv("UGC_FAUX_VC_COMMANDE", str(commande))
    page = _page(qtbot, services, monkeypatch, tmp_path)
    page.definir_video_compare(FAUX)
    assert page.etat_programme.text() == "video-compare 20261004-osaka : prêt"
    assert page.zone_depot.isVisible() and not page.bouton_comparer.isEnabled()
    gauche, droite = _images(tmp_path / "Rendus")
    page.definir_les_fichiers([gauche])  # un seul : à gauche
    assert page.fichiers() == (gauche, None) and not page.bouton_comparer.isEnabled()
    page.definir_les_fichiers([droite])  # le suivant : à droite
    assert page.fichiers() == (gauche, droite) and page.bouton_comparer.isEnabled()
    qtbot.waitUntil(lambda: page.infos["gauche"].text().startswith("108 × 192 · image"), timeout=10_000)
    assert page.infos["droite"].text().startswith("216 × 384 · image")
    page.echanger()
    assert page.fichiers() == (droite, gauche)
    page.echanger()
    page.disposition.setCurrentIndex(page.disposition.findData(COTE_A_COTE))
    page.decalage.setValue(-40)
    assert page.comparer()
    assert page.bouton_fermer.isVisible() and page.etat_comparaison.isVisible() and not page.bouton_comparer.isEnabled()
    # Les touches M puis F, dans la fenêtre de video-compare : ce qu'il écrit revient ici, en français.
    qtbot.waitUntil(lambda: page.tableau_mesures.rowCount() == 1 and page.bouton_captures.isVisible(), timeout=20_000)
    assert [page.tableau_mesures.item(0, colonne).text() for colonne in range(4)] == ["00:01,000", "0,9981", "42,13 dB", "97,31"]
    assert page.captures.text() == "Captures enregistrées dans « Rendus » : Topaz_0000.png · App_0000.png · Topaz_App_osd_0000.png"
    assert (tmp_path / "Rendus" / "Topaz_App_osd_0000.png").is_file()  # dans le dossier du fichier de gauche
    assert commande.read_text(encoding="utf-8").splitlines() == ["-m", "hstack", "-W", "-t", "-0.040", "--", str(gauche), str(droite)]
    page.fermer_la_comparaison()
    qtbot.waitUntil(lambda: not page.comparaison_ouverte() and not page.bouton_fermer.isVisible(), timeout=20_000)
    assert page.statut.text() == "" and page.bouton_comparer.isEnabled()  # fermée par l'app : pas une erreur
    autre = _page(qtbot, services, monkeypatch, tmp_path)  # réglages retenus
    assert autre.disposition.currentData() == COTE_A_COTE and autre.decalage.value() == -40
    page.vider()
    assert page.fichiers() == (None, None) and page.zone_depot.isVisible()


def test_video_compare_qui_s_arrete(app_configuree, qtbot, services, monkeypatch, tmp_path):
    monkeypatch.setenv("UGC_FAUX_VC_ECHEC", "1")
    page = _page(qtbot, services, monkeypatch, tmp_path)
    page.definir_video_compare(FAUX)
    page.definir_les_fichiers(list(_images(tmp_path / "Rendus")))
    assert page.comparer()
    qtbot.waitUntil(lambda: page.statut.text().startswith("video-compare s'est arrêté : Error: Failed to open"), timeout=20_000)
    assert not page.comparaison_ouverte() and page.bouton_comparer.isEnabled()
