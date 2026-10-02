"""Structure commune des pages : un en-tête (titre, sous-titre, « Conseils »), puis le contenu, qui
défile si besoin.

V3.1 : la fenêtre confie l'en-tête de chaque page au bandeau du haut (voir composants/entete.py) ;
la page ne garde que son contenu, avec le même espace partout autour des blocs (16 px)."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..composants.defilement import zone_defilante
from ..composants.entete import EnteteDePage
from ..theme import Dimensions


class Page(QWidget):
    """Page avec un en-tête (titre + sous-titre + « Conseils ») et une zone de contenu défilante.

    Les pages ajoutent leurs éléments dans `self.contenu` (une disposition verticale). L'en-tête
    reste accessible : `self.entete`, `self.titre`, `self.sous_titre`, `self.bouton_conseils` (ou
    None). Tant que la fenêtre ne l'a pas pris pour le bandeau (detacher_entete), il est en haut du
    contenu (ex. une page créée seule, dans un test).

    `remplir_la_hauteur` : le contenu prend toute la hauteur de la page (voir zone_defilante)."""

    def __init__(self, titre: str, sous_titre: str, conseils: str | None = None, remplir_la_hauteur: bool = False):
        super().__init__()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        marge = Dimensions.ESPACE_BLOCS
        zone, self.contenu = zone_defilante(
            marges=(marge, marge, marge, marge), remplir_la_hauteur=remplir_la_hauteur, barre_dans_la_marge=True
        )
        self.defilement = zone  # pour amener un élément à l'écran (ensureWidgetVisible)
        disposition.addWidget(zone)
        self.entete = EnteteDePage(titre, sous_titre, conseils)
        self.titre, self.sous_titre, self.bouton_conseils = self.entete.titre, self.entete.sous_titre, self.entete.conseils
        self.contenu.addWidget(self.entete)

    def detacher_entete(self) -> EnteteDePage:
        """L'en-tête quitte le haut du contenu (la fenêtre le met dans le bandeau)."""
        self.contenu.removeWidget(self.entete)
        return self.entete
