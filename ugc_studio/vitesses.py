"""Vitesse de parole mesurée sur tes prises (V2, lot 2, §10.7 du document V2).

Au départ, l'app compte 2,7 mots par seconde (environ 160 mots par minute). Chaque prise générée
donne une mesure : nombre de mots dits ÷ temps de parole. Le temps de parole est la durée de la
prise moins le temps estimé des balises (pauses, rires…) : c'est exactement ce que la formule
d'estimation ajoute à part, et les petits silences du début et de la fin restent comptés, si bien
que la durée estimée d'un script correspond à la durée réelle de ses prises.

La vitesse change d'une voix à l'autre : l'app fait la moyenne des 20 dernières prises de la même
voix ; sans prise de cette voix, la moyenne de toutes tes prises ; sans aucune prise, 2,7. Elle
sert au module Voix (durée et coût estimés) et au module Script (nombre de mots, durée estimée).

Rangement : %APPDATA%\\UGC Studio\\vitesses.json (toutes les voix, tous les projets).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .estimation import MOTS_PAR_SECONDE, duree_des_balises, mots_dits
from .stockage import ecrire_json, lire_json

MESURES_POUR_LA_MOYENNE = 20
MESURES_GARDEES_PAR_VOIX = 50
MOTS_MIN = 4  # une prise trop courte (« Salut ! ») ne dit rien de la vitesse
TEMPS_MIN_S = 1.0
# Mesures hors de ces bornes : prise ratée ou texte qui ne correspond pas (ignorées).
VITESSE_MIN = 1.0
VITESSE_MAX = 6.0


@dataclass(frozen=True)
class Mesure:
    prise: str  # identifiant de la prise mesurée (une prise ne compte qu'une fois)
    voix: str
    mots: int
    secondes: float
    date: str

    @property
    def vitesse(self) -> float:
        return self.mots / self.secondes


@dataclass(frozen=True)
class Vitesse:
    mots_par_seconde: float
    nombre: int  # prises mesurées prises en compte (0 : valeur de départ)
    de_cette_voix: bool  # mesurée sur des prises de cette voix (sinon : toutes les voix, ou départ)

    def texte(self, nom_voix: str) -> str:
        """« vitesse de Kore mesurée sur 9 prises : 2,7 mots/s », ou la valeur de départ."""
        valeur = f"{self.mots_par_seconde:.1f}".replace(".", ",")
        if self.nombre == 0:
            return f"vitesse de départ : {valeur} mots/s"
        prises = f"{self.nombre} prise{'s' if self.nombre > 1 else ''}"
        if self.de_cette_voix:
            return f"vitesse de {nom_voix} mesurée sur {prises} : {valeur} mots/s"
        return f"vitesse mesurée sur {prises} d'autres voix : {valeur} mots/s"


def mots_et_temps(texte_api: str, duree_s: float) -> tuple[int, float]:
    """(mots dits, temps de parole) d'une prise : les balises comptent leur durée estimée, pas leurs
    mots (mêmes calculs que l'estimation, voir estimation.py)."""
    return mots_dits(texte_api), max(0.0, duree_s - duree_des_balises(texte_api))


def mesure_valide(mots: int, secondes: float) -> bool:
    return mots >= MOTS_MIN and secondes >= TEMPS_MIN_S and VITESSE_MIN <= mots / secondes <= VITESSE_MAX


class VitessesDeParole:
    VERSION_FORMAT = 1

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        brutes = donnees.get("mesures") if isinstance(donnees, dict) else None
        self._mesures: list[Mesure] = []
        for brute in brutes if isinstance(brutes, list) else []:
            try:
                mesure = Mesure(str(brute["prise"]), str(brute["voix"]), int(brute["mots"]), float(brute["secondes"]), str(brute.get("date") or ""))
            except (KeyError, TypeError, ValueError):
                continue
            if mesure_valide(mesure.mots, mesure.secondes):
                self._mesures.append(mesure)
        self._abonnes: list[Callable[[], None]] = []

    def mesures(self, voix: str | None = None) -> list[Mesure]:
        return [m for m in self._mesures if voix is None or m.voix == voix]

    def connait(self, prise: str) -> bool:
        return any(m.prise == prise for m in self._mesures)

    def noter(self, voix: str, prise: str, texte_api: str, duree_s: float, enregistrer: bool = True) -> bool:
        """Mesure d'une prise (une seule par prise : une nouvelle mesure remplace l'ancienne).
        Renvoie False si la prise ne permet pas de mesurer (trop courte, durée incohérente)."""
        mots, secondes = mots_et_temps(texte_api, duree_s)
        if not voix or not mesure_valide(mots, secondes):
            return False
        date = datetime.now().astimezone().isoformat(timespec="seconds")
        self._mesures = [m for m in self._mesures if m.prise != prise] + [Mesure(prise, voix, mots, round(secondes, 3), date)]
        de_cette_voix = [m for m in self._mesures if m.voix == voix]
        if len(de_cette_voix) > MESURES_GARDEES_PAR_VOIX:
            trop_anciennes = {id(m) for m in de_cette_voix[: len(de_cette_voix) - MESURES_GARDEES_PAR_VOIX]}
            self._mesures = [m for m in self._mesures if id(m) not in trop_anciennes]
        if enregistrer:
            self._enregistrer()
        return True

    def noter_prises(self, prises: Iterable) -> int:
        """Mesure les prises pas encore mesurées (ex. celles d'un projet de la 1.2.0) ; renvoie leur nombre."""
        nouvelles = 0
        for prise in prises:
            if not self.connait(prise.identifiant) and self.noter(prise.voix, prise.identifiant, prise.texte_api, prise.duree_s, enregistrer=False):
                nouvelles += 1
        if nouvelles:
            self._enregistrer()
        return nouvelles

    def vitesse(self, voix: str) -> Vitesse:
        """Moyenne des 20 dernières prises de cette voix ; sinon de toutes les voix ; sinon 2,7."""
        for mesures, de_cette_voix in ((self.mesures(voix), True), (self._mesures, False)):
            recentes = mesures[-MESURES_POUR_LA_MOYENNE:]
            if recentes:
                total_mots = sum(m.mots for m in recentes)
                total_secondes = sum(m.secondes for m in recentes)
                return Vitesse(round(total_mots / total_secondes, 3), len(recentes), de_cette_voix)
        return Vitesse(MOTS_PAR_SECONDE, 0, False)

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    def _enregistrer(self) -> None:
        ecrire_json(self._chemin, {"version_format": self.VERSION_FORMAT, "mesures": [asdict(m) for m in self._mesures]})
        for fonction in list(self._abonnes):
            fonction()
