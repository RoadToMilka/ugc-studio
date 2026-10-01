"""Estimation de la durée et du coût d'une voix off AVANT de la générer (§5.2).

- Tokens d'entrée : le texte envoyé (environ 1 token pour 4 caractères).
- Durée : d'après le nombre de mots et les pauses. La vitesse de parole part de 2,7 mots par
  seconde, puis elle est mesurée sur tes prises, voix par voix (V2, vitesses.py).
- Tokens de sortie : l'audio produit, proportionnel à sa durée. Le nombre de tokens par seconde
  est ajusté automatiquement après chaque génération, avec les vrais chiffres renvoyés par Google :
  l'estimation devient donc de plus en plus juste.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .balises import MOTIF_BALISE
from .fournisseurs.capacites import TOKENS_AUDIO_PAR_SECONDE
from .fournisseurs.voix import Replique
from .prix import CataloguePrix

CARACTERES_PAR_TOKEN = 4
MOTS_PAR_SECONDE = 2.7  # ≈ 160 mots par minute, débit courant d'une pub UGC
# Valeur de départ : 25 tokens par seconde d'audio, d'après la page des tarifs de Google.
TOKENS_AUDIO_PAR_SECONDE_DEFAUT = float(TOKENS_AUDIO_PAR_SECONDE)
DUREE_BALISES = {"short pause": 0.5, "long pause": 1.2}
DUREE_AUTRE_BALISE = 0.6  # rire, soupir…
POIDS_NOUVELLE_MESURE = 0.3  # part de la dernière génération dans la moyenne ajustée

# Limites du modèle (§5.6 bis) : au-delà, le script est généré en plusieurs morceaux.
TOKENS_ENTREE_MAX = 8_192
TOKENS_SORTIE_MAX = 16_384
MARGE_SECURITE = 0.8


@dataclass(frozen=True)
class Estimation:
    caracteres: int
    duree_s: float
    tokens_entree: int
    tokens_sortie: int
    cout_eur: Decimal | None


def tokens_texte(texte: str) -> int:
    return math.ceil(len(texte) / CARACTERES_PAR_TOKEN) if texte else 0


def duree_des_balises(texte_api: str) -> float:
    """Temps estimé des balises d'un texte (pauses, rires…), en secondes."""
    return sum(
        DUREE_BALISES.get(" ".join(trouve.group(1).lower().split()), DUREE_AUTRE_BALISE)
        for trouve in MOTIF_BALISE.finditer(texte_api)
    )


def mots_dits(texte_api: str) -> int:
    """Nombre de mots dits (les balises ne comptent pas)."""
    return len(re.findall(r"\w+", MOTIF_BALISE.sub(" ", texte_api)))


def duree_parlee(texte_api: str, mots_par_seconde: float = MOTS_PAR_SECONDE) -> float:
    """Durée approximative (s) d'un texte envoyé au TTS, balises comprises.

    `mots_par_seconde` : vitesse de parole de la voix, mesurée sur tes prises (vitesses.py) ;
    2,7 au départ."""
    return duree_des_balises(texte_api) + mots_dits(texte_api) / mots_par_seconde


def estimer(
    texte_api: str,
    style: str,
    modele: str,
    prix: CataloguePrix,
    tokens_par_seconde: float = TOKENS_AUDIO_PAR_SECONDE_DEFAUT,
    mots_par_seconde: float = MOTS_PAR_SECONDE,
) -> Estimation:
    return estimer_repliques([Replique(texte_api, style)], modele, prix, tokens_par_seconde, mots_par_seconde)


def estimer_repliques(
    repliques: Sequence[Replique],
    modele: str,
    prix: CataloguePrix,
    tokens_par_seconde: float = TOKENS_AUDIO_PAR_SECONDE_DEFAUT,
    mots_par_seconde: float = MOTS_PAR_SECONDE,
) -> Estimation:
    """Estimation pour tout le script : chaque réplique envoie son texte et son propre style.
    `mots_par_seconde` : vitesse de la voix choisie, mesurée sur tes prises (V2)."""
    avec_texte = [r for r in repliques if r.texte.strip()]
    duree = sum(duree_parlee(r.texte, mots_par_seconde) for r in avec_texte)
    entree = sum(tokens_texte(r.texte) + tokens_texte(r.style) for r in avec_texte)
    sortie = math.ceil(duree * tokens_par_seconde)
    cout = prix.cout_eur(modele, entree, sortie) if avec_texte else Decimal(0)
    return Estimation(sum(len(r.texte) for r in avec_texte), duree, entree, sortie, cout)


def ajuster_tokens_par_seconde(actuel: float, tokens_sortie: int, duree_s: float) -> float:
    """Moyenne ajustée avec une nouvelle mesure réelle (tokens de sortie ÷ durée de l'audio)."""
    if duree_s <= 0 or tokens_sortie <= 0:
        return actuel
    mesure = tokens_sortie / duree_s
    return (1 - POIDS_NOUVELLE_MESURE) * actuel + POIDS_NOUVELLE_MESURE * mesure


def _trop_long(repliques: Sequence[Replique], tokens_par_seconde: float) -> bool:
    """Ces répliques dépassent-elles les limites d'une seule requête (§5.6 bis) ?"""
    entree = sum(tokens_texte(r.texte) + tokens_texte(r.style) for r in repliques)
    sortie = sum(duree_parlee(r.texte) for r in repliques) * tokens_par_seconde
    return entree > TOKENS_ENTREE_MAX * MARGE_SECURITE or sortie > TOKENS_SORTIE_MAX * MARGE_SECURITE


def regrouper(repliques: Sequence[Replique], tokens_par_seconde: float) -> list[tuple[Replique, ...]]:
    """Répartit les répliques en requêtes qui respectent les limites du modèle.

    Les répliques voisines partent ensemble tant qu'elles tiennent dans une requête. Une réplique
    trop longue à elle seule est découpée aux fins de phrases, chaque morceau gardant son style.
    """
    groupes: list[tuple[Replique, ...]] = []
    courant: list[Replique] = []
    for replique in repliques:
        if not replique.texte.strip():
            continue
        for morceau in decouper_si_trop_long(replique.texte, tokens_par_seconde):
            element = Replique(morceau, replique.style)
            if courant and _trop_long([*courant, element], tokens_par_seconde):
                groupes.append(tuple(courant))
                courant = []
            courant.append(element)
    if courant:
        groupes.append(tuple(courant))
    return groupes


def decouper_si_trop_long(texte_api: str, tokens_par_seconde: float) -> list[str]:
    """Découpe un texte trop long pour une seule requête en morceaux, aux fins de phrases (§5.6 bis)."""

    def trop_long(texte: str) -> bool:
        return _trop_long([Replique(texte)], tokens_par_seconde)

    if not trop_long(texte_api):
        return [texte_api]
    phrases = re.findall(r"[^.!?…\n]+(?:[.!?…]+|\n+|$)", texte_api)
    morceaux: list[str] = []
    courant = ""
    for phrase in phrases:
        if courant and trop_long(courant + phrase):
            morceaux.append(courant.strip())
            courant = ""
        courant += phrase
    if courant.strip():
        morceaux.append(courant.strip())
    return morceaux
