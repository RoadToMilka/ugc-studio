"""Module Comparer (V4.1, 4.2.0) : video-compare trouvé, installé depuis son zip, vérifié, lancé avec
les bons réglages ; ses mesures et ses captures mises en français (avec un faux video-compare)."""

import sys
import time
import zipfile
from pathlib import Path

import pytest

from ugc_studio.comparer import faux
from ugc_studio.comparer.video_compare import (
    COTE_A_COTE,
    CURSEUR,
    EMPILEES,
    NOM_PROGRAMME,
    PLEIN_ECRAN,
    TAILLE_VIDEO,
    Comparaison,
    Reglages,
    VideoCompare,
    VideoCompareIntrouvable,
    arguments,
    dans_les_telechargements,
    installations,
    installer,
    lire_la_version,
    lire_le_choix,
    lire_les_captures,
    lire_les_mesures,
    programme_dans,
    trouver,
)

FAUX = (sys.executable, str(Path(faux.__file__)))


def _zip(dossier: Path, nom: str = "video-compare-20261004-win10-x86_64.zip", avec_programme: bool = True) -> Path:
    """Un zip comme celui de la page de video-compare : ses fichiers à la racine (le .exe, ses
    bibliothèques, ses licences)."""
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    with zipfile.ZipFile(chemin, "w") as contenu:
        if avec_programme:
            contenu.writestr(NOM_PROGRAMME, b"MZ programme")
        contenu.writestr("avcodec-62.dll", b"bibliotheque")
        contenu.writestr("LICENSE.md", "GPL v2")
        contenu.writestr("licenses/THIRD-PARTY-NOTICES.txt", "FFmpeg, SDL2")
    return chemin


def test_trouver_video_compare(tmp_path):
    telechargements, racine = tmp_path / "Téléchargements", tmp_path / "programmes" / "video-compare"
    telechargements.mkdir()
    assert trouver(None, telechargements, racine).programme is None  # rien nulle part
    # Le zip téléchargé, laissé dans Téléchargements : à installer.
    archive = _zip(telechargements)
    (telechargements / "autre.zip").write_bytes(b"")
    trouvaille = trouver(None, telechargements, racine)
    assert trouvaille.archive == archive and trouvaille.programme is None and trouvaille.ou == "dans tes Téléchargements"
    # Décompressé par l'utilisateur (« Extraire tout » : un dossier au nom du zip) : utilisable tel quel.
    decompresse = telechargements / "video-compare-20261004-win10-x86_64"
    decompresse.mkdir()
    (decompresse / NOM_PROGRAMME).write_bytes(b"MZ")
    assert dans_les_telechargements(telechargements).programme == decompresse / NOM_PROGRAMME
    # Une copie installée par l'app passe avant les Téléchargements ; la plus récente d'abord.
    for version in ("video-compare-20260828-win10-x86_64", "video-compare-20261004-win10-x86_64"):
        (racine / version).mkdir(parents=True)
        (racine / version / NOM_PROGRAMME).write_bytes(b"MZ")
    (racine / "video-compare-20991231-win10-x86_64.en-cours").mkdir()  # installation coupée : ignorée
    assert installations(racine)[0] == racine / "video-compare-20261004-win10-x86_64" / NOM_PROGRAMME
    assert trouver(None, telechargements, racine).ou == "installé par l'app"
    # Le choix de l'utilisateur passe avant tout, s'il existe encore.
    choisi = tmp_path / "Outils" / NOM_PROGRAMME
    choisi.parent.mkdir()
    choisi.write_bytes(b"MZ")
    assert trouver(choisi, telechargements, racine).programme == choisi
    assert trouver(tmp_path / "disparu.exe", telechargements, racine).ou == "installé par l'app"
    # Un zip choisi puis installé : la copie installée, pas le zip à nouveau.
    assert trouver(archive, telechargements, racine).programme == racine / archive.stem / NOM_PROGRAMME


def test_lire_le_choix(tmp_path):
    archive = _zip(tmp_path)
    assert lire_le_choix(archive).archive == archive
    (tmp_path / "vc" / "bin").mkdir(parents=True)
    (tmp_path / "vc" / "bin" / NOM_PROGRAMME).write_bytes(b"MZ")
    assert lire_le_choix(tmp_path / "vc" / "bin" / NOM_PROGRAMME).programme == tmp_path / "vc" / "bin" / NOM_PROGRAMME
    assert lire_le_choix(tmp_path / "vc").programme == tmp_path / "vc" / "bin" / NOM_PROGRAMME  # un sous-dossier
    assert programme_dans(tmp_path / "rien") is None
    autre = tmp_path / "notes.txt"
    autre.write_text("non", encoding="utf-8")
    assert not lire_le_choix(autre).programme and not lire_le_choix(autre).archive


def test_installer_le_zip(tmp_path):
    archive = _zip(tmp_path / "Téléchargements")
    racine = tmp_path / "programmes" / "video-compare"
    avancees = []
    programme = installer(archive, avancees.append, racine)
    assert programme == racine / "video-compare-20261004-win10-x86_64" / NOM_PROGRAMME and programme.is_file()
    assert (programme.parent / "licenses" / "THIRD-PARTY-NOTICES.txt").is_file()  # tout le contenu, licences comprises
    assert archive.is_file()  # le zip ne bouge pas
    assert avancees[-1] == 1.0 and not list(racine.glob("*.en-cours"))
    # Réinstaller remplace la copie précédente.
    assert installer(archive, None, racine) == programme


def test_zips_refuses(tmp_path):
    racine = tmp_path / "programmes"
    with pytest.raises(VideoCompareIntrouvable, match="ne contient pas video-compare.exe"):
        installer(_zip(tmp_path, "video-compare-macos.zip", avec_programme=False), None, racine)
    abime = tmp_path / "video-compare-coupe.zip"
    abime.write_bytes(b"PK\x03\x04 pas fini")
    with pytest.raises(VideoCompareIntrouvable, match="pas un zip lisible"):
        installer(abime, None, racine)
    assert not list(racine.glob("**/*.en-cours"))  # rien de bancal


def test_lire_la_version():
    assert lire_la_version(FAUX) == "20261004-osaka"
    with pytest.raises(VideoCompareIntrouvable, match="ne répond pas comme prévu"):
        lire_la_version((sys.executable, "-c", "import sys; sys.exit(3)"))
    with pytest.raises(VideoCompareIntrouvable, match="ne démarre pas"):
        lire_la_version((str(Path("introuvable") / NOM_PROGRAMME),))


def test_options_de_video_compare(tmp_path):
    video_compare = VideoCompare(("C:/vc/video-compare.exe",), "20261004-osaka")
    gauche, droite = tmp_path / "Topaz.mp4", tmp_path / "App.mp4"
    assert arguments(video_compare, gauche, droite, Reglages()) == ["C:/vc/video-compare.exe", "-W", "--", str(gauche), str(droite)]
    tout = Reglages(disposition=COTE_A_COTE, fenetre=PLEIN_ECRAN, decalage_ms=-1500, boucle=True, difference=True)
    assert arguments(video_compare, gauche, droite, tout) == [
        "C:/vc/video-compare.exe", "-m", "hstack", "-u", "-t", "-1.500", "-a", "on", "-S", "--", str(gauche), str(droite),
    ]
    assert arguments(video_compare, gauche, droite, Reglages(EMPILEES, TAILLE_VIDEO, 40))[1:5] == ["-m", "vstack", "-t", "0.040"]
    assert "-m" not in arguments(video_compare, gauche, droite, Reglages(CURSEUR))  # le curseur : par défaut


def test_mesures_et_captures_en_francais():
    mesures = lire_les_mesures("Metrics: [00:00:05.120|00:00:05.120] PSNR(42.131), SSIM(0.99812), VMAF(97.312)")
    assert (mesures.moment(), mesures.ssim_lisible(), mesures.psnr_lisible(), mesures.vmaf_lisible()) == ("00:05,120", "0,9981", "42,13 dB", "97,31")
    assert mesures.en_francais() == "SSIM 0,9981 · PSNR 42,13 dB · VMAF 97,31" and not mesures.zone
    identiques = lire_les_mesures("Metrics: [00:00:01.000|00:00:01.040] PSNR(inf), SSIM(1.00000), VMAF(n/a)  (10,20)-(500,700)")
    assert identiques.psnr_lisible() == "infini (identiques)" and identiques.vmaf_lisible() == ""
    assert identiques.moment() == "00:01,000 / 00:01,040" and identiques.zone  # décalage, zone visible
    assert lire_les_mesures("Metrics: [01:02:03.000|01:02:03.000] PSNR(30.0), SSIM(n/a), VMAF(90.1|88.4)").vmaf_lisible() == "90,10 | 88,40"
    assert lire_les_mesures("Seeking to 00:00:05.120") is None
    assert lire_les_captures("Saved Topaz_0000.png, App_0000.png and Topaz_App_osd_0000.png") == [
        "Topaz_0000.png", "App_0000.png", "Topaz_App_osd_0000.png",
    ]
    assert lire_les_captures("Saved window size") is None


def test_une_comparaison_avec_le_faux_video_compare(tmp_path, monkeypatch):
    monkeypatch.setenv("UGC_FAUX_VC_DUREE", "30")
    gauche, droite = tmp_path / "Topaz.mp4", tmp_path / "App.mp4"
    gauche.write_bytes(b"video")
    droite.write_bytes(b"video")
    comparaison = Comparaison(arguments(VideoCompare(FAUX, "20261004-osaka"), gauche, droite, Reglages()), tmp_path)
    lignes = []

    def recue(ligne: str) -> None:
        lignes.append(ligne)
        if ligne.startswith("Saved"):
            comparaison.fermer()  # « Fermer la comparaison »

    debut = time.monotonic()
    comparaison.lire(recue)
    assert time.monotonic() - debut < 20 and not comparaison.ouverte()
    assert lire_les_mesures(lignes[0]) is not None and lire_les_captures(lignes[1]) is not None
    assert (tmp_path / "Topaz_App_osd_0000.png").is_file()  # les captures dans le dossier choisi
