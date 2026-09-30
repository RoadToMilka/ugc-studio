"""Balises (§5.2) : nom français affiché dans l'app, nom anglais envoyé à Google."""

from ugc_studio.balises import FAMILLES, NOMS_FRANCAIS, TOUTES, balise_depuis_nom, info_balise, nom_affiche
from ugc_studio.script import depuis_texte, texte_pour_affichage, texte_pour_api


def test_chaque_balise_a_un_nom_francais_unique():
    assert sum(len(famille.balises) for famille in FAMILLES) == len(TOUTES) == 40
    assert set(NOMS_FRANCAIS) == set(TOUTES)
    noms = list(NOMS_FRANCAIS.values())
    assert len(set(noms)) == len(noms)  # deux balises n'ont jamais le même nom affiché


def test_du_nom_francais_au_nom_anglais_et_retour():
    assert nom_affiche("laugh") == "rire" and nom_affiche("short pause") == "pause courte"
    for balise in TOUTES:
        assert balise_depuis_nom(balise) == balise
        assert balise_depuis_nom(nom_affiche(balise)) == balise
    # Majuscules, accents oubliés et espaces en trop ne gênent pas.
    assert balise_depuis_nom("  Eclats  de RIRE ") == "laughter"
    assert balise_depuis_nom("bâillement") == balise_depuis_nom("baillement") == "yawn"
    assert balise_depuis_nom("truc") is None


def test_infobulle_avec_le_vrai_nom():
    assert info_balise("laugh") == "Envoyé à Google : <laugh>"


def test_balises_francaises_collees_puis_envoyees_en_anglais():
    segments = depuis_texte("Salut ! <rire> Waouh <Éclats de rire> puis <pause courte>, <laugh> et <truc>.")
    assert [s["balise"] for s in segments if "balise" in s] == ["laugh", "laughter", "short pause", "laugh"]
    # Google reçoit toujours les noms anglais (sa documentation le demande) ; « <truc> » reste du texte.
    assert texte_pour_api(segments) == "Salut ! <laugh> Waouh <laughter> puis <short pause>, <laugh> et <truc>."
    # Là où un script s'affiche en texte simple (fenêtre des variantes) : les noms français.
    assert texte_pour_affichage(segments) == (
        "Salut ! <rire> Waouh <éclats de rire> puis <pause courte>, <rire> et <truc>."
    )


def test_un_signe_inferieur_n_est_pas_une_balise():
    assert texte_pour_api(depuis_texte("prix < 20 € et > 10")) == "prix < 20 € et > 10"
