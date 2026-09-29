"""Module Voix : éditeur à badges, projets, génération d'une prise (avec un faux fournisseur)."""

from decimal import Decimal

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QTextCursor

from ugc_studio.audio import duree_wav, wav_depuis_pcm
from ugc_studio.fournisseurs.base import Adaptateur, ErreurFournisseur
from ugc_studio.fournisseurs.voix import ResultatVoix
from ugc_studio.script import normaliser
from ugc_studio.ui.composants.editeur_script import EditeurScript
from ugc_studio.ui.pages.voix import PageVoix

SCRIPT = [
    {"texte": "Franchement, "},
    {"balise": "short pause"},
    {"texte": " ce sérum est "},
    {"texte": "top", "accentue": True},
    {"texte": " ! "},
    {"balise": "laugh"},
]


class FauxTTS(Adaptateur):
    identifiant = "google"
    nom = "Faux"
    echec: str | None = None

    def lister_modeles(self):
        return []

    def generer_voix(self, requete):
        if FauxTTS.echec:
            raise ErreurFournisseur(FauxTTS.echec, "requete")
        wav = wav_depuis_pcm(b"\x00\x00" * 24_000)
        return ResultatVoix(wav, duree_wav(wav), tokens_entree=20, tokens_sortie=30)


@pytest.fixture
def editeur(app_configuree, qtbot):
    widget = EditeurScript()
    qtbot.addWidget(widget)
    return widget


def test_editeur_aller_retour(editeur):
    editeur.definir_segments(SCRIPT)
    assert editeur.segments() == normaliser([dict(s) for s in SCRIPT])
    assert editeur.texte_api() == "Franchement, <short pause> ce sérum est TOP ! <laugh>"


def test_badge_insere_au_curseur(editeur):
    editeur.definir_segments([{"texte": "Salut ça va"}])
    curseur = editeur.textCursor()
    curseur.setPosition(len("Salut"))
    editeur.setTextCursor(curseur)
    editeur.inserer_balise("giggle")
    assert editeur.texte_api() == "Salut<giggle> ça va"
    # Le badge s'efface d'un seul retour arrière, comme un caractère.
    curseur = editeur.textCursor()
    curseur.deletePreviousChar()
    assert editeur.texte_api() == "Salut ça va"


def test_texte_tape_apres_un_badge_reste_du_texte(editeur, qtbot):
    editeur.definir_segments([{"texte": "A "}])
    editeur.moveCursor(QTextCursor.MoveOperation.End)
    editeur.inserer_balise("sigh")
    qtbot.keyClicks(editeur, " ok")
    assert editeur.segments() == [{"texte": "A "}, {"balise": "sigh"}, {"texte": " ok"}]


def test_accentuer_un_mot(editeur):
    editeur.definir_segments([{"texte": "Ce sérum est incroyable"}])
    curseur = editeur.textCursor()
    curseur.setPosition(len("Ce sérum est "))
    curseur.setPosition(len("Ce sérum est incroyable"), QTextCursor.MoveMode.KeepAnchor)
    editeur.setTextCursor(curseur)
    editeur.basculer_accent()
    assert editeur.texte_api() == "Ce sérum est INCROYABLE"
    assert editeur.segments()[-1] == {"texte": "incroyable", "accentue": True}
    editeur.basculer_accent()  # deuxième clic : l'accent est retiré
    assert editeur.texte_api() == "Ce sérum est incroyable"


def test_coller_du_texte_avec_balises(editeur):
    donnees = QMimeData()
    donnees.setText("Wow <gasp> génial")
    editeur.insertFromMimeData(donnees)
    assert editeur.segments() == [{"texte": "Wow "}, {"balise": "gasp"}, {"texte": " génial"}]


def test_copier_coller_garde_les_accents(editeur):
    editeur.definir_segments(SCRIPT)
    editeur.selectAll()
    donnees = editeur.createMimeDataFromSelection()
    assert "<laugh>" in donnees.text()
    autre = EditeurScript()
    autre.insertFromMimeData(donnees)
    assert autre.segments() == editeur.segments()


def test_page_voix_sans_puis_avec_projet(app_configuree, qtbot, services, tmp_path):
    page = PageVoix(services)
    qtbot.addWidget(page)
    assert page.currentWidget() is page.sans_projet
    services.projets.creer("Sérum Glowzy", tmp_path)
    assert page.currentWidget() is page.atelier
    assert page.atelier.titre.text() == "Voix — Sérum Glowzy"


def _atelier_pret(services, qtbot, tmp_path, monkeypatch):
    from ugc_studio.ui.pages.voix import atelier as module_atelier

    monkeypatch.setattr(module_atelier, "creer_adaptateur", lambda _f, _cle: FauxTTS("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.8-flash-tts"])
    services.projets.creer("Sérum", tmp_path)
    page = PageVoix(services)
    qtbot.addWidget(page)
    return page.atelier


def test_generer_une_prise(app_configuree, qtbot, services, tmp_path, monkeypatch):
    FauxTTS.echec = None
    atelier = _atelier_pret(services, qtbot, tmp_path, monkeypatch)
    atelier.editeur.definir_segments(SCRIPT)
    atelier.generer()
    qtbot.waitUntil(lambda: len(services.projets.projet.prises) == 1, timeout=5000)
    (prise,) = services.projets.projet.prises
    assert prise.texte_api == "Franchement, <short pause> ce sérum est TOP ! <laugh>"
    assert services.projets.projet.chemin(prise.fichier).exists()
    (appel,) = services.couts.lire()
    assert appel.projet == "Sérum" and Decimal(prise.cout_eur) == appel.cout_eur
    assert atelier.statut.property("role") == "succes"
    assert len(atelier.prises.lignes()) == 1
    # Le script a été enregistré dans le projet.
    assert services.projets.projet.script == atelier.editeur.segments()


def test_erreur_de_generation_affichee(app_configuree, qtbot, services, tmp_path, monkeypatch):
    FauxTTS.echec = "Google refuse cette voix."
    atelier = _atelier_pret(services, qtbot, tmp_path, monkeypatch)
    atelier.editeur.definir_segments([{"texte": "Bonjour"}])
    atelier.generer()
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "erreur", timeout=5000)
    assert "refuse cette voix" in atelier.statut.text()
    assert services.projets.projet.prises == []
    FauxTTS.echec = None


def test_script_vide_refuse(app_configuree, qtbot, services, tmp_path, monkeypatch):
    atelier = _atelier_pret(services, qtbot, tmp_path, monkeypatch)
    atelier.generer()
    assert "vide" in atelier.statut.text()


def test_noter_une_prise(app_configuree, qtbot, services, tmp_path, monkeypatch):
    atelier = _atelier_pret(services, qtbot, tmp_path, monkeypatch)
    prise = services.projets.ajouter_prise(
        wav_depuis_pcm(b"\x00\x00" * 2400), modele="gemini-3.8-flash-tts", voix="Kore", style="",
        texte_api="a", script=[{"texte": "a"}], duree_s=0.1,
    )
    atelier.prises.rafraichir()
    (ligne,) = atelier.prises.lignes()
    ligne.etoiles[3].click()
    assert services.projets.prise(prise.identifiant).note == 4


def test_estimation_mise_a_jour(app_configuree, qtbot, services, tmp_path, monkeypatch):
    atelier = _atelier_pret(services, qtbot, tmp_path, monkeypatch)
    atelier.editeur.definir_segments([{"texte": "Bonjour à toutes et à tous"}])
    atelier._mettre_a_jour_estimation()
    assert atelier.estimation.text().startswith("26 caractères")


def test_menu_projet(app_configuree, qtbot, services, tmp_path):
    from PySide6.QtWidgets import QMenu, QWidget

    from ugc_studio.ui.actions_projet import remplir_menu_projet

    services.projets.creer("A", tmp_path)
    services.projets.creer("B", tmp_path)
    parent = QWidget()
    qtbot.addWidget(parent)
    menu = QMenu(parent)
    remplir_menu_projet(menu, parent, services)
    textes = [a.text() for a in menu.actions() if a.text()]
    assert textes[:2] == ["Nouveau projet…", "Ouvrir un projet…"]
    assert "A" in textes and "B" not in textes  # B est le projet ouvert
    assert "Ouvrir le dossier du projet" in textes
