"""Zones de l'app (V3.3, lot 1 ; cahier des charges §9.6) : les blocs des pages et des fenêtres, les
cartes, les colonnes qui défilent. Règle : quand une zone est plus haute que son contenu, la place en
trop va en bas de la zone, jamais au-dessus de son titre ni entre deux éléments. Seul un élément fait
pour remplir la zone (une liste, une colonne qui défile, un éditeur de texte) prend la place qui reste.

Quand une zone est-elle plus haute que son contenu ? Quand elle est étirée : à côté d'une zone plus
haute (deux blocs côte à côte ont la même hauteur), dans une fenêtre agrandie, dans une colonne qui
défile plus haute que ce qu'elle montre. Sans indication, Qt (la bibliothèque qui dessine
l'interface) répartit alors lui-même la place en trop : il agrandit les éléments qui peuvent grandir
(un titre plus haut, son texte centré dedans) ou ajoute des espaces au-dessus et entre les éléments.
Jusqu'à la 3.2.2, en fenêtre moyenne, le bloc Apparence, étiré à la hauteur de l'Aperçu, avait ainsi
un grand vide au-dessus et sous son titre.

- DispositionDeZone : la disposition verticale de toute zone (bloc(), cartes, colonnes qui défilent).
  Elle range son contenu en haut, à sa hauteur, et laisse la place en trop en bas.
- zones(), ecarts_de_place() et ecarts_dans() : vérifient la règle sur chaque zone d'une page ou
  d'une fenêtre (tests et autotest du .exe).
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QBoxLayout, QFrame, QLabel, QLayout, QLayoutItem, QVBoxLayout, QWidget

# De combien la vérification étire une zone (en pixels) : assez pour voir où la place en trop va.
ETIREMENT_VERIFIE = 300


def remplit(element: QLayoutItem, etirement: int = 0) -> bool:
    """Un élément fait pour prendre la place qui reste : il grandit en hauteur de lui-même (une liste,
    une colonne qui défile, un éditeur de texte), ou il a été ajouté avec un facteur d'étirement
    (`etirement`, ex. addWidget(liste, 1) ou addStretch(1)). Un élément caché ne compte pas."""
    if element.spacerItem() is None and element.isEmpty():
        return False
    return bool(element.expandingDirections() & Qt.Orientation.Vertical) or etirement > 0


def hauteur_du_contenu(disposition: QLayout, largeur: int) -> int:
    """Hauteur dont le contenu d'une disposition a besoin à cette largeur, marges comprises (les
    textes qui passent à la ligne comptent)."""
    hauteur = disposition.heightForWidth(largeur) if disposition.hasHeightForWidth() else -1
    if hauteur < 0:
        hauteur = disposition.sizeHint().height()
    return max(hauteur, disposition.minimumSize().height())


class DispositionDeZone(QVBoxLayout):
    """Disposition verticale d'une zone (voir en haut du fichier) : quand la zone est plus haute que
    son contenu, le contenu reste en haut, chaque élément à sa hauteur, et la place en trop va en bas.
    Si un élément est fait pour remplir la zone (voir remplit), c'est lui qui la prend, comme avant."""

    def setGeometry(self, zone: QRect) -> None:  # noqa: N802 — nom imposé par Qt
        if not self.a_un_element_qui_remplit():
            hauteur = hauteur_du_contenu(self, zone.width())
            if hauteur < zone.height():
                # La disposition ne reçoit que la hauteur de son contenu, en haut de la zone : le reste,
                # en dessous, reste vide.
                zone = QRect(zone.x(), zone.y(), zone.width(), hauteur)
        super().setGeometry(zone)

    def a_un_element_qui_remplit(self) -> bool:
        return any(remplit(self.itemAt(rang), self.stretch(rang)) for rang in range(self.count()))


# --- Vérification (tests et autotest) -------------------------------------------------------------


def zones(racine: QWidget) -> list[QWidget]:
    """Les zones visibles d'une page ou d'une fenêtre : ses blocs et cartes (rôle « bloc »), et le
    contenu de ses colonnes qui défilent."""
    from .defilement import ColonneDefilante  # (defilement.py se sert de ce module)

    trouvees = [racine] if racine.property("role") == "bloc" else []
    trouvees += [cadre for cadre in racine.findChildren(QFrame) if cadre.property("role") == "bloc"]
    trouvees += [colonne.widget() for colonne in racine.findChildren(ColonneDefilante) if colonne.widget() is not None]
    return [zone for zone in trouvees if zone.isVisible() and isinstance(zone.layout(), QBoxLayout)]


def _texte(widget: QWidget) -> str:
    texte = getattr(widget, "text", None)
    if callable(texte):
        try:
            valeur = texte()
        except TypeError:
            return ""
        return valeur if isinstance(valeur, str) else ""
    return ""


def _premier_widget(disposition: QLayout) -> QWidget | None:
    for rang in range(disposition.count()):
        element = disposition.itemAt(rang)
        if element.widget() is not None:
            return element.widget()
        if element.layout() is not None:
            trouve = _premier_widget(element.layout())
            if trouve is not None:
                return trouve
    return None


def _nom(element: QLayoutItem) -> str:
    """« « Apparence » », « la rangée de « Préréglage » », « ColonneDefilante » : pour savoir quel
    élément corriger."""
    widget = element.widget()
    rangee = widget is None and element.layout() is not None
    if rangee:
        widget = _premier_widget(element.layout())
    if widget is None:
        return "un élément"
    texte = _texte(widget).strip().replace("\n", " ")
    nom = f"« {texte[:40]} »" if texte else type(widget).__name__
    return f"la rangée de {nom}" if rangee else nom


def description_de_zone(zone: QWidget) -> str:
    """La zone, par son titre (ou son premier texte) : « « Apparence » »."""
    titre = getattr(zone, "titre", None)
    texte = _texte(titre) if isinstance(titre, QWidget) else ""
    if not texte:
        texte = next((_texte(e) for e in zone.findChildren(QLabel) if e.isVisibleTo(zone) and _texte(e)), "")
    texte = texte.strip().replace("\n", " ")
    return f"« {texte[:40]} »" if texte else type(zone).__name__


def ecarts_de_place(zone: QWidget) -> list[str]:
    """Étire la disposition de la zone de ETIREMENT_VERIFIE px de plus que son contenu, et relève ce
    qui bouge : un élément qui descend (du vide au-dessus de lui) ou qui devient plus haut (son texte
    se décale vers le milieu). Seuls grandissent les éléments faits pour remplir (voir remplit) ; ceux
    qui les suivent descendent d'autant, pas plus. Renvoie les écarts (aucun : la règle est
    respectée) ; la zone est remise en place ensuite."""
    disposition = zone.layout()
    if not isinstance(disposition, QBoxLayout):
        return []
    cadre = zone.contentsRect()
    largeur = cadre.width()
    naturelle = hauteur_du_contenu(disposition, largeur)
    elements = [
        (rang, disposition.itemAt(rang))
        for rang in range(disposition.count())
        if disposition.itemAt(rang).spacerItem() is None and not disposition.itemAt(rang).isEmpty()
    ]

    def releve(hauteur: int) -> list[QRect]:
        disposition.setGeometry(QRect(cadre.x(), cadre.y(), largeur, hauteur))
        return [QRect(element.geometry()) for _rang, element in elements]

    try:
        avant = releve(naturelle)
        apres = releve(naturelle + ETIREMENT_VERIFIE)
    finally:
        disposition.setGeometry(cadre)  # la zone reprend sa place

    ecarts = []
    croissance = 0  # ce dont ont grandi, au-dessus, les éléments faits pour remplir
    for (rang, element), a, b in zip(elements, avant, apres):
        descente = b.top() - a.top() - croissance
        if descente:
            ecarts.append(f"{descente} px de vide au-dessus de {_nom(element)}")
        if remplit(element, disposition.stretch(rang)):
            croissance += b.height() - a.height()
        elif b.height() != a.height():
            ecarts.append(f"{_nom(element)} : {b.height() - a.height()} px plus haut (son texte descend)")
    return ecarts


def ecarts_dans(racine: QWidget) -> list[str]:
    """Les écarts à la règle de chaque zone visible d'une page ou d'une fenêtre (voir ecarts_de_place) :
    « zone « Apparence » : 150 px de vide au-dessus de « Apparence » »."""
    return [f"zone {description_de_zone(zone)} : {ecart}" for zone in zones(racine) for ecart in ecarts_de_place(zone)]
