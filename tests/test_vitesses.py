"""Vitesse de parole mesurée sur les prises, voix par voix (V2, lot 2, §10.7)."""

import pytest

from ugc_studio.audio import duree_wav, wav_depuis_pcm
from ugc_studio.estimation import MOTS_PAR_SECONDE, duree_parlee, estimer_repliques
from ugc_studio.fournisseurs.voix import Replique, ResultatVoix
from ugc_studio.generation import enregistrer_prise, preparer
from ugc_studio.prix import CataloguePrix
from ugc_studio.projets import GestionnaireProjets, RepliqueProjet
from ugc_studio.vitesses import (
    MESURES_GARDEES_PAR_VOIX,
    MESURES_POUR_LA_MOYENNE,
    Vitesse,
    VitessesDeParole,
    mesure_valide,
    mots_et_temps,
)

TEXTE = "Franchement je n'y croyais pas mais ce sérum a changé ma peau"  # 13 mots


def test_mots_et_temps_de_parole():
    # Les balises comptent leur durée estimée (rire : 0,6 s ; pause longue : 1,2 s), pas leurs mots.
    assert mots_et_temps("Salut <laugh> tout le <long pause> monde", 4.0) == (4, pytest.approx(2.2))
    assert mesure_valide(4, 2.0) and not mesure_valide(3, 2.0)  # trop court pour mesurer
    assert not mesure_valide(10, 1.0) and not mesure_valide(10, 20.0)  # 10 ou 0,5 mot/s : prise ratée


def test_vitesse_de_depart_puis_mesuree(tmp_path):
    vitesses = VitessesDeParole(tmp_path / "vitesses.json")
    assert vitesses.vitesse("Kore") == Vitesse(MOTS_PAR_SECONDE, 0, False)
    assert vitesses.vitesse("Kore").texte("Kore") == "vitesse de départ : 2,7 mots/s"

    assert vitesses.noter("Kore", "p1", TEXTE, 4.0)  # 13 mots en 4 s
    assert vitesses.noter("Kore", "p2", TEXTE + " <laugh>", 5.6)  # 13 mots en 5 s (rire : 0,6 s)
    assert not vitesses.noter("Kore", "p3", "…", 2.0)  # rien à mesurer
    kore = vitesses.vitesse("Kore")
    assert kore.mots_par_seconde == pytest.approx(26 / 9, abs=0.001) and kore.nombre == 2 and kore.de_cette_voix
    assert kore.texte("Kore") == "vitesse de Kore mesurée sur 2 prises : 2,9 mots/s"
    # Une voix pas encore mesurée : la moyenne de toutes les prises.
    puck = vitesses.vitesse("Puck")
    assert puck.mots_par_seconde == kore.mots_par_seconde and not puck.de_cette_voix
    assert puck.texte("Puck") == "vitesse mesurée sur 2 prises d'autres voix : 2,9 mots/s"

    # Une prise ne compte qu'une fois ; la mesure est gardée d'une session à l'autre.
    vitesses.noter("Kore", "p1", TEXTE, 6.5)
    assert len(vitesses.mesures("Kore")) == 2
    relue = VitessesDeParole(tmp_path / "vitesses.json")
    assert relue.vitesse("Kore") == vitesses.vitesse("Kore") and relue.connait("p1")


def test_moyenne_des_dernieres_prises(tmp_path):
    vitesses = VitessesDeParole(tmp_path / "vitesses.json")
    for numero in range(MESURES_GARDEES_PAR_VOIX + 5):
        lente = numero < MESURES_GARDEES_PAR_VOIX + 5 - MESURES_POUR_LA_MOYENNE
        vitesses.noter("Kore", f"p{numero}", TEXTE, 6.5 if lente else 5.2, enregistrer=False)  # 2 puis 2,5 mots/s
    assert len(vitesses.mesures("Kore")) == MESURES_GARDEES_PAR_VOIX
    assert vitesses.vitesse("Kore").mots_par_seconde == pytest.approx(2.5)  # les 20 dernières seulement
    assert vitesses.vitesse("Kore").nombre == MESURES_POUR_LA_MOYENNE


def test_estimation_avec_la_vitesse_mesuree(tmp_path):
    texte = " ".join(["mot"] * 30) + " <laugh>"
    assert duree_parlee(texte) == pytest.approx(30 / 2.7 + 0.6)
    assert duree_parlee(texte, 3.0) == pytest.approx(10.6)
    prix = CataloguePrix(tmp_path / "prix.json")
    lente = estimer_repliques([Replique(texte)], "gemini-3.8-flash-tts", prix, mots_par_seconde=2.0)
    rapide = estimer_repliques([Replique(texte)], "gemini-3.8-flash-tts", prix, mots_par_seconde=3.0)
    assert lente.duree_s > rapide.duree_s and lente.tokens_sortie > rapide.tokens_sortie


def test_chaque_prise_generee_est_mesuree(services, tmp_path):
    services.projets.creer("Pub", tmp_path)
    commande = preparer("google", "gemini-3.8-flash-tts", "Kore", [RepliqueProjet([{"texte": TEXTE}])], "Pub")
    wav = wav_depuis_pcm(b"\x00\x00" * 24_000 * 5)  # 5 s
    prise = enregistrer_prise(services, commande, ResultatVoix(wav, duree_wav(wav), 10, 125))
    assert services.vitesses.connait(prise.identifiant)
    assert services.vitesses.vitesse("Kore").mots_par_seconde == pytest.approx(13 / 5)


def test_prises_d_un_projet_mesurees_a_l_ouverture(services, tmp_path):
    """Un projet de la 1.2.0 : ses prises affinent la vitesse dès qu'il s'ouvre."""
    projet = services.projets.creer("Ancien", tmp_path)
    for duree in (4.0, 5.0):
        services.projets.ajouter_prise(b"RIFF", modele="m", voix="Leda", style="", texte_api=TEXTE, script=[], duree_s=duree)
    assert services.vitesses.mesures("Leda") == []  # ajoutées sans passer par la génération
    services.projets.fermer()
    services.projets.ouvrir(projet.dossier)
    assert len(services.vitesses.mesures("Leda")) == 2
    assert services.vitesses.noter_prises(services.projets.projet.prises) == 0  # déjà mesurées
    # Un autre gestionnaire de projets (sans les services) ne mesure rien : c'est le rôle des services.
    assert GestionnaireProjets(tmp_path / "recents.json").ouvrir(projet.dossier).prises[0].voix == "Leda"
