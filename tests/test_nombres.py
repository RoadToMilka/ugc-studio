"""Nombres dits à la belge ou à la suisse (V2, lot 2) : seul le texte envoyé à la voix change."""

from pathlib import Path

import pytest

from ugc_studio.generation import preparer, repliques_api
from ugc_studio.nombres import BELGIQUE, FRANCE, SUISSE, VARIANTE_DE_LANGUE, appliquer, differe, en_lettres
from ugc_studio.projets import Projet, ReglagesVoix, RepliqueProjet


@pytest.mark.parametrize(
    ("nombre", "france", "belgique", "suisse"),
    [
        (21, "vingt et un", "vingt et un", "vingt et un"),
        (70, "soixante-dix", "septante", "septante"),
        (71, "soixante et onze", "septante et un", "septante et un"),
        (77, "soixante-dix-sept", "septante-sept", "septante-sept"),
        (80, "quatre-vingts", "quatre-vingts", "huitante"),
        (81, "quatre-vingt-un", "quatre-vingt-un", "huitante et un"),
        (90, "quatre-vingt-dix", "nonante", "nonante"),
        (91, "quatre-vingt-onze", "nonante et un", "nonante et un"),
        (99, "quatre-vingt-dix-neuf", "nonante-neuf", "nonante-neuf"),
        (200, "deux cents", "deux cents", "deux cents"),
        (280, "deux cent quatre-vingts", "deux cent quatre-vingts", "deux cent huitante"),
        (1290, "mille deux cent quatre-vingt-dix", "mille deux cent nonante", "mille deux cent nonante"),
        (80_000, "quatre-vingt mille", "quatre-vingt mille", "huitante mille"),
        (2_000_000, "deux millions", "deux millions", "deux millions"),
    ],
)
def test_en_lettres(nombre, france, belgique, suisse):
    assert (en_lettres(nombre), en_lettres(nombre, BELGIQUE), en_lettres(nombre, SUISSE)) == (france, belgique, suisse)


def test_seuls_les_nombres_qui_se_lisent_autrement_changent():
    assert differe(75, BELGIQUE) and differe(1990, BELGIQUE) and differe(85, SUISSE)
    assert not differe(45, BELGIQUE) and not differe(85, BELGIQUE) and not differe(75, FRANCE)
    with pytest.raises(ValueError):
        en_lettres(-1)


def test_texte_envoye_a_la_voix():
    texte = (
        "Elle est à 29,90 €, recharge à 90 % en 1 heure. Code GLOW20, 4,7/5 sur 1 280 avis, 79 € au lieu de 99 €. "
        "<laugh> 14:30, 1990, 0,95, appelle le 0470 12 34 56"
    )
    belge = appliquer(texte, BELGIQUE)
    assert belge == (
        "Elle est à vingt-neuf euros nonante, recharge à nonante pour cent en 1 heure. Code GLOW20, 4,7/5 sur 1 280 "
        "avis, septante-neuf euros au lieu de nonante-neuf euros. <laugh> 14:30, mille neuf cent nonante, zéro "
        "virgule nonante-cinq, appelle le 0470 12 34 56"
    )
    assert "sur mille deux cent huitante avis" in appliquer(texte, SUISSE)  # 80 : huitante à la suisse
    assert appliquer(texte, FRANCE) == texte
    assert appliquer("Elle coûte 79 CHF.", SUISSE) == "Elle coûte septante-neuf francs."
    assert appliquer("3,99 euros, 1.290 €, 97€ et 71,5 %", BELGIQUE) == (
        "trois euros nonante-neuf, mille deux cent nonante euros, nonante-sept euros et septante et un virgule cinq pour cent"
    )


def test_balises_jamais_modifiees():
    assert appliquer("<pause 90> 90 fois <laugh>", BELGIQUE) == "<pause 90> nonante fois <laugh>"


def test_variante_proposee_d_apres_la_langue_du_script():
    assert VARIANTE_DE_LANGUE == {"fr-BE": BELGIQUE, "fr-CH": SUISSE}


def test_dans_le_texte_envoye_au_tts_seulement(tmp_path):
    """Le script (et donc les sous-titres) garde les chiffres ; le texte envoyé à Google change."""
    repliques = [RepliqueProjet([{"texte": "Seulement 79 € au lieu de 99 € !"}])]
    assert repliques_api(repliques, (), BELGIQUE)[0].texte == "Seulement septante-neuf euros au lieu de nonante-neuf euros !"
    commande = preparer("google", "gemini-3.8-flash-tts", "Kore", repliques, "Pub", (), SUISSE)
    assert "septante-neuf euros" in commande.texte_api
    assert commande.script == [{"texte": "Seulement 79 € au lieu de 99 € !"}]
    assert repliques_api(repliques)[0].texte == "Seulement 79 € au lieu de 99 € !"


def test_reglage_du_projet():
    assert ReglagesVoix().nombres == FRANCE
    assert ReglagesVoix(nombres="xx").nombres == FRANCE  # valeur inconnue : à la française
    projet = Projet.depuis_dict(Path("x"), {"nom": "P", "voix": {"modele": "m", "voix": "Kore", "nombres": "be"}})
    assert projet.voix.nombres == BELGIQUE and projet.en_dict()["voix"]["nombres"] == "be"
