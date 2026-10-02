"""Sources des sous-titres (V3.1, lot 6 ; cahier des charges §7.14) : d'où viennent la vidéo de
l'aperçu et les mots des sous-titres.

- **Vidéo ou audio** : celle du module Transcription (la même que là-bas : importer une vidéo dans
  l'un des deux modules la met dans l'autre), ou une vidéo importée dans la page Sous-titres (ex. le
  montage exporté de Premiere Pro, rangée dans `sous_titres.apercu`). C'est elle que montre l'aperçu,
  et elle que reprend l'export « Vidéo avec sous-titres ».
- **Sous-titres** : les mots transcrits dans le module Transcription (`Projet.transcription`), ou des
  mots importés (`Projet.sous_titres_importes`) : ceux d'une prise de voix (transcrite, puis calée
  sur son script) ou d'un fichier SRT (moment de chaque mot estimé, import_srt.py).

Une source à la fois pour chacun, celle choisie (`Projet.sources`). On passe de l'une à l'autre sans
rien perdre : chacune garde ses mots et ses retouches (mots corrigés, sous-titres réorganisés à la
main). Un nouvel import ne remplace que l'import précédent, jamais ce qui vient du module
Transcription. Quand la vidéo et les mots ne viennent pas du même enregistrement, « La voix commence
à » cale les mots sur la vidéo (`sous_titres.apercu.decalage_s`).

Ce module ne dépend pas de l'interface : il est testé seul.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .transcription import Transcription, resolution_video

if TYPE_CHECKING:
    from .projets import Projet

SOURCE_TRANSCRIPTION = "transcription"  # le module Transcription
SOURCE_IMPORTEE = "importee"  # importée dans la zone « Source » de la page Sous-titres
SOURCES = (SOURCE_TRANSCRIPTION, SOURCE_IMPORTEE)


@dataclass
class ChoixDesSources:
    """La source choisie dans chaque onglet de la zone « Source »."""

    video: str = SOURCE_TRANSCRIPTION  # onglet « Vidéo ou audio »
    sous_titres: str = SOURCE_TRANSCRIPTION  # onglet « Sous-titres »

    def en_dict(self) -> dict:
        return {"video": self.video, "sous_titres": self.sous_titres}

    @classmethod
    def depuis_dict(cls, brut) -> ChoixDesSources:
        """Lecture tolérante : un choix absent ou inconnu revient au module Transcription."""
        brut = brut if isinstance(brut, dict) else {}
        return cls(*(brut.get(cle) if brut.get(cle) in SOURCES else SOURCE_TRANSCRIPTION for cle in ("video", "sous_titres")))


def a_une_video(transcription: Transcription | None) -> bool:
    """La source du module Transcription est-elle une vidéo (et pas seulement un audio) ?"""
    if transcription is None or transcription.prise or not transcription.source:
        return False
    infos = transcription.infos or {}
    return bool(infos.get("video")) or resolution_video(infos) is not None


def mots_des_sous_titres(projet: Projet) -> Transcription | None:
    """Les mots dont sont faits les sous-titres : ceux du module Transcription, ou ceux importés
    (prise de voix, fichier SRT), selon le choix de l'onglet « Sous-titres »."""
    if projet.sources.sous_titres == SOURCE_IMPORTEE:
        return projet.sous_titres_importes
    return projet.transcription


def a_des_retouches(transcription: Transcription | None) -> bool:
    """Des mots corrigés ou des sous-titres réorganisés à la main, qu'un nouvel import ferait perdre."""
    return transcription is not None and (transcription.corrigee or bool(transcription.ajustements_sous_titres))


@dataclass(frozen=True)
class VideoDeLApercu:
    chemin: str
    resolution: tuple[int, int] | None  # telle qu'on la voit ; None : pas encore lue
    importee: bool  # importée dans la page Sous-titres (sinon : celle du module Transcription)
    son_de_la_video: bool = True  # sinon : la voix des mots, sous la vidéo muette (vidéo importée)


def video_de_l_apercu(projet: Projet) -> VideoDeLApercu | None:
    """La vidéo que montre l'aperçu, et que reprend l'export « Vidéo avec sous-titres » : celle du
    module Transcription, ou la vidéo importée, selon le choix de l'onglet « Vidéo ou audio ». None :
    pas de vidéo (un audio seul, ou rien d'importé) ; l'aperçu montre alors un fond gris ou un damier."""
    if projet.sources.video == SOURCE_IMPORTEE:
        apercu = projet.sous_titres.apercu
        if not apercu.chemin:
            return None
        return VideoDeLApercu(apercu.chemin, apercu.resolution, True, apercu.son_de_la_video)
    transcription = projet.transcription
    if not a_une_video(transcription):
        return None
    return VideoDeLApercu(transcription.source, resolution_video(transcription.infos), False)


def meme_enregistrement(projet: Projet) -> bool:
    """La vidéo et les mots viennent-ils du même enregistrement (ceux du module Transcription) ?
    Sinon, « La voix commence à » cale les mots sur la vidéo."""
    return projet.sources.video == SOURCE_TRANSCRIPTION and projet.sources.sous_titres == SOURCE_TRANSCRIPTION


def voix_a_caler(projet: Projet) -> bool:
    """« La voix commence à » s'affiche : il y a une vidéo, et les mots viennent d'un autre
    enregistrement (ex. les sous-titres d'une prise sur ton montage)."""
    return not meme_enregistrement(projet) and video_de_l_apercu(projet) is not None and mots_des_sous_titres(projet) is not None


def decalage_des_mots(projet: Projet) -> float:
    """Moment de la vidéo où commence la voix des sous-titres (en secondes) : 0 quand la vidéo et les
    mots viennent du même enregistrement, ou sans vidéo."""
    return projet.sous_titres.apercu.decalage_s if voix_a_caler(projet) else 0.0


def audio_des_mots(projet: Projet) -> Path | None:
    """La piste son des mots des sous-titres, dans le dossier du projet (celle du module
    Transcription, ou celle d'une prise) ; None pour des mots d'un fichier SRT, qui n'a pas de son."""
    mots = mots_des_sous_titres(projet)
    if mots is None or not mots.audio:
        return None
    return projet.chemin(mots.audio)
