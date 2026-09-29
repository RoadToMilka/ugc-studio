"""Génération d'une prise : découpage, coût noté, calibrage, rangement dans le projet."""

from decimal import Decimal

import pytest

from ugc_studio.audio import duree_wav, wav_depuis_pcm
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.voix import ResultatVoix
from ugc_studio.generation import CLE_CALIBRAGE, enregistrer_prise, preparer, produire_audio, tokens_par_seconde
from ugc_studio.projets import RepliqueProjet
from ugc_studio.prononciation import Prononciation


class FauxTTS(Adaptateur):
    identifiant = "google"
    nom = "Faux"

    def __init__(self):
        super().__init__("cle-de-test-123456")
        self.requetes = []

    def lister_modeles(self):
        return []

    def generer_voix(self, requete):
        self.requetes.append(requete)
        wav = wav_depuis_pcm(b"\x00\x00" * 24_000 * 2)  # 2 s
        return ResultatVoix(wav, duree_wav(wav), tokens_entree=10, tokens_sortie=60)


SCRIPT = [{"texte": "Ce sérum est "}, {"texte": "top", "accentue": True}, {"texte": " ! "}, {"balise": "laugh"}]


def test_prise_complete(services, tmp_path):
    services.projets.creer("Sérum", tmp_path)
    commande = preparer("google", "gemini-3.8-flash-tts", "Kore", [RepliqueProjet(SCRIPT, " chaleureux ")], "Sérum")
    assert commande.texte_api == "Ce sérum est TOP ! <laugh>"
    faux = FauxTTS()
    resultat = produire_audio(faux, commande, 25)
    (requete,) = faux.requetes
    assert requete.voix == "Kore" and requete.repliques[0].style == "chaleureux"

    prise = enregistrer_prise(services, commande, resultat)
    assert prise.nom == "Prise 1" and prise.duree_s == pytest.approx(2.0)
    assert prise.script == SCRIPT  # le script d'origine est gardé pour les sous-titres
    (appel,) = services.couts.lire()
    assert (appel.projet, appel.operation, appel.tokens_sortie) == ("Sérum", "voix", 60)
    assert Decimal(prise.cout_eur) == appel.cout_eur
    # 60 tokens pour 2 s = 30 tokens/s, contre 25 au départ : l'estimation se rapproche de la réalité.
    assert 25 < tokens_par_seconde(services, "gemini-3.8-flash-tts") < 30
    assert CLE_CALIBRAGE in services.preferences._donnees


def test_script_long_genere_en_plusieurs_fois(services, tmp_path):
    services.projets.creer("Long", tmp_path)
    phrase = " ".join(["mot"] * 50) + ". "
    commande = preparer("google", "gemini-3.8-flash-tts", "Kore", [RepliqueProjet([{"texte": phrase * 200}])], "Long")
    faux = FauxTTS()
    resultat = produire_audio(faux, commande, 25)
    assert len(faux.requetes) > 1
    assert resultat.tokens_sortie == 60 * len(faux.requetes)
    assert resultat.duree_s > 2 * len(faux.requetes) - 0.01


def test_repliques_envoyees_ensemble_chacune_avec_son_style(services, tmp_path):
    services.projets.creer("Pub", tmp_path)
    repliques = [
        RepliqueProjet([{"texte": "Stop ! Regarde ça."}], "excited, fast-paced"),
        RepliqueProjet([]),  # réplique vide : ignorée
        RepliqueProjet([{"texte": "Ce sérum a changé ma peau."}], "warm and sincere"),
    ]
    commande = preparer("google", "gemini-3.8-flash-tts", "Kore", repliques, "Pub")
    faux = FauxTTS()
    resultat = produire_audio(faux, commande, 25)
    (requete,) = faux.requetes  # une seule requête pour les deux répliques
    assert [(r.texte, r.style) for r in requete.repliques] == [
        ("Stop ! Regarde ça.", "excited, fast-paced"),
        ("Ce sérum a changé ma peau.", "warm and sincere"),
    ]
    prise = enregistrer_prise(services, commande, resultat)
    assert prise.style == "styles par réplique"
    assert prise.repliques == [
        {"texte_api": "Stop ! Regarde ça.", "style": "excited, fast-paced"},
        {"texte_api": "Ce sérum a changé ma peau.", "style": "warm and sincere"},
    ]
    assert prise.script == [{"texte": "Stop ! Regarde ça. Ce sérum a changé ma peau."}]


def test_prononciation_appliquee_seulement_au_texte_envoye(services, tmp_path):
    services.projets.creer("Glowzy", tmp_path)
    script = [{"texte": "Glowzy, c'est top."}]
    commande = preparer(
        "google", "gemini-3.8-flash-tts", "Kore", [RepliqueProjet(script)], "Glowzy", [Prononciation("Glowzy", "Glo-zi")]
    )
    assert commande.texte_api == "Glo-zi, c'est top."  # ce que la voix prononce
    assert commande.script == script  # les sous-titres gardent l'orthographe correcte
