"""Les 30 voix de base de Gemini TTS (§5.4), avec leur caractère.

Le caractère (« Upbeat », « Firm »…) est celui donné par Google ; le genre est indicatif.
On peut écouter un extrait de chaque voix depuis l'app (bouton ▶).
"""

from __future__ import annotations

from .voix import VoixDeBase

VOIX_GOOGLE: tuple[VoixDeBase, ...] = (
    VoixDeBase("Zephyr", "Lumineuse", "Bright", "F"),
    VoixDeBase("Puck", "Enjouée", "Upbeat", "M"),
    VoixDeBase("Charon", "Informative", "Informative", "M"),
    VoixDeBase("Kore", "Ferme", "Firm", "F"),
    VoixDeBase("Fenrir", "Vive", "Excitable", "M"),
    VoixDeBase("Leda", "Jeune", "Youthful", "F"),
    VoixDeBase("Orus", "Ferme", "Firm", "M"),
    VoixDeBase("Aoede", "Légère", "Breezy", "F"),
    VoixDeBase("Callirrhoe", "Décontractée", "Easy-going", "F"),
    VoixDeBase("Autonoe", "Lumineuse", "Bright", "F"),
    VoixDeBase("Enceladus", "Soufflée", "Breathy", "M"),
    VoixDeBase("Iapetus", "Claire", "Clear", "M"),
    VoixDeBase("Umbriel", "Décontractée", "Easy-going", "M"),
    VoixDeBase("Algieba", "Veloutée", "Smooth", "M"),
    VoixDeBase("Despina", "Veloutée", "Smooth", "F"),
    VoixDeBase("Erinome", "Claire", "Clear", "F"),
    VoixDeBase("Algenib", "Rocailleuse", "Gravelly", "M"),
    VoixDeBase("Rasalgethi", "Informative", "Informative", "M"),
    VoixDeBase("Laomedeia", "Enjouée", "Upbeat", "F"),
    VoixDeBase("Achernar", "Douce", "Soft", "F"),
    VoixDeBase("Alnilam", "Ferme", "Firm", "M"),
    VoixDeBase("Schedar", "Posée", "Even", "M"),
    VoixDeBase("Gacrux", "Mûre", "Mature", "F"),
    VoixDeBase("Pulcherrima", "Assurée", "Forward", "F"),
    VoixDeBase("Achird", "Amicale", "Friendly", "M"),
    VoixDeBase("Zubenelgenubi", "Détendue", "Casual", "M"),
    VoixDeBase("Vindemiatrix", "Tendre", "Gentle", "F"),
    VoixDeBase("Sadachbia", "Pétillante", "Lively", "M"),
    VoixDeBase("Sadaltager", "Érudite", "Knowledgeable", "M"),
    VoixDeBase("Sulafat", "Chaleureuse", "Warm", "F"),
)

VOIX_PAR_DEFAUT = "Kore"

# Phrase lue par le bouton ▶ « écouter un extrait », selon la langue du projet.
PHRASES_EXTRAIT = {
    "fr": "Salut ! Voici un aperçu de ma voix pour ta prochaine publicité.",
    "en": "Hi! Here's a quick preview of my voice for your next ad.",
    "es": "¡Hola! Así suena mi voz para tu próximo anuncio.",
    "it": "Ciao! Ecco un'anteprima della mia voce per il tuo prossimo annuncio.",
    "nl": "Hoi! Zo klinkt mijn stem voor je volgende advertentie.",
    "de": "Hallo! So klingt meine Stimme für deine nächste Werbung.",
}


def voix_de_base(nom: str) -> VoixDeBase | None:
    return next((v for v in VOIX_GOOGLE if v.nom == nom), None)


def phrase_extrait(langue: str) -> str:
    return PHRASES_EXTRAIT.get(langue.split("-")[0], PHRASES_EXTRAIT["fr"])
