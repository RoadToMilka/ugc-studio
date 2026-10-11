"""Doublons (V4.3) : numpy et ONNX Runtime rangés à part dans le .exe (un zip), recopiés à la première
analyse. Ici, le zip est fabriqué depuis les bibliothèques installées pour les tests, puis essayé dans un
Python qui ne connaît qu'elles."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from ugc_studio.doublons import bibliotheques
from ugc_studio.doublons.bibliotheques import TEMOIN, ErreurBibliotheques, extraire

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
from outils.preparer_bibliotheques import construire, fichiers_a_ranger, dossier_des_paquets  # noqa: E402


@pytest.fixture(scope="module")
def zip_des_bibliotheques(tmp_path_factory):
    destination = tmp_path_factory.mktemp("bibliotheques") / "bibliotheques.zip"
    chiffres = construire(destination)
    print(f"Zip des bibliothèques : {chiffres['fichiers']} fichiers, {chiffres['zip'] / 1024**2:.1f} Mo")
    return destination


def test_ce_qui_va_dans_le_zip():
    noms = [nom for _fichier, nom in fichiers_a_ranger(dossier_des_paquets())]
    assert len(noms) > 100
    assert "numpy/__init__.py" in noms and "onnxruntime/__init__.py" in noms
    assert any(nom.startswith("numpy-") and "dist-info/" in nom and "licen" in nom.lower() for nom in noms)  # les licences
    assert not any("/tests/" in nom or nom.startswith(("onnxruntime/transformers/", "onnxruntime/tools/", "numpy/f2py/")) for nom in noms)
    assert not any("__pycache__" in nom or nom.endswith(".pyi") for nom in noms)


def test_le_zip_suffit_a_charger_numpy_et_onnx_runtime(zip_des_bibliotheques, tmp_path):
    dossier = tmp_path / "bibliotheques" / "4.3.0-1"
    extraire(zip_des_bibliotheques.read_bytes(), dossier)
    assert (dossier / TEMOIN).is_file()
    assert not list(dossier.parent.glob("*.en-cours"))
    # Un Python sans ses bibliothèques installées (-S) : il ne trouve numpy et ONNX Runtime que dans le dossier.
    code = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(dossier)!r})\n"
        "os.environ['ORT_DISABLE_TELEMETRY'] = '1'\n"
        "import numpy, onnxruntime\n"
        f"assert numpy.__file__.startswith({str(dossier)!r}), numpy.__file__\n"
        "assert onnxruntime.get_device() == 'CPU'\n"
        "print(numpy.__version__, onnxruntime.__version__, float(numpy.linalg.norm(numpy.ones(4))))\n"
    )
    sortie = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True, env={**os.environ, "PYTHONUTF8": "1"})
    assert sortie.returncode == 0, sortie.stderr
    assert sortie.stdout.split()[-1] == "2.0"


def test_meme_zip_d_une_fabrication_a_l_autre(zip_des_bibliotheques, tmp_path):
    autre = tmp_path / "autre.zip"
    construire(autre)
    assert autre.read_bytes() == zip_des_bibliotheques.read_bytes()


def test_zip_abime_refuse(tmp_path):
    with pytest.raises(ErreurBibliotheques, match="abîmée"):
        extraire(b"pas un zip", tmp_path / "bibliotheques" / "x")
    assert not (tmp_path / "bibliotheques" / "x").exists()


def test_recopie_deja_faite_reprise_telle_quelle(tmp_path):
    tampon = tmp_path / "petit.zip"
    with zipfile.ZipFile(tampon, "w") as archive:
        archive.writestr("module_essai.py", "VALEUR = 1\n")
    dossier = tmp_path / "bibliotheques" / "v"
    extraire(tampon.read_bytes(), dossier)
    (dossier / "module_essai.py").write_text("VALEUR = 2\n")
    extraire(tampon.read_bytes(), dossier)  # une autre fenêtre de l'app la refait : la première reste
    assert (dossier / "module_essai.py").read_text() == "VALEUR = 2\n"


def test_hors_du_exe_rien_a_faire():
    assert not bibliotheques.dans_le_exe()
    assert bibliotheques.dossier_des_bibliotheques() is None
    assert not bibliotheques.bibliotheques_a_preparer()
    bibliotheques.preparer_les_bibliotheques()  # sans effet : elles sont installées normalement
