"""Ce que le module Script garde dans le projet (format 6, V2) : le brief, la page produit lue (avec
son adresse et sa date), la fiche comprise, les accroches proposées et les scripts écrits (relecture
et coût compris). Un projet plus ancien s'ouvre avec un état vide."""

from __future__ import annotations

from dataclasses import dataclass, field

from .brief import Brief
from .fiche import FicheProduit
from .page_produit import PageLue
from .scripts import Accroche, ScriptEcrit


@dataclass
class EtatScript:
    brief: Brief = field(default_factory=Brief)
    adresse: str = ""  # adresse de la page produit, telle que tapée
    page: PageLue | None = None
    fiche: FicheProduit | None = None
    accroches: list[Accroche] = field(default_factory=list)
    scripts: list[ScriptEcrit] = field(default_factory=list)  # du plus ancien au plus récent

    def script(self, identifiant: str) -> ScriptEcrit | None:
        return next((s for s in self.scripts if s.identifiant == identifiant), None)

    def accroches_cochees(self) -> list[Accroche]:
        return [a for a in self.accroches if a.cochee]

    def en_dict(self) -> dict:
        return {
            "brief": self.brief.en_dict(),
            "adresse": self.adresse,
            "page": self.page.en_dict() if self.page else None,
            "fiche": self.fiche.en_dict() if self.fiche else None,
            "accroches": [
                {"texte": a.texte, "angle": a.angle, "pourquoi": a.pourquoi, "alerte": a.alerte, "cochee": a.cochee}
                for a in self.accroches
            ],
            "scripts": [s.en_dict() for s in self.scripts],
        }

    @classmethod
    def depuis_dict(cls, brut) -> EtatScript:
        if not isinstance(brut, dict):
            return cls()
        fiche = FicheProduit.depuis_dict(brut["fiche"]) if isinstance(brut.get("fiche"), dict) else None
        return cls(
            brief=Brief.depuis_dict(brut.get("brief")),
            adresse=str(brut.get("adresse") or ""),
            page=PageLue.depuis_dict(brut.get("page")),
            fiche=fiche,
            accroches=[a for a in (Accroche.depuis_dict(b) for b in brut.get("accroches") or []) if a is not None],
            scripts=[s for s in (ScriptEcrit.depuis_dict(b) for b in brut.get("scripts") or []) if s is not None],
        )
