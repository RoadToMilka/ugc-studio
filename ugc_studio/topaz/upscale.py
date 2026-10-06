"""File de vidéos à agrandir avec Topaz (V4, lot 3 ; cahier des charges §8 bis.3) : chaque vidéo est
lue (taille telle qu'on la voit, durée, son), reçoit sa taille finale et son nom, puis passe dans le
FFmpeg de Topaz avec la commande du préréglage. Une vidéo après l'autre : c'est la carte graphique qui
fait le travail, et elle n'en fait bien qu'un à la fois.

Le nom (4.1.0, demande de l'utilisateur) : un masque, comme dans le module Renommer (mêmes balises,
mêmes règles de Windows : renommage.py), avec deux balises en plus, `%res%` (« 1080p ») et `%preset%`
(le nom du préréglage). Au départ `%name% (upscale)%ext%` : « Sérum (upscale).mp4 », le nom d'avant.

Les vidéos d'origine ne sont jamais modifiées. Le fichier en cours d'écriture porte un nom provisoire
(« Sérum (upscale).en-cours.mp4 »), renommé à la fin, effacé si le travail échoue ou s'arrête.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..dossiers import fichiers_du_dossier
from ..exports.ffmpeg import Processus, analyser
from ..renommage import (
    LONGUEUR_CHEMIN_MAX,
    Numerotation,
    analyser_le_masque,
    appliquer_le_masque,
    nom_du_dossier,
    probleme_du_nom,
    quantite,
)
from .commande import Prereglage, taille_finale
from .installation import Topaz

MASQUE_PAR_DEFAUT = "%name% (upscale)%ext%"  # « Sérum (upscale).mp4 » : le nom d'avant la 4.1.0
BALISE_RESOLUTION, BALISE_PREREGLAGE = "res", "preset"
BALISES_EN_PLUS = (BALISE_RESOLUTION, BALISE_PREREGLAGE)
EXEMPLE = Path("Glowzy") / "Sérum.mp4"  # pour montrer ce que donne le masque, sans vidéo dans la liste
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


def resolution_lisible(petit_cote: int) -> str:
    """`%res%` : le petit côté visé, comme on dit « 1080p » (« 1440p », « 2160p » pour la 4K)."""
    return f"{petit_cote}p"


@dataclass(frozen=True)
class NomDesVideos:
    """Le nom des vidéos faites (4.1.0) : le masque de Renommer (`%name%`, `%num%`, `%ext%`,
    `%folderN%`, `%%`), avec `%res%` et `%preset%`. Deux différences avec Renommer, voulues :
    `%num%` n'est pas obligatoire (une seule vidéo n'a pas besoin de numéro), et le masque doit finir
    par `%ext%` (le format est celui du préréglage : l'app met elle-même la bonne extension)."""

    masque: str = MASQUE_PAR_DEFAUT
    numerotation: Numerotation = Numerotation()
    prereglage: str = ""  # le nom du préréglage, pour %preset%

    def erreur(self, extension: str) -> str:
        """Ce qui rend le masque inutilisable (« Lancer » grisé), ou rien."""
        if not self.masque:
            return "Écris le masque du nom (par exemple « %name% (upscale)%ext% »)."
        if not analyser_le_masque(self.masque, BALISES_EN_PLUS).finit_par_extension:
            return f"Le masque doit finir par %ext% : l'app y met l'extension du format du préréglage ({extension})."
        return ""

    def base(self, source: Path, rang: int, extension: str, petit_cote: int) -> str:
        """Le nom sans son extension (« NeMu_VID_01 ») : le masque sans le %ext% qui le finit, appliqué à
        la vidéo de rang `rang` (0 pour la première de la liste)."""
        analyse = analyser_le_masque(self.masque, BALISES_EN_PLUS)
        masque = self.masque[: analyse.extension_finale] if analyse.finit_par_extension else self.masque
        valeurs = {BALISE_RESOLUTION: resolution_lisible(petit_cote), BALISE_PREREGLAGE: self.prereglage}
        return appliquer_le_masque(masque, source, self.numerotation.numero(rang), extension, valeurs)


def exemple_de_nom(nom: NomDesVideos, extension: str, petit_cote: int) -> tuple[str, str]:
    """Ce que donne le masque pour « Sérum.mp4 » (dans un dossier « Glowzy »), et ce que Windows en
    refuserait : de quoi essayer un masque avant d'ajouter des vidéos."""
    exemple = f"{nom.base(EXEMPLE, 0, extension, petit_cote)}{extension}"
    return exemple, probleme_du_nom(exemple)


def nom_de_sortie(base: str, dossier: Path, extension: str, deja_pris: set[Path] | None = None) -> Path:
    """« base + extension » dans `dossier` (« Sérum (upscale).mp4 ») ; « Sérum (upscale) (2).mp4 » si ce
    nom est déjà pris (un fichier existant, ou une autre vidéo de la même file) : aucun fichier n'est
    écrasé."""
    deja_pris = deja_pris or set()
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
    voulu: str = ""  # le nom donné par le masque, avant un « (2) » (nom déjà pris)
    probleme: str = ""  # ce que Windows refuserait (en rouge) : rien n'est lancé tant qu'il y en a


@dataclass
class PlanDeLaFile:
    """Les travaux de la file, et ce qui empêcherait de lancer (en rouge) ou mérite un coup d'œil
    (en orange)."""

    travaux: list[Travail] = field(default_factory=list)
    erreur: str = ""  # masque inutilisable : aucun nom n'est calculé
    alertes: list[str] = field(default_factory=list)

    @property
    def problemes(self) -> list[Travail]:
        return [travail for travail in self.travaux if travail.probleme]

    @property
    def possible(self) -> bool:
        return not self.erreur and not self.problemes and bool(self.travaux)

    def resume(self) -> str:
        """« 3 vidéos : de « NeMu_VID_01.mp4 » à « NeMu_VID_03.mp4 ». » (comme Renommer)."""
        if self.erreur or not self.travaux:
            return self.erreur
        if self.problemes:
            mauvaises = len(self.problemes)
            sujet = "1 vidéo a" if mauvaises == 1 else f"{mauvaises} vidéos ont"
            return f"{sujet} un nom impossible (en rouge) : rien n'est lancé tant que c'est le cas."
        premier, dernier = self.travaux[0].destination.name, self.travaux[-1].destination.name
        if len(self.travaux) == 1:
            return f"1 vidéo : « {premier} »."
        return f"{quantite(len(self.travaux), 'vidéo')} : de « {premier} » à « {dernier} »."


def planifier(
    videos: Sequence[Video],
    petit_cote: int,
    extension: str,
    dossier_sortie: Path | None = None,
    nom: NomDesVideos = NomDesVideos(),
    faites: Collection[Path] = (),
) -> PlanDeLaFile:
    """Les travaux de la file, dans l'ordre de la liste : chaque vidéo à sa taille finale (voir
    taille_finale) et à son nom (le masque), dans `dossier_sortie` ou, sans lui, dans son propre
    dossier. Les vidéos illisibles en sont exclues ; celles déjà faites (`faites`) aussi, mais elles
    gardent leur place : `%num%` suit l'ordre des vidéos lisibles de la liste, et des vidéos ajoutées
    après un lot prennent les numéros suivants."""
    plan = PlanDeLaFile(erreur=nom.erreur(extension))
    if plan.erreur:
        return plan
    pris: set[Path] = set()
    lisibles = [video for video in videos if not video.erreur and video.largeur and video.hauteur]
    for rang, video in enumerate(lisibles):
        if video.source in faites:
            continue
        dossier = dossier_sortie or video.source.parent
        base = nom.base(video.source, rang, extension, petit_cote)
        voulu = f"{base}{extension}"
        probleme = probleme_du_nom(voulu)
        if probleme:  # pas de « (2) » pour un nom que Windows refuse : il ne sera pas écrit
            destination = dossier / voulu
        else:
            destination = nom_de_sortie(base, dossier, extension, pris)
            if len(str(chemin_provisoire(destination))) > LONGUEUR_CHEMIN_MAX:
                probleme = f"Chemin trop long pour Windows ({LONGUEUR_CHEMIN_MAX} caractères au plus)."
        pris.add(destination)
        finale = taille_finale(video.largeur, video.hauteur, petit_cote)
        plan.travaux.append(Travail(video, finale, destination, voulu, probleme))
    plan.alertes = _alertes(plan, nom)
    return plan


def _alertes(plan: PlanDeLaFile, nom: NomDesVideos) -> list[str]:
    """En orange : les noms déjà pris (un « (2) » est ajouté : rien n'est écrasé), puis les balises
    inconnues ou sans dossier, comme dans Renommer."""
    alertes: list[str] = []
    deja_la, en_double = [], []
    for travail in plan.travaux:
        if travail.probleme or travail.destination.name == travail.voulu:
            continue
        if (travail.destination.parent / travail.voulu).exists():
            deja_la.append(travail)
        else:
            en_double.append(travail)
    if en_double:
        alertes.append(
            f"{quantite(len(en_double), 'vidéo')} {'aurait' if len(en_double) == 1 else 'auraient'} le même nom "
            f"qu'une autre de la liste : « (2) », « (3) »… ajoutés. Mets %num% ou %name% dans le masque pour les distinguer."
        )
    if len(deja_la) == 1:
        travail = deja_la[0]
        alertes.append(f"« {travail.voulu} » existe déjà : la vidéo sera enregistrée en « {travail.destination.name} » (rien n'est écrasé).")
    elif deja_la:
        alertes.append(
            f"{len(deja_la)} noms existent déjà : ces vidéos prennent « (2) » (rien n'est écrasé). Change « Démarrer à » "
            f"si tu continues une série."
        )
    analyse = analyser_le_masque(nom.masque, BALISES_EN_PLUS)
    for inconnue in analyse.inconnues:
        alertes.append(f"{inconnue} n'est pas une balise : écrit tel quel dans les noms.")
    if plan.travaux:
        for niveau in sorted(set(analyse.niveaux)):
            if not nom_du_dossier(plan.travaux[0].video.source, niveau):
                alertes.append(f"%folder{niveau}% : pas de dossier à ce niveau, remplacé par rien.")
    return alertes



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
