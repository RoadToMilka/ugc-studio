"""V3.2, lot 3 (§9.6) : toutes les fenêtres comme une page. Le fond de l'app, le contenu dans un bloc à
16 px des bords, les boutons sous le bloc ; questions, demandes de nom et « Autre couleur » comprises
(jusqu'à la 3.1.2 : fenêtres toutes faites de Qt, sur le fond gris des menus)."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QLineEdit

from ugc_studio.conseils_des_pages import PAGES
from ugc_studio.ui.composants.bouton import Bouton
from ugc_studio.ui.composants.conseils import DialogueConseils
from ugc_studio.ui.dialogues import messages
from ugc_studio.ui.dialogues.cle_api import DialogueCle
from ugc_studio.ui.dialogues.couleur import DialogueCouleur
from ugc_studio.ui.dialogues.messages import DialogueMessage
from ugc_studio.ui.dialogues.projet import DialogueNouveauProjet
from ugc_studio.ui.theme import Couleurs, Dimensions, Espacements, Hauteurs

MARGE = Dimensions.ESPACE_BLOCS


def _montrer(qtbot, dialogue):
    qtbot.addWidget(dialogue)
    dialogue.show()
    qtbot.waitExposed(dialogue)
    return dialogue


def _couleur(dialogue, x: int, y: int) -> str:
    """Couleur du point (x, y) de la fenêtre, sur sa capture."""
    image = dialogue.grab().toImage()
    echelle = image.width() / dialogue.width()
    return image.pixelColor(round(x * echelle), round(y * echelle)).name().upper()


def _boutons_du_bas(dialogue) -> list[Bouton]:
    """Les boutons posés sur la fenêtre elle-même (et non dans le bloc) : ceux du bas."""
    return [b for b in dialogue.findChildren(Bouton) if b.parentWidget() is dialogue and b.isVisible()]


def _sans_insecables(texte: str) -> str:
    return texte.replace(" ", " ")


def _verifier_comme_une_page(dialogue) -> None:
    """Fond de l'app autour, bloc à 16 px des bords (fond des blocs), boutons du bas sous le bloc,
    16 px plus bas, le dernier à 16 px du bord droit."""
    assert _couleur(dialogue, MARGE // 2, MARGE // 2) == Couleurs.FOND.upper()
    cadre = dialogue.cadre
    assert cadre.property("role") == "bloc" and (cadre.x(), cadre.y()) == (MARGE, MARGE)
    assert cadre.width() == dialogue.width() - 2 * MARGE
    assert _couleur(dialogue, MARGE + Espacements.S, cadre.y() + cadre.height() // 2) == Couleurs.SURFACE.upper()
    boutons = _boutons_du_bas(dialogue)
    assert boutons
    for element in boutons:
        assert element.y() >= cadre.geometry().bottom() + 1 + MARGE
    assert max(b.geometry().right() for b in boutons) + 1 + MARGE == dialogue.width()


# --- Fenêtres de l'app --------------------------------------------------------------------------------


def test_nouveau_projet_comme_une_page(app_configuree, qtbot, services):
    dialogue = _montrer(qtbot, DialogueNouveauProjet(services.projets))
    _verifier_comme_une_page(dialogue)
    annuler, creer = _boutons_du_bas(dialogue)
    assert annuler.text() == "Annuler" and creer is dialogue.bouton_creer
    assert annuler.geometry().right() + 1 + Espacements.S == creer.x()  # 8 px entre les boutons


def test_ajout_d_une_cle_comme_une_page(app_configuree, qtbot, services):
    dialogue = _montrer(qtbot, DialogueCle(services.connexions))
    _verifier_comme_une_page(dialogue)
    assert dialogue.bouton_valider in _boutons_du_bas(dialogue)


def test_conseils_sur_le_fond_de_l_app(app_configuree, qtbot):
    """La fenêtre des conseils : le fond de l'app, ses cartes avec le fond des blocs, 16 px du bord."""
    dialogue = _montrer(qtbot, DialogueConseils(PAGES["voix"]))
    assert _couleur(dialogue, MARGE // 2, MARGE // 2) == Couleurs.FOND.upper()
    carte = dialogue.cartes[0]
    assert carte.mapTo(dialogue, carte.rect().topLeft()).x() == MARGE
    assert carte.property("role") == "bloc"


# --- Questions, avertissements, demandes de texte ---------------------------------------------------


def test_question_comme_une_page(app_configuree, qtbot):
    dialogue = _montrer(
        qtbot,
        DialogueMessage(
            None,
            "Supprimer la prise",
            "Supprimer « Prise 3 » ?",
            "Le fichier audio sera effacé du dossier du projet.",
            action="Supprimer",
            icone_action="trash",
            annuler="Annuler",
        ),
    )
    _verifier_comme_une_page(dialogue)
    # Le titre en haut du bloc, la question, puis la précision en gris.
    assert dialogue.titre.text() == "Supprimer la prise" and dialogue.titre.property("role") == "titre-bloc"
    assert _sans_insecables(dialogue.texte.text()) == "Supprimer « Prise 3 » ?"
    assert dialogue.precision.property("role") == "secondaire"
    # « Annuler », puis l'action (le bouton principal), 8 px entre eux.
    assert _boutons_du_bas(dialogue) == [dialogue.bouton_annuler, dialogue.bouton_action]
    assert dialogue.bouton_action.variante == "principal" and dialogue.bouton_action.text() == "Supprimer"
    assert dialogue.bouton_annuler.geometry().right() + 1 + Espacements.S == dialogue.bouton_action.x()
    # Entrée choisit le bouton sans risque.
    assert dialogue.focusWidget() is dialogue.bouton_annuler
    qtbot.keyClick(dialogue.bouton_annuler, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: not dialogue.isVisible(), timeout=2000)
    assert dialogue.choix is None


def test_fenetre_d_erreur(app_configuree, qtbot):
    dialogue = _montrer(
        qtbot,
        DialogueMessage(
            None,
            "Erreur inattendue",
            "Une erreur inattendue s'est produite.",
            autre="Ouvrir le journal",
            erreur=True,
        ),
    )
    _verifier_comme_une_page(dialogue)
    # Icône rouge devant le titre, 8 px avant lui ; « Ouvrir le journal » seul à gauche, « OK » à droite.
    assert dialogue.pictogramme.geometry().right() + 1 + Dimensions.ECART_INFO == dialogue.titre.x()
    assert dialogue.bouton_autre.x() == MARGE and dialogue.bouton_annuler is None
    assert dialogue.bouton_action.text() == "OK" and dialogue.focusWidget() is dialogue.bouton_action


def _repondre(action) -> list:
    """Dès que la prochaine fenêtre s'ouvre : `action(fenêtre)`. Renvoie ce que l'action a noté."""
    notes: list = []

    def repondre() -> None:
        dialogue = QApplication.activeModalWidget()
        if dialogue is None:  # pas encore ouverte : on réessaie un peu plus tard
            QTimer.singleShot(10, repondre)
            return
        try:
            notes.append(action(dialogue))
        finally:
            if dialogue.isVisible():  # l'action n'a pas fermé la fenêtre : le test ne doit pas rester bloqué
                dialogue.reject()

    QTimer.singleShot(0, repondre)
    return notes


def test_confirmer_et_prevenir(app_configuree, qtbot):
    """confirmer() : True seulement avec le bouton de l'action ; prevenir() : True avec le second bouton."""
    _repondre(lambda d: d.bouton_action.click())
    assert messages.confirmer(None, "Supprimer la prise", "Supprimer « Prise 3 » ?", action="Supprimer")
    _repondre(lambda d: d.bouton_annuler.click())
    assert not messages.confirmer(None, "Supprimer la prise", "Supprimer « Prise 3 » ?", action="Supprimer")
    _repondre(lambda d: d.reject())  # touche Échap, croix de la fenêtre
    assert not messages.confirmer(None, "Supprimer la prise", "Supprimer « Prise 3 » ?", action="Supprimer")
    _repondre(lambda d: d.bouton_autre.click())
    assert messages.prevenir(None, "Erreur inattendue", "Une erreur.", erreur=True, autre="Ouvrir le journal")
    _repondre(lambda d: d.bouton_action.click())
    assert not messages.prevenir(None, "Erreur inattendue", "Une erreur.", erreur=True, autre="Ouvrir le journal")


def test_demander_texte(app_configuree, qtbot):
    """Le nom proposé est sélectionné (il se remplace en tapant) ; Entrée valide ; « Annuler » : None."""

    def taper(dialogue):
        propose = (dialogue.champ.text(), dialogue.champ.selectedText())
        dialogue.champ.setText("Clé du bureau")
        qtbot.keyClick(dialogue.champ, Qt.Key.Key_Return)
        return propose

    notes = _repondre(taper)
    nom = messages.demander_texte(None, "Renommer la clé", "Nouveau nom", "Google perso", action="Renommer")
    assert nom == "Clé du bureau" and notes == [("Google perso", "Google perso")]
    _repondre(lambda d: d.bouton_annuler.click())
    assert messages.demander_texte(None, "Renommer la clé", "Nouveau nom", "Google perso") is None


def test_fenetre_de_texte_comme_une_page(app_configuree, qtbot):
    dialogue = _montrer(
        qtbot, DialogueMessage(None, "Renommer la clé", action="Renommer", annuler="Annuler", champ=("Nouveau nom", "x"))
    )
    _verifier_comme_une_page(dialogue)
    assert isinstance(dialogue.champ, QLineEdit) and dialogue.champ.height() == Hauteurs.CONTROLE


# --- « Autre couleur » ---------------------------------------------------------------------------------


def test_autre_couleur_comme_une_page(app_configuree, qtbot):
    """Le sélecteur de Qt est posé dans le bloc (ce n'est plus une fenêtre à part), avec le fond du
    bloc ; « Annuler » et « Choisir cette couleur » sous le bloc."""
    dialogue = _montrer(qtbot, DialogueCouleur(QColor("#FFD43B")))
    _verifier_comme_une_page(dialogue)
    selecteur = dialogue.selecteur
    assert not selecteur.isWindow() and selecteur.parentWidget() is dialogue.cadre and selecteur.isVisible()
    assert _boutons_du_bas(dialogue) == [dialogue.bouton_annuler, dialogue.bouton_choisir]
    # Autour de ses éléments, le sélecteur laisse voir le fond du bloc (et non le fond de l'app, que la
    # feuille de style donne aux fenêtres).
    image = dialogue.grab().toImage()
    echelle = image.width() / dialogue.width()
    zone = selecteur.geometry().translated(dialogue.cadre.pos())
    points = [(x, y) for x in range(zone.left(), zone.right(), 4) for y in range(zone.top(), zone.bottom(), 4)]
    surface = sum(
        image.pixelColor(round(x * echelle), round(y * echelle)).name().upper() == Couleurs.SURFACE.upper()
        for x, y in points
    )
    assert surface / len(points) > 0.2
    selecteur.setCurrentColor(QColor("#22C55E"))
    dialogue.bouton_choisir.click()
    assert not dialogue.isVisible() and dialogue.couleur().name().upper() == "#22C55E"


def test_autre_couleur_echap_ferme_la_fenetre(app_configuree, qtbot):
    """Échap dans un champ du sélecteur ferme toute la fenêtre (et ne cache pas le sélecteur seul)."""
    dialogue = _montrer(qtbot, DialogueCouleur(QColor("#FFD43B")))
    champ = dialogue.selecteur.findChildren(QLineEdit)[0]
    qtbot.keyClick(champ, Qt.Key.Key_Escape)
    assert not dialogue.isVisible() and dialogue.result() == 0
