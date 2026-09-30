"""Transcrire la source du projet ouvert (§6) : de la piste son aux mots horodatés.

Étapes :
1. si la source dépasse la limite de Google (30 min avec les temps des mots), elle est coupée en
   morceaux, chaque coupure étant placée dans un silence ;
2. chaque morceau est transcrit (fichier déposé chez Google, puis transcription) ; les temps des
   mots sont recalés sur le début du morceau ;
3. le dictionnaire de remplacements est appliqué, le coût est noté dans le suivi des coûts.

La partie « appels réseau » (`transcrire_source`) tourne en tâche de fond ; la suite
(`terminer_transcription`) se fait dans la tâche principale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from .alignement import aligner, mots_du_script
from .audio import OCTETS_PAR_ECHANTILLON, duree_wav, lire_wav, wav_depuis_pcm
from .audio_source import coupure_dans_un_silence, morceau_pcm
from .fournisseurs.base import Adaptateur
from .fournisseurs.capacites import TOKENS_AUDIO_PAR_SECONDE, TOKENS_TEXTE_PAR_MINUTE_TRANSCRITE
from .fournisseurs.stt import MODE_SMART, RequeteTranscription
from .prix import CataloguePrix
from .projets import FICHIER_AUDIO, Prise, Projet
from .prononciation import appliquer as remplacer_dans_le_texte
from .prononciation import Prononciation
from .script import texte_brut
from .services import Services
from .transcription import (
    DUREE_MAX_HORODATEE_S,
    DUREE_MAX_TEXTE_S,
    Mot,
    Remplacement,
    Transcription,
    appliquer_remplacements,
    decoupage,
    fusionner_remplacements,
    hesitations_pour,
)

OPERATION = "transcription"
MODELE_PAR_DEFAUT = "gemini-3.5-transcribe"
PREFERENCE_HESITATIONS = "hesitations"  # préférences de l'app : {code de langue : [mots]}


@dataclass(frozen=True)
class Options:
    modele: str
    langue: str = ""  # vide = détection automatique
    mode: str = "verbatim"
    separation_voix: bool = False
    fournisseur: str = "google"


@dataclass
class ResultatSource:
    texte: str
    mots: list[Mot] = field(default_factory=list)
    tokens_entree: int = 0
    tokens_sortie: int = 0
    morceaux: int = 1


def estimer_cout(duree_s: float, modele: str, prix: CataloguePrix):
    """Coût estimé avant de transcrire : ≈ 25 tokens par seconde d'audio en entrée, ≈ 175 tokens
    de texte par minute en sortie (ordre de grandeur de la page des tarifs de Google)."""
    entree = math.ceil(duree_s * TOKENS_AUDIO_PAR_SECONDE)
    sortie = math.ceil(duree_s / 60 * TOKENS_TEXTE_PAR_MINUTE_TRANSCRITE)
    return prix.cout_eur(modele, entree, sortie)


def transcrire_source(adaptateur: Adaptateur, wav: bytes, options: Options, nom: str = "audio") -> ResultatSource:
    """Appel(s) au fournisseur — à lancer en tâche de fond. `wav` : WAV 16 bits mono."""
    pcm, frequence, _canaux = lire_wav(wav)
    duree = len(pcm) / OCTETS_PAR_ECHANTILLON / frequence
    limite = DUREE_MAX_TEXTE_S if options.mode == MODE_SMART else DUREE_MAX_HORODATEE_S
    bornes = decoupage(duree, limite)
    coupures = [0.0, *(coupure_dans_un_silence(pcm, frequence, fin) for _debut, fin in bornes[:-1]), duree]
    textes: list[str] = []
    mots: list[Mot] = []
    resultat = ResultatSource("", morceaux=len(bornes))
    for numero, (debut, fin) in enumerate(zip(coupures, coupures[1:], strict=False), 1):
        morceau = wav if len(bornes) == 1 else wav_depuis_pcm(morceau_pcm(pcm, frequence, debut, fin), frequence)
        suffixe = f" ({numero}/{len(bornes)})" if len(bornes) > 1 else ""
        reponse = adaptateur.transcrire(
            RequeteTranscription(
                options.modele,
                morceau,
                "audio/wav",
                options.langue,
                options.mode,
                horodatage=options.mode != MODE_SMART,
                separation_voix=options.separation_voix and options.mode != MODE_SMART,
                nom=f"{nom}{suffixe}.wav",
            )
        )
        if reponse.texte:
            textes.append(reponse.texte)
        mots += [Mot(m.texte, round(m.debut + debut, 3), round(m.fin + debut, 3), m.locuteur) for m in reponse.mots]
        resultat.tokens_entree += reponse.tokens_entree
        resultat.tokens_sortie += reponse.tokens_sortie
    resultat.texte = "\n".join(textes)
    resultat.mots = mots
    return resultat


def appliquer_dictionnaire(resultat: ResultatSource, entrees: list[Remplacement]) -> ResultatSource:
    """Dictionnaire de remplacements : sur les mots horodatés, et sur le texte complet."""
    if not entrees:
        return resultat
    texte = remplacer_dans_le_texte(resultat.texte, [Prononciation(e.cherche, e.remplace) for e in entrees])
    return ResultatSource(
        texte,
        appliquer_remplacements(resultat.mots, entrees),
        resultat.tokens_entree,
        resultat.tokens_sortie,
        resultat.morceaux,
    )


def langue_de(transcription: Transcription | None, projet: Projet | None) -> str:
    """Langue de la transcription (celle choisie à l'envoi), sinon celle du projet."""
    if transcription is not None and transcription.langue:
        return transcription.langue
    return projet.langue if projet is not None else "fr-FR"


def hesitations(services: Services, transcription: Transcription | None) -> set[str]:
    """Hésitations (« euh »…) de la langue de la transcription, telles que réglées dans l'app."""
    personnalisees = services.preferences.lire(PREFERENCE_HESITATIONS, {}) or {}
    return hesitations_pour(langue_de(transcription, services.projets.projet), personnalisees)


def transcription_de_prise(projet: Projet, prise: Prise) -> tuple[Transcription, bytes]:
    """Prépare les sous-titres d'une prise TTS (§3.3) : sa transcription, à aligner sur son script,
    et son audio (WAV 24 kHz mono, envoyé tel quel ; rangé dans « sources » une fois transcrit)."""
    wav = projet.chemin(prise.fichier).read_bytes()
    transcription = Transcription(
        source=prise.nom,
        audio=FICHIER_AUDIO,
        duree_s=round(duree_wav(wav), 3),
        infos={"duree_s": round(duree_wav(wav), 3), "video": False},
        langue=projet.langue,
        prise=prise.identifiant,
        script=texte_brut(prise.script),
    )
    return transcription, wav


def terminer_transcription(
    services: Services, transcription: Transcription, options: Options, resultat: ResultatSource
) -> Transcription:
    """Dans la tâche principale : remplacements, alignement sur le script (prise TTS), coût noté,
    transcription rangée dans le projet."""
    projet = services.projets.projet
    entrees = fusionner_remplacements(services.remplacements.entrees, projet.remplacements if projet else [])
    resultat = appliquer_dictionnaire(resultat, entrees)
    if transcription.script and resultat.mots:
        # Prise TTS (§3.3) : les mots gardent l'orthographe exacte du script, avec les temps transcrits.
        resultat.mots = aligner(mots_du_script(transcription.script), resultat.mots)
    appel = services.couts.enregistrer(
        options.fournisseur,
        options.modele,
        OPERATION,
        resultat.tokens_entree,
        resultat.tokens_sortie,
        projet=projet.nom if projet else None,
    )
    transcription.modele = options.modele
    transcription.langue = options.langue
    transcription.mode = options.mode
    transcription.separation_voix = options.separation_voix
    transcription.texte = resultat.texte
    transcription.mots = resultat.mots
    transcription.date = datetime.now().astimezone().isoformat(timespec="seconds")
    transcription.cout_eur = None if appel.cout_eur is None else format(appel.cout_eur, "f")
    if projet is not None:
        projet.transcription = transcription
        services.projets.enregistrer()
    return transcription
