"""V2, lot 2 : interface du module Script (variantes, retouche, copie, note et « Retenir », comparaison,
bibliothèque de briefs, « Mes meilleurs scripts »), vitesse de parole mesurée, nombres dits à la
belge ou à la suisse, accroches envoyées en variantes de voix. Avec un faux Google."""

import json

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from ugc_studio.ecriture.brief import Brief
from ugc_studio.ecriture.controles import controler
from ugc_studio.ecriture.exemples import EXEMPLES_FOURNIS
from ugc_studio.ecriture.page_produit import PageLue
from ugc_studio.ecriture.scripts import RepliqueEcrite, nouveau_script
from ugc_studio.ecriture.variantes import ACCROCHES, MEMES, PAR_VARIANTE, ReglagesScript
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.texte import ResultatTexte
from ugc_studio.nombres import BELGIQUE, FRANCE
from ugc_studio.ui.dialogues import briefs as dialogue_briefs
from ugc_studio.ui.dialogues import retouche as dialogue_retouche
from ugc_studio.ui.dialogues import variantes as dialogue_variantes
from ugc_studio.ui.dialogues.comparer_scripts import DialogueComparerScripts, choix_par_defaut
from ugc_studio.ui.dialogues.meilleurs_scripts import DialogueAjoutExemple, DialogueMeilleursScripts
from ugc_studio.ui.dialogues.variantes_script import ONGLET_ACCROCHES, ONGLET_PAR_VARIANTE, DialogueVariantesScript
from ugc_studio.ui.fenetre_principale import FenetrePrincipale
from ugc_studio.ui.pages.script import PageScript


def _script(accroche, mots=55):
    return {
        "angle": "temoignage",
        "repliques": [
            {"roles": ["accroche"], "texte": accroche, "style": "intrigued", "style_fr": "intriguée"},
            {"roles": ["preuve", "appel_action"], "texte": " ".join(["mot"] * mots), "style": "warm", "style_fr": "chaleureuse"},
        ],
    }


RELECTURE = {"points": [], "corrige": False, "repliques": [], "corrections": []}


def _accroches(*textes):
    return {"accroches": [{"texte": t, "angle": "pov", "pourquoi": "", "alerte": ""} for t in textes]}


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


def _attendre(qtbot, atelier, nombre):
    qtbot.waitUntil(lambda: len(atelier.scripts.cartes()) == nombre and not atelier._occupe, timeout=10_000)


def _scripts_de_demo(etat, nombre=2):
    for rang in range(nombre):
        script = nouveau_script(
            modele="gemini-3.8-flash", reseau="tiktok", langue="fr-FR", angle="temoignage", duree_visee_s=10,
            repliques=[RepliqueEcrite(["accroche"], [{"texte": f"Accroche {rang + 1}."}]),
                       RepliqueEcrite(["preuve"], [{"texte": " ".join(["mot"] * 24)}])],
            cout_eur="0.01",
        )
        script.relecture = controler(script, etat.brief)
        etat.ajouter(script)
    return etat.scripts


# --- Variantes de script -----------------------------------------------------------------------------


def test_fenetre_des_variantes_de_script(app_configuree, qtbot, services):
    brief = Brief(produit="Sérum", reseau="tiktok", duree_s=20)
    dialogue = DialogueVariantesScript(services, brief, "Page", list(EXEMPLES_FOURNIS[:2]))
    qtbot.addWidget(dialogue)
    assert dialogue.mode() == MEMES and dialogue.nombre() == 3
    assert dialogue.bouton_ecrire.text() == "Écrire les 3 scripts" and dialogue.cout.text() != "prix inconnu"
    dialogue.onglets.setCurrentIndex(ONGLET_PAR_VARIANTE)
    assert dialogue.mode() == PAR_VARIANTE and dialogue.nombre() == 2
    champs = dialogue.colonnes()[1].champs
    champs["duree_s"].setValue(15)
    champs["accroche"].setText("Trois gouttes, et voilà.")
    assert champs["duree_s"].property("modifie") and champs["accroche"].property("modifie")
    assert not champs["angle"].property("modifie") and not dialogue.colonnes()[0].champs["duree_s"].property("modifie")
    variantes = dialogue.variantes()
    assert (variantes[1].duree_s, variantes[1].accroche) == (15, "Trois gouttes, et voilà.")
    dialogue.dupliquer_variante(1)
    assert len(dialogue.colonnes()) == 3 and dialogue.variantes()[2].duree_s == 15
    dialogue.supprimer_variante(0)
    dialogue.supprimer_variante(0)
    assert len(dialogue.colonnes()) == 2  # 2 au minimum
    dialogue.onglets.setCurrentIndex(ONGLET_ACCROCHES)
    assert dialogue.mode() == ACCROCHES and dialogue.bouton_ecrire.text() == "Écrire les 3 scripts"


def test_variantes_memes_reglages(page, qtbot, services, avec_cle):
    atelier = page.atelier
    FauxGoogle.reponses = [
        _accroches("Accroche A.", "Accroche B.", "Accroche C."),
        _script("Accroche A."), RELECTURE, _script("Accroche B."), RELECTURE, _script("Accroche C."), RELECTURE,
    ]
    atelier.ecrire_variantes(MEMES, 3)
    _attendre(qtbot, atelier, 3)
    assert "each one on a different angle" in FauxGoogle.requetes[0].texte
    etat = services.projets.projet.ecriture
    assert [s.nom() for s in etat.scripts] == ["Script 1 (variante A)", "Script 2 (variante B)", "Script 3 (variante C)"]
    assert len({s.serie for s in etat.scripts}) == 1 and {s.mode for s in etat.scripts} == {MEMES}
    assert [s.accroche_imposee for s in etat.scripts] == ["Accroche A.", "Accroche B.", "Accroche C."]
    # Les accroches (une demande) sont réparties entre les 3 scripts : la somme fait le coût total.
    total = sum(appel.cout_eur for appel in services.couts.lire())
    assert abs(sum(float(s.cout_eur) for s in etat.scripts) - float(total)) < 1e-5
    assert [c.titre.text() for c in atelier.scripts.cartes()] == [s.nom() for s in etat.scripts]  # A, B, C
    assert "Comparer" in atelier.statut.text() and not atelier.barre_scripts.isHidden()


def test_variantes_accroches_seulement_puis_voix(app_configuree, qtbot, services, tmp_path, avec_cle, monkeypatch):
    services.projets.creer("Sérum", tmp_path)
    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    fenetre.show()
    atelier = fenetre.page("script").atelier
    FauxGoogle.reponses = [_script("Mes nuits ont changé."), RELECTURE, _accroches("Je dors enfin.", "Fini les fuites.", "En trop.", "Encore.")]
    atelier.ecrire_variantes(ACCROCHES, 3)
    _attendre(qtbot, atelier, 3)
    etat = services.projets.projet.ecriture
    assert [s.accroche() for s in etat.scripts] == ["Mes nuits ont changé.", "Je dors enfin.", "Fini les fuites."]
    assert all(s.repliques[1:] == etat.scripts[0].repliques[1:] for s in etat.scripts)  # même corps
    assert [s.lettre for s in etat.scripts] == ["A", "B", "C"] and {s.mode for s in etat.scripts} == {ACCROCHES}
    carte = atelier.scripts.cartes()[1]
    assert carte.action_variantes is not None and "3 accroches" in carte.action_variantes.text()

    # « Envoyer les accroches en variantes » : le script A part dans Voix, puis la fenêtre Variantes
    # s'ouvre avec une variante par accroche.
    vues = []

    def exec_variantes(dialogue):
        vues.append(dialogue)
        return 0  # « Annuler »

    monkeypatch.setattr(dialogue_variantes.DialogueVariantes, "exec", exec_variantes)
    carte.action_variantes.trigger()
    assert fenetre.module_actuel() == "voix"
    assert services.projets.projet.repliques[0].script == etat.scripts[0].repliques[0].script
    assert vues and vues[0].onglets.currentIndex() == dialogue_variantes.ONGLET_PAR_VARIANTE
    textes = [v.repliques[0].script for v in vues[0].variantes()]
    assert textes == [s.repliques[0].script for s in etat.scripts]
    assert all(s.envoye_le for s in etat.scripts)


def test_variantes_par_reglages(page, qtbot, services, avec_cle):
    atelier = page.atelier
    base = ReglagesScript.depuis_brief(services.projets.projet.ecriture.brief)
    courte = base.copie()
    courte.duree_s, courte.accroche = 15, "Trois gouttes."
    FauxGoogle.reponses = [_script("Une accroche."), RELECTURE, _script("Trois gouttes.", 30), RELECTURE]
    atelier.ecrire_variantes(PAR_VARIANTE, 2, [base, courte])
    _attendre(qtbot, atelier, 2)
    assert "Target duration: 15 seconds" in FauxGoogle.requetes[2].texte
    assert 'word for word: "Trois gouttes."' in FauxGoogle.requetes[2].texte
    etat = services.projets.projet.ecriture
    assert [s.duree_visee_s for s in etat.scripts] == [25, 15] and [s.lettre for s in etat.scripts] == ["A", "B"]


# --- Retouche, copie, note, « Retenir » ---------------------------------------------------------------


def test_retouche_copie_note_et_retenir(page, qtbot, services, avec_cle, monkeypatch):
    atelier = page.atelier
    FauxGoogle.reponses = [_script("J'ai arrêté le fond de teint."), RELECTURE]
    atelier.ecrire()
    _attendre(qtbot, atelier, 1)
    original = services.projets.projet.ecriture.scripts[0]

    def exec_retouche(dialogue):
        dialogue.ajouter_suggestion("Plus court", -0.25)
        return 1  # « Retoucher »

    monkeypatch.setattr(dialogue_retouche.DialogueRetouche, "exec", exec_retouche)
    FauxGoogle.reponses = [_script("J'ai arrêté le fond de teint.", 40), RELECTURE]
    atelier.scripts.cartes()[0].bouton_retoucher.click()
    _attendre(qtbot, atelier, 2)
    assert '"Plus court"' in FauxGoogle.requetes[-2].texte and "never undo it" in FauxGoogle.requetes[-1].texte
    nouveau = services.projets.projet.ecriture.scripts[1]
    assert (nouveau.origine, nouveau.consigne_retouche, nouveau.duree_visee_s) == (original.identifiant, "Plus court", 19)
    operations = [appel.operation for appel in services.couts.lire()]
    assert operations.count("script : retouche") == 1
    carte = atelier.scripts.cartes()[0]
    assert carte.script is nouveau and carte.origine.text() == "Retouche du script 1 : « Plus court »"

    carte.bouton_retenir.click()
    assert nouveau.retenu and carte.bouton_retenir.text() == "Retenu" and not carte.pastille_retenu.isHidden()
    carte.etoiles[3].click()
    assert nouveau.note == 4
    atelier.dupliquer_script(original)
    copie = services.projets.projet.ecriture.scripts[-1]
    assert copie.nom() == "Script 3" and copie.origine == original.identifiant and copie.cout_eur is None
    assert atelier.scripts.cartes()[0].origine.text() == "Copie du script 1"
    relu = json.loads(services.projets.projet.fichier.read_text(encoding="utf-8"))["ecriture"]["scripts"]
    assert [(s["numero"], s["retenu"], s["note"]) for s in relu] == [(1, False, 0), (2, True, 4), (3, False, 0)]


def test_comparer_les_scripts(app_configuree, qtbot, services, tmp_path):
    projet = services.projets.creer("Sérum", tmp_path)
    scripts = _scripts_de_demo(projet.ecriture, 3)
    assert choix_par_defaut(scripts) == [scripts[2], scripts[1], scripts[0]]
    retouche = nouveau_script(modele="m", reseau="tiktok", langue="fr-FR", angle="", duree_visee_s=10,
                              repliques=[RepliqueEcrite(["accroche"], [{"texte": "Court."}])], origine=scripts[0].identifiant)
    projet.ecriture.ajouter(retouche)
    assert choix_par_defaut(projet.ecriture.scripts) == [scripts[0], retouche]  # une retouche et son original
    dialogue = DialogueComparerScripts(projet.ecriture.scripts)
    qtbot.addWidget(dialogue)
    colonnes = dialogue.colonnes()
    assert [c.script for c in colonnes] == [scripts[0], retouche, None]
    colonnes[2].liste.setCurrentIndex(colonnes[2].liste.findData(scripts[1].identifiant))
    assert colonnes[2].script is scripts[1] and not colonnes[2].bouton_envoyer.isHidden()
    colonnes[2].bouton_envoyer.click()
    assert dialogue.script_a_envoyer is scripts[1]


# --- Bibliothèque de briefs, exemples -----------------------------------------------------------------


def test_enregistrer_puis_charger_un_brief(page, qtbot, services, tmp_path, monkeypatch):
    atelier = page.atelier
    etat = services.projets.projet.ecriture
    etat.brief.produit, etat.brief.reseau = "Culotte Léa", "meta"
    etat.page = PageLue("https://x.fr/products/lea", "shopify", "2026-10-01T10:00:00+02:00", "Données…", nom="Léa")
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("Léa, Facebook", True))
    atelier.enregistrer_brief()
    assert [b.nom for b in services.briefs.briefs()] == ["Léa, Facebook"]
    assert "Léa, Facebook" in atelier.statut.text()
    # Même nom : confirmation, puis remplacement.
    questions = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **_k: questions.append(a[2]) or QMessageBox.StandardButton.Yes)
    atelier.enregistrer_brief()
    assert questions and "le remplacer" in questions[0] and len(services.briefs.briefs()) == 1

    # Nouveau projet : le brief se charge (avec la page lue), les options d'écriture restent.
    services.projets.creer("Autre", tmp_path)
    nouveau = services.projets.projet.ecriture
    nouveau.brief.accents = True

    def exec_bibliotheque(dialogue):
        assert len(dialogue.lignes()) == 1
        dialogue.lignes()[0].bouton_charger.click()
        return dialogue.result()

    monkeypatch.setattr(dialogue_briefs.DialogueBibliothequeBriefs, "exec", exec_bibliotheque)
    atelier.bouton_charger_brief.click()
    assert nouveau.brief is not None and services.projets.projet.ecriture.brief.produit == "Culotte Léa"
    charge = services.projets.projet.ecriture
    assert charge.brief.reseau == "meta" and charge.brief.accents is True
    assert charge.page is not None and charge.page.nom == "Léa"
    assert atelier.formulaire.champs["produit"].valeur() == "Culotte Léa"


def test_mes_meilleurs_scripts(app_configuree, qtbot, services, monkeypatch):
    dialogue = DialogueMeilleursScripts(services, Brief(produit="Gourde", langue="fr-BE", reseau="meta"))
    qtbot.addWidget(dialogue)
    assert len(dialogue.lignes()) == 5 and dialogue.bouton_remettre.isHidden()  # les 5 scripts fournis

    ajout = DialogueAjoutExemple(Brief(produit="Gourde", langue="fr-BE", reseau="meta"))
    qtbot.addWidget(ajout)
    assert not ajout.bouton_ajouter.isEnabled() and ajout.titre.text() == "Gourde"
    ajout.texte.setPlainText("J'ai arrêté les bouteilles.\n\nCette gourde garde le froid.")
    ajout.note.setText("CPA 9 €")
    ajout.bouton_ajouter.click()
    assert ajout.exemple is not None and ajout.exemple.langue == "fr-BE" and ajout.exemple.reseau == "meta"
    services.exemples.ajouter(ajout.exemple)
    dialogue.rafraichir()
    ligne = dialogue.lignes()[0]
    assert ligne.exemple.note == "CPA 9 €" and ligne.note is not None
    ligne.note.setText("CPA 7 €")
    ligne.note.editingFinished.emit()
    assert services.exemples.gardes()[0].note == "CPA 7 €"

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    fourni = next(l for l in dialogue.lignes() if l.exemple.fourni)
    dialogue.retirer(fourni.exemple)
    assert len(dialogue.lignes()) == 5 and not dialogue.bouton_remettre.isHidden()
    dialogue.remettre()
    assert len(dialogue.lignes()) == 6 and dialogue.bouton_remettre.isHidden()


# --- Vitesse de parole, nombres dits ------------------------------------------------------------------


def test_vitesse_mesuree_dans_le_brief_et_les_cartes(page, qtbot, services):
    atelier = page.atelier
    etat = services.projets.projet.ecriture
    _scripts_de_demo(etat, 1)
    atelier._afficher_scripts()
    assert atelier.formulaire.info_duree.text().endswith("vitesse de départ : 2,7 mots/s")
    avant = atelier.scripts.cartes()[0].details.text()
    texte = " ".join(["mot"] * 20)
    services.vitesses.noter("Kore", "p1", texte, 10.0)  # 2 mots par seconde : une voix lente
    info = atelier.formulaire.info_duree.text()
    assert info.startswith("25 s ≈ 50 mots") and "vitesse de Kore mesurée sur 1 prise : 2,0 mots/s" in info
    assert atelier.scripts.cartes()[0].details.text() != avant  # durée estimée plus longue
    duree = next(p for p in etat.scripts[0].relecture if p.critere == "duree")
    assert duree.explication.startswith("≈ 13 s")  # 25 mots à 2 mots par seconde


def test_nombres_dits_dans_le_module_voix(app_configuree, qtbot, services, tmp_path, monkeypatch):
    projet = services.projets.creer("Batterie", tmp_path)
    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    fenetre.show()
    voix = fenetre.page("voix").atelier
    assert not voix.zone_nombres.isHidden() and voix.nombres.currentData() == FRANCE
    script = nouveau_script(
        modele="m", reseau="tiktok", langue="fr-BE", angle="", duree_visee_s=10,
        repliques=[RepliqueEcrite(["accroche"], [{"texte": "Elle est à 29,90 € seulement."}])],
    )
    projet.ecriture.ajouter(script)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    assert fenetre.envoyer_dans_voix(script)
    assert projet.voix.nombres == BELGIQUE and voix.nombres.currentData() == BELGIQUE
    assert "à la belge" in voix.statut.text()
    assert projet.repliques[0].script == [{"texte": "Elle est à 29,90 € seulement."}]  # le script garde les chiffres
    # L'estimation compte le texte envoyé : « Elle est à vingt-neuf euros nonante seulement. »
    assert voix.estimation.text().startswith("46 caractères")
    assert voix.estimation.toolTip() == "Durée estimée avec la vitesse de départ : 2,7 mots/s"
    services.projets.changer_langue("en-US")
    assert voix.zone_nombres.isHidden() and voix._nombres() == FRANCE  # anglais : sans objet
