"""Fenêtre principale : barre latérale, bandeau, navigation entre les modules."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMenu, QWidget

from ugc_studio.connexions import CoffreMemoire
from ugc_studio.services import creer_services
from ugc_studio.ui.composants.montant_label import MontantLabel
from ugc_studio.ui.fenetre_principale import FenetrePrincipale


def _fenetre(qtbot, _chemin=None):
    # Les préférences sont rangées dans le dossier de données temporaire des tests.
    fenetre = FenetrePrincipale(creer_services(CoffreMemoire()))
    qtbot.addWidget(fenetre)
    return fenetre


def test_modules_de_la_barre_laterale(app_configuree, qtbot, tmp_path):
    fenetre = _fenetre(qtbot, tmp_path / "preferences.json")
    libelles = [b.text() for b in fenetre.barre_laterale.boutons()]
    # V2 : le module Script en tête, c'est la première étape d'une pub.
    assert libelles == ["Script", "Voix", "Transcription", "Sous-titres", "Réglages"]
    assert all(not b.icon().isNull() for b in fenetre.barre_laterale.boutons())
    assert fenetre.module_actuel() == "script"


def test_clic_sur_un_module(app_configuree, qtbot, tmp_path):
    fenetre = _fenetre(qtbot, tmp_path / "preferences.json")
    fenetre.show()
    bouton_reglages = fenetre.barre_laterale.boutons()[-1]
    qtbot.mouseClick(bouton_reglages, Qt.MouseButton.LeftButton)
    assert fenetre.module_actuel() == "reglages"
    assert bouton_reglages.isChecked()


def test_cout_de_session_affiche_au_format(app_configuree, qtbot, tmp_path):
    fenetre = _fenetre(qtbot, tmp_path / "preferences.json")
    assert ">0.00<" in fenetre.entete.cout_session.text()
    fenetre.entete.definir_cout_session(0.0071)
    texte = fenetre.entete.cout_session.text()
    assert ">0.00<" in texte and ">71<" in texte and "€" in texte


def test_cout_de_session_suit_les_appels(app_configuree, qtbot):
    fenetre = _fenetre(qtbot)
    fenetre.services.couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 1_000, 20_000)
    assert fenetre.entete.cout_session.montant == fenetre.services.couts.cout_session > 0


def test_montant_label_petites_decimales(app_configuree, qtbot):
    from ugc_studio.ui.theme import COULEUR_PETITES_DECIMALES, Couleurs

    etiquette = MontantLabel(0.0071, 20)
    qtbot.addWidget(etiquette)
    texte = etiquette.text()
    assert '<span style="font-size:20px">0.00</span>' in texte  # 1re et 2e décimales : normales
    # 3e et 4e décimales : 70 % de 20 px et plus sombres
    assert f'<span style="font-size:14px; color:{COULEUR_PETITES_DECIMALES}">71</span>' in texte
    assert COULEUR_PETITES_DECIMALES == Couleurs.TEXTE_SECONDAIRE
    assert etiquette.accessibleName() == "0.0071\u00a0€"


def test_la_fenetre_se_souvient_du_module(app_configuree, qtbot, tmp_path):
    chemin = tmp_path / "preferences.json"
    fenetre = _fenetre(qtbot, chemin)
    fenetre.afficher_module("sous-titres")
    fenetre.close()
    fenetre2 = _fenetre(qtbot, chemin)
    assert fenetre2.module_actuel() == "sous-titres"
    assert fenetre2.barre_laterale.boutons()[3].isChecked()


def test_balises_affichees_telles_quelles(app_configuree, qtbot):
    from ugc_studio.ui.composants.elements import libelle

    etiquette = libelle("Rire : <laugh>")
    qtbot.addWidget(etiquette)
    assert etiquette.textFormat() == Qt.TextFormat.PlainText


def test_police_inter_chargee(app_configuree):
    from PySide6.QtGui import QFontDatabase

    assert "Inter" in QFontDatabase.families()


def test_creer_les_sous_titres_depuis_une_prise(app_configuree, qtbot, tmp_path, monkeypatch):
    """Menu ⋯ d'une prise → « Créer les sous-titres de cette prise » : le module Sous-titres s'en charge."""
    from ugc_studio.audio import wav_depuis_pcm

    fenetre = _fenetre(qtbot)
    services = fenetre.services
    services.projets.creer("Sérum", tmp_path)
    assert fenetre.windowTitle() == "UGC Studio / Sérum"  # barre de titre : l'app, puis le projet
    prise = services.projets.ajouter_prise(
        wav_depuis_pcm(b"\x00\x00" * 24_000), modele="m", voix="Kore", style="", texte_api="Bonjour",
        script=[{"texte": "Bonjour"}], duree_s=1.0,
    )
    fenetre.show()
    fenetre.afficher_module("voix")
    liste = fenetre.page("voix").atelier.prises
    liste.rafraichir()
    (ligne,) = liste.lignes()
    actions = [a.text() for a in ligne.findChild(QMenu).actions()]
    assert actions[0] == "Créer les sous-titres de cette prise"
    demandes = []
    monkeypatch.setattr(fenetre.page("sous-titres").atelier, "creer_depuis_prise", demandes.append)
    ligne.findChild(QMenu).actions()[0].trigger()
    assert fenetre.module_actuel() == "sous-titres" and demandes == [prise.identifiant]
    # « Corriger les mots » : dans le module Transcription.
    fenetre.page("sous-titres").atelier.corriger_demande.emit(-1.0)
    assert fenetre.module_actuel() == "transcription"


# --- V3.1, lot 1 : barre latérale, bandeau, espaces ------------------------------------------------


def test_barre_laterale_plus_fine_avec_le_projet_en_haut(app_configuree, qtbot, tmp_path):
    from ugc_studio import NOM_APP, __version__
    from ugc_studio.ui.theme import Dimensions, Hauteurs

    fenetre = _fenetre(qtbot)
    fenetre.show()
    barre = fenetre.barre_laterale
    assert barre.width() == Dimensions.LARGEUR_BARRE_LATERALE == 200
    projet = barre.bouton_projet
    # Le bouton du projet est centré dans une bande de la hauteur du bandeau (16 px au-dessus et dessous).
    assert projet.mapTo(barre, QPoint(0, 0)).y() == (Hauteurs.BANDEAU - projet.height()) // 2 == 16
    assert fenetre.entete.height() == Hauteurs.BANDEAU
    # Le premier module est à 16 px sous cette bande, comme le premier bloc de la page.
    premier = barre.boutons()[0]
    assert premier.mapTo(barre, QPoint(0, 0)).y() == Hauteurs.BANDEAU + Dimensions.ESPACE_BLOCS
    assert barre.version.text() == f"{NOM_APP} {__version__}"  # le logo n'y est plus : le nom de l'app, ici
    fenetre.services.projets.creer("Sérum", tmp_path)
    assert projet.text() == "Sérum" and not projet.est_attenue()


def test_le_bandeau_montre_le_titre_du_module(app_configuree, qtbot, tmp_path):
    fenetre = _fenetre(qtbot)
    fenetre.show()
    fenetre.afficher_module("voix")
    entete = fenetre.entete.entete_affichee()
    assert entete is fenetre.page("voix").sans_projet.entete
    assert (entete.titre.text(), entete.sous_titre.text()) == ("Voix", "Voix off générée par IA (TTS).")
    fenetre.services.projets.creer("Sérum", tmp_path)
    entete = fenetre.entete.entete_affichee()
    assert entete is fenetre.page("voix").atelier.entete and entete.titre.text() == "Voix / Sérum"
    fenetre.afficher_module("reglages")
    assert fenetre.entete.entete_affichee().titre.text() == "Réglages"
    # Le titre ne prend plus de place en haut des pages : il est dans le bandeau.
    for identifiant in fenetre.identifiants_modules():
        page = fenetre.page(identifiant)
        assert not any(page.isAncestorOf(e) for e in fenetre.entete.findChildren(QWidget))


def test_les_memes_espaces_partout(app_configuree, qtbot):
    """16 px entre la barre latérale et les blocs, sous le bandeau et jusqu'au bord droit, avec ou
    sans barre de défilement (elle prend place dans cet espace, au bord de la fenêtre)."""
    from ugc_studio.ui.theme import Dimensions, Hauteurs

    fenetre = _fenetre(qtbot)
    fenetre.resize(Dimensions.FENETRE_LARGEUR_MIN, Dimensions.FENETRE_HAUTEUR_MIN)
    fenetre.show()
    espace = Dimensions.ESPACE_BLOCS
    barres_vues = set()
    for identifiant, onglet in (("voix", None), ("reglages", 0), ("reglages", 1)):
        fenetre.afficher_module(identifiant)
        page = fenetre.page_affichee()
        if onglet is not None:
            page.onglets.setCurrentIndex(onglet)
        qtbot.wait(20)
        premier = page.contenu.itemAt(0).geometry()
        colonne = page.contenu.parentWidget()
        haut_gauche = colonne.mapTo(fenetre, premier.topLeft())
        droite = colonne.mapTo(fenetre, QPoint(premier.x() + premier.width(), 0)).x()
        barre = page.defilement.verticalScrollBar()
        barres_vues.add(barre.isVisible())
        assert (haut_gauche.x(), haut_gauche.y()) == (Dimensions.LARGEUR_BARRE_LATERALE + espace, Hauteurs.BANDEAU + espace)
        assert fenetre.width() - droite == espace, (identifiant, onglet, barre.isVisible())
        if barre.isVisible():
            assert barre.mapTo(fenetre, QPoint(barre.width(), 0)).x() == fenetre.width()  # au bord de la fenêtre
    assert barres_vues == {True, False}  # les deux cas ont été vérifiés


def test_reglages_defile_comme_les_autres_pages(app_configuree, qtbot):
    """Une seule zone qui défile pour toute la page (V3.1) : sa barre est au bord de la fenêtre."""
    from PySide6.QtWidgets import QScrollArea

    from ugc_studio.ui.theme import Dimensions

    fenetre = _fenetre(qtbot)
    fenetre.resize(Dimensions.FENETRE_LARGEUR_MIN, Dimensions.FENETRE_HAUTEUR_MIN)
    fenetre.show()
    fenetre.afficher_module("reglages")
    reglages = fenetre.page("reglages")
    assert reglages.findChildren(QScrollArea) == [reglages.defilement]
    reglages.onglets.setCurrentIndex(1)  # Modèles et prix : plus haut que la fenêtre
    qtbot.wait(20)
    barre = reglages.defilement.verticalScrollBar()
    assert barre.maximum() > 0
    barre.setValue(barre.maximum())
    reglages.onglets.setCurrentIndex(2)
    assert barre.value() == 0  # un autre onglet s'ouvre en haut
