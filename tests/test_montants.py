"""Affichage des montants (§4.4) : « 0.0 » + « 07 » + « € »."""

from decimal import Decimal

import pytest

from ugc_studio.montants import decouper_montant, en_decimal, formater_montant


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (0, ("0.0", "00")),
        (0.007, ("0.0", "07")),
        ("0.0123", ("0.0", "12")),
        (1.2345, ("1.2", "35")),  # arrondi « au plus proche », 5 vers le haut
        (12.5, ("12.5", "00")),
        (0.0999, ("0.1", "00")),
        (Decimal("0.0005"), ("0.0", "01")),
        (1234.5678, ("1234.5", "68")),
    ],
)
def test_trois_decimales(valeur, attendu):
    assert decouper_montant(valeur) == attendu


def test_petit_montant_non_nul_jamais_affiche_zero():
    # 0.00042 € s'afficherait « 0.000 € » : on ajoute des décimales jusqu'au premier chiffre utile.
    assert decouper_montant(0.00042) == ("0.0", "004")
    assert decouper_montant(Decimal("0.00049")) == ("0.0", "005")


def test_montant_infime_reste_a_zero():
    assert decouper_montant(0.0000001) == ("0.0", "00")


def test_pas_de_zero_negatif():
    assert decouper_montant(Decimal("-0.0000001")) == ("0.0", "00")


def test_texte_complet():
    assert formater_montant(0.007) == "0.007 €"


@pytest.mark.parametrize("valeur", [float("nan"), float("inf"), "abc"])
def test_montant_invalide(valeur):
    with pytest.raises(ValueError):
        en_decimal(valeur)


def test_decimal_exact():
    # Avec des nombres à virgule classiques, 0.1 + 0.2 = 0.30000000000000004.
    assert en_decimal(0.1) + en_decimal(0.2) == Decimal("0.3")
