"""Emplacements des fichiers (§10)."""

from ugc_studio import chemins


def test_dossier_donnees_force_pour_les_tests(dossier_donnees_temporaire):
    assert chemins.dossier_donnees() == dossier_donnees_temporaire
    assert dossier_donnees_temporaire.is_dir()


def test_journal_dans_le_dossier_de_donnees(dossier_donnees_temporaire):
    assert chemins.fichier_journal().parent == dossier_donnees_temporaire / "journal"


def test_ressources_embarquees_presentes():
    ressources = chemins.dossier_ressources()
    assert (ressources / "app.png").is_file()
    assert (ressources / "app.ico").is_file()
    assert len(list((ressources / "polices").glob("Inter-*.ttf"))) == 4
    for nom in ("mic", "audio-lines", "captions", "settings", "chevron-down", "check"):
        assert (ressources / "icones" / f"{nom}.svg").is_file(), nom
