"""V2, lot 7 (§7.6, §7.13) : préréglages de style des sous-titres. Les 6 fournis, appliquer, « (modifié) »,
bibliothèque (ajouter, renommer, dupliquer, supprimer, ★, rétablir), export et import, style des
nouveaux projets. Sans interface."""

import json

import pytest

from ugc_studio.prereglages import (
    DEFAUT_FOURNI,
    BibliothequePrereglages,
    ErreurPrereglage,
    appliquer,
    modifie,
    normaliser,
    prereglages_fournis,
    style_du_projet,
)
from ugc_studio.projets import GestionnaireProjets
from ugc_studio.sous_titres import ReglagesSousTitres
from ugc_studio.style_sous_titres import (
    CASSE_MAJUSCULES,
    CENTRE,
    FOND_LIGNE,
    JAUNE_ACTIF,
    JAUNE_KARAOKE,
    Couleur,
    Position,
    VideoApercu,
    style_de_depart,
)

NOMS = ["Blanc contour noir", "Surligneur", "Karaoké", "Mot par mot", "Bandeau", "Atténué"]


def _lu(prereglage) -> ReglagesSousTitres:
    return ReglagesSousTitres.depuis_dict({"style": prereglage.style})


def test_les_six_styles_fournis():
    """Les 6 styles de l'annexe B du document V2, faits avec les seuls réglages de l'app."""
    fournis = prereglages_fournis()
    assert [p.nom for p in fournis] == NOMS and all(p.fourni for p in fournis)
    blanc, surligneur, karaoke, mot_par_mot, bandeau, attenue = (_lu(p) for p in fournis)
    assert (blanc.texte.police, blanc.texte.graisse, blanc.texte.taille_pct) == ("Montserrat", 800, 4.2)
    assert blanc.mots.actif.couleur == JAUNE_ACTIF and blanc.animations.mot.type == "pop"
    assert blanc.position == Position(CENTRE, 11.0)  # milieu du bloc à 61 % de la hauteur
    assert surligneur.mots.actif.fond.couleur == Couleur(124, 58, 237) and surligneur.animations.mot.type == "zoom"
    assert karaoke.mots.dits.couleur == JAUNE_KARAOKE and karaoke.animations.mot.taille_sommet_pct == 114.0
    assert mot_par_mot.texte.casse == CASSE_MAJUSCULES and not mot_par_mot.mots.a_venir.visible
    assert (mot_par_mot.mots_max, mot_par_mot.lignes_max) == (2, 1)
    assert mot_par_mot.animations.mot.profil().depart == 60.0
    assert bandeau.texte.fond.mode == FOND_LIGNE and bandeau.mots.fixe and bandeau.animations.aucune
    assert attenue.mots.a_venir.opacite_pct == 45.0 and attenue.mots.actif.lueur.active
    # Chaque style est écrit sous sa forme complète (les mêmes valeurs qu'un projet).
    assert all(p.style == normaliser(p.style) for p in fournis)


def test_appliquer_garde_l_ecran_et_retient_l_origine():
    surligneur = prereglages_fournis()[1]
    projet = ReglagesSousTitres(format="1:1", plateforme="meta", marge_max_pct=6.0, apercu=VideoApercu("C:/pub.mp4"))
    applique = appliquer(projet, surligneur)
    assert (applique.format, applique.plateforme, applique.marge_max_pct, applique.apercu) == ("1:1", "meta", 6.0, projet.apercu)
    assert applique.texte.police == "Poppins" and applique.prereglage == surligneur.identifiant
    assert applique.prereglage_nom == "Surligneur" and not modifie(applique, surligneur)
    change = ReglagesSousTitres.depuis_dict(applique.en_dict())
    change.caracteres_max = 30  # le découpage fait partie du style
    assert modifie(change, surligneur)
    assert style_du_projet(applique) == surligneur.style


def test_bibliotheque_au_premier_lancement_et_relue(tmp_path):
    chemin = tmp_path / "prereglages_sous_titres.json"
    bibliotheque = BibliothequePrereglages(chemin)
    assert [p.nom for p in bibliotheque.prereglages] == NOMS and bibliotheque.par_defaut == DEFAUT_FOURNI
    cree = bibliotheque.ajouter("Mon style", style_du_projet(ReglagesSousTitres(caracteres_max=30)))
    relue = BibliothequePrereglages(chemin)
    assert [p.nom for p in relue.prereglages] == [*NOMS, "Mon style"] and relue.par_defaut == DEFAUT_FOURNI
    assert _lu(relue.prereglage(cree.identifiant)).caracteres_max == 30


def test_ajouter_renommer_dupliquer_supprimer(tmp_path):
    bibliotheque = BibliothequePrereglages(tmp_path / "p.json")
    vus = []
    bibliotheque.abonner(lambda: vus.append(len(bibliotheque.prereglages)))
    a = bibliotheque.ajouter("Surligneur", {})  # nom déjà pris : numéroté
    assert a.nom == "Surligneur (2)" and _lu(a) == ReglagesSousTitres()
    with pytest.raises(ErreurPrereglage):
        bibliotheque.renommer(a.identifiant, "   ")
    assert bibliotheque.renommer(a.identifiant, "Karaoké").nom == "Karaoké (2)"
    assert bibliotheque.renommer(a.identifiant, "Karaoké (2)").nom == "Karaoké (2)"  # son propre nom reste libre
    copie = bibliotheque.dupliquer(DEFAUT_FOURNI)
    assert copie.nom == "Blanc contour noir (copie)" and not copie.fourni and copie.style == bibliotheque.defaut().style
    assert bibliotheque.prereglages.index(copie) == 1  # juste après l'original
    bibliotheque.supprimer(DEFAUT_FOURNI)  # celui des nouveaux projets : plus de ★
    assert bibliotheque.par_defaut == "" and bibliotheque.defaut() is None
    assert vus and vus[-1] == len(bibliotheque.prereglages)


def test_mettre_a_jour_puis_retablir_les_fournis(tmp_path):
    bibliotheque = BibliothequePrereglages(tmp_path / "p.json")
    bandeau = bibliotheque.prereglages[4]
    bibliotheque.mettre_a_jour(bandeau.identifiant, style_du_projet(ReglagesSousTitres()))
    assert _lu(bibliotheque.prereglage(bandeau.identifiant)).texte.police == "Inter"
    bibliotheque.supprimer(bibliotheque.prereglages[1].identifiant)  # Surligneur
    bibliotheque.definir_par_defaut("")
    a_moi = bibliotheque.ajouter("Mon style", {})
    bibliotheque.renommer(bibliotheque.prereglages[0].identifiant, "Mon blanc")
    perso = bibliotheque.ajouter("Surligneur", {})  # le nom d'un fourni supprimé
    bibliotheque.retablir_fournis()
    noms = [p.nom for p in bibliotheque.prereglages]
    assert noms[:6] == NOMS and "Mon style" in noms and "Surligneur (2)" in noms
    assert bibliotheque.prereglage(bandeau.identifiant).style == bandeau.style  # comme à l'origine
    assert bibliotheque.prereglage(a_moi.identifiant) is not None and bibliotheque.prereglage(perso.identifiant).nom == "Surligneur (2)"
    assert bibliotheque.par_defaut == ""  # « aucun ★ » est un choix : il est gardé
    bibliotheque.supprimer(DEFAUT_FOURNI)
    bibliotheque.definir_par_defaut(a_moi.identifiant)
    bibliotheque.supprimer(a_moi.identifiant)
    bibliotheque.retablir_fournis()
    assert bibliotheque.par_defaut == ""


def test_exporter_puis_importer(tmp_path):
    source = BibliothequePrereglages(tmp_path / "a.json")
    karaoke = source.prereglages[2]
    fichier = tmp_path / "Karaoké.json"
    source.exporter([karaoke.identifiant], fichier)
    ecrit = json.loads(fichier.read_text(encoding="utf-8"))
    assert ecrit["type"] == "prereglages_sous_titres" and ecrit["prereglages"][0]["nom"] == "Karaoké"
    assert "identifiant" not in ecrit["prereglages"][0]  # un nouvel identifiant à l'import
    cible = BibliothequePrereglages(tmp_path / "b.json")
    (importe,) = cible.importer(fichier)
    assert importe.nom == "Karaoké (2)" and importe.style == karaoke.style and not importe.fourni
    assert importe.identifiant != karaoke.identifiant


def test_un_fichier_illisible_est_refuse_sans_etre_touche(tmp_path):
    bibliotheque = BibliothequePrereglages(tmp_path / "p.json")
    nombre = len(bibliotheque.prereglages)
    for contenu, message in (
        ("pas du json", "illisible"),
        ('{"autre": 1}', "exporté par UGC Studio"),
        ('{"prereglages": [{"nom": "", "style": {}}]}', "aucun préréglage lisible"),
    ):
        fichier = tmp_path / "mauvais.json"
        fichier.write_text(contenu, encoding="utf-8")
        with pytest.raises(ErreurPrereglage, match=message):
            bibliotheque.importer(fichier)
        assert fichier.read_text(encoding="utf-8") == contenu  # jamais renommé ni modifié
    assert len(bibliotheque.prereglages) == nombre
    with pytest.raises(ErreurPrereglage, match="illisible"):
        bibliotheque.importer(tmp_path / "absent.json")


def test_un_style_ecrit_a_la_main_est_lu_avec_ses_limites(tmp_path):
    fichier = tmp_path / "main.json"
    fichier.write_text(
        json.dumps({"prereglages": [{"nom": "  Écrit   à la main ", "style": {"texte": {"taille_pct": 999}, "decoupage": {"lignes_max": 7}}}]}),
        encoding="utf-8",
    )
    (lu,) = BibliothequePrereglages(tmp_path / "p.json").importer(fichier)
    reglages = _lu(lu)
    assert lu.nom == "Écrit à la main" and reglages.lignes_max == 2 and reglages.texte.taille_pct < 999


def test_style_des_nouveaux_projets(tmp_path):
    bibliotheque = BibliothequePrereglages(tmp_path / "p.json")
    gestion = GestionnaireProjets(tmp_path / "recents.json")
    gestion.style_des_nouveaux = bibliotheque.reglages_des_nouveaux
    projet = gestion.creer("Avec étoile", tmp_path)
    assert projet.sous_titres.prereglage == DEFAUT_FOURNI and projet.sous_titres.texte.taille_pct == 4.2
    relu = gestion.ouvrir(projet.dossier).sous_titres
    assert relu.prereglage == DEFAUT_FOURNI and relu.prereglage_nom == "Blanc contour noir"
    assert not modifie(relu, bibliotheque.defaut())
    bibliotheque.definir_par_defaut("")
    sans = gestion.creer("Sans étoile", tmp_path).sous_titres
    assert sans.texte == style_de_depart() and sans.prereglage == "" and sans.mots.fixe
