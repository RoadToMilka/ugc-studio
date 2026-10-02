"""Fenêtres de l'app (V3.2, lot 3, §9.6) : une fenêtre se présente comme une page.

Le fond de la fenêtre est celui de l'app ; son contenu est dans un bloc (fond et contour des blocs,
coins arrondis), 16 px autour, comme les blocs d'une page ; les boutons du bas (« Annuler »,
« Créer le projet »…) sont sous le bloc, sur le fond de l'app. Jusqu'à la 3.1.2, tout était posé sur
le fond gris des menus, sans bloc.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFrame, QVBoxLayout

from ..theme import Dimensions, Espacements, Hauteurs
from .elements import bloc, marge_haute_titre


def fenetre_en_bloc(dialogue: QDialog, titre_avec_boutons: bool = False) -> tuple[QVBoxLayout, QFrame, QVBoxLayout]:
    """Met en place une fenêtre comme une page (voir en haut du fichier). Renvoie la disposition de la
    fenêtre (pour les boutons du bas, sous le bloc), le bloc et sa disposition (pour le contenu, qui
    commence par le titre de la fenêtre). `titre_avec_boutons` : le titre partage sa ligne avec un
    bouton (« Conseils ») ; il reste à 24 px du haut du bloc (voir marge_haute_titre)."""
    fenetre = QVBoxLayout(dialogue)
    marge = Dimensions.ESPACE_BLOCS
    fenetre.setContentsMargins(marge, marge, marge, marge)
    fenetre.setSpacing(marge)
    cadre, disposition = bloc()
    haut = marge_haute_titre(hauteur_ligne=Hauteurs.CONTROLE if titre_avec_boutons else 0)
    disposition.setContentsMargins(Espacements.XL, haut, Espacements.XL, Espacements.XL)
    fenetre.addWidget(cadre, 1)
    return fenetre, cadre, disposition
