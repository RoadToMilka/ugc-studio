"""Traduire un style (ou une description de voix) du français vers l'anglais (§5.5).

Google conseille d'écrire les consignes de jeu en anglais. On peut les écrire en français, puis
cliquer « Traduire en anglais » : l'app demande la traduction à un modèle de texte Gemini, avec
la même clé API. Une traduction de quelques mots coûte une fraction de centime ; elle est notée
dans le suivi des coûts (« traduction »).
"""

from __future__ import annotations

from .fournisseurs.base import Adaptateur
from .fournisseurs.texte import RequeteTexte, ResultatTexte

MODELE_TRADUCTION = "gemini-3.8-flash"
# Niveau de réflexion le plus bas accepté par Gemini 3.8 Flash (documentation « Thinking ») :
# une traduction de quelques mots n'a pas besoin de plus.
REFLEXION_TRADUCTION = "low"
LONGUEUR_MAX = 1000  # caractères : un style fait quelques mots, une description 1 à 2 phrases

CONSIGNE_TRADUCTION = (
    "You translate voice-acting instructions for a text-to-speech model from French to English. "
    "The text is either a short delivery style (emotion, attitude, pace, volume) or a short voice "
    "description. Translate faithfully and concisely, in natural English, like the examples in "
    "Google's speech generation guide (e.g. 'warm and enthusiastic, fast-paced'). Do not add, "
    "explain or remove anything. If the text is already in English, return it unchanged. "
    "Reply with the English text only, without quotes."
)


def nettoyer_traduction(texte: str) -> str:
    """Retire les guillemets ou les retours à la ligne qu'un modèle ajoute parfois."""
    propre = " ".join(texte.split())
    for ouvrant, fermant in (('"', '"'), ("'", "'"), ("«", "»"), ("“", "”")):
        if len(propre) >= 2 and propre.startswith(ouvrant) and propre.endswith(fermant):
            propre = propre[len(ouvrant) : -len(fermant)].strip()
    return propre


def traduire_en_anglais(adaptateur: Adaptateur, texte: str, modele: str = MODELE_TRADUCTION) -> ResultatTexte:
    """Appel au modèle de texte — à lancer en tâche de fond."""
    texte = " ".join(texte.split())[:LONGUEUR_MAX]
    resultat = adaptateur.generer_texte(
        RequeteTexte(modele, texte, consigne_systeme=CONSIGNE_TRADUCTION, reflexion=REFLEXION_TRADUCTION)
    )
    resultat.texte = nettoyer_traduction(resultat.texte)
    return resultat
