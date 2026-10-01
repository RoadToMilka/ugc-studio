"""Prépare FFmpeg pour la fabrication du .exe (V3) : lancé par la fabrication automatique, jamais par
l'utilisateur.

1. Télécharge l'archive « essentials » de FFmpeg 9.0.2 publiée par gyan.dev (l'une des deux sources
   Windows indiquées par ffmpeg.org), sauf si elle est déjà dans le cache (outils/cache).
2. Vérifie son empreinte SHA-256 : un code calculé sur tout son contenu. Une archive abîmée ou
   modifiée aurait une autre empreinte et serait refusée (la fabrication s'arrête).
3. En extrait ffmpeg.exe dans ugc_studio/ressources/ffmpeg/, où l'app le cherche (dans le .exe comme
   pendant les tests) ; la licence de FFmpeg (GPL version 3) et le README de gyan.dev (version,
   adresse du code source, configuration) y sont déjà, enregistrés avec le code.

FFmpeg ne change que quand on le décide : en modifiant VERSION et EMPREINTE ci-dessous.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "9.0.2"
ARCHIVE = f"ffmpeg-{VERSION}-essentials_build.zip"
ADRESSE = f"https://github.com/GyanD/codexffmpeg/releases/download/{VERSION}/{ARCHIVE}"
# Empreinte publiée par GitHub pour cette archive, recalculée le 02/10/2026 sur le fichier téléchargé.
EMPREINTE = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"

RACINE = Path(__file__).resolve().parents[1]
CACHE = RACINE / "outils" / "cache"
DESTINATION = RACINE / "ugc_studio" / "ressources" / "ffmpeg"
DANS_L_ARCHIVE = f"ffmpeg-{VERSION}-essentials_build/bin/ffmpeg.exe"


def empreinte(chemin: Path) -> str:
    calcul = hashlib.sha256()
    with chemin.open("rb") as fichier:
        for morceau in iter(lambda: fichier.read(1024 * 1024), b""):
            calcul.update(morceau)
    return calcul.hexdigest()


def telecharger(cible: Path) -> None:
    print(f"Téléchargement de {ADRESSE}")
    with tempfile.NamedTemporaryFile(dir=cible.parent, delete=False) as provisoire:
        with urllib.request.urlopen(ADRESSE, timeout=300) as reponse:  # noqa: S310 (adresse fixe, https)
            shutil.copyfileobj(reponse, provisoire)
    Path(provisoire.name).replace(cible)


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / ARCHIVE
    if not archive.is_file() or empreinte(archive) != EMPREINTE:
        telecharger(archive)
    trouvee = empreinte(archive)
    if trouvee != EMPREINTE:
        archive.unlink(missing_ok=True)
        print(f"Empreinte inattendue : {trouvee} (attendue : {EMPREINTE}). Archive refusée.", file=sys.stderr)
        return 1
    DESTINATION.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as contenu:
        with contenu.open(DANS_L_ARCHIVE) as source, (DESTINATION / "ffmpeg.exe").open("wb") as copie:
            shutil.copyfileobj(source, copie)
    taille = (DESTINATION / "ffmpeg.exe").stat().st_size / 1024**2
    print(f"FFmpeg {VERSION} prêt : {DESTINATION / 'ffmpeg.exe'} ({taille:.1f} Mo), empreinte de l'archive vérifiée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
