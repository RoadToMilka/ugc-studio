"""Suivi des coûts (§4.3).

Chaque appel payant à une API est noté : date, projet, modèle, tokens d'entrée et de sortie,
coût en euros (calculé avec les compteurs de tokens renvoyés par l'API et les prix du moment).

Rangement : un fichier par mois dans %APPDATA%\\UGC Studio\\couts\\ (ex. 2026-09.jsonl), une
ligne par appel. On ne fait qu'ajouter des lignes à la fin : même en cas de coupure, les
appels déjà notés ne peuvent pas être abîmés.

Limite : l'app compte ce qu'elle a consommé ; elle ne connaît pas le solde du compte Google.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from .prix import CataloguePrix, lire_decimal

journal = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppelApi:
    date: datetime
    fournisseur: str
    modele: str
    operation: str  # ex. « voix », « transcription », « essai de voix »
    tokens_entree: int
    tokens_sortie: int
    cout_eur: Decimal | None  # None : prix du modèle non renseigné au moment de l'appel
    projet: str | None = None

    def en_ligne(self, taux: Decimal) -> str:
        return json.dumps(
            {
                "date": self.date.isoformat(timespec="seconds"),
                "fournisseur": self.fournisseur,
                "modele": self.modele,
                "operation": self.operation,
                "tokens_entree": self.tokens_entree,
                "tokens_sortie": self.tokens_sortie,
                "cout_eur": None if self.cout_eur is None else format(self.cout_eur, "f"),
                "taux_usd_eur": format(taux, "f"),
                "projet": self.projet,
            },
            ensure_ascii=False,
        )

    @classmethod
    def depuis_ligne(cls, ligne: str) -> AppelApi:
        brut = json.loads(ligne)
        return cls(
            date=datetime.fromisoformat(brut["date"]),
            fournisseur=brut.get("fournisseur", ""),
            modele=brut["modele"],
            operation=brut.get("operation", ""),
            tokens_entree=int(brut.get("tokens_entree", 0)),
            tokens_sortie=int(brut.get("tokens_sortie", 0)),
            cout_eur=lire_decimal(brut.get("cout_eur")),
            projet=brut.get("projet"),
        )


@dataclass(frozen=True)
class Totaux:
    nombre: int
    tokens_entree: int
    tokens_sortie: int
    cout_eur: Decimal
    sans_prix: int  # appels dont le coût n'a pas pu être calculé


def totaux(appels: Iterable[AppelApi]) -> Totaux:
    liste = list(appels)
    return Totaux(
        nombre=len(liste),
        tokens_entree=sum(a.tokens_entree for a in liste),
        tokens_sortie=sum(a.tokens_sortie for a in liste),
        cout_eur=sum((a.cout_eur for a in liste if a.cout_eur is not None), Decimal(0)),
        sans_prix=sum(1 for a in liste if a.cout_eur is None),
    )


def filtrer(
    appels: Iterable[AppelApi],
    *,
    depuis: date | None = None,
    jusqu_a: date | None = None,
    projet: str | None = None,
    modele: str | None = None,
) -> list[AppelApi]:
    """Filtre par période (dates incluses), projet et modèle (None = tous)."""
    resultat = []
    for appel in appels:
        jour = appel.date.date()
        if depuis and jour < depuis:
            continue
        if jusqu_a and jour > jusqu_a:
            continue
        if projet is not None and appel.projet != projet:
            continue
        if modele is not None and appel.modele != modele:
            continue
        resultat.append(appel)
    return resultat


class JournalCouts:
    def __init__(self, dossier: Path, catalogue: CataloguePrix):
        self._dossier = dossier
        self._catalogue = catalogue
        self._cout_session = Decimal(0)
        self._abonnes: list[Callable[[AppelApi], None]] = []

    @property
    def cout_session(self) -> Decimal:
        """Total des appels depuis l'ouverture de l'app (affiché dans le bandeau)."""
        return self._cout_session

    def enregistrer(
        self,
        fournisseur: str,
        modele: str,
        operation: str,
        tokens_entree: int,
        tokens_sortie: int,
        projet: str | None = None,
        quand: datetime | None = None,
    ) -> AppelApi:
        appel = AppelApi(
            date=(quand or datetime.now().astimezone()).replace(microsecond=0),
            fournisseur=fournisseur,
            modele=modele,
            operation=operation,
            tokens_entree=int(tokens_entree),
            tokens_sortie=int(tokens_sortie),
            cout_eur=self._catalogue.cout_eur(modele, tokens_entree, tokens_sortie),
            projet=projet,
        )
        self._dossier.mkdir(parents=True, exist_ok=True)
        fichier = self._dossier / f"{appel.date:%Y-%m}.jsonl"
        with open(fichier, "a", encoding="utf-8") as sortie:
            sortie.write(appel.en_ligne(self._catalogue.taux_usd_eur) + "\n")
        if appel.cout_eur is not None:
            self._cout_session += appel.cout_eur
        journal.info(
            "Appel %s %s (%s) : %s + %s tokens, %s €",
            fournisseur,
            modele,
            operation,
            tokens_entree,
            tokens_sortie,
            appel.cout_eur,
        )
        for fonction in list(self._abonnes):
            fonction(appel)
        return appel

    def lire(self, depuis: date | None = None, jusqu_a: date | None = None) -> list[AppelApi]:
        """Appels enregistrés (du plus ancien au plus récent), en ne lisant que les mois utiles."""
        appels: list[AppelApi] = []
        if not self._dossier.exists():
            return appels
        for fichier in sorted(self._dossier.glob("*.jsonl")):
            mois = fichier.stem  # « 2026-09 »
            if depuis and mois < f"{depuis:%Y-%m}":
                continue
            if jusqu_a and mois > f"{jusqu_a:%Y-%m}":
                continue
            with open(fichier, encoding="utf-8") as entree:
                for numero, ligne in enumerate(entree, start=1):
                    if not ligne.strip():
                        continue
                    try:
                        appels.append(AppelApi.depuis_ligne(ligne))
                    except (ValueError, KeyError, TypeError) as erreur:
                        journal.warning("Ligne %s de %s illisible, ignorée (%s)", numero, fichier.name, erreur)
        appels.sort(key=lambda a: a.date)
        return filtrer(appels, depuis=depuis, jusqu_a=jusqu_a)

    def abonner(self, fonction: Callable[[AppelApi], None]) -> None:
        self._abonnes.append(fonction)
