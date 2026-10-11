"""Les choix du module Doublons (V4.3) et les noms des cas, sans aucun calcul : la page les lit au
démarrage de l'app, sans charger numpy ni ONNX Runtime (qui ne le sont qu'à la première analyse).
"""

from __future__ import annotations

# « Méthode » (demande de l'utilisateur du 11/10/2026, 19 h 49)
SANS_IA = "sans_ia"  # copies seulement : identiques et même photo, prouvées sans IA
AVEC_IA = "avec_ia"  # copies et photos proches : aussi ce que l'IA juge proche
METHODES = {AVEC_IA: "Copies et photos proches (avec IA)", SANS_IA: "Copies seulement (sans IA)"}
METHODE_DE_DEPART = AVEC_IA

# « Comparer » (à partir de deux dossiers)
DANS_CHAQUE_DOSSIER = "dans"
ENTRE_LES_DOSSIERS = "entre"
LES_DEUX = "les_deux"
MODES = {DANS_CHAQUE_DOSSIER: "Dans chaque dossier", ENTRE_LES_DOSSIERS: "Entre les dossiers", LES_DEUX: "Les deux"}
MODE_DE_DEPART = LES_DEUX

# Le seuil : les paires en dessous ne sont pas montrées.
SEUIL_MIN, SEUIL_MAX = 50, 100
SEUIL_DE_DEPART = 85
MAX_PAIRES = 5000  # au-delà, seulement les plus proches (une sécurité : les lots de 200 photos en sont loin)

# Ce qu'est une paire (document V4.3, §4.3)
IDENTIQUES = "identiques"  # 100 % : le même fichier, ou les mêmes pixels (prouvé sans IA)
MEME_PHOTO = "meme_photo"  # 95 à 99 % : la même photo, modifiée (prouvé sans IA)
RESSEMBLANTES = "ressemblantes"  # 94 % au plus : estimé par l'IA
NOMS_DES_CAS = {IDENTIQUES: "Identiques", MEME_PHOTO: "Même photo", RESSEMBLANTES: "Ressemblantes"}

# Les étapes de l'analyse, pour son avancement (analyse.py)
PREPARATION = "preparation"  # les bibliothèques de calcul se recopient (la première fois seulement)
MODELE = "modele"  # le modèle d'IA se prépare
LECTURE = "lecture"  # les photos se lisent (sans IA)
IA = "ia"  # les photos se lisent et l'IA les décrit
COMPARAISON = "comparaison"  # les paires se comparent
