"""Page Réglages (§4) : quatre onglets.

V3.1 : la page défile comme les autres, d'une seule barre au bord de la fenêtre. Jusqu'à la 3.0.0, le
titre et les onglets restaient fixes et chaque onglet défilait dans sa propre zone, dont la barre
était collée aux blocs, loin du bord. Les onglets prennent la hauteur de l'onglet affiché, et le
tableau du suivi des coûts remplit la hauteur de la fenêtre (la page défile s'il n'a plus la place)."""

from __future__ import annotations

from ....services import Services
from ...composants.onglets import Onglets
from ..base import Page
from .onglet_connexions import OngletConnexions
from .onglet_couts import OngletCouts
from .onglet_donnees import OngletDonnees
from .onglet_modeles import OngletModeles


class PageReglages(Page):
    def __init__(self, services: Services):
        super().__init__(
            "Réglages",
            "Connexions API, modèles et prix, suivi des coûts, journal et données.",
            conseils="reglages",
            remplir_la_hauteur=True,
        )
        # Pas de ligne au-dessus des onglets : ils sont en haut de la page, juste sous le bandeau.
        self.onglets = Onglets(hauteur_selon_l_onglet=True, separateur=False)
        self.connexions = OngletConnexions(services)
        self.modeles = OngletModeles(services)
        self.couts = OngletCouts(services)
        self.donnees = OngletDonnees()
        self.onglets.addTab(self.connexions, "Connexions API")
        self.onglets.addTab(self.modeles, "Modèles et prix")
        self.onglets.addTab(self.couts, "Suivi des coûts")
        self.onglets.addTab(self.donnees, "Journal et données")
        # « Choisir les modèles » sans clé testée : on va tester une clé.
        self.modeles.connexions_demandees.connect(lambda: self.onglets.setCurrentIndex(0))
        self.onglets.currentChanged.connect(lambda _index: self.defilement.verticalScrollBar().setValue(0))
        self.contenu.addWidget(self.onglets, 1)
