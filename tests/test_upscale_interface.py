"""Module Upscale vidéo (V4, lot 3) : la page, le préréglage, la file de vidéos avec un faux Topaz."""

import subprocess
import sys
from pathlib import Path

import pytest

from ugc_studio.exports.ffmpeg import programme_ffmpeg
from ugc_studio.topaz import faux
from ugc_studio.topaz.commande import comprendre
from ugc_studio.topaz.installation import CONNEXION, Topaz
from ugc_studio.ui.dialogues import messages
from ugc_studio.ui.pages.upscale import AUTRE, AUTRE_DOSSIER, PREF_DOSSIERS_TOPAZ, PageUpscale
from ugc_studio.ui.pages.upscale.prereglage import DialoguePrereglage
from ugc_studio.ui.theme import Dimensions

from test_topaz import COMMANDE

FFMPEG = programme_ffmpeg()
avec_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")


def _video(dossier: Path, nom: str, taille: str = "606x1080") -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    subprocess.run(
        [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={taille}:rate=30",
         "-t", "0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(chemin)],
        check=True,
    )
    return chemin


def _faux_topaz(tmp_path) -> Topaz:
    modeles = tmp_path / "models"
    modeles.mkdir(exist_ok=True)
    (modeles / CONNEXION).write_bytes(b"")
    (modeles / "prob-4.json").write_text("{}", encoding="utf-8")
    return Topaz(tmp_path, (sys.executable, str(Path(faux.__file__))), "7.1.1", modeles, modeles)


def _page(qtbot, services) -> PageUpscale:
    page = PageUpscale(services)
    qtbot.addWidget(page)
    page.resize(Dimensions.FENETRE_LARGEUR, Dimensions.FENETRE_HAUTEUR)
    page.show()
    return page


def test_sans_topaz_ni_prereglage(app_configuree, qtbot, services, tmp_path):
    page = _page(qtbot, services)
    page.definir_les_dossiers({"installation": tmp_path / "pas-de-topaz", "modeles": None, "telecharges": None})
    assert page.etat_topaz.text().startswith("Topaz Video AI introuvable dans")
    assert page.resume_prereglage.text().startswith("Aucun préréglage")
    assert not page.prereglage.isVisible() and not page.bouton_lancer.isEnabled()
    assert page.zone_depot.isVisible() and not page.tableau.isVisible()


def test_topaz_trouve_dans_le_dossier_choisi(app_configuree, qtbot, services, tmp_path):
    installation = tmp_path / "Topaz Video AI"
    installation.mkdir()
    (installation / "ffmpeg.exe").write_bytes(b"")
    topaz = _faux_topaz(tmp_path)
    page = _page(qtbot, services)
    page.definir_les_dossiers({"installation": installation, "modeles": topaz.modeles, "telecharges": topaz.donnees})
    assert page.etat_topaz.text() == "Topaz Video AI : prêt" and not page.problemes_topaz.isVisible()
    assert services.preferences.lire(PREF_DOSSIERS_TOPAZ)["installation"] == str(installation)
    (topaz.modeles / CONNEXION).unlink()
    page.chercher_topaz()
    assert page.etat_topaz.text() == "Topaz Video AI : à vérifier"
    assert page.problemes_topaz.text() == "Topaz ne semble pas connecté : ouvre Topaz Video AI et connecte-toi une fois."


def test_nouveau_prereglage(app_configuree, qtbot, services, monkeypatch):
    dialogue = DialoguePrereglage()
    qtbot.addWidget(dialogue)
    assert not dialogue.bouton_creer.isEnabled()
    dialogue.commande.setPlainText("ffmpeg -i a.mp4 -c:v libx264 b.mp4")
    assert dialogue.compris.text().startswith("Ce n'est pas une commande d'export de Topaz Video AI")
    dialogue.commande.setPlainText(COMMANDE)
    assert dialogue.nom.text() == "Proteus" and dialogue.bouton_creer.isEnabled()
    assert "Encodage : H.264 (carte NVIDIA), 24 Mb/s constant, profil high" in dialogue.compris.text()
    dialogue.nom.setText("Proteus 1080p")
    dialogue._creer()
    assert dialogue.prereglage.nom == "Proteus 1080p" and dialogue.prereglage.modele == "prob-4"
    page = _page(qtbot, services)
    page.ajouter_le_prereglage(dialogue.prereglage)
    assert page.prereglage.currentText() == "Proteus 1080p" and page.prereglage.isVisible()
    assert page.resume_prereglage.text().splitlines()[0] == "Modèle : Proteus (prob-4), réglages estimés par Topaz sur chaque vidéo (mode automatique)"
    autre = _page(qtbot, services)  # retenu
    assert autre.prereglage.currentText() == "Proteus 1080p"
    monkeypatch.setattr(messages, "confirmer", lambda *_args, **_kwargs: True)
    autre.supprimer_prereglage()
    assert autre.prereglage_choisi() is None and not autre.prereglage.isVisible()


@avec_ffmpeg
def test_file_de_videos_avec_le_faux_topaz(app_configuree, qtbot, services, tmp_path):
    rushs = tmp_path / "Rushs"
    verticale = _video(rushs, "RawBox01.mp4")
    horizontale = _video(rushs, "Paysage.mp4", "320x180")
    page = _page(qtbot, services)
    page.definir_topaz(_faux_topaz(tmp_path))
    page.ajouter_le_prereglage(comprendre(COMMANDE))
    page.ajouter([verticale, horizontale, verticale])  # la même vidéo n'est ajoutée qu'une fois
    qtbot.waitUntil(lambda: not page.occupe, timeout=20_000)
    lignes = [[page.tableau.item(rang, colonne).text() for colonne in (0, 1, 2, 4)] for rang in range(page.tableau.rowCount())]
    assert lignes == [
        ["RawBox01.mp4", "606 × 1080", "1080 × 1924", "en attente : RawBox01 (upscale).mp4"],  # son futur nom (4.1.0)
        ["Paysage.mp4", "320 × 180", "1920 × 1080", "en attente : Paysage (upscale).mp4"],
    ]
    page.resolution.setCurrentIndex(page.resolution.findData(AUTRE))
    assert page.champ_petit_cote.isVisible()
    page.petit_cote.setValue(720)
    assert page.tableau.item(0, 2).text() == "720 × 1284"
    page.resolution.setCurrentIndex(page.resolution.findData(1080))
    assert page.lancer()
    qtbot.waitUntil(lambda: not page.occupe, timeout=30_000)
    assert (rushs / "RawBox01 (upscale).mp4").is_file() and (rushs / "Paysage (upscale).mp4").is_file()
    assert not list(rushs.glob("*.en-cours.*"))
    assert page.tableau.item(0, 4).text().startswith("faite en ") and page.tableau.item(0, 4).text().endswith(": RawBox01 (upscale).mp4")
    assert page.statut.text().startswith("2 vidéos agrandies en ") and page.bouton_ouvrir.isVisible()
    # Les vidéos faites ne sont pas relancées.
    assert not page.bouton_lancer.isEnabled()
    # La taille de la vidéo faite reste affichée (elle disparaissait), même si la résolution visée change.
    assert page.tableau.item(0, 2).text() == "1080 × 1924"
    page.resolution.setCurrentIndex(page.resolution.findData(1440))
    assert page.tableau.item(0, 2).text() == "1080 × 1924" and not page.bouton_lancer.isEnabled()
    page.vider_la_liste()
    assert page.zone_depot.isVisible()


@avec_ffmpeg
def test_autre_dossier_et_erreur_de_topaz(app_configuree, qtbot, services, tmp_path, monkeypatch):
    video = _video(tmp_path / "Rushs", "Sérum.mp4")
    sortie = tmp_path / "Upscales"
    sortie.mkdir()
    page = _page(qtbot, services)
    page.definir_topaz(_faux_topaz(tmp_path))
    page.ajouter_le_prereglage(comprendre(COMMANDE))
    page.definir_autre_dossier(sortie)
    page.sortie.setCurrentIndex(page.sortie.findData(AUTRE_DOSSIER))
    page.ajouter([video])
    qtbot.waitUntil(lambda: not page.occupe, timeout=20_000)
    monkeypatch.setenv("UGC_FAUX_TOPAZ_ECHEC", "1")
    assert page.lancer()
    qtbot.waitUntil(lambda: not page.occupe, timeout=30_000)
    assert page.tableau.item(0, 4).text() == "erreur : Error while filtering: Invalid argument"
    assert "1 en erreur" in page.statut.text() and not list(sortie.iterdir())
    monkeypatch.delenv("UGC_FAUX_TOPAZ_ECHEC")
    assert page.lancer()  # une vidéo en erreur peut être relancée
    qtbot.waitUntil(lambda: not page.occupe, timeout=30_000)
    assert (sortie / "Sérum (upscale).mp4").is_file()


@avec_ffmpeg
def test_nom_des_videos_par_masque(app_configuree, qtbot, services, tmp_path):
    """4.1.0 : le nom des vidéos faites par un masque, avec les champs de Renommer (le même
    composant) et deux balises en plus, %res% et %preset%."""
    rushs = tmp_path / "Glowzy"
    premiere = _video(rushs, "RawBox01.mp4")
    seconde = _video(rushs, "RawBox02.mp4", "320x180")
    page = _page(qtbot, services)
    # Sans vidéo : un exemple ; au départ, le nom d'avant.
    assert page.champs_nom.texte() == "%name% (upscale)%ext%"
    assert page.resume_nom.text() == "Exemple : « Sérum.mp4 » donne « Sérum (upscale).mp4 »."
    assert [b.text() for b in page.champs_nom.boutons_balises] == ["%num%", "%name%", "%ext%", "%folder1%", "%res%", "%preset%"]
    page.definir_topaz(_faux_topaz(tmp_path))
    page.ajouter_le_prereglage(comprendre(COMMANDE))  # nommé d'après son modèle : « Proteus »
    page.ajouter([premiere, seconde])
    qtbot.waitUntil(lambda: not page.occupe, timeout=20_000)
    # Sans %ext% à la fin : en rouge, « Lancer » grisé.
    page.champs_nom.masque.setEditText("NeMu_VID_%num%_%res%")
    assert page.resume_nom.text() == "Le masque doit finir par %ext% : l'app y met l'extension du format du préréglage (.mp4)."
    assert page.resume_nom.property("role") == "erreur" and not page.bouton_lancer.isEnabled()
    page.champs_nom.inserer_balise("%ext%")  # à l'endroit du curseur : la fin
    assert page.champs_nom.texte() == "NeMu_VID_%num%_%res%%ext%" and page.bouton_lancer.isEnabled()
    assert page.resume_nom.text() == "2 vidéos : de « NeMu_VID_01_1080p.mp4 » à « NeMu_VID_02_1080p.mp4 »."
    etats = [page.tableau.item(rang, 4).text() for rang in range(2)]
    assert etats == ["en attente : NeMu_VID_01_1080p.mp4", "en attente : NeMu_VID_02_1080p.mp4"]
    page.champs_nom.depart.setValue(7)
    page.champs_nom.chiffres.setValue(3)
    page.champs_nom.masque.setEditText("%folder1%_%num%_%preset%%ext%")
    assert page.tableau.item(1, 4).text() == "en attente : Glowzy_008_Proteus.mp4"
    # Un nom que Windows refuse : en rouge, dans le tableau aussi.
    page.champs_nom.masque.setEditText("NeMu?%num%%ext%")
    assert page.resume_nom.text() == "2 vidéos ont un nom impossible (en rouge) : rien n'est lancé tant que c'est le cas."
    assert page.tableau.item(0, 4).text() == "nom impossible : Caractère interdit par Windows : ?"
    assert not page.bouton_lancer.isEnabled()
    # Ni numéro ni nom d'origine : le même nom pour les deux, « (2) » ajouté, signalé en orange.
    page.champs_nom.masque.setEditText("NeMu%ext%")
    assert page.bouton_lancer.isEnabled() and page.alertes_nom.isVisible()
    assert page.alertes_nom.text().startswith("1 vidéo aurait le même nom qu'une autre de la liste")
    assert page.tableau.item(1, 4).text() == "en attente : NeMu (2).mp4"
    page.champs_nom.masque.setEditText("NeMu_VID_%num%%ext%")
    page.champs_nom.depart.setValue(1)
    page.champs_nom.chiffres.setValue(2)
    assert page.lancer()
    qtbot.waitUntil(lambda: not page.occupe, timeout=30_000)
    assert (rushs / "NeMu_VID_01.mp4").is_file() and (rushs / "NeMu_VID_02.mp4").is_file()
    assert page.tableau.item(0, 4).text().endswith(": NeMu_VID_01.mp4")
    # Le masque retenu en tête des masques récents, à part de ceux de Renommer.
    assert services.preferences.lire("upscale_masques_recents")[0] == "NeMu_VID_%num%%ext%"
    assert services.preferences.lire("renommer_masque") is None
    # Une vidéo ajoutée ensuite prend le numéro suivant.
    page.ajouter([_video(rushs, "RawBox03.mp4")])
    qtbot.waitUntil(lambda: not page.occupe, timeout=20_000)
    assert page.tableau.item(2, 4).text() == "en attente : NeMu_VID_03.mp4"
    # Un nom déjà pris dans le dossier : « (2) », signalé en orange.
    page.champs_nom.depart.setValue(0)  # 00, 01, 02 : la 3e prendrait « NeMu_VID_02.mp4 », déjà là
    assert page.tableau.item(2, 4).text() == "en attente : NeMu_VID_02 (2).mp4"
    assert "« NeMu_VID_02.mp4 » existe déjà" in page.alertes_nom.text()
    autre = _page(qtbot, services)  # réglages retenus
    assert autre.champs_nom.texte() == "NeMu_VID_%num%%ext%" and autre.champs_nom.depart.value() == 0


@avec_ffmpeg
def test_comparer_deux_videos(app_configuree, qtbot, services, tmp_path):
    video = _video(tmp_path, "a.mp4")
    page = _page(qtbot, services)
    page.comparer_les_videos(video, video)
    qtbot.waitUntil(lambda: not page.occupe, timeout=30_000)
    assert page.statut.text().startswith("Ressemblance : 100,0 %") and page.statut.text().endswith("identiques à l'œil.")
