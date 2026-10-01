"""Relecture par l'app (V2, §10.8) : tout ce qui se compte est vérifié ici, exactement et gratuitement.

- durée estimée (même formule et même vitesse de parole que le module Voix, balises comprises) :
  à ± 10 % de la cible, sinon ⚠ ; au-delà de 15 %, point grave (le modèle corrige le script avant
  de te le montrer) ;
- mots interdits absents, mentions obligatoires présentes (points graves) ;
- balises connues de l'app, un mot accentué au plus par réplique (retraits signalés) ;
- styles de jeu courts et en anglais : mêmes vérifications que dans le module Voix (§5.5).
Le reste (accroche, langage parlé, règles publicitaires…) demande un jugement : le modèle le relit
(consignes.py).
"""

from __future__ import annotations

import re
import unicodedata

from ..conseils import verifier_style
from ..estimation import MOTS_PAR_SECONDE
from ..script import texte_brut
from .brief import Brief
from .scripts import PointRelecture, ScriptEcrit

ECART_LEGER = 0.10  # ± 10 % de la durée visée : ok
ECART_GRAVE = 0.15  # au-delà de 15 % : corrigé par le modèle


def _simplifier(texte: str) -> str:
    """Sans accents ni majuscules, espaces réduits : « Garanti À Vie » → « garanti a vie »."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode("ascii")
    return " ".join(sans_accents.casefold().split())


def _texte_complet(script: ScriptEcrit) -> str:
    return " ".join(texte_brut(r.script) for r in script.repliques)


def controle_duree(script: ScriptEcrit, mots_par_seconde: float = MOTS_PAR_SECONDE) -> PointRelecture:
    estimee, visee = script.duree_estimee(mots_par_seconde), script.duree_visee_s
    if visee <= 0:
        return PointRelecture("duree", "ok", f"≈ {round(estimee)} s")
    ecart = (estimee - visee) / visee
    message = f"≈ {round(estimee)} s pour {visee} visées"
    if abs(ecart) <= ECART_LEGER:
        return PointRelecture("duree", "ok", message)
    sens = "trop long" if ecart > 0 else "trop court"
    gravite = "grave" if abs(ecart) > ECART_GRAVE else "leger"
    return PointRelecture("duree", gravite, f"{message} : {sens} de {round(abs(ecart) * 100)} %")


def mots_interdits_presents(script: ScriptEcrit, brief: Brief) -> list[str]:
    texte = _simplifier(_texte_complet(script))
    presents = []
    for mot in brief.liste_mots_interdits():
        motif = r"(?<!\w)" + re.escape(_simplifier(mot)) + r"(?!\w)"
        if re.search(motif, texte):
            presents.append(mot)
    return presents


def mentions_absentes(script: ScriptEcrit, brief: Brief) -> list[str]:
    texte = " ".join(_texte_complet(script).casefold().split())
    return [m for m in brief.liste_mentions() if " ".join(m.casefold().split()) not in texte]


def controler(
    script: ScriptEcrit,
    brief: Brief,
    retraits: list[str] | None = None,
    mots_par_seconde: float = MOTS_PAR_SECONDE,
) -> list[PointRelecture]:
    """Points de relecture vérifiés par l'app. `retraits` : ce que la conversion du texte du modèle a
    retiré (balise inconnue, accent en trop…) ; `mots_par_seconde` : vitesse de la voix du projet,
    mesurée sur tes prises (vitesses.py)."""
    points = [controle_duree(script, mots_par_seconde)]
    interdits = mots_interdits_presents(script, brief)
    if brief.liste_mots_interdits():
        if interdits:
            points.append(
                PointRelecture("mots_interdits", "grave", "Mot interdit présent : " + ", ".join(f"« {m} »" for m in interdits))
            )
        else:
            points.append(PointRelecture("mots_interdits", "ok", "Aucun mot interdit"))
    if brief.liste_mentions():
        absentes = mentions_absentes(script, brief)
        if absentes:
            points.append(
                PointRelecture(
                    "mentions", "grave", "Mention obligatoire absente : " + ", ".join(f"« {m} »" for m in absentes)
                )
            )
        else:
            points.append(PointRelecture("mentions", "ok", "Mentions obligatoires présentes"))
    for retrait in retraits or []:
        points.append(PointRelecture("balises", "leger", retrait))
    for rang, replique in enumerate(script.repliques, start=1):
        if replique.style:
            for avertissement in verifier_style(replique.style):
                points.append(PointRelecture("styles", "leger", f"Style de la réplique {rang} : {avertissement.message}"))
        accents = sum(1 for s in replique.script if s.get("accentue"))
        if accents > 1:
            points.append(PointRelecture("accents", "leger", f"Réplique {rang} : {accents} mots accentués (un seul conseillé)"))
    if script.accroche_imposee and script.repliques:
        premiere = _simplifier(texte_brut(script.repliques[0].script))
        if _simplifier(script.accroche_imposee) not in premiere:
            points.append(PointRelecture("accroche", "leger", "La réplique 1 diffère de l'accroche choisie"))
    return points


def points_graves(points: list[PointRelecture]) -> list[PointRelecture]:
    return [p for p in points if p.gravite == "grave"]
