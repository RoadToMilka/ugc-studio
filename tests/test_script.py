"""Script en segments (§5.2) : texte pour l'API, texte des sous-titres, balises collées."""

from ugc_studio.balises import FAMILLES, TOUTES, famille_de
from ugc_studio.script import depuis_texte, est_vide, normaliser, texte_brut, texte_pour_api


def test_liste_des_balises_du_cahier_des_charges():
    assert len(FAMILLES) == 6
    assert len(TOUTES) == 2 + 7 + 9 + 10 + 5 + 7
    assert famille_de("short pause").nom == "Pauses"
    assert famille_de("throat-clearing").identifiant == "voix"


def test_texte_colle_avec_balises():
    segments = depuis_texte("Salut ! <laugh> J'ai testé <Short Pause> ce sérum <truc> ok")
    assert segments == [
        {"texte": "Salut ! "},
        {"balise": "laugh"},
        {"texte": " J'ai testé "},
        {"balise": "short pause"},
        {"texte": " ce sérum <truc> ok"},  # balise inconnue : gardée comme texte
    ]


def test_texte_pour_l_api_et_pour_les_sous_titres():
    segments = [
        {"texte": "Ce sérum est "},
        {"texte": "incroyable", "accentue": True},
        {"texte": " ! "},
        {"balise": "laugh"},
        {"texte": " Vraiment."},
    ]
    assert texte_pour_api(segments) == "Ce sérum est INCROYABLE ! <laugh> Vraiment."
    assert texte_brut(segments) == "Ce sérum est incroyable ! Vraiment."


def test_normaliser_fusionne_et_nettoie():
    assert normaliser([{"texte": "a"}, {"texte": "b"}, {"texte": ""}, {"texte": "c", "accentue": True}]) == [
        {"texte": "ab"},
        {"texte": "c", "accentue": True},
    ]


def test_script_vide():
    assert est_vide([])
    assert est_vide([{"texte": "   "}])
    assert not est_vide([{"balise": "sigh"}])


def test_couper_une_replique_au_curseur():
    from ugc_studio.script import couper

    script = [{"texte": "Wow ! Le lien "}, {"balise": "laugh"}, {"texte": " vite", "accentue": True}]
    avant, apres = couper(script, len("Wow ! "))
    assert avant == [{"texte": "Wow !"}]  # espaces retirés à l'endroit de la coupe
    assert apres == [{"texte": "Le lien "}, {"balise": "laugh"}, {"texte": " vite", "accentue": True}]
    # Un badge compte pour un caractère.
    avant, apres = couper(script, len("Wow ! Le lien ") + 1)
    assert avant[-1] == {"balise": "laugh"} and apres == [{"texte": "vite", "accentue": True}]
    assert couper(script, 0) == ([], script)


def test_joindre_les_repliques():
    from ugc_studio.script import joindre_repliques

    assert joindre_repliques([[{"texte": "A !"}], [], [{"balise": "sigh"}, {"texte": " B"}]]) == [
        {"texte": "A ! "},
        {"balise": "sigh"},
        {"texte": " B"},
    ]
    assert joindre_repliques([]) == []
