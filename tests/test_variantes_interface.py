"""Étape 6 (§5.6) — interface : fenêtre des variantes, génération d'une série, écoute
comparative, écoute pendant la génération (avec un faux Google)."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QLabel

from ugc_studio.audio import duree_wav, wav_depuis_pcm
from ugc_studio.fournisseurs.base import Adaptateur, ErreurFournisseur
from ugc_studio.fournisseurs.voix import ResultatVoix
from ugc_studio.projets import RepliqueProjet
from ugc_studio.ui import taches
from ugc_studio.ui.composants import comparateur as module_comparateur
from ugc_studio.ui.composants.choix_voix import choisir
from ugc_studio.ui.composants.comparateur import ComparateurAudio, position_equivalente
from ugc_studio.ui.composants.lecteur_flux import LecteurFlux
from ugc_studio.ui.dialogues.variantes import ONGLET_MEMES_REGLAGES, ONGLET_PAR_VARIANTE, DialogueVariantes
from ugc_studio.ui.pages.voix import PageVoix
from ugc_studio.ui.pages.voix.atelier import CLE_ECOUTE_DIRECTE
from ugc_studio.variantes import TEXTE, VOIX, champs_differents, differences

SCRIPT_1 = [{"texte": "Franchement, je n'y croyais pas… "}, {"balise": "short pause"}]
SCRIPT_2 = [{"texte": "Le lien est juste en dessous."}]
MORCEAU = b"\x00\x00" * 4800  # 0,2 s de voix (PCM 16 bits, 24 kHz)


class FauxFlux(Adaptateur):
    """Faux Google : envoie sa voix en deux morceaux quand on l'écoute pendant la génération."""

    identifiant = "google"
    nom = "Faux"
    appels: list = []
    echec_au_numero: int | None = None

    def lister_modeles(self):
        return []

    def generer_voix(self, requete, recevoir_audio=None):
        FauxFlux.appels.append((requete, recevoir_audio is not None))
        if FauxFlux.echec_au_numero == len(FauxFlux.appels):
            raise ErreurFournisseur("Limite d'utilisation atteinte chez Google.", "quota")
        if recevoir_audio is not None:
            recevoir_audio(MORCEAU, 24_000)
            recevoir_audio(MORCEAU, 24_000)
        wav = wav_depuis_pcm(MORCEAU * 2)
        return ResultatVoix(wav, duree_wav(wav), tokens_entree=20, tokens_sortie=25)


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path, monkeypatch):
    from ugc_studio.ui import connexion_ia

    FauxFlux.appels, FauxFlux.echec_au_numero = [], None
    monkeypatch.setattr(connexion_ia, "creer_adaptateur", lambda _f, _cle: FauxFlux("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.8-flash-tts"])
    services.projets.creer("Sérum", tmp_path)
    page = PageVoix(services)
    qtbot.addWidget(page)
    page.show()
    page.atelier.repliques.definir([RepliqueProjet(SCRIPT_1, "excited"), RepliqueProjet(SCRIPT_2, "calm")])
    return page.atelier


def test_fenetre_des_variantes(atelier, qtbot, services):
    dialogue = DialogueVariantes(services, atelier.reglages_de_base())
    qtbot.addWidget(dialogue)
    dialogue.onglets.setCurrentIndex(ONGLET_PAR_VARIANTE)
    a, b = dialogue.colonnes()
    assert dialogue.bouton_generer.text() == "Générer les 2 variantes"

    # La variante B change de voix et de style : ces valeurs sont surlignées en mauve.
    choisir(b.voix, "Puck")
    b.styles[0].setText("whispering")
    assert b.voix.property("modifie") and b.styles[0].property("modifie")
    assert not bool(a.voix.property("modifie")) and not bool(b.styles[1].property("modifie"))
    b.textes[1].moveCursor(QTextCursor.MoveOperation.End)
    b.textes[1].insertPlainText(" Vite !")
    assert b.textes[1].property("modifie")
    b.styles[0].setText("excited")  # revenu à la valeur de base : plus surligné
    assert not b.styles[0].property("modifie")

    variante_a, variante_b = dialogue.variantes()
    assert differences(atelier.reglages_de_base(), variante_a) == set()
    assert differences(atelier.reglages_de_base(), variante_b) == {(VOIX, -1), (TEXTE, 1)}

    # « Dupliquer » crée une variante voisine (C = copie de B), qu'on modifie un peu.
    dialogue.dupliquer_variante(1)
    assert [c.voix.currentData() for c in dialogue.colonnes()] == ["Kore", "Puck", "Puck"]
    assert dialogue.colonnes()[2].voix.property("modifie")
    assert dialogue.bouton_generer.text() == "Générer les 3 variantes"
    assert "3 variantes" in dialogue.info_cout.text()
    dialogue.supprimer_variante(0)
    assert [c.voix.currentData() for c in dialogue.colonnes()] == ["Puck", "Puck"]
    dialogue.supprimer_variante(0)  # au moins deux variantes
    assert len(dialogue.colonnes()) == 2

    # Onglet « Mêmes réglages » : N copies identiques des réglages de base.
    dialogue.onglets.setCurrentIndex(ONGLET_MEMES_REGLAGES)
    choisir(dialogue.nombre, 4)
    variantes = dialogue.variantes()
    assert len(variantes) == 4 and all(differences(atelier.reglages_de_base(), v) == set() for v in variantes)
    assert dialogue.bouton_generer.text() == "Générer les 4 variantes"


def test_generer_une_serie_puis_comparer(atelier, qtbot, services):
    base = atelier.reglages_de_base()
    puck = base.copie()
    puck.voix = "Puck"
    atelier.generer_variantes([base, puck])
    assert atelier.bouton_arreter.isVisible() and not atelier.bouton_variantes.isVisible()
    qtbot.waitUntil(lambda: atelier.comparaison is not None, timeout=5000)

    a, b = services.projets.serie(1)
    assert (a.nom, a.voix, b.nom, b.voix) == ("Prise 1 (variante A)", "Kore", "Prise 2 (variante B)", "Puck")
    assert atelier.statut.property("role") == "succes" and "2 variantes prêtes" in atelier.statut.text()
    assert atelier.bouton_variantes.isVisible() and not atelier.bouton_arreter.isVisible()
    assert [ecoute for _requete, ecoute in FauxFlux.appels] == [False, False]

    # Écoute comparative : la fenêtre s'ouvre toute seule à la fin de la série.
    comparaison = atelier.comparaison
    assert [ligne.prise.variante for ligne in comparaison.lignes()] == ["A", "B"]
    assert "voix Puck" in comparaison.description(b, champs_differents([a, b]))
    comparaison.ecouter(1)
    assert comparaison.comparateur.actif == 1 and comparaison.comparateur.en_lecture
    assert comparaison.lignes()[1].lettre.isChecked() and not comparaison.lignes()[0].lettre.isChecked()
    qtbot.keyClick(comparaison, Qt.Key.Key_A)  # touche A : retour à la variante A
    assert comparaison.comparateur.actif == 0
    qtbot.keyClick(comparaison, Qt.Key.Key_Space)  # Espace : pause
    assert not comparaison.comparateur.en_lecture

    comparaison.noter(a.identifiant, 4)
    comparaison.retenir(b.identifiant)
    assert services.projets.prise(a.identifiant).note == 4
    assert services.projets.prise(b.identifiant).retenue
    assert comparaison.lignes()[1].bouton_garder.text() == "Retenue"
    comparaison.accept()
    qtbot.waitUntil(lambda: atelier.comparaison is None, timeout=2000)

    # La liste des prises montre la série et la variante retenue.
    ligne_b = next(l for l in atelier.prises.lignes() if l.prise.identifiant == b.identifiant)
    assert any(e.text() == "Retenue" for e in ligne_b.findChildren(QLabel))
    assert any("série 1" in e.text() for e in ligne_b.findChildren(QLabel))


def test_serie_interrompue_par_une_erreur(atelier, qtbot, services):
    FauxFlux.echec_au_numero = 2
    base = atelier.reglages_de_base()
    atelier.generer_variantes([base, base.copie(), base.copie()])
    qtbot.waitUntil(lambda: atelier._serie is None, timeout=5000)
    assert [p.variante for p in services.projets.serie(1)] == ["A"]
    assert atelier.statut.property("role") == "erreur"
    assert "Variante B non générée" in atelier.statut.text() and "Déjà prêtes : A" in atelier.statut.text()
    assert len(FauxFlux.appels) == 2  # la C n'a pas été demandée
    assert atelier.comparaison is None  # une seule variante prête : rien à comparer


def test_arreter_une_serie(atelier, qtbot, services):
    base = atelier.reglages_de_base()
    atelier.generer_variantes([base, base.copie(), base.copie()])
    atelier.arreter_variantes()  # pendant la variante A : elle est gardée, les suivantes non
    qtbot.waitUntil(lambda: atelier._serie is None, timeout=5000)
    assert [p.variante for p in services.projets.serie(1)] == ["A"]
    assert "arrêtée" in atelier.statut.text()


def test_ecoute_pendant_la_generation(atelier, qtbot, services):
    atelier.flux.simulation = True  # comme avec une carte son, sans rien jouer
    assert atelier.ecoute_directe.isChecked()
    atelier.generer()
    qtbot.waitUntil(lambda: len(services.projets.projet.prises) == 1, timeout=5000)
    assert FauxFlux.appels[-1][1] is True  # audio demandé en flux
    # Les deux morceaux ont été joués pendant la génération ; la prise complète est gardée.
    assert atelier.flux.a_joue and atelier.flux.octets_joues == 2 * len(MORCEAU)
    assert not atelier.flux.actif
    assert atelier.statut.property("role") == "succes"


def test_sans_ecoute_pendant_la_generation(atelier, qtbot, services):
    atelier.flux.simulation = True
    atelier.ecoute_directe.setChecked(False)
    assert services.preferences.lire(CLE_ECOUTE_DIRECTE, True) is False  # choix retenu
    atelier.generer()
    qtbot.waitUntil(lambda: len(services.projets.projet.prises) == 1, timeout=5000)
    assert FauxFlux.appels[-1][1] is False and not atelier.flux.a_joue


def test_lecteur_en_flux(app_configuree):
    flux = LecteurFlux(simulation=True)
    fins = []
    flux.fini.connect(lambda: fins.append(True))
    assert flux.commencer()
    flux.ajouter(b"\x00\x00" * 2400, 24_000)  # 0,1 s : pas encore assez d'avance pour démarrer
    assert not flux.a_joue
    flux.ajouter(b"\x00\x00" * 6000, 24_000)  # 0,35 s au total : la lecture démarre
    assert flux.a_joue and flux.octets_joues == 2 * 8400
    flux.terminer()
    assert fins == [True] and not flux.actif


def test_lecteur_en_flux_sans_carte_son(app_configuree):
    flux = LecteurFlux()
    assert not flux.commencer()  # pas de sortie audio (tests) : la prise sera jouée à la fin
    flux.ajouter(MORCEAU, 24_000)
    flux.terminer()
    assert not flux.a_joue and not flux.actif


def test_bascule_au_meme_moment_du_texte(app_configuree):
    assert position_equivalente(4_000, 10_000, 12_000) == 4_800  # 40 % de A → 40 % de B
    assert position_equivalente(20_000, 10_000, 12_000) == 12_000
    assert position_equivalente(1_000, 0, 12_000) == 0
    comparateur = ComparateurAudio([Path("a.wav"), Path("b.wav")], [10_000, 12_000])
    comparateur.aller_a(4_000)
    comparateur.jouer()
    comparateur.basculer(1)
    assert (comparateur.actif, comparateur.position(), comparateur.en_lecture) == (1, 4_800, True)
    comparateur.pause()
    comparateur.basculer(0)  # en pause aussi : même moment, sans lancer la lecture
    assert (comparateur.actif, comparateur.position(), comparateur.en_lecture) == (0, 4_000, False)


def test_lecture_enchainee(app_configuree, qtbot, monkeypatch):
    monkeypatch.setattr(module_comparateur, "PAUSE_ENCHAINEMENT_MS", 10)
    comparateur = ComparateurAudio([Path("a.wav"), Path("b.wav"), Path("c.wav")], [1_000] * 3)
    comparateur.enchainer()
    assert (comparateur.actif, comparateur.enchainement, comparateur.en_lecture) == (0, True, True)
    comparateur.variante_finie()
    qtbot.waitUntil(lambda: comparateur.actif == 1, timeout=2000)
    comparateur.variante_finie()
    qtbot.waitUntil(lambda: comparateur.actif == 2, timeout=2000)
    comparateur.variante_finie()  # la dernière : fin de la lecture enchaînée
    assert not comparateur.en_lecture and not comparateur.enchainement


def test_tache_qui_donne_des_nouvelles(app_configuree, qtbot):
    nouvelles, resultats = [], []

    def travail(progres):
        for numero in range(3):
            progres(numero)
        return "fini"

    taches.lancer_avec_progres(travail, resultats.append, None, nouvelles.append)
    qtbot.waitUntil(lambda: resultats == ["fini"], timeout=2000)
    assert nouvelles == [0, 1, 2]  # dans l'ordre, avant le résultat
