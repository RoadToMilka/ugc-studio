"""Étape 7 (§6) — interface : import d'une source, transcription (faux Google), éditeur de mots."""

from array import array
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt

from ugc_studio.audio import lire_wav, wav_depuis_pcm
from ugc_studio.fournisseurs.base import Adaptateur, ErreurFournisseur
from ugc_studio.fournisseurs.stt import MotTranscrit, ResultatTranscription
from ugc_studio.transcription import Mot, Remplacement, Transcription
from ugc_studio.ui import taches
from ugc_studio.ui.pages.transcription import PageTranscription
from ugc_studio.ui.pages.transcription.atelier import FICHIER_AUDIO, description_source

MOTS = [
    MotTranscrit("Franchement,", 0.10, 0.70),
    MotTranscrit("euh", 0.80, 1.00),
    MotTranscrit("ce", 1.10, 1.25),
    MotTranscrit("sérum", 1.25, 1.70),
    MotTranscrit("glowzy", 1.70, 2.20),
    MotTranscrit("est", 2.30, 2.50),
    MotTranscrit("top.", 2.50, 2.90),
]


class FauxTranscripteur(Adaptateur):
    identifiant = "google"
    nom = "Faux"
    requetes: list = []
    echec: str | None = None
    smart = False

    def lister_modeles(self):
        return []

    def transcrire(self, requete):
        FauxTranscripteur.requetes.append(requete)
        if FauxTranscripteur.echec:
            raise ErreurFournisseur(FauxTranscripteur.echec, "quota")
        if requete.mode == "smart":
            return ResultatTranscription("Franchement, ce sérum est top.", [], 80, 10)
        return ResultatTranscription(" ".join(m.texte for m in MOTS), list(MOTS), 80, 20)


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path, monkeypatch):
    from ugc_studio.ui import connexion_ia

    FauxTranscripteur.requetes, FauxTranscripteur.echec = [], None
    monkeypatch.setattr(connexion_ia, "creer_adaptateur", lambda _f, _cle: FauxTranscripteur("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.5-transcribe"])
    services.projets.creer("Sérum", tmp_path / "projets")
    page = PageTranscription(services)
    qtbot.addWidget(page)
    page.show()
    return page.atelier


def _source_wav(dossier: Path, secondes: float = 3.0) -> Path:
    """Un WAV stéréo à 48 kHz, comme une piste audio exportée d'un logiciel de montage."""
    chemin = dossier / "pub glowzy.wav"
    chemin.write_bytes(wav_depuis_pcm(array("h", [500, -500] * int(48_000 * secondes)).tobytes(), 48_000, 2))
    return chemin


def _transcription(services) -> Transcription:
    transcription = Transcription(
        source="C:/Vidéos/pub.mp4",
        audio=FICHIER_AUDIO,
        duree_s=3.0,
        langue="fr-FR",
        mots=[Mot(m.texte, m.debut, m.fin, m.locuteur) for m in MOTS],
        date="2026-09-30T10:00:00+02:00",
    )
    services.projets.projet.transcription = transcription
    return transcription


def test_page_sans_puis_avec_projet(app_configuree, qtbot, services, tmp_path):
    page = PageTranscription(services)
    qtbot.addWidget(page)
    page.show()
    assert page.currentWidget() is page.sans_projet
    assert page.sans_projet.titre.text() == "Transcription"
    services.projets.creer("Sérum", tmp_path)
    assert page.currentWidget() is page.atelier
    assert page.atelier.titre.text() == "Transcription • Sérum"
    assert page.atelier.zone_depot.isVisible() and not page.atelier.cadre_transcription.isVisible()


def test_importer_puis_transcrire(atelier, qtbot, services, tmp_path):
    source = _source_wav(tmp_path)
    atelier.importer(source)
    qtbot.waitUntil(lambda: atelier.transcription is not None, timeout=10_000)
    transcription = atelier.transcription
    # Piste son rangée dans le projet : WAV 16 kHz mono.
    _pcm, frequence, canaux = lire_wav(services.projets.projet.chemin(FICHIER_AUDIO).read_bytes())
    assert (frequence, canaux) == (16_000, 1)
    assert transcription.source == str(source) and transcription.duree_s == pytest.approx(3.0, abs=0.01)
    assert not atelier.zone_depot.isVisible() and "pub glowzy.wav" in atelier.texte_source.text()
    assert atelier.statut.property("role") == "succes"
    assert atelier.estimation.text().startswith("≈ 0:03")

    services.remplacements.enregistrer([Remplacement("sérum glowzy", "Sérum Glowzy")])
    atelier.separation.setChecked(True)
    atelier.transcrire()
    qtbot.waitUntil(lambda: bool(atelier.transcription.mots), timeout=10_000)
    (requete,) = FauxTranscripteur.requetes
    assert requete.langue == "fr-FR" and requete.separation_voix and requete.horodatage
    assert [m.texte for m in atelier.transcription.mots] == ["Franchement,", "euh", "ce", "Sérum Glowzy", "est", "top."]
    (appel,) = services.couts.lire()
    assert appel.operation == "transcription" and Decimal(atelier.transcription.cout_eur) == appel.cout_eur
    assert atelier.cadre_transcription.isVisible() and "Sérum Glowzy" in atelier.editeur.toPlainText()
    assert "6 mots" in atelier.resume.text()
    # Rouvert, le projet retrouve sa transcription.
    services.projets.ouvrir(services.projets.projet.dossier)
    assert len(atelier.transcription.mots) == 6


def test_erreur_de_transcription(atelier, qtbot, services, tmp_path):
    _transcription(services)
    services.projets.projet.chemin(FICHIER_AUDIO).parent.mkdir(parents=True, exist_ok=True)
    services.projets.projet.chemin(FICHIER_AUDIO).write_bytes(wav_depuis_pcm(b"\x00\x00" * 16_000, 16_000))
    FauxTranscripteur.echec = "Limite d'utilisation atteinte chez Google."
    atelier.transcrire()
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "erreur", timeout=5_000)
    assert "Limite d'utilisation" in atelier.statut.text()
    assert taches.en_cours() == 0


def test_texte_seul(atelier, qtbot, services):
    _transcription(services).mots = []
    services.projets.projet.chemin(FICHIER_AUDIO).parent.mkdir(parents=True, exist_ok=True)
    services.projets.projet.chemin(FICHIER_AUDIO).write_bytes(wav_depuis_pcm(b"\x00\x00" * 16_000, 16_000))
    atelier.rafraichir()
    atelier.separation.setChecked(True)
    atelier.texte_seul.setChecked(True)
    assert not atelier.separation.isEnabled()  # incompatibles chez Google
    assert atelier.options().mode == "smart" and not atelier.options().separation_voix
    atelier.transcrire()
    qtbot.waitUntil(lambda: bool(atelier.transcription.texte), timeout=5_000)
    assert atelier.texte_smart.isVisible() and not atelier.editeur.isVisible()
    assert atelier.texte_smart.toPlainText() == "Franchement, ce sérum est top."


def test_corriger_fusionner_couper_supprimer(atelier, services):
    _transcription(services)
    atelier.rafraichir()
    atelier.choisir_mot(3)
    assert (atelier.champ_mot.text(), atelier.champ_debut.text(), atelier.champ_fin.text()) == ("sérum", "1.25", "1.70")
    atelier.champ_mot.setText("Sérum")
    atelier.champ_debut.setText("1,20")  # virgule acceptée
    atelier.appliquer_mot()
    mots = atelier.transcription.mots
    assert (mots[3].texte, mots[3].debut) == ("Sérum", 1.2)
    assert mots[2].fin == 1.2  # le mot d'avant est raccourci
    atelier.fusionner_mot()  # « Sérum » + « glowzy »
    assert atelier.transcription.mots[3].texte == "Sérum glowzy"
    atelier.couper_mot()
    assert [m.texte for m in atelier.transcription.mots[3:5]] == ["Sérum", "glowzy"]
    atelier.choisir_mot(1)
    atelier.supprimer_mot()
    assert "euh" not in [m.texte for m in atelier.transcription.mots]
    # Les corrections sont enregistrées dans le projet.
    services.projets.ouvrir(services.projets.projet.dossier)
    assert services.projets.projet.transcription.mots[2].texte == "Sérum"


def test_temps_invalides_refuses(atelier, services):
    _transcription(services)
    atelier.rafraichir()
    atelier.choisir_mot(0)
    atelier.champ_debut.setText("abc")
    atelier.appliquer_mot()
    assert atelier.statut.property("role") == "erreur"


def test_clic_sur_un_mot(atelier, services, qtbot):
    _transcription(services)
    atelier.rafraichir()
    editeur = atelier.editeur
    texte = editeur.toPlainText()
    position = texte.index("glowzy") + 2
    assert editeur.index_a(position) == 4
    curseur = editeur.textCursor()
    curseur.setPosition(position)
    point = editeur.cursorRect(curseur).center()
    qtbot.mouseClick(editeur.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(point.x(), point.y()))
    assert editeur.mot_choisi == 4 and atelier.champ_mot.text() == "glowzy"


def test_voix_separees_en_paragraphes(atelier, services):
    transcription = _transcription(services)
    for mot in transcription.mots[:3]:
        mot.locuteur = "spk_1"
    for mot in transcription.mots[3:]:
        mot.locuteur = "spk_2"
    atelier.rafraichir()
    texte = atelier.editeur.toPlainText()
    assert texte.startswith("Personne 1 : Franchement,") and "\nPersonne 2 : sérum" in texte
    assert atelier.editeur.index_a(texte.index("Personne 2") + 2) == -1  # nom de la personne : pas un mot
    assert "Personne 1, Personne 2" in atelier.resume.text()


def test_hesitations_barrees_quand_masquees(atelier, services):
    _transcription(services)
    atelier.rafraichir()
    editeur = atelier.editeur

    def barre(mot: str) -> bool:
        curseur = editeur.textCursor()
        curseur.setPosition(editeur.toPlainText().index(mot) + 1)
        return curseur.charFormat().fontStrikeOut()

    assert atelier.masquer.isChecked() and barre("euh") and not barre("Franchement")
    atelier.masquer.setChecked(False)
    assert not barre("euh") and not atelier.transcription.masquer_hesitations


def test_dictionnaire_applique_sans_refaire_la_transcription(atelier, services):
    _transcription(services)
    services.projets.projet.remplacements = [Remplacement("sérum glowzy", "Sérum Glowzy")]
    atelier.appliquer_dictionnaire()
    assert "Sérum Glowzy" in [m.texte for m in atelier.transcription.mots]
    assert FauxTranscripteur.requetes == []


def test_formats_et_confirmation(atelier, services, tmp_path, monkeypatch):
    atelier.importer(tmp_path / "notes.txt")
    assert atelier.statut.property("role") == "erreur" and "non pris en charge" in atelier.statut.text()
    _transcription(services)
    monkeypatch.setattr(atelier, "_confirmer_remplacement", lambda: False)
    atelier.importer(_source_wav(tmp_path))  # transcription existante : on demande avant de la remplacer
    assert atelier.transcription.source == "C:/Vidéos/pub.mp4"


def test_description_de_la_source():
    transcription = Transcription(
        source="C:/Vidéos/pub.mp4",
        duree_s=42.2,
        infos={"resolution": [1080, 1920], "images_par_seconde": 29.97, "codec_video": "H264", "hdr": True},
    )
    assert description_source(transcription) == "pub.mp4  ·  0:42  ·  1080 × 1920  ·  29.97 images/s  ·  H264  ·  HDR"


def test_masquer_les_hesitations_demande_avant_de_defaire_un_ajustement(atelier, services, monkeypatch):
    """Même réglage que dans la page Sous-titres (V1.1) : la même question est posée."""
    from ugc_studio.ui import sous_titres_du_projet

    transcription = _transcription(services)
    transcription.masquer_hesitations = False
    transcription.ajustements_sous_titres = [[0.8, 1.0]]  # « euh », seul dans un sous-titre ajusté à la main
    atelier.rafraichir()
    questions = []
    monkeypatch.setattr(sous_titres_du_projet, "demander", lambda _parent, texte, _plusieurs: questions.append(texte) or False)
    atelier.masquer.setChecked(True)
    (question,) = questions
    assert question.startswith("Ce réglage défait ton ajustement du sous-titre 2 (« euh »)")
    assert question.endswith(" : plus aucun de ses mots n'est affiché.")
    assert not atelier.masquer.isChecked() and not transcription.masquer_hesitations  # réglage gardé
    monkeypatch.setattr(sous_titres_du_projet, "demander", lambda *_arguments: True)
    atelier.masquer.setChecked(True)
    assert transcription.masquer_hesitations and transcription.ajustements_sous_titres == []
