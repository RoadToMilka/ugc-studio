"""V3.1, lot 6 (§7.14) : la zone « Source » de la page Sous-titres.

La vidéo de l'aperçu et les mots des sous-titres, du module Transcription ou importés (prise de voix,
fichier SRT) ; l'import et la transcription confiés au module Transcription, qui montre la même
source ; la fenêtre « Corriger les mots » des mots importés ; ce qui en découle pour la lecture et
les exports.
"""

from array import array

import pytest

from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.exports.plan import source_du_projet
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.stt import MotTranscrit, ResultatTranscription
from ugc_studio.projets import FICHIER_AUDIO
from ugc_studio.sources import SOURCE_IMPORTEE, SOURCE_TRANSCRIPTION
from ugc_studio.transcription import Mot, Transcription

SRT = """1
00:00:00,500 --> 00:00:02,000
Franchement, je n'y croyais pas.

2
00:00:02,400 --> 00:00:04,000
Mais ce sérum Glowzy !
"""

TRANSCRITS = [MotTranscrit("Franchement,", 0.1, 0.6), MotTranscrit("top.", 0.7, 1.1)]


class FauxTranscripteur(Adaptateur):
    identifiant = "google"
    nom = "Faux"
    requetes: list = []

    def lister_modeles(self):
        return []

    def transcrire(self, requete):
        FauxTranscripteur.requetes.append(requete)
        return ResultatTranscription(" ".join(m.texte for m in TRANSCRITS), list(TRANSCRITS), 80, 20)


@pytest.fixture
def pages(app_configuree, qtbot, services, tmp_path, monkeypatch):
    """La page Sous-titres reliée au module Transcription, comme dans la fenêtre principale."""
    from ugc_studio.ui import connexion_ia
    from ugc_studio.ui.pages.sous_titres import PageSousTitres
    from ugc_studio.ui.pages.transcription import PageTranscription

    FauxTranscripteur.requetes = []
    monkeypatch.setattr(connexion_ia, "creer_adaptateur", lambda _f, _cle: FauxTranscripteur("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.5-transcribe"])
    services.projets.creer("Sérum", tmp_path / "projets")
    module = PageTranscription(services)
    qtbot.addWidget(module)
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.atelier.relier_transcription(module.atelier)
    page.resize(1100, 900)
    page.show()
    return page.atelier, module.atelier


def _video_du_module(services, tmp_path, infos: dict | None = None) -> Transcription:
    video = tmp_path / "pub.mp4"
    video.write_bytes(b"pas une vraie video")
    transcription = Transcription(
        source=str(video), audio=FICHIER_AUDIO, duree_s=4.5,
        infos={"video": True, "resolution": [1080, 1920]} if infos is None else infos, langue="fr-FR",
        mots=[Mot("Bonjour", 0.1, 0.5), Mot("à", 0.55, 0.6), Mot("tous.", 0.65, 1.0), Mot("Regardez", 1.6, 2.0), Mot("ça.", 2.05, 2.4)],
        date="2026-10-01T10:00:00+02:00",
    )
    services.projets.projet.transcription = transcription
    return transcription


def _srt(tmp_path, texte: str = SRT, nom: str = "montage.srt"):
    chemin = tmp_path / nom
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def test_zone_source_d_un_nouveau_projet(pages):
    atelier, _module = pages
    from ugc_studio.ui.pages.sous_titres.source import ONGLET_MOTS

    source = atelier.source
    assert source.titre.text() == "Source"
    assert [source.onglets.tabText(i) for i in range(source.onglets.count())] == ["Vidéo ou audio", "Sous-titres"]
    assert source.onglets.currentIndex() == ONGLET_MOTS  # d'où viennent les mots : le plus utile au départ
    assert source.choix_mots.valeur() == SOURCE_TRANSCRIPTION and "Pas encore de mots" in source.texte_mots.text()
    assert source.bouton_corriger.isHidden() and source.zone_transcrire.isHidden() and source.zone_importes.isHidden()
    assert source.ligne_decalage.isHidden() and source.statut.isHidden()
    assert source.texte_video.text() == "Rien d'importé dans le module Transcription."
    assert not source.bouton_importer.isHidden() and source.bouton_importer.text() == "Choisir une vidéo ou un audio…"
    assert source.bouton_choisir_video.isHidden() and source.bouton_retirer_video.isHidden()
    assert not atelier.bloc_apercu.bouton_lecture.isEnabled()  # rien à lire
    source.choix_mots.bouton(SOURCE_IMPORTEE).click()
    assert not source.zone_importes.isHidden() and "Pas encore de mots importés" in source.texte_mots.text()
    assert not atelier.bouton_creer.isEnabled()  # pas encore de prise


def test_importer_puis_transcrire_depuis_la_zone_source(pages, qtbot, services, tmp_path, monkeypatch):
    """« Choisir une vidéo ou un audio… » l'importe dans le module Transcription (les deux modules
    montrent la même source) ; « Transcrire » la transcrit ici, avec les options du module."""
    atelier, module = pages
    wav = tmp_path / "pub glowzy.wav"
    wav.write_bytes(wav_depuis_pcm(array("h", [500, -500] * 48_000 * 2).tobytes(), 48_000, 2))  # 2 s, stéréo
    monkeypatch.setattr(atelier, "_choisir_un_fichier", lambda _titre, _filtre: wav)
    source = atelier.source
    source.bouton_importer.click()
    assert source.bouton_importer.est_occupe() and not source.bouton_transcrire.isEnabled()  # le cercle tourne
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "succes", timeout=10_000)
    projet = services.projets.projet
    assert projet.transcription.source == str(wav) and module.transcription is projet.transcription
    assert "pub glowzy.wav" in atelier.statut.text() and not source.bouton_importer.est_occupe()
    assert "pub glowzy.wav" in source.texte_video.text() and "un audio" in source.texte_video.text()
    assert source.bouton_importer.text() == "Changer de source…"
    assert "n'est pas encore transcrite" in source.texte_mots.text()
    assert not source.zone_transcrire.isHidden() and source.estimation_transcrire.text().startswith("≈ 0:02")
    assert atelier.bloc_apercu.bouton_lecture.isEnabled()  # le son se lit déjà, avant la transcription
    source.bouton_transcrire.click()
    assert source.bouton_transcrire.est_occupe()
    qtbot.waitUntil(lambda: not source.bouton_transcrire.est_occupe(), timeout=10_000)
    (requete,) = FauxTranscripteur.requetes
    assert requete.horodatage and [m.texte for m in projet.transcription.mots] == ["Franchement,", "top."]
    assert atelier.sous_titres and source.zone_transcrire.isHidden()
    assert source.texte_mots.text().startswith("Les sous-titres viennent de la transcription de pub glowzy.wav (2 mots")
    assert atelier.statut.property("role") == "succes" and atelier.statut.text().startswith("Transcription prête")


def test_module_deja_au_travail(pages, services, tmp_path):
    atelier, module = pages
    _video_du_module(services, tmp_path)
    atelier.rafraichir()
    module._occuper(True, module.bouton_transcrire)  # une transcription lancée dans le module
    atelier.transcrire_ici()
    assert atelier.statut.property("role") == "avertissement" and "déjà au travail" in atelier.statut.text()
    assert FauxTranscripteur.requetes == [] and atelier._attente_du_module.bouton is None
    module._occuper(False)


def test_infos_de_la_video_arrivees_apres_l_import(pages, services, tmp_path):
    """La taille de la vidéo arrive parfois après la fin de l'import : l'aperçu et le format suivent."""
    atelier, module = pages
    transcription = _video_du_module(services, tmp_path, infos={})
    atelier.rafraichir()
    assert "un audio" in atelier.source.texte_video.text() and atelier.format.isEnabled()
    module._infos_pretes({"video": True, "resolution": [1080, 1350]})
    assert transcription.infos["resolution"] == [1080, 1350]
    assert "1080 × 1350" in atelier.source.texte_video.text() and not atelier.format.isEnabled()
    assert atelier.toile.taille_video() == (1080, 1350)


def test_importer_un_fichier_srt(pages, services, tmp_path, monkeypatch):
    atelier, _module = pages
    video = _video_du_module(services, tmp_path)
    atelier.rafraichir()
    de_la_video = [s.texte for s in atelier.sous_titres]
    chemin = _srt(tmp_path)
    monkeypatch.setattr(atelier, "_choisir_un_fichier", lambda _titre, _filtre: chemin)
    source = atelier.source
    source.choix_mots.bouton(SOURCE_IMPORTEE).click()
    source.bouton_srt.click()
    projet = services.projets.projet
    importes = projet.sous_titres_importes
    assert projet.transcription is video and projet.sources.sous_titres == SOURCE_IMPORTEE  # rien n'est remplacé
    assert [m.texte for m in importes.mots][:3] == ["Franchement,", "je", "n'y"] and not importes.audio
    assert atelier.statut.property("role") == "succes" and "2 sous-titres, 10 mots" in atelier.statut.text()
    assert "montage.srt" in source.texte_mots.text() and "moment de chaque mot estimé" in source.texte_mots.text()
    assert atelier.sous_titres and [s.texte for s in atelier.sous_titres] != de_la_video
    # La vidéo du module et les mots d'un autre enregistrement : « La voix commence à ».
    assert not source.ligne_decalage.isHidden() and not source.bouton_corriger.isHidden()
    # Un fichier sans sous-titre lisible ne change rien.
    atelier.importer_srt_depuis(_srt(tmp_path, "pas de sous-titres ici", "notes.srt"))
    assert atelier.statut.property("role") == "erreur" and "Aucun sous-titre lisible" in atelier.statut.text()
    assert projet.sous_titres_importes is importes
    # Repasser au module Transcription : ses sous-titres, intacts.
    source.choix_mots.bouton(SOURCE_TRANSCRIPTION).click()
    assert [s.texte for s in atelier.sous_titres] == de_la_video and source.ligne_decalage.isHidden()


def test_sous_titres_d_un_fichier_srt_sans_video(pages, services, tmp_path, monkeypatch):
    """Ni vidéo ni son : rien à lire (un clic sur un sous-titre le montre) ; le calque et le fichier
    SRT s'exportent, la vidéo avec sous-titres demande une vidéo. Une vidéo importée la permet : pas de
    « Son de la vidéo » à choisir (le fichier SRT n'a pas de voix)."""
    atelier, _module = pages
    atelier.importer_srt_depuis(_srt(tmp_path))
    projet = services.projets.projet
    assert atelier.source.choix_mots.valeur() == SOURCE_IMPORTEE and len(atelier.sous_titres) >= 2
    bloc = atelier.bloc_apercu
    assert not bloc.bouton_lecture.isEnabled() and "Rien à lire" in bloc.bouton_lecture.toolTip()
    atelier.choisir_sous_titre(1)
    assert atelier.toile.sous_titre is atelier.sous_titres[1]
    assert atelier.bouton_calque.isEnabled() and atelier.bouton_exporter.isEnabled()
    assert not atelier.bouton_video.isEnabled() and not atelier.info_video.isHidden()
    source = source_du_projet(projet)
    assert source.format == "SRT" and not source.video and source.chemin is None
    assert atelier.source.ligne_decalage.isHidden()  # pas de vidéo : rien à caler
    montage = tmp_path / "montage.mp4"
    montage.write_bytes(b"video")
    monkeypatch.setattr(atelier, "_demander_video", lambda _titre, _proposition: montage)
    atelier.source.choix_video.bouton(SOURCE_IMPORTEE).click()
    atelier.source.bouton_choisir_video.click()
    assert projet.sources.video == SOURCE_IMPORTEE and bloc.bouton_lecture.isEnabled()
    assert not atelier.source.ligne_decalage.isHidden() and atelier.source.zone_son_video.isHidden()
    assert atelier.bouton_video.isEnabled() and source_du_projet(projet).chemin == montage


def test_corriger_les_mots_importes(pages, services, tmp_path, monkeypatch):
    """« Corriger les mots » des mots importés : la fenêtre de correction (la même que dans le module
    Transcription) ; « Enregistrer » garde les corrections, « Annuler » les oublie."""
    atelier, _module = pages
    atelier.importer_srt_depuis(_srt(tmp_path))
    importes = services.projets.projet.sous_titres_importes
    ouvertes = []

    def corriger(fenetre):
        ouvertes.append(fenetre)
        fenetre.choisir_mot(0)
        fenetre.correcteur.champ_mot.setText("Honnêtement,")
        fenetre.correcteur.appliquer_mot()
        return True

    monkeypatch.setattr(atelier, "_corriger", corriger)
    atelier.source.bouton_corriger.click()
    (fenetre,) = ouvertes
    assert fenetre.windowTitle() == "Corriger les mots" and fenetre.zone_lecture.isHidden()  # un SRT n'a pas de son
    assert "montage.srt" in fenetre.description.text()
    assert importes.mots[0].texte == "Honnêtement," and importes.corrigee
    assert atelier.sous_titres[0].texte.startswith("Honnêtement,")
    assert atelier.statut.text() == "Mots corrigés : les sous-titres suivent."
    services.projets.ouvrir(services.projets.projet.dossier)
    importes = services.projets.projet.sous_titres_importes
    assert importes.mots[0].texte == "Honnêtement," and importes.corrigee

    def annuler(fenetre):
        fenetre.choisir_mot(1)
        fenetre.correcteur.supprimer_mot()
        assert fenetre.modifie
        return False

    nombre = len(importes.mots)
    monkeypatch.setattr(atelier, "_corriger", annuler)
    atelier.corriger_les_mots()
    assert len(importes.mots) == nombre  # « Annuler » : rien n'a changé


def test_corriger_les_mots_du_module(pages, services, tmp_path):
    """Les mots du module Transcription se corrigent dans le module, comme avant."""
    atelier, _module = pages
    _video_du_module(services, tmp_path)
    atelier.rafraichir()
    demandes = []
    atelier.corriger_demande.connect(demandes.append)
    atelier.source.bouton_corriger.click()
    assert demandes == [-1.0] and "module Transcription" in atelier.source.bouton_corriger.toolTip()


def test_double_clic_dans_la_frise_sur_des_mots_importes(pages, services, tmp_path, monkeypatch):
    """La fenêtre de correction s'ouvre sur le premier mot du sous-titre."""
    atelier, _module = pages
    atelier.importer_srt_depuis(_srt(tmp_path))
    choisis = []
    monkeypatch.setattr(atelier, "_corriger", lambda fenetre: choisis.append(fenetre.correcteur.mot_choisi) or False)
    atelier._corriger_le_sous_titre(1)
    (choisi,) = choisis
    mots = services.projets.projet.sous_titres_importes.mots
    assert choisi > 0 and mots[choisi].debut == pytest.approx(atelier.mots[atelier.sous_titres[1].premier_mot].debut)


def test_fenetre_corriger_les_mots(app_configuree, qtbot, tmp_path):
    from ugc_studio.ui.dialogues.corriger_mots import DialogueCorrigerMots

    transcription = Transcription(
        source="Prise 2", duree_s=1.0, prise="prise-002", mots=[Mot("Mais", 0.0, 0.3), Mot("ce", 0.35, 0.5), Mot("sérum", 0.55, 0.9)]
    )
    audio = tmp_path / "prise-002.wav"
    audio.write_bytes(wav_depuis_pcm(b"\x00\x00" * 24_000, 24_000))
    fenetre = DialogueCorrigerMots(transcription, "Les sous-titres viennent de « Prise 2 ».", audio, set(), mot=2)
    qtbot.addWidget(fenetre)
    assert not fenetre.zone_lecture.isHidden()  # une prise : on l'écoute pendant la correction
    assert fenetre.correcteur.mot_choisi == 2 and fenetre.correcteur.champ_mot.text() == "sérum"
    assert not fenetre.correcteur.bouton_fusionner.isEnabled()  # le dernier mot n'a pas de suivant
    fenetre.choisir_mot(0)
    fenetre.correcteur.fusionner_mot()
    assert [m.texte for m in fenetre.mots] == ["Mais ce", "sérum"] and fenetre.modifie
    assert [m.texte for m in transcription.mots] == ["Mais", "ce", "sérum"]  # une copie : « Annuler » l'oublie
    assert fenetre.statut.property("role") == "succes"
    fenetre.correcteur.champ_debut.setText("abc")
    fenetre.correcteur.appliquer_mot()
    assert fenetre.statut.property("role") == "erreur" and "secondes" in fenetre.statut.text()
    fenetre.reject()


def test_la_fenetre_principale_relie_les_deux_modules(app_configuree, qtbot, services):
    from ugc_studio.ui.fenetre_principale import FenetrePrincipale

    fenetre = FenetrePrincipale(services)
    qtbot.addWidget(fenetre)
    assert fenetre.page("sous-titres").atelier._module_transcription is fenetre.page("transcription").atelier
