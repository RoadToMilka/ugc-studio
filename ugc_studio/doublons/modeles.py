"""Les modèles d'IA du module Doublons (V4.3) : quels fichiers, d'où, et leur empreinte.

Un modèle de vision résume chaque photo en une « empreinte visuelle » (une liste de 384 nombres) :
deux photos du même objet ont des empreintes proches. Le modèle de l'app est DINOv2 « small », de
Meta (licence Apache 2.0), au format ONNX, celui que lit ONNX Runtime : la conversion publiée par
Hugging Face (« onnx-community/dinov2-small ») du modèle officiel « facebook/dinov2-small ».

Les fichiers ne sont jamais enregistrés avec le code : la fabrication automatique les télécharge
(outils/preparer_modeles.py) depuis une version figée de leur page (le « commit » ci-dessous : son
contenu ne peut plus changer), avec le texte de leur licence, vérifie leur empreinte SHA-256, puis
range le modèle de l'app dans le .exe. Les autres ne servent qu'aux essais (DINOv3, version complète
de DINOv2 : document V4.3, §2.6).

Ce fichier ne dépend d'aucune bibliothèque : la préparation le lit avant d'avoir installé quoi que ce
soit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

ADRESSE_DES_FICHIERS = "https://huggingface.co/{depot}/resolve/{revision}/{chemin}"


@dataclass(frozen=True)
class FichierDuModele:
    """Un fichier d'un modèle : son chemin sur sa page Hugging Face, son empreinte SHA-256 et sa taille
    en octets (0 : pas encore notée, l'empreinte suffit)."""

    chemin: str
    empreinte: str
    taille: int = 0

    @property
    def nom(self) -> str:
        return self.chemin.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class TexteDeLicence:
    """Le texte de la licence d'un modèle, pris sur la page officielle de ses auteurs à une version figée,
    avec son empreinte SHA-256, et le nom du fichier rangé à côté du modèle."""

    adresse: str
    empreinte: str
    nom: str


@dataclass(frozen=True)
class Modele:
    """Un modèle : son nom dans l'app, sa page Hugging Face (dépôt et version figée), ses fichiers (le
    premier est celui qu'on ouvre ; un modèle peut ranger ses réglages dans un second fichier, à côté)
    et sa licence (son nom et son texte)."""

    nom: str
    depot: str
    revision: str
    fichiers: tuple[FichierDuModele, ...]
    licence: str
    texte_de_licence: TexteDeLicence
    description: str

    @property
    def principal(self) -> FichierDuModele:
        return self.fichiers[0]

    def adresse(self, fichier: FichierDuModele) -> str:
        return ADRESSE_DES_FICHIERS.format(depot=self.depot, revision=self.revision, chemin=fichier.chemin)


DEPOT_DINOV2 = "onnx-community/dinov2-small"
REVISION_DINOV2 = "ef1fb1005bfd7768839d18080f7038b403506f87"  # page lue le 11/10/2026
DEPOT_DINOV3 = "onnx-community/dinov3-vits16-pretrain-lvd1689m-ONNX"
REVISION_DINOV3 = "48988dfe73065df8d6f5ccc0edc7c8bcf307de41"  # page lue le 11/10/2026

# Les textes des licences, sur les pages officielles de Meta (GitHub), aux versions du 11/10/2026.
LICENCE_DINOV2 = TexteDeLicence(
    "https://raw.githubusercontent.com/facebookresearch/dinov2/7764ea0f912e53c92e82eb78a2a1631e92725fc8/LICENSE",
    "600cc67cc4cb2f5ea317dcfc687ad1c74dc4bec8782bbe9db0afd83513b935b7",
    "LICENCE-DINOv2.txt",
)
LICENCE_DINOV3 = TexteDeLicence(
    "https://raw.githubusercontent.com/facebookresearch/dinov3/6876159a11b4df116f30f667f8c9888617df0751/LICENSE.md",
    "25d122eb8f5b880fd23c736fb6ea8018ee45c12237e00b8a86d14c653904999e",
    "LICENCE-DINOv3.md",
)

MODELES: dict[str, Modele] = {
    modele.nom: modele
    for modele in (
        Modele(
            "dinov2-small-q8",
            DEPOT_DINOV2,
            REVISION_DINOV2,
            (FichierDuModele("onnx/model_quantized.onnx", "c179f8f7f592449c4c1bca4cd124a7538021428c5ffb89afde9503935b197efb"),),
            "Apache 2.0",
            LICENCE_DINOV2,
            "DINOv2 small (Meta), version compacte : chaque réglage sur 1 octet au lieu de 4",
        ),
        Modele(
            "dinov2-small-fp32",
            DEPOT_DINOV2,
            REVISION_DINOV2,
            (FichierDuModele("onnx/model.onnx", "f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a"),),
            "Apache 2.0",
            LICENCE_DINOV2,
            "DINOv2 small (Meta), version complète",
        ),
        Modele(
            "dinov3-small-q8",
            DEPOT_DINOV3,
            REVISION_DINOV3,
            (
                FichierDuModele("onnx/model_quantized.onnx", "7686e8c849202c4fdd67d1cd336449c29bdddbcca535d765d3014f50d04d516d"),
                FichierDuModele("onnx/model_quantized.onnx_data", "51572f7fc3c272eb574a70509ea1eeb7e674e5ca2cd96fec1632edb38983d529"),
            ),
            "DINOv3 License (Meta)",
            LICENCE_DINOV3,
            "DINOv3 small (Meta), version compacte : essai seulement (document V4.3, §2.6)",
        ),
    )
}

# Le modèle rangé dans le .exe (V4.3, lot 1 : choisi après l'essai sur des photos de test et sur le lot
# de l'utilisateur ; voir le cahier des charges, §8 bis.5).
MODELE_DE_L_APP = "dinov2-small-q8"
# Les modèles d'essai : préparés seulement sur demande (outils/preparer_modeles.py --essai).
MODELES_D_ESSAI = ("dinov2-small-fp32", "dinov3-small-q8")


def empreinte_du_fichier(chemin) -> str:
    """Empreinte SHA-256 d'un fichier, lu par morceaux (peu de mémoire, même pour 90 Mo)."""
    calcul = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for morceau in iter(lambda: fichier.read(1024 * 1024), b""):
            calcul.update(morceau)
    return calcul.hexdigest()


def cle_des_modeles(noms) -> str:
    """Un court code qui résume ces modèles (noms, pages, versions et empreintes) : il change dès que
    l'un d'eux change. Sert à nommer le cache de la fabrication et le dépôt des modèles pour les essais."""
    texte = "\n".join(
        f"{modele.nom} {modele.depot} {modele.revision} "
        + " ".join(f"{f.chemin}={f.empreinte}" for f in modele.fichiers)
        + f" {modele.texte_de_licence.nom}={modele.texte_de_licence.empreinte}"
        for modele in (MODELES[nom] for nom in sorted(noms))
    )
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:12]
