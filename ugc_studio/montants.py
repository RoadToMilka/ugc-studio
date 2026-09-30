"""Mise en forme des montants en euros (cahier des charges §4.4).

Format : « 0.0000 € », avec 4 décimales minimum. À l'écran, la partie entière et les
2 premières décimales sont en taille et couleur normales ; les décimales suivantes (3e et 4e)
sont plus petites et plus sombres, pour ne pas attirer l'œil :
0.0071 € s'affiche « 0.00 » + « 71 » + « € ».

Si un montant non nul s'afficherait « 0.0000 » (ex. 0.00004 €), on ajoute des décimales
jusqu'au premier chiffre utile (6 au maximum) : « 0.00 » + « 004 ».
Ainsi un coût réel n'apparaît jamais comme gratuit.

Les calculs utilisent le type Decimal (nombres décimaux exacts) : avec les nombres à
virgule classiques, 0.1 + 0.2 donne 0.30000000000000004, ce qui fausserait les totaux.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

DECIMALES_MIN = 4
DECIMALES_MAX = 6
DECIMALES_NORMALES = 2  # 1re et 2e décimales : taille et couleur normales

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
    """4 décimales, ou plus (6 max) si un montant non nul s'afficherait « 0.0000 »."""
    if valeur == 0 or _arrondir(abs(valeur), DECIMALES_MIN) != 0:
        return DECIMALES_MIN
    for decimales in range(DECIMALES_MIN + 1, DECIMALES_MAX + 1):
        if _arrondir(abs(valeur), decimales) != 0:
            return decimales
    return DECIMALES_MIN  # trop petit pour être visible : affiché 0.0000


def decouper_montant(valeur: Montant) -> tuple[str, str]:
    """(partie normale, petites décimales) — ex. 0.0071 → ("0.00", "71")."""
    montant = en_decimal(valeur)
    arrondi = _arrondir(montant, nombre_de_decimales(montant))
    if arrondi == 0:
        arrondi = abs(arrondi)  # évite d'afficher « -0.0000 »
    entier, decimales = f"{arrondi:f}".split(".")
    return f"{entier}.{decimales[:DECIMALES_NORMALES]}", decimales[DECIMALES_NORMALES:]


def formater_montant(valeur: Montant) -> str:
    """Texte simple du montant, ex. « 0.0071 € » (espace insécable avant €)."""
    principal, petites = decouper_montant(valeur)
    return f"{principal}{petites}\u00a0€"


def nombre_lisible(nombre: int) -> str:
    """1234567 → « 1 234 567 » : milliers séparés par une espace fine insécable, à la française
    (elle ne coupe jamais un nombre en fin de ligne)."""
    return f"{nombre:,}".replace(",", "\u202f")
