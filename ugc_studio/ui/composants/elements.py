"""Petites fonctions pour créer les éléments de base de l'interface avec le bon style.

Le style lui-même est dans theme.py : ici, on se contente d'indiquer le « rôle » de chaque
élément (titre de page, légende, bouton principal…), et la feuille de style fait le reste.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..theme import Dimensions, Espacements
from .bouton import Bouton


def libelle(
    texte: str,
    role: str | None = None,
    selectionnable: bool = False,
    retour_a_la_ligne: bool = True,
) -> QLabel:
    """Texte. Rôles : « titre-page », « titre-bloc », « secondaire », « legende », « discret »,
    « succes », « avertissement », « erreur ».

    `retour_a_la_ligne=False` pour les textes courts placés sur une ligne avec d'autres éléments
    (titres de bloc à côté d'une pastille…) : ils gardent alors leur largeur naturelle."""
    etiquette = QLabel(texte)
    # Texte brut : sans cela, Qt prendrait « <laugh> » pour une balise HTML et l'effacerait.
    etiquette.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        etiquette.setProperty("role", role)
    etiquette.setWordWrap(retour_a_la_ligne)
    if selectionnable:
        etiquette.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return etiquette


def minutes_secondes(secondes: float) -> str:
    """Durée lisible : 75,4 s → « 1:15 »."""
    secondes = max(0, round(secondes))
    return f"{secondes // 60}:{secondes % 60:02d}"


def pastille(texte: str) -> QLabel:
    """Petite étiquette arrondie (ex. « Étape 2 »)."""
    etiquette = QLabel(texte)
    etiquette.setTextFormat(Qt.TextFormat.PlainText)
    etiquette.setProperty("role", "pastille")
    etiquette.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return etiquette


def bouton(
    texte: str,
    variante: str | None = None,
    nom_icone: str | None = None,
    action: Callable[[], None] | None = None,
) -> Bouton:
    """Bouton de l'app (voir composants/bouton.py). Variantes : None (normal), « principal »
    (contour mauve), « discret » (sans cadre), « icone » (petit bouton carré, icône seule)."""
    resultat = Bouton(texte, variante, nom_icone)
    if action is not None:
        resultat.clicked.connect(action)
    return resultat


def liste_deroulante(info: str | None = None) -> QComboBox:
    """Liste déroulante de l'app (toujours créée ici, jamais avec QComboBox() directement).

    Elle prend la largeur de son plus long choix quand il y a de la place, et peut rétrécir sinon
    (texte abrégé par « … » ; le menu ouvert montre toujours les textes en entier). Sans cela, un
    choix très long (ex. le nom d'une voix créée) élargirait toute la page au-delà de la fenêtre,
    et le bord droit serait coupé. `info` : texte de l'infobulle."""
    liste = QComboBox()
    liste.setMinimumContentsLength(Dimensions.LISTE_CARACTERES_MIN)
    if info:
        liste.setToolTip(info)
    return liste


def case_a_cocher(texte: str, explication: str | None = None) -> tuple[QWidget, QCheckBox]:
    """Case à cocher au texte court, avec son explication en légende dessous (alignée sur le
    texte de la case). Renvoie la zone à placer dans la page et la case elle-même ; pour griser
    la case, griser la zone (la légende l'est alors aussi).

    Pourquoi ? Le texte d'une case à cocher ne passe jamais à la ligne : une longue phrase
    imposerait sa largeur à toute la page, qui déborderait à droite dans une fenêtre étroite.
    L'explication, elle, passe à la ligne. (Un test vérifie que le texte des cases reste court.)"""
    zone = QWidget()
    disposition = QVBoxLayout(zone)
    disposition.setContentsMargins(0, 0, 0, 0)
    disposition.setSpacing(Espacements.XS)
    case = QCheckBox(texte)
    disposition.addWidget(case)
    if explication:
        legende = libelle(explication, "legende")
        # Retrait = case + espace avant son texte (voir QCheckBox dans la feuille de style).
        legende.setContentsMargins(Dimensions.CASE_A_COCHER + Espacements.S, 0, 0, 0)
        disposition.addWidget(legende)
    return zone, case


def bloc(titre: str | None = None, marges: int = Espacements.XL) -> tuple[QFrame, QVBoxLayout]:
    """Bloc (panneau arrondi sur fond « surface »). Renvoie le bloc et sa disposition verticale."""
    cadre = QFrame()
    cadre.setProperty("role", "bloc")
    disposition = QVBoxLayout(cadre)
    disposition.setContentsMargins(marges, marges, marges, marges)
    disposition.setSpacing(Espacements.M)
    if titre:
        disposition.addWidget(libelle(titre, "titre-bloc"))
    return cadre, disposition


def separateur() -> QFrame:
    """Fine ligne horizontale."""
    ligne = QFrame()
    ligne.setProperty("role", "separateur")
    return ligne


def vider_disposition(disposition) -> None:
    """Retire et détruit tout le contenu d'une disposition (y compris les dispositions imbriquées)."""
    while disposition.count():
        element = disposition.takeAt(0)
        if element.widget() is not None:
            element.widget().deleteLater()
        elif element.layout() is not None:
            vider_disposition(element.layout())
            element.layout().deleteLater()


def conteneur_vertical(espacement: int = Espacements.M) -> tuple[QWidget, QVBoxLayout]:
    """Zone transparente qui empile ses éléments verticalement."""
    zone = QWidget()
    disposition = QVBoxLayout(zone)
    disposition.setContentsMargins(0, 0, 0, 0)
    disposition.setSpacing(espacement)
    return zone, disposition
