"""Variantes de script (V2, lot 2, §10.9) : plusieurs scripts du même produit en un seul lancement.

Trois façons de faire (onglets de la fenêtre « Variantes de script ») :
- « Mêmes réglages » (MEMES) : 2 à 6 scripts du même brief, chacun sur une accroche différente.
  Le modèle propose d'abord autant d'accroches, sur des angles différents (une seule demande, peu
  coûteuse), puis il écrit un script complet par accroche : les scripts diffèrent vraiment.
- « Réglages par variante » (PAR_VARIANTE) : un tableau, une colonne par variante. Chaque variante
  part du brief et ne change que ce qu'on veut comparer : angle, accroche imposée, durée, réseau,
  personne qui parle, profil, consigne libre, modèle. Les valeurs modifiées sont surlignées en mauve.
- « Accroches seulement » (ACCROCHES) : un seul script est écrit et relu, puis le modèle propose
  d'autres accroches pour sa réplique 1 ; chaque variante garde exactement le même corps. Elles
  s'envoient ensemble dans le module Voix, en variantes A/B de voix.

Les scripts écrits ensemble forment une « série » : même identifiant de série, une lettre chacun
(A, B…), comme les prises d'une série de variantes du module Voix. Ce module ne dépend pas de
l'interface : il est testé seul.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, fields
from decimal import Decimal

from ..estimation import MOTS_PAR_SECONDE
from ..prix import CataloguePrix
from .brief import ANGLES, DUREE_MAX, DUREE_MIN, GENRES, RESEAUX, Brief
from .exemples import ExempleScript
from .redaction import Estimation, estimer_accroches, estimer_accroches_pour_corps, estimer_script

MEMES = "memes"
PAR_VARIANTE = "par_variante"
ACCROCHES = "accroches"
MODES = {MEMES: "Mêmes réglages", PAR_VARIANTE: "Réglages par variante", ACCROCHES: "Accroches seulement"}

LETTRES = "ABCDEF"
VARIANTES_MIN = 2
VARIANTES_MAX = len(LETTRES)
VARIANTES_PAR_DEFAUT = 3
ACCROCHE_TYPIQUE = 60  # caractères d'une accroche, pour estimer un script avant de connaître son accroche

# Ce qu'une variante peut changer (« Réglages par variante »), dans l'ordre du tableau.
REGLAGES = {
    "angle": "Angle",
    "accroche": "Accroche imposée",
    "duree_s": "Durée",
    "reseau": "Réseau",
    "genre": "Personne qui parle",
    "profil": "Profil",
    "consigne": "Consigne libre",
    "modele": "Modèle",
}


@dataclass
class ReglagesScript:
    """Réglages d'une variante de script ; au départ, ceux du brief du projet."""

    angle: str = "auto"
    accroche: str = ""  # accroche imposée (facultatif) : la réplique 1, mot pour mot
    duree_s: int = 0  # 0 : durée conseillée pour le réseau
    reseau: str = "tiktok"
    genre: str = ""
    profil: str = ""
    consigne: str = ""
    modele: str = ""

    @classmethod
    def depuis_brief(cls, brief: Brief) -> ReglagesScript:
        return cls(
            angle=brief.angle,
            duree_s=brief.duree_s,
            reseau=brief.reseau,
            genre=brief.genre,
            profil=brief.profil,
            consigne=brief.consigne,
            modele=brief.modele,
        )

    def copie(self) -> ReglagesScript:
        return ReglagesScript(**{champ.name: getattr(self, champ.name) for champ in fields(self)})

    def valeur(self, nom: str) -> object:
        """Valeur comparable d'un réglage (les textes sans espaces en trop)."""
        valeur = getattr(self, nom)
        return " ".join(valeur.split()) if isinstance(valeur, str) else valeur

    def brief(self, base: Brief) -> Brief:
        """Le brief de cette variante : celui du projet, avec les valeurs de la variante."""
        brief = Brief.depuis_dict(base.en_dict())
        brief.angle = self.angle if self.angle in ANGLES else base.angle
        valide = self.duree_s == 0 or DUREE_MIN <= self.duree_s <= DUREE_MAX
        brief.duree_s = self.duree_s if valide else base.duree_s
        brief.reseau = self.reseau if self.reseau in RESEAUX else base.reseau
        if self.genre != base.genre and self.genre in GENRES:
            brief.genre = self.genre
            brief.modifie_a_la_main("genre")
        brief.profil = self.profil.strip()
        brief.consigne = self.consigne.strip()
        brief.modele = self.modele or base.modele
        return brief


def differences(base: ReglagesScript, variante: ReglagesScript) -> set[str]:
    """Réglages de la variante qui diffèrent de la base (surlignés en mauve dans le tableau)."""
    return {nom for nom in REGLAGES if variante.valeur(nom) != base.valeur(nom)}


def nouvelle_serie() -> str:
    """Identifiant d'une nouvelle série de scripts."""
    return "serie-" + uuid.uuid4().hex[:8]


def _cout(prix: CataloguePrix, modele: str, estimation: Estimation) -> Decimal | None:
    return prix.cout_eur(modele, estimation.tokens_entree, estimation.tokens_sortie)


def cout_estime(
    mode: str,
    brief: Brief,
    page: str,
    exemples: list[ExempleScript],
    prix: CataloguePrix,
    nombre: int = VARIANTES_PAR_DEFAUT,
    variantes: Sequence[ReglagesScript] = (),
    mots_par_seconde: float = MOTS_PAR_SECONDE,
) -> Decimal | None:
    """Coût total estimé d'une série, avant de la lancer (None si le prix d'un modèle est inconnu).

    - Mêmes réglages : les accroches (une demande), puis `nombre` scripts écrits et relus ;
    - Réglages par variante : un script écrit et relu par variante, chacun avec son modèle ;
    - Accroches seulement : un script écrit et relu, puis les autres accroches (une demande)."""
    if mode == PAR_VARIANTE:
        total = Decimal(0)
        for variante in variantes:
            brief_variante = variante.brief(brief)
            estimation = estimer_script(brief_variante, page, exemples, variante.accroche, mots_par_seconde)
            cout = _cout(prix, brief_variante.modele, estimation)
            if cout is None:
                return None
            total += cout
        return total
    if mode == MEMES:
        accroches = estimer_accroches(brief, page, exemples, nombre, une_par_angle=True)
        script = estimer_script(brief, page, exemples, "x" * ACCROCHE_TYPIQUE, mots_par_seconde)
        total = Estimation(
            accroches.tokens_entree + nombre * script.tokens_entree,
            accroches.tokens_sortie + nombre * script.tokens_sortie,
        )
        return _cout(prix, brief.modele, total)
    estimation = estimer_script(brief, page, exemples, "", mots_par_seconde) + estimer_accroches_pour_corps(
        brief, page, nombre - 1
    )
    return _cout(prix, brief.modele, estimation)
