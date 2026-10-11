"""Module Doublons (V4.3, lot 1) : la page, avec un faux modèle d'IA dont les empreintes sont connues."""

import os
import shutil

import numpy as np
import pytest
from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtWidgets import QLabel

from photos_factices import miroir, photo_factice, plus_petite
from ugc_studio.doublons import vision
from ugc_studio.doublons.choix import AVEC_IA, COPIES_IA, DANS_CHAQUE_DOSSIER, ENTRE_LES_DOSSIERS, IDENTIQUES, LES_DEUX, MEME_PHOTO, RESSEMBLANTES, SANS_IA
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
from ugc_studio.doublons.paires import Paire
from ugc_studio.doublons.recadrages import PreuveRecadrage
from ugc_studio.ui.pages.doublons.tableau import COLONNE_DOSSIERS, COLONNE_IMAGE_1, COLONNE_IMAGE_2, COLONNE_PROXIMITE, COLONNE_TYPE, texte_de_l_origine, texte_du_type
from ugc_studio.ui.theme import Dimensions, Espacements


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
    # V4.4 : « Toutes les copies (avec IA) » au départ ; seules des copies prouvées : pas de seuil.
    assert page.methode.valeur() == COPIES_IA and page.seuil == 85
    assert [page.methode.itemText(k) for k in range(page.methode.count())] == [
        "Toutes les copies (avec IA)",
        "Copies et photos proches (avec IA)",
        "Copies entières (sans IA)",
    ]
    assert not page.zone_seuil.isVisible()
    page.methode.definir(AVEC_IA)
    page._methode_changee(AVEC_IA)
    assert page.zone_seuil.isVisible()  # avec les photos proches, le seuil choisit les paires montrées
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
    assert page.description.text().endswith("98 % · Même photo")
    assert page.origine.text() == "Prouvé sans IA : la même photo (autre format, retournée)."
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
    page.methode.definir(AVEC_IA)
    page._methode_changee(AVEC_IA)
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
    page.methode.definir(COPIES_IA)  # toutes les copies : les mêmes ici (le faux modèle ne donne pas de carreaux)
    page._methode_changee(COPIES_IA)
    assert RESSEMBLANTES not in [paire.genre for paire in page.paires()] and not page.zone_seuil.isVisible()
    assert page.resultat is resultat
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
    # D'où vient la note (V4.4)
    assert texte_de_l_origine(Paire(0, 1, 100, IDENTIQUES, ("même fichier",))) == "Prouvé sans IA : le même fichier, à l'octet près."
    assert texte_de_l_origine(Paire(0, 1, 100, IDENTIQUES, ("mêmes pixels",))) == "Prouvé sans IA : les mêmes pixels, dans deux fichiers différents."
    assert texte_de_l_origine(Paire(0, 1, 98, MEME_PHOTO, ("autre taille", "retournée"))) == "Prouvé sans IA : la même photo (autre taille, retournée)."
    recadrage = PreuveRecadrage(extrait=1, gardee=0.55, angle=-6.2, miroir=True, agrandie=False, contours=0.99, carreaux=1.0, ecart_de_couleurs=30, correspondances=90)
    paire = Paire(0, 1, 95, MEME_PHOTO, (*recadrage.details(), "autre format"), 0.9, recadrage)
    assert texte_de_l_origine(paire) == (
        "Prouvé sans IA : la même photo ; celle de droite est recadrée (55 % de la photo gardée), tournée de 6° "
        "et retournée (autres couleurs, autre format)."
    )
    assert texte_de_l_origine(Paire(0, 1, 88, RESSEMBLANTES)).startswith("Estimé par l'IA :")

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
    if page.resultats.width() >= page.resultats.largeur_cote_a_cote() + Dimensions.BARRE_DEFILEMENT + Espacements.S:
        assert page.resultats.cote_a_cote
        assert page.cadre_comparaison.x() > page.cadre_paires.x()
    # Côte à côte, la disposition annonce la largeur minimale des blocs l'un sous l'autre : elle peut
    # donc rétrécir et repasser l'un sous l'autre (à 125 et 150 %, elle restait côte à côte, coupée).
    assert page.resultats.minimumSizeHint().width() < page.resultats.largeur_cote_a_cote()
    page.resize(Dimensions.FENETRE_LARGEUR_MIN - Dimensions.LARGEUR_BARRE_LATERALE, Dimensions.FENETRE_HAUTEUR)
    qtbot.waitUntil(lambda: not page.resultats.cote_a_cote, timeout=5_000)
    qtbot.waitUntil(lambda: page.cadre_comparaison.y() > page.cadre_paires.y(), timeout=5_000)
    assert page.cadre_comparaison.x() == page.cadre_paires.x()
    assert page.resultats.width() <= page.defilement.viewport().width()  # rien ne dépasse à droite
    assert page.mode.valeur() == LES_DEUX  # le mode de départ (sans effet avec un seul dossier)


# --- V4.5 : décider (Supprimer, Ignorer, Annuler, suggestion) -----------------------------------------


def _analyser_le_premier_lot(qtbot, page, dossiers):
    page.ajouter([dossiers[0]])
    page.methode.definir(SANS_IA)
    page._methode_changee(SANS_IA)
    _analyser(qtbot, page)


def test_supprimer_puis_annuler(app_configuree, qtbot, services, dossiers, fausse_corbeille):
    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)
    premier = dossiers[0]
    assert [(a, b) for a, b, *_ in _lignes(page)] == [("a copie.jpg", "a.jpg"), ("a copie.jpg", "a petite.jpg")]
    # La suggestion : deux copies identiques, dont l'une porte un nom de copie.
    assert page.suggestion.isVisible() and page.suggestion.text() == "Suggestion : garder celle de droite (l'autre a un nom de copie)."
    assert not page.zone_decision.isVisible()
    assert all(b.isEnabled() for b in page.deux_photos.boutons_supprimer) and page.bouton_ignorer.isEnabled()
    page.deux_photos.boutons_supprimer[0].click()  # « Supprimer » sous a copie.jpg
    qtbot.waitUntil(lambda: not page.decision_en_cours, timeout=10_000)
    assert not (premier / "a copie.jpg").exists()
    assert sorted(chemin.name[:2] for chemin in fausse_corbeille.iterdir()) == ["$I", "$R"]
    assert page.texte_decision.text() == "« a copie.jpg » mise à la corbeille."
    assert page.zone_decision.isVisible() and page.bouton_annuler.isVisible() and page.bouton_annuler.isEnabled()
    # Ses paires disparaissent ; a.jpg, sa copie identique, prend sa place face à a petite.jpg.
    assert [(a, b) for a, b, *_ in _lignes(page)] == [("a petite.jpg", "a.jpg")]
    assert page.rang_choisi() == 0 and page.deux_photos.premiere.nom.text() == "a petite.jpg"
    assert page.resume.text() == "4 images dans 1 dossier · 1 paire de copies : 1 même photo."
    assert any(e.text().startswith("4 images · ") for e in page.liste_dossiers.findChildren(QLabel))
    assert page.tableau.hasFocus()  # ↑, ↓ et I continuent de marcher
    assert page.suggestion.text() == "Suggestion : garder celle de droite (plus grande)."
    page.bouton_annuler.click()
    qtbot.waitUntil(lambda: not page.decision_en_cours, timeout=10_000)
    assert (premier / "a copie.jpg").exists() and list(fausse_corbeille.iterdir()) == []
    assert page.texte_decision.text() == "« a copie.jpg » est revenue à sa place."
    assert not page.bouton_annuler.isVisible() and page.derniere_decision is None
    assert [(a, b) for a, b, *_ in _lignes(page)] == [("a copie.jpg", "a.jpg"), ("a copie.jpg", "a petite.jpg")]
    assert page.rang_choisi() == 0  # la paire d'où la photo était partie


def test_ignorer_avec_la_touche_i_puis_annuler(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)
    page.choisir(1)
    page.tableau.setFocus()
    qtbot.keyClick(page.tableau, Qt.Key.Key_I)
    assert [(a, b) for a, b, *_ in _lignes(page)] == [("a copie.jpg", "a.jpg")]
    assert page.rang_choisi() == 0  # la dernière paire est partie : la précédente
    assert page.texte_decision.text() == "Paire ignorée : « a copie.jpg » et « a petite.jpg »."
    assert page.resume.text().endswith("1 paire de copies : 1 identique.")
    # Ctrl+I n'ignore rien.
    qtbot.keyClick(page.tableau, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert len(page.paires()) == 1
    page.annuler()
    assert [(a, b) for a, b, *_ in _lignes(page)] == [("a copie.jpg", "a.jpg"), ("a copie.jpg", "a petite.jpg")]
    assert page.rang_choisi() == 1 and page.texte_decision.text() == "La paire est revenue dans le tableau."
    assert not page.annuler()  # plus rien à annuler
    # Une nouvelle analyse oublie les paires ignorées (rien n'est retenu) et la dernière décision.
    page.ignorer()
    _analyser(qtbot, page)
    assert len(page.paires()) == 2 and page.derniere_decision is None and not page.zone_decision.isVisible()


def test_une_photo_changee_depuis_l_analyse_n_est_pas_touchee(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)
    photo = dossiers[0] / "a.jpg"
    os.utime(photo, (photo.stat().st_mtime + 120, photo.stat().st_mtime + 120))
    assert not page.supprimer(1)
    assert photo.exists()
    assert page.texte_decision.text().startswith("« a.jpg » a changé depuis l'analyse")
    assert not page.bouton_annuler.isVisible()


def test_un_disque_sans_corbeille_la_question_d_abord(app_configuree, qtbot, services, dossiers, monkeypatch):
    from ugc_studio.doublons import corbeille
    from ugc_studio.ui.dialogues import messages

    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)

    def sans_corbeille(_chemin, _fenetre=None):
        raise corbeille.PasDeCorbeille()

    monkeypatch.setattr(corbeille, "mettre_a_la_corbeille", sans_corbeille)
    questions = []
    reponse = {"oui": False}

    def confirmer(_parent, titre, question, precision="", action="OK", icone_action=None, annuler="Annuler"):
        questions.append((titre, question, action, annuler))
        return reponse["oui"]

    monkeypatch.setattr(messages, "confirmer", confirmer)
    photo = dossiers[0] / "a copie.jpg"
    assert page.supprimer(0)
    qtbot.waitUntil(lambda: not page.decision_en_cours and bool(questions), timeout=10_000)
    assert questions[0][0] == "Supprimer définitivement ?" and "ne peut pas mettre « a copie.jpg » dans la corbeille" in questions[0][1]
    assert questions[0][2:] == ("Supprimer définitivement", "Garder la photo")
    assert photo.exists() and page.texte_decision.text() == "« a copie.jpg » est gardée."
    reponse["oui"] = True
    assert page.supprimer(0)
    qtbot.waitUntil(lambda: not page.decision_en_cours and not photo.exists(), timeout=10_000)
    qtbot.waitUntil(lambda: page.texte_decision.text() == "« a copie.jpg » supprimée définitivement.", timeout=10_000)
    assert not page.bouton_annuler.isVisible() and page.derniere_decision is None


def test_decider_dans_la_fenetre_en_grand(app_configuree, qtbot, services, dossiers):
    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)
    fenetre = page.agrandir(0)
    assert fenetre is not None and fenetre.titre.text() == "Paire 1 sur 2"
    assert all(b.isEnabled() for b in fenetre.boutons_supprimer) and not fenetre.zone_decision.isVisible()
    qtbot.keyClick(fenetre, Qt.Key.Key_I)  # « Ignorer » : la fenêtre reste ouverte, sur la paire suivante
    assert page._fenetre_en_grand is fenetre and fenetre.isVisible()
    assert fenetre.titre.text() == "Paire 1 sur 1" and fenetre.description.text().startswith("99 % · Même photo")
    assert fenetre.zone_decision.isVisible() and fenetre.texte_decision.text() == "Paire ignorée : « a copie.jpg » et « a.jpg »."
    fenetre.bouton_annuler.click()
    assert fenetre.titre.text() == "Paire 1 sur 2" and fenetre.description.text().startswith("100 % · Identiques")
    # « Supprimer » sous la photo de droite (a.jpg).
    fenetre.boutons_supprimer[1].click()
    qtbot.waitUntil(lambda: not page.decision_en_cours, timeout=10_000)
    assert not (dossiers[0] / "a.jpg").exists() and fenetre.isVisible()
    assert fenetre.texte_decision.text() == "« a.jpg » mise à la corbeille." and fenetre.bouton_annuler.isVisible()
    assert fenetre.titre.text() == "Paire 1 sur 1"
    fenetre.close()


def test_la_fenetre_en_grand_suit_la_page_et_reste_suivie(app_configuree, qtbot, services, dossiers):
    """Relecture indépendante de la 4.5.0 : la fenêtre « Agrandir » montre toujours la paire choisie dans
    la page (ce qu'on y supprime est ce qu'on y voit), et une fenêtre rouverte reste suivie."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)
    premiere = page.agrandir(0)
    seconde = page.agrandir(1)  # la première se ferme ; elle n'est détruite qu'ensuite
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    assert premiere is not seconde and page._fenetre_en_grand is seconde
    page.choisir(0)  # ↑ dans le tableau, la fenêtre ouverte
    assert seconde.rang == 0 and seconde.description.text().startswith("100 % · Identiques")
    seconde.boutons_supprimer[1].click()  # la photo de droite de la paire montrée : a.jpg
    qtbot.waitUntil(lambda: not page.decision_en_cours, timeout=10_000)
    assert not (dossiers[0] / "a.jpg").exists() and (dossiers[0] / "a petite.jpg").exists()
    assert seconde.texte_decision.text() == "« a.jpg » mise à la corbeille." and seconde.titre.text() == "Paire 1 sur 1"
    seconde.close()


def test_la_touche_i_gardee_enfoncee_n_ignore_qu_une_paire(app_configuree, qtbot, services, dossiers):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)
    page.tableau.setFocus()
    for repetee in (False, True, True, True):
        QApplication.sendEvent(page.tableau, QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_I, Qt.KeyboardModifier.NoModifier, "i", repetee))
    assert len(page.paires()) == 1


def test_rien_ne_change_pendant_qu_une_photo_part(app_configuree, qtbot, services, dossiers, monkeypatch):
    """Relecture indépendante de la 4.5.0 : pendant qu'une photo part dans la corbeille, ni dossier
    ajouté (même glissé sur la page) ni nouvelle analyse : la décision arrive toujours à son résultat."""
    import threading

    from ugc_studio.doublons import corbeille

    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)
    feu = threading.Event()
    vraie = corbeille.mettre_a_la_corbeille

    def lente(chemin, fenetre=None):
        feu.wait(10)
        return vraie(chemin, fenetre)

    monkeypatch.setattr(corbeille, "mettre_a_la_corbeille", lente)
    assert page.supprimer(0) and page.decision_en_cours
    assert page.ajouter([dossiers[1]]) == 0 and not page.analyser()
    assert not page.bouton_analyser.isEnabled() and not page.bouton_ignorer.isEnabled()
    feu.set()
    qtbot.waitUntil(lambda: not page.decision_en_cours, timeout=10_000)
    assert page.texte_decision.text() == "« a copie.jpg » mise à la corbeille." and page.bouton_annuler.isVisible()
    assert page.ajouter([dossiers[1]]) == 1  # ensuite, tout est permis


def test_non_a_la_question_de_windows_garde_la_photo(app_configuree, qtbot, services, dossiers, monkeypatch):
    """Si Windows demande lui-même « supprimer définitivement ? » (une photo plus grande que la corbeille)
    et qu'on répond « Non », la photo est gardée, et la page le dit."""
    from ugc_studio.doublons import corbeille

    page = _page(qtbot, services)
    _analyser_le_premier_lot(qtbot, page, dossiers)

    def non(_chemin, _fenetre=None):
        raise corbeille.Gardee()

    monkeypatch.setattr(corbeille, "mettre_a_la_corbeille", non)
    assert page.supprimer(0)
    qtbot.waitUntil(lambda: not page.decision_en_cours, timeout=10_000)
    assert page.texte_decision.text() == "« a copie.jpg » est gardée." and not page.bouton_annuler.isVisible()
    assert (dossiers[0] / "a copie.jpg").exists() and len(page.paires()) == 2
