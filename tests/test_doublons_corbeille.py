"""Doublons (V4.5, lot 3) : la corbeille. La fausse corbeille partout (le même code pour « Annuler »),
et, sous Windows (la fabrication sur GitHub), la vraie corbeille de Windows."""

import os
import struct
import sys
import threading
import time
import warnings
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
    assert raison(corbeille._signe(0x8027_0027)) == "elle est ouverte dans un autre programme"  # relevé par la fabrication
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
    assert not corbeille.corbeille_possible(en_reseau)  # un dossier réseau : vu avant d'appeler Windows
    with pytest.raises(PasDeCorbeille):
        mettre_a_la_corbeille(en_reseau)
    assert photo.exists() and photo.read_bytes() == b"\xff\xd8 une photo \xff\xd9"
    # Sans cette vérification, le suivi arrête Windows juste avant la suppression (ou Windows demande
    # lui-même, et la réponse « Non » la garde) : jamais supprimée pour de bon sans question.
    with _repondre_non_a_windows() as questions:
        with pytest.raises((PasDeCorbeille, corbeille.Gardee, ErreurDeCorbeille)) as arret:
            corbeille._jeter_avec_windows(en_reseau)
    assert photo.exists()
    warnings.warn(f"Dossier réseau, sans la vérification de l'app : {type(arret.value).__name__}, questions de Windows : {questions}", stacklevel=1)


@sous_windows
def test_une_photo_lue_ailleurs_un_instant_part_quand_meme(tmp_path, monkeypatch):
    """Une photo qu'un autre programme lit à ce moment-là (une vignette de l'app, un antivirus) : Windows
    ne peut pas la déplacer tout de suite ; l'app réessaie un peu plus tard."""
    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    photo = _photo(tmp_path / "Lue")
    fichier = open(photo, "rb")  # noqa: SIM115 : Python l'ouvre sans permettre qu'on la déplace
    threading.Timer(0.5, fichier.close).start()
    jetee = mettre_a_la_corbeille(photo)
    assert jetee.recyclee and not photo.exists()
    ressortir(jetee)
    assert photo.exists()


@sous_windows
def test_une_photo_tenue_par_un_autre_programme(tmp_path, monkeypatch):
    """Tenue tout du long : rien n'est supprimé, et la raison est dite en français."""
    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    photo = _photo(tmp_path / "Tenue")
    with open(photo, "rb"):
        with pytest.raises(ErreurDeCorbeille) as erreur:
            mettre_a_la_corbeille(photo)
    assert photo.exists()
    assert str(erreur.value) == "elle est ouverte dans un autre programme"


def _repondre_non_a_windows():
    """Pendant le bloc, répond « Non » à toute question que Windows poserait dans une fenêtre de ce
    programme (« Voulez-vous supprimer définitivement ce fichier ? ») ; la liste des questions vues (leur
    titre) est rendue, pour le rapport."""
    import contextlib
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")
    rappel_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [rappel_t, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    WM_COMMAND, IDNO = 0x0111, 7
    questions: list[str] = []
    fin = threading.Event()

    def guetter() -> None:
        repondues: set[int] = set()
        while not fin.is_set():
            trouvees = []

            def rappel(hwnd, _parametre):
                processus = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(processus))
                if processus.value == os.getpid() and user32.IsWindowVisible(hwnd):
                    classe = ctypes.create_unicode_buffer(64)
                    user32.GetClassNameW(hwnd, classe, 64)
                    if classe.value == "#32770":
                        trouvees.append(hwnd)
                return True

            user32.EnumWindows(rappel_t(rappel), 0)
            for hwnd in trouvees:
                if hwnd not in repondues:
                    titre = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, titre, 256)
                    questions.append(titre.value)
                    repondues.add(hwnd)
                user32.PostMessageW(hwnd, WM_COMMAND, IDNO, 0)
            fin.wait(0.1)

    @contextlib.contextmanager
    def bloc():
        fil = threading.Thread(target=guetter, daemon=True)
        fil.start()
        try:
            yield questions
        finally:
            fin.set()
            fil.join(5)

    return bloc()


def _reglage_de_la_corbeille(chemin: Path, nom: str, valeur: int):
    """Change un réglage de la corbeille du disque de `chemin` (HKCU\\…\\BitBucket\\Volume\\{…}) le temps
    d'un test, puis le remet comme avant. None si le disque n'a pas d'identifiant de volume."""
    import contextlib
    import ctypes
    import winreg

    tampon = ctypes.create_unicode_buffer(64)
    racine = os.path.splitdrive(str(chemin))[0] + "\\"
    if not ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(racine, tampon, len(tampon)):
        return None
    volume = tampon.value[tampon.value.index("{") : tampon.value.index("}") + 1]
    cle = rf"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\{volume}"

    @contextlib.contextmanager
    def reglage():
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, cle, 0, winreg.KEY_READ | winreg.KEY_WRITE) as ouverte:
            try:
                avant = winreg.QueryValueEx(ouverte, nom)
            except OSError:
                avant = None
            winreg.SetValueEx(ouverte, nom, 0, winreg.REG_DWORD, valeur)
            try:
                yield
            finally:
                if avant is None:
                    winreg.DeleteValue(ouverte, nom)
                else:
                    winreg.SetValueEx(ouverte, nom, 0, avant[1], avant[0])

    return reglage()


@sous_windows
@pytest.mark.parametrize(("nom", "valeur", "octets"), [("NukeOnDelete", 1, 4096), ("MaxCapacity", 1, 3 * 1024 * 1024)])
def test_jamais_supprimee_pour_de_bon_quand_la_corbeille_la_refuse(tmp_path, monkeypatch, nom, valeur, octets):
    """La corbeille réglée pour tout supprimer (NukeOnDelete), ou une photo plus grande que la corbeille
    (MaxCapacity, en Mo) : Windows la supprimerait pour de bon. L'app le voit avant de l'appeler (ses
    réglages) : PasDeCorbeille, rien n'est supprimé. Puis, sans cette vérification : le suivi arrête
    Windows, ou Windows demande lui-même (FOF_WANTNUKEWARNING), et la réponse « Non » garde la photo ;
    sans FOF_WANTNUKEWARNING, la fabrication a vu Windows supprimer pour de bon une photo trop grande.
    Ce qui ne doit jamais arriver : la photo partie sans être dans la corbeille."""
    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    reglage = _reglage_de_la_corbeille(tmp_path, nom, valeur)
    if reglage is None:
        pytest.skip("ce disque n'a pas d'identifiant de volume")
    photo = _photo(tmp_path / nom, octets=os.urandom(octets))
    with reglage:
        assert not corbeille.corbeille_possible(photo)
        with pytest.raises(PasDeCorbeille):
            mettre_a_la_corbeille(photo)
        assert photo.exists()
        with _repondre_non_a_windows() as questions:
            try:
                jetee = corbeille._jeter_avec_windows(photo)
            except (PasDeCorbeille, corbeille.Gardee, ErreurDeCorbeille) as arret:
                issue = f"{type(arret).__name__} {arret}"
                jetee = None
    if jetee is None:
        assert photo.exists()  # rien n'a été supprimé
    else:
        # Windows a pris la photo dans la corbeille (son réglage pas encore relu) : rien de perdu.
        issue = "dans la corbeille"
        assert jetee.recyclee and jetee.dans_la_corbeille is not None and jetee.dans_la_corbeille.exists(), jetee
        ressortir(jetee)
    warnings.warn(f"{nom}, sans la vérification de l'app : {issue}, questions de Windows : {questions}", stacklevel=1)


def test_la_meme_place_ecrite_autrement(tmp_path):
    """La fiche de la corbeille et l'app peuvent écrire un même dossier de deux façons (relevé par la
    fabrication : le nom court « RUNNER~1 » du dossier temporaire de Windows, « runneradmin » dans la
    fiche). Le dossier est comparé par le système lui-même ; le nom de la photo, lui, doit être le même."""
    dossier = tmp_path / "Lot"
    dossier.mkdir()
    photo = dossier / "Photo.jpg"
    assert corbeille.meme_place(str(photo), photo)
    assert not corbeille.meme_place(str(dossier / "Autre.jpg"), photo)
    assert not corbeille.meme_place(str(tmp_path / "Ailleurs" / "Photo.jpg"), photo)
    if sys.platform != "win32":
        lien = tmp_path / "Lien vers le lot"
        lien.symlink_to(dossier, target_is_directory=True)
        assert corbeille.meme_place(str(lien / "Photo.jpg"), photo)


@sous_windows
def test_annuler_avec_le_nom_court_d_un_dossier(tmp_path, monkeypatch):
    """La photo désignée par le nom court de son dossier (comme dans le dossier temporaire de Windows) :
    la corbeille note le nom long ; « Annuler » la remet quand même."""
    import ctypes

    monkeypatch.delenv(corbeille.VARIABLE_FAUSSE_CORBEILLE)
    dossier = tmp_path / "Un dossier au nom vraiment long"
    photo = _photo(dossier)
    tampon = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(dossier), tampon, len(tampon)) or tampon.value == str(dossier):
        pytest.skip("pas de noms courts sur ce disque")
    courte = Path(tampon.value) / photo.name
    assert courte.exists() and str(courte) != str(photo)
    depuis = time.time()
    jetee = mettre_a_la_corbeille(courte)
    assert jetee.recyclee and not photo.exists()
    assert corbeille.chercher_dans_la_corbeille(courte, depuis) == jetee.dans_la_corbeille
    ressortir(jetee)
    assert photo.exists()


class _SuiviFactice:
    def __init__(self, supprimee=False, recyclee=False, dans_la_corbeille=None, code_de_suppression=None, vers_la_corbeille=True):
        self.refusee = False
        self.supprimee, self.recyclee, self.dans_la_corbeille = supprimee, recyclee, dans_la_corbeille
        self.code_de_suppression, self.vers_la_corbeille = code_de_suppression, vers_la_corbeille


def test_ce_qui_s_est_passe_d_apres_le_disque(tmp_path):
    """Ce que l'opération de Windows a fait se lit d'abord sur le disque : la photo est-elle encore là ?"""
    photo = _photo(tmp_path)
    passe = corbeille._ce_qui_s_est_passe
    # Encore là : « Non » à la question de Windows (trois façons de le dire), ou une erreur.
    for code in (0x8027_0000, 0x8007_04C7, 0x0027_0005):
        with pytest.raises(corbeille.Gardee):
            passe(photo, _SuiviFactice(code_de_suppression=corbeille._signe(code)), 0, 0)
    with pytest.raises(ErreurDeCorbeille, match="ouverte dans un autre programme"):
        passe(photo, _SuiviFactice(code_de_suppression=corbeille._signe(0x8027_0027)), 0, 0)
    with pytest.raises(ErreurDeCorbeille, match="ne l'a pas déplacée"):
        passe(photo, _SuiviFactice(), 0, 0)
    # Partie : dans la corbeille (où Windows l'a dit), supprimée sur « Oui » à sa question, ou annoncée.
    dedans = tmp_path / "$RABCDEF.jpg"
    photo.rename(dedans)
    assert passe(photo, _SuiviFactice(supprimee=True, recyclee=True, dans_la_corbeille=str(dedans)), 0, 0) == Jetee(photo, True, dedans)
    assert passe(photo, _SuiviFactice(supprimee=True, recyclee=False), 0, 0) == Jetee(photo, False)
    assert passe(photo, _SuiviFactice(), 0, 0) == Jetee(photo, True, None)
