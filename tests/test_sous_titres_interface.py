"""Étape 8 (§7, §3.3, §8.1) — page Sous-titres : mots, réglages, prise → sous-titres, export SRT."""

from decimal import Decimal

import pytest

from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.fournisseurs.base import Adaptateur, ErreurFournisseur
from ugc_studio.fournisseurs.stt import MotTranscrit, ResultatTranscription
from ugc_studio.projets import FICHIER_AUDIO
from ugc_studio.transcription import Mot, Transcription
from ugc_studio.ui import taches
from ugc_studio.ui.pages.sous_titres import PageSousTitres
from ugc_studio.ui.theme import Couleurs

WAV_PRISE = wav_depuis_pcm(b"\x00\x00" * 24_000 * 3, 24_000)  # 3 s, comme une prise TTS
SCRIPT = [{"texte": "Franchement, ce "}, {"texte": "sérum", "accentue": True}, {"texte": " Glowzy est top ! "}, {"balise": "laugh"}]
TRANSCRITS = [
    MotTranscrit("franchement", 0.1, 0.6),
    MotTranscrit("ce", 0.7, 0.8),
    MotTranscrit("sérum", 0.8, 1.2),
    MotTranscrit("glowzi", 1.2, 1.7),  # nom de marque mal transcrit : le script le corrige
    MotTranscrit("est", 1.8, 1.9),
    MotTranscrit("top", 1.9, 2.3),
    MotTranscrit("haha", 2.4, 2.8),  # le rire (<laugh>) transcrit : absent du script, ignoré
]


class FauxTranscripteur(Adaptateur):
    identifiant = "google"
    nom = "Faux"
    requetes: list = []
    echec: str | None = None

    def lister_modeles(self):
        return []

    def transcrire(self, requete):
        FauxTranscripteur.requetes.append(requete)
        if FauxTranscripteur.echec:
            raise ErreurFournisseur(FauxTranscripteur.echec, "quota")
        return ResultatTranscription(" ".join(m.texte for m in TRANSCRITS), list(TRANSCRITS), 75, 12)


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path, monkeypatch):
    from ugc_studio.ui import connexion_ia

    FauxTranscripteur.requetes, FauxTranscripteur.echec = [], None
    monkeypatch.setattr(connexion_ia, "creer_adaptateur", lambda _f, _cle: FauxTranscripteur("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(connexion.identifiant, True, "ok", ["gemini-3.5-transcribe"])
    services.projets.creer("Sérum", tmp_path / "projets")
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.show()
    return page.atelier


def _prise(services):
    return services.projets.ajouter_prise(
        WAV_PRISE,
        modele="gemini-3.8-flash-tts",
        voix="Kore",
        style="",
        texte_api="Franchement, ce SÉRUM Glowzy est top ! <laugh>",
        script=SCRIPT,
        duree_s=3.0,
    )


def _transcription_video(services, mots: list[Mot] | None = None) -> Transcription:
    transcription = Transcription(
        source="C:/Vidéos/pub.mp4",
        audio=FICHIER_AUDIO,
        duree_s=4.0,
        infos={"resolution": [1920, 1080], "rotation": 90},  # vidéo de téléphone, enregistrée couchée
        langue="fr-FR",
        mots=mots
        or [
            Mot("Franchement,", 0.1, 0.6),
            Mot("euh", 0.7, 0.9),
            Mot("je", 1.0, 1.1),
            Mot("n'y", 1.1, 1.3),
            Mot("croyais", 1.3, 1.7),
            Mot("pas.", 1.7, 2.0),
            Mot("Incroyable", 2.6, 3.2),
            Mot("!", 3.2, 3.3),
        ],
        date="2026-09-30T10:00:00+02:00",
    )
    services.projets.projet.transcription = transcription
    return transcription


def test_page_sans_puis_avec_projet(app_configuree, qtbot, services, tmp_path):
    page = PageSousTitres(services)
    qtbot.addWidget(page)
    page.show()
    assert page.currentWidget() is page.sans_projet
    assert page.sans_projet.titre.text() == "Sous-titres"
    services.projets.creer("Sérum", tmp_path)
    assert page.currentWidget() is page.atelier
    atelier = page.atelier
    assert atelier.titre.text() == "Sous-titres — Sérum"
    assert not atelier.cadre_sous_titres.isVisible() and not atelier.bouton_creer.isEnabled()
    assert "Pas encore de mots" in atelier.texte_source.text()


def test_sous_titres_d_une_transcription(atelier, services):
    _transcription_video(services)
    atelier.rafraichir()
    assert atelier.cadre_sous_titres.isVisible()
    textes = [s.texte for s in atelier.sous_titres]
    # « euh » masqué ; fin de phrase = fin de sous-titre ; « ! » rejoint son mot (espace insécable).
    assert textes[0].startswith("Franchement,") and "euh" not in " ".join(textes)
    assert textes[-1] == "Incroyable\u00a0!"
    assert atelier.tableau.rowCount() == len(atelier.sous_titres)
    assert atelier.tableau.item(0, 2).text() == atelier.sous_titres[0].texte.replace("\u00a0", " ")
    # Vidéo tournée d'un quart de tour : mesurée à la verticale.
    assert "Vidéo 1080 × 1920" in atelier.infos_ecran.text()
    assert "pub.mp4" in atelier.texte_source.text() and atelier.bouton_corriger.isVisible()
    assert atelier.bouton_exporter.isEnabled()


def test_reglages_recalculent_et_sont_enregistres(atelier, services):
    _transcription_video(services)
    atelier.rafraichir()
    avant = len(atelier.sous_titres)
    atelier.mots_max.setValue(1)
    assert len(atelier.sous_titres) > avant
    assert all(s.dernier_mot - s.premier_mot == 1 for s in atelier.sous_titres)
    atelier.majuscules.setChecked(True)
    assert atelier.sous_titres[0].texte == "FRANCHEMENT,"
    atelier.ponctuation.setChecked(False)
    assert atelier.sous_titres[0].texte == "FRANCHEMENT"
    atelier.masquer.setChecked(False)  # réglage partagé avec la transcription
    assert "EUH" in [s.texte for s in atelier.sous_titres]
    assert not services.projets.projet.transcription.masquer_hesitations
    # Réglages enregistrés dans le projet.
    services.projets.ouvrir(services.projets.projet.dossier)
    reglages = services.projets.projet.sous_titres
    assert (reglages.mots_max, reglages.majuscules, reglages.ponctuation) == (1, True, False)
    assert atelier.mots_max.value() == 1 and atelier.majuscules.isChecked()


def test_mot_trop_large_signale_en_orange(atelier, services):
    _transcription_video(services, [Mot("Anticonstitutionnellement", 0.0, 1.0), Mot("oui", 1.1, 1.3)])
    atelier.rafraichir()
    atelier.taille.setValue(5.5)  # texte plus grand : le mot seul dépasse la marge maximum
    (signale,) = [s for s in atelier.sous_titres if s.signale]
    rang = atelier.sous_titres.index(signale)
    assert 0.6 <= signale.echelle < 1 and "rapetissé" in atelier.tableau.item(rang, 3).text()
    assert atelier.tableau.item(rang, 2).foreground().color().name().lower() == Couleurs.AVERTISSEMENT.lower()
    assert "signalé en orange" in atelier.resume.text()
    atelier.taille.setValue(15.0)  # même rapetissé au minimum, il ne tient pas
    assert "raccourcis ce mot" in atelier.tableau.item(rang, 3).text()


def test_creer_les_sous_titres_d_une_prise(atelier, qtbot, services):
    prise = _prise(services)
    atelier.rafraichir()
    assert atelier.prises.currentData() == prise.identifiant and atelier.bouton_creer.isEnabled()
    assert atelier.estimation.text().startswith("≈ 0:03")
    atelier.creer_depuis_la_prise_choisie()
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "succes", timeout=10_000)
    (requete,) = FauxTranscripteur.requetes
    assert requete.langue == "fr-FR" and requete.horodatage and not requete.separation_voix
    transcription = services.projets.projet.transcription
    # Orthographe du script (majuscules, ponctuation, nom de marque), temps de la transcription.
    assert [m.texte for m in transcription.mots] == ["Franchement,", "ce", "sérum", "Glowzy", "est", "top !"]
    assert (transcription.mots[3].debut, transcription.mots[3].fin) == (1.2, 1.7)
    assert transcription.prise == prise.identifiant and transcription.source == prise.nom
    assert services.projets.projet.chemin(FICHIER_AUDIO).read_bytes() == WAV_PRISE
    (appel,) = services.couts.lire()
    assert appel.operation == "transcription" and Decimal(transcription.cout_eur) == appel.cout_eur
    assert atelier.sous_titres and "voix générée" in atelier.texte_source.text()
    assert taches.en_cours() == 0


def test_prise_qui_remplacerait_une_transcription(atelier, services, monkeypatch):
    video = _transcription_video(services)
    prise = _prise(services)
    atelier.rafraichir()
    monkeypatch.setattr(atelier, "_confirmer_remplacement", lambda _actuelle: False)
    atelier.creer_depuis_prise(prise.identifiant)
    assert services.projets.projet.transcription is video and FauxTranscripteur.requetes == []


def test_erreur_de_transcription_de_la_prise(atelier, qtbot, services):
    prise = _prise(services)
    atelier.rafraichir()
    FauxTranscripteur.echec = "Limite d'utilisation atteinte chez Google."
    atelier.creer_depuis_prise(prise.identifiant)
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "erreur", timeout=10_000)
    assert "Limite d'utilisation" in atelier.statut.text()
    assert services.projets.projet.transcription is None  # rien n'est remplacé
    assert not services.projets.projet.chemin(FICHIER_AUDIO).exists()
    assert atelier.bouton_creer.isEnabled()


def test_export_srt(atelier, services, tmp_path, monkeypatch):
    _transcription_video(services)
    atelier.rafraichir()
    monkeypatch.setattr(atelier, "_demander_fichier", lambda _proposition: tmp_path / "pub")
    atelier.exporter_srt()
    fichier = tmp_path / "pub.srt"
    brut = fichier.read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf") and b"\r\n" in brut  # UTF-8 avec BOM, fins de ligne Windows
    texte = brut.decode("utf-8-sig")
    assert texte.startswith("1\r\n00:00:00,") and "Incroyable\u00a0!" in texte
    assert texte.count(" --> ") == len(atelier.sous_titres)
    assert atelier.statut_export.property("role") == "succes" and "pub.srt" in atelier.statut_export.text()


def test_clic_sur_un_sous_titre(atelier, services):
    _transcription_video(services)
    atelier.rafraichir()
    dernier = len(atelier.sous_titres) - 1
    atelier.choisir_sous_titre(dernier)
    assert atelier.tableau.currentRow() == dernier
    assert atelier.apercu.text() == atelier.sous_titres[dernier].texte
