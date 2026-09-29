"""Générer une voix off pour le projet ouvert (§5.6) : du script à la prise enregistrée.

Étapes :
1. le script est transformé en texte pour l'API (balises, mots accentués en majuscules) ;
2. s'il est trop long pour une seule requête, il est découpé aux fins de phrases (§5.6 bis) ;
3. chaque morceau est envoyé au fournisseur ; les audios sont recollés ;
4. la prise est rangée dans le dossier du projet, et le coût est noté dans le suivi des coûts.

La partie « appel réseau » (`produire_audio`) tourne en tâche de fond ; l'enregistrement de la
prise (`enregistrer_prise`) se fait ensuite dans la tâche principale.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .audio import concatener_wav, duree_wav
from .estimation import TOKENS_AUDIO_PAR_SECONDE_DEFAUT, ajuster_tokens_par_seconde, decouper_si_trop_long
from .fournisseurs.base import Adaptateur
from .fournisseurs.voix import Replique, RequeteVoix, ResultatVoix
from .projets import Prise
from .script import texte_pour_api
from .services import Services

PAUSE_ENTRE_MORCEAUX_S = 0.25
CLE_CALIBRAGE = "tokens_audio_par_seconde"


@dataclass(frozen=True)
class Commande:
    """Tout ce qu'il faut pour générer, figé au moment du clic sur « Générer »."""

    fournisseur: str
    modele: str
    voix: str
    style: str
    script: list[dict]
    texte_api: str
    projet: str | None = None
    operation: str = "voix"


def preparer(fournisseur: str, modele: str, voix: str, style: str, script: list[dict], projet: str | None) -> Commande:
    return Commande(fournisseur, modele, voix, style.strip(), [dict(s) for s in script], texte_pour_api(script), projet)


def tokens_par_seconde(services: Services, modele: str) -> float:
    valeurs = services.preferences.lire(CLE_CALIBRAGE, {}) or {}
    try:
        return float(valeurs.get(modele, TOKENS_AUDIO_PAR_SECONDE_DEFAUT))
    except (TypeError, ValueError):
        return TOKENS_AUDIO_PAR_SECONDE_DEFAUT


def produire_audio(adaptateur: Adaptateur, commande: Commande, tokens_seconde: float) -> ResultatVoix:
    """Appel(s) au fournisseur — à lancer en tâche de fond."""
    morceaux = decouper_si_trop_long(commande.texte_api, tokens_seconde)
    resultats = [
        adaptateur.generer_voix(RequeteVoix(commande.modele, commande.voix, (Replique(texte, commande.style),)))
        for texte in morceaux
    ]
    if len(resultats) == 1:
        return resultats[0]
    wav = concatener_wav([r.audio_wav for r in resultats], PAUSE_ENTRE_MORCEAUX_S)
    return ResultatVoix(
        wav,
        duree_wav(wav),
        sum(r.tokens_entree for r in resultats),
        sum(r.tokens_sortie for r in resultats),
        {"morceaux": len(resultats)},
    )


def noter_cout(services: Services, commande: Commande, resultat: ResultatVoix) -> Decimal | None:
    """Note l'appel dans le suivi des coûts et affine l'estimation des tokens audio."""
    appel = services.couts.enregistrer(
        commande.fournisseur,
        commande.modele,
        commande.operation,
        resultat.tokens_entree,
        resultat.tokens_sortie,
        projet=commande.projet,
    )
    if resultat.tokens_sortie and resultat.duree_s > 0:
        valeurs = dict(services.preferences.lire(CLE_CALIBRAGE, {}) or {})
        valeurs[commande.modele] = ajuster_tokens_par_seconde(
            tokens_par_seconde(services, commande.modele), resultat.tokens_sortie, resultat.duree_s
        )
        services.preferences.ecrire(CLE_CALIBRAGE, valeurs)
        services.preferences.enregistrer()
    return appel.cout_eur


def enregistrer_prise(services: Services, commande: Commande, resultat: ResultatVoix) -> Prise:
    """Dans la tâche principale : coût noté, prise rangée dans le projet."""
    cout = noter_cout(services, commande, resultat)
    return services.projets.ajouter_prise(
        resultat.audio_wav,
        modele=commande.modele,
        voix=commande.voix,
        style=commande.style,
        texte_api=commande.texte_api,
        script=commande.script,
        duree_s=round(resultat.duree_s, 3),
        tokens_entree=resultat.tokens_entree,
        tokens_sortie=resultat.tokens_sortie,
        cout_eur=None if cout is None else format(cout, "f"),
    )
