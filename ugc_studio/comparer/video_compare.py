"""Module Comparer (V4.1, version 4.2.0 ; cahier des charges §8 bis.4) : deux vidéos ou deux images
comparées dans **video-compare** (logiciel libre de Pixop, licence GPL v2 : https://github.com/pixop/
video-compare), lancé tel quel dans sa propre fenêtre. Décision de l'utilisateur du 06/10/2026 : sa
propre copie, téléchargée sur son ordinateur (le zip « video-compare-20261004-win10-x86_64.zip »).

Ce fichier, sans interface :
- trouver video-compare : la copie choisie (son zip, son dossier décompressé ou video-compare.exe),
  celle déjà installée par l'app, ou celle des Téléchargements de l'utilisateur ;
- installer un zip : décompressé dans le dossier des programmes de l'app (%LOCALAPPDATA%\\UGC Studio\\
  video-compare\\…), d'abord sous un nom provisoire ; le zip ne bouge pas ;
- lire sa version (`video-compare -V`) : la preuve qu'il démarre ;
- les options de lancement, traduites des réglages du module (documentation de video-compare et
  liste de ses options dans `src/main.cpp`, version 20261004) ;
- ce qu'il écrit pendant la comparaison, mis en français : les mesures de la touche M (PSNR, SSIM,
  VMAF) et les captures de la touche F.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..chemins import dossier_programmes

NOM_PROGRAMME = "video-compare.exe"
VERSION_TESTEE = "20261004-osaka"
PAGE_OFFICIELLE = "https://github.com/pixop/video-compare/releases"
# « video-compare-20261004-win10-x86_64.zip » (le zip pour Windows de chaque version), ou le dossier
# où il a été décompressé (« Extraire tout » de Windows lui donne le nom du zip).
MOTIF_DU_NOM = re.compile(r"^video-compare", re.IGNORECASE)
DOSSIER_D_INSTALLATION = "video-compare"
EN_COURS = ".en-cours"
DELAI_VERSION_S = 30  # au premier lancement, l'antivirus examine ses bibliothèques (plus de 100 Mo)

# Réglages du module, et les options de video-compare qui leur correspondent.
CURSEUR, COTE_A_COTE, EMPILEES = "split", "hstack", "vstack"  # option -m (« split » : celle par défaut)
DISPOSITIONS = {
    CURSEUR: "Curseur",
    COTE_A_COTE: "Côte à côte",
    EMPILEES: "L'une sous l'autre",
}
ECRAN, PLEIN_ECRAN, TAILLE_VIDEO = "ecran", "plein", "video"  # -W, -u, ou rien
FENETRES = {
    ECRAN: "Adaptée à l'écran",
    PLEIN_ECRAN: "Plein écran",
    TAILLE_VIDEO: "Taille de la vidéo",
}
DECALAGE_MAX_MS = 10_000  # video-compare : « Keep time-shifts below a few seconds »


class VideoCompareIntrouvable(Exception):
    """video-compare manque, ou ne démarre pas : le message est pour l'utilisateur."""


@dataclass(frozen=True)
class VideoCompare:
    """Une copie de video-compare qui démarre : `programme`, ce qu'on lance (son .exe ; dans les
    tests, un faux), et sa version."""

    programme: tuple[str, ...]
    version: str

    def nom(self) -> str:
        return f"video-compare {self.version}"

    @property
    def chemin(self) -> Path:
        return Path(self.programme[-1])


@dataclass(frozen=True)
class Trouvaille:
    """Ce qu'on a trouvé : un video-compare.exe à essayer, ou un zip à installer (ou rien)."""

    programme: Path | None = None
    archive: Path | None = None
    ou: str = ""  # « dans tes Téléchargements », « installé par l'app »…


# --- Trouver ----------------------------------------------------------------------------------------


def programme_dans(dossier: Path) -> Path | None:
    """video-compare.exe dans ce dossier, ou dans l'un de ses sous-dossiers (un zip décompressé dans
    un dossier à son nom, par exemple)."""
    if not dossier.is_dir():
        return None
    direct = dossier / NOM_PROGRAMME
    if direct.is_file():
        return direct
    try:
        sous_dossiers = sorted((d for d in dossier.iterdir() if d.is_dir()), key=lambda d: d.name.lower(), reverse=True)
    except OSError:
        return None
    for sous_dossier in sous_dossiers:
        if (sous_dossier / NOM_PROGRAMME).is_file():
            return sous_dossier / NOM_PROGRAMME
    return None


def lire_le_choix(chemin: Path) -> Trouvaille:
    """Ce que l'utilisateur a choisi : le zip téléchargé, video-compare.exe, ou son dossier."""
    if chemin.is_file() and chemin.suffix.lower() == ".zip":
        return Trouvaille(archive=chemin, ou="choisi")
    if chemin.is_file() and chemin.name.lower() == NOM_PROGRAMME:
        return Trouvaille(programme=chemin, ou="choisi")
    programme = programme_dans(chemin)
    return Trouvaille(programme=programme, ou="choisi") if programme else Trouvaille()


def installations(racine: Path | None = None) -> list[Path]:
    """Les copies installées par l'app (décompressées depuis un zip), la plus récente d'abord (le nom
    du zip commence par la date de la version : « video-compare-20261004-… »)."""
    racine = racine or dossier_programmes() / DOSSIER_D_INSTALLATION
    if not racine.is_dir():
        return []
    dossiers = sorted((d for d in racine.iterdir() if d.is_dir() and not d.name.endswith(EN_COURS)), key=lambda d: d.name.lower(), reverse=True)
    return [programme for programme in (programme_dans(d) for d in dossiers) if programme is not None]


def dans_les_telechargements(telechargements: Path) -> Trouvaille:
    """video-compare dans les Téléchargements de l'utilisateur : un dossier décompressé (utilisable tel
    quel) ou le zip (à installer), le plus récent d'abord ; les dossiers passent avant les zips."""
    try:
        elements = sorted((e for e in telechargements.iterdir() if MOTIF_DU_NOM.match(e.name)), key=lambda e: e.name.lower(), reverse=True)
    except OSError:
        return Trouvaille()
    for element in elements:
        if element.is_dir():
            programme = programme_dans(element)
            if programme is not None:
                return Trouvaille(programme=programme, ou="dans tes Téléchargements")
    for element in elements:
        if element.is_file() and element.suffix.lower() == ".zip":
            return Trouvaille(archive=element, ou="dans tes Téléchargements")
    return Trouvaille()


def trouver(choisi: Path | None, telechargements: Path | None, racine: Path | None = None) -> Trouvaille:
    """Où est video-compare, dans cet ordre : la copie choisie (si elle existe encore), la dernière
    installée par l'app, puis les Téléchargements."""
    racine = racine or dossier_programmes() / DOSSIER_D_INSTALLATION
    if choisi is not None and choisi.exists():
        trouvaille = lire_le_choix(choisi)
        if trouvaille.archive is not None:  # un zip choisi, déjà installé : sa copie installée
            installee = programme_dans(racine / trouvaille.archive.stem)
            if installee is not None:
                return Trouvaille(programme=installee, ou="installé par l'app")
        if trouvaille.programme or trouvaille.archive:
            return trouvaille
    installees = installations(racine)
    if installees:
        return Trouvaille(programme=installees[0], ou="installé par l'app")
    if telechargements is not None:
        return dans_les_telechargements(telechargements)
    return Trouvaille()


# --- Installer et vérifier ----------------------------------------------------------------------------


def installer(archive: Path, progres: Callable[[float], None] | None = None, racine: Path | None = None) -> Path:
    """Décompresse le zip de video-compare dans le dossier des programmes de l'app (`…\\video-compare\\
    <nom du zip>\\`), d'abord dans un dossier provisoire renommé à la fin : une installation coupée ne
    laisse rien de bancal. Le zip ne bouge pas. Renvoie le chemin de video-compare.exe.
    (`zipfile` refuse de lui-même les noms qui sortiraient du dossier : « .. », chemins absolus.)"""
    racine = racine or dossier_programmes() / DOSSIER_D_INSTALLATION
    destination = racine / archive.stem
    provisoire = racine / f"{archive.stem}{EN_COURS}"
    try:
        with zipfile.ZipFile(archive) as contenu:
            membres = contenu.infolist()
            if not any(Path(membre.filename).name.lower() == NOM_PROGRAMME for membre in membres):
                raise VideoCompareIntrouvable(
                    f"Ce zip ne contient pas {NOM_PROGRAMME} : prends celui de Windows sur la page de video-compare "
                    "(« video-compare-…-win10-x86_64.zip »)."
                )
            shutil.rmtree(provisoire, ignore_errors=True)
            provisoire.mkdir(parents=True)
            total = sum(membre.file_size for membre in membres) or 1
            fait = 0
            for membre in membres:
                contenu.extract(membre, provisoire)
                fait += membre.file_size
                if progres is not None:
                    progres(fait / total)
    except zipfile.BadZipFile as erreur:
        shutil.rmtree(provisoire, ignore_errors=True)
        raise VideoCompareIntrouvable("Ce fichier n'est pas un zip lisible : téléchargement incomplet ? Télécharge-le à nouveau.") from erreur
    except OSError as erreur:
        shutil.rmtree(provisoire, ignore_errors=True)
        raise VideoCompareIntrouvable(f"Impossible de décompresser video-compare : {erreur}") from erreur
    shutil.rmtree(destination, ignore_errors=True)
    provisoire.rename(destination)
    programme = programme_dans(destination)
    if programme is None:  # vérifié plus haut : ne devrait pas arriver
        raise VideoCompareIntrouvable(f"{NOM_PROGRAMME} introuvable après la décompression.")
    return programme


def _options_de_lancement() -> dict:
    """video-compare est un programme « console » : sans précaution, une fenêtre noire s'ouvrirait à
    côté de la sienne. CREATE_NO_WINDOW l'en empêche (sa fenêtre de comparaison s'ouvre normalement)."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def lire_la_version(programme: Sequence[str]) -> str:
    """`video-compare -V` (« video-compare 20261004-osaka ») : la version, et la preuve qu'il démarre."""
    try:
        resultat = subprocess.run(
            [*programme, "-V"],
            capture_output=True,
            timeout=DELAI_VERSION_S,
            stdin=subprocess.DEVNULL,
            **_options_de_lancement(),
        )
    except (OSError, subprocess.TimeoutExpired) as erreur:
        raise VideoCompareIntrouvable(f"video-compare ne démarre pas : {erreur}") from erreur
    sortie = resultat.stdout.decode("utf-8", errors="replace") + resultat.stderr.decode("utf-8", errors="replace")
    trouve = re.search(r"video-compare\s+(\S+)", sortie)
    if resultat.returncode != 0 or trouve is None:
        derniere = next((ligne for ligne in reversed(sortie.splitlines()) if ligne.strip()), "")
        raise VideoCompareIntrouvable(
            "video-compare ne répond pas comme prévu"
            + (f" : {derniere.strip()}" if derniere else f" (code {resultat.returncode}).")
            + " Il lui manque peut-être un fichier : garde tout le contenu du zip ensemble."
        )
    return trouve.group(1)


def ouvrir(programme: Path) -> VideoCompare:
    """Une copie de video-compare, vérifiée (elle démarre et donne sa version)."""
    return VideoCompare((str(programme),), lire_la_version((str(programme),)))


# --- Lancer -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reglages:
    disposition: str = CURSEUR
    fenetre: str = ECRAN
    decalage_ms: int = 0  # la vidéo de droite décalée (positif : celle de gauche attend)
    boucle: bool = False
    difference: bool = False


def arguments(video_compare: VideoCompare, gauche: Path, droite: Path, reglages: Reglages) -> list[str]:
    """La commande de video-compare pour ces deux fichiers et ces réglages. « -- » avant les fichiers :
    un nom qui commencerait par « - » ne serait pas pris pour une option."""
    commande = [*video_compare.programme]
    if reglages.disposition in (COTE_A_COTE, EMPILEES):
        commande += ["-m", reglages.disposition]
    if reglages.fenetre == ECRAN:
        commande.append("-W")
    elif reglages.fenetre == PLEIN_ECRAN:
        commande.append("-u")
    if reglages.decalage_ms:
        commande += ["-t", f"{reglages.decalage_ms / 1000:.3f}"]
    if reglages.boucle:
        commande += ["-a", "on"]
    if reglages.difference:
        commande.append("-S")
    return [*commande, "--", str(gauche), str(droite)]


class Comparaison:
    """Une fenêtre de video-compare ouverte : le programme lancé sans console, dans le dossier des
    captures (la touche F y enregistre ses images) ; ce qu'il écrit est lu ligne par ligne."""

    def __init__(self, commande: list[str], dossier_des_captures: Path):
        self.commande = commande
        self.dossier_des_captures = dossier_des_captures
        self._processus = subprocess.Popen(
            commande,
            cwd=str(dossier_des_captures),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **_options_de_lancement(),
        )
        self.dernieres_lignes: list[str] = []

    def lire(self, ligne_recue: Callable[[str], None]) -> int:
        """Lit ce qu'écrit video-compare jusqu'à ce que sa fenêtre se ferme ; renvoie son code de fin."""
        flux = self._processus.stdout
        if flux is not None:
            for brute in iter(flux.readline, b""):
                ligne = brute.decode("utf-8", errors="replace").rstrip("\r\n")
                if ligne:
                    self.dernieres_lignes = [*self.dernieres_lignes[-4:], ligne]
                    ligne_recue(ligne)
        return self._processus.wait()

    def ouverte(self) -> bool:
        return self._processus.poll() is None

    def fermer(self) -> None:
        """Ferme la fenêtre de video-compare (« Fermer la comparaison », ou l'app qui se ferme)."""
        if self.ouverte():
            self._processus.terminate()


# --- Ce qu'il écrit -----------------------------------------------------------------------------------

# « Metrics: [00:00:05.120|00:00:05.120] PSNR(42.131), SSIM(0.99812), VMAF(97.312)  (10,20)-(500,700) »
_MESURES = re.compile(r"^Metrics: \[([^|\]]*)\|([^\]]*)\] PSNR\(([^)]*)\), SSIM\(([^)]*)\), VMAF\(([^)]*)\)(.*)$")
# « Saved a_0000.png, b_0000.png and a_b_osd_0000.png » (en fenêtre ; en plein écran, il l'affiche)
_CAPTURES = re.compile(r"^Saved (.+), (.+) and (.+)$")


@dataclass(frozen=True)
class Mesures:
    """Les mesures de la touche M, pour l'image affichée (ou la zone visible, après un zoom)."""

    moment_gauche: str
    moment_droite: str
    psnr: str
    ssim: str
    vmaf: str
    zone: bool  # la zone visible seulement (après un zoom), pas toute l'image

    def moment(self) -> str:
        """« 00:05,120 » (et celui de droite s'il diffère : décalage)."""
        gauche, droite = _moment(self.moment_gauche), _moment(self.moment_droite)
        return gauche if gauche == droite else f"{gauche} / {droite}"

    def ssim_lisible(self) -> str:
        """« 0,9981 » (1 : identiques), ou rien s'il n'a pas pu être mesuré."""
        valeur = _nombre(self.ssim)
        return _virgule(f"{valeur:.4f}") if valeur is not None else ""

    def psnr_lisible(self) -> str:
        """« 42,13 dB », « infini (identiques) », ou rien."""
        if self.psnr.strip().lower() == "inf":
            return "infini (identiques)"
        valeur = _nombre(self.psnr)
        return f"{_virgule(f'{valeur:.2f}')} dB" if valeur is not None else ""

    def vmaf_lisible(self) -> str:
        """« 97,31 » (sur 100), ou rien (« n/a » : pas mesuré, par exemple sur une très petite image)."""
        scores = [_nombre(score) for score in self.vmaf.split("|")]
        if not scores or any(score is None for score in scores):
            return ""
        return " | ".join(_virgule(f"{score:.2f}") for score in scores)

    def en_francais(self) -> str:
        """« SSIM 0,9981 · PSNR 42,13 dB · VMAF 97,31 »."""
        valeurs = (("SSIM", self.ssim_lisible()), ("PSNR", self.psnr_lisible()), ("VMAF", self.vmaf_lisible()))
        return " · ".join(f"{nom} {valeur}" for nom, valeur in valeurs if valeur)


def _nombre(texte: str) -> float | None:
    try:
        return float(texte)
    except ValueError:
        return None


def _virgule(texte: str) -> str:
    return texte.replace(".", ",")


def _moment(texte: str) -> str:
    """« 00:00:05.120 » devient « 00:05,120 » (les heures seulement si elles comptent)."""
    texte = texte.strip()
    if texte.startswith("00:") and texte.count(":") == 2:
        texte = texte[3:]
    return _virgule(texte)


def lire_les_mesures(ligne: str) -> Mesures | None:
    trouve = _MESURES.match(ligne.strip())
    if trouve is None:
        return None
    gauche, droite, psnr, ssim, vmaf, reste = trouve.groups()
    return Mesures(gauche, droite, psnr, ssim, vmaf, bool(reste.strip()))


def lire_les_captures(ligne: str) -> list[str] | None:
    """Les trois images de la touche F : celle de gauche, celle de droite, et l'écran tel qu'on le voit."""
    trouve = _CAPTURES.match(ligne.strip())
    return list(trouve.groups()) if trouve else None
