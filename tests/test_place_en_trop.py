"""V3.3, lot 1 (cahier des charges §9.6) : quand une zone (bloc d'une page ou d'une fenêtre, carte,
colonne qui défile) est plus haute que son contenu, la place en trop va en bas de la zone, jamais
au-dessus de son titre ni entre deux éléments. Seul un élément fait pour remplir la zone (une liste,
une colonne qui défile) prend la place qui reste.

Jusqu'à la 3.2.2, en fenêtre moyenne, le bloc Apparence (ses groupes fermés), étiré à la hauteur de
l'Aperçu, avait un grand vide au-dessus et sous son titre : Qt répartissait lui-même la place en trop."""

import pytest

from ugc_studio.projets import FICHIER_AUDIO
from ugc_studio.transcription import Mot, Transcription

ETIREMENT = 300

TEXTE = (
    "Franchement je n'y croyais pas du tout mais ce sérum Glowzy a vraiment changé ma peau en deux "
    "semaines seulement et le lien est juste en dessous pour en profiter"
)


def _hauteur_naturelle(widget, largeur: int) -> int:
    hauteur = widget.heightForWidth(largeur)
    return hauteur if hauteur > 0 else widget.sizeHint().height()


def _geometries(elements) -> list:
    return [element.geometry() for element in elements]


def _etirer(qtbot, cadre, largeur: int = 320) -> tuple:
    """Montre le bloc à la hauteur de son contenu, relève la place de ses éléments, puis l'étire de
    ETIREMENT px (comme à côté d'un bloc plus haut). Renvoie (éléments, places avant)."""
    disposition = cadre.layout()
    elements = [disposition.itemAt(rang).widget() for rang in range(disposition.count()) if disposition.itemAt(rang).widget()]
    qtbot.addWidget(cadre)
    cadre.resize(largeur, _hauteur_naturelle(cadre, largeur))
    cadre.show()
    qtbot.waitExposed(cadre)
    naturelle = _hauteur_naturelle(cadre, largeur)
    cadre.resize(largeur, naturelle)
    qtbot.waitUntil(lambda: cadre.height() == naturelle, timeout=3000)
    avant = _geometries(elements)
    cadre.resize(largeur, naturelle + ETIREMENT)
    qtbot.waitUntil(lambda: cadre.height() == naturelle + ETIREMENT, timeout=3000)
    return elements, avant


def test_un_bloc_etire_garde_son_contenu_en_haut(app_configuree, qtbot):
    """Le titre et les éléments restent à leur place, à leur hauteur ; le vide est en bas."""
    from PySide6.QtWidgets import QLineEdit

    from ugc_studio.ui.composants.elements import bloc, libelle
    from ugc_studio.ui.composants.zone import DispositionDeZone, ecarts_de_place

    cadre, disposition = bloc("Apparence")
    assert isinstance(disposition, DispositionDeZone)
    disposition.addWidget(libelle("Une explication assez longue pour passer à la ligne dans un bloc étroit comme celui-ci."))
    disposition.addWidget(QLineEdit())
    elements, avant = _etirer(qtbot, cadre)
    qtbot.waitUntil(lambda: _geometries(elements) == avant, timeout=3000)
    assert cadre.titre.y() == avant[0].y()
    assert ecarts_de_place(cadre) == []


def test_la_verification_voit_le_vide_d_une_disposition_ordinaire(app_configuree, qtbot):
    """Avec une disposition verticale ordinaire (jusqu'à la 3.2.2), Qt répartit la place en trop
    lui-même : la vérification le voit, et nomme l'élément touché."""
    from PySide6.QtWidgets import QFrame, QLineEdit, QVBoxLayout

    from ugc_studio.ui.composants.elements import libelle
    from ugc_studio.ui.composants.zone import ecarts_de_place

    cadre = QFrame()
    disposition = QVBoxLayout(cadre)
    disposition.addWidget(libelle("Apparence", "titre-bloc"))
    disposition.addWidget(QLineEdit())
    qtbot.addWidget(cadre)
    cadre.resize(320, 120)
    cadre.show()
    qtbot.waitExposed(cadre)
    ecarts = ecarts_de_place(cadre)
    assert ecarts and any("Apparence" in ecart for ecart in ecarts)


def test_un_element_qui_remplit_prend_la_place_qui_reste(app_configuree, qtbot):
    """Une liste ajoutée pour remplir le bloc (facteur d'étirement) prend la place en trop ; le titre
    ne bouge pas."""
    from PySide6.QtWidgets import QListWidget

    from ugc_studio.ui.composants.elements import bloc
    from ugc_studio.ui.composants.zone import ecarts_de_place

    cadre, disposition = bloc("Sous-titres")
    liste = QListWidget()
    disposition.addWidget(liste, 1)
    qtbot.addWidget(cadre)
    cadre.resize(320, _hauteur_naturelle(cadre, 320))
    cadre.show()
    qtbot.waitExposed(cadre)
    naturelle = _hauteur_naturelle(cadre, 320)
    cadre.resize(320, naturelle)
    qtbot.waitUntil(lambda: cadre.height() == naturelle, timeout=3000)
    titre, hauteur_liste = cadre.titre.geometry(), liste.height()
    cadre.resize(320, naturelle + ETIREMENT)
    qtbot.waitUntil(lambda: liste.height() == hauteur_liste + ETIREMENT, timeout=3000)
    assert cadre.titre.geometry() == titre
    assert ecarts_de_place(cadre) == []


# --- Le studio des sous-titres (le cas signalé après la 3.2.2) ----------------------------------


def _mots() -> list[Mot]:
    return [Mot(texte, rang * 0.4, rang * 0.4 + 0.35) for rang, texte in enumerate(TEXTE.split())]


@pytest.fixture
def page(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Sérum", tmp_path / "projets")
    services.projets.projet.transcription = Transcription(
        source=str(tmp_path / "pub.mp4"),
        audio=FICHIER_AUDIO,
        duree_s=12.0,
        infos={"video": True, "resolution": [1080, 1920]},
        langue="fr-FR",
        mots=_mots(),
        date="2026-10-03T14:00:00+02:00",
    )
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.resize(1100, 900)
    page.show()
    page.atelier.rafraichir()
    return page


def _y_dans(element, bloc) -> int:
    from PySide6.QtCore import QPoint

    return element.mapTo(bloc, QPoint(0, 0)).y()


def test_apparence_etiree_a_la_hauteur_de_l_apercu(page, qtbot):
    """Fenêtre moyenne, groupes de l'onglet Texte fermés : Apparence, plus courte que l'Aperçu, a sa
    hauteur (côte à côte) ; son titre reste en haut, à la même hauteur que celui de l'Aperçu, et ses
    réglages juste dessous."""
    from ugc_studio.ui.composants.zone import ecarts_dans, hauteur_du_contenu
    from ugc_studio.ui.pages.sous_titres.disposition import MOYENNE

    atelier = page.atelier
    assert atelier.studio.mode == MOYENNE
    for section in atelier.panneau.texte.sections.values():
        section.ouvrir(False)
    apparence, apercu = atelier.cadre_apparence, atelier.bloc_apercu

    def etiree() -> bool:
        contenu = hauteur_du_contenu(apparence.layout(), apparence.contentsRect().width())
        return apparence.height() == apercu.height() and contenu < apparence.contentsRect().height()

    qtbot.waitUntil(etiree, timeout=3000)
    assert _y_dans(apparence.titre, apparence) == _y_dans(apercu.titre, apercu)
    colonne = atelier.colonne_apparence
    espace = apparence.layout().spacing()
    assert _y_dans(colonne, apparence) == _y_dans(apparence.titre, apparence) + apparence.titre.height() + espace
    assert ecarts_dans(atelier) == []


def test_studio_en_grande_fenetre(page, qtbot):
    from ugc_studio.ui.composants.zone import ecarts_dans
    from ugc_studio.ui.pages.sous_titres.disposition import GRANDE

    page.resize(1800, 1300)
    qtbot.waitUntil(lambda: page.atelier.studio.mode == GRANDE, timeout=3000)
    qtbot.wait(50)
    assert ecarts_dans(page.atelier) == []


# --- Toute l'app : chaque page, des fenêtres ------------------------------------------------------


def test_chaque_page_garde_la_place_en_trop_en_bas(app_configuree, qtbot, services, tmp_path):
    """Chaque zone de chaque page (et de chaque onglet des Réglages) : la vérification étire sa
    disposition et regarde où va la place en trop."""
    from ugc_studio.ui.composants.zone import ecarts_dans
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    services.projets.creer("Sérum", tmp_path)
    fenetre.show()
    qtbot.waitExposed(fenetre)
    ecarts = []
    for identifiant in fenetre.identifiants_modules():
        fenetre.afficher_module(identifiant)
        qtbot.wait(50)
        ecarts += [f"page {identifiant}, {ecart}" for ecart in ecarts_dans(fenetre.page(identifiant))]
    fenetre.afficher_module("reglages")
    reglages = fenetre.page("reglages")
    for index in range(reglages.onglets.count()):
        reglages.onglets.setCurrentIndex(index)
        qtbot.wait(50)
        ecarts += [f"réglages, onglet {index}, {ecart}" for ecart in ecarts_dans(reglages)]
    assert not ecarts, "\n".join(ecarts)


def test_fenetres_et_cartes(app_configuree, qtbot, services):
    """Une fenêtre (bloc et boutons du bas), les cartes des préréglages et celles des conseils ; une
    fenêtre agrandie garde son contenu en haut du bloc, chaque élément à sa place."""
    from ugc_studio.conseils_des_pages import PAGES
    from ugc_studio.ui.composants.conseils import DialogueConseils
    from ugc_studio.ui.composants.zone import ecarts_dans
    from ugc_studio.ui.dialogues.prereglages import DialoguePrereglages
    from ugc_studio.ui.dialogues.projet import DialogueNouveauProjet

    nouveau = DialogueNouveauProjet(services.projets)
    for dialogue in (nouveau, DialoguePrereglages(services), DialogueConseils(PAGES["voix"])):
        qtbot.addWidget(dialogue)
        dialogue.show()
        qtbot.waitExposed(dialogue)
        ecarts = ecarts_dans(dialogue)
        assert not ecarts, f"{dialogue.windowTitle()} :\n" + "\n".join(ecarts)
    _sans_contenu_serre(nouveau)
    disposition = nouveau.cadre.layout()
    elements = [disposition.itemAt(rang) for rang in range(disposition.count())]
    avant, hauteur = _geometries(elements), nouveau.cadre.height()
    nouveau.resize(nouveau.width(), nouveau.height() + ETIREMENT)
    qtbot.waitUntil(lambda: nouveau.cadre.height() == hauteur + ETIREMENT, timeout=3000)
    assert _geometries(elements) == avant


def _sans_contenu_serre(dialogue) -> None:
    """Le bloc de la fenêtre a au moins la hauteur de son contenu à sa largeur : rien n'est serré."""
    from ugc_studio.ui.composants.zone import hauteur_du_contenu

    cadre = dialogue.cadre.contentsRect()
    assert hauteur_du_contenu(dialogue.cadre.layout(), cadre.width()) <= cadre.height()


# Un chemin qui passe sur plusieurs lignes dans une colonne étroite (il se coupe aux espaces).
CHEMIN_LONG = "D:\\Mes pubs\\Clients 2026\\Marque de sérum bio\\Campagne de rentrée\\Vidéos des créatrices"


def test_un_champ_qui_passe_a_la_ligne_a_la_hauteur_de_son_contenu(app_configuree, qtbot):
    """Un champ dont le texte passe à la ligne (le chemin du dossier des projets) a la hauteur qu'il
    lui faut à sa largeur. Jusqu'à la 3.2.2, sa hauteur restait bloquée à celle que Qt calcule pour
    une autre largeur, plus grande : la dernière ligne était coupée, et dans la fenêtre « Nouveau
    projet » agrandie, la place qui manquait au champ allait au titre."""
    from PySide6.QtWidgets import QHBoxLayout

    from ugc_studio.ui.composants.elements import ChampNomme, bloc, bouton, libelle
    from ugc_studio.ui.composants.zone import ecarts_de_place

    cadre, disposition = bloc("Nouveau projet")
    ligne = QHBoxLayout()
    chemin = libelle(CHEMIN_LONG, "secondaire", selectionnable=True)
    ligne.addWidget(chemin, 1)
    ligne.addWidget(bouton("Changer…", variante="contour"))
    champ = ChampNomme("Emplacement", ligne, etire=True)
    disposition.addWidget(champ)
    elements, avant = _etirer(qtbot, cadre, largeur=280)
    qtbot.waitUntil(lambda: _geometries(elements) == avant, timeout=3000)
    # Le cas d'avant : à sa largeur, le champ a besoin de plus que la hauteur calculée par Qt.
    assert champ.heightForWidth(champ.width()) > champ.sizeHint().height()
    assert champ.height() == champ.heightForWidth(champ.width())
    assert chemin.height() == chemin.heightForWidth(chemin.width())  # aucune ligne coupée
    assert ecarts_de_place(cadre) == []


def test_la_fenetre_nouveau_projet_grandit_avec_son_chemin(app_configuree, qtbot, services):
    """Un autre dossier, au chemin plus long, prend des lignes de plus : la fenêtre grandit pour le
    montrer en entier, le contenu toujours en haut du bloc."""
    from ugc_studio.ui.composants.zone import ecarts_dans
    from ugc_studio.ui.dialogues.projet import DialogueNouveauProjet

    dialogue = DialogueNouveauProjet(services.projets)
    qtbot.addWidget(dialogue)
    dialogue.show()
    qtbot.waitExposed(dialogue)
    _sans_contenu_serre(dialogue)
    hauteur = dialogue.height()
    dialogue.chemin.setText("\\".join([CHEMIN_LONG] * 3))  # comme après « Changer… »
    qtbot.waitUntil(lambda: dialogue.height() > hauteur, timeout=3000)
    qtbot.wait(50)
    _sans_contenu_serre(dialogue)
    assert ecarts_dans(dialogue) == []
