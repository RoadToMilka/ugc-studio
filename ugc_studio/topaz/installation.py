"""Topaz Video AI sur l'ordinateur (V4, lot 3 ; cahier des charges §8 bis.3) : où il est installé, sa
version, ses dossiers de modèles, et ce qui manquerait pour lancer un modèle.

D'après la documentation de Topaz (« Command Line Interface », consultée le 04/10/2026) et le forum de
Topaz :
- le FFmpeg de Topaz, qui contient ses filtres d'IA, est dans le dossier d'installation
  (`C:\\Program Files\\Topaz Labs LLC\\Topaz Video AI` par défaut) ;
- lancé sans l'interface de Topaz, il a besoin de deux variables d'environnement : `TVAI_MODEL_DIR`, le
  dossier des définitions des modèles (« prob-4.json »…), du fichier de connexion (« auth.tpz ») et de
  « tvai.tz » (par défaut `C:\\ProgramData\\Topaz Labs LLC\\Topaz Video AI\\models`) ; et
  `TVAI_MODEL_DATA_DIR`, le dossier où les modèles sont téléchargés (« prob-v4-….tz » ; choisi dans
  les préférences de Topaz) ;
- il se sert de la connexion de l'app Topaz : il faut s'y être connecté une fois.

Si Topaz a déjà posé ces variables pour tout Windows, l'app les reprend telles quelles. Sinon, elle
cherche les dossiers habituels, et l'utilisateur peut les choisir.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

DOSSIER_PAR_DEFAUT = Path(r"C:\Program Files\Topaz Labs LLC\Topaz Video AI")
DONNEES_PAR_DEFAUT = Path(r"C:\ProgramData\Topaz Labs LLC\Topaz Video AI")
MODELES_PAR_DEFAUT = DONNEES_PAR_DEFAUT / "models"
PROGRAMME = "ffmpeg.exe"
APPLICATION = "Topaz Video AI.exe"
VARIABLE_MODELES = "TVAI_MODEL_DIR"
VARIABLE_DONNEES = "TVAI_MODEL_DATA_DIR"
CONNEXION = "auth.tpz"


def version_du_programme(chemin: Path) -> str:
    """Version d'un programme de Windows (« 7.1.1 »), lue dans ses informations de fichier ; vide si
    elle est illisible (ou hors de Windows)."""
    if sys.platform != "win32" or not chemin.is_file():
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        version = ctypes.windll.version
        taille = version.GetFileVersionInfoSizeW(str(chemin), None)
        if not taille:
            return ""
        tampon = ctypes.create_string_buffer(taille)
        if not version.GetFileVersionInfoW(str(chemin), 0, taille, tampon):
            return ""
        infos = ctypes.c_void_p()
        longueur = wintypes.UINT()
        if not version.VerQueryValueW(tampon, "\\", ctypes.byref(infos), ctypes.byref(longueur)):
            return ""

        class InfosFixes(ctypes.Structure):  # VS_FIXEDFILEINFO
            _fields_ = [(nom, wintypes.DWORD) for nom in (
                "signature", "version_structure", "version_haute", "version_basse", "produit_haute",
                "produit_basse", "masque", "drapeaux", "systeme", "type", "sous_type", "date_haute", "date_basse",
            )]

        fixes = ctypes.cast(infos, ctypes.POINTER(InfosFixes)).contents
        nombres = (fixes.version_haute >> 16, fixes.version_haute & 0xFFFF, fixes.version_basse >> 16)
        return ".".join(str(nombre) for nombre in nombres)
    except (AttributeError, OSError, ValueError):
        return ""


def _contient_le_modele(dossier: Path, modele: str) -> bool:
    """Le dossier contient-il des fichiers téléchargés de ce modèle ? « prob-4 » → « prob-v4-….tz »."""
    famille, _, numero = modele.partition("-")
    try:
        return any(dossier.glob(f"{famille}-v{numero}-*")) if numero else any(dossier.glob(f"{famille}-*"))
    except OSError:
        return False


@dataclass(frozen=True)
class Topaz:
    """Topaz Video AI tel que l'app va le lancer."""

    dossier: Path
    programme: tuple[str, ...]  # ce qu'on lance : (ffmpeg.exe,) ; tests et autotest : un faux Topaz
    version: str = ""
    modeles: Path | None = None  # TVAI_MODEL_DIR
    donnees: Path | None = None  # TVAI_MODEL_DATA_DIR

    def nom(self) -> str:
        return f"Topaz Video AI {self.version}".strip()

    def environnement(self) -> dict[str, str]:
        """Les variables que le FFmpeg de Topaz attend (celles de Windows si elles existent déjà)."""
        variables = {}
        if self.modeles is not None:
            variables[VARIABLE_MODELES] = str(self.modeles)
        if self.donnees is not None:
            variables[VARIABLE_DONNEES] = str(self.donnees)
        return variables

    def problemes(self, modele: str = "") -> list[str]:
        """Ce qui empêcherait de lancer le modèle `modele` (« prob-4 »), en français ; vide : prêt."""
        if len(self.programme) == 1 and not Path(self.programme[0]).is_file():
            return [f"Le programme de Topaz ({PROGRAMME}) n'est pas dans « {self.dossier} »."]
        problemes = []
        if self.modeles is None or not self.modeles.is_dir():
            problemes.append("Dossier des modèles de Topaz introuvable : choisis-le (« Dossiers de Topaz… »).")
            return problemes
        if not (self.modeles / CONNEXION).is_file():
            problemes.append("Topaz ne semble pas connecté : ouvre Topaz Video AI et connecte-toi une fois.")
        if modele and not (self.modeles / f"{modele}.json").is_file():
            problemes.append(f"Le modèle « {modele} » n'est pas défini dans « {self.modeles} ».")
        if self.donnees is None or not self.donnees.is_dir():
            problemes.append("Dossier des modèles téléchargés introuvable : choisis-le (« Dossiers de Topaz… »).")
        return problemes


def trouver_topaz(
    dossier: Path | None = None,
    modeles: Path | None = None,
    donnees: Path | None = None,
    modele: str = "prob-4",
) -> Topaz | None:
    """Topaz Video AI : dans `dossier` (choisi par l'utilisateur) ou à sa place habituelle ; None s'il
    n'y est pas. Les dossiers des modèles : ceux choisis, sinon les variables de Windows, sinon les
    dossiers habituels (pour les modèles téléchargés : celui qui contient ceux de `modele`)."""
    dossier = dossier or DOSSIER_PAR_DEFAUT
    programme = dossier / PROGRAMME
    if not programme.is_file():
        return None
    if modeles is None:
        variable = os.environ.get(VARIABLE_MODELES)
        modeles = Path(variable) if variable else MODELES_PAR_DEFAUT
    if donnees is None:
        variable = os.environ.get(VARIABLE_DONNEES)
        if variable:
            donnees = Path(variable)
        else:
            candidats = [modeles, DONNEES_PAR_DEFAUT, MODELES_PAR_DEFAUT]
            donnees = next((c for c in candidats if c.is_dir() and _contient_le_modele(c, modele)), modeles)
    return Topaz(dossier, (str(programme),), version_du_programme(dossier / APPLICATION), modeles, donnees)
