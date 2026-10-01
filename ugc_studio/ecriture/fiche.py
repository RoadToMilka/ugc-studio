"""Fiche « Ce que l'app a compris » (V2, §10.4) : le produit tel que le modèle l'a compris en lisant
la page, case par case.

Le modèle la remplit sous forme de « réponse structurée » (un objet JSON conforme à SCHEMA_FICHE) :
l'app la lit sans risque d'erreur de format. Les prix exacts lus par l'app (données Shopify)
l'emportent sur ceux du modèle. La fiche pré-remplit ensuite les champs vides du brief, où chaque
case se corrige à la main (une seule place pour corriger).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from .page_produit import SHOPIFY, PageLue

ELEMENTS_MAX = 5  # bénéfices, problèmes, objections, preuves : 3 à 5 suffisent pour un script court


def _liste(description: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "maxItems": ELEMENTS_MAX, "description": description}


# Schéma de la réponse structurée (sous-ensemble de JSON Schema accepté par Gemini).
SCHEMA_FICHE = {
    "type": "object",
    "properties": {
        "nom": {"type": "string", "description": "Product name, as written on the page."},
        "marque": {"type": "string", "description": "Brand name, empty if unknown."},
        "type_produit": {"type": "string", "description": "Short product category, e.g. 'period underwear'."},
        "prix": {
            "type": "string",
            "description": "Current price with its currency, exactly as written (e.g. '21,90 €'); empty if absent.",
        },
        "prix_barre": {
            "type": "string",
            "description": "Previous crossed-out price if the page shows a discount; empty otherwise.",
        },
        "offre": {
            "type": "string",
            "description": "Delivery, returns, guarantee and bundle offers exactly as stated on the page; empty if none.",
        },
        "benefices": _liste("3 to 5 concrete benefits for the user, from the page only."),
        "distinction": {"type": "string", "description": "What makes this product different, in one sentence."},
        "problemes": _liste("Problems the product solves, from the page."),
        "objections": _liste("Likely objections of a buyer (price, effectiveness, comfort...)."),
        "preuves": _liste(
            "Proof found on the page: average rating, number of reviews, short review excerpts, figures, "
            "certifications. Never a person's name."
        ),
        "clientele": {"type": "string", "description": "Probable customers, in one short sentence."},
        "noms_a_prononcer": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": ELEMENTS_MAX,
            "description": "Brand or product names that a text-to-speech voice could mispronounce.",
        },
    },
    "required": [
        "nom", "marque", "type_produit", "prix", "prix_barre", "offre", "benefices", "distinction",
        "problemes", "objections", "preuves", "clientele", "noms_a_prononcer",
    ],
}


@dataclass
class FicheProduit:
    nom: str = ""
    marque: str = ""
    type_produit: str = ""
    prix: str = ""
    prix_barre: str = ""
    offre: str = ""
    benefices: list[str] = field(default_factory=list)
    distinction: str = ""
    problemes: list[str] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    preuves: list[str] = field(default_factory=list)
    clientele: str = ""
    noms_a_prononcer: list[str] = field(default_factory=list)

    def est_vide(self) -> bool:
        return not any(getattr(self, c.name) for c in fields(self))

    def en_texte(self) -> str:
        """La fiche en texte simple : ce qui est donné au modèle quand la page a été lue par Google
        (l'app n'a alors pas le texte de la page elle-même)."""
        prix = self.prix + (f" au lieu de {self.prix_barre}" if self.prix and self.prix_barre else "")
        champs = (
            ("Nom", self.nom),
            ("Marque", self.marque),
            ("Type de produit", self.type_produit),
            ("Prix", prix),
            ("Offre", self.offre),
            ("Bénéfices", " ; ".join(self.benefices)),
            ("Ce qui le distingue", self.distinction),
            ("Problèmes résolus", " ; ".join(self.problemes)),
            ("Objections probables", " ; ".join(self.objections)),
            ("Preuves", " ; ".join(self.preuves)),
            ("Clientèle probable", self.clientele),
        )
        lignes = [f"- {nom} : {valeur}" for nom, valeur in champs if valeur]
        return "\n".join(["Fiche du produit (page lue par Google) :", *lignes]) if lignes else ""

    def valeurs_du_brief(self) -> dict[str, str]:
        """Valeurs proposées aux champs du brief (les listes deviennent une ligne par élément)."""
        promo = f"au lieu de {self.prix_barre}" if self.prix_barre else ""
        return {
            "produit": self.nom,
            "type_produit": self.type_produit,
            "prix": self.prix,
            "promo": promo,
            "offre": self.offre,
            "benefices": "\n".join(self.benefices),
            "distinction": self.distinction,
            "clientele": self.clientele,
            "problemes": "\n".join(self.problemes),
            "objections": "\n".join(self.objections),
            "preuves": "\n".join(self.preuves),
        }

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, brut) -> FicheProduit:
        fiche = cls()
        if not isinstance(brut, dict):
            return fiche
        for champ in fields(cls):
            valeur = brut.get(champ.name)
            if isinstance(getattr(fiche, champ.name), list):
                if isinstance(valeur, list):
                    propres = [" ".join(str(v).split()) for v in valeur if str(v).strip()]
                    setattr(fiche, champ.name, propres[:ELEMENTS_MAX])
            elif isinstance(valeur, (str, int, float)):
                setattr(fiche, champ.name, " ".join(str(valeur).split()))
        return fiche


def lire_fiche(texte_json: str, page: PageLue | None = None) -> FicheProduit:
    """Fiche à partir de la réponse du modèle ; les valeurs exactes lues par l'app l'emportent.
    ValueError si la réponse n'est pas un objet JSON."""
    donnees = json.loads(texte_json)
    if not isinstance(donnees, dict):
        raise ValueError("La réponse n'est pas un objet JSON.")
    fiche = FicheProduit.depuis_dict(donnees)
    if page is not None:
        for nom in ("nom", "marque", "prix", "prix_barre"):
            exact = getattr(page, nom)
            if exact:
                setattr(fiche, nom, exact)
        if page.source == SHOPIFY and page.prix and not page.prix_barre:
            fiche.prix_barre = ""  # données exactes de la boutique : pas de promo en ce moment
    return fiche
