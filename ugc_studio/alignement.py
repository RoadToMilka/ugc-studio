"""Prise TTS → sous-titres (§3.3) : caler le script d'origine sur les temps de la transcription.

Le TTS ne donne pas le moment de chaque mot. La prise est donc transcrite (STT), puis le texte
transcrit est **aligné sur le script**, connu exactement : les sous-titres gardent l'orthographe
du script (noms de marque, ponctuation, majuscules d'origine) et prennent les temps de la
transcription.

Méthode : les deux suites de mots sont comparées (sans majuscules, accents ni ponctuation), comme
le fait un outil de comparaison de textes :
- mot identique des deux côtés → il prend les temps du mot transcrit ;
- mots différents (ex. « 2 » écrit, « deux » transcrit) → le passage transcrit est partagé entre
  les mots du script, selon leur longueur ;
- mot du script absent de la transcription → il prend place dans le silence entre ses voisins
  (juste avant le premier mot, ou juste après le dernier ; s'il n'y a pas de silence, il
  partage le temps d'un voisin) ;
- mot transcrit absent du script (rire transcrit, hésitation…) → ignoré.

Mots accentués (V2, lot 5) : les mots mis en valeur dans le script d'une prise (bouton
« Accentuer » du module Voix, dits en MAJUSCULES à la voix) sont retrouvés dans les mots des
sous-titres, pour l'état « Accentués » de l'onglet Mots (marquer_les_accentues).

Ce module ne dépend pas de l'interface : il est testé seul.
"""

from __future__ import annotations

import unicodedata
from dataclasses import replace
from difflib import SequenceMatcher

from .transcription import DUREE_MOT_MIN, PONCTUATION, Mot

OUVRANTES = "«“‘„([{¿¡"  # ponctuation qui s'accroche au mot suivant
DUREE_PAR_LETTRE = 0.07  # secondes : débit d'une voix off (≈ 14 lettres par seconde)


def cle_d_alignement(texte: str) -> str:
    """Forme comparable d'un mot : minuscules, sans accents ni ponctuation (« N'y » → « ny »)."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", texte.casefold()) if not unicodedata.combining(c)
    )
    return "".join(c for c in sans_accents if c.isalnum())


def _ponctuation_seule(texte: str) -> bool:
    return bool(texte) and all(c in PONCTUATION for c in texte)


def mots_du_script(texte: str) -> list[str]:
    """Mots du texte, tels qu'ils seront affichés. Une ponctuation isolée ne reste jamais seule :
    « semaines ! » forme un seul mot, et « « Salut » aussi (la ponctuation ouvrante va avec le mot
    suivant)."""
    mots: list[str] = []
    en_attente = ""  # ponctuation ouvrante, en attente du mot suivant
    for morceau in texte.split():
        if _ponctuation_seule(morceau) and all(c in OUVRANTES for c in morceau):
            en_attente += morceau + " "
            continue
        if _ponctuation_seule(morceau) and mots and not en_attente:
            mots[-1] = f"{mots[-1]} {morceau}"
            continue
        mots.append(en_attente + morceau)
        en_attente = ""
    if en_attente:  # ponctuation ouvrante tout à la fin : avec le dernier mot
        if mots:
            mots[-1] = f"{mots[-1]} {en_attente.strip()}"
        else:
            mots.append(en_attente.strip())
    return mots


def _repartir(textes: list[str], debut: float, fin: float) -> list[tuple[float, float]]:
    """Partage [debut, fin] entre des mots, selon leur longueur (au moins 20 ms chacun)."""
    if not textes:
        return []
    fin = max(fin, debut + DUREE_MOT_MIN * len(textes))
    poids = [max(1, len(cle_d_alignement(t))) for t in textes]
    total = sum(poids)
    temps, curseur = [], debut
    for p in poids:
        suivant = curseur + (fin - debut) * p / total
        temps.append((curseur, suivant))
        curseur = suivant
    return temps


def aligner(textes_script: list[str], transcrits: list[Mot]) -> list[Mot]:
    """Mots du script, avec les temps des mots transcrits correspondants (liste vide si la
    transcription ne contient aucun mot)."""
    if not transcrits or not textes_script:
        return []
    cles_script = [cle_d_alignement(t) for t in textes_script]
    cles_transcrits = [cle_d_alignement(m.texte) for m in transcrits]
    resultat: list[Mot | None] = [None] * len(textes_script)
    comparaison = SequenceMatcher(None, cles_script, cles_transcrits, autojunk=False)
    for operation, i1, i2, j1, j2 in comparaison.get_opcodes():
        if operation == "equal":
            for decalage in range(i2 - i1):
                source = transcrits[j1 + decalage]
                resultat[i1 + decalage] = Mot(textes_script[i1 + decalage], source.debut, source.fin, source.locuteur)
        elif operation == "replace":
            debut, fin = transcrits[j1].debut, transcrits[j2 - 1].fin
            for index, (d, f) in zip(range(i1, i2), _repartir(textes_script[i1:i2], debut, fin), strict=True):
                resultat[index] = Mot(textes_script[index], d, f, transcrits[j1].locuteur)
    _placer_les_mots_manquants(textes_script, transcrits, resultat)
    return _sans_chevauchement([m for m in resultat if m is not None])


def _placer_les_mots_manquants(textes: list[str], transcrits: list[Mot], resultat: list[Mot | None]) -> None:
    """Mots du script absents de la transcription : dans le silence entre leurs voisins, ou, sans
    silence, en partageant le temps d'un voisin (celui d'avant, sinon celui d'après)."""
    index = 0
    while index < len(resultat):
        if resultat[index] is not None:
            index += 1
            continue
        fin_trou = index
        while fin_trou < len(resultat) and resultat[fin_trou] is None:
            fin_trou += 1
        precedent = resultat[index - 1] if index > 0 else None
        suivant = resultat[fin_trou] if fin_trou < len(resultat) else None
        # Au début ou à la fin : juste avant le premier mot (ou après le dernier), le temps qu'il
        # faut pour les dire, plutôt que tout le silence du début ou de la fin.
        naturelle = DUREE_PAR_LETTRE * sum(max(1, len(cle_d_alignement(t))) for t in textes[index:fin_trou])
        if precedent is not None and suivant is not None:
            avant, apres = precedent.fin, suivant.debut
        elif suivant is not None:
            apres = suivant.debut
            avant = max(0.0, apres - naturelle)
        elif precedent is not None:
            avant = precedent.fin
            apres = avant + naturelle
        else:
            avant, apres = transcrits[0].debut, transcrits[-1].fin
        locuteur = (precedent or suivant or transcrits[0]).locuteur
        premier, dernier = index, fin_trou
        if apres - avant < DUREE_MOT_MIN * (fin_trou - index):  # pas de silence : un voisin partage
            if precedent is not None:
                premier, avant = index - 1, precedent.debut
            elif suivant is not None:
                dernier, apres = fin_trou + 1, suivant.fin
        temps = _repartir(textes[premier:dernier], avant, apres)
        for position, (d, f) in zip(range(premier, dernier), temps, strict=True):
            resultat[position] = Mot(textes[position], d, f, locuteur)
        index = dernier


def _sans_chevauchement(mots: list[Mot]) -> list[Mot]:
    """Temps toujours croissants : un mot ne commence jamais avant la fin du précédent."""
    for precedent, mot in zip(mots, mots[1:], strict=False):
        if mot.debut < precedent.fin:
            mot.debut = precedent.fin
        if mot.fin < mot.debut + DUREE_MOT_MIN:
            mot.fin = mot.debut + DUREE_MOT_MIN
    for mot in mots:
        mot.debut, mot.fin = round(mot.debut, 3), round(mot.fin, 3)
    return mots


# --- Mots accentués du script (V2, lot 5) --------------------------------------------------------


def mots_du_script_accentues(segments: list[dict]) -> list[tuple[str, bool]]:
    """Mots du script (les mêmes que mots_du_script(texte_brut(segments)), dans l'ordre), avec pour
    chacun s'il est accentué : une de ses lettres vient d'un passage accentué du script."""
    caracteres = [
        (caractere, bool(segment.get("accentue")))
        for segment in segments
        if "balise" not in segment
        for caractere in segment.get("texte", "")
    ]
    jetons: list[tuple[str, bool]] = []
    courant, accentue = "", False
    for caractere, dans_l_accent in [*caracteres, (" ", False)]:
        if caractere.isspace():
            if courant:
                jetons.append((courant, accentue))
            courant, accentue = "", False
        else:
            courant += caractere
            accentue = accentue or (dans_l_accent and caractere.isalnum())
    mots: list[tuple[str, bool]] = []
    en_attente = ""
    for morceau, accentue in jetons:  # même regroupement de la ponctuation que mots_du_script
        if _ponctuation_seule(morceau) and all(c in OUVRANTES for c in morceau):
            en_attente += morceau + " "
            continue
        if _ponctuation_seule(morceau) and mots and not en_attente:
            texte, deja = mots[-1]
            mots[-1] = (f"{texte} {morceau}", deja or accentue)
            continue
        mots.append((en_attente + morceau, accentue))
        en_attente = ""
    if en_attente:
        if mots:
            texte, deja = mots[-1]
            mots[-1] = (f"{texte} {en_attente.strip()}", deja)
        else:
            mots.append((en_attente.strip(), False))
    return mots


def marquer_les_accentues(mots: list[Mot], segments: list[dict]) -> list[Mot]:
    """Copie des mots (ceux d'une prise, alignés sur son script), avec `accentue` pour ceux qui
    sont accentués dans le script. Les mots sont retrouvés par la même comparaison que
    l'alignement : un mot corrigé depuis dans le module Transcription n'est plus reconnu (il
    s'affiche comme les autres)."""
    script = mots_du_script_accentues(segments)
    resultat = [replace(mot, accentue=False) for mot in mots]
    if not any(accentue for _texte, accentue in script):
        return resultat
    cles_script = [cle_d_alignement(texte) for texte, _accentue in script]
    cles_mots = [cle_d_alignement(mot.texte) for mot in mots]
    comparaison = SequenceMatcher(None, cles_script, cles_mots, autojunk=False)
    for operation, i1, i2, j1, _j2 in comparaison.get_opcodes():
        if operation != "equal":
            continue
        for decalage in range(i2 - i1):
            if script[i1 + decalage][1]:
                resultat[j1 + decalage] = replace(resultat[j1 + decalage], accentue=True)
    return resultat
