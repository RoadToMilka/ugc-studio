"""Transcription (§6) : mots horodatés, corrections, remplacements, hésitations, longues sources."""

import math
from array import array
from decimal import Decimal

import pytest

from ugc_studio.audio import lire_wav, wav_depuis_pcm
from ugc_studio.audio_source import (
    FREQUENCE_TRANSCRIPTION,
    coupure_dans_un_silence,
    en_mono,
    morceau_pcm,
    preparer_wav,
)
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.stt import MotTranscrit, ResultatTranscription
from ugc_studio.stt import Options, estimer_cout, terminer_transcription, transcrire_source
from ugc_studio.transcription import (
    DUREE_MAX_HORODATEE_S,
    MORCEAU_S,
    DictionnaireRemplacements,
    Mot,
    Remplacement,
    Transcription,
    ajuster,
    appliquer_remplacements,
    corriger,
    couper,
    decoupage,
    est_hesitation,
    fusionner,
    fusionner_remplacements,
    hesitations_pour,
    index_au_temps,
    mots_affiches,
    supprimer,
    texte_complet,
)


def _mots():
    return [
        Mot("Franchement,", 0.10, 0.72, "spk_1"),
        Mot("euh", 0.80, 1.00, "spk_1"),
        Mot("ce", 1.10, 1.25, "spk_1"),
        Mot("sérum", 1.25, 1.70, "spk_1"),
        Mot("anti", 1.70, 1.95, "spk_1"),
        Mot("rides,", 1.95, 2.40, "spk_1"),
        Mot("c'est", 2.50, 2.80, "spk_2"),
        Mot("top.", 2.80, 3.20, "spk_2"),
    ]


def test_mot_prononce_a_un_moment():
    mots = _mots()
    assert index_au_temps(mots, 0.0) == -1  # avant le premier mot
    assert index_au_temps(mots, 0.5) == 0
    assert index_au_temps(mots, 0.75) == -1  # silence entre deux mots
    assert index_au_temps(mots, 1.25) == 3  # début exact du mot suivant
    assert index_au_temps(mots, 3.19) == 7
    assert index_au_temps(mots, 3.5) == -1


def test_corriger_garde_le_timing():
    mots = _mots()
    corriger(mots, 3, "  Sérum  ")
    assert (mots[3].texte, mots[3].debut, mots[3].fin) == ("Sérum", 1.25, 1.70)
    with pytest.raises(ValueError):
        corriger(mots, 3, "   ")


def test_fusionner_couper_supprimer():
    mots = _mots()
    fusionner(mots, 4)  # « anti » + « rides, »
    assert (mots[4].texte, mots[4].debut, mots[4].fin) == ("anti rides,", 1.70, 2.40)
    assert len(mots) == 7
    couper(mots, 4)  # à l'espace
    assert [m.texte for m in mots[4:6]] == ["anti", "rides,"]
    assert mots[4].debut == 1.70 and mots[5].fin == 2.40
    assert mots[4].fin == pytest.approx(1.70 + 0.70 * 4 / 10)  # temps partagé selon les lettres
    couper(mots, 3, 3)  # « sér » + « um »
    assert [m.texte for m in mots[3:5]] == ["sér", "um"]
    with pytest.raises(ValueError):
        couper(mots, 0, 0)
    supprimer(mots, 1)
    assert "euh" not in texte_complet(mots)
    fusionner(mots, len(mots) - 1)  # dernier mot : rien à fusionner
    assert mots[-1].texte == "top."


def test_ajuster_les_temps_sans_chevauchement():
    mots = _mots()
    ajuster(mots, 3, 1.15, 1.80)  # déborde sur le mot d'avant et celui d'après
    assert (mots[3].debut, mots[3].fin) == (1.15, 1.8)
    assert mots[2].fin == 1.15 and mots[4].debut == 1.8  # voisins raccourcis
    ajuster(mots, 3, 0.0, 5.0)  # ne dépasse jamais les voisins (20 ms minimum chacun)
    assert mots[3].debut == pytest.approx(1.10 + 0.02) and mots[3].fin == pytest.approx(1.95 - 0.02)
    ajuster(mots, 0, -1.0, 0.5)
    assert mots[0].debut == 0.0
    ajuster(mots, 7, 2.9, 2.0)  # fin avant le début : le mot garde 20 ms
    assert mots[7].fin == pytest.approx(mots[7].debut + 0.02)


def test_remplacements_sur_plusieurs_mots():
    mots = _mots()
    remplaces = appliquer_remplacements(
        mots,
        [Remplacement("sérum anti rides", "Sérum Anti-Rides®"), Remplacement("sérum", "Sérum"), Remplacement("TOP", "top 🔥")],
    )
    assert [m.texte for m in remplaces] == ["Franchement,", "euh", "ce", "Sérum Anti-Rides®,", "c'est", "top 🔥."]
    # Temps : du début du premier mot à la fin du dernier.
    assert (remplaces[3].debut, remplaces[3].fin) == (1.25, 2.40)
    assert mots[3].texte == "sérum"  # la liste d'origine n'est pas modifiée


def test_dictionnaires_de_remplacements(tmp_path):
    dictionnaire = DictionnaireRemplacements(tmp_path / "remplacements.json")
    dictionnaire.enregistrer([Remplacement(" glowzy ", "Glowzy"), Remplacement("", "x"), Remplacement("a", "")])
    assert [e.cherche for e in DictionnaireRemplacements(tmp_path / "remplacements.json").entrees] == ["glowzy"]
    projet = [Remplacement("Glowzy", "GLOWZY")]
    assert fusionner_remplacements(dictionnaire.entrees, projet) == [Remplacement("Glowzy", "GLOWZY")]  # le projet l'emporte


def test_hesitations_masquees_dans_les_sous_titres():
    mots = _mots()
    francais = hesitations_pour("fr-FR")
    assert est_hesitation(mots[1], francais)
    assert [m.texte for m in mots_affiches(mots, francais)][:2] == ["Franchement,", "ce"]
    assert len(mots_affiches(mots, francais, masquer=False)) == len(mots)
    assert "um" in hesitations_pour("en-US")
    assert hesitations_pour("fr-FR", {"fr": ["Bah", "  "]}) == {"bah"}
    assert hesitations_pour("xx-YY") == hesitations_pour("fr")  # langue inconnue : français


def test_transcription_enregistree_puis_relue():
    transcription = Transcription(source="C:/pub.mp4", audio="sources/audio.wav", duree_s=3.2, langue="fr-FR", mots=_mots())
    relue = Transcription.depuis_dict(transcription.en_dict())
    assert relue == transcription and relue.horodatee
    assert not Transcription.depuis_dict({"texte": "Bonjour", "mode": "smart"}).horodatee


def test_projet_avec_transcription(services, tmp_path):
    projets = services.projets
    projets.creer("Sérum", tmp_path)
    projets.projet.transcription = Transcription(audio="sources/audio.wav", mots=_mots())
    projets.projet.remplacements = [Remplacement("anti rides", "Anti-Rides")]
    projets.enregistrer()
    projets.ouvrir(projets.projet.dossier)
    assert projets.projet.transcription.mots == _mots()
    assert projets.projet.remplacements == [Remplacement("anti rides", "Anti-Rides")]


# --- Longues sources ----------------------------------------------------------------------------


def test_decoupage_sous_la_limite_de_google():
    assert decoupage(120.0, DUREE_MAX_HORODATEE_S) == [(0.0, 120.0)]
    morceaux = decoupage(70 * 60.0, DUREE_MAX_HORODATEE_S)
    assert morceaux[0] == (0.0, MORCEAU_S)
    assert all(fin - debut <= DUREE_MAX_HORODATEE_S for debut, fin in morceaux)
    assert morceaux[-1][1] == 70 * 60.0


def _son(secondes: float, frequence: int, silence_entre: tuple[float, float] | None = None) -> bytes:
    echantillons = array("h")
    for n in range(int(secondes * frequence)):
        temps = n / frequence
        muet = silence_entre is not None and silence_entre[0] <= temps < silence_entre[1]
        echantillons.append(0 if muet else int(8000 * math.sin(2 * math.pi * 220 * temps)))
    return echantillons.tobytes()


def test_coupure_placee_dans_un_silence():
    pcm = _son(4.0, 8000, silence_entre=(2.6, 2.9))
    coupure = coupure_dans_un_silence(pcm, 8000, 2.0, fenetre=1.0)
    assert 2.6 <= coupure <= 2.9
    assert len(morceau_pcm(pcm, 8000, 1.0, 2.0)) == 8000 * 2


def test_preparer_un_wav_stereo_48_khz():
    stereo = array("h", [1000, 3000] * 4800).tobytes()  # 0,1 s : gauche 1000, droite 3000
    assert array("h", en_mono(stereo, 2))[:3].tolist() == [2000, 2000, 2000]
    pcm, frequence, canaux = lire_wav(preparer_wav(wav_depuis_pcm(stereo, 48_000, 2)))
    assert (frequence, canaux) == (FREQUENCE_TRANSCRIPTION, 1)
    assert abs(len(pcm) // 2 - 1600) <= 1  # 0,1 s à 16 kHz
    assert set(array("h", pcm)[1:-1]) == {2000}


# --- Transcrire la source du projet (avec un faux Google) -----------------------------------------


class FauxTranscripteur(Adaptateur):
    identifiant = "google"
    nom = "Faux"

    def __init__(self):
        super().__init__("cle-de-test-123456")
        self.requetes = []

    def lister_modeles(self):
        return []

    def transcrire(self, requete):
        self.requetes.append(requete)
        duree = len(lire_wav(requete.audio)[0]) / 2 / 8000
        return ResultatTranscription(
            f"morceau {len(self.requetes)}",
            [MotTranscrit("sérum", 0.5, 0.9, "spk_1"), MotTranscrit("anti", 0.9, 1.1), MotTranscrit("rides", 1.1, min(1.5, duree))],
            tokens_entree=100,
            tokens_sortie=20,
        )


def test_transcrire_une_source_courte():
    faux = FauxTranscripteur()
    wav = wav_depuis_pcm(_son(2.0, 8000), 8000)
    resultat = transcrire_source(faux, wav, Options("gemini-3.5-transcribe", "fr-FR", separation_voix=True), "Sérum")
    (requete,) = faux.requetes
    assert requete.audio == wav and requete.nom == "Sérum.wav" and requete.langue == "fr-FR"
    assert requete.horodatage and requete.separation_voix and requete.mode == "verbatim"
    assert [m.texte for m in resultat.mots] == ["sérum", "anti", "rides"]
    assert (resultat.texte, resultat.tokens_entree, resultat.morceaux) == ("morceau 1", 100, 1)


def test_texte_seul_sans_temps():
    faux = FauxTranscripteur()
    transcrire_source(faux, wav_depuis_pcm(_son(1.0, 8000), 8000), Options("m", mode="smart", separation_voix=True))
    (requete,) = faux.requetes
    assert requete.mode == "smart" and not requete.horodatage and not requete.separation_voix


def test_longue_source_coupee_dans_les_silences(monkeypatch):
    from ugc_studio import stt

    # Limite ramenée à 3 s pour le test : une source de 7 s est coupée en trois morceaux.
    monkeypatch.setattr(stt, "DUREE_MAX_HORODATEE_S", 3.0)
    monkeypatch.setattr(stt, "decoupage", lambda duree, limite: decoupage(duree, limite, morceau=2.5))
    monkeypatch.setattr(stt, "coupure_dans_un_silence", lambda pcm, f, temps: temps + 0.25)
    faux = FauxTranscripteur()
    resultat = transcrire_source(faux, wav_depuis_pcm(_son(7.0, 8000), 8000), Options("m"))
    assert resultat.morceaux == len(faux.requetes) == 3
    assert [r.nom for r in faux.requetes] == ["audio (1/3).wav", "audio (2/3).wav", "audio (3/3).wav"]
    # Les temps des mots sont recalés sur le début de chaque morceau (coupures à 2,75 s et 5,25 s).
    assert [m.debut for m in resultat.mots if m.texte == "sérum"] == [0.5, 3.25, 5.75]
    assert resultat.texte == "morceau 1\nmorceau 2\nmorceau 3"
    assert resultat.tokens_entree == 300


def test_terminer_une_transcription(services, tmp_path):
    services.projets.creer("Sérum", tmp_path)
    services.remplacements.enregistrer([Remplacement("sérum anti rides", "Sérum Anti-Rides®")])
    services.projets.projet.remplacements = [Remplacement("morceau", "Partie")]
    transcription = Transcription(audio="sources/audio.wav", duree_s=2.0)
    resultat = transcrire_source(FauxTranscripteur(), wav_depuis_pcm(_son(2.0, 8000), 8000), Options("gemini-3.5-transcribe"))
    fini = terminer_transcription(services, transcription, Options("gemini-3.5-transcribe", "fr-FR"), resultat)
    assert [m.texte for m in fini.mots] == ["Sérum Anti-Rides®"]
    assert fini.texte == "Partie 1"  # dictionnaire du projet appliqué au texte aussi
    (appel,) = services.couts.lire()
    assert (appel.operation, appel.projet, appel.tokens_entree) == ("transcription", "Sérum", 100)
    assert Decimal(fini.cout_eur) == appel.cout_eur
    assert services.projets.projet.transcription is fini and fini.langue == "fr-FR" and fini.date


def test_estimation_du_cout(services):
    une_minute = estimer_cout(60, "gemini-3.5-transcribe", services.prix)
    assert une_minute > 0
    deux_minutes = estimer_cout(120, "gemini-3.5-transcribe", services.prix)
    assert float(deux_minutes) == pytest.approx(2 * float(une_minute), rel=0.01)
