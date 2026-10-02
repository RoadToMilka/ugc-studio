"""V3.1, lot 3 : boutons et aides. Un cercle tourne dans le bouton pendant un travail ; les phrases
d'aide passent dans une icône « i » (sauf les indispensables) ; « Rétablir » de « Réorganiser à la
main » devient une icône ; la fenêtre « Conseils » montre ses rubriques en cartes ; plus de « TOUT EN
MAJUSCULES » dans l'interface."""

from decimal import Decimal

from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QToolTip,
    QWidget,
)

from ugc_studio.conseils_des_pages import PAGES
from ugc_studio.sous_titres import typographie
from ugc_studio.style_sous_titres import CASSES
from ugc_studio.ui import taches
from ugc_studio.ui.composants.bouton import Bouton, BoutonOccupe, montrer_occupe
from ugc_studio.ui.composants.conseils import DialogueConseils, entete_de_fenetre
from ugc_studio.ui.composants.elements import (
    BoutonInfo,
    ChampNomme,
    Info,
    bloc,
    bouton,
    case_a_cocher,
    intitule,
    ligne_avec_aide,
    texte_en_lignes,
)
from ugc_studio.ui.composants.section_repliable import SectionRepliable
from ugc_studio.ui.theme import Dimensions, Durees, Espacements, Hauteurs


def _montrer(qtbot, element):
    qtbot.addWidget(element)
    element.show()
    qtbot.waitExposed(element)
    return element


# --- Le cercle qui tourne dans le bouton -----------------------------------------------------------


def test_bouton_occupe(app_configuree, qtbot):
    """Pendant un travail : un cercle tourne à la place de l'icône et du texte ; le bouton garde sa
    taille et ses couleurs (il n'est pas grisé) et ne se reclique pas, ni à la souris ni au clavier."""
    clics = []
    principal = _montrer(qtbot, bouton("Générer l'audio", "principal", "audio-lines", lambda: clics.append(1)))
    taille, avant = principal.size(), principal.grab().toImage()
    echelle = avant.width() / principal.width()
    bord = QPoint(round(Espacements.XS * echelle), round(principal.height() / 2 * echelle))  # fond, loin du texte

    principal.definir_occupe(True)
    assert principal.est_occupe() and principal.isEnabled() and principal.size() == taille
    assert principal.cursor().shape() == Qt.CursorShape.BusyCursor
    qtbot.mouseClick(principal, Qt.MouseButton.LeftButton)
    principal.setFocus()
    qtbot.keyClick(principal, Qt.Key.Key_Space)
    qtbot.keyClick(principal, Qt.Key.Key_Return)
    assert clics == []
    image = principal.grab().toImage()
    assert image.pixelColor(bord) == avant.pixelColor(bord)  # même fond mauve : pas grisé
    assert image != avant  # le texte a laissé place au cercle
    qtbot.wait(Durees.ROUE_TOUR_MS // 4)
    assert principal.grab().toImage() != image  # le cercle a tourné

    principal.definir_occupe(False)
    assert not principal.est_occupe() and principal.cursor().shape() == Qt.CursorShape.PointingHandCursor
    qtbot.mouseClick(principal, Qt.MouseButton.LeftButton)
    assert clics == [1]


def test_un_seul_bouton_occupe_a_la_fois(app_configuree, qtbot):
    premier, second = bouton("Lire la page"), bouton("Analyser ce texte")
    for element in (premier, second):
        qtbot.addWidget(element)
    occupe = BoutonOccupe()
    occupe.occuper(premier)
    assert premier.est_occupe() and occupe.est(premier) and not occupe.est(second)
    occupe.occuper(second)  # un nouveau travail : le cercle passe dans l'autre bouton
    assert not premier.est_occupe() and second.est_occupe()
    occupe.liberer()
    assert not second.est_occupe() and occupe.bouton is None and not occupe.est(None)
    # Sans effet (et sans erreur) : aucun bouton, un bouton de Qt, un bouton détruit entre-temps.
    montrer_occupe(None, True)
    autre = QPushButton("Qt")
    qtbot.addWidget(autre)
    montrer_occupe(autre, True)
    detruit = bouton("Supprimé")
    detruit.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    montrer_occupe(detruit, False)


def test_icone_seule_au_milieu_d_une_rangee_de_boutons(app_configuree, qtbot):
    """V3.1 : un bouton sans texte (ex. le ↺ de « Réorganiser à la main ») est un carré à la hauteur
    des autres boutons ; « icone » garde sa petite taille."""
    retablir = bouton("", variante="contour", nom_icone="rotate-ccw")
    assert retablir.sizeHint().width() == retablir.sizeHint().height() == Hauteurs.CONTROLE
    assert bouton("", variante="icone", nom_icone="play").sizeHint().height() == Hauteurs.PETIT_BOUTON


# --- L'icône « i » ---------------------------------------------------------------------------------


def test_texte_d_une_bulle_en_lignes_courtes():
    texte = " ".join(["Une explication assez longue pour passer à la ligne"] * 4)
    lignes = texte_en_lignes(texte).split("\n")
    assert len(lignes) > 1 and all(len(ligne) <= Dimensions.BULLE_CARACTERES for ligne in lignes)
    # Les retours à la ligne voulus (une ligne par état…) sont gardés.
    assert texte_en_lignes("À venir : les mots pas encore dits.\nMot actif : le mot dit.").count("\n") == 1


def test_bouton_info(app_configuree, qtbot):
    """L'icône « i » : à la hauteur du texte courant ; son explication s'affiche dans une bulle,
    tout de suite au survol (ou au clic, ou après le temps d'arrêt habituel)."""
    texte = "Une fin de phrase termine alors toujours le sous-titre : pratique."
    aide = _montrer(qtbot, BoutonInfo(texte))
    assert aide.size().width() == aide.size().height() == Dimensions.ICONE_INFO
    assert aide.text() == texte and aide.cursor().shape() == Qt.CursorShape.WhatsThisCursor
    attendu = texte_en_lignes(typographie(texte, "fr"))  # espace insécable avant « : »
    assert " :" in attendu
    aide.montrer()
    qtbot.waitUntil(lambda: QToolTip.isVisible() and QToolTip.text() == attendu, timeout=2000)
    QToolTip.hideText()
    centre = QPoint(aide.width() // 2, aide.height() // 2)
    assert QApplication.sendEvent(aide, QHelpEvent(QEvent.Type.ToolTip, centre, aide.mapToGlobal(centre)))
    qtbot.waitUntil(lambda: QToolTip.isVisible() and QToolTip.text() == attendu, timeout=2000)
    QToolTip.hideText()
    aide.setText("Autre explication.")
    assert aide.text() == "Autre explication."


def _ecart_et_centres(gauche, droite) -> tuple[int, int]:
    """L'écart entre deux éléments côte à côte, et l'écart entre leurs centres en hauteur."""
    racine = gauche.window()
    ecart = droite.mapTo(racine, QPoint(0, 0)).x() - gauche.mapTo(racine, QPoint(gauche.width(), 0)).x()
    centre_gauche = gauche.mapTo(racine, QPoint(0, gauche.height() // 2)).y()
    centre_droite = droite.mapTo(racine, QPoint(0, droite.height() // 2)).y()
    return ecart, abs(centre_gauche - centre_droite)


def _juste_avant(texte, aide) -> bool:
    """L'icône est 8 px avant le texte, centrée sur sa hauteur (à 1 px près)."""
    ecart, centres = _ecart_et_centres(aide, texte)
    return ecart == Dimensions.ECART_INFO and centres <= 1


def test_icone_i_au_debut_du_texte_qu_elle_explique(app_configuree, qtbot):
    """V3.2 : devant le titre d'un bloc, le nom d'un champ, un petit titre ou le titre d'une fenêtre,
    8 px avant lui (jusqu'à la 3.1.0 : 4 px après) ; sans aide, rien ne change."""
    assert Dimensions.ECART_INFO == Espacements.S
    cadre, _d = bloc("Frise", aide="Clic : aller à ce moment.")
    _montrer(qtbot, cadre)
    assert cadre.titre.text() == "Frise" and _juste_avant(cadre.titre, cadre.aide)
    sans_aide, _d = bloc("Exporter")
    assert sans_aide.aide is None and sans_aide.findChildren(BoutonInfo) == []

    champ = ChampNomme("Avance de l'allumage", QLineEdit(), aide="Si les mots s'allument un peu tard.")
    _montrer(qtbot, champ)
    assert _juste_avant(champ.nom, champ.aide)
    assert champ.aide.mapTo(champ, QPoint(0, 0)).x() == champ.element.mapTo(champ, QPoint(0, 0)).x()  # au bord du champ

    titre = intitule("Réorganiser à la main", "Choisis un sous-titre dans la liste.")
    _montrer(qtbot, titre)
    assert _juste_avant(titre.etiquette, titre.aide)

    from PySide6.QtWidgets import QDialog

    fenetre = QDialog()
    entete = entete_de_fenetre("Variantes A/B", "variantes", aide="Génère plusieurs versions du même script.")
    fenetre.setLayout(entete)
    fenetre.resize(Dimensions.DIALOGUE_LARGEUR, Hauteurs.CONTROLE)
    _montrer(qtbot, fenetre)
    assert _juste_avant(entete.titre, entete.aide)
    assert entete.conseils.mapTo(fenetre, QPoint(entete.conseils.width(), 0)).x() == fenetre.width()  # Conseils au bout


def test_icone_i_entre_la_case_et_son_texte(app_configuree, qtbot):
    """V3.2 : sur une case à cocher, la case, 8 px, l'icône, 8 px, le texte. Un clic sur l'icône
    montre l'explication sans cocher la case ; un clic sur le texte la coche."""
    zone, case = case_a_cocher("Séparer les voix", "Chaque mot reçoit la personne qui parle.")
    _montrer(qtbot, zone)
    aide = zone.aide
    assert aide is case.aide and aide.parentWidget() is case and case.text() == "Séparer les voix"
    option = QStyleOptionButton()
    case.initStyleOption(option)
    indicateur = case.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, case)
    texte = case.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, case)
    assert aide.x() - (indicateur.right() + 1) == Dimensions.ECART_INFO
    assert texte.left() - (aide.x() + aide.width()) == Dimensions.ECART_INFO
    assert abs((aide.y() + aide.height() / 2) - (indicateur.top() + indicateur.height() / 2)) <= 1
    qtbot.mouseClick(aide, Qt.MouseButton.LeftButton)
    assert not case.isChecked()
    qtbot.mouseClick(case, Qt.MouseButton.LeftButton, pos=texte.center())
    assert case.isChecked()
    # Sans explication : la case, 8 px, le texte (rien ne change).
    _zone, simple = case_a_cocher("Grille")
    _montrer(qtbot, _zone)
    option = QStyleOptionButton()
    simple.initStyleOption(option)
    indicateur = simple.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, simple)
    texte = simple.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, simple)
    assert simple.aide is None and texte.left() - (indicateur.right() + 1) == Espacements.S


def test_icone_i_apres_un_bouton_et_dans_une_section(app_configuree, qtbot):
    """Après un bouton, l'icône reste après lui, 8 px après. Sur le titre d'une section repliable :
    la flèche, 8 px, l'icône, 8 px, le texte (comme sur une case à cocher)."""
    zone = QWidget()
    choisir = bouton("Choisir les modèles…")
    ligne = ligne_avec_aide(choisir, BoutonInfo("Seuls les modèles chargés sont listés."), apres=True)
    zone.setLayout(ligne)
    _montrer(qtbot, zone)
    ecart, centres = _ecart_et_centres(choisir, ligne.aide)
    assert ecart == Dimensions.ECART_INFO and centres <= 1

    section = SectionRepliable("Sous-titre entier", True, aide="Les animations ne changent pas les temps.")
    _montrer(qtbot, section)
    assert section.aide.parentWidget() is section.titre
    assert section.aide.x() == Dimensions.ICONE_PETITE + Dimensions.ECART_INFO
    assert section.titre._debut_du_texte() == section.aide.x() + section.aide.width() + Dimensions.ECART_INFO
    assert abs(section.aide.y() + section.aide.height() / 2 - section.titre.height() / 2) <= 1
    section.titre.click()  # le titre ouvre et ferme la section…
    assert not section.est_ouverte()
    qtbot.mouseClick(section.aide, Qt.MouseButton.LeftButton)  # … pas l'icône
    assert not section.est_ouverte()


def test_retablir_d_un_groupe_de_16_px(app_configuree, qtbot):
    """V3.2 : le ↺ d'un groupe du studio fait 16 px de haut à l'écran (18 px jusqu'à la 3.1.0), 4 px
    après le titre."""
    section = SectionRepliable("Contour", True)
    retablir = section.ajouter_retablir(lambda: None, "Revenir au préréglage")
    retablir.show()
    _montrer(qtbot, section)
    assert retablir.iconSize() == QSize(Dimensions.ICONE_RETABLIR, Dimensions.ICONE_RETABLIR)
    image = retablir.icon().pixmap(retablir.iconSize()).toImage()
    lignes = [y for y in range(image.height()) if any(image.pixelColor(x, y).alpha() > 0 for x in range(image.width()))]
    assert len(lignes) == 16  # du haut au bas du dessin, comme le mesure l'œil
    assert retablir.mapTo(section, QPoint(0, 0)).x() - section.titre.width() == Espacements.XS


# --- Dans l'app ------------------------------------------------------------------------------------


def _infos_visibles(page) -> list[str]:
    """Les phrases d'aide affichées (avec leur ampoule) dans une page."""
    return [i.text() for i in page.findChildren(Info) if i.isVisible() and i.ampoule.isVisible() and i.text()]


def test_moins_de_phrases_d_aide_dans_l_app(app_configuree, qtbot, services, tmp_path):
    """Les explications passent dans des icônes « i » ; ne restent écrites que les phrases
    indispensables pour savoir quoi faire (V3.1, annexe du document de la version)."""
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    services.projets.creer("Sérum", tmp_path)
    fenetre.show()
    fenetre.afficher_module("transcription")
    transcription = fenetre.page("transcription").atelier
    assert _infos_visibles(transcription) == [
        "Vidéo (MP4, MOV, MKV…) ou audio (WAV, MP3, M4A…) : la piste son est extraite automatiquement."
    ]
    assert transcription.zone_separation.aide.text().startswith("Chaque mot reçoit la personne qui parle")
    fenetre.afficher_module("script")
    script = fenetre.page("script").atelier
    assert _infos_visibles(script) == []  # « Remplis ce que tu sais… », « L'app lit d'abord la page… » : dans des « i »
    assert script.produit.aide_lecture.text().startswith("L'app lit d'abord la page elle-même")
    fenetre.afficher_module("voix")
    assert _infos_visibles(fenetre.page("voix").atelier) == []
    fenetre.afficher_module("sous-titres")
    sous_titres = fenetre.page("sous-titres").atelier
    assert _infos_visibles(sous_titres) == []
    assert sous_titres.cadre_frise.aide.text().startswith("Clic : aller à ce moment")
    assert sous_titres.cadre_export.aide.text().startswith("Vidéo avec sous-titres : la vidéo de l'aperçu")
    assert sous_titres.titre_reorganiser.aide.text().startswith("Choisis un sous-titre dans la liste")
    # « Rétablir » : l'icône seule, au milieu des autres boutons ; même sens au survol, même menu.
    retablir = sous_titres.bouton_retablir
    assert retablir.text() == "" and retablir.toolTip() == "Revenir au découpage automatique" and retablir.menu() is not None
    # Les mesures de l'écran : une ligne de données, sans ampoule.
    assert type(sous_titres.infos_ecran) is QLabel
    fenetre.afficher_module("reglages")
    reglages = fenetre.page("reglages")
    assert _infos_visibles(reglages) == []  # Connexions API
    reglages.onglets.setCurrentIndex(1)  # Modèles et prix : il reste une chose à faire avec le taux
    assert _infos_visibles(reglages) == ["Taux de départ, à vérifier : saisis le taux du jour ou récupère-le auprès de la BCE."]


def test_date_du_taux_en_ligne_de_donnees(app_configuree, qtbot, services):
    """La date du taux de change : « 01/10/2026 » (et non « 2026-10-01 »), sans ampoule."""
    from ugc_studio.ui.pages.reglages import PageReglages

    page = PageReglages(services)
    qtbot.addWidget(page)
    services.prix.definir_taux(Decimal("0.86"), source="BCE", le="2026-10-01")
    info_taux = page.modeles.info_taux
    assert info_taux.text() == "Taux de la Banque centrale européenne du 01/10/2026."
    assert info_taux.ampoule.isHidden()


def test_le_cercle_tourne_dans_le_bouton_clique(app_configuree, qtbot, services, tmp_path, monkeypatch):
    """Module Script : « Lire la page » montre le cercle, sans être grisé ; les autres actions
    sont grisées ; à la fin, tout redevient cliquable."""
    from ugc_studio.ui.pages.script import PageScript

    travaux = []
    monkeypatch.setattr(taches, "lancer_avec_progres", lambda *arguments: travaux.append(arguments))
    page = PageScript(services)
    qtbot.addWidget(page)
    services.projets.creer("Sérum", tmp_path)
    atelier = page.atelier
    atelier.lire_la_page("https://boutique.example/products/serum")
    ((_travail, fin, echec, _nouvelles),) = travaux
    lire = atelier.produit.bouton_lire
    assert lire.est_occupe() and lire.isEnabled()
    assert not atelier.bouton_ecrire.isEnabled() and not atelier.bouton_accroches.isEnabled()
    echec(RuntimeError("pas de réseau"))
    assert not lire.est_occupe() and lire.isEnabled() and atelier.bouton_ecrire.isEnabled()
    assert fin is not None


def test_cercle_dans_le_bouton_du_taux_de_change(app_configuree, qtbot, services, monkeypatch):
    from ugc_studio.ui.pages.reglages import PageReglages

    travaux = []
    monkeypatch.setattr(taches, "lancer", lambda *arguments: travaux.append(arguments))
    page = PageReglages(services)
    qtbot.addWidget(page)
    page.modeles.taux_du_jour()
    ((_travail, fin, _echec),) = travaux
    assert page.modeles.bouton_bce.est_occupe() and page.modeles.bouton_bce.isEnabled()
    fin((Decimal("0.86"), "2026-10-01"))
    assert not page.modeles.bouton_bce.est_occupe()


# --- Fenêtre « Conseils » en cartes ----------------------------------------------------------------


def test_conseils_en_cartes(app_configuree, qtbot):
    """Chaque rubrique est une carte (fond et contour d'un bloc, coins arrondis), avec son titre en
    haut et ses conseils dessous ; 12 px entre deux cartes."""
    page = PAGES["voix"]
    dialogue = _montrer(qtbot, DialogueConseils(page))
    assert len(dialogue.cartes) == len(page.rubriques) >= 2
    for carte, rubrique in zip(dialogue.cartes, page.rubriques, strict=True):
        assert isinstance(carte, QFrame) and carte.property("role") == "bloc"
        (titre,) = [e for e in carte.findChildren(QLabel) if e.property("role") == "intitule"]
        assert titre.text().replace(" ", " ") == rubrique.titre
        hauts = [e.mapTo(carte, QPoint(0, 0)).y() for e in carte.findChildren(QLabel) if e is not titre]
        assert titre.mapTo(carte, QPoint(0, 0)).y() < min(hauts)  # le titre en haut, les conseils dessous
    premiere, seconde = dialogue.cartes[:2]
    assert seconde.y() - (premiere.y() + premiere.height()) == Espacements.M
    assert dialogue.conseils() == [c for rubrique in page.rubriques for c in rubrique.conseils]


# --- « Tout en majuscules » ------------------------------------------------------------------------


def test_plus_de_majuscules_dans_l_interface():
    """V3.1 : « Comme écrit », « Tout en majuscules », « Tout en minuscules » (la liste « Casse »
    écrivait « TOUT EN MAJUSCULES ») ; pareil dans les conseils et l'aide d'« Accentuer »."""
    assert list(CASSES.values()) == ["Comme écrit", "Tout en majuscules", "Tout en minuscules"]
    textes = [texte for page in PAGES.values() for rubrique in page.rubriques for texte in (rubrique.titre, *rubrique.conseils)]
    assert not [texte for texte in textes if "MAJUSCULES" in texte]


def test_accentuer_sans_majuscules(app_configuree, qtbot, services):
    from ugc_studio.ui.pages.voix.atelier import AtelierVoix

    atelier = AtelierVoix(services)
    qtbot.addWidget(atelier)
    (accentuer,) = [b for b in atelier.findChildren(Bouton) if b.text() == "Accentuer"]
    assert "en majuscules pour la voix" in accentuer.toolTip() and "MAJUSCULES" not in accentuer.toolTip()
