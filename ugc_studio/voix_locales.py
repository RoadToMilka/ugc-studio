"""Ce que l'app retient des voix (§5.4) : favoris, noms donnés dans l'app, traduction française des
descriptions, et la bibliothèque de Google gardée en mémoire.

Rangement : %APPDATA%\\UGC Studio\\voix.json. La bibliothèque de Google (plusieurs centaines de voix)
n'est redemandée qu'une fois par semaine, ou sur demande (« Actualiser ») ; les extraits audio,
eux, sont rangés à part, dans le cache.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta
from pathlib import Path

from .fournisseurs.google_voix import VOIX_GOOGLE, voix_de_base
from .fournisseurs.voix import VoixBibliotheque
from .stockage import ecrire_json, lire_json

DUREE_BIBLIOTHEQUE = timedelta(days=7)
DUREE_VOIX_CREEES = timedelta(hours=1)  # la liste des voix créées est redemandée au plus toutes les heures
MAX_VOIX_CREEES = 200  # documentation Google (Voice Design) : 200 voix enregistrées par projet
_CHAMPS = {f.name for f in fields(VoixBibliotheque)} - {"extrait_wav"}

GENRES = {"female": "féminine", "male": "masculine", "neutral": "neutre"}
HAUTEURS = {"low": "grave", "medium": "moyenne", "high": "aiguë"}


def _en_dict(voix: VoixBibliotheque) -> dict:
    return {k: v for k, v in asdict(voix).items() if k in _CHAMPS}


def _depuis_dict(brut: dict) -> VoixBibliotheque | None:
    try:
        return VoixBibliotheque(**{k: v for k, v in brut.items() if k in _CHAMPS})
    except TypeError:
        return None


def _maintenant() -> datetime:
    return datetime.now().astimezone()


def _recent(date_iso: str, duree: timedelta) -> bool:
    try:
        date = datetime.fromisoformat(date_iso)
    except ValueError:
        return False
    if date.tzinfo is None:
        date = date.astimezone()
    return _maintenant() - date < duree


def date_lisible(date_iso: str) -> str:
    """« 2027-09-30T10:00:00Z » → « 30/09/2027 » (vide si la date est illisible)."""
    try:
        return datetime.fromisoformat(date_iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y")
    except ValueError:
        return ""


def est_expiree(voix: VoixBibliotheque) -> bool:
    try:
        return datetime.fromisoformat(voix.expire_le.replace("Z", "+00:00")) < _maintenant()
    except ValueError:
        return False


class GestionnaireVoix:
    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        donnees = donnees if isinstance(donnees, dict) else {}
        self._favoris: list[str] = [str(v) for v in donnees.get("favoris") or [] if v]
        self._noms: dict[str, str] = {str(k): str(v) for k, v in (donnees.get("noms") or {}).items() if v}
        self._descriptions_fr: dict[str, str] = {
            str(k): str(v) for k, v in (donnees.get("descriptions_fr") or {}).items() if v
        }
        bibliotheque = donnees.get("bibliotheque") or {}
        self._bibliotheque = [v for v in map(_depuis_dict, bibliotheque.get("voix") or []) if v]
        self._bibliotheque_date = str(bibliotheque.get("date") or "")
        self._creees = [v for v in map(_depuis_dict, donnees.get("voix_creees") or []) if v]
        self._creees_date = str(donnees.get("voix_creees_date") or "")
        self._abonnes: list[Callable[[], None]] = []

    # --- Favoris -----------------------------------------------------------------------------

    def favoris(self) -> list[str]:
        return list(self._favoris)

    def est_favori(self, identifiant: str) -> bool:
        return identifiant in self._favoris

    def basculer_favori(self, identifiant: str) -> bool:
        """Ajoute ou retire des favoris ; renvoie le nouvel état."""
        if identifiant in self._favoris:
            self._favoris.remove(identifiant)
        else:
            self._favoris.append(identifiant)
        self._enregistrer()
        return identifiant in self._favoris

    # --- Noms et descriptions ----------------------------------------------------------------

    def nom(self, identifiant: str) -> str:
        """Nom affiché : celui donné dans l'app, sinon celui de Google, sinon l'identifiant."""
        if identifiant in self._noms:
            return self._noms[identifiant]
        voix = self.voix(identifiant)
        return voix.nom if voix is not None else identifiant

    def renommer(self, identifiant: str, nom: str) -> None:
        """L'API de Google ne permet pas de renommer une voix : le nouveau nom est gardé dans l'app."""
        nom = " ".join(nom.split())
        if nom:
            self._noms[identifiant] = nom
        else:
            self._noms.pop(identifiant, None)
        self._enregistrer()

    def description_fr(self, identifiant: str) -> str:
        return self._descriptions_fr.get(identifiant, "")

    def definir_description_fr(self, identifiant: str, texte: str) -> None:
        if texte.strip():
            self._descriptions_fr[identifiant] = texte.strip()
            self._enregistrer()

    def libelle(self, identifiant: str) -> str:
        """Texte d'une voix dans les listes, ex. « Kore — Ferme · féminine » ou « Léa (ma voix) »."""
        base = voix_de_base(identifiant)
        if base is not None and identifiant not in self._noms:
            return base.libelle
        voix = self.voix(identifiant)
        nom = self.nom(identifiant)
        if voix is None:
            return nom
        if voix.creee:
            return f"{nom} (ma voix)"
        details = [d for d in (GENRES.get(voix.genre, ""), voix.accent or voix.langue) if d]
        return f"{nom} — {' · '.join(details)}" if details else nom

    # --- Bibliothèque de Google et voix créées (gardées en mémoire) ---------------------------

    def bibliotheque(self) -> list[VoixBibliotheque]:
        return list(self._bibliotheque)

    def bibliotheque_a_jour(self) -> bool:
        return bool(self._bibliotheque) and _recent(self._bibliotheque_date, DUREE_BIBLIOTHEQUE)

    def voix_creees_a_jour(self) -> bool:
        return _recent(self._creees_date, DUREE_VOIX_CREEES)

    def definir_bibliotheque(self, voix: list[VoixBibliotheque]) -> None:
        self._bibliotheque = [replace(v, extrait_wav=None) for v in voix if not v.creee]
        self._bibliotheque_date = _maintenant().isoformat(timespec="seconds")
        self._enregistrer()

    def voix_creees(self) -> list[VoixBibliotheque]:
        return list(self._creees)

    def definir_voix_creees(self, voix: list[VoixBibliotheque]) -> None:
        self._creees = [replace(v, extrait_wav=None) for v in voix if v.creee]
        self._creees_date = _maintenant().isoformat(timespec="seconds")
        self._enregistrer()

    def ajouter_voix_creee(self, voix: VoixBibliotheque) -> None:
        self._creees = [v for v in self._creees if v.identifiant != voix.identifiant]
        self._creees.insert(0, replace(voix, extrait_wav=None))
        self._enregistrer()

    def retirer_voix(self, identifiant: str) -> None:
        self._creees = [v for v in self._creees if v.identifiant != identifiant]
        if identifiant in self._favoris:
            self._favoris.remove(identifiant)
        self._noms.pop(identifiant, None)
        self._descriptions_fr.pop(identifiant, None)
        self._enregistrer()

    def voix(self, identifiant: str) -> VoixBibliotheque | None:
        """Voix connue de l'app : créée, de la bibliothèque, ou l'une des 30 voix de base."""
        for voix in (*self._creees, *self._bibliotheque):
            if voix.identifiant == identifiant:
                return voix
        base = voix_de_base(identifiant)
        if base is not None:
            genre = {"F": "female", "M": "male"}.get(base.genre, "")
            return VoixBibliotheque(base.nom, base.nom, base.caractere, genre=genre)
        return None

    # --- Notifications et fichier -------------------------------------------------------------

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    def desabonner(self, fonction: Callable[[], None]) -> None:
        if fonction in self._abonnes:
            self._abonnes.remove(fonction)

    def _enregistrer(self) -> None:
        ecrire_json(
            self._chemin,
            {
                "version_format": 1,
                "favoris": self._favoris,
                "noms": self._noms,
                "descriptions_fr": self._descriptions_fr,
                "bibliotheque": {"date": self._bibliotheque_date, "voix": [_en_dict(v) for v in self._bibliotheque]},
                "voix_creees": [_en_dict(v) for v in self._creees],
                "voix_creees_date": self._creees_date,
            },
        )
        for fonction in list(self._abonnes):
            fonction()


def voix_de_base_en_bibliotheque() -> list[VoixBibliotheque]:
    """Les 30 voix de base, sous la même forme que les voix de la bibliothèque (si Google n'est pas joignable)."""
    return [
        VoixBibliotheque(v.nom, v.nom, v.caractere, genre={"F": "female", "M": "male"}.get(v.genre, ""))
        for v in VOIX_GOOGLE
    ]
