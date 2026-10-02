"""Étape 8 (§7.2, §7.3, §8.1) — texte affiché, découpage des sous-titres, limites d'écran, SRT."""

import pytest

from ugc_studio.sous_titres import (
    ESPACE_INSECABLE as NBSP,
    FORMATS,
    TAILLE_REDUITE_MIN,
    Ecran,
    MotAffiche,
    ReglagesSousTitres,
    caler_les_temps,
    creer_sous_titres,
    decales,
    decouper,
    ecran,
    ecrire_srt,
    mots_a_afficher,
    resolution,
    srt,
    temps_srt,
    texte_affiche,
    typographie,
)
from ugc_studio.style_sous_titres import CASSE_MAJUSCULES, CASSE_MINUSCULES, StyleTexte
from ugc_studio.transcription import Mot, resolution_video

# Écran de test : 10 px par caractère ; 20 caractères dans la zone de sécurité, 30 jusqu'à la marge.
ECRAN = Ecran(largeur=1000, hauteur=1000, taille_texte=50, largeur_securite=200, largeur_max=300)


def mesure(texte: str) -> float:
    return len(texte) * 10


def _mots(texte: str, duree: float = 0.3, ecart: float = 0.05, locuteur: str = "") -> list[Mot]:
    mots, temps = [], 0.0
    for morceau in texte.split():
        mots.append(Mot(morceau, round(temps, 3), round(temps + duree, 3), locuteur))
        temps += duree + ecart
    return mots


def _affiches(texte: str, **options) -> list[MotAffiche]:
    return mots_a_afficher(_mots(texte), ReglagesSousTitres(**options), "fr-FR")


def _decouper(texte: str, **options):
    reglages = ReglagesSousTitres(**options)
    return decouper(mots_a_afficher(_mots(texte), reglages, "fr-FR"), reglages, ECRAN, mesure)


# --- Texte affiché (§7.2) ---


def test_typographie_francaise():
    assert typographie("semaines !", "fr-FR") == f"semaines{NBSP}!"
    assert typographie("incroyable!", "fr-FR") == f"incroyable{NBSP}!"
    assert typographie("Quoi ?!", "fr-FR") == f"Quoi{NBSP}?!"
    assert typographie("Attention :", "fr-FR") == f"Attention{NBSP}:"
    assert typographie("10:30", "fr-FR") == "10:30"
    assert typographie("«Wahou»", "fr-FR") == f"«{NBSP}Wahou{NBSP}»"
    assert typographie("top .", "fr-FR") == "top."
    assert typographie(f"semaines{NBSP}!", "fr-FR") == f"semaines{NBSP}!"  # déjà juste : inchangé


def test_typographie_des_autres_langues():
    assert typographie("amazing !", "en-US") == "amazing!"
    assert typographie("really ?", "nl-BE") == "really?"


def test_ponctuation_masquee_et_majuscules():
    reglages = ReglagesSousTitres(texte=StyleTexte(ponctuation=False))
    assert texte_affiche("l'huile,", reglages, "fr-FR") == "l'huile"
    assert texte_affiche("anti-rides.", reglages, "fr-FR") == "anti-rides"
    assert texte_affiche("3.5", reglages, "fr-FR") == "3.5"
    assert texte_affiche("semaines !", reglages, "fr-FR") == "semaines"
    assert texte_affiche("…", reglages, "fr-FR") == ""
    majuscules = ReglagesSousTitres(texte=StyleTexte(casse=CASSE_MAJUSCULES))
    assert texte_affiche("Sérum Glowzy !", majuscules, "fr-FR") == f"SÉRUM GLOWZY{NBSP}!"
    minuscules = ReglagesSousTitres(texte=StyleTexte(casse=CASSE_MINUSCULES))
    assert texte_affiche("Sérum Glowzy !", minuscules, "fr-FR") == f"sérum glowzy{NBSP}!"


def test_mots_a_afficher():
    mots = [Mot("Franchement,", 0.0, 0.5), Mot("euh", 0.6, 0.8), Mot("top", 0.9, 1.2), Mot("!", 1.2, 1.3)]
    affiches = mots_a_afficher(mots, ReglagesSousTitres(), "fr-FR", {"euh"}, True)
    # Hésitation masquée ; « ! » transcrit à part rejoint le mot d'avant, qui garde ses temps.
    assert [(m.texte, m.debut, m.fin) for m in affiches] == [("Franchement,", 0.0, 0.5), (f"top{NBSP}!", 0.9, 1.2)]
    affiches = mots_a_afficher(mots, ReglagesSousTitres(), "fr-FR", {"euh"}, False)
    assert [m.texte for m in affiches] == ["Franchement,", "euh", f"top{NBSP}!"]
    # Ponctuation masquée : le mot garde son texte d'origine, qui sert à couper sur la ponctuation.
    affiches = mots_a_afficher(mots, ReglagesSousTitres(texte=StyleTexte(ponctuation=False)), "fr-FR", {"euh"}, True)
    assert [(m.texte, m.original) for m in affiches] == [("Franchement", "Franchement,"), ("top", "top !")]


# --- Découpage (§7.3) ---

TEXTE = (
    "Franchement, je n'y croyais pas du tout. Mais ce sérum a vraiment changé ma peau en deux "
    "semaines, et mes amies me demandent mon secret. Le lien est juste en dessous."
)


@pytest.mark.parametrize("caracteres, mots_max, lignes", [(24, 5, 2), (16, 3, 1), (40, 8, 2), (10, 2, 1)])
def test_limites_toujours_respectees(caracteres, mots_max, lignes):
    affiches = _affiches(TEXTE)
    reglages = ReglagesSousTitres(caracteres_max=caracteres, mots_max=mots_max, lignes_max=lignes)
    sous_titres = decouper(affiches, reglages, ECRAN, mesure)
    # Tous les mots, dans l'ordre, jamais coupés ni répétés.
    assert [m.texte for s in sous_titres for m in affiches[s.premier_mot : s.dernier_mot]] == [m.texte for m in affiches]
    assert " ".join(" ".join(s.lignes) for s in sous_titres).split() == " ".join(m.texte for m in affiches).split()
    for s in sous_titres:
        nombre = s.dernier_mot - s.premier_mot
        assert nombre <= mots_max
        assert nombre == 1 or len(" ".join(s.lignes)) <= caracteres
        assert len(s.lignes) <= lignes  # jamais une ligne de trop
        assert all(mesure(ligne) <= ECRAN.largeur_max for ligne in s.lignes)  # jamais au-delà de la marge


def test_fin_de_phrase_termine_le_sous_titre():
    sous_titres = _decouper("C'est fou. Vraiment top.", caracteres_max=40, mots_max=8)
    assert [s.lignes for s in sous_titres] == [["C'est fou."], ["Vraiment top."]]
    # Option décochée : la fin de phrase n'est plus une coupure obligatoire.
    sous_titres = _decouper("C'est fou. Vraiment top.", caracteres_max=40, mots_max=8, couper_sur_ponctuation=False)
    assert [s.lignes for s in sous_titres] == [["C'est fou.", "Vraiment top."]]  # un seul sous-titre, 2 lignes


def test_coupe_de_preference_apres_une_virgule():
    sous_titres = _decouper("Franchement, je n'y croyais pas", caracteres_max=24, mots_max=5)
    assert [s.lignes for s in sous_titres] == [["Franchement,"], ["je n'y croyais pas"]]


def test_sous_titres_equilibres():
    sous_titres = _decouper("un deux trois quatre cinq six sept", caracteres_max=24, mots_max=4)
    assert [s.dernier_mot - s.premier_mot for s in sous_titres] in ([4, 3], [3, 4])


def test_changement_de_personne_et_long_silence():
    mots = _mots("Tu as testé ?", locuteur="spk_1") + [
        Mot(m.texte, m.debut + 2.0, m.fin + 2.0, "spk_2") for m in _mots("Oui carrément")
    ]
    reglages = ReglagesSousTitres(caracteres_max=40, mots_max=8, couper_sur_ponctuation=False)
    affiches = mots_a_afficher(mots, reglages, "fr-FR")
    assert [s.lignes for s in decouper(affiches, reglages, ECRAN, mesure)] == [[f"Tu as testé{NBSP}?"], ["Oui carrément"]]
    mots = [Mot("Attendez", 0.0, 0.5), Mot("voilà", 2.0, 2.4)]  # 1,5 s de silence
    affiches = mots_a_afficher(mots, reglages, "fr-FR")
    assert len(decouper(affiches, reglages, ECRAN, mesure)) == 2


def test_deux_lignes_dans_la_zone_de_securite():
    # 25 caractères : trop large pour une ligne dans la zone de sécurité (20), donc deux lignes.
    (sous_titre,) = _decouper("abcde fghij klmno pqrst u", caracteres_max=30, mots_max=6, lignes_max=2)
    assert sous_titre.lignes == ["abcde fghij", "klmno pqrst u"]  # les deux lignes les plus proches
    assert not sous_titre.dans_la_marge


def test_debordement_dans_la_marge_avant_de_redecouper():
    # Une seule ligne permise : 25 caractères dépassent la zone de sécurité mais tiennent dans la marge.
    (sous_titre,) = _decouper("abcde fghij klmno pqrst u", caracteres_max=30, mots_max=6, lignes_max=1)
    assert sous_titre.lignes == ["abcde fghij klmno pqrst u"] and sous_titre.dans_la_marge
    assert sous_titre.echelle == 1.0 and not sous_titre.signale


def test_redecoupage_quand_la_marge_ne_suffit_pas():
    # 35 caractères sur une ligne : au-delà de la marge maximum (30) → deux sous-titres, taille inchangée.
    sous_titres = _decouper("abcdefgh ijklmnop qrstuvwx yzabcdef", caracteres_max=40, mots_max=6, lignes_max=1)
    assert len(sous_titres) == 2 and all(s.echelle == 1.0 for s in sous_titres)


def test_mot_seul_trop_large_rapetisse_et_signale():
    (sous_titre,) = _decouper("Anticonstitutionnellementissimes")  # 32 caractères : 320 px > 300 px
    assert sous_titre.echelle == pytest.approx(300 / 320) and sous_titre.signale and not sous_titre.trop_large
    (sous_titre,) = _decouper("x" * 80)  # même à la taille minimum, trop large
    assert sous_titre.echelle == TAILLE_REDUITE_MIN and sous_titre.trop_large and sous_titre.signale


def test_duree_minimale_et_petits_trous_combles():
    affiches = [MotAffiche("Oui", "Oui.", 1.0, 1.2), MotAffiche("Bien", "Bien.", 1.5, 1.7), MotAffiche("Fin", "Fin.", 3.0, 3.2)]
    reglages = ReglagesSousTitres(duree_min_s=0.6)
    sous_titres = decouper(affiches, reglages, ECRAN, mesure)
    caler_les_temps(sous_titres, reglages.duree_min_s, duree_totale=3.5)
    # « Oui » : prolongé jusqu'au début de « Bien » (sans le chevaucher), puis avancé pour durer 0,6 s.
    assert (sous_titres[0].debut, sous_titres[0].fin) == (0.9, 1.5)
    # « Bien » : prolongé à 0,6 s ; « Fin » : prolongé jusqu'à la fin de l'audio, puis avancé.
    assert (sous_titres[1].debut, sous_titres[1].fin) == (1.5, 2.1)
    assert (sous_titres[2].debut, sous_titres[2].fin) == (2.9, 3.5)
    affiches = [MotAffiche("Un", "Un.", 0.0, 1.0), MotAffiche("Deux", "Deux.", 1.2, 2.0)]
    sous_titres = decouper(affiches, reglages, ECRAN, mesure)
    caler_les_temps(sous_titres, reglages.duree_min_s)
    assert sous_titres[0].fin == 1.2  # trou de 0,2 s comblé : pas de clignotement


# --- Écran ---


def test_ecran_selon_format_et_plateforme():
    assert resolution(ReglagesSousTitres(), (1080, 1920)) == (1080, 1920)
    assert resolution(ReglagesSousTitres(), None) == FORMATS["9:16"]
    # V2 : une vidéo impose son format (l'overlay de la V3 doit avoir sa taille exacte).
    assert resolution(ReglagesSousTitres(format="16:9"), (1080, 1920)) == (1080, 1920)
    assert resolution(ReglagesSousTitres(format="16:9"), None) == (1920, 1080)
    tiktok = ecran(ReglagesSousTitres())
    assert (tiktok.largeur, tiktok.hauteur) == (1080, 1920)
    assert tiktok.largeur_max == pytest.approx(972) and tiktok.largeur_securite == pytest.approx(840)
    assert tiktok.taille_texte == pytest.approx(76.8)
    meta = ecran(ReglagesSousTitres(plateforme="meta"))
    assert meta.largeur_securite == pytest.approx(1080 * 0.88)
    # Zone de sécurité plus large que la marge maximum : c'est la marge maximum qui compte.
    aucune = ecran(ReglagesSousTitres(plateforme="aucune", marge_max_pct=8))
    assert aucune.largeur_securite == aucune.largeur_max == pytest.approx(1080 * 0.84)


def test_resolution_d_une_video_tournee():
    assert resolution_video({"resolution": [1920, 1080], "rotation": 90}) == (1080, 1920)
    assert resolution_video({"resolution": [1080, 1920]}) == (1080, 1920)
    assert resolution_video({"resolution": [0, 0]}) is None
    assert resolution_video({}) is None


def test_reglages_relus_et_ramenes_dans_les_limites():
    reglages = ReglagesSousTitres.depuis_dict(
        {"caracteres_max": 500, "mots_max": "3", "lignes_max": 7, "duree_min_s": "abc", "format": "21:9", "plateforme": "myspace", "inconnu": 1}
    )
    assert (reglages.caracteres_max, reglages.mots_max, reglages.lignes_max) == (120, 3, 2)
    assert reglages.duree_min_s == ReglagesSousTitres().duree_min_s
    assert (reglages.format, reglages.plateforme) == ("auto", "tiktok")
    assert ReglagesSousTitres.depuis_dict(None) == ReglagesSousTitres()
    majuscules = ReglagesSousTitres(texte=StyleTexte(casse=CASSE_MAJUSCULES))
    assert ReglagesSousTitres.depuis_dict(majuscules.en_dict()) == majuscules


# --- SRT (§8.1) ---


def test_temps_srt():
    assert temps_srt(0) == "00:00:00,000"
    assert temps_srt(1.25) == "00:00:01,250"
    assert temps_srt(3725.0996) == "01:02:05,100"


def test_fichier_srt(tmp_path):
    mots = [Mot("Franchement,", 0.1, 0.7), Mot("ce", 0.8, 0.9), Mot("sérum", 0.9, 1.3), Mot("est", 1.35, 1.5), Mot("top.", 1.5, 2.0)]
    reglages = ReglagesSousTitres(caracteres_max=14, mots_max=3, lignes_max=1, duree_min_s=0.0)
    _affiches, sous_titres = creer_sous_titres(mots, reglages, "fr-FR", ECRAN, mesure)
    # Coupure après la virgule, sous-titres équilibrés, petits trous comblés.
    assert srt(sous_titres) == (
        "1\r\n00:00:00,100 --> 00:00:00,800\r\nFranchement,\r\n\r\n"
        "2\r\n00:00:00,800 --> 00:00:01,350\r\nce sérum\r\n\r\n"
        "3\r\n00:00:01,350 --> 00:00:02,000\r\nest top.\r\n"
    )
    chemin = tmp_path / "pub.srt"
    ecrire_srt(chemin, sous_titres)
    brut = chemin.read_bytes()
    assert brut.startswith(b"\xef\xbb\xbf")  # UTF-8 avec BOM, pour Premiere Pro
    assert "sérum".encode() in brut and b"\r\n" in brut and b"\r\r\n" not in brut
    assert srt([]) == ""


def test_sous_titres_sur_le_temps_de_la_video():
    """V3.1, lot 6 : la voix commence à 2 s dans la vidéo (« La voix commence à ») ; les exports
    posent les sous-titres et leurs mots à ce moment de la vidéo. Sans décalage, rien ne change."""
    mots = [Mot("Franchement,", 0.1, 0.7), Mot("ce", 0.8, 0.9), Mot("sérum", 0.9, 1.3)]
    reglages = ReglagesSousTitres(caracteres_max=14, mots_max=3, lignes_max=1, duree_min_s=0.0)
    affiches, sous_titres = creer_sous_titres(mots, reglages, "fr-FR", ECRAN, mesure)
    decales_st, decales_mots = decales(sous_titres, affiches, 2.0)
    assert [(s.debut, s.fin) for s in decales_st] == [(s.debut + 2.0, s.fin + 2.0) for s in sous_titres]
    assert [(m.debut, m.texte) for m in decales_mots] == [(m.debut + 2.0, m.texte) for m in affiches]
    assert [s.texte for s in decales_st] == [s.texte for s in sous_titres] and sous_titres[0].debut == 0.1  # copies
    assert srt(decales_st).startswith("1\r\n00:00:02,100 --> ")
    assert decales(sous_titres, affiches, 0.0) == (sous_titres, affiches)
