"""Sous-titres importés d'un fichier SRT (V3.1, lot 6 ; cahier des charges §7.14).

Un fichier SRT (Premiere Pro, CapCut…) donne le texte et le moment de chaque sous-titre, pas celui
de chaque mot. L'app l'estime : la durée d'un sous-titre est partagée entre ses mots selon leur
longueur (chaque mot compte ses lettres, plus une pour l'espace qui le suit : un « à » n'est pas
réduit à rien). C'est gratuit et immédiat. Ensuite, le découpage de l'app s'applique comme pour une
transcription : seuls les mots du fichier et leurs moments comptent, pas sa façon de couper.

Pour un mot actif parfaitement calé sur une vidéo, c'est le module Transcription : il mesure le
moment de chaque mot dans le son (décision de l'utilisateur du 02/10/2026 : pas d'option qui ferait
doublon avec lui).

Lecture tolérante : UTF-8 (avec ou sans BOM) ou Windows-1252, fins de ligne Windows ou Unix,
numéros absents ou faux, virgule ou point avant les millisecondes, balises de mise en forme
(<i>, <b>, <font…>, {\\an8}) retirées, sous-titres qui se chevauchent remis bout à bout.

Ce module ne dépend pas de l'interface : il est testé seul.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .transcription import MODE_VERBATIM, PONCTUATION, Mot, Transcription

EXTENSION = ".srt"
FILTRE = "Sous-titres SRT (*.srt)"
_TEMPS = r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
_LIGNE_DE_TEMPS = re.compile(rf"^\s*{_TEMPS}\s*-->\s*{_TEMPS}")
_BALISES = re.compile(r"<[^>]*>|\{\\[^}]*\}")


class ErreurSrt(ValueError):
    """Fichier SRT illisible : le message dit pourquoi, en clair."""


@dataclass(frozen=True)
class EntreeSrt:
    debut: float  # secondes
    fin: float
    texte: str  # ses lignes, réunies par une espace


def decoder(octets: bytes) -> str:
    """Le texte du fichier : UTF-8 (avec ou sans BOM), sinon Windows-1252 (anciens logiciels)."""
    try:
        return octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        return octets.decode("cp1252", errors="replace")


def _secondes(heures: str, minutes: str, secondes: str, millisecondes: str) -> float:
    # « 5 » après la virgule : 500 ms (une fraction de seconde, comme « 0,5 »).
    return int(heures) * 3600 + int(minutes) * 60 + int(secondes) + int(millisecondes.ljust(3, "0")) / 1000


def lire_srt(texte: str) -> list[EntreeSrt]:
    """Les sous-titres d'un fichier SRT, dans l'ordre du temps. Un sous-titre sans texte, ou qui ne
    dure rien, est ignoré ; un sous-titre qui commence avant la fin du précédent commence à sa fin."""
    lignes = texte.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    brutes: list[EntreeSrt] = []
    index = 0
    while index < len(lignes):
        temps = _LIGNE_DE_TEMPS.match(lignes[index])
        index += 1
        if temps is None:
            continue
        valeurs = temps.groups()
        debut, fin = _secondes(*valeurs[:4]), _secondes(*valeurs[4:])
        texte_du_sous_titre: list[str] = []
        while index < len(lignes) and lignes[index].strip() and not _LIGNE_DE_TEMPS.match(lignes[index]):
            suivante = lignes[index + 1] if index + 1 < len(lignes) else ""
            if lignes[index].strip().isdigit() and _LIGNE_DE_TEMPS.match(suivante):
                break  # numéro du sous-titre suivant (ligne vide oubliée entre les deux)
            texte_du_sous_titre.append(_BALISES.sub("", lignes[index]))
            index += 1
        mots = " ".join(texte_du_sous_titre).split()
        if mots and fin > debut:
            brutes.append(EntreeSrt(debut, fin, " ".join(mots)))
    brutes.sort(key=lambda entree: entree.debut)
    entrees: list[EntreeSrt] = []
    for entree in brutes:
        debut = max(entree.debut, entrees[-1].fin) if entrees else entree.debut
        if entree.fin > debut:
            entrees.append(EntreeSrt(round(debut, 3), entree.fin, entree.texte))
    return entrees


def mots_estimes(entrees: list[EntreeSrt]) -> list[Mot]:
    """Le moment de chaque mot, estimé : la durée de chaque sous-titre partagée entre ses mots selon
    leur longueur. Le premier mot commence avec le sous-titre, le dernier finit avec lui."""
    mots: list[Mot] = []
    for entree in entrees:
        morceaux = entree.texte.split()
        poids = [len(morceau.strip(PONCTUATION)) + 1 for morceau in morceaux]
        total = sum(poids)
        duree = entree.fin - entree.debut
        cumul = 0
        for morceau, part in zip(morceaux, poids, strict=True):
            debut = entree.debut + duree * cumul / total
            cumul += part
            fin = entree.fin if cumul == total else entree.debut + duree * cumul / total
            mots.append(Mot(morceau, round(debut, 3), round(fin, 3)))
    return mots


def transcription_depuis_srt(chemin: Path, langue: str) -> Transcription:
    """Les mots d'un fichier SRT, comme une transcription (sans son : le fichier n'en a pas).
    ErreurSrt si le fichier ne contient aucun sous-titre lisible."""
    try:
        texte = decoder(chemin.read_bytes())
    except OSError as erreur:
        raise ErreurSrt(f"Fichier illisible : {erreur}") from erreur
    entrees = lire_srt(texte)
    if not entrees:
        raise ErreurSrt("Aucun sous-titre lisible dans ce fichier : est-ce bien un fichier SRT ?")
    mots = mots_estimes(entrees)
    return Transcription(
        source=str(chemin),
        duree_s=entrees[-1].fin,
        infos={"srt": True, "video": False, "sous_titres": len(entrees)},
        langue=langue,
        mode=MODE_VERBATIM,
        texte=" ".join(entree.texte for entree in entrees),
        mots=mots,
        date=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def est_srt(transcription: Transcription | None) -> bool:
    """Ces mots viennent-ils d'un fichier SRT (moments estimés) ?"""
    return transcription is not None and bool((transcription.infos or {}).get("srt"))
