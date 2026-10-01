"""Textes affichés par le module Script (V2) : dates, ordre de la liste des scripts, origine d'un
script, points de relecture. Sans interface : testés seuls, et partagés par la page Script et ses
fenêtres (« Comparer les scripts », « Bibliothèque de briefs »…)."""

from __future__ import annotations

from datetime import datetime

from .brief import ANGLES
from .consignes import CRITERES
from .scripts import PointRelecture, ScriptEcrit
from .variantes import MODES


def date_lisible(iso: str) -> str:
    """« aujourd'hui à 14:32 », « hier à 09:05 » ou « le 28/09/2026 à 18:10 »."""
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    jours = (datetime.now(moment.tzinfo).date() - moment.date()).days
    heure = moment.strftime("%H:%M")
    if jours == 0:
        return f"aujourd'hui à {heure}"
    if jours == 1:
        return f"hier à {heure}"
    return f"le {moment:%d/%m/%Y} à {heure}"


def nom_angle(angle: str) -> str:
    """« Témoignage » ; vide pour un angle inconnu ou laissé au choix du modèle."""
    return ANGLES.get(angle, "") if angle and angle != "auto" else ""


def texte_du_point(point: PointRelecture) -> str:
    """« Langage parlé naturel : une phrase un peu longue. » (le critère, puis l'explication)."""
    if point.par == "modele":
        critere = CRITERES.get(point.critere, point.critere)
        return f"{critere} : {point.explication}" if point.explication else critere
    return point.explication


def ordre_d_affichage(scripts: list[ScriptEcrit]) -> list[ScriptEcrit]:
    """Du plus récent au plus ancien ; les scripts d'une même série restent ensemble (A, B, C…)."""
    groupes: list[list[ScriptEcrit]] = []
    rang_de_serie: dict[str, int] = {}
    for script in scripts:
        if script.serie and script.serie in rang_de_serie:
            groupes[rang_de_serie[script.serie]].append(script)
            continue
        if script.serie:
            rang_de_serie[script.serie] = len(groupes)
        groupes.append([script])
    return [s for groupe in reversed(groupes) for s in sorted(groupe, key=lambda s: s.lettre)]


def _minuscule(nom: str) -> str:
    """« Script 3 » → « script 3 » (dans une phrase)."""
    return nom[:1].lower() + nom[1:]


def texte_d_origine(script: ScriptEcrit, scripts: list[ScriptEcrit]) -> str:
    """Place du script dans sa série (« Série « Accroches seulement » : variante B sur 3 ») et ce dont
    il vient (« Retouche du script 3 : « plus court » », « Copie du script 3 »)."""
    morceaux = []
    if script.serie:
        serie = [s for s in scripts if s.serie == script.serie]
        mode = MODES.get(script.mode, "Variantes")
        morceaux.append(f"Série « {mode} » : variante {script.lettre} sur {len(serie)}")
    if script.origine:
        source = next((s for s in scripts if s.identifiant == script.origine), None)
        de = f"du {_minuscule(source.nom())}" if source is not None else "d'un script supprimé"
        if script.consigne_retouche:
            morceaux.append(f"Retouche {de} : « {script.consigne_retouche} »")
        else:
            morceaux.append(f"Copie {de}")
    return "  ·  ".join(morceaux)


def titre_de_retouche(script: ScriptEcrit) -> str:
    """« Retoucher le script 3 » (titre de la fenêtre de retouche)."""
    return f"Retoucher le {_minuscule(script.nom())}"
