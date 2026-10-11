# -*- mode: python ; coding: utf-8 -*-
"""Recette de fabrication du .exe avec PyInstaller.

Elle est utilisée par la fabrication automatique (GitHub Actions) : rien à lancer à la main.
Résultat : un seul fichier « UGC-Studio.exe » qui contient Python, Qt, les polices, les icônes et
FFmpeg (exports vidéo, V3).

Au démarrage, le .exe recopie Python, Qt et les ressources dans un dossier temporaire. FFmpeg n'en
fait pas partie : il voyage compressé dans une « ressource » Windows du .exe, que l'app ne lit qu'au
premier export pour le recopier une fois pour toutes (exports/ffmpeg.py). Avec les autres
ressources, ses 100 Mo étaient recopiés à chaque démarrage : 2,4 s de plus (mesuré).

De même pour Doublons (V4.3) : son modèle d'IA (lu directement dans sa ressource, vision.py) et ses
bibliothèques de calcul, numpy et ONNX Runtime (un zip recopié à la première analyse,
doublons/bibliotheques.py). Les modules de Python dont elles ont besoin, eux, sont avec l'app.
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

from outils.preparer_bibliotheques import PAQUETS, construire  # noqa: E402
from ugc_studio import NOM_APP, __version__  # noqa: E402
from ugc_studio.doublons import bibliotheques  # noqa: E402
from ugc_studio.doublons.modeles import MODELE_DE_L_APP, MODELES, empreinte_du_fichier  # noqa: E402
from ugc_studio.doublons.modeles import NOM_DE_RESSOURCE as NOM_DU_MODELE  # noqa: E402
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

# Doublons (V4.3) : le modèle d'IA de l'app, préparé par outils/preparer_modeles.py (version figée,
# empreinte vérifiée) ; vérifié à nouveau ici. Sans lui, pas d'analyse avec IA : la fabrication s'arrête.
_MODELE = MODELES[MODELE_DE_L_APP]
FICHIER_DU_MODELE = RACINE / "outils" / "cache-modeles" / _MODELE.nom / _MODELE.principal.nom
if not FICHIER_DU_MODELE.is_file() or empreinte_du_fichier(FICHIER_DU_MODELE) != _MODELE.principal.empreinte:
    raise SystemExit(f"Modèle d'IA absent ou différent ({FICHIER_DU_MODELE}) : lancer d'abord outils/preparer_modeles.py.")
# Ses bibliothèques de calcul, en un zip (outils/preparer_bibliotheques.py).
ZIP_DES_BIBLIOTHEQUES = RACINE / "build" / "bibliotheques-doublons.zip"
_chiffres = construire(ZIP_DES_BIBLIOTHEQUES)
print(f"Bibliothèques de Doublons : {_chiffres['fichiers']} fichiers, zip de {_chiffres['zip'] / 1024**2:.1f} Mo")
for _fichier in (FICHIER_DU_MODELE, ZIP_DES_BIBLIOTHEQUES):
    if "," in str(_fichier):
        raise SystemExit(f"Ce chemin ne doit pas contenir de virgule (séparateur de PyInstaller) : {_fichier}")


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

# Les modules de Python (et leurs bibliothèques de Windows) dont numpy et ONNX Runtime ont besoin : ceux
# que PyInstaller trouve en analysant un fichier qui les charge. Ils seront avec l'app ; numpy et ONNX
# Runtime eux-mêmes, non (voir plus haut).
_besoins = Analysis([str(RACINE / "packaging" / "bibliotheques_doublons.py")], pathex=[str(RACINE)], excludes=["tkinter"], noarchive=False)


def _des_bibliotheques(nom: str) -> bool:
    premier = Path(nom).parts[0] if Path(nom).parts else nom
    return premier.split(".")[0] in PAQUETS or premier.split("-")[0] in PAQUETS


def _module_de_l_extension(destination: str) -> str:
    """« _ctypes.pyd » → « _ctypes » ; « sous\\nom.cp312-win_amd64.pyd » → « sous.nom »."""
    nom = Path(destination).name.split(".")[0]
    return ".".join([*Path(destination).parent.parts, nom]) if Path(destination).parent.parts else nom


MODULES_POUR_LES_BIBLIOTHEQUES = sorted(
    {nom for nom, _source, _type in _besoins.pure if not _des_bibliotheques(nom)}
    | {_module_de_l_extension(nom) for nom, _source, type_ in _besoins.binaries if type_ == "EXTENSION" and not _des_bibliotheques(nom)}
)
DLL_POUR_LES_BIBLIOTHEQUES = [
    entree for entree in _besoins.binaries if entree[2] == "BINARY" and len(Path(entree[0]).parts) == 1 and not _des_bibliotheques(entree[0])
]

a = Analysis(
    [str(RACINE / "lancer_ugc_studio.py")],
    pathex=[str(RACINE)],
    datas=[(str(RACINE / "ugc_studio" / "ressources"), "ugc_studio/ressources")],
    hiddenimports=MODULES_POUR_LES_BIBLIOTHEQUES,
    excludes=["tkinter", *PAQUETS],
    noarchive=False,
)
_deja = {Path(entree[0]).name.lower() for entree in a.binaries}
a.binaries += [entree for entree in DLL_POUR_LES_BIBLIOTHEQUES if Path(entree[0]).name.lower() not in _deja]


def _garder(destination):
    """Allège le .exe : seules les traductions françaises de Qt sont gardées, et FFmpeg (préparé à côté
    du code pour les tests) n'est pas recopié à chaque démarrage : il voyage dans la ressource. De même
    pour les modèles d'IA de Doublons (V4.3), préparés dans un sous-dossier de ressources/modeles pour
    les tests : seuls les fichiers du dossier modeles lui-même (licences) sont gardés."""
    parties = Path(destination).parts
    if "translations" in parties and parties[0] == "PySide6":
        return Path(destination).name.endswith("_fr.qm")
    if parties[:3] == ("ugc_studio", "ressources", "ffmpeg") and parties[-1] in ("ffmpeg.exe", "ffmpeg"):
        return False
    if parties[:3] == ("ugc_studio", "ressources", "modeles") and len(parties) > 4:
        return False
    return True


a.datas = [entree for entree in a.datas if _garder(entree[0])]
# PyInstaller range ffmpeg.exe (un programme) avec les « binaires », même pris dans les ressources :
# le filtre s'applique donc aussi à eux. Rendu OpenGL logiciel de secours (~20 Mo) : inutile pour une
# interface Qt Widgets.
a.binaries = [entree for entree in a.binaries if _garder(entree[0]) and Path(entree[0]).name.lower() != "opengl32sw.dll"]
_restes = [entree[0] for entree in (*a.datas, *a.binaries) if not _garder(entree[0])]
if _restes:
    raise SystemExit(f"FFmpeg ou un modèle d'IA serait recopié à chaque démarrage : {_restes}")
_bibliotheques_avec_l_app = [entree[0] for entree in (*a.pure, *a.binaries) if _des_bibliotheques(entree[0])]
if _bibliotheques_avec_l_app:
    raise SystemExit(f"numpy ou ONNX Runtime seraient recopiés à chaque démarrage : {_bibliotheques_avec_l_app[:5]}")

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
    # « fichier,type,nom,langue » (type 10 : données brutes ; langue 0 : neutre) : FFmpeg compressé, le
    # modèle d'IA de Doublons et ses bibliothèques de calcul (V4.3).
    resources=[
        f"{FFMPEG_COMPRESSE},{TYPE_DE_RESSOURCE},{NOM_DE_RESSOURCE},0",
        f"{FICHIER_DU_MODELE},{TYPE_DE_RESSOURCE},{NOM_DU_MODELE},0",
        f"{ZIP_DES_BIBLIOTHEQUES},{TYPE_DE_RESSOURCE},{bibliotheques.NOM_DE_RESSOURCE},0",
    ],
)
