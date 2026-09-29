"""Mise en forme des montants en euros (cahier des charges §4.4).

Format : « 0.000 € », avec 3 décimales minimum. À l'écran, la partie entière et la
1re décimale sont en taille normale, les décimales suivantes en plus petit :
0.007 € s'affiche « 0.0 » + « 07 » + « € ».

Si un montant non nul s'afficherait « 0.000 » (ex. 0.0004 €, le prix d'un essai de voix),
on ajoute des décimales jusqu'au premier chiffre utile (6 au maximum) : « 0.0 » + « 004 ».
Ainsi un coût réel n'apparaît jamais comme gratuit.

Les calculs utilisent le type Decimal (nombres décimaux exacts) : avec les nombres à
virgule classiques, 0.1 + 0.2 donne 0.30000000000000004, ce qui fausserait les totaux.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

DECIMALES_MIN = 3
DECIMALES_MAX = 6

Montant = Decimal | float | int | str


def en_decimal(valeur: Montant) -> Decimal:
    """Convertit un nombre en Decimal (en passant par son écriture décimale pour les floats)."""
    if isinstance(valeur, Decimal):
        resultat = valeur
    else:
        try:
            resultat = Decimal(str(valeur))
        except InvalidOperation as erreur:
            raise ValueError(f"Montant invalide : {valeur!r}") from erreur
    if not resultat.is_finite():
        raise ValueError(f"Montant invalide : {valeur!r}")
    return resultat


def _arrondir(valeur: Decimal, decimales: int) -> Decimal:
    return valeur.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def nombre_de_decimales(valeur: Decimal) -> int:
    """3 décimales, ou plus (6 max) si un montant non nul s'afficherait « 0.000 »."""
    if valeur == 0 or _arrondir(abs(valeur), DECIMALES_MIN) != 0:
        return DECIMALES_MIN
    for decimales in range(DECIMALES_MIN + 1, DECIMALES_MAX + 1):
        if _arrondir(abs(valeur), decimales) != 0:
            return decimales
    return DECIMALES_MIN  # trop petit pour être visible : affiché 0.000


def decouper_montant(valeur: Montant) -> tuple[str, str]:
    """(partie en taille normale, petites décimales) — ex. 0.007 → ("0.0", "07")."""
    montant = en_decimal(valeur)
    arrondi = _arrondir(montant, nombre_de_decimales(montant))
    if arrondi == 0:
        arrondi = abs(arrondi)  # évite d'afficher « -0.000 »
    entier, decimales = f"{arrondi:f}".split(".")
    return f"{entier}.{decimales[0]}", decimales[1:]


def formater_montant(valeur: Montant) -> str:
    """Texte simple du montant, ex. « 0.007 € » (espace insécable avant €)."""
    principal, petites = decouper_montant(valeur)
    return f"{principal}{petites} €"
