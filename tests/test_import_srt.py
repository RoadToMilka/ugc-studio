"""Sous-titres importés d'un fichier SRT (V3.1, lot 6) : lecture tolérante, moment de chaque mot
estimé selon sa longueur."""

import pytest

from ugc_studio.import_srt import (
    EntreeSrt,
    ErreurSrt,
    decoder,
    est_srt,
    lire_srt,
    mots_estimes,
    transcription_depuis_srt,
)

SRT = """1
00:00:00,500 --> 00:00:02,000
Franchement, je n'y
croyais pas…

2
00:00:02,400 --> 00:00:04,000
<i>Mais ce sérum</i> {\\an8}Glowzy !
"""


def test_lire_un_fichier_srt():
    entrees = lire_srt(SRT)
    assert entrees == [
        EntreeSrt(0.5, 2.0, "Franchement, je n'y croyais pas…"),  # lignes réunies
        EntreeSrt(2.4, 4.0, "Mais ce sérum Glowzy !"),  # balises retirées
    ]


def test_lecture_tolerante():
    """Fins de ligne Windows, point avant les millisecondes, numéros absents ou faux, ligne vide
    oubliée entre deux sous-titres, millisecondes sur moins de 3 chiffres, sous-titres vides."""
    texte = (
        "00:00:01.5 --> 00:00:02.000\r\nUn\r\n"
        "7\r\n00:00:02,000 --> 00:00:03,000\r\nDeux\r\n\r\n"
        "3\r\n00:00:03,000 --> 00:00:04,000\r\n\r\n"  # sans texte : ignoré
        "4\r\n00:00:05,000 --> 00:00:05,000\r\nRien\r\n"  # ne dure rien : ignoré
    )
    assert lire_srt(texte) == [EntreeSrt(1.5, 2.0, "Un"), EntreeSrt(2.0, 3.0, "Deux")]


def test_sous_titres_dans_le_desordre_ou_qui_se_chevauchent():
    texte = "2\n00:00:03,000 --> 00:00:05,000\nB\n\n1\n00:00:01,000 --> 00:00:04,000\nA\n"
    assert lire_srt(texte) == [EntreeSrt(1.0, 4.0, "A"), EntreeSrt(4.0, 5.0, "B")]


def test_encodages():
    assert decoder("﻿Été".encode()) == "Été"  # UTF-8 avec BOM
    assert decoder("Été".encode("cp1252")) == "Été"  # anciens logiciels


def test_moment_de_chaque_mot_selon_sa_longueur():
    """La durée d'un sous-titre est partagée selon la longueur des mots (lettres + 1) : le premier
    commence avec lui, le dernier finit avec lui, sans trou entre eux."""
    mots = mots_estimes([EntreeSrt(1.0, 3.0, "a bbb"), EntreeSrt(4.0, 5.0, "Glowzy !")])
    assert [m.texte for m in mots] == ["a", "bbb", "Glowzy", "!"]
    # « a » : 2 parts sur 6, « bbb » : 4 parts sur 6, sur 2 s.
    assert (mots[0].debut, mots[0].fin) == (1.0, pytest.approx(1.667, abs=1e-3))
    assert (mots[1].debut, mots[1].fin) == (mots[0].fin, 3.0)
    # « ! » seul compte pour 1 : il rejoindra le mot d'avant dans les sous-titres.
    assert mots[2].debut == 4.0 and mots[3].fin == 5.0 and mots[3].debut == mots[2].fin


def test_transcription_depuis_un_fichier(tmp_path):
    chemin = tmp_path / "montage.srt"
    chemin.write_text(SRT, encoding="utf-8")
    transcription = transcription_depuis_srt(chemin, "fr-FR")
    assert est_srt(transcription) and transcription.source == str(chemin) and not transcription.audio
    assert transcription.duree_s == 4.0 and transcription.infos["sous_titres"] == 2
    assert [m.texte for m in transcription.mots][:3] == ["Franchement,", "je", "n'y"]
    assert transcription.langue == "fr-FR" and transcription.horodatee and transcription.date


def test_fichier_sans_sous_titre(tmp_path):
    chemin = tmp_path / "vide.srt"
    chemin.write_text("Ceci n'est pas un fichier SRT.", encoding="utf-8")
    with pytest.raises(ErreurSrt, match="Aucun sous-titre lisible"):
        transcription_depuis_srt(chemin, "fr-FR")
    with pytest.raises(ErreurSrt, match="illisible"):
        transcription_depuis_srt(tmp_path / "absent.srt", "fr-FR")
