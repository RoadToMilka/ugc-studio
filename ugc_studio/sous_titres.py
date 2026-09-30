"""Studio sous-titres (§7) : des mots horodatés aux sous-titres, puis au fichier SRT (§8.1).

1. Texte affiché (§7.2) : sans les hésitations (si l'option est cochée), ponctuation affichée ou
   masquée, typographie de la langue (français : espace insécable avant « ! ? : ; »), TOUT EN
   MAJUSCULES en option. Les temps des mots ne changent pas.
2. Découpage (§7.3) : les mots sont regroupés en sous-titres qui respectent les nombres maximum
   de caractères, de mots et de lignes. Parmi tous les découpages possibles, l'app retient celui
   qui donne des sous-titres bien remplis et équilibrés, en coupant de préférence après une
   ponctuation. Une fin de phrase, un changement de personne ou un long silence terminent
   toujours un sous-titre. Un mot n'est jamais coupé en deux.
3. Écran (§7.3) : la largeur de chaque ligne est mesurée en pixels, avec la police et la taille
   du texte. Elle doit tenir dans la zone de sécurité de la plateforme ; sinon elle peut
   déborder dans la marge, jusqu'à la marge maximum, jamais au-delà (le sous-titre est alors
   redécoupé). Seul un mot affiché seul et trop large est rapetissé : il est signalé en orange.
4. Temps : un sous-titre va du début de son premier mot à la fin du dernier, dure au moins la
   durée minimale (prolongé sans chevaucher le suivant), et les petits trous entre deux
   sous-titres sont comblés (pas de clignotement).

Ce module ne dépend pas de l'interface : la largeur d'un texte en pixels est mesurée par une
fonction fournie (Qt dans l'app, une règle simple dans les tests).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .transcription import PONCTUATION, Mot, mots_affiches

Mesure = Callable[[str], float]  # largeur d'un texte, en pixels, à la taille normale du texte

# --- Formats de vidéo (§7.1) -------------------------------------------------------------------

FORMAT_AUTO = "auto"  # celui de la vidéo importée (sinon 9:16)
FORMATS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "3:4": (1080, 1440),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
FORMAT_PAR_DEFAUT = "9:16"
NOMS_FORMATS = {
    FORMAT_AUTO: "Celui de la vidéo (sinon 9:16)",
    "9:16": "9:16 — TikTok, Reels, Snap, Shorts",
    "4:5": "4:5 — fil Facebook, Instagram",
    "3:4": "3:4",
    "1:1": "1:1 — carré",
    "16:9": "16:9 — horizontal",
}


# --- Zones de sécurité des plateformes (§7.3) ---------------------------------------------------


@dataclass(frozen=True)
class Plateforme:
    """Zone de sécurité : les bords de l'écran que l'interface de la plateforme recouvre (nom du
    compte, légende, boutons…). En part de la largeur (côtés) et de la hauteur (haut, bas)."""

    identifiant: str
    nom: str
    gauche: float
    droite: float
    haut: float
    bas: float
    source: str = ""


PLATEFORMES = (
    Plateforme(
        "tiktok", "TikTok", 120 / 1080, 120 / 1080, 240 / 1920, 660 / 1920,
        "modèle de zone de sécurité de TikTok Ads (avril 2025)",
    ),
    Plateforme(
        "meta", "Instagram, Facebook (Reels, Stories)", 0.06, 0.06, 0.14, 0.35,
        "guide des publicités Meta",
    ),
    Plateforme("youtube", "YouTube Shorts", 0.0, 0.10, 0.10, 0.25, "Google Ads, emplacement Shorts"),
    Plateforme(
        "snapchat", "Snapchat", 40 / 1080, 40 / 1080, 200 / 1920, 370 / 1920,
        "valeurs courantes, non confirmées par Snapchat",
    ),
    Plateforme("aucune", "Aucune (marge maximum seulement)", 0.0, 0.0, 0.0, 0.0),
)
PLATEFORME_PAR_DEFAUT = "tiktok"


def plateforme(identifiant: str) -> Plateforme:
    return next((p for p in PLATEFORMES if p.identifiant == identifiant), PLATEFORMES[0])


# --- Réglages -----------------------------------------------------------------------------------

LIGNES_POSSIBLES = (1, 2)
LIMITES: dict[str, tuple] = {  # valeurs permises (champs de la page Sous-titres, relecture d'un projet)
    "caracteres_max": (8, 120),
    "mots_max": (1, 20),
    "lignes_max": (1, 2),
    "duree_min_s": (0.0, 5.0),
    "marge_max_pct": (0.0, 20.0),
    "taille_pct": (1.0, 15.0),
}


@dataclass
class ReglagesSousTitres:
    """Réglages du projet (§7.2, §7.3), enregistrés dans projet.json."""

    caracteres_max: int = 24  # par sous-titre, espaces comprises
    mots_max: int = 5
    lignes_max: int = 2
    couper_sur_ponctuation: bool = True
    duree_min_s: float = 0.6
    majuscules: bool = False  # TOUT EN MAJUSCULES (affichage seulement)
    ponctuation: bool = True  # ponctuation affichée
    format: str = FORMAT_AUTO
    plateforme: str = PLATEFORME_PAR_DEFAUT
    marge_max_pct: float = 5.0  # de chaque bord : le texte ne la dépasse jamais
    taille_pct: float = 4.0  # taille du texte, en % de la hauteur de la vidéo

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, brut) -> ReglagesSousTitres:
        """Réglages lus dans un projet : une valeur absente ou illisible garde sa valeur par
        défaut ; une valeur hors limites est ramenée dans les limites."""
        reglages = cls()
        if not isinstance(brut, dict):
            return reglages
        for champ in fields(cls):
            if champ.name not in brut:
                continue
            defaut = getattr(reglages, champ.name)
            try:
                if isinstance(defaut, bool):
                    valeur = bool(brut[champ.name])
                elif isinstance(defaut, int):
                    valeur = int(brut[champ.name])
                elif isinstance(defaut, float):
                    valeur = float(brut[champ.name])
                else:
                    valeur = str(brut[champ.name])
            except (TypeError, ValueError):
                continue
            if champ.name in LIMITES:
                bas, haut = LIMITES[champ.name]
                valeur = type(defaut)(min(max(valeur, bas), haut))
            setattr(reglages, champ.name, valeur)
        if reglages.format not in (FORMAT_AUTO, *FORMATS):
            reglages.format = FORMAT_AUTO
        if reglages.plateforme not in {p.identifiant for p in PLATEFORMES}:
            reglages.plateforme = PLATEFORME_PAR_DEFAUT
        return reglages


# --- Écran ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ecran:
    """Dimensions utiles pour vérifier la largeur des sous-titres (en pixels de la vidéo)."""

    largeur: int
    hauteur: int
    taille_texte: float  # taille du texte (px)
    largeur_securite: float  # largeur d'une ligne dans la zone de sécurité (limite souple)
    largeur_max: float  # largeur d'une ligne jusqu'à la marge maximum (limite stricte)


def resolution(format_video: str, resolution_source: tuple[int, int] | None = None) -> tuple[int, int]:
    """Largeur × hauteur de la vidéo : celle de la source (format « auto »), ou du format choisi."""
    if format_video == FORMAT_AUTO:
        return resolution_source or FORMATS[FORMAT_PAR_DEFAUT]
    return FORMATS.get(format_video, FORMATS[FORMAT_PAR_DEFAUT])


def ecran(reglages: ReglagesSousTitres, resolution_source: tuple[int, int] | None = None) -> Ecran:
    largeur, hauteur = resolution(reglages.format, resolution_source)
    largeur_max = largeur * (1 - 2 * reglages.marge_max_pct / 100)
    # Sous-titres centrés : un côté plus large que l'autre réduit d'autant les deux côtés.
    zone = plateforme(reglages.plateforme)
    largeur_securite = min(largeur_max, largeur * (1 - 2 * max(zone.gauche, zone.droite)))
    return Ecran(largeur, hauteur, hauteur * reglages.taille_pct / 100, largeur_securite, largeur_max)


# --- Texte affiché (§7.2) -----------------------------------------------------------------------

ESPACE_INSECABLE = " "
FINS_DE_PHRASE = ".!?…"
PONCTUATION_DE_COUPURE = ",;:" + FINS_DE_PHRASE
FERMANTES = "»”’\"')]}"
OUVRANTES = "«“‘„([{¿¡"


def _fin_sans_fermantes(texte: str) -> str:
    return texte.rstrip(FERMANTES + " " + ESPACE_INSECABLE)


def finit_une_phrase(texte: str) -> bool:
    """« pas… », « semaines ! », « dessous.» » terminent une phrase."""
    fin = _fin_sans_fermantes(texte)
    return bool(fin) and fin[-1] in FINS_DE_PHRASE


def finit_par_ponctuation(texte: str) -> bool:
    """Virgule, point-virgule, deux-points, ou fin de phrase."""
    fin = _fin_sans_fermantes(texte)
    return bool(fin) and fin[-1] in PONCTUATION_DE_COUPURE


def typographie(texte: str, langue: str) -> str:
    """Espaces autour de la ponctuation, selon la langue. Français : espace insécable avant
    « ! ? ; : » et à l'intérieur des guillemets « » (la ponctuation ne se retrouve jamais seule
    en début de ligne). Autres langues : pas d'espace avant « ! ? ; : »."""
    texte = re.sub(r"\s+([,.…)\]}])", r"\1", texte)  # jamais d'espace avant , . … ) ] }
    texte = re.sub(r"([(\[{¿¡])\s+", r"\1", texte)  # ni après ( [ { ¿ ¡
    if (langue or "").split("-")[0].lower() == "fr":
        texte = re.sub(r"(?<=\S)\s*([!?;]+)", lambda m: ESPACE_INSECABLE + m.group(1), texte)
        texte = re.sub(r"(?<=\S)\s*:(?=\s|$)", ESPACE_INSECABLE + ":", texte)  # pas « 10:30 »
        texte = re.sub(r"«\s*", "«" + ESPACE_INSECABLE, texte)
        texte = re.sub(r"(?<=\S)\s*»", ESPACE_INSECABLE + "»", texte)
    else:
        texte = re.sub(r"\s+([!?;:])", r"\1", texte)
    return texte


def sans_ponctuation(texte: str) -> str:
    """Retire la ponctuation autour des mots ; celle à l'intérieur reste (« l'huile », « anti-rides »,
    « 3.5 »)."""
    morceaux = (m.strip(PONCTUATION) for m in texte.split())
    return " ".join(m for m in morceaux if m)


def texte_affiche(texte: str, reglages: ReglagesSousTitres, langue: str) -> str:
    texte = " ".join(texte.split())
    texte = typographie(texte, langue) if reglages.ponctuation else sans_ponctuation(texte)
    return texte.upper() if reglages.majuscules else texte


@dataclass
class MotAffiche:
    texte: str  # tel qu'affiché
    original: str  # texte d'origine (sert à repérer la ponctuation, même masquée)
    debut: float
    fin: float
    locuteur: str = ""


def _ponctuation_seule(texte: str) -> bool:
    return bool(texte) and all(c in PONCTUATION for c in texte)


def accrocher_la_ponctuation(mots: list[Mot]) -> list[Mot]:
    """Une ponctuation transcrite comme un mot à part (« ! ») ne s'affiche jamais seule : elle
    rejoint le mot d'avant (« semaines ! »), ou le suivant pour « « » et « ( ». Les temps sont
    ceux du mot qui l'accueille."""
    resultat: list[Mot] = []
    en_attente = ""
    for mot in mots:
        texte = mot.texte.strip()
        if _ponctuation_seule(texte) and all(c in OUVRANTES for c in texte):
            en_attente += texte + " "
        elif _ponctuation_seule(texte) and resultat and not en_attente:
            dernier = resultat[-1]
            resultat[-1] = Mot(f"{dernier.texte} {texte}", dernier.debut, dernier.fin, dernier.locuteur)
        else:
            resultat.append(Mot(en_attente + texte, mot.debut, mot.fin, mot.locuteur))
            en_attente = ""
    if en_attente and resultat:
        dernier = resultat[-1]
        resultat[-1] = Mot(f"{dernier.texte} {en_attente.strip()}", dernier.debut, dernier.fin, dernier.locuteur)
    return resultat


def mots_a_afficher(
    mots: list[Mot],
    reglages: ReglagesSousTitres,
    langue: str,
    hesitations: Iterable[str] = (),
    masquer_hesitations: bool = True,
) -> list[MotAffiche]:
    """Mots des sous-titres, avec leur texte affiché (options du §7.2 appliquées)."""
    gardes = mots_affiches(mots, set(hesitations), masquer_hesitations)
    resultat = []
    for mot in accrocher_la_ponctuation(gardes):
        affiche = texte_affiche(mot.texte, reglages, langue)
        if affiche:
            resultat.append(MotAffiche(affiche, mot.texte, mot.debut, mot.fin, mot.locuteur))
    return resultat


# --- Découpage (§7.3) ---------------------------------------------------------------------------

PAUSE_COUPURE_S = 0.8  # un silence plus long termine toujours le sous-titre
ECART_COMBLE_S = 0.3  # un trou plus court entre deux sous-titres est comblé (pas de clignotement)
TAILLE_REDUITE_MIN = 0.6  # un mot seul trop large est rapetissé, jusqu'à 60 % de la taille du texte
# Poids des critères du meilleur découpage (voir _cout) :
BONUS_PONCTUATION = 0.25  # sous-titre qui finit sur une ponctuation
PENALITE_MARGE = 0.05  # ligne qui déborde de la zone de sécurité (autorisé, mais moins bien)
PREFERENCE_COUPURE_PONCTUATION = 0.85  # 2 lignes : passage à la ligne après une ponctuation


@dataclass
class SousTitre:
    debut: float
    fin: float
    lignes: list[str]
    premier_mot: int  # indices dans les mots affichés
    dernier_mot: int  # (exclu)
    echelle: float = 1.0  # < 1 : un mot seul trop large, affiché plus petit (signalé en orange)
    dans_la_marge: bool = False  # déborde de la zone de sécurité (jusqu'à la marge maximum)
    trop_large: bool = False  # même à la taille minimum, le mot dépasse la marge maximum

    @property
    def texte(self) -> str:
        return "\n".join(self.lignes)

    @property
    def signale(self) -> bool:
        """À signaler en orange (§7.3, étape 4) : un mot rapetissé pour tenir dans l'écran."""
        return self.echelle < 1.0 or self.trop_large

    @property
    def duree(self) -> float:
        return self.fin - self.debut


@dataclass(frozen=True)
class _Disposition:
    lignes: tuple[str, ...]
    dans_la_marge: bool = False
    echelle: float = 1.0
    trop_large: bool = False


def disposer(groupe: list[MotAffiche], lignes_max: int, ecran: Ecran, mesure: Mesure) -> _Disposition | None:
    """Place les mots d'un sous-titre sur 1 ou 2 lignes : d'abord dans la zone de sécurité (une
    ligne, sinon deux lignes équilibrées), sinon jusqu'à la marge maximum. None : ça ne tient pas
    (il faudra redécouper). Un mot seul trop large est rapetissé (et signalé)."""
    textes = [m.texte for m in groupe]
    for limite, dans_la_marge in ((ecran.largeur_securite, False), (ecran.largeur_max, True)):
        une_ligne = " ".join(textes)
        if mesure(une_ligne) <= limite:
            return _Disposition((une_ligne,), dans_la_marge)
        if lignes_max >= 2 and len(textes) >= 2:
            meilleure: tuple[float, tuple[str, str]] | None = None
            for coupe in range(1, len(textes)):
                haut, bas = " ".join(textes[:coupe]), " ".join(textes[coupe:])
                largeur = max(mesure(haut), mesure(bas))
                if largeur > limite:
                    continue
                if finit_par_ponctuation(groupe[coupe - 1].original):
                    largeur *= PREFERENCE_COUPURE_PONCTUATION
                if meilleure is None or largeur < meilleure[0]:
                    meilleure = (largeur, (haut, bas))
            if meilleure is not None:
                return _Disposition(meilleure[1], dans_la_marge)
    if len(textes) == 1:
        largeur = mesure(textes[0])
        echelle = ecran.largeur_max / largeur if largeur > 0 else 1.0
        return _Disposition((textes[0],), True, max(TAILLE_REDUITE_MIN, echelle), echelle < TAILLE_REDUITE_MIN)
    return None


def coupure_obligatoire(mot: MotAffiche, suivant: MotAffiche, reglages: ReglagesSousTitres) -> bool:
    """Entre ces deux mots, le sous-titre se termine toujours : changement de personne, long
    silence, ou fin de phrase (si « couper sur la ponctuation » est coché)."""
    if mot.locuteur and suivant.locuteur and mot.locuteur != suivant.locuteur:
        return True
    if suivant.debut - mot.fin > PAUSE_COUPURE_S:
        return True
    return reglages.couper_sur_ponctuation and finit_une_phrase(mot.original)


def _cout(groupe: list[MotAffiche], disposition: _Disposition, reglages: ReglagesSousTitres) -> float:
    """Plus c'est bas, mieux c'est : sous-titres bien remplis et de longueurs proches (l'écart au
    maximum compte au carré), qui finissent si possible sur une ponctuation."""
    caracteres = len(" ".join(m.texte for m in groupe))
    cout = (1.0 - min(1.0, caracteres / reglages.caracteres_max)) ** 2
    if disposition.dans_la_marge:
        cout += PENALITE_MARGE
    if reglages.couper_sur_ponctuation and finit_par_ponctuation(groupe[-1].original):
        cout -= BONUS_PONCTUATION
    return cout


def decouper(mots: list[MotAffiche], reglages: ReglagesSousTitres, ecran: Ecran, mesure: Mesure) -> list[SousTitre]:
    """Meilleur découpage des mots en sous-titres (programmation dynamique : pour chaque mot, le
    meilleur découpage de tout ce qui précède est calculé une fois, puis réutilisé)."""
    nombre_de_mots = len(mots)
    meilleur = [0.0] + [math.inf] * nombre_de_mots
    choix: list[tuple[int, _Disposition] | None] = [None] * (nombre_de_mots + 1)
    for fin in range(1, nombre_de_mots + 1):
        for debut in range(fin - 1, -1, -1):
            groupe = mots[debut:fin]
            if len(groupe) > 1 and (
                len(groupe) > reglages.mots_max
                or coupure_obligatoire(mots[debut], mots[debut + 1], reglages)
                or len(" ".join(m.texte for m in groupe)) > reglages.caracteres_max
            ):
                break  # un groupe plus grand dépasserait aussi
            disposition = disposer(groupe, reglages.lignes_max, ecran, mesure)
            if disposition is None:
                break  # ne tient pas dans l'écran : un groupe plus grand non plus
            cout = meilleur[debut] + _cout(groupe, disposition, reglages)
            if cout < meilleur[fin]:
                meilleur[fin], choix[fin] = cout, (debut, disposition)
    sous_titres: list[SousTitre] = []
    fin = nombre_de_mots
    while fin > 0:
        debut, disposition = choix[fin]
        sous_titres.append(
            SousTitre(
                mots[debut].debut,
                mots[fin - 1].fin,
                list(disposition.lignes),
                debut,
                fin,
                disposition.echelle,
                disposition.dans_la_marge,
                disposition.trop_large,
            )
        )
        fin = debut
    sous_titres.reverse()
    return sous_titres


def caler_les_temps(sous_titres: list[SousTitre], duree_min: float, duree_totale: float | None = None) -> None:
    """Durée minimale (prolongé après, sinon avant, sans chevaucher les voisins), puis petits trous
    comblés : le sous-titre reste affiché jusqu'au suivant."""
    for index, sous_titre in enumerate(sous_titres):
        precedent = sous_titres[index - 1].fin if index else 0.0
        suivant = sous_titres[index + 1].debut if index + 1 < len(sous_titres) else (duree_totale or math.inf)
        if sous_titre.duree < duree_min:
            sous_titre.fin = max(sous_titre.fin, min(sous_titre.debut + duree_min, suivant))
        if sous_titre.duree < duree_min:
            sous_titre.debut = min(sous_titre.debut, max(sous_titre.fin - duree_min, precedent))
    for sous_titre, suivant in zip(sous_titres, sous_titres[1:], strict=False):
        if 0 < suivant.debut - sous_titre.fin <= ECART_COMBLE_S:
            sous_titre.fin = suivant.debut
    for sous_titre in sous_titres:
        sous_titre.debut, sous_titre.fin = round(sous_titre.debut, 3), round(sous_titre.fin, 3)


def creer_sous_titres(
    mots: list[Mot],
    reglages: ReglagesSousTitres,
    langue: str,
    ecran_video: Ecran,
    mesure: Mesure,
    hesitations: Iterable[str] = (),
    masquer_hesitations: bool = True,
    duree_totale: float | None = None,
) -> tuple[list[MotAffiche], list[SousTitre]]:
    """Des mots de la transcription aux sous-titres : texte affiché, découpage, temps."""
    affiches = mots_a_afficher(mots, reglages, langue, hesitations, masquer_hesitations)
    largeurs: dict[str, float] = {}  # une même ligne est mesurée une seule fois

    def mesure_memorisee(texte: str) -> float:
        if texte not in largeurs:
            largeurs[texte] = mesure(texte)
        return largeurs[texte]

    sous_titres = decouper(affiches, reglages, ecran_video, mesure_memorisee)
    caler_les_temps(sous_titres, reglages.duree_min_s, duree_totale)
    return affiches, sous_titres


# --- Export SRT (§8.1) --------------------------------------------------------------------------


def temps_srt(secondes: float) -> str:
    """1.25 → « 00:00:01,250 »."""
    millisecondes = max(0, round(secondes * 1000))
    heures, reste = divmod(millisecondes, 3_600_000)
    minutes, reste = divmod(reste, 60_000)
    secondes_entieres, millisecondes = divmod(reste, 1000)
    return f"{heures:02d}:{minutes:02d}:{secondes_entieres:02d},{millisecondes:03d}"


def srt(sous_titres: list[SousTitre]) -> str:
    """Texte du fichier SRT : numéro, temps, lignes ; un bloc par sous-titre, séparés par une
    ligne vide. Fins de ligne Windows (CRLF)."""
    blocs = [
        "\r\n".join([str(numero), f"{temps_srt(s.debut)} --> {temps_srt(s.fin)}", *s.lignes])
        for numero, s in enumerate(sous_titres, 1)
    ]
    return "\r\n\r\n".join(blocs) + ("\r\n" if blocs else "")


def ecrire_srt(chemin: Path, sous_titres: list[SousTitre]) -> None:
    """UTF-8 avec BOM : sans lui, Premiere Pro lit mal les lettres accentuées (é, à, ç…)."""
    chemin.write_text(srt(sous_titres), encoding="utf-8-sig", newline="")
