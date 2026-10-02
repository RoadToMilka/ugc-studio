"""Système de design (§9) : les valeurs du cahier des charges sont bien celles du thème."""

import re

from ugc_studio.ui import theme
from ugc_studio.ui.theme import (
    ESPACEMENTS_AUTORISES,
    RATIO_PETITES_DECIMALES,
    Arrondis,
    Couleurs,
    Dimensions,
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
    # V3.2 : boutons et champs de 32 px, bordure comprise (36 px jusqu'à la 3.1.0) ; les lignes des
    # tableaux restent à 36 px ; le bandeau : 16 px, le bouton du projet, 16 px et la ligne de 1 px.
    assert (Hauteurs.CONTROLE, Hauteurs.PETIT_BOUTON, Hauteurs.LIGNE_TABLEAU) == (32, 28, 36)
    assert Hauteurs.BANDEAU == 65
    assert Typo.FAMILLE == "Inter"
    assert (Typo.LEGENDE, Typo.COURANT, Typo.TITRE_BLOC, Typo.TITRE_PAGE, Typo.GRAND_CHIFFRE) == (12, 14, 16, 20, 24)
    assert RATIO_PETITES_DECIMALES == 0.70


def test_feuille_de_style_complete():
    feuille = theme.feuille_de_style(ICONES_FACTICES)
    assert "$" not in feuille  # toutes les valeurs ont été remplacées
    assert feuille.count("{") == feuille.count("}")
    assert Couleurs.ACCENT in feuille
    assert 'url("C:/c.svg")' in feuille


def test_familles_par_graisse():
    # Sous Windows, le SemiBold d'Inter peut être rangé dans une famille « Inter SemiBold » séparée.
    feuille = theme.feuille_de_style(ICONES_FACTICES, {600: "Inter SemiBold", 500: "Inter Medium"})
    assert 'font-family: "Inter SemiBold";\n    font-weight: 600;' in feuille
    assert 'font-family: "Inter Medium";\n    font-weight: 500;' in feuille
    par_defaut = theme.feuille_de_style(ICONES_FACTICES)
    assert "Inter SemiBold" not in par_defaut


def test_hauteur_des_boutons_32px():
    # Qt compte la hauteur sans la bordure : 30 px + 2 × 1 px = 32 px (§9.4, V3.2).
    feuille = theme.feuille_de_style(ICONES_FACTICES)
    bloc_bouton = re.search(r"QPushButton \{(.*?)\}", feuille, re.S).group(1)
    assert "min-height: 30px" in bloc_bouton
    champs = re.search(r"QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox \{(.*?)\}", feuille, re.S).group(1)
    assert "min-height: 30px" in champs


def test_mesures_v32():
    """V3.2 : 8 px visibles entre le nom d'un champ et le champ (5 px + les 3 px que la police garde sous
    la ligne de base) ; le haut des majuscules d'un titre de bloc à 24 px du bord (20 px + les 4 px que
    la police garde au-dessus) ; l'icône « i » à 8 px de son texte ; sur une case à cocher, 8 px,
    l'icône, 8 px entre la case et son texte."""
    assert Dimensions.ECART_NOM_CHAMP + Dimensions.DESCENTE_LEGENDE == Espacements.S
    assert Espacements.XL - Dimensions.RESERVE_TITRE_BLOC == 20
    assert Dimensions.ECART_INFO == Espacements.S
    feuille = theme.feuille_de_style(ICONES_FACTICES)
    case_avec_aide = re.search(r'QCheckBox\[aide="true"\] \{(.*?)\}', feuille, re.S).group(1)
    assert f"spacing: {2 * Espacements.S + Dimensions.ICONE_INFO}px" in case_avec_aide


def test_rgba():
    assert theme.rgba("#8B5CF6", 1.0) == "rgba(139, 92, 246, 255)"
    assert theme.rgba("#000000", 0.5) == "rgba(0, 0, 0, 128)"
