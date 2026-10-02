"""V3.1, lot 2 : noms des champs au-dessus des champs, réglages du studio côte à côte, cases à cocher
à la taille du texte."""

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QLabel, QLineEdit, QStyle, QStyleOptionButton, QVBoxLayout, QWidget

from ugc_studio.ui.composants.elements import (
    TOUTE_LA_RANGEE,
    ChampNomme,
    case_a_cocher,
    champ_entier,
    champs_en_colonnes,
    liste_deroulante,
)
from ugc_studio.ui.pages.sous_titres.reglages_communs import GrilleDeReglages, grille
from ugc_studio.ui.theme import Dimensions, Espacements, Typo


def _montrer(qtbot, contenu, largeur: int) -> QWidget:
    fenetre = QWidget()
    disposition = QVBoxLayout(fenetre)
    disposition.setContentsMargins(0, 0, 0, 0)
    if isinstance(contenu, QWidget):
        disposition.addWidget(contenu)
    else:
        disposition.addLayout(contenu)
    disposition.addStretch(1)
    qtbot.addWidget(fenetre)
    fenetre.resize(largeur, 400)
    fenetre.show()
    qtbot.waitExposed(fenetre)
    return fenetre


def test_le_nom_au_dessus_du_champ(app_configuree, qtbot):
    """Comme dans le brief du module Script : le nom en 12 px gris, 4 px au-dessus du champ."""
    champ = QLineEdit()
    nomme = ChampNomme("Couleur", champ)
    _fenetre = _montrer(qtbot, nomme, 300)  # garder la fenêtre : sinon Python la détruit
    assert nomme.nom.text() == "Couleur" and nomme.nom.property("role") == "legende"
    assert nomme.nom.font().pixelSize() == Typo.LEGENDE
    bas_du_nom = nomme.nom.mapTo(nomme, QPoint(0, nomme.nom.height())).y()
    assert champ.mapTo(nomme, QPoint(0, 0)).y() - bas_du_nom == Espacements.XS
    assert nomme.nom.mapTo(nomme, QPoint(0, 0)).x() == champ.mapTo(nomme, QPoint(0, 0)).x()  # alignés à gauche
    nomme.setEnabled(False)  # griser le champ grise aussi son nom
    assert not champ.isEnabled() and not nomme.nom.isEnabled()


def test_reglages_cote_a_cote_qui_passent_a_la_ligne(app_configuree, qtbot):
    """Studio : des réglages à leur largeur, côte à côte ; à la ligne quand la place manque ; une
    glissière (ou une case qui ouvre un effet) prend une rangée à elle seule ; un réglage caché ne
    laisse ni place ni espace."""
    champs = [champ_entier(0, 100, " px") for _ in range(3)]
    reglages = grille((("Flou", champs[0]), ("Décalage horizontal", champs[1]), ("Décalage vertical", champs[2])))
    assert isinstance(reglages, GrilleDeReglages) and list(reglages.champs) == ["Flou", "Décalage horizontal", "Décalage vertical"]
    fenetre = _montrer(qtbot, reglages, 700)
    hauts = {champ.mapTo(fenetre, QPoint(0, 0)).y() for champ in champs}
    assert len(hauts) == 1  # une seule rangée
    premier, second = (reglages.champs[nom] for nom in ("Flou", "Décalage horizontal"))
    assert second.x() - (premier.x() + premier.width()) == Espacements.L
    fenetre.resize(Dimensions.CHAMP_NOMBRE_LARGEUR + Espacements.L, 400)  # place pour un seul réglage
    qtbot.waitUntil(lambda: len({champ.mapTo(fenetre, QPoint(0, 0)).y() for champ in champs}) == 3, timeout=2000)
    haut_1, haut_2 = (reglages.champs[nom].y() for nom in ("Flou", "Décalage horizontal"))
    assert haut_2 - (haut_1 + premier.height()) == Espacements.M  # 12 px entre deux rangées
    reglages.champs["Décalage horizontal"].hide()
    qtbot.waitUntil(lambda: reglages.champs["Décalage vertical"].y() == haut_2, timeout=2000)


def test_reglage_sur_toute_la_largeur(app_configuree, qtbot):
    curseur = QLineEdit()
    reglages = grille((("Position", champ_entier(0, 10)), ("Réglage fin", curseur), ("Alignement", champ_entier(0, 10))), etirees=(1,))
    fenetre = _montrer(qtbot, reglages, 600)
    fin = reglages.champs["Réglage fin"]
    assert fin.width() == 600 and curseur.width() == 600
    position, alignement = reglages.champs["Position"], reglages.champs["Alignement"]
    assert position.y() < fin.y() < alignement.y()  # une rangée à lui seul, entre les deux autres
    assert fenetre.isVisible()


def test_champs_en_colonnes(app_configuree, qtbot):
    """Fenêtres et Options de Transcription : deux colonnes de même largeur, comme le brief."""
    nom, categorie, style = QLineEdit(), liste_deroulante(), QLineEdit()
    colonnes = champs_en_colonnes((("Nom", nom), ("Catégorie", categorie), ("Style", style, TOUTE_LA_RANGEE)))
    _fenetre = _montrer(qtbot, colonnes, 516)
    assert set(colonnes.champs) == {"Nom", "Catégorie", "Style"}
    assert nom.width() == categorie.width() == (516 - Espacements.L) // 2
    assert style.width() == 516
    assert colonnes.champs["Catégorie"].nom.mapTo(colonnes.champs["Catégorie"].parentWidget(), QPoint(0, 0)).y() == 0


def test_case_a_cocher_a_la_taille_du_texte(app_configuree, qtbot):
    """14 px, bordure comprise : la hauteur du texte courant (20 px jusqu'à la 3.0.0)."""
    assert Dimensions.CASE_A_COCHER == Typo.COURANT == 14
    zone, case = case_a_cocher("Séparer les voix")
    _fenetre = _montrer(qtbot, zone, 300)
    option = QStyleOptionButton()
    case.initStyleOption(option)
    # La place réservée à la case par le style : exactement 14 × 14.
    indicateur = case.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, case)
    assert (indicateur.width(), indicateur.height()) == (Dimensions.CASE_A_COCHER, Dimensions.CASE_A_COCHER)
    texte = case.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, case)
    # La case réellement dessinée : les points au moins à moitié couverts, à gauche du texte (le
    # lissage des coins arrondis déborde d'un léger voile sur le pixel voisin, d'où la tolérance).
    image = case.grab().toImage()
    echelle = image.width() / case.width()
    points = [
        (x / echelle, y / echelle)
        for x in range(round(texte.left() * echelle))
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() >= 128
    ]
    largeur = max(x for x, _ in points) - min(x for x, _ in points) + 1 / echelle
    hauteur = max(y for _, y in points) - min(y for _, y in points) + 1 / echelle
    assert abs(largeur - Dimensions.CASE_A_COCHER) <= 1 and abs(hauteur - Dimensions.CASE_A_COCHER) <= 1


def test_noms_au_dessus_dans_l_app(app_configuree, qtbot, services, tmp_path):
    """Quelques endroits typiques : Options de Transcription, Voix, studio des sous-titres."""
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    services.projets.creer("Sérum", tmp_path)
    fenetre.show()

    def nom_au_dessus(champ, texte: str) -> bool:
        parent = champ.parentWidget()
        while parent is not None and not isinstance(parent, ChampNomme):
            parent = parent.parentWidget()
        noms = [e for e in (parent.findChildren(QLabel) if parent else []) if e.text() == texte]
        if not noms:  # grille « nom au-dessus » faite à la main (Voix, Prise)
            noms = [e for e in champ.parentWidget().findChildren(QLabel) if e.text() == texte]
        (nom,) = noms
        haut_du_champ = champ.mapToGlobal(QPoint(0, 0))
        bas_du_nom = nom.mapToGlobal(QPoint(0, nom.height()))
        return bas_du_nom.y() <= haut_du_champ.y() and abs(nom.mapToGlobal(QPoint(0, 0)).x() - haut_du_champ.x()) <= 1

    fenetre.afficher_module("transcription")
    transcription = fenetre.page("transcription").atelier
    assert nom_au_dessus(transcription.modele, "Modèle") and nom_au_dessus(transcription.langue, "Langue")
    fenetre.afficher_module("voix")
    voix = fenetre.page("voix").atelier
    assert nom_au_dessus(voix.modele, "Modèle") and nom_au_dessus(voix.voix, "Voix")
    fenetre.afficher_module("sous-titres")
    studio = fenetre.page("sous-titres").atelier
    studio.source.choix_mots.bouton("importee").click()  # V3.1, lot 6 : les prises, dans les mots importés
    assert nom_au_dessus(studio.prises, "Prise")
    panneau = studio.panneau
    assert nom_au_dessus(panneau.prereglage, "Préréglage")
    assert nom_au_dessus(panneau.texte.police, "Police") and nom_au_dessus(panneau.texte.graisse, "Graisse")
