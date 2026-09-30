"""Écoute pendant la génération (§5.6) : adapter l'audio reçu en flux au format de la carte son.

Google envoie la voix par morceaux, en PCM 16 bits mono à 24 kHz. Beaucoup de cartes son (ou
Windows) préfèrent un autre format : 48 kHz, stéréo, nombres à virgule… Le `Convertisseur`
transforme chaque morceau dès son arrivée, sans coupure entre deux morceaux :

- fréquence : interpolation linéaire entre deux échantillons voisins (on garde le dernier
  échantillon d'un morceau pour calculer le début du suivant) ;
- canaux : le même son dans chaque canal (gauche = droite) ;
- type d'échantillon : entier 16 bits, 32 bits, 8 bits non signé ou nombre à virgule (float).

Ce module n'utilise pas Qt : il est testé seul.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass

from .audio import FREQUENCE_TTS

ENTIER_16_MAX = 32767
ENTIER_16_MIN = -32768
ECHELLE_FLOTTANT = 32768.0
DECALAGE_32_BITS = 16  # un échantillon 16 bits devient 32 bits en le décalant de 16 bits
DECALAGE_8_BITS = 8
MILIEU_8_BITS = 128  # le silence d'un échantillon 8 bits « non signé »

# Type d'échantillon → (code du module « array », octets par échantillon)
TYPES = {"int16": ("h", 2), "int32": ("i", 4), "float": ("f", 4), "uint8": ("B", 1)}


@dataclass(frozen=True)
class FormatAudio:
    frequence: int
    canaux: int
    echantillon: str  # une clé de TYPES

    @property
    def octets_par_trame(self) -> int:
        """Taille d'une « trame » : un échantillon pour chaque canal."""
        return TYPES[self.echantillon][1] * self.canaux

    def octets_par_seconde(self) -> int:
        return self.frequence * self.octets_par_trame


FORMAT_TTS = FormatAudio(FREQUENCE_TTS, 1, "int16")


class Convertisseur:
    """Convertit, morceau après morceau, du PCM 16 bits mono vers le format de sortie."""

    def __init__(self, sortie: FormatAudio):
        if sortie.echantillon not in TYPES:
            raise ValueError(f"Type d'échantillon non pris en charge : {sortie.echantillon}")
        self.sortie = sortie
        self._reste = b""  # octet isolé d'un morceau de longueur impaire (moitié d'échantillon)
        self._precedent = 0.0  # dernier échantillon du morceau précédent
        self._position = 1.0  # position du prochain échantillon à produire (0 = le précédent)

    def convertir(self, pcm: bytes, frequence: int = FREQUENCE_TTS) -> bytes:
        donnees = self._reste + pcm
        coupure = len(donnees) - len(donnees) % 2
        self._reste = donnees[coupure:]
        entree = array("h")
        entree.frombytes(donnees[:coupure])
        if not entree:
            return b""
        if (frequence, self.sortie) == (FORMAT_TTS.frequence, FORMAT_TTS):
            return entree.tobytes()  # déjà au bon format
        echantillons = self._reechantillonner(entree, frequence)
        return self._encoder(echantillons)

    def _reechantillonner(self, entree: array, frequence: int) -> list[float]:
        if frequence == self.sortie.frequence:
            return [float(v) for v in entree]
        pas = frequence / self.sortie.frequence  # avance dans l'entrée pour chaque échantillon produit
        valeurs = [self._precedent, *map(float, entree)]  # indice 0 : dernier échantillon précédent
        resultat = []
        position = self._position
        derniere = len(valeurs) - 1
        while position < derniere:
            indice = int(position)
            fraction = position - indice
            gauche = valeurs[indice]
            resultat.append(gauche + (valeurs[indice + 1] - gauche) * fraction)
            position += pas
        # Le dernier échantillon devient l'indice 0 du morceau suivant.
        self._position = position - derniere
        self._precedent = valeurs[-1]
        return resultat

    def _encoder(self, echantillons: list[float]) -> bytes:
        code, _ = TYPES[self.sortie.echantillon]
        if self.sortie.echantillon == "float":
            valeurs = [v / ECHELLE_FLOTTANT for v in echantillons]
        else:
            entiers = [min(ENTIER_16_MAX, max(ENTIER_16_MIN, round(v))) for v in echantillons]
            if self.sortie.echantillon == "int32":
                valeurs = [v << DECALAGE_32_BITS for v in entiers]
            elif self.sortie.echantillon == "uint8":
                valeurs = [(v >> DECALAGE_8_BITS) + MILIEU_8_BITS for v in entiers]
            else:
                valeurs = entiers
        if self.sortie.canaux > 1:
            valeurs = [v for v in valeurs for _ in range(self.sortie.canaux)]
        return array(code, valeurs).tobytes()
