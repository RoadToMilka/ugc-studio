"""Bilan de l'autotest en affichage agrandi (125 % et 150 %) : lancé par la fabrication automatique,
jamais par l'utilisateur.

Pourquoi (V4 ; demande de l'utilisateur du 06/10/2026) : beaucoup d'écrans d'ordinateur portable sont
réglés à 125 % ou 150 % dans Windows. La fabrication relance l'autotest du .exe avec Qt agrandi d'autant
(QT_SCALE_FACTOR) ; ce script lit chaque rapport et relève, où qu'ils soient dans le rapport, les
débordements : textes coupés, boutons qui débordent, contenus plus larges que leur place (voir
_debordements et _textes_coupes dans ugc_studio/autotest.py).

Les débordements font échouer la fabrication. Les autres vérifications non réussies sont seulement
signalées (avertissement) : faites pour l'écran à 100 %, certaines mesurent la disposition au pixel près.
Le bilan est aussi écrit dans le résumé du run (GITHUB_STEP_SUMMARY), s'il existe.

Usage : python outils/affichage_agrandi.py rapport/captures-125 rapport/captures-150
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def debordements(donnees) -> list[str]:
    """Les textes de toutes les listes « debordements » (ou « …_debordements »), à toute profondeur."""
    trouves: list[str] = []
    if isinstance(donnees, dict):
        for cle, valeur in donnees.items():
            if cle.endswith("debordements") and isinstance(valeur, list):
                trouves += [str(element) for element in valeur]
            else:
                trouves += debordements(valeur)
    elif isinstance(donnees, list):
        for valeur in donnees:
            trouves += debordements(valeur)
    return trouves


def bilan(dossier: Path) -> tuple[list[str], list[str], str | None]:
    """(vérifications non réussies, débordements, erreur) du rapport de l'autotest dans `dossier`."""
    fichier = dossier / "autotest.json"
    if not fichier.is_file():
        return [], [], f"pas de rapport de l'autotest dans {dossier.name}"
    rapport = json.loads(fichier.read_text(encoding="utf-8"))
    ratees = sorted(nom for nom, valeur in rapport.get("verifications", {}).items() if valeur is not True)
    return ratees, list(dict.fromkeys(debordements(rapport))), None


def principal(dossiers: list[str]) -> int:
    lignes: list[str] = []
    echec = False
    for chemin in dossiers:
        dossier = Path(chemin)
        nom = dossier.name
        ratees, trouves, erreur = bilan(dossier)
        lignes.append(f"### {nom}")
        if erreur:
            echec = True
            print(f"::error title=Affichage agrandi ({nom})::{erreur}")
            lignes.append(erreur)
            continue
        lignes.append("Vérifications non réussies : " + (", ".join(ratees) if ratees else "aucune"))
        lignes += [f"- {texte}" for texte in trouves]
        if trouves:
            echec = True
            print(f"::error title=Textes coupés ou débordements ({nom})::" + " | ".join(trouves))
        elif ratees:
            print(f"::warning title=Affichage agrandi ({nom})::Vérifications non réussies, sans texte coupé : " + ", ".join(ratees))
    resume = os.environ.get("GITHUB_STEP_SUMMARY")
    if resume:
        with open(resume, "a", encoding="utf-8") as fichier:
            fichier.write("\n".join(lignes) + "\n")
    print("\n".join(lignes))
    return 1 if echec else 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
