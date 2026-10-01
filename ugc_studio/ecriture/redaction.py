"""Enchaînement des appels au modèle de texte (V2, §10.4 à §10.8) et estimation de leur coût.

Toutes les fonctions qui appellent le modèle sont à lancer en tâche de fond. `signaler(x)` donne
des nouvelles en cours de route : un texte (l'étape en cours, ex. « Relecture du script… ») ou un
Appel terminé, pour que son coût soit noté tout de suite dans le suivi des coûts, même si l'étape
suivante échoue.

Niveau de réflexion du modèle (§10.12) : bas pour l'analyse de la page, moyen pour les accroches,
l'écriture et la relecture (plus de réflexion coûte plus cher, rarement mieux pour un texte
court). Température : celle par défaut, comme le recommande Google pour Gemini 3.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from ..fournisseurs.base import Adaptateur, ErreurFournisseur
from ..fournisseurs.texte import RequeteTexte, ResultatTexte
from .brief import ANGLES_ANGLAIS, Brief, mots_vises
from .consignes import (
    CONSIGNE_SYSTEME,
    SCHEMA_ACCROCHES,
    SCHEMA_RELECTURE,
    SCHEMA_SCRIPT,
    demande_accroches,
    demande_fiche,
    demande_fiche_par_adresse,
    demande_relecture,
    demande_script,
)
from .controles import controler, mentions_absentes, mots_interdits_presents, points_graves
from .exemples import ExempleScript, texte_des_exemples
from .fiche import SCHEMA_FICHE, FicheProduit, lire_fiche
from .page_produit import GOOGLE, ErreurLecture, PageLue, maintenant
from .scripts import (
    Accroche,
    PointRelecture,
    ScriptEcrit,
    nouveau_script,
    repliques_depuis_reponse,
    repliques_pour_modele,
)

# Opérations notées dans le suivi des coûts (§4.3).
LECTURE = "script : lecture de page"
ACCROCHES = "script : accroches"
ECRITURE = "script : écriture"
RELECTURE = "script : relecture"

REFLEXION_FICHE = "low"
REFLEXION_ECRITURE = "medium"
DELAI_ECRITURE = 180  # secondes : un modèle qui réfléchit sur une longue demande peut prendre du temps
DELAI_LECTURE_GOOGLE = 180

# Pour estimer un coût AVANT de lancer : tokens produits (texte de la réponse), plus la réflexion.
CARACTERES_PAR_TOKEN = 4
SORTIE_FICHE = 700
SORTIE_PAR_ACCROCHE = 60
SORTIE_SCRIPT = 700
SORTIE_RELECTURE = 900  # la relecture renvoie parfois le script corrigé
REFLEXION_ESTIMEE = {"low": 400, "medium": 1500, "high": 4000}
PAGE_LUE_PAR_GOOGLE = 8_000  # tokens d'une page produit lue par Google (comptés en entrée)

MESSAGES_STATUTS_GOOGLE = {
    "paywall": "La page est réservée (abonnement ou connexion) : Google ne peut pas la lire.",
    "unsafe": "Google a refusé de lire cette page (jugée dangereuse).",
}


@dataclass(frozen=True)
class Appel:
    """Un appel au modèle, pour le suivi des coûts."""

    operation: str
    modele: str
    tokens_entree: int
    tokens_sortie: int


@dataclass(frozen=True)
class Estimation:
    tokens_entree: int
    tokens_sortie: int

    def __add__(self, autre: Estimation) -> Estimation:
        return Estimation(self.tokens_entree + autre.tokens_entree, self.tokens_sortie + autre.tokens_sortie)


class ErreurRedaction(Exception):
    """Réponse du modèle inutilisable, avec un message clair pour l'utilisateur."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


Signaleur = Callable[[object], None]


def _rien(_nouvelle: object) -> None:
    pass


# --- Appels et réponses ----------------------------------------------------------------------------


def _appeler(adaptateur: Adaptateur, requete: RequeteTexte, operation: str, signaler: Signaleur) -> ResultatTexte:
    resultat = adaptateur.generer_texte(requete)
    signaler(Appel(operation, requete.modele, resultat.tokens_entree, resultat.tokens_sortie))
    return resultat


def lire_json_du_modele(texte: str) -> dict:
    """Objet JSON de la réponse structurée (tolère des ``` autour, que certains modèles ajoutent)."""
    propre = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", texte.strip())
    try:
        donnees = json.loads(propre)
    except ValueError as erreur:
        raise ErreurRedaction("Le modèle a renvoyé une réponse illisible. Réessaie dans un instant.") from erreur
    if not isinstance(donnees, dict):
        raise ErreurRedaction("Le modèle a renvoyé une réponse illisible. Réessaie dans un instant.")
    return donnees


def _requete(modele: str, texte: str, schema: dict, reflexion: str = REFLEXION_ECRITURE, **options) -> RequeteTexte:
    return RequeteTexte(
        modele, texte, consigne_systeme=CONSIGNE_SYSTEME, reflexion=reflexion, schema=schema, delai=DELAI_ECRITURE,
        **options,
    )


# --- Estimations -----------------------------------------------------------------------------------


def estimer(requete: RequeteTexte, sortie: int) -> Estimation:
    """Tokens d'une demande avant de l'envoyer (environ 1 token pour 4 caractères), réflexion comprise."""
    caracteres = len(requete.texte) + len(requete.consigne_systeme) + len(json.dumps(requete.schema or {}))
    return Estimation(math.ceil(caracteres / CARACTERES_PAR_TOKEN), sortie + REFLEXION_ESTIMEE.get(requete.reflexion, 0))


def estimer_lecture(texte_page: str, modele: str, langue: str) -> Estimation:
    """Analyse d'une page lue par l'app (ou d'un texte collé)."""
    requete = _requete(modele, demande_fiche(texte_page, "", langue), SCHEMA_FICHE, REFLEXION_FICHE)
    return estimer(requete, SORTIE_FICHE)


def estimer_lecture_par_google(adresse: str, modele: str, langue: str) -> Estimation:
    requete = _requete(modele, demande_fiche_par_adresse(adresse, langue), SCHEMA_FICHE, REFLEXION_FICHE)
    return estimer(requete, SORTIE_FICHE) + Estimation(PAGE_LUE_PAR_GOOGLE, 0)


def estimer_accroches(brief: Brief, page: str, exemples: list[ExempleScript]) -> Estimation:
    requete = requete_accroches(brief, page, exemples)
    return estimer(requete, SORTIE_PAR_ACCROCHE * brief.nombre_accroches)


def estimer_script(brief: Brief, page: str, exemples: list[ExempleScript], accroche: str = "") -> Estimation:
    """Écriture, puis relecture (la relecture renvoie le script et une demande un peu plus longue)."""
    ecriture = estimer(requete_script(brief, page, exemples, accroche), SORTIE_SCRIPT)
    relecture = Estimation(ecriture.tokens_entree + SORTIE_SCRIPT, SORTIE_RELECTURE + REFLEXION_ESTIMEE[REFLEXION_ECRITURE])
    return ecriture + relecture


# --- Page produit ----------------------------------------------------------------------------------


def analyser_page(
    adaptateur: Adaptateur, modele: str, page: PageLue, langue: str, signaler: Signaleur = _rien
) -> FicheProduit:
    """Fiche « Ce que l'app a compris » d'une page lue par l'app (ou d'un texte collé)."""
    signaler("Analyse de la page par le modèle…")
    requete = _requete(modele, demande_fiche(page.texte, page.source, langue), SCHEMA_FICHE, REFLEXION_FICHE)
    resultat = _appeler(adaptateur, requete, LECTURE, signaler)
    try:
        return lire_fiche(resultat.texte, page)
    except ValueError as erreur:
        raise ErreurRedaction("Le modèle a renvoyé une réponse illisible. Réessaie dans un instant.") from erreur


def lire_par_google(
    adaptateur: Adaptateur, modeles: list[str], adresse: str, langue: str, signaler: Signaleur = _rien
) -> tuple[PageLue, FicheProduit]:
    """Google lit la page (outil « URL context ») et remplit la fiche dans la même demande.

    `modeles` : le modèle choisi d'abord, puis ceux qui savent aussi lire les pages. Si Google
    refuse la demande avec un modèle (outil non disponible pour lui), le suivant essaie."""
    erreur_precedente: ErreurFournisseur | None = None
    for rang, modele in enumerate(modeles):
        requete = RequeteTexte(
            modele,
            demande_fiche_par_adresse(adresse, langue),
            consigne_systeme=CONSIGNE_SYSTEME,
            reflexion=REFLEXION_FICHE,
            schema=SCHEMA_FICHE,
            lire_adresses=True,
            delai=DELAI_LECTURE_GOOGLE,
        )
        try:
            resultat = _appeler(adaptateur, requete, LECTURE, signaler)
        except ErreurFournisseur as erreur:
            if erreur.code == "requete" and rang < len(modeles) - 1:
                erreur_precedente = erreur
                continue
            raise
        lues = resultat.adresses_lues
        if lues and not any(a.reussie for a in lues):
            statut = lues[0].statut
            raise ErreurLecture(
                MESSAGES_STATUTS_GOOGLE.get(statut, f"Google n'a pas pu lire la page (statut « {statut} »)."), "google"
            )
        try:
            fiche = lire_fiche(resultat.texte)
        except ValueError as erreur:
            raise ErreurRedaction("Le modèle a renvoyé une réponse illisible. Réessaie dans un instant.") from erreur
        if not fiche.nom and not fiche.benefices:
            raise ErreurLecture("Google n'a rien trouvé d'utilisable sur cette page.", "google")
        page = PageLue(
            adresse=adresse,
            source=GOOGLE,
            lu_le=maintenant(),
            texte=fiche.en_texte(),
            nom=fiche.nom,
            marque=fiche.marque,
            prix=fiche.prix,
            prix_barre=fiche.prix_barre,
        )
        return page, fiche
    assert erreur_precedente is not None
    raise erreur_precedente


# --- Accroches -------------------------------------------------------------------------------------


def _autre_langue(exemples: list[ExempleScript], brief: Brief) -> bool:
    langue = brief.langue.split("-")[0]
    return bool(exemples) and all(e.langue.split("-")[0] != langue for e in exemples)


def requete_accroches(brief: Brief, page: str, exemples: list[ExempleScript]) -> RequeteTexte:
    texte = demande_accroches(brief, page, texte_des_exemples(exemples, brief), _autre_langue(exemples, brief))
    return _requete(brief.modele, texte, SCHEMA_ACCROCHES)


def proposer_accroches(
    adaptateur: Adaptateur, brief: Brief, page: str, exemples: list[ExempleScript], signaler: Signaleur = _rien
) -> list[Accroche]:
    signaler("Le modèle cherche des accroches…")
    resultat = _appeler(adaptateur, requete_accroches(brief, page, exemples), ACCROCHES, signaler)
    donnees = lire_json_du_modele(resultat.texte)
    accroches = [a for a in (Accroche.depuis_dict(b) for b in donnees.get("accroches") or []) if a is not None]
    if not accroches:
        raise ErreurRedaction("Le modèle n'a proposé aucune accroche. Réessaie dans un instant.")
    return accroches[: brief.nombre_accroches]


# --- Écriture et relecture -------------------------------------------------------------------------


def requete_script(brief: Brief, page: str, exemples: list[ExempleScript], accroche: str = "") -> RequeteTexte:
    texte = demande_script(brief, page, texte_des_exemples(exemples, brief), accroche, _autre_langue(exemples, brief))
    return _requete(brief.modele, texte, SCHEMA_SCRIPT)


def constats_pour_le_modele(script: ScriptEcrit, brief: Brief) -> list[str]:
    """Problèmes graves mesurés par l'app, écrits pour le modèle (en anglais)."""
    constats = []
    visee = script.duree_visee_s
    estimee = script.duree_estimee()
    if visee > 0 and abs(estimee - visee) / visee > 0.15:
        cible = mots_vises(visee)
        sens = "shorten" if estimee > visee else "lengthen"
        constats.append(
            f"Estimated duration {round(estimee)} s for {visee} s targeted ({script.nombre_de_mots()} words): {sens} "
            f"the script to about {cible} words."
        )
    interdits = mots_interdits_presents(script, brief)
    if interdits:
        constats.append("Forbidden words used: " + ", ".join(interdits) + ".")
    absentes = mentions_absentes(script, brief)
    if absentes:
        constats.append("Mandatory mentions missing (add them word for word): " + " | ".join(absentes) + ".")
    return constats


def ecrire_script(
    adaptateur: Adaptateur,
    brief: Brief,
    page: str,
    exemples: list[ExempleScript],
    accroche: str = "",
    signaler: Signaleur = _rien,
) -> ScriptEcrit:
    """Écrit un script complet, le relit (app, puis modèle) et le corrige si un point est grave."""
    signaler("Écriture du script…")
    resultat = _appeler(adaptateur, requete_script(brief, page, exemples, accroche), ECRITURE, signaler)
    donnees = lire_json_du_modele(resultat.texte)
    repliques, retraits = repliques_depuis_reponse(donnees.get("repliques"), brief.balises, brief.styles, brief.accents)
    if not repliques:
        raise ErreurRedaction("Le modèle n'a renvoyé aucune réplique. Réessaie dans un instant.")
    angle = str(donnees.get("angle") or "")
    script = nouveau_script(
        modele=brief.modele,
        reseau=brief.reseau,
        langue=brief.langue,
        angle=angle if angle in ANGLES_ANGLAIS else (brief.angle if brief.angle != "auto" else ""),
        duree_visee_s=brief.duree_visee(),
        repliques=repliques,
        tutoiement=brief.tutoiement_effectif(),
        accroche_imposee=accroche,
        balises=brief.balises,
        styles=brief.styles,
        accents=brief.accents,
        tokens_entree=resultat.tokens_entree,
        tokens_sortie=resultat.tokens_sortie,
    )

    signaler("Relecture du script…")
    texte_relecture = demande_relecture(brief, page, repliques_pour_modele(script.repliques), constats_pour_le_modele(script, brief))
    relecture = _appeler(adaptateur, _requete(brief.modele, texte_relecture, SCHEMA_RELECTURE), RELECTURE, signaler)
    script.tokens_entree += relecture.tokens_entree
    script.tokens_sortie += relecture.tokens_sortie
    avis = lire_json_du_modele(relecture.texte)
    corrige = False
    if avis.get("corrige"):
        corrigees, retraits_corriges = repliques_depuis_reponse(avis.get("repliques"), brief.balises, brief.styles, brief.accents)
        if corrigees:
            script.repliques, retraits, corrige = corrigees, retraits_corriges, True
            script.corrections = [" ".join(str(c).split()) for c in avis.get("corrections") or [] if str(c).strip()]
            if not script.corrections:
                script.corrections = ["Script corrigé à la relecture."]
    points_modele = []
    for brut in avis.get("points") or []:
        point = PointRelecture.depuis_dict({**brut, "par": "modele"}) if isinstance(brut, dict) else None
        if point is None or (corrige and point.gravite == "grave"):
            continue  # un point grave corrigé est décrit dans les corrections
        points_modele.append(point)
    script.relecture = controler(script, brief, retraits) + points_modele
    return script


def reste_grave(script: ScriptEcrit) -> bool:
    """Un point grave reste-t-il après la relecture (ex. durée encore trop éloignée de la cible) ?"""
    return bool(points_graves(script.relecture))
