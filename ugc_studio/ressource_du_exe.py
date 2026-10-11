"""Les « ressources » Windows du .exe : des données rangées dans le fichier du programme (FFmpeg depuis
la V3 ; le modèle d'IA et les bibliothèques de calcul de Doublons depuis la V4.3), que Windows ne lit que
si on les demande. Pourquoi pas avec les autres ressources de l'app ? Le .exe recopie celles-ci dans un
dossier temporaire à chaque démarrage : de gros fichiers rangés là ralentiraient chaque démarrage.

FindResource, LoadResource et LockResource (fonctions de Windows) donnent l'adresse des données dans le
programme déjà ouvert : rien n'est lu du disque avant qu'on y touche.
"""

from __future__ import annotations

import functools
import sys

TYPE_DONNEES_BRUTES = 10  # RT_RCDATA


@functools.cache
def adresse_de_la_ressource(nom: str, type_de_ressource: int = TYPE_DONNEES_BRUTES) -> tuple[int, int] | None:
    """Adresse et taille de la ressource `nom` du .exe, ou None (pas dans un .exe, ou ressource absente).
    Rien ne change pendant que l'app tourne : la réponse est gardée."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    import ctypes
    from ctypes import wintypes

    noyau = ctypes.WinDLL("kernel32", use_last_error=True)
    noyau.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    noyau.GetModuleHandleW.restype = wintypes.HMODULE
    noyau.FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
    noyau.FindResourceW.restype = wintypes.HANDLE
    noyau.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    noyau.SizeofResource.restype = wintypes.DWORD
    noyau.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    noyau.LoadResource.restype = wintypes.HGLOBAL
    noyau.LockResource.argtypes = [wintypes.HGLOBAL]
    noyau.LockResource.restype = ctypes.c_void_p
    module = noyau.GetModuleHandleW(None)  # le .exe lui-même
    # Un type de ressource numéroté se donne comme une « adresse » égale à son numéro (MAKEINTRESOURCE).
    trouvee = noyau.FindResourceW(module, nom, wintypes.LPCWSTR(type_de_ressource))
    if not trouvee:
        return None
    taille = noyau.SizeofResource(module, trouvee)
    chargee = noyau.LoadResource(module, trouvee)
    adresse = noyau.LockResource(chargee) if chargee else None
    if not taille or not adresse:
        return None
    return adresse, taille


def lire_la_ressource(nom: str, type_de_ressource: int = TYPE_DONNEES_BRUTES) -> bytes | None:
    """Une copie des données de la ressource `nom` du .exe, ou None."""
    trouvee = adresse_de_la_ressource(nom, type_de_ressource)
    if trouvee is None:
        return None
    import ctypes

    adresse, taille = trouvee
    return ctypes.string_at(adresse, taille)
