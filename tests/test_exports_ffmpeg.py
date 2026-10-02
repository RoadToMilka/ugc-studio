"""V3, lot 1 (§2, §8.2) : FFmpeg, ses commandes, l'analyse d'une vidéo et le suivi d'un export.

Les commandes sont vérifiées option par option (sans interface). Quand un FFmpeg est disponible (celui
intégré à l'app sur la fabrication Windows, celui de l'ordinateur ailleurs), de vrais fichiers sont
écrits puis relus : ProRes 4444 avec transparence, couleurs et transparence comparées pixel par pixel.
"""

import hashlib
import lzma
import struct
import sys
import time
from fractions import Fraction
from pathlib import Path

import pytest

from ugc_studio.exports import ffmpeg as module_ffmpeg
from ugc_studio.exports.ffmpeg import (
    FORMAT_DES_IMAGES,
    ErreurFFmpeg,
    Nouvelles,
    Processus,
    analyser,
    commande_analyse,
    commande_calque,
    commande_lire_une_image,
    copie_de_ffmpeg,
    ecrire_le_programme,
    executer,
    ffmpeg_a_preparer,
    infos_ffmpeg,
    lire_analyse,
    lire_encodeurs,
    lire_formats_d_encodeur,
    lire_nouvelles,
    lire_version,
    preparer_ffmpeg,
    programme_ffmpeg,
)

# Une vidéo H.264 à 29,97 (images B : moments dans le désordre), et son son AAC (avec ses 1 024
# échantillons d'amorce, à un moment négatif), telles que FFmpeg 9 les décrit.
FRAMECRC_VIDEO = """#extradata 0:       45, 0x5e2211c4
#extradata 1:        5, 0x054101d4
#software: Lavf62.3.100
#tb 0: 1/30000
#media_type 0: video
#codec_id 0: h264
#dimensions 0: 1080x1920
#sar 0: 1/1
#tb 1: 1/48000
#media_type 1: audio
#codec_id 1: aac
#sample_rate 1: 48000
#channel_layout_name 1: stereo
0,      -2002,          0,     1001,    40000, 0x619f07c8
1,      -1024,      -1024,     1024,      700, 0x1f1766a3, F=0x5, S=1,       10
0,      -1001,       3003,     1001,    20000, 0x12a5a6a7, F=0x0
0,          0,       1001,     1001,    10000, 0x392f10b4, F=0x0
1,          0,          0,     1024,      700, 0x1f1766a3
0,       1001,       2002,     1001,    10000, 0x24938d68, F=0x0
1,       1024,       1024,     1024,      700, 0x1f1766a3
"""

# iPhone réglé sur 30 : unité de temps 1/600, images tous les 20 (parfois 19, 21, ou une image sautée).
FRAMECRC_IPHONE = "#tb 0: 1/600\n#media_type 0: video\n#codec_id 0: hevc\n#dimensions 0: 1920x1080\n" + "".join(
    f"0, {m}, {m}, 20, 1000, 0x0\n" for m in (0, 20, 40, 59, 80, 101, 120, 140, 180, 200, 220)
)

FRAMECRC_AUDIO = """#tb 0: 1/48000
#media_type 0: audio
#codec_id 0: pcm_s16le
#sample_rate 0: 48000
#channel_layout_name 0: mono
0,          0,          0,     2048,     4096, 0x8bbde571
0,       2048,       2048,     2048,     4096, 0x4685ea5a
"""


def test_analyse_d_une_video_a_29_97():
    analyse = lire_analyse(FRAMECRC_VIDEO)
    images = analyse.images
    assert images.nombre == 4
    assert images.temps == (0, Fraction(1001, 30000), Fraction(2002, 30000), Fraction(3003, 30000))  # remis dans l'ordre
    assert images.frequence == Fraction(30000, 1001) and images.constante
    assert images.duree == Fraction(4 * 1001, 30000)
    assert images.codec == "h264" and (images.largeur, images.hauteur) == (1080, 1920)
    assert images.debit == round(80_000 * 8 / (4 * 1001 / 30000))
    son = analyse.son
    assert son.codec == "aac" and son.frequence == 48000 and son.canaux == "stereo"
    assert son.duree == Fraction(3 * 1024, 48000) and son.octets == 2100


def test_analyse_d_une_video_a_frequence_variable():
    """La fréquence nominale (l'écart le plus fréquent : 20/600 s, soit 30) et pas la moyenne."""
    images = lire_analyse(FRAMECRC_IPHONE).images
    assert not images.constante
    assert images.frequence == Fraction(30)
    assert images.nombre == 11 and images.temps[3] == Fraction(59, 600)


def test_analyse_d_un_audio():
    analyse = lire_analyse(FRAMECRC_AUDIO)
    assert analyse.images is None
    assert analyse.son.codec == "pcm_s16le" and analyse.son.duree == Fraction(4096, 48000)


def test_lectures_de_textes_de_ffmpeg():
    assert lire_version("ffmpeg version 9.0.2-essentials_build-www.gyan.dev Copyright (c) 2000-2026") == (
        "9.0.2-essentials_build-www.gyan.dev"
    )
    encodeurs = lire_encodeurs(
        "Encoders:\n V..... = Video\n ------\n V....D libx264              libx264 H.264\n"
        " VF...D prores_ks            Apple ProRes (iCodec Pro)\n A....D aac                  AAC\n"
    )
    assert encodeurs == {"libx264", "prores_ks", "aac"}
    assert lire_formats_d_encodeur("    Supported pixel formats: yuv420p yuv420p10le gbrp\n") == ("yuv420p", "yuv420p10le", "gbrp")
    nouvelles = Nouvelles()
    lire_nouvelles(["frame=412\n", "out_time_us=13746066\n", "progress=continue\n"], nouvelles)
    assert (nouvelles.images, round(nouvelles.temps_s, 3), nouvelles.fini) == (412, 13.746, False)
    lire_nouvelles(["out_time_us=N/A", "progress=end"], nouvelles)
    assert nouvelles.fini and nouvelles.temps_s == pytest.approx(13.746066)


def test_commande_du_calque():
    """Chaque option, d'après la documentation de FFmpeg 9.0.2 (rawvideo, prores_ks, scale, mov)."""
    commande = commande_calque(Path("ffmpeg.exe"), 1080, 1920, Fraction(30000, 1001), 930, Path("D:/pub (calque).mov.en-cours"))
    texte = " ".join(commande)
    assert commande[0] == "ffmpeg.exe" and commande[-1] == str(Path("D:/pub (calque).mov.en-cours"))
    assert "-f rawvideo -pixel_format rgba64le -video_size 1080x1920 -framerate 30000/1001 -i pipe:0" in texte
    assert "-vf scale=out_color_matrix=bt709:out_range=tv,format=yuva444p10le" in texte
    assert "-c:v prores_ks -profile:v 4444 -alpha_bits 16 -vendor apl0 -qscale:v 1" in texte  # compression la plus fine, sans recherche
    assert "-color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv" in texte
    assert "-frames:v 930 -an -f mov" in texte
    assert "-progress pipe:1" in texte and "-nostdin" not in commande  # l'entrée standard porte les images
    analyse = commande_analyse(Path("ffmpeg"), Path("v.mp4"))
    assert analyse[-9:] == ["-map", "0:V:0?", "-map", "0:a:0?", "-c", "copy", "-f", "framecrc", "-"]


def test_ffmpeg_designe_par_la_variable(tmp_path, monkeypatch):
    faux = tmp_path / "ffmpeg.exe"
    faux.write_bytes(b"")
    monkeypatch.setenv(module_ffmpeg.VARIABLE_FFMPEG, str(faux))
    assert programme_ffmpeg() == faux
    monkeypatch.setenv(module_ffmpeg.VARIABLE_FFMPEG, str(tmp_path / "absent.exe"))
    assert programme_ffmpeg() is None


# --- FFmpeg recopié depuis le .exe au premier export ----------------------------------------------

FAUX_PROGRAMME = bytes(range(256)) * 20_000  # 5 Mo : plusieurs morceaux de 1 Mo à décompresser


def _faux_exe(monkeypatch, tmp_path, compresse: bytes | None):
    """Comme dans le .exe : FFmpeg compressé dans la ressource, recopié dans le dossier des programmes."""
    monkeypatch.delenv(module_ffmpeg.VARIABLE_FFMPEG, raising=False)
    monkeypatch.setenv("UGC_STUDIO_DOSSIER_PROGRAMMES", str(tmp_path / "programmes"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(module_ffmpeg, "_ressource", lambda: (0, len(compresse)) if compresse is not None else None)
    monkeypatch.setattr(module_ffmpeg, "_lire_la_ressource", lambda: compresse)
    monkeypatch.setattr(module_ffmpeg, "TAILLE_DU_PROGRAMME", len(FAUX_PROGRAMME))
    monkeypatch.setattr(module_ffmpeg, "EMPREINTE_DU_PROGRAMME", hashlib.sha256(FAUX_PROGRAMME).hexdigest())


def test_ffmpeg_recopie_une_fois_depuis_le_exe(tmp_path, monkeypatch):
    """Premier export : FFmpeg est à recopier (programme_ffmpeg ne le donne pas encore) ; une fois
    recopié et vérifié, il est repris tel quel, et les copies des anciennes versions sont effacées."""
    _faux_exe(monkeypatch, tmp_path, lzma.compress(FAUX_PROGRAMME))
    ancienne = tmp_path / "programmes" / "ffmpeg" / "8.0" / "ffmpeg.exe"
    ancienne.parent.mkdir(parents=True)
    ancienne.write_bytes(b"ancien")
    copie = copie_de_ffmpeg()
    assert copie == tmp_path / "programmes" / "ffmpeg" / module_ffmpeg.VERSION_INTEGREE / copie.name
    assert ffmpeg_a_preparer() and programme_ffmpeg() is None
    assert preparer_ffmpeg() == copie and copie.read_bytes() == FAUX_PROGRAMME
    assert not ffmpeg_a_preparer() and programme_ffmpeg() == copie
    assert not ancienne.parent.exists()
    assert [f.name for f in copie.parent.iterdir()] == [copie.name]  # aucun fichier provisoire laissé
    monkeypatch.setattr(module_ffmpeg, "_lire_la_ressource", lambda: pytest.fail("déjà recopié : rien à relire"))
    assert preparer_ffmpeg() == copie


def test_ffmpeg_abime_jamais_lance(tmp_path, monkeypatch):
    """Une copie qui ne redonne pas exactement FFmpeg (empreinte, fin manquante, données illisibles)
    est refusée, et rien ne reste sous le vrai nom."""
    compresse = lzma.compress(FAUX_PROGRAMME)
    for abime, motif in (
        (lzma.compress(FAUX_PROGRAMME[:-1] + b"x"), "abîmée"),
        (compresse[: len(compresse) // 2], "abîmée"),
        (b"pas du xz" * 100, "illisible"),
    ):
        _faux_exe(monkeypatch, tmp_path, abime)
        with pytest.raises(ErreurFFmpeg, match=motif):
            preparer_ffmpeg()
        assert not copie_de_ffmpeg().exists() and list(copie_de_ffmpeg().parent.iterdir()) == []
        assert programme_ffmpeg() is None and ffmpeg_a_preparer()


def test_ffmpeg_absent_du_exe(tmp_path, monkeypatch):
    _faux_exe(monkeypatch, tmp_path, None)
    monkeypatch.setattr(module_ffmpeg, "programme_integre", lambda: tmp_path / "absent" / "ffmpeg.exe")
    assert not ffmpeg_a_preparer() and programme_ffmpeg() is None
    with pytest.raises(ErreurFFmpeg, match="introuvable"):
        preparer_ffmpeg()


def test_ecrire_le_programme_deja_la(tmp_path):
    """Une autre fenêtre de l'app l'a déjà recopié (et s'en sert peut-être : impossible de le remplacer) :
    la copie existante, de la bonne taille, sert."""
    destination = tmp_path / "ffmpeg.exe"
    empreinte = hashlib.sha256(FAUX_PROGRAMME).hexdigest()
    ecrire_le_programme(lzma.compress(FAUX_PROGRAMME), destination, len(FAUX_PROGRAMME), empreinte)
    assert destination.read_bytes() == FAUX_PROGRAMME
    ecrire_le_programme(lzma.compress(FAUX_PROGRAMME), destination, len(FAUX_PROGRAMME), empreinte)
    assert sorted(f.name for f in tmp_path.iterdir()) == ["ffmpeg.exe"]


# --- Avec un vrai FFmpeg -----------------------------------------------------------------------

FFMPEG = programme_ffmpeg()
avec_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")

LARGEUR, HAUTEUR = 64, 48
JAUNE_16 = (0xFFFF, 0xD4D4, 0x3B3B)  # #FFD43B, le jaune du mot actif des préréglages


def _image(numero: int) -> bytes:
    """Une image RGBA 16 bits : un rectangle jaune opaque, une ombre noire de plus en plus opaque,
    le reste transparent ; le rectangle avance d'un pixel par image."""
    pixels = bytearray(LARGEUR * HAUTEUR * 8)
    for y in range(HAUTEUR):
        for x in range(LARGEUR):
            if 10 + numero <= x < 30 + numero and 10 <= y < 30:
                valeurs = (*JAUNE_16, 0xFFFF)
            elif 40 <= x < 56:
                valeurs = (0, 0, 0, round(65535 * (x - 39) / 16))
            else:
                continue
            struct.pack_into("<4H", pixels, (y * LARGEUR + x) * 8, *valeurs)
    return bytes(pixels)


def _pixel(donnees: bytes, x: int, y: int) -> tuple[int, ...]:
    return struct.unpack_from("<4H", donnees, (y * LARGEUR + x) * 8)


@avec_ffmpeg
def test_ffmpeg_sait_tout_faire():
    infos = infos_ffmpeg()
    assert infos is not None and infos.version
    assert {"prores_ks", "libx264", "libx265", "ffv1", "aac"} <= infos.encodeurs
    assert infos.x265_10_bits  # utile au HDR (lot 3)


@avec_ffmpeg
def test_calque_prores_4444_ecrit_puis_relu(tmp_path):
    """Un vrai calque : images envoyées par le tuyau, ProRes 4444 écrit ; relu, il a le bon nombre
    d'images à la bonne fréquence, et ses couleurs et sa transparence sont celles envoyées."""
    sortie = tmp_path / "calque.mov.en-cours"
    nombre = 5
    processus = Processus(commande_calque(FFMPEG, LARGEUR, HAUTEUR, Fraction(30000, 1001), nombre, sortie), avec_images=True)
    for numero in range(nombre):
        while not processus.envoyer(_image(numero)):
            time.sleep(0.01)
    while not processus.fin_des_images():
        time.sleep(0.01)
    assert processus.attendre(60) == 0, processus.erreurs()
    assert processus.nouvelles.fini and processus.nouvelles.images == nombre

    analyse = analyser(sortie)
    assert analyse.images.codec == "prores" and analyse.images.nombre == nombre
    assert analyse.images.frequence == Fraction(30000, 1001) and analyse.son is None
    assert (analyse.images.largeur, analyse.images.hauteur) == (LARGEUR, HAUTEUR)

    lue = executer(commande_lire_une_image(FFMPEG, sortie, 2), binaire=True).stdout
    assert len(lue) == LARGEUR * HAUTEUR * 8 and FORMAT_DES_IMAGES == "rgba64le"
    attendue = _image(2)
    for x, y in ((20, 20), (5, 5), (42, 20), (47, 20), (55, 40), (13, 12)):
        rouge, vert, bleu, alpha = _pixel(lue, x, y)
        r0, v0, b0, a0 = _pixel(attendue, x, y)
        assert abs(alpha - a0) <= 0x0040, (x, y)  # transparence sur 10 bits au moins
        if a0 > 0xF000:  # couleur opaque : la même, à un niveau sur 255 près
            assert max(abs(rouge - r0), abs(vert - v0), abs(bleu - b0)) <= 0x0101, (x, y)


@avec_ffmpeg
def test_arreter_ffmpeg(tmp_path):
    """« Arrêter » : FFmpeg s'arrête tout de suite, même s'il attend encore des images."""
    sortie = tmp_path / "long.mov.en-cours"
    processus = Processus(commande_calque(FFMPEG, LARGEUR, HAUTEUR, Fraction(30), 10_000, sortie), avec_images=True)
    assert processus.envoyer(_image(0))
    debut = time.monotonic()
    processus.arreter()
    assert processus.termine() and time.monotonic() - debut < 5
    assert processus.tuyau_coupe and not processus.peut_recevoir()


@avec_ffmpeg
def test_erreur_de_ffmpeg_lisible(tmp_path):
    """Une commande refusée : FFmpeg s'arrête, et son dernier message est gardé pour l'expliquer."""
    commande = commande_calque(FFMPEG, LARGEUR, HAUTEUR, Fraction(30), 2, tmp_path / "absent" / "x.mov")
    processus = Processus(commande, avec_images=True)
    for numero in range(2):
        processus.envoyer(_image(numero))
    processus.fin_des_images()
    assert processus.attendre(60) not in (0, None)
    deadline = time.monotonic() + 5
    while not processus.erreur() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert processus.erreur()
