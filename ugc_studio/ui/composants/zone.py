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
    """Hauteur où chaque élément d'une disposition a sa hauteur naturelle, à cette largeur (marges
    comprises ; les textes qui passent à la ligne comptent) : la hauteur que Qt lui donne pour cette
    largeur, ou sa hauteur souhaitée.

    Pas sa hauteur minimale : Qt calcule celle d'un champ qui dépend de sa largeur (un chemin qui
    passe à la ligne, sous son nom) sur sa hauteur souhaitée, qui peut dépasser sa hauteur réelle à
    cette largeur. La zone donnerait alors à son contenu un peu trop de place, qu'un titre prendrait :
    le test de la fenêtre « Nouveau projet » agrandie l'a montré (34 px de plus pour son titre)."""
    hauteur = disposition.heightForWidth(largeur) if disposition.hasHeightForWidth() else -1
    return hauteur if hauteur >= 0 else disposition.sizeHint().height()


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


def hauteur_naturelle(element: QLayoutItem, largeur: int) -> int:
    """Hauteur naturelle d'un élément à cette largeur : celle que Qt lui donne pour cette largeur (un
    texte qui passe à la ligne), ou sa hauteur souhaitée, entre ses hauteurs minimale et maximale."""
    hauteur = element.heightForWidth(largeur) if element.hasHeightForWidth() else element.sizeHint().height()
    return max(element.minimumSize().height(), min(hauteur, element.maximumSize().height()))


def ecarts_de_place(zone: QWidget) -> list[str]:
    """Étire la disposition de la zone de ETIREMENT_VERIFIE px de plus que son contenu, et relève ce
    qui ne respecte pas la règle :
    - du vide au-dessus d'un élément : le premier n'est plus à sa place, en haut, ou un élément n'est
      plus juste sous le précédent (avec l'écart que Qt met entre eux à la hauteur du contenu) ;
    - un élément plus haut que son contenu (son texte descend vers le milieu), sauf un élément fait
      pour remplir la zone (voir remplit), qui peut grandir : ceux qui le suivent descendent avec lui.
    Renvoie les écarts (aucun : la règle est respectée) ; la zone est remise en place ensuite."""
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

    def releve(hauteur: int, comme_qt: bool = False) -> list[QRect]:
        place = QRect(cadre.x(), cadre.y(), largeur, hauteur)
        if comme_qt:
            # La disposition de Qt elle-même (sans DispositionDeZone) : les écarts entre les éléments.
            QBoxLayout.setGeometry(disposition, place)
        else:
            disposition.setGeometry(place)
        return [QRect(element.geometry()) for _rang, element in elements]

    try:
        avant = releve(naturelle, comme_qt=True)
        apres = releve(naturelle + ETIREMENT_VERIFIE)
    finally:
        disposition.setGeometry(cadre)  # la zone reprend sa place

    ecarts = []
    for index, ((rang, element), a, b) in enumerate(zip(elements, avant, apres)):
        nom = _nom(element)
        if index == 0:
            attendu = a.top()
        else:
            attendu = apres[index - 1].bottom() + (a.top() - avant[index - 1].bottom())
        if b.top() != attendu:
            ecarts.append(f"{b.top() - attendu} px de vide au-dessus de {nom}")
        if not remplit(element, disposition.stretch(rang)):
            hauteur = hauteur_naturelle(element, b.width())
            if b.height() > hauteur:
                ecarts.append(f"{nom} : {b.height() - hauteur} px plus haut que son contenu (son texte descend)")
    return ecarts


def ecarts_dans(racine: QWidget) -> list[str]:
    """Les écarts à la règle de chaque zone visible d'une page ou d'une fenêtre (voir ecarts_de_place) :
    « zone « Apparence » : 150 px de vide au-dessus de « Apparence » »."""
    return [f"zone {description_de_zone(zone)} : {ecart}" for zone in zones(racine) for ecart in ecarts_de_place(zone)]
