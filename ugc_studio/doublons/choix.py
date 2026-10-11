"""Les choix du module Doublons (V4.3) et les noms des cas, sans aucun calcul : la page les lit au
démarrage de l'app, sans charger numpy ni ONNX Runtime (qui ne le sont qu'à la première analyse).
"""

from __future__ import annotations

# « Méthode » (demandes de l'utilisateur du 11/10/2026, 19 h 49 et 21 h 10). Les valeurs retenues dans
# les préférences ne changent pas d'une version à l'autre (« sans_ia » s'appelait « Copies seulement »
# en 4.3.0).
SANS_IA = "sans_ia"  # copies entières : identiques et même photo entière, prouvées sans IA
COPIES_IA = "copies_ia"  # toutes les copies : aussi recadrées, zoomées ou tournées, repérées par l'IA, prouvées sans elle
AVEC_IA = "avec_ia"  # copies et photos proches : aussi ce que l'IA juge proche, sans preuve
METHODES = {
    COPIES_IA: "Toutes les copies (avec IA)",
    AVEC_IA: "Copies et photos proches (avec IA)",
    SANS_IA: "Copies entières (sans IA)",
}
METHODE_DE_DEPART = COPIES_IA
METHODES_AVEC_IA = (COPIES_IA, AVEC_IA)

# « Comparer » (à partir de deux dossiers)
DANS_CHAQUE_DOSSIER = "dans"
ENTRE_LES_DOSSIERS = "entre"
LES_DEUX = "les_deux"
MODES = {DANS_CHAQUE_DOSSIER: "Dans chaque dossier", ENTRE_LES_DOSSIERS: "Entre les dossiers", LES_DEUX: "Les deux"}
MODE_DE_DEPART = LES_DEUX

# Le seuil : les paires en dessous ne sont pas montrées.
SEUIL_MIN, SEUIL_MAX = 50, 100
# 85 % : le plus bas pour ne trouver que de vrais doublons, réglé sur le lot de l'utilisateur (sa paire de
# photos différentes la plus proche, la même montre chez deux clients, est à 84 %). Rappelé à côté du seuil
# (demande de l'utilisateur du 11/10/2026, 21 h 28 : « que je me souvienne de ne pas mettre moins »).
SEUIL_DES_VRAIS_DOUBLONS = 85
SEUIL_DE_DEPART = SEUIL_DES_VRAIS_DOUBLONS
MAX_PAIRES = 5000  # au-delà, seulement les plus proches (une sécurité : les lots de 200 photos en sont loin)
# Sans les photos proches (copies entières, toutes les copies) : toutes les copies prouvées sont montrées,
# sans seuil (question de l'utilisateur du 11/10/2026, 21 h 14 : un seuil n'y sert à rien, toutes sont
# de vraies copies, de 95 à 100 %).
SEUIL_DES_COPIES = 95

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
RECADRAGES = "recadrages"  # les photos recadrées, zoomées ou tournées se cherchent (avec IA)
