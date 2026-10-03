"""Préréglages de style des sous-titres (V2, lot 7 ; cahier des charges §7.6 et §7.13).

Un préréglage = un nom et un style complet : les réglages des onglets Texte (le Découpage et la
Position compris, depuis la V3.3), Mots et Animations, sous la même forme écrite que la partie
« style » d'un projet. Ni le format ni la plateforme : ils dépendent de la vidéo et de
l'endroit où passe la pub.

- **Fournis** : « Par défaut » (V3.1 : neutre, le style de départ) et les 6 styles du document V2
  (annexe B), dans ressources/prereglages_sous_titres.json. Modifiables et supprimables ; « Rétablir
  les préréglages fournis » les remet comme à l'origine.
- **Rangés** dans %APPDATA%\\UGC Studio\\prereglages_sous_titres.json.
- **★ par défaut** : le style des nouveaux projets (au départ « Par défaut » ; « Blanc contour noir »
  jusqu'à la 3.0.3 ; sans ★, le style de départ, le même que « Par défaut »).
- Un projet garde sa **propre copie** du style : modifier ou supprimer un préréglage ne change pas
  un projet déjà fait. Il retient son préréglage d'origine, pour afficher « (modifié) ».
- **Référence** (V3.1) : le préréglage d'origine du projet **tel qu'il est enregistré** (sans lui,
  le style de départ). Les ↺ du studio y ramènent un groupe de réglages, et les réglages qui s'en
  écartent ont leur nom en mauve.
- **Export** : un petit fichier .json lisible (un ou plusieurs préréglages) ; **import** : ajoutés à
  la liste, avec « (2) » si le nom existe déjà.

Sans interface : testé sans Qt.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from .chemins import dossier_ressources
from .sous_titres import ReglagesSousTitres, avec_le_style, style_de_depart_complet
from .stockage import ecrire_json, lire_json

FICHIER_FOURNIS = "prereglages_sous_titres.json"  # dans ressources/
FICHIER_PREREGLAGES = "prereglages_sous_titres.json"  # dans le dossier de l'app
EXTENSION = ".json"
TYPE_DE_FICHIER = "prereglages_sous_titres"  # marque d'un fichier exporté par l'app
VERSION_FORMAT = 1  # forme écrite d'un préréglage (fichiers exportés)
# Fichier de la bibliothèque : 2 depuis la V3.1 (le préréglage « Par défaut » y a été ajouté).
VERSION_BIBLIOTHEQUE = 2
DEFAUT_FOURNI = "fourni-par-defaut"  # ★ au départ (V3.1)
ANCIEN_DEFAUT_FOURNI = "fourni-blanc-contour-noir"  # ★ au départ jusqu'à la 3.0.3
NOM_MAX = 60  # caractères


class ErreurPrereglage(Exception):
    """Préréglage impossible à lire, importer ou enregistrer, avec un message clair."""


@dataclass(frozen=True)
class Prereglage:
    identifiant: str
    nom: str
    style: dict = field(default_factory=dict)  # forme écrite normalisée (voir normaliser)
    fourni: bool = False  # un des 7 styles fournis (identifiant stable, « fourni-… »)


# --- Style d'un projet et d'un préréglage ------------------------------------------------------


def style_du_projet(reglages: ReglagesSousTitres) -> dict:
    """La partie « style » des réglages : texte, mots, animations, position, découpage."""
    return reglages.en_dict()["style"]


def normaliser(style) -> dict:
    """Forme écrite complète et valide d'un style lu dans un fichier : une valeur absente ou
    illisible prend sa valeur par défaut, une valeur hors limites est ramenée dans les limites
    (mêmes règles qu'un projet). Deux styles qui donnent le même dessin s'écrivent pareil."""
    return style_du_projet(ReglagesSousTitres.depuis_dict({"style": style if isinstance(style, dict) else {}}))


def appliquer(reglages: ReglagesSousTitres, prereglage: Prereglage) -> ReglagesSousTitres:
    """Réglages du projet avec le style du préréglage (format, plateforme et vidéo importée ne
    changent pas) ; le préréglage devient celui d'origine."""
    return replace(avec_le_style(reglages, prereglage.style), prereglage=prereglage.identifiant, prereglage_nom=prereglage.nom)


def modifie(reglages: ReglagesSousTitres, prereglage: Prereglage) -> bool:
    """Le style du projet s'écarte-t-il de celui du préréglage ?"""
    return style_du_projet(reglages) != prereglage.style


def _nouvel_identifiant() -> str:
    return uuid.uuid4().hex[:12]


def _nom_propre(nom) -> str:
    return " ".join(str(nom or "").split())[:NOM_MAX]


def _lire(brut, fourni: bool = False) -> Prereglage | None:
    if not isinstance(brut, dict) or not isinstance(brut.get("style"), dict):
        return None
    nom = _nom_propre(brut.get("nom"))
    if not nom:
        return None
    identifiant = str(brut.get("identifiant") or "") or _nouvel_identifiant()
    return Prereglage(identifiant, nom, normaliser(brut["style"]), fourni or bool(brut.get("fourni")))


def _version(donnees: dict) -> int:
    try:
        return int(donnees.get("version_format") or 1)
    except (TypeError, ValueError):
        return 1


def prereglages_fournis() -> list[Prereglage]:
    """Les 7 styles fournis (ressources/prereglages_sous_titres.json) : « Par défaut », puis les 6 du
    document V2."""
    brut = lire_json(dossier_ressources() / FICHIER_FOURNIS, {})
    lus = [_lire(element, fourni=True) for element in (brut.get("prereglages") if isinstance(brut, dict) else None) or []]
    return [p for p in lus if p is not None]


def lire_fichier(chemin: Path) -> list[Prereglage]:
    """Préréglages d'un fichier exporté (par cette app ou une autre installation). Le fichier n'est
    jamais modifié, même illisible."""
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except OSError as erreur:
        raise ErreurPrereglage(f"Fichier illisible : {erreur}") from erreur
    except (json.JSONDecodeError, UnicodeDecodeError) as erreur:
        raise ErreurPrereglage("Ce fichier n'est pas un préréglage de sous-titres (contenu illisible).") from erreur
    elements = brut.get("prereglages") if isinstance(brut, dict) else None
    if not isinstance(elements, list):
        raise ErreurPrereglage("Ce fichier n'est pas un préréglage de sous-titres exporté par UGC Studio.")
    lus = [_lire({**element, "identifiant": "", "fourni": False}) for element in elements if isinstance(element, dict)]
    lus = [p for p in lus if p is not None]
    if not lus:
        raise ErreurPrereglage("Ce fichier ne contient aucun préréglage lisible.")
    return lus


def contenu_d_export(prereglages: list[Prereglage]) -> dict:
    """Forme écrite d'un fichier exporté : lisible, un style par préréglage."""
    return {
        "description": (
            "Préréglages de sous-titres exportés par UGC Studio : style complet (onglets Texte, Mots et "
            "Animations, le Découpage et la Position compris). Tailles en % de la hauteur de la vidéo ; couleurs "
            "« #RRGGBB » avec leur opacité (0 à 100 %). À importer depuis la fenêtre « Préréglages de sous-titres »."
        ),
        "type": TYPE_DE_FICHIER,
        "version_format": VERSION_FORMAT,
        "prereglages": [{"nom": p.nom, "style": p.style} for p in prereglages],
    }


# --- Bibliothèque ------------------------------------------------------------------------------


class BibliothequePrereglages:
    """Préréglages de l'app, dans %APPDATA%\\UGC Studio\\prereglages_sous_titres.json (les 6 fournis au
    premier lancement)."""

    def __init__(self, chemin: Path):
        self._chemin = chemin
        self._abonnes: list[Callable[[], None]] = []
        donnees = lire_json(chemin, None)
        if isinstance(donnees, dict) and isinstance(donnees.get("prereglages"), list):
            lus = [_lire(element) for element in donnees["prereglages"]]
            self.prereglages: list[Prereglage] = [p for p in lus if p is not None]
            self.par_defaut: str = str(donnees.get("par_defaut") or "")
            if _version(donnees) < VERSION_BIBLIOTHEQUE:
                self._ajouter_par_defaut()
        else:
            self.prereglages = prereglages_fournis()
            self.par_defaut = DEFAUT_FOURNI if self.prereglage(DEFAUT_FOURNI) else ""

    # --- Lecture -------------------------------------------------------------------------------

    def prereglage(self, identifiant: str) -> Prereglage | None:
        return next((p for p in self.prereglages if p.identifiant == identifiant), None) if identifiant else None

    def defaut(self) -> Prereglage | None:
        return self.prereglage(self.par_defaut)

    def nom_libre(self, nom: str, sauf: str = "") -> str:
        """`nom`, ou « nom (2) », « nom (3) »… s'il est déjà pris (sauf par le préréglage `sauf`)."""
        nom = _nom_propre(nom) or "Préréglage"
        pris = {p.nom.casefold() for p in self.prereglages if p.identifiant != sauf}
        candidat, numero = nom, 2
        while candidat.casefold() in pris:
            candidat = f"{nom} ({numero})"
            numero += 1
        return candidat

    def reglages_des_nouveaux(self, reglages: ReglagesSousTitres) -> ReglagesSousTitres:
        """Style d'un nouveau projet : celui du préréglage ★ ; sans ★, le style de départ (le même
        que le préréglage fourni « Par défaut »)."""
        defaut = self.defaut()
        if defaut is not None:
            return appliquer(reglages, defaut)
        return replace(avec_le_style(reglages, style_de_depart_complet()), prereglage="", prereglage_nom="")

    def reference(self, reglages: ReglagesSousTitres) -> ReglagesSousTitres:
        """Ce que les ↺ du studio remettent (V3.1) : le style du préréglage d'origine du projet, tel
        qu'il est enregistré dans la bibliothèque ; sans préréglage (ou s'il a été supprimé depuis), le
        style de départ. L'écran et la vidéo importée restent ceux du projet."""
        origine = self.prereglage(reglages.prereglage)
        if origine is not None:
            return appliquer(reglages, origine)
        return avec_le_style(reglages, style_de_depart_complet())

    def nom_de_reference(self, reglages: ReglagesSousTitres) -> str:
        """« Revenir au préréglage « Par défaut » », ou au style de départ (infobulle des ↺)."""
        origine = self.prereglage(reglages.prereglage)
        return f"Revenir au préréglage « {origine.nom} »" if origine is not None else "Revenir au style de départ"

    # --- Modifications -------------------------------------------------------------------------

    def ajouter(self, nom: str, style: dict) -> Prereglage:
        """Nouveau préréglage (« Enregistrer comme nouveau », « Nouveau », copie)."""
        prereglage = Prereglage(_nouvel_identifiant(), self.nom_libre(nom), normaliser(style))
        self.prereglages.append(prereglage)
        self._enregistrer()
        return prereglage

    def mettre_a_jour(self, identifiant: str, style: dict) -> Prereglage:
        """« Mettre à jour ce préréglage » : il prend ce style (un fourni reste rétablissable)."""
        return self._remplacer(identifiant, style=normaliser(style))

    def renommer(self, identifiant: str, nom: str) -> Prereglage:
        if not _nom_propre(nom):
            raise ErreurPrereglage("Donne un nom au préréglage.")
        return self._remplacer(identifiant, nom=self.nom_libre(nom, sauf=identifiant))

    def dupliquer(self, identifiant: str) -> Prereglage:
        source = self._existant(identifiant)
        copie = Prereglage(_nouvel_identifiant(), self.nom_libre(f"{source.nom} (copie)"), dict(source.style))
        self.prereglages.insert(self.prereglages.index(source) + 1, copie)
        self._enregistrer()
        return copie

    def supprimer(self, identifiant: str) -> None:
        self.prereglages = [p for p in self.prereglages if p.identifiant != identifiant]
        if self.par_defaut == identifiant:
            self.par_defaut = ""  # plus de ★ : les nouveaux projets prennent le style de départ
        self._enregistrer()

    def definir_par_defaut(self, identifiant: str) -> None:
        """★ sur ce préréglage ("" : aucun)."""
        if identifiant:
            self._existant(identifiant)
        self.par_defaut = identifiant
        self._enregistrer()

    def retablir_fournis(self) -> None:
        """Les 7 préréglages fournis redeviennent comme à l'origine (remis s'ils avaient été
        supprimés, en tête de liste) ; les autres ne changent pas, ni le choix du ★ (« aucun » compris :
        c'est un choix)."""
        fournis = prereglages_fournis()
        identifiants = {p.identifiant for p in fournis}
        autres = [p for p in self.prereglages if p.identifiant not in identifiants]
        noms_fournis = {p.nom.casefold() for p in fournis}
        # Un préréglage à soi qui porte le nom d'un fourni garde le sien, avec un numéro.
        self.prereglages = list(fournis)
        for autre in autres:
            if autre.nom.casefold() in noms_fournis:
                autre = replace(autre, nom=self.nom_libre(autre.nom))
            self.prereglages.append(autre)
        self._enregistrer()

    def exporter(self, identifiants: list[str], chemin: Path) -> None:
        choisis = [self._existant(identifiant) for identifiant in identifiants]
        try:
            ecrire_json(chemin, contenu_d_export(choisis))
        except OSError as erreur:
            raise ErreurPrereglage(f"Fichier non enregistré : {erreur}") from erreur

    def importer(self, chemin: Path) -> list[Prereglage]:
        """Ajoute les préréglages d'un fichier exporté ; renvoie ceux ajoutés (noms rendus uniques)."""
        ajoutes = []
        for lu in lire_fichier(chemin):
            prereglage = replace(lu, identifiant=_nouvel_identifiant(), nom=self.nom_libre(lu.nom), fourni=False)
            self.prereglages.append(prereglage)
            ajoutes.append(prereglage)
        self._enregistrer()
        return ajoutes

    # --- Abonnements (fenêtres et studio prévenus des changements) ------------------------------

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    def desabonner(self, fonction: Callable[[], None]) -> None:
        if fonction in self._abonnes:
            self._abonnes.remove(fonction)

    # --- Interne -------------------------------------------------------------------------------

    def _ajouter_par_defaut(self) -> None:
        """Bibliothèque d'avant la V3.1 : le préréglage fourni « Par défaut » arrive en tête de liste ;
        la ★ passe de « Blanc contour noir » (la ★ de départ jusqu'à la 3.0.3) à « Par défaut ». Une ★
        mise sur un autre préréglage (ou retirée) reste comme elle est. Fait une seule fois : le fichier
        est réécrit à la nouvelle version."""
        nouveau = next((p for p in prereglages_fournis() if p.identifiant == DEFAUT_FOURNI), None)
        if nouveau is not None and self.prereglage(DEFAUT_FOURNI) is None:
            self.prereglages.insert(0, replace(nouveau, nom=self.nom_libre(nouveau.nom)))
            if self.par_defaut == ANCIEN_DEFAUT_FOURNI:
                self.par_defaut = DEFAUT_FOURNI
        self._enregistrer()

    def _existant(self, identifiant: str) -> Prereglage:
        prereglage = self.prereglage(identifiant)
        if prereglage is None:
            raise ErreurPrereglage("Ce préréglage n'existe plus.")
        return prereglage

    def _remplacer(self, identifiant: str, **changements) -> Prereglage:
        ancien = self._existant(identifiant)
        nouveau = replace(ancien, **changements)
        self.prereglages[self.prereglages.index(ancien)] = nouveau
        self._enregistrer()
        return nouveau

    def _enregistrer(self) -> None:
        ecrire_json(
            self._chemin,
            {
                "version_format": VERSION_BIBLIOTHEQUE,
                "par_defaut": self.par_defaut,
                "prereglages": [
                    {"identifiant": p.identifiant, "nom": p.nom, "fourni": p.fourni, "style": p.style} for p in self.prereglages
                ],
            },
        )
        for fonction in list(self._abonnes):
            fonction()
