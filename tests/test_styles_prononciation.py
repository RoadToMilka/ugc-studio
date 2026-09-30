"""Styles (§5.5), conseils et vérifications en direct, dictionnaire de prononciation (§5.2)."""

from ugc_studio.conseils import CONSEILS_STYLE, semble_francais, verifier_description_voix, verifier_style
from ugc_studio.prononciation import DictionnaireGlobal, Prononciation, appliquer, fusionner
from ugc_studio.styles import EXEMPLES, BibliothequeStyles, Style, assembler

# --- Assistant et bibliothèque de styles -------------------------------------------------------


def test_assistant_assemble_en_anglais_avec_traduction():
    assert assembler("chaleureux", "enthousiaste", "débit rapide") == (
        "warm and enthusiastic, fast-paced",
        "chaleureux et enthousiaste, débit rapide",
    )
    assert assembler("chuchoté", rythme="", intensite="") == ("whispered", "chuchoté")
    assert assembler("", rythme="débit lent") == ("slow pace", "débit lent")


def test_exemples_fournis_puis_modifiables(tmp_path):
    bibliotheque = BibliothequeStyles(tmp_path / "styles.json")
    assert len(bibliotheque.styles) == len(EXEMPLES)
    nouveau = bibliotheque.enregistrer_style(Style("", "Mon hook", "Hook perso", "excited, fast-paced", "excité, débit rapide"))
    assert nouveau.identifiant
    copie = bibliotheque.dupliquer(nouveau.identifiant)
    assert copie.nom == "Mon hook (copie)"
    bibliotheque.supprimer(EXEMPLES[0].identifiant)
    rechargee = BibliothequeStyles(tmp_path / "styles.json")
    noms = [s.nom for s in rechargee.styles]
    assert "Mon hook" in noms and "Mon hook (copie)" in noms and EXEMPLES[0].nom not in noms
    assert "Hook perso" in rechargee.categories()
    assert ("Hook perso", [s for s in rechargee.styles if s.categorie == "Hook perso"]) in rechargee.par_categorie()


def test_bibliotheque_previent_de_ses_changements(tmp_path):
    bibliotheque = BibliothequeStyles(tmp_path / "styles.json")
    appels = []
    bibliotheque.abonner(lambda: appels.append(True))
    bibliotheque.dupliquer(EXEMPLES[0].identifiant)
    assert appels == [True]


# --- Vérifications en direct -------------------------------------------------------------------


def test_style_court_en_anglais_sans_avertissement():
    assert verifier_style("warm and enthusiastic, fast-paced") == []
    assert verifier_style("whispered and playful") == []


def test_style_en_francais_propose_la_traduction():
    (avertissement,) = verifier_style("chuchoté, complice")
    assert avertissement.en_francais and "anglais" in avertissement.message
    assert semble_francais("calme et doux") and not semble_francais("calm and soft")


def test_style_trop_long():
    avertissements = verifier_style("very warm and very enthusiastic and also fast and also a bit loud please now")
    assert any("long" in a.message for a in avertissements)


def test_trait_permanent_et_meta_consigne():
    messages = " ".join(a.message for a in verifier_style("femme de 30 ans, garde la même voix"))
    assert "permanent" in messages and "Méta-consigne" in messages


def test_son_ponctuel_propose_une_balise():
    suggestions = [a.balise_suggeree for a in verifier_style("rire au début") if a.balise_suggeree]
    assert suggestions == ["laugh"]
    assert [a.balise_suggeree for a in verifier_style("sigh at the end")] == ["sigh"]


def test_description_de_voix_trop_longue():
    assert verifier_description_voix("A young woman in her mid-20s with a slightly husky voice.") == []
    assert any("longue" in a.message for a in verifier_description_voix("One sentence. Two sentences. Three sentences."))
    (francais,) = verifier_description_voix("Jeune femme d'environ 25 ans, voix légèrement voilée.")
    assert francais.en_francais


def test_conseils_en_anglais_et_en_francais():
    assert all(c.anglais and c.francais for c in CONSEILS_STYLE)


# --- Dictionnaire de prononciation --------------------------------------------------------------

GLOWZY = Prononciation("Glowzy", "Glo-zi")


def test_prononciation_appliquee_au_texte_du_tts_seulement():
    texte = "J'adore Glowzy ! <laugh> glowzy, c'est top. Glowzyland reste intact."
    assert appliquer(texte, [GLOWZY]) == "J'adore Glo-zi ! <laugh> Glo-zi, c'est top. Glowzyland reste intact."


def test_balises_jamais_modifiees():
    assert appliquer("<laugh> laugh", [Prononciation("laugh", "rire")]) == "<laugh> rire"


def test_le_mot_le_plus_long_gagne():
    entrees = [GLOWZY, Prononciation("Glowzy Pro", "Glo-zi Pro")]
    assert appliquer("Le Glowzy Pro et le Glowzy", entrees) == "Le Glo-zi Pro et le Glo-zi"


def test_le_projet_l_emporte_sur_le_global():
    projet = [Prononciation("glowzy", "Glaou-zi")]
    assert appliquer("Glowzy", fusionner([GLOWZY], projet)) == "Glaou-zi"


def test_dictionnaire_global_enregistre(tmp_path):
    dictionnaire = DictionnaireGlobal(tmp_path / "prononciations.json")
    dictionnaire.enregistrer([GLOWZY, Prononciation("  ", "x"), Prononciation("Sérum", "")])
    assert DictionnaireGlobal(tmp_path / "prononciations.json").entrees == [GLOWZY]
