"""Transcription (§6) : le texte d'une vidéo ou d'un audio, mot par mot, avec le moment où chaque
mot est prononcé.

- `Mot` : un mot et ses temps (en secondes), avec la personne qui parle si les voix sont séparées.
- `Transcription` : la source (vidéo ou audio importé), les options, le texte et les mots.
- Corrections dans l'éditeur (§6.4) : corriger l'orthographe d'un mot sans perdre son timing,
  fusionner, couper, supprimer, ajuster le début et la fin.
- Dictionnaire de remplacements (§6.3) : « sérum anti rides » → « Sérum Anti-Rides® »,
  appliqué après chaque transcription (les mots remplacés gardent leurs temps).
- Hésitations (« euh », « hum »…) : repérées pour être masquées dans les sous-titres ; l'audio
  et les temps des autres mots ne changent pas.
- Sous-titres réorganisés à la main (V1.1) : rangés avec les mots qu'ils regroupent, repérés par
  le temps (voir sous_titres.Ajustement).

Ce module ne dépend pas de l'interface : il est testé seul.
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .stockage import ecrire_json, lire_json

DUREE_MOT_MIN = 0.02  # secondes : un mot dure au moins 20 ms après un ajustement
PONCTUATION = ".,;:!?…«»\"'“”‘’()[]{}-–—/"
MODE_VERBATIM = "verbatim"  # mot à mot, avec les temps (indispensable pour les sous-titres)
MODE_SMART = "smart"  # texte nettoyé, sans temps (ex. recopier le script d'une vidéo)

# Hésitations proposées au départ, par langue (liste modifiable dans l'app).
HESITATIONS_PAR_DEFAUT: dict[str, tuple[str, ...]] = {
    "fr": ("euh", "heu", "euhm", "hum", "hmm", "mmh", "mh", "bah"),
    "en": ("uh", "um", "uhm", "er", "erm", "hmm", "mm", "mhm"),
    "es": ("eh", "em", "ehm", "mmm"),
    "it": ("eh", "ehm", "mmm"),
    "nl": ("eh", "uh", "uhm", "ehm", "hmm"),
    "de": ("äh", "ähm", "öh", "hm", "hmm"),
}


@dataclass
class Mot:
    texte: str
    debut: float  # secondes depuis le début de l'audio
    fin: float
    locuteur: str = ""  # « spk_1 », « spk_2 »… quand les voix sont séparées

    @property
    def duree(self) -> float:
        return max(0.0, self.fin - self.debut)


@dataclass
class Transcription:
    source: str = ""  # vidéo ou audio importé (chemin sur l'ordinateur ; le fichier n'est pas copié)
    audio: str = ""  # piste son extraite, dans le dossier du projet (ex. « sources/audio.wav »)
    duree_s: float = 0.0
    infos: dict = field(default_factory=dict)  # infos de la source : résolution, images/s, codecs…
    modele: str = ""
    langue: str = ""  # code BCP-47 ; vide = détection automatique
    separation_voix: bool = False
    mode: str = MODE_VERBATIM
    texte: str = ""  # texte complet (seul résultat en mode « smart »)
    mots: list[Mot] = field(default_factory=list)
    date: str = ""
    cout_eur: str | None = None
    masquer_hesitations: bool = True  # dans les sous-titres (§6.3)
    # Prise TTS transcrite pour créer ses sous-titres (§3.3) : les mots transcrits sont alignés
    # sur le script de la prise (son orthographe exacte), à chaque transcription.
    prise: str = ""  # identifiant de la prise
    script: str = ""  # texte du script (sans balises)
    # Sous-titres réorganisés à la main (V1.1, §7.8) : pour chacun, [début, fin] en secondes (début
    # de son premier mot, fin de son dernier mot). Repérés par le temps, ils suivent les mots
    # corrigés ; une nouvelle transcription les efface.
    ajustements_sous_titres: list[list[float]] = field(default_factory=list)

    @property
    def horodatee(self) -> bool:
        """Transcription utilisable pour des sous-titres (des mots avec leurs temps) ?"""
        return bool(self.mots)

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, brut: dict) -> Transcription:
        champs = {
            k: v for k, v in brut.items() if k in cls.__dataclass_fields__ and k not in ("mots", "ajustements_sous_titres")
        }
        mots = [
            Mot(str(m.get("texte", "")), float(m.get("debut", 0)), float(m.get("fin", 0)), str(m.get("locuteur", "")))
            for m in brut.get("mots") or []
            if isinstance(m, dict)
        ]
        transcription = cls(**champs)
        transcription.mots = mots
        transcription.ajustements_sous_titres = _ajustements_lisibles(brut.get("ajustements_sous_titres"))
        if not isinstance(transcription.infos, dict):
            transcription.infos = {}
        return transcription


def _ajustements_lisibles(brut) -> list[list[float]]:
    """Ajustements relus dans un projet : les paires [début, fin] illisibles sont ignorées (un
    projet de la v1.0 n'en a aucun)."""
    ajustements = []
    for paire in brut if isinstance(brut, list) else []:
        if not (isinstance(paire, list | tuple) and len(paire) == 2):
            continue
        if any(isinstance(v, bool) or not isinstance(v, int | float) for v in paire):
            continue
        debut, fin = float(paire[0]), float(paire[1])
        if math.isfinite(debut) and math.isfinite(fin) and debut <= fin:
            ajustements.append([debut, fin])
    return ajustements


def resolution_video(infos: dict) -> tuple[int, int] | None:
    """Largeur × hauteur de la vidéo source, telle qu'elle s'affiche. Une vidéo de téléphone
    filmée à la verticale est souvent enregistrée « couchée » avec une rotation de 90° : ses
    dimensions sont alors remises dans le bon sens (1920 × 1080 → 1080 × 1920)."""
    brut = infos.get("resolution") if isinstance(infos, dict) else None
    if not (isinstance(brut, list | tuple) and len(brut) == 2):
        return None
    try:
        largeur, hauteur = int(brut[0]), int(brut[1])
        rotation = int(float(infos.get("rotation") or 0))
    except (TypeError, ValueError):
        return None
    if largeur <= 0 or hauteur <= 0:
        return None
    if rotation % 180 == 90:
        largeur, hauteur = hauteur, largeur
    return largeur, hauteur


# --- Lecture synchronisée -----------------------------------------------------------------------


def index_au_temps(mots: list[Mot], temps: float) -> int:
    """Indice du mot prononcé à ce moment (-1 s'il n'y en a pas : silence, avant le début…)."""
    debuts = [m.debut for m in mots]
    index = bisect.bisect_right(debuts, temps) - 1
    if 0 <= index < len(mots) and temps < mots[index].fin:
        return index
    return -1


def texte_complet(mots: list[Mot]) -> str:
    return " ".join(m.texte for m in mots)


# --- Corrections dans l'éditeur (§6.4) -----------------------------------------------------------


def corriger(mots: list[Mot], index: int, texte: str) -> None:
    """Change l'orthographe d'un mot ; ses temps ne bougent pas."""
    texte = " ".join(texte.split())
    if not texte:
        raise ValueError("Un mot ne peut pas être vide : utilise « Supprimer ».")
    mots[index].texte = texte


def fusionner(mots: list[Mot], index: int) -> None:
    """Réunit un mot et le suivant (ex. « Glow » + « zy » coupé par erreur) : un seul mot, du début
    du premier à la fin du second. Le texte réuni garde l'espace ; on peut le corriger ensuite."""
    if not 0 <= index < len(mots) - 1:
        return
    premier, second = mots[index], mots[index + 1]
    mots[index] = Mot(f"{premier.texte} {second.texte}", premier.debut, max(premier.fin, second.fin), premier.locuteur)
    del mots[index + 1]


def couper(mots: list[Mot], index: int, position: int | None = None) -> None:
    """Coupe un mot en deux à la position donnée (par défaut : à l'espace, ou au milieu). Le temps
    est partagé selon le nombre de lettres de chaque morceau."""
    mot = mots[index]
    texte = mot.texte
    if position is None:
        espace = texte.find(" ")
        position = espace if espace > 0 else len(texte) // 2
    gauche, droite = texte[:position].strip(), texte[position:].strip()
    if not gauche or not droite:
        raise ValueError("Ce mot est trop court pour être coupé à cet endroit.")
    part = len(gauche) / (len(gauche) + len(droite))
    milieu = mot.debut + (mot.fin - mot.debut) * part
    mots[index : index + 1] = [
        Mot(gauche, mot.debut, milieu, mot.locuteur),
        Mot(droite, milieu, mot.fin, mot.locuteur),
    ]


def supprimer(mots: list[Mot], index: int) -> None:
    """Retire un mot (ex. un bruit transcrit par erreur)."""
    if 0 <= index < len(mots):
        del mots[index]


def ajuster(mots: list[Mot], index: int, debut: float, fin: float, duree: float | None = None) -> None:
    """Change le début et la fin d'un mot. Les voisins sont raccourcis s'ils le chevauchent, sans
    jamais descendre sous 20 ms ; le mot reste entre le début du précédent et la fin du suivant."""
    precedent = mots[index - 1] if index > 0 else None
    suivant = mots[index + 1] if index + 1 < len(mots) else None
    minimum = precedent.debut + DUREE_MOT_MIN if precedent else 0.0
    maximum = suivant.fin - DUREE_MOT_MIN if suivant else (duree if duree else max(fin, debut) + DUREE_MOT_MIN)
    debut = min(max(debut, minimum), maximum - DUREE_MOT_MIN)
    fin = max(min(fin, maximum), debut + DUREE_MOT_MIN)
    mots[index].debut, mots[index].fin = round(debut, 3), round(fin, 3)
    if precedent and precedent.fin > debut:
        precedent.fin = round(debut, 3)
    if suivant and suivant.debut < fin:
        suivant.debut = round(fin, 3)


# --- Dictionnaire de remplacements (§6.3) ----------------------------------------------------------


@dataclass
class Remplacement:
    cherche: str  # tel que transcrit, un ou plusieurs mots (ex. « sérum anti rides »)
    remplace: str  # ce qu'on veut lire (ex. « Sérum Anti-Rides® »)


def nettoyer_remplacements(entrees: list[Remplacement]) -> list[Remplacement]:
    """Retire les entrées vides et les doublons (le dernier gagne)."""
    par_cle: dict[str, Remplacement] = {}
    for entree in entrees:
        cherche, remplace = " ".join(entree.cherche.split()), " ".join(entree.remplace.split())
        if cherche and remplace:
            par_cle[cherche.casefold()] = Remplacement(cherche, remplace)
    return list(par_cle.values())


def fusionner_remplacements(globales: list[Remplacement], projet: list[Remplacement]) -> list[Remplacement]:
    """Dictionnaire global + dictionnaire du projet (le projet l'emporte pour une même entrée)."""
    return nettoyer_remplacements([*globales, *projet])


def cle_de_mot(texte: str) -> str:
    """Forme comparable d'un mot : minuscules, sans la ponctuation collée autour."""
    return texte.strip(PONCTUATION + " ").casefold()


def appliquer_remplacements(mots: list[Mot], entrees: list[Remplacement]) -> list[Mot]:
    """Remplace les suites de mots du dictionnaire (sans tenir compte des majuscules ni de la
    ponctuation collée). Le mot obtenu va du début du premier mot à la fin du dernier ; la
    ponctuation qui suivait le dernier mot est gardée. Les entrées les plus longues passent
    d'abord (« sérum anti rides » avant « sérum »)."""
    regles = []
    for entree in nettoyer_remplacements(entrees):
        cles = [cle_de_mot(m) for m in entree.cherche.split()]
        cles = [c for c in cles if c]
        if cles:
            regles.append((cles, entree.remplace))
    regles.sort(key=lambda regle: len(regle[0]), reverse=True)
    resultat: list[Mot] = []
    index = 0
    while index < len(mots):
        for cles, remplace in regles:
            morceau = mots[index : index + len(cles)]
            if len(morceau) == len(cles) and all(cle_de_mot(m.texte) == c for m, c in zip(morceau, cles, strict=True)):
                dernier = morceau[-1].texte
                ponctuation = dernier[len(dernier.rstrip(PONCTUATION)) :] if dernier.rstrip(PONCTUATION) else ""
                resultat.append(Mot(remplace + ponctuation, morceau[0].debut, morceau[-1].fin, morceau[0].locuteur))
                index += len(cles)
                break
        else:
            mot = mots[index]
            resultat.append(Mot(mot.texte, mot.debut, mot.fin, mot.locuteur))
            index += 1
    return resultat


def remplacements_depuis_liste(brutes: list) -> list[Remplacement]:
    return nettoyer_remplacements(
        [Remplacement(str(e.get("cherche", "")), str(e.get("remplace", ""))) for e in brutes or [] if isinstance(e, dict)]
    )


class DictionnaireRemplacements:
    """Remplacements communs à tous les projets, dans %APPDATA%\\UGC Studio\\remplacements.json."""

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        self.entrees = remplacements_depuis_liste(donnees.get("entrees", []) if isinstance(donnees, dict) else [])

    def enregistrer(self, entrees: list[Remplacement]) -> None:
        self.entrees = nettoyer_remplacements(entrees)
        ecrire_json(self._chemin, {"version_format": 1, "entrees": [asdict(e) for e in self.entrees]})


# --- Hésitations (§6.3) ----------------------------------------------------------------------------


def hesitations_pour(langue: str, personnalisees: dict[str, list[str]] | None = None) -> set[str]:
    """Hésitations d'une langue (« fr-FR » → celles du français), personnalisées ou par défaut."""
    code = (langue or "fr").split("-")[0].lower()
    if personnalisees and code in personnalisees:
        return {cle_de_mot(m) for m in personnalisees[code] if cle_de_mot(m)}
    return set(HESITATIONS_PAR_DEFAUT.get(code, HESITATIONS_PAR_DEFAUT["fr"]))


def est_hesitation(mot: Mot, hesitations: set[str]) -> bool:
    return cle_de_mot(mot.texte) in hesitations


def mots_affiches(mots: list[Mot], hesitations: set[str], masquer: bool = True) -> list[Mot]:
    """Mots à afficher dans les sous-titres : sans les hésitations si l'option est cochée (les
    autres mots gardent leurs temps)."""
    if not masquer:
        return list(mots)
    return [m for m in mots if not est_hesitation(m, hesitations)]


# --- Longues sources (§6.3 bis) ------------------------------------------------------------------

DUREE_MAX_HORODATEE_S = 30 * 60  # limite de Google avec l'horodatage par mot ou la séparation des voix
DUREE_MAX_TEXTE_S = 60 * 60  # limite de Google en texte seul
MORCEAU_S = 25 * 60  # taille visée des morceaux (marge sous la limite)


def decoupage(duree: float, limite: float, morceau: float = MORCEAU_S) -> list[tuple[float, float]]:
    """Découpe [0, durée] en morceaux sous la limite de Google : [(début, fin), …] (un seul
    morceau si la source est assez courte). Les coupures exactes sont ensuite placées dans un
    silence voisin (voir audio.coupure_dans_un_silence)."""
    if duree <= limite:
        return [(0.0, duree)]
    bornes = []
    debut = 0.0
    while duree - debut > limite:
        bornes.append((debut, debut + morceau))
        debut += morceau
    bornes.append((debut, duree))
    return bornes


_ESPACES = re.compile(r"\s+")


def normaliser_texte(texte: str) -> str:
    return _ESPACES.sub(" ", texte).strip()
