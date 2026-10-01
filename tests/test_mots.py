"""V2, lot 5 (§7.5, §7.11) : états des mots (à venir, actif, déjà dits, accentués), raccourcis, forme
écrite, mots accentués du script d'une prise. Sans interface."""

import json

from ugc_studio.alignement import marquer_les_accentues, mots_du_script, mots_du_script_accentues
from ugc_studio.script import texte_brut
from ugc_studio.sous_titres import ReglagesSousTitres, accrocher_la_ponctuation, mots_a_afficher
from ugc_studio.style_sous_titres import (
    JAUNE_ACTIF,
    JAUNE_KARAOKE,
    RACCOURCIS,
    Contour,
    Couleur,
    EtatMot,
    FondMot,
    Mots,
    Soulignement,
    appliquer_raccourci,
    en_dict,
    etats_du_raccourci,
    lire,
    raccourci_de,
)
from ugc_studio.transcription import Mot, Transcription


def test_un_etat_vaut_comme_le_texte_au_depart():
    etat = EtatMot()
    assert not etat.change and etat.echelle == 1 and etat.opacite == 1 and etat.decalage_pct == 0
    assert Mots().fixe and raccourci_de(Mots()) == "fixe"
    ecrit = en_dict(etat)
    assert ecrit["couleur"] is None and ecrit["visible"] is True
    assert lire(EtatMot, json.loads(json.dumps(ecrit))) == etat


def test_etat_complet_ecrit_puis_relu():
    etat = EtatMot(
        visible=True,
        opacite_pct=45.0,
        couleur=Couleur(255, 212, 59),
        contour=Contour(True, Couleur(0, 0, 0), 0.47, "nets"),
        fond=FondMot(Couleur(124, 58, 237), 0.94, 0.16, 1.25, True, 160),
        soulignement=Soulignement(Couleur(239, 68, 68), 0.3, 0.4),
        taille_pct=108.0,
        decalage_y_pct=-0.5,
    )
    mots = Mots(actif=etat, avance_ms=-80, accentues_actifs=True)
    relu = ReglagesSousTitres.depuis_dict(json.loads(json.dumps(ReglagesSousTitres(mots=mots).en_dict())))
    assert relu.mots == mots and not relu.mots.fixe
    ecrit = ReglagesSousTitres(mots=mots).en_dict()["style"]["mots"]
    assert ecrit["actif"]["fond"]["glisse"] is True and ecrit["actif"]["couleur"] == {"code": "#FFD43B", "opacite": 100.0}
    assert ecrit["a_venir"]["couleur"] is None  # « comme le texte »


def test_lecture_tolerante_des_mots():
    lu = lire(
        Mots,
        {
            "avance_ms": 900,
            "actif": {"taille_pct": 999, "opacite_pct": -5, "couleur": "jaune", "fond": {"marge_x_pct": 40}, "decalage_y_pct": None},
            "dits": "n'importe quoi",
        },
    )
    assert lu.avance_ms == 200  # ramenée dans les limites
    assert lu.actif.taille_pct == 200.0 and lu.actif.opacite_pct == 0.0
    assert lu.actif.couleur is None  # illisible : comme le texte
    assert lu.actif.fond == FondMot(marge_x_pct=5.0)  # un fond, avec ses valeurs par défaut et une marge ramenée
    assert lu.actif.decalage_y_pct is None and lu.dits == EtatMot()


def test_projet_sans_mots_garde_son_apparence():
    """Un projet de la 1.5.0 (sans « mots ») : sous-titre fixe, comme avant."""
    reglages = ReglagesSousTitres.depuis_dict({"style": {"texte": {"police": "Montserrat", "graisse": 800}}})
    assert reglages.mots == Mots() and reglages.mots.fixe


def test_raccourcis():
    assert set(RACCOURCIS) == {"fixe", "surlignage", "karaoke", "apparition", "mot_par_mot"}
    surlignage = appliquer_raccourci(Mots(avance_ms=50), "surlignage")
    assert surlignage.actif == EtatMot(couleur=JAUNE_ACTIF, taille_pct=108.0) and surlignage.avance_ms == 50
    karaoke = etats_du_raccourci("karaoke")
    assert karaoke["dits"].couleur == JAUNE_KARAOKE == karaoke["actif"].couleur
    apparition = etats_du_raccourci("apparition")
    assert not apparition["a_venir"].visible and apparition["dits"].visible
    mot_par_mot = etats_du_raccourci("mot_par_mot")
    assert not mot_par_mot["a_venir"].visible and not mot_par_mot["dits"].visible
    for nom in RACCOURCIS:
        assert raccourci_de(appliquer_raccourci(Mots(), nom)) == nom
    modifie = appliquer_raccourci(Mots(), "surlignage")
    modifie = Mots(a_venir=modifie.a_venir, actif=EtatMot(couleur=Couleur(0, 0, 0)), dits=modifie.dits)
    assert raccourci_de(modifie) is None  # personnalisé


# --- Mots accentués du script (§16 du document V2) ------------------------------------------------

SCRIPT = [
    {"texte": "Franchement, je n'y croyais pas… Mais ce sérum a "},
    {"texte": "vraiment", "accentue": True},
    {"texte": " changé ma peau "},
    {"balise": "laugh"},
    {"texte": " en "},
    {"texte": "deux semaines", "accentue": True},
    {"texte": " !"},
]


def test_mots_du_script_avec_leurs_accents():
    mots = mots_du_script_accentues(SCRIPT)
    assert [texte for texte, _accentue in mots] == mots_du_script(texte_brut(SCRIPT))
    assert [texte for texte, accentue in mots if accentue] == ["vraiment", "deux", "semaines !"]
    # Un passage accentué au milieu d'un mot : le mot entier est accentué.
    assert mots_du_script_accentues([{"texte": "super"}, {"texte": "bien", "accentue": True}, {"texte": " oui"}]) == [
        ("superbien", True), ("oui", False),
    ]
    # La ponctuation seule n'accentue pas un mot.
    assert mots_du_script_accentues([{"texte": "Oui"}, {"texte": " !", "accentue": True}]) == [("Oui !", False)]


def test_marquer_les_accentues_dans_les_mots_d_une_prise():
    textes = mots_du_script(texte_brut(SCRIPT))
    mots = [Mot(texte, i * 0.3, i * 0.3 + 0.25) for i, texte in enumerate(textes)]
    mots[3].texte = "croyait"  # mot corrigé depuis dans le module Transcription : sans effet ici
    marques = marquer_les_accentues(mots, SCRIPT)
    assert [m.texte for m in marques if m.accentue] == ["vraiment", "deux", "semaines !"]
    assert not any(m.accentue for m in mots)  # les mots de la transcription ne changent pas
    assert [m.debut for m in marques] == [m.debut for m in mots]
    # Mots corrigés autour d'un accent : il n'est plus reconnu (il s'affiche comme les autres).
    mots[9].texte = "réellement"
    assert [m.texte for m in marquer_les_accentues(mots, SCRIPT) if m.accentue] == ["deux", "semaines !"]
    # La casse et la ponctuation ne comptent pas (même comparaison que l'alignement).
    mots[9].texte = "VRAIMENT"
    assert "VRAIMENT" in [m.texte for m in marquer_les_accentues(mots, SCRIPT) if m.accentue]


def test_l_accent_suit_le_mot_affiche():
    mots = [Mot("Top", 0.0, 0.3, accentue=True), Mot("!", 0.3, 0.35), Mot("Oui", 0.5, 0.8)]
    assert [(m.texte, m.accentue) for m in accrocher_la_ponctuation(mots)] == [("Top !", True), ("Oui", False)]
    affiches = mots_a_afficher(mots, ReglagesSousTitres(), "fr-FR")
    assert [(m.texte, m.accentue) for m in affiches] == [("Top !", True), ("Oui", False)]


def test_l_accent_n_est_pas_enregistre():
    transcription = Transcription(mots=[Mot("Top", 0.0, 0.3, accentue=True), Mot("Oui", 0.5, 0.8)])
    ecrit = transcription.en_dict()
    assert all("accentue" not in mot for mot in ecrit["mots"])  # repéré d'après le script, à chaque calcul
    relu = Transcription.depuis_dict(json.loads(json.dumps(ecrit)))
    assert [m.texte for m in relu.mots] == ["Top", "Oui"]


def test_la_boite_compte_l_agrandissement_des_mots():
    """Un mot peut grandir de 50 % : la boîte de la ligne gagne, de chaque côté, la moitié de ce que
    gagne son plus large mot ; à gauche, la ligne part d'autant plus loin du bord de la zone."""
    from ugc_studio.mise_en_page import Metriques, placer
    from ugc_studio.sous_titres import MotAffiche, SousTitre, cadre
    from ugc_studio.style_sous_titres import GAUCHE, Position

    def mesure(texte: str) -> float:
        return len(texte) * 10.0

    textes = ["Mais", "sérum"]
    mots = [MotAffiche(t, t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate(textes)]
    sous_titre = SousTitre(0.0, 1.0, ["Mais sérum"], 0, 2)
    metriques = Metriques(40.0, 10.0, 60.0, croissance=0.5)
    reglages = ReglagesSousTitres()
    bloc = placer(sous_titre, mots, reglages, cadre(reglages, 1080, 1920), metriques, mesure)
    assert bloc.largeur == 100 + 2 * 0.5 * 50 / 2  # « Mais sérum » (100 px), « sérum » (50 px) grandit de 25 px
    gauche = ReglagesSousTitres(position=Position(alignement=GAUCHE))
    bloc = placer(sous_titre, mots, gauche, cadre(gauche, 1080, 1920), metriques, mesure)
    assert bloc.x == 120 and bloc.lignes[0].x == 120 + 12.5
