"""Faux video-compare, pour les tests (comme topaz/faux.py pour Topaz) : il répond à « -V » comme le vrai,
puis, lancé avec deux fichiers, écrit ce qu'écrirait le vrai quand on appuie sur M puis sur F (les
trois captures sont écrites dans le dossier où il est lancé), et attend qu'on ferme sa « fenêtre ».

Variables (tests) : UGC_FAUX_VC_COMMANDE (fichier où noter la commande reçue), UGC_FAUX_VC_DUREE
(secondes avant de se fermer seul ; 60 par défaut), UGC_FAUX_VC_ECHEC (échoue comme le vrai quand un
fichier ne s'ouvre pas).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

VERSION = "20261004-osaka"


def principal(arguments: list[str]) -> int:
    if arguments == ["-V"]:
        print(f"video-compare {VERSION}", flush=True)
        return 0
    commande = os.environ.get("UGC_FAUX_VC_COMMANDE")
    if commande:
        Path(commande).write_text("\n".join(arguments), encoding="utf-8")
    fichiers = arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments[-2:]
    if os.environ.get("UGC_FAUX_VC_ECHEC") or len(fichiers) != 2 or not all(Path(f).is_file() for f in fichiers):
        print(f"Error: Failed to open input file '{fichiers[0] if fichiers else ''}'", file=sys.stderr, flush=True)
        return 255
    gauche, droite = Path(fichiers[0]).stem, Path(fichiers[1]).stem
    print("Metrics: [00:00:01.000|00:00:01.000] PSNR(42.131), SSIM(0.99812), VMAF(97.312)", flush=True)
    captures = (f"{gauche}_0000.png", f"{droite}_0000.png", f"{gauche}_{droite}_osd_0000.png")
    for nom in captures:
        Path(nom).write_bytes(b"capture")
    print(f"Saved {captures[0]}, {captures[1]} and {captures[2]}", flush=True)
    time.sleep(float(os.environ.get("UGC_FAUX_VC_DUREE", "60")))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
