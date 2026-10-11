"""La corbeille de Windows (V4.5, lot 3 de Doublons ; document V4.3, §3.5 et §5) : mettre une photo à
la corbeille, et l'en ressortir (« Annuler »).

**Mettre à la corbeille** : avec la fonction de Windows faite pour ça, IFileOperation (celle que
Microsoft conseille depuis Windows Vista), appelée directement (ctypes), sans bibliothèque en plus.

**Jamais de suppression définitive sans question** : juste avant de supprimer, Windows dit à l'app si
la photo ira dans la corbeille (PreDeleteItem, appelé sur le « suivi » que l'app lui donne). Si non (une
clé USB ou un dossier réseau n'ont pas de corbeille ; ou elle est réglée pour tout supprimer), l'app
arrête tout : rien n'est supprimé, et la page pose la question (PasDeCorbeille). C'est la vérification
que fait aussi Electron (le moteur de Visual Studio Code, de Slack…) pour mettre un fichier à la
corbeille.

**Ressortir** : Windows dit aussi où il a mis la photo (PostDeleteItem) : un fichier « $R… » dans le
dossier $Recycle.Bin du même disque ; à côté, un petit fichier « $I… » note d'où elle vient. L'app
vérifie que ce fichier dit bien le même chemin et que la place est libre, puis remet la photo à sa
place, comme « Restaurer » dans la corbeille de Windows : un simple déplacement sur le même disque (la
photo revient intacte, avec sa date), puis le « $I… » est retiré.

Hors de Windows (les tests, ici) et quand UGC_STUDIO_FAUSSE_CORBEILLE est posée (les tests de la page,
partout) : une fausse corbeille, un dossier qui imite celle de Windows ($R… et $I…). « Annuler » y passe
par le même code.
"""

from __future__ import annotations

import os
import secrets
import shutil
import string
import struct
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

VARIABLE_FAUSSE_CORBEILLE = "UGC_STUDIO_FAUSSE_CORBEILLE"  # un dossier : la fausse corbeille, même sous Windows
NOM_DE_LA_FAUSSE_CORBEILLE = "UGC Studio - fausse corbeille"
OUVRIR_LA_CORBEILLE = "shell:RecycleBinFolder"  # la corbeille, dans l'Explorateur de Windows

ESSAIS_POUR_RESSORTIR = 3  # l'Explorateur peut tenir le fichier un instant (aperçu de la corbeille ouverte)
PAUSE_ENTRE_LES_ESSAIS_S = 0.2
# Mettre à la corbeille : une photo que l'app (une vignette, la comparaison), un antivirus ou l'Explorateur
# lit à ce moment-là ne peut pas être déplacée ; l'opération est refaite un peu plus tard (rien n'a été
# supprimé entre-temps).
ESSAIS_POUR_JETER = 3
PAUSE_AVANT_DE_REJETER_S = 0.4


class PasDeCorbeille(Exception):
    """Windows ne peut pas mettre cette photo dans la corbeille (un disque sans corbeille, comme une clé
    USB ou un dossier réseau) : rien n'a été supprimé."""


class ErreurDeCorbeille(Exception):
    """La photo n'a pas pu être mise à la corbeille (la raison, en français : ouverte dans un autre
    programme, protégée…). Rien n'a été supprimé."""


class ImpossibleDeRessortir(Exception):
    """La photo ne peut pas être remise à sa place (la raison, en français)."""


class DejaRevenue(ImpossibleDeRessortir):
    """La photo est déjà revenue à sa place (remise depuis la corbeille de Windows, par exemple)."""


@dataclass(frozen=True)
class Jetee:
    """Une photo mise à la corbeille (ou supprimée définitivement) : son chemin, et ce que Windows en a fait.
    `dans_la_corbeille` : le fichier « $R… » où elle est maintenant ; None si on ne le sait pas (« Annuler »
    renvoie alors à la corbeille de Windows, où « Restaurer » la remet), ou si elle a été supprimée
    définitivement (`recyclee` faux : rien à annuler)."""

    origine: Path
    recyclee: bool
    dans_la_corbeille: Path | None = None


# --- Mettre à la corbeille, supprimer --------------------------------------------------------------------


def mettre_a_la_corbeille(chemin: Path) -> Jetee:
    """Met la photo dans la corbeille. Lance PasDeCorbeille (rien n'est supprimé) si Windows ne peut pas
    l'y mettre, ErreurDeCorbeille si elle n'a pas pu être déplacée."""
    chemin = Path(os.path.abspath(chemin))
    fausse = _fausse_corbeille()
    if fausse is not None:
        return Jetee(chemin, True, _jeter_dans_la_fausse(chemin, fausse))
    return _jeter_avec_windows(chemin)


def supprimer_definitivement(chemin: Path) -> Jetee:
    """Supprime la photo pour de bon (un disque sans corbeille, après la question de la page). Lance
    OSError si c'est impossible."""
    chemin = Path(os.path.abspath(chemin))
    chemin.unlink()
    return Jetee(chemin, False)


def emplacement_de_la_corbeille() -> str:
    """Ce qu'il faut ouvrir pour montrer la corbeille : celle de Windows, ou la fausse (un dossier)."""
    fausse = _fausse_corbeille()
    return OUVRIR_LA_CORBEILLE if fausse is None else str(fausse)


def _fausse_corbeille() -> Path | None:
    """Le dossier de la fausse corbeille, ou None pour la vraie (sous Windows)."""
    dossier = os.environ.get(VARIABLE_FAUSSE_CORBEILLE)
    if dossier:
        return Path(dossier)
    if sys.platform == "win32":
        return None
    return Path(tempfile.gettempdir()) / NOM_DE_LA_FAUSSE_CORBEILLE


# --- Ressortir (« Annuler ») ---------------------------------------------------------------------------


def ressortir(jetee: Jetee) -> None:
    """Remet à sa place une photo mise à la corbeille. Lance ImpossibleDeRessortir (avec la raison) si
    ce n'est pas possible sans risque : rien n'est alors déplacé."""
    origine, dedans = jetee.origine, jetee.dans_la_corbeille
    if not jetee.recyclee:
        raise ImpossibleDeRessortir("elle a été supprimée définitivement")
    if dedans is None:
        raise ImpossibleDeRessortir("Windows n'a pas dit où il l'a rangée")
    if not dedans.exists():
        if origine.exists():
            raise DejaRevenue("elle est déjà revenue à sa place")
        raise ImpossibleDeRessortir("elle n'est plus dans la corbeille (vidée entre-temps ?)")
    if origine.exists():
        raise ImpossibleDeRessortir(f"un fichier « {origine.name} » est déjà à sa place (il n'est pas remplacé)")
    if not origine.parent.is_dir():
        raise ImpossibleDeRessortir("son dossier n'existe plus")
    fiche = fiche_de_la_corbeille(dedans)
    notee = lire_l_origine(fiche)
    if notee is None or not meme_place(notee, origine):
        raise ImpossibleDeRessortir("la corbeille ne confirme pas d'où elle vient")
    for essai in range(ESSAIS_POUR_RESSORTIR):
        try:
            # Le même disque : un simple renommage, comme « Restaurer ». Sous Windows, il échoue si un
            # fichier est arrivé à sa place entre-temps (rien n'est jamais écrasé).
            os.rename(dedans, origine)
            break
        except OSError as erreur:
            if essai == ESSAIS_POUR_RESSORTIR - 1:
                raise ImpossibleDeRessortir(f"Windows refuse de la déplacer ({erreur.strerror or erreur})") from erreur
            time.sleep(PAUSE_ENTRE_LES_ESSAIS_S)
    try:
        fiche.unlink()
    except OSError:
        pass  # la photo est revenue : la fiche orpheline n'est qu'une ligne vide pour la corbeille
    _prevenir_l_explorateur(dedans, origine)


def meme_place(notee: str, chemin: Path) -> bool:
    """Vrai si le chemin noté par la corbeille désigne la même place que `chemin` : le même nom, dans le
    même dossier. Le dossier est comparé par Windows lui-même (os.path.samefile) : un même dossier
    s'écrit de plusieurs façons (le nom court « RUNNER~1 » du dossier temporaire de Windows, relevé par
    la fabrication : la corbeille note « runneradmin » ; un lien ; un lecteur substitué ; les majuscules)."""
    ecrit = Path(notee)
    if os.path.normcase(ecrit.name) != os.path.normcase(chemin.name):
        return False
    if os.path.normcase(str(ecrit.parent)) == os.path.normcase(str(chemin.parent)):
        return True
    try:
        return os.path.samefile(ecrit.parent, chemin.parent)
    except OSError:
        return False


def fiche_de_la_corbeille(dedans: Path) -> Path:
    """Le fichier « $I… » qui accompagne « $R… » dans la corbeille (même nom, à la deuxième lettre près)."""
    return dedans.with_name("$I" + dedans.name[2:])


def lire_l_origine(fiche: Path) -> str | None:
    """Le chemin d'origine noté dans un fichier « $I… » de la corbeille, ou None s'il est illisible.

    Ce format n'est pas publié par Microsoft ; il est décrit par Joachim Metz (libyal, « Windows
    Recycle.Bin file formats ») : version (8 octets : 1 depuis Windows Vista, 2 depuis Windows 10),
    taille du fichier (8), date de suppression (8) ; puis, en version 1, le chemin (UTF-16, 260
    caractères au plus) ; en version 2, son nombre de caractères (4 octets, fin comprise) et le chemin."""
    try:
        donnees = fiche.read_bytes()
    except OSError:
        return None
    if len(donnees) < 26:
        return None
    version = struct.unpack_from("<q", donnees, 0)[0]
    if version == 1:
        brut = donnees[24 : 24 + 520]
    elif version == 2 and len(donnees) >= 28:
        caracteres = struct.unpack_from("<i", donnees, 24)[0]
        if caracteres <= 0 or 28 + 2 * caracteres > len(donnees):
            return None
        brut = donnees[28 : 28 + 2 * caracteres]
    else:
        return None
    try:
        texte = brut.decode("utf-16-le")
    except UnicodeDecodeError:
        return None
    return texte.split("\0", 1)[0] or None


def ecrire_l_origine(fiche: Path, origine: Path, octets: int, quand: float) -> None:
    """Écrit une fiche « $I… » (version 2, celle de Windows 10 et 11) : pour la fausse corbeille."""
    chemin = str(origine) + "\0"
    filetime = int((quand + 11_644_473_600) * 10_000_000)  # dixièmes de microseconde depuis 1601
    fiche.write_bytes(struct.pack("<qqqi", 2, octets, filetime, len(chemin)) + chemin.encode("utf-16-le"))


def _jeter_dans_la_fausse(chemin: Path, dossier: Path) -> Path:
    """La fausse corbeille : la photo déplacée en « $R… » dans le dossier, avec sa fiche « $I… »."""
    if not chemin.is_file():
        raise ErreurDeCorbeille("elle n'existe plus à cet endroit")
    dossier.mkdir(parents=True, exist_ok=True)
    lettres = string.ascii_uppercase + string.digits
    while True:
        nom = "".join(secrets.choice(lettres) for _ in range(6)) + chemin.suffix
        dedans, fiche = dossier / f"$R{nom}", dossier / f"$I{nom}"
        if not dedans.exists() and not fiche.exists():
            break
    ecrire_l_origine(fiche, chemin, chemin.stat().st_size, time.time())
    shutil.move(chemin, dedans)
    return dedans


def chercher_dans_la_corbeille(chemin: Path, depuis: float) -> Path | None:
    """Le « $R… » de la photo mise à la corbeille depuis `depuis` (secondes, comme time.time()), cherché
    dans les fiches « $I… » de la corbeille de son disque ; None si rien ne correspond. Seulement si
    Windows ne l'a pas dit lui-même."""
    corbeille = Path(chemin.anchor) / "$Recycle.Bin"
    trouvees: list[tuple[float, Path]] = []
    try:
        dossiers = list(os.scandir(corbeille))
    except OSError:
        return None
    for dossier in dossiers:
        try:
            entrees = list(os.scandir(dossier.path))  # les dossiers des autres comptes sont refusés
        except OSError:
            continue
        for entree in entrees:
            if not entree.name.startswith("$I"):
                continue
            try:
                modifiee = entree.stat().st_mtime
            except OSError:
                continue
            if modifiee < depuis - 2:
                continue
            notee = lire_l_origine(Path(entree.path))
            dedans = Path(dossier.path) / ("$R" + entree.name[2:])
            if notee is not None and meme_place(notee, chemin) and dedans.exists():
                trouvees.append((modifiee, dedans))
    return max(trouvees)[1] if trouvees else None


# --- Windows : IFileOperation ----------------------------------------------------------------------------

# Identifiants des objets et interfaces de Windows (shobjidl_core.h ; vérifiés aussi dans les
# définitions de Wine, include/shobjidl.idl).
CLSID_FILE_OPERATION = "3ad05575-8857-4850-9277-11b85bdb8e09"
IID_IFILE_OPERATION = "947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8"
IID_ISHELL_ITEM = "43826d1e-e718-42ee-bc55-a1e261c37bfe"
IID_IFILE_OPERATION_PROGRESS_SINK = "04b0f1a7-9490-44bc-96e1-4296a31252e2"
IID_IUNKNOWN = "00000000-0000-0000-c000-000000000046"

# Place des fonctions dans la table de chaque interface (après QueryInterface, AddRef, Release).
RELEASE = 2
IFILE_OPERATION_ADVISE = 3
IFILE_OPERATION_UNADVISE = 4
IFILE_OPERATION_SET_OPERATION_FLAGS = 5
IFILE_OPERATION_DELETE_ITEM = 18
IFILE_OPERATION_PERFORM_OPERATIONS = 21
ISHELL_ITEM_GET_DISPLAY_NAME = 5

# Réglages de l'opération (IFileOperation::SetOperationFlags) : à la corbeille (FOFX_RECYCLEONDELETE,
# et FOF_ALLOWUNDO, qui garde aussi l'annulation de l'Explorateur), sans question (on peut l'en
# ressortir), sans fenêtre d'avancement ni d'erreur de Windows (la page dit ce qui se passe).
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
FOFX_RECYCLEONDELETE = 0x0008_0000
REGLAGES_DE_L_OPERATION = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOFX_RECYCLEONDELETE
# PreDeleteItem : présent si Windows va mettre la photo dans la corbeille, absent s'il va la supprimer
# pour de bon (TRANSFER_SOURCE_FLAGS).
TSF_DELETE_RECYCLE_IF_POSSIBLE = 0x80
SIGDN_FILESYSPATH = 0x8005_8000  # le chemin d'un élément (IShellItem::GetDisplayName)
COINIT_APARTMENTTHREADED = 0x2
COINIT_DISABLE_OLE1DDE = 0x4
CLSCTX_ALL = 0x17
SHCNE_RENAMEITEM = 0x1
SHCNF_PATHW = 0x5

S_OK = 0

# Les suivis déjà donnés à Windows restent en mémoire jusqu'à la fermeture de l'app (quelques Ko par
# photo mise à la corbeille) : si Windows gardait une référence au-delà de l'opération, il ne doit
# jamais appeler un objet disparu.
_SUIVIS_GARDES: list = []


def _signe(valeur: int) -> int:
    """Un code de Windows (HRESULT, 32 bits) tel que ctypes le donne : un entier signé."""
    return valeur - (1 << 32) if valeur >= 1 << 31 else valeur


E_ABORT = _signe(0x8000_4004)
E_NOINTERFACE = _signe(0x8000_4002)
E_POINTER = _signe(0x8000_4003)

RAISONS = {
    0x8007_0020: "elle est ouverte dans un autre programme",  # ERROR_SHARING_VIOLATION
    0x8007_0021: "elle est ouverte dans un autre programme",  # ERROR_LOCK_VIOLATION
    0x8007_0005: "Windows en refuse l'accès (photo protégée ?)",  # E_ACCESSDENIED
    0x8007_0002: "elle n'existe plus à cet endroit",  # ERROR_FILE_NOT_FOUND
    0x8007_0003: "son dossier n'existe plus",  # ERROR_PATH_NOT_FOUND
}


def raison(code: int) -> str:
    """La raison d'un échec de Windows (un HRESULT), en français."""
    code &= 0xFFFF_FFFF
    return RAISONS.get(code, f"erreur de Windows 0x{code:08X}")


def _jeter_avec_windows(chemin: Path) -> Jetee:
    """Met la photo à la corbeille ; si Windows ne peut pas la déplacer à ce moment-là (lue par un autre
    programme), réessaie un peu plus tard (ESSAIS_POUR_JETER fois en tout). PasDeCorbeille n'est jamais
    réessayée : la question d'abord."""
    for essai in range(ESSAIS_POUR_JETER):
        try:
            return _jeter_avec_windows_une_fois(chemin)
        except ErreurDeCorbeille:
            if essai == ESSAIS_POUR_JETER - 1 or not chemin.exists():
                raise
            time.sleep(PAUSE_AVANT_DE_REJETER_S)
    raise ErreurDeCorbeille("Windows ne l'a pas déplacée")  # jamais atteint


def _jeter_avec_windows_une_fois(chemin: Path) -> Jetee:
    """IFileOperation ne marche que dans un fil de travail « à appartement unique » (STA) : l'opération
    se fait dans un fil à elle, quel que soit celui qui la demande."""
    issue: dict[str, object] = {}

    def travail() -> None:
        try:
            issue["jetee"] = _operation_windows(chemin)
        except BaseException as erreur:  # noqa: BLE001 : rendue telle quelle à l'appelant
            issue["erreur"] = erreur

    fil = threading.Thread(target=travail, name="Corbeille de Windows", daemon=True)
    fil.start()
    fil.join()
    if "erreur" in issue:
        raise issue["erreur"]  # type: ignore[misc]
    return issue["jetee"]  # type: ignore[return-value]


def _operation_windows(chemin: Path) -> Jetee:  # Windows seulement (ses tests tournent sur GitHub)
    import ctypes
    from ctypes import wintypes

    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    def guid(texte: str):
        return ctypes.create_string_buffer(__import__("uuid").UUID(texte).bytes_le, 16)

    def appeler(objet: ctypes.c_void_p, rang: int, *arguments, types=()) -> int:
        """La fonction `rang` de la table d'un objet de Windows (COM)."""
        table = ctypes.cast(objet, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fonction = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[rang])
        return fonction(objet, *arguments)

    def chemin_de(element) -> str | None:
        nom = ctypes.c_void_p()
        code = appeler(ctypes.c_void_p(element), ISHELL_ITEM_GET_DISPLAY_NAME, SIGDN_FILESYSPATH, ctypes.byref(nom), types=(wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)))
        if code < 0 or not nom.value:
            return None
        try:
            return ctypes.wstring_at(nom.value)
        finally:
            ole32.CoTaskMemFree(nom)

    depuis = time.time()
    code = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE)
    if code < 0:
        raise ErreurDeCorbeille(raison(code))
    try:
        operation = ctypes.c_void_p()
        code = ole32.CoCreateInstance(guid(CLSID_FILE_OPERATION), None, CLSCTX_ALL, guid(IID_IFILE_OPERATION), ctypes.byref(operation))
        if code < 0 or not operation.value:
            raise ErreurDeCorbeille(raison(code))
        try:
            element = ctypes.c_void_p()
            code = shell32.SHCreateItemFromParsingName(str(chemin), None, guid(IID_ISHELL_ITEM), ctypes.byref(element))
            if code < 0 or not element.value:
                raise ErreurDeCorbeille(raison(code))
            try:
                suivi = _Suivi(chemin_de)
                _SUIVIS_GARDES.append(suivi)
                jeton = wintypes.DWORD()
                code = appeler(operation, IFILE_OPERATION_ADVISE, suivi.pointeur, ctypes.byref(jeton), types=(ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)))
                if code < 0:
                    raise ErreurDeCorbeille(raison(code))
                try:
                    code = appeler(operation, IFILE_OPERATION_SET_OPERATION_FLAGS, REGLAGES_DE_L_OPERATION, types=(wintypes.DWORD,))
                    if code < 0:
                        raise ErreurDeCorbeille(raison(code))
                    code = appeler(operation, IFILE_OPERATION_DELETE_ITEM, element, None, types=(ctypes.c_void_p, ctypes.c_void_p))
                    if code < 0:
                        raise ErreurDeCorbeille(raison(code))
                    code_des_operations = appeler(operation, IFILE_OPERATION_PERFORM_OPERATIONS)
                finally:
                    appeler(operation, IFILE_OPERATION_UNADVISE, jeton, types=(wintypes.DWORD,))
            finally:
                appeler(element, RELEASE)
        finally:
            appeler(operation, RELEASE)
    finally:
        ole32.CoUninitialize()

    if suivi.refusee:
        raise PasDeCorbeille()
    if suivi.supprimee:
        dedans = Path(suivi.dans_la_corbeille) if suivi.dans_la_corbeille else None
        if dedans is None or not dedans.exists():
            dedans = chercher_dans_la_corbeille(chemin, depuis)
        # Pas dans la corbeille d'après Windows (ne devrait pas arriver : il avait annoncé la corbeille) :
        # dite supprimée définitivement, sauf si on l'y retrouve.
        return Jetee(chemin, suivi.recyclee or dedans is not None, dedans)
    if suivi.code_de_suppression is not None and suivi.code_de_suppression < 0:
        raise ErreurDeCorbeille(raison(suivi.code_de_suppression))
    if code_des_operations < 0:
        raise ErreurDeCorbeille(raison(code_des_operations))
    # Windows n'a rien dit après la suppression : on regarde ce qu'il en est. Il l'avait annoncée dans
    # la corbeille (sinon le suivi aurait tout arrêté) : elle y est, même si on ne la retrouve pas.
    if chemin.exists():
        raise ErreurDeCorbeille("Windows ne l'a pas déplacée")
    dedans = chercher_dans_la_corbeille(chemin, depuis)
    return Jetee(chemin, suivi.vers_la_corbeille or dedans is not None, dedans)


class _Suivi:  # Windows seulement (ses tests tournent sur GitHub)
    """Le « suivi » de l'opération (IFileOperationProgressSink) : un objet COM fait à la main, que
    Windows appelle avant et après chaque suppression. Avant : si la photo n'irait pas dans la corbeille,
    il refuse (E_ABORT), et Windows arrête tout sans rien supprimer. Après : il note si la photo est dans
    la corbeille, et où."""

    def __init__(self, chemin_de):
        import ctypes
        from ctypes import wintypes

        self.refusee = False
        self.vers_la_corbeille = False  # Windows a annoncé la corbeille (PreDeleteItem)
        self.supprimee = False
        self.recyclee = False
        self.dans_la_corbeille: str | None = None
        self.code_de_suppression: int | None = None
        self._references = 1
        self._chemin_de = chemin_de
        reconnus = {bytes(__import__("uuid").UUID(iid).bytes_le) for iid in (IID_IUNKNOWN, IID_IFILE_OPERATION_PROGRESS_SINK)}

        resultat = ctypes.c_long
        objet, element, texte, drapeaux = ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD
        fonction = ctypes.WINFUNCTYPE

        def query_interface(this, iid, sortie):
            if not sortie:
                return E_POINTER
            sortie_typee = ctypes.cast(sortie, ctypes.POINTER(ctypes.c_void_p))
            if iid and ctypes.string_at(iid, 16) in reconnus:
                sortie_typee[0] = this
                self._references += 1
                return S_OK
            sortie_typee[0] = None
            return E_NOINTERFACE

        def add_ref(_this):
            self._references += 1
            return self._references

        def release(_this):
            self._references -= 1
            return self._references

        def avant_suppression(_this, drapeaux_recus, _element):
            try:
                if drapeaux_recus & TSF_DELETE_RECYCLE_IF_POSSIBLE:
                    self.vers_la_corbeille = True
                    return S_OK
            except Exception:  # noqa: BLE001 : dans le doute, rien n'est supprimé
                pass
            self.refusee = True
            return E_ABORT

        def apres_suppression(_this, _drapeaux, _element, code, nouvel_element):
            try:
                self.code_de_suppression = code
                if code >= 0:
                    self.supprimee = True
                    if nouvel_element:  # NULL : supprimée pour de bon (documentation de PostDeleteItem)
                        self.recyclee = True
                        self.dans_la_corbeille = self._chemin_de(nouvel_element)
            except Exception:  # noqa: BLE001 : la photo est déjà partie ; on la cherchera
                pass
            return S_OK

        def rien(*_arguments):
            return S_OK

        prototypes = (
            ("QueryInterface", fonction(resultat, objet, ctypes.c_void_p, ctypes.c_void_p), query_interface),
            ("AddRef", fonction(ctypes.c_ulong, objet), add_ref),
            ("Release", fonction(ctypes.c_ulong, objet), release),
            ("StartOperations", fonction(resultat, objet), rien),
            ("FinishOperations", fonction(resultat, objet, ctypes.c_long), rien),
            ("PreRenameItem", fonction(resultat, objet, drapeaux, element, texte), rien),
            ("PostRenameItem", fonction(resultat, objet, drapeaux, element, texte, ctypes.c_long, element), rien),
            ("PreMoveItem", fonction(resultat, objet, drapeaux, element, element, texte), rien),
            ("PostMoveItem", fonction(resultat, objet, drapeaux, element, element, texte, ctypes.c_long, element), rien),
            ("PreCopyItem", fonction(resultat, objet, drapeaux, element, element, texte), rien),
            ("PostCopyItem", fonction(resultat, objet, drapeaux, element, element, texte, ctypes.c_long, element), rien),
            ("PreDeleteItem", fonction(resultat, objet, drapeaux, element), avant_suppression),
            ("PostDeleteItem", fonction(resultat, objet, drapeaux, element, ctypes.c_long, element), apres_suppression),
            ("PreNewItem", fonction(resultat, objet, drapeaux, element, texte), rien),
            ("PostNewItem", fonction(resultat, objet, drapeaux, element, texte, texte, drapeaux, ctypes.c_long, element), rien),
            ("UpdateProgress", fonction(resultat, objet, ctypes.c_uint, ctypes.c_uint), rien),
            ("ResetTimer", fonction(resultat, objet), rien),
            ("PauseTimer", fonction(resultat, objet), rien),
            ("ResumeTimer", fonction(resultat, objet), rien),
        )

        class Table(ctypes.Structure):
            _fields_ = [(nom, prototype) for nom, prototype, _action in prototypes]

        class Objet(ctypes.Structure):
            _fields_ = [("table", ctypes.POINTER(Table))]

        # Les fonctions, la table et l'objet restent en vie avec ce suivi (Windows les appelle).
        self._fonctions = [prototype(action) for _nom, prototype, action in prototypes]
        self._table = Table(*self._fonctions)
        self._objet = Objet(ctypes.pointer(self._table))
        self.pointeur = ctypes.c_void_p(ctypes.addressof(self._objet))


def _prevenir_l_explorateur(avant: Path, apres: Path) -> None:
    """Dit à l'Explorateur que la photo a quitté la corbeille pour revenir à sa place (les fenêtres
    ouvertes et la corbeille se mettent à jour). Sans conséquence si ça échoue."""
    if sys.platform != "win32" or _fausse_corbeille() is not None:
        return
    try:
        import ctypes

        shell32 = ctypes.WinDLL("shell32")
        shell32.SHChangeNotify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p]
        shell32.SHChangeNotify.restype = None
        shell32.SHChangeNotify(SHCNE_RENAMEITEM, SHCNF_PATHW, str(avant), str(apres))
    except Exception:  # noqa: BLE001
        pass
