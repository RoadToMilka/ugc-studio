"""Module Script, lot 2 (V2) : bibliothèque de briefs, exemples collés, copies et séries de scripts,
variantes (trois modes), retouche, autres accroches pour un même corps, vitesse de parole."""

import json
from decimal import Decimal

import pytest

from ugc_studio.ecriture.brief import Brief
from ugc_studio.ecriture.briefs import BibliothequeBriefs, nom_propose
from ugc_studio.ecriture.etat import EtatScript
from ugc_studio.ecriture.exemples import EXEMPLES_FOURNIS, BibliothequeExemples, exemple_colle
from ugc_studio.ecriture.fiche import FicheProduit
from ugc_studio.ecriture.page_produit import PageLue
from ugc_studio.ecriture.redaction import (
    ACCROCHES,
    RELECTURE,
    RETOUCHE,
    Appel,
    ErreurRedaction,
    accroches_pour_corps,
    ecrire_script,
    estimer_accroches_pour_corps,
    estimer_retouche,
    proposer_accroches,
    retoucher_script,
    variantes_d_accroches,
)
from ugc_studio.ecriture.scripts import Accroche, PointRelecture, RepliqueEcrite, dupliquer, nouveau_script
from ugc_studio.ecriture.variantes import (
    ACCROCHES as MODE_ACCROCHES,
    MEMES,
    PAR_VARIANTE,
    REGLAGES,
    ReglagesScript,
    cout_estime,
    differences,
    nouvelle_serie,
)
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.texte import ResultatTexte
from ugc_studio.prix import CataloguePrix


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
        return ResultatTexte(json.dumps(self.reponses.pop(0), ensure_ascii=False), 1_000, 300)


def _reponse_script(textes):
    return {
        "angle": "temoignage",
        "repliques": [
            {"roles": ["accroche"] if rang == 0 else ["preuve"], "texte": texte, "style": "", "style_fr": ""}
            for rang, texte in enumerate(textes)
        ],
    }


def _relecture(points=(), corrige=False, repliques=(), corrections=()):
    return {"points": list(points), "corrige": corrige, "repliques": list(repliques), "corrections": list(corrections)}


def _script(textes=("Mes nuits ont changé.", " ".join(["mot"] * 20)), **valeurs):
    repliques = [RepliqueEcrite(["accroche"] if rang == 0 else ["preuve"], [{"texte": t}]) for rang, t in enumerate(textes)]
    valeurs = {"modele": "gemini-3.8-flash", "reseau": "tiktok", "langue": "fr-FR", "angle": "temoignage", "duree_visee_s": 10, **valeurs}
    return nouveau_script(repliques=repliques, **valeurs)


# --- Bibliothèque de briefs --------------------------------------------------------------------------


def test_bibliotheque_de_briefs(tmp_path):
    briefs = BibliothequeBriefs(tmp_path / "briefs.json")
    brief = Brief(produit="Culotte Léa", reseau="meta", duree_s=20)
    page = PageLue("https://x.fr/products/lea", "shopify", "2026-10-01T10:00:00+02:00", "Données…", nom="Léa")
    fiche = FicheProduit(nom="Culotte Léa", benefices=["Au sec"])
    assert nom_propose(brief) == "Culotte Léa (Facebook et Instagram)"
    premier = briefs.enregistrer(nom_propose(brief), brief, " x.fr/products/lea ", page, fiche)
    brief.produit = "Modifié après coup"  # la bibliothèque garde une copie
    assert premier.brief.produit == "Culotte Léa" and premier.adresse == "x.fr/products/lea"
    assert premier.resume() == "Culotte Léa  ·  Facebook et Instagram  ·  20 s  ·  France"
    assert briefs.existe("culotte léa  (facebook et instagram)")

    # Même nom : remplacé (même identifiant) ; autre nom : ajouté.
    remplace = briefs.enregistrer("Culotte Léa (Facebook et Instagram)", Brief(produit="Léa v2"))
    assert remplace.identifiant == premier.identifiant and len(briefs.briefs()) == 1
    autre = briefs.enregistrer("Sérum", Brief(produit="Sérum", duree_s=0))
    assert autre.resume() == "Sérum  ·  TikTok  ·  25 s (auto)  ·  France"
    assert not briefs.renommer(autre.identifiant, "culotte léa (facebook et instagram)")  # nom déjà pris
    assert briefs.renommer(autre.identifiant, "Sérum éclat")

    relue = BibliothequeBriefs(tmp_path / "briefs.json")
    assert {b.nom for b in relue.briefs()} == {"Culotte Léa (Facebook et Instagram)", "Sérum éclat"}
    assert relue.brief(premier.identifiant).brief.produit == "Léa v2"
    relue.retirer(premier.identifiant)
    assert [b.nom for b in BibliothequeBriefs(tmp_path / "briefs.json").briefs()] == ["Sérum éclat"]


def test_brief_enregistre_avec_sa_page(tmp_path):
    briefs = BibliothequeBriefs(tmp_path / "briefs.json")
    page = PageLue("https://x.fr/p", "shopify", "2026-10-01T10:00:00+02:00", "Texte", nom="Léa", prix="21,90 €")
    briefs.enregistrer("Léa", Brief(produit="Léa"), "x.fr/p", page, FicheProduit(nom="Léa"))
    relu = BibliothequeBriefs(tmp_path / "briefs.json").briefs()[0]
    assert relu.page == page and relu.fiche.nom == "Léa" and relu.adresse == "x.fr/p"


# --- Mes meilleurs scripts ----------------------------------------------------------------------------


def test_script_colle_decoupe_en_repliques():
    paragraphes = exemple_colle("Gourde", "J'ai arrêté les bouteilles.\n\nCette gourde garde le froid 24 h.\nLien en dessous.", "fr-FR", "tiktok")
    assert [r["texte"] for r in paragraphes.repliques] == [
        "J'ai arrêté les bouteilles.",
        "Cette gourde garde le froid 24 h. Lien en dessous.",
    ]
    assert paragraphes.repliques[0]["roles"] == ["accroche"] and not paragraphes.fourni
    lignes = exemple_colle("", "Ligne 1 ?\nLigne 2.\nLigne 3.", "fr-BE", "meta", "liste", "vous", 0, " CPA  9 € ")
    assert [r["texte"] for r in lignes.repliques] == ["Ligne 1 ?", "Ligne 2. Ligne 3."]
    assert (lignes.titre, lignes.note, lignes.tutoiement, lignes.angle) == ("Script collé", "CPA 9 €", "vous", "liste")
    assert lignes.duree_s >= 1  # estimée d'après le texte
    bloc = exemple_colle("X", "Première phrase ! Et la suite du script ici.", "fr-FR", "inconnu", "inconnu", duree_s=12)
    assert [r["texte"] for r in bloc.repliques] == ["Première phrase !", "Et la suite du script ici."]
    assert (bloc.reseau, bloc.angle, bloc.duree_s) == ("autre", "", 12)
    assert exemple_colle("X", "   ", "fr-FR", "tiktok") is None


def test_notes_et_exemples_fournis_remis(tmp_path):
    bibliotheque = BibliothequeExemples(tmp_path / "exemples.json")
    colle = exemple_colle("Gourde", "Accroche.\n\nCorps.", "fr-FR", "tiktok")
    bibliotheque.ajouter(colle)
    bibliotheque.noter(colle.identifiant, " CPA 9 € ")
    bibliotheque.noter(EXEMPLES_FOURNIS[0].identifiant, "ignorée")  # un script fourni ne se note pas
    bibliotheque.retirer(EXEMPLES_FOURNIS[1].identifiant)
    relue = BibliothequeExemples(tmp_path / "exemples.json")
    assert relue.gardes()[0].note == "CPA 9 €" and EXEMPLES_FOURNIS[0].note == ""
    assert [e.identifiant for e in relue.fournis_retires()] == [EXEMPLES_FOURNIS[1].identifiant]
    relue.remettre_fournis()
    assert relue.fournis_retires() == [] and relue.contient(EXEMPLES_FOURNIS[1].identifiant)


# --- Copies, séries ------------------------------------------------------------------------------------


def test_dupliquer_un_script():
    script = _script(cout_eur="0.0161", envoye_le="2026-10-01", note=5, retenu=True, serie="s", lettre="B", mode=MEMES)
    script.garde_comme_exemple = True
    copie = dupliquer(script)
    assert copie.identifiant != script.identifiant and copie.origine == script.identifiant
    assert copie.repliques == script.repliques and copie.repliques[0] is not script.repliques[0]
    assert (copie.cout_eur, copie.envoye_le, copie.note, copie.retenu, copie.serie, copie.lettre) == (None, "", 0, False, "", "")
    assert not copie.garde_comme_exemple and copie.consigne_retouche == ""
    copie.repliques[0].script = [{"texte": "Autre"}]
    assert script.repliques[0].script == [{"texte": "Mes nuits ont changé."}]


def test_series_et_numeros():
    etat = EtatScript()
    serie = nouvelle_serie()
    for lettre in "BAC":
        etat.ajouter(_script(serie=serie, lettre=lettre, mode=MODE_ACCROCHES))
    seul = etat.ajouter(_script())
    assert [s.nom() for s in etat.serie(serie)] == ["Script 2 (variante A)", "Script 1 (variante B)", "Script 3 (variante C)"]
    assert seul.nom() == "Script 4" and etat.serie("") == []
    relu = EtatScript.depuis_dict(etat.en_dict())
    assert [s.nom() for s in relu.scripts] == [s.nom() for s in etat.scripts] and relu.scripts[0].mode == MODE_ACCROCHES


# --- Variantes : réglages et coût ----------------------------------------------------------------------


def test_reglages_par_variante():
    brief = Brief(produit="Léa", reseau="meta", duree_s=20, genre="femme", profil="maman", consigne="ton léger")
    base = ReglagesScript.depuis_brief(brief)
    variante = base.copie()
    variante.angle, variante.duree_s, variante.genre, variante.consigne = "pov", 15, "homme", "  ton  léger "
    variante.accroche = "Mes nuits ont changé."
    assert differences(base, variante) == {"angle", "duree_s", "genre", "accroche"}  # consigne : même texte
    assert list(REGLAGES)[:3] == ["angle", "accroche", "duree_s"]
    brief_variante = variante.brief(brief)
    assert (brief_variante.angle, brief_variante.duree_s, brief_variante.genre) == ("pov", 15, "homme")
    assert brief_variante.produit == "Léa" and brief.angle == "auto"  # le brief du projet ne change pas
    variante.duree_s, variante.reseau, variante.modele = 3, "inconnu", ""
    assert (variante.brief(brief).duree_s, variante.brief(brief).reseau, variante.brief(brief).modele) == (
        20, "meta", "gemini-3.8-flash"
    )


def test_cout_estime_des_trois_modes(tmp_path):
    prix = CataloguePrix(tmp_path / "prix.json")
    brief = Brief(produit="Léa")
    memes = cout_estime(MEMES, brief, "Page", [], prix, 3)
    accroches = cout_estime(MODE_ACCROCHES, brief, "Page", [], prix, 3)
    base = ReglagesScript.depuis_brief(brief)
    par_variante = cout_estime(PAR_VARIANTE, brief, "Page", [], prix, variantes=[base, base.copie()])
    assert all(isinstance(c, Decimal) and c > 0 for c in (memes, accroches, par_variante))
    assert accroches < par_variante < memes  # un seul script écrit pour « Accroches seulement »
    inconnu = base.copie()
    inconnu.modele = "modele-sans-prix"
    assert cout_estime(PAR_VARIANTE, brief, "Page", [], prix, variantes=[base, inconnu]) is None


# --- Appels au modèle ------------------------------------------------------------------------------------


def test_accroches_des_variantes_une_par_angle():
    reponse = {"accroches": [{"texte": f"Accroche {n}.", "angle": "pov", "pourquoi": "", "alerte": ""} for n in range(4)]}
    adaptateur = AdaptateurFactice([reponse, reponse])
    accroches = proposer_accroches(adaptateur, Brief(nombre_accroches=6), "", [], nombre=3, une_par_angle=True)
    assert len(accroches) == 3
    assert "Write 3 clearly different hooks for this ad, each one on a different angle" in adaptateur.requetes[0].texte
    proposer_accroches(adaptateur, Brief(angle="routine"), "", [], nombre=2, une_par_angle=True)
    assert "Use only this angle: routine" in adaptateur.requetes[1].texte


def test_autres_accroches_pour_le_meme_corps():
    script = _script()
    brief = Brief(mots_interdits="miracle", balises=False, accents=False)
    reponse = {
        "accroches": [
            {"texte": "Mes nuits ont changé.", "angle": "temoignage", "pourquoi": "", "alerte": ""},  # celle du script
            {"texte": "Un produit miracle ?", "angle": "pov", "pourquoi": "", "alerte": ""},  # mot interdit
            {"texte": "Je dors enfin sans stress.", "angle": "temoignage", "pourquoi": "Rassure.", "alerte": ""},
            {"texte": "Tu as des fuites la nuit ?", "angle": "probleme_solution", "pourquoi": "", "alerte": "Meta : question sur la personne."},
            {"texte": "Encore une.", "angle": "pov", "pourquoi": "", "alerte": ""},
        ]
    }
    adaptateur = AdaptateurFactice([reponse])
    nouvelles = []
    accroches = accroches_pour_corps(adaptateur, brief, "Page", script, 2, nouvelles.append)
    assert [a.texte for a in accroches] == ["Je dors enfin sans stress.", "Tu as des fuites la nuit ?"]
    demande = adaptateur.requetes[0].texte
    assert "Write 4 other hooks that can replace line 1" in demande and "Mes nuits ont changé." in demande
    assert nouvelles[-1] == Appel(ACCROCHES, "gemini-3.8-flash", 1_000, 300)
    with pytest.raises(ErreurRedaction, match="aucune autre accroche"):
        accroches_pour_corps(AdaptateurFactice([{"accroches": [reponse["accroches"][0]]}]), brief, "", script, 2)
    assert estimer_accroches_pour_corps(brief, "Page", 2).tokens_entree > estimer_accroches_pour_corps(brief, "", 2, script).tokens_entree


def test_variantes_d_accroches_gardent_le_corps():
    script = _script()
    script.relecture = [
        PointRelecture("accroche", "leger", "Accroche un peu longue.", "modele"),
        PointRelecture("langage_parle", "leger", "Une phrase longue.", "modele"),
    ]
    accroches = [Accroche("Je dors *enfin* sans stress.", "temoignage"), Accroche("Tu as des fuites ?", "pov", alerte="Meta : question.")]
    variantes = variantes_d_accroches(script, accroches, Brief(duree_s=10, accents=True))
    assert [v.accroche() for v in variantes] == ["Je dors enfin sans stress.", "Tu as des fuites ?"]
    assert variantes[0].repliques[0].script[1] == {"texte": "enfin", "accentue": True}
    assert all(v.repliques[1:] == script.repliques[1:] for v in variantes)
    assert [v.accroche_imposee for v in variantes] == [a.texte for a in accroches]
    criteres = {(p.critere, p.explication) for p in variantes[1].relecture if p.par == "modele"}
    assert ("langage_parle", "Une phrase longue.") in criteres and ("regles", "Accroche : Meta : question.") in criteres
    assert not any(c == "accroche" for c, _ in criteres)  # le point sur l'ancienne accroche ne vaut plus
    assert any(p.critere == "duree" and p.par == "app" for p in variantes[0].relecture)


def test_retouche_d_un_script():
    script = _script()
    brief = Brief(duree_s=8, tutoiement="vous")
    adaptateur = AdaptateurFactice([_reponse_script(["Mes nuits ont changé.", " ".join(["mot"] * 16)]), _relecture()])
    nouvelles = []
    nouveau = retoucher_script(adaptateur, brief, "Page", script, "  plus  court ", nouvelles.append)
    retouche, relecture = adaptateur.requetes
    assert '"plus  court"' in retouche.texte and "takes priority over the brief" in retouche.texte
    assert "Mes nuits ont changé." in retouche.texte and "about 22 words" in retouche.texte  # 8 s
    assert 'never undo it: "plus  court"' in relecture.texte
    assert (nouveau.origine, nouveau.consigne_retouche, nouveau.duree_visee_s, nouveau.tutoiement) == (
        script.identifiant, "plus court", 8, "vous"
    )
    assert [n.operation for n in nouvelles if isinstance(n, Appel)] == [RETOUCHE, RELECTURE]
    assert estimer_retouche(brief, "Page", script, "plus court").tokens_sortie > 0


def test_vitesse_mesuree_dans_l_ecriture():
    """Une voix plus lente : moins de mots demandés, et la durée estimée suit la même vitesse."""
    brief = Brief(duree_s=20)
    adaptateur = AdaptateurFactice([_reponse_script(["Salut.", " ".join(["mot"] * 39)]), _relecture()])
    script = ecrire_script(adaptateur, brief, "", [], mots_par_seconde=2.0)
    assert "about 40 words" in adaptateur.requetes[0].texte  # 20 s à 2 mots par seconde
    duree = next(p for p in script.relecture if p.critere == "duree")
    assert duree.gravite == "ok" and duree.explication.startswith("≈ 20 s")
