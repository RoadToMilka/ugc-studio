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

from .balises import MOTIF_BALISE, est_balise

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
    """Texte brut (ex. collé depuis ailleurs) → segments ; les balises connues deviennent des badges."""
    segments: list[Segment] = []
    position = 0
    for trouve in MOTIF_BALISE.finditer(texte):
        nom = " ".join(trouve.group(1).lower().split())
        if not est_balise(nom):
            continue  # « <truc> » inconnu : laissé tel quel dans le texte
        segments.append({"texte": texte[position : trouve.start()]})
        segments.append({"balise": nom})
        position = trouve.end()
    segments.append({"texte": texte[position:]})
    return normaliser(segments)


def texte_pour_api(segments: list[Segment]) -> str:
    """Texte exact envoyé au TTS : balises entre chevrons, mots accentués en majuscules."""
    morceaux = []
    for segment in segments:
        if "balise" in segment:
            morceaux.append(f"<{segment['balise']}>")
        elif segment.get("accentue"):
            morceaux.append(segment["texte"].upper())
        else:
            morceaux.append(segment["texte"])
    return "".join(morceaux)


def texte_brut(segments: list[Segment]) -> str:
    """Texte pour les sous-titres et l'alignement : sans balises, casse d'origine."""
    texte = "".join(s.get("texte", "") for s in segments if "balise" not in s)
    return re.sub(r"[ \t]{2,}", " ", texte).strip()


def est_vide(segments: list[Segment]) -> bool:
    return not texte_brut(segments) and not any("balise" in s for s in segments)
