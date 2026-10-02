"""V3, lots 2 et 3 (§8.3, §8.5) : vidéo avec sous-titres, sans interface.

- Ce qui sera exporté : débits (identique + 10 %, conseillé, personnalisé), son copié ou converti,
  couleurs, combinaisons de conteneur et de codec, résumé avant export.
- HDR (lot 3) : gardé (H.265 en 10 bits ou ProRes, sous-titres au blanc de référence), Dolby Vision
  repris en MP4 et MKV, ou « Convertir en SDR ».
- Les commandes données à FFmpeg, option par option.
- Le calque provisoire (MOV d'images PNG, chacune avec sa durée), relu par FFmpeg.
- De vrais exports (quand FFmpeg est là : celui de l'app sur la fabrication Windows) : la vidéo
  relue a les mêmes images aux mêmes moments (fréquence variable comprise), le son copié, les
  étiquettes de couleurs, et le jaune des sous-titres est le bon ; en HDR, le blanc des sous-titres
  est au blanc de référence (75 % du signal en HLG, 58 % en PQ).
- V3.1 (lot 6) : sous une vidéo importée muette, la voix des sous-titres (une prise), placée au
  moment où elle commence dans la vidéo.
"""

import array
import struct
import subprocess
import zlib
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from ugc_studio.exports.ffmpeg import (
    Analyse,
    CouleursDeLaVideo,
    ImagesDeLaVideo,
    SonDeLaVideo,
    analyser,
    executer,
    lecture_en_rgb,
    programme_ffmpeg,
)
from ugc_studio.exports.mov_png import EcritureMovPng
from ugc_studio.exports.plan import Source
from ugc_studio.exports.video import (
    DEBIT_AAC,
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
    SON_VOIX,
    codecs_possibles,
    commande_video,
    couleurs_de_l_export,
    debit_conseille,
    debit_hdr_de_youtube,
    debit_par_defaut,
    decalage_du_calque,
    graphe_de_filtres,
    options_conteneur,
    options_video,
    plan_video,
    resume_video,
    son_de_l_export,
)

from video_dolby_vision import fabriquer_video_dolby_vision

FFMPEG = programme_ffmpeg()
avec_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")

SDR_HD = CouleursDeLaVideo("yuv420p", "tv", "bt709", "bt709", "bt709")
HLG_IPHONE = CouleursDeLaVideo("yuv420p10le", "tv", "bt2020nc", "bt2020", "arib-std-b67")
PQ_HDR10 = CouleursDeLaVideo("yuv420p10le", "tv", "bt2020nc", "bt2020", "smpte2084")


def _images(nombre=930, base=Fraction(1, 30000), ecart=1001, debit_octets=46_500, codec="h264", depart=0) -> ImagesDeLaVideo:
    moments = tuple(depart + n * ecart for n in range(nombre))
    duree = nombre * ecart * base
    return ImagesDeLaVideo(
        tuple((m - depart) * base for m in moments), 1 / (ecart * base), True, duree, codec, debit_octets * nombre,
        1080, 1920, base, moments, ecart,
    )


def _source(
    tmp_path: Path, images=None, son="aac", couleurs=SDR_HD, rotation=0, format_="MP4", codec_video="H.264", dolby_vision=""
) -> Source:
    chemin = tmp_path / "Sérum Glowzy.mp4"
    chemin.write_bytes(b"\0" * 1000)
    images = images or _images()
    sons = SonDeLaVideo(son, 256_000 // 8 * 31, Fraction(31)) if son else None
    analyse = Analyse(images, sons, couleurs, rotation, dolby_vision)
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
        "[0:v]format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[video];"
        "[1:v]zscale=rin=full:pin=bt709:tin=bt709:p=bt709:t=bt709:m=bt709:r=limited:threads=1,format=yuva420p[calque];"
        "[video][calque]overlay=format=yuv420:alpha=straight:eof_action=repeat[sortie]"
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
    graphe = graphe_de_filtres(plan)
    assert graphe.startswith("[0:v]scale=in_range=pc:out_range=tv,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt470bg:range=tv[video];")
    assert "[1:v]zscale=rin=full:pin=bt709:tin=bt709:p=bt709:t=bt709:m=bt470bg:r=limited:threads=1," in graphe  # la même norme que la vidéo
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


def test_voix_des_sous_titres_sous_la_video_muette(tmp_path):
    """V3.1, lot 6 : vidéo importée, « Son de la vidéo » décoché. La voix (3e entrée, au dernier
    passage seulement) est précédée du silence qui la place à « La voix commence à » (adelay), puis
    prolongée de silence (apad) ; « -shortest » arrête le fichier avec la dernière image."""
    voix = tmp_path / "prise-002.wav"
    source = replace(_source(tmp_path), voix=voix, decalage_s=1.5)
    plan = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "montage (sous-titres).mp4")
    assert (plan.son, plan.voix, plan.decalage_voix, plan.debit_son) == (SON_VOIX, voix, 1.5, DEBIT_AAC)
    calque = tmp_path / "calque.mov"
    premier = commande_video(Path("ffmpeg"), plan, calque, 1, tmp_path / "p")
    assert str(voix) not in premier and "-an" in premier
    texte = " ".join(commande_video(Path("ffmpeg"), plan, calque, 2, tmp_path / "p"))
    assert f"-i {calque} -i {voix} -filter_complex" in texte
    assert "-map [sortie] -map 2:a:0 -filter:a adelay=delays=1500:all=1,apad -c:a aac -b:a 320000 -shortest" in texte
    prores = plan_video(source, MOV, PRORES, DEBIT_CONSEILLE, 0, tmp_path / "montage.mov")  # un seul passage
    assert f"-i {voix}" in " ".join(commande_video(Path("ffmpeg"), prores, calque, 1, tmp_path / "p"))
    son = {ligne.titre: ligne for ligne in resume_video(source, plan, "3 sous-titres", libre=10**12).lignes}["Son"]
    assert (son.export, son.differente) == ("voix des sous-titres, en AAC, 320 kb/s", True)
    # Sans voix (son de la vidéo coché, ou des mots d'un fichier SRT) : le son de la vidéo, comme avant.
    assert plan_video(replace(source, voix=None), MP4, H264, DEBIT_CONSEILLE, 0, plan.sortie).son == SON_COPIE


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
    hdr = _source(tmp_path, couleurs=HLG_IPHONE)
    resume = resume_video(hdr, plan_video(hdr, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4"), "")
    assert resume.possible and not resume.avertissements  # le HDR est gardé (lot 3), en H.265
    sans_analyse = Source(source.chemin, True)
    resume = resume_video(sans_analyse, plan_video(sans_analyse, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "x.mp4"), "")
    assert not resume.possible and "FFmpeg n'a pas pu lire ta vidéo" in resume.erreurs[0]
    disparue = Source(tmp_path / "déplacée.mp4", True)
    resume = resume_video(disparue, None, "")
    assert not resume.possible and "« déplacée.mp4 » est introuvable" in resume.erreurs[0]


# --- HDR (lot 3) -----------------------------------------------------------------------------------


def test_hdr_garde_en_h265_10_bits(tmp_path):
    """Le HDR suit la vidéo source : H.265 en 10 bits (H.264 demandé : H.265), ou ProRes ; mêmes
    couleurs (BT.2020, HLG) ; débit conseillé d'après les débits HDR de YouTube."""
    source = _source(tmp_path, couleurs=HLG_IPHONE)
    assert codecs_possibles(MP4, True) == (H265,) and codecs_possibles(MOV, True) == (H265, PRORES)
    assert codecs_possibles(MP4, False) == (H264, H265)
    plan = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4")
    assert (plan.codec, plan.bits, plan.format_des_pixels, plan.format_du_calque) == (H265, 10, "yuv420p10le", "yuva420p10le")
    assert plan.calque_16_bits and plan.couleurs.hdr and not plan.dolby_vision
    assert (plan.couleurs.matrice, plan.couleurs.primaires, plan.couleurs.transfert) == ("bt2020nc", "bt2020", "arib-std-b67")
    assert plan.debit == 20_000_000  # 1080 × 1920 à 29,97 en HDR : 2 × 10 Mb/s
    prores = plan_video(source, MOV, PRORES, DEBIT_CONSEILLE, 0, tmp_path / "v.mov")
    assert (prores.codec, prores.bits, prores.format_des_pixels) == (PRORES, 10, "yuv422p10le") and prores.couleurs.hdr


def test_debit_conseille_en_hdr():
    """Le double des débits HDR de YouTube ; sous la 720p (pas de HDR chez YouTube), ceux du SDR."""
    assert debit_conseille(1080, 1920, Fraction(30000, 1001), hdr=True) == 20_000_000
    assert debit_conseille(1080, 1920, Fraction(60), hdr=True) == 30_000_000
    assert debit_conseille(2160, 3840, Fraction(30), hdr=True) == 112_000_000
    assert debit_conseille(720, 1280, Fraction(30), hdr=True) == 13_000_000
    assert debit_conseille(540, 960, Fraction(30), hdr=True) == debit_conseille(540, 960, Fraction(30)) == 5_000_000
    assert debit_hdr_de_youtube(1080, 1920) and debit_hdr_de_youtube(720, 1280) and not debit_hdr_de_youtube(540, 960)


def test_couleurs_de_l_export_en_hdr():
    hlg = couleurs_de_l_export(HLG_IPHONE)
    assert hlg.hdr and (hlg.matrice, hlg.primaires, hlg.transfert, hlg.hdr_converti) == ("bt2020nc", "bt2020", "arib-std-b67", None)
    pq = couleurs_de_l_export(CouleursDeLaVideo("yuv420p10le", "tv", "", "", "smpte2084"))
    assert pq.hdr and (pq.matrice, pq.primaires) == ("bt2020nc", "bt2020")  # étiquettes manquantes : celles du HDR
    sdr = couleurs_de_l_export(HLG_IPHONE, convertir_en_sdr=True)
    assert not sdr.hdr and (sdr.matrice, sdr.primaires, sdr.transfert) == ("bt709", "bt709", "bt709")
    assert (sdr.hdr_converti.matrice, sdr.hdr_converti.primaires, sdr.hdr_converti.courbe) == ("bt2020nc", "bt2020", "arib-std-b67")
    assert couleurs_de_l_export(SDR_HD, convertir_en_sdr=True) == couleurs_de_l_export(SDR_HD)  # une vidéo SDR ne change pas


def test_graphes_du_hdr(tmp_path):
    """HDR gardé : l'image de la vidéo telle quelle, les sous-titres convertis au blanc de référence
    (npl=203) ; « Convertir en SDR » : la vidéo en lumière linéaire, ramenée en BT.709, reflets adoucis
    (mobius, genou à la moitié du blanc de référence, crête de 1 000 cd/m²), puis BT.709 limité."""
    source = _source(tmp_path, couleurs=HLG_IPHONE)
    hdr = plan_video(source, MP4, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4")
    assert graphe_de_filtres(hdr) == (
        "[0:v]format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc:range=tv[video];"
        "[1:v]zscale=rin=full:pin=bt709:tin=bt709:p=bt2020:t=arib-std-b67:m=bt2020nc:r=limited:npl=203:threads=1,format=yuva420p10le[calque];"
        "[video][calque]overlay=format=yuv420p10:alpha=straight:eof_action=repeat[sortie]"
    )
    pq = plan_video(_source(tmp_path, couleurs=PQ_HDR10), MOV, PRORES, DEBIT_CONSEILLE, 0, tmp_path / "v.mov")
    assert ":t=smpte2084:" in graphe_de_filtres(pq) and "overlay=format=yuv422p10" in graphe_de_filtres(pq)
    assert "threads" not in graphe_de_filtres(pq)  # en 4:2:2, zscale peut découper l'image (pas de défaut)
    sdr = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4", convertir_en_sdr=True)
    assert (sdr.codec, sdr.bits, sdr.format_des_pixels) == (H264, 8, "yuv420p") and not sdr.calque_16_bits
    assert sdr.debit == 16_000_000  # le débit conseillé du SDR
    assert graphe_de_filtres(sdr) == (
        "[0:v]zscale=min=bt2020nc:pin=bt2020:tin=arib-std-b67:rin=limited:t=linear:npl=203,format=gbrpf32le,"
        "zscale=pin=bt2020:tin=linear:p=bt709,tonemap=tonemap=mobius:param=0.5:peak=4.926:desat=0,"
        "zscale=pin=bt709:tin=linear:t=bt709:m=bt709:r=limited,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[video];"
        "[1:v]zscale=rin=full:pin=bt709:tin=bt709:p=bt709:t=bt709:m=bt709:r=limited:threads=1,format=yuva420p[calque];"
        "[video][calque]overlay=format=yuv420:alpha=straight:eof_action=repeat[sortie]"
    )
    h265 = plan_video(source, MKV, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mkv", convertir_en_sdr=True)
    assert h265.bits == 8 and not h265.couleurs.hdr  # « Convertir en SDR » : 8 bits


def test_dolby_vision_repris_en_mp4_et_mkv(tmp_path):
    """Profil 8.4 (iPhone) : repris en MP4 et MKV avec H.265 (« -dolbyvision 1 », limite de débit
    demandée par x265) ; en MP4, « -strict unofficial » pour que FFmpeg écrive la boîte dvvC."""
    source = _source(tmp_path, couleurs=HLG_IPHONE, dolby_vision="8.4")
    mp4 = plan_video(source, MP4, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4")
    assert mp4.dolby_vision and mp4.debit == 20_000_000
    texte = " ".join(options_video(mp4, 1, tmp_path / "p"))
    assert "-dolbyvision 1 -maxrate 40000000 -bufsize 80000000" in texte and "-tag:v hvc1" in texte
    assert options_conteneur(mp4)[:2] == ["-strict", "unofficial"]
    second = commande_video(Path("ffmpeg"), mp4, tmp_path / "c.mov", 2, tmp_path / "p")
    assert "-strict unofficial -movflags +faststart -f mp4" in " ".join(second)
    assert "-strict" not in commande_video(Path("ffmpeg"), mp4, tmp_path / "c.mov", 1, tmp_path / "p")  # premier passage : rien d'écrit
    mkv = plan_video(source, MKV, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mkv")
    assert mkv.dolby_vision and "-strict" not in options_conteneur(mkv)
    for plan in (
        plan_video(source, MOV, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mov"),  # FFmpeg n'écrit pas la boîte dans un MOV
        plan_video(source, MOV, PRORES, DEBIT_CONSEILLE, 0, tmp_path / "v.mov"),
        plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4", convertir_en_sdr=True),
        plan_video(_source(tmp_path, couleurs=PQ_HDR10, dolby_vision="8.1"), MP4, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4"),
    ):
        assert not plan.dolby_vision and "-dolbyvision" not in options_video(plan, 2, tmp_path / "p")


def test_resume_du_hdr(tmp_path):
    """Couleurs : « HDR (HLG, Dolby Vision), 10 bits » gardées (pas en mauve) ; perdues en MOV (mauve,
    avertissement) ; « Convertir en SDR » en mauve, sans avertissement ; profil 5 : erreur."""
    source = _source(tmp_path, couleurs=HLG_IPHONE, dolby_vision="8.4")

    def couleurs(plan):
        resume = resume_video(source, plan, "", libre=10**12)
        ligne = next(ligne for ligne in resume.lignes if ligne.titre == "Couleurs")
        return (ligne.source, ligne.export, ligne.differente), resume

    (ligne, resume) = couleurs(plan_video(source, MP4, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4"))
    assert ligne == ("HDR (HLG, Dolby Vision), 10 bits", "HDR (HLG, Dolby Vision), 10 bits", False)
    assert resume.possible and not resume.avertissements
    (ligne, resume) = couleurs(plan_video(source, MOV, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mov"))
    assert ligne == ("HDR (HLG, Dolby Vision), 10 bits", "HDR (HLG), 10 bits", True)
    assert resume.possible and "Dolby Vision n'est gardé qu'en MP4 ou en MKV" in resume.avertissements[0]
    (ligne, resume) = couleurs(plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4", convertir_en_sdr=True))
    assert ligne == ("HDR (HLG, Dolby Vision), 10 bits", "SDR (BT.709), 8 bits", True) and not resume.avertissements
    pq = _source(tmp_path, couleurs=PQ_HDR10, dolby_vision="8.1")
    resume = resume_video(pq, plan_video(pq, MP4, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4"), "", libre=10**12)
    assert "(profil 8.1) ne sont pas gardées : elle reste en HDR (PQ)" in resume.avertissements[0]
    streaming = _source(tmp_path, couleurs=CouleursDeLaVideo("yuv420p10le", "tv", "", "", ""), dolby_vision="5")
    resume = resume_video(streaming, plan_video(streaming, MP4, H265, DEBIT_CONSEILLE, 0, tmp_path / "v.mp4"), "")
    assert not resume.possible and "profil 5" in resume.erreurs[0]


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


def _png16(largeur: int, hauteur: int, carre: tuple[int, int, int, int] | None) -> bytes:
    """Un PNG RGBA de 16 bits par couleur : transparent, avec un carré jaune #FFD43B opaque."""
    vide, jaune = bytes(8), struct.pack(">4H", 0xFFFF, 0xD4D4, 0x3B3B, 0xFFFF)
    lignes = []
    for y in range(hauteur):
        dedans = carre is not None and carre[1] <= y < carre[3]
        lignes.append(b"\0" + b"".join(jaune if dedans and carre[0] <= x < carre[2] else vide for x in range(largeur)))

    def morceau(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 16, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + morceau(b"IHDR", entete) + morceau(b"IDAT", zlib.compress(b"".join(lignes))) + morceau(b"IEND", b"")


@avec_ffmpeg
def test_calque_provisoire_de_16_bits_relu(tmp_path):
    """Calque provisoire d'une vidéo en 10 bits : des PNG de 16 bits, transparent, puis un carré, puis
    transparent ; relu par FFmpeg, chaque image est la bonne (transparence et couleur)."""
    ecriture = EcritureMovPng(tmp_path / "calque.mov", 32, 24, 600)
    ecriture.ajouter(_png16(32, 24, None), 20)
    ecriture.ajouter(_png16(32, 24, (8, 6, 24, 18)), 20)
    ecriture.ajouter(_png16(32, 24, None), 20)
    ecriture.fermer()
    for numero, attendu in ((0, (0, 0, 0, 0)), (1, (0xFFFF, 0xD4D4, 0x3B3B, 0xFFFF)), (2, (0, 0, 0, 0))):
        brut = executer(
            [str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(tmp_path / "calque.mov"),
             "-vf", f"select=eq(n\\,{numero})", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba64le", "-"],
            60, binaire=True,
        ).stdout
        assert len(brut) == 32 * 24 * 8, numero
        assert struct.unpack_from("<4H", brut, (12 * 32 + 16) * 8) == attendu, numero


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
         "-vf", f"select=eq(n\\,{numero}),{lecture_en_rgb()},format=gbrp,format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"],
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
    _calque_blanc_et_jaune(prores, tmp_path / "calque.mov", seize_bits=True)  # PNG de 16 bits, comme ceux de l'app
    _exporter(prores, tmp_path / "calque.mov", tmp_path)
    assert _proches(_pixel_rgb(prores.en_cours, 4, 10, 24, 64, 48), (255, 255, 255), 4)
    assert _proches(_pixel_rgb(prores.en_cours, 4, 50, 24, 64, 48), (255, 212, 59), 6)
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


def _echantillons(video: Path, frequence: int = 48_000) -> array.array:
    """Le son d'une vidéo, décodé en mono 16 bits."""
    brut = executer(
        [str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video), "-map", "0:a:0",
         "-ac", "1", "-ar", str(frequence), "-f", "s16le", "-"],
        60, binaire=True,
    ).stdout
    return array.array("h", brut[: len(brut) // 2 * 2])


def _niveau_et_passages(echantillons: array.array, debut: float, fin: float, frequence: int = 48_000) -> tuple[float, float]:
    """Niveau moyen (0 à 32 767) et passages par zéro par seconde, entre deux moments."""
    morceau = echantillons[round(debut * frequence) : round(fin * frequence)]
    niveau = sum(abs(e) for e in morceau) / max(len(morceau), 1)
    passages = sum(1 for a, b in zip(morceau, morceau[1:], strict=False) if (a < 0) != (b < 0))
    return niveau, passages / (fin - debut)


@avec_ffmpeg
def test_export_avec_la_voix_des_sous_titres_reel(tmp_path):
    """V3.1, lot 6 : le montage (1 s, avec son propre son à 440 Hz) et la voix d'une prise (0,4 s à
    1 000 Hz, 24 kHz mono comme une prise) qui y commence à 0,3 s. L'export a le son de la voix, au
    bon moment, et dure exactement la vidéo : silence avant et après la voix, plus le son du montage."""
    montage = tmp_path / "montage.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=64x48:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(montage))
    voix = tmp_path / "prise-002.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=24000", "-t", "0.4", "-ac", "1", "-c:a", "pcm_s16le", str(voix))
    source = replace(_source_reelle(montage), voix=voix, decalage_s=0.3)
    plan = plan_video(source, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "montage (sous-titres).mp4")
    _calque_jaune(plan, tmp_path / "calque.mov", 3)
    _exporter(plan, tmp_path / "calque.mov", tmp_path)
    sortie = analyser(plan.en_cours)
    assert sortie.son is not None and sortie.son.codec == "aac" and sortie.images.nombre == 30
    echantillons = _echantillons(plan.en_cours)
    assert abs(len(echantillons) / 48_000 - 1.0) < 0.05  # le son s'arrête avec la vidéo
    avant, _ = _niveau_et_passages(echantillons, 0.0, 0.25)
    pendant, passages = _niveau_et_passages(echantillons, 0.35, 0.65)
    apres, _ = _niveau_et_passages(echantillons, 0.75, 0.95)
    # La sinusoïde de FFmpeg est au huitième du maximum : niveau moyen ≈ 4 096 × 2/π ≈ 2 600.
    assert avant < 50 and apres < 50 and pendant > 1500, (avant, pendant, apres)
    assert 1800 < passages < 2200  # 1 000 Hz : la voix, pas le son du montage (440 Hz)


def _calque_blanc_et_jaune(plan, chemin: Path, seize_bits: bool = False) -> None:
    """Calque : moitié gauche blanche, moitié droite jaune #FFD43B, opaques, sur toute la vidéo ; en
    PNG de 8 ou de 16 bits par couleur (ceux de l'app pour une vidéo en 10 bits)."""
    largeur, hauteur = plan.largeur, plan.hauteur
    if seize_bits:
        blanc, jaune = struct.pack(">4H", 65535, 65535, 65535, 65535), struct.pack(">4H", 65535, 212 * 257, 59 * 257, 65535)
    else:
        blanc, jaune = bytes((255, 255, 255, 255)), bytes((255, 212, 59, 255))
    ligne = blanc * (largeur // 2) + jaune * (largeur - largeur // 2)
    brut = b"".join(b"\0" + ligne for _ in range(hauteur))

    def morceau(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 16 if seize_bits else 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + morceau(b"IHDR", entete) + morceau(b"IDAT", zlib.compress(brut)) + morceau(b"IEND", b""))
    images = plan.images
    ecriture = EcritureMovPng(chemin, largeur, hauteur, images.base_de_temps.denominator)
    ecriture.ajouter(png, images.moments[-1] - images.moments[0] + images.duree_derniere)
    ecriture.fermer()


def _source_hdr(tmp_path: Path, courbe: str) -> Source:
    """Une vidéo HDR (H.265, 10 bits, BT.2020) fabriquée par FFmpeg : la mire de FFmpeg convertie en HLG
    ou en PQ, son blanc au blanc de référence."""
    chemin = tmp_path / f"hdr-{courbe}.mov"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x64:rate=30", "-t", "0.4",
            "-vf", f"zscale=rin=limited:pin=bt709:tin=bt709:min=bt709:p=bt2020:t={courbe}:m=bt2020nc:r=limited:npl=203,"
                   f"format=yuv420p10le,setparams=color_primaries=bt2020:color_trc={courbe}:colorspace=bt2020nc:range=tv",
            "-c:v", "libx265", "-x265-params", "log-level=error", "-tag:v", "hvc1", str(chemin))
    return _source_reelle(chemin)


def _yuv10(video: Path, x: int, y: int, largeur: int) -> int:
    """La luminance (Y, sur 1 023) d'un point de la première image, en 10 bits."""
    brut = executer([str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video), "-frames:v", "1",
                     "-f", "rawvideo", "-pix_fmt", "yuv420p10le", "-"], 60, binaire=True).stdout
    return struct.unpack_from("<H", brut, (y * largeur + x) * 2)[0]


def _rgb_depuis_le_hdr(video: Path, x: int, y: int, largeur: int) -> tuple[int, int, int]:
    """Un point de la première image d'une vidéo HDR, ramené en SDR avec le même blanc de référence :
    les couleurs des sous-titres d'origine."""
    brut = executer([str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video), "-frames:v", "1",
                     "-vf", "zscale=p=bt709:t=bt709:m=bt709:r=full:npl=203,format=rgb24", "-f", "rawvideo", "-"], 60, binaire=True).stdout
    debut = (y * largeur + x) * 3
    return tuple(brut[debut : debut + 3])


def _proches(a, b, ecart: int) -> bool:
    return all(abs(p - q) <= ecart for p, q in zip(a, b, strict=True))


@avec_ffmpeg
def test_export_hdr_reel(tmp_path):
    """HLG gardé (H.265, 10 bits) : le blanc des sous-titres à 75 % du signal (Y = 721 sur 1 023), et
    leur jaune redevient #FFD43B une fois ramené en SDR ; PQ en ProRes : 58 % (Y = 573)."""
    hlg = _source_hdr(tmp_path, "arib-std-b67")
    assert hlg.analyse.couleurs.hlg and hlg.analyse.couleurs.bits == 10
    plan = plan_video(hlg, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "hlg (sous-titres).mp4")
    assert plan.codec == H265 and plan.calque_16_bits
    for seize_bits in (False, True):  # l'app donne des PNG de 16 bits pour une vidéo en 10 bits
        _calque_blanc_et_jaune(plan, tmp_path / "calque.mov", seize_bits)
        _exporter(plan, tmp_path / "calque.mov", tmp_path)
        sortie = analyser(plan.en_cours)
        couleurs = sortie.couleurs
        assert sortie.images.codec == "hevc" and sortie.images.nombre == hlg.analyse.images.nombre
        assert (couleurs.format_pixels, couleurs.plage, couleurs.matrice, couleurs.primaires, couleurs.transfert) == (
            "yuv420p10le", "tv", "bt2020nc", "bt2020", "arib-std-b67"
        )
        assert abs(_yuv10(plan.en_cours, 20, 32, 96) - 721) <= 4, seize_bits  # blanc de référence : 75 % de 64 à 940
        assert _proches(_rgb_depuis_le_hdr(plan.en_cours, 20, 32, 96), (255, 255, 255), 4), seize_bits
        assert _proches(_rgb_depuis_le_hdr(plan.en_cours, 70, 32, 96), (255, 212, 59), 6), seize_bits

    pq = _source_hdr(tmp_path, "smpte2084")
    prores = plan_video(pq, MOV, PRORES, DEBIT_CONSEILLE, 0, tmp_path / "pq (sous-titres).mov")
    _calque_blanc_et_jaune(prores, tmp_path / "calque.mov", seize_bits=True)
    _exporter(prores, tmp_path / "calque.mov", tmp_path)
    sortie = analyser(prores.en_cours)
    assert sortie.images.codec == "prores" and sortie.couleurs.pq and sortie.couleurs.format_pixels.startswith("yuv422p10")
    assert abs(_yuv10(prores.en_cours, 20, 32, 96) - 573) <= 3  # blanc de référence : 58 % en PQ


@avec_ffmpeg
def test_export_converti_en_sdr_reel(tmp_path):
    """« Convertir en SDR » : H.264, 8 bits, étiquettes BT.709 ; les sous-titres gardent exactement
    leurs couleurs (blanc et jaune), et l'image de la vidéo a changé de couleurs (lumière, BT.709)."""
    hlg = _source_hdr(tmp_path, "arib-std-b67")
    plan = plan_video(hlg, MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / "hlg (sous-titres).mp4", convertir_en_sdr=True)
    _calque_blanc_et_jaune(plan, tmp_path / "calque.mov")
    _exporter(plan, tmp_path / "calque.mov", tmp_path)
    sortie = analyser(plan.en_cours)
    couleurs = sortie.couleurs
    assert sortie.images.codec == "h264" and couleurs.bits == 8 and not couleurs.hdr
    assert (couleurs.plage, couleurs.matrice, couleurs.primaires, couleurs.transfert) == ("tv", "bt709", "bt709", "bt709")
    assert _proches(_pixel_rgb(plan.en_cours, 0, 20, 32, 96, 64), (255, 255, 255), 4)
    assert _proches(_pixel_rgb(plan.en_cours, 0, 70, 32, 96, 64), (255, 212, 59), 6)


def _sait_garder_dolby_vision() -> bool:
    """FFmpeg 7.1 et plus (celui de l'app : 9.0.2) : x265 reprend Dolby Vision (option « -dolbyvision »)."""
    if FFMPEG is None:
        return False
    return "-dolbyvision" in executer([str(FFMPEG), "-hide_banner", "-h", "encoder=libx265"], 60).stdout


@pytest.mark.skipif(not _sait_garder_dolby_vision(), reason="FFmpeg sans Dolby Vision pour x265 (celui de l'app le sait)")
def test_export_dolby_vision_reel(tmp_path):
    """Une vidéo d'iPhone en HDR (HLG et Dolby Vision 8.4, fabriquée par video_dolby_vision.py) : en MP4
    et en MKV, l'export reste en Dolby Vision 8.4 (description du fichier, et informations de chaque
    image) ; en MOV, il reste en HDR (HLG), sans Dolby Vision."""
    chemin = tmp_path / "IMG_0420.mp4"
    fabriquer_video_dolby_vision(executer, FFMPEG, chemin)
    source = _source_reelle(chemin)
    assert source.analyse.dolby_vision == "8.4" and source.analyse.couleurs.hlg
    for conteneur in (MP4, MKV, MOV):
        plan = plan_video(source, conteneur, H265, DEBIT_CONSEILLE, 0, tmp_path / f"IMG_0420 (sous-titres).{conteneur}")
        assert plan.dolby_vision == (conteneur != MOV)
        _calque_blanc_et_jaune(plan, tmp_path / "calque.mov")
        _exporter(plan, tmp_path / "calque.mov", tmp_path)
        sortie = analyser(plan.en_cours)
        assert sortie.couleurs.hlg and sortie.images.nombre == source.analyse.images.nombre, conteneur
        images = executer([str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "info", "-i", str(plan.en_cours),
                           "-vf", "showinfo", "-frames:v", "3", "-f", "null", "-"], 60).stderr
        if conteneur == MOV:
            assert sortie.dolby_vision == "" and "Dolby Vision Metadata" not in images
        else:
            assert sortie.dolby_vision == "8.4", conteneur  # boîte dvvC (MP4), ou sa place dans le MKV
            assert images.count("Dolby Vision Metadata") >= 3, conteneur  # chaque image a ses informations
        assert abs(_yuv10(plan.en_cours, 20, 48, 128) - 721) <= 4  # sous-titres au blanc de référence


def _png_carre_blanc(largeur: int, hauteur: int, carre: tuple[int, int, int, int]) -> bytes:
    """Un PNG RGBA de 8 bits : transparent, avec un carré blanc opaque (gauche, haut, droite, bas)."""
    vide, blanc = bytes(4), bytes((255, 255, 255, 255))
    lignes = [b"\0" + b"".join(blanc if carre[0] <= x < carre[2] and carre[1] <= y < carre[3] else vide for x in range(largeur))
              for y in range(hauteur)]

    def morceau(nom: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees))

    entete = struct.pack(">IIBBBBB", largeur, hauteur, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + morceau(b"IHDR", entete) + morceau(b"IDAT", zlib.compress(b"".join(lignes))) + morceau(b"IEND", b"")


def _luminances(video: Path, largeur: int, hauteur: int, bits: int) -> list[int]:
    """La luminance (Y) de chaque point de la première image, telle qu'elle est dans la vidéo."""
    format_ = "yuv420p" if bits == 8 else "yuv420p10le"
    brut = executer([str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video), "-frames:v", "1",
                     "-f", "rawvideo", "-pix_fmt", format_, "-"], 60, binaire=True).stdout
    if bits == 8:
        return list(brut[: largeur * hauteur])
    return [valeur for (valeur,) in struct.iter_unpack("<H", brut[: largeur * hauteur * 2])]


@avec_ffmpeg
def test_sous_titres_du_bas_d_une_image_haute(tmp_path):
    """Défaut de zscale (FFmpeg 8.1 et plus, voir vers_le_format) : sur une image haute, découpée en
    bandes, la transparence des bandes du bas était rangée trop haut en 4:2:0 ; des sous-titres du bas
    disparaissaient (vu sur la fabrication, lot 3). Une vidéo grise de 96 × 512, un carré blanc sur les
    lignes 440 à 470 : en H.264 (SDR) comme en H.265 HLG (10 bits), il est là, et rien d'autre ne change."""
    largeur, hauteur, carre = 96, 512, (30, 440, 60, 470)
    sdr = "format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
    hlg = ("zscale=rin=limited:pin=bt709:tin=bt709:min=bt709:p=bt2020:t=arib-std-b67:m=bt2020nc:r=limited:npl=203,"
           "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc:range=tv")
    for nom, filtres, encodeur, codec, bits, blanc, ecart_du_blanc, ecart_ailleurs in (
        ("sdr", sdr, ["libx264"], H264, 8, 235, 3, 4),
        ("hlg", hlg, ["libx265", "-x265-params", "log-level=error"], H265, 10, 721, 8, 16),
    ):
        source_chemin = tmp_path / f"{nom}.mov"
        _ffmpeg("-f", "lavfi", "-i", f"color=c=0x808080:size={largeur}x{hauteur}:rate=30", "-t", "0.2",
                "-vf", filtres, "-c:v", *encodeur, str(source_chemin))
        source = _source_reelle(source_chemin)
        plan = plan_video(source, MP4, codec, DEBIT_CONSEILLE, 0, tmp_path / f"{nom} (sous-titres).mp4")
        assert plan.bits == bits
        images = plan.images
        ecriture = EcritureMovPng(tmp_path / "calque.mov", largeur, hauteur, images.base_de_temps.denominator)
        ecriture.ajouter(_png_carre_blanc(largeur, hauteur, carre), images.moments[-1] - images.moments[0] + images.duree_derniere)
        ecriture.fermer()
        _exporter(plan, tmp_path / "calque.mov", tmp_path)
        avant, apres = _luminances(source_chemin, largeur, hauteur, bits), _luminances(plan.en_cours, largeur, hauteur, bits)
        assert abs(apres[455 * largeur + 45] - blanc) <= ecart_du_blanc, (nom, apres[455 * largeur + 45])  # le carré, à sa place
        ailleurs = [
            abs(a - b) for n, (a, b) in enumerate(zip(avant, apres, strict=True))
            if not (carre[0] - 8 <= n % largeur < carre[2] + 8 and carre[1] - 8 <= n // largeur < carre[3] + 8)
        ]
        assert max(ailleurs) <= ecart_ailleurs, (nom, max(ailleurs))  # pas de bande sombre plus haut


def test_rien_d_inutile_dans_les_commandes(tmp_path):
    """Aucune commande n'utilise le shell : la liste d'arguments va telle quelle à FFmpeg (un nom de
    fichier avec des espaces ou des guillemets ne pose pas de problème)."""
    plan = plan_video(_source(tmp_path), MP4, H264, DEBIT_CONSEILLE, 0, tmp_path / 'Pub "été" (sous-titres).mp4')
    commande = commande_video(Path("C:/Program Files/ffmpeg.exe"), plan, tmp_path / "calque.mov", 2, tmp_path / "p")
    assert commande[-1].endswith('Pub "été" (sous-titres).mp4.en-cours') and all(isinstance(a, str) for a in commande)
    assert subprocess.list2cmdline(commande)  # Windows saura la transmettre
