"""V3.2, lot 2 : bulles d'aide, menus, messages qui s'effacent, barres de lecture, Réglages."""

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QAction, QContextMenuEvent, QHelpEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ugc_studio.ui.composants.bulle import bulle, bulle_visible, cacher_bulle, texte_de_la_bulle
from ugc_studio.ui.composants.elements import (
    Info,
    afficher_message,
    bouton,
    glissiere,
    libelle,
)
from ugc_studio.ui.composants.menu import Menu, position_du_menu
from ugc_studio.ui.theme import Couleurs, Dimensions, Durees, Espacements


def _montrer(qtbot, element, largeur: int = 400, hauteur: int = 200):
    qtbot.addWidget(element)
    element.resize(largeur, hauteur)
    element.show()
    qtbot.waitExposed(element)
    return element


def _survol(element, point: QPoint | None = None) -> bool:
    """Le temps d'arrêt de la souris sur `element` : Qt lui envoie l'événement « infobulle »."""
    point = point or QPoint(element.width() // 2, element.height() // 2)
    return QApplication.sendEvent(element, QHelpEvent(QEvent.Type.ToolTip, point, element.mapToGlobal(point)))


# --- Bulles d'aide ---------------------------------------------------------------------------------


def test_bulle_de_l_app_a_la_place_de_celle_de_qt(app_configuree, qtbot):
    """Au survol d'un élément qui a une infobulle : la bulle de l'app (coins arrondis, fond des blocs,
    16 px autour du texte), coupée en lignes d'environ 60 caractères ; elle se ferme quand la souris
    s'en va ou au clic."""
    fenetre = QWidget()
    disposition = QVBoxLayout(fenetre)
    tester = bouton("Tester")
    texte = "Tester la clé auprès de Google : la liste des modèles accessibles est mise à jour au passage."
    tester.setToolTip(texte)
    disposition.addWidget(tester)
    _montrer(qtbot, fenetre)
    assert _survol(tester)
    assert bulle_visible() and texte_de_la_bulle().replace("\n", " ") == texte
    assert max(len(ligne) for ligne in texte_de_la_bulle().split("\n")) <= Dimensions.BULLE_CARACTERES
    la_bulle = bulle()
    assert (la_bulle.etiquette.x(), la_bulle.etiquette.y()) == (Espacements.L, Espacements.L)
    assert la_bulle.width() - la_bulle.etiquette.geometry().right() - 1 == Espacements.L
    image = la_bulle.grab().toImage()
    echelle = image.width() / la_bulle.width()
    assert image.pixelColor(0, 0).alpha() == 0  # coin arrondi : transparent autour
    assert image.pixelColor(round(Espacements.XS * echelle), image.height() // 2).name().upper() == Couleurs.SURFACE.upper()
    QApplication.sendEvent(tester, QEvent(QEvent.Type.Leave))
    assert not bulle_visible()
    assert _survol(tester) and bulle_visible()
    qtbot.mouseClick(tester, Qt.MouseButton.LeftButton)
    assert not bulle_visible()


def test_sans_infobulle_la_bulle_vient_du_parent(app_configuree, qtbot):
    """Comme avec Qt : un élément sans infobulle laisse la place à celle de son parent."""
    parent = QWidget()
    parent.setToolTip("Le bloc entier")
    disposition = QVBoxLayout(parent)
    enfant = libelle("Sans infobulle")
    disposition.addWidget(enfant)
    _montrer(qtbot, parent)
    _survol(enfant)
    assert bulle_visible() and texte_de_la_bulle() == "Le bloc entier"
    cacher_bulle()


def test_bulles_des_menus_et_des_listes(app_configuree, qtbot):
    """Un choix de menu ou une case d'une liste qui a son infobulle : la bulle de l'app aussi."""
    fenetre = QWidget()
    _montrer(qtbot, fenetre)
    menu = Menu(fenetre)
    menu.setToolTipsVisible(True)
    action = QAction("Garder comme exemple", menu)
    action.setToolTip("Le modèle s'en inspirera pour les prochains scripts")
    menu.addAction(action)
    menu.addAction("Dupliquer")
    menu.popup(fenetre.mapToGlobal(QPoint(0, 0)))
    qtbot.waitExposed(menu)
    _survol(menu, menu.actionGeometry(action).center())
    assert bulle_visible() and texte_de_la_bulle() == "Le modèle s'en inspirera pour les prochains scripts"
    cacher_bulle()
    _survol(menu, menu.actionGeometry(menu.actions()[1]).center())  # « Dupliquer » : pas de bulle
    assert not bulle_visible()
    menu.hide()

    liste = QListWidget()
    element = QListWidgetItem("Kore")
    element.setToolTip("Ferme, féminine")
    liste.addItem(element)
    _montrer(qtbot, liste)
    _survol(liste.viewport(), liste.visualItemRect(element).center())
    assert bulle_visible() and texte_de_la_bulle() == "Ferme, féminine"
    cacher_bulle()


# --- Menus -----------------------------------------------------------------------------------------


def test_menu_de_l_app(app_configuree, qtbot):
    """Coins arrondis lissés (fenêtre transparente autour, sans l'ombre carrée de Windows), fond des
    listes ; un sous-menu est aussi un menu de l'app."""
    fenetre = _montrer(qtbot, QWidget())
    menu = Menu(fenetre)
    assert menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint
    menu.addAction("Dupliquer")
    sous_menu = menu.addMenu("Rires")
    assert isinstance(sous_menu, Menu) and sous_menu.menuAction() in menu.actions()
    menu.popup(fenetre.mapToGlobal(QPoint(0, 0)))
    qtbot.waitExposed(menu)
    image = menu.grab().toImage()
    echelle = image.width() / menu.width()
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(round(Espacements.XS * echelle), image.height() // 2).name().upper() == Couleurs.SURFACE_ELEVEE.upper()
    menu.hide()


def test_menu_8_px_sous_son_bouton(app_configuree, qtbot):
    """Comme une liste déroulante : 8 px sous le bouton ; au-dessus s'il manque de la place en bas."""
    fenetre = QWidget()
    plus = bouton("", variante="icone", nom_icone="ellipsis")
    plus.setParent(fenetre)
    _montrer(qtbot, fenetre)
    menu = Menu(plus)
    for numero in range(3):
        menu.addAction(f"Choix {numero}")
    position = position_du_menu(plus, menu)
    bas_du_bouton = plus.mapToGlobal(QPoint(0, plus.height())).y()
    assert position == QPoint(plus.mapToGlobal(QPoint(0, 0)).x(), bas_du_bouton + Dimensions.ECART_LISTE)
    ecran = plus.screen().availableGeometry()
    fenetre.move(fenetre.x(), ecran.bottom() - fenetre.height() + 1)  # le bas de la fenêtre au bas de l'écran
    plus.move(0, fenetre.height() - plus.height())
    qtbot.waitUntil(lambda: plus.mapToGlobal(QPoint(0, plus.height())).y() >= ecran.bottom() - 1, timeout=2000)
    position = position_du_menu(plus, menu)
    assert position.y() + menu.sizeHint().height() == plus.mapToGlobal(QPoint(0, 0)).y() - Dimensions.ECART_LISTE


def test_clic_droit_dans_un_champ(app_configuree, qtbot):
    """Le menu du clic droit d'un champ de texte (Copier, Coller…) est un menu de l'app."""
    champ = QLineEdit("Sérum Glowzy")
    _montrer(qtbot, champ)
    centre = QPoint(champ.width() // 2, champ.height() // 2)
    QApplication.sendEvent(champ, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, centre, champ.mapToGlobal(centre)))
    menus = [m for m in QApplication.topLevelWidgets() if isinstance(m, Menu) and m.isVisible()]
    assert len(menus) == 1
    # Qt souligne une lettre de chaque choix avec « & » (« Co&pier » en français) : on l'enlève.
    textes = [a.text().replace("&", "") for a in menus[0].actions()]
    assert any("Copier" in t or "Copy" in t for t in textes), textes
    menus[0].close()


# --- Messages qui s'effacent -----------------------------------------------------------------------


def test_message_vert_ou_rouge_efface_apres_le_delai(app_configuree, qtbot, monkeypatch):
    """Vert, rouge ou orange : effacé après Durees.MESSAGE_MS (8 s), le même délai partout ; un
    message gris (travail en cours) reste."""
    assert Durees.MESSAGE_MS == 8000
    monkeypatch.setattr(Durees, "MESSAGE_MS", 50)
    etiquette = libelle("")
    _montrer(qtbot, etiquette)
    afficher_message(etiquette, "Brief enregistré.", "succes")
    assert etiquette.isVisible() and etiquette.text() == "Brief enregistré." and etiquette.property("role") == "succes"
    qtbot.waitUntil(lambda: etiquette.text() == "" and not etiquette.isVisible(), timeout=2000)
    afficher_message(etiquette, "Transcription en cours…", "secondaire")
    qtbot.wait(150)
    assert etiquette.text() == "Transcription en cours…"
    afficher_message(etiquette, "Lecture impossible", "erreur")
    afficher_message(etiquette, "Lecture en cours…", "secondaire")  # le message suivant arrête l'effacement
    qtbot.wait(150)
    assert etiquette.text() == "Lecture en cours…"
    garde = libelle("")
    _montrer(qtbot, garde)
    afficher_message(garde, "Voix créée.", "succes", cacher_vide=False)
    qtbot.waitUntil(lambda: garde.text() == "", timeout=2000)
    assert garde.isVisible()  # la ligne garde sa place


def test_erreur_d_une_info_effacee(app_configuree, qtbot, monkeypatch):
    """Une erreur écrite à la place d'une info s'efface aussi : ce qui était affiché revient."""
    monkeypatch.setattr(Durees, "MESSAGE_MS", 50)
    etat = Info()
    _montrer(qtbot, etat)
    etat.afficher_etat("Taux de la Banque centrale européenne du 01/10/2026.")
    etat.afficher_etat("Taux non récupéré : pas de réseau", erreur=True)
    assert etat.etiquette.property("role") == "legende-erreur"
    qtbot.waitUntil(lambda: etat.text() == "Taux de la Banque centrale européenne du 01/10/2026.", timeout=2000)
    assert etat.etiquette.property("role") == "legende"


def test_messages_des_modules(app_configuree, qtbot, services, tmp_path, monkeypatch):
    """Dans un module : le message vert d'une action s'efface après le délai."""
    from ugc_studio.ui.pages.script import PageScript

    monkeypatch.setattr(Durees, "MESSAGE_MS", 50)
    page = PageScript(services)
    qtbot.addWidget(page)
    services.projets.creer("Sérum", tmp_path)
    atelier = page.atelier
    atelier._afficher("Brief « Sérum » chargé.", "succes")
    assert atelier.statut.text() == "Brief « Sérum » chargé."
    qtbot.waitUntil(lambda: atelier.statut.text() == "", timeout=2000)


# --- Barres de lecture -----------------------------------------------------------------------------


def test_clic_n_importe_ou_sur_la_barre(app_configuree, qtbot):
    """Un clic sur la barre y place la lecture tout de suite (`sliderMoved`, que les lecteurs
    écoutent), puis on peut glisser ; la barre n'est plus « saisie » une fois la souris relâchée."""
    barre = glissiere()
    barre.setRange(0, 10_000)
    _montrer(qtbot, barre, 400, 40)
    moments = []
    barre.sliderMoved.connect(moments.append)
    qtbot.mouseClick(barre, Qt.MouseButton.LeftButton, pos=QPoint(round(barre.width() * 0.75), barre.height() // 2))
    assert moments and abs(moments[-1] - 7_500) <= 300
    assert abs(barre.value() - 7_500) <= 300 and not barre.isSliderDown()
    qtbot.mouseClick(barre, Qt.MouseButton.LeftButton, pos=QPoint(round(barre.width() * 0.25), barre.height() // 2))
    assert abs(moments[-1] - 2_500) <= 300


# --- Réglages --------------------------------------------------------------------------------------


def test_voyant_au_debut_du_nom_de_la_cle(app_configuree, qtbot, services):
    """Connexions API : le voyant au début du nom (« ● Google perso »), et les lignes dessous
    commencent au même bord gauche que lui."""
    from ugc_studio.ui.pages.reglages import PageReglages

    page = PageReglages(services)
    _montrer(qtbot, page, 1000, 600)
    connexion = services.connexions.ajouter("google", "Perso", "AIza" + "x" * 35)
    services.connexions.enregistrer_test(connexion.identifiant, True, "Clé valide", ["gemini-3.8-flash-tts"])
    (ligne,) = page.connexions.lignes()
    qtbot.waitUntil(lambda: ligne.isVisible(), timeout=2000)
    voyant, nom, etat = ligne.voyant, ligne.nom, ligne.etat
    gauche = voyant.mapTo(ligne, QPoint(0, 0)).x()
    assert gauche == etat.mapTo(ligne, QPoint(0, 0)).x() == 0  # recollé à gauche
    assert nom.mapTo(ligne, QPoint(0, 0)).x() - (gauche + voyant.width()) == Espacements.S
    centre_voyant = voyant.mapTo(ligne, QPoint(0, voyant.height() // 2)).y()
    centre_nom = nom.mapTo(ligne, QPoint(0, nom.height() // 2)).y()
    assert abs(centre_voyant - centre_nom) <= 1


def test_espace_sous_le_nom_d_un_modele(app_configuree, qtbot, services):
    """Modèles et prix : 4 px entre le nom d'un modèle et sa description (0 avant)."""
    from ugc_studio.ui.pages.reglages import PageReglages

    page = PageReglages(services)
    qtbot.addWidget(page)
    grille = page.modeles._grille
    noms = [grille.itemAtPosition(rang, 0).layout() for rang in range(grille.rowCount()) if grille.itemAtPosition(rang, 0) is not None]
    noms = [nom for nom in noms if nom is not None]
    assert noms and all(nom.spacing() == Espacements.XS for nom in noms)
