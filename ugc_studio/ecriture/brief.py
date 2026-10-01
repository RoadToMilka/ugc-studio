"""Brief d'un script (V2, §10.5) : ce que le modèle doit savoir pour écrire.

Aucun champ n'est obligatoire : ce qui manque est déduit de la page produit, et rien n'est inventé
(sans information, le script reste sans chiffre). Les champs vides sont pré-remplis d'après la
page produit (ou, pour le genre de la personne qui parle, d'après la voix du projet) ; un champ
pré-rempli est marqué « d'après la page » jusqu'à ce que tu le modifies, et rien de ce que tu as
tapé n'est jamais écrasé.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

from ..estimation import MOTS_PAR_SECONDE


@dataclass(frozen=True)
class Pays:
    code: str  # « FR »
    nom: str  # « France »
    langues: tuple[str, ...]  # variantes proposées, la première par défaut
    devise: str  # code ISO : « EUR »


PAYS: tuple[Pays, ...] = (
    Pays("FR", "France", ("fr-FR",), "EUR"),
    Pays("BE", "Belgique", ("fr-BE", "nl-BE"), "EUR"),
    Pays("CH", "Suisse", ("fr-CH", "de-CH"), "CHF"),
    Pays("LU", "Luxembourg", ("fr-LU",), "EUR"),
    Pays("CA", "Canada", ("fr-CA",), "CAD"),
    Pays("US", "États-Unis", ("en-US",), "USD"),
    Pays("GB", "Royaume-Uni", ("en-GB",), "GBP"),
    Pays("ES", "Espagne", ("es-ES",), "EUR"),
    Pays("IT", "Italie", ("it-IT",), "EUR"),
    Pays("NL", "Pays-Bas", ("nl-NL",), "EUR"),
    Pays("DE", "Allemagne", ("de-DE",), "EUR"),
)
PAYS_PAR_DEFAUT = "FR"

# Langue et variante régionale du script (nom affiché, puis nom donné au modèle).
LANGUES_ECRITURE: dict[str, tuple[str, str]] = {
    "fr-FR": ("Français (France)", "French (France)"),
    "fr-BE": ("Français (Belgique)", "French (Belgium)"),
    "fr-CH": ("Français (Suisse)", "French (Switzerland)"),
    "fr-LU": ("Français (Luxembourg)", "French (Luxembourg)"),
    "fr-CA": ("Français (Canada)", "French (Canada, Quebec)"),
    "nl-BE": ("Néerlandais (Belgique)", "Dutch (Belgium, Flemish)"),
    "nl-NL": ("Néerlandais (Pays-Bas)", "Dutch (Netherlands)"),
    "de-CH": ("Allemand (Suisse)", "German (Switzerland)"),
    "de-DE": ("Allemand (Allemagne)", "German (Germany)"),
    "en-US": ("Anglais (États-Unis)", "English (United States)"),
    "en-GB": ("Anglais (Royaume-Uni)", "English (United Kingdom)"),
    "es-ES": ("Espagnol (Espagne)", "Spanish (Spain)"),
    "it-IT": ("Italien (Italie)", "Italian (Italy)"),
}

# Mots et usages régionaux signalés au modèle (les prix restent en chiffres : les sous-titres les
# gardent ainsi ; la façon de les dire à la belge ou à la suisse arrive au lot 2).
USAGES_REGIONAUX = {
    "fr-BE": "Use Belgian French where it sounds natural (e.g. 'GSM' for a mobile phone, 'kot' for a "
    "student room, 'septante' and 'nonante' when a number is written in words).",
    "fr-CH": "Use Swiss French where it sounds natural (e.g. 'septante' and 'nonante' when a number is "
    "written in words). Prices in Swiss francs.",
    "fr-CA": "Use Quebec French where it sounds natural, while staying easy to understand.",
    "nl-BE": "Use Flemish (Belgian Dutch) wording where it sounds natural.",
    "de-CH": "Use Swiss Standard German spelling (ss instead of the sharp s).",
}

SYMBOLES_DEVISE = {"EUR": "€", "CHF": "CHF", "CAD": "$ CA", "USD": "$", "GBP": "£"}

RESEAUX = {
    "tiktok": "TikTok",
    "snapchat": "Snapchat",
    "meta": "Facebook et Instagram",
    "autre": "Autre",
}
# Durée visée quand le champ est vide (§14, question 4 : TikTok conseille 21 à 34 s pour une pub ;
# Meta citait 15 s pour Reels ; les 5 à 6 s de Snap (2020) sont trop courtes pour un script parlé).
DUREES_PAR_DEFAUT = {"tiktok": 25, "snapchat": 10, "meta": 20, "autre": 20}
DUREE_MIN = 5
DUREE_MAX = 120

ANGLES = {
    "auto": "Laisser le modèle choisir",
    "temoignage": "Témoignage",
    "probleme_solution": "Problème-solution",
    "unboxing": "Unboxing",
    "routine": "Routine",
    "comparaison": "Comparaison",
    "avant_apres": "Avant/après raconté",
    "pov": "Point de vue (« POV »)",
    "liste": "Liste (« 3 raisons de… »)",
}
# Nom de chaque angle pour le modèle, avec ce qu'il veut dire.
ANGLES_ANGLAIS = {
    "temoignage": "testimonial (the speaker tells their own experience with the product)",
    "probleme_solution": "problem-solution (a relatable problem, then the product as the answer)",
    "unboxing": "unboxing (first discovery of the product, described as it is opened)",
    "routine": "routine (the product inside a daily routine)",
    "comparaison": "comparison (with what the speaker used before, never a named competitor)",
    "avant_apres": "before/after told in words (no before/after pictures promised)",
    "pov": "POV (the viewer is put in a situation: 'POV: you…')",
    "liste": "list ('3 reasons why…', numbered)",
}

TUTOIEMENTS = {"auto": "Automatique", "tu": "Tutoiement", "vous": "Vouvoiement"}
TRANCHES_AGE = {
    "": "Non précisé",
    "18-24": "18 à 24 ans",
    "25-34": "25 à 34 ans",
    "35-44": "35 à 44 ans",
    "45-54": "45 à 54 ans",
    "55+": "55 ans et plus",
}
_AGES_VOUVOIEMENT = {"35-44", "45-54", "55+"}
GENRES = {"": "Non précisé", "femme": "Femme", "homme": "Homme"}

NOMBRE_ACCROCHES_PAR_DEFAUT = 6
NOMBRE_ACCROCHES_MIN = 3
NOMBRE_ACCROCHES_MAX = 10
MODELE_PAR_DEFAUT = "gemini-3.8-flash"

# Champs que la page produit peut pré-remplir (quand ils sont vides), avec leur nom affiché.
CHAMPS_DE_LA_PAGE = {
    "produit": "Nom du produit",
    "type_produit": "Type de produit",
    "prix": "Prix",
    "promo": "Promo",
    "offre": "Livraison, garantie, retours",
    "benefices": "Bénéfices",
    "distinction": "Ce qui le distingue",
    "clientele": "Clientèle probable",
    "problemes": "Problèmes qu'il résout",
    "objections": "Objections",
    "preuves": "Preuves",
}


def pays_de(code: str) -> Pays:
    return next((p for p in PAYS if p.code == code), PAYS[0])


def langue_du_projet(langue_ecriture: str) -> str:
    """Langue du projet (module Voix, transcription) qui correspond à la langue du script :
    les variantes du français partagent le français de France, l'allemand de Suisse celui
    d'Allemagne (les voix et la transcription ne distinguent pas ces variantes dans l'app)."""
    if langue_ecriture.startswith("fr-"):
        return "fr-FR"
    if langue_ecriture == "de-CH":
        return "de-DE"
    return langue_ecriture


def mots_vises(duree_s: float, mots_par_seconde: float = MOTS_PAR_SECONDE) -> int:
    """Nombre de mots d'un script dit en `duree_s` secondes (balises non comprises)."""
    return max(1, round(duree_s * mots_par_seconde))


@dataclass
class Brief:
    # Essentiel
    pays: str = PAYS_PAR_DEFAUT
    langue: str = "fr-FR"
    reseau: str = "tiktok"
    duree_s: int = 0  # 0 : durée par défaut du réseau
    angle: str = "auto"
    tutoiement: str = "auto"
    # Produit et offre
    produit: str = ""
    type_produit: str = ""
    prix: str = ""
    promo: str = ""
    offre: str = ""  # livraison, garantie, retours
    benefices: str = ""
    distinction: str = ""
    description: str = ""
    # Clientèle
    age: str = ""  # tranche d'âge (TRANCHES_AGE)
    clientele: str = ""
    problemes: str = ""
    objections: str = ""
    preuves: str = ""
    # Personne qui parle
    genre: str = ""  # « femme », « homme » ou vide
    age_personne: str = ""
    profil: str = ""
    # Contraintes
    appel_action: str = ""
    mentions: str = ""  # mentions obligatoires, une par ligne, reprises telles quelles
    mots_interdits: str = ""  # séparés par des virgules ou des retours à la ligne
    consigne: str = ""  # consigne libre
    # Options d'écriture (retenues d'une fois sur l'autre, voir l'écran Script)
    balises: bool = False
    styles: bool = True
    accents: bool = False
    modele: str = MODELE_PAR_DEFAUT
    nombre_accroches: int = NOMBRE_ACCROCHES_PAR_DEFAUT
    # Champs remplis par l'app (d'après la page, ou la voix pour le genre), pas encore modifiés.
    pre_remplis: list[str] = field(default_factory=list)

    # --- Valeurs déduites ------------------------------------------------------------------------

    def duree_visee(self) -> int:
        return self.duree_s if self.duree_s > 0 else DUREES_PAR_DEFAUT.get(self.reseau, DUREES_PAR_DEFAUT["autre"])

    def tutoiement_effectif(self) -> str:
        """« tu » ou « vous ». Automatique : tutoiement sur TikTok et Snapchat ; ailleurs (Facebook,
        Instagram…), vouvoiement pour une clientèle de 35 ans et plus, tutoiement sinon."""
        if self.tutoiement in ("tu", "vous"):
            return self.tutoiement
        if self.reseau in ("tiktok", "snapchat"):
            return "tu"
        return "vous" if self.age in _AGES_VOUVOIEMENT else "tu"

    def devise(self) -> str:
        return pays_de(self.pays).devise

    def liste_mots_interdits(self) -> list[str]:
        morceaux = self.mots_interdits.replace("\n", ",").replace(";", ",").split(",")
        return [m.strip() for m in morceaux if m.strip()]

    def liste_mentions(self) -> list[str]:
        return [ligne.strip() for ligne in self.mentions.splitlines() if ligne.strip()]

    # --- Pré-remplissage -------------------------------------------------------------------------

    def pre_remplir(self, valeurs: dict[str, str]) -> list[str]:
        """Remplit les champs vides (ou encore pré-remplis, ex. d'après une page lue avant) avec ces
        valeurs ; ne touche jamais un champ tapé à la main. Renvoie les champs changés."""
        changes = []
        for nom, valeur in valeurs.items():
            if nom not in CHAMPS_DE_LA_PAGE and nom != "genre":
                continue
            valeur = (valeur or "").strip()
            actuelle = getattr(self, nom)
            if actuelle and nom not in self.pre_remplis:
                continue  # tapé à la main : jamais écrasé
            if valeur == actuelle:
                continue
            setattr(self, nom, valeur)
            if valeur:
                if nom not in self.pre_remplis:
                    self.pre_remplis.append(nom)
            elif nom in self.pre_remplis:
                self.pre_remplis.remove(nom)
            changes.append(nom)
        return changes

    def modifie_a_la_main(self, nom: str) -> None:
        """Le champ a été modifié par toi : il n'est plus « d'après la page »."""
        if nom in self.pre_remplis:
            self.pre_remplis.remove(nom)

    # --- Fichier ---------------------------------------------------------------------------------

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, brut) -> Brief:
        """Brief relu d'un projet ou d'une bibliothèque ; une valeur inconnue reprend sa valeur par défaut."""
        brief = cls()
        if not isinstance(brut, dict):
            return brief
        for champ in fields(cls):
            if champ.name not in brut:
                continue
            valeur = brut[champ.name]
            defaut = getattr(brief, champ.name)
            if isinstance(defaut, bool):
                setattr(brief, champ.name, bool(valeur))
            elif isinstance(defaut, int):
                try:
                    setattr(brief, champ.name, int(valeur))
                except (TypeError, ValueError):
                    pass
            elif isinstance(defaut, list):
                setattr(brief, champ.name, [str(v) for v in valeur] if isinstance(valeur, list) else [])
            elif isinstance(valeur, str):
                setattr(brief, champ.name, valeur)
        if brief.pays not in {p.code for p in PAYS}:
            brief.pays = PAYS_PAR_DEFAUT
        if brief.langue not in LANGUES_ECRITURE:
            brief.langue = pays_de(brief.pays).langues[0]
        for nom, choix in (("reseau", RESEAUX), ("angle", ANGLES), ("tutoiement", TUTOIEMENTS)):
            if getattr(brief, nom) not in choix:
                setattr(brief, nom, next(iter(choix)))
        if brief.age not in TRANCHES_AGE:
            brief.age = ""
        if brief.genre not in GENRES:
            brief.genre = ""
        brief.duree_s = brief.duree_s if DUREE_MIN <= brief.duree_s <= DUREE_MAX else 0
        brief.nombre_accroches = min(max(brief.nombre_accroches, NOMBRE_ACCROCHES_MIN), NOMBRE_ACCROCHES_MAX)
        brief.pre_remplis = [nom for nom in brief.pre_remplis if nom in CHAMPS_DE_LA_PAGE or nom == "genre"]
        return brief
