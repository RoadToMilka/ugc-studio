"""Étape 8 (§7, §3.3, §8.1) — page Sous-titres : mots, réglages, prise → sous-titres, export SRT."""

from decimal import Decimal

import pytest

from ugc_studio.audio import wav_depuis_pcm
from ugc_studio.fournisseurs.base import Adaptateur, ErreurFournisseur
from ugc_studio.fournisseurs.stt import MotTranscrit, ResultatTranscription
from ugc_studio.projets import FICHIER_AUDIO
from ugc_studio.sources import SOURCE_IMPORTEE, SOURCE_TRANSCRIPTION
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
    assert atelier.titre.text() == "Sous-titres / Sérum"
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
    atelier.casse.setCurrentIndex(atelier.casse.findData("majuscules"))
    assert atelier.sous_titres[0].texte == "FRANCHEMENT,"
    atelier.ponctuation.setChecked(False)
    assert atelier.sous_titres[0].texte == "FRANCHEMENT"
    atelier.masquer.setChecked(False)  # réglage partagé avec la transcription
    assert "EUH" in [s.texte for s in atelier.sous_titres]
    assert not services.projets.projet.transcription.masquer_hesitations
    # Réglages enregistrés dans le projet.
    services.projets.ouvrir(services.projets.projet.dossier)
    reglages = services.projets.projet.sous_titres
    assert (reglages.mots_max, reglages.texte.casse, reglages.texte.ponctuation) == (1, "majuscules", False)
    assert atelier.mots_max.value() == 1 and atelier.casse.currentData() == "majuscules"


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
    projet = services.projets.projet
    # V3.1, lot 6 : des mots importés, choisis ; le module Transcription garde les siens (aucun ici).
    transcription = projet.sous_titres_importes
    assert projet.transcription is None and projet.sources.sous_titres == SOURCE_IMPORTEE
    # Orthographe du script (majuscules, ponctuation, nom de marque), temps de la transcription.
    assert [m.texte for m in transcription.mots] == ["Franchement,", "ce", "sérum", "Glowzy", "est", "top !"]
    assert (transcription.mots[3].debut, transcription.mots[3].fin) == (1.2, 1.7)
    assert transcription.prise == prise.identifiant and transcription.source == prise.nom
    # La piste son est celle de la prise elle-même (plus de copie dans celle du module Transcription).
    assert transcription.audio == prise.fichier and not projet.chemin(FICHIER_AUDIO).exists()
    (appel,) = services.couts.lire()
    assert appel.operation == "transcription" and Decimal(transcription.cout_eur) == appel.cout_eur
    assert atelier.sous_titres and "voix générée" in atelier.texte_source.text()
    assert atelier.source.choix_mots.valeur() == SOURCE_IMPORTEE
    assert taches.en_cours() == 0


def test_une_prise_ne_remplace_plus_la_transcription(atelier, qtbot, services):
    """V3.1, lot 6 : les sous-titres d'une prise s'ajoutent aux mots du module Transcription, qui
    restent ; on passe de l'une à l'autre sans rien perdre, retouches comprises."""
    prise = _prise(services)
    _pub_en_sous_titres(atelier, services)  # « Mais ce sérum », « Glowzy a vraiment »…
    video = services.projets.projet.transcription
    atelier.choisir_sous_titre(0)
    atelier.couper_avant(1)  # une retouche des sous-titres de la vidéo : « Mais » | « ce sérum »
    de_la_video = [s.texte for s in atelier.sous_titres]
    assert de_la_video[:2] == ["Mais", "ce sérum"]
    atelier.creer_depuis_prise(prise.identifiant)
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "succes", timeout=10_000)
    projet = services.projets.projet
    assert projet.transcription is video and len(video.ajustements_sous_titres) == 2  # rien n'est remplacé
    assert projet.sous_titres_importes.prise == prise.identifiant
    assert [s.texte for s in atelier.sous_titres] != de_la_video
    # La vidéo du module et les mots d'une prise : « La voix commence à » les cale.
    assert not atelier.source.ligne_decalage.isHidden()
    atelier.source.choix_mots.bouton(SOURCE_TRANSCRIPTION).click()
    assert projet.sources.sous_titres == SOURCE_TRANSCRIPTION and [s.texte for s in atelier.sous_titres] == de_la_video
    assert "pub.mp4" in atelier.texte_source.text() and atelier.source.ligne_decalage.isHidden()
    atelier.source.choix_mots.bouton(SOURCE_IMPORTEE).click()
    assert "voix générée" in atelier.texte_source.text() and atelier.sous_titres[0].texte.startswith("Franchement")


def test_nouvel_import_apres_confirmation_si_retouches(atelier, qtbot, services, monkeypatch):
    """Un nouvel import remplace l'import précédent : il demande d'abord s'il avait des retouches."""
    prise = _prise(services)
    atelier.rafraichir()
    atelier.creer_depuis_prise(prise.identifiant)
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "succes", timeout=10_000)
    importes = services.projets.projet.sous_titres_importes
    questions = []
    monkeypatch.setattr(atelier, "_confirmer_remplacement", lambda actuelle: questions.append(actuelle) or False)
    atelier.creer_depuis_prise(prise.identifiant)  # sans retouche : remplacé sans question
    qtbot.waitUntil(lambda: services.projets.projet.sous_titres_importes is not importes, timeout=10_000)
    assert questions == [] and len(FauxTranscripteur.requetes) == 2
    importes = services.projets.projet.sous_titres_importes
    importes.corrigee = True  # une retouche : un mot corrigé
    atelier.creer_depuis_prise(prise.identifiant)
    assert questions == [importes] and len(FauxTranscripteur.requetes) == 2  # « Annuler » : rien n'est envoyé
    assert services.projets.projet.sous_titres_importes is importes


def test_erreur_de_transcription_de_la_prise(atelier, qtbot, services):
    prise = _prise(services)
    atelier.rafraichir()
    FauxTranscripteur.echec = "Limite d'utilisation atteinte chez Google."
    atelier.creer_depuis_prise(prise.identifiant)
    qtbot.waitUntil(lambda: atelier.statut.property("role") == "erreur", timeout=10_000)
    assert "Limite d'utilisation" in atelier.statut.text()
    projet = services.projets.projet
    assert projet.transcription is None and projet.sous_titres_importes is None  # rien n'est remplacé
    assert not projet.chemin(FICHIER_AUDIO).exists()
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
    # L'aperçu (V2) montre ce sous-titre : la lecture s'est placée à son début.
    assert atelier.toile.sous_titre is atelier.sous_titres[dernier]
    assert atelier.lecteur.temps == atelier.sous_titres[dernier].debut


# --- V1.1 : réorganiser les sous-titres à la main ---------------------------------------------

MOTS_PUB = [
    ("Mais", 0.0, 0.3),
    ("ce", 0.35, 0.5),
    ("sérum", 0.55, 0.9),
    ("Glowzy", 0.95, 1.4),
    ("a", 1.45, 1.5),
    ("vraiment", 1.55, 2.0),
    ("changé", 2.05, 2.4),
    ("ma", 2.45, 2.6),
    ("peau", 2.65, 3.0),
    ("en", 3.05, 3.15),
    ("deux", 3.2, 3.5),
    ("semaines", 3.55, 4.0),
    ("!", 4.0, 4.05),
]


def _textes(atelier) -> list[str]:
    return [s.texte.replace("\n", " ").replace(" ", " ") for s in atelier.sous_titres]


def _pub_en_sous_titres(atelier, services) -> None:
    """4 sous-titres de 3 mots : « Mots au plus » réglé sur 3, « Caractères au plus » sur 40."""
    from ugc_studio.sous_titres import ReglagesSousTitres

    _transcription_video(services, [Mot(texte, debut, fin) for texte, debut, fin in MOTS_PUB])
    services.projets.projet.sous_titres = ReglagesSousTitres(caracteres_max=40, mots_max=3)
    atelier.rafraichir()
    assert _textes(atelier) == ["Mais ce sérum", "Glowzy a vraiment", "changé ma peau", "en deux semaines !"]


def test_actions_selon_le_sous_titre_choisi(atelier, services):
    _pub_en_sous_titres(atelier, services)
    boutons = (atelier.bouton_monter, atelier.bouton_descendre, atelier.bouton_couper, atelier.bouton_fusionner)
    assert not any(b.isEnabled() for b in boutons) and not atelier.bouton_retablir.isEnabled()
    atelier.choisir_sous_titre(0)
    assert not atelier.bouton_monter.isEnabled() and atelier.bouton_descendre.isEnabled() and atelier.bouton_couper.isEnabled()
    assert atelier.bouton_descendre.toolTip() == "« sérum » passe au début du sous-titre 2"
    atelier.choisir_sous_titre(3)
    assert atelier.bouton_monter.isEnabled() and not atelier.bouton_descendre.isEnabled()
    assert not atelier.bouton_fusionner.isEnabled()
    assert atelier.bouton_monter.toolTip() == "« en » passe à la fin du sous-titre 3"


def test_action_refusee_avec_la_raison(atelier, services):
    _pub_en_sous_titres(atelier, services)
    atelier.choisir_sous_titre(1)
    atelier.monter_premier_mot()
    assert atelier.statut_ajustements.isVisible() and atelier.statut_ajustements.property("role") == "erreur"
    assert atelier.statut_ajustements.text() == (
        "Impossible : le sous-titre 1 aurait 4 mots, et « Mots au plus » est réglé sur 3."
    )
    assert services.projets.projet.transcription.ajustements_sous_titres == []
    assert _textes(atelier)[:2] == ["Mais ce sérum", "Glowzy a vraiment"]  # rien n'a changé


def test_couper_monter_retablir(atelier, services, tmp_path, monkeypatch):
    _pub_en_sous_titres(atelier, services)
    atelier.choisir_sous_titre(0)
    atelier._remplir_menu_couper()  # ce que fait le menu « Couper » en s'ouvrant
    actions = atelier.menu_couper.actions()
    assert [a.text() for a in actions] == ["Couper avant « ce »", "Couper avant « sérum »"]
    actions[0].trigger()
    assert _textes(atelier)[:3] == ["Mais", "ce sérum", "Glowzy a vraiment"]
    assert atelier.statut_ajustements.property("role") == "succes"
    assert atelier.statut_ajustements.text() == "Sous-titre 1 coupé avant « ce »."
    assert atelier.tableau.item(0, 3).text() == "Ajusté à la main" == atelier.tableau.item(1, 3).text()
    assert atelier.tableau.item(2, 3).text() == ""
    assert "2 ajustés à la main" in atelier.resume.text() and atelier.tableau.currentRow() == 0
    # Le temps des mots ne change pas : chaque sous-titre commence avec son premier mot.
    assert [s.debut for s in atelier.sous_titres[:2]] == [0.0, 0.35]

    atelier.choisir_sous_titre(1)
    atelier.monter_premier_mot()
    assert _textes(atelier)[:2] == ["Mais ce", "sérum"]
    assert atelier.statut_ajustements.text() == "« ce » passe à la fin du sous-titre 1."

    # Enregistré dans le projet, retrouvé à la réouverture, et repris tel quel dans le SRT.
    services.projets.ouvrir(services.projets.projet.dossier)
    assert len(services.projets.projet.transcription.ajustements_sous_titres) == 2
    assert _textes(atelier)[:2] == ["Mais ce", "sérum"]
    monkeypatch.setattr(atelier, "_demander_fichier", lambda _proposition: tmp_path / "pub.srt")
    atelier.exporter_srt()
    texte = (tmp_path / "pub.srt").read_bytes().decode("utf-8-sig")
    assert "\r\nMais ce\r\n\r\n2\r\n" in texte and texte.count(" --> ") == len(atelier.sous_titres)

    atelier.choisir_sous_titre(1)
    atelier.retablir(tous=False)
    assert atelier.statut_ajustements.text() == "Sous-titre 2 : découpage automatique rétabli."
    assert len(services.projets.projet.transcription.ajustements_sous_titres) == 1
    atelier.retablir(tous=True)
    assert services.projets.projet.transcription.ajustements_sous_titres == []
    assert _textes(atelier) == ["Mais ce sérum", "Glowzy a vraiment", "changé ma peau", "en deux semaines !"]
    assert not atelier.bouton_retablir.isEnabled()


def test_reglage_qui_defait_un_ajustement_demande_d_abord(atelier, services, monkeypatch):
    from ugc_studio.ui import sous_titres_du_projet

    _pub_en_sous_titres(atelier, services)
    atelier.choisir_sous_titre(0)
    atelier.couper_avant(2)  # « Mais ce » | « sérum »
    assert _textes(atelier)[:2] == ["Mais ce", "sérum"]
    questions, reponse = [], {"appliquer": False}

    def demander(_parent, texte, plusieurs):
        questions.append((texte, plusieurs))
        return reponse["appliquer"]

    monkeypatch.setattr(sous_titres_du_projet, "demander", demander)
    atelier.mots_max.setValue(1)  # « Mais ce » (2 mots) ne tiendrait plus
    assert questions == [("Ce réglage défait ton ajustement du sous-titre 1 (« Mais ce ») : 2 mots, pour 1 au plus.", False)]
    # « Garder le réglage actuel » : rien ne change.
    assert atelier.mots_max.value() == 3 and services.projets.projet.sous_titres.mots_max == 3
    assert len(services.projets.projet.transcription.ajustements_sous_titres) == 2
    # « Appliquer et défaire cet ajustement ».
    reponse["appliquer"] = True
    atelier.mots_max.setValue(1)
    assert services.projets.projet.sous_titres.mots_max == 1
    assert len(services.projets.projet.transcription.ajustements_sous_titres) == 1  # « sérum » (1 mot) tient
    assert [s.texte for s in atelier.sous_titres if s.ajuste] == ["sérum"]
    # Un réglage sans conflit ne demande rien.
    questions.clear()
    atelier.duree_min.setValue(1.0)
    assert questions == []


def test_mots_corriges_dans_transcription_defont_un_ajustement(atelier, services):
    from ugc_studio.transcription import corriger

    _pub_en_sous_titres(atelier, services)
    atelier.choisir_sous_titre(0)
    atelier.couper_avant(2)  # « Mais ce » | « sérum »
    corriger(services.projets.projet.transcription.mots, 1, "c" * 40)  # corrigé dans le module Transcription
    atelier.rafraichir()  # retour sur la page Sous-titres
    assert atelier.statut_ajustements.property("role") == "avertissement"
    texte = atelier.statut_ajustements.text()
    assert texte.startswith("Des mots ont changé dans le module Transcription : ton ajustement du sous-titre 1 (« Mais ccc")
    assert texte.endswith("ne tient plus (45 caractères, pour 40 au plus). Il revient au découpage automatique.")
    assert len(services.projets.projet.transcription.ajustements_sous_titres) == 1  # « sérum » tient toujours
