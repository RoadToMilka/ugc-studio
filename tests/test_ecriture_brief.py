"""Module Script (V2) : brief, durées par défaut, tutoiement automatique, pré-remplissage."""

from ugc_studio.ecriture.brief import (
    DUREES_PAR_DEFAUT,
    LANGUES_ECRITURE,
    PAYS,
    Brief,
    langue_du_projet,
    mots_vises,
    pays_de,
)
from ugc_studio.projets import LANGUES


def test_durees_par_defaut_des_reseaux():
    """§14, question 4 : TikTok 25 s, Snapchat 10 s, Facebook et Instagram 20 s, Autre 20 s."""
    assert DUREES_PAR_DEFAUT == {"tiktok": 25, "snapchat": 10, "meta": 20, "autre": 20}
    brief = Brief(reseau="snapchat")
    assert brief.duree_visee() == 10
    brief.duree_s = 30
    assert brief.duree_visee() == 30


def test_mots_vises_a_2_7_mots_par_seconde():
    assert mots_vises(25) == 68  # « 25 s ≈ 68 mots » (§10.7)
    assert mots_vises(10) == 27
    assert mots_vises(10, 3.0) == 30


def test_tutoiement_automatique():
    assert Brief(reseau="tiktok", age="55+").tutoiement_effectif() == "tu"
    assert Brief(reseau="snapchat").tutoiement_effectif() == "tu"
    assert Brief(reseau="meta", age="25-34").tutoiement_effectif() == "tu"
    assert Brief(reseau="meta", age="45-54").tutoiement_effectif() == "vous"
    assert Brief(reseau="meta").tutoiement_effectif() == "tu"  # âge inconnu
    assert Brief(reseau="tiktok", tutoiement="vous").tutoiement_effectif() == "vous"


def test_pays_langues_et_devises():
    assert pays_de("BE").langues == ("fr-BE", "nl-BE")
    assert pays_de("CH").devise == "CHF"
    assert pays_de("??").code == "FR"
    assert all(langue in LANGUES_ECRITURE for pays in PAYS for langue in pays.langues)
    # Chaque langue d'écriture correspond à une langue de projet (voix, transcription).
    assert all(langue_du_projet(langue) in LANGUES for langue in LANGUES_ECRITURE)
    assert langue_du_projet("fr-BE") == "fr-FR" and langue_du_projet("nl-BE") == "nl-BE"


def test_pre_remplissage_sans_jamais_ecraser_ce_qui_est_tape():
    brief = Brief(produit="Mon nom à moi")
    changes = brief.pre_remplir({"produit": "Culotte Léa", "prix": "21,90 €", "promo": ""})
    assert changes == ["prix"]
    assert brief.produit == "Mon nom à moi" and brief.prix == "21,90 €"
    assert brief.pre_remplis == ["prix"]
    # Nouvelle page lue : un champ encore « d'après la page » suit la nouvelle page.
    brief.pre_remplir({"prix": "44,90 €"})
    assert brief.prix == "44,90 €"
    # Modifié à la main : il n'est plus « d'après la page » et n'est plus touché.
    brief.prix = "40 €"
    brief.modifie_a_la_main("prix")
    brief.pre_remplir({"prix": "49,90 €"})
    assert brief.prix == "40 €" and brief.pre_remplis == []
    # Seuls les champs que la page peut remplir (ou le genre, d'après la voix) sont acceptés.
    assert brief.pre_remplir({"mots_interdits": "x", "genre": "femme"}) == ["genre"]


def test_pre_rempli_puis_vide_n_est_plus_marque():
    brief = Brief()
    brief.pre_remplir({"promo": "au lieu de 27,90 €"})
    brief.pre_remplir({"promo": ""})
    assert brief.promo == "" and brief.pre_remplis == []


def test_listes_de_contraintes():
    brief = Brief(mots_interdits="garanti, miracle\n  n°1 ;guérit", mentions="Code GLOW20\n\n  Offre limitée ")
    assert brief.liste_mots_interdits() == ["garanti", "miracle", "n°1", "guérit"]
    assert brief.liste_mentions() == ["Code GLOW20", "Offre limitée"]


def test_brief_relu_avec_des_valeurs_inconnues():
    brief = Brief.depuis_dict(
        {
            "pays": "ZZ",
            "langue": "xx-XX",
            "reseau": "myspace",
            "angle": "?",
            "duree_s": 999,
            "balises": 1,
            "nombre_accroches": 50,
            "pre_remplis": ["produit", "inconnu"],
            "champ_futur": "ignoré",
        }
    )
    assert (brief.pays, brief.langue, brief.reseau, brief.angle) == ("FR", "fr-FR", "tiktok", "auto")
    assert brief.duree_s == 0 and brief.balises is True and brief.nombre_accroches == 10
    assert brief.pre_remplis == ["produit"]
    assert Brief.depuis_dict(Brief(reseau="meta", consigne="Ton léger").en_dict()) == Brief(reseau="meta", consigne="Ton léger")
    assert Brief.depuis_dict(None) == Brief()
