"""Ce que l'app retient des voix (§5.4) : favoris, noms donnés dans l'app, traduction française des
descriptions, voix créées, et la bibliothèque de Google gardée en mémoire.

Rangement, dans %APPDATA%\\UGC Studio\\ :
- voix.json : favoris, noms, traductions et voix créées. Petit fichier, réécrit à chaque changement.
- bibliotheque_voix.json : la bibliothèque de Google (plus de 2 000 voix). Réécrite seulement quand
  elle est redemandée (une fois par semaine, ou « Actualiser »).

Pourquoi deux fichiers ? Jusqu'à la 1.0.3, la bibliothèque était dans voix.json : chaque clic sur ★
réécrivait tout le fichier (plus de 2 000 voix), puis chaque écran ouvert se reconstruisait. Chaque
changement dit maintenant ce qu'il touche (favoris, bibliothèque…), et seuls les écrans concernés
sont prévenus. Les extraits audio, eux, sont rangés à part, dans le cache.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta
from pathlib import Path

from .fournisseurs.google_voix import VOIX_GOOGLE, voix_de_base
from .fournisseurs.voix import VoixBibliotheque
from .stockage import ecrire_json, lire_json

DUREE_BIBLIOTHEQUE = timedelta(days=7)
DUREE_VOIX_CREEES = timedelta(hours=1)  # la liste des voix créées est redemandée au plus toutes les heures
MAX_VOIX_CREEES = 200  # documentation Google (Voice Design) : 200 voix enregistrées par projet
FICHIER_BIBLIOTHEQUE = "bibliotheque_voix.json"
_CHAMPS = {f.name for f in fields(VoixBibliotheque)} - {"extrait_wav"}

GENRES = {"female": "féminine", "male": "masculine", "neutral": "neutre"}
HAUTEURS = {"low": "grave", "medium": "moyenne", "high": "aiguë"}

# Ce qui a changé : chaque écran ne s'abonne qu'à ce qui le concerne.
FAVORIS = "favoris"
NOMS = "noms"
TRADUCTIONS = "traductions"
BIBLIOTHEQUE = "bibliotheque"
VOIX_CREEES = "voix_creees"
TOUT = frozenset({FAVORIS, NOMS, TRADUCTIONS, BIBLIOTHEQUE, VOIX_CREEES})


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
        self._chemin_bibliotheque = chemin.with_name(FICHIER_BIBLIOTHEQUE)
        donnees = lire_json(chemin, {})
        donnees = donnees if isinstance(donnees, dict) else {}
        self._favoris: list[str] = [str(v) for v in donnees.get("favoris") or [] if v]
        self._noms: dict[str, str] = {str(k): str(v) for k, v in (donnees.get("noms") or {}).items() if v}
        self._descriptions_fr: dict[str, str] = {
            str(k): str(v) for k, v in (donnees.get("descriptions_fr") or {}).items() if v
        }
        self._creees = [v for v in map(_depuis_dict, donnees.get("voix_creees") or []) if v]
        self._creees_date = str(donnees.get("voix_creees_date") or "")

        bibliotheque = lire_json(self._chemin_bibliotheque, None)
        ancienne = donnees.get("bibliotheque")  # 1.0.3 et avant : dans voix.json
        a_deplacer = isinstance(ancienne, dict)
        if not isinstance(bibliotheque, dict):
            bibliotheque = ancienne if a_deplacer else {}
        self._bibliotheque = [v for v in map(_depuis_dict, bibliotheque.get("voix") or []) if v]
        self._bibliotheque_date = str(bibliotheque.get("date") or "")
        self._abonnes: list[tuple[Callable[[], None], frozenset[str]]] = []
        self._index: dict[str, VoixBibliotheque] = {}
        self._indexer()
        if a_deplacer:
            # Rangement de la 1.0.4 : la bibliothèque passe dans son propre fichier, une seule fois.
            self._enregistrer_bibliotheque()
            self._enregistrer()

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
        self._enregistrer(FAVORIS)
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
        self._enregistrer(NOMS)

    def description_fr(self, identifiant: str) -> str:
        return self._descriptions_fr.get(identifiant, "")

    def definir_description_fr(self, identifiant: str, texte: str) -> None:
        if texte.strip():
            self._descriptions_fr[identifiant] = texte.strip()
            self._enregistrer(TRADUCTIONS)

    def libelle(self, identifiant: str) -> str:
        """Texte d'une voix dans les listes, ex. « Kore · Ferme · féminine » ou « Léa (ma voix) »."""
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
        return " · ".join([nom, *details])

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
        self._indexer()
        self._enregistrer_bibliotheque()
        self._prevenir({BIBLIOTHEQUE})

    def voix_creees(self) -> list[VoixBibliotheque]:
        return list(self._creees)

    def definir_voix_creees(self, voix: list[VoixBibliotheque]) -> None:
        self._creees = [replace(v, extrait_wav=None) for v in voix if v.creee]
        self._creees_date = _maintenant().isoformat(timespec="seconds")
        self._indexer()
        self._enregistrer(VOIX_CREEES)

    def ajouter_voix_creee(self, voix: VoixBibliotheque) -> None:
        self._creees = [v for v in self._creees if v.identifiant != voix.identifiant]
        self._creees.insert(0, replace(voix, extrait_wav=None))
        self._indexer()
        self._enregistrer(VOIX_CREEES)

    def retirer_voix(self, identifiant: str) -> None:
        self._creees = [v for v in self._creees if v.identifiant != identifiant]
        if identifiant in self._favoris:
            self._favoris.remove(identifiant)
        self._noms.pop(identifiant, None)
        self._descriptions_fr.pop(identifiant, None)
        self._indexer()
        self._enregistrer(VOIX_CREEES, FAVORIS, NOMS, TRADUCTIONS)

    def voix(self, identifiant: str) -> VoixBibliotheque | None:
        """Voix connue de l'app : créée, de la bibliothèque, ou l'une des 30 voix de base."""
        connue = self._index.get(identifiant)
        if connue is not None:
            return connue
        base = voix_de_base(identifiant)
        if base is not None:
            genre = {"F": "female", "M": "male"}.get(base.genre, "")
            return VoixBibliotheque(base.nom, base.nom, base.caractere, genre=genre)
        return None

    def _indexer(self) -> None:
        """Voix rangées par identifiant (une recherche parmi plus de 2 000 voix, sans les parcourir).
        Une voix créée l'emporte sur une voix de la bibliothèque qui aurait le même identifiant."""
        self._index = {v.identifiant: v for v in self._bibliotheque}
        self._index.update((v.identifiant, v) for v in self._creees)

    # --- Notifications et fichiers ------------------------------------------------------------

    def abonner(self, fonction: Callable[[], None], sujets: Iterable[str] = TOUT) -> None:
        """`fonction` est appelée après chaque changement de l'un des `sujets` (FAVORIS, NOMS,
        TRADUCTIONS, BIBLIOTHEQUE, VOIX_CREEES ; tous par défaut)."""
        self._abonnes.append((fonction, frozenset(sujets)))

    def desabonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes = [(f, s) for f, s in self._abonnes if f != fonction]

    def _prevenir(self, sujets: set[str]) -> None:
        for fonction, suivis in list(self._abonnes):
            if suivis & sujets:
                fonction()

    def _enregistrer(self, *sujets: str) -> None:
        """Écrit le petit fichier (tout sauf la bibliothèque), puis prévient les écrans concernés."""
        ecrire_json(
            self._chemin,
            {
                "version_format": 2,
                "favoris": self._favoris,
                "noms": self._noms,
                "descriptions_fr": self._descriptions_fr,
                "voix_creees": [_en_dict(v) for v in self._creees],
                "voix_creees_date": self._creees_date,
            },
        )
        if sujets:
            self._prevenir(set(sujets))

    def _enregistrer_bibliotheque(self) -> None:
        ecrire_json(
            self._chemin_bibliotheque,
            {
                "version_format": 1,
                "date": self._bibliotheque_date,
                "voix": [_en_dict(v) for v in self._bibliotheque],
            },
        )


def voix_de_base_en_bibliotheque() -> list[VoixBibliotheque]:
    """Les 30 voix de base, sous la même forme que les voix de la bibliothèque (si Google n'est pas joignable)."""
    return [
        VoixBibliotheque(v.nom, v.nom, v.caractere, genre={"F": "female", "M": "male"}.get(v.genre, ""))
        for v in VOIX_GOOGLE
    ]
