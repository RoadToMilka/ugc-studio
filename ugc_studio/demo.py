"""Données de démonstration, utilisées uniquement par l'autotest de la fabrication automatique.

Elles remplissent un dossier temporaire (jamais les vraies données) pour que les captures
d'écran montrent des écrans réalistes : deux clés, quelques appels payants, un projet avec
un script et des prises.
"""

from __future__ import annotations

import math
import struct
from dataclasses import replace
from datetime import datetime, timedelta

from .fournisseurs.voix import VoixBibliotheque

from .audio import FREQUENCE_TTS, wav_depuis_pcm
from .chemins import dossier_projets_defaut
from .projets import RepliqueProjet
from .prononciation import Prononciation
from .script import joindre_repliques
from .services import Services

CLE_DEMO = "AIzaDEMO-cle-de-demonstration-0000-4f2c"

# Deux répliques : un hook enthousiaste, puis un appel à l'action chaleureux.
REPLIQUES_DEMO = [
    RepliqueProjet(
        [
            {"texte": "Franchement, je n'y croyais pas… "},
            {"balise": "short pause"},
            {"texte": " Mais ce sérum Glowzy a "},
            {"texte": "vraiment", "accentue": True},
            {"texte": " changé ma peau en deux semaines ! "},
            {"balise": "laugh"},
        ],
        "excited and playful, fast-paced",
        "excité et complice, débit rapide",
    ),
    RepliqueProjet([{"texte": "Le lien est juste en dessous."}], "warm and reassuring", "chaleureux et rassurant"),
]
SCRIPT_DEMO = REPLIQUES_DEMO[0].script  # 1re réplique (vérifiée par l'autotest dans l'éditeur)


def son_de_demonstration(secondes: float, frequence: float = 220.0) -> bytes:
    """Petit son doux (WAV) pour les prises de démonstration."""
    total = int(secondes * FREQUENCE_TTS)
    fondu = FREQUENCE_TTS // 20
    echantillons = bytearray()
    for i in range(total):
        volume = min(1.0, i / fondu, (total - i) / fondu) * 0.2
        echantillons += struct.pack("<h", int(volume * 32767 * math.sin(2 * math.pi * frequence * i / FREQUENCE_TTS)))
    return wav_depuis_pcm(bytes(echantillons))


# Bibliothèque de voix de démonstration (noms marqués « démo » : ce ne sont pas de vraies voix Google).
VOIX_DEMO = [
    VoixBibliotheque("demo-camille", "Camille (démo)", "Warm and friendly narrator with a clear, smiling delivery.",
                     "fr-FR", "FR", "Parisian", "female", "medium", "Warm, Friendly", "Commercial"),
    VoixBibliotheque("demo-hugo", "Hugo (démo)", "Deep, confident voice for premium product launches.",
                     "fr-FR", "FR", "Standard French", "male", "low", "Confident", "Narration"),
    VoixBibliotheque("demo-ines", "Inès (démo)", "Bright and playful voice, perfect for social media hooks.",
                     "fr-FR", "FR", "Southern French", "female", "high", "Playful", "Social media"),
    VoixBibliotheque("demo-lucas", "Lucas (démo)", "Relaxed, conversational voice with a soft Belgian accent.",
                     "fr-BE", "BE", "Belgian", "male", "medium", "Friendly", "Conversational"),
    VoixBibliotheque("demo-ava", "Ava (démo)", "Energetic American voice for upbeat ads.",
                     "en-US", "US", "American", "female", "medium", "Energetic", "Commercial"),
]
VOIX_CREEE_DEMO = VoixBibliotheque(
    "voice_demo_lea",
    "Léa — créatrice UGC (démo)",
    "A young woman in her mid-20s with a warm, slightly husky voice and a Parisian French accent. "
    "Spontaneous and playful, like a creator talking to a friend on camera.",
    "fr-FR",
    genre="female",
    type="prompted",
    modele="gemini-3.8-flash-tts",
)


def remplir_donnees_demo(services: Services) -> None:
    connexions = services.connexions
    if not connexions.lister():
        perso = connexions.ajouter("google", "Google perso", CLE_DEMO)
        connexions.enregistrer_test(
            perso.identifiant,
            True,
            "Clé valide — 42 modèles accessibles.",
            [
                "gemini-3.8-flash-tts",
                "gemini-3.8-flash-lite-tts",
                "gemini-3.5-transcribe",
                "gemini-3.5-transcribe-live",
                "gemini-3.1-flash-tts-preview",
                "gemini-3.5-flash",
            ],
        )
        ancienne = connexions.ajouter("google", "Ancienne clé", CLE_DEMO.replace("4f2c", "9a1b"))
        connexions.enregistrer_test(
            ancienne.identifiant,
            False,
            "Google refuse cette clé : elle n'est pas valide. Vérifie qu'elle a été copiée en entier.",
        )

    maintenant = datetime.now().astimezone().replace(microsecond=0)
    appels = [
        ("gemini-3.8-flash-tts", "voix", 412, 18_950, "Sérum Glowzy", timedelta(minutes=5)),
        ("gemini-3.8-flash-tts", "voix", 398, 17_400, "Sérum Glowzy", timedelta(minutes=12)),
        ("gemini-3.8-flash-lite-tts", "essai de voix", 24, 1_150, None, timedelta(hours=2)),
        ("gemini-3.5-transcribe", "transcription", 7_680, 612, "Brosse lissante", timedelta(hours=3)),
    ]
    if not services.couts.lire():
        for modele, operation, entree, sortie, projet, anciennete in appels:
            services.couts.enregistrer("google", modele, operation, entree, sortie, projet, maintenant - anciennete)

    if not services.voix.bibliotheque():
        services.voix.definir_bibliotheque(VOIX_DEMO)
        expiration = (datetime.now().astimezone() + timedelta(days=365)).isoformat(timespec="seconds")
        services.voix.definir_voix_creees([replace(VOIX_CREEE_DEMO, expire_le=expiration)])
        services.voix.definir_description_fr(
            VOIX_CREEE_DEMO.identifiant,
            "Jeune femme d'environ 25 ans, voix chaleureuse et légèrement voilée, accent parisien. "
            "Spontanée et complice, comme face caméra avec une amie.",
        )
        services.voix.basculer_favori("Puck")
        services.voix.basculer_favori("demo-camille")

    if services.projets.projet is None and not services.projets.recents():
        projet = services.projets.creer("Sérum Glowzy", dossier_projets_defaut())
        projet.repliques = [RepliqueProjet([dict(s) for s in r.script], r.style, r.style_fr) for r in REPLIQUES_DEMO]
        projet.prononciations = [Prononciation("Glowzy", "Glo-zi")]
        services.projets.enregistrer()
        for duree, voix, note, frequence in ((7.4, "Kore", 4, 220.0), (8.1, "Leda", 0, 262.0)):
            services.projets.ajouter_prise(
                son_de_demonstration(duree, frequence),
                modele="gemini-3.8-flash-tts",
                voix=voix,
                style="styles par réplique",
                texte_api="…",
                script=joindre_repliques([r.script for r in REPLIQUES_DEMO]),
                repliques=[{"texte_api": "…", "style": r.style} for r in REPLIQUES_DEMO],
                duree_s=duree,
                tokens_entree=120,
                tokens_sortie=int(duree * 25),
                cout_eur="0.0021",
                note=note,
            )
