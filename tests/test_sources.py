"""Sources des sous-titres (V3.1, lot 6 ; cahier des charges §7.14) : la vidéo de l'aperçu et les
mots des sous-titres, chacun depuis le module Transcription ou importé ; projets d'avant la 3.1.0."""

import json
from dataclasses import asdict

from ugc_studio.projets import FICHIER_AUDIO, FICHIER_AUDIO_IMPORTE, GestionnaireProjets, Prise, Projet, liberer_la_piste_son
from ugc_studio.sources import (
    SOURCE_IMPORTEE,
    SOURCE_TRANSCRIPTION,
    ChoixDesSources,
    VideoDeLApercu,
    a_des_retouches,
    a_une_video,
    audio_des_mots,
    decalage_des_mots,
    meme_enregistrement,
    mots_des_sous_titres,
    video_de_l_apercu,
    voix_a_caler,
)
from ugc_studio.sous_titres import ReglagesSousTitres
from ugc_studio.style_sous_titres import VideoApercu
from ugc_studio.transcription import Mot, Transcription


def _video() -> Transcription:
    return Transcription(
        source="C:/Vidéos/pub.mp4", audio=FICHIER_AUDIO, duree_s=4.0, infos={"video": True, "resolution": [1920, 1080], "rotation": 90},
        langue="fr-FR", mots=[Mot("Franchement,", 0.1, 0.6), Mot("top", 0.7, 1.0)],
    )


def _audio() -> Transcription:
    return Transcription(source="C:/Sons/voix.wav", audio=FICHIER_AUDIO, duree_s=4.0, infos={"video": False}, mots=[Mot("Salut", 0.1, 0.4)])


def _prise(audio: str = "prises/prise-002.wav") -> Transcription:
    return Transcription(source="Prise 2", audio=audio, duree_s=3.0, prise="prise-002", mots=[Mot("Mais", 0.0, 0.3)])


def _srt() -> Transcription:
    return Transcription(source="C:/Montage/pub.srt", duree_s=5.0, infos={"srt": True, "video": False}, mots=[Mot("Mais", 0.0, 0.3)])


def _projet(tmp_path, transcription=None, importes=None) -> Projet:
    return Projet(tmp_path, "Sérum", transcription=transcription, sous_titres_importes=importes)


def test_choix_lu_avec_tolerance():
    assert ChoixDesSources.depuis_dict(None) == ChoixDesSources(SOURCE_TRANSCRIPTION, SOURCE_TRANSCRIPTION)
    lu = ChoixDesSources.depuis_dict({"video": SOURCE_IMPORTEE, "sous_titres": "inconnue"})
    assert lu == ChoixDesSources(SOURCE_IMPORTEE, SOURCE_TRANSCRIPTION)  # un choix inconnu : le module
    assert ChoixDesSources.depuis_dict(lu.en_dict()) == lu


def test_a_une_video():
    assert a_une_video(_video())
    assert not a_une_video(_audio()) and not a_une_video(_prise()) and not a_une_video(None)
    assert not a_une_video(Transcription(infos={"video": True}))  # rien d'importé


def test_mots_selon_le_choix_sans_rien_perdre(tmp_path):
    module, prise = _video(), _prise()
    projet = _projet(tmp_path, module, prise)
    assert mots_des_sous_titres(projet) is module
    projet.sources.sous_titres = SOURCE_IMPORTEE
    assert mots_des_sous_titres(projet) is prise
    projet.sources.sous_titres = SOURCE_TRANSCRIPTION
    assert mots_des_sous_titres(projet) is module and projet.sous_titres_importes is prise  # rien n'a disparu


def test_video_de_l_apercu(tmp_path):
    projet = _projet(tmp_path, _video())
    # Celle du module Transcription (dès son import, même sans mots), remise debout.
    assert video_de_l_apercu(projet) == VideoDeLApercu("C:/Vidéos/pub.mp4", (1080, 1920), False)
    projet.transcription = _audio()
    assert video_de_l_apercu(projet) is None  # un audio seul : fond gris
    projet.sources.video = SOURCE_IMPORTEE
    assert video_de_l_apercu(projet) is None  # rien d'importé ici
    projet.sous_titres.apercu = VideoApercu("C:/Montage/montage.mp4", 1.5, 1080, 1350, son_de_la_video=False)
    assert video_de_l_apercu(projet) == VideoDeLApercu("C:/Montage/montage.mp4", (1080, 1350), True, False)


def test_la_voix_commence_a(tmp_path):
    """« La voix commence à » ne compte que si la vidéo et les mots viennent d'enregistrements
    différents, et qu'il y a une vidéo."""
    projet = _projet(tmp_path, _video(), _prise())
    projet.sous_titres.apercu = VideoApercu(decalage_s=2.0)
    assert meme_enregistrement(projet) and not voix_a_caler(projet) and decalage_des_mots(projet) == 0.0
    projet.sources.sous_titres = SOURCE_IMPORTEE  # les mots d'une prise sur la vidéo du module
    assert voix_a_caler(projet) and decalage_des_mots(projet) == 2.0
    projet.transcription = _audio()  # plus de vidéo : rien à caler
    assert not voix_a_caler(projet) and decalage_des_mots(projet) == 0.0
    projet.sources = ChoixDesSources(SOURCE_IMPORTEE, SOURCE_TRANSCRIPTION)
    projet.sous_titres.apercu = VideoApercu("C:/Montage/montage.mp4", 2.0, 1080, 1920)
    assert not meme_enregistrement(projet) and voix_a_caler(projet)  # les mots du module sur le montage
    projet.transcription = None
    assert not voix_a_caler(projet)  # pas de mots


def test_piste_son_des_mots(tmp_path):
    projet = _projet(tmp_path, _video(), _prise())
    assert audio_des_mots(projet) == tmp_path / FICHIER_AUDIO
    projet.sources.sous_titres = SOURCE_IMPORTEE
    assert audio_des_mots(projet) == tmp_path / "prises" / "prise-002.wav"
    projet.sous_titres_importes = _srt()
    assert audio_des_mots(projet) is None  # un fichier SRT n'a pas de son


def test_retouches():
    mots = _prise()
    assert not a_des_retouches(mots) and not a_des_retouches(None)
    mots.corrigee = True
    assert a_des_retouches(mots)
    mots.corrigee, mots.ajustements_sous_titres = False, [[0.0, 0.3]]
    assert a_des_retouches(mots)


def _ancien_projet(dossier, transcription: Transcription, apercu: VideoApercu | None = None, prises=()) -> GestionnaireProjets:
    """Un projet de la 3.0.5 (format 7) : une seule liste de mots, et la vidéo d'aperçu de l'onglet Écran."""
    dossier.mkdir()
    sous_titres = ReglagesSousTitres(apercu=apercu or VideoApercu()).en_dict()
    donnees = {
        "version_format": 7, "nom": "Ancien", "transcription": transcription.en_dict(), "sous_titres": sous_titres,
        "prises": [asdict(p) for p in prises],
    }
    (dossier / "projet.json").write_text(json.dumps(donnees), encoding="utf-8")
    gestion = GestionnaireProjets(dossier.parent / "recents.json")
    gestion.ouvrir(dossier)
    return gestion


def test_projet_d_une_prise_d_avant_la_3_1(tmp_path):
    """Ses sous-titres deviennent les mots importés, choisis, avec la piste son de la prise elle-même ;
    sa vidéo d'aperçu devient la vidéo importée, choisie. Le module Transcription n'a rien."""
    prise = Prise("prise-002", "Prise 2", "prises/prise-002.wav", "2026-10-01", "gemini-3.8-flash-tts", "Kore", "", "Mais", [], 3.0)
    apercu = VideoApercu("C:/Montage/montage.mp4", 1.5, 1080, 1920, son_de_la_video=False)
    gestion = _ancien_projet(tmp_path / "Ancien", _prise(audio=FICHIER_AUDIO), apercu, [prise])
    projet = gestion.projet
    assert projet.transcription is None and projet.sources == ChoixDesSources(SOURCE_IMPORTEE, SOURCE_IMPORTEE)
    assert projet.sous_titres_importes.prise == "prise-002" and projet.sous_titres_importes.audio == "prises/prise-002.wav"
    assert video_de_l_apercu(projet) == VideoDeLApercu("C:/Montage/montage.mp4", (1080, 1920), True, False)
    assert decalage_des_mots(projet) == 1.5
    # Enregistré au format 8, relu tel quel.
    gestion.enregistrer()
    ecrit = json.loads((projet.dossier / "projet.json").read_text(encoding="utf-8"))
    assert ecrit["version_format"] == 8 and ecrit["sources"] == {"video": SOURCE_IMPORTEE, "sous_titres": SOURCE_IMPORTEE}
    relu = gestion.ouvrir(projet.dossier)
    assert relu.sous_titres_importes.mots == projet.sous_titres_importes.mots and relu.transcription is None


def test_projet_d_une_video_d_avant_la_3_1(tmp_path):
    """La vidéo transcrite reste dans le module Transcription, choisie ; rien d'importé."""
    projet = _ancien_projet(tmp_path / "Ancien", _video()).projet
    assert projet.transcription.source == "C:/Vidéos/pub.mp4" and projet.sous_titres_importes is None
    assert projet.sources == ChoixDesSources(SOURCE_TRANSCRIPTION, SOURCE_TRANSCRIPTION)


def test_mots_corriges_enregistres(tmp_path):
    projet = _projet(tmp_path, _video(), _srt())
    projet.sous_titres_importes.corrigee = True
    relu = Projet.depuis_dict(tmp_path, json.loads(json.dumps(projet.en_dict())))
    assert relu.sous_titres_importes.corrigee and not relu.transcription.corrigee


def test_piste_son_liberee_avant_un_nouvel_import(tmp_path):
    """Une prise sous-titrée avant la 3.1.0, supprimée depuis : ses mots se servent encore de la piste
    son du module Transcription. Avant que le module en écrive une nouvelle, ils en gardent une copie."""
    importes = _prise(audio=FICHIER_AUDIO)
    projet = _projet(tmp_path, None, importes)
    liberer_la_piste_son(projet)  # pas encore de fichier : rien à copier
    assert importes.audio == FICHIER_AUDIO
    (tmp_path / FICHIER_AUDIO).parent.mkdir()
    (tmp_path / FICHIER_AUDIO).write_bytes(b"voix de la prise")
    liberer_la_piste_son(projet)
    assert importes.audio == FICHIER_AUDIO_IMPORTE and (tmp_path / FICHIER_AUDIO_IMPORTE).read_bytes() == b"voix de la prise"
    projet.sous_titres_importes = _prise()  # la piste de la prise elle-même : rien à faire
    liberer_la_piste_son(projet)
    assert projet.sous_titres_importes.audio == "prises/prise-002.wav"
