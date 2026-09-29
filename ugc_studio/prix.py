"""Catalogue des prix et taux de change (§4.2).

- Prix par modèle, en dollars par million de tokens, séparés en entrée (ce qu'on envoie :
  le texte) et sortie (ce que le modèle produit : l'audio…). Par défaut, les tarifs officiels de
  Google (fournisseurs/capacites.py), y compris les changements de prix annoncés à une date
  (ex. hausse du 01/01/2027) : l'app applique le tarif en vigueur le jour de l'appel.
- Chaque prix reste modifiable à la main. Un prix saisi s'applique jusqu'au prochain changement
  de tarif annoncé par Google (l'information la plus récente l'emporte).
- Taux de change dollar → euro, saisi à la main ou récupéré auprès de la Banque centrale
  européenne (BCE).

Coût d'un appel = (tokens d'entrée × prix d'entrée + tokens de sortie × prix de sortie)
                  ÷ 1 000 000 × taux de change.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .fournisseurs.capacites import MODELES_CONNUS, Tarif, modele_connu
from .stockage import ecrire_json, lire_json

journal = logging.getLogger(__name__)

TAUX_PAR_DEFAUT = Decimal("0.86")  # 1 $ = 0,86 € — valeur de départ, à vérifier
UN_MILLION = Decimal(1_000_000)
ADRESSE_TAUX_BCE = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


@dataclass(frozen=True)
class PrixModele:
    entree: Decimal | None  # $ par million de tokens
    sortie: Decimal | None
    personnalise: bool = False  # saisi dans les réglages (différent du tarif Google)


def aujourd_hui() -> date:
    """Date du jour (fonction à part pour que les tests puissent la fixer)."""
    return date.today()


def _date_sur(valeur) -> date | None:
    try:
        return date.fromisoformat(str(valeur))
    except (TypeError, ValueError):
        return None


def lire_decimal(texte: str | None) -> Decimal | None:
    """« 0,50 » ou « 0.50 » → Decimal('0.50') ; vide → None ; texte invalide → ValueError."""
    if texte is None:
        return None
    texte = texte.strip().replace(",", ".").replace(" ", "").replace(" ", "")
    if not texte:
        return None
    try:
        valeur = Decimal(texte)
    except InvalidOperation as erreur:
        raise ValueError(f"Nombre invalide : {texte}") from erreur
    if not valeur.is_finite() or valeur < 0:
        raise ValueError(f"Nombre invalide : {texte}")
    return valeur


def _en_texte(valeur: Decimal | None) -> str | None:
    return None if valeur is None else format(valeur, "f")


class CataloguePrix:
    VERSION_FORMAT = 1

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        donnees = donnees if isinstance(donnees, dict) else {}
        self._taux = self._decimal_sur(donnees.get("taux_usd_eur")) or TAUX_PAR_DEFAUT
        self._taux_source = donnees.get("taux_source", "défaut")  # « défaut », « manuel » ou « BCE »
        self._taux_date = donnees.get("taux_date", "")
        self._prix: dict[str, dict[str, str | None]] = {
            k: v for k, v in (donnees.get("modeles") or {}).items() if isinstance(v, dict)
        }
        self._abonnes: list[Callable[[], None]] = []

    # --- Taux de change ----------------------------------------------------------------------

    @property
    def taux_usd_eur(self) -> Decimal:
        return self._taux

    @property
    def taux_source(self) -> str:
        return self._taux_source

    @property
    def taux_date(self) -> str:
        return self._taux_date

    def definir_taux(self, taux: Decimal, source: str = "manuel", le: str | None = None) -> None:
        if taux <= 0:
            raise ValueError("Le taux de change doit être positif.")
        self._taux = taux
        self._taux_source = source
        self._taux_date = le or date.today().isoformat()
        self._enregistrer()

    # --- Prix --------------------------------------------------------------------------------

    def identifiants(self, supplementaires: set[str] | None = None) -> list[str]:
        """Modèles à lister dans les réglages.

        D'abord les modèles principaux du catalogue ; puis les autres modèles du catalogue et les
        modèles inconnus, s'ils sont accessibles avec une clé (`supplementaires`) ou ont un prix saisi.
        """
        visibles = set(self._prix) | (supplementaires or set())
        catalogue = [m.identifiant for m in MODELES_CONNUS if m.principal or m.identifiant in visibles]
        autres = sorted(visibles - {m.identifiant for m in MODELES_CONNUS})
        return catalogue + autres

    def tarif_google(self, identifiant: str, le: date | None = None) -> Tarif | None:
        """Tarif officiel en vigueur à cette date (aujourd'hui par défaut), si le modèle est connu."""
        connu = modele_connu(identifiant)
        return connu.tarif(le or aujourd_hui()) if connu else None

    def prochain_tarif_google(self, identifiant: str, le: date | None = None) -> Tarif | None:
        """Prochain changement de prix annoncé par Google, s'il y en a un."""
        connu = modele_connu(identifiant)
        return connu.prochain_tarif(le or aujourd_hui()) if connu else None

    def prix(self, identifiant: str, le: date | None = None) -> PrixModele:
        """Prix appliqué à cette date (aujourd'hui par défaut) : le prix saisi, sinon le tarif Google."""
        tarif = self.tarif_google(identifiant, le)
        saisi = self._prix.get(identifiant)
        if saisi is not None:
            entree, sortie = self._decimal_sur(saisi.get("entree")), self._decimal_sur(saisi.get("sortie"))
            saisi_le = _date_sur(saisi.get("depuis")) or date.min
            # Un changement de tarif annoncé par Google après la saisie l'emporte sur le prix saisi.
            remplace = tarif is not None and tarif.depuis is not None and tarif.depuis > saisi_le
            if not remplace:
                personnalise = tarif is None or (entree, sortie) != (tarif.entree, tarif.sortie)
                return PrixModele(entree, sortie, personnalise)
        if tarif is None:
            return PrixModele(None, None)
        return PrixModele(tarif.entree, tarif.sortie)

    def definir_prix(self, identifiant: str, entree: Decimal | None, sortie: Decimal | None) -> None:
        tarif = self.tarif_google(identifiant)
        if tarif is not None and (entree, sortie) == (tarif.entree, tarif.sortie):
            self._prix.pop(identifiant, None)  # identique au tarif Google : rien à retenir
        else:
            self._prix[identifiant] = {
                "entree": _en_texte(entree),
                "sortie": _en_texte(sortie),
                "depuis": aujourd_hui().isoformat(),
            }
        self._enregistrer()

    def retablir_defauts(self) -> None:
        self._prix.clear()
        self._enregistrer()

    def cout_eur(
        self, identifiant: str, tokens_entree: int, tokens_sortie: int, le: date | None = None
    ) -> Decimal | None:
        """Coût en euros au prix en vigueur à cette date, ou None si un prix nécessaire manque."""
        prix = self.prix(identifiant, le)
        total_usd = Decimal(0)
        for tokens, prix_unitaire in ((tokens_entree, prix.entree), (tokens_sortie, prix.sortie)):
            if tokens:
                if prix_unitaire is None:
                    return None
                total_usd += Decimal(tokens) * prix_unitaire / UN_MILLION
        return total_usd * self._taux

    def cout_reference_eur(self, identifiant: str, tarif: Tarif | None = None) -> Decimal | None:
        """Ordre de grandeur parlant (ex. coût d'une minute de voix), au prix actuel ou à ce tarif.

        None si le modèle n'a pas de consommation de référence ou si un prix manque.
        """
        connu = modele_connu(identifiant)
        if connu is None or connu.reference is None:
            return None
        reference = connu.reference
        if tarif is None:
            return self.cout_eur(identifiant, reference.tokens_entree, reference.tokens_sortie)
        if tarif.entree is None or tarif.sortie is None:
            return None
        total_usd = (reference.tokens_entree * tarif.entree + reference.tokens_sortie * tarif.sortie) / UN_MILLION
        return total_usd * self._taux

    # --- Notifications et fichier -------------------------------------------------------------

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    @staticmethod
    def _decimal_sur(valeur) -> Decimal | None:
        try:
            return lire_decimal(None if valeur is None else str(valeur))
        except ValueError:
            return None

    def _enregistrer(self) -> None:
        ecrire_json(
            self._chemin,
            {
                "version_format": self.VERSION_FORMAT,
                "taux_usd_eur": _en_texte(self._taux),
                "taux_source": self._taux_source,
                "taux_date": self._taux_date,
                "modeles": self._prix,
            },
        )
        for fonction in list(self._abonnes):
            fonction()


# ---------------------------------------------------------------------------------------------
# Taux du jour de la Banque centrale européenne
# ---------------------------------------------------------------------------------------------


def analyser_taux_bce(xml: str) -> tuple[Decimal, str]:
    """Extrait du fichier de la BCE le taux dollar → euro et sa date.

    La BCE publie « 1 € = X $ » (ex. <Cube currency='USD' rate='1.1650'/>) : 1 $ = 1 / X €.
    """
    trouve = re.search(r"currency=['\"]USD['\"]\s+rate=['\"]([0-9.]+)['\"]", xml)
    if not trouve:
        raise ValueError("Taux du dollar absent de la réponse de la BCE.")
    euro_en_dollars = Decimal(trouve.group(1))
    jour = re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", xml)
    taux = (Decimal(1) / euro_en_dollars).quantize(Decimal("0.0001"))
    return taux, jour.group(1) if jour else date.today().isoformat()


def recuperer_taux_bce() -> tuple[Decimal, str]:
    """Taux dollar → euro publié chaque jour ouvré par la BCE (gratuit, sans clé)."""
    from .fournisseurs.base import ErreurFournisseur
    from .fournisseurs.http import requete

    reponse = requete("GET", ADRESSE_TAUX_BCE, delai=20)
    if reponse.statut >= 400:
        raise ErreurFournisseur(
            f"La Banque centrale européenne n'a pas répondu (code {reponse.statut}).", "serveur"
        )
    try:
        return analyser_taux_bce(reponse.corps.decode("utf-8", "replace"))
    except (ValueError, ArithmeticError) as erreur:
        raise ErreurFournisseur("Réponse de la BCE illisible.", "reponse_illisible", str(erreur)) from erreur
