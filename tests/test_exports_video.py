"""V3, lot 2 (§8.3, §8.5) : vidéo avec sous-titres, sans interface.

- Ce qui sera exporté : débits (identique + 10 %, conseillé, personnalisé), son copié ou converti,
  couleurs, combinaisons de conteneur et de codec, résumé avant export.
- Les commandes données à FFmpeg, option par option.
- Le calque provisoire (MOV d'images PNG, chacune avec sa durée), relu par FFmpeg.
- De vrais exports (quand FFmpeg est là : celui de l'app sur la fabrication Windows) : la vidéo
  relue a les mêmes images aux mêmes moments (fréquence variable comprise), le son copié, les
  étiquettes de couleurs, et le jaune des sous-titres est le bon.
"""

import struct
import subprocess
import zlib
from fractions import Fraction
from pathlib import Path

import pytest

from ugc_studio.exports.ffmpeg import Analyse, CouleursDeLaVideo, ImagesDeLaVideo, SonDeLaVideo, analyser, executer, programme_ffmpeg
from ugc_studio.exports.mov_png import EcritureMovPng
from ugc_studio.exports.plan import Source
from ugc_studio.exports.video import (
    DEBIT_CONSEILLE,
    DEBIT_IDENTIQUE,
    DEBIT_PERSONNALISE,
    H264,
    H265,
    MKV,
    MOV,
    MP4,
    PRORES,
    SON_AAC,
    SON_COPIE,
    commande_video,
    couleurs_de_l_export,
    debit_conseille,
    debit_par_defaut,
    decalage_du_calque,
    graphe_de_filtres,
    plan_video,
    resume_video,
    son_de_l_export,
)

FFMPEG = programme_ffmpeg()
avec_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")

SDR_HD = CouleursDeLaVideo("yuv420p", "tv", "bt709", "bt709", "bt709")


def _images(nombre=930, base=Fraction(1, 30000), ecart=1001, debit_octets=46_500, codec="h264", depart=0) -> ImagesDeLaVideo:
    moments = tuple(depart + n * ecart for n in range(nombre))
    duree = nombre * ecart * base
    return ImagesDeLaVideo(
        tuple((m - depart) * base for m in moments), 1 / (ecart * base), True, duree, codec, debit_octets * nombre,
        1080, 1920, base, moments, ecart,
    )


def _source(tmp_path: Path, images=None, son="aac", couleurs=SDR_HD, rotation=0, format_="MP4", codec_video="H.264") -> Source:
    chemin = tmp_path / "Sérum Glowzy.mp4"
    chemin.write_bytes(b"\0" * 1000)
    images = images or _images()
    sons = SonDeLaVideo(son, 256_000 // 8 * 31, Fraction(31)) if son else None
    analyse = Analyse(images, sons, couleurs, rotation)
    return Source(
        chemin, True, 1080, 1920, images.frequence, True, images.nombre, float(images.duree), format_, codec_video,
        images.debit, "AAC" if son == "aac" else (son or "").upper(), 256_000 if son else None, 1000,
        bool(couleurs and couleurs.hdr), couleurs, analyse=analyse,
    )


# --- Choix de l'export ---------------------------------------------------------------------------


def test_debit_conseille_d_apres_youtube():
    """Le double des débits conseillés par YouTube (consultés le 02/10/2026), selon le petit côté."""
    assert debit_conseille(1080, 1920, Fraction(30000, 1001)) == 16_000_000  # vertical 1080p, 30 i/s : 2 × 8 Mb/s
    assert debit_conseille(1920, 1080, Fraction(60)) == 24_000_000  # 48 à 60 i/s : 2 × 12 Mb/s
    assert debit_conseille(720, 1280, Fraction(25)) == 10_000_000
    assert debit_conseille(2160, 3840, Fraction(30)) == 90_000_000  # la valeur haute de la fourchette 4K
    assert debit_conseille(540, 960, Fraction(10)) == 5_000_000  # 480p
    assert debit_conseille(200, 200, None) == 2_000_000


def test_debit_par_defaut(tmp_path):
    assert debit_par_defaut(_source(tmp_path)) == DEBIT_IDENTIQUE
    prores = _source(tmp_path, _images(codec="prores", debit_octets=900_000))
    assert debit_par_defaut(prores) == DEBIT_CONSEILLE  # format de montage : énorme au même débit
    inconnu = _source(tmp_path, _images(debit_octets=0))
    assert debit_par_defaut(inconnu) == DEBIT_CONSEILLE


def test_son_copie_ou_converti():
    """Copié tel quel quand le conteneur l'accepte, sinon AAC 320 kb/s (PCM d'un MOV vers un MP4)."""
    assert son_de_l_export(MP4, "aac") == SON_COPIE
    assert son_de_l_export(MP4, "pcm_s16le") == SON_AAC
    assert son_de_l_export(MOV, "pcm_s16le") == SON_COPIE
    assert son_de_l_export(MP4, "opus") == SON_AAC and son_de_l_export(MKV, "opus") == SON_COPIE
    assert son_de_l_export(MP4, None) is None


def test_couleurs_de_l_export():
    """La norme de la vidéo quand elle est connue ; sinon celle d'une vidéo HD (BT.709)."""
    hd, inconnues = couleurs_de_l_export(SDR_HD), couleurs_de_l_export(None)
    assert (hd.matrice, hd.primaires, hd.transfert) == (inconnues.matrice, inconnues.primaires, inconnues.transfert) == ("bt709",) * 3
    assert not hd.rgb_source and couleurs_de_l_export(CouleursDeLaVideo("rgba", "pc", "gbr")).rgb_source
    sd = couleurs_de_l_export(CouleursDeLaVideo("yuv420p", "tv", "smpte170m", "smpte170m", "smpte170m"))
    assert (sd.matrice, sd.primaires, sd.transfert, sd.matrice_du_filtre) == ("smpte170m", "smpte170m", "smpte170m", "smpte170m")
    mjpeg = couleurs_de_l_export(CouleursDeLaVideo("yuvj420p", "pc", "bt470bg", "", ""))
    assert (mjpeg.matrice, mjpeg.primaires, mjpeg.transfert, mjpeg.plage_source, mjpeg.matrice_du_filtre) == ("bt470bg", "bt709", "bt709", "pc", "bt470")


def test_plan_par_defaut(tmp_path):
    source = _source(tmp_path)
    plan = plan_video(source, MP4, H264, DEBIT_IDENTIQUE, 0, tmp_path / "Sérum Glowzy (sous-titres).mp4")
    assert (plan.largeur, plan.hauteur, plan.passages, plan.bits) == (1080, 1920, 2, 8)
    assert plan.debit == round(46_500 * 8 * 30000 / 1001 * 1.1)  # le débit réel de la vidéo + 10 %
    assert plan.son == SON_COPIE and plan.format_des_pixels == "yuv420p" and plan.format_du_calque == "yuva420p"
    assert plan.en_cours.name == "Sérum Glowzy (sous-titres).mp4.en-cours"
    assert plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, plan.sortie).debit == 16_000_000
    assert plan_video(source, MP4, H264, DEBIT_PERSONNALISE, 12.5, plan.sortie).debit == 12_500_000
    prores = plan_video(source, MOV, PRORES, DEBIT_IDENTIQUE, 0, tmp_path / "x.mov")
    assert prores.debit is None and prores.passages == 1 and prores.format_des_pixels == "yuv422p10le" and prores.calque_16_bits
    assert plan_video(source, MP4, PRORES, DEBIT_IDENTIQUE, 0, plan.sortie).codec == H264  # ProRes : seulement en MOV
    dix = _source(tmp_path, couleurs=CouleursDeLaVideo("yuv420p10le", "tv", "bt709", "bt709", "bt709"))
    assert plan_video(dix, MP4, H265, DEBIT_IDENTIQUE, 0, plan.sortie).bits == 10  # H.265 garde les 10 bits
    assert plan_video(dix, MP4, H264, DEBIT_IDENTIQUE, 0, plan.sortie).bits == 8


def test_plan_d_une_video_couchee(tmp_path):
    """Vidéo de téléphone enregistrée « couchée » : FFmpeg la redresse, l'export est debout."""
    images = _images()
    images = ImagesDeLaVideo(images.temps, images.frequence, True, images.duree, "h264", images.octets, 1920, 1080,
                             images.base_de_temps, images.moments, images.duree_derniere)
    plan = plan_video(_source(tmp_path, images, rotation=90), MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "x.mp4")
    assert (plan.largeur, plan.hauteur) == (1080, 1920)


def test_commandes_h264_en_deux_passages(tmp_path):
    """Chaque option, d'après la documentation de FFmpeg 9.0.2 (overlay, setparams, libx264, mov)."""
    source = _source(tmp_path)
    plan = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v (sous-titres).mp4")
    calque, journal = tmp_path / "calque.mov", tmp_path / "passages"
    premier = commande_video(Path("ffmpeg.exe"), plan, calque, 1, journal)
    texte = " ".join(premier)
    assert premier[-3:] == ["-f", "null", "-"] and "-an" in premier and "-c:a" not in premier
    assert f"-i {source.chemin} -i {calque}" in texte
    assert "-fps_mode passthrough -enc_time_base:v demux" in texte  # chaque image garde son moment exact
    assert "-c:v libx264 -preset medium -profile:v high -pix_fmt yuv420p -b:v 16000000 -pass 1 -passlogfile" in texte
    second = commande_video(Path("ffmpeg.exe"), plan, calque, 2, journal)
    texte = " ".join(second)
    assert "-map [sortie] -map 0:a:0 -c:a copy" in texte and "-pass 2" in texte
    assert second[-4:] == ["+faststart", "-f", "mp4", str(plan.en_cours)]
    assert graphe_de_filtres(plan) == (
        "[0:v]format=yuv420p[video];[1:v]scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[calque];"
        "[video][calque]overlay=format=yuv420:eof_action=repeat,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[sortie]"
    )


def test_commandes_h265_prores_mkv(tmp_path):
    source = _source(tmp_path, son="pcm_s16le")
    h265 = plan_video(source, MP4, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4")
    texte = " ".join(commande_video(Path("ffmpeg"), h265, tmp_path / "c.mov", 2, tmp_path / "p"))
    assert "-c:v libx265" in texte and "-tag:v hvc1" in texte and "-x265-params log-level=error" in texte
    assert "-c:a aac -b:a 320000" in texte  # PCM : pas dans un MP4
    mkv = plan_video(source, MKV, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mkv")
    texte = " ".join(commande_video(Path("ffmpeg"), mkv, tmp_path / "c.mov", 2, tmp_path / "p"))
    assert "hvc1" not in texte and texte.endswith(f"-f matroska {mkv.en_cours}") and "-c:a copy" in texte
    prores = plan_video(source, MOV, PRORES, DEBIT_CONSEILLE, 0, tmp_path / "v.mov")
    commande = commande_video(Path("ffmpeg"), prores, tmp_path / "c.mov", 1, tmp_path / "p")
    texte = " ".join(commande)
    assert "-c:v prores_ks -profile:v hq -vendor apl0 -pix_fmt yuv422p10le" in texte and "-pass" not in texte
    assert "-c:a copy" in texte and "overlay=format=yuv422p10" in texte and commande[-1] == str(prores.en_cours)
    muette = plan_video(_source(tmp_path, son=None), MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4")
    assert "-c:a" not in commande_video(Path("ffmpeg"), muette, tmp_path / "c.mov", 2, tmp_path / "p")


def test_video_en_plage_complete_et_debut_decale(tmp_path):
    """Plage complète (Motion JPEG) : convertie en plage limitée. Première image à 0,0667 s : le calque
    provisoire est décalé d'autant, au millionième de seconde près, arrondi vers le bas."""
    images = _images(depart=2002)
    couleurs = CouleursDeLaVideo("yuvj420p", "pc", "bt470bg", "", "")
    plan = plan_video(_source(tmp_path, images, couleurs=couleurs), MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4")
    assert graphe_de_filtres(plan).startswith("[0:v]scale=in_range=pc:out_range=tv,format=yuv420p[video];[1:v]scale=out_color_matrix=bt470")
    assert decalage_du_calque(images) == ["-itsoffset", "0.066733"]
    assert decalage_du_calque(_images(depart=-2002)) == ["-itsoffset", "-0.066734"]
    assert decalage_du_calque(_images()) == []


def test_resume_de_la_video(tmp_path):
    source = _source(tmp_path)
    plan = plan_video(source, MP4, H264, DEBIT_IDENTIQUE, 0, tmp_path / "Sérum Glowzy (sous-titres).mp4")
    resume = resume_video(source, plan, "14 sous-titres, préréglage « Karaoké »", libre=10**12)
    lignes = {ligne.titre: ligne for ligne in resume.lignes}
    assert list(lignes) == ["Taille", "Images par seconde", "Débit vidéo", "Format et codec", "Son", "Couleurs", "Durée", "Poids", "Sous-titres"]
    assert (lignes["Taille"].source, lignes["Taille"].export) == ("1080 × 1920", "1080 × 1920")
    assert (lignes["Images par seconde"].source, lignes["Images par seconde"].differente) == ("29,97", False)
    assert lignes["Débit vidéo"].source == "11,1 Mb/s" and lignes["Débit vidéo"].export == "12,3 Mb/s" and lignes["Débit vidéo"].differente
    assert (lignes["Format et codec"].source, lignes["Format et codec"].export, lignes["Format et codec"].differente) == ("MP4, H.264", "MP4, H.264", False)
    assert (lignes["Son"].source, lignes["Son"].export, lignes["Son"].differente) == ("AAC, 256 kb/s", "copié tel quel", False)
    assert (lignes["Couleurs"].source, lignes["Couleurs"].export, lignes["Couleurs"].differente) == ("SDR, 8 bits", "SDR (BT.709), 8 bits", False)
    assert lignes["Poids"].export.startswith("≈ ")
    assert resume.possible and not resume.avertissements


def test_resume_avertissements_et_erreurs(tmp_path):
    source = _source(tmp_path, son="pcm_s16le")
    plan = plan_video(source, MKV, H264, DEBIT_PERSONNALISE, 400, tmp_path / "v.mkv")
    resume = resume_video(source, plan, "")
    textes = " ".join(resume.avertissements)
    assert "Premiere Pro ne lit pas le MKV" in textes and "limite de TikTok" in textes  # 400 Mb/s × 31 s
    son = next(ligne for ligne in resume.lignes if ligne.titre == "Son")
    assert son.export == "copié tel quel"  # le MKV accepte le PCM
    plan = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4")
    son = next(ligne for ligne in resume_video(source, plan, "").lignes if ligne.titre == "Son")
    assert son.export == "converti en AAC, 320 kb/s" and son.differente
    hdr = _source(tmp_path, couleurs=CouleursDeLaVideo("yuv420p10le", "tv", "bt2020nc", "bt2020", "arib-std-b67"))
    resume = resume_video(hdr, plan_video(hdr, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4"), "")
    assert not resume.possible and "HDR" in resume.erreurs[0]  # le HDR arrive avec la 3.0.0
    sans_analyse = Source(source.chemin, True)
    resume = resume_video(sans_analyse, plan_video(sans_analyse, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "x.mp4"), "")
    assert not resume.possible and "FFmpeg n'a pas pu lire ta vidéo" in resume.erreurs[0]
    disparue = Source(tmp_path / "déplacée.mp4", True)
    resume = resume_video(disparue, None, "")
    assert not resume.possible and "« déplacée.mp4 » est introuvable" in resume.erreurs[0]


# --- Calque provisoire : MOV d'images PNG ----------------------------------------------------------


def _png(largeur: int, hauteur: int, couleur: tuple[int, int, int, int]) -> bytes:
    """Un PNG RGBA 8 bits d'une seule couleur (écrit ici, sans Qt)."""
    brut = b"".join(b"\0" + bytes(couleur) * largeur for _ in range(hauteur))

    def morceau(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + morceau(b"IHDR", entete) + morceau(b"IDAT", zlib.compress(brut)) + morceau(b"IEND", b"")


@avec_ffmpeg
def test_calque_provisoire_relu_par_ffmpeg(tmp_path):
    """Chaque image du calque garde sa durée exacte, dans l'unité de temps choisie (1/600 s, celle d'un
    iPhone) ; une image prolongée n'est écrite qu'une fois."""
    ecriture = EcritureMovPng(tmp_path / "calque.mov", 64, 48, 600)
    ecriture.ajouter(_png(64, 48, (0, 0, 0, 0)), 20)
    ecriture.ajouter(_png(64, 48, (255, 212, 59, 255)), 19)
    ecriture.prolonger(21)
    ecriture.ajouter(_png(64, 48, (0, 0, 255, 128)), 41)
    ecriture.fermer()
    images = analyser(tmp_path / "calque.mov").images
    assert images.codec == "png" and images.base_de_temps == Fraction(1, 600)
    assert images.moments == (0, 20, 60) and images.duree_derniere == 41
    assert (images.largeur, images.hauteur) == (64, 48)


# --- Vrais exports -----------------------------------------------------------------------------------


def _ffmpeg(*arguments: str) -> None:
    resultat = executer([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", *arguments], 120)
    assert resultat.returncode == 0, resultat.stderr


def _source_reelle(chemin: Path) -> Source:
    analyse = analyser(chemin)
    images = analyse.images
    return Source(chemin, True, *analyse.taille_affichee, images.frequence, images.constante, images.nombre, float(images.duree),
                  "MP4", "H.264", images.debit, "", analyse.son.debit if analyse.son else None, chemin.stat().st_size,
                  False, analyse.couleurs, analyse=analyse)


def _calque_jaune(plan, chemin: Path, depuis: int) -> None:
    """Calque : transparent, puis un rectangle jaune #FFD43B opaque sur la moitié gauche à partir de
    l'image `depuis` (dans l'unité de temps de la vidéo, chaque image à son moment)."""
    images = plan.images
    largeur, hauteur = plan.largeur, plan.hauteur
    transparent = _png(largeur, hauteur, (0, 0, 0, 0))
    ligne = bytes((255, 212, 59, 255)) * (largeur // 2) + bytes(4) * (largeur - largeur // 2)
    brut = b"".join(b"\0" + ligne for _ in range(hauteur))

    def morceau(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    jaune = (b"\x89PNG\r\n\x1a\n" + morceau(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0))
             + morceau(b"IDAT", zlib.compress(brut)) + morceau(b"IEND", b""))
    ecriture = EcritureMovPng(chemin, largeur, hauteur, images.base_de_temps.denominator)
    moments = images.moments
    for n, moment in enumerate(moments):
        duree = (moments[n + 1] - moment) if n + 1 < len(moments) else images.duree_derniere
        if n in (0, depuis):
            ecriture.ajouter(jaune if n == depuis else transparent, duree)
        else:
            ecriture.prolonger(duree)
    ecriture.fermer()


def _exporter(plan, calque: Path, dossier: Path) -> None:
    for passage in range(1, plan.passages + 1):
        resultat = executer(commande_video(FFMPEG, plan, calque, passage, dossier / "passages"), 300)
        assert resultat.returncode == 0, resultat.stderr


def _pixel_rgb(video: Path, numero: int, x: int, y: int, largeur: int, hauteur: int) -> tuple[int, int, int]:
    image = executer(
        [str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video),
         "-vf", f"select=eq(n\\,{numero}),scale=in_color_matrix=bt709:in_range=tv,format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"],
        60, binaire=True,
    ).stdout
    assert len(image) == largeur * hauteur * 3
    debut = (y * largeur + x) * 3
    return tuple(image[debut : debut + 3])


@avec_ffmpeg
def test_export_h264_mp4_reel(tmp_path):
    """Une vraie vidéo à 29,97 avec son AAC : mêmes images aux mêmes moments, son copié, étiquettes
    BT.709, et le jaune des sous-titres retrouvé à quelques niveaux près (sur 255)."""
    source_chemin = tmp_path / "source.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30000/1001", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-vf", "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source_chemin))
    source = _source_reelle(source_chemin)
    plan = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "source (sous-titres).mp4")
    _calque_jaune(plan, tmp_path / "calque.mov", 10)
    _exporter(plan, tmp_path / "calque.mov", tmp_path)
    sortie = analyser(plan.en_cours)
    assert sortie.images.codec == "h264" and sortie.images.nombre == source.analyse.images.nombre
    secondes = [m * sortie.images.base_de_temps for m in sortie.images.moments]
    assert secondes == [m * source.analyse.images.base_de_temps for m in source.analyse.images.moments]
    assert sortie.son is not None and sortie.son.codec == "aac"
    assert (sortie.couleurs.matrice, sortie.couleurs.primaires, sortie.couleurs.transfert, sortie.couleurs.plage) == ("bt709", "bt709", "bt709", "tv")
    jaune = _pixel_rgb(plan.en_cours, 15, 20, 32, plan.largeur, plan.hauteur)
    assert all(abs(a - b) <= 6 for a, b in zip(jaune, (255, 212, 59), strict=True)), jaune
    avant = _pixel_rgb(plan.en_cours, 5, 20, 32, plan.largeur, plan.hauteur)
    assert abs(avant[0] - 255) + abs(avant[1] - 212) + abs(avant[2] - 59) > 30  # avant le sous-titre : l'image de la vidéo


@avec_ffmpeg
def test_export_d_une_video_a_frequence_variable(tmp_path):
    """Fréquence variable (comme un iPhone, unité 1/600 s) : chaque image garde son moment exact."""
    source_chemin = tmp_path / "iphone.mov"
    ecriture = EcritureMovPng(source_chemin, 64, 48, 600)
    for couleur, duree in (((255, 0, 0, 255), 20), ((0, 255, 0, 255), 19), ((0, 0, 255, 255), 21), ((90, 90, 90, 255), 20), ((200, 200, 200, 255), 41)):
        ecriture.ajouter(_png(64, 48, couleur), duree)
    ecriture.fermer()
    source = _source_reelle(source_chemin)
    assert source.analyse.images.moments == (0, 20, 39, 60, 80)
    plan = plan_video(source, MOV, H264, DEBIT_CONSEILLE, 0, tmp_path / "iphone (sous-titres).mov")
    _calque_jaune(plan, tmp_path / "calque.mov", 2)
    _exporter(plan, tmp_path / "calque.mov", tmp_path)
    sortie = analyser(plan.en_cours).images
    assert [m * sortie.base_de_temps for m in sortie.moments] == [Fraction(m, 600) for m in (0, 20, 39, 60, 80)]
    jaune = _pixel_rgb(plan.en_cours, 2, 10, 24, 64, 48)
    assert all(abs(a - b) <= 6 for a, b in zip(jaune, (255, 212, 59), strict=True)), jaune
    rouge = _pixel_rgb(plan.en_cours, 0, 10, 24, 64, 48)
    assert rouge[0] > 200 and rouge[1] < 60  # la première image, sans sous-titre


@avec_ffmpeg
def test_export_prores_et_son_converti(tmp_path):
    """ProRes 422 HQ dans un MOV (un seul passage), et un son PCM converti en AAC pour un MP4."""
    source_chemin = tmp_path / "montage.mov"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=64x48:rate=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "0.6", "-c:v", "prores_ks", "-profile:v", "hq", "-c:a", "pcm_s16le", str(source_chemin))
    source = _source_reelle(source_chemin)
    assert debit_par_defaut(source) == DEBIT_CONSEILLE  # format de montage
    prores = plan_video(source, MOV, PRORES, DEBIT_CONSEILLE, 0, tmp_path / "montage (sous-titres).mov")
    _calque_jaune(prores, tmp_path / "calque.mov", 3)
    _exporter(prores, tmp_path / "calque.mov", tmp_path)
    sortie = analyser(prores.en_cours)
    assert sortie.images.codec == "prores" and sortie.images.nombre == 15 and sortie.son.codec == "pcm_s16le"  # copié
    assert sortie.couleurs.format_pixels.startswith("yuv422p10")
    mp4 = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "montage (sous-titres).mp4")
    _exporter(mp4, tmp_path / "calque.mov", tmp_path)
    assert analyser(mp4.en_cours).son.codec == "aac"


@avec_ffmpeg
def test_export_h265_mkv(tmp_path):
    source_chemin = tmp_path / "source.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=64x48:rate=30", "-t", "0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source_chemin))
    source = _source_reelle(source_chemin)
    plan = plan_video(source, MKV, H265, DEBIT_CONSEILLE, 0, tmp_path / "source (sous-titres).mkv")
    _calque_jaune(plan, tmp_path / "calque.mov", 1)
    _exporter(plan, tmp_path / "calque.mov", tmp_path)
    sortie = analyser(plan.en_cours)
    assert sortie.images.codec == "hevc" and sortie.images.nombre == 15 and sortie.son is None


def test_rien_d_inutile_dans_les_commandes(tmp_path):
    """Aucune commande n'utilise le shell : la liste d'arguments va telle quelle à FFmpeg (un nom de
    fichier avec des espaces ou des guillemets ne pose pas de problème)."""
    plan = plan_video(_source(tmp_path), MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / 'Pub "été" (sous-titres).mp4')
    commande = commande_video(Path("C:/Program Files/ffmpeg.exe"), plan, tmp_path / "calque.mov", 2, tmp_path / "p")
    assert commande[-1].endswith('Pub "été" (sous-titres).mp4.en-cours') and all(isinstance(a, str) for a in commande)
    assert subprocess.list2cmdline(commande)  # Windows saura la transmettre
