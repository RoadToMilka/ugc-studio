"""Accroches et scripts écrits par le module Script (V2, §10.6 à §10.11).

Le modèle écrit chaque réplique en texte simple, avec deux conventions :
- balises en anglais entre chevrons (« <laugh> »), seulement celles de l'app ;
- mot accentué entre astérisques (« *tout* »), un au plus par réplique.
L'app les convertit en « segments », comme le script du module Voix (script.py) : badges de
balises et mots accentués (envoyés en MAJUSCULES à la voix, écriture d'origine pour les
sous-titres). Une balise inconnue est retirée, et la relecture le signale.

Découpage : l'accroche est toujours la réplique 1 ; ensuite, une nouvelle réplique seulement quand
l'émotion change (§5.3). Les rôles (problème, solution, preuve…) sont des étiquettes affichées sur
le script, ils ne créent pas de répliques.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

from ..balises import balise_depuis_nom
from ..estimation import MOTS_PAR_SECONDE, duree_parlee
from ..script import Segment, depuis_texte, est_vide, normaliser, texte_brut, texte_pour_api

ROLES = {
    "accroche": "Accroche",
    "probleme": "Problème",
    "solution": "Solution",
    "demonstration": "Démonstration",
    "preuve": "Preuve",
    "offre": "Offre",
    "appel_action": "Appel à l'action",
}
GRAVITES = ("ok", "leger", "grave")
NOTE_MAX = 5

_ACCENT = re.compile(r"\*{1,2}([^*\n]{1,40}?)\*{1,2}")
_BALISE_RESTANTE = re.compile(r"<\s*([^<>\n]{1,40}?)\s*>")


def _maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _entier(valeur) -> int:
    try:
        return int(valeur or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class Accroche:
    texte: str
    angle: str = ""
    pourquoi: str = ""  # pourquoi elle accroche (en français)
    alerte: str = ""  # signal orange si elle frôle une règle publicitaire (en français), sinon vide
    cochee: bool = False

    @classmethod
    def depuis_dict(cls, brut) -> Accroche | None:
        if not isinstance(brut, dict) or not str(brut.get("texte") or "").strip():
            return None
        return cls(
            texte=" ".join(str(brut["texte"]).split()),
            angle=str(brut.get("angle") or ""),
            pourquoi=" ".join(str(brut.get("pourquoi") or "").split()),
            alerte=" ".join(str(brut.get("alerte") or "").split()),
            cochee=bool(brut.get("cochee")),
        )


@dataclass
class RepliqueEcrite:
    roles: list[str]
    script: list[Segment]  # segments (voir script.py)
    style: str = ""  # en anglais, envoyé à la voix
    style_fr: str = ""

    @classmethod
    def depuis_dict(cls, brut) -> RepliqueEcrite | None:
        if not isinstance(brut, dict):
            return None
        script = [dict(s) for s in brut.get("script") or [] if isinstance(s, dict)]
        return cls(
            roles=[str(r) for r in brut.get("roles") or [] if str(r) in ROLES],
            script=normaliser(script),
            style=str(brut.get("style") or ""),
            style_fr=str(brut.get("style_fr") or ""),
        )


@dataclass
class PointRelecture:
    critere: str  # ex. « duree », « mots_interdits » (app) ou « accroche », « faits » (modèle)
    gravite: str  # « ok », « leger » (⚠, à toi de voir) ou « grave »
    explication: str = ""
    par: str = "app"  # « app » (vérifié exactement) ou « modele » (jugement)

    @classmethod
    def depuis_dict(cls, brut) -> PointRelecture | None:
        if not isinstance(brut, dict) or not brut.get("critere"):
            return None
        gravite = str(brut.get("gravite") or "ok")
        return cls(
            critere=str(brut["critere"]),
            gravite=gravite if gravite in GRAVITES else "leger",
            explication=str(brut.get("explication") or ""),
            par="modele" if brut.get("par") == "modele" else "app",
        )


@dataclass
class ScriptEcrit:
    identifiant: str
    date: str
    modele: str
    reseau: str
    langue: str
    angle: str
    duree_visee_s: int
    repliques: list[RepliqueEcrite]
    tutoiement: str = "tu"
    accroche_imposee: str = ""  # accroche choisie parmi les propositions (sinon vide)
    balises: bool = False  # options cochées au moment de l'écriture
    styles: bool = True
    accents: bool = False
    relecture: list[PointRelecture] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)  # ce que la relecture a corrigé
    tokens_entree: int = 0
    tokens_sortie: int = 0
    cout_eur: str | None = None
    envoye_le: str = ""  # date de l'envoi dans le module Voix
    garde_comme_exemple: bool = False
    # Lot 2 (même format de projet : valeurs par défaut pour un script de la 1.2.0).
    numero: int = 0  # « Script 3 » : donné à la création, il ne change plus (voir etat.py)
    note: int = 0  # 0 à 5 étoiles
    retenu: bool = False  # « Retenir » : un script que tu gardes pour tes pubs
    serie: str = ""  # scripts écrits ensemble par « Variantes… » : même identifiant de série
    lettre: str = ""  # A, B, C… dans la série
    mode: str = ""  # mode de la série (variantes.py) : « memes », « par_variante » ou « accroches »
    origine: str = ""  # identifiant du script retouché ou dupliqué
    consigne_retouche: str = ""  # consigne de la retouche (vide pour une simple copie)

    @staticmethod
    def nouvel_identifiant() -> str:
        return uuid.uuid4().hex[:12]

    def nom(self) -> str:
        """« Script 3 », ou « Script 5 (variante B) » pour un script d'une série de variantes."""
        nom = f"Script {self.numero}" if self.numero else "Script"
        return f"{nom} (variante {self.lettre})" if self.lettre else nom

    def texte_api(self) -> str:
        """Texte envoyé à la voix, répliques séparées par un retour à la ligne (balises et accents)."""
        return "\n".join(texte_pour_api(r.script) for r in self.repliques if not est_vide(r.script))

    def accroche(self) -> str:
        """Texte de la réplique 1 (l'accroche), tel qu'il s'affiche."""
        return texte_brut(self.repliques[0].script).strip() if self.repliques else ""

    def duree_estimee(self, mots_par_seconde: float = MOTS_PAR_SECONDE) -> float:
        """Durée estimée avec la même formule que le module Voix, balises comprises.
        `mots_par_seconde` : vitesse de la voix du projet, mesurée sur tes prises (vitesses.py)."""
        return sum(duree_parlee(texte_pour_api(r.script), mots_par_seconde) for r in self.repliques)

    def nombre_de_mots(self) -> int:
        return sum(len(re.findall(r"\w+", texte_brut(r.script))) for r in self.repliques)

    def points(self, gravite: str) -> list[PointRelecture]:
        return [p for p in self.relecture if p.gravite == gravite]

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, brut) -> ScriptEcrit | None:
        if not isinstance(brut, dict) or not isinstance(brut.get("repliques"), list):
            return None
        repliques = [r for r in (RepliqueEcrite.depuis_dict(b) for b in brut["repliques"]) if r is not None]
        if not repliques:
            return None
        return cls(
            identifiant=str(brut.get("identifiant") or cls.nouvel_identifiant()),
            date=str(brut.get("date") or ""),
            modele=str(brut.get("modele") or ""),
            reseau=str(brut.get("reseau") or ""),
            langue=str(brut.get("langue") or ""),
            angle=str(brut.get("angle") or ""),
            duree_visee_s=_entier(brut.get("duree_visee_s")),
            repliques=repliques,
            tutoiement=str(brut.get("tutoiement") or "tu"),
            accroche_imposee=str(brut.get("accroche_imposee") or ""),
            balises=bool(brut.get("balises")),
            styles=bool(brut.get("styles", True)),
            accents=bool(brut.get("accents")),
            relecture=[p for p in (PointRelecture.depuis_dict(b) for b in brut.get("relecture") or []) if p],
            corrections=[str(c) for c in brut.get("corrections") or [] if str(c).strip()],
            tokens_entree=_entier(brut.get("tokens_entree")),
            tokens_sortie=_entier(brut.get("tokens_sortie")),
            cout_eur=None if brut.get("cout_eur") in (None, "") else str(brut["cout_eur"]),
            envoye_le=str(brut.get("envoye_le") or ""),
            garde_comme_exemple=bool(brut.get("garde_comme_exemple")),
            numero=max(0, _entier(brut.get("numero"))),
            note=min(max(_entier(brut.get("note")), 0), NOTE_MAX),
            retenu=bool(brut.get("retenu")),
            serie=str(brut.get("serie") or ""),
            lettre=str(brut.get("lettre") or "") if brut.get("serie") else "",
            mode=str(brut.get("mode") or "") if brut.get("serie") else "",
            origine=str(brut.get("origine") or ""),
            consigne_retouche=str(brut.get("consigne_retouche") or ""),
        )


# --- Conversion du texte du modèle -----------------------------------------------------------------


def segments_depuis_modele(texte: str, balises: bool = True, accents: bool = True) -> tuple[list[Segment], list[str]]:
    """Texte d'une réplique écrit par le modèle → segments, et ce qui a été retiré (pour la relecture).

    - « <laugh> » (ou son nom français) devient un badge ; une balise inconnue est retirée ;
    - « *tout* » devient un mot accentué (un seul par réplique) ;
    - balises ou accents non demandés sont retirés."""
    notes: list[str] = []
    propre = " ".join(texte.replace("\r", " ").split())
    # Guillemets droits autour de toute la réplique (le modèle en ajoute parfois).
    if len(propre) >= 2 and propre[0] == propre[-1] == '"':
        propre = propre[1:-1].strip()
    segments: list[Segment] = []
    accents_vus = 0
    for segment in depuis_texte(propre):
        if "balise" in segment:
            if balises:
                segments.append(segment)
            else:
                notes.append(f"Balise retirée (non demandée) : « {segment['balise']} »")
            continue
        morceau = segment["texte"]
        # Balises restantes : inconnues de l'app.
        for trouve in _BALISE_RESTANTE.finditer(morceau):
            if balise_depuis_nom(trouve.group(1)) is None:
                notes.append(f"Balise inconnue retirée : « <{trouve.group(1)}> »")
        morceau = _BALISE_RESTANTE.sub(lambda t: "" if balise_depuis_nom(t.group(1)) is None else t.group(0), morceau)
        position = 0
        for trouve in _ACCENT.finditer(morceau):
            segments.append({"texte": morceau[position : trouve.start()]})
            mot = trouve.group(1)
            if accents and accents_vus == 0:
                segments.append({"texte": mot, "accentue": True})
            else:
                segments.append({"texte": mot})
                if accents:
                    notes.append(f"Un seul mot accentué par réplique : « {mot} » ne l'est plus")
                else:
                    notes.append(f"Accentuation retirée (non demandée) : « {mot} »")
            accents_vus += 1
            position = trouve.end()
        segments.append({"texte": morceau[position:].replace("*", "")})
    resultat = normaliser(segments)
    # Espaces doublés laissés par une balise retirée.
    for segment in resultat:
        if "texte" in segment:
            segment["texte"] = re.sub(r"[ \t]{2,}", " ", segment["texte"])
    if resultat and "texte" in resultat[0]:
        resultat[0]["texte"] = resultat[0]["texte"].lstrip()
    if resultat and "texte" in resultat[-1]:
        resultat[-1]["texte"] = resultat[-1]["texte"].rstrip()
    return [s for s in resultat if "balise" in s or s.get("texte")], notes


def texte_pour_modele(segments: list[Segment]) -> str:
    """Segments → texte avec les conventions du modèle (« <laugh> », « *mot* ») : pour lui renvoyer
    un script à relire, ou pour un exemple."""
    morceaux = []
    for segment in segments:
        if "balise" in segment:
            morceaux.append(f"<{segment['balise']}>")
        elif segment.get("accentue"):
            morceaux.append(f"*{segment['texte']}*")
        else:
            morceaux.append(segment["texte"])
    return "".join(morceaux)


def repliques_depuis_reponse(
    brutes: list, balises: bool, styles: bool, accents: bool
) -> tuple[list[RepliqueEcrite], list[str]]:
    """Répliques de la réponse structurée du modèle → répliques de l'app, et ce qui a été retiré."""
    repliques: list[RepliqueEcrite] = []
    notes: list[str] = []
    for rang, brute in enumerate(brutes if isinstance(brutes, list) else [], start=1):
        if not isinstance(brute, dict):
            continue
        segments, retires = segments_depuis_modele(str(brute.get("texte") or ""), balises, accents)
        notes += [f"Réplique {rang} : {note}" for note in retires]
        if est_vide(segments):
            continue
        roles = [str(r) for r in brute.get("roles") or [] if str(r) in ROLES]
        style = " ".join(str(brute.get("style") or "").split()) if styles else ""
        style_fr = " ".join(str(brute.get("style_fr") or "").split()) if styles and style else ""
        repliques.append(RepliqueEcrite(roles, segments, style, style_fr))
    if repliques and "accroche" not in repliques[0].roles:
        repliques[0].roles.insert(0, "accroche")
    return repliques, notes


def repliques_pour_modele(repliques: list[RepliqueEcrite]) -> list[dict]:
    """Répliques telles que le modèle les écrit (pour la relecture)."""
    return [
        {"roles": list(r.roles), "texte": texte_pour_modele(r.script), "style": r.style, "style_fr": r.style_fr}
        for r in repliques
    ]


def nouveau_script(**valeurs) -> ScriptEcrit:
    return ScriptEcrit(identifiant=ScriptEcrit.nouvel_identifiant(), date=_maintenant(), **valeurs)


def dupliquer(script: ScriptEcrit) -> ScriptEcrit:
    """« Dupliquer » : une copie à modifier à la main, l'original reste tel quel. La copie ne coûte
    rien, ne fait partie d'aucune série et n'a encore été ni envoyée, ni notée, ni retenue."""
    copie = ScriptEcrit.depuis_dict(script.en_dict())
    assert copie is not None  # un script valide se relit toujours
    copie.identifiant = ScriptEcrit.nouvel_identifiant()
    copie.date = _maintenant()
    copie.numero = 0
    copie.tokens_entree = copie.tokens_sortie = 0
    copie.cout_eur = None
    copie.envoye_le = ""
    copie.garde_comme_exemple = False
    copie.note = 0
    copie.retenu = False
    copie.serie = copie.lettre = copie.mode = ""
    copie.origine = script.identifiant
    copie.consigne_retouche = ""
    return copie
