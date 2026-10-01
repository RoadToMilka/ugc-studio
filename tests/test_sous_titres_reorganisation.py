"""V1.1 : sous-titres réorganisés à la main (sous_titres.py, sans interface).

Monter, descendre, couper, fusionner, rétablir ; mêmes règles que le découpage automatique ; les
réglages redécoupent le reste autour des sous-titres ajustés ; un ajustement suit les mots
corrigés dans le module Transcription ; le temps des mots ne change jamais.
"""

import pytest

from ugc_studio.sous_titres import (
    CARACTERES,
    CHEVAUCHEMENT,
    ECRAN,
    LIGNES,
    MOTS,
    PERSONNE,
    PHRASE,
    SANS_MOT,
    SILENCE,
    Ajustement,
    Defait,
    Ecran,
    Refus,
    ReglagesSousTitres,
    calculer_sous_titres,
    couper_avant,
    descendre_dernier_mot,
    fusionner_avec_le_suivant,
    monter_premier_mot,
    retablir_automatique,
    srt,
    texte_ajustements_defaits,
    texte_reglage_qui_defait,
    verifier_groupe,
)
from ugc_studio.transcription import Mot, Transcription, corriger, couper, fusionner, supprimer

# Écran de test : 10 px par caractère ; 20 caractères dans la zone de sécurité, 30 jusqu'à la marge.
ECRAN_TEST = Ecran(largeur=1000, hauteur=1000, taille_texte=50, largeur_securite=200, largeur_max=300)
NBSP = " "


def mesure(texte: str) -> float:
    return len(texte) * 10


def _pub() -> list[Mot]:
    return [
        Mot("Mais", 0.0, 0.3),
        Mot("ce", 0.35, 0.5),
        Mot("sérum", 0.55, 0.9),
        Mot("Glowzy", 0.95, 1.4),
        Mot("a", 1.45, 1.5),
        Mot("vraiment", 1.55, 2.0),
        Mot("changé", 2.05, 2.4),
        Mot("ma", 2.45, 2.6),
        Mot("peau", 2.65, 3.0),
        Mot("en", 3.05, 3.15),
        Mot("deux", 3.2, 3.5),
        Mot("semaines", 3.55, 4.0),
        Mot("!", 4.0, 4.05),
    ]


def _calculer(mots, ajustements=(), **options):
    reglages = ReglagesSousTitres(**({"caracteres_max": 40, "mots_max": 3, "duree_min_s": 0.0} | options))
    return calculer_sous_titres(mots, reglages, "fr-FR", ECRAN_TEST, mesure, ajustements=ajustements), reglages


def _textes(decoupage) -> list[str]:
    return [s.texte.replace("\n", " ").replace(NBSP, " ") for s in decoupage.sous_titres]


def _appliquer(action, mots, decoupage, reglages, *arguments, **options):
    resultat = action(decoupage, *arguments, reglages, ECRAN_TEST, mesure)
    assert resultat.possible, resultat.message
    nouveau, _reglages = _calculer(mots, resultat.ajustements, **options)
    assert not nouveau.defaits
    return nouveau, resultat


def test_decoupage_de_depart():
    decoupage, _reglages = _calculer(_pub())
    assert _textes(decoupage) == ["Mais ce sérum", "Glowzy a vraiment", "changé ma peau", "en deux semaines !"]
    assert not any(s.ajuste for s in decoupage.sous_titres) and not decoupage.defaits


def test_couper_puis_monter_le_premier_mot():
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    decoupage, resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 1)
    assert _textes(decoupage) == ["Mais", "ce sérum", "Glowzy a vraiment", "changé ma peau", "en deux semaines !"]
    assert [s.ajuste for s in decoupage.sous_titres] == [True, True, False, False, False]
    assert resultat.choisi == 0
    decoupage, resultat = _appliquer(monter_premier_mot, mots, decoupage, reglages, 1)
    assert _textes(decoupage)[:3] == ["Mais ce", "sérum", "Glowzy a vraiment"]
    assert resultat.choisi == 1


def test_descendre_le_dernier_mot():
    mots = _pub()
    decoupage, reglages = _calculer(mots, mots_max=5)
    assert _textes(decoupage) == ["Mais ce sérum Glowzy", "a vraiment changé ma", "peau en deux semaines !"]
    decoupage, resultat = _appliquer(descendre_dernier_mot, mots, decoupage, reglages, 1, mots_max=5)
    assert _textes(decoupage) == ["Mais ce sérum Glowzy", "a vraiment changé", "ma peau en deux semaines !"]
    assert [s.ajuste for s in decoupage.sous_titres] == [False, True, True]
    assert resultat.choisi == 1


def test_monter_le_seul_mot_d_un_sous_titre_le_fait_disparaitre():
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    decoupage, _resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 2)  # « Mais ce » | « sérum »
    decoupage, resultat = _appliquer(fusionner_avec_le_suivant, mots, decoupage, reglages, 0)
    assert _textes(decoupage)[0] == "Mais ce sérum" and decoupage.sous_titres[0].ajuste
    decoupage, _resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 2)
    decoupage, resultat = _appliquer(monter_premier_mot, mots, decoupage, reglages, 1)
    assert _textes(decoupage)[:2] == ["Mais ce sérum", "Glowzy a vraiment"]
    assert resultat.choisi == 0  # le sous-titre vidé n'existe plus : on montre le précédent


def test_le_temps_des_mots_ne_change_jamais():
    mots = _pub()
    avant = [(m.debut, m.fin) for m in mots]
    decoupage, reglages = _calculer(mots)
    decoupage, _resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 1)
    decoupage, _resultat = _appliquer(monter_premier_mot, mots, decoupage, reglages, 1)
    assert [(m.debut, m.fin) for m in mots] == avant
    for sous_titre in decoupage.sous_titres:
        assert sous_titre.debut == decoupage.mots[sous_titre.premier_mot].debut
        assert sous_titre.fin >= decoupage.mots[sous_titre.dernier_mot - 1].fin


def test_action_refusee_avec_la_raison_et_le_reglage():
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    resultat = monter_premier_mot(decoupage, 1, reglages, ECRAN_TEST, mesure)
    assert not resultat.possible and resultat.ajustements == ()
    assert resultat.message == "Impossible : le sous-titre 1 aurait 4 mots, et « Mots au plus » est réglé sur 3."
    resultat = fusionner_avec_le_suivant(decoupage, 0, reglages, ECRAN_TEST, mesure)
    assert resultat.message.startswith("Impossible : le sous-titre fusionné aurait 6 mots")
    # Exemple du cahier des charges : la limite de caractères.
    decoupage, reglages = _calculer(mots, caracteres_max=24, mots_max=8)
    groupe = decoupage.mots[0:6]  # « Mais ce sérum Glowzy a vraiment » : 31 caractères
    _disposition, refus = verifier_groupe(groupe, reglages, ECRAN_TEST, mesure)
    assert refus == (Refus(CARACTERES, 31, 24),)
    assert refus[0].pour_une_action() == "ce sous-titre ferait 31 caractères, et « Caractères au plus » est réglé sur 24"


def test_le_reglage_change_rend_l_action_possible():
    decoupage, reglages = _calculer(_pub())
    groupe = decoupage.mots[0:4]  # « Mais ce sérum Glowzy »
    assert verifier_groupe(groupe, reglages, ECRAN_TEST, mesure)[1] == (Refus(MOTS, 4, 3),)
    plus_large = ReglagesSousTitres(caracteres_max=40, mots_max=4)
    disposition, refus = verifier_groupe(groupe, plus_large, ECRAN_TEST, mesure)
    assert refus == () and disposition.lignes


@pytest.mark.parametrize(
    ("mots", "options", "attendu"),
    [
        # Fin de phrase : coupure toujours faite si « Couper de préférence après la ponctuation ».
        ([Mot("C'est", 0, 0.2), Mot("fou.", 0.25, 0.5), Mot("Vraiment", 0.55, 0.9)], {}, Refus(PHRASE, mot="fou.")),
        # Changement de personne.
        (
            [Mot("Oui", 0, 0.2, "spk_1"), Mot("Non", 0.25, 0.5, "spk_2")],
            {},
            Refus(PERSONNE, mot="Oui", suivant="Non"),
        ),
        # Silence de plus de 0,8 s.
        ([Mot("Alors", 0, 0.2), Mot("voilà", 1.2, 1.5)], {}, Refus(SILENCE, 1.0, 0.8, "Alors", "voilà")),
        # Tiendrait sur 2 lignes, mais une seule permise.
        (
            [Mot("abcdefghij", 0, 0.2), Mot("klmnopqrst", 0.25, 0.5), Mot("uvwxyzabcd", 0.55, 0.9)],
            {"lignes_max": 1},
            Refus(LIGNES, limite=1),
        ),
        # Trop large, même sur 2 lignes jusqu'à la marge maximum.
        ([Mot("a" * 35, 0, 0.2), Mot("b" * 35, 0.25, 0.5)], {"caracteres_max": 120}, Refus(ECRAN, limite=2)),
    ],
)
def test_memes_regles_que_le_decoupage_automatique(mots, options, attendu):
    reglages = ReglagesSousTitres(**({"caracteres_max": 40, "mots_max": 5} | options))
    decoupage = calculer_sous_titres(mots, reglages, "fr-FR", ECRAN_TEST, mesure)
    _disposition, refus = verifier_groupe(decoupage.mots, reglages, ECRAN_TEST, mesure)
    assert refus == (attendu,)
    assert len(decoupage.sous_titres) >= 2  # le découpage automatique coupe au même endroit


def test_textes_des_raisons():
    assert Refus(PHRASE, mot="fou.").pour_une_action() == (
        "« fou. » termine une phrase, et « Couper de préférence après la ponctuation » est coché : une fin "
        "de phrase termine alors toujours le sous-titre"
    )
    assert Refus(SILENCE, 1.25, 0.8, "Alors", "voilà").pour_une_action() == (
        "il y a un silence de 1,25 s entre « Alors » et « voilà », et un silence de plus de 0,8 s termine "
        "toujours le sous-titre"
    )
    assert Refus(LIGNES, limite=1).pour_une_action("le sous-titre 3") == (
        "le sous-titre 3 ne tiendrait pas sur une ligne dans l'écran, et « Lignes au plus » est réglé sur 1"
    )
    assert Refus(MOTS, 6, 5).pour_un_reglage() == "6 mots, pour 5 au plus"
    assert Refus(CARACTERES, 22, 20).pour_un_reglage() == "22 caractères, pour 20 au plus"
    assert Refus(SANS_MOT).pour_un_reglage() == "plus aucun de ses mots n'est affiché"


def test_silence_juste_au_dessus_de_la_limite_jamais_affiche_0_8():
    mots = [Mot("Alors", 0, 0.2), Mot("voilà", 1.0001, 1.3)]
    reglages = ReglagesSousTitres()
    decoupage = calculer_sous_titres(mots, reglages, "fr-FR", ECRAN_TEST, mesure)
    _disposition, (refus,) = verifier_groupe(decoupage.mots, reglages, ECRAN_TEST, mesure)
    assert refus.regle == SILENCE and "silence de 0,81 s" in refus.pour_une_action()


def test_un_reglage_redecoupe_le_reste_autour_des_ajustements():
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    decoupage, resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 1)  # « Mais » | « ce sérum »
    plus_large, _reglages = _calculer(mots, resultat.ajustements, mots_max=5)
    assert _textes(plus_large) == ["Mais", "ce sérum", "Glowzy a vraiment changé", "ma peau en deux semaines !"]
    assert [s.ajuste for s in plus_large.sous_titres] == [True, True, False, False]


def test_reglage_qui_defait_un_ajustement():
    mots = _pub()
    decoupage, reglages = _calculer(mots, mots_max=5)
    _decoupage, resultat = _appliquer(descendre_dernier_mot, mots, decoupage, reglages, 1, mots_max=5)
    # 4 mots au plus : « ma peau en deux semaines ! » (5 mots) ne tient plus.
    plus_strict, _reglages = _calculer(mots, resultat.ajustements, mots_max=4)
    (defait,) = plus_strict.defaits
    assert defait.refus == (Refus(MOTS, 5, 4),)
    assert defait.texte == f"ma peau en deux semaines{NBSP}!" and defait.premier_mot == 7
    # Ses mots reviennent au découpage automatique ; l'autre ajustement (« a vraiment changé ») tient.
    assert [s.texte for s in plus_strict.sous_titres if s.ajuste] == ["a vraiment changé"]
    assert all(s.dernier_mot - s.premier_mot <= 4 for s in plus_strict.sous_titres)


def test_texte_de_la_question_avant_un_reglage():
    assert texte_reglage_qui_defait([(4, "Mais ce Sérum\nGlowzy a", (Refus(CARACTERES, 22, 20),))]) == (
        "Ce réglage défait ton ajustement du sous-titre 4 (« Mais ce Sérum Glowzy a ») : 22 caractères, pour 20 au plus."
    )
    texte = texte_reglage_qui_defait(
        [(4, "Mais ce", (Refus(CARACTERES, 22, 20),)), (6, "peau", (Refus(MOTS, 6, 5), Refus(CARACTERES, 30, 24)))]
    )
    assert texte.splitlines() == [
        "Ce réglage défait tes ajustements de 2 sous-titres :",
        "• sous-titre 4 (« Mais ce ») : 22 caractères, pour 20 au plus.",
        "• sous-titre 6 (« peau ») : 6 mots, pour 5 au plus ; 30 caractères, pour 24 au plus.",
    ]
    assert "—" not in texte and "–" not in texte


def test_texte_quand_des_mots_corriges_defont_un_ajustement():
    defait = Defait(Ajustement(0, 1), (Refus(CARACTERES, 26, 24),), "Mais ce Sérum Glowzy a", 5)
    assert texte_ajustements_defaits([(4, defait)]) == (
        "Des mots ont changé dans le module Transcription : ton ajustement du sous-titre 4 (« Mais ce Sérum "
        "Glowzy a ») ne tient plus (26 caractères, pour 24 au plus). Il revient au découpage automatique."
    )
    vide = Defait(Ajustement(2, 3), (Refus(SANS_MOT),))
    lignes = texte_ajustements_defaits([(4, defait), (0, vide)]).splitlines()
    assert lignes[0].endswith("ces ajustements ne tiennent plus et reviennent au découpage automatique.")
    assert lignes[2] == "• un sous-titre ajusté n'a plus aucun mot affiché."


# --- Les ajustements suivent les mots corrigés dans le module Transcription ----------------------


def _deux_ajustements():
    """« Mais » | « ce sérum » ajustés à la main."""
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    _decoupage, resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 1)
    return mots, resultat.ajustements


def test_mots_fusionnes_dans_un_ajustement():
    mots, ajustements = _deux_ajustements()
    fusionner(mots, 1)  # « ce » + « sérum »
    decoupage, _reglages = _calculer(mots, ajustements)
    assert _textes(decoupage)[:2] == ["Mais", "ce sérum"] and not decoupage.defaits
    assert decoupage.sous_titres[1].ajuste and decoupage.sous_titres[1].dernier_mot - decoupage.sous_titres[1].premier_mot == 1


def test_mot_coupe_dans_un_ajustement():
    mots, ajustements = _deux_ajustements()
    corriger(mots, 2, "sérumGlowzy")
    couper(mots, 2, 5)  # « sérum » | « Glowzy » : les deux moitiés restent dans le sous-titre ajusté
    decoupage, _reglages = _calculer(mots, ajustements)
    assert _textes(decoupage)[1] == "ce sérum Glowzy" and decoupage.sous_titres[1].ajuste


def test_mot_supprime_dans_un_ajustement():
    mots, ajustements = _deux_ajustements()
    supprimer(mots, 1)  # « ce »
    decoupage, _reglages = _calculer(mots, ajustements)
    assert _textes(decoupage)[:2] == ["Mais", "sérum"] and decoupage.sous_titres[1].ajuste
    supprimer(mots, 0)  # « Mais » : son ajustement n'a plus de mot
    decoupage, _reglages = _calculer(mots, ajustements)
    (defait,) = decoupage.defaits
    assert defait.refus == (Refus(SANS_MOT),) and defait.texte == "" and defait.premier_mot == -1


def test_mot_corrige_trop_long_defait_l_ajustement():
    mots, ajustements = _deux_ajustements()
    corriger(mots, 1, "c" * 40)  # « Mais » | « ccc…c sérum » : 46 caractères, pour 40 au plus
    decoupage, _reglages = _calculer(mots, ajustements)
    (defait,) = decoupage.defaits
    assert defait.refus == (Refus(CARACTERES, 46, 40),) and defait.premier_mot == 1
    assert decoupage.sous_titres[0].ajuste  # « Mais » tient toujours
    assert not any(s.ajuste for s in decoupage.sous_titres[1:])


def test_hesitations_affichees_ou_masquees():
    mots = [Mot("Alors", 0.0, 0.3), Mot("euh", 0.35, 0.6), Mot("voilà", 0.65, 0.9), Mot("le", 0.95, 1.0), Mot("sérum", 1.05, 1.4)]
    alors_voila = Ajustement(0.0, 0.9)  # « Alors voilà », ajusté pendant que « euh » était masqué

    def calculer(mots_max, masquer, ajustements):
        reglages = ReglagesSousTitres(caracteres_max=40, mots_max=mots_max)
        return calculer_sous_titres(mots, reglages, "fr-FR", ECRAN_TEST, mesure, ["euh"], masquer, None, ajustements)

    assert _textes(calculer(3, True, [alors_voila]))[0] == "Alors voilà"
    # « euh » réaffiché : il tombe dans le moment de l'ajustement, qui le prend s'il reste dans les règles…
    assert _textes(calculer(3, False, [alors_voila]))[0] == "Alors euh voilà"
    # … sinon, l'ajustement est défait.
    (defait,) = calculer(2, False, [alors_voila]).defaits
    assert defait.refus == (Refus(MOTS, 3, 2),) and defait.texte == "Alors euh voilà"
    # Entre deux sous-titres ajustés, « euh » ne rejoint aucun des deux : il s'affiche seul.
    avec_euh = calculer(2, False, [Ajustement(0.0, 0.3), Ajustement(0.65, 0.9)])
    assert _textes(avec_euh)[:3] == ["Alors", "euh", "voilà"] and not avec_euh.defaits


def test_mots_au_meme_moment_impossibles_a_separer():
    mots = [Mot("Un", 0.0, 0.2), Mot("deux", 0.3, 0.3), Mot("trois", 0.3, 0.3), Mot("quatre", 0.4, 0.6)]
    decoupage, reglages = _calculer(mots, mots_max=4)
    assert _textes(decoupage) == ["Un deux trois quatre"]
    resultat = couper_avant(decoupage, 0, 2, reglages, ECRAN_TEST, mesure)
    assert not resultat.possible and resultat.refus[0].regle == CHEVAUCHEMENT
    assert "« deux » et « trois » ont le même moment" in resultat.message
    assert couper_avant(decoupage, 0, 1, reglages, ECRAN_TEST, mesure).possible  # ailleurs, ça marche


def test_mots_qui_se_chevauchent_un_peu():
    """Temps de la transcription qui se recouvrent : la borne passe entre les deux mots."""
    mots = [Mot("Un", 0.0, 0.5), Mot("deux", 0.3, 0.6), Mot("trois", 0.62, 0.9)]
    decoupage, reglages = _calculer(mots)
    resultat = couper_avant(decoupage, 0, 1, reglages, ECRAN_TEST, mesure)
    assert resultat.possible
    apres, _reglages = _calculer(mots, resultat.ajustements)
    assert _textes(apres) == ["Un", "deux trois"]


def test_retablir():
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    decoupage, _resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 1)
    un = retablir_automatique(decoupage, 1)
    assert len(un.ajustements) == 1 and un.choisi == 1
    apres, _reglages = _calculer(mots, un.ajustements)
    assert _textes(apres)[0] == "Mais" and apres.sous_titres[0].ajuste and not apres.sous_titres[1].ajuste
    assert retablir_automatique(decoupage).ajustements == ()
    with pytest.raises(ValueError):
        retablir_automatique(decoupage, 99)


def test_actions_impossibles_aux_bords():
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    with pytest.raises(ValueError):
        monter_premier_mot(decoupage, 0, reglages, ECRAN_TEST, mesure)
    with pytest.raises(ValueError):
        descendre_dernier_mot(decoupage, 3, reglages, ECRAN_TEST, mesure)
    with pytest.raises(ValueError):
        fusionner_avec_le_suivant(decoupage, 3, reglages, ECRAN_TEST, mesure)
    with pytest.raises(ValueError):
        couper_avant(decoupage, 0, 0, reglages, ECRAN_TEST, mesure)  # avant le premier mot : rien à couper


def test_srt_reprend_la_liste_affichee():
    mots = _pub()
    decoupage, reglages = _calculer(mots)
    decoupage, _resultat = _appliquer(couper_avant, mots, decoupage, reglages, 0, 1)
    texte = srt(decoupage.sous_titres)
    assert texte.startswith("1\r\n00:00:00,000 --> ") and "\r\nMais\r\n\r\n2\r\n" in texte
    assert texte.count(" --> ") == len(decoupage.sous_titres) == 5


# --- Enregistrés dans le projet ------------------------------------------------------------------


def test_ajustements_enregistres_avec_la_transcription():
    transcription = Transcription(mots=_pub(), ajustements_sous_titres=[[0.0, 0.3], [0.35, 0.9]])
    relue = Transcription.depuis_dict(transcription.en_dict())
    assert relue.ajustements_sous_titres == [[0.0, 0.3], [0.35, 0.9]]
    # Projet de la v1.0 : pas d'ajustement. Valeurs illisibles : ignorées.
    assert Transcription.depuis_dict({"mots": []}).ajustements_sous_titres == []
    brut = {"ajustements_sous_titres": [[1, 2], ["a", 2], [3, 1], [True, 2], [1, 2, 3], "x", [0.5, float("inf")]]}
    assert Transcription.depuis_dict(brut).ajustements_sous_titres == [[1.0, 2.0]]
    assert Transcription.depuis_dict({"ajustements_sous_titres": "rien"}).ajustements_sous_titres == []


# --- Frise (V2, lot 7) : le bord commun de deux sous-titres, glissé de mot en mot ---------------


def test_deplacer_la_limite_entre_deux_sous_titres():
    from ugc_studio.sous_titres import deplacer_la_limite

    mots = _pub()
    decoupage, reglages = _calculer(mots, mots_max=5)
    assert _textes(decoupage) == ["Mais ce sérum Glowzy", "a vraiment changé ma", "peau en deux semaines !"]
    # Vers la gauche : « Glowzy » passe au sous-titre 2 (celui qui reçoit des mots est choisi ensuite).
    nouveau, resultat = _appliquer(deplacer_la_limite, mots, decoupage, reglages, 0, 3, mots_max=5)
    assert _textes(nouveau)[:2] == ["Mais ce sérum", "Glowzy a vraiment changé ma"] and resultat.choisi == 1
    assert [s.ajuste for s in nouveau.sous_titres][:2] == [True, True]
    # Vers la droite : « a » passe au sous-titre 1.
    nouveau, resultat = _appliquer(deplacer_la_limite, mots, decoupage, reglages, 0, 5, mots_max=5)
    assert _textes(nouveau)[:2] == ["Mais ce sérum Glowzy a", "vraiment changé ma"] and resultat.choisi == 0
    # Le moment des mots ne change jamais.
    assert [(m.debut, m.fin) for m in nouveau.mots] == [(m.debut, m.fin) for m in decoupage.mots]


def test_deplacer_la_limite_respecte_les_regles():
    from ugc_studio.sous_titres import deplacer_la_limite

    mots = _pub()
    decoupage, reglages = _calculer(mots, mots_max=5)
    refus = deplacer_la_limite(decoupage, 0, 2, reglages, ECRAN_TEST, mesure)  # 6 mots dans le sous-titre 2
    assert not refus.possible and refus.refus[0].regle == MOTS
    assert "sous-titre 2" in refus.message and "Mots au plus" in refus.message
    with pytest.raises(ValueError):
        deplacer_la_limite(decoupage, 0, 0, reglages, ECRAN_TEST, mesure)  # le sous-titre 1 resterait vide
    with pytest.raises(ValueError):
        deplacer_la_limite(decoupage, 2, 12, reglages, ECRAN_TEST, mesure)  # pas de sous-titre après le dernier
