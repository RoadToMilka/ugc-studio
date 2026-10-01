"""V2, lot 4 (§7.4) : style du texte complet (couleurs, dégradé, contour, ombre, lueur, fond, espaces),
style de départ des nouveaux projets, débord du contour et du fond dans la mise en page et le
découpage. Sans interface."""

import json

import pytest

from ugc_studio.mise_en_page import Metriques, hauteur_du_bloc, limites_du_reglage_fin, placer
from ugc_studio.projets import GestionnaireProjets
from ugc_studio.sous_titres import MotAffiche, ReglagesSousTitres, SousTitre, cadre, calculer_sous_titres, ecran
from ugc_studio.style_sous_titres import (
    DROITE,
    FOND_LIGNE,
    GAUCHE,
    Contour,
    Couleur,
    Degrade,
    Espaces,
    Fond,
    Lueur,
    Ombre,
    Position,
    StyleTexte,
    en_dict,
    lire,
    style_de_depart,
)
from ugc_studio.transcription import Mot


def _style_complet() -> StyleTexte:
    return StyleTexte(
        police="Poppins",
        graisse=700,
        taille_pct=4.1,
        degrade=Degrade(True, Couleur(250, 204, 21), "horizontal"),
        contour=Contour(True, Couleur(0, 0, 0), 0.47, "nets"),
        ombre=Ombre(True, Couleur(0, 0, 0, 55.0), 0.94, 0.0, 0.31, "fond"),
        lueur=Lueur(True, Couleur(245, 158, 11), 2.2, 70.0),
        fond=Fond(FOND_LIGNE, Couleur(255, 255, 255), 1.9, 0.6, 1.6, True, Couleur(17, 24, 39), 0.2),
        espaces=Espaces(152.0, 0.08, 1.9),
    )


def test_style_complet_ecrit_puis_relu():
    ecrit = en_dict(_style_complet())
    assert ecrit["degrade"] == {"actif": True, "couleur": {"code": "#FACC15", "opacite": 100.0}, "direction": "horizontal"}
    assert ecrit["contour"] == {"actif": True, "couleur": {"code": "#000000", "opacite": 100.0}, "epaisseur_pct": 0.47, "angles": "nets"}
    assert ecrit["ombre"]["portee"] == "fond"
    assert ecrit["fond"]["mode"] == "ligne" and ecrit["fond"]["bordure_couleur"] == {"code": "#111827", "opacite": 100.0}
    assert ecrit["espaces"] == {"interligne_pct": 152.0, "lettres_pct": 0.08, "mots_pct": 1.9}
    assert lire(StyleTexte, json.loads(json.dumps(ecrit))) == _style_complet()


def test_lecture_tolerante_des_effets():
    lu = lire(
        StyleTexte,
        {
            "contour": {"actif": True, "epaisseur_pct": 12, "angles": "pointus"},
            "fond": {"mode": "partout", "couleur": "bleu", "arrondi_pct": -1},
            "espaces": {"interligne_pct": 10, "lettres_pct": 9},
            "lueur": {"active": True, "intensite_pct": 300},
            "degrade": {"actif": True, "direction": "en-rond"},
            "ombre": {"portee": "ciel", "active": False},
        },
    )
    assert lu.contour == Contour(True, Contour().couleur, 3.0, "arrondis")  # ramenée à 3 % ; angles inconnus : ignorés
    assert lu.fond == Fond(arrondi_pct=0.0)  # mode inconnu et couleur illisible : valeurs par défaut
    assert lu.espaces == Espaces(50.0, 3.0, 0.0)
    assert lu.lueur == Lueur(active=True, intensite_pct=100.0)
    assert lu.degrade == Degrade(actif=True)
    assert lu.ombre == Ombre(active=False)


def test_projet_de_la_1_4_garde_son_apparence():
    """Un projet de la 1.4.0 (format 7, sans les groupes du lot 4) : sans contour, lueur ni fond."""
    reglages = ReglagesSousTitres.depuis_dict(
        {"style": {"texte": {"police": "Inter", "graisse": 600, "taille_pct": 4.0, "ombre": {"active": True}}}}
    )
    assert reglages.texte == StyleTexte()
    assert not reglages.texte.contour.actif and not reglages.texte.lueur.active and not reglages.texte.fond.visible


def test_style_de_depart_des_nouveaux_projets(tmp_path):
    depart = style_de_depart()
    assert (depart.police, depart.graisse, depart.taille_pct, depart.couleur) == ("Montserrat", 800, 4.0, Couleur(255, 255, 255))
    assert depart.contour == Contour(True, Couleur(0, 0, 0), 0.3, "arrondis")
    assert not depart.ombre.active and not depart.lueur.active and not depart.fond.visible
    gestion = GestionnaireProjets(tmp_path / "recents.json")
    projet = gestion.creer("Nouveau", tmp_path)
    assert projet.sous_titres.texte == depart
    assert gestion.ouvrir(projet.dossier).sous_titres.texte == depart  # écrit puis relu


# --- Débord du contour et du fond (mise en page) ---------------------------------------------

METRIQUES = Metriques(ascendante=40.0, descendante=10.0, interligne=60.0, debord_x=6.0, debord_y=4.0)


def mesure(texte: str) -> float:
    return len(texte) * 10.0


def _sous_titre(textes: list[str], lignes: list[str], echelle: float = 1.0) -> tuple[SousTitre, list[MotAffiche]]:
    mots = [MotAffiche(t, t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate(textes)]
    return SousTitre(0.0, 2.0, lignes, 0, len(mots), echelle), mots


def test_le_bloc_compte_le_debord():
    reglages = ReglagesSousTitres()  # TikTok : bas de la zone à 1260 px
    sous_titre, mots = _sous_titre(["Mais", "ce", "sérum"], ["Mais ce", "sérum"])
    bloc = placer(sous_titre, mots, reglages, cadre(reglages, 1080, 1920), METRIQUES, mesure)
    assert bloc.hauteur == hauteur_du_bloc(2, METRIQUES) == 110 + 2 * 4
    assert bloc.y + bloc.hauteur == pytest.approx(1260)  # la boîte visible s'arrête au bas de la zone
    premiere, seconde = bloc.lignes
    assert premiere.base == pytest.approx(bloc.y + 4 + 40) and seconde.base == pytest.approx(premiere.base + 60)
    assert (premiere.x, premiere.largeur) == (540 - 35, 70)  # le texte reste centré
    assert bloc.x == 540 - 35 - 6 and bloc.largeur == 70 + 2 * 6


def test_a_gauche_la_boite_visible_part_du_bord_de_la_zone():
    sous_titre, mots = _sous_titre(["Top"], ["Top"])
    gauche = ReglagesSousTitres(position=Position(alignement=GAUCHE))
    bloc = placer(sous_titre, mots, gauche, cadre(gauche, 1080, 1920), METRIQUES, mesure)
    assert bloc.x == 120 and bloc.lignes[0].x == 126  # le contour ne déborde pas de la zone
    droite = ReglagesSousTitres(position=Position(alignement=DROITE))
    bloc = placer(sous_titre, mots, droite, cadre(droite, 1080, 1920), METRIQUES, mesure)
    assert bloc.x + bloc.largeur == 960 and bloc.lignes[0].x + bloc.lignes[0].largeur == 954


def test_le_reglage_fin_s_arrete_avec_le_debord():
    reglages = ReglagesSousTitres()
    sans = limites_du_reglage_fin(reglages, cadre(reglages, 1080, 1920), Metriques(40.0, 10.0, 60.0))
    avec = limites_du_reglage_fin(reglages, cadre(reglages, 1080, 1920), METRIQUES)
    assert avec[0] > sans[0] or avec[1] < sans[1]  # un bloc plus haut a moins de place pour bouger


def mesure_avec_debord(texte: str) -> float:
    """Comme le moteur : largeur du texte plus le débord de chaque côté (attribut « debord »)."""
    return len(texte) * 30.0 + 2 * 10.0


mesure_avec_debord.debord = 10.0


def test_le_decoupage_compte_le_debord():
    reglages = ReglagesSousTitres(caracteres_max=60, mots_max=10)
    ecran_video = ecran(reglages)  # une ligne tient en 840 px dans la zone de sécurité TikTok
    mots = [Mot(texte, i * 0.3, i * 0.3 + 0.25) for i, texte in enumerate(["abcdefghij"] * 3)]
    sans_debord = calculer_sous_titres(mots, reglages, "fr-FR", ecran_video, lambda texte: len(texte) * 30.0)
    avec_debord = calculer_sous_titres(mots, reglages, "fr-FR", ecran_video, mesure_avec_debord)
    # « abcdefghij abcdefghij » : 630 px ; « × 3 » : 960 px. Deux mots par ligne dans les deux cas,
    # mais le débord ne doit jamais faire passer une ligne au-delà de la largeur.
    for decoupage, debord in ((sans_debord, 0.0), (avec_debord, 20.0)):
        for sous_titre in decoupage.sous_titres:
            for ligne in sous_titre.lignes:
                assert len(ligne) * 30.0 + debord <= ecran_video.largeur_max


def test_mot_seul_rapetisse_sans_rapetisser_le_debord():
    reglages = ReglagesSousTitres()
    ecran_video = ecran(reglages)
    mots = [Mot("A" * 40, 0.0, 1.0)]  # 1200 px de texte : trop large
    decoupage = calculer_sous_titres(mots, reglages, "fr-FR", ecran_video, mesure_avec_debord)
    (seul,) = decoupage.sous_titres
    # Texte réduit + débord (20 px, pas réduit) = largeur maximum (972 px).
    assert 1200 * seul.echelle + 20 == pytest.approx(ecran_video.largeur_max)
