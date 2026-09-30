"""Variantes A/B (§5.6) : plusieurs versions d'un même script, générées en un seul lancement.

Deux façons de faire :
- « mêmes réglages » : N générations identiques. Le modèle interprète le texte un peu
  différemment à chaque fois : on écoute, puis on garde la meilleure prise ;
- « réglages par variante » : chaque variante part des réglages de base (ceux de l'atelier) et
  ne change que ce qu'on veut comparer : modèle, voix, style ou texte d'une réplique (balises).

Chaque variante devient une prise normale, marquée de sa série (« série 2 ») et de sa lettre
(A, B…). Ce module ne dépend pas de l'interface : il est testé seul.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from .estimation import estimer_repliques
from .generation import repliques_api
from .prix import CataloguePrix
from .projets import Prise, RepliqueProjet
from .prononciation import Prononciation
from .script import normaliser, texte_pour_api

LETTRES = "ABCDEF"
VARIANTES_MIN = 2
VARIANTES_MAX = len(LETTRES)
VARIANTES_PAR_DEFAUT = 3

# Ce qui peut changer d'une variante à l'autre (l'indice de réplique vaut -1 pour modèle et voix).
MODELE = "modele"
VOIX = "voix"
STYLE = "style"
TEXTE = "texte"
Reglage = tuple[str, int]


def copie_replique(replique: RepliqueProjet) -> RepliqueProjet:
    return RepliqueProjet([dict(s) for s in replique.script], replique.style, replique.style_fr)


@dataclass
class ReglagesVariante:
    """Réglages d'une variante : modèle, voix, et chaque réplique (texte et style)."""

    modele: str
    voix: str
    repliques: list[RepliqueProjet] = field(default_factory=list)

    def copie(self) -> ReglagesVariante:
        return ReglagesVariante(self.modele, self.voix, [copie_replique(r) for r in self.repliques])

    def valeur(self, reglage: Reglage) -> object:
        """Valeur comparable d'un réglage (le texte : tel qu'il est envoyé, balises comprises)."""
        nom, indice = reglage
        if nom == MODELE:
            return self.modele
        if nom == VOIX:
            return self.voix
        replique = self.repliques[indice] if 0 <= indice < len(self.repliques) else RepliqueProjet()
        if nom == STYLE:
            return replique.style.strip()
        return texte_pour_api(normaliser([dict(s) for s in replique.script]))


def reglages(base: ReglagesVariante) -> list[Reglage]:
    """Tous les réglages d'une variante, dans l'ordre du tableau (§5.6)."""
    resultat: list[Reglage] = [(MODELE, -1), (VOIX, -1)]
    for indice in range(len(base.repliques)):
        resultat += [(STYLE, indice), (TEXTE, indice)]
    return resultat


def differences(base: ReglagesVariante, variante: ReglagesVariante) -> set[Reglage]:
    """Réglages de la variante qui diffèrent de la base (surlignés en mauve dans le tableau)."""
    return {r for r in reglages(base) if variante.valeur(r) != base.valeur(r)}


def memes_reglages(base: ReglagesVariante, nombre: int) -> list[ReglagesVariante]:
    """Mode « mêmes réglages » : `nombre` copies identiques de la base."""
    nombre = max(VARIANTES_MIN, min(VARIANTES_MAX, nombre))
    return [base.copie() for _ in range(nombre)]


def cout_total(
    variantes: Sequence[ReglagesVariante],
    prix: CataloguePrix,
    prononciations: Sequence[Prononciation] = (),
    tokens_par_seconde=None,
) -> Decimal | None:
    """Coût estimé de toutes les variantes (None si le prix d'un modèle est inconnu).

    `tokens_par_seconde(modele)` : valeur ajustée pour chaque modèle (voir generation.py)."""
    total = Decimal(0)
    for variante in variantes:
        arguments = () if tokens_par_seconde is None else (tokens_par_seconde(variante.modele),)
        estimation = estimer_repliques(repliques_api(variante.repliques, prononciations), variante.modele, prix, *arguments)
        if estimation.cout_eur is None:
            return None
        total += estimation.cout_eur
    return total


# --- Séries de prises (écoute comparative) ------------------------------------------------------


def champs_differents(prises: Sequence[Prise]) -> list[Reglage]:
    """Réglages qui changent d'une prise à l'autre dans une série (pour les afficher côte à côte).

    Une série « mêmes réglages » n'en a aucun : seule l'interprétation du modèle change."""
    if len(prises) < 2:
        return []
    nombre = max(len(p.repliques) for p in prises)
    candidats: list[Reglage] = [(MODELE, -1), (VOIX, -1)]
    for indice in range(nombre):
        candidats += [(STYLE, indice), (TEXTE, indice)]
    return [c for c in candidats if len({valeur_de_prise(p, c) for p in prises}) > 1]


def valeur_de_prise(prise: Prise, reglage: Reglage) -> str:
    nom, indice = reglage
    if nom == MODELE:
        return prise.modele
    if nom == VOIX:
        return prise.voix
    replique = prise.repliques[indice] if 0 <= indice < len(prise.repliques) else {}
    return str(replique.get("style" if nom == STYLE else "texte_api", "")).strip()
