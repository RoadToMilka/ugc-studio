"""Doublons (V4.3) : les paires à montrer, leur note et le seuil (sans interface)."""

import numpy as np

from ugc_studio.doublons.paires import (
    DANS_CHAQUE_DOSSIER,
    ENTRE_LES_DOSSIERS,
    IDENTIQUES,
    LES_DEUX,
    MEME_PHOTO,
    PLAFOND_ESTIME,
    RESSEMBLANTES,
    SEUIL_DE_DEPART,
    Paire,
    ToutesLesPaires,
    note_de_l_ia,
    paires_permises,
)


def test_note_de_l_ia_suit_la_table_et_reste_sous_95():
    assert note_de_l_ia(0.50) == 50
    assert note_de_l_ia(0.75) == 70
    assert note_de_l_ia(0.87) == 84
    assert note_de_l_ia(0.95) == 94
    assert note_de_l_ia(0.999) == PLAFOND_ESTIME == 94  # sans preuve, jamais dans les zones du haut
    assert note_de_l_ia(1.0) == 94
    assert note_de_l_ia(0.2) == 20
    assert note_de_l_ia(-0.3) == 0
    notes = [note_de_l_ia(c) for c in np.linspace(-1, 1, 401)]
    assert notes == sorted(notes)  # plus proches pour l'IA, jamais moins bien notées


def test_reglage_sur_le_lot_de_l_utilisateur():
    # La paire de photos différentes la plus proche du lot (0,867) reste sous le seuil de départ ;
    # une photo déclinée typique (0,95 et plus) passe au-dessus.
    assert note_de_l_ia(0.867) < SEUIL_DE_DEPART <= note_de_l_ia(0.90)


def test_paires_permises_selon_comparer():
    dossiers = [0, 0, 1, 1]
    dans = paires_permises(dossiers, DANS_CHAQUE_DOSSIER)
    entre = paires_permises(dossiers, ENTRE_LES_DOSSIERS)
    tout = paires_permises(dossiers, LES_DEUX)
    assert dans[0, 1] and dans[2, 3] and not dans[0, 2]
    assert entre[0, 2] and entre[1, 3] and not entre[0, 1]
    assert tout[0, 1] and tout[0, 2] and not tout.diagonal().any()
    assert not dans.diagonal().any() and not entre.diagonal().any()


def test_un_seul_dossier_toutes_les_paires():
    assert paires_permises([0, 0, 0], DANS_CHAQUE_DOSSIER).sum() == 6
    assert paires_permises([0, 0, 0], LES_DEUX).sum() == 6


def test_ordre_seuil_et_nombre():
    prouvees = [Paire(0, 1, 97, MEME_PHOTO), Paire(2, 3, 100, IDENTIQUES), Paire(4, 5, 99, MEME_PHOTO)]
    ia_a, ia_b = np.array([0, 1, 2, 3]), np.array([2, 3, 4, 5])
    cosinus = np.array([0.95, 0.80, 0.97, 0.40])  # notes : 94, 76, 94, sous 50 (jamais gardée)
    toutes = ToutesLesPaires(prouvees, ia_a, ia_b, cosinus)
    assert len(toutes) == 6
    selection = toutes.au_dessus(50)
    assert [(p.a, p.b, p.proximite) for p in selection.paires] == [(2, 3, 100), (4, 5, 99), (0, 1, 97), (2, 4, 94), (0, 2, 94), (1, 3, 76)]
    assert selection.paires[3].genre == RESSEMBLANTES and selection.paires[3].ia == np.float32(0.97)
    assert toutes.au_dessus(95).total == 3
    assert toutes.au_dessus(94).total == 5
    assert toutes.au_dessus(100).paires == [Paire(2, 3, 100, IDENTIQUES)]
    assert toutes.au_dessus(50).compte(MEME_PHOTO) == 2


def test_au_dela_du_maximum_les_plus_proches_seulement():
    n = 300
    ia_a = np.arange(n)
    ia_b = ia_a + 1
    cosinus = np.linspace(0.6, 0.99, n)
    toutes = ToutesLesPaires([Paire(900, 901, 100, IDENTIQUES)], ia_a, ia_b, cosinus)
    selection = toutes.au_dessus(50, maximum=10)
    assert selection.total == n + 1 and selection.tronquee
    assert len(selection.paires) == 10
    assert selection.paires[0].genre == IDENTIQUES
    assert [p.a for p in selection.paires[1:4]] == [n - 1, n - 2, n - 3]


def test_aucune_paire():
    selection = ToutesLesPaires([]).au_dessus(50)
    assert selection.paires == [] and selection.total == 0 and not selection.tronquee
