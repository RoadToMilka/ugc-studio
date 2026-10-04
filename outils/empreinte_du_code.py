"""Empreinte du code de l'app : tout ce qui sert à fabriquer le .exe, sans la documentation.

Lancé par la fabrication automatique, jamais par l'utilisateur.

Pourquoi : le dépôt est privé, et GitHub compte les minutes de ses machines (avec un quota par mois).
Chaque étape fabriquait le .exe deux fois : sur sa branche, pour le vérifier, puis sur main après la
fusion, pour publier la Release. Le .exe vérifié sur la branche porte maintenant cette empreinte dans
son nom ; après la fusion, main calcule la sienne et, si elle est la même, publie ce .exe au lieu de
tout refaire.

La documentation (le dossier `docs/` et les fichiers `.md`) ne compte pas : modifier seulement elle ne
relance pas la fabrication (`paths-ignore` dans .github/workflows/fabrication.yml), elle ne change donc
pas le .exe. Une étape dont le dernier envoi ne touche que le cahier des charges garde ainsi son .exe.

Usage : python outils/empreinte_du_code.py   (affiche 64 caractères hexadécimaux)
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

# Les mêmes que `paths-ignore` dans .github/workflows/fabrication.yml (vérifié par un test).
DOCUMENTATION = ("docs/**", "**/*.md")


def est_documentation(chemin: str) -> bool:
    """Chemin relatif à la racine du dépôt, avec des « / » (comme Git les écrit)."""
    return chemin.startswith("docs/") or chemin.endswith(".md")


def empreinte(dossier: Path | str = ".", version: str = "HEAD") -> str:
    """Empreinte SHA-256 de la liste des fichiers de `version` hors documentation : pour chacun, son
    chemin, son mode (exécutable ou non) et l'empreinte Git de son contenu.

    Git donne cette liste telle qu'elle est enregistrée dans le dépôt, triée et sans conversion des fins
    de ligne : la même sur Windows et sur Linux."""
    liste = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--full-tree", version],
        cwd=dossier,
        check=True,
        capture_output=True,
    ).stdout
    calcul = hashlib.sha256()
    for entree in liste.split(b"\0"):
        if not entree:
            continue
        _infos, _tabulation, chemin = entree.partition(b"\t")
        if est_documentation(chemin.decode("utf-8", "surrogateescape")):
            continue
        calcul.update(entree + b"\0")
    return calcul.hexdigest()


if __name__ == "__main__":
    print(empreinte(Path(__file__).resolve().parent.parent))
    sys.exit(0)
