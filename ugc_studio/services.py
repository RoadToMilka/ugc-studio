"""Les « services » de l'app : les objets partagés par toutes les pages.

Ils sont créés une seule fois au démarrage, puis transmis à la fenêtre et aux pages.
"""

from __future__ import annotations

from dataclasses import dataclass

from .chemins import dossier_donnees, fichier_preferences
from .connexions import Coffre, CoffreWindows, GestionnaireConnexions
from .couts import JournalCouts
from .ecriture.briefs import BibliothequeBriefs
from .ecriture.exemples import BibliothequeExemples
from .modeles_charges import ModelesCharges
from .preferences import Preferences
from .prix import CataloguePrix
from .projets import GestionnaireProjets
from .prononciation import DictionnaireGlobal
from .styles import BibliothequeStyles
from .transcription import DictionnaireRemplacements
from .vitesses import VitessesDeParole
from .voix_locales import GestionnaireVoix


@dataclass
class Services:
    preferences: Preferences
    connexions: GestionnaireConnexions
    prix: CataloguePrix
    couts: JournalCouts
    projets: GestionnaireProjets
    styles: BibliothequeStyles  # bibliothèque de styles personnalisés (§5.5)
    prononciations: DictionnaireGlobal  # dictionnaire de prononciation commun à tous les projets (§5.2)
    voix: GestionnaireVoix  # favoris, voix créées, bibliothèque de Google gardée en mémoire (§5.4)
    remplacements: DictionnaireRemplacements  # remplacements après transcription, tous projets (§6.3)
    modeles: ModelesCharges  # modèles chargés dans l'app, et où ils servent (§4.2 bis)
    exemples: BibliothequeExemples  # « Mes meilleurs scripts » : exemples donnés au modèle (V2, §10.9)
    briefs: BibliothequeBriefs  # briefs réutilisables d'un projet à l'autre (V2, §10.5)
    vitesses: VitessesDeParole  # vitesse de parole de chaque voix, mesurée sur les prises (V2, §10.7)


def creer_services(coffre: Coffre | None = None) -> Services:
    """`coffre` : coffre-fort des clés (par défaut celui de Windows)."""
    dossier = dossier_donnees()
    prix = CataloguePrix(dossier / "prix.json")
    styles = BibliothequeStyles(dossier / "styles.json")
    voix = GestionnaireVoix(dossier / "voix.json")
    projets = GestionnaireProjets(dossier / "projets_recents.json")
    vitesses = VitessesDeParole(dossier / "vitesses.json")
    # Un projet qui s'ouvre : ses prises pas encore mesurées (ex. créées avec la 1.2.0) affinent la
    # vitesse de leur voix. Abonné en premier : les modules affichent ensuite la vitesse à jour.
    projets.abonner(lambda projet: vitesses.noter_prises(projet.prises) if projet is not None else None)
    return Services(
        preferences=Preferences(fichier_preferences()),
        connexions=GestionnaireConnexions(dossier / "connexions.json", coffre or CoffreWindows()),
        prix=prix,
        couts=JournalCouts(dossier / "couts", prix),
        projets=projets,
        styles=styles,
        prononciations=DictionnaireGlobal(dossier / "prononciations.json"),
        voix=voix,
        remplacements=DictionnaireRemplacements(dossier / "remplacements.json"),
        modeles=ModelesCharges(dossier / "modeles.json", voix, styles),
        exemples=BibliothequeExemples(dossier / "scripts_exemples.json"),
        briefs=BibliothequeBriefs(dossier / "briefs.json"),
        vitesses=vitesses,
    )
