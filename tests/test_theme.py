"""Système de design (§9) : les valeurs du cahier des charges sont bien celles du thème."""

import re

from ugc_studio.ui import theme
from ugc_studio.ui.theme import (
    ESPACEMENTS_AUTORISES,
    RATIO_PETITES_DECIMALES,
    Arrondis,
    Couleurs,
    Espacements,
    Hauteurs,
    Typo,
)

ICONES_FACTICES = {"fleche": "C:/a.svg", "fleche_desactivee": "C:/b.svg", "coche": "C:/c.svg"}


def _valeurs(classe):
    return {nom: valeur for nom, valeur in vars(classe).items() if nom.isupper()}


def test_couleurs_du_cahier_des_charges():
    assert _valeurs(Couleurs) == {
        "FOND": "#0F0F14",
        "SURFACE": "#17171F",
        "SURFACE_ELEVEE": "#1F1F2A",
        "BORDURE": "#2A2A38",
        "ACCENT": "#8B5CF6",
        "ACCENT_SURVOL": "#A78BFA",
        "ACCENT_PRESSE": "#7C3AED",
        "TEXTE": "#F4F4F8",
        "TEXTE_SECONDAIRE": "#A1A1B5",
        "TEXTE_DESACTIVE": "#5C5C70",
        "SUCCES": "#22C55E",
        "AVERTISSEMENT": "#F59E0B",
        "ERREUR": "#EF4444",
    }


def test_espacements_autorises_uniquement():
    assert ESPACEMENTS_AUTORISES == (4, 8, 12, 16, 24, 32)
    assert set(_valeurs(Espacements).values()) == set(ESPACEMENTS_AUTORISES)


def test_arrondis_hauteurs_typo():
    assert (Arrondis.CONTROLE, Arrondis.BLOC) == (8, 12)
    assert (Hauteurs.CONTROLE, Hauteurs.PETIT_BOUTON) == (36, 28)
    assert Typo.FAMILLE == "Inter"
    assert (Typo.LEGENDE, Typo.COURANT, Typo.TITRE_BLOC, Typo.TITRE_PAGE, Typo.GRAND_CHIFFRE) == (12, 14, 16, 20, 24)
    assert RATIO_PETITES_DECIMALES == 0.70


def test_feuille_de_style_complete():
    feuille = theme.feuille_de_style(ICONES_FACTICES)
    assert "$" not in feuille  # toutes les valeurs ont été remplacées
    assert feuille.count("{") == feuille.count("}")
    assert Couleurs.ACCENT in feuille
    assert 'url("C:/c.svg")' in feuille


def test_hauteur_des_boutons_36px():
    # Qt compte la hauteur sans la bordure : 34 px + 2 × 1 px = 36 px (§9.4).
    feuille = theme.feuille_de_style(ICONES_FACTICES)
    bloc_bouton = re.search(r"QPushButton \{(.*?)\}", feuille, re.S).group(1)
    assert "min-height: 34px" in bloc_bouton


def test_rgba():
    assert theme.rgba("#8B5CF6", 1.0) == "rgba(139, 92, 246, 255)"
    assert theme.rgba("#000000", 0.5) == "rgba(0, 0, 0, 128)"
