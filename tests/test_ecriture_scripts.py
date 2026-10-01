"""Module Script (V2) : conversion du texte du modèle (balises, mots accentués), scripts, relecture
par l'app et exemples."""

import pytest

from ugc_studio.ecriture.brief import Brief
from ugc_studio.ecriture.controles import controler, controle_duree
from ugc_studio.ecriture.exemples import (
    EXEMPLES_FOURNIS,
    BibliothequeExemples,
    ExempleScript,
    adapter_au_brief,
    choisir_exemples,
    texte_des_exemples,
)
from ugc_studio.ecriture.scripts import (
    RepliqueEcrite,
    ScriptEcrit,
    nouveau_script,
    repliques_depuis_reponse,
    segments_depuis_modele,
    texte_pour_modele,
)
from ugc_studio.script import texte_brut, texte_pour_api


def test_balises_et_mot_accentue():
    segments, notes = segments_depuis_modele("J'entends *tout* autour <laugh> et <rire> c'est *fou*.")
    assert segments == [
        {"texte": "J'entends "},
        {"texte": "tout", "accentue": True},
        {"texte": " autour "},
        {"balise": "laugh"},
        {"texte": " et "},
        {"balise": "laugh"},  # nom français reconnu, gardé en anglais
        {"texte": " c'est fou."},  # un seul mot accentué par réplique
    ]
    assert notes == ["Un seul mot accentué par réplique : « fou » ne l'est plus"]
    assert texte_pour_api(segments) == "J'entends TOUT autour <laugh> et <laugh> c'est fou."
    assert texte_brut(segments) == "J'entends tout autour et c'est fou."  # sous-titres


def test_balise_inconnue_ou_non_demandee_retiree():
    segments, notes = segments_depuis_modele("Salut <smile> toi <short pause> !", balises=True)
    assert segments == [{"texte": "Salut toi "}, {"balise": "short pause"}, {"texte": " !"}]
    assert notes == ["Balise inconnue retirée : « <smile> »"]
    segments, notes = segments_depuis_modele("Salut <laugh> toi *vraiment*.", balises=False, accents=False)
    assert segments == [{"texte": "Salut toi vraiment."}]
    assert notes == ["Balise retirée (non demandée) : « laugh »", "Accentuation retirée (non demandée) : « vraiment »"]


def test_guillemets_autour_de_la_replique_retires():
    segments, _notes = segments_depuis_modele('"Le lien est en dessous."')
    assert segments == [{"texte": "Le lien est en dessous."}]


def test_texte_pour_le_modele_reciproque():
    texte = "<breath> Regarde : j'entends *tout* autour."
    segments, notes = segments_depuis_modele(texte)
    assert not notes and texte_pour_modele(segments) == texte


def test_repliques_de_la_reponse():
    brutes = [
        {"roles": ["probleme"], "texte": "J'avais le teint gris.", "style": "warm", "style_fr": "chaleureuse"},
        {"roles": ["offre", "inconnu"], "texte": "   ", "style": "", "style_fr": ""},
        {"roles": ["appel_action"], "texte": "Le lien est en dessous.", "style": "upbeat", "style_fr": "enjouée"},
    ]
    repliques, notes = repliques_depuis_reponse(brutes, balises=False, styles=False, accents=False)
    assert notes == []
    assert [r.roles for r in repliques] == [["accroche", "probleme"], ["appel_action"]]  # l'accroche d'abord
    assert all(r.style == "" and r.style_fr == "" for r in repliques)  # styles non demandés
    repliques, _notes = repliques_depuis_reponse(brutes, balises=False, styles=True, accents=False)
    assert (repliques[0].style, repliques[0].style_fr) == ("warm", "chaleureuse")


def _script(textes: list[str], duree: int = 25) -> ScriptEcrit:
    repliques = [RepliqueEcrite(["accroche"], [{"texte": t}]) for t in textes]
    return nouveau_script(
        modele="gemini-3.8-flash", reseau="tiktok", langue="fr-FR", angle="temoignage", duree_visee_s=duree,
        repliques=repliques,
    )


def test_script_enregistre_et_relu():
    script = _script(["J'ai arrêté le fond de teint.", "Le lien est en dessous."])
    script.repliques[0].script.append({"balise": "laugh"})
    assert script.texte_api() == "J'ai arrêté le fond de teint.<laugh>\nLe lien est en dessous."
    assert script.nombre_de_mots() == 12
    assert ScriptEcrit.depuis_dict(script.en_dict()) == script
    assert ScriptEcrit.depuis_dict({"repliques": []}) is None


def test_duree_controlee_par_l_app():
    mots = " ".join(["mot"] * 68)
    assert controle_duree(_script([mots])).gravite == "ok"  # 68 mots à 2,7 mots/s ≈ 25 s
    leger = controle_duree(_script([" ".join(["mot"] * 76)]))
    assert leger.gravite == "leger" and "trop long de 13 %" in leger.explication
    grave = controle_duree(_script([" ".join(["mot"] * 40)]))
    assert grave.gravite == "grave" and "trop court" in grave.explication


def test_mots_interdits_et_mentions():
    brief = Brief(mots_interdits="garanti, n°1", mentions="Code GLOW20")
    script = _script(["Résultat GARANTÍ, le n°1 des sérums !"])
    points = {p.critere: p for p in controler(script, brief)}
    assert points["mots_interdits"].gravite == "grave"
    assert "« garanti »" in points["mots_interdits"].explication and "« n°1 »" in points["mots_interdits"].explication
    assert points["mentions"].gravite == "grave"
    script = _script(["Avec le code glow20, c'est garantie zéro souci."])
    points = {p.critere: p for p in controler(script, brief)}
    assert points["mots_interdits"].gravite == "ok"  # « garantie » n'est pas « garanti »
    assert points["mentions"].gravite == "ok"


def test_styles_et_accroche_choisie_verifies():
    script = _script(["Fini les fuites.", "Le lien est en dessous."])
    script.repliques[1].style = "voix chaleureuse et rassurante"
    script.accroche_imposee = "Mes nuits ont changé."
    points = controler(script, Brief(), ["Réplique 1 : Balise inconnue retirée : « <smile> »"])
    criteres = [(p.critere, p.gravite) for p in points]
    assert ("styles", "leger") in criteres  # style en français
    assert ("accroche", "leger") in criteres
    assert ("balises", "leger") in criteres


def test_exemples_fournis_valides():
    """Les 5 scripts de l'annexe A : balises connues, un mot accentué au plus, durée proche de la cible."""
    assert len(EXEMPLES_FOURNIS) == 5
    for exemple in EXEMPLES_FOURNIS:
        repliques, notes = repliques_depuis_reponse(exemple.repliques, True, True, True)
        assert not notes, exemple.titre
        assert repliques[0].roles[0] == "accroche"
        script = nouveau_script(
            modele="m", reseau=exemple.reseau, langue=exemple.langue, angle=exemple.angle,
            duree_visee_s=exemple.duree_s, repliques=repliques,
        )
        assert controle_duree(script).gravite in ("ok", "leger"), (exemple.titre, script.duree_estimee())


def test_choix_des_exemples():
    belge = Brief(langue="fr-BE", pays="BE", reseau="tiktok", angle="liste")
    assert choisir_exemples(list(EXEMPLES_FOURNIS), belge)[0].identifiant == "fourni-voltie"
    snap = Brief(reseau="snapchat")
    assert choisir_exemples(list(EXEMPLES_FOURNIS), snap)[0].identifiant == "fourni-choppy"
    # Tes scripts gardés passent avant les scripts fournis.
    garde = ExempleScript("mon-script", "Mon meilleur", "fr-FR", "meta", "", "vous", 20, "…", [{"texte": "Bonjour."}])
    assert choisir_exemples([*EXEMPLES_FOURNIS, garde], Brief(reseau="meta"))[0].identifiant == "mon-script"
    assert len(choisir_exemples(list(EXEMPLES_FOURNIS), Brief())) == 3
    # Aucun exemple dans la langue du brief : les autres servent quand même (structure, rythme).
    assert len(choisir_exemples(list(EXEMPLES_FOURNIS), Brief(langue="en-US", pays="US"))) == 3


def test_exemples_adaptes_aux_options_du_brief():
    runbeat = next(e for e in EXEMPLES_FOURNIS if e.identifiant == "fourni-runbeat")
    sans = adapter_au_brief(runbeat, Brief(balises=False, styles=False, accents=False))
    assert "<breath>" not in sans[1]["texte"] and "*" not in sans[1]["texte"]
    assert sans[1]["texte"].startswith("Regarde :") and sans[1]["style"] == ""
    avec = adapter_au_brief(runbeat, Brief(balises=True, styles=True, accents=True))
    assert "<breath>" in avec[1]["texte"] and "*tout*" in avec[1]["texte"] and avec[1]["style"]
    texte = texte_des_exemples([runbeat], Brief())
    assert texte.startswith("<example") and "Why it works:" in texte and texte.endswith("</example>")


def test_bibliotheque_d_exemples(tmp_path):
    chemin = tmp_path / "scripts_exemples.json"
    bibliotheque = BibliothequeExemples(chemin)
    assert len(bibliotheque.exemples()) == 5
    vus = []
    bibliotheque.abonner(lambda: vus.append(1))
    garde = ExempleScript("abc", "Culotte Léa", "fr-FR", "meta", "temoignage", "tu", 20, "…", [{"texte": "Fini."}], fourni=True)
    bibliotheque.ajouter(garde)
    bibliotheque.retirer("fourni-choppy")
    relue = BibliothequeExemples(chemin)
    assert [e.identifiant for e in relue.exemples()][:1] == ["abc"] and not relue.gardes()[0].fourni
    assert not relue.contient("fourni-choppy") and len(relue.exemples()) == 5
    relue.retirer("abc")
    assert not BibliothequeExemples(chemin).gardes() and vus == [1, 1]
    assert ExempleScript.depuis_dict({"repliques": [{"texte": "x"}], "duree_s": "abc"}).duree_s == 0
    assert ExempleScript.depuis_dict({"repliques": []}) is None


@pytest.mark.parametrize("identifiant", [e.identifiant for e in EXEMPLES_FOURNIS])
def test_exemple_fourni_relu(identifiant):
    exemple = next(e for e in EXEMPLES_FOURNIS if e.identifiant == identifiant)
    assert ExempleScript.depuis_dict(exemple.en_dict()) == exemple
