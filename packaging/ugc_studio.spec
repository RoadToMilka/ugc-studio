# -*- mode: python ; coding: utf-8 -*-
"""Recette de fabrication du .exe avec PyInstaller.

Elle est utilisée par la fabrication automatique (GitHub Actions) : rien à lancer à la main.
Résultat : un seul fichier « UGC-Studio.exe » qui contient Python, Qt, les polices, les icônes et
FFmpeg (exports vidéo, V3).

Au démarrage, le .exe recopie Python, Qt et les ressources dans un dossier temporaire. FFmpeg n'en
fait pas partie : il voyage compressé dans une « ressource » Windows du .exe, que l'app ne lit qu'au
premier export pour le recopier une fois pour toutes (exports/ffmpeg.py). Avec les autres
ressources, ses 100 Mo étaient recopiés à chaque démarrage : 2,4 s de plus (mesuré).
"""

import sys
from pathlib import Path

RACINE = Path(SPECPATH).parent  # SPECPATH : dossier de ce fichier (fourni par PyInstaller)
sys.path.insert(0, str(RACINE))

from PyInstaller.utils.win32.versioninfo import (  # noqa: E402
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

from ugc_studio import NOM_APP, __version__  # noqa: E402
from ugc_studio.exports.ffmpeg import NOM_DE_RESSOURCE, TYPE_DE_RESSOURCE, VERSION_INTEGREE  # noqa: E402

NOM_EXE = "UGC-Studio"

# FFmpeg (V3, exports vidéo) : compressé par outils/preparer_ffmpeg.py (version 9.0.2 de gyan.dev,
# empreinte vérifiée). Sans lui, pas d'export : la fabrication s'arrête plutôt que de produire un
# .exe incomplet.
FFMPEG_COMPRESSE = RACINE / "outils" / "cache" / f"ffmpeg-{VERSION_INTEGREE}.exe.xz"
if not FFMPEG_COMPRESSE.is_file():
    raise SystemExit(f"FFmpeg compressé absent ({FFMPEG_COMPRESSE}) : lancer d'abord outils/preparer_ffmpeg.py.")
if "," in str(FFMPEG_COMPRESSE):
    raise SystemExit(f"Le chemin de FFmpeg ne doit pas contenir de virgule (séparateur de PyInstaller) : {FFMPEG_COMPRESSE}")


def _version_windows(texte):
    """« 0.1.0 » → (0, 1, 0, 0), le format attendu par Windows."""
    parties = [int(p) for p in texte.split(".")[:4]]
    return tuple(parties + [0] * (4 - len(parties)))


# Fiche d'identité du .exe (clic droit → Propriétés → Détails dans Windows).
INFOS_VERSION = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_version_windows(__version__), prodvers=_version_windows(__version__)),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040C04B0",  # français, Unicode
                    [
                        StringStruct("CompanyName", "RoadToMilka"),
                        StringStruct("FileDescription", NOM_APP),
                        StringStruct("FileVersion", __version__),
                        StringStruct("InternalName", NOM_APP),
                        StringStruct("OriginalFilename", f"{NOM_EXE}.exe"),
                        StringStruct("ProductName", NOM_APP),
                        StringStruct("ProductVersion", __version__),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x040C, 1200])]),
    ],
)

a = Analysis(
    [str(RACINE / "lancer_ugc_studio.py")],
    pathex=[str(RACINE)],
    datas=[(str(RACINE / "ugc_studio" / "ressources"), "ugc_studio/ressources")],
    excludes=["tkinter"],
    noarchive=False,
)


def _garder(destination):
    """Allège le .exe : seules les traductions françaises de Qt sont gardées, et FFmpeg (préparé à côté
    du code pour les tests) n'est pas recopié à chaque démarrage : il voyage dans la ressource."""
    parties = Path(destination).parts
    if "translations" in parties and parties[0] == "PySide6":
        return Path(destination).name.endswith("_fr.qm")
    if parties[:3] == ("ugc_studio", "ressources", "ffmpeg") and parties[-1] in ("ffmpeg.exe", "ffmpeg"):
        return False
    return True


a.datas = [entree for entree in a.datas if _garder(entree[0])]
# Rendu OpenGL logiciel de secours (~20 Mo) : inutile pour une interface Qt Widgets.
a.binaries = [entree for entree in a.binaries if Path(entree[0]).name.lower() != "opengl32sw.dll"]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=NOM_EXE,
    icon=str(RACINE / "ugc_studio" / "ressources" / "app.ico"),
    version=INFOS_VERSION,
    console=False,  # application fenêtrée : pas de fenêtre noire de terminal
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # FFmpeg compressé : « fichier,type,nom,langue » (type 10 : données brutes ; langue 0 : neutre).
    resources=[f"{FFMPEG_COMPRESSE},{TYPE_DE_RESSOURCE},{NOM_DE_RESSOURCE},0"],
)
