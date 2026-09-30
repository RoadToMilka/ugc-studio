"""Connexions API (§4.1, §10) : les clés des fournisseurs.

Deux endroits, pour deux types d'informations :
- la clé elle-même (secrète) va dans le **coffre-fort de Windows** (Gestionnaire
  d'identification), chiffré par Windows avec le compte de l'utilisateur ;
- les informations non secrètes (nom, fournisseur, aperçu « AIza…4f2c », clé par défaut,
  résultat du dernier test) vont dans connexions.json.
Ainsi, aucun fichier de l'app ne contient jamais une clé.
"""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from . import NOM_APP
from .journal import declarer_secret
from .stockage import ecrire_json, lire_json

journal = logging.getLogger(__name__)


class ErreurConnexion(Exception):
    """Problème de gestion des clés, avec un message clair pour l'utilisateur."""


# ---------------------------------------------------------------------------------------------
# Coffre-fort
# ---------------------------------------------------------------------------------------------


class Coffre(Protocol):
    def lire(self, compte: str) -> str | None: ...

    def ecrire(self, compte: str, secret: str) -> None: ...

    def supprimer(self, compte: str) -> None: ...


class CoffreWindows:
    """Coffre-fort de Windows, via la bibliothèque `keyring`.

    Les clés sont visibles (et supprimables) dans Windows : Panneau de configuration →
    Gestionnaire d'identification → Informations d'identification Windows → « UGC Studio ».
    """

    SERVICE = NOM_APP

    def __init__(self):
        import keyring

        if sys.platform == "win32":
            # On choisit explicitement le coffre de Windows (plus fiable dans le .exe que la
            # détection automatique de keyring).
            from keyring.backends.Windows import WinVaultKeyring

            keyring.set_keyring(WinVaultKeyring())
        self._keyring = keyring

    def lire(self, compte: str) -> str | None:
        return self._keyring.get_password(self.SERVICE, compte)

    def ecrire(self, compte: str, secret: str) -> None:
        self._keyring.set_password(self.SERVICE, compte, secret)

    def supprimer(self, compte: str) -> None:
        import keyring.errors

        try:
            self._keyring.delete_password(self.SERVICE, compte)
        except keyring.errors.PasswordDeleteError:
            pass  # déjà absente


class CoffreMemoire:
    """Coffre en mémoire, pour les tests automatiques et l'autotest (rien n'est enregistré)."""

    def __init__(self):
        self.secrets: dict[str, str] = {}

    def lire(self, compte: str) -> str | None:
        return self.secrets.get(compte)

    def ecrire(self, compte: str, secret: str) -> None:
        self.secrets[compte] = secret

    def supprimer(self, compte: str) -> None:
        self.secrets.pop(compte, None)


# ---------------------------------------------------------------------------------------------
# Connexions
# ---------------------------------------------------------------------------------------------


def apercu_cle(cle: str) -> str:
    """Aperçu non secret d'une clé : « AIza…4f2c » (§4.1)."""
    cle = cle.strip()
    if len(cle) < 12:
        return "••••"
    return f"{cle[:4]}…{cle[-4:]}"


def nettoyer_cle(cle: str) -> str:
    """Retire les espaces et retours à la ligne ajoutés par un copier-coller."""
    return "".join(cle.split())


# Début du message d'un test réussi, tel que la v1.0.0 l'enregistrait (avec un tiret long).
_ANCIEN_MESSAGE_CLE_VALIDE = "Clé valide — "


@dataclass
class ResultatDernierTest:
    date: str
    ok: bool
    message: str


@dataclass
class Connexion:
    identifiant: str
    fournisseur: str
    nom: str
    apercu: str
    par_defaut: bool = False
    ajoutee_le: str = ""
    dernier_test: ResultatDernierTest | None = None
    modeles: list[str] = field(default_factory=list)  # modèles accessibles lors du dernier test réussi

    @property
    def compte_coffre(self) -> str:
        return f"{self.fournisseur}/{self.identifiant}"


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class GestionnaireConnexions:
    VERSION_FORMAT = 1

    def __init__(self, chemin: Path, coffre: Coffre):
        self._chemin = chemin
        self._coffre = coffre
        self._abonnes: list[Callable[[], None]] = []
        self._connexions: list[Connexion] = self._charger()

    # --- Lecture ---------------------------------------------------------------------------

    def lister(self, fournisseur: str | None = None) -> list[Connexion]:
        return [c for c in self._connexions if fournisseur is None or c.fournisseur == fournisseur]

    def connexion(self, identifiant: str) -> Connexion:
        for connexion in self._connexions:
            if connexion.identifiant == identifiant:
                return connexion
        raise ErreurConnexion("Cette connexion n'existe plus.")

    def connexion_par_defaut(self, fournisseur: str) -> Connexion | None:
        candidates = self.lister(fournisseur)
        return next((c for c in candidates if c.par_defaut), candidates[0] if candidates else None)

    def lire_cle(self, identifiant: str) -> str:
        connexion = self.connexion(identifiant)
        cle = self._coffre.lire(connexion.compte_coffre)
        if not cle:
            raise ErreurConnexion(
                f"La clé « {connexion.nom} » est introuvable dans le coffre-fort de Windows. "
                "Remplace-la (menu … → Remplacer la clé)."
            )
        declarer_secret(cle)
        return cle

    def modeles_disponibles(self, fournisseur: str | None = None) -> set[str]:
        """Modèles accessibles avec au moins une clé testée avec succès."""
        modeles: set[str] = set()
        for connexion in self.lister(fournisseur):
            if connexion.dernier_test and connexion.dernier_test.ok:
                modeles.update(connexion.modeles)
        return modeles

    # --- Modifications -----------------------------------------------------------------------

    def ajouter(self, fournisseur: str, nom: str, cle: str) -> Connexion:
        cle = nettoyer_cle(cle)
        if not cle:
            raise ErreurConnexion("La clé est vide.")
        nom = self._nom_unique(nom.strip() or "Ma clé")
        connexion = Connexion(
            identifiant=uuid.uuid4().hex[:12],
            fournisseur=fournisseur,
            nom=nom,
            apercu=apercu_cle(cle),
            par_defaut=not self.lister(fournisseur),  # la première clé d'un fournisseur est celle par défaut
            ajoutee_le=_maintenant(),
        )
        declarer_secret(cle)
        self._coffre.ecrire(connexion.compte_coffre, cle)
        self._connexions.append(connexion)
        self._enregistrer()
        journal.info("Clé ajoutée : %s (%s, %s)", connexion.nom, fournisseur, connexion.apercu)
        return connexion

    def remplacer_cle(self, identifiant: str, cle: str) -> None:
        cle = nettoyer_cle(cle)
        if not cle:
            raise ErreurConnexion("La clé est vide.")
        connexion = self.connexion(identifiant)
        declarer_secret(cle)
        self._coffre.ecrire(connexion.compte_coffre, cle)
        connexion.apercu = apercu_cle(cle)
        connexion.dernier_test = None
        connexion.modeles = []
        self._enregistrer()
        journal.info("Clé remplacée : %s (%s)", connexion.nom, connexion.apercu)

    def renommer(self, identifiant: str, nom: str) -> None:
        nom = nom.strip()
        if not nom:
            raise ErreurConnexion("Le nom ne peut pas être vide.")
        connexion = self.connexion(identifiant)
        if nom != connexion.nom:
            connexion.nom = self._nom_unique(nom)
            self._enregistrer()

    def definir_par_defaut(self, identifiant: str) -> None:
        choisie = self.connexion(identifiant)
        for connexion in self.lister(choisie.fournisseur):
            connexion.par_defaut = connexion is choisie
        self._enregistrer()

    def supprimer(self, identifiant: str) -> None:
        connexion = self.connexion(identifiant)
        self._coffre.supprimer(connexion.compte_coffre)
        self._connexions.remove(connexion)
        restantes = self.lister(connexion.fournisseur)
        if connexion.par_defaut and restantes:
            restantes[0].par_defaut = True
        self._enregistrer()
        journal.info("Clé supprimée : %s (%s)", connexion.nom, connexion.fournisseur)

    def enregistrer_test(self, identifiant: str, ok: bool, message: str, modeles: list[str] | None = None) -> None:
        connexion = self.connexion(identifiant)
        connexion.dernier_test = ResultatDernierTest(_maintenant(), ok, message)
        if ok:
            connexion.modeles = sorted(modeles or [])
        self._enregistrer()

    # --- Notifications (l'interface se met à jour quand les connexions changent) -------------

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    def _notifier(self) -> None:
        for fonction in list(self._abonnes):
            fonction()

    # --- Fichier -----------------------------------------------------------------------------

    def _nom_unique(self, nom: str) -> str:
        existants = {c.nom for c in self._connexions}
        if nom not in existants:
            return nom
        numero = 2
        while f"{nom} ({numero})" in existants:
            numero += 1
        return f"{nom} ({numero})"

    def _charger(self) -> list[Connexion]:
        donnees = lire_json(self._chemin, {})
        connexions = []
        for brut in donnees.get("connexions", []) if isinstance(donnees, dict) else []:
            try:
                test = brut.get("dernier_test")
                if test and isinstance(test.get("message"), str):
                    # Message enregistré par la v1.0.0 : « Clé valide — 42 modèles accessibles. »
                    test = {**test, "message": test["message"].replace(_ANCIEN_MESSAGE_CLE_VALIDE, "Clé valide, ", 1)}
                connexions.append(
                    Connexion(
                        identifiant=brut["identifiant"],
                        fournisseur=brut["fournisseur"],
                        nom=brut["nom"],
                        apercu=brut.get("apercu", "••••"),
                        par_defaut=bool(brut.get("par_defaut", False)),
                        ajoutee_le=brut.get("ajoutee_le", ""),
                        dernier_test=ResultatDernierTest(**test) if test else None,
                        modeles=list(brut.get("modeles", [])),
                    )
                )
            except (KeyError, TypeError) as erreur:
                journal.warning("Connexion illisible ignorée (%s)", erreur)
        return connexions

    def _enregistrer(self) -> None:
        ecrire_json(
            self._chemin,
            {"version_format": self.VERSION_FORMAT, "connexions": [asdict(c) for c in self._connexions]},
        )
        self._notifier()
