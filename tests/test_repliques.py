"""Étape 4 (§5.2, §5.3, §5.5) : répliques et styles, traduction, bibliothèque, prononciation."""

from decimal import Decimal

import pytest
from PySide6.QtGui import QTextCursor

from ugc_studio.audio import duree_wav, wav_depuis_pcm
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.texte import ResultatTexte
from ugc_studio.fournisseurs.voix import ResultatVoix
from ugc_studio.projets import RepliqueProjet
from ugc_studio.prononciation import Prononciation
from ugc_studio.styles import EXEMPLES
from ugc_studio.ui.pages.voix import PageVoix


class FauxGoogle(Adaptateur):
    identifiant = "google"
    nom = "Faux"
    requetes_voix: list = []
    requetes_texte: list = []

    def lister_modeles(self):
        return []

    def generer_voix(self, requete):
        FauxGoogle.requetes_voix.append(requete)
        wav = wav_depuis_pcm(b"\x00\x00" * 24_000)
        return ResultatVoix(wav, duree_wav(wav), tokens_entree=20, tokens_sortie=25)

    def generer_texte(self, requete):
        FauxGoogle.requetes_texte.append(requete)
        return ResultatTexte('"warm and enthusiastic, fast-paced"', tokens_entree=120, tokens_sortie=40)


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path, monkeypatch):
    from ugc_studio.ui import connexion_ia

    FauxGoogle.requetes_voix, FauxGoogle.requetes_texte = [], []
    monkeypatch.setattr(connexion_ia, "creer_adaptateur", lambda _f, _cle: FauxGoogle("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.8-flash-tts"])
    services.projets.creer("Sérum", tmp_path)
    page = PageVoix(services)
    qtbot.addWidget(page)
    page.show()
    return page.atelier


def _texte(texte: str) -> list[dict]:
    return [{"texte": texte}]


# --- Répliques --------------------------------------------------------------------------------


def test_repliques_du_projet_affichees_et_enregistrees(atelier, services):
    projet = services.projets.projet
    projet.repliques = [RepliqueProjet(_texte("Stop !"), "excited"), RepliqueProjet(_texte("Le lien."), "calm")]
    services.projets.enregistrer()
    atelier._projet_change(projet)
    cartes = atelier.repliques.cartes()
    assert [c.titre.text() for c in cartes] == ["Réplique 1", "Réplique 2"]
    assert [c.champ_style.consigne() for c in cartes] == ["excited", "calm"]
    cartes[1].editeur.definir_segments(_texte("Le lien est en dessous."))
    cartes[1].champ_style.champ.setText("warm")
    atelier.enregistrer_maintenant()
    assert projet.repliques[1] == RepliqueProjet(_texte("Le lien est en dessous."), "warm")


def test_ajouter_une_replique_et_y_inserer_une_balise(atelier, qtbot):
    atelier.editeur.definir_segments(_texte("Premier bloc."))
    atelier.ajouter_replique()
    premiere, seconde = atelier.repliques.cartes()
    assert atelier.repliques.carte_active is seconde  # la nouvelle réplique reçoit le focus
    atelier.palette.boutons["laugh"].click()
    assert seconde.editeur.segments() == [{"balise": "laugh"}]
    assert premiere.editeur.segments() == _texte("Premier bloc.")
    assert premiere.bouton_plus.menu().actions()[1].isEnabled() is False  # « Monter » impossible pour la 1re


def test_decouper_une_replique_au_curseur(atelier):
    carte = atelier.repliques.cartes()[0]
    carte.champ_style.definir("excited", "excité")
    carte.editeur.definir_segments(_texte("Stop ! Ce sérum a changé ma peau."))
    curseur = carte.editeur.textCursor()
    curseur.setPosition(len("Stop ! "))
    carte.editeur.setTextCursor(curseur)
    atelier.repliques.decouper(carte)
    premiere, seconde = atelier.repliques.repliques()
    assert premiere == RepliqueProjet(_texte("Stop !"), "excited", "excité")
    assert seconde == RepliqueProjet(_texte("Ce sérum a changé ma peau."), "excited", "excité")


def test_deplacer_et_supprimer(atelier):
    atelier.editeur.definir_segments(_texte("A"))
    atelier.ajouter_replique()
    atelier.editeur.definir_segments(_texte("B"))
    premiere, seconde = atelier.repliques.cartes()
    atelier.repliques._action("monter", seconde)
    assert [r.script for r in atelier.repliques.repliques()] == [_texte("B"), _texte("A")]
    atelier.repliques.supprimer(premiere, confirmer=False)
    assert [r.script for r in atelier.repliques.repliques()] == [_texte("B")]
    atelier.repliques.supprimer(seconde, confirmer=False)  # la dernière réplique reste
    assert len(atelier.repliques.cartes()) == 1


def test_generer_avec_deux_repliques(atelier, qtbot, services):
    carte = atelier.repliques.cartes()[0]
    carte.editeur.definir_segments(_texte("Stop ! Regarde ça."))
    carte.champ_style.champ.setText("excited, fast-paced")
    nouvelle = atelier.repliques.ajouter()
    nouvelle.editeur.definir_segments(_texte("Le lien est en dessous."))
    nouvelle.champ_style.champ.setText("warm")
    atelier.generer()
    qtbot.waitUntil(lambda: len(services.projets.projet.prises) == 1, timeout=5000)
    (requete,) = FauxGoogle.requetes_voix
    assert [(r.texte, r.style) for r in requete.repliques] == [
        ("Stop ! Regarde ça.", "excited, fast-paced"),
        ("Le lien est en dessous.", "warm"),
    ]
    (ligne,) = atelier.prises.lignes()
    assert ligne.prise.style == "styles par réplique"


# --- Style : vérifications, assistant, traduction --------------------------------------------


def test_style_en_francais_signale(atelier):
    champ = atelier.repliques.cartes()[0].champ_style
    champ.champ.setText("chuchoté et complice")
    assert any("anglais" in message for message in champ.avertissements())
    champ.champ.setText("whispered and playful")
    assert champ.avertissements() == []


def test_son_ponctuel_insere_en_balise(atelier):
    carte = atelier.repliques.cartes()[0]
    carte.champ_style.champ.setText("laugh at the start")
    carte.champ_style.balise_suggeree.emit("laugh")
    assert {"balise": "laugh"} in carte.editeur.segments()


def test_traduire_un_style_en_anglais(atelier, qtbot, services):
    champ = atelier.repliques.cartes()[0].champ_style
    champ.champ.setText("chaleureux et enthousiaste, débit rapide")
    champ.traduire()
    qtbot.waitUntil(lambda: champ.consigne() == "warm and enthusiastic, fast-paced", timeout=5000)
    assert champ.consigne_fr() == "chaleureux et enthousiaste, débit rapide"
    assert not champ.traduction.isHidden() and "chaleureux" in champ.traduction.text()
    (requete,) = FauxGoogle.requetes_texte
    assert requete.modele == "gemini-3.8-flash" and requete.reflexion == "low"
    (appel,) = services.couts.lire()
    assert (appel.operation, appel.modele, appel.projet) == ("traduction", "gemini-3.8-flash", "Sérum")
    assert appel.cout_eur is not None and appel.cout_eur > 0
    # Modifier le style à la main efface la traduction, qui ne lui correspond plus.
    champ.champ.setText("warm")
    assert champ.consigne_fr() == "" and champ.traduction.isHidden()


def test_assistant_de_style(app_configuree, qtbot):
    from ugc_studio.ui.dialogues.assistant_style import DialogueAssistantStyle

    dialogue = DialogueAssistantStyle()
    qtbot.addWidget(dialogue)
    assert not dialogue.bouton_utiliser.isEnabled()
    dialogue.emotion.setCurrentIndex(dialogue.emotion.findData("chaleureux"))
    dialogue.rythme.setCurrentIndex(dialogue.rythme.findData("débit rapide"))
    assert dialogue.resultat() == ("warm, fast-paced", "chaleureux, débit rapide")
    assert dialogue.bouton_utiliser.isEnabled()
    assert dialogue.anglais.text() == "warm, fast-paced"


# --- Bibliothèque de styles ---------------------------------------------------------------------


def test_appliquer_un_style_de_la_bibliotheque(atelier, services, qtbot):
    from ugc_studio.ui.dialogues.styles import DialogueBibliothequeStyles

    dialogue = DialogueBibliothequeStyles(services, atelier, cible="réplique 1")
    qtbot.addWidget(dialogue)
    assert len(dialogue.lignes()) == len(EXEMPLES)
    hook = next(s for s in EXEMPLES if s.nom == "Hook énergique")
    dialogue.appliquer(hook.identifiant)
    assert dialogue.style_choisi.identifiant == hook.identifiant
    carte = atelier.repliques.cartes()[0]
    atelier.appliquer_style(carte, dialogue.style_choisi)
    assert (carte.champ_style.consigne(), carte.champ_style.consigne_fr()) == (hook.consigne, hook.consigne_fr)
    assert atelier.voix.currentData() == hook.voix == "Puck"
    assert "Hook énergique" in atelier.statut.text()


def test_creer_un_style(app_configuree, qtbot, services):
    from ugc_studio.styles import Style
    from ugc_studio.ui.dialogues.styles import DialogueBibliothequeStyles, DialogueStyle

    liste = DialogueBibliothequeStyles(services)
    qtbot.addWidget(liste)
    dialogue = DialogueStyle(services, Style("", "", "", "", voix="Leda"))
    qtbot.addWidget(dialogue)
    dialogue.valider()
    assert "nom" in dialogue.statut.text()
    dialogue.nom.setText("Témoignage doux")
    dialogue.champ_style.definir("soft and sincere", "doux et sincère")
    dialogue.balises.setText("sigh, truc")
    dialogue.valider()
    assert "truc" in dialogue.statut.text()  # balise inconnue refusée
    dialogue.balises.setText("sigh, <short pause>")
    dialogue.valider()
    cree = next(s for s in services.styles.styles if s.nom == "Témoignage doux")
    assert (cree.consigne, cree.consigne_fr, cree.voix, cree.balises) == (
        "soft and sincere",
        "doux et sincère",
        "Leda",
        ["sigh", "short pause"],
    )
    assert len(liste.lignes()) == len(EXEMPLES) + 1  # la liste ouverte s'est mise à jour
    liste.reject()
    services.styles.dupliquer(cree.identifiant)  # liste fermée : plus de mise à jour (pas d'erreur)


# --- Dictionnaire de prononciation ------------------------------------------------------------


def test_dictionnaire_de_prononciation(atelier, services, qtbot):
    from ugc_studio.ui.dialogues.prononciation import DialoguePrononciation

    dialogue = DialoguePrononciation(services, atelier.tester_prononciation, atelier)
    qtbot.addWidget(dialogue)
    mot, dit, _ecouter, _retirer = dialogue.projet._lignes[0][2]
    mot.setText("Glowzy")
    dit.setText("Glo-zi")
    dialogue.global_.ajouter(Prononciation("Sérum", "Sé-rom"))
    dialogue.valider()
    assert services.projets.projet.prononciations == [Prononciation("Glowzy", "Glo-zi")]
    assert services.prononciations.entrees == [Prononciation("Sérum", "Sé-rom")]

    atelier.editeur.definir_segments(_texte("Glowzy, le sérum qui change tout."))
    atelier.generer()
    qtbot.waitUntil(lambda: len(services.projets.projet.prises) == 1, timeout=5000)
    (prise,) = services.projets.projet.prises
    assert prise.texte_api == "Glo-zi, le Sé-rom qui change tout."  # ce que la voix prononce
    assert prise.script == _texte("Glowzy, le sérum qui change tout.")  # l'orthographe est gardée


def test_tester_une_prononciation(atelier, qtbot, services):
    atelier.tester_prononciation("Glo-zi")
    qtbot.waitUntil(lambda: len(services.couts.lire()) == 1, timeout=5000)
    (appel,) = services.couts.lire()
    assert appel.operation == "essai de prononciation"
    (requete,) = FauxGoogle.requetes_voix
    assert requete.repliques[0].texte == "Glo-zi"
    # Deuxième écoute : l'audio est gardé en cache, pas de nouvel appel.
    atelier.tester_prononciation("Glo-zi")
    assert len(FauxGoogle.requetes_voix) == 1


def test_estimation_compte_toutes_les_repliques(atelier):
    atelier.editeur.definir_segments(_texte("Bonjour à toutes et à tous"))
    atelier._mettre_a_jour_estimation()
    assert atelier.estimation.text().startswith("26 caractères")
    atelier.ajouter_replique()
    atelier.editeur.definir_segments(_texte("Merci"))
    atelier._mettre_a_jour_estimation()
    assert atelier.estimation.text().startswith("31 caractères")
    assert atelier.cout_estime.montant > Decimal(0)


def test_editeur_de_replique_grandit_avec_son_texte(atelier, qtbot):
    editeur = atelier.editeur
    hauteur = editeur.height()
    editeur.definir_segments(_texte("Une ligne.\n" * 12))
    qtbot.waitUntil(lambda: editeur.height() > hauteur, timeout=2000)
    assert editeur.verticalScrollBar().maximum() == 0 or not editeur.verticalScrollBar().isVisible()
    editeur.moveCursor(QTextCursor.MoveOperation.End)
