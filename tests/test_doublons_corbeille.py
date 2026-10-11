"""Doublons (V4.5, lot 3) : la corbeille. La fausse corbeille partout (le même code pour « Annuler »),
et, sous Windows (la fabrication sur GitHub), la vraie corbeille de Windows."""

import os
import struct
import sys
import time
from pathlib import Path

import pytest

from ugc_studio.doublons import corbeille
from ugc_studio.doublons.corbeille import (
    ErreurDeCorbeille,
    ImpossibleDeRessortir,
    Jetee,
    PasDeCorbeille,
    ecrire_l_origine,
    fiche_de_la_corbeille,
    lire_l_origine,
    mettre_a_la_corbeille,
    raison,
    ressortir,
    supprimer_definitivement,
)

sous_windows = pytest.mark.skipif(sys.platform != "win32", reason="la vraie corbeille : sous Windows seulement")


def _photo(dossier: Path, nom: str = "Photo été 01.jpg", octets: bytes = b"\xff\xd8 une photo \xff\xd9") -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    chemin.write_bytes(octets)
    os.utime(chemin, (1_700_000_000, 1_700_000_000))
    return chemin


# --- La fausse corbeille (tous les tests de l'app l'utilisent : conftest.py) -------------------------------


def test_mise_a_la_corbeille_puis_remise_a_sa_place(tmp_path, fausse_corbeille):
    photo = _photo(tmp_path / "Lot 1")
    jetee = mettre_a_la_corbeille(photo)
    assert not photo.exists()
    assert jetee.origine == photo and jetee.recyclee
    assert jetee.dans_la_corbeille.parent == fausse_corbeille and jetee.dans_la_corbeille.name.startswith("$R")
    assert jetee.dans_la_corbeille.suffix == ".jpg"
    fiche = fiche_de_la_corbeille(jetee.dans_la_corbeille)
    assert fiche.name == "$I" + jetee.dans_la_corbeille.name[2:]
    assert lire_l_origine(fiche) == str(photo)
    ressortir(jetee)
    assert photo.read_bytes() == b"\xff\xd8 une photo \xff\xd9"
    assert photo.stat().st_mtime == 1_700_000_000  # la même photo, intacte, avec sa date
    assert not jetee.dans_la_corbeille.exists() and not fiche.exists()


def test_ressortir_seulement_sans_risque(tmp_path):
    photo = _photo(tmp_path / "Lot 1")
    jetee = mettre_a_la_corbeille(photo)
    # Un autre fichier est arrivé à sa place : il n'est jamais remplacé.
    photo.write_bytes(b"autre")
    with pytest.raises(ImpossibleDeRessortir, match="déjà à sa place"):
        ressortir(jetee)
    assert photo.read_bytes() == b"autre" and jetee.dans_la_corbeille.exists()
    photo.unlink()
    # La fiche de la corbeille dit un autre chemin : rien n'est déplacé.
    fiche = fiche_de_la_corbeille(jetee.dans_la_corbeille)
    ecrire_l_origine(fiche, tmp_path / "ailleurs.jpg", 10, 1_700_000_000)
    with pytest.raises(ImpossibleDeRessortir, match="ne confirme pas"):
        ressortir(jetee)
    assert jetee.dans_la_corbeille.exists() and not photo.exists()
    # Sans fiche : pareil.
    fiche.unlink()
    with pytest.raises(ImpossibleDeRessortir, match="ne confirme pas"):
        ressortir(jetee)
    # Son dossier n'existe plus.
    ecrire_l_origine(fiche, photo, 10, 1_700_000_000)
    (tmp_path / "Lot 1").rmdir()
    with pytest.raises(ImpossibleDeRessortir, match="dossier n'existe plus"):
        ressortir(jetee)
    (tmp_path / "Lot 1").mkdir()
    ressortir(jetee)
    assert photo.exists()
    # Déjà revenue (remise à sa place depuis la corbeille de Windows) ; ou la corbeille a été vidée.
    with pytest.raises(corbeille.DejaRevenue, match="déjà revenue"):
        ressortir(jetee)
    photo.unlink()
    with pytest.raises(ImpossibleDeRessortir, match="plus dans la corbeille"):
        ressortir(jetee)


def test_rien_a_ressortir_d_une_suppression_definitive(tmp_path):
    photo = _photo(tmp_path)
    jetee = supprimer_definitivement(photo)
    assert not photo.exists() and jetee == Jetee(photo, False)
    with pytest.raises(ImpossibleDeRessortir, match="définitivement"):
        ressortir(jetee)
    with pytest.raises(ImpossibleDeRessortir, match="pas dit où"):
        ressortir(Jetee(photo, True, None))


def test_une_photo_disparue_n_est_pas_mise_a_la_corbeille(tmp_path):
    with pytest.raises(ErreurDeCorbeille, match="n'existe plus"):
        mettre_a_la_corbeille(tmp_path / "absente.jpg")


def test_les_fiches_de_la_corbeille_de_windows(tmp_path):
    """Les deux formats des fiches « $I… » : version 1 (Windows Vista à 8.1, chemin sur 520 octets) et
    version 2 (Windows 10 et 11, longueur puis chemin)."""
    chemin = r"C:\Users\Moi\Photos\Lot 1\Photo été 01.jpg"
    version_1 = struct.pack("<qqq", 1, 1234, 133_000_000_000_000_000) + (chemin + "\0").encode("utf-16-le").ljust(520, b"\0")
    (tmp_path / "$I1").write_bytes(version_1)
    assert lire_l_origine(tmp_path / "$I1") == chemin
    ecrire_l_origine(tmp_path / "$I2", Path(chemin), 1234, 1_700_000_000)
    donnees = (tmp_path / "$I2").read_bytes()
    assert struct.unpack_from("<qqqi", donnees) == (2, 1234, 133_444_736_000_000_000, len(chemin) + 1)
    assert lire_l_origine(tmp_path / "$I2") == chemin
    for abimee in (b"", b"\x02" + b"\0" * 30, struct.pack("<qqqi", 2, 1, 1, 4000) + b"a\0", struct.pack("<qqq", 7, 1, 1) + b"x\0" * 4):
        (tmp_path / "$I3").write_bytes(abimee)
        assert lire_l_origine(tmp_path / "$I3") is None
    assert lire_l_origine(tmp_path / "absente") is None


def test_les_raisons_en_francais():
    assert raison(corbeille._signe(0x8007_0020)) == "elle est ouverte dans un autre programme"
    assert raison(0x8007_0005) == "Windows en refuse l'accès (photo protégée ?)"
    assert raison(corbeille._signe(0x8000_FFFF)) == "erreur de Windows 0x8000FFFF"
    assert corbeille.E_ABORT == -2147467260  # 0x80004004, tel que ctypes le rend à Windows


def test_l_emplacement_a_ouvrir(fausse_corbeille, monkeypatch):
    assert corbeille.emplacement_de_la_corbeille() == str(fausse_corbeille)
    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    attendu = corbeille.OUVRIR_LA_CORBEILLE if sys.platform == "win32" else str(Path(corbeille.tempfile.gettempdir()) / corbeille.NOM_DE_LA_FAUSSE_CORBEILLE)
    assert corbeille.emplacement_de_la_corbeille() == attendu


# --- La vraie corbeille de Windows (sur la machine Windows de la fabrication) -----------------------------


@sous_windows
def test_la_vraie_corbeille_de_windows(tmp_path, monkeypatch):
    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    photo = _photo(tmp_path / "Lot à trier", octets=os.urandom(4096))
    contenu = photo.read_bytes()
    depuis = time.time()
    jetee = mettre_a_la_corbeille(photo)
    print("Dans la corbeille :", jetee)
    assert not photo.exists()
    assert jetee.recyclee, "supprimée pour de bon : elle devait aller dans la corbeille"
    assert jetee.dans_la_corbeille is not None and jetee.dans_la_corbeille.exists()
    assert jetee.dans_la_corbeille.parent.parent.name == "$Recycle.Bin"
    assert jetee.dans_la_corbeille.read_bytes() == contenu
    assert lire_l_origine(fiche_de_la_corbeille(jetee.dans_la_corbeille)) == str(photo)
    # Windows dit lui-même où il l'a rangée ; la recherche dans la corbeille, au cas où, la retrouve aussi.
    assert corbeille.chercher_dans_la_corbeille(photo, depuis) == jetee.dans_la_corbeille
    ressortir(jetee)
    assert photo.read_bytes() == contenu and photo.stat().st_mtime == 1_700_000_000
    assert not jetee.dans_la_corbeille.exists() and not fiche_de_la_corbeille(jetee.dans_la_corbeille).exists()


@sous_windows
def test_windows_dit_quand_une_photo_a_disparu(tmp_path, monkeypatch):
    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    with pytest.raises(ErreurDeCorbeille, match="n'existe plus"):
        mettre_a_la_corbeille(tmp_path / "absente.jpg")


@sous_windows
def test_jamais_supprimee_pour_de_bon_sans_question(tmp_path, monkeypatch):
    """Un dossier réseau n'a pas de corbeille : Windows supprimerait la photo pour de bon. L'app l'apprend
    juste avant et arrête tout : la photo est toujours là (PasDeCorbeille). Le dossier réseau : le même
    dossier, vu par le partage administratif du disque (\\\\localhost\\C$\\…)."""
    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    photo = _photo(tmp_path / "Réseau")
    lecteur, reste = os.path.splitdrive(str(photo))
    en_reseau = Path(rf"\\localhost\{lecteur[0]}$" + reste)
    if not en_reseau.exists():
        pytest.skip("le partage administratif du disque n'est pas joignable sur cette machine")
    with pytest.raises(PasDeCorbeille):
        mettre_a_la_corbeille(en_reseau)
    assert photo.exists() and photo.read_bytes() == b"\xff\xd8 une photo \xff\xd9"
