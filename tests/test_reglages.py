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
    resultat = ResultatTest(True, "Clé valide, 1 modèles accessibles.", [InfoModele("gemini-3.8-flash-tts")])

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


def test_tarifs_google_dans_l_onglet(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    transcription = page.modeles.ligne("gemini-3.5-transcribe")
    assert (transcription.entree.text(), transcription.sortie.text()) == ("2.00", "12.00")
    assert not transcription.zone_minute.isHidden()
    assert transcription.cout_minute.montant == services.prix.cout_reference_eur("gemini-3.5-transcribe")
    assert transcription.hausse.isHidden()  # aucun changement de prix annoncé
    voix = page.modeles.ligne("gemini-3.8-flash-tts")
    assert not voix.hausse.isHidden() and "01/01/2027" in voix.hausse.text() and "18.00 $" in voix.hausse.text()
    assert voix.personnalise.isHidden()


def test_prix_personnalise_signale_puis_retabli(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    voix = page.modeles.ligne("gemini-3.8-flash-tts")
    avant = voix.cout_minute.montant
    voix.sortie.setText("10")
    voix.sortie.editingFinished.emit()
    assert voix.sortie.text() == "10"
    assert not voix.personnalise.isHidden() and "9.00 $" in voix.personnalise.text()
    assert voix.cout_minute.montant > avant  # l'ordre de grandeur suit le prix saisi
    page.modeles._retablir()
    assert voix.sortie.text() == "9.00" and voix.personnalise.isHidden()
    assert voix.cout_minute.montant == avant


def test_seuls_les_modeles_charges_sont_listes(app_configuree, qtbot, services):
    """Au départ : les modèles dont l'app se sert, plus Flash-Lite TTS et 3.1 Pro (à comparer pour les
    scripts, V2). Un ancien modèle accessible avec la clé n'est listé qu'une fois chargé (« Choisir les
    modèles… »)."""
    page = PageReglages(services)
    qtbot.addWidget(page)
    assert list(page.modeles._lignes) == [
        "gemini-3.8-flash-tts",
        "gemini-3.8-flash-lite-tts",
        "gemini-3.5-transcribe",
        "gemini-3.8-flash",
        "gemini-3.1-pro-preview",
    ]
    connexion = services.connexions.ajouter("google", "Perso", CLE)
    services.connexions.enregistrer_test(
        connexion.identifiant, True, "Clé valide", ["gemini-3.8-flash-tts", "gemini-2.5-pro-preview-tts", "gemini-3.5-transcribe-live"]
    )
    assert page.modeles.ligne("gemini-2.5-pro-preview-tts") is None
    services.modeles.definir([*services.modeles.charges(), "gemini-2.5-pro-preview-tts"])
    assert page.modeles.ligne("gemini-2.5-pro-preview-tts") is not None


def test_colonne_utilise_dans(app_configuree, qtbot, services):
    from ugc_studio.modeles_charges import TRANSCRIPTION

    page = PageReglages(services)
    qtbot.addWidget(page)
    assert page.modeles.ligne("gemini-3.8-flash").utilise_dans.text() == "Traductions"
    assert page.modeles.ligne("gemini-3.8-flash-tts").utilise_dans.text() == "Voix"  # styles d'exemple
    assert page.modeles.ligne("gemini-3.8-flash-lite-tts").utilise_dans.text() == "Aucun"
    services.modeles.choisir(TRANSCRIPTION, "gemini-3.5-transcribe")  # mise à jour en direct
    assert page.modeles.ligne("gemini-3.5-transcribe").utilise_dans.text() == "Transcription"


def test_nom_du_modele_sur_une_seule_ligne(app_configuree, qtbot, services):
    from ugc_studio.ui.composants.elements import EtiquetteAbregee

    page = PageReglages(services)
    qtbot.addWidget(page)
    page.resize(960, 600)
    page.show()
    # Onglet « Modèles et prix » affiché : un onglet caché n'est jamais mis en page (ses textes
    # gardent la taille par défaut d'un élément de Qt, 640 × 480 px).
    page.onglets.setCurrentIndex(1)
    qtbot.waitUntil(page.modeles.isVisible, timeout=2000)
    (nom,) = [e for e in page.modeles.findChildren(EtiquetteAbregee) if e.text() == "Gemini 3.8 Flash TTS"]
    assert not nom.wordWrap() and nom.height() < 2 * nom.fontMetrics().lineSpacing()  # une seule ligne
    assert "gemini-3.8-flash-tts" in nom.toolTip()  # identifiant technique au survol


def test_fenetre_choisir_les_modeles(app_configuree, qtbot, services):
    from ugc_studio.modeles_charges import TRANSCRIPTION
    from ugc_studio.ui.dialogues.choix_modeles import DialogueChoixModeles

    connexion = services.connexions.ajouter("google", "Perso", CLE)
    services.connexions.enregistrer_test(
        connexion.identifiant,
        True,
        "Clé valide",
        ["gemini-3.8-flash-tts", "gemini-2.5-pro-preview-tts", "gemini-3.5-transcribe-live", "imagen-5", "gemini-3.5-transcribe"],
    )
    services.modeles.choisir(TRANSCRIPTION, "gemini-3.5-transcribe")
    dialogue = DialogueChoixModeles(services)
    qtbot.addWidget(dialogue)
    lignes = {ligne.identifiant: ligne for ligne in dialogue.lignes()}
    # Seulement ce que l'app sait utiliser : ni modèle « Live », ni modèle d'images.
    assert "gemini-3.5-transcribe-live" not in lignes and "imagen-5" not in lignes
    assert "gemini-2.5-pro-preview-tts" in lignes and not lignes["gemini-2.5-pro-preview-tts"].case.isChecked()
    # Un modèle utilisé reste coché, et ne peut pas être décoché.
    transcription = lignes["gemini-3.5-transcribe"].case
    assert transcription.isChecked() and not transcription.isEnabled()
    assert "Transcription" in transcription.toolTip()
    lignes["gemini-2.5-pro-preview-tts"].case.setChecked(True)
    lignes["gemini-3.8-flash-lite-tts"].case.setChecked(False)  # pas utilisé : on peut le retirer
    services.modeles.definir(dialogue.modeles_coches())
    assert services.modeles.est_charge("gemini-2.5-pro-preview-tts")
    assert not services.modeles.est_charge("gemini-3.8-flash-lite-tts")


def test_sans_cle_la_fenetre_renvoie_vers_connexions(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    page.onglets.setCurrentIndex(1)
    from ugc_studio.ui.composants.bouton import Bouton
    from ugc_studio.ui.dialogues.choix_modeles import DialogueChoixModeles

    dialogue = DialogueChoixModeles(services, None, page.modeles.connexions_demandees.emit)
    qtbot.addWidget(dialogue)
    (aller,) = [b for b in dialogue.findChildren(Bouton) if b.text() == "Connexions API"]
    aller.click()
    assert page.onglets.currentIndex() == 0


def test_le_cout_d_une_minute_suit_le_taux(app_configuree, qtbot, services):
    page = PageReglages(services)
    qtbot.addWidget(page)
    voix = page.modeles.ligne("gemini-3.8-flash-tts")
    services.prix.definir_taux(Decimal("1"))
    assert voix.cout_minute.montant == Decimal("0.013625")  # 250 × 0,50 $ + 1 500 × 9 $, par million


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
    services.couts.enregistrer("google", "modele-sans-prix", "transcription", 500, 50)
    assert page.couts.tableau.rowCount() == 2
    attendu = services.prix.cout_eur("gemini-3.8-flash-tts", 1_000, 20_000)
    assert page.couts.total.montant == attendu
    assert page.couts.avertissement.isVisibleTo(page.couts)  # un appel sans prix
    # Filtre par projet
    page.couts.projet.setCurrentIndex(page.couts.projet.findData("Sérum"))
    assert page.couts.tableau.rowCount() == 1
