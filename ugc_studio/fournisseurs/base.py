"""Ce que tout adaptateur de fournisseur sait faire (§3.4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from ..journal import declarer_secret
from .stt import RequeteTranscription, ResultatTranscription
from .texte import RequeteTexte, ResultatTexte
from .voix import RecepteurAudio, RequeteVoiceDesign, RequeteVoix, ResultatVoix, VoixBibliotheque, VoixCreee


class ErreurFournisseur(Exception):
    """Problème lors d'un appel à un fournisseur.

    `message` : phrase claire en français, affichée à l'utilisateur.
    `code` : catégorie (« cle_invalide », « acces_refuse », « quota », « reseau », « serveur »…).
    `detail` : texte technique d'origine, écrit dans le journal d'erreurs.
    """

    def __init__(self, message: str, code: str = "inconnu", detail: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class InfoModele:
    """Un modèle accessible avec une clé, tel que le fournisseur le décrit."""

    identifiant: str  # ex. « gemini-3.8-flash-tts »
    nom: str = ""
    description: str = ""
    methodes: tuple[str, ...] = ()
    limite_entree: int | None = None
    limite_sortie: int | None = None


@dataclass
class ResultatTest:
    ok: bool
    message: str
    modeles: list[InfoModele] = field(default_factory=list)
    code: str = ""


class Adaptateur(ABC):
    identifiant: ClassVar[str]  # ex. « google »
    nom: ClassVar[str]  # ex. « Google (Gemini) »
    aide_cle: ClassVar[str] = ""  # où obtenir une clé
    adresse_cles: ClassVar[str] = ""  # page web de création des clés

    def __init__(self, cle: str):
        self._cle = cle.strip()
        declarer_secret(self._cle)  # la clé ne pourra jamais apparaître dans le journal

    @abstractmethod
    def lister_modeles(self) -> list[InfoModele]:
        """Modèles accessibles avec cette clé."""

    def tester_cle(self) -> ResultatTest:
        """La clé fonctionne-t-elle ? (Demander la liste des modèles est gratuit.)"""
        try:
            modeles = self.lister_modeles()
        except ErreurFournisseur as erreur:
            return ResultatTest(False, erreur.message, code=erreur.code)
        return ResultatTest(True, f"Clé valide, {len(modeles)} modèles accessibles.", modeles)

    # --- Fonctions des tâches (chaque fournisseur n'implémente que ce qu'il sait faire) -------

    def generer_voix(self, requete: RequeteVoix, recevoir_audio: RecepteurAudio | None = None) -> ResultatVoix:
        """Génère une voix off (TTS). Avec `recevoir_audio`, l'audio est demandé « en flux » : chaque
        morceau lui est transmis dès son arrivée (pour l'écouter avant la fin du calcul)."""
        raise ErreurFournisseur(f"{self.nom} ne sait pas générer de voix.", "non_disponible")

    def transcrire(self, requete: RequeteTranscription) -> ResultatTranscription:
        """Transcrit un audio (STT), mot par mot avec les temps si demandé."""
        raise ErreurFournisseur(f"{self.nom} ne sait pas transcrire.", "non_disponible")

    def generer_texte(self, requete: RequeteTexte) -> ResultatTexte:
        """Génère du texte (ex. traduction d'un style en anglais)."""
        raise ErreurFournisseur(f"{self.nom} ne sait pas générer de texte.", "non_disponible")

    def lister_voix(self, types: tuple[str, ...] = ("prebuilt",)) -> list[VoixBibliotheque]:
        """Voix de la bibliothèque du fournisseur (« prebuilt ») ou voix créées (« prompted »…)."""
        raise ErreurFournisseur(f"{self.nom} n'a pas de bibliothèque de voix.", "non_disponible")

    def obtenir_voix(self, identifiant: str) -> VoixBibliotheque:
        """Détail d'une voix, avec son extrait audio s'il existe."""
        raise ErreurFournisseur(f"{self.nom} n'a pas de bibliothèque de voix.", "non_disponible")

    def creer_voix(self, requete: RequeteVoiceDesign) -> VoixCreee:
        """Crée une voix à partir d'une description (Voice Design)."""
        raise ErreurFournisseur(f"{self.nom} ne sait pas créer de voix.", "non_disponible")

    def supprimer_voix(self, identifiant: str) -> None:
        raise ErreurFournisseur(f"{self.nom} ne sait pas supprimer de voix.", "non_disponible")
