"""Module Upscale vidéo (V4, lot 3) : la commande de Topaz comprise et rejouée, la taille finale, Topaz
trouvé sur l'ordinateur, et la file de vidéos (avec un faux Topaz)."""

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from ugc_studio.exports.ffmpeg import programme_ffmpeg
from ugc_studio.topaz import faux
from ugc_studio.topaz.commande import (
    CommandeIncomprise,
    Prereglage,
    comprendre,
    decouper,
    mp4_classique,
    pair_le_plus_proche,
    taille_finale,
)
from ugc_studio.topaz.installation import CONNEXION, VARIABLE_DONNEES, VARIABLE_MODELES, Topaz, trouver_topaz
from ugc_studio.renommage import Numerotation
from ugc_studio.topaz.upscale import (
    NomDesVideos,
    Video,
    chemin_provisoire,
    duree_lisible,
    exemple_de_nom,
    lire_la_video,
    nom_de_sortie,
    planifier,
    resolution_lisible,
    upscaler,
)

# La commande « FFmpeg Command » de l'utilisateur (Topaz Video AI 7.1.1, 04/10/2026), chemins changés.
COMMANDE = (
    'ffmpeg "-hide_banner" "-t" "0.15833306944488423" "-ss" "0" "-i" "C:/Users/Moi/Desktop/RawBox01.mp4" '
    '"-sws_flags" "spline+accurate_rnd+full_chroma_int" "-filter_complex" '
    '"tvai_up=model=prob-4:scale=0:w=1080:h=1920:preblur=0:noise=0:details=0:halo=0:blur=0:compression=0:'
    'estimate=8:blend=0.3:device=-2:vram=1:instances=1,scale=w=1080:h=1920:flags=lanczos:threads=0" '
    '"-c:v" "h264_nvenc" "-profile:v" "high" "-pix_fmt" "yuv420p" "-g" "30" "-rc" "cbr" "-b:v" "24M" '
    '"-preset" "p6" "-map" "0:a?" "-map_metadata:s:a:0" "0:s:a:0" "-c:a" "copy" "-bsf:a:0" "aac_adtstoasc" '
    '"-map_metadata" "0" "-map_metadata:s:v" "0:s:v" "-fps_mode:v" "passthrough" "-movflags" '
    '"frag_keyframe+empty_moov+delay_moov+use_metadata_tags+write_colr" "-bf" "0" "-metadata" '
    '"videoai=Enhanced using prob-4; mode: auto; revert compression at 0; recover details at 0; sharpen at 0; '
    'reduce noise at 0; dehalo at 0; anti-alias/deblur at 0; focus fix Off; and recover original detail at 30. '
    'Changed resolution to 1080x1920" "C:/Users/Moi/Desktop/RawBox01_805515910.mp4"'
)


# --- La commande ------------------------------------------------------------------------------


def test_decouper_comme_windows():
    assert decouper('ffmpeg "-i" "C:\\Mes vidéos\\a.mp4" -y "b.mp4"') == ["ffmpeg", "-i", "C:\\Mes vidéos\\a.mp4", "-y", "b.mp4"]
    assert decouper('"" a') == ["", "a"]
    with pytest.raises(CommandeIncomprise):
        decouper('ffmpeg "-i a.mp4')  # guillemet pas refermé : commande coupée en la copiant


def test_la_commande_de_l_utilisateur():
    prereglage = comprendre(COMMANDE)
    assert (prereglage.nom, prereglage.modele, prereglage.extension) == ("Proteus", "prob-4", ".mp4")
    assert prereglage.automatique and prereglage.son_copie()
    assert prereglage.resume() == [
        "Modèle : Proteus (prob-4), réglages estimés par Topaz sur chaque vidéo (mode automatique)",
        "Réglages : Recover original detail 30",
        "Encodage : H.264 (carte NVIDIA), 24 Mb/s constant, profil high",
        "Son : copié tel quel",
        "Cadence : celle de chaque vidéo, image par image",
        "Fichier : MP4",
    ]
    # Les chemins de la vidéo d'origine ne sont pas gardés.
    assert "RawBox01" not in str(prereglage.en_donnees())


def test_rejouer_la_commande_sur_une_autre_video():
    prereglage = comprendre(COMMANDE)
    arguments = prereglage.arguments("D:/Pubs/Sérum.mp4", "D:/Pubs/Sérum (upscale).en-cours.mp4", 1080, 1924)
    assert arguments[:6] == ["-nostdin", "-nostats", "-y", "-progress", "pipe:1", "-hide_banner"]
    # L'extrait (-t, -ss) est retiré : toute la vidéo est traitée.
    assert "-t" not in arguments and "-ss" not in arguments
    assert arguments[arguments.index("-i") + 1] == "D:/Pubs/Sérum.mp4" and arguments[-1] == "D:/Pubs/Sérum (upscale).en-cours.mp4"
    graphe = arguments[arguments.index("-filter_complex") + 1]
    assert graphe == (
        "tvai_up=model=prob-4:scale=0:w=1080:h=1924:preblur=0:noise=0:details=0:halo=0:blur=0:compression=0:"
        "estimate=8:blend=0.3:device=-2:vram=1:instances=1,scale=w=1080:h=1924:flags=lanczos:threads=0"
    )
    # Tout le reste dans l'ordre de Topaz (les options d'image avant le graphe, l'encodage après).
    assert arguments.index("-sws_flags") < arguments.index("-filter_complex") < arguments.index("-c:v")
    for option, valeur in (("-c:v", "h264_nvenc"), ("-b:v", "24M"), ("-rc", "cbr"), ("-c:a", "copy"), ("-fps_mode:v", "passthrough")):
        assert arguments[arguments.index(option) + 1] == valeur
    note = arguments[arguments.index("-metadata") + 1]
    assert note.endswith("Changed resolution to 1080x1924")
    # 4.0.3 : un MP4 classique, comme le fichier final de l'interface de Topaz (la commande écrivait un
    # MP4 fragmenté, sans durée dans l'Explorateur de Windows) ; les autres drapeaux de Topaz restent.
    assert arguments[arguments.index("-movflags") + 1] == "+faststart+use_metadata_tags+write_colr"


def test_mp4_classique():
    """4.0.3 : seules les options de fragmentation sont retirées ; le sommaire passe au début quand la
    commande règle le conteneur (-movflags), sans être répété."""
    assert mp4_classique(["-c:v", "libx264", "-movflags", "+faststart"]) == ["-c:v", "libx264", "-movflags", "+faststart"]
    assert mp4_classique(["-movflags", "empty_moov+frag_keyframe", "-frag_duration", "1000000", "-c:a", "copy"]) == [
        "-movflags",
        "+faststart",
        "-c:a",
        "copy",
    ]
    assert mp4_classique(["-movflags", "frag_keyframe-use_metadata_tags+write_colr"]) == ["-movflags", "+faststart-use_metadata_tags+write_colr"]
    assert mp4_classique(["-c:v", "prores_ks", "-profile:v", "3"]) == ["-c:v", "prores_ks", "-profile:v", "3"]  # sans -movflags : rien


def test_preset_x2_sans_taille():
    commande = 'ffmpeg -i in.mov -filter_complex "tvai_up=model=prob-4:scale=2:device=0" -c:v prores_ks out.mov'
    prereglage = comprendre(commande, "Proteus ×2")
    assert prereglage.nom == "Proteus ×2" and prereglage.extension == ".mov"
    arguments = prereglage.arguments("a.mov", "b.mov", 2160, 3840)
    graphe = arguments[arguments.index("-filter_complex") + 1]
    assert graphe == "tvai_up=model=prob-4:scale=0:device=0:w=2160:h=3840,scale=w=2160:h=3840:flags=lanczos"


def test_commandes_refusees():
    for commande, debut in (
        ("", "La commande est vide."),
        ("ffmpeg -i a.mp4 -c:v libx264 b.mp4", "Ce n'est pas une commande d'export de Topaz Video AI"),
        ('ffmpeg -filter_complex "tvai_up=model=prob-4" b.mp4', "Il manque la vidéo lue"),
        ('ffmpeg -i a.mp4 -i b.mp4 -filter_complex "tvai_up=model=prob-4" c.mp4', "Cette commande lit plusieurs fichiers"),
        ('ffmpeg -i a.mp4 -filter_complex "tvai_up=scale=2" b.mp4', "Le modèle de Topaz"),
    ):
        try:
            comprendre(commande)
            raise AssertionError(f"CommandeIncomprise attendue : {commande}")
        except CommandeIncomprise as erreur:
            assert str(erreur).startswith(debut), (commande, str(erreur))


def test_prereglage_enregistre_puis_relu():
    prereglage = comprendre(COMMANDE)
    relu = Prereglage.depuis(prereglage.en_donnees())
    assert relu == prereglage
    assert Prereglage.depuis({"nom": "abîmé"}) is None


# --- La taille finale ----------------------------------------------------------------------------


def test_taille_finale_sans_jamais_etirer():
    assert taille_finale(1080, 1920, 1080) == (1080, 1920)  # 9:16
    assert taille_finale(606, 1080, 1080) == (1080, 1924)  # l'exemple de l'utilisateur (1924,75)
    assert taille_finale(606, 1080, 1440) == (1440, 2566)
    assert taille_finale(720, 1280, 1440) == (1440, 2560)
    assert taille_finale(1920, 1080, 1080) == (1920, 1080)  # horizontale : le petit côté est la hauteur
    assert taille_finale(1000, 1000, 1080) == (1080, 1080)
    assert (pair_le_plus_proche(1077.33), pair_le_plus_proche(1924.75), pair_le_plus_proche(1)) == (1078, 1924, 2)


# --- Topaz sur l'ordinateur ----------------------------------------------------------------------


def _faux_topaz_installe(tmp_path) -> tuple[Path, Path, Path]:
    dossier, modeles, donnees = tmp_path / "Topaz Video AI", tmp_path / "models", tmp_path / "telecharges"
    for chemin in (dossier, modeles, donnees):
        chemin.mkdir()
    (dossier / "ffmpeg.exe").write_bytes(b"")
    (modeles / CONNEXION).write_bytes(b"")
    (modeles / "prob-4.json").write_text("{}", encoding="utf-8")
    (donnees / "prob-v4-fgnet-fp16-512x512-2x-ox.tz").write_bytes(b"")
    return dossier, modeles, donnees


def test_trouver_topaz(tmp_path, monkeypatch):
    dossier, modeles, donnees = _faux_topaz_installe(tmp_path)
    monkeypatch.delenv(VARIABLE_MODELES, raising=False)
    monkeypatch.delenv(VARIABLE_DONNEES, raising=False)
    assert trouver_topaz(tmp_path / "ailleurs") is None
    topaz = trouver_topaz(dossier, modeles)
    assert topaz.programme == (str(dossier / "ffmpeg.exe"),) and topaz.modeles == modeles
    # Aucun modèle téléchargé trouvé ailleurs : le dossier des modèles sert aussi pour les téléchargés.
    assert topaz.donnees == modeles and topaz.problemes("prob-4") == []
    choisi = trouver_topaz(dossier, modeles, donnees)
    assert choisi.problemes("prob-4") == [] and choisi.environnement() == {VARIABLE_MODELES: str(modeles), VARIABLE_DONNEES: str(donnees)}
    # Les variables de Windows passent avant les dossiers habituels.
    monkeypatch.setenv(VARIABLE_MODELES, str(modeles))
    monkeypatch.setenv(VARIABLE_DONNEES, str(donnees))
    assert trouver_topaz(dossier).environnement() == {VARIABLE_MODELES: str(modeles), VARIABLE_DONNEES: str(donnees)}
    (modeles / CONNEXION).unlink()
    assert trouver_topaz(dossier).problemes("prob-4") == ["Topaz ne semble pas connecté : ouvre Topaz Video AI et connecte-toi une fois."]
    assert trouver_topaz(dossier).problemes("ahq-12") == [
        "Topaz ne semble pas connecté : ouvre Topaz Video AI et connecte-toi une fois.",
        f"Le modèle « ahq-12 » n'est pas défini dans « {modeles} ».",
    ]


# --- La file de vidéos ---------------------------------------------------------------------------


def _faux(tmp_path) -> Topaz:
    """Le faux Topaz (topaz/faux.py), lancé par Python comme le serait le FFmpeg de Topaz."""
    return Topaz(tmp_path, (sys.executable, str(Path(faux.__file__))), "7.1.1", tmp_path, tmp_path)


def _videos(tmp_path, noms=("Sérum.mp4", "Crème.mov")) -> list[Video]:
    dossier = tmp_path / "Rushs"
    dossier.mkdir(exist_ok=True)
    videos = []
    for nom in noms:
        (dossier / nom).write_bytes(f"vidéo {nom}".encode("utf-8"))
        videos.append(Video(dossier / nom, 606, 1080, 2.0, True))
    return videos


def test_noms_de_sortie(tmp_path):
    assert nom_de_sortie("Sérum (upscale)", tmp_path, ".mp4") == tmp_path / "Sérum (upscale).mp4"
    (tmp_path / "Sérum (upscale).mp4").write_bytes(b"")
    assert nom_de_sortie("Sérum (upscale)", tmp_path, ".mp4") == tmp_path / "Sérum (upscale) (2).mp4"  # rien n'est écrasé
    assert chemin_provisoire(tmp_path / "Sérum (upscale).mp4") == tmp_path / "Sérum (upscale).en-cours.mp4"
    # Le masque de départ donne le nom d'avant la 4.1.0 : « x (upscale).mp4 ».
    deux = planifier([Video(tmp_path / "a" / "x.mp4", 606, 1080, 1.0), Video(tmp_path / "b" / "x.mp4", 1920, 1080, 1.0)], 1080, ".mp4", tmp_path).travaux
    assert [t.destination.name for t in deux] == ["x (upscale).mp4", "x (upscale) (2).mp4"]
    assert [t.finale for t in deux] == [(1080, 1924), (1920, 1080)]
    assert planifier([Video(tmp_path / "abimee.mp4", erreur="illisible")], 1080, ".mp4").travaux == []
    assert (duree_lisible(42.4), duree_lisible(192), duree_lisible(3900)) == ("42 s", "3 min 12 s", "1 h 05 min")


def test_nom_des_videos_par_masque(tmp_path):
    """4.1.0 : le masque de Renommer, avec %res% et %preset% ; %num% facultatif, %ext% à la fin."""
    dossier = tmp_path / "Glowzy"
    dossier.mkdir()
    videos = [
        Video(dossier / "A.mp4", 606, 1080, 1.0),
        Video(dossier / "B.mov", erreur="illisible"),  # pas de numéro : elle ne sera pas faite
        Video(dossier / "C.mp4", 1920, 1080, 1.0),
        Video(dossier / "D.mp4", 720, 1280, 1.0),
    ]
    nom = NomDesVideos("NeMu_VID_%num%_%res%%ext%")
    plan = planifier(videos, 1080, ".mp4", nom=nom)
    assert [t.destination.name for t in plan.travaux] == ["NeMu_VID_01_1080p.mp4", "NeMu_VID_02_1080p.mp4", "NeMu_VID_03_1080p.mp4"]
    assert plan.possible and plan.alertes == []
    assert plan.resume() == "3 vidéos : de « NeMu_VID_01_1080p.mp4 » à « NeMu_VID_03_1080p.mp4 »."
    # Une vidéo déjà faite garde sa place : les autres gardent leur numéro.
    plan = planifier(videos, 1440, ".mp4", nom=nom, faites={dossier / "A.mp4"})
    assert [t.destination.name for t in plan.travaux] == ["NeMu_VID_02_1440p.mp4", "NeMu_VID_03_1440p.mp4"]
    # Les autres balises, sans tenir compte des majuscules, et la numérotation de Renommer.
    nom = NomDesVideos("%Folder1%_%NUM%_%preset%_%name%%Ext%", Numerotation(7, 3, 5), "Proteus")
    noms = [t.destination.name for t in planifier(videos, 2160, ".mov", nom=nom).travaux]
    assert noms == ["Glowzy_007_Proteus_A.mov", "Glowzy_012_Proteus_C.mov", "Glowzy_017_Proteus_D.mov"]
    assert resolution_lisible(2160) == "2160p"
    # Le masque doit finir par %ext% (« %% » suivi de « ext% » n'est pas la balise).
    for masque in ("NeMu_%num%", "NeMu_%ext%_%num%", "NeMu%%ext%", ""):
        plan = planifier(videos, 1080, ".mp4", nom=NomDesVideos(masque))
        assert plan.erreur and not plan.travaux and not plan.possible, masque
    erreur = planifier(videos, 1080, ".mp4", nom=NomDesVideos("x")).erreur
    assert erreur == "Le masque doit finir par %ext% : l'app y met l'extension du format du préréglage (.mp4)."
    # Ce que Windows refuse : en rouge, rien n'est lancé.
    plan = planifier(videos, 1080, ".mp4", nom=NomDesVideos("CON%ext%"))
    assert not plan.possible and plan.travaux[0].probleme == "« CON » est un nom réservé par Windows."
    assert plan.resume() == "3 vidéos ont un nom impossible (en rouge) : rien n'est lancé tant que c'est le cas."
    # Sans vidéo : un exemple.
    assert exemple_de_nom(NomDesVideos(), ".mp4", 1080) == ("Sérum (upscale).mp4", "")
    assert exemple_de_nom(NomDesVideos("%folder1%_%res%%ext%"), ".mp4", 1440) == ("Glowzy_1440p.mp4", "")
    assert exemple_de_nom(NomDesVideos("a|b%ext%"), ".mp4", 1080)[1] == "Caractère interdit par Windows : |"


def test_noms_deja_pris_et_balises_inconnues(tmp_path):
    dossier = tmp_path / "Rushs"
    dossier.mkdir()
    videos = [Video(dossier / f"{lettre}.mp4", 606, 1080, 1.0) for lettre in "ABC"]
    plan = planifier(videos, 1080, ".mp4", nom=NomDesVideos("NeMu%ext%"))  # ni %num% ni %name% : permis
    assert [t.destination.name for t in plan.travaux] == ["NeMu.mp4", "NeMu (2).mp4", "NeMu (3).mp4"]
    assert plan.possible and plan.alertes == [
        "2 vidéos auraient le même nom qu'une autre de la liste : « (2) », « (3) »… ajoutés. Mets %num% ou %name% dans le "
        "masque pour les distinguer."
    ]
    (dossier / "NeMu_02.mp4").write_bytes(b"")  # un lot précédent
    plan = planifier(videos, 1080, ".mp4", nom=NomDesVideos("NeMu_%num%%ext%"))
    assert [t.destination.name for t in plan.travaux] == ["NeMu_01.mp4", "NeMu_02 (2).mp4", "NeMu_03.mp4"]
    assert plan.alertes == ["« NeMu_02.mp4 » existe déjà : la vidéo sera enregistrée en « NeMu_02 (2).mp4 » (rien n'est écrasé)."]
    plan = planifier(videos[:1], 1080, ".mp4", nom=NomDesVideos("%date%_%folder99%_%num%%ext%"))
    assert plan.alertes == ["%date% n'est pas une balise : écrit tel quel dans les noms.", "%folder99% : pas de dossier à ce niveau, remplacé par rien."]
    assert plan.travaux[0].destination.name == "%date%__01.mp4"


def test_file_de_videos_avec_le_faux_topaz(tmp_path, monkeypatch):
    commande = tmp_path / "commande.txt"
    monkeypatch.setenv("UGC_FAUX_TOPAZ_COMMANDE", str(commande))
    travaux = planifier(_videos(tmp_path), 1080, ".mp4").travaux
    avancement = []
    resultats = upscaler(travaux, comprendre(COMMANDE), _faux(tmp_path), avancement.append, threading.Event())
    assert [r.reussi for r in resultats] == [True, True]
    dossier = tmp_path / "Rushs"
    assert (dossier / "Sérum (upscale).mp4").read_bytes() == "vidéo Sérum.mp4".encode("utf-8")
    assert (dossier / "Crème (upscale).mp4").is_file()  # le format du préréglage (MP4)
    assert not list(dossier.glob("*.en-cours.*"))
    assert [a.rang for a in avancement][0] == 0 and avancement[-1].rang == 1 and avancement[-1].fraction == 1.0
    recue = commande.read_text(encoding="utf-8").splitlines()
    assert "tvai_up=model=prob-4:scale=0:w=1080:h=1924" in recue[recue.index("-filter_complex") + 1]


def test_topaz_en_echec(tmp_path, monkeypatch):
    monkeypatch.setenv("UGC_FAUX_TOPAZ_ECHEC", "1")
    travaux = planifier(_videos(tmp_path, ("Sérum.mp4",)), 1080, ".mp4").travaux
    resultats = upscaler(travaux, comprendre(COMMANDE), _faux(tmp_path), lambda _a: None, threading.Event())
    assert not resultats[0].reussi and "Model prob-4 could not be loaded" in resultats[0].erreur
    assert not list((tmp_path / "Rushs").glob("*(upscale)*"))  # rien de laissé


def test_arreter_la_file(tmp_path, monkeypatch):
    monkeypatch.setenv("UGC_FAUX_TOPAZ_PAUSE", "0.5")
    travaux = planifier(_videos(tmp_path), 1080, ".mp4").travaux
    arret = threading.Event()
    resultats = upscaler(travaux, comprendre(COMMANDE), _faux(tmp_path), lambda _a: arret.set(), arret)
    assert len(resultats) == 1 and resultats[0].arrete  # la 2e vidéo n'est pas commencée
    assert not list((tmp_path / "Rushs").glob("*(upscale)*"))


# --- La vidéo lue par FFmpeg (taille redressée) ------------------------------------------------------

FFMPEG = programme_ffmpeg()


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")
def test_video_couchee_lue_debout(tmp_path):
    """Une vidéo enregistrée 1920 × 1080 avec une consigne « à tourner de 90° » (comme celles d'un
    téléphone) est vue 1080 × 1920 : la taille finale se calcule dans ce sens."""
    droite, source = tmp_path / "droite.mp4", tmp_path / "couchee.mp4"
    commun = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(
        [*commun, "-f", "lavfi", "-i", "testsrc2=size=192x108:rate=30", "-t", "0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(droite)],
        check=True,
    )
    # La consigne de rotation, comme un téléphone l'écrit (option d'entrée de FFmpeg, recopiée telle quelle).
    subprocess.run([*commun, "-display_rotation", "90", "-i", str(droite), "-c", "copy", str(source)], check=True)
    video = lire_la_video(source, FFMPEG)
    assert (video.largeur, video.hauteur) == (108, 192) and not video.son
    assert planifier([video], 1080, ".mp4").travaux[0].finale == (1080, 1920)


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")
def test_options_du_conteneur_donnent_un_mp4_classique(tmp_path):
    """4.0.3 : les options du conteneur de la commande de l'utilisateur, telles que l'app les rejoue,
    donnent à FFmpeg un MP4 classique : aucun morceau (« moof »), le sommaire (« moov ») au début et
    sa durée lisible. Avec les options d'origine, le fichier était fragmenté."""
    prereglage = comprendre(COMMANDE)
    arguments = prereglage.arguments("entree.mp4", "sortie.mp4", 1080, 1924)
    conteneur = ["-movflags", arguments[arguments.index("-movflags") + 1]]
    commun = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=96x160:rate=30", "-t", "2"]
    commun += ["-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p"]
    rejoue, origine = tmp_path / "rejoue.mp4", tmp_path / "origine.mp4"
    subprocess.run([*commun, *conteneur, str(rejoue)], check=True)
    subprocess.run([*commun, "-movflags", "frag_keyframe+empty_moov+delay_moov+use_metadata_tags+write_colr", str(origine)], check=True)
    octets = rejoue.read_bytes()
    assert b"moof" not in octets and octets.index(b"moov") < octets.index(b"mdat")
    assert b"moof" in origine.read_bytes()  # la commande d'origine : un MP4 fragmenté
    video = lire_la_video(rejoue, FFMPEG)
    assert abs(video.duree_s - 2) < 0.1


@pytest.mark.skipif(FFMPEG is None, reason="FFmpeg absent de cet ordinateur")
def test_comparer_deux_videos(tmp_path):
    from ugc_studio.topaz.comparaison import comparer

    commun = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi"]
    for nom, source in (("a.mp4", "testsrc2=size=128x96:rate=10"), ("b.mp4", "smptebars=size=128x96:rate=10")):
        subprocess.run([*commun, "-i", source, "-t", "0.5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / nom)], check=True)
    meme = comparer(tmp_path / "a.mp4", tmp_path / "a.mp4", FFMPEG)
    assert meme.ssim > 0.999 and meme.message().endswith("identiques à l'œil.")
    autre = comparer(tmp_path / "a.mp4", tmp_path / "b.mp4", FFMPEG)
    assert autre.ssim < 0.9 and "différentes" in autre.message()


def test_lire_le_ssim_et_le_message():
    from ugc_studio.topaz.comparaison import Comparaison, lire_ssim

    texte = "[Parsed_ssim_1 @ 000001] SSIM Y:0.998 (27.1) U:0.999 (30.2) V:0.999 (30.0) All:0.998512 (28.27)"
    assert lire_ssim(texte) == 0.998512 and lire_ssim("rien") is None
    assert Comparaison(0.998512, True).message() == "Ressemblance : 99,9 % (SSIM 0,9985), identiques à l'œil."
    assert Comparaison(0.975, False).message().startswith("Ressemblance : 97,5 % (SSIM 0,9750), très proches (tailles différentes")


def test_prereglages_enregistres(tmp_path):
    from ugc_studio.topaz.prereglages import PrereglagesTopaz

    prereglages = PrereglagesTopaz(tmp_path / "prereglages_topaz.json")
    assert prereglages.liste() == []
    proteus = comprendre(COMMANDE)
    prereglages.enregistrer(proteus)
    x2 = comprendre('ffmpeg -i a.mp4 -filter_complex "tvai_up=model=prob-4:scale=2" b.mp4', "Proteus ×2")
    prereglages.enregistrer(x2)
    assert prereglages.noms() == ["Proteus", "Proteus ×2"] and prereglages.trouver("Proteus") == proteus
    prereglages.enregistrer(comprendre(COMMANDE.replace("24M", "30M"), "Proteus"))  # même nom : remplacé, à sa place
    assert prereglages.noms() == ["Proteus", "Proteus ×2"] and prereglages.trouver("Proteus").option("-b:v") == "30M"
    prereglages.supprimer("Proteus")
    assert prereglages.noms() == ["Proteus ×2"]
