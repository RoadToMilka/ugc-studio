"""Générer une voix off pour le projet ouvert (§5.6) : du script à la prise enregistrée.

Étapes :
1. chaque réplique du script est transformée en texte pour l'API (balises, mots accentués en
   majuscules), puis le dictionnaire de prononciation y est appliqué (§5.2) ;
2. les répliques partent ensemble, chacune avec son style ; si c'est trop long pour une seule
   requête, elles sont réparties en plusieurs requêtes (§5.6 bis) et les audios sont recollés ;
3. la prise est rangée dans le dossier du projet, et le coût est noté dans le suivi des coûts.

La partie « appel réseau » (`produire_audio`) tourne en tâche de fond ; l'enregistrement de la
prise (`enregistrer_prise`) se fait ensuite dans la tâche principale.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .audio import FREQUENCE_TTS, concatener_wav, duree_wav, silence_pcm
from .estimation import TOKENS_AUDIO_PAR_SECONDE_DEFAUT, ajuster_tokens_par_seconde, regrouper
from .fournisseurs.base import Adaptateur
from .fournisseurs.voix import RecepteurAudio, Replique, RequeteVoix, ResultatVoix
from .projets import Prise, RepliqueProjet
from .prononciation import Prononciation, appliquer
from .script import est_vide, joindre_repliques, texte_pour_api
from .services import Services

PAUSE_ENTRE_MORCEAUX_S = 0.25
CLE_CALIBRAGE = "tokens_audio_par_seconde"


@dataclass(frozen=True)
class Commande:
    """Tout ce qu'il faut pour générer, figé au moment du clic sur « Générer »."""

    fournisseur: str
    modele: str
    voix: str
    repliques: tuple[Replique, ...]  # texte envoyé (prononciations appliquées) et style de chaque réplique
    script: list[dict]  # script complet d'origine (pour les sous-titres)
    projet: str | None = None
    operation: str = "voix"

    @property
    def texte_api(self) -> str:
        return "\n".join(r.texte for r in self.repliques)

    @property
    def style(self) -> str:
        """Style affiché avec la prise : le style commun, ou « styles par réplique »."""
        styles = {r.style for r in self.repliques}
        if len(styles) > 1:
            return "styles par réplique"
        return styles.pop() if styles else ""


def repliques_api(repliques: Sequence[RepliqueProjet], prononciations: Sequence[Prononciation] = ()) -> list[Replique]:
    """Répliques du projet → texte exact envoyé au TTS (répliques vides ignorées)."""
    return [
        Replique(appliquer(texte_pour_api(r.script), list(prononciations)), r.style.strip())
        for r in repliques
        if not est_vide(r.script)
    ]


def preparer(
    fournisseur: str,
    modele: str,
    voix: str,
    repliques: Sequence[RepliqueProjet],
    projet: str | None,
    prononciations: Sequence[Prononciation] = (),
) -> Commande:
    return Commande(
        fournisseur,
        modele,
        voix,
        tuple(repliques_api(repliques, prononciations)),
        joindre_repliques([r.script for r in repliques]),
        projet,
    )


def preparer_texte(fournisseur: str, modele: str, voix: str, texte: str, operation: str) -> Commande:
    """Commande pour une courte phrase (extrait d'une voix, essai de prononciation)."""
    return Commande(fournisseur, modele, voix, (Replique(texte),), [{"texte": texte}], None, operation)


def tokens_par_seconde(services: Services, modele: str) -> float:
    valeurs = services.preferences.lire(CLE_CALIBRAGE, {}) or {}
    try:
        return float(valeurs.get(modele, TOKENS_AUDIO_PAR_SECONDE_DEFAUT))
    except (TypeError, ValueError):
        return TOKENS_AUDIO_PAR_SECONDE_DEFAUT


def produire_audio(
    adaptateur: Adaptateur,
    commande: Commande,
    tokens_seconde: float,
    recevoir_audio: RecepteurAudio | None = None,
) -> ResultatVoix:
    """Appel(s) au fournisseur — à lancer en tâche de fond.

    `recevoir_audio` : écoute pendant la génération ; l'audio est alors demandé en flux et chaque
    morceau lui est transmis dès son arrivée (avec, entre deux requêtes d'un script long, le même
    silence que dans la prise recollée)."""
    groupes = regrouper(commande.repliques, tokens_seconde)
    resultats = []
    for index, groupe in enumerate(groupes):
        requete = RequeteVoix(commande.modele, commande.voix, groupe)
        if recevoir_audio is None:
            resultats.append(adaptateur.generer_voix(requete))
            continue
        if index:
            recevoir_audio(silence_pcm(PAUSE_ENTRE_MORCEAUX_S), FREQUENCE_TTS)
        resultats.append(adaptateur.generer_voix(requete, recevoir_audio=recevoir_audio))
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


def enregistrer_prise(
    services: Services, commande: Commande, resultat: ResultatVoix, serie: int = 0, variante: str = ""
) -> Prise:
    """Dans la tâche principale : coût noté, prise rangée dans le projet.

    `serie` et `variante` : pour une prise d'une série de variantes A/B (§5.6)."""
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
        repliques=[{"texte_api": r.texte, "style": r.style} for r in commande.repliques],
        serie=serie,
        variante=variante,
    )
