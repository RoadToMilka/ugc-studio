"""V2, lot 7 (§7.13) : la frise des sous-titres (composant et studio) et les préréglages (liste du
studio, « (modifié) », enregistrer, mettre à jour, revenir, fenêtre « Préréglages de sous-titres »)."""

import json

import pytest

from ugc_studio.prereglages import DEFAUT_FOURNI, modifie
from ugc_studio.sous_titres import MotAffiche, SousTitre

TEXTES = ["Mais", "ce", "sérum", "Glowzy", "a", "vraiment", "changé", "ma", "peau"]


def _mots() -> list[MotAffiche]:
    return [MotAffiche(t, t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate(TEXTES)]


def _sous_titres() -> list[SousTitre]:
    return [
        SousTitre(0.0, 1.5, ["Mais ce sérum"], 0, 3),
        SousTitre(1.5, 3.0, ["Glowzy a vraiment"], 3, 6, echelle=0.8),  # signalé (mot rapetissé)
        SousTitre(3.2, 4.4, ["changé ma peau"], 6, 9),  # un silence avant lui : pas de bord commun
    ]


@pytest.fixture
def frise(app_configuree, qtbot):
    from ugc_studio.ui.composants.frise import FriseSousTitres

    resultat = FriseSousTitres()
    qtbot.addWidget(resultat)
    resultat.resize(908, resultat.sizeHint().height())  # 892 px utiles : 5 s → 178,4 px par seconde
    resultat.show()
    resultat.toile.definir(_sous_titres(), _mots(), 5.0)
    return resultat.toile


def test_frise_place_les_blocs_et_les_mots(frise):
    assert frise.duree == 5.0 and frise.zoom == 1.0
    assert frise.x_du_temps(0.0) == pytest.approx(8.0) and frise.x_du_temps(5.0) == pytest.approx(frise.width() - 8.0)
    assert frise.temps_du_x(frise.x_du_temps(2.5)) == pytest.approx(2.5)
    rect = frise.rect_du_bloc(1)
    assert rect.left() == pytest.approx(frise.x_du_temps(1.5)) and rect.right() == pytest.approx(frise.x_du_temps(3.0))
    assert frise.bords_communs() == [0]  # 1 et 2 se touchent ; un silence sépare 2 et 3


def test_frise_clic_double_clic_et_survol(frise, qtbot):
    from PySide6.QtCore import QPoint, Qt

    temps, choisis, corrections = [], [], []
    frise.temps_demande.connect(temps.append)
    frise.sous_titre_clique.connect(lambda index, moment: choisis.append((index, round(moment, 1))))
    frise.correction_demandee.connect(corrections.append)
    milieu_blocs = round(frise.rect_du_bloc(0).center().y())
    qtbot.mouseClick(frise, Qt.MouseButton.LeftButton, pos=QPoint(round(frise.x_du_temps(2.0)), milieu_blocs))
    assert choisis == [(1, 2.0)]
    qtbot.mouseClick(frise, Qt.MouseButton.LeftButton, pos=QPoint(round(frise.x_du_temps(4.8)), milieu_blocs))
    assert temps and temps[-1] == pytest.approx(4.8, abs=0.01)  # hors d'un bloc : la lecture va à ce moment
    qtbot.mouseDClick(frise, Qt.MouseButton.LeftButton, pos=QPoint(round(frise.x_du_temps(3.5)), milieu_blocs))
    assert corrections == [2]
    frise.definir_choisi(1)
    frise.definir_temps(2.2)
    image = frise.grab().toImage()
    assert not image.isNull()


def test_glisser_le_bord_commun_de_mot_en_mot(frise):
    deplacements = []
    frise.limite_deplacee.connect(lambda index, mot: deplacements.append((index, mot)))
    verifies = []

    def verifier(index, mot):
        verifies.append((index, mot))
        return "Impossible : le sous-titre 2 ferait 4 mots, et « Mots au plus » est réglé sur 3." if mot < 3 else ""

    frise.definir_verification(verifier)
    frise.commencer_glissement(0)
    assert frise.glissement == (0, 3) and "saute de mot en mot" in frise.description_du_glissement()
    # Le pointeur va vers la droite : le bord vise la limite de mot la plus proche.
    assert frise._mot_vise(0, frise.x_de_la_limite(4) + 2) == 4
    frise.viser(4)
    assert frise.description_du_glissement() == "« Glowzy » passe au sous-titre 1."
    frise.viser(2)  # vers la gauche : refusé par la règle (raison affichée, en rouge)
    assert frise.description_du_glissement().startswith("Impossible : ") and frise._refus
    assert verifies == [(0, 4), (0, 2)]
    frise.viser(5)
    assert frise.description_du_glissement() == "« Glowzy a » passent au sous-titre 1."
    frise.finir_glissement()
    assert deplacements == [(0, 5)] and frise.glissement is None
    # Relâché à sa place de départ, ou annulé : rien ne change.
    frise.commencer_glissement(0)
    frise.finir_glissement()
    frise.commencer_glissement(0)
    frise.viser(4)
    frise.annuler_glissement()
    assert deplacements == [(0, 5)]


def test_glisser_a_la_souris(frise, qtbot):
    from PySide6.QtCore import QPoint, Qt

    deplacements = []
    frise.limite_deplacee.connect(lambda index, mot: deplacements.append((index, mot)))
    y = round(frise.rect_du_bloc(0).center().y())
    bord = round(frise.x_du_bord(0))
    qtbot.mousePress(frise, Qt.MouseButton.LeftButton, pos=QPoint(bord, y))
    assert frise.glissement == (0, 3)
    qtbot.mouseMove(frise, QPoint(round(frise.x_de_la_limite(4)), y))
    assert frise.glissement == (0, 4)
    qtbot.mouseRelease(frise, Qt.MouseButton.LeftButton, pos=QPoint(round(frise.x_de_la_limite(4)), y))
    assert deplacements == [(0, 4)]


def test_zoom_et_defilement(frise):
    ancre = frise.temps_du_x(300)
    frise.zoomer(4.0, 300)
    assert frise.zoom == 4.0 and frise.temps_du_x(300) == pytest.approx(ancre)
    assert frise.duree_visible() == pytest.approx(1.25)
    frise.definir_debut(99)
    assert frise.debut == pytest.approx(5.0 - 1.25)  # pas plus loin que la fin
    frise.definir_temps(0.5)  # la lecture sort de la partie visible : la frise la suit
    assert frise.debut <= 0.5 <= frise.debut + frise.duree_visible()
    frise.zoomer(0.01)
    assert frise.zoom == 1.0 and frise.debut == 0.0


def test_molette_sans_zoom_laisse_la_page_defiler(frise):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    def molette(modificateurs):
        evenement = QWheelEvent(
            QPointF(300, 30), QPointF(frise.mapToGlobal(QPoint(300, 30))), QPoint(0, 0), QPoint(0, 120),
            Qt.MouseButton.NoButton, modificateurs, Qt.ScrollPhase.NoScrollPhase, False,
        )
        frise.wheelEvent(evenement)
        return evenement.isAccepted()

    assert not molette(Qt.KeyboardModifier.NoModifier)  # la page défile
    assert molette(Qt.KeyboardModifier.ControlModifier) and frise.zoom > 1  # Ctrl : zoom


# --- Dans le studio ---------------------------------------------------------------------------------


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.transcription import Mot, Transcription
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.projets.creer("Sérum", tmp_path / "projets")
    services.projets.projet.transcription = Transcription(
        source=str(tmp_path / "pub.mp4"),
        audio="audio.wav",
        duree_s=6.0,
        infos={"video": True, "resolution": [1080, 1920]},
        langue="fr-FR",
        mots=[Mot(t, i * 0.5, i * 0.5 + 0.45) for i, t in enumerate(TEXTES)],
        date="2026-10-01T10:00:00+02:00",
    )
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.resize(1100, 900)
    page.show()
    page.atelier.rafraichir()
    return page.atelier


def test_frise_du_studio(atelier):
    frise = atelier.frise.toile
    assert len(frise._sous_titres) == len(atelier.sous_titres) >= 2 and not atelier.cadre_frise.isHidden()
    frise.sous_titre_clique.emit(1, atelier.sous_titres[1].debut + 0.1)
    assert atelier.tableau.currentRow() == 1 and frise._choisi == 1
    assert atelier.lecteur.temps == pytest.approx(atelier.sous_titres[1].debut + 0.1)
    atelier.choisir_sous_titre(0)  # depuis la liste : la frise suit
    assert frise._choisi == 0
    corrections = []
    atelier.corriger_demande.connect(corrections.append)
    frise.correction_demandee.emit(1)
    assert corrections == [atelier.mots[atelier.sous_titres[1].premier_mot].debut]


def test_bord_glisse_dans_le_studio(atelier, services):
    # 40 caractères au plus : seul « Mots au plus » (5) limite, un mot de plus ou de moins passe toujours.
    atelier.panneau.caracteres.setValue(40)
    frise = atelier.frise.toile
    assert 0 in frise.bords_communs()
    gauche, droite = atelier.sous_titres[0], atelier.sous_titres[1]
    candidats = range(gauche.premier_mot + 1, droite.dernier_mot)
    possibles = [mot for mot in candidats if mot != droite.premier_mot and not atelier._verifier_la_limite(0, mot)]
    refuses = [mot for mot in candidats if atelier._verifier_la_limite(0, mot)]
    assert possibles and refuses  # un mot de plus ou de moins passe ; trop de mots, non
    # Refusé : rien ne change, la raison s'affiche sous la frise.
    avant = [s.texte for s in atelier.sous_titres]
    atelier.deplacer_la_limite(0, refuses[-1])
    assert [s.texte for s in atelier.sous_titres] == avant and not any(s.ajuste for s in atelier.sous_titres)
    assert atelier.statut_frise.text().startswith("Impossible : ") and atelier.statut_frise.property("role") == "erreur"
    # Possible : le bord glissé dans la frise, les mots passent d'un sous-titre à l'autre.
    mot = possibles[0]
    frise.commencer_glissement(0)
    frise.viser(mot)
    attendu = frise.description_du_glissement()
    assert attendu.startswith("« ") and not frise._refus
    frise.finir_glissement()
    assert atelier.sous_titres[0].dernier_mot == mot and atelier.sous_titres[0].ajuste and atelier.sous_titres[1].ajuste
    assert atelier.statut_frise.text() == attendu and atelier.statut_frise.property("role") == "succes"
    assert services.projets.projet.transcription.ajustements_sous_titres  # enregistré dans le projet
    assert frise._sous_titres == atelier.sous_titres  # la frise montre le nouveau découpage


def test_corriger_les_mots_depuis_la_frise(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.transcription import Mot, Transcription
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    services.projets.creer("Sérum", tmp_path)
    services.projets.projet.transcription = Transcription(
        source="pub.wav", audio="audio.wav", duree_s=6.0, langue="fr-FR",
        mots=[Mot(t, i * 0.5, i * 0.5 + 0.45) for i, t in enumerate(TEXTES)],
    )
    fenetre.corriger_les_mots(1.5)
    assert fenetre.module_actuel() == "transcription"
    assert fenetre.page("transcription").atelier.editeur.mot_choisi == 3  # « Glowzy » commence à 1,5 s


# --- Préréglages dans le studio ----------------------------------------------------------------------


def test_liste_des_prereglages_et_modifie(atelier, services):
    panneau = atelier.panneau
    assert panneau.prereglage.currentText() == "Aucun préréglage"  # projet sans préréglage d'origine
    assert panneau.prereglage.count() == 7 and not panneau.action_mettre_a_jour.isEnabled()
    surligneur = services.prereglages.prereglages[1]
    panneau.prereglage.setCurrentIndex(panneau.prereglage.findData(surligneur.identifiant))
    panneau.prereglage.activated.emit(panneau.prereglage.currentIndex())
    reglages = services.projets.projet.sous_titres
    assert reglages.prereglage == surligneur.identifiant and reglages.texte.police == "Poppins"
    assert panneau.prereglage.currentText() == "Surligneur" and panneau.prereglage.count() == 6
    assert "appliqué" in panneau.statut_prereglage.text()
    assert atelier.panneau.texte._reference.police == "Poppins"  # « Rétablir » : les valeurs du préréglage
    # Un réglage changé : « (modifié) », et le menu ⋯ peut mettre à jour ou revenir.
    panneau.caracteres.setValue(panneau.caracteres.value() + 2)
    assert panneau.prereglage.currentText() == "Surligneur (modifié)"
    assert panneau.action_mettre_a_jour.isEnabled() and panneau.action_revenir.isEnabled()
    assert "« Surligneur »" in panneau.action_revenir.text()
    atelier.revenir_au_prereglage()
    assert panneau.prereglage.currentText() == "Surligneur"
    assert not modifie(services.projets.projet.sous_titres, surligneur)
    # La position fait partie du style : la glisser suffit à « (modifié) ».
    panneau.reglage_fin.setValue(panneau.reglage_fin.value() - 10)
    assert panneau.prereglage.currentText() == "Surligneur (modifié)"


def test_enregistrer_et_mettre_a_jour_un_prereglage(atelier, services, monkeypatch):
    panneau = atelier.panneau
    monkeypatch.setattr(atelier, "_demander_nom", lambda _titre, _nom: "Mon style")
    panneau.caracteres.setValue(30)
    panneau.enregistrer_prereglage_demande.emit()
    reglages = services.projets.projet.sous_titres
    cree = services.prereglages.prereglage(reglages.prereglage)
    assert cree is not None and cree.nom == "Mon style" and reglages.prereglage_nom == "Mon style"
    assert panneau.prereglage.currentText() == "Mon style" and not modifie(reglages, cree)
    # « Mettre à jour » : le préréglage prend le style du projet, après confirmation.
    panneau.caracteres.setValue(32)
    assert panneau.prereglage.currentText() == "Mon style (modifié)"
    monkeypatch.setattr(atelier, "_confirmer", lambda _boite, _oui: False)
    panneau.mettre_a_jour_prereglage_demande.emit()
    assert panneau.prereglage.currentText() == "Mon style (modifié)"
    monkeypatch.setattr(atelier, "_confirmer", lambda _boite, _oui: True)
    panneau.mettre_a_jour_prereglage_demande.emit()
    assert panneau.prereglage.currentText() == "Mon style"
    assert services.prereglages.prereglage(cree.identifiant).style["decoupage"]["caracteres_max"] == 32
    # Supprimé depuis la bibliothèque : le projet garde son style, la liste le dit.
    services.prereglages.supprimer(cree.identifiant)
    assert panneau.prereglage.currentText() == "Mon style (supprimé)"
    assert services.projets.projet.sous_titres.caracteres_max == 32


def test_nouveau_projet_avec_le_prereglage_par_defaut(app_configuree, qtbot, services, tmp_path):
    from ugc_studio.ui.pages.sous_titres import PageSousTitres

    services.prereglages.definir_par_defaut(DEFAUT_FOURNI)
    services.projets.creer("Nouveau", tmp_path)
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.show()
    assert services.projets.projet.sous_titres.prereglage == DEFAUT_FOURNI
    assert page.atelier.panneau.prereglage.currentText() == "Blanc contour noir"


# --- Fenêtre « Préréglages de sous-titres » ------------------------------------------------------------


def test_fenetre_des_prereglages(app_configuree, qtbot, services, tmp_path, monkeypatch):
    from ugc_studio.ui.dialogues.prereglages import DialoguePrereglages

    fenetre = DialoguePrereglages(services, None, actuel=DEFAUT_FOURNI)
    qtbot.addWidget(fenetre)
    fenetre.show()
    assert [c.prereglage.nom for c in fenetre.cartes][:2] == ["Blanc contour noir", "Surligneur"] and len(fenetre.cartes) == 6
    assert "style du projet" in fenetre.cartes[0].details.text() and "fourni" in fenetre.cartes[0].details.text()
    # ★ sur la carte du style des nouveaux projets, sans abréger son nom (« Blanc conto… » au lot 7).
    assert not any(carte.etoile for carte in fenetre.cartes)  # le service des tests n'a pas de ★
    fenetre.definir_par_defaut(DEFAUT_FOURNI)
    assert [carte.etoile is not None for carte in fenetre.cartes] == [True, False, False, False, False, False]
    assert fenetre.cartes[0].etoile.toolTip() == "Le style des nouveaux projets"
    qtbot.waitUntil(lambda: not fenetre.cartes[0].nom.est_abrege(), timeout=2000)
    # Vignettes animées : un exemple dessiné par le moteur (au milieu de « sérum », le sous-titre est là).
    vignette = fenetre.cartes[2].vignette
    vignette.definir_temps(0.1)
    vide = vignette.grab().toImage()
    vignette.definir_temps(1.0)
    pleine = vignette.grab().toImage()
    assert vignette.sous_titres and vide != pleine
    # Actions du menu ⋯ (questions remplacées).
    monkeypatch.setattr(fenetre, "_demander_nom", lambda _titre, _nom: "Karaoké fort")
    monkeypatch.setattr(fenetre, "_confirmer", lambda _titre, _question, _action: True)
    karaoke = fenetre.cartes[2].prereglage.identifiant
    fenetre.dupliquer(karaoke)
    assert len(fenetre.cartes) == 7 and fenetre.cartes[3].prereglage.nom == "Karaoké (copie)"
    fenetre.renommer(fenetre.cartes[3].prereglage.identifiant)
    assert fenetre.cartes[3].prereglage.nom == "Karaoké fort" and "Renommé" in fenetre.statut.text()
    fenetre.definir_par_defaut(fenetre.cartes[3].prereglage.identifiant)
    assert services.prereglages.par_defaut == fenetre.cartes[3].prereglage.identifiant
    fichier = tmp_path / "export.json"
    monkeypatch.setattr(fenetre, "_fichier_d_export", lambda _nom: fichier)
    fenetre.exporter(karaoke)
    assert json.loads(fichier.read_text(encoding="utf-8"))["prereglages"][0]["nom"] == "Karaoké"
    monkeypatch.setattr(fenetre, "_fichier_a_importer", lambda: fichier)
    fenetre.importer()
    assert fenetre.cartes[-1].prereglage.nom == "Karaoké (2)" and "Importé" in fenetre.statut.text()
    fenetre.supprimer(karaoke)
    assert services.prereglages.prereglage(karaoke) is None
    fenetre.retablir_fournis()
    assert services.prereglages.prereglage(karaoke) is not None
    fenetre.appliquer(karaoke)
    assert fenetre.prereglage_choisi == karaoke and not fenetre.isVisible()  # fenêtre fermée : la page l'applique


def test_fenetre_sans_projet_et_police_absente(app_configuree, qtbot, services, tmp_path, monkeypatch):
    from ugc_studio.ui.dialogues.prereglages import DialoguePrereglages

    fichier = tmp_path / "ailleurs.json"
    fichier.write_text(
        json.dumps({"prereglages": [{"nom": "D'un autre ordinateur", "style": {"texte": {"police": "Police Disparue"}}}]}),
        encoding="utf-8",
    )
    fenetre = DialoguePrereglages(services, None, projet_ouvert=False)
    qtbot.addWidget(fenetre)
    assert not fenetre.cartes[0].bouton_appliquer.isEnabled()
    monkeypatch.setattr(fenetre, "_fichier_a_importer", lambda: fichier)
    fenetre.importer()
    assert "Police absente" in fenetre.statut.text() and "Inter la remplace" in fenetre.statut.text()
    assert "absente" in fenetre.cartes[-1].details.text()
    fichier.write_text("pas un préréglage", encoding="utf-8")
    fenetre.importer()
    assert fenetre.statut.property("role") == "erreur"
