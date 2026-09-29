"""Système de design de UGC Studio (cahier des charges §9).

C'est le SEUL fichier où l'on écrit des couleurs, des tailles, des espacements ou des arrondis.
Le reste du code utilise ces noms (ex. `Couleurs.ACCENT`) : pour changer l'apparence de toute
l'app, on modifie une valeur ici, et c'est tout. Un test automatique vérifie qu'aucune valeur
n'est écrite en dur ailleurs.

Ce fichier contient aussi la « feuille de style » Qt (l'équivalent du CSS d'une page web),
construite à partir de ces valeurs.
"""

from __future__ import annotations

from string import Template

# ---------------------------------------------------------------------------------------------
# Valeurs du design
# ---------------------------------------------------------------------------------------------


class Couleurs:
    """§9.1 — Thème sombre."""

    FOND = "#0F0F14"  # fond de l'app
    SURFACE = "#17171F"  # blocs, panneaux
    SURFACE_ELEVEE = "#1F1F2A"  # menus, fenêtres
    BORDURE = "#2A2A38"  # bordure neutre
    ACCENT = "#8B5CF6"  # mauve : contours des éléments clés, focus, repères
    ACCENT_SURVOL = "#A78BFA"
    ACCENT_PRESSE = "#7C3AED"
    TEXTE = "#F4F4F8"
    TEXTE_SECONDAIRE = "#A1A1B5"
    TEXTE_DESACTIVE = "#5C5C70"
    SUCCES = "#22C55E"
    AVERTISSEMENT = "#F59E0B"  # orange
    ERREUR = "#EF4444"


class CouleursBalises:
    """§5.2 — Couleur des badges de balises, une par famille (voir ugc_studio/balises.py)."""

    PAUSES = "#94A3B8"  # gris ardoise
    RIRES = "#FACC15"  # jaune
    SOUFFLE = "#2DD4BF"  # turquoise
    REACTIONS = "#FB923C"  # orange
    VOIX = "#38BDF8"  # bleu ciel
    EMOTIONS = "#F472B6"  # rose

    @classmethod
    def de(cls, famille: str) -> str:
        return {
            "pauses": cls.PAUSES,
            "rires": cls.RIRES,
            "souffle": cls.SOUFFLE,
            "reactions": cls.REACTIONS,
            "voix": cls.VOIX,
            "emotions": cls.EMOTIONS,
        }.get(famille, Couleurs.TEXTE_SECONDAIRE)


class Opacites:
    """Transparences appliquées aux couleurs ci-dessus (0 = invisible, 1 = opaque)."""

    TEINTE_SELECTION = 0.12  # fond mauve léger d'un élément sélectionné
    TEINTE = 0.18  # fond mauve du bouton principal
    TEINTE_SURVOL = 0.26
    TEINTE_PRESSEE = 0.34
    FOND_BADGE = 0.16  # fond coloré des badges de balises
    CONTOUR_BADGE = 0.55
    FOND_BADGE_SURVOL = 0.30


class Espacements:
    """§9.2 — Uniquement ces valeurs (en pixels)."""

    XS = 4
    S = 8
    M = 12
    L = 16
    XL = 24
    XXL = 32


ESPACEMENTS_AUTORISES = (4, 8, 12, 16, 24, 32)


class Arrondis:
    """§9.3 — Rayons des coins (px)."""

    CONTROLE = 8  # boutons, champs, badges
    BLOC = 12  # blocs, panneaux, fenêtres
    PETIT = 4  # petits éléments : cases à cocher, poignées des barres de défilement
    # Badges de balises et pastilles : entièrement arrondis (rayon = moitié de la hauteur).


class Hauteurs:
    """§9.4 — Hauteurs (px)."""

    CONTROLE = 36  # boutons et champs
    PETIT_BOUTON = 28  # petits boutons (icônes)
    PASTILLE = 20  # pastilles d'information (ex. « Étape 2 »)


class Typo:
    """§9.5 — Police Inter (embarquée dans l'app). Tailles en pixels."""

    FAMILLE = "Inter"
    LEGENDE = 12
    COURANT = 14
    TITRE_BLOC = 16
    TITRE_PAGE = 20
    GRAND_CHIFFRE = 24
    GRAISSE_NORMALE = 400
    GRAISSE_MOYENNE = 500
    GRAISSE_FORTE = 600


# §4.4 — Montants : les 2e et 3e décimales sont affichées à ~70 % de la taille normale.
RATIO_PETITES_DECIMALES = 0.70


class Dimensions:
    """Autres tailles fixes de l'interface (px)."""

    BORDURE = 1  # épaisseur des bordures
    LARGEUR_BARRE_LATERALE = 224
    ICONE = 20  # icônes de la barre latérale et des boutons
    ICONE_PETITE = 16  # flèches des listes déroulantes, coches
    LOGO = 28
    CASE_A_COCHER = 18
    BARRE_DEFILEMENT = 16
    POIGNEE_DEFILEMENT_MIN = 32
    CONTENU_LARGEUR_MAX = 960  # largeur maximale des pages de type « formulaire »
    SOULIGNEMENT_ONGLET = 2  # trait mauve sous l'onglet sélectionné
    DIALOGUE_LARGEUR = 520
    CHAMP_NOMBRE_LARGEUR = 96  # champs de prix, de taux…
    ETIQUETTE_HAUTEUR = 20  # petites étiquettes grises (ex. capacités d'un modèle)
    TABLEAU_HAUTEUR_MIN = 320
    EDITEUR_HAUTEUR_MIN = 180  # éditeur de script
    # Badges de balises : même hauteur que les pastilles (Hauteurs.PASTILLE), entièrement arrondis.
    BADGE_MARGE_HORIZONTALE = 8  # espace intérieur, à gauche et à droite du nom de la balise
    BADGE_ECART = 4  # espace de part et d'autre d'un badge dans le texte
    GLISSIERE_HAUTEUR = 4  # barre de progression du lecteur
    GLISSIERE_POIGNEE = 12
    ETOILE = 16  # étoiles de notation des prises
    CHAMP_STYLE_LARGEUR_MIN = 320
    FENETRE_LARGEUR = 1360
    FENETRE_HAUTEUR = 860
    FENETRE_LARGEUR_MIN = 960
    FENETRE_HAUTEUR_MIN = 600
    FENETRE_PART_ECRAN_MAX = 0.92  # au premier lancement, la fenêtre occupe au plus 92 % de l'écran


# ---------------------------------------------------------------------------------------------
# Outils de conversion
# ---------------------------------------------------------------------------------------------


def composantes(couleur: str) -> tuple[int, int, int]:
    """'#8B5CF6' → (139, 92, 246)."""
    return int(couleur[1:3], 16), int(couleur[3:5], 16), int(couleur[5:7], 16)


def rgba(couleur: str, opacite: float) -> str:
    """Couleur avec transparence, au format des feuilles de style Qt : 'rgba(139, 92, 246, 46)'."""
    rouge, vert, bleu = composantes(couleur)
    return f"rgba({rouge}, {vert}, {bleu}, {round(opacite * 255)})"


def qcolor(couleur: str, opacite: float = 1.0):
    """Couleur Qt (QColor), avec une transparence éventuelle."""
    from PySide6.QtGui import QColor

    resultat = QColor(couleur)
    resultat.setAlphaF(opacite)
    return resultat


# ---------------------------------------------------------------------------------------------
# Palette Qt : couleurs utilisées par les éléments que la feuille de style ne décrit pas
# (fenêtres de dialogue, menus contextuels…)
# ---------------------------------------------------------------------------------------------


def palette():
    from PySide6.QtGui import QColor, QPalette

    role = QPalette.ColorRole
    p = QPalette()
    couleurs = {
        role.Window: Couleurs.SURFACE_ELEVEE,
        role.WindowText: Couleurs.TEXTE,
        role.Base: Couleurs.FOND,
        role.AlternateBase: Couleurs.SURFACE,
        role.Text: Couleurs.TEXTE,
        role.PlaceholderText: Couleurs.TEXTE_DESACTIVE,
        role.Button: Couleurs.SURFACE_ELEVEE,
        role.ButtonText: Couleurs.TEXTE,
        role.BrightText: Couleurs.TEXTE,
        role.Highlight: Couleurs.ACCENT,
        role.HighlightedText: Couleurs.TEXTE,
        role.ToolTipBase: Couleurs.SURFACE_ELEVEE,
        role.ToolTipText: Couleurs.TEXTE,
        role.Link: Couleurs.ACCENT_SURVOL,
        role.LinkVisited: Couleurs.ACCENT,
        role.Light: Couleurs.BORDURE,
        role.Midlight: Couleurs.BORDURE,
        role.Mid: Couleurs.BORDURE,
        role.Dark: Couleurs.FOND,
        role.Shadow: Couleurs.FOND,
    }
    if hasattr(role, "Accent"):  # rôle ajouté dans Qt 6.6
        couleurs[role.Accent] = Couleurs.ACCENT
    for cle, valeur in couleurs.items():
        p.setColor(cle, QColor(valeur))

    desactive = QPalette.ColorGroup.Disabled
    for cle in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(desactive, cle, QColor(Couleurs.TEXTE_DESACTIVE))
    p.setColor(desactive, role.Highlight, QColor(Couleurs.BORDURE))
    return p


# ---------------------------------------------------------------------------------------------
# Feuille de style Qt (QSS)
# Les « $nom » sont remplacés par les valeurs ci-dessus. Les éléments sont repérés par leur
# type (QPushButton…), leur nom d'objet (#racine…) ou une propriété (role="titre-page"…).
# ---------------------------------------------------------------------------------------------

_MODELE_FEUILLE_DE_STYLE = Template(
    """
/* ---------- Base ---------- */
QWidget {
    color: $texte;
    font-family: "$famille";
    font-size: ${courant}px;
}
QMainWindow, QFrame#racine {
    background: $fond;
}
QDialog, QMessageBox {
    background: $surface_elevee;
}
QFrame#barreLaterale {
    background: $surface;
    border: none;
    border-right: ${bordure}px solid $couleur_bordure;
}
QFrame#entete {
    background: $fond;
    border: none;
    border-bottom: ${bordure}px solid $couleur_bordure;
}

/* ---------- Textes ---------- */
QLabel {
    background: transparent;
}
QLabel[role="titre-page"] {
    font-size: ${titre_page}px;
    font-family: "$famille_forte";
    font-weight: $graisse_forte;
}
QLabel[role="titre-bloc"], QLabel[role="nom-app"] {
    font-size: ${titre_bloc}px;
    font-family: "$famille_forte";
    font-weight: $graisse_forte;
}
QLabel[role="secondaire"] {
    color: $texte_secondaire;
}
QLabel[role="legende"] {
    color: $texte_secondaire;
    font-size: ${legende}px;
}
QLabel[role="discret"] {
    color: $texte_desactive;
    font-size: ${legende}px;
}
QLabel[role="montant"] {
    font-family: "$famille_forte";
    font-weight: $graisse_forte;
}
QLabel[role="succes"] {
    color: $succes;
}
QLabel[role="avertissement"] {
    color: $avertissement;
}
QLabel[role="erreur"] {
    color: $erreur;
}
QLabel[role="pastille"] {
    color: $accent_survol;
    background: $teinte_selection;
    border: ${bordure}px solid $accent;
    border-radius: ${rayon_pastille}px;
    padding: 0px ${esp_s}px;
    font-size: ${legende}px;
    font-family: "$famille_moyenne";
    font-weight: $graisse_moyenne;
    min-height: ${hauteur_interne_pastille}px;
    max-height: ${hauteur_interne_pastille}px;
}
QLabel[vide="true"] {
    color: $texte_secondaire;
}
QLabel[role="etiquette"] {
    color: $texte_secondaire;
    background: $surface_elevee;
    border: none;
    border-radius: ${rayon_etiquette}px;
    padding: 0px ${esp_s}px;
    font-size: ${legende}px;
    min-height: ${etiquette_hauteur}px;
    max-height: ${etiquette_hauteur}px;
}

/* ---------- Blocs ---------- */
QFrame[role="bloc"] {
    background: $surface;
    border: ${bordure}px solid $couleur_bordure;
    border-radius: ${arrondi_bloc}px;
}
QFrame[role="separateur"] {
    background: $couleur_bordure;
    border: none;
    min-height: ${bordure}px;
    max-height: ${bordure}px;
}
QFrame[role="ligne"] {
    background: transparent;
    border: none;
    border-bottom: ${bordure}px solid $couleur_bordure;
}

/* ---------- Onglets ---------- */
QTabWidget::pane {
    border: none;
    border-top: ${bordure}px solid $couleur_bordure;
    top: -${bordure}px;
    background: transparent;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: $texte_secondaire;
    border: none;
    border-bottom: ${soulignement_onglet}px solid transparent;
    padding: ${esp_s}px ${esp_xs}px;
    margin-right: ${esp_xl}px;
    font-family: "$famille_moyenne";
    font-weight: $graisse_moyenne;
}
QTabBar::tab:hover {
    color: $texte;
}
QTabBar::tab:selected {
    color: $texte;
    border-bottom-color: $accent;
}

/* ---------- Glissières (position de lecture) ---------- */
QSlider::groove:horizontal {
    height: ${glissiere}px;
    background: $couleur_bordure;
    border-radius: ${rayon_glissiere}px;
}
QSlider::sub-page:horizontal {
    background: $accent;
    border-radius: ${rayon_glissiere}px;
}
QSlider::handle:horizontal {
    background: $texte;
    width: ${poignee_glissiere}px;
    height: ${poignee_glissiere}px;
    margin: -${marge_poignee_glissiere}px 0px;
    border-radius: ${rayon_poignee_glissiere}px;
}

/* ---------- Tableaux ---------- */
QTableView {
    background: transparent;
    color: $texte;
    border: none;
    gridline-color: transparent;
    selection-background-color: $teinte_selection;
    selection-color: $texte;
    outline: none;
}
QTableView::item {
    padding: 0px ${esp_m}px;
    border: none;
    border-bottom: ${bordure}px solid $couleur_bordure;
}
QHeaderView {
    background: transparent;
    border: none;
}
QHeaderView::section {
    background: transparent;
    color: $texte_secondaire;
    border: none;
    border-bottom: ${bordure}px solid $couleur_bordure;
    padding: ${esp_s}px ${esp_m}px;
    font-size: ${legende}px;
    font-family: "$famille_moyenne";
    font-weight: $graisse_moyenne;
}
QTableCornerButton::section {
    background: transparent;
    border: none;
}

/* ---------- Boutons ---------- */
QPushButton {
    background: $surface_elevee;
    color: $texte;
    border: ${bordure}px solid $couleur_bordure;
    border-radius: ${arrondi_controle}px;
    padding: 0px ${esp_l}px;
    min-height: ${hauteur_interne_controle}px;
    font-family: "$famille_moyenne";
    font-weight: $graisse_moyenne;
}
QPushButton:hover {
    border-color: $texte_desactive;
}
QPushButton:pressed {
    background: $fond;
}
QPushButton:focus {
    border-color: $accent;
}
QPushButton:disabled {
    background: $surface;
    color: $texte_desactive;
    border-color: $couleur_bordure;
}
QPushButton[variante="principal"] {
    background: $teinte;
    border-color: $accent;
}
QPushButton[variante="principal"]:hover {
    background: $teinte_survol;
    border-color: $accent_survol;
}
QPushButton[variante="principal"]:pressed {
    background: $teinte_pressee;
    border-color: $accent_presse;
}
QPushButton[variante="principal"]:disabled {
    background: $surface;
    color: $texte_desactive;
    border-color: $couleur_bordure;
}
QPushButton[variante="discret"] {
    background: transparent;
    border-color: transparent;
    color: $texte_secondaire;
}
QPushButton[variante="discret"]:hover {
    background: $surface_elevee;
    color: $texte;
}
QPushButton[variante="discret"]:focus {
    border-color: $accent;
}
QPushButton[variante="icone"] {
    padding: 0px;
    background: transparent;
    border-color: transparent;
    min-width: ${hauteur_interne_petit_bouton}px;
    max-width: ${hauteur_interne_petit_bouton}px;
    min-height: ${hauteur_interne_petit_bouton}px;
    max-height: ${hauteur_interne_petit_bouton}px;
}
QPushButton[variante="icone"]:hover {
    background: $surface_elevee;
}
QPushButton[variante="icone"]:focus {
    border-color: $accent;
}
QPushButton::menu-indicator {
    image: none;
    width: 0px;
}
QPushButton[variante="projet"] {
    background: transparent;
    border: none;
    padding: 0px;
    min-height: 0px;
    text-align: left;
    font-size: ${titre_bloc}px;
    font-family: "$famille_forte";
    font-weight: $graisse_forte;
}
QPushButton[variante="projet"]:hover {
    color: $accent_survol;
}
QPushButton[variante="projet"][vide="true"] {
    color: $texte_secondaire;
}

/* ---------- Champs ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: $fond;
    color: $texte;
    border: ${bordure}px solid $couleur_bordure;
    border-radius: ${arrondi_controle}px;
    padding: 0px ${esp_m}px;
    min-height: ${hauteur_interne_controle}px;
    selection-background-color: $accent;
    selection-color: $texte;
}
QTextEdit, QPlainTextEdit {
    background: $fond;
    color: $texte;
    border: ${bordure}px solid $couleur_bordure;
    border-radius: ${arrondi_controle}px;
    padding: ${esp_s}px ${esp_m}px;
    selection-background-color: $accent;
    selection-color: $texte;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
QTextEdit:hover, QPlainTextEdit:hover {
    border-color: $texte_desactive;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: $accent;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QTextEdit:disabled, QPlainTextEdit:disabled {
    background: $surface;
    color: $texte_desactive;
    border-color: $couleur_bordure;
}
QLineEdit[invalide="true"] {
    border-color: $erreur;
}
QComboBox {
    padding-right: ${esp_xxl}px;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: ${esp_xxl}px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow {
    image: url("$icone_fleche");
    width: ${icone_petite}px;
    height: ${icone_petite}px;
}
QComboBox::down-arrow:disabled {
    image: url("$icone_fleche_desactivee");
}
QComboBox QAbstractItemView {
    background: $surface_elevee;
    color: $texte;
    border: ${bordure}px solid $couleur_bordure;
    padding: ${esp_xs}px;
    outline: none;
    selection-background-color: $teinte;
    selection-color: $texte;
}

/* ---------- Cases à cocher ---------- */
QCheckBox {
    spacing: ${esp_s}px;
    background: transparent;
}
QCheckBox:disabled {
    color: $texte_desactive;
}
QCheckBox::indicator {
    width: ${case_a_cocher}px;
    height: ${case_a_cocher}px;
    border: ${bordure}px solid $texte_desactive;
    border-radius: ${arrondi_petit}px;
    background: $fond;
}
QCheckBox::indicator:hover {
    border-color: $accent_survol;
}
QCheckBox::indicator:checked {
    background: $accent;
    border-color: $accent;
    image: url("$icone_coche");
}
QCheckBox::indicator:checked:hover {
    background: $accent_survol;
    border-color: $accent_survol;
}
QCheckBox::indicator:disabled {
    background: $surface;
    border-color: $couleur_bordure;
}

/* ---------- Défilement ---------- */
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget#qt_scrollarea_viewport {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: ${barre_defilement}px;
    margin: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: ${barre_defilement}px;
    margin: 0px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: $couleur_bordure;
    border-radius: ${arrondi_petit}px;
    margin: ${esp_xs}px;
}
QScrollBar::handle:vertical {
    min-height: ${poignee_min}px;
}
QScrollBar::handle:horizontal {
    min-width: ${poignee_min}px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: $texte_desactive;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0px;
    height: 0px;
    border: none;
    background: none;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
}

/* ---------- Menus et infobulles ---------- */
QMenu {
    background: $surface_elevee;
    border: ${bordure}px solid $couleur_bordure;
    padding: ${esp_xs}px;
}
QMenu::item {
    padding: ${esp_s}px ${esp_m}px;
    border-radius: ${arrondi_controle}px;
    background: transparent;
}
QMenu::item:selected {
    background: $teinte;
}
QMenu::separator {
    height: ${bordure}px;
    background: $couleur_bordure;
    margin: ${esp_xs}px ${esp_s}px;
}
QToolTip {
    background: $surface_elevee;
    color: $texte;
    border: ${bordure}px solid $couleur_bordure;
    padding: ${esp_xs}px ${esp_s}px;
}
"""
)


def feuille_de_style(icones: dict[str, str], familles: dict[int, str] | None = None) -> str:
    """Feuille de style complète de l'app.

    `icones` donne le chemin des images utilisées par la feuille de style (flèche des listes
    déroulantes, coche des cases à cocher) : clés « fleche », « fleche_desactivee », « coche ».
    `familles` indique, pour chaque graisse, le nom de famille de police à utiliser
    (voir ui/polices.py) ; par défaut « Inter » pour toutes.
    """
    familles = familles or {}
    valeurs = {
        # couleurs
        "fond": Couleurs.FOND,
        "surface": Couleurs.SURFACE,
        "surface_elevee": Couleurs.SURFACE_ELEVEE,
        "couleur_bordure": Couleurs.BORDURE,
        "accent": Couleurs.ACCENT,
        "accent_survol": Couleurs.ACCENT_SURVOL,
        "accent_presse": Couleurs.ACCENT_PRESSE,
        "texte": Couleurs.TEXTE,
        "texte_secondaire": Couleurs.TEXTE_SECONDAIRE,
        "texte_desactive": Couleurs.TEXTE_DESACTIVE,
        "succes": Couleurs.SUCCES,
        "avertissement": Couleurs.AVERTISSEMENT,
        "erreur": Couleurs.ERREUR,
        "teinte_selection": rgba(Couleurs.ACCENT, Opacites.TEINTE_SELECTION),
        "teinte": rgba(Couleurs.ACCENT, Opacites.TEINTE),
        "teinte_survol": rgba(Couleurs.ACCENT, Opacites.TEINTE_SURVOL),
        "teinte_pressee": rgba(Couleurs.ACCENT, Opacites.TEINTE_PRESSEE),
        # typographie
        "famille": Typo.FAMILLE,
        "legende": Typo.LEGENDE,
        "courant": Typo.COURANT,
        "titre_bloc": Typo.TITRE_BLOC,
        "titre_page": Typo.TITRE_PAGE,
        "graisse_moyenne": Typo.GRAISSE_MOYENNE,
        "graisse_forte": Typo.GRAISSE_FORTE,
        "famille_moyenne": familles.get(Typo.GRAISSE_MOYENNE, Typo.FAMILLE),
        "famille_forte": familles.get(Typo.GRAISSE_FORTE, Typo.FAMILLE),
        # espacements
        "esp_xs": Espacements.XS,
        "esp_s": Espacements.S,
        "esp_m": Espacements.M,
        "esp_l": Espacements.L,
        "esp_xl": Espacements.XL,
        "esp_xxl": Espacements.XXL,
        # formes et tailles
        "bordure": Dimensions.BORDURE,
        "arrondi_controle": Arrondis.CONTROLE,
        "arrondi_bloc": Arrondis.BLOC,
        "arrondi_petit": Arrondis.PETIT,
        "rayon_pastille": Hauteurs.PASTILLE // 2,
        "rayon_etiquette": Dimensions.ETIQUETTE_HAUTEUR // 2,
        "etiquette_hauteur": Dimensions.ETIQUETTE_HAUTEUR,
        "soulignement_onglet": Dimensions.SOULIGNEMENT_ONGLET,
        "glissiere": Dimensions.GLISSIERE_HAUTEUR,
        "rayon_glissiere": Dimensions.GLISSIERE_HAUTEUR // 2,
        "poignee_glissiere": Dimensions.GLISSIERE_POIGNEE,
        "rayon_poignee_glissiere": Dimensions.GLISSIERE_POIGNEE // 2,
        "marge_poignee_glissiere": (Dimensions.GLISSIERE_POIGNEE - Dimensions.GLISSIERE_HAUTEUR) // 2,
        # Qt compte la hauteur sans les bordures : 36 px au total = 34 px + 2 × 1 px de bordure.
        "hauteur_interne_controle": Hauteurs.CONTROLE - 2 * Dimensions.BORDURE,
        "hauteur_interne_petit_bouton": Hauteurs.PETIT_BOUTON - 2 * Dimensions.BORDURE,
        "hauteur_interne_pastille": Hauteurs.PASTILLE - 2 * Dimensions.BORDURE,
        "icone_petite": Dimensions.ICONE_PETITE,
        "case_a_cocher": Dimensions.CASE_A_COCHER,
        "barre_defilement": Dimensions.BARRE_DEFILEMENT,
        "poignee_min": Dimensions.POIGNEE_DEFILEMENT_MIN,
        # images
        "icone_fleche": icones["fleche"],
        "icone_fleche_desactivee": icones["fleche_desactivee"],
        "icone_coche": icones["coche"],
    }
    return _MODELE_FEUILLE_DE_STYLE.substitute(valeurs)
