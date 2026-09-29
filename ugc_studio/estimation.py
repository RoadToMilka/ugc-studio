"""Estimation de la durée et du coût d'une voix off AVANT de la générer (§5.2).

- Tokens d'entrée : le texte envoyé (environ 1 token pour 4 caractères).
- Durée : d'après le nombre de mots (débit parlé d'une pub UGC) et les pauses.
- Tokens de sortie : l'audio produit, proportionnel à sa durée. Le nombre de tokens par seconde
  est ajusté automatiquement après chaque génération, avec les vrais chiffres renvoyés par Google :
  l'estimation devient donc de plus en plus juste.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal

from .balises import MOTIF_BALISE
from .fournisseurs.capacites import TOKENS_AUDIO_PAR_SECONDE
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


def duree_parlee(texte_api: str) -> float:
    """Durée approximative (s) d'un texte envoyé au TTS, balises comprises."""
    duree = 0.0
    for trouve in MOTIF_BALISE.finditer(texte_api):
        duree += DUREE_BALISES.get(" ".join(trouve.group(1).lower().split()), DUREE_AUTRE_BALISE)
    mots = re.findall(r"\w+", MOTIF_BALISE.sub(" ", texte_api))
    return duree + len(mots) / MOTS_PAR_SECONDE


def estimer(
    texte_api: str,
    style: str,
    modele: str,
    prix: CataloguePrix,
    tokens_par_seconde: float = TOKENS_AUDIO_PAR_SECONDE_DEFAUT,
) -> Estimation:
    duree = duree_parlee(texte_api)
    entree = tokens_texte(texte_api) + tokens_texte(style)
    sortie = math.ceil(duree * tokens_par_seconde)
    cout = prix.cout_eur(modele, entree, sortie) if texte_api.strip() else Decimal(0)
    return Estimation(len(texte_api), duree, entree, sortie, cout)


def ajuster_tokens_par_seconde(actuel: float, tokens_sortie: int, duree_s: float) -> float:
    """Moyenne ajustée avec une nouvelle mesure réelle (tokens de sortie ÷ durée de l'audio)."""
    if duree_s <= 0 or tokens_sortie <= 0:
        return actuel
    mesure = tokens_sortie / duree_s
    return (1 - POIDS_NOUVELLE_MESURE) * actuel + POIDS_NOUVELLE_MESURE * mesure


def decouper_si_trop_long(texte_api: str, tokens_par_seconde: float) -> list[str]:
    """Découpe un script trop long pour une seule requête en morceaux, aux fins de phrases (§5.6 bis)."""
    limite_sortie = TOKENS_SORTIE_MAX * MARGE_SECURITE
    limite_entree = TOKENS_ENTREE_MAX * MARGE_SECURITE

    def trop_long(texte: str) -> bool:
        return tokens_texte(texte) > limite_entree or duree_parlee(texte) * tokens_par_seconde > limite_sortie

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
