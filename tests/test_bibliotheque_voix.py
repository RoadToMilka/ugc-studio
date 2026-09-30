"""Étape 5 (§5.4, §5.4 bis) : bibliothèque de voix filtrable, favoris, écoute, Voice Design."""

from dataclasses import replace

import pytest

from ugc_studio.audio import duree_wav, wav_depuis_pcm
from ugc_studio.demo import VOIX_CREEE_DEMO, VOIX_DEMO
from ugc_studio.fournisseurs.base import Adaptateur
from ugc_studio.fournisseurs.voix import ResultatVoix, VoixBibliotheque, VoixCreee
from ugc_studio.ui.pages.voix import PageVoix

WAV = wav_depuis_pcm(b"\x00\x00" * 2_400)


class FauxGoogleVoix(Adaptateur):
    identifiant = "google"
    nom = "Faux"
    appels: list = []
    bibliotheque = VOIX_DEMO

    def lister_modeles(self):
        return []

    def lister_voix(self, types=("prebuilt",)):
        FauxGoogleVoix.appels.append(("lister", types))
        return list(FauxGoogleVoix.bibliotheque) if "prebuilt" in types else [VOIX_CREEE_DEMO]

    def obtenir_voix(self, identifiant):
        FauxGoogleVoix.appels.append(("obtenir", identifiant))
        return replace(VOIX_CREEE_DEMO, identifiant=identifiant, extrait_wav=WAV)

    def creer_voix(self, requete):
        FauxGoogleVoix.appels.append(("creer", requete))
        numero = sum(1 for a in FauxGoogleVoix.appels if a[0] == "creer")
        voix = VoixBibliotheque(
            f"voice_{numero}", requete.nom, requete.description, requete.langue, genre=requete.genre,
            type="prompted", modele=requete.modele, expire_le="2027-09-30T10:00:00Z", extrait_wav=WAV,
        )
        return VoixCreee(voix, tokens_entree=40, tokens_sortie=300)

    def supprimer_voix(self, identifiant):
        FauxGoogleVoix.appels.append(("supprimer", identifiant))

    def generer_voix(self, requete):
        FauxGoogleVoix.appels.append(("tts", requete.voix))
        return ResultatVoix(WAV, duree_wav(WAV), tokens_entree=10, tokens_sortie=25)


@pytest.fixture
def atelier(app_configuree, qtbot, services, tmp_path, monkeypatch):
    from ugc_studio.ui import connexion_ia

    FauxGoogleVoix.appels = []
    monkeypatch.setattr(connexion_ia, "creer_adaptateur", lambda _f, _cle: FauxGoogleVoix("cle-factice-123456"))
    connexion = services.connexions.ajouter("google", "Perso", "AIza-cle-factice-123456")
    services.connexions.enregistrer_test(
        connexion.identifiant, True, "ok", ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
    )
    services.projets.creer("Sérum", tmp_path)
    page = PageVoix(services)
    qtbot.addWidget(page)
    return page.atelier


def _caches_a_jour(services, creees=()):
    """Bibliothèque et voix créées déjà connues : la fenêtre ne demande rien à Google."""
    services.voix.definir_bibliotheque(VOIX_DEMO)
    services.voix.definir_voix_creees(list(creees))


def _bibliotheque(services, atelier, qtbot, **options):
    from ugc_studio.ui.dialogues.voix import DialogueBibliothequeVoix

    dialogue = DialogueBibliothequeVoix(services, atelier.lecteur, atelier, **options)
    qtbot.addWidget(dialogue)
    return dialogue


def test_bibliotheque_chargee_puis_gardee(atelier, services, qtbot):
    from ugc_studio.ui import taches

    dialogue = _bibliotheque(services, atelier, qtbot)
    qtbot.waitUntil(lambda: services.voix.bibliotheque_a_jour() and taches.en_cours() == 0, timeout=5000)
    assert ("lister", ("prebuilt",)) in FauxGoogleVoix.appels
    # Au départ, la langue du projet (fr-FR) est choisie : 3 voix françaises de France.
    assert dialogue.filtre_langue.currentData() == "fr-FR"
    assert sorted(ligne.voix.identifiant for ligne in dialogue.lignes()) == ["demo-camille", "demo-hugo", "demo-ines"]
    dialogue.reject()
    FauxGoogleVoix.appels = []
    _bibliotheque(services, atelier, qtbot)
    assert ("lister", ("prebuilt",)) not in FauxGoogleVoix.appels  # gardée en mémoire une semaine


def test_langue_du_projet_meme_si_mes_voix_arrivent_d_abord(atelier, services, qtbot, monkeypatch):
    """Les deux listes (bibliothèque et « Mes voix ») sont demandées en même temps : la première
    arrivée n'a pas forcément de langues. La langue du projet est choisie dès qu'elle apparaît."""
    from ugc_studio.ui import taches

    monkeypatch.setattr(taches, "lancer", lambda *_args: None)  # les réponses arrivent « à la main »
    dialogue = _bibliotheque(services, atelier, qtbot)
    services.voix.definir_voix_creees([VOIX_CREEE_DEMO])  # « Mes voix » d'abord : pas encore de langue
    assert dialogue.filtre_langue.findData("fr-FR") < 0  # (et la liste des voix de Google n'est pas reconstruite)
    services.voix.definir_bibliotheque(VOIX_DEMO)  # puis la bibliothèque
    assert dialogue.filtre_langue.currentData() == "fr-FR"
    services.voix.definir_bibliotheque(VOIX_DEMO)  # une actualisation garde le choix
    assert dialogue.filtre_langue.currentData() == "fr-FR"


def test_filtres_recherche_et_favoris(atelier, services, qtbot):
    _caches_a_jour(services)
    dialogue = _bibliotheque(services, atelier, qtbot)
    dialogue.filtre_langue.setCurrentIndex(0)  # toutes les langues
    assert len(dialogue.lignes()) == len(VOIX_DEMO)
    dialogue.filtre_genre.setCurrentIndex(dialogue.filtre_genre.findData("male"))
    assert {ligne.voix.identifiant for ligne in dialogue.lignes()} == {"demo-hugo", "demo-lucas"}
    dialogue.filtre_hauteur.setCurrentIndex(dialogue.filtre_hauteur.findData("low"))
    assert [ligne.voix.identifiant for ligne in dialogue.lignes()] == ["demo-hugo"]
    dialogue.filtre_genre.setCurrentIndex(0)
    dialogue.filtre_hauteur.setCurrentIndex(0)
    # La recherche attend une courte pause dans la frappe avant de filtrer.
    dialogue.recherche.setText("social")
    assert len(dialogue.lignes()) == len(VOIX_DEMO)
    qtbot.waitUntil(lambda: [ligne.voix.identifiant for ligne in dialogue.lignes()] == ["demo-ines"], timeout=2000)
    dialogue.recherche.clear()
    qtbot.waitUntil(lambda: len(dialogue.lignes()) == len(VOIX_DEMO), timeout=2000)
    # Favori ★ : la voix passe en tête, et le filtre « Favoris seulement » la garde seule.
    ava = next(ligne for ligne in dialogue.lignes() if ligne.voix.identifiant == "demo-ava")
    dialogue.basculer_favori(ava)
    assert services.voix.est_favori("demo-ava")
    dialogue.favoris_seulement.setChecked(True)
    assert [ligne.voix.identifiant for ligne in dialogue.lignes()] == ["demo-ava"]


def test_choisir_une_voix_pour_le_projet(atelier, services, qtbot):
    _caches_a_jour(services)
    dialogue = _bibliotheque(services, atelier, qtbot)
    hugo = next(ligne for ligne in dialogue.lignes() if ligne.voix.identifiant == "demo-hugo")
    dialogue.choisir(hugo.voix)
    atelier.choisir_voix(dialogue.voix_choisie)
    assert atelier.voix.currentData() == "demo-hugo"
    assert "Hugo" in atelier.voix.currentText()
    atelier.enregistrer_maintenant()
    assert services.projets.projet.voix.voix == "demo-hugo"


def test_favoris_en_tete_de_la_liste_des_voix(atelier, services):
    services.voix.definir_bibliotheque(VOIX_DEMO)
    services.voix.basculer_favori("demo-camille")
    assert atelier.voix.itemText(0).startswith("★ Camille")
    assert atelier.voix.itemData(0) == "demo-camille"
    assert atelier.voix.findData("Kore") > 0  # les 30 voix de base restent là


def test_voix_creee_prend_son_modele(atelier, services):
    services.voix.definir_voix_creees([replace(VOIX_CREEE_DEMO, modele="gemini-3.8-flash-lite-tts")])
    atelier.choisir_voix(VOIX_CREEE_DEMO)
    assert atelier.voix.currentData() == "voice_demo_lea"
    assert atelier.modele.currentData() == "gemini-3.8-flash-lite-tts"


def test_ecouter_une_voix_creee_sans_frais(atelier, services, qtbot):
    services.voix.definir_voix_creees([VOIX_CREEE_DEMO])
    atelier.choisir_voix(VOIX_CREEE_DEMO)
    atelier.ecouter_extrait()
    qtbot.waitUntil(lambda: ("obtenir", "voice_demo_lea") in FauxGoogleVoix.appels, timeout=5000)
    from ugc_studio.ui.extraits import fichier_extrait_google

    qtbot.waitUntil(lambda: fichier_extrait_google("voice_demo_lea").exists(), timeout=5000)
    assert services.couts.lire() == []  # l'extrait fourni par Google ne coûte rien
    assert not any(a[0] == "tts" for a in FauxGoogleVoix.appels)


def test_ecouter_une_voix_de_base_genere_une_phrase(atelier, services, qtbot):
    atelier.ecouter_extrait()  # Kore : phrase d'exemple dans la langue du projet
    qtbot.waitUntil(lambda: len(services.couts.lire()) == 1, timeout=5000)
    (appel,) = services.couts.lire()
    assert appel.operation == "essai de voix"
    assert ("tts", "Kore") in FauxGoogleVoix.appels


def test_mes_voix_supprimer(atelier, services, qtbot):
    _caches_a_jour(services, [VOIX_CREEE_DEMO])
    dialogue = _bibliotheque(services, atelier, qtbot, onglet=1)
    assert dialogue.compteur.text() == "1 / 200 voix créées"
    (ligne,) = dialogue.lignes_creees()
    dialogue.supprimer(ligne.voix, confirmer=False)
    qtbot.waitUntil(lambda: services.voix.voix_creees() == [], timeout=5000)
    assert ("supprimer", "voice_demo_lea") in FauxGoogleVoix.appels
    assert dialogue.compteur.text() == "0 / 200 voix créées"


# --- Voice Design -----------------------------------------------------------------------------


def _voice_design(services, atelier, qtbot):
    from ugc_studio.ui.dialogues.voice_design import DialogueVoiceDesign

    dialogue = DialogueVoiceDesign(services, atelier.ecoute, atelier)
    qtbot.addWidget(dialogue)
    return dialogue


def test_creer_une_voix_puis_l_utiliser(atelier, services, qtbot):
    dialogue = _voice_design(services, atelier, qtbot)
    dialogue.creer()
    assert "nom" in dialogue.statut.text()
    dialogue.nom.setText("Léa")
    dialogue.creer()
    assert "description" in dialogue.statut.text()
    dialogue.description.definir("A young woman in her mid-20s with a warm voice.", "Jeune femme d'environ 25 ans.")
    dialogue.genre.setCurrentIndex(dialogue.genre.findData("female"))
    dialogue.creer()
    qtbot.waitUntil(lambda: len(dialogue.versions()) == 1, timeout=5000)
    (creation,) = [a[1] for a in FauxGoogleVoix.appels if a[0] == "creer"]
    assert (creation.nom, creation.langue, creation.genre, creation.modele) == (
        "Léa", "fr-FR", "female", "gemini-3.8-flash-tts",
    )
    assert services.voix.voix("voice_1").creee
    assert services.voix.description_fr("voice_1") == "Jeune femme d'environ 25 ans."
    (appel,) = services.couts.lire()
    assert (appel.operation, appel.tokens_entree, appel.tokens_sortie) == ("création de voix", 40, 300)
    from ugc_studio.ui.extraits import fichier_extrait_google

    assert fichier_extrait_google("voice_1").exists()  # l'extrait est gardé (et joué)
    assert dialogue.bouton_creer.text() == "Créer une autre version"

    # Deuxième version, puis on supprime la première et on garde la seconde.
    dialogue.creer()
    qtbot.waitUntil(lambda: len(dialogue.versions()) == 2, timeout=5000)
    dialogue.supprimer(dialogue.versions()[0])
    qtbot.waitUntil(lambda: len(dialogue.versions()) == 1, timeout=5000)
    assert services.voix.voix("voice_1") is None
    dialogue.utiliser(dialogue.versions()[0].voix)
    assert dialogue.voix_creee.identifiant == "voice_2"


def test_assistant_de_description_reporte_le_genre(atelier, services, qtbot):
    from ugc_studio.ui.dialogues.assistant_voix import DialogueAssistantVoix

    dialogue = _voice_design(services, atelier, qtbot)
    assistant = DialogueAssistantVoix()
    qtbot.addWidget(assistant)
    assistant.genre.setCurrentIndex(assistant.genre.findData("homme"))
    assistant.age.setCurrentIndex(assistant.age.findData("environ 40 ans"))
    assistant.timbre.setCurrentIndex(assistant.timbre.findData("grave"))
    assert assistant.resultat()[0] == "A man in his 40s with a deep voice."
    dialogue.description.definir(*assistant.resultat())
    dialogue.description.assistant_utilise.emit(assistant)
    assert dialogue.genre.currentData() == "male"


def test_description_en_francais_signalee(atelier, services, qtbot):
    dialogue = _voice_design(services, atelier, qtbot)
    dialogue.description.champ.setPlainText("Jeune femme, voix douce.")
    assert any("anglais" in message for message in dialogue.description.avertissements())
    dialogue.description.champ.setPlainText("One. Two. Three sentences here.")
    assert any("longue" in message for message in dialogue.description.avertissements())


# --- Bibliothèque plus rapide (V1.1, lot 4) ---------------------------------------------------


def _beaucoup_de_voix(nombre: int) -> list[VoixBibliotheque]:
    return [
        VoixBibliotheque(f"voix-{n:03d}", f"Voix {n:03d}", "", "fr-FR", genre="female" if n % 2 else "male")
        for n in range(nombre)
    ]


def test_vingt_voix_puis_vingt_de_plus(atelier, services, qtbot):
    services.voix.definir_bibliotheque(_beaucoup_de_voix(45))
    services.voix.definir_voix_creees([])
    dialogue = _bibliotheque(services, atelier, qtbot)
    assert len(dialogue.lignes()) == 20
    assert dialogue.info_liste.text() == "45 voix."
    assert dialogue.bouton_plus.text() == "Afficher 20 voix de plus (25 restantes)"
    premieres = dialogue.lignes()
    dialogue.bouton_plus.click()
    assert len(dialogue.lignes()) == 40 and dialogue.lignes()[:20] == premieres  # rien n'est reconstruit
    assert dialogue.bouton_plus.text() == "Afficher les 5 dernières voix"
    dialogue.bouton_plus.click()
    assert len(dialogue.lignes()) == 45 and dialogue.bouton_plus.isHidden()
    # Un filtre change : le nombre exact de voix trouvées, et de nouveau les 20 premières.
    dialogue.filtre_genre.setCurrentIndex(dialogue.filtre_genre.findData("female"))
    assert dialogue.info_liste.text() == "22 voix (sur 45)."
    assert len(dialogue.lignes()) == 20 and not dialogue.bouton_plus.isHidden()


def test_une_etoile_ne_reconstruit_rien(atelier, services, qtbot):
    _caches_a_jour(services)
    dialogue = _bibliotheque(services, atelier, qtbot)
    lignes = dialogue.lignes()
    dialogue.basculer_favori(lignes[1])
    assert dialogue.lignes() == lignes  # mêmes lignes : seule l'étoile a changé
    assert services.voix.est_favori(lignes[1].voix.identifiant)
    assert lignes[1].etoile.toolTip() == "Retirer des favoris"


def test_une_seule_construction_a_l_ouverture(atelier, services, qtbot, monkeypatch):
    """« Mes voix » est redemandée à Google à l'ouverture (au plus une fois par heure) : sa réponse
    ne reconstruit pas la liste des voix de Google."""
    from ugc_studio.ui import taches
    from ugc_studio.ui.dialogues import voix as module

    services.voix.definir_bibliotheque(VOIX_DEMO)  # bibliothèque à jour, « Mes voix » à redemander
    construites = []

    class LigneComptee(module.LigneVoix):
        def __init__(self, dialogue, voix):
            construites.append(voix.identifiant)
            super().__init__(dialogue, voix)

    monkeypatch.setattr(module, "LigneVoix", LigneComptee)
    dialogue = _bibliotheque(services, atelier, qtbot)
    qtbot.waitUntil(lambda: services.voix.voix_creees_a_jour() and taches.en_cours() == 0, timeout=5000)
    google = [identifiant for identifiant in construites if identifiant.startswith("demo-")]
    assert sorted(google) == sorted(ligne.voix.identifiant for ligne in dialogue.lignes())  # une seule fois chacune
    assert [ligne.voix.identifiant for ligne in dialogue.lignes_creees()] == ["voice_demo_lea"]
