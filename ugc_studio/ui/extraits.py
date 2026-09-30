"""Écouter une voix (§5.4) : un extrait, gardé en cache pour n'être préparé qu'une fois.

- Voix créées (Voice Design) et voix de la bibliothèque étendue : l'extrait fourni par Google
  (demandé une fois, gratuit) ; s'il n'y en a pas, une phrase d'exemple est générée.
- 30 voix de base : une phrase d'exemple dans la langue du projet (ces voix parlent toutes les
  langues ; on veut les entendre en français). Coût minime, noté « essai de voix ».
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ..audio import en_wav
from ..chemins import dossier_cache
from ..fournisseurs.google_voix import phrase_extrait, voix_de_base
from ..fournisseurs.voix import RequeteVoix
from ..generation import noter_cout, preparer_texte
from ..services import Services
from . import taches
from .composants.lecteur import Lecteur
from .connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur


def _nom_de_fichier(texte: str) -> str:
    return re.sub(r"[^\w.-]", "_", texte)


def fichier_extrait_google(voix: str) -> Path:
    return dossier_cache() / "extraits" / f"google-{_nom_de_fichier(voix)}.wav"


def fichier_extrait_genere(voix: str, modele: str, langue: str) -> Path:
    return dossier_cache() / "extraits" / f"{_nom_de_fichier(modele)}-{_nom_de_fichier(voix)}-{langue}.wav"


def fichier_prononciation(voix: str, modele: str, texte: str) -> Path:
    empreinte = hashlib.sha1(texte.encode("utf-8")).hexdigest()[:12]
    return dossier_cache() / "prononciations" / f"{_nom_de_fichier(modele)}-{_nom_de_fichier(voix)}-{empreinte}.wav"


class EcouteVoix:
    """`afficher(message, rôle)` : où écrire l'avancement ou l'erreur ; `occupe(vrai/faux)` : pour
    désactiver les boutons pendant la préparation."""

    def __init__(
        self,
        services: Services,
        lecteur: Lecteur,
        afficher: Callable[[str, str], None],
        occupe: Callable[[bool], None] | None = None,
    ):
        self._services = services
        self._lecteur = lecteur
        self._afficher = afficher
        self._occupe = occupe or (lambda _occupe: None)

    def garder_et_jouer(self, voix: str, extrait_wav: bytes) -> None:
        """Extrait reçu de Google (ex. à la création d'une voix) : gardé en cache, puis joué."""
        fichier = fichier_extrait_google(voix)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_bytes(extrait_wav)
        self._lecteur.basculer(fichier)

    def _projet(self) -> str | None:
        projet = self._services.projets.projet
        return projet.nom if projet is not None else None

    def ecouter(self, voix: str, modele: str, langue: str) -> None:
        """▶ d'une voix : extrait de Google s'il existe, sinon phrase d'exemple (en cache)."""
        for fichier in (fichier_extrait_google(voix), fichier_extrait_genere(voix, modele, langue)):
            if fichier.exists():
                self._lecteur.basculer(fichier)
                return
        if voix_de_base(voix) is not None:
            self._phrase_exemple(voix, modele, langue)
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        self._occupe(True)
        self._afficher(f"Préparation de l'extrait de {self._services.voix.nom(voix)}…", "secondaire")

        def fin(detail) -> None:
            self._occupe(False)
            if detail.extrait_wav:
                self._afficher("", "secondaire")
                self.garder_et_jouer(voix, detail.extrait_wav)
            else:
                self._phrase_exemple(voix, modele, langue)

        def echec(_erreur: Exception) -> None:
            self._occupe(False)
            self._phrase_exemple(voix, modele, langue)  # pas d'extrait chez Google : on en génère un

        taches.lancer(lambda: adaptateur.obtenir_voix(voix), fin, echec)

    def _phrase_exemple(self, voix: str, modele: str, langue: str) -> None:
        self.dire(
            phrase_extrait(langue),
            voix,
            modele,
            "essai de voix",
            fichier_extrait_genere(voix, modele, langue),
            f"Préparation de l'extrait de {self._services.voix.nom(voix)}…",
        )

    def dire(self, texte: str, voix: str, modele: str, operation: str, fichier: Path, message: str) -> None:
        """Fait dire une courte phrase par une voix (une seule fois : l'audio est gardé en cache)."""
        if fichier.exists():
            self._lecteur.basculer(fichier)
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        commande = replace(preparer_texte(FOURNISSEUR, modele, voix, texte, operation), projet=self._projet())
        self._occupe(True)
        self._afficher(message, "secondaire")

        def fin(resultat) -> None:
            self._occupe(False)
            self._afficher("", "secondaire")
            noter_cout(self._services, commande, resultat)
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_bytes(en_wav(resultat.audio_wav))
            self._lecteur.basculer(fichier)

        def echec(erreur: Exception) -> None:
            self._occupe(False)
            self._afficher(message_erreur(erreur), "erreur")

        requete = RequeteVoix(commande.modele, commande.voix, commande.repliques)
        taches.lancer(lambda: adaptateur.generer_voix(requete), fin, echec)
