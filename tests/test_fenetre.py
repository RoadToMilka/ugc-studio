"""Fenêtre principale : barre latérale, bandeau, navigation entre les modules."""

from PySide6.QtCore import Qt

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
    assert libelles == ["Voix", "Transcription", "Sous-titres", "Réglages"]
    assert all(not b.icon().isNull() for b in fenetre.barre_laterale.boutons())
    assert fenetre.module_actuel() == "voix"


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
    assert fenetre2.barre_laterale.boutons()[2].isChecked()


def test_balises_affichees_telles_quelles(app_configuree, qtbot):
    from ugc_studio.ui.composants.elements import libelle

    etiquette = libelle("Rire : <laugh>")
    qtbot.addWidget(etiquette)
    assert etiquette.textFormat() == Qt.TextFormat.PlainText


def test_police_inter_chargee(app_configuree):
    from PySide6.QtGui import QFontDatabase

    assert "Inter" in QFontDatabase.families()
