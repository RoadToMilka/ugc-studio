"""Prépare FFmpeg pour la fabrication du .exe (V3) : lancé par la fabrication automatique, jamais par
l'utilisateur.

1. Télécharge l'archive « essentials » de FFmpeg 9.0.2 publiée par gyan.dev (l'une des deux sources
   Windows indiquées par ffmpeg.org), sauf si elle est déjà dans le cache (outils/cache).
2. Vérifie son empreinte SHA-256 : un code calculé sur tout son contenu. Une archive abîmée ou
   modifiée aurait une autre empreinte et serait refusée (la fabrication s'arrête).
3. En extrait ffmpeg.exe dans ugc_studio/ressources/ffmpeg/, pour les tests automatiques (taille et
   empreinte de ffmpeg.exe vérifiées elles aussi) ; la licence de FFmpeg (GPL version 3) et le
   README de gyan.dev (version, adresse du code source, configuration) y sont déjà, enregistrés avec
   le code.
4. Le compresse au format xz (outils/cache/ffmpeg-9.0.2.exe.xz, 27 Mo au lieu de 100) : c'est cette
   copie que la recette du .exe range dans une ressource Windows (packaging/ugc_studio.spec), et que
   l'app recopie au premier export. Gardée en cache elle aussi, et vérifiée avant de resservir.

FFmpeg ne change que quand on le décide : en modifiant sa version, sa taille et son empreinte dans
ugc_studio/exports/ffmpeg.py, et l'empreinte de l'archive ci-dessous.
"""

from __future__ import annotations

import hashlib
import lzma
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from ugc_studio.exports.ffmpeg import EMPREINTE_DU_PROGRAMME, TAILLE_DU_PROGRAMME, VERSION_INTEGREE  # noqa: E402

VERSION = VERSION_INTEGREE
ARCHIVE = f"ffmpeg-{VERSION}-essentials_build.zip"
ADRESSE = f"https://github.com/GyanD/codexffmpeg/releases/download/{VERSION}/{ARCHIVE}"
# Empreinte publiée par GitHub pour cette archive, recalculée le 02/10/2026 sur le fichier téléchargé.
EMPREINTE = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"

CACHE = RACINE / "outils" / "cache"
DESTINATION = RACINE / "ugc_studio" / "ressources" / "ffmpeg"
DANS_L_ARCHIVE = f"ffmpeg-{VERSION}-essentials_build/bin/ffmpeg.exe"
COMPRESSE = CACHE / f"ffmpeg-{VERSION}.exe.xz"
NIVEAU_XZ = 6  # le réglage par défaut de xz : 27 Mo ; décompression : 1 à 2 s, une fois par version


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


def programme_conforme(donnees: bytes) -> bool:
    return len(donnees) == TAILLE_DU_PROGRAMME and hashlib.sha256(donnees).hexdigest() == EMPREINTE_DU_PROGRAMME


def compresse_conforme(chemin: Path) -> bool:
    """La copie compressée redonne-t-elle exactement ffmpeg.exe ? (décompressée pour le vérifier)"""
    try:
        return chemin.is_file() and programme_conforme(lzma.decompress(chemin.read_bytes()))
    except lzma.LZMAError:
        return False


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
    with zipfile.ZipFile(archive) as contenu:
        programme = contenu.read(DANS_L_ARCHIVE)
    if not programme_conforme(programme):
        print("ffmpeg.exe ne correspond pas à la taille et à l'empreinte attendues : refusé.", file=sys.stderr)
        return 1
    DESTINATION.mkdir(parents=True, exist_ok=True)
    (DESTINATION / "ffmpeg.exe").write_bytes(programme)
    print(f"FFmpeg {VERSION} prêt pour les tests : {DESTINATION / 'ffmpeg.exe'} ({len(programme) / 1024**2:.1f} Mo), empreintes vérifiées.")
    if not compresse_conforme(COMPRESSE):
        print(f"Compression de FFmpeg (xz, niveau {NIVEAU_XZ})…")
        provisoire = COMPRESSE.with_name(COMPRESSE.name + ".en-cours")
        provisoire.write_bytes(lzma.compress(programme, format=lzma.FORMAT_XZ, preset=NIVEAU_XZ))
        provisoire.replace(COMPRESSE)
        if not compresse_conforme(COMPRESSE):
            print("La copie compressée de FFmpeg ne redonne pas ffmpeg.exe : refusée.", file=sys.stderr)
            return 1
    print(f"FFmpeg compressé pour le .exe : {COMPRESSE} ({COMPRESSE.stat().st_size / 1024**2:.1f} Mo), vérifié.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
