"""Projets (§3.2) : un projet = un dossier qui regroupe tout.

    Documents\\UGC Studio\\Projets\\Sérum Glowzy\\
        projet.json        ← nom, langue, script, réglages de voix, liste des prises…
        prises\\           ← fichiers audio générés (WAV 24 kHz mono)

Rouvrir un projet restaure son état complet. L'enregistrement est automatique.
"""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .chemins import dossier_donnees
from .stockage import ecrire_json, lire_json

journal = logging.getLogger(__name__)

NOM_FICHIER = "projet.json"
DOSSIER_PRISES = "prises"
NB_RECENTS = 10

# §5.7 — Langues proposées (codes « langue-PAYS »).
LANGUES = {
    "fr-FR": "Français",
    "en-US": "Anglais (US)",
    "en-GB": "Anglais (UK)",
    "es-ES": "Espagnol (Espagne)",
    "it-IT": "Italien",
    "nl-BE": "Néerlandais (Belgique)",
    "nl-NL": "Néerlandais (Pays-Bas)",
    "de-DE": "Allemand",
}
LANGUE_PAR_DEFAUT = "fr-FR"

_CARACTERES_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_NOMS_RESERVES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class ErreurProjet(Exception):
    """Problème de projet, avec un message clair pour l'utilisateur."""


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def nom_de_dossier(nom: str) -> str:
    """Nom de projet → nom de dossier valide sous Windows (caractères interdits retirés)."""
    propre = _CARACTERES_INTERDITS.sub(" ", nom)
    propre = " ".join(propre.split()).strip(" .")
    if not propre or propre.upper() in _NOMS_RESERVES:
        propre = f"Projet {propre}".strip()
    return propre[:80]


@dataclass
class ReglagesVoix:
    modele: str = "gemini-3.8-flash-tts"
    voix: str = "Kore"
    style: str = ""


@dataclass
class Prise:
    identifiant: str
    nom: str
    fichier: str  # chemin relatif au dossier du projet, ex. « prises/prise-001.wav »
    date: str
    modele: str
    voix: str
    style: str
    texte_api: str  # texte exact envoyé au TTS
    script: list[dict]  # script au moment de la génération (pour créer les sous-titres)
    duree_s: float
    tokens_entree: int = 0
    tokens_sortie: int = 0
    cout_eur: str | None = None
    note: int = 0  # 0 à 5 étoiles


@dataclass
class Projet:
    dossier: Path
    nom: str
    langue: str = LANGUE_PAR_DEFAUT
    cree_le: str = ""
    modifie_le: str = ""
    voix: ReglagesVoix = field(default_factory=ReglagesVoix)
    script: list[dict] = field(default_factory=list)
    prises: list[Prise] = field(default_factory=list)

    VERSION_FORMAT = 1

    @property
    def fichier(self) -> Path:
        return self.dossier / NOM_FICHIER

    def chemin(self, relatif: str) -> Path:
        return self.dossier / relatif

    def en_dict(self) -> dict:
        return {
            "version_format": self.VERSION_FORMAT,
            "nom": self.nom,
            "langue": self.langue,
            "cree_le": self.cree_le,
            "modifie_le": self.modifie_le,
            "voix": asdict(self.voix),
            "script": self.script,
            "prises": [asdict(p) for p in self.prises],
        }

    @classmethod
    def depuis_dict(cls, dossier: Path, donnees: dict) -> Projet:
        voix = donnees.get("voix") or {}
        prises = []
        for brut in donnees.get("prises", []):
            try:
                prises.append(Prise(**{k: v for k, v in brut.items() if k in Prise.__dataclass_fields__}))
            except TypeError as erreur:
                journal.warning("Prise illisible ignorée (%s)", erreur)
        return cls(
            dossier=dossier,
            nom=donnees.get("nom") or dossier.name,
            langue=donnees.get("langue") if donnees.get("langue") in LANGUES else LANGUE_PAR_DEFAUT,
            cree_le=donnees.get("cree_le", ""),
            modifie_le=donnees.get("modifie_le", ""),
            voix=ReglagesVoix(**{k: v for k, v in voix.items() if k in ReglagesVoix.__dataclass_fields__}),
            script=list(donnees.get("script") or []),
            prises=prises,
        )


class GestionnaireProjets:
    """Projet ouvert, création / ouverture / enregistrement, et liste des projets récents."""

    def __init__(self, fichier_recents: Path | None = None):
        self._fichier_recents = fichier_recents or dossier_donnees() / "projets_recents.json"
        self.projet: Projet | None = None
        self._abonnes: list[Callable[[Projet | None], None]] = []

    # --- Projet ouvert -----------------------------------------------------------------------

    def creer(self, nom: str, dossier_parent: Path, langue: str = LANGUE_PAR_DEFAUT) -> Projet:
        nom = " ".join(nom.split())
        if not nom:
            raise ErreurProjet("Donne un nom au projet.")
        base = dossier_parent / nom_de_dossier(nom)
        dossier = base
        numero = 2
        while dossier.exists():
            dossier = base.with_name(f"{base.name} ({numero})")
            numero += 1
        try:
            (dossier / DOSSIER_PRISES).mkdir(parents=True)
        except OSError as erreur:
            raise ErreurProjet(f"Impossible de créer le dossier du projet : {erreur}") from erreur
        maintenant = _maintenant()
        projet = Projet(dossier=dossier, nom=nom, langue=langue, cree_le=maintenant, modifie_le=maintenant)
        self._activer(projet)
        self.enregistrer()
        journal.info("Projet créé : %s (%s)", nom, dossier)
        return projet

    def ouvrir(self, dossier: Path) -> Projet:
        fichier = dossier / NOM_FICHIER
        if not fichier.exists():
            raise ErreurProjet(f"Ce dossier ne contient pas de projet UGC Studio ({NOM_FICHIER} absent).")
        donnees = lire_json(fichier, None)
        if not isinstance(donnees, dict):
            raise ErreurProjet("Le fichier du projet est illisible. Une copie a été mise de côté dans le dossier.")
        projet = Projet.depuis_dict(dossier, donnees)
        (dossier / DOSSIER_PRISES).mkdir(exist_ok=True)
        self._activer(projet)
        journal.info("Projet ouvert : %s (%s)", projet.nom, dossier)
        return projet

    def fermer(self) -> None:
        self.projet = None
        self._notifier()

    def enregistrer(self) -> None:
        if self.projet is None:
            return
        self.projet.modifie_le = _maintenant()
        ecrire_json(self.projet.fichier, self.projet.en_dict())

    def renommer(self, nom: str) -> None:
        nom = " ".join(nom.split())
        if self.projet is None or not nom:
            return
        self.projet.nom = nom
        self.enregistrer()
        self._memoriser_recent(self.projet)
        self._notifier()

    # --- Prises ------------------------------------------------------------------------------

    def ajouter_prise(self, audio_wav: bytes, **infos) -> Prise:
        """Range l'audio dans le dossier « prises » du projet et l'ajoute à la liste."""
        projet = self._projet_ouvert()
        # Numéro suivant, d'après les noms de fichiers (le nom affiché, lui, peut être renommé).
        numeros = [int(m.group(1)) for p in projet.prises if (m := re.search(r"prise-(\d+)", p.fichier))]
        numero = 1 + max(numeros, default=0)
        relatif = f"{DOSSIER_PRISES}/prise-{numero:03d}.wav"
        while projet.chemin(relatif).exists():
            numero += 1
            relatif = f"{DOSSIER_PRISES}/prise-{numero:03d}.wav"
        projet.chemin(relatif).parent.mkdir(parents=True, exist_ok=True)
        projet.chemin(relatif).write_bytes(audio_wav)
        prise = Prise(
            identifiant=uuid.uuid4().hex[:12],
            nom=f"Prise {numero}",
            fichier=relatif,
            date=_maintenant(),
            **infos,
        )
        projet.prises.append(prise)
        self.enregistrer()
        return prise

    def prise(self, identifiant: str) -> Prise:
        for prise in self._projet_ouvert().prises:
            if prise.identifiant == identifiant:
                return prise
        raise ErreurProjet("Cette prise n'existe plus.")

    def modifier_prise(self, identifiant: str, **changements) -> None:
        prise = self.prise(identifiant)
        for cle, valeur in changements.items():
            setattr(prise, cle, valeur)
        self.enregistrer()

    def supprimer_prise(self, identifiant: str) -> None:
        projet = self._projet_ouvert()
        prise = self.prise(identifiant)
        try:
            projet.chemin(prise.fichier).unlink(missing_ok=True)
        except OSError:
            journal.warning("Fichier de prise non supprimé : %s", prise.fichier, exc_info=True)
        projet.prises.remove(prise)
        self.enregistrer()

    # --- Récents -----------------------------------------------------------------------------

    def recents(self) -> list[tuple[str, Path]]:
        """Projets récemment ouverts qui existent encore (du plus récent au plus ancien)."""
        donnees = lire_json(self._fichier_recents, [])
        resultat = []
        for element in donnees if isinstance(donnees, list) else []:
            try:
                dossier = Path(element["dossier"])
            except (KeyError, TypeError):
                continue
            if (dossier / NOM_FICHIER).exists():
                resultat.append((element.get("nom") or dossier.name, dossier))
        return resultat

    def dernier_projet(self) -> Path | None:
        recents = self.recents()
        return recents[0][1] if recents else None

    # --- Notifications -----------------------------------------------------------------------

    def abonner(self, fonction: Callable[[Projet | None], None]) -> None:
        self._abonnes.append(fonction)

    # --- Interne -----------------------------------------------------------------------------

    def _projet_ouvert(self) -> Projet:
        if self.projet is None:
            raise ErreurProjet("Aucun projet n'est ouvert.")
        return self.projet

    def _activer(self, projet: Projet) -> None:
        self.projet = projet
        self._memoriser_recent(projet)
        self._notifier()

    def _memoriser_recent(self, projet: Projet) -> None:
        anciens = lire_json(self._fichier_recents, [])
        anciens = anciens if isinstance(anciens, list) else []
        dossier = str(projet.dossier)
        nouveaux = [{"nom": projet.nom, "dossier": dossier}] + [
            e for e in anciens if isinstance(e, dict) and e.get("dossier") != dossier
        ]
        try:
            ecrire_json(self._fichier_recents, nouveaux[:NB_RECENTS])
        except OSError:
            journal.warning("Liste des projets récents non enregistrée", exc_info=True)

    def _notifier(self) -> None:
        for fonction in list(self._abonnes):
            fonction(self.projet)


def copier_fichier(source: Path, destination: Path) -> None:
    """Copie un fichier (ex. export d'une prise en WAV)."""
    shutil.copyfile(source, destination)
