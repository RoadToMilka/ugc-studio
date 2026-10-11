"""Module Doublons (V4.3, lot 1) : la page, avec un faux modèle d'IA dont les empreintes sont connues."""

import shutil

import numpy as np
import pytest
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtWidgets import QLabel

from photos_factices import miroir, photo_factice, plus_petite
from ugc_studio.doublons import vision
from ugc_studio.doublons.choix import AVEC_IA, DANS_CHAQUE_DOSSIER, ENTRE_LES_DOSSIERS, IDENTIQUES, LES_DEUX, MEME_PHOTO, RESSEMBLANTES, SANS_IA
from ugc_studio.ui.pages.doublons import (
    PREF_METHODE,
    PREF_MODE,
    PREF_SEUIL,
    PREF_SOUS_DOSSIERS,
    TEXTE_SANS_ANALYSE,
    PageDoublons,
    dossiers_deposes,
    duree_lisible,
    texte_des_illisibles,
    texte_du_resume,
)
from ugc_studio.ui.pages.doublons.tableau import COLONNE_DOSSIERS, COLONNE_IMAGE_1, COLONNE_IMAGE_2, COLONNE_PROXIMITE, COLONNE_TYPE, texte_du_type
from ugc_studio.ui.theme import Dimensions


class FauxModele:
    """Empreintes choisies d'après la taille des photos (une taille par photo dans ces tests)."""

    def __init__(self, empreintes):
        self.empreintes = empreintes

    def decrire(self, image):
        vecteur = self.empreintes.get(image.size)
        if vecteur is None:
            vecteur = np.random.default_rng(image.size[0] * 10_000 + image.size[1]).normal(size=768)
        return (vecteur / np.linalg.norm(vecteur)).astype(np.float32)


def _deux_proches(cosinus: float):
    a, b = np.zeros(768), np.zeros(768)
    a[0], b[0], b[1] = 1.0, cosinus, np.sqrt(1 - cosinus**2)
    return a, b


@pytest.fixture
def faux_modele(monkeypatch):
    a, b = _deux_proches(0.95)  # note de l'IA : 94 %
    modele = FauxModele({(500, 640): a, (502, 640): b})
    monkeypatch.setattr(vision, "descripteur", lambda: modele)
    return modele


@pytest.fixture
def dossiers(tmp_path):
    """Deux dossiers : dans le premier, une photo, sa copie exacte, la même plus petite, deux photos que
    le faux modèle voit proches ; dans le second, la photo retournée, et une photo sans rapport."""
    premier, second = tmp_path / "Lot 1", tmp_path / "Lot 2"
    premier.mkdir()
    second.mkdir()
    originale = photo_factice(1)
    originale.save(premier / "a.jpg", quality=90)
    shutil.copyfile(premier / "a.jpg", premier / "a copie.jpg")
    plus_petite(originale).save(premier / "a petite.jpg", quality=90)
    photo_factice(2, (500, 640)).save(premier / "b.jpg", quality=90)
    photo_factice(3, (502, 640)).save(premier / "c.jpg", quality=90)
    miroir(originale).save(second / "a miroir.png")
    photo_factice(4, (504, 640)).save(second / "d.jpg", quality=90)
    return premier, second


def _page(qtbot, services) -> PageDoublons:
    page = PageDoublons(services)
    qtbot.addWidget(page)
    page.resize(Dimensions.FENETRE_LARGEUR, Dimensions.FENETRE_HAUTEUR)
    page.show()
    return page


def _analyser(qtbot, page) -> None:
    assert page.analyser()
    qtbot.waitUntil(lambda: not page.occupe, timeout=30_000)


def _lignes(page):
    tableau = page.tableau
    return [
        (tableau.item(rang, COLONNE_IMAGE_1).text(), tableau.item(rang, COLONNE_IMAGE_2).text(), tableau.item(rang, COLONNE_PROXIMITE).text(), tableau.item(rang, COLONNE_TYPE).text())
        for rang in range(tableau.rowCount())
    ]


def test_page_vide(app_configuree, qtbot, services):
    page = _page(qtbot, services)
    assert page.zone_depot.isVisible() and not page.liste_dossiers.isVisible()
    assert not page.bouton_analyser.isEnabled()
    assert not page.champ_mode.isVisible()  # « Comparer » : à partir de deux dossiers
    assert not page.tableau.isVisible()
    assert page.methode.valeur() == AVEC_IA and page.seuil == 85
    assert page.zone_seuil.isVisible()  # avec l'IA, le seuil choisit les paires montrées
    assert page.rappel_seuil.isVisible() and page.rappel_seuil.text() == "Vrais doublons : 85 % au moins"
    assert not page.alertes.isVisible()
    # Sous 85 % : le rappel de ne pas descendre plus bas pour ne trouver que de vrais doublons.
    page.definir_le_seuil(84)
    assert page.alertes.isVisible() and page.alertes.text().startswith("Sous 85 % : surtout des photos qui se ressemblent")
    page.definir_le_seuil(85)
    assert not page.alertes.isVisible()
    textes = {e.text() for e in page.zone_depot.findChildren(QLabel) if e.wordWrap()}
    assert "Glisse un ou plusieurs dossiers de photos ici" in textes


def test_dossiers_ajoutes_et_retires(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    premier, second = dossiers
    assert page.ajouter([premier, premier, second]) == 2
    assert page.dossiers == [premier, second]
    assert page.liste_dossiers.isVisible() and not page.zone_depot.isVisible()
    assert page.champ_mode.isVisible() and page.bouton_analyser.isEnabled()
    textes = [e.text() for e in page.liste_dossiers.findChildren(QLabel)]
    assert "Lot 1" in textes and any(texte.startswith("5 images · ") for texte in textes)
    page.retirer(second)
    assert page.dossiers == [premier] and not page.champ_mode.isVisible()


def test_analyse_sans_ia(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    page.ajouter(list(dossiers))
    page.methode.definir(SANS_IA)
    page._methode_changee(SANS_IA)
    _analyser(qtbot, page)
    lignes = _lignes(page)
    assert lignes[0] == ("a copie.jpg", "a.jpg", "100 %", "Identiques")
    genres = [paire.genre for paire in page.paires()]
    assert genres.count(IDENTIQUES) == 1 and genres.count(MEME_PHOTO) == 3 and RESSEMBLANTES not in genres
    assert ("a copie.jpg", "a miroir.png", "98 %", "Même photo") in lignes
    rang = next(k for k, ligne in enumerate(lignes) if ligne[1] == "a miroir.png" and ligne[0] == "a copie.jpg")
    assert page.tableau.item(rang, COLONNE_TYPE).toolTip() == "Même photo · autre format, retournée"
    page.choisir(rang)
    assert page.description.text().endswith("98 % · Même photo · autre format, retournée")
    page.choisir(0)
    # Copies seulement : pas de seuil, toutes les copies (prouvées) sont montrées.
    assert not page.zone_seuil.isVisible()
    assert page.resume.text() == "7 images dans 2 dossiers · 4 paires de copies : 1 identique, 3 mêmes photos."
    page.definir_le_seuil(100)  # le seuil retenu pour l'IA ne change rien ici
    assert len(page.paires()) == 4
    assert page.statut.text().startswith("Analyse terminée en ")
    assert not page.tableau.isColumnHidden(COLONNE_DOSSIERS)
    assert page.tableau.item(0, COLONNE_DOSSIERS).text() == "Lot 1"
    # La première paire est montrée dans la comparaison.
    assert page.rang_choisi() == 0 and page.deux_photos.isVisible()
    assert page.deux_photos.premiere.nom.text() == "a copie.jpg" and page.deux_photos.seconde.nom.text() == "a.jpg"
    assert page.description.text().startswith("Paire 1 sur 4 · 100 % · Identiques")
    qtbot.waitUntil(lambda: page.deux_photos.premiere.image.pixmap() is not None and not page.deux_photos.premiere.image.pixmap().isNull(), timeout=10_000)
    qtbot.waitUntil(lambda: page.vignettes_faites() == 7, timeout=10_000)


def test_le_seuil_et_comparer_sans_refaire_l_analyse(app_configuree, qtbot, services, dossiers, faux_modele):
    page = _page(qtbot, services)
    page.ajouter(list(dossiers))
    _analyser(qtbot, page)
    resultat = page.resultat
    genres = [paire.genre for paire in page.paires()]
    assert genres.count(RESSEMBLANTES) == 1  # b et c, vues proches par le faux modèle (94 %)
    ressemblantes = next(ligne for ligne in _lignes(page) if ligne[3] == "Ressemblantes")
    assert ressemblantes[:3] == ("b.jpg", "c.jpg", "94 %")
    page.definir_le_seuil(95)
    assert all(paire.proximite >= 95 for paire in page.paires()) and len(page.paires()) == 4
    page.definir_le_seuil(100)
    assert [paire.genre for paire in page.paires()] == [IDENTIQUES]
    page.definir_le_seuil(85)
    page.mode.definir(ENTRE_LES_DOSSIERS)
    page._mode_change(ENTRE_LES_DOSSIERS)
    assert {(a, b) for a, b, *_ in _lignes(page)} == {("a copie.jpg", "a miroir.png"), ("a petite.jpg", "a miroir.png")}
    page.mode.definir(DANS_CHAQUE_DOSSIER)
    page._mode_change(DANS_CHAQUE_DOSSIER)
    assert ("b.jpg", "c.jpg", "94 %", "Ressemblantes") in _lignes(page)
    assert page.resultat is resultat  # rien n'a été refait
    # Copies seulement : les paires de l'IA disparaissent, sans refaire l'analyse.
    page.methode.definir(SANS_IA)
    page._methode_changee(SANS_IA)
    assert RESSEMBLANTES not in [paire.genre for paire in page.paires()]
    assert page.resultat is resultat
    assert not page.zone_seuil.isVisible()
    page.methode.definir(AVEC_IA)
    page._methode_changee(AVEC_IA)
    assert page.zone_seuil.isVisible() and page.seuil == 85


def test_avec_ia_apres_une_analyse_sans_ia(app_configuree, qtbot, services, dossiers, faux_modele):
    page = _page(qtbot, services)
    page.ajouter([dossiers[0]])
    page.methode.definir(SANS_IA)
    page._methode_changee(SANS_IA)
    _analyser(qtbot, page)
    page.methode.definir(AVEC_IA)
    page._methode_changee(AVEC_IA)
    assert page.alertes.isVisible() and "Analyser" in page.alertes.text()
    _analyser(qtbot, page)
    assert not page.alertes.isVisible()
    assert RESSEMBLANTES in [paire.genre for paire in page.paires()]
    assert page.tableau.isColumnHidden(COLONNE_DOSSIERS)  # un seul dossier


def test_paire_suivante_et_en_grand(app_configuree, qtbot, services, dossiers, faux_modele):
    page = _page(qtbot, services)
    page.ajouter(list(dossiers))
    _analyser(qtbot, page)
    nombre = len(page.paires())
    assert not page.bouton_precedente.isEnabled() and page.bouton_suivante.isEnabled()
    page.aller(1)
    assert page.rang_choisi() == 1 and page.description.text().startswith(f"Paire 2 sur {nombre}")
    fenetre = page.agrandir()
    assert fenetre is not None and fenetre.titre.text() == f"Paire 2 sur {nombre}"
    fenetre.aller(2)
    assert page.rang_choisi() == 2  # la page suit la paire montrée en grand
    fenetre.basculer()  # côte à côte → l'une puis l'autre
    assert fenetre.pages.currentIndex() == 1 and fenetre.legende_unique.text().startswith("Image 1 sur 2 : ")
    fenetre.basculer()
    assert fenetre.legende_unique.text().startswith("Image 2 sur 2 : ")
    fenetre.close()


def test_plus_de_paires_choisie_apres_un_changement_de_dossier(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    page.ajouter([dossiers[0]])
    page.methode.definir(SANS_IA)
    _analyser(qtbot, page)
    assert page.paires()
    page.ajouter([dossiers[1]])  # la liste change : l'analyse est à refaire
    assert page.resultat is None and page.paires() == [] and page.resume.text() == TEXTE_SANS_ANALYSE
    assert not page.tableau.isVisible() and not page.bouton_agrandir.isEnabled()


def test_reglages_retenus(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    page.case_sous_dossiers.setChecked(True)
    page.methode.definir(SANS_IA)
    page._methode_changee(SANS_IA)
    page.mode.definir(ENTRE_LES_DOSSIERS)
    page._mode_change(ENTRE_LES_DOSSIERS)
    page.definir_le_seuil(72)
    preferences = services.preferences
    assert preferences.lire(PREF_SOUS_DOSSIERS) is True and preferences.lire(PREF_METHODE) == SANS_IA
    assert preferences.lire(PREF_MODE) == ENTRE_LES_DOSSIERS and preferences.lire(PREF_SEUIL) == 72
    autre = _page(qtbot, services)
    assert autre.case_sous_dossiers.isChecked() and autre.methode.valeur() == SANS_IA
    assert autre.mode.valeur() == ENTRE_LES_DOSSIERS and autre.seuil == 72 and autre.champ_seuil.value() == 72


def test_dossiers_deposes(tmp_path):
    dossier = tmp_path / "Photos"
    dossier.mkdir()
    photo = dossier / "x.jpg"
    photo.write_bytes(b"x")
    texte = tmp_path / "notes.txt"
    texte.write_text("x")
    donnees = QMimeData()
    donnees.setUrls([QUrl.fromLocalFile(str(dossier)), QUrl.fromLocalFile(str(photo)), QUrl.fromLocalFile(str(texte))])
    assert dossiers_deposes(donnees) == [dossier]


def test_textes():
    assert duree_lisible(0.4) == "moins d'une seconde"
    assert duree_lisible(12.3) == "12 s"
    assert duree_lisible(65) == "1 min 05 s"
    assert texte_du_type(IDENTIQUES, ("même fichier",)) == "Identiques"
    assert texte_du_type(IDENTIQUES, ("mêmes pixels",)) == "Identiques · mêmes pixels"
    assert texte_du_type(MEME_PHOTO, ("autre taille", "retournée")) == "Même photo · autre taille, retournée"
    assert texte_du_type(RESSEMBLANTES, ()) == "Ressemblantes"
    assert texte_des_illisibles([]) == ""

    class Selection:
        def __init__(self, total, comptes):
            self.total, self._comptes = total, comptes

        def compte(self, genre):
            return self._comptes.get(genre, 0)

    aucune, quelques = Selection(0, {}), Selection(43, {IDENTIQUES: 42, MEME_PHOTO: 1})
    assert texte_du_resume(163, 1, None, aucune, True) == "163 images dans 1 dossier · Aucune copie."
    assert texte_du_resume(163, 1, None, quelques, True) == "163 images dans 1 dossier · 43 paires de copies : 42 identiques, 1 même photo."
    assert texte_du_resume(163, 1, 85, quelques, False) == "163 images dans 1 dossier · 43 paires à 85 % ou plus : 42 identiques, 1 même photo."
    assert texte_du_resume(163, 1, 85, aucune, False) == "163 images dans 1 dossier · Aucune paire à 85 % ou plus : pas de doublon."
    assert texte_du_resume(163, 1, 80, aucune, False) == "163 images dans 1 dossier · Aucune paire à 80 % ou plus."
    assert texte_du_resume(163, 1, 85, aucune, True) == "163 images dans 1 dossier · Aucune copie à 85 % ou plus."


def test_la_comparaison_a_cote_du_tableau_en_grande_fenetre(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    page.ajouter([dossiers[0]])
    page.methode.definir(SANS_IA)
    _analyser(qtbot, page)
    qtbot.waitUntil(lambda: page.resultats.width() > 0, timeout=5_000)
    if page.resultats.width() >= Dimensions.DOUBLONS_COTE_A_COTE_MIN:
        assert page.resultats.cote_a_cote
        assert page.cadre_comparaison.x() > page.cadre_paires.x()
    page.resize(Dimensions.FENETRE_LARGEUR_MIN - Dimensions.LARGEUR_BARRE_LATERALE, Dimensions.FENETRE_HAUTEUR)
    qtbot.waitUntil(lambda: not page.resultats.cote_a_cote, timeout=5_000)
    qtbot.waitUntil(lambda: page.cadre_comparaison.y() > page.cadre_paires.y(), timeout=5_000)
    assert page.cadre_comparaison.x() == page.cadre_paires.x()
    assert page.mode.valeur() == LES_DEUX  # le mode de départ (sans effet avec un seul dossier)
