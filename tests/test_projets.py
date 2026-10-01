"""Projets (§3.2) : création, réouverture, prises, projets récents."""

import pytest

import json

from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.projets import ErreurProjet, GestionnaireProjets, Projet, RepliqueProjet, nom_de_dossier
from ugc_studio.prononciation import Prononciation
from ugc_studio.sous_titres import ReglagesSousTitres

WAV = wav_depuis_pcm(b"\x00\x00" * 24_000)  # 1 seconde de silence


@pytest.fixture
def gestion(tmp_path):
    return GestionnaireProjets(tmp_path / "recents.json")


def _infos():
    return dict(modele="m", voix="Kore", style="", texte_api="t", script=[{"texte": "t"}], duree_s=1.0)


def test_nom_de_dossier_valide_sous_windows():
    assert nom_de_dossier('Sérum: "Glowzy"?') == "Sérum Glowzy"
    assert nom_de_dossier("CON") == "Projet CON"
    assert nom_de_dossier("  ...  ") == "Projet"


def test_creer_puis_rouvrir(gestion, tmp_path):
    projet = gestion.creer("Sérum Glowzy", tmp_path, "nl-BE")
    assert (projet.dossier / "projet.json").exists()
    assert (projet.dossier / "prises").is_dir()
    projet.repliques = [
        RepliqueProjet([{"texte": "Salut "}, {"balise": "laugh"}], "excited", "excité"),
        RepliqueProjet([{"texte": "Le lien est en dessous."}]),
    ]
    projet.prononciations = [Prononciation("Glowzy", "Glo-zi")]
    projet.voix.voix = "Puck"
    gestion.enregistrer()

    autre = GestionnaireProjets(tmp_path / "recents.json")
    rouvert = autre.ouvrir(projet.dossier)
    assert rouvert.nom == "Sérum Glowzy" and rouvert.langue == "nl-BE"
    assert rouvert.repliques == projet.repliques
    assert rouvert.prononciations == [Prononciation("Glowzy", "Glo-zi")]
    # Script complet (sous-titres) : les répliques bout à bout.
    assert rouvert.script == [{"texte": "Salut "}, {"balise": "laugh"}, {"texte": " Le lien est en dessous."}]
    assert rouvert.voix.voix == "Puck"


def test_projet_de_l_etape_3_converti(gestion, tmp_path):
    """Format 1 : un seul script, et le style dans les réglages de voix → une seule réplique."""
    dossier = tmp_path / "Ancien"
    dossier.mkdir()
    (dossier / "projet.json").write_text(
        json.dumps(
            {
                "version_format": 1,
                "nom": "Ancien",
                "voix": {"modele": "gemini-3.8-flash-tts", "voix": "Leda", "style": "warm"},
                "script": [{"texte": "Bonjour"}],
                "prises": [],
            }
        ),
        encoding="utf-8",
    )
    projet = gestion.ouvrir(dossier)
    assert projet.repliques == [RepliqueProjet([{"texte": "Bonjour"}], "warm")]
    assert projet.voix.voix == "Leda" and projet.prononciations == []
    gestion.enregistrer()
    enregistre = json.loads((dossier / "projet.json").read_text(encoding="utf-8"))
    assert enregistre["version_format"] == Projet.VERSION_FORMAT
    assert "script" not in enregistre and "style" not in enregistre["voix"]
    assert projet.transcription is None and projet.remplacements == []
    assert projet.sous_titres == ReglagesSousTitres()  # format 4 : réglages par défaut


def test_noms_de_variantes_de_la_v1_0_0_sans_tiret(gestion, tmp_path):
    """Jusqu'à la v1.0.0, une variante s'appelait « Prise 3 — variante B » : à l'ouverture, elle
    prend la forme actuelle, « Prise 3 (variante B) ». Un nom choisi à la main ne change jamais."""
    dossier = tmp_path / "Ancien"
    dossier.mkdir()
    prises = [
        dict(identifiant="a", nom="Prise 3 — variante B", fichier="prises/prise-003.wav", date="", **_infos()),
        dict(identifiant="b", nom="Mon essai — final", fichier="prises/prise-004.wav", date="", **_infos()),
    ]
    (dossier / "projet.json").write_text(
        json.dumps({"version_format": 4, "nom": "Ancien", "prises": prises}), encoding="utf-8"
    )
    projet = gestion.ouvrir(dossier)
    assert [p.nom for p in projet.prises] == ["Prise 3 (variante B)", "Mon essai — final"]


def test_module_script_enregistre_dans_le_projet(gestion, tmp_path):
    """Format 6 (V2) : brief, page lue, fiche, accroches et scripts sont gardés dans le projet."""
    from ugc_studio.ecriture.fiche import FicheProduit
    from ugc_studio.ecriture.page_produit import PageLue
    from ugc_studio.ecriture.scripts import Accroche, RepliqueEcrite, nouveau_script

    projet = gestion.creer("Culotte Léa", tmp_path)
    etat = projet.ecriture
    etat.adresse = "mademoiselleculotte.com/products/culotte-menstruelle-lea"
    etat.brief.reseau, etat.brief.duree_s, etat.brief.balises = "meta", 20, True
    etat.brief.pre_remplir({"produit": "Culotte menstruelle Léa"})
    etat.page = PageLue("https://x.fr/products/lea", "shopify", "2026-10-01T14:32:00+02:00", "Données…", prix="21,90 €")
    etat.fiche = FicheProduit(nom="Culotte menstruelle Léa", benefices=["Au sec jusqu'à 12 h"])
    etat.accroches = [Accroche("Fini les fuites la nuit.", "temoignage", "Parle d'un vrai souci.", cochee=True)]
    script = nouveau_script(
        modele="gemini-3.8-flash", reseau="meta", langue="fr-FR", angle="temoignage", duree_visee_s=20,
        repliques=[RepliqueEcrite(["accroche"], [{"texte": "Fini les fuites "}, {"balise": "laugh"}], "warm", "chaleureux")],
    )
    etat.ajouter(script)
    script.note, script.retenu = 4, True  # lot 2 : même format, informations en plus
    gestion.enregistrer()

    rouvert = GestionnaireProjets(tmp_path / "recents.json").ouvrir(projet.dossier).ecriture
    assert rouvert.brief == etat.brief and rouvert.brief.pre_remplis == ["produit"]
    assert rouvert.adresse == etat.adresse and rouvert.page == etat.page and rouvert.fiche == etat.fiche
    assert rouvert.accroches == etat.accroches and rouvert.accroches_cochees()[0].texte == "Fini les fuites la nuit."
    assert rouvert.scripts == [script] and rouvert.script(script.identifiant) == script
    assert rouvert.scripts[0].nom() == "Script 1" and rouvert.scripts[0].note == 4 and rouvert.scripts[0].retenu


def test_scripts_de_la_1_2_0_numerotes_a_l_ouverture():
    """Lot 2 : un script écrit avec la 1.2.0 n'a pas de numéro ; il en reçoit un, dans l'ordre d'écriture."""
    from ugc_studio.ecriture.etat import EtatScript

    brut = {"repliques": [{"roles": ["accroche"], "script": [{"texte": "Salut"}]}], "modele": "m", "reseau": "tiktok"}
    etat = EtatScript.depuis_dict({"scripts": [dict(brut, identifiant="a"), dict(brut, identifiant="b")]})
    assert [(s.identifiant, s.nom()) for s in etat.scripts] == [("a", "Script 1"), ("b", "Script 2")]
    nouveau = etat.ajouter(etat.scripts[0].__class__.depuis_dict(dict(brut, identifiant="c")))
    assert nouveau.nom() == "Script 3" and etat.scripts[-1] is nouveau


def test_projet_de_la_v1_1_sans_script(gestion, tmp_path):
    dossier = tmp_path / "Ancien"
    dossier.mkdir()
    (dossier / "projet.json").write_text(json.dumps({"version_format": 5, "nom": "Ancien"}), encoding="utf-8")
    projet = gestion.ouvrir(dossier)
    assert projet.ecriture.scripts == [] and projet.ecriture.page is None and projet.ecriture.brief.reseau == "tiktok"


def test_dernieres_modifications_d_un_projet_qu_on_quitte(gestion, tmp_path):
    """Un module enregistre ses dernières modifications au moment où un autre projet s'ouvre : elles vont
    dans l'ancien projet, pas dans le nouveau."""
    ancien = gestion.creer("Ancien", tmp_path)
    nouveau = gestion.creer("Nouveau", tmp_path)
    ancien.repliques = [RepliqueProjet([{"texte": "Modifié juste avant."}])]
    gestion.enregistrer(ancien)
    assert GestionnaireProjets(tmp_path / "autres.json").ouvrir(ancien.dossier).repliques == ancien.repliques
    assert GestionnaireProjets(tmp_path / "autres.json").ouvrir(nouveau.dossier).repliques == [RepliqueProjet()]


def test_changer_la_langue_du_projet(gestion, tmp_path):
    projet = gestion.creer("Batterie", tmp_path)
    vus = []
    gestion.abonner(lambda p: vus.append(p.langue if p else None))
    gestion.changer_langue("nl-BE")
    assert projet.langue == "nl-BE" and vus == ["nl-BE"]
    gestion.changer_langue("xx-XX")  # inconnue : rien ne change
    assert projet.langue == "nl-BE" and vus == ["nl-BE"]


def test_reglages_des_sous_titres_enregistres(gestion, tmp_path):
    from dataclasses import replace

    projet = gestion.creer("Sous-titres", tmp_path)
    projet.sous_titres.texte = replace(projet.sous_titres.texte, casse="majuscules")
    projet.sous_titres.lignes_max = 1
    gestion.enregistrer()
    rouvert = GestionnaireProjets(tmp_path / "recents.json").ouvrir(projet.dossier)
    assert rouvert.sous_titres.texte.casse == "majuscules" and rouvert.sous_titres.lignes_max == 1


def test_nouveau_projet_avec_une_replique_vide(gestion, tmp_path):
    projet = gestion.creer("Vide", tmp_path)
    assert projet.repliques == [RepliqueProjet()]
    assert projet.script == []


def test_deux_projets_du_meme_nom(gestion, tmp_path):
    a = gestion.creer("Test", tmp_path)
    b = gestion.creer("Test", tmp_path)
    assert a.dossier != b.dossier
    assert b.dossier.name == "Test (2)"


def test_nom_vide_refuse(gestion, tmp_path):
    with pytest.raises(ErreurProjet):
        gestion.creer("   ", tmp_path)


def test_dossier_sans_projet(gestion, tmp_path):
    with pytest.raises(ErreurProjet, match="projet.json"):
        gestion.ouvrir(tmp_path)


def test_prises(gestion, tmp_path):
    projet = gestion.creer("P", tmp_path)
    p1 = gestion.ajouter_prise(WAV, **_infos())
    p2 = gestion.ajouter_prise(WAV, **_infos())
    assert (p1.nom, p2.nom) == ("Prise 1", "Prise 2")
    assert (projet.dossier / p2.fichier).read_bytes() == WAV
    gestion.modifier_prise(p1.identifiant, nom="Meilleure", note=5)
    gestion.supprimer_prise(p2.identifiant)
    assert not (projet.dossier / p2.fichier).exists()
    p3 = gestion.ajouter_prise(WAV, **_infos())
    assert p3.fichier.endswith("prise-002.wav")  # numéro libéré réutilisable, jamais de doublon
    rouvert = GestionnaireProjets(tmp_path / "recents.json").ouvrir(projet.dossier)
    assert [p.nom for p in rouvert.prises] == ["Meilleure", "Prise 2"]
    assert rouvert.prises[0].note == 5


def test_projets_recents(gestion, tmp_path):
    a = gestion.creer("A", tmp_path)
    gestion.creer("B", tmp_path)
    gestion.ouvrir(a.dossier)
    assert [nom for nom, _ in gestion.recents()] == ["A", "B"]
    assert gestion.dernier_projet() == a.dossier


def test_notification_du_projet_ouvert(gestion, tmp_path):
    vus = []
    gestion.abonner(vus.append)
    projet = gestion.creer("A", tmp_path)
    gestion.fermer()
    assert vus == [projet, None]
