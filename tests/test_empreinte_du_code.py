"""Empreinte du code (outils/empreinte_du_code.py) : main reprend le .exe vérifié sur la branche d'une
étape quand le code est le même, documentation mise à part."""

import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))

from empreinte_du_code import DOCUMENTATION, empreinte, est_documentation  # noqa: E402


def _git(dossier, *arguments) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@exemple.invalid", "-c", "commit.gpgsign=false", *arguments],
        cwd=dossier,
        check=True,
        capture_output=True,
    )


def _enregistrer(dossier, fichiers: dict[str, str]) -> str:
    for chemin, texte in fichiers.items():
        fichier = dossier / chemin
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(texte, encoding="utf-8")
    _git(dossier, "add", "-A")
    _git(dossier, "commit", "-q", "-m", "étape")
    return empreinte(dossier)


def test_la_documentation_ne_compte_pas(tmp_path):
    _git(tmp_path, "init", "-q")
    depart = _enregistrer(tmp_path, {"app/code.py": "x = 1\n", "docs/CAHIER.md": "v1\n", "README.md": "a\n"})
    assert re.fullmatch(r"[0-9a-f]{64}", depart)
    # Seule la documentation change : même empreinte, le .exe vérifié est repris.
    assert _enregistrer(tmp_path, {"docs/CAHIER.md": "v2\n", "README.md": "b\n", "app/NOTES.md": "c\n"}) == depart
    # Le code change : autre empreinte, fabrication complète.
    assert _enregistrer(tmp_path, {"app/code.py": "x = 2\n"}) != depart


def test_les_memes_fichiers_que_la_fabrication():
    assert est_documentation("docs/CAHIER_DES_CHARGES.md") and est_documentation("docs/images/plan.png")
    assert est_documentation("README.md") and est_documentation("ugc_studio/ressources/LISEZMOI.md")
    assert not est_documentation("ugc_studio/__init__.py") and not est_documentation("documents/a.py")
    assert not est_documentation(".github/workflows/fabrication.yml")
    # La fabrication ne se lance pas pour ces fichiers : ce sont exactement ceux que l'empreinte ignore.
    flux = (RACINE / ".github" / "workflows" / "fabrication.yml").read_text(encoding="utf-8")
    bloc = re.search(r"paths-ignore:\n((?:\s+- .+\n)+)", flux)
    assert bloc is not None
    assert tuple(re.findall(r'- "([^"]+)"', bloc.group(1))) == DOCUMENTATION
