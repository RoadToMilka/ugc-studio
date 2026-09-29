"""Les « services » de l'app : les objets partagés par toutes les pages.

Ils sont créés une seule fois au démarrage, puis transmis à la fenêtre et aux pages.
"""

from __future__ import annotations

from dataclasses import dataclass

from .chemins import dossier_donnees, fichier_preferences
from .connexions import Coffre, CoffreWindows, GestionnaireConnexions
from .couts import JournalCouts
from .preferences import Preferences
from .prix import CataloguePrix
from .projets import GestionnaireProjets
from .prononciation import DictionnaireGlobal
from .styles import BibliothequeStyles


@dataclass
class Services:
    preferences: Preferences
    connexions: GestionnaireConnexions
    prix: CataloguePrix
    couts: JournalCouts
    projets: GestionnaireProjets
    styles: BibliothequeStyles  # bibliothèque de styles personnalisés (§5.5)
    prononciations: DictionnaireGlobal  # dictionnaire de prononciation commun à tous les projets (§5.2)


def creer_services(coffre: Coffre | None = None) -> Services:
    """`coffre` : coffre-fort des clés (par défaut celui de Windows)."""
    dossier = dossier_donnees()
    prix = CataloguePrix(dossier / "prix.json")
    return Services(
        preferences=Preferences(fichier_preferences()),
        connexions=GestionnaireConnexions(dossier / "connexions.json", coffre or CoffreWindows()),
        prix=prix,
        couts=JournalCouts(dossier / "couts", prix),
        projets=GestionnaireProjets(dossier / "projets_recents.json"),
        styles=BibliothequeStyles(dossier / "styles.json"),
        prononciations=DictionnaireGlobal(dossier / "prononciations.json"),
    )
