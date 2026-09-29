"""Bibliothèque de styles personnalisés (§5.5) et assistant de style structuré.

Un style enregistré = nom, catégorie, fournisseur + modèle, voix, consigne de style (en anglais,
envoyée à Google, avec sa traduction française affichée), balises par défaut, langue.
Quelques exemples sont fournis au départ ; ils sont modifiables et supprimables.

L'assistant assemble une consigne courte « émotion / attitude + rythme » directement en anglais,
à partir de choix en français (aucun appel à l'API).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .stockage import ecrire_json, lire_json

# --- Assistant de style : (français, anglais) -------------------------------------------------

EMOTIONS: tuple[tuple[str, str], ...] = (
    ("chaleureux", "warm"),
    ("enthousiaste", "enthusiastic"),
    ("complice", "playful"),
    ("confiant", "confident"),
    ("sincère", "sincere"),
    ("rassurant", "reassuring"),
    ("amusé", "amused"),
    ("excité", "excited"),
    ("surpris", "surprised"),
    ("énergique", "energetic"),
    ("calme", "calm"),
    ("détendu", "relaxed"),
    ("sérieux", "serious"),
    ("mystérieux", "mysterious"),
    ("ému", "moved"),
    ("chuchoté", "whispered"),
)
RYTHMES: tuple[tuple[str, str], ...] = (
    ("débit rapide", "fast-paced"),
    ("débit naturel", "natural pace"),
    ("débit posé", "measured pace"),
    ("débit lent", "slow pace"),
    ("rythme percutant", "punchy delivery"),
    ("ton de conversation", "conversational tone"),
)
INTENSITES: tuple[tuple[str, str], ...] = (
    ("voix douce", "soft voice"),
    ("voix projetée", "projected voice"),
    ("sourire dans la voix", "smiling voice"),
)

CATEGORIES_PAR_DEFAUT = ("UGC témoignage", "Unboxing", "Placement influenceur", "Hook", "Pub classique")


def _traduire(choix: str, table: tuple[tuple[str, str], ...]) -> str:
    return next((en for fr, en in table if fr == choix), choix)


def assembler(emotion: str, emotion2: str = "", rythme: str = "", intensite: str = "") -> tuple[str, str]:
    """Choix de l'assistant (en français) → (consigne anglaise, traduction française).

    ex. (« chaleureux », « enthousiaste », « débit rapide ») →
        (« warm and enthusiastic, fast-paced », « chaleureux et enthousiaste, débit rapide »)
    """
    emotions_fr = [e for e in (emotion, emotion2) if e]
    francais = " et ".join(emotions_fr)
    anglais = " and ".join(_traduire(e, EMOTIONS) for e in emotions_fr)
    for choix, table in ((rythme, RYTHMES), (intensite, INTENSITES)):
        if choix:
            francais = f"{francais}, {choix}" if francais else choix
            anglais = f"{anglais}, {_traduire(choix, table)}" if anglais else _traduire(choix, table)
    return anglais, francais


# --- Bibliothèque ----------------------------------------------------------------------------


@dataclass
class Style:
    identifiant: str
    nom: str
    categorie: str
    consigne: str  # en anglais : envoyée à Google
    consigne_fr: str = ""  # traduction française affichée
    fournisseur: str = "google"
    modele: str = "gemini-3.8-flash-tts"
    voix: str = "Kore"
    balises: list[str] = field(default_factory=list)  # balises souvent utilisées avec ce style
    langue: str = "fr-FR"


def _nouvel_identifiant() -> str:
    return uuid.uuid4().hex[:12]


EXEMPLES: tuple[Style, ...] = (
    Style("ex-temoignage", "Témoignage chaleureux", "UGC témoignage", "warm and sincere, natural pace",
          "chaleureux et sincère, débit naturel", voix="Kore", balises=["short pause", "laugh"]),
    Style("ex-hook", "Hook énergique", "Hook", "excited and energetic, fast-paced",
          "excité et énergique, débit rapide", voix="Puck", balises=["gasp"]),
    Style("ex-unboxing", "Unboxing complice", "Unboxing", "playful and amused, conversational tone",
          "complice et amusé, ton de conversation", voix="Leda", balises=["giggle", "short pause"]),
    Style("ex-influence", "Placement influenceur", "Placement influenceur", "relaxed and confident, conversational tone",
          "détendu et confiant, ton de conversation", voix="Aoede"),
    Style("ex-classique", "Pub classique", "Pub classique", "confident and reassuring, measured pace",
          "confiant et rassurant, débit posé", voix="Charon"),
    Style("ex-chuchote", "Confidence chuchotée", "Hook", "whispered and playful",
          "chuchoté et complice", voix="Enceladus"),
)


class BibliothequeStyles:
    """Styles enregistrés, dans %APPDATA%\\UGC Studio\\styles.json (exemples fournis au premier lancement)."""

    def __init__(self, chemin: Path):
        self._chemin = chemin
        self._abonnes: list[Callable[[], None]] = []
        donnees = lire_json(chemin, None)
        if isinstance(donnees, dict) and isinstance(donnees.get("styles"), list):
            self.styles = [self._lire(s) for s in donnees["styles"] if isinstance(s, dict)]
            self.styles = [s for s in self.styles if s is not None]
        else:
            self.styles = [Style(**asdict(s)) for s in EXEMPLES]

    @staticmethod
    def _lire(brut: dict) -> Style | None:
        try:
            return Style(**{k: v for k, v in brut.items() if k in Style.__dataclass_fields__})
        except TypeError:
            return None

    def categories(self) -> list[str]:
        vues = list(CATEGORIES_PAR_DEFAUT)
        for style in self.styles:
            if style.categorie and style.categorie not in vues:
                vues.append(style.categorie)
        return vues

    def style(self, identifiant: str) -> Style | None:
        return next((s for s in self.styles if s.identifiant == identifiant), None)

    def enregistrer_style(self, style: Style) -> Style:
        """Ajoute un nouveau style ou met à jour un style existant."""
        if not style.identifiant:
            style.identifiant = _nouvel_identifiant()
        existant = self.style(style.identifiant)
        if existant is None:
            self.styles.append(style)
        else:
            self.styles[self.styles.index(existant)] = style
        self._enregistrer()
        return style

    def dupliquer(self, identifiant: str) -> Style:
        source = self.style(identifiant)
        copie = Style(**{**asdict(source), "identifiant": _nouvel_identifiant(), "nom": f"{source.nom} (copie)"})
        self.styles.append(copie)
        self._enregistrer()
        return copie

    def supprimer(self, identifiant: str) -> None:
        self.styles = [s for s in self.styles if s.identifiant != identifiant]
        self._enregistrer()

    def par_categorie(self) -> list[tuple[str, list[Style]]]:
        """Styles rangés par catégorie (catégories vides omises), dans l'ordre des catégories."""
        return [
            (categorie, [s for s in self.styles if s.categorie == categorie])
            for categorie in self.categories()
            if any(s.categorie == categorie for s in self.styles)
        ]

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    def desabonner(self, fonction: Callable[[], None]) -> None:
        if fonction in self._abonnes:
            self._abonnes.remove(fonction)

    def _enregistrer(self) -> None:
        ecrire_json(self._chemin, {"version_format": 1, "styles": [asdict(s) for s in self.styles]})
        for fonction in list(self._abonnes):
            fonction()
