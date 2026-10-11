"""numpy et ONNX Runtime dans le .exe (V4.3) : les bibliothèques de calcul de Doublons, rangées à part.

Pourquoi à part ? Le .exe recopie tout ce qu'il contient dans un dossier temporaire à chaque démarrage :
avec ces deux bibliothèques (plusieurs dizaines de Mo), chaque démarrage de l'app serait plus lent, même
sans jamais ouvrir Doublons. Elles voyagent donc compressées (un fichier zip) dans une « ressource »
Windows du .exe, comme FFmpeg (ressource_du_exe.py), et sont recopiées une seule fois, à la première
analyse, dans %LOCALAPPDATA%\\UGC Studio\\bibliotheques\\<version>\\ ; ensuite, elles sont reprises de là.
La recette du .exe (packaging/ugc_studio.spec) les prépare avec outils/preparer_bibliotheques.py.

Hors du .exe (tests, développement), elles sont installées normalement : rien à faire.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import sys
import threading
import zipfile
from pathlib import Path

from .. import __version__
from ..chemins import dossier_programmes
from ..ressource_du_exe import adresse_de_la_ressource, lire_la_ressource

journal = logging.getLogger(__name__)

NOM_DE_RESSOURCE = "DOUBLONS_BIBLIOTHEQUES"
DOSSIER = "bibliotheques"
TEMOIN = "recopie-complete.txt"  # écrit en dernier : sa présence dit que la recopie est complète
# Les dossiers de DLL des bibliothèques (Windows les cherche là quand Python les charge).
DOSSIERS_DE_DLL = ("numpy.libs", "onnxruntime/capi")


class ErreurBibliotheques(Exception):
    """Les bibliothèques de calcul n'ont pas pu être préparées (message clair, montré à l'utilisateur)."""


def dans_le_exe() -> bool:
    """Vrai dans le .exe fabriqué avec les bibliothèques dans sa ressource."""
    return adresse_de_la_ressource(NOM_DE_RESSOURCE) is not None


def dossier_des_bibliotheques() -> Path | None:
    """Où elles sont recopiées : un dossier par version de l'app et par taille du zip (None hors du .exe)."""
    trouvee = adresse_de_la_ressource(NOM_DE_RESSOURCE)
    if trouvee is None:
        return None
    return dossier_programmes() / DOSSIER / f"{__version__}-{trouvee[1]}"


def bibliotheques_a_preparer() -> bool:
    """Vrai à la première analyse d'une version de l'app : les bibliothèques sont à recopier."""
    dossier = dossier_des_bibliotheques()
    return dossier is not None and not (dossier / TEMOIN).is_file()


def extraire(zip_en_octets: bytes, destination: Path) -> None:
    """Décompresse les bibliothèques dans `destination`, d'abord sous un nom provisoire propre à ce
    lancement de l'app, puis renommé une fois complet (le témoin écrit en dernier) : une recopie
    interrompue n'est jamais utilisée. Le zip vérifie lui-même chaque fichier (code de contrôle)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    provisoire = destination.with_name(f"{destination.name}.{os.getpid()}.en-cours")
    shutil.rmtree(provisoire, ignore_errors=True)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_en_octets)) as archive:
            archive.extractall(provisoire)
        (provisoire / TEMOIN).write_text(f"UGC Studio {__version__}\n", encoding="utf-8")
        try:
            os.replace(provisoire, destination)
        except OSError:
            if not (destination / TEMOIN).is_file():
                # Un reste d'une recopie abandonnée : remplacé.
                shutil.rmtree(destination, ignore_errors=True)
                os.replace(provisoire, destination)
            # Sinon, une autre fenêtre de l'app vient de les recopier : on prend les siennes.
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as erreur:
        raise ErreurBibliotheques(f"la copie des bibliothèques contenue dans l'app est abîmée ({erreur})") from erreur
    finally:
        shutil.rmtree(provisoire, ignore_errors=True)


def _ranger_les_anciennes_versions(garde: Path) -> None:
    """Les copies des versions précédentes de l'app sont effacées."""
    for ancienne in garde.parent.iterdir() if garde.parent.is_dir() else ():
        if ancienne.is_dir() and ancienne.name != garde.name and not ancienne.name.endswith(".en-cours"):
            shutil.rmtree(ancienne, ignore_errors=True)  # encore utilisée par une autre fenêtre : la prochaine fois


_dossiers_de_dll: list = []  # gardés : un dossier ajouté reste cherché tant que l'app tourne


def utiliser(dossier: Path) -> None:
    """Python trouvera les bibliothèques dans `dossier`, et Windows leurs DLL (et celles de l'app : les
    fichiers de Microsoft dont ONNX Runtime a besoin, livrés avec Qt)."""
    if str(dossier) not in sys.path:
        sys.path.insert(0, str(dossier))
    if sys.platform == "win32":
        dossiers = [dossier / sous_dossier for sous_dossier in DOSSIERS_DE_DLL]
        if getattr(sys, "_MEIPASS", None):
            dossiers.append(Path(sys._MEIPASS))
        for dossier_de_dll in dossiers:
            if dossier_de_dll.is_dir():
                _dossiers_de_dll.append(os.add_dll_directory(str(dossier_de_dll)))


_preparation = threading.Lock()
_pretes = False


def preparer_les_bibliotheques() -> None:
    """Les bibliothèques prêtes à être chargées : dans le .exe, recopiées si besoin (une seconde ou deux,
    une fois par version de l'app) puis ajoutées au chemin de Python ; ailleurs, rien à faire. Lance
    ErreurBibliotheques (ou OSError : disque plein…) si elles n'ont pas pu être préparées."""
    global _pretes
    with _preparation:
        if _pretes:
            return
        dossier = dossier_des_bibliotheques()
        if dossier is not None:
            if not (dossier / TEMOIN).is_file():
                octets = lire_la_ressource(NOM_DE_RESSOURCE)
                if octets is None:
                    raise ErreurBibliotheques("les bibliothèques de calcul sont introuvables dans l'app")
                journal.info("Recopie des bibliothèques de Doublons depuis l'app : %s", dossier)
                extraire(octets, dossier)
                _ranger_les_anciennes_versions(dossier)
            utiliser(dossier)
        _pretes = True
