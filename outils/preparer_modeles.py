"""Prépare les modèles d'IA du module Doublons (V4.3) : lancé par la fabrication automatique, jamais par
l'utilisateur.

1. Télécharge chaque fichier du modèle depuis sa page Hugging Face, à une version figée (un « commit » :
   son contenu ne peut plus changer), et le texte de sa licence depuis la page de ses auteurs (Meta, sur
   GitHub), sauf s'ils sont déjà dans le cache (outils/cache-modeles).
2. Vérifie leur empreinte SHA-256 (et la taille quand elle est notée) : un fichier abîmé ou modifié
   aurait une autre empreinte et serait refusé (la fabrication s'arrête).
3. Les copie dans ugc_studio/ressources/modeles/<modèle>/, pour les tests automatiques. La recette du
   .exe (packaging/ugc_studio.spec) ne prend pas cette copie.

Sans option : le modèle de l'app seulement. « --essai » : aussi les modèles d'essai (DINOv3, version
complète de DINOv2), pour les comparer (document « UGC Studio - V4.3 Doublons », §2.6).
« --assembler <dossier> » : range aussi ces modèles, leurs licences et un LISEZ-MOI dans ce dossier, que
la fabrication dépose ensuite dans une référence Git cachée, pour les essais de Claude sur les photos de
l'utilisateur (son espace de travail n'a pas accès à Hugging Face, mais a accès à GitHub).
« --cle » : affiche seulement le court code qui résume ces modèles (le nom de ce dépôt).

Les modèles ne changent que quand on le décide : en modifiant ugc_studio/doublons/modeles.py.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from ugc_studio.doublons.modeles import (  # noqa: E402
    MODELE_DE_L_APP,
    MODELES,
    MODELES_D_ESSAI,
    Modele,
    cle_des_modeles,
    empreinte_du_fichier,
)

CACHE = RACINE / "outils" / "cache-modeles"
DESTINATION = RACINE / "ugc_studio" / "ressources" / "modeles"
DELAI_S = 300


def conforme(chemin: Path, empreinte: str, taille: int = 0) -> bool:
    if not chemin.is_file():
        return False
    if taille and chemin.stat().st_size != taille:
        return False
    return empreinte_du_fichier(chemin) == empreinte


def telecharger(adresse: str, cible: Path) -> None:
    print(f"Téléchargement de {adresse}")
    cible.parent.mkdir(parents=True, exist_ok=True)
    demande = urllib.request.Request(adresse, headers={"User-Agent": "UGC-Studio-fabrication"})
    with tempfile.NamedTemporaryFile(dir=cible.parent, delete=False) as provisoire:
        with urllib.request.urlopen(demande, timeout=DELAI_S) as reponse:  # noqa: S310 (adresse fixe, https)
            shutil.copyfileobj(reponse, provisoire)
    Path(provisoire.name).replace(cible)


def obtenir(adresse: str, en_cache: Path, empreinte: str, taille: int, quoi: str) -> bool:
    """Le fichier dans le cache, téléchargé si besoin, puis vérifié. False (et message) s'il est refusé."""
    if not conforme(en_cache, empreinte, taille):
        telecharger(adresse, en_cache)
    trouvee = empreinte_du_fichier(en_cache)
    if trouvee != empreinte:
        en_cache.unlink(missing_ok=True)
        print(f"{quoi} : empreinte inattendue {trouvee} (attendue : {empreinte}). Refusé.", file=sys.stderr)
        return False
    octets = en_cache.stat().st_size
    if taille and octets != taille:
        en_cache.unlink(missing_ok=True)
        print(f"{quoi} : taille inattendue {octets} (attendue : {taille}). Refusé.", file=sys.stderr)
        return False
    print(f"{quoi} : prêt ({octets} octets, {octets / 1024**2:.1f} Mo), empreinte {trouvee} vérifiée.")
    return True


def preparer(modele: Modele) -> bool:
    """Le modèle et sa licence dans le cache (téléchargés si besoin) et dans les ressources, vérifiés.
    False s'il est refusé."""
    a_copier: list[tuple[str, str]] = []
    for fichier in modele.fichiers:
        if not obtenir(modele.adresse(fichier), CACHE / modele.nom / fichier.nom, fichier.empreinte, fichier.taille, f"{modele.nom}, {fichier.chemin}"):
            return False
        a_copier.append((fichier.nom, fichier.empreinte))
    licence = modele.texte_de_licence
    if not obtenir(licence.adresse, CACHE / modele.nom / licence.nom, licence.empreinte, 0, f"{modele.nom}, {licence.nom}"):
        return False
    a_copier.append((licence.nom, licence.empreinte))
    for nom, empreinte in a_copier:
        copie = DESTINATION / modele.nom / nom
        if not conforme(copie, empreinte):
            copie.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(CACHE / modele.nom / nom, copie)
    return True


def assembler(noms: list[str], dossier: Path) -> None:
    """Range les modèles préparés (cache), leurs licences et un LISEZ-MOI dans ce dossier."""
    dossier.mkdir(parents=True, exist_ok=True)
    lignes = [
        "Modèles d'IA du module Doublons d'UGC Studio (V4.3), pour les essais de Claude",
        "",
        "Déposés par la fabrication automatique : chaque fichier a été téléchargé depuis sa page officielle,",
        "à une version figée, et son empreinte SHA-256 vérifiée (outils/preparer_modeles.py). Chaque modèle",
        "est accompagné du texte de sa licence, comme elle le demande.",
        f"Code de ce jeu de modèles : {cle_des_modeles(noms)}",
        "",
    ]
    for nom in noms:
        modele = MODELES[nom]
        cible = dossier / modele.nom
        cible.mkdir(parents=True, exist_ok=True)
        lignes += [f"{modele.nom} : {modele.description}", f"  Licence : {modele.licence} (texte : {modele.nom}/{modele.texte_de_licence.nom}, depuis {modele.texte_de_licence.adresse})"]
        for fichier in modele.fichiers:
            shutil.copyfile(CACHE / modele.nom / fichier.nom, cible / fichier.nom)
            octets = (cible / fichier.nom).stat().st_size
            lignes.append(f"  {modele.nom}/{fichier.nom} : {octets} octets, SHA-256 {fichier.empreinte}, depuis {modele.adresse(fichier)}")
        shutil.copyfile(CACHE / modele.nom / modele.texte_de_licence.nom, cible / modele.texte_de_licence.nom)
        lignes.append("")
    (dossier / "LISEZ-MOI.txt").write_text("\n".join(lignes), encoding="utf-8")
    print(f"Assemblés dans {dossier}.")


def main() -> int:
    analyse = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyse.add_argument("--essai", action="store_true", help="aussi les modèles d'essai")
    analyse.add_argument("--cle", action="store_true", help="affiche seulement le code qui résume ces modèles")
    analyse.add_argument("--assembler", type=Path, metavar="DOSSIER", help="range aussi les modèles et leurs licences dans ce dossier")
    options = analyse.parse_args()
    noms = [MODELE_DE_L_APP, *(MODELES_D_ESSAI if options.essai else ())]
    if options.cle:
        print(cle_des_modeles(noms))
        return 0
    for nom in noms:
        if not preparer(MODELES[nom]):
            return 1
    if options.assembler:
        assembler(noms, options.assembler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
