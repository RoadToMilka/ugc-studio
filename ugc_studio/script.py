"""Le script d'une voix off, sous forme de « segments ».

Un segment est soit du texte, soit une balise :
    {"texte": "Salut ! "}
    {"balise": "laugh"}
    {"texte": "incroyable", "accentue": True}     ← mot mis en valeur (bouton « Accentuer »)

Pourquoi ce découpage ? Le même script sert à deux choses différentes :
- le texte envoyé au TTS : balises écrites « <laugh> », mots accentués en MAJUSCULES
  (le modèle appuie sur les mots en capitales, §5.2) ;
- le texte des sous-titres : sans balises et avec la casse d'origine (§7.2).
"""

from __future__ import annotations

import re

from .balises import MOTIF_BALISE_SAISIE, balise_depuis_nom, nom_affiche

Segment = dict


def normaliser(segments: list[Segment]) -> list[Segment]:
    """Fusionne les morceaux de texte voisins de même nature et retire les segments vides."""
    resultat: list[Segment] = []
    for segment in segments:
        if "balise" in segment:
            resultat.append({"balise": segment["balise"]})
            continue
        texte = segment.get("texte", "")
        if not texte:
            continue
        accentue = bool(segment.get("accentue"))
        precedent = resultat[-1] if resultat else None
        if precedent is not None and "texte" in precedent and bool(precedent.get("accentue")) == accentue:
            precedent["texte"] += texte
        else:
            resultat.append({"texte": texte, "accentue": True} if accentue else {"texte": texte})
    return resultat


def depuis_texte(texte: str) -> list[Segment]:
    """Texte brut (ex. collé depuis ailleurs) → segments ; les balises connues deviennent des badges.

    Une balise peut être écrite en anglais (« <laugh> ») ou en français (« <rire> ») : le segment
    garde toujours le nom anglais, celui qui est envoyé à Google."""
    segments: list[Segment] = []
    position = 0
    for trouve in MOTIF_BALISE_SAISIE.finditer(texte):
        balise = balise_depuis_nom(trouve.group(1))
        if balise is None:
            continue  # « <truc> » inconnu : laissé tel quel dans le texte
        segments.append({"texte": texte[position : trouve.start()]})
        segments.append({"balise": balise})
        position = trouve.end()
    segments.append({"texte": texte[position:]})
    return normaliser(segments)


def _texte(segments: list[Segment], nom_de_balise) -> str:
    morceaux = []
    for segment in segments:
        if "balise" in segment:
            morceaux.append(f"<{nom_de_balise(segment['balise'])}>")
        elif segment.get("accentue"):
            morceaux.append(segment["texte"].upper())
        else:
            morceaux.append(segment["texte"])
    return "".join(morceaux)


def texte_pour_api(segments: list[Segment]) -> str:
    """Texte exact envoyé au TTS : balises entre chevrons (noms anglais), mots accentués en majuscules."""
    return _texte(segments, lambda balise: balise)


def texte_pour_affichage(segments: list[Segment]) -> str:
    """Même texte que pour l'API, mais avec le nom français des balises (« <rire> ») : pour
    afficher un script sur une ligne de texte simple, là où il n'y a pas de badges."""
    return _texte(segments, nom_affiche)


def texte_brut(segments: list[Segment]) -> str:
    """Texte pour les sous-titres et l'alignement : sans balises, casse d'origine."""
    texte = "".join(s.get("texte", "") for s in segments if "balise" not in s)
    return re.sub(r"[ \t]{2,}", " ", texte).strip()


def est_vide(segments: list[Segment]) -> bool:
    return not texte_brut(segments) and not any("balise" in s for s in segments)


def joindre_repliques(scripts: list[list[Segment]]) -> list[Segment]:
    """Script complet à partir des répliques : bout à bout, séparées par une espace.

    ex. [« …en deux semaines ! »] + [« Le lien est en dessous. »] → « …en deux semaines ! Le lien… »
    """
    resultat: list[Segment] = []
    for segments in scripts:
        if est_vide(segments):
            continue
        if resultat:
            resultat.append({"texte": " "})
        resultat.extend(dict(s) for s in segments)
    return normaliser(resultat)


def couper(segments: list[Segment], position: int) -> tuple[list[Segment], list[Segment]]:
    """Coupe un script en deux à une position (en caractères ; un badge compte pour 1).

    Sert à « Découper ici » : la fin d'une réplique devient une nouvelle réplique.
    """
    avant: list[Segment] = []
    apres: list[Segment] = []
    restant = position
    for segment in segments:
        if "balise" in segment:
            (avant if restant > 0 else apres).append(dict(segment))
            restant -= 1
            continue
        texte = segment.get("texte", "")
        coupe = max(0, min(len(texte), restant))
        for morceau, cible in ((texte[:coupe], avant), (texte[coupe:], apres)):
            if morceau:
                cible.append({**segment, "texte": morceau})
        restant -= len(texte)
    return _rogner(normaliser(avant), fin=True), _rogner(normaliser(apres), fin=False)


def _rogner(segments: list[Segment], fin: bool) -> list[Segment]:
    """Retire les espaces laissés à l'endroit de la coupe (fin du 1er morceau, début du 2e)."""
    if not segments:
        return segments
    index = -1 if fin else 0
    if "texte" in segments[index]:
        texte = segments[index]["texte"].rstrip() if fin else segments[index]["texte"].lstrip()
        if texte:
            segments[index] = {**segments[index], "texte": texte}
        else:
            segments.pop(index)
    return segments
