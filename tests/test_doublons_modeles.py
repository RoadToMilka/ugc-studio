"""Doublons (V4.3) : le catalogue des modèles d'IA et leur préparation par la fabrication."""

import re
import subprocess
import sys
from pathlib import Path

from ugc_studio.doublons.modeles import MODELE_DE_L_APP, MODELES, MODELES_D_ESSAI, cle_des_modeles

RACINE = Path(__file__).resolve().parents[1]
COMMIT = re.compile(r"^[0-9a-f]{40}$")
EMPREINTE = re.compile(r"^[0-9a-f]{64}$")


def test_catalogue_fige():
    assert MODELE_DE_L_APP in MODELES and set(MODELES_D_ESSAI) <= set(MODELES)
    for modele in MODELES.values():
        assert COMMIT.match(modele.revision), modele.nom  # une version figée : son contenu ne peut plus changer
        assert modele.fichiers and all(EMPREINTE.match(f.empreinte) and f.taille > 0 for f in modele.fichiers)
        assert modele.adresse(modele.principal).startswith(f"https://huggingface.co/{modele.depot}/resolve/{modele.revision}/")
        licence = modele.texte_de_licence
        assert EMPREINTE.match(licence.empreinte)
        assert re.search(r"/[0-9a-f]{40}/", licence.adresse), licence.adresse  # texte de la licence, version figée lui aussi
    assert MODELES[MODELE_DE_L_APP].licence == "Apache 2.0"


def test_cle_des_modeles():
    tous = [MODELE_DE_L_APP, *MODELES_D_ESSAI]
    assert re.match(r"^[0-9a-f]{12}$", cle_des_modeles(tous))
    assert cle_des_modeles(tous) == cle_des_modeles(list(reversed(tous)))
    assert cle_des_modeles(tous) != cle_des_modeles([MODELE_DE_L_APP])


def test_preparer_modeles_donne_la_cle():
    sortie = subprocess.run([sys.executable, str(RACINE / "outils" / "preparer_modeles.py"), "--essai", "--cle"], capture_output=True, text=True, check=True)
    assert sortie.stdout.strip() == cle_des_modeles([MODELE_DE_L_APP, *MODELES_D_ESSAI])


def test_licence_du_modele_de_l_app_jointe_a_l_app():
    """Le texte de la licence du modèle de l'app (Apache 2.0) est joint à l'app, tel que publié par Meta
    à la version notée dans le catalogue (la page « À propos » le montre dans Réglages)."""
    from ugc_studio.chemins import dossier_ressources
    from ugc_studio.doublons.modeles import empreinte_du_fichier

    dossier = dossier_ressources() / "modeles"
    licence = MODELES[MODELE_DE_L_APP].texte_de_licence
    assert empreinte_du_fichier(dossier / licence.nom) == licence.empreinte
    a_propos = (dossier / "A-PROPOS.txt").read_text(encoding="utf-8")
    modele = MODELES[MODELE_DE_L_APP]
    assert modele.revision in a_propos and modele.principal.empreinte in a_propos and licence.nom in a_propos
