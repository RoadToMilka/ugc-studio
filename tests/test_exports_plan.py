"""V3, lots 1 et 3 (§8.2, §8.4, §8.5) : ce qui sera exporté (source, nom, dossier, fréquence, nombre
d'images, couleurs du calque) et le résumé avant export, sans interface."""

from fractions import Fraction
from pathlib import Path

from dataclasses import replace

from ugc_studio.exports.ffmpeg import CouleursDeLaVideo, NormeHDR, lire_analyse
from ugc_studio.exports.plan import (
    PlanCalque,
    debit_lisible,
    duree_d_export_lisible,
    nom_propose,
    plan_du_calque,
    poids_lisible,
    resume_calque,
    source_du_projet,
    texte_des_sous_titres,
)
from ugc_studio.projets import Projet
from ugc_studio.style_sous_titres import VideoApercu
from ugc_studio.transcription import Mot, Transcription

INFOS_VIDEO = {
    "duree_s": 31.06, "video": True, "resolution": [1920, 1080], "rotation": 90,  # téléphone « couché »
    "images_par_seconde": 29.97002997, "codec_video": "H264", "debit_video": 12_400_000,
    "codec_audio": "AAC", "debit_audio": 256_000, "format": "MPEG4", "hdr": False,
}


def _projet_video(dossier: Path, infos: dict | None = None) -> Projet:
    video = dossier / "Vidéos" / "Sérum Glowzy.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"\0" * 1000)
    projet = Projet(dossier / "Projet", "Sérum Glowzy")
    projet.dossier.mkdir()
    projet.transcription = Transcription(source=str(video), duree_s=31.06, infos=infos or dict(INFOS_VIDEO), mots=[Mot("Salut", 0.1, 0.4)])
    return projet


def _projet_prise(dossier: Path) -> Projet:
    projet = Projet(dossier / "Projet", "Voix Glowzy")
    projet.dossier.mkdir(parents=True)
    projet.transcription = Transcription(source="Prise 3", audio="sources/audio.wav", duree_s=12.34, prise="prise-003", mots=[Mot("Salut", 0.1, 0.4)])
    return projet


def test_source_video_lue_par_qt(tmp_path):
    source = source_du_projet(_projet_video(tmp_path))
    assert source.video and (source.largeur, source.hauteur) == (1080, 1920)  # remise debout
    assert source.frequence == Fraction(30000, 1001) and source.nombre_images is None
    assert (source.format, source.codec_video, source.codec_audio) == ("MP4", "H.264", "AAC")
    assert (source.debit_video, source.debit_audio, source.poids, source.hdr) == (12_400_000, 256_000, 1000, False)
    assert source.dossier == tmp_path / "Vidéos" and not source.prise


def test_source_completee_par_ffmpeg(tmp_path):
    """FFmpeg compte les images, donne la fréquence exacte et les vrais débits ; Qt ne connaît pas le
    ProRes (« Unspecified ») : FFmpeg le nomme."""
    infos = dict(INFOS_VIDEO, codec_video="Unspecified", images_par_seconde=29.98)
    texte = "#tb 0: 1/30000\n#media_type 0: video\n#codec_id 0: prores\n" + "".join(
        f"0, {n * 1001}, {n * 1001}, 1001, 500000, 0x0\n" for n in range(930)
    )
    source = source_du_projet(_projet_video(tmp_path, infos), lire_analyse(texte))
    assert source.frequence == Fraction(30000, 1001) and source.frequence_constante
    assert source.nombre_images == 930 and source.codec_video == "ProRes"
    assert source.codec_audio == ""  # FFmpeg n'a pas trouvé de son : vidéo muette
    assert round(source.duree_s, 3) == round(930 * 1001 / 30000, 3)


def test_couleurs_de_la_source_lues_par_ffmpeg(tmp_path):
    """Qt ne disait rien du HDR (projet importé avec la 2.0.0) : FFmpeg donne les couleurs, et le
    résumé les montre ; le calque d'une vidéo HDR est en HDR (lot 3), sauf « Convertir en SDR »."""
    infos = dict(INFOS_VIDEO)
    del infos["hdr"]
    projet = _projet_video(tmp_path, infos)
    analyse = lire_analyse("#tb 0: 1/30000\n#media_type 0: video\n#codec_id 0: hevc\n0, 0, 0, 1001, 9000, 0x0\n0, 1001, 1001, 1001, 9000, 0x0\n")
    hlg = CouleursDeLaVideo("yuv420p10le", "tv", "bt2020nc", "bt2020", "arib-std-b67")
    source = source_du_projet(projet, replace(analyse, couleurs=hlg))
    assert source.couleurs == hlg and source.hdr
    plan = plan_du_calque(source, 1080, 1920, None, tmp_path / "c.mov")
    assert plan.hdr == NormeHDR("bt2020nc", "bt2020", "arib-std-b67")
    resume = resume_calque(source, plan, "")
    lignes = {ligne.titre: ligne for ligne in resume.lignes}
    assert (lignes["Couleurs"].source, lignes["Couleurs"].export) == ("HDR (HLG), 10 bits", "HDR (HLG), 10 bits + transparence")
    assert not any("HDR" in texte for texte in resume.avertissements)
    converti = plan_du_calque(source, 1080, 1920, None, tmp_path / "c.mov", convertir_en_sdr=True)
    assert converti.hdr is None
    lignes = {ligne.titre: ligne for ligne in resume_calque(source, converti, "").lignes}
    assert lignes["Couleurs"].export == "SDR (BT.709), 10 bits + transparence" and lignes["Couleurs"].differente
    sdr = CouleursDeLaVideo("yuv420p", "tv", "bt709", "bt709", "bt709")
    source = source_du_projet(projet, replace(analyse, couleurs=sdr))
    assert not source.hdr and source.couleurs.texte() == "SDR, 8 bits"
    assert plan_du_calque(source, 1080, 1920, None, tmp_path / "c.mov").hdr is None
    assert source_du_projet(projet).hdr is None  # sans FFmpeg ni Qt : inconnu


def test_source_d_une_prise(tmp_path):
    projet = _projet_prise(tmp_path)
    source = source_du_projet(projet)
    assert not source.video and source.prise and source.chemin is None and source.dossier is None
    assert source.duree_s == 12.34
    projet.sous_titres.apercu = VideoApercu(str(tmp_path / "Montage" / "montage.mp4"), 1.5, 1080, 1920)
    assert source_du_projet(projet).dossier == tmp_path / "Montage"  # dossier de la vidéo d'aperçu


def test_nom_propose(tmp_path):
    projet = _projet_video(tmp_path)
    assert nom_propose(source_du_projet(projet), projet) == "Sérum Glowzy (calque)"
    prise = _projet_prise(tmp_path / "b")
    assert nom_propose(source_du_projet(prise), prise) == "Voix Glowzy (calque)"
    prise.nom = 'Pub : "été" ?'
    assert nom_propose(source_du_projet(prise), prise) == "Pub été (calque)"  # caractères interdits sous Windows


def test_plan_d_une_video(tmp_path):
    source = source_du_projet(_projet_video(tmp_path))
    plan = plan_du_calque(source, 1080, 1920, Fraction(60), tmp_path / "c.mov")
    assert plan.frequence == Fraction(30000, 1001)  # celle de la vidéo, pas celle choisie
    assert plan.nombre_images == 931  # 31,06 s : de quoi couvrir la durée (Qt n'a pas compté les images)
    assert plan.temps(17_982) == 17_982 * 1001 / 30000
    assert plan.en_cours == tmp_path / "c.mov.en-cours"


def test_plan_d_une_prise(tmp_path):
    source = source_du_projet(_projet_prise(tmp_path))
    plan = plan_du_calque(source, 1080, 1920, None, tmp_path / "c.mov")
    assert plan.frequence == Fraction(30) and plan.nombre_images == 371  # 12,34 s à 30 : 371 images
    assert plan.hdr is None  # sans vidéo : SDR (BT.709), décision du 02/10/2026
    assert plan_du_calque(source, 1080, 1920, Fraction(60), tmp_path / "c.mov").nombre_images == 741


def test_poids_maximum_du_prores_4444():
    """330 Mb/s pour 1920 × 1080 à 29,97 (Apple) : environ 41 Mo par seconde en 1080 × 1920."""
    plan = PlanCalque(1080, 1920, Fraction(30000, 1001), 900, Path("c.mov"))
    assert round(plan.poids_max / plan.duree_s / 1e6, 2) == 41.25
    assert poids_lisible(plan.poids_max) == "1,2 Go"
    petit = PlanCalque(540, 960, Fraction(30000, 1001), 900, Path("c.mov"))
    assert round(petit.poids_max / plan.poids_max, 3) == 0.25


def test_resume_du_calque(tmp_path):
    projet = _projet_video(tmp_path)
    source = source_du_projet(projet)
    plan = plan_du_calque(source, 1080, 1920, None, tmp_path / "Vidéos" / "Sérum Glowzy (calque).mov")
    resume = resume_calque(source, plan, texte_des_sous_titres(14, "Karaoké"), libre=10**12)
    lignes = {ligne.titre: ligne for ligne in resume.lignes}
    assert list(lignes) == ["Taille", "Images par seconde", "Format et codec", "Son", "Couleurs", "Durée", "Poids", "Sous-titres"]
    assert (lignes["Taille"].source, lignes["Taille"].export, lignes["Taille"].differente) == ("1080 × 1920", "1080 × 1920", False)
    assert (lignes["Images par seconde"].source, lignes["Images par seconde"].differente) == ("29,97", False)
    assert lignes["Format et codec"].source == "MP4, H.264" and lignes["Format et codec"].differente  # en mauve
    assert lignes["Son"].source == "AAC, 256 kb/s" and lignes["Son"].differente
    assert lignes["Couleurs"].source == "SDR" and lignes["Couleurs"].export.startswith("SDR (BT.709)")
    assert (lignes["Durée"].source, lignes["Durée"].export) == ("0:31", "0:31")
    assert lignes["Poids"].export.startswith("≈ ") and not lignes["Poids"].differente
    assert lignes["Sous-titres"].export == "14 sous-titres, préréglage « Karaoké »"
    assert resume.possible and not resume.avertissements


def test_resume_avertissements_et_erreurs(tmp_path):
    projet = _projet_video(tmp_path, dict(INFOS_VIDEO, hdr=True))
    texte = "#tb 0: 1/600\n#media_type 0: video\n#codec_id 0: hevc\n" + "".join(
        f"0, {m}, {m}, 20, 1000, 0x0\n" for m in (0, 20, 40, 60, 100, 120, 140)  # une image sautée : variable
    )
    source = source_du_projet(projet, lire_analyse(texte))
    existant = tmp_path / "Vidéos" / "déjà là.mov"
    existant.write_bytes(b"x")
    resume = resume_calque(source, plan_du_calque(source, 1080, 1920, None, existant), "3 sous-titres", libre=1000)
    textes = " ".join(resume.avertissements)
    assert "fréquence d'images variable" in textes and "30 images" in textes
    assert "existe déjà" in textes and "Place libre" in textes
    assert resume.possible  # des avertissements, rien qui empêche l'export
    # Ce qui empêche l'export : la vidéo elle-même, un dossier absent, un nom vide.
    for sortie, motif in (
        (Path(projet.transcription.source), "C'est le nom de ta vidéo"),
        (tmp_path / "absent" / "x.mov", "n'existe pas"),
        (tmp_path / ".mov", "Donne un nom"),
    ):
        resume = resume_calque(source, plan_du_calque(source, 1080, 1920, None, sortie), "", libre=None)
        assert not resume.possible and motif in resume.erreurs[0], sortie


def test_resume_d_une_prise(tmp_path):
    source = source_du_projet(_projet_prise(tmp_path))
    plan = plan_du_calque(source, 1080, 1920, None, tmp_path / "Projet" / "Voix Glowzy (calque).mov")
    lignes = {ligne.titre: ligne for ligne in resume_calque(source, plan, "").lignes}
    assert (lignes["Taille"].source, lignes["Taille"].differente) == ("son seul", False)
    assert (lignes["Images par seconde"].source, lignes["Images par seconde"].export) == ("aucune", "30")
    assert lignes["Format et codec"].source == "WAV"


def test_textes_lisibles():
    assert poids_lisible(850_000) == "830 Ko"
    assert poids_lisible(5.5 * 1024**2) == "5,5 Mo"
    assert poids_lisible(52 * 1024**2) == "52 Mo"
    assert poids_lisible(None) == "inconnu"
    assert debit_lisible(12_400_000) == "12,4 Mb/s" and debit_lisible(256_000) == "256 kb/s"
    assert duree_d_export_lisible(12.4) == "12 s" and duree_d_export_lisible(72) == "1 min 12 s"
    assert texte_des_sous_titres(1, "") == "1 sous-titre"
