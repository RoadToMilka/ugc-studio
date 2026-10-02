"""V3.1, lot 3 : boutons et aides. Un cercle tourne dans le bouton pendant un travail ; les phrases
d'aide passent dans une icône « i » (sauf les indispensables) ; « Rétablir » de « Réorganiser à la
main » devient une icône ; la fenêtre « Conseils » montre ses rubriques en cartes ; plus de « TOUT EN
MAJUSCULES » dans l'interface."""

from decimal import Decimal

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QPushButton, QToolTip

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
    intitule,
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


def _juste_apres(texte, aide) -> bool:
    """L'icône est 4 px après le texte, centrée sur sa hauteur (à 1 px près)."""
    racine = aide.window()
    droite_du_texte = texte.mapTo(racine, QPoint(texte.width(), 0)).x()
    centre_du_texte = texte.mapTo(racine, QPoint(0, texte.height() // 2)).y()
    gauche_de_l_icone = aide.mapTo(racine, QPoint(0, 0)).x()
    centre_de_l_icone = aide.mapTo(racine, QPoint(0, aide.height() // 2)).y()
    return gauche_de_l_icone - droite_du_texte == Dimensions.ECART_INFO and abs(centre_de_l_icone - centre_du_texte) <= 1


def test_icone_i_juste_apres_le_texte_qu_elle_explique(app_configuree, qtbot):
    """Après le titre d'un bloc, le nom d'un champ, un petit titre, le titre d'une section repliable
    ou d'une fenêtre ; sans aide, rien ne change."""
    cadre, _d = bloc("Frise", aide="Clic : aller à ce moment.")
    _montrer(qtbot, cadre)
    assert cadre.titre.text() == "Frise" and _juste_apres(cadre.titre, cadre.aide)
    sans_aide, _d = bloc("Exporter")
    assert sans_aide.aide is None and sans_aide.findChildren(BoutonInfo) == []

    champ = ChampNomme("Avance de l'allumage", QLineEdit(), aide="Si les mots s'allument un peu tard.")
    _montrer(qtbot, champ)
    assert _juste_apres(champ.nom, champ.aide)

    titre = intitule("Réorganiser à la main", "Choisis un sous-titre dans la liste.")
    _montrer(qtbot, titre)
    assert _juste_apres(titre.etiquette, titre.aide)

    section = SectionRepliable("Sous-titre entier", True, aide="Les animations ne changent pas les temps.")
    _montrer(qtbot, section)
    assert section.aide.mapTo(section, QPoint(0, 0)).x() - section.titre.width() == Dimensions.ECART_INFO

    from PySide6.QtWidgets import QDialog

    fenetre = QDialog()
    entete = entete_de_fenetre("Variantes A/B", "variantes", aide="Génère plusieurs versions du même script.")
    fenetre.setLayout(entete)
    fenetre.resize(Dimensions.DIALOGUE_LARGEUR, Hauteurs.CONTROLE)
    _montrer(qtbot, fenetre)
    assert _juste_apres(entete.titre, entete.aide)
    assert entete.conseils.mapTo(fenetre, QPoint(entete.conseils.width(), 0)).x() == fenetre.width()  # Conseils au bout


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
    assert sous_titres.cadre_export.aide.text().startswith("Vidéo avec sous-titres : ta vidéo")
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
        assert titre.y() < min(e.y() for e in carte.findChildren(QLabel) if e is not titre)  # le titre en haut
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
