"""Modèles chargés (V1.1, §4.2 bis) : les modèles mis à disposition dans l'app, et où ils servent.

Seuls les modèles chargés apparaissent dans Réglages → Modèles et prix et dans les listes « Modèle »
des modules. Au départ : ceux dont l'app se sert (Gemini 3.8 Flash TTS, 3.5 Transcribe, et 3.8
Flash pour les scripts et les traductions), plus 3.8 Flash-Lite TTS, pratique et lié à Flash TTS,
et Gemini 3.1 Pro (aperçu), à comparer à 3.8 Flash pour écrire les scripts (V2). La fenêtre
« Choisir les modèles… » en ajoute ou en retire.

« Utilisé dans » : où un modèle sert en ce moment (le modèle choisi dans le module Script ou Voix,
dans les options de Transcription, pour créer les sous-titres d'une prise ; celui d'une voix créée
ou d'un style enregistré ; celui des traductions). Un modèle utilisé reste toujours chargé : aucun
module ne peut se retrouver sans modèle. Un projet, une voix créée ou un style qui se sert d'un
modèle non chargé le recharge donc automatiquement, sans rien changer dans le projet.

Rangement : %APPDATA%\\UGC Studio\\modeles.json. Les prix saisis à la main (prix.json) sont gardés,
même si le modèle est retiré puis rechargé.

Format 2 (V2, lot 1) : un fichier du format 1 (v1.1.0) reçoit une seule fois les modèles ajoutés au
départ depuis (Gemini 3.1 Pro). Si tu le retires ensuite, il ne revient pas.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from .fournisseurs.capacites import MODELES_CONNUS
from .stockage import ecrire_json, lire_json
from .styles import BibliothequeStyles
from .traduction import MODELE_TRADUCTION
from .voix_locales import VOIX_CREEES, GestionnaireVoix

MODELES_DE_DEPART = (
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
    "gemini-3.5-transcribe",
    "gemini-3.8-flash",
    "gemini-3.1-pro-preview",
)
VERSION_FORMAT = 2
# Modèles ajoutés au départ après la v1.1.0 (format 1) : proposés une seule fois aux anciens fichiers.
AJOUTES_AU_FORMAT_2 = ("gemini-3.1-pro-preview",)

# Où un modèle peut servir, dans l'ordre d'affichage de la colonne « Utilisé dans ».
SCRIPT = "Script"
VOIX = "Voix"
TRANSCRIPTION = "Transcription"
SOUS_TITRES = "Sous-titres"
TRADUCTIONS = "Traductions"
MODULES = (SCRIPT, VOIX, TRANSCRIPTION, SOUS_TITRES, TRADUCTIONS)

# Ce qui a changé : la liste des modèles chargés, ou seulement où ils servent.
CHARGES = "charges"
USAGES = "usages"

_RANG = {modele.identifiant: rang for rang, modele in enumerate(MODELES_CONNUS)}


def dans_l_ordre(identifiants: Iterable[str]) -> list[str]:
    """Modèles du catalogue dans son ordre (le modèle conseillé d'abord), puis les autres par nom."""
    return sorted(set(identifiants), key=lambda m: (_RANG.get(m, len(_RANG)), m))


class ModelesCharges:
    def __init__(self, chemin: Path, voix: GestionnaireVoix, styles: BibliothequeStyles):
        self._chemin = chemin
        self._voix = voix
        self._styles = styles
        donnees = lire_json(chemin, {})
        liste = donnees.get("modeles") if isinstance(donnees, dict) else None
        self._charges: list[str] = (
            dans_l_ordre(str(m) for m in liste if m) if isinstance(liste, list) else list(MODELES_DE_DEPART)
        )
        if isinstance(liste, list) and donnees.get("version_format", 1) < VERSION_FORMAT:
            # Fichier de la v1.1.0 : les modèles ajoutés au départ depuis sont chargés une fois.
            self._charges = dans_l_ordre([*self._charges, *AJOUTES_AU_FORMAT_2])
            self._enregistrer()
        # Modèle choisi en ce moment dans chaque module (déclaré par le module lui-même).
        self._choisis: dict[str, str] = {TRADUCTIONS: MODELE_TRADUCTION}
        self._abonnes: list[tuple[Callable[[], None], frozenset[str]]] = []
        voix.abonner(self._usages_changes, {VOIX_CREEES})
        styles.abonner(self._usages_changes)
        self._charger_les_utilises()

    # --- Modèles chargés -----------------------------------------------------------------------

    def charges(self) -> list[str]:
        return list(self._charges)

    def est_charge(self, identifiant: str) -> bool:
        return identifiant in self._charges

    def definir(self, identifiants: Iterable[str]) -> None:
        """Choix de la fenêtre « Choisir les modèles » ; les modèles utilisés restent chargés."""
        nouveaux = dans_l_ordre([*identifiants, *self.usages()])
        if nouveaux != self._charges:
            self._charges = nouveaux
            self._enregistrer()
            self._prevenir({CHARGES})

    # --- Où les modèles servent ----------------------------------------------------------------

    def choisir(self, module: str, identifiant: str | None) -> None:
        """Le module (SCRIPT, VOIX, TRANSCRIPTION, SOUS_TITRES) se sert maintenant de ce modèle (ou d'aucun)."""
        if self._choisis.get(module, "") == (identifiant or ""):
            return
        self._choisis[module] = identifiant or ""
        self._usages_changes()

    def usages(self) -> dict[str, list[str]]:
        """{modèle: modules où il sert}, ex. {"gemini-3.8-flash": ["Traductions"]}."""
        par_modele: dict[str, set[str]] = {}
        for module, modele in self._choisis.items():
            if modele:
                par_modele.setdefault(modele, set()).add(module)
        for creee in self._voix.voix_creees():
            if creee.modele:
                par_modele.setdefault(creee.modele, set()).add(VOIX)
        for style in self._styles.styles:
            if style.modele:
                par_modele.setdefault(style.modele, set()).add(VOIX)
        return {modele: [m for m in MODULES if m in modules] for modele, modules in par_modele.items()}

    def utilise_dans(self, identifiant: str) -> list[str]:
        return self.usages().get(identifiant, [])

    def _usages_changes(self) -> None:
        self._charger_les_utilises()
        self._prevenir({USAGES})

    def _charger_les_utilises(self) -> None:
        """Un modèle utilisé mais pas chargé (ex. projet d'une version précédente) est rechargé."""
        manquants = [m for m in self.usages() if m not in self._charges]
        if manquants:
            self._charges = dans_l_ordre([*self._charges, *manquants])
            self._enregistrer()
            self._prevenir({CHARGES})

    # --- Notifications et fichier -------------------------------------------------------------

    def abonner(self, fonction: Callable[[], None], sujets: Iterable[str] = (CHARGES, USAGES)) -> None:
        self._abonnes.append((fonction, frozenset(sujets)))

    def desabonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes = [(f, s) for f, s in self._abonnes if f != fonction]

    def _prevenir(self, sujets: set[str]) -> None:
        for fonction, suivis in list(self._abonnes):
            if suivis & sujets:
                fonction()

    def _enregistrer(self) -> None:
        ecrire_json(self._chemin, {"version_format": VERSION_FORMAT, "modeles": self._charges})
