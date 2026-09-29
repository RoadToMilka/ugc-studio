"""Catalogue des prix et taux de change (§4.2).

- Prix par modèle, en dollars par million de tokens, séparés en entrée (ce qu'on envoie :
  le texte) et sortie (ce que le modèle produit : l'audio…). Modifiables, car les tarifs changent.
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

from .fournisseurs.capacites import MODELES_CONNUS, modele_connu
from .stockage import ecrire_json, lire_json

journal = logging.getLogger(__name__)

TAUX_PAR_DEFAUT = Decimal("0.86")  # 1 $ = 0,86 € — valeur de départ, à vérifier
UN_MILLION = Decimal(1_000_000)
ADRESSE_TAUX_BCE = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


@dataclass(frozen=True)
class PrixModele:
    entree: Decimal | None  # $ par million de tokens
    sortie: Decimal | None
    personnalise: bool = False  # modifié par l'utilisateur (différent du catalogue)


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
        """Modèles du catalogue, puis ceux ajoutés (prix saisis ou modèles détectés)."""
        connus = [m.identifiant for m in MODELES_CONNUS]
        autres = sorted((set(self._prix) | (supplementaires or set())) - set(connus))
        return connus + autres

    def prix(self, identifiant: str) -> PrixModele:
        connu = modele_connu(identifiant)
        defaut_entree = connu.prix_entree if connu else None
        defaut_sortie = connu.prix_sortie if connu else None
        saisi = self._prix.get(identifiant)
        if saisi is None:
            return PrixModele(defaut_entree, defaut_sortie)
        return PrixModele(self._decimal_sur(saisi.get("entree")), self._decimal_sur(saisi.get("sortie")), True)

    def definir_prix(self, identifiant: str, entree: Decimal | None, sortie: Decimal | None) -> None:
        connu = modele_connu(identifiant)
        if connu is not None and (entree, sortie) == (connu.prix_entree, connu.prix_sortie):
            self._prix.pop(identifiant, None)  # identique au catalogue : rien à retenir
        else:
            self._prix[identifiant] = {"entree": _en_texte(entree), "sortie": _en_texte(sortie)}
        self._enregistrer()

    def retablir_defauts(self) -> None:
        self._prix.clear()
        self._enregistrer()

    def cout_eur(self, identifiant: str, tokens_entree: int, tokens_sortie: int) -> Decimal | None:
        """Coût en euros, ou None si un prix nécessaire n'est pas renseigné."""
        prix = self.prix(identifiant)
        total_usd = Decimal(0)
        for tokens, prix_unitaire in ((tokens_entree, prix.entree), (tokens_sortie, prix.sortie)):
            if tokens:
                if prix_unitaire is None:
                    return None
                total_usd += Decimal(tokens) * prix_unitaire / UN_MILLION
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
