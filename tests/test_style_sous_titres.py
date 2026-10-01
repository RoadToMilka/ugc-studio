"""V2, lot 3 (§7.1, §7.3, §7.4, §7.9) : style des sous-titres, format 7 des projets, largeur utile
selon l'alignement, mise en page (position verticale, réglage fin, alignement). Sans interface."""

import json

import pytest

from ugc_studio.mise_en_page import (
    Metriques,
    hauteur_du_bloc,
    limites_du_reglage_fin,
    mots_par_ligne,
    placer,
)
from ugc_studio.projets import GestionnaireProjets, Projet
from ugc_studio.sous_titres import (
    FORMAT_PERSONNALISE,
    MotAffiche,
    ReglagesSousTitres,
    SousTitre,
    cadre,
    cote_pair,
    ecran,
    resolution,
    sous_titre_au_temps,
)
from ugc_studio.style_sous_titres import (
    BAS,
    BLANC,
    CASSE_MAJUSCULES,
    CENTRE,
    DROITE,
    GAUCHE,
    HAUT,
    Couleur,
    Ombre,
    Position,
    StyleTexte,
    VideoApercu,
    en_dict,
    lire,
)

# --- Style : couleurs, lecture tolérante, forme écrite ------------------------------------------


def test_couleur_lue_et_ecrite():
    assert Couleur.depuis({"code": "#7c3aed", "opacite": 80}) == Couleur(124, 58, 237, 80.0)
    assert Couleur.depuis("FFD43B") == Couleur(255, 212, 59, 100.0)
    assert Couleur.depuis({"code": "#12345", "opacite": 50}) is None  # code incomplet
    assert Couleur.depuis({"code": "#000000", "opacite": 250}).opacite == 100.0  # ramenée à 100 %
    assert Couleur(255, 255, 255, 55.0).en_dict() == {"code": "#FFFFFF", "opacite": 55.0}
    assert BLANC.code == "#FFFFFF"


def test_lecture_tolerante_d_un_element_du_style():
    texte = lire(StyleTexte, {"taille_pct": 99, "casse": "en-italique", "graisse": "700", "ombre": {"flou_pct": -3, "active": 0}})
    assert texte.taille_pct == 15.0  # ramenée dans les limites
    assert texte.casse == StyleTexte().casse  # choix inconnu : ignoré
    assert texte.graisse == 700
    assert texte.ombre.flou_pct == 0.0 and not texte.ombre.active
    assert texte.ombre.couleur == Ombre().couleur  # absente : valeur par défaut
    assert lire(Position, "n'importe quoi") == Position()
    assert lire(Position, {"verticale": "haut", "alignement": "droite", "largeur_lignes_pct": 5}) == Position(
        HAUT, 0.0, DROITE, 30.0
    )


def test_forme_ecrite_du_style():
    ecrit = en_dict(StyleTexte())
    assert ecrit["police"] == "Inter" and ecrit["graisse"] == 600 and ecrit["casse"] == "normale"
    assert ecrit["couleur"] == {"code": "#FFFFFF", "opacite": 100.0}
    assert ecrit["ombre"]["couleur"] == {"code": "#000000", "opacite": 55.0}
    assert lire(StyleTexte, json.loads(json.dumps(ecrit))) == StyleTexte()


# --- Projet au format 7 -------------------------------------------------------------------------


def _reglages_complets() -> ReglagesSousTitres:
    return ReglagesSousTitres(
        caracteres_max=30,
        mots_max=4,
        lignes_max=1,
        couper_sur_ponctuation=False,
        duree_min_s=0.8,
        texte=StyleTexte(taille_pct=5.2, casse=CASSE_MAJUSCULES, ponctuation=False),
        position=Position(HAUT, 2.5, GAUCHE, 80.0),
        format=FORMAT_PERSONNALISE,
        largeur_perso=1200,
        hauteur_perso=1500,
        plateforme="meta",
        marge_max_pct=6.0,
        apercu=VideoApercu("C:/Montages/pub.mp4", 2.0, 1080, 1920, False),
        prereglage="fourni-surligneur",
        prereglage_nom="Surligneur",
    )


def test_format_7_ecrit_en_quatre_parties():
    ecrit = _reglages_complets().en_dict()
    assert set(ecrit) == {"style", "ecran", "apercu", "prereglage"}  # préréglage d'origine : lot 7
    assert set(ecrit["style"]) == {"texte", "mots", "animations", "position", "decoupage"}  # lots 5 et 6
    assert ecrit["style"]["decoupage"] == {
        "caracteres_max": 30, "mots_max": 4, "lignes_max": 1, "couper_sur_ponctuation": False, "duree_min_s": 0.8,
    }
    assert ecrit["style"]["position"] == {"verticale": "haut", "decalage_pct": 2.5, "alignement": "gauche", "largeur_lignes_pct": 80.0}
    assert ecrit["ecran"] == {"format": "personnalise", "largeur": 1200, "hauteur": 1500, "plateforme": "meta", "marge_max_pct": 6.0}
    assert ecrit["apercu"]["chemin"] == "C:/Montages/pub.mp4" and not ecrit["apercu"]["son_de_la_video"]
    assert ecrit["prereglage"] == {"identifiant": "fourni-surligneur", "nom": "Surligneur"}
    assert ReglagesSousTitres.depuis_dict(json.loads(json.dumps(ecrit))) == _reglages_complets()


def test_projet_de_la_v1_garde_son_decoupage_et_prend_l_apparence_de_la_v1():
    """Formats 4 à 6 : une seule liste de réglages ; « Tout en majuscules », la ponctuation et la
    taille passent dans le style du texte ; apparence de la V1, en bas de la zone, centrée."""
    ancien = {
        "caracteres_max": 20, "mots_max": 4, "lignes_max": 2, "couper_sur_ponctuation": True, "duree_min_s": 0.6,
        "majuscules": True, "ponctuation": False, "format": "auto", "plateforme": "snapchat", "marge_max_pct": 5.0,
        "taille_pct": 4.5,
    }
    reglages = ReglagesSousTitres.depuis_dict(ancien)
    assert (reglages.caracteres_max, reglages.mots_max, reglages.plateforme) == (20, 4, "snapchat")
    assert reglages.texte == StyleTexte(taille_pct=4.5, casse=CASSE_MAJUSCULES, ponctuation=False)
    assert reglages.texte.police == "Inter" and reglages.texte.graisse == 600
    assert reglages.position == Position(BAS, 0.0, CENTRE, 100.0)


def test_projet_au_format_6_s_ouvre_et_s_enregistre_au_format_7(tmp_path):
    dossier = tmp_path / "Ancien"
    dossier.mkdir()
    (dossier / "projet.json").write_text(
        json.dumps({"version_format": 6, "nom": "Ancien", "sous_titres": {"majuscules": True, "lignes_max": 1}}),
        encoding="utf-8",
    )
    gestion = GestionnaireProjets(tmp_path / "recents.json")
    projet = gestion.ouvrir(dossier)
    assert projet.sous_titres.texte.casse == CASSE_MAJUSCULES and projet.sous_titres.lignes_max == 1
    gestion.enregistrer()
    ecrit = json.loads((dossier / "projet.json").read_text(encoding="utf-8"))
    assert ecrit["version_format"] == Projet.VERSION_FORMAT == 7
    assert ecrit["sous_titres"]["style"]["texte"]["casse"] == "majuscules"
    assert ecrit["sous_titres"]["style"]["decoupage"]["lignes_max"] == 1


def test_format_personnalise_pair_et_dans_les_limites():
    assert cote_pair(1081) == 1082 and cote_pair(100) == 240 and cote_pair(9999) == 4096
    reglages = ReglagesSousTitres.depuis_dict({"ecran": {"format": "personnalise", "largeur": 1001, "hauteur": 50}})
    assert (reglages.largeur_perso, reglages.hauteur_perso) == (1002, 240)
    assert resolution(reglages) == (1002, 240)
    # Une vidéo impose son format, même personnalisé.
    assert resolution(reglages, (1080, 1920)) == (1080, 1920)
    assert ReglagesSousTitres.depuis_dict({"ecran": {"format": "21:9"}}).format == "auto"


def test_video_d_apercu():
    assert VideoApercu("C:/pub.mp4", 2.0, 1080, 1350).resolution == (1080, 1350)
    assert VideoApercu("", 0.0, 1080, 1350).resolution is None  # pas de vidéo
    assert VideoApercu("C:/pub.mp4").resolution is None  # résolution pas encore lue
    lue = lire(VideoApercu, {"chemin": "C:/pub.mp4", "decalage_s": -4, "largeur": 1080, "hauteur": 1920})
    assert lue.decalage_s == 0.0 and lue.resolution == (1080, 1920)


# --- Largeur utile selon l'alignement (§7.4) ---------------------------------------------------


def test_largeur_utile_centree_comme_en_v1():
    zone = cadre(ReglagesSousTitres(), 1080, 1920)
    assert zone.largeur_max == pytest.approx(972) and zone.largeur_securite == pytest.approx(840)
    assert zone.x_depart == 540


def test_largeur_utile_a_gauche_et_a_droite():
    # TikTok : 120 px de chaque côté ; marge maximum 5 % (54 px).
    gauche = cadre(ReglagesSousTitres(position=Position(alignement=GAUCHE)), 1080, 1920)
    assert gauche.x_depart == pytest.approx(120)
    assert gauche.largeur_securite == pytest.approx(840)  # jusqu'au bord droit de la zone
    assert gauche.largeur_max == pytest.approx(1026 - 120)  # jusqu'à la marge maximum de droite
    droite = cadre(ReglagesSousTitres(position=Position(alignement=DROITE), plateforme="youtube"), 1080, 1920)
    # YouTube Shorts : rien à gauche, 10 % à droite.
    assert droite.x_depart == pytest.approx(972)
    assert droite.largeur_securite == pytest.approx(972 - 54)
    assert droite.largeur_max == pytest.approx(972 - 54)


def test_largeur_maximale_des_lignes():
    zone = cadre(ReglagesSousTitres(position=Position(largeur_lignes_pct=50.0)), 1080, 1920)
    assert zone.largeur_securite == pytest.approx(420) and zone.largeur_max == pytest.approx(486)
    assert ecran(ReglagesSousTitres(position=Position(largeur_lignes_pct=50.0))).largeur_max == pytest.approx(486)


# --- Mise en page --------------------------------------------------------------------------------

METRIQUES = Metriques(ascendante=40.0, descendante=10.0, interligne=60.0)


def mesure(texte: str) -> float:
    return len(texte) * 10.0


def _sous_titre(textes: list[str], lignes: list[str], echelle: float = 1.0) -> tuple[SousTitre, list[MotAffiche]]:
    mots = [MotAffiche(t, t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate(textes)]
    return SousTitre(0.0, 2.0, lignes, 0, len(mots), echelle), mots


def test_mots_par_ligne_meme_avec_une_espace_dans_un_mot():
    assert mots_par_ligne(["Mais", "ce", "sérum"], ["Mais ce", "sérum"]) == [[0, 1], [2]]
    assert mots_par_ligne(["“ Hello", "you"], ["“ Hello you"]) == [[0, 1]]
    assert mots_par_ligne(["Mais", "ce"], ["Mais ce", "sérum"]) is None


def test_bloc_centre_en_bas_de_la_zone_de_securite():
    reglages = ReglagesSousTitres()  # TikTok : bas de la zone à 1920 - 660 = 1260 px
    zone = cadre(reglages, 1080, 1920)
    sous_titre, mots = _sous_titre(["Mais", "ce", "sérum"], ["Mais ce", "sérum"])
    bloc = placer(sous_titre, mots, reglages, zone, METRIQUES, mesure)
    assert bloc.hauteur == hauteur_du_bloc(2, METRIQUES) == 110  # 60 + 40 + 10
    assert bloc.y + bloc.hauteur == pytest.approx(1260)  # point fixe : le bas du bloc
    premiere, seconde = bloc.lignes
    assert (premiere.x, premiere.largeur) == (540 - 35, 70) and premiere.base == pytest.approx(1150 + 40)
    assert (seconde.x, seconde.largeur) == (540 - 25, 50) and seconde.base == pytest.approx(1150 + 100)
    assert [(m.texte, m.x, m.largeur, m.ligne) for m in bloc.mots] == [
        ("Mais", 505, 40, 0), ("ce", 555, 20, 0), ("sérum", 515, 50, 1),
    ]
    assert [m.index for m in bloc.mots] == [0, 1, 2]


def test_position_haut_centre_et_reglage_fin():
    zone_tiktok = cadre(ReglagesSousTitres(), 1080, 1920)
    sous_titre, mots = _sous_titre(["Top"], ["Top"])
    haut = placer(sous_titre, mots, ReglagesSousTitres(position=Position(HAUT)), zone_tiktok, METRIQUES, mesure)
    assert haut.y == pytest.approx(240)  # juste sous le haut de la zone de sécurité
    centre = placer(sous_titre, mots, ReglagesSousTitres(position=Position(CENTRE)), zone_tiktok, METRIQUES, mesure)
    assert centre.y + centre.hauteur / 2 == pytest.approx(960)
    decale = placer(sous_titre, mots, ReglagesSousTitres(position=Position(CENTRE, -10.0)), zone_tiktok, METRIQUES, mesure)
    assert decale.y == pytest.approx(centre.y - 192)  # 10 % de 1920 px vers le haut


def test_jamais_au_dela_de_la_marge_maximum():
    reglages = ReglagesSousTitres(position=Position(BAS, 40.0))  # beaucoup trop bas
    zone = cadre(reglages, 1080, 1920)
    sous_titre, mots = _sous_titre(["Top"], ["Top"])
    bloc = placer(sous_titre, mots, reglages, zone, METRIQUES, mesure)
    assert bloc.y + bloc.hauteur == pytest.approx(1920 - 96)  # marge maximum : 5 % de 1920 px
    reglages = ReglagesSousTitres(position=Position(HAUT, -40.0), plateforme="aucune")
    bloc = placer(sous_titre, mots, reglages, cadre(reglages, 1080, 1920), METRIQUES, mesure)
    assert bloc.y == pytest.approx(96)


def test_limites_du_reglage_fin_pour_le_plus_grand_sous_titre():
    reglages = ReglagesSousTitres()  # bas de la zone TikTok : 1260 px ; 2 lignes : 110 px
    bas, haut = limites_du_reglage_fin(reglages, cadre(reglages, 1080, 1920), METRIQUES)
    # Monter : le haut du bloc (1150 px) peut aller jusqu'à 96 px ; descendre : le bas jusqu'à 1824 px.
    assert bas == pytest.approx((96 - 1150) / 1920 * 100)
    assert haut == pytest.approx((1824 - 1260) / 1920 * 100)
    une_ligne = ReglagesSousTitres(lignes_max=1, position=Position(HAUT))
    bas, haut = limites_du_reglage_fin(une_ligne, cadre(une_ligne, 1080, 1920), METRIQUES)
    assert bas == pytest.approx((96 - 240) / 1920 * 100) and haut == pytest.approx((1824 - 50 - 240) / 1920 * 100)


def test_alignement_a_gauche_et_a_droite():
    sous_titre, mots = _sous_titre(["Mais", "ce", "sérum"], ["Mais ce", "sérum"])
    gauche = ReglagesSousTitres(position=Position(alignement=GAUCHE))
    bloc = placer(sous_titre, mots, gauche, cadre(gauche, 1080, 1920), METRIQUES, mesure)
    assert [ligne.x for ligne in bloc.lignes] == [120, 120] and bloc.x == 120 and bloc.largeur == 70
    droite = ReglagesSousTitres(position=Position(alignement=DROITE))
    bloc = placer(sous_titre, mots, droite, cadre(droite, 1080, 1920), METRIQUES, mesure)
    assert [ligne.x + ligne.largeur for ligne in bloc.lignes] == [960, 960]


def test_mot_seul_rapetisse():
    reglages = ReglagesSousTitres()
    sous_titre, mots = _sous_titre(["Anticonstitutionnellement"], ["Anticonstitutionnellement"], echelle=0.8)
    bloc = placer(sous_titre, mots, reglages, cadre(reglages, 1080, 1920), METRIQUES, mesure)
    assert bloc.echelle == 0.8 and bloc.largeur == pytest.approx(250 * 0.8)
    assert bloc.hauteur == pytest.approx(50 * 0.8)
    assert bloc.mots[0].largeur == pytest.approx(200)


def test_sous_titre_au_temps():
    sous_titres = [SousTitre(0.0, 1.0, ["a"], 0, 1), SousTitre(1.5, 2.0, ["b"], 1, 2)]
    assert [sous_titre_au_temps(sous_titres, t) for t in (0.0, 0.99, 1.2, 1.5, 2.0, -1)] == [0, 0, -1, 1, -1, -1]
