"""Variantes A/B (§5.6) : réglages par variante, différences, coût total, séries de prises."""

from decimal import Decimal

import pytest

from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.generation import enregistrer_prise, preparer
from ugc_studio.fournisseurs.voix import ResultatVoix
from ugc_studio.projets import RepliqueProjet
from ugc_studio.variantes import (
    MODELE,
    STYLE,
    TEXTE,
    VARIANTES_MAX,
    VOIX,
    ReglagesVariante,
    champs_differents,
    cout_total,
    differences,
    memes_reglages,
    reglages,
)

SCRIPT_1 = [{"texte": "Franchement, je n'y croyais pas… "}, {"balise": "short pause"}]
SCRIPT_2 = [{"texte": "Le lien est juste en dessous."}]


def _base() -> ReglagesVariante:
    return ReglagesVariante(
        "gemini-3.8-flash-tts",
        "Kore",
        [RepliqueProjet(SCRIPT_1, "excited", "enthousiaste"), RepliqueProjet(SCRIPT_2, "calm")],
    )


def test_reglages_dans_l_ordre_du_tableau():
    assert reglages(_base()) == [(MODELE, -1), (VOIX, -1), (STYLE, 0), (TEXTE, 0), (STYLE, 1), (TEXTE, 1)]


def test_differences_avec_la_base():
    base = _base()
    variante = base.copie()
    assert differences(base, variante) == set()
    variante.voix = "Puck"
    variante.repliques[1].style = "warm"
    variante.repliques[0].script.append({"balise": "laugh"})  # une balise en plus
    assert differences(base, variante) == {(VOIX, -1), (STYLE, 1), (TEXTE, 0)}
    # La copie est indépendante : la base n'a pas bougé.
    assert base.repliques[0].script == SCRIPT_1 and base.repliques[1].style == "calm"


def test_espaces_et_morceaux_de_texte_ne_comptent_pas():
    base = _base()
    variante = base.copie()
    variante.repliques[0].style = "  excited "
    # Même texte découpé autrement : pas de différence.
    variante.repliques[1].script = [{"texte": "Le lien est "}, {"texte": "juste en dessous."}]
    assert differences(base, variante) == set()


def test_mode_memes_reglages():
    variantes = memes_reglages(_base(), 3)
    assert len(variantes) == 3
    assert all(differences(_base(), v) == set() for v in variantes)
    assert variantes[0].repliques[0] is not variantes[1].repliques[0]
    assert len(memes_reglages(_base(), 99)) == VARIANTES_MAX
    assert len(memes_reglages(_base(), 1)) == 2


def test_cout_total_des_variantes(services):
    base = _base()
    lite = base.copie()
    lite.modele = "gemini-3.8-flash-lite-tts"
    seul = cout_total([base], services.prix)
    assert seul > 0
    total = cout_total([base, lite], services.prix)
    assert seul < total < 2 * seul  # Flash-Lite coûte moins cher que Flash
    assert cout_total([base, base.copie()], services.prix) == 2 * seul
    inconnu = base.copie()
    inconnu.modele = "modele-sans-prix"
    assert cout_total([base, inconnu], services.prix) is None


def _generer(services, base: ReglagesVariante, serie: int, lettre: str):
    commande = preparer("google", base.modele, base.voix, base.repliques, "Sérum")
    wav = wav_depuis_pcm(b"\x00\x00" * 2400)
    return enregistrer_prise(services, commande, ResultatVoix(wav, 0.1, 10, 20), serie=serie, variante=lettre)


def test_serie_de_prises(services, tmp_path):
    services.projets.creer("Sérum", tmp_path)
    projets = services.projets
    assert projets.nouvelle_serie() == 1
    base = _base()
    puck = base.copie()
    puck.voix = "Puck"
    a = _generer(services, base, 1, "A")
    b = _generer(services, puck, 1, "B")
    assert (a.nom, b.nom) == ("Prise 1 (variante A)", "Prise 2 (variante B)")
    assert projets.nouvelle_serie() == 2
    assert [p.variante for p in projets.serie(1)] == ["A", "B"]
    assert projets.serie(0) == []
    # Seule la voix change dans la série : c'est elle qu'on compare.
    assert champs_differents(projets.serie(1)) == [(VOIX, -1)]
    # Chaque variante est une prise normale : coût noté, enregistrée avec le projet.
    assert Decimal(a.cout_eur) > 0 and len(services.couts.lire()) == 2

    projets.retenir(b.identifiant)
    assert [p.retenue for p in projets.serie(1)] == [False, True]
    projets.retenir(a.identifiant)  # une seule variante retenue par série
    assert [p.retenue for p in projets.serie(1)] == [True, False]
    projets.retenir(a.identifiant)  # recliquer la retire
    assert [p.retenue for p in projets.serie(1)] == [False, False]

    # Rouvrir le projet garde la série, les lettres et le choix.
    projets.retenir(b.identifiant)
    dossier = projets.projet.dossier
    projets.ouvrir(dossier)
    assert [(p.serie, p.variante, p.retenue) for p in projets.projet.prises] == [(1, "A", False), (1, "B", True)]


def test_serie_memes_reglages_sans_difference(services, tmp_path):
    services.projets.creer("Sérum", tmp_path)
    for lettre in "ABC":
        _generer(services, _base(), 1, lettre)
    assert champs_differents(services.projets.serie(1)) == []


@pytest.mark.parametrize("modification", ["style", "texte"])
def test_differences_de_replique_dans_une_serie(services, tmp_path, modification):
    services.projets.creer("Sérum", tmp_path)
    base = _base()
    autre = base.copie()
    if modification == "style":
        autre.repliques[0].style = "whispering"
    else:
        autre.repliques[1].script = [{"texte": "Clique sur le lien !"}]
    _generer(services, base, 1, "A")
    _generer(services, autre, 1, "B")
    attendu = (STYLE, 0) if modification == "style" else (TEXTE, 1)
    assert champs_differents(services.projets.serie(1)) == [attendu]

