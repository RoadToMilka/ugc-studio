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


def test_chaque_icone_utilisee_existe():
    """Chaque nom d'icône écrit dans le code (nom_icone="…", icone("…"), icone_menu("…"),
    definir_icone("…"), modules de la barre latérale) a son fichier SVG dans les ressources :
    sinon, le bouton s'afficherait sans icône."""
    import re
    from pathlib import Path

    racine = Path(chemins.__file__).parent
    motifs = (
        r'nom_icone="([a-z0-9-]+)"',
        r'\bicone(?:_menu)?\("([a-z0-9-]+)"',
        r'definir_icone\("([a-z0-9-]+)"',
        r'Module\("[^"]+", "[^"]+", "([a-z0-9-]+)"\)',
        r'fichier_icone\("([a-z0-9-]+)"',
    )
    noms = {nom for fichier in racine.rglob("*.py") for motif in motifs for nom in re.findall(motif, fichier.read_text(encoding="utf-8"))}
    assert {"scroll-text", "globe", "pen-line", "send"} <= noms
    manquants = sorted(n for n in noms if not (chemins.dossier_ressources() / "icones" / f"{n}.svg").is_file())
    assert not manquants, f"Icônes sans fichier : {manquants}"


def test_dossier_des_programmes(dossier_donnees_temporaire, monkeypatch, tmp_path):
    """FFmpeg recopié depuis le .exe (V3) : dans %LOCALAPPDATA%\\UGC Studio (pas avec les données, qui
    peuvent suivre l'utilisateur d'un ordinateur à l'autre) ; tests : avec leurs données ; autotest :
    là où il le demande, hors de son rapport."""
    monkeypatch.delenv(chemins.VARIABLE_DOSSIER_PROGRAMMES, raising=False)
    assert chemins.dossier_programmes() == dossier_donnees_temporaire / "programmes"
    monkeypatch.setenv(chemins.VARIABLE_DOSSIER_PROGRAMMES, str(tmp_path / "autotest"))
    assert chemins.dossier_programmes() == tmp_path / "autotest" and (tmp_path / "autotest").is_dir()
    monkeypatch.delenv(chemins.VARIABLE_DOSSIER_PROGRAMMES)
    monkeypatch.delenv(chemins.VARIABLE_DOSSIER_DONNEES)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(chemins.sys, "platform", "win32")
    assert chemins.dossier_programmes() == tmp_path / "Local" / "UGC Studio"
