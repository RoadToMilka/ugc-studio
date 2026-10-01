"""Bibliothèque de briefs (V2, lot 2, §10.5) : des briefs réutilisables d'un projet à l'autre.

« Enregistrer » (bloc Brief du module Script) range le brief du projet ouvert sous un nom ;
« Charger un brief » en reprend un, par exemple pour un nouveau projet sur le même produit. Un
brief enregistré garde aussi la page produit lue et la fiche comprise, s'il y en a : en le
chargeant, tu peux les reprendre sans relire la page (et sans repayer son analyse).

Enregistrer sous un nom déjà pris remplace l'ancien brief (l'écran demande d'abord confirmation).

Rangement : %APPDATA%\\UGC Studio\\briefs.json (tous les projets).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..stockage import ecrire_json, lire_json
from .brief import RESEAUX, Brief, pays_de
from .fiche import FicheProduit
from .page_produit import PageLue

NOM_MAX = 80


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _cle(nom: str) -> str:
    return " ".join(nom.casefold().split())


@dataclass
class BriefEnregistre:
    identifiant: str
    nom: str
    date: str  # date du dernier enregistrement
    brief: Brief
    adresse: str = ""
    page: PageLue | None = None
    fiche: FicheProduit | None = None

    def resume(self) -> str:
        """« Sérum éclat Glowzy · TikTok · 25 s · France » : de quoi le reconnaître dans la liste."""
        brief = self.brief
        duree = f"{brief.duree_s} s" if brief.duree_s else f"{brief.duree_visee()} s (auto)"
        morceaux = [brief.produit.strip(), RESEAUX.get(brief.reseau, brief.reseau), duree, pays_de(brief.pays).nom]
        return "  ·  ".join(m for m in morceaux if m)

    def en_dict(self) -> dict:
        return {
            "identifiant": self.identifiant,
            "nom": self.nom,
            "date": self.date,
            "brief": self.brief.en_dict(),
            "adresse": self.adresse,
            "page": self.page.en_dict() if self.page else None,
            "fiche": self.fiche.en_dict() if self.fiche else None,
        }

    @classmethod
    def depuis_dict(cls, brut) -> BriefEnregistre | None:
        if not isinstance(brut, dict) or not str(brut.get("nom") or "").strip():
            return None
        fiche = FicheProduit.depuis_dict(brut["fiche"]) if isinstance(brut.get("fiche"), dict) else None
        return cls(
            identifiant=str(brut.get("identifiant") or uuid.uuid4().hex[:12]),
            nom=" ".join(str(brut["nom"]).split())[:NOM_MAX],
            date=str(brut.get("date") or ""),
            brief=Brief.depuis_dict(brut.get("brief")),
            adresse=str(brut.get("adresse") or ""),
            page=PageLue.depuis_dict(brut.get("page")),
            fiche=fiche,
        )


def nom_propose(brief: Brief, nom_du_projet: str = "") -> str:
    """Nom proposé à l'enregistrement : « Sérum éclat Glowzy (TikTok) »."""
    produit = brief.produit.strip() or nom_du_projet.strip() or "Brief"
    return f"{produit} ({RESEAUX.get(brief.reseau, brief.reseau)})"[:NOM_MAX]


class BibliothequeBriefs:
    """Briefs enregistrés, du plus récent au plus ancien."""

    VERSION_FORMAT = 1

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        brutes = donnees.get("briefs") if isinstance(donnees, dict) else None
        self._briefs = [b for b in (BriefEnregistre.depuis_dict(x) for x in brutes or []) if b is not None]
        self._abonnes: list[Callable[[], None]] = []

    def briefs(self) -> list[BriefEnregistre]:
        return sorted(self._briefs, key=lambda b: b.date, reverse=True)

    def brief(self, identifiant: str) -> BriefEnregistre | None:
        return next((b for b in self._briefs if b.identifiant == identifiant), None)

    def existe(self, nom: str) -> bool:
        return any(_cle(b.nom) == _cle(nom) for b in self._briefs)

    def enregistrer(
        self,
        nom: str,
        brief: Brief,
        adresse: str = "",
        page: PageLue | None = None,
        fiche: FicheProduit | None = None,
    ) -> BriefEnregistre:
        """Range une copie du brief (et de la page lue) ; un brief du même nom est remplacé."""
        nom = " ".join(nom.split())[:NOM_MAX] or nom_propose(brief)
        ancien = next((b for b in self._briefs if _cle(b.nom) == _cle(nom)), None)
        enregistre = BriefEnregistre(
            identifiant=ancien.identifiant if ancien else uuid.uuid4().hex[:12],
            nom=nom,
            date=_maintenant(),
            brief=Brief.depuis_dict(brief.en_dict()),
            adresse=adresse.strip(),
            page=PageLue.depuis_dict(page.en_dict()) if page else None,
            fiche=FicheProduit.depuis_dict(fiche.en_dict()) if fiche else None,
        )
        self._briefs = [b for b in self._briefs if b is not ancien] + [enregistre]
        self._enregistrer()
        return enregistre

    def renommer(self, identifiant: str, nom: str) -> bool:
        """Renomme un brief ; refusé (False) si le nom est vide ou déjà pris par un autre brief."""
        nom = " ".join(nom.split())[:NOM_MAX]
        brief = self.brief(identifiant)
        if brief is None or not nom or any(b is not brief and _cle(b.nom) == _cle(nom) for b in self._briefs):
            return False
        brief.nom = nom
        self._enregistrer()
        return True

    def retirer(self, identifiant: str) -> None:
        self._briefs = [b for b in self._briefs if b.identifiant != identifiant]
        self._enregistrer()

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    def _enregistrer(self) -> None:
        ecrire_json(self._chemin, {"version_format": self.VERSION_FORMAT, "briefs": [b.en_dict() for b in self._briefs]})
        for fonction in list(self._abonnes):
            fonction()
