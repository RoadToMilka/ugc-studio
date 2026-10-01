"""Module Script (V2) : enchaînement des appels au modèle (fiche, accroches, écriture, relecture),
avec un faux adaptateur qui répond comme Google."""

import json

import pytest

from ugc_studio.ecriture.brief import Brief
from ugc_studio.ecriture.consignes import CONSIGNE_SYSTEME, SCHEMA_RELECTURE, SCHEMA_SCRIPT, bloc_brief
from ugc_studio.ecriture.exemples import EXEMPLES_FOURNIS
from ugc_studio.ecriture.fiche import SCHEMA_FICHE
from ugc_studio.ecriture.page_produit import GOOGLE, ErreurLecture, PageLue
from ugc_studio.ecriture.redaction import (
    ACCROCHES,
    ECRITURE,
    LECTURE,
    RELECTURE,
    Appel,
    ErreurRedaction,
    analyser_page,
    ecrire_script,
    estimer_accroches,
    estimer_lecture,
    estimer_script,
    lire_par_google,
    proposer_accroches,
)
from ugc_studio.fournisseurs.base import Adaptateur, ErreurFournisseur
from ugc_studio.fournisseurs.texte import AdresseLue, ResultatTexte

FICHE = {
    "nom": "Culotte Léa (selon le modèle)",
    "marque": "",
    "type_produit": "Culotte menstruelle",
    "prix": "21 €",
    "prix_barre": "",
    "offre": "Livraison offerte en France métropolitaine",
    "benefices": ["Au sec jusqu'à 12 h", "Douce", "Lavable"],
    "distinction": "4 couches absorbantes.",
    "problemes": ["Fuites la nuit"],
    "objections": ["Le prix"],
    "preuves": [],
    "clientele": "Femmes de 18 à 45 ans",
    "noms_a_prononcer": ["Léa"],
}


class AdaptateurFactice(Adaptateur):
    identifiant = "faux"
    nom = "Faux"

    def __init__(self, reponses):
        super().__init__("cle-de-test")
        self.reponses = list(reponses)
        self.requetes = []

    def lister_modeles(self):
        return []

    def generer_texte(self, requete):
        self.requetes.append(requete)
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        if isinstance(reponse, ResultatTexte):
            return reponse
        return ResultatTexte(json.dumps(reponse, ensure_ascii=False), 1_000, 300)


def _page():
    return PageLue("https://x.fr/products/lea", "shopify", "2026-10-01T10:00:00+02:00", "Données…", nom="Culotte menstruelle Léa", prix="21,90 €", prix_barre="27,90 €")


def test_fiche_d_une_page_lue_par_l_app():
    adaptateur = AdaptateurFactice([FICHE])
    nouvelles = []
    fiche = analyser_page(adaptateur, "gemini-3.8-flash", _page(), "fr-FR", nouvelles.append)
    requete = adaptateur.requetes[0]
    assert requete.schema == SCHEMA_FICHE and requete.reflexion == "low" and not requete.lire_adresses
    assert requete.consigne_systeme == CONSIGNE_SYSTEME
    assert '<product_page source="shopify">' in requete.texte and "never guess" in requete.texte
    # Les valeurs exactes lues par l'app l'emportent sur celles du modèle.
    assert (fiche.nom, fiche.prix, fiche.prix_barre) == ("Culotte menstruelle Léa", "21,90 €", "27,90 €")
    assert fiche.benefices[0] == "Au sec jusqu'à 12 h"
    assert nouvelles == ["Analyse de la page par le modèle…", Appel(LECTURE, "gemini-3.8-flash", 1_000, 300)]


def test_reponse_illisible():
    adaptateur = AdaptateurFactice([ResultatTexte("Désolé, je ne peux pas.", 10, 10)])
    with pytest.raises(ErreurRedaction, match="illisible"):
        analyser_page(adaptateur, "gemini-3.8-flash", _page(), "fr-FR")


def test_page_lue_par_google():
    adaptateur = AdaptateurFactice(
        [ResultatTexte(json.dumps(FICHE), 6_000, 400, adresses_lues=[AdresseLue("https://x.fr/p", "success")])]
    )
    page, fiche = lire_par_google(adaptateur, ["gemini-3.8-flash"], "https://x.fr/p", "fr-FR")
    requete = adaptateur.requetes[0]
    assert requete.lire_adresses and requete.schema == SCHEMA_FICHE
    assert "<product_page_url>https://x.fr/p</product_page_url>" in requete.texte
    assert page.source == GOOGLE and page.prix == "21 €" and "Au sec jusqu'à 12 h" in page.texte
    assert fiche.nom == FICHE["nom"]


@pytest.mark.parametrize(
    ("statut", "extrait"),
    [("paywall", "réservée"), ("unsafe", "dangereuse"), ("error", "n'a pas pu lire")],
)
def test_page_que_google_ne_peut_pas_lire(statut, extrait):
    adaptateur = AdaptateurFactice([ResultatTexte(json.dumps(FICHE), 10, 10, adresses_lues=[AdresseLue("https://x.fr/p", statut)])])
    with pytest.raises(ErreurLecture, match=extrait):
        lire_par_google(adaptateur, ["gemini-3.8-flash"], "https://x.fr/p", "fr-FR")


def test_un_autre_modele_essaie_si_le_premier_ne_sait_pas_lire_les_pages():
    refus = ErreurFournisseur("Google a refusé la demande (code 400).", "requete")
    adaptateur = AdaptateurFactice([refus, ResultatTexte(json.dumps(FICHE), 10, 10)])
    page, _fiche = lire_par_google(adaptateur, ["gemini-3.8-flash", "gemini-3.5-flash"], "https://x.fr/p", "fr-FR")
    assert [r.modele for r in adaptateur.requetes] == ["gemini-3.8-flash", "gemini-3.5-flash"]
    assert page.nom == FICHE["nom"]
    # Une autre erreur (quota, clé…) ne change pas de modèle.
    quota = ErreurFournisseur("Limite d'utilisation atteinte.", "quota")
    with pytest.raises(ErreurFournisseur, match="Limite"):
        lire_par_google(AdaptateurFactice([quota]), ["gemini-3.8-flash", "gemini-3.5-flash"], "https://x.fr/p", "fr-FR")


def test_google_ne_trouve_rien():
    vide = {**FICHE, "nom": "", "benefices": []}
    with pytest.raises(ErreurLecture, match="rien trouvé"):
        lire_par_google(AdaptateurFactice([vide]), ["gemini-3.8-flash"], "https://x.fr/p", "fr-FR")


def test_accroches():
    brief = Brief(produit="Culotte Léa", reseau="meta", nombre_accroches=3)
    reponse = {
        "accroches": [
            {"texte": "Mes nuits ont changé.", "angle": "temoignage", "pourquoi": "Intrigue.", "alerte": ""},
            {"texte": "Tu as des règles abondantes ?", "angle": "probleme_solution", "pourquoi": "Direct.",
             "alerte": "Meta refuse une caractéristique personnelle supposée."},
            {"texte": "3 raisons d'essayer Léa.", "angle": "liste", "pourquoi": "Liste.", "alerte": ""},
            {"texte": "En trop.", "angle": "pov", "pourquoi": "", "alerte": ""},
        ]
    }
    adaptateur = AdaptateurFactice([reponse])
    nouvelles = []
    accroches = proposer_accroches(adaptateur, brief, "Texte de la page", list(EXEMPLES_FOURNIS[:2]), nouvelles.append)
    assert [a.texte for a in accroches] == ["Mes nuits ont changé.", "Tu as des règles abondantes ?", "3 raisons d'essayer Léa."]
    assert accroches[1].alerte.startswith("Meta")
    requete = adaptateur.requetes[0]
    assert "Write 3 different hooks" in requete.texte and "<ad_rules>" in requete.texte and "<examples>" in requete.texte
    assert "personal attribute" in requete.texte  # règle de Meta donnée pour Facebook et Instagram
    assert nouvelles[-1] == Appel(ACCROCHES, "gemini-3.8-flash", 1_000, 300)
    with pytest.raises(ErreurRedaction, match="aucune accroche"):
        proposer_accroches(AdaptateurFactice([{"accroches": []}]), brief, "", [])


def _reponse_script(textes, style=""):
    return {
        "angle": "temoignage",
        "repliques": [
            {"roles": ["accroche"] if rang == 0 else ["preuve"], "texte": texte, "style": style, "style_fr": ""}
            for rang, texte in enumerate(textes)
        ],
    }


def _relecture(corrige=False, repliques=(), corrections=(), gravite_regles="ok"):
    return {
        "points": [
            {"critere": "accroche", "gravite": "ok", "explication": ""},
            {"critere": "langage_parle", "gravite": "leger", "explication": "Une phrase un peu longue."},
            {"critere": "regles", "gravite": gravite_regles, "explication": "Promesse trop forte." if gravite_regles != "ok" else ""},
        ],
        "corrige": corrige,
        "repliques": list(repliques),
        "corrections": list(corrections),
    }


def test_script_ecrit_puis_relu_sans_correction():
    brief = Brief(produit="Sérum", duree_s=10, balises=True, styles=False)
    texte = " ".join(["mot"] * 26) + " <laugh>"  # ≈ 10,2 s
    adaptateur = AdaptateurFactice([_reponse_script([texte]), _relecture()])
    nouvelles = []
    script = ecrire_script(adaptateur, brief, "Page", list(EXEMPLES_FOURNIS[:1]), "", nouvelles.append)
    ecriture, relecture = adaptateur.requetes
    assert ecriture.schema == SCHEMA_SCRIPT and relecture.schema == SCHEMA_RELECTURE
    assert ecriture.reflexion == relecture.reflexion == "medium"
    assert "Tags: you may add 1 or 2" in ecriture.texte and "Delivery styles: none" in ecriture.texte
    assert '"texte": "mot mot' in relecture.texte and "<laugh>" in relecture.texte  # le script à relire
    assert script.repliques[0].script[-1] == {"balise": "laugh"} and script.angle == "temoignage"
    assert (script.tokens_entree, script.tokens_sortie) == (2_000, 600)  # écriture + relecture
    assert script.corrections == []
    points = {(p.critere, p.par): p.gravite for p in script.relecture}
    assert points[("duree", "app")] == "ok"
    assert points[("langage_parle", "modele")] == "leger"
    assert [n for n in nouvelles if isinstance(n, Appel)] == [
        Appel(ECRITURE, "gemini-3.8-flash", 1_000, 300),
        Appel(RELECTURE, "gemini-3.8-flash", 1_000, 300),
    ]
    assert "Écriture du script…" in nouvelles and "Relecture du script…" in nouvelles


def test_point_grave_corrige_avant_affichage():
    brief = Brief(produit="Sérum", duree_s=10, mots_interdits="miracle")
    trop_long = "Ce sérum miracle " + " ".join(["mot"] * 60)
    corrige = _reponse_script(["Ce sérum change tout. " + " ".join(["mot"] * 20)])["repliques"]
    adaptateur = AdaptateurFactice(
        [_reponse_script([trop_long]), _relecture(True, corrige, ["Script raccourci.", "« miracle » retiré."], "grave")]
    )
    script = ecrire_script(adaptateur, brief, "Page", [])
    relecture = adaptateur.requetes[1].texte
    assert "shorten the script to about 27 words" in relecture  # mesuré par l'app
    assert "Forbidden words used: miracle." in relecture
    assert script.corrections == ["Script raccourci.", "« miracle » retiré."]
    assert "miracle" not in script.texte_api()
    graves = [p for p in script.relecture if p.gravite == "grave"]
    assert graves == []  # corrigés : décrits dans les corrections, plus dans la liste
    assert {p.critere for p in script.relecture if p.par == "app"} >= {"duree", "mots_interdits"}


def test_point_grave_non_corrige_reste_visible():
    brief = Brief(duree_s=10)
    adaptateur = AdaptateurFactice([_reponse_script([" ".join(["mot"] * 27)]), _relecture(gravite_regles="grave")])
    script = ecrire_script(adaptateur, brief, "Page", [])
    assert [(p.critere, p.par) for p in script.relecture if p.gravite == "grave"] == [("regles", "modele")]


def test_accroche_imposee_et_erreurs():
    brief = Brief(duree_s=10)
    adaptateur = AdaptateurFactice([_reponse_script(["Mes nuits ont changé.", " ".join(["mot"] * 22)]), _relecture()])
    script = ecrire_script(adaptateur, brief, "", [], accroche="Mes nuits ont changé.")
    assert 'Line 1 must be exactly this hook, word for word: "Mes nuits ont changé."' in adaptateur.requetes[0].texte
    assert "(no product page: use the brief only)" in adaptateur.requetes[0].texte
    assert script.accroche_imposee == "Mes nuits ont changé."
    assert all(p.critere != "accroche" or p.par == "modele" for p in script.relecture)
    with pytest.raises(ErreurRedaction, match="aucune réplique"):
        ecrire_script(AdaptateurFactice([{"angle": "pov", "repliques": []}]), brief, "", [])
    # Une erreur de Google pendant la relecture remonte (l'écriture a déjà été signalée pour son coût).
    nouvelles = []
    with pytest.raises(ErreurFournisseur):
        ecrire_script(
            AdaptateurFactice([_reponse_script(["Bonjour."]), ErreurFournisseur("Surcharge.", "serveur")]),
            brief, "", [], "", nouvelles.append,
        )
    assert [n.operation for n in nouvelles if isinstance(n, Appel)] == [ECRITURE]


def test_brief_donne_au_modele():
    brief = Brief(
        pays="BE", langue="fr-BE", reseau="meta", age="45-54", genre="femme", age_personne="environ 50 ans",
        produit="Brosse", mentions="Offre valable jusqu'au 31/10", duree_s=20,
    )
    texte = bloc_brief(brief)
    assert "Language: French (Belgium)." in texte and "'GSM'" in texte
    assert "Currency: EUR (€)." in texte
    assert "about 54 words" in texte
    assert 'Address the viewer formally, with "vous"' in texte  # Facebook, 45 à 54 ans
    assert "Speaker: a woman, environ 50 ans (use the matching grammatical agreements)." in texte
    assert "Mandatory mentions (use each one word for word): Offre valable jusqu'au 31/10" in texte
    assert "Description" not in texte  # champ vide : omis
    assert "Address the viewer" not in bloc_brief(Brief(langue="en-US", pays="US"))


def test_estimations_avant_de_lancer():
    brief = Brief(produit="Sérum")
    lecture = estimer_lecture("x" * 20_000, "gemini-3.8-flash", "fr-FR")
    assert lecture.tokens_entree > 5_000 and lecture.tokens_sortie == 700 + 400
    accroches = estimer_accroches(brief, "Page", list(EXEMPLES_FOURNIS[:3]))
    assert accroches.tokens_sortie == 6 * 60 + 1_500
    script = estimer_script(brief, "Page", list(EXEMPLES_FOURNIS[:3]))
    assert script.tokens_entree > 2 * 1_500 and script.tokens_sortie == 700 + 1_500 + 900 + 1_500
