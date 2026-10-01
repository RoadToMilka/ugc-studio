"""Nombres dits à la belge ou à la suisse (V2, lot 2, §16 du document V2).

La voix dit « septante », « nonante » (et « huitante » à la suisse) ; les sous-titres gardent les
chiffres. Même principe que le dictionnaire de prononciation : seul le texte envoyé à la voix
change, le script affiché et les sous-titres gardent « 29,90 € » et « 90 % ».

Seuls les nombres dont la lecture diffère de celle de France sont écrits en toutes lettres
(70 à 79 et 90 à 99, plus 80 à 89 à la suisse, y compris dans 170, 1 290 ou 1990) : les autres
restent en chiffres, la voix les lit déjà bien. Un prix est écrit en entier, dans l'ordre où on le
dit (« 29,90 € » → « vingt-neuf euros nonante ») ; un nombre collé à des lettres (un code promo
comme « GLOW20 »), une heure (« 14:30 ») ou un numéro qui commence par 0 ne change jamais.

« À la belge » vaut aussi pour Genève, Neuchâtel et le Jura, où l'on dit « quatre-vingts » ;
« huitante » se dit dans les cantons de Vaud, du Valais et de Fribourg.
"""

from __future__ import annotations

import re

FRANCE = "fr"
BELGIQUE = "be"
SUISSE = "ch"
VARIANTES = {
    FRANCE: "À la française",
    BELGIQUE: "À la belge (septante, nonante)",
    SUISSE: "À la suisse (septante, huitante, nonante)",
}
# Variante proposée d'après la langue d'écriture d'un script (module Script).
VARIANTE_DE_LANGUE = {"fr-BE": BELGIQUE, "fr-CH": SUISSE}

_UNITES = (
    "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
    "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf",
)
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
NOMBRE_MAX = 999_999_999_999


def _moins_de_cent(nombre: int, variante: str) -> str:
    if nombre < 20:
        return _UNITES[nombre]
    dizaine, unite = divmod(nombre, 10)
    if dizaine == 7 and variante != FRANCE:
        base = "septante"
    elif dizaine == 9 and variante != FRANCE:
        base = "nonante"
    elif dizaine == 8 and variante == SUISSE:
        base = "huitante"
    elif dizaine == 7:  # France : soixante-dix, soixante et onze…
        return "soixante et onze" if unite == 1 else f"soixante-{_UNITES[10 + unite]}"
    elif dizaine == 9:  # France (et Belgique pour 80) : quatre-vingt-dix…
        return f"quatre-vingt-{_UNITES[10 + unite]}"
    elif dizaine == 8:
        return "quatre-vingts" if unite == 0 else f"quatre-vingt-{_UNITES[unite]}"
    else:
        base = _DIZAINES[dizaine]
    if unite == 0:
        return base
    if unite == 1:
        return f"{base} et un"
    return f"{base}-{_UNITES[unite]}"


def _moins_de_mille(nombre: int, variante: str, final: bool = True) -> str:
    """`final` : rien ne suit (« deux cents », « quatre-vingts ») ; sinon « deux cent mille »."""
    centaines, reste = divmod(nombre, 100)
    morceaux = []
    if centaines:
        if centaines == 1:
            morceaux.append("cent")
        else:
            morceaux.append(f"{_UNITES[centaines]} cent{'s' if reste == 0 and final else ''}")
    if reste or not centaines:
        texte = _moins_de_cent(reste, variante)
        if not final and texte == "quatre-vingts":
            texte = "quatre-vingt"  # « quatre-vingt mille »
        morceaux.append(texte)
    return " ".join(morceaux)


def en_lettres(nombre: int, variante: str = FRANCE) -> str:
    """Nombre entier (0 à 999 999 999 999) écrit en toutes lettres, à la française, à la belge ou à
    la suisse : 1290 → « mille deux cent nonante » (à la belge)."""
    if not 0 <= nombre <= NOMBRE_MAX:
        raise ValueError("Nombre hors des limites")
    if nombre < 1000:
        return _moins_de_mille(nombre, variante)
    morceaux = []
    for valeur, nom in ((1_000_000_000, "milliard"), (1_000_000, "million")):
        groupe, nombre = divmod(nombre, valeur)
        if groupe:
            morceaux.append(f"{_moins_de_mille(groupe, variante)} {nom}{'s' if groupe > 1 else ''}")
    milliers, nombre = divmod(nombre, 1000)
    if milliers:
        morceaux.append("mille" if milliers == 1 else f"{_moins_de_mille(milliers, variante, final=False)} mille")
    if nombre:
        morceaux.append(_moins_de_mille(nombre, variante))
    return " ".join(morceaux)


def differe(nombre: int, variante: str) -> bool:
    """La lecture de ce nombre diffère-t-elle de celle de France ?"""
    return variante != FRANCE and 0 <= nombre <= NOMBRE_MAX and en_lettres(nombre, variante) != en_lettres(nombre)


_MONNAIES = {"€": ("euro", "euros"), "eur": ("euro", "euros"), "euro": ("euro", "euros"), "euros": ("euro", "euros"),
             "chf": ("franc", "francs"), "franc": ("franc", "francs"), "francs": ("franc", "francs")}
_ENTIER = r"\d{1,3}(?:[  .]\d{3})+|\d+"  # « 1 280 », « 1.280 » ou « 1280 »
_PRIX = re.compile(
    rf"(?<![\w,.])({_ENTIER})(?:,(\d{{1,2}}))?[  ]?(€|EUR\b|euros?\b|CHF\b|francs?\b)", re.IGNORECASE
)
_POURCENT = re.compile(rf"(?<![\w,.])({_ENTIER})(?:,(\d+))?[  ]?%")
_NOMBRE = re.compile(rf"(?<![\w,.:/])({_ENTIER})(?:,(\d+))?(?![\w:/]|[.,]\d)")
_BALISE = re.compile(r"(<[^<>]*>)")


def _entier(texte: str) -> int:
    return int(re.sub(r"[  .]", "", texte))


def _prix(trouve: re.Match, variante: str) -> str:
    entier, centimes, monnaie = _entier(trouve.group(1)), trouve.group(2), trouve.group(3)
    centimes_valeur = int(centimes.ljust(2, "0")) if centimes else 0
    if not (differe(entier, variante) or (centimes_valeur and differe(centimes_valeur, variante))):
        return trouve.group(0)
    singulier, pluriel = _MONNAIES.get(monnaie.lower(), ("euro", "euros"))
    texte = f"{en_lettres(entier, variante)} {singulier if entier <= 1 else pluriel}"
    if centimes_valeur:
        texte += f" {en_lettres(centimes_valeur, variante)}"
    return texte


def _decimal(entier: str, decimales: str | None, variante: str) -> str | None:
    """Nombre (entier ou décimal) en lettres s'il se lit autrement qu'en France, sinon None.
    Un nombre qui commence par 0 (« 0470 », un numéro de téléphone) se lit chiffre par chiffre :
    il ne change pas."""
    if len(entier) > 1 and entier.startswith("0"):
        return None
    valeur = _entier(entier)
    if not decimales:
        return en_lettres(valeur, variante) if differe(valeur, variante) else None
    apres = int(decimales) if len(decimales) <= 3 else None
    if not (differe(valeur, variante) or (apres is not None and differe(apres, variante))):
        return None
    texte = f"{en_lettres(valeur, variante)} virgule "
    if apres is None or decimales.startswith("0"):
        return texte + " ".join(_UNITES[int(c)] for c in decimales)  # chiffre par chiffre
    return texte + en_lettres(apres, variante)


def appliquer(texte: str, variante: str) -> str:
    """Texte envoyé à la voix, avec les nombres dits à la belge ou à la suisse (balises intactes)."""
    if variante not in (BELGIQUE, SUISSE) or not texte:
        return texte
    morceaux = _BALISE.split(texte)
    for rang, morceau in enumerate(morceaux):
        if rang % 2 == 1:
            continue  # balise : jamais modifiée
        morceau = _PRIX.sub(lambda t: _prix(t, variante), morceau)
        morceau = _POURCENT.sub(
            lambda t: f"{_decimal(t.group(1), t.group(2), variante)} pour cent"
            if _decimal(t.group(1), t.group(2), variante)
            else t.group(0),
            morceau,
        )
        morceau = _NOMBRE.sub(lambda t: _decimal(t.group(1), t.group(2), variante) or t.group(0), morceau)
        morceaux[rang] = morceau
    return "".join(morceaux)
