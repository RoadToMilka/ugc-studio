"""Types communs pour la génération de voix (TTS), quel que soit le fournisseur."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# Reçoit chaque morceau d'audio dès son arrivée pendant une génération « en flux » :
# (échantillons PCM 16 bits mono, fréquence en Hz). Sert à écouter la voix avant la fin du calcul.
RecepteurAudio = Callable[[bytes, int], None]


@dataclass(frozen=True)
class Replique:
    """Un bloc du script, avec sa consigne de style facultative (§5.3)."""

    texte: str  # texte exact à prononcer (balises « <laugh> » comprises)
    style: str = ""  # ex. « chaleureux et enthousiaste, débit rapide »


@dataclass(frozen=True)
class RequeteVoix:
    modele: str
    voix: str  # voix de base (ex. « Kore ») ou identifiant d'une voix créée
    repliques: tuple[Replique, ...]


@dataclass
class ResultatVoix:
    audio_wav: bytes  # fichier WAV complet (24 kHz, mono, 16 bits)
    duree_s: float
    tokens_entree: int = 0
    tokens_sortie: int = 0
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VoixDeBase:
    nom: str
    caractere: str  # en français
    caractere_origine: str  # tel que décrit par Google
    genre: str  # « F » ou « M » (indicatif)

    @property
    def libelle(self) -> str:
        genre = {"F": "féminine", "M": "masculine"}.get(self.genre, "")
        return f"{self.nom} — {self.caractere}" + (f" · {genre}" if genre else "")


# --- Bibliothèque de voix et Voice Design (§5.4, §5.4 bis) ----------------------------------


@dataclass(frozen=True)
class VoixBibliotheque:
    """Une voix de la bibliothèque du fournisseur : voix prête à l'emploi ou voix créée."""

    identifiant: str  # à donner au TTS (ex. « Kore » ou « voice_abc123 »)
    nom: str
    description: str = ""
    langue: str = ""  # code BCP-47, ex. « fr-FR »
    region: str = ""
    accent: str = ""
    genre: str = ""  # « female », « male », « neutral »…
    hauteur: str = ""  # « low », « medium », « high »
    persona: str = ""
    contexte: str = ""
    type: str = "prebuilt"  # « prebuilt » (Google), « prompted » (Voice Design), « replicated »
    modele: str = ""  # modèle qui a servi à créer la voix (voix créées)
    expire_le: str = ""  # date d'expiration (voix créées), au format ISO
    extrait_wav: bytes | None = field(default=None, compare=False, repr=False)  # extrait audio, si fourni

    @property
    def creee(self) -> bool:
        """Voix créée par l'utilisateur (Voice Design ou clonage), et non une voix de Google."""
        return self.type in ("prompted", "replicated")


@dataclass(frozen=True)
class RequeteVoiceDesign:
    """Créer une voix à partir d'une description (Voice Design, §5.4 bis)."""

    modele: str
    nom: str
    description: str  # en anglais, 1 à 2 phrases
    langue: str = ""
    genre: str = ""


@dataclass
class VoixCreee:
    voix: VoixBibliotheque
    tokens_entree: int = 0
    tokens_sortie: int = 0
