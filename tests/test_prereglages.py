"""V2, lot 7 (§7.6, §7.13) : préréglages de style des sous-titres. Les 7 fournis (« Par défaut » depuis
la V3.1), appliquer, « (modifié) », bibliothèque (ajouter, renommer, dupliquer, supprimer, ★,
rétablir), export et import, style des nouveaux projets, référence des ↺ (V3.1). Sans interface."""

import json

import pytest

from ugc_studio.prereglages import (
    ANCIEN_DEFAUT_FOURNI,
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
from ugc_studio.sous_titres import ReglagesSousTitres, style_de_depart_complet
from ugc_studio.style_sous_titres import (
    CASSE_MAJUSCULES,
    CENTRE,
    Animations,
    Contour,
    Mots,
    FOND_LIGNE,
    JAUNE_ACTIF,
    JAUNE_KARAOKE,
    Couleur,
    Position,
    VideoApercu,
    style_de_depart,
)

NOMS = ["Par défaut", "Blanc contour noir", "Surligneur", "Karaoké", "Mot par mot", "Bandeau", "Atténué"]


def _lu(prereglage) -> ReglagesSousTitres:
    return ReglagesSousTitres.depuis_dict({"style": prereglage.style})


def test_les_sept_styles_fournis():
    """« Par défaut » (V3.1 : neutre, le style de départ), puis les 6 styles de l'annexe B du document
    V2, faits avec les seuls réglages de l'app."""
    fournis = prereglages_fournis()
    assert [p.nom for p in fournis] == NOMS and all(p.fourni for p in fournis)
    assert fournis[0].identifiant == DEFAUT_FOURNI and fournis[1].identifiant == ANCIEN_DEFAUT_FOURNI
    neutre, blanc, surligneur, karaoke, mot_par_mot, bandeau, attenue = (_lu(p) for p in fournis)
    # « Par défaut » : Poppins Extra-grasse, blanc, contour noir ; tout le reste neutre.
    assert (neutre.texte.police, neutre.texte.graisse, neutre.texte.taille_pct) == ("Poppins", 800, 4.0)
    assert neutre.texte.couleur == Couleur(255, 255, 255) and neutre.texte.contour == Contour(True, Couleur(0, 0, 0), 0.3, "arrondis")
    assert not (neutre.texte.ombre.active or neutre.texte.lueur.active or neutre.texte.fond.visible)
    assert neutre.mots == Mots() and neutre.mots.fixe and neutre.animations == Animations() and neutre.animations.aucune
    assert neutre.position == Position(CENTRE, 11.0)
    assert (neutre.caracteres_max, neutre.mots_max, neutre.lignes_max) == (24, 5, 2)
    assert fournis[0].style == style_de_depart_complet()  # le style de départ, à l'identique
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
    surligneur = prereglages_fournis()[2]
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
    assert copie.nom == "Par défaut (copie)" and not copie.fourni and copie.style == bibliotheque.defaut().style
    assert bibliotheque.prereglages.index(copie) == 1  # juste après l'original
    bibliotheque.supprimer(DEFAUT_FOURNI)  # celui des nouveaux projets : plus de ★
    assert bibliotheque.par_defaut == "" and bibliotheque.defaut() is None
    assert vus and vus[-1] == len(bibliotheque.prereglages)


def test_mettre_a_jour_puis_retablir_les_fournis(tmp_path):
    bibliotheque = BibliothequePrereglages(tmp_path / "p.json")
    bandeau = bibliotheque.prereglages[5]
    bibliotheque.mettre_a_jour(bandeau.identifiant, style_du_projet(ReglagesSousTitres()))
    assert _lu(bibliotheque.prereglage(bandeau.identifiant)).texte.police == "Inter"
    bibliotheque.supprimer(bibliotheque.prereglages[2].identifiant)  # Surligneur
    bibliotheque.definir_par_defaut("")
    a_moi = bibliotheque.ajouter("Mon style", {})
    bibliotheque.renommer(bibliotheque.prereglages[0].identifiant, "Mon blanc")
    perso = bibliotheque.ajouter("Surligneur", {})  # le nom d'un fourni supprimé
    bibliotheque.retablir_fournis()
    noms = [p.nom for p in bibliotheque.prereglages]
    assert noms[:7] == NOMS and "Mon style" in noms and "Surligneur (2)" in noms
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
    karaoke = source.prereglages[3]
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
    assert projet.sous_titres.prereglage == DEFAUT_FOURNI and projet.sous_titres.texte.police == "Poppins"
    relu = gestion.ouvrir(projet.dossier).sous_titres
    assert relu.prereglage == DEFAUT_FOURNI and relu.prereglage_nom == "Par défaut"
    assert not modifie(relu, bibliotheque.defaut())
    bibliotheque.definir_par_defaut("")
    sans = gestion.creer("Sans étoile", tmp_path).sous_titres
    assert sans.texte == style_de_depart() and sans.prereglage == "" and sans.mots.fixe
    # Sans ★ : le style de départ complet (le même que « Par défaut »), position comprise.
    assert style_du_projet(sans) == style_de_depart_complet() and sans.position == Position(CENTRE, 11.0)
    # Sans bibliothèque (ni ★) : le même style de départ.
    seul = GestionnaireProjets(tmp_path / "autres.json").creer("Seul", tmp_path).sous_titres
    assert style_du_projet(seul) == style_de_depart_complet()


def _bibliotheque_v1(chemin, par_defaut: str) -> None:
    """Fichier de la bibliothèque tel qu'écrit jusqu'à la 3.0.3 : les 6 fournis, sans « Par défaut »."""
    anciens = [p for p in prereglages_fournis() if p.identifiant != DEFAUT_FOURNI]
    chemin.write_text(
        json.dumps(
            {
                "version_format": 1,
                "par_defaut": par_defaut,
                "prereglages": [{"identifiant": p.identifiant, "nom": p.nom, "fourni": True, "style": p.style} for p in anciens],
            }
        ),
        encoding="utf-8",
    )


def test_par_defaut_ajoute_aux_bibliotheques_d_avant(tmp_path):
    """Bibliothèque de la 3.0.3 : « Par défaut » arrive en tête, et la ★ passe de « Blanc contour noir »
    (la ★ de départ) à « Par défaut » ; une ★ mise ailleurs, ou retirée, reste comme elle est. Une
    seule fois : supprimé ensuite, « Par défaut » ne revient pas tout seul."""
    chemin = tmp_path / "p.json"
    _bibliotheque_v1(chemin, ANCIEN_DEFAUT_FOURNI)
    bibliotheque = BibliothequePrereglages(chemin)
    assert [p.nom for p in bibliotheque.prereglages] == NOMS and bibliotheque.par_defaut == DEFAUT_FOURNI
    assert json.loads(chemin.read_text(encoding="utf-8"))["version_format"] == 2  # réécrit à la nouvelle version
    bibliotheque.supprimer(DEFAUT_FOURNI)
    assert [p.nom for p in BibliothequePrereglages(chemin).prereglages] == NOMS[1:]
    for etoile in ("fourni-surligneur", ""):
        _bibliotheque_v1(chemin, etoile)
        assert BibliothequePrereglages(chemin).par_defaut == etoile


def test_reference_des_retablir(tmp_path):
    """V3.1 : les ↺ ramènent au préréglage du projet tel qu'il est enregistré (sans lui, au style de
    départ) ; l'écran et la vidéo importée restent ceux du projet."""
    bibliotheque = BibliothequePrereglages(tmp_path / "p.json")
    karaoke = bibliotheque.prereglages[3]
    projet = appliquer(ReglagesSousTitres(format="1:1", apercu=VideoApercu("C:/pub.mp4")), karaoke)
    projet.caracteres_max = 30
    reference = bibliotheque.reference(projet)
    assert style_du_projet(reference) == karaoke.style and reference.caracteres_max != 30
    assert (reference.format, reference.apercu) == ("1:1", projet.apercu)
    assert bibliotheque.nom_de_reference(projet) == "Revenir au préréglage « Karaoké »"
    # Enregistré à nouveau (« Mettre à jour ») : la référence suit, le projet ne s'en écarte plus.
    bibliotheque.mettre_a_jour(karaoke.identifiant, style_du_projet(projet))
    assert style_du_projet(bibliotheque.reference(projet)) == style_du_projet(projet)
    bibliotheque.supprimer(karaoke.identifiant)  # préréglage supprimé depuis : le style de départ
    assert style_du_projet(bibliotheque.reference(projet)) == style_de_depart_complet()
    assert bibliotheque.nom_de_reference(projet) == "Revenir au style de départ"
