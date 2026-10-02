"""V2, lot 1 : interface du module Script (brief, lecture de la page, accroches, scripts, envoi dans
Voix), avec un faux Google et une fausse boutique."""

import json

import pytest

from serveur_factice import ServeurFactice
from ugc_studio.ecriture.page_produit import SHOPIFY
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.texte import ResultatTexte
from ugc_studio.projets import RepliqueProjet
from ugc_studio.ui import taches
from ugc_studio.ui.composants.section_repliable import SectionRepliable
from ugc_studio.ui.dialogues import messages
from ugc_studio.ui.fenetre_principale import FenetrePrincipale
from ugc_studio.ui.pages.script import PageScript

ACCROCHES = {
    "accroches": [
        {"texte": "J'ai arrêté le fond de teint.", "angle": "temoignage", "pourquoi": "Surprend.", "alerte": ""},
        {"texte": "Trois gouttes, et ma sœur a remarqué.", "angle": "temoignage", "pourquoi": "Preuve.", "alerte": ""},
        {"texte": "Tu as le teint terne ?", "angle": "probleme_solution", "pourquoi": "Direct.",
         "alerte": "Meta refuse une caractéristique personnelle supposée."},
    ]
}


def _script(accroche):
    corps = " ".join(["mot"] * 55)
    return {
        "angle": "temoignage",
        "repliques": [
            {"roles": ["accroche"], "texte": accroche, "style": "intrigued", "style_fr": "intriguée"},
            {"roles": ["preuve", "appel_action"], "texte": f"{corps} <laugh>", "style": "warm", "style_fr": "chaleureuse"},
        ],
    }


RELECTURE = {
    "points": [{"critere": "langage_parle", "gravite": "leger", "explication": "Une phrase un peu longue."}],
    "corrige": False,
    "repliques": [],
    "corrections": [],
}


class FauxGoogle(Adaptateur):
    identifiant = "google"
    nom = "Faux"
    reponses: list = []
    requetes: list = []

    def lister_modeles(self):
        return []

    def generer_texte(self, requete):
        FauxGoogle.requetes.append(requete)
        return ResultatTexte(json.dumps(FauxGoogle.reponses.pop(0), ensure_ascii=False), 2_000, 800)


@pytest.fixture
def avec_cle(services, monkeypatch):
    from ugc_studio.ui import connexion_ia

    FauxGoogle.reponses, FauxGoogle.requetes = [], []
    monkeypatch.setattr(connexion_ia, "creer_adaptateur", lambda _f, _cle: FauxGoogle("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.8-flash", "gemini-3.8-flash-tts"])


@pytest.fixture
def page(app_configuree, qtbot, services, tmp_path):
    services.projets.creer("Sérum", tmp_path)
    page = PageScript(services)
    qtbot.addWidget(page)
    page.show()
    return page


def test_sans_projet_puis_avec(app_configuree, qtbot, services, tmp_path):
    page = PageScript(services)
    qtbot.addWidget(page)
    assert page.currentWidget() is page.sans_projet
    services.projets.creer("Brosse", tmp_path)
    assert page.currentWidget() is page.atelier
    assert page.atelier.titre.text() == "Script • Brosse"
    assert page.atelier.bouton_ecrire.text() == "Écrire le script"


def test_brief_modifie_et_enregistre(page, qtbot, services):
    atelier = page.atelier
    brief = services.projets.projet.ecriture.brief
    champ = atelier.formulaire.champs["prix"]
    brief.pre_remplir({"prix": "21,90 €"})
    atelier.formulaire.rafraichir_champs()
    assert champ.valeur() == "21,90 €" and not champ.marque.isHidden()
    atelier.formulaire.sections[0].ouvrir()  # « Produit et offre »
    champ.saisie.clear()
    qtbot.keyClicks(champ.saisie, "19,90")  # tapé à la main : le champ n'est plus « d'après la page »
    assert brief.prix == "19,90" and "prix" not in brief.pre_remplis and champ.marque.isHidden()
    atelier.formulaire.reseau.setCurrentIndex(atelier.formulaire.reseau.findData("snapchat"))
    assert brief.reseau == "snapchat"
    assert atelier.formulaire.info_duree.text().startswith("10 s ≈ 27 mots")
    atelier.enregistrer_maintenant()
    relu = json.loads(services.projets.projet.fichier.read_text(encoding="utf-8"))
    assert relu["ecriture"]["brief"]["prix"] == "19,90" and relu["ecriture"]["brief"]["reseau"] == "snapchat"


def test_genre_d_apres_la_voix_du_projet(page, services):
    brief = services.projets.projet.ecriture.brief
    assert brief.genre == "femme" and "genre" in brief.pre_remplis  # voix par défaut : Kore
    assert not page.atelier.formulaire.marque_genre.isHidden()


def test_options_retenues_pour_le_prochain_projet(page, services, tmp_path):
    page.atelier.formulaire.accents.setChecked(True)
    services.projets.creer("Autre", tmp_path)
    assert services.projets.projet.ecriture.brief.accents is True


def test_langue_du_projet_proposee(page, qtbot, services):
    formulaire = page.atelier.formulaire
    assert formulaire.zone_langue_projet.isHidden()
    formulaire.pays.setCurrentIndex(formulaire.pays.findData("BE"))
    formulaire.langue.setCurrentIndex(formulaire.langue.findData("nl-BE"))
    assert not formulaire.zone_langue_projet.isHidden()
    formulaire.bouton_langue_projet.click()
    assert services.projets.projet.langue == "nl-BE"
    assert formulaire.zone_langue_projet.isHidden()


def test_lecture_d_une_boutique_shopify_sans_cle(page, qtbot, services):
    """Sans clé, l'app lit quand même la page (gratuit) : les valeurs exactes pré-remplissent le brief."""
    boutique = ServeurFactice()
    try:
        boutique.programmer(200, b"<html><body><p>Livraison offerte.</p></body></html>", {"Content-Type": "text/html"})
        boutique.programmer(
            200,
            {"title": "Culotte Léa", "vendor": "MC", "price": 2190, "compare_at_price": 2790,
             "variants": [{"id": 1, "price": 2190, "compare_at_price": 2790, "available": True}]},
        )
        atelier = page.atelier
        atelier.produit.adresse.setText(f"{boutique.url}/products/lea")
        atelier.produit.bouton_lire.click()
        qtbot.waitUntil(lambda: taches.en_cours() == 0 and not atelier._occupe, timeout=10_000)
    finally:
        boutique.arreter()
    etat = services.projets.projet.ecriture
    assert etat.page.source == SHOPIFY and etat.fiche is None
    assert (etat.brief.produit, etat.brief.prix, etat.brief.promo) == ("Culotte Léa", "21,90 €", "au lieu de 27,90 €")
    assert not atelier.formulaire.champs["produit"].marque.isHidden()
    assert "clé Google" in atelier.statut.text()
    assert "Lu par l'app (données Shopify)" in atelier.produit.etat.text()


def test_accroches_puis_deux_scripts_puis_envoi_dans_voix(app_configuree, qtbot, services, tmp_path, avec_cle, monkeypatch):
    services.projets.creer("Sérum", tmp_path)
    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    fenetre.show()
    atelier = fenetre.page("script").atelier

    FauxGoogle.reponses = [ACCROCHES]
    atelier.bouton_accroches.click()
    qtbot.waitUntil(lambda: len(atelier.accroches.lignes()) == 3, timeout=10_000)
    lignes = atelier.accroches.lignes()
    assert lignes[2].accroche.alerte.startswith("Meta")
    lignes[0].case.setChecked(True)
    lignes[1].case.setChecked(True)
    assert atelier.bouton_ecrire.text() == "Écrire les 2 scripts"
    atelier.formulaire.balises.setChecked(True)  # sinon la balise <laugh> du faux Google serait retirée

    FauxGoogle.reponses = [_script(ACCROCHES["accroches"][0]["texte"]), RELECTURE, _script(ACCROCHES["accroches"][1]["texte"]), RELECTURE]
    atelier.bouton_ecrire.click()
    qtbot.waitUntil(lambda: len(atelier.scripts.cartes()) == 2 and not atelier._occupe, timeout=10_000)
    etat = services.projets.projet.ecriture
    assert [s.accroche_imposee for s in etat.scripts] == [a["texte"] for a in ACCROCHES["accroches"][:2]]
    assert "Line 1 must be exactly this hook" in FauxGoogle.requetes[1].texte
    # Coûts : accroches, puis écriture et relecture de chaque script, notés un par un.
    operations = [appel.operation for appel in services.couts.lire()]
    assert operations.count("script : écriture") == 2 and operations.count("script : relecture") == 2
    assert operations.count("script : accroches") == 1
    assert all(s.cout_eur is not None and float(s.cout_eur) > 0 for s in etat.scripts)
    carte = atelier.scripts.cartes()[0]  # le plus récent en haut
    assert carte.script is etat.scripts[1]
    assert carte.pastille_envoye.isHidden()

    # Envoi dans Voix : le module Voix a déjà un texte, la confirmation est demandée.
    fenetre.page("voix").atelier.repliques.definir([RepliqueProjet([{"texte": "Ancien script."}])])
    questions = []
    monkeypatch.setattr(messages, "confirmer", lambda *args, **_kw: questions.append(args[2]) or True)
    carte.bouton_envoyer.click()
    assert questions and "Remplacer la réplique actuelle" in questions[0]
    assert fenetre.module_actuel() == "voix"
    repliques = services.projets.projet.repliques
    assert [r.style for r in repliques] == ["intrigued", "warm"]
    assert repliques[1].script[-1] == {"balise": "laugh"}
    assert etat.scripts[1].envoye_le and not carte.pastille_envoye.isHidden()

    # « Garder comme exemple » (menu ⋯ depuis le lot 2) : rangé parmi les exemples donnés au modèle.
    carte.action_garder.trigger()
    assert services.exemples.gardes()[0].identifiant == f"script-{etat.scripts[1].identifiant}"
    assert not carte.action_garder.isEnabled() and not carte.pastille_exemple.isHidden()


def test_texte_modifie_a_la_main_puis_reverifie(page, qtbot, services, avec_cle):
    atelier = page.atelier
    FauxGoogle.reponses = [_script("J'ai arrêté le fond de teint."), RELECTURE]
    atelier.ecrire()
    qtbot.waitUntil(lambda: len(atelier.scripts.cartes()) == 1 and not atelier._occupe, timeout=10_000)
    carte = atelier.scripts.cartes()[0]
    script = carte.script
    avant = script.duree_estimee()
    editeur = carte.editeurs[1]
    editeur.selectAll()
    editeur.insertPlainText("Le lien est en dessous.")  # comme une saisie au clavier
    assert script.repliques[1].script == [{"texte": "Le lien est en dessous."}]
    assert script.duree_estimee() < avant
    duree = next(p for p in script.relecture if p.critere == "duree")
    assert duree.gravite == "grave" and "trop court" in duree.explication
    assert any(p.par == "modele" for p in script.relecture)  # l'avis du modèle est gardé
    atelier.supprimer_script(script, confirmer=False)
    assert services.projets.projet.ecriture.scripts == [] and atelier.scripts.isHidden()


def test_avertissement_genre_dans_voix(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ecriture.scripts import RepliqueEcrite, nouveau_script
    from ugc_studio.ui.pages.voix import PageVoix

    projet = services.projets.creer("Barre", tmp_path)
    projet.ecriture.brief.genre = "homme"
    projet.ecriture.scripts = [
        nouveau_script(modele="m", reseau="tiktok", langue="fr-FR", angle="", duree_visee_s=20,
                       repliques=[RepliqueEcrite(["accroche"], [{"texte": "Salut."}])])
    ]
    services.projets.enregistrer()
    page = PageVoix(services)
    qtbot.addWidget(page)
    services.projets.ouvrir(projet.dossier)
    info = page.atelier.info_genre
    assert not info.isHidden() and "un homme" in info.text() and "féminine" in info.text()  # Kore


def test_noms_proposes_au_dictionnaire(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.prononciation import Prononciation
    from ugc_studio.ui.dialogues.prononciation import DialoguePrononciation

    projet = services.projets.creer("Sérum", tmp_path)
    projet.prononciations = [Prononciation("Glowzy", "Glo-zi")]
    dialogue = DialoguePrononciation(services, None, mots_proposes=["glowzy", "Sérum éclat", "Sérum éclat"])
    qtbot.addWidget(dialogue)
    mots = [mot.text() for mot, _dit, _elements in dialogue.projet._lignes]
    assert mots == ["Glowzy", "Sérum éclat"]  # déjà connu : pas en double ; proposé une seule fois
    dialogue.valider()
    assert projet.prononciations == [Prononciation("Glowzy", "Glo-zi")]  # sans prononciation : pas gardé


def test_section_repliable(app_configuree, qtbot):
    section = SectionRepliable("Clientèle")
    qtbot.addWidget(section)
    section.show()
    assert not section.est_ouverte() and section.zone.isHidden()
    section.definir_resume("2 remplis")
    assert not section.resume.isHidden()
    section.titre.click()
    assert section.est_ouverte() and not section.zone.isHidden() and section.resume.isHidden()
