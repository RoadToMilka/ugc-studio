"""Affichage des montants (§4.4) : « 0.00 » + « 71 » + « € »."""

from decimal import Decimal

import pytest

from ugc_studio.montants import decouper_montant, en_decimal, formater_montant


@pytest.mark.parametrize(
    ("valeur", "attendu"),
    [
        (0, ("0.00", "00")),
        (0.0071, ("0.00", "71")),
        (0.007, ("0.00", "70")),
        ("0.0123", ("0.01", "23")),
        (1.23456, ("1.23", "46")),  # arrondi « au plus proche », 5 vers le haut
        (Decimal("1.23455"), ("1.23", "46")),
        (12.5, ("12.50", "00")),
        (0.09999, ("0.10", "00")),
        (Decimal("0.00005"), ("0.00", "01")),
        (1234.5678, ("1234.56", "78")),
    ],
)
def test_quatre_decimales(valeur, attendu):
    assert decouper_montant(valeur) == attendu


def test_petit_montant_non_nul_jamais_affiche_zero():
    # 0.000042 € s'afficherait « 0.0000 € » : on ajoute des décimales jusqu'au premier chiffre utile.
    assert decouper_montant(0.000042) == ("0.00", "004")
    assert decouper_montant(Decimal("0.0000049")) == ("0.00", "0005")


def test_montant_infime_reste_a_zero():
    assert decouper_montant(0.0000001) == ("0.00", "00")


def test_pas_de_zero_negatif():
    assert decouper_montant(Decimal("-0.0000001")) == ("0.00", "00")


def test_texte_complet():
    assert formater_montant(0.0071) == "0.0071\u00a0€"
    assert formater_montant(0.288) == "0.2880\u00a0€"


@pytest.mark.parametrize("valeur", [float("nan"), float("inf"), "abc"])
def test_montant_invalide(valeur):
    with pytest.raises(ValueError):
        en_decimal(valeur)


def test_decimal_exact():
    # Avec des nombres à virgule classiques, 0.1 + 0.2 = 0.30000000000000004.
    assert en_decimal(0.1) + en_decimal(0.2) == Decimal("0.3")
