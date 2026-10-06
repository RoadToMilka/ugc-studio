"""Faux Topaz (V4, lot 3) : pour les tests et l'autotest du .exe, qui n'ont ni Topaz, ni sa licence,
ni la carte graphique de l'utilisateur. Il répond comme le FFmpeg de Topaz pour tout ce qui entoure le
modèle : il lit la commande, donne son avancement (« -progress pipe:1 »), puis écrit le fichier
demandé (une simple copie de la vidéo : son contenu n'importe pas ici). Le vrai test du modèle reste
celui de l'utilisateur, avec Topaz.

Lancé par `python -m ugc_studio.topaz.faux …` (tests) ou `UGC-Studio.exe --faux-topaz …` (autotest).
Variables (tests) : UGC_FAUX_TOPAZ_DUREE (durée annoncée, en secondes), UGC_FAUX_TOPAZ_PAUSE (pause
entre deux nouvelles), UGC_FAUX_TOPAZ_ECHEC (échoue comme Topaz sans modèle), UGC_FAUX_TOPAZ_COMMANDE
(fichier où écrire la commande reçue).
"""

from __future__ import annotations

import os
import shutil
import sys
import time

OPTION = "--faux-topaz"  # option du .exe (app.py)
PAS = 4  # nouvelles d'avancement données avant la fin


def _ecrire(descripteur: int, texte: str) -> None:
    """Écrit sur la sortie standard (1) ou d'erreur (2), même dans le .exe sans console (où sys.stdout
    peut manquer : on écrit directement dans le tuyau donné par l'app)."""
    try:
        os.write(descripteur, texte.encode("utf-8"))
    except OSError:
        pass


def principal(arguments: list[str]) -> int:
    commande = os.environ.get("UGC_FAUX_TOPAZ_COMMANDE")
    if commande:
        with open(commande, "w", encoding="utf-8") as fichier:
            fichier.write("\n".join(arguments))
    if "-i" not in arguments or len(arguments) < 3:
        _ecrire(2, "Error: no input\n")
        return 1
    entree = arguments[arguments.index("-i") + 1]
    sortie = arguments[-1]
    if os.environ.get("UGC_FAUX_TOPAZ_ECHEC"):
        _ecrire(2, "[tvai_up @ 0000] Model prob-4 could not be loaded\nError while filtering: Invalid argument\n")
        return 1
    graphe = next((arguments[rang + 1] for rang, morceau in enumerate(arguments[:-1]) if morceau in ("-filter_complex", "-vf")), "")
    if "tvai_up=" not in graphe:
        _ecrire(2, "Error: no tvai_up filter\n")
        return 1
    duree = float(os.environ.get("UGC_FAUX_TOPAZ_DUREE", "2"))
    pause = float(os.environ.get("UGC_FAUX_TOPAZ_PAUSE", "0.05"))
    for pas in range(1, PAS + 1):
        _ecrire(1, f"frame={pas * 10}\nout_time_us={int(duree * pas / PAS * 1_000_000)}\nprogress=continue\n")
        time.sleep(pause)
    try:
        shutil.copyfile(entree, sortie)
    except OSError as erreur:
        _ecrire(2, f"Error opening output file {sortie}: {erreur}\n")
        return 1
    _ecrire(1, "progress=end\n")
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
