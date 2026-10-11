"""L'IA de Doublons (V4.3) : l'empreinte visuelle de chaque photo, une liste de 768 nombres.

Le modèle : DINOv2 « small » de Meta (licence Apache 2.0), au format ONNX, version compacte (voir
modeles.py), qui tourne sur le processeur avec ONNX Runtime (Microsoft, licence MIT). Rien ne part sur
internet : ni les photos, ni rien d'autre. ONNX Runtime envoie par défaut des statistiques d'utilisation
à Microsoft (sa « télémétrie », vérifié le 11/10/2026 sur la version 1.30.0) : l'app la coupe avant de
le charger.

Comment une photo est décrite (réglé le 11/10/2026 sur le lot de l'utilisateur et sur ses photos
déclinées : document « UGC Studio - V4.3 Doublons », §9) :
- ses bords unis sont retirés (une photo mise au carré avec des bords blancs reste la même photo) ;
- elle est vue en entier, à 224 pixels de petit côté, ses proportions gardées (un multiple de 14 pixels,
  la taille des carreaux que le modèle regarde) : rien n'est coupé ;
- le modèle en tire un résumé global et la moyenne de ce qu'il voit dans chaque carreau, mis bout à
  bout ;
- la photo est décrite droite et retournée, et les deux résumés sont additionnés : une photo et sa
  copie retournée en miroir ont exactement la même empreinte.
Deux empreintes se comparent par leur « cosinus » : 1 pour deux photos que le modèle voit identiques,
autour de 0,5 pour deux photos sans rapport (sur ce lot).
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from ..chemins import dossier_ressources
from ..ressource_du_exe import lire_la_ressource
from .copies import rogner_bords_unis
from .modeles import MODELE_DE_L_APP, MODELES, NOM_DE_RESSOURCE, Modele

COTE = 224  # petit côté de la photo vue par le modèle
CARREAU = 14  # DINOv2 regarde des carreaux de 14 × 14 pixels
GRAND_COTE_MAX = 2 * COTE  # au-delà (photo très allongée), elle est un peu écrasée
MOYENNE = np.array([0.485, 0.456, 0.406], dtype=np.float32)  # couleurs moyennes des photos d'apprentissage
ECART_TYPE = np.array([0.229, 0.224, 0.225], dtype=np.float32)
TAILLE_EMPREINTE = 768

DOSSIER_MODELES = "modeles"  # dans les ressources de l'app (tests, développement)


class ErreurModele(Exception):
    """Le modèle d'IA n'a pas pu être préparé (message clair, montré à l'utilisateur)."""


def fichier_du_modele(modele: Modele | None = None) -> Path:
    """Où le modèle est rangé à côté du code (tests et développement, après outils/preparer_modeles.py)."""
    modele = modele or MODELES[MODELE_DE_L_APP]
    return dossier_ressources() / DOSSIER_MODELES / modele.nom / modele.principal.nom


def octets_du_modele() -> bytes:
    """Le fichier du modèle de l'app : dans le .exe, sa ressource ; sinon, le fichier à côté du code.
    Sa taille et son empreinte sont vérifiées : un modèle abîmé n'est jamais utilisé."""
    attendu = MODELES[MODELE_DE_L_APP].principal
    octets = lire_la_ressource(NOM_DE_RESSOURCE)
    if octets is None:
        chemin = fichier_du_modele()
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            raise ErreurModele("le modèle d'IA est introuvable dans l'app")
        try:
            octets = chemin.read_bytes()
        except OSError as erreur:
            raise ErreurModele(f"le modèle d'IA est introuvable ({chemin})") from erreur
    if len(octets) != attendu.taille or hashlib.sha256(octets).hexdigest() != attendu.empreinte:
        raise ErreurModele("le modèle d'IA contenu dans l'app est abîmé (empreinte inattendue)")
    return octets


def importer_onnxruntime():
    """ONNX Runtime, chargé seulement quand on en a besoin, sa télémétrie coupée : la variable
    ORT_DISABLE_TELEMETRY doit être posée avant qu'il démarre (vérifié : sans elle, il tente de joindre
    les serveurs de Microsoft ; avec elle, il ne le fait plus), et sa fonction disable_telemetry_events
    coupe celle de Windows."""
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    import onnxruntime

    try:
        onnxruntime.disable_telemetry_events()
    except Exception:  # noqa: BLE001 : absente d'une autre version : la variable suffit
        pass
    return onnxruntime


def preparer_pour_le_modele(image: Image.Image) -> np.ndarray:
    """La photo (RGB) au format attendu par le modèle : 224 pixels de petit côté, proportions gardées,
    côtés multiples de 14 ; couleurs centrées réduites ; tableau 1 × 3 × hauteur × largeur."""
    largeur, hauteur = image.size
    echelle = COTE / min(largeur, hauteur)
    nouvelle_largeur = min(max(round(largeur * echelle / CARREAU) * CARREAU, CARREAU), GRAND_COTE_MAX)
    nouvelle_hauteur = min(max(round(hauteur * echelle / CARREAU) * CARREAU, CARREAU), GRAND_COTE_MAX)
    image = image.resize((nouvelle_largeur, nouvelle_hauteur), Image.Resampling.BICUBIC)
    pixels = (np.asarray(image, dtype=np.float32) / 255.0 - MOYENNE) / ECART_TYPE
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[None])


def _normee(vecteur: np.ndarray) -> np.ndarray:
    norme = float(np.linalg.norm(vecteur))
    return vecteur / norme if norme > 1e-12 else vecteur


class Descripteur:
    """Le modèle prêt à décrire des photos. Le créer prend environ une seconde ; une seule fois par
    séance (descripteur())."""

    def __init__(self, octets: bytes | None = None):
        ort = importer_onnxruntime()
        options = ort.SessionOptions()
        options.log_severity_level = 3  # erreurs seulement
        self._session = ort.InferenceSession(octets if octets is not None else octets_du_modele(), options, providers=["CPUExecutionProvider"])
        self._entree = self._session.get_inputs()[0].name

    def _resume(self, image: Image.Image) -> np.ndarray:
        pixels = preparer_pour_le_modele(image)
        etat = self._session.run(None, {self._entree: pixels})[0][0]
        carreaux = (pixels.shape[2] // CARREAU) * (pixels.shape[3] // CARREAU)
        global_, details = etat[0], etat[etat.shape[0] - carreaux :].mean(axis=0)
        return np.concatenate([_normee(global_), _normee(details)])

    def decrire(self, image: Image.Image) -> np.ndarray:
        """L'empreinte visuelle de la photo (RGB, dans le bon sens) : 768 nombres, de longueur 1."""
        rognee, _bords = rogner_bords_unis(image)
        droite = self._resume(rognee)
        retournee = self._resume(rognee.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
        return _normee(droite + retournee).astype(np.float32)


_descripteur: Descripteur | None = None
_creation = threading.Lock()


def descripteur() -> Descripteur:
    """Le modèle de l'app, créé à la première demande puis gardé pour la séance. Lance ErreurModele si le
    modèle est introuvable ou abîmé."""
    global _descripteur
    with _creation:
        if _descripteur is None:
            _descripteur = Descripteur()
        return _descripteur
