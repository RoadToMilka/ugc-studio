"""File de vidéos à agrandir avec Topaz (V4, lot 3 ; cahier des charges §8 bis.3) : chaque vidéo est
lue (taille telle qu'on la voit, durée, son), reçoit sa taille finale et son nom, puis passe dans le
FFmpeg de Topaz avec la commande du préréglage. Une vidéo après l'autre : c'est la carte graphique qui
fait le travail, et elle n'en fait bien qu'un à la fois.

Les vidéos d'origine ne sont jamais modifiées. Le fichier en cours d'écriture porte un nom provisoire
(« Sérum (upscale).en-cours.mp4 »), renommé à la fin, effacé si le travail échoue ou s'arrête.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..dossiers import fichiers_du_dossier
from ..exports.ffmpeg import Processus, analyser
from .commande import Prereglage, taille_finale
from .installation import Topaz

SUFFIXE = " (upscale)"
EXTENSION_PROVISOIRE = ".en-cours"
EXTENSIONS_VIDEOS = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts", ".wmv")
PERIODE_S = 0.25  # l'avancement est relu 4 fois par seconde
LIGNES_D_ERREUR = 3  # dernières lignes de Topaz montrées en cas d'échec


@dataclass(frozen=True)
class Video:
    """Une vidéo de la file, telle que FFmpeg la lit (`erreur` : illisible)."""

    source: Path
    largeur: int = 0  # telle qu'on la voit (redressée)
    hauteur: int = 0
    duree_s: float = 0.0
    son: bool = False
    erreur: str = ""


def lire_la_video(source: Path, ffmpeg: Path | None = None) -> Video:
    """Taille (redressée : une vidéo enregistrée « couchée » avec une consigne de rotation est vue
    debout), durée et son, lus par le FFmpeg de l'app."""
    analyse = analyser(source, ffmpeg)
    if analyse is None or analyse.images is None:
        return Video(source, erreur="Pas d'image lisible dans ce fichier.")
    largeur, hauteur = analyse.taille_affichee
    return Video(source, largeur, hauteur, float(analyse.images.duree), analyse.son is not None)


def videos_du_dossier(dossier: Path) -> list[Path]:
    return fichiers_du_dossier(dossier, EXTENSIONS_VIDEOS)


def nom_de_sortie(source: Path, dossier: Path, extension: str, deja_pris: set[Path] | None = None) -> Path:
    """« Sérum (upscale).mp4 » dans `dossier` ; « Sérum (upscale) (2).mp4 » si ce nom est déjà pris
    (un fichier existant, ou une autre vidéo de la même file) : aucun fichier n'est écrasé."""
    deja_pris = deja_pris or set()
    base = f"{source.stem}{SUFFIXE}"
    candidat = dossier / f"{base}{extension}"
    numero = 2
    while candidat.exists() or candidat in deja_pris:
        candidat = dossier / f"{base} ({numero}){extension}"
        numero += 1
    return candidat


def chemin_provisoire(destination: Path) -> Path:
    return destination.with_name(f"{destination.stem}{EXTENSION_PROVISOIRE}{destination.suffix}")


@dataclass(frozen=True)
class Travail:
    """Une vidéo à agrandir : sa taille finale et le fichier à écrire."""

    video: Video
    finale: tuple[int, int]
    destination: Path


def planifier(videos: Sequence[Video], petit_cote: int, extension: str, dossier_sortie: Path | None = None) -> list[Travail]:
    """Les travaux de la file (les vidéos illisibles en sont exclues) : chaque vidéo à sa taille finale
    (voir taille_finale), dans `dossier_sortie` ou, sans lui, dans son propre dossier."""
    travaux: list[Travail] = []
    pris: set[Path] = set()
    for video in videos:
        if video.erreur or not video.largeur or not video.hauteur:
            continue
        destination = nom_de_sortie(video.source, dossier_sortie or video.source.parent, extension, pris)
        pris.add(destination)
        travaux.append(Travail(video, taille_finale(video.largeur, video.hauteur, petit_cote), destination))
    return travaux


@dataclass(frozen=True)
class Avancement:
    rang: int  # la vidéo en cours (0 : la première)
    total: int
    fraction: float  # de la vidéo en cours, de 0 à 1
    ecoule_s: float  # depuis le début de cette vidéo


@dataclass(frozen=True)
class Resultat:
    travail: Travail
    duree_s: float = 0.0
    erreur: str = ""
    arrete: bool = False

    @property
    def reussi(self) -> bool:
        return not self.erreur and not self.arrete


def _effacer(chemin: Path) -> None:
    with contextlib.suppress(OSError):
        chemin.unlink()


def upscaler(
    travaux: Sequence[Travail],
    prereglage: Prereglage,
    topaz: Topaz,
    progres: Callable[[Avancement], None],
    arret: threading.Event,
) -> list[Resultat]:
    """Passe chaque vidéo dans le FFmpeg de Topaz, l'une après l'autre. `progres` reçoit l'avancement
    (4 fois par seconde) ; « Arrêter » (`arret`) arrête Topaz tout de suite, efface le fichier
    inachevé, et les vidéos suivantes ne sont pas commencées. Une vidéo en échec n'arrête pas la file."""
    resultats: list[Resultat] = []
    for rang, travail in enumerate(travaux):
        if arret.is_set():
            break
        provisoire = chemin_provisoire(travail.destination)
        _effacer(provisoire)  # reste d'un travail interrompu (coupure de courant…)
        largeur, hauteur = travail.finale
        arguments = [*topaz.programme, *prereglage.arguments(str(travail.video.source), str(provisoire), largeur, hauteur)]
        debut = time.monotonic()
        try:
            processus = Processus(arguments, avec_images=False, environnement=topaz.environnement())
        except OSError as erreur:
            resultats.append(Resultat(travail, erreur=f"Impossible de lancer Topaz : {erreur}"))
            continue
        while not processus.termine():
            if arret.is_set():
                processus.arreter()
                _effacer(provisoire)
                resultats.append(Resultat(travail, time.monotonic() - debut, arrete=True))
                return resultats
            duree = travail.video.duree_s
            fraction = min(1.0, processus.nouvelles.temps_s / duree) if duree > 0 else 0.0
            progres(Avancement(rang, len(travaux), fraction, time.monotonic() - debut))
            time.sleep(PERIODE_S)
        code = processus.attendre(30)
        duree_s = time.monotonic() - debut
        if code == 0 and provisoire.is_file() and provisoire.stat().st_size > 0:
            try:
                os.replace(provisoire, travail.destination)
            except OSError as erreur:
                _effacer(provisoire)
                resultats.append(Resultat(travail, duree_s, erreur=f"Impossible d'enregistrer la vidéo : {erreur}"))
                continue
            progres(Avancement(rang, len(travaux), 1.0, duree_s))
            resultats.append(Resultat(travail, duree_s))
        else:
            _effacer(provisoire)
            lignes = [ligne for ligne in processus.erreurs() if ligne.strip()][-LIGNES_D_ERREUR:]
            resultats.append(Resultat(travail, duree_s, erreur="\n".join(lignes) or f"Topaz s'est arrêté (code {code})."))
    return resultats


def duree_lisible(secondes: float) -> str:
    """« 45 s », « 3 min 12 s », « 1 h 05 min »."""
    secondes = round(secondes)
    if secondes < 60:
        return f"{secondes} s"
    minutes, secondes = divmod(secondes, 60)
    if minutes < 60:
        return f"{minutes} min {secondes:02d} s"
    heures, minutes = divmod(minutes, 60)
    return f"{heures} h {minutes:02d} min"
