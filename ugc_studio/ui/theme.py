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


class CouleursApercu:
    """Studio des sous-titres (V2, lot 3, §7.7) : fond neutre, damier et repères de l'aperçu.

    Ce sont des couleurs de l'interface. Celles des sous-titres, elles, sont des choix de la vidéo :
    elles sont dans le style du projet (style_sous_titres.py), pas ici."""

    AUTOUR = "#09090D"  # autour de la vidéo, dans la toile (plus sombre que le fond de l'app)
    FOND_NEUTRE = "#52525B"  # gris moyen : un texte blanc ou noir y reste lisible
    DAMIER_CLAIR = "#71717A"  # damier : pour juger un texte prévu pour le calque transparent (V3)
    DAMIER_FONCE = "#3F3F46"
    ZONE_DE_SECURITE = Couleurs.ACCENT  # pointillés mauves
    MARGE_MAXIMUM = Couleurs.ERREUR  # trait rouge
    GRILLE = Couleurs.TEXTE  # traits fins des tiers et du milieu (voir Opacites.GRILLE)


class Opacites:
    """Transparences appliquées aux couleurs ci-dessus (0 = invisible, 1 = opaque)."""

    TEINTE_SELECTION = 0.12  # fond mauve léger d'un élément sélectionné
    TEINTE = 0.18  # fond mauve du bouton principal
    TEINTE_SURVOL = 0.26
    TEINTE_PRESSEE = 0.34
    # Bouton « contour » (outils dans un bloc) : contour gris (texte secondaire) bien visible.
    CONTOUR_BOUTON = 0.35
    CONTOUR_BOUTON_SURVOL = 0.60
    FOND_BADGE = 0.16  # fond coloré des badges de balises
    CONTOUR_BADGE = 0.55
    FOND_BADGE_SURVOL = 0.30
    # Barre de défilement fine des listes (listes déroulantes, tableaux) : légèrement transparente.
    POIGNEE_FINE = 0.35
    POIGNEE_FINE_SURVOL = 0.60
    GRILLE = 0.35  # grille de l'aperçu des sous-titres
    REPERES = 0.90  # zone de sécurité et marge maximum de l'aperçu


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
    # Bandeau du haut (V3.1) : titre du module, « Conseils » et coût de la session ; le haut de la
    # barre latérale (bouton du projet) a la même hauteur, et la même ligne dessous. 68 px : le
    # bouton du projet (36 px) y tombe à 16 px du haut et du bas.
    BANDEAU = 68
    PETIT_BOUTON = 28  # petits boutons (icônes)
    PASTILLE = 20  # pastilles d'information (ex. « Étape 2 »)
    CHOIX_LISTE = 32  # un choix dans une liste déroulante ouverte
    LIGNE_RESUME = 30  # résumé avant export (V3) : tableau en lecture seule, lignes plus serrées


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


# Listes déroulantes intégrées au champ (V1.1, §9.4 quinquies). Filet de sécurité : False remet
# la liste standard de Qt (posée par-dessus le champ), sans rien changer d'autre dans l'app.
LISTES_INTEGREES = True

# §4.4 — Montants : la partie entière et les 2 premières décimales sont en taille et couleur
# normales ; les décimales suivantes (3e, 4e…) sont plus petites (~70 %) et plus sombres.
RATIO_PETITES_DECIMALES = 0.70
COULEUR_PETITES_DECIMALES = Couleurs.TEXTE_SECONDAIRE


class Dimensions:
    """Autres tailles fixes de l'interface (px)."""

    BORDURE = 1  # épaisseur des bordures
    LARGEUR_BARRE_LATERALE = 200  # 224 jusqu'à la 3.0.0 (V3.1 : barre plus fine)
    ICONE = 20  # icônes de la barre latérale et des boutons-icônes (⋯, lecture)
    ICONE_PETITE = 16  # icônes des boutons avec texte et des menus, flèches, coches
    # Espace entre une icône et son texte : le même partout (barre latérale, boutons, menus…).
    ECART_ICONE_TEXTE = Espacements.M
    # Espace autour des blocs d'une page et entre eux (V3.1) : le même partout, entre la barre
    # latérale et les blocs, en haut, en bas, et entre deux blocs, l'un sous l'autre comme côte à côte.
    # À droite, la barre de défilement prend place dans cet espace (voir zone_defilante).
    ESPACE_BLOCS = Espacements.L
    CASE_A_COCHER = 18
    BARRE_DEFILEMENT = 16
    POIGNEE_DEFILEMENT_MIN = 32
    # Barre fine (listes déroulantes, barre horizontale des tableaux) : 10 px, poignée de 6 px.
    BARRE_DEFILEMENT_FINE = 10
    MARGE_POIGNEE_FINE = 2
    FONDU = 24  # dégradé en haut et en bas d'une zone qui défile, quand du contenu y est caché
    LISTE_CHOIX_VISIBLES = 8  # choix visibles d'un coup dans une liste déroulante ouverte
    RETRAIT_CHOIX = Espacements.XL  # les choix de la liste ouverte, décalés vers la droite
    SEPARATEUR_LISTE = 2 * Espacements.XS + BORDURE  # séparation entre deux groupes de choix
    # (Les pages ne sont plus limitées en largeur depuis la 1.0.1 : en plein écran, les blocs
    # prennent toute la place disponible.)
    DIALOGUE_LARGEUR = 520
    DIALOGUE_LARGE_LARGEUR = 760  # bibliothèque de styles, dictionnaire de prononciation
    DIALOGUE_LARGE_HAUTEUR = 560
    DIALOGUE_CONSEILS_LARGEUR = 640  # fenêtre « Conseils » : des lignes de texte faciles à lire
    DIALOGUE_VARIANTES_LARGEUR = 1000  # variantes A/B : une colonne par variante (le tableau défile)
    COLONNE_VARIANTE_LARGEUR = 240
    COLONNE_TITRES_VARIANTES_LARGEUR = 104  # « Modèle », « Voix », « Style », « Texte »
    CHAMP_DESCRIPTION_HAUTEUR = 88  # description d'une voix (Voice Design) : environ 3 lignes
    CHAMP_BRIEF_HAUTEUR = 88  # champ de plusieurs lignes du brief (bénéfices, preuves…) : 3 lignes
    CHAMP_TEXTE_COLLE_HAUTEUR = 160  # texte d'une page produit collé à la main (module Script)
    # Module Script, lot 2 : tableau « Réglages par variante » (« Personne qui parle »…) et
    # comparaison de scripts côte à côte (2 ou 3 colonnes, la fenêtre défile au-delà).
    COLONNE_TITRES_VARIANTES_SCRIPT_LARGEUR = 136
    DIALOGUE_COMPARER_SCRIPTS_LARGEUR = 1000
    COLONNE_SCRIPT_COMPARE_LARGEUR = 296
    DIALOGUE_SCRIPTS_HAUTEUR = 660  # variantes de script et comparaison : plus de lignes visibles d'un coup
    CHAMP_SCRIPT_COLLE_HAUTEUR = 120  # « Ajouter un script qui a marché » : environ 5 lignes
    COLONNE_FORMULAIRE_LARGEUR = 220  # formulaire sur deux colonnes de même largeur (fenêtre étroite)
    CHAMP_NOMBRE_LARGEUR = 96  # champs de prix, de taux…
    ETIQUETTE_HAUTEUR = 20  # petites étiquettes grises (ex. capacités d'un modèle)
    TABLEAU_HAUTEUR_MIN = 320
    COLONNE_TEXTE_MIN = 88  # une colonne de texte d'un tableau ne se resserre pas en dessous
    ZONE_DEFILANTE_HAUTEUR_SOUHAITEE = 160  # voir ZoneDefilante (ui/composants/defilement.py)
    DIALOGUE_HAUTEUR_MAX = 680  # une fenêtre de dialogue doit tenir sur l'écran d'un portable (768 px)
    EDITEUR_HAUTEUR_MIN = 180  # éditeur de script
    # Studio des sous-titres (V2, lot 3) : aperçu à gauche, réglages à droite ; l'un sous l'autre
    # quand la page a moins de STUDIO_DEUX_COLONNES_MIN de large (fenêtre étroite).
    STUDIO_COLONNE_APERCU_LARGEUR = 400
    STUDIO_DEUX_COLONNES_MIN = 880
    APERCU_HAUTEUR_MAX = 540  # toile de l'aperçu : une vidéo 9:16 y fait 304 × 540
    APERCU_HAUTEUR_MIN = 200
    APERCU_LARGEUR_MIN = 160
    DAMIER_CASE = 12  # côté d'une case du damier
    REPERE_EPAISSEUR = 1  # traits des repères (toujours 1 px à l'écran, quel que soit le zoom)
    REPERE_POINTILLES = (4, 4)  # zone de sécurité : 4 px de trait, 4 px d'espace
    CHAMP_COTE_LARGEUR = 112  # largeur ou hauteur d'un format personnalisé (« 1080 px »)
    # Frise des sous-titres (V2, lot 7) : graduations du temps, blocs des sous-titres, traits des mots.
    FRISE_REGLE_HAUTEUR = 18
    FRISE_BLOC_HAUTEUR = 36
    FRISE_MOTS_HAUTEUR = 12
    FRISE_MARGE = 8  # à gauche et à droite : le premier et le dernier bloc restent saisissables
    FRISE_POIGNEE = 6  # un bord commun se saisit à 6 px près
    FRISE_CURSEUR = 2  # trait du moment lu
    FRISE_MARQUE_AJUSTE = 3  # rayon du point d'un sous-titre ajusté à la main
    FRISE_GRADUATION_MIN = 64  # écart minimum entre deux temps écrits sur la règle
    FRISE_ZOOM_MAX = 24  # Ctrl + molette : jusqu'à 24 fois plus large que « toute la pub »
    FRISE_PAS_DE_ZOOM = 1.25  # un cran de molette
    # Préréglages de sous-titres (V2, lot 7) : vignettes animées, 3 cartes par rangée et les 2
    # rangées des 6 préréglages fournis visibles sans faire défiler, dans une fenêtre qui tient sur
    # l'écran d'un portable (DIALOGUE_HAUTEUR_MAX).
    VIGNETTE_LARGEUR = 240
    VIGNETTE_HAUTEUR = 108
    VIGNETTE_IMAGES_PAR_SECONDE = 20
    DIALOGUE_PREREGLAGES_LARGEUR = 880
    DIALOGUE_PREREGLAGES_HAUTEUR = DIALOGUE_HAUTEUR_MAX
    # Fenêtre d'export (V3) : réglages, résumé avant export et avancement dans une seule fenêtre, qui
    # tient sur l'écran d'un portable ; le résumé (source et export côte à côte) défile si besoin.
    DIALOGUE_EXPORT_LARGEUR = 760
    DIALOGUE_EXPORT_HAUTEUR = DIALOGUE_HAUTEUR_MAX
    BARRE_AVANCEMENT_HAUTEUR = 8  # barre d'avancement d'un export : rail arrondi, rempli de mauve
    EDITEUR_REPLIQUE_HAUTEUR_MIN = 88  # éditeur d'une réplique (grandit ensuite avec son texte)
    # Badges de balises : même hauteur que les pastilles (Hauteurs.PASTILLE), entièrement arrondis.
    BADGE_MARGE_HORIZONTALE = 8  # espace intérieur, à gauche et à droite du nom de la balise
    BADGE_ECART = 4  # espace de part et d'autre d'un badge dans le texte
    GLISSIERE_HAUTEUR = 4  # barre de progression du lecteur
    GLISSIERE_POIGNEE = 12
    ETOILE = 16  # étoiles de notation des prises
    CHAMP_STYLE_LARGEUR_MIN = 320
    # Une liste déroulante prend la largeur de son plus long choix quand il y a de la place, mais
    # peut rétrécir jusqu'à environ ce nombre de caractères (texte abrégé par « … ») : ainsi, un
    # choix très long n'élargit jamais la page au-delà de la fenêtre.
    LISTE_CARACTERES_MIN = 10
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

# Espace fixe (non réglable) que Qt ajoute après la colonne des icônes dans les menus.
_QT_ESPACE_APRES_ICONE_MENU = 4

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
/* Haut de la barre latérale (bouton du projet) : même ligne dessous que le bandeau. */
QFrame#hautBarreLaterale {
    background: transparent;
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
QLabel[role="intitule"] {
    font-family: "$famille_moyenne";
    font-weight: $graisse_moyenne;
}
QLabel[role="titre-bloc"] {
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
QLabel[role="legende"]:disabled {
    color: $texte_desactive;
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
QLabel[role="legende-avertissement"] {
    color: $avertissement;
    font-size: ${legende}px;
}
QLabel[role="erreur"] {
    color: $erreur;
}
QLabel[role="legende-erreur"] {
    color: $erreur;
    font-size: ${legende}px;
}
QLabel[role="legende-modifiee"] {
    color: $accent_survol;
    font-size: ${legende}px;
}
QLabel[role="legende-modifiee"]:disabled {
    color: $texte_desactive;
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
QFrame[role="separateur-vertical"] {
    background: $couleur_bordure;
    border: none;
    min-width: ${bordure}px;
    max-width: ${bordure}px;
}
QFrame[role="depot"] {
    background: transparent;
    border: ${bordure}px dashed $texte_desactive;
    border-radius: ${arrondi_bloc}px;
}
QFrame[role="depot"][survol="true"] {
    border-color: $accent;
    background: $teinte_selection;
}
QFrame[role="ligne"] {
    background: transparent;
    border: none;
    border-bottom: ${bordure}px solid $couleur_bordure;
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
/* Barre horizontale d'un tableau trop large (dernier recours) : fine, comme celle des listes. */
QTableView QScrollBar:horizontal {
    height: ${barre_fine}px;
}
QTableView QScrollBar::handle:horizontal {
    background: $poignee_fine;
    border-radius: ${rayon_poignee_fine}px;
    margin: ${marge_poignee_fine}px;
}
QTableView QScrollBar::handle:horizontal:hover {
    background: $poignee_fine_survol;
}

/* ---------- Boutons des fenêtres standard de Qt (messages, saisie d'un nom…) ----------
   Les boutons de l'app elle-même sont dessinés par ui/composants/bouton.py. */
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
/* Variantes A/B (§5.6) et variantes de script (V2) : valeur modifiée par rapport aux réglages de
   base, surlignée en mauve */
QLineEdit[modifie="true"], QComboBox[modifie="true"], QTextEdit[modifie="true"], QSpinBox[modifie="true"] {
    border-color: $accent;
    background: $teinte_selection;
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
/* Liste ouverte : sous le champ (combobox-popup: 0), bordée de mauve comme le champ ouvert ;
   les choix sont décalés vers la droite (voir ui/composants/liste_deroulante.py). */
QComboBox {
    combobox-popup: $liste_popup;
}
QComboBox:on {
    border-color: $accent;
}
QComboBox QAbstractItemView {
    background: $surface_elevee;
    color: $texte;
    border: ${bordure}px solid $accent;
    padding: ${esp_xs}px 0px;
    outline: none;
    selection-background-color: $teinte;
    selection-color: $texte;
}
QComboBox QAbstractItemView::item {
    padding: 0px ${esp_m}px 0px ${retrait_choix}px;
    min-height: ${hauteur_choix}px;
    border: none;
}
QComboBox QAbstractItemView::item:selected {
    background: $teinte;
    color: $texte;
}
QComboBox QAbstractItemView::item:disabled {
    color: $texte_desactive;
}
QComboBox QAbstractItemView QScrollBar:vertical {
    width: ${barre_fine}px;
}
QComboBox QAbstractItemView QScrollBar::handle:vertical {
    background: $poignee_fine;
    border-radius: ${rayon_poignee_fine}px;
    margin: ${marge_poignee_fine}px;
}
QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {
    background: $poignee_fine_survol;
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
QAbstractScrollArea::corner {
    background: transparent;
    border: none;
}

/* ---------- Menus et infobulles ---------- */
QMenu {
    background: $surface_elevee;
    border: ${bordure}px solid $couleur_bordure;
    padding: ${esp_xs}px;
}
QMenu::item {
    padding: ${esp_s}px ${esp_m}px ${esp_s}px ${marge_gauche_menu}px;
    border-radius: ${arrondi_controle}px;
    background: transparent;
}
QMenu::icon {
    left: ${esp_m}px;
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
        "poignee_fine": rgba(Couleurs.TEXTE_SECONDAIRE, Opacites.POIGNEE_FINE),
        "poignee_fine_survol": rgba(Couleurs.TEXTE_SECONDAIRE, Opacites.POIGNEE_FINE_SURVOL),
        # typographie
        "famille": Typo.FAMILLE,
        "legende": Typo.LEGENDE,
        "courant": Typo.COURANT,
        "titre_bloc": Typo.TITRE_BLOC,
        "titre_page": Typo.TITRE_PAGE,
        "grand_chiffre": Typo.GRAND_CHIFFRE,
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
        "rayon_etiquette": Dimensions.ETIQUETTE_HAUTEUR // 2,
        "etiquette_hauteur": Dimensions.ETIQUETTE_HAUTEUR,
        "glissiere": Dimensions.GLISSIERE_HAUTEUR,
        "rayon_glissiere": Dimensions.GLISSIERE_HAUTEUR // 2,
        "poignee_glissiere": Dimensions.GLISSIERE_POIGNEE,
        "rayon_poignee_glissiere": Dimensions.GLISSIERE_POIGNEE // 2,
        "marge_poignee_glissiere": (Dimensions.GLISSIERE_POIGNEE - Dimensions.GLISSIERE_HAUTEUR) // 2,
        # Qt compte la hauteur sans les bordures : 36 px au total = 34 px + 2 × 1 px de bordure.
        "hauteur_interne_controle": Hauteurs.CONTROLE - 2 * Dimensions.BORDURE,
        "hauteur_interne_petit_bouton": Hauteurs.PETIT_BOUTON - 2 * Dimensions.BORDURE,
        "icone_petite": Dimensions.ICONE_PETITE,
        # Menus : Qt place le texte à « taille d'icône + 4 px » du début de la zone de texte.
        # Cette marge gauche pose l'icône à 12 px du bord et son texte à ECART_ICONE_TEXTE
        # après elle, comme partout ailleurs dans l'app.
        "marge_gauche_menu": Espacements.M + Dimensions.ECART_ICONE_TEXTE - _QT_ESPACE_APRES_ICONE_MENU,
        "case_a_cocher": Dimensions.CASE_A_COCHER,
        "barre_defilement": Dimensions.BARRE_DEFILEMENT,
        "poignee_min": Dimensions.POIGNEE_DEFILEMENT_MIN,
        "barre_fine": Dimensions.BARRE_DEFILEMENT_FINE,
        "marge_poignee_fine": Dimensions.MARGE_POIGNEE_FINE,
        "rayon_poignee_fine": (Dimensions.BARRE_DEFILEMENT_FINE - 2 * Dimensions.MARGE_POIGNEE_FINE) // 2,
        "liste_popup": 0 if LISTES_INTEGREES else 1,
        "retrait_choix": Dimensions.RETRAIT_CHOIX,
        "hauteur_choix": Hauteurs.CHOIX_LISTE,
        # images
        "icone_fleche": icones["fleche"],
        "icone_fleche_desactivee": icones["fleche_desactivee"],
        "icone_coche": icones["coche"],
    }
    return _MODELE_FEUILLE_DE_STYLE.substitute(valeurs)
