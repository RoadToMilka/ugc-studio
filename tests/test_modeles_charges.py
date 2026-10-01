"""Modèles chargés et « Utilisé dans » (V1.1, modeles_charges.py)."""

from ugc_studio.fournisseurs.voix import VoixBibliotheque
from ugc_studio.modeles_charges import (
    MODELES_DE_DEPART,
    SOUS_TITRES,
    TRADUCTIONS,
    TRANSCRIPTION,
    VOIX,
    ModelesCharges,
)
from ugc_studio.styles import BibliothequeStyles
from ugc_studio.voix_locales import GestionnaireVoix


def _modeles(tmp_path) -> tuple[ModelesCharges, GestionnaireVoix, BibliothequeStyles]:
    voix = GestionnaireVoix(tmp_path / "voix.json")
    styles = BibliothequeStyles(tmp_path / "styles.json")
    return ModelesCharges(tmp_path / "modeles.json", voix, styles), voix, styles


def test_modeles_charges_au_depart(tmp_path):
    """Ceux dont l'app se sert, plus Flash-Lite TTS ; pas les anciennes générations."""
    modeles, _voix, _styles = _modeles(tmp_path)
    assert modeles.charges() == list(MODELES_DE_DEPART) == [
        "gemini-3.8-flash-tts",
        "gemini-3.8-flash-lite-tts",
        "gemini-3.5-transcribe",
        "gemini-3.8-flash",
    ]
    assert not modeles.est_charge("gemini-2.5-flash-preview-tts")


def test_utilise_dans(tmp_path):
    modeles, voix, _styles = _modeles(tmp_path)
    assert modeles.utilise_dans("gemini-3.8-flash") == [TRADUCTIONS]  # traductions des styles
    modeles.choisir(VOIX, "gemini-3.8-flash-tts")
    modeles.choisir(TRANSCRIPTION, "gemini-3.5-transcribe")
    modeles.choisir(SOUS_TITRES, "gemini-3.5-transcribe")
    assert modeles.utilise_dans("gemini-3.5-transcribe") == [TRANSCRIPTION, SOUS_TITRES]
    voix.definir_voix_creees(
        [VoixBibliotheque("voice_lea", "Léa", type="prompted", modele="gemini-3.8-flash-lite-tts")]
    )
    assert modeles.utilise_dans("gemini-3.8-flash-lite-tts") == [VOIX]  # modèle d'une voix créée
    modeles.choisir(VOIX, None)  # plus de projet ouvert
    assert modeles.utilise_dans("gemini-3.8-flash-tts") == [VOIX]  # … mais les styles d'exemple s'en servent


def test_un_modele_utilise_reste_charge(tmp_path):
    modeles, _voix, _styles = _modeles(tmp_path)
    modeles.choisir(TRANSCRIPTION, "gemini-3.5-transcribe")
    modeles.definir(["gemini-3.8-flash-tts"])  # on décoche tout le reste
    assert "gemini-3.5-transcribe" in modeles.charges()  # utilisé : il reste
    assert "gemini-3.8-flash" in modeles.charges()  # traductions
    assert "gemini-3.8-flash-lite-tts" not in modeles.charges()  # pas utilisé : retiré


def test_un_projet_recharge_son_modele(tmp_path):
    """Projet d'une version précédente, avec un modèle qui n'est plus chargé : il revient."""
    modeles, _voix, _styles = _modeles(tmp_path)
    changements = []
    modeles.abonner(lambda: changements.append(modeles.charges()))
    modeles.choisir(VOIX, "gemini-2.5-flash-preview-tts")
    assert modeles.est_charge("gemini-2.5-flash-preview-tts")
    assert changements and "gemini-2.5-flash-preview-tts" in changements[0]


def test_choix_garde(tmp_path):
    modeles, _voix, _styles = _modeles(tmp_path)
    modeles.definir([*MODELES_DE_DEPART, "gemini-2.5-pro-preview-tts"])
    relu, _voix2, _styles2 = _modeles(tmp_path)
    assert relu.est_charge("gemini-2.5-pro-preview-tts")
    assert relu.charges()[-1] == "gemini-2.5-pro-preview-tts"  # dans l'ordre du catalogue
