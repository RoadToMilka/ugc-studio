"""Données de démonstration, utilisées uniquement par l'autotest de la fabrication automatique.

Elles remplissent un dossier temporaire (jamais les vraies données) pour que les captures
d'écran montrent des écrans réalistes : deux clés, quelques appels payants, un projet avec
un script et des prises.
"""

from __future__ import annotations

import math
import struct
from datetime import datetime, timedelta

from .audio import FREQUENCE_TTS, wav_depuis_pcm
from .chemins import dossier_projets_defaut
from .services import Services

CLE_DEMO = "AIzaDEMO-cle-de-demonstration-0000-4f2c"

SCRIPT_DEMO = [
    {"texte": "Franchement, je n'y croyais pas… "},
    {"balise": "short pause"},
    {"texte": " Mais ce sérum a "},
    {"texte": "vraiment", "accentue": True},
    {"texte": " changé ma peau en deux semaines ! "},
    {"balise": "laugh"},
    {"texte": " Le lien est juste en dessous."},
]


def son_de_demonstration(secondes: float, frequence: float = 220.0) -> bytes:
    """Petit son doux (WAV) pour les prises de démonstration."""
    total = int(secondes * FREQUENCE_TTS)
    fondu = FREQUENCE_TTS // 20
    echantillons = bytearray()
    for i in range(total):
        volume = min(1.0, i / fondu, (total - i) / fondu) * 0.2
        echantillons += struct.pack("<h", int(volume * 32767 * math.sin(2 * math.pi * frequence * i / FREQUENCE_TTS)))
    return wav_depuis_pcm(bytes(echantillons))


def remplir_donnees_demo(services: Services) -> None:
    connexions = services.connexions
    if not connexions.lister():
        perso = connexions.ajouter("google", "Google perso", CLE_DEMO)
        connexions.enregistrer_test(
            perso.identifiant,
            True,
            "Clé valide — 42 modèles accessibles.",
            ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.5-transcribe", "gemini-3.5-flash"],
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

    if services.projets.projet is None and not services.projets.recents():
        projet = services.projets.creer("Sérum Glowzy", dossier_projets_defaut())
        projet.script = [dict(s) for s in SCRIPT_DEMO]
        projet.voix.style = "complice et enthousiaste, débit rapide"
        services.projets.enregistrer()
        for duree, voix, note, frequence in ((7.4, "Kore", 4, 220.0), (8.1, "Leda", 0, 262.0)):
            services.projets.ajouter_prise(
                son_de_demonstration(duree, frequence),
                modele="gemini-3.8-flash-tts",
                voix=voix,
                style=projet.voix.style,
                texte_api="…",
                script=[dict(s) for s in SCRIPT_DEMO],
                duree_s=duree,
                tokens_entree=120,
                tokens_sortie=int(duree * 25),
                cout_eur="0.0021",
                note=note,
            )
