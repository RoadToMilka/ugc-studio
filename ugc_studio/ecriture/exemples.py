"""Exemples de scripts donnés au modèle (V2, §10.9) : « Mes meilleurs scripts ».

Le guide officiel de Google le dit : les demandes sans exemples sont probablement moins efficaces.
Pour chaque demande, l'app choisit jusqu'à 3 exemples proches (même langue, puis même réseau,
puis même angle ; tes scripts gardés passent avant les scripts fournis) ; le modèle s'en inspire
pour le ton et le rythme, sans les recopier.

Au départ, 5 scripts fournis (annexe A du document V2), écrits sur des produits fictifs pour
montrer le ton attendu. « Garder comme exemple » y ajoute tes scripts ; la fenêtre « Mes meilleurs
scripts » (lot 2) permet d'y coller un script qui a marché, écrit ailleurs, de noter chaque
exemple (« CPA 9 € ») et de retirer les scripts fournis (puis de les remettre).

Rangement : %APPDATA%\\UGC Studio\\scripts_exemples.json.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from ..estimation import duree_parlee
from ..stockage import ecrire_json, lire_json
from .brief import ANGLES_ANGLAIS, RESEAUX, Brief

EXEMPLES_PAR_DEMANDE = 3
_BALISE = re.compile(r"\s*<[^<>]+>")
_ACCENT = re.compile(r"\*([^*]+)\*")


@dataclass
class ExempleScript:
    identifiant: str
    titre: str
    langue: str
    reseau: str
    angle: str  # un angle de brief.ANGLES, ou vide (ex. offre directe)
    tutoiement: str
    duree_s: int
    brief: str  # ce que disait le brief, en quelques mots
    # Répliques avec les conventions du modèle : {"roles", "texte" (« <laugh> », « *mot* »), "style", "style_fr"}
    repliques: list[dict] = field(default_factory=list)
    pourquoi: str = ""  # pourquoi il marche
    note: str = ""  # ta note libre (ex. « CPA 9 € »)
    fourni: bool = False

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, brut) -> ExempleScript | None:
        if not isinstance(brut, dict) or not isinstance(brut.get("repliques"), list):
            return None
        textes = {c.name: str(brut.get(c.name) or "") for c in fields(cls) if c.type == "str"}
        try:
            duree = int(brut.get("duree_s") or 0)
        except (TypeError, ValueError):
            duree = 0
        repliques = [dict(r) for r in brut["repliques"] if isinstance(r, dict) and r.get("texte")]
        if not repliques:
            return None
        return cls(
            **{**textes, "identifiant": textes.get("identifiant") or uuid.uuid4().hex[:12]},
            duree_s=duree,
            repliques=repliques,
            fourni=bool(brut.get("fourni")),
        )


def _replique(roles: list[str], texte: str, style: str = "", style_fr: str = "") -> dict:
    return {"roles": roles, "texte": texte, "style": style, "style_fr": style_fr}


# Annexe A du document V2 : produits fictifs (à ne pas recopier pour tes vrais produits).
EXEMPLES_FOURNIS: tuple[ExempleScript, ...] = (
    ExempleScript(
        "fourni-glowzy",
        "Sérum éclat « Glowzy »",
        "fr-FR",
        "tiktok",
        "temoignage",
        "tu",
        25,
        "Femme d'environ 30 ans ; 29,90 € ; code GLOW20 (-20 %) ; 3 gouttes le matin, texture fluide qui ne colle pas.",
        [
            _replique(
                ["accroche"],
                "J'ai arrêté le fond de teint la semaine dernière.",
                "intrigued and conspiratorial, a little fast",
                "intriguée et complice, un peu rapide",
            ),
            _replique(
                ["probleme", "solution", "preuve"],
                "J'avais ce teint gris, fatigué, même après une bonne nuit. Une collègue m'a fait tester le sérum "
                "Glowzy : trois gouttes, ça pénètre direct, ça colle pas. Et hier, ma sœur me demande : « T'as "
                "changé quoi ? » <chuckle>",
                "warm and natural, like talking to a friend",
                "chaleureuse et naturelle, comme à une amie",
            ),
            _replique(
                ["offre", "appel_action"],
                "Il est à moins de 30 euros, et avec mon code GLOW20, t'as 20 % en moins. Le lien est en dessous.",
                "upbeat and direct",
                "enjouée et directe",
            ),
        ],
        "L'accroche surprend en parlant de soi ; la preuve vient d'une autre personne (la sœur) ; l'offre "
        "arrive juste avant l'unique appel à l'action.",
        fourni=True,
    ),
    ExempleScript(
        "fourni-choppy",
        "Mini hachoir sans fil « Choppy » (offre directe)",
        "fr-FR",
        "snapchat",
        "",
        "tu",
        10,
        "Homme d'environ 25 ans ; 24,90 € au lieu de 34,90 € jusqu'à dimanche ; rechargeable en USB.",
        [
            _replique(["accroche", "offre"], "Moins 10 euros sur le mini hachoir sans fil, jusqu'à dimanche."),
            _replique(
                ["demonstration", "appel_action"],
                "Oignons, ail, persil : tu appuies, c'est haché. Il se recharge en USB. Appuie juste en dessous.",
            ),
        ],
        "Sur Snapchat, l'offre dès les 2 premières secondes ; une démonstration en une phrase ; une vraie date "
        "limite, donnée par le brief.",
        fourni=True,
    ),
    ExempleScript(
        "fourni-brosso",
        "Brosse de nettoyage électrique « Brosso »",
        "fr-FR",
        "meta",
        "probleme_solution",
        "vous",
        20,
        "Femme d'environ 55 ans ; livraison offerte ; satisfait ou remboursé 30 jours ; embouts pour joints et carrelage.",
        [
            _replique(
                ["accroche"],
                "Trente ans que je frotte les joints de ma douche à la main.",
                "amused, slightly exasperated",
                "amusée, un peu exaspérée",
            ),
            _replique(
                ["solution", "offre", "appel_action"],
                "Ma fille m'a offert cette brosse électrique. Elle tourne toute seule, avec un embout pour les joints, "
                "un pour le carrelage. Je la guide, c'est tout. Elle est livrée gratuitement, et vous avez trente "
                "jours pour l'essayer. Le lien est en dessous.",
                "warm and reassuring",
                "chaleureuse et rassurante",
            ),
        ],
        "Un public plus âgé sur Facebook, d'où le vouvoiement ; la personne parle de sa propre corvée (pas "
        "« Vous avez du mal à frotter ? ») ; l'offre retire le risque.",
        fourni=True,
    ),
    ExempleScript(
        "fourni-runbeat",
        "Écouteurs à conduction osseuse « Runbeat »",
        "fr-FR",
        "tiktok",
        "comparaison",
        "tu",
        30,
        "Homme d'environ 28 ans, coureur ; 59,90 € au lieu de 79,90 € ; posés devant l'oreille, oreilles libres ; "
        "arceau qui tient en place ; résistants à la pluie et à la sueur.",
        [
            _replique(
                ["accroche"],
                "Courir avec des écouteurs dans les oreilles, pour moi, c'est terminé.",
                "confident, a little provocative",
                "sûr de lui, un peu provocateur",
            ),
            _replique(
                ["solution", "demonstration", "preuve"],
                "<breath> Regarde : ceux-là se posent devant l'oreille, sur l'os. Le son passe quand même, et "
                "j'entends *tout* ce qui se passe autour : les voitures, les vélos, mon pote qui me parle. Ils ne "
                "bougent pas, même en sprint, et je les porte sous la pluie depuis trois semaines.",
                "curious and enthusiastic",
                "curieux et enthousiaste",
            ),
            _replique(
                ["offre", "appel_action"],
                "En ce moment, ils sont à 59,90 euros au lieu de 79,90. Le lien est en dessous.",
                "upbeat and direct",
                "enjoué et direct",
            ),
        ],
        "Une accroche à contre-pied ; la démonstration décrit ce qu'on voit à l'écran ; chaque promesse vient "
        "du brief.",
        fourni=True,
    ),
    ExempleScript(
        "fourni-voltie",
        "Batterie externe « Voltie »",
        "fr-BE",
        "tiktok",
        "liste",
        "tu",
        20,
        "Étudiante d'environ 20 ans ; 29,90 € ; recharge un téléphone à 90 % en une heure ; deux appareils en "
        "même temps ; format poche.",
        [
            _replique(["accroche"], "Trois raisons pour lesquelles je ne quitte plus mon kot sans elle."),
            _replique(
                ["solution", "preuve", "offre", "appel_action"],
                "Un : elle recharge mon GSM à 90 % en une heure. Deux : elle tient dans la poche de mon jean. "
                "Trois : elle charge deux appareils en même temps, donc ma coloc m'adore. <laugh> Elle est à "
                "29,90 euros, le lien est juste là.",
            ),
        ],
        "Les mots de Belgique (« kot », « GSM ») ; une liste numérotée retient l'attention jusqu'au bout.",
        fourni=True,
    ),
)


def exemple_colle(
    titre: str,
    texte: str,
    langue: str,
    reseau: str,
    angle: str = "",
    tutoiement: str = "tu",
    duree_s: int = 0,
    note: str = "",
) -> ExempleScript | None:
    """Un script qui a marché, écrit ailleurs et collé dans « Mes meilleurs scripts ».

    Un paragraphe (séparé par une ligne vide) devient une réplique ; un texte d'un seul bloc est
    coupé après sa première phrase : l'accroche est toujours la réplique 1. Balises (« <laugh> »)
    et mots entre astérisques sont gardés tels quels. Durée vide : estimée d'après le texte."""
    blocs = [" ".join(b.split()) for b in re.split(r"\n\s*\n", texte) if b.strip()]
    if len(blocs) == 1:
        lignes = [" ".join(ligne.split()) for ligne in texte.splitlines() if ligne.strip()]
        if len(lignes) > 1:
            blocs = [lignes[0], " ".join(lignes[1:])]
        else:
            coupe = re.match(r"(.+?[.!?…])\s+(\S.*)", blocs[0])
            if coupe:
                blocs = [coupe.group(1), coupe.group(2)]
    if not blocs:
        return None
    repliques = [_replique(["accroche"] if rang == 0 else [], bloc) for rang, bloc in enumerate(blocs)]
    if duree_s <= 0:
        duree_s = max(1, round(duree_parlee("\n".join(blocs).replace("*", ""))))
    return ExempleScript(
        identifiant=f"colle-{uuid.uuid4().hex[:12]}",
        titre=" ".join(titre.split()) or "Script collé",
        langue=langue,
        reseau=reseau if reseau in RESEAUX else "autre",
        angle=angle if angle in ANGLES_ANGLAIS else "",
        tutoiement=tutoiement if tutoiement in ("tu", "vous") else "tu",
        duree_s=duree_s,
        brief="",
        repliques=repliques,
        note=" ".join(note.split()),
    )


def choisir_exemples(exemples: list[ExempleScript], brief: Brief, nombre: int = EXEMPLES_PAR_DEMANDE) -> list[ExempleScript]:
    """Jusqu'à `nombre` exemples proches du brief : même langue d'abord (variante exacte, puis même
    langue), puis même réseau, puis même angle ; tes scripts gardés passent avant les scripts
    fournis. Sans exemple dans la langue du brief, les plus proches des autres langues servent
    (pour la structure et le rythme seulement)."""
    langue = brief.langue.split("-")[0]
    memes = [e for e in exemples if e.langue.split("-")[0] == langue] or list(exemples)

    def score(exemple: ExempleScript) -> int:
        points = 4 if exemple.langue == brief.langue else 0
        points += 2 if exemple.reseau == brief.reseau else 0
        points += 1 if brief.angle != "auto" and exemple.angle == brief.angle else 0
        points += 3 if not exemple.fourni else 0
        return points

    return sorted(memes, key=score, reverse=True)[:nombre]


def adapter_au_brief(exemple: ExempleScript, brief: Brief) -> list[dict]:
    """Répliques de l'exemple, sans ce que le brief ne demande pas (balises, styles, accentuations) :
    sinon le modèle imiterait des balises ou des styles non voulus."""
    repliques = []
    for replique in exemple.repliques:
        texte = str(replique.get("texte") or "")
        if not brief.balises:
            texte = " ".join(_BALISE.sub("", texte).split())
        if not brief.accents:
            texte = _ACCENT.sub(r"\1", texte)
        repliques.append(
            {
                "roles": list(replique.get("roles") or []),
                "texte": texte,
                "style": str(replique.get("style") or "") if brief.styles else "",
                "style_fr": str(replique.get("style_fr") or "") if brief.styles else "",
            }
        )
    return repliques


def texte_des_exemples(exemples: list[ExempleScript], brief: Brief) -> str:
    """Les exemples tels qu'ils sont donnés au modèle (un bloc par exemple)."""
    blocs = []
    for exemple in exemples:
        entete = (
            f'<example title="{exemple.titre}" language="{exemple.langue}" network="{RESEAUX.get(exemple.reseau, exemple.reseau)}" '
            f'angle="{ANGLES_ANGLAIS.get(exemple.angle, "direct offer").split(" (")[0]}" '
            f'duration="{exemple.duree_s} s" address="{exemple.tutoiement}">'
        )
        corps = [entete, f"Brief: {exemple.brief}"]
        corps.append("Script: " + json.dumps(adapter_au_brief(exemple, brief), ensure_ascii=False))
        if exemple.pourquoi:
            corps.append(f"Why it works: {exemple.pourquoi}")
        if exemple.note:
            corps.append(f"Advertiser's note: {exemple.note}")
        corps.append("</example>")
        blocs.append("\n".join(corps))
    return "\n\n".join(blocs)


class BibliothequeExemples:
    """Exemples fournis (sauf ceux que tu as retirés) et scripts que tu as gardés."""

    VERSION_FORMAT = 1

    def __init__(self, chemin: Path):
        self._chemin = chemin
        donnees = lire_json(chemin, {})
        donnees = donnees if isinstance(donnees, dict) else {}
        self._gardes = [e for e in (ExempleScript.depuis_dict(b) for b in donnees.get("exemples") or []) if e]
        for exemple in self._gardes:
            exemple.fourni = False
        retires = donnees.get("fournis_retires")
        self._fournis_retires: list[str] = [str(i) for i in retires] if isinstance(retires, list) else []
        self._abonnes: list[Callable[[], None]] = []

    def exemples(self) -> list[ExempleScript]:
        fournis = [e for e in EXEMPLES_FOURNIS if e.identifiant not in self._fournis_retires]
        return [*self._gardes, *fournis]

    def gardes(self) -> list[ExempleScript]:
        return list(self._gardes)

    def fournis_retires(self) -> list[ExempleScript]:
        return [e for e in EXEMPLES_FOURNIS if e.identifiant in self._fournis_retires]

    def ajouter(self, exemple: ExempleScript) -> None:
        exemple.fourni = False
        self._gardes = [e for e in self._gardes if e.identifiant != exemple.identifiant] + [exemple]
        self._enregistrer()

    def retirer(self, identifiant: str) -> None:
        if any(e.identifiant == identifiant for e in EXEMPLES_FOURNIS):
            if identifiant not in self._fournis_retires:
                self._fournis_retires.append(identifiant)
        self._gardes = [e for e in self._gardes if e.identifiant != identifiant]
        self._enregistrer()

    def remettre_fournis(self) -> None:
        """« Remettre les exemples fournis » : les scripts fournis retirés reviennent."""
        self._fournis_retires = []
        self._enregistrer()

    def noter(self, identifiant: str, note: str) -> None:
        """Note libre d'un de tes exemples (ex. « CPA 9 € ») : le modèle la lit avec l'exemple."""
        for exemple in self._gardes:
            if exemple.identifiant == identifiant:
                exemple.note = " ".join(note.split())
                self._enregistrer()
                return

    def contient(self, identifiant: str) -> bool:
        return any(e.identifiant == identifiant for e in self.exemples())

    def abonner(self, fonction: Callable[[], None]) -> None:
        self._abonnes.append(fonction)

    def _enregistrer(self) -> None:
        ecrire_json(
            self._chemin,
            {
                "version_format": self.VERSION_FORMAT,
                "exemples": [e.en_dict() for e in self._gardes],
                "fournis_retires": self._fournis_retires,
            },
        )
        for fonction in list(self._abonnes):
            fonction()
