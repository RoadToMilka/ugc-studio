"""Page Réglages : ajout de clé, liste des connexions, prix, taux et suivi des coûts."""

from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog

from ugc_studio.fournisseurs.base import Adaptateur, InfoModele, ResultatTest
from ugc_studio.ui.dialogues.cle_api import DialogueCle
from ugc_studio.ui.pages.reglages import PageReglages

CLE = "AIza" + "T" * 31 + "4f2c"


class FauxAdaptateur(Adaptateur):
    identifiant = "google"
    nom = "Google (Gemini)"
    resultat = ResultatTest(True, "Clé valide — 1 modèles accessibles.", [InfoModele("gemini-3.8-flash-tts")])

    def lister_modeles(self):
        return self.resultat.modeles

    def tester_cle(self):
        return FauxAdaptateur.resultat


@pytest.fixture
def dialogue(app_configuree, qtbot, services):
    d = DialogueCle(services.connexions, fabrique=lambda _f, cle: FauxAdaptateur(cle))
    qtbot.addWidget(d)
    return d


def test_quatre_onglets(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    titres = [page.onglets.tabText(i) for i in range(page.onglets.count())]
    assert titres == ["Connexions API", "Modèles et prix", "Suivi des coûts", "Journal et données"]


def test_ajout_de_cle_testee_puis_enregistree(dialogue, qtbot, services):
    FauxAdaptateur.resultat = ResultatTest(True, "Clé valide", [InfoModele("gemini-3.8-flash-tts")])
    dialogue.nom.setText("Google perso")
    dialogue.cle.setText(f" {CLE} ")
    dialogue.valider()
    qtbot.waitUntil(lambda: dialogue.result() == QDialog.DialogCode.Accepted, timeout=5000)
    (connexion,) = services.connexions.lister()
    assert connexion.nom == "Google perso" and connexion.apercu == "AIza…4f2c"
    assert connexion.dernier_test.ok
    assert services.connexions.modeles_disponibles() == {"gemini-3.8-flash-tts"}
    assert services.connexions.lire_cle(connexion.identifiant) == CLE
    assert dialogue.cle.text() == ""  # la clé ne reste pas affichée


def test_cle_refusee_non_enregistree(dialogue, qtbot, services):
    FauxAdaptateur.resultat = ResultatTest(False, "Google refuse cette clé : elle n'est pas valide.", code="cle_invalide")
    dialogue.cle.setText(CLE)
    dialogue.valider()
    qtbot.waitUntil(lambda: "refuse" in dialogue.statut.text(), timeout=5000)
    assert services.connexions.lister() == []
    assert dialogue.bouton_sans_test.isHidden()


def test_hors_ligne_enregistrer_sans_tester(dialogue, qtbot, services):
    FauxAdaptateur.resultat = ResultatTest(False, "Impossible de joindre le serveur.", code="reseau")
    dialogue.cle.setText(CLE)
    dialogue.valider()
    qtbot.waitUntil(lambda: not dialogue.bouton_sans_test.isHidden(), timeout=5000)
    dialogue.bouton_sans_test.click()
    (connexion,) = services.connexions.lister()
    assert connexion.dernier_test is None


def test_cle_vide(dialogue, services):
    dialogue.valider()
    assert "Colle ta clé" in dialogue.statut.text()
    assert services.connexions.lister() == []


def test_liste_des_connexions(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    assert page.connexions.lignes() == []
    a = services.connexions.ajouter("google", "Perso", CLE)
    services.connexions.ajouter("google", "Pro", CLE[:-1] + "0")
    services.connexions.enregistrer_test(a.identifiant, True, "Clé valide", ["gemini-3.8-flash-tts"])
    lignes = page.connexions.lignes()
    assert [ligne.connexion.nom for ligne in lignes] == ["Perso", "Pro"]
    assert lignes[0].voyant.property("role") == "succes"
    assert lignes[1].voyant.property("role") == "discret"


def test_prix_modifie_depuis_l_onglet(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    entree, sortie = page.modeles._champs_prix["gemini-3.8-flash-tts"]
    sortie.setText("18,00")
    sortie.editingFinished.emit()
    assert services.prix.prix("gemini-3.8-flash-tts").sortie == Decimal("18.00")
    entree.setText("abc")
    entree.editingFinished.emit()
    assert entree.property("invalide") is True
    assert services.prix.prix("gemini-3.8-flash-tts").entree == Decimal("0.50")


def test_taux_saisi(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    page.modeles.champ_taux.setText("0,9")
    page.modeles.champ_taux.editingFinished.emit()
    assert services.prix.taux_usd_eur == Decimal("0.9")
    assert services.prix.taux_source == "manuel"
    assert "à la main" in page.modeles.info_taux.text()


def test_suivi_des_couts(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    assert page.couts.tableau.rowCount() == 0
    services.couts.enregistrer("google", "gemini-3.8-flash-tts", "voix", 1_000, 20_000, projet="Sérum")
    services.couts.enregistrer("google", "gemini-3.5-transcribe", "transcription", 500, 50)
    assert page.couts.tableau.rowCount() == 2
    attendu = services.prix.cout_eur("gemini-3.8-flash-tts", 1_000, 20_000)
    assert page.couts.total.montant == attendu
    assert page.couts.avertissement.isVisibleTo(page.couts)  # un appel sans prix
    # Filtre par projet
    page.couts.projet.setCurrentIndex(page.couts.projet.findData("Sérum"))
    assert page.couts.tableau.rowCount() == 1
