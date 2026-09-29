"""Données de démonstration, utilisées uniquement par l'autotest de la fabrication automatique.

Elles remplissent un dossier temporaire (jamais les vraies données) pour que les captures
d'écran montrent des écrans réalistes : deux clés, quelques appels payants.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .services import Services

CLE_DEMO = "AIzaDEMO-cle-de-demonstration-0000-4f2c"


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
