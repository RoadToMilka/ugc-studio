"""Prépare les bibliothèques de calcul de Doublons (numpy, ONNX Runtime) pour le .exe (V4.3) : un zip,
rangé par la recette du .exe (packaging/ugc_studio.spec) dans une ressource Windows, et recopié par
l'app à la première analyse (ugc_studio/doublons/bibliotheques.py). Lancé par la recette du .exe, jamais
par l'utilisateur.

Le zip contient les deux bibliothèques telles qu'installées pour la fabrication (versions figées dans
requirements.txt), avec leurs licences, sans ce qui ne sert jamais à l'app : leurs tests, leurs outils de
développement (conversion de modèles, compilation), les fichiers de description pour les éditeurs de
code. Le code Python y est déjà traduit pour Python (fichiers .pyc) : rien à refaire à chaque analyse.
Chaque fichier y porte la même date : deux fabrications du même code donnent le même zip.
"""

from __future__ import annotations

import argparse
import importlib.util
import py_compile
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

PAQUETS = ("numpy", "onnxruntime")
# Dossiers à côté des paquets qui en font partie : les DLL de numpy, et les licences des deux.
COMPAGNONS = ("numpy.libs",)
# Ce qui ne sert jamais à l'app (chemins dans le paquet, avec des « / »).
DOSSIERS_EXCLUS = {
    "numpy": ("tests", "f2py", "_pyinstaller", "_core/include", "random/_examples", "_core/lib/pkgconfig"),
    "onnxruntime": ("tests", "tools", "transformers", "quantization", "datasets"),
}
EXTENSIONS_EXCLUES = (".pyi", ".pxd", ".h", ".c", ".cpp", ".pyx", ".typed")
DATE_DES_FICHIERS = (2026, 1, 1, 0, 0, 0)


def dossier_des_paquets() -> Path:
    """Le dossier où numpy et ONNX Runtime sont installés (site-packages), sans les charger."""
    trouve = importlib.util.find_spec("numpy")
    if trouve is None or not trouve.submodule_search_locations:
        raise SystemExit("numpy n'est pas installé")
    return Path(next(iter(trouve.submodule_search_locations))).parent


def _exclu(chemin_dans_le_paquet: str, paquet: str) -> bool:
    morceaux = chemin_dans_le_paquet.split("/")
    if "__pycache__" in morceaux or chemin_dans_le_paquet.endswith(EXTENSIONS_EXCLUES):
        return True
    if "tests" in morceaux[:-1]:
        return True
    return any(chemin_dans_le_paquet == dossier or chemin_dans_le_paquet.startswith(dossier + "/") for dossier in DOSSIERS_EXCLUS.get(paquet, ()))


def fichiers_a_ranger(site_packages: Path) -> Iterator[tuple[Path, str]]:
    """(fichier sur le disque, chemin dans le zip) de tout ce qui va dans le zip, trié."""
    dossiers = [site_packages / paquet for paquet in PAQUETS] + [site_packages / compagnon for compagnon in COMPAGNONS]
    for paquet in PAQUETS:
        dossiers += sorted(site_packages.glob(f"{paquet}-*.dist-info"))
    for dossier in dossiers:
        if not dossier.is_dir():
            continue
        paquet = dossier.name.split("-")[0].split(".")[0]
        for fichier in sorted(dossier.rglob("*")):
            if not fichier.is_file():
                continue
            dans_le_paquet = fichier.relative_to(dossier).as_posix()
            if dossier.name in PAQUETS and _exclu(dans_le_paquet, paquet):
                continue
            yield fichier, f"{dossier.name}/{dans_le_paquet}"


def construire(destination: Path, site_packages: Path | None = None) -> dict:
    """Écrit le zip des bibliothèques dans `destination`. Renvoie quelques chiffres (pour le journal)."""
    site_packages = site_packages or dossier_des_paquets()
    destination.parent.mkdir(parents=True, exist_ok=True)
    nombre, taille = 0, 0
    with tempfile.TemporaryDirectory() as provisoire, zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for fichier, nom in fichiers_a_ranger(site_packages):
            if fichier.suffix == ".py":
                # Le code Python, déjà traduit (fichier .pyc à la place du .py).
                compile_ = Path(provisoire) / nom
                compile_.parent.mkdir(parents=True, exist_ok=True)
                py_compile.compile(str(fichier), cfile=str(compile_.with_suffix(".pyc")), dfile=nom, doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
                fichier, nom = compile_.with_suffix(".pyc"), nom[: -len(".py")] + ".pyc"
            info = zipfile.ZipInfo(nom, DATE_DES_FICHIERS)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            donnees = fichier.read_bytes()
            archive.writestr(info, donnees, compresslevel=6)
            nombre += 1
            taille += len(donnees)
    return {"fichiers": nombre, "octets": taille, "zip": destination.stat().st_size}


def main() -> int:
    analyse = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyse.add_argument("destination", type=Path, help="le zip à écrire")
    options = analyse.parse_args()
    chiffres = construire(options.destination)
    print(f"Bibliothèques de Doublons : {chiffres['fichiers']} fichiers, {chiffres['octets'] / 1024**2:.1f} Mo, zip de {chiffres['zip'] / 1024**2:.1f} Mo ({options.destination}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
