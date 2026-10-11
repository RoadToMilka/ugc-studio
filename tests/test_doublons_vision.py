"""Doublons (V4.3) : l'IA (DINOv2 small avec ONNX Runtime). Les tests avec le vrai modèle ne tournent que
s'il a été préparé à côté du code (outils/preparer_modeles.py : la fabrication automatique le fait)."""

import os
import subprocess
import sys
import time

import numpy as np
import pytest

from photos_factices import autres_couleurs, miroir, photo_factice, plus_petite
from ugc_studio.doublons import vision
from ugc_studio.doublons.modeles import MODELE_DE_L_APP, MODELES
from ugc_studio.doublons.vision import ErreurModele, preparer_pour_le_modele

MODELE_PRESENT = vision.fichier_du_modele().is_file()
avec_le_modele = pytest.mark.skipif(not MODELE_PRESENT, reason="modèle d'IA absent (outils/preparer_modeles.py)")


@pytest.mark.parametrize(
    ("taille", "forme"),
    [((300, 400), (1, 3, 294, 224)), ((224, 224), (1, 3, 224, 224)), ((1000, 250), (1, 3, 224, 448)), ((40, 30), (1, 3, 224, 294))],
)
def test_photo_preparee_pour_le_modele(taille, forme):
    from PIL import Image

    pixels = preparer_pour_le_modele(Image.new("RGB", taille, (124, 116, 104)))
    assert pixels.shape == forme and pixels.dtype == np.float32
    # Une photo de la couleur moyenne des photos d'apprentissage donne des valeurs proches de 0.
    assert np.abs(pixels).max() < 0.02


def test_le_calcul_ne_charge_pas_onnx_runtime_sans_ia():
    """La méthode sans IA, la page et le démarrage de l'app n'ont jamais besoin d'ONNX Runtime."""
    code = (
        "import sys\n"
        "import ugc_studio.doublons.analyse, ugc_studio.doublons.copies, ugc_studio.doublons.paires\n"
        "import ugc_studio.doublons.vision\n"
        "print('onnxruntime' in sys.modules)\n"
    )
    sortie = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env={**os.environ, "PYTHONUTF8": "1"})
    assert sortie.stdout.strip() == "False"


def test_telemetrie_d_onnx_runtime_coupee():
    """ONNX Runtime envoie par défaut des statistiques à Microsoft : la variable qui l'en empêche est posée
    avant qu'il démarre (vérifié le 11/10/2026 : sans elle, il tente de joindre ses serveurs)."""
    code = (
        "import os\n"
        "os.environ.pop('ORT_DISABLE_TELEMETRY', None)\n"
        "from ugc_studio.doublons.vision import importer_onnxruntime\n"
        "importer_onnxruntime()\n"
        "print(os.environ.get('ORT_DISABLE_TELEMETRY'))\n"
    )
    sortie = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, env={**os.environ, "PYTHONUTF8": "1"})
    assert sortie.stdout.strip().splitlines()[-1] == "1"


def test_modele_abime_refuse(tmp_path, monkeypatch):
    abime = tmp_path / "model_quantized.onnx"
    abime.write_bytes(b"0" * 1000)
    monkeypatch.setattr(vision, "fichier_du_modele", lambda modele=None: abime)
    with pytest.raises(ErreurModele, match="abîmé"):
        vision.octets_du_modele()
    monkeypatch.setattr(vision, "fichier_du_modele", lambda modele=None: tmp_path / "absent.onnx")
    with pytest.raises(ErreurModele, match="introuvable"):
        vision.octets_du_modele()


@avec_le_modele
def test_le_vrai_modele_retrouve_les_copies():
    attendu = MODELES[MODELE_DE_L_APP].principal
    assert len(vision.octets_du_modele()) == attendu.taille
    modele = vision.Descripteur()
    originale = photo_factice(1)
    debut = time.perf_counter()
    empreinte = modele.decrire(originale)
    duree = time.perf_counter() - debut
    print(f"Une photo décrite par le modèle (droite et retournée) en {duree * 1000:.0f} ms")
    assert empreinte.shape == (768,) and empreinte.dtype == np.float32
    assert abs(float(np.linalg.norm(empreinte)) - 1) < 1e-5
    # Une photo et sa copie retournée ont la même empreinte.
    assert float(empreinte @ modele.decrire(miroir(originale))) > 0.999
    autre = float(empreinte @ modele.decrire(photo_factice(2)))
    for copie in (plus_petite(originale), autres_couleurs(originale)):
        proximite = float(empreinte @ modele.decrire(copie))
        assert proximite > 0.9 and proximite > autre + 0.05
