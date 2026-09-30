"""Ce que l'app retient des voix (§5.4) et assistant de description Voice Design (§5.4 bis)."""

from datetime import datetime, timedelta

from ugc_studio import voix_locales
from ugc_studio.fournisseurs.voix import VoixBibliotheque
from ugc_studio.voice_design import assembler_description, code_genre
from ugc_studio.voix_locales import GestionnaireVoix, date_lisible, est_expiree

CAMILLE = VoixBibliotheque("camille", "Camille", "Warm narrator.", "fr-FR", accent="Parisian", genre="female")
LEA = VoixBibliotheque("voice_lea", "Léa", "A young woman.", "fr-FR", type="prompted", modele="gemini-3.8-flash-tts")


def test_favoris_et_noms_gardes(tmp_path):
    voix = GestionnaireVoix(tmp_path / "voix.json")
    appels = []
    voix.abonner(lambda: appels.append(True))
    assert voix.basculer_favori("Kore") is True
    voix.definir_voix_creees([LEA])
    voix.renommer("voice_lea", "  Léa   UGC ")
    voix.definir_description_fr("voice_lea", "Jeune femme.")
    relu = GestionnaireVoix(tmp_path / "voix.json")
    assert relu.favoris() == ["Kore"] and relu.est_favori("Kore")
    assert relu.nom("voice_lea") == "Léa UGC" and relu.description_fr("voice_lea") == "Jeune femme."
    assert relu.voix_creees() == [LEA]
    assert appels  # les fenêtres ouvertes sont prévenues
    assert voix.basculer_favori("Kore") is False


def test_libelles(tmp_path):
    voix = GestionnaireVoix(tmp_path / "voix.json")
    voix.definir_bibliotheque([CAMILLE, LEA])  # une voix créée n'entre pas dans la bibliothèque
    voix.definir_voix_creees([LEA])
    assert voix.libelle("Kore") == "Kore · Ferme · féminine"
    assert voix.libelle("camille") == "Camille · féminine · Parisian"
    assert voix.libelle("voice_lea") == "Léa (ma voix)"
    assert voix.libelle("inconnue") == "inconnue"
    assert [v.identifiant for v in voix.bibliotheque()] == ["camille"]


def test_bibliotheque_gardee_une_semaine(tmp_path, monkeypatch):
    voix = GestionnaireVoix(tmp_path / "voix.json")
    assert not voix.bibliotheque_a_jour() and not voix.voix_creees_a_jour()
    voix.definir_bibliotheque([CAMILLE])
    voix.definir_voix_creees([LEA])
    assert voix.bibliotheque_a_jour() and voix.voix_creees_a_jour()
    plus_tard = datetime.now().astimezone() + timedelta(days=8)
    monkeypatch.setattr(voix_locales, "_maintenant", lambda: plus_tard)
    assert not voix.bibliotheque_a_jour() and not voix.voix_creees_a_jour()


def test_voix_supprimee_oubliee(tmp_path):
    voix = GestionnaireVoix(tmp_path / "voix.json")
    voix.ajouter_voix_creee(LEA)
    voix.basculer_favori("voice_lea")
    voix.renommer("voice_lea", "Léa")
    voix.retirer_voix("voice_lea")
    assert voix.voix_creees() == [] and not voix.est_favori("voice_lea") and voix.nom("voice_lea") == "voice_lea"


def test_dates_d_expiration():
    assert date_lisible("2027-09-30T10:00:00.123456789Z") == "30/09/2027"
    assert date_lisible("") == ""
    assert est_expiree(VoixBibliotheque("a", "a", expire_le="2020-01-01T00:00:00Z"))
    assert not est_expiree(VoixBibliotheque("a", "a", expire_le="2999-01-01T00:00:00Z"))
    assert not est_expiree(VoixBibliotheque("a", "a"))  # voix de Google : pas d'expiration


def test_assistant_de_description():
    anglais, francais = assembler_description(
        "femme", "environ 25 ans", "chaleureuse", "légèrement voilée", "parisien", "créateur·rice UGC"
    )
    assert anglais == (
        "A young woman in her mid-20s with a warm, slightly husky voice and a Parisian French accent. "
        "Spontaneous and playful, like a creator talking to a friend on camera."
    )
    assert francais.startswith("Jeune femme d'environ 25 ans, voix chaleureuse et légèrement voilée, accent parisien.")
    assert "Spontanée" in francais  # accordé au féminin
    assert assembler_description("homme", "environ 40 ans", "grave") == ("A man in his 40s with a deep voice.", "Homme d'environ 40 ans, voix grave.")
    assert code_genre("neutre") == "neutral" and code_genre("") == ""
