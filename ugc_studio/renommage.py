"""Module Renommer (V4, lot 2 ; cahier des charges §8 bis.2) : choisir l'ordre des images d'un dossier
en les cliquant, puis les renommer toutes d'un coup avec un masque, comme l'action « Énumération »
d'Ant Renamer 2.13 (même masque, mêmes balises : les masques de l'utilisateur marchent tels quels).

Ce fichier ne contient que le calcul et le renommage, sans interface :
- le masque et ses balises : `%num%` (le numéro, obligatoire), `%name%` (le nom d'origine, sans
  l'extension), `%ext%` (l'extension d'origine, avec son point), `%folderN%` (le nom d'un dossier :
  `%folder1%` celui des images, `%folder2%` celui du dessus…), `%%` (le caractère « % ») ;
- l'ordre : les images cliquées d'abord, dans l'ordre des clics, puis les autres dans l'ordre de
  l'affichage (celui de l'Explorateur, ou par date) ;
- le plan : le nouveau nom de chaque image, et ce qui empêcherait de renommer (règles de Windows) ;
- le renommage en deux temps, avec retour en arrière si un fichier est bloqué ;
- le journal des renommages (renommages.json, dans le dossier des données de l'app), pour
  « Annuler le dernier renommage ».

Seul le nom des fichiers change, jamais leur contenu.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .dossiers import images_du_dossier
from .stockage import ecrire_json, lire_json

# --- Le masque ---------------------------------------------------------------------------------

MASQUE_PAR_DEFAUT = "image_%num%%ext%"
MASQUES_RECENTS_MAX = 10  # comme la liste du champ « Masque » d'Ant Renamer

BALISE_NUMERO = "%num%"
BALISE_EXTENSION = "%ext%"

# Une balise connue (`%num%`, `%name%`, `%ext%`, `%folderN%` avec N à partir de 1, `%%`), ou un mot
# entre deux « % » qui n'en est pas une (gardé tel quel, et signalé). Lu de gauche à droite, sans tenir
# compte des majuscules : « 100%_promo_%num% » garde son premier « % ».
_JETON = re.compile(r"%(num|name|ext|folder([1-9]\d*)|)%|%([A-Za-z][A-Za-z0-9]*)%", re.IGNORECASE)

DEPART_MIN, DEPART_MAX = 0, 999_999
CHIFFRES_MIN, CHIFFRES_MAX = 1, 10
PAS_MIN, PAS_MAX = 1, 1000


@dataclass(frozen=True)
class Numerotation:
    """« Démarrer à », « Nombre de chiffres » et « Incrémenter de », comme dans Ant Renamer."""

    depart: int = 1
    chiffres: int = 2
    pas: int = 1

    def numero(self, rang: int) -> str:
        """Le numéro du fichier de rang `rang` (0 pour le premier), avec ses zéros devant : 1 → « 01 ».
        Au-delà du nombre de chiffres, le numéro s'allonge tout seul (99, puis 100)."""
        return f"{self.depart + rang * self.pas:0{self.chiffres}d}"


@dataclass(frozen=True)
class AnalyseDuMasque:
    avec_numero: bool
    avec_extension: bool
    inconnues: tuple[str, ...]  # « %date% » : gardées telles quelles
    niveaux: tuple[int, ...]  # N des balises %folderN%


def analyser_le_masque(masque: str) -> AnalyseDuMasque:
    avec_numero = avec_extension = False
    inconnues: list[str] = []
    niveaux: list[int] = []
    for jeton in _JETON.finditer(masque):
        balise = (jeton.group(1) or "").lower() if jeton.group(3) is None else None
        if balise is None:
            if jeton.group(0) not in inconnues:
                inconnues.append(jeton.group(0))
        elif balise == "num":
            avec_numero = True
        elif balise == "ext":
            avec_extension = True
        elif balise.startswith("folder"):
            niveaux.append(int(jeton.group(2)))
    return AnalyseDuMasque(avec_numero, avec_extension, tuple(inconnues), tuple(niveaux))


def nom_du_dossier(chemin: Path, niveau: int) -> str:
    """`%folder1%` : le dossier de l'image ; `%folder2%` : celui du dessus… ; rien au-delà du disque."""
    parents = chemin.parents
    return parents[niveau - 1].name if niveau - 1 < len(parents) else ""


def appliquer_le_masque(masque: str, chemin: Path, numero: str) -> str:
    """Le nouveau nom de l'image `chemin`, avec ce numéro (déjà écrit avec ses zéros)."""

    def remplacer(jeton: re.Match) -> str:
        if jeton.group(3) is not None:
            return jeton.group(0)  # balise inconnue : gardée telle quelle
        balise = jeton.group(1).lower()
        if balise == "":
            return "%"
        if balise == "num":
            return numero
        if balise == "name":
            return chemin.stem
        if balise == "ext":
            return chemin.suffix
        return nom_du_dossier(chemin, int(jeton.group(2)))

    return _JETON.sub(remplacer, masque)


def masques_recents(recents: Iterable[str], masque: str) -> list[str]:
    """La liste des masques récents, avec `masque` en tête (sans doublon, au plus MASQUES_RECENTS_MAX)."""
    liste = [masque] + [m for m in recents if isinstance(m, str) and m and m != masque]
    return liste[:MASQUES_RECENTS_MAX]


# --- Les noms permis par Windows ------------------------------------------------------------------

# Documentation de Microsoft, « Naming Files, Paths, and Namespaces » (consultée le 04/10/2026).
CARACTERES_INTERDITS = '<>:"/\\|?*'
NOMS_RESERVES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{chiffre}" for chiffre in "123456789¹²³"}
    | {f"LPT{chiffre}" for chiffre in "123456789¹²³"}
)
LONGUEUR_NOM_MAX = 255  # caractères, pour un nom de fichier
LONGUEUR_CHEMIN_MAX = 259  # MAX_PATH (260) moins le caractère de fin : la limite habituelle de Windows


def cle_windows(nom: str) -> str:
    """Pour Windows, « Photo.JPG » et « photo.jpg » sont le même nom : on compare les majuscules (une
    lettre pour une lettre, comme Windows : « ß » reste « ß »)."""
    return "".join(lettre.upper() if len(lettre.upper()) == 1 else lettre for lettre in nom)


def probleme_du_nom(nom: str) -> str:
    """Pourquoi Windows refuserait ce nom de fichier (vide si le nom est permis)."""
    if not nom:
        return "Nom vide."
    interdits = []
    for lettre in nom:
        if (lettre in CARACTERES_INTERDITS or ord(lettre) < 32) and lettre not in interdits:
            interdits.append(lettre)
    if interdits:
        lisibles = " ".join(lettre if ord(lettre) >= 32 else "(invisible)" for lettre in interdits)
        return f"Caractère interdit par Windows : {lisibles}"
    if nom[-1] in " .":
        return "Un nom ne peut pas finir par un espace ou un point."
    base = nom.split(".")[0]
    if base.rstrip(" ").upper() in NOMS_RESERVES:
        return f"« {base} » est un nom réservé par Windows."
    if len(nom.encode("utf-16-le")) // 2 > LONGUEUR_NOM_MAX:
        return f"Nom trop long ({LONGUEUR_NOM_MAX} caractères au plus)."
    return ""


# --- Les images du dossier, et leur ordre ------------------------------------------------------

NOM, DATE_MODIFICATION, DATE_PRISE_DE_VUE = "nom", "modification", "prise_de_vue"
TRIS = {
    NOM: "Nom (comme l'Explorateur)",
    DATE_MODIFICATION: "Date de modification",
    DATE_PRISE_DE_VUE: "Date de prise de vue",
}
_DATE_ORIGINALE, _DATE_EXIF, _IFD_EXIF = 0x9003, 0x0132, 0x8769  # étiquettes EXIF


@dataclass(frozen=True)
class ImageDuDossier:
    chemin: Path
    modifiee: float  # date de modification (secondes depuis 1970)
    prise_de_vue: float | None = None  # date de prise de vue (EXIF), si l'image la donne


@dataclass(frozen=True)
class ContenuDuDossier:
    dossier: Path
    images: tuple[ImageDuDossier, ...]  # dans l'ordre de l'Explorateur
    autres_noms: frozenset[str]  # tout le reste du dossier : autres fichiers, sous-dossiers, fichiers cachés


def _date_de_prise_de_vue(chemin: Path) -> float | None:
    from PIL import Image  # chargé à la demande : le démarrage de l'app n'en a pas besoin

    try:
        with Image.open(chemin) as image:
            exif = image.getexif()
            texte = exif.get_ifd(_IFD_EXIF).get(_DATE_ORIGINALE) or exif.get(_DATE_EXIF)
        if not isinstance(texte, str):
            return None
        return datetime.strptime(texte.strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:  # noqa: BLE001 : une date illisible ne compte simplement pas
        return None


def lire_le_dossier(dossier: Path) -> ContenuDuDossier:
    """Les images du dossier (pas celles des sous-dossiers, pas les fichiers cachés), dans l'ordre de
    l'Explorateur, avec leurs dates ; et les noms de tout le reste, pour éviter qu'un nouveau nom ne
    tombe sur un fichier qui n'est pas renommé."""
    chemins = images_du_dossier(dossier)
    images = []
    for chemin in chemins:
        try:
            modifiee = chemin.stat().st_mtime
        except OSError:
            continue
        images.append(ImageDuDossier(chemin, modifiee, _date_de_prise_de_vue(chemin)))
    noms_des_images = {image.chemin.name for image in images}
    try:
        autres = frozenset(nom for nom in os.listdir(dossier) if nom not in noms_des_images)
    except OSError:
        autres = frozenset()
    return ContenuDuDossier(dossier, tuple(images), autres)


def trier(images: Sequence[ImageDuDossier], tri: str) -> list[ImageDuDossier]:
    """L'ordre de l'affichage. Par date : de la plus ancienne à la plus récente (à date égale, l'ordre
    de l'Explorateur). Sans date de prise de vue, celle de modification."""
    if tri == DATE_MODIFICATION:
        return sorted(images, key=lambda image: image.modifiee)
    if tri == DATE_PRISE_DE_VUE:
        return sorted(images, key=lambda image: image.prise_de_vue if image.prise_de_vue is not None else image.modifiee)
    return list(images)


def ordre_final(affichage: Sequence[Path], choisies: Sequence[Path]) -> list[tuple[Path, bool]]:
    """Les images cliquées d'abord, dans l'ordre des clics, puis les autres dans l'ordre de
    l'affichage. Chaque image avec « cliquée ou non »."""
    deja = set(choisies)
    return [(chemin, True) for chemin in choisies] + [(chemin, False) for chemin in affichage if chemin not in deja]


# --- Le plan ---------------------------------------------------------------------------------------


@dataclass
class Ligne:
    """Une image du plan, dans l'ordre final."""

    chemin: Path
    numero: str  # tel qu'il sera écrit (« 01 »)
    choisie: bool  # cliquée (numéro mauve) ou suivant l'ordre de l'affichage (gris)
    nouveau: str
    probleme: str = ""  # en rouge : empêche de renommer
    avertissement: str = ""  # en orange : à regarder

    @property
    def inchangee(self) -> bool:
        return self.nouveau == self.chemin.name


@dataclass
class PlanDeRenommage:
    dossier: Path
    lignes: list[Ligne] = field(default_factory=list)
    erreur: str = ""  # masque inutilisable (vide, sans %num%) : aucun nouveau nom n'est calculé
    alertes: list[str] = field(default_factory=list)  # en orange

    @property
    def problemes(self) -> list[Ligne]:
        return [ligne for ligne in self.lignes if ligne.probleme]

    @property
    def a_renommer(self) -> list[Ligne]:
        return [ligne for ligne in self.lignes if not ligne.inchangee]

    @property
    def possible(self) -> bool:
        return not self.erreur and not self.problemes and bool(self.a_renommer)

    def changements(self) -> list[tuple[str, str]]:
        return [(ligne.chemin.name, ligne.nouveau) for ligne in self.a_renommer]

    def resume(self) -> str:
        """« 12 images : de « NeMu_JPG_01.jpg » à « NeMu_JPG_12.jpg ». »"""
        if self.erreur:
            return self.erreur
        if not self.lignes:
            return "Aucune image à renommer dans ce dossier."
        nombre = len(self.lignes)
        if self.problemes:
            mauvaises = len(self.problemes)
            sujet = "1 image a" if mauvaises == 1 else f"{mauvaises} images ont"
            return f"{sujet} un nom impossible (en rouge) : rien n'est renommé tant que c'est le cas."
        if not self.a_renommer:
            return f"{quantite(nombre, 'image')} : {'elle a' if nombre == 1 else 'elles ont'} déjà ces noms."
        texte = f"{quantite(nombre, 'image')} : « {self.lignes[0].nouveau} »"
        if nombre > 1:
            texte = f"{quantite(nombre, 'image')} : de « {self.lignes[0].nouveau} » à « {self.lignes[-1].nouveau} »"
        gardes = nombre - len(self.a_renommer)
        if gardes:
            texte += f" ({gardes} {'garde' if gardes == 1 else 'gardent'} {'son' if gardes == 1 else 'leur'} nom)"
        return texte + "."


def quantite(nombre: int, mot: str) -> str:
    return f"{nombre} {mot}{'s' if nombre > 1 else ''}"


def _avertissement_d_extension(chemin: Path, nouveau: str) -> str:
    ancienne, nouvelle = chemin.suffix, Path(nouveau).suffix
    if not nouvelle:
        return "Sans extension : Windows ne saura plus avec quelle app l'ouvrir."
    if nouvelle.lower() != ancienne.lower():
        return f"Extension changée ({ancienne} devient {nouvelle}) : l'image risque de ne plus s'ouvrir."
    return ""


def planifier(
    contenu: ContenuDuDossier,
    ordre: Sequence[tuple[Path, bool]],
    masque: str,
    numerotation: Numerotation,
) -> PlanDeRenommage:
    """Le nouveau nom de chaque image, dans l'ordre final (voir ordre_final), et ce qui l'empêcherait."""
    plan = PlanDeRenommage(contenu.dossier)
    analyse = analyser_le_masque(masque)
    if not masque:
        plan.erreur = "Écris le masque du nouveau nom (par exemple « NeMu_JPG_%num%%ext% »)."
        return plan
    if not analyse.avec_numero:
        plan.erreur = "Le masque doit contenir %num% (le numéro) : sans lui, toutes les images auraient le même nom."
        return plan
    for rang, (chemin, choisie) in enumerate(ordre):
        numero = numerotation.numero(rang)
        plan.lignes.append(Ligne(chemin, numero, choisie, appliquer_le_masque(masque, chemin, numero)))

    # Ce que Windows refuserait, puis deux images au même nom, puis un nom déjà pris par un fichier
    # qui n'est pas renommé (un autre fichier du dossier, un sous-dossier).
    par_nom: dict[str, list[Ligne]] = {}
    for ligne in plan.lignes:
        par_nom.setdefault(cle_windows(ligne.nouveau), []).append(ligne)
    autres = {cle_windows(nom) for nom in contenu.autres_noms}
    for ligne in plan.lignes:
        probleme = probleme_du_nom(ligne.nouveau)
        if not probleme:
            memes = [autre for autre in par_nom[cle_windows(ligne.nouveau)] if autre is not ligne]
            if memes:
                probleme = f"Même nom que l'image n° {memes[0].numero}."
            elif cle_windows(ligne.nouveau) in autres:
                probleme = "Nom déjà pris par un autre fichier du dossier (qui n'est pas renommé)."
            elif len(str(contenu.dossier / ligne.nouveau)) > LONGUEUR_CHEMIN_MAX:
                probleme = f"Chemin trop long pour Windows ({LONGUEUR_CHEMIN_MAX} caractères au plus)."
        ligne.probleme = probleme
        if not probleme:
            ligne.avertissement = _avertissement_d_extension(ligne.chemin, ligne.nouveau)

    # En orange : ce qui mérite un coup d'œil.
    sans_extension = [ligne for ligne in plan.lignes if ligne.avertissement.startswith("Sans extension")]
    changees = [ligne for ligne in plan.lignes if ligne.avertissement.startswith("Extension changée")]
    if sans_extension:
        plan.alertes.append(
            f"{quantite(len(sans_extension), 'image')} sans extension (.jpg…) : Windows ne saura plus avec quelle app "
            f"{'l' if len(sans_extension) == 1 else 'les'} ouvrir. Ajoute %ext% à la fin du masque."
        )
    if changees:
        plan.alertes.append(
            f"{quantite(len(changees), 'image')} {'change' if len(changees) == 1 else 'changent'} d'extension : "
            f"{'elle risque' if len(changees) == 1 else 'elles risquent'} de ne plus s'ouvrir. Utilise plutôt %ext%."
        )
    for inconnue in analyse.inconnues:
        plan.alertes.append(f"{inconnue} n'est pas une balise : écrit tel quel dans les noms.")
    if plan.lignes:
        for niveau in sorted(set(analyse.niveaux)):
            if not nom_du_dossier(plan.lignes[0].chemin, niveau):
                plan.alertes.append(f"%folder{niveau}% : pas de dossier à ce niveau, remplacé par rien.")
    return plan


# --- Le renommage ------------------------------------------------------------------------------


class RenommageImpossible(Exception):
    """Le renommage n'a pas pu se faire ; tout est revenu comme avant. Le message est pour
    l'utilisateur. `definitif` : il ne marchera pas mieux plus tard (un fichier a disparu, un nom est
    pris), au contraire d'un fichier ouvert dans une autre app."""

    def __init__(self, message: str, definitif: bool = False):
        super().__init__(message)
        self.definitif = definitif


PREFIXE_PROVISOIRE = "~ugc-renommage-"


def _nom_provisoire(dossier: Path) -> str:
    while True:
        nom = f"{PREFIXE_PROVISOIRE}{uuid.uuid4().hex[:12]}.tmp"
        if not os.path.lexists(dossier / nom):
            return nom


def _deplacer(source: Path, cible: Path) -> None:
    """Renomme `source` en `cible`, sans jamais écraser un fichier existant (Windows refuse de toute
    façon ; ailleurs, un renommage remplacerait le fichier sans rien dire)."""
    if os.path.lexists(cible):
        raise FileExistsError(17, "Le fichier existe déjà", str(cible))
    os.rename(source, cible)


def _raison(nom: str, erreur: OSError) -> tuple[str, bool]:
    if isinstance(erreur, PermissionError):
        return f"« {nom} » est ouvert dans une autre app, ou protégé : ferme-la puis réessaie.", False
    if isinstance(erreur, FileNotFoundError):
        return f"« {nom} » n'est plus dans le dossier.", True
    if isinstance(erreur, FileExistsError):
        return f"« {nom} » : ce nom est déjà pris dans le dossier.", True
    return f"« {nom} » ne peut pas être renommé ({erreur.strerror or erreur}).", False


def _remettre(dossier: Path, paires: Iterable[tuple[str, str]]) -> list[str]:
    """Retour en arrière : renomme chaque (actuel → d'avant). Renvoie les noms restés provisoires."""
    restes = []
    for actuel, avant in paires:
        try:
            _deplacer(dossier / actuel, dossier / avant)
        except OSError:
            restes.append(actuel)
    return restes


def renommer(dossier: Path, changements: Sequence[tuple[str, str]]) -> int:
    """Renomme chaque fichier (ancien nom → nouveau nom) en deux temps : d'abord un nom provisoire
    pour chacun, puis le nom final. Sinon, renommer « 2.jpg » en « 1.jpg » alors que « 1.jpg » n'a pas
    encore changé de nom échouerait. Si un fichier ne peut pas être renommé (ouvert dans une autre
    app…), tout est remis comme avant et RenommageImpossible dit lequel. Renvoie le nombre de fichiers
    renommés."""
    changements = [(ancien, nouveau) for ancien, nouveau in changements if ancien != nouveau]
    if not changements:
        return 0
    # Vérifications avant de toucher à quoi que ce soit.
    liberes = {cle_windows(ancien) for ancien, _ in changements}
    for ancien, nouveau in changements:
        if not (dossier / ancien).is_file():
            raise RenommageImpossible(f"« {ancien} » n'est plus dans le dossier. Rien n'a changé.", definitif=True)
        if os.path.lexists(dossier / nouveau) and cle_windows(nouveau) not in liberes:
            raise RenommageImpossible(f"« {nouveau} » : ce nom est déjà pris dans le dossier. Rien n'a changé.", definitif=True)

    # 1er temps : un nom provisoire pour chacun.
    provisoires: list[str] = []
    for ancien, _nouveau in changements:
        provisoire = _nom_provisoire(dossier)
        try:
            _deplacer(dossier / ancien, dossier / provisoire)
        except OSError as erreur:
            restes = _remettre(dossier, zip(provisoires, (a for a, _n in changements)))
            raise _echec(ancien, erreur, restes) from erreur
        provisoires.append(provisoire)

    # 2e temps : le nom final.
    for rang, ((ancien, nouveau), provisoire) in enumerate(zip(changements, provisoires)):
        try:
            _deplacer(dossier / provisoire, dossier / nouveau)
        except OSError as erreur:
            # Retour en arrière, en deux temps lui aussi : les fichiers déjà à leur nom final
            # reprennent leur nom provisoire, puis chacun reprend son ancien nom.
            faits = [(n, p) for (_a, n), p in zip(changements[:rang], provisoires[:rang])]
            restes = _remettre(dossier, faits)
            restes += _remettre(dossier, zip(provisoires, (a for a, _n in changements)))
            raise _echec(ancien, erreur, restes) from erreur
    return len(changements)


def _echec(nom: str, erreur: OSError, restes: list[str]) -> RenommageImpossible:
    message, definitif = _raison(nom, erreur)
    if restes:
        noms = ", ".join(f"« {reste} »" for reste in restes[:3]) + ("…" if len(restes) > 3 else "")
        return RenommageImpossible(
            f"{message} Attention : {quantite(len(restes), 'fichier')} {'garde' if len(restes) == 1 else 'gardent'} "
            f"un nom provisoire ({noms}), à renommer à la main.",
            definitif,
        )
    return RenommageImpossible(f"{message} Rien n'a changé.", definitif)


# --- Le journal, pour « Annuler le dernier renommage » ------------------------------------------

FICHIER_JOURNAL = "renommages.json"
RENOMMAGES_GARDES = 20


@dataclass(frozen=True)
class Renommage:
    dossier: Path
    date: str  # date et heure (ISO 8601)
    changements: tuple[tuple[str, str], ...]  # (ancien nom, nouveau nom)

    def inverse(self) -> list[tuple[str, str]]:
        return [(nouveau, ancien) for ancien, nouveau in self.changements]

    def en_donnees(self) -> dict:
        return {"dossier": str(self.dossier), "date": self.date, "changements": [list(paire) for paire in self.changements]}

    @staticmethod
    def depuis(donnees) -> Renommage | None:
        try:
            changements = tuple((str(ancien), str(nouveau)) for ancien, nouveau in donnees["changements"])
            return Renommage(Path(donnees["dossier"]), str(donnees["date"]), changements)
        except (KeyError, TypeError, ValueError):
            return None


class JournalDesRenommages:
    """Les derniers renommages (les plus récents d'abord), dans le dossier des données de l'app : pas
    dans le dossier des images. « Annuler » reprend le plus récent, puis le précédent, etc."""

    def __init__(self, chemin: Path):
        self.chemin = chemin

    def renommages(self) -> list[Renommage]:
        donnees = lire_json(self.chemin, {})
        liste = donnees.get("renommages", []) if isinstance(donnees, dict) else []
        return [r for r in (Renommage.depuis(element) for element in liste if isinstance(element, dict)) if r is not None]

    def dernier(self) -> Renommage | None:
        liste = self.renommages()
        return liste[0] if liste else None

    def _ecrire(self, liste: list[Renommage]) -> None:
        ecrire_json(self.chemin, {"version": 1, "renommages": [r.en_donnees() for r in liste[:RENOMMAGES_GARDES]]})

    def ajouter(self, renommage: Renommage) -> None:
        self._ecrire([renommage, *self.renommages()])

    def retirer(self, renommage: Renommage) -> None:
        self._ecrire([r for r in self.renommages() if r != renommage])


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


def annuler(renommage: Renommage) -> int:
    """Remet les anciens noms (en deux temps, comme le renommage). RenommageImpossible si un fichier
    a disparu ou si un ancien nom est pris entre-temps (`definitif`), ou si un fichier est bloqué."""
    return renommer(renommage.dossier, renommage.inverse())
