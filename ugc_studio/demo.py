"""Données de démonstration, utilisées uniquement par l'autotest de la fabrication automatique.

Elles remplissent un dossier temporaire (jamais les vraies données) pour que les captures
d'écran montrent des écrans réalistes : deux clés, quelques appels payants, un projet avec
un script, des prises et une série de variantes A/B ; dans le module Script, des scripts (dont une
série « Accroches seulement » et une retouche), deux briefs enregistrés et deux exemples gardés.
"""

from __future__ import annotations

import math
import struct
from dataclasses import replace
from datetime import datetime, timedelta

from .fournisseurs.voix import VoixBibliotheque

from .audio import FREQUENCE_TTS, wav_depuis_pcm
from .chemins import dossier_projets_defaut
from .ecriture.brief import Brief
from .ecriture.controles import controler
from .ecriture.etat import EtatScript
from .ecriture.exemples import EXEMPLES_FOURNIS
from .ecriture.fiche import FicheProduit
from .ecriture.page_produit import SHOPIFY, PageLue
from .ecriture.briefs import nom_propose
from .ecriture.exemples import ExempleScript, exemple_colle
from .ecriture.redaction import variantes_d_accroches
from .ecriture.scripts import (
    Accroche,
    PointRelecture,
    dupliquer,
    nouveau_script,
    repliques_depuis_reponse,
    repliques_pour_modele,
)
from .generation import repliques_api
from .projets import DOSSIER_SOURCES, RepliqueProjet
from .prononciation import Prononciation
from .script import joindre_repliques
from .services import Services
from .transcription import Mot, Remplacement, Transcription

CLE_DEMO = "AIzaDEMO-cle-de-demonstration-0000-4f2c"

# Deux répliques : un hook enthousiaste, puis un appel à l'action chaleureux.
REPLIQUES_DEMO = [
    RepliqueProjet(
        [
            {"texte": "Franchement, je n'y croyais pas… "},
            {"balise": "short pause"},
            {"texte": " Mais ce sérum Glowzy a "},
            {"texte": "vraiment", "accentue": True},
            {"texte": " changé ma peau en deux semaines ! "},
            {"balise": "laugh"},
        ],
        "excited and playful, fast-paced",
        "excité et complice, débit rapide",
    ),
    RepliqueProjet([{"texte": "Le lien est juste en dessous."}], "warm and reassuring", "chaleureux et rassurant"),
]
SCRIPT_DEMO = REPLIQUES_DEMO[0].script  # 1re réplique (vérifiée par l'autotest dans l'éditeur)

# Transcription de démonstration (§6) : une vidéo verticale, avec une hésitation (« euh »).
MOTS_DEMO = (
    "Franchement, euh je n'y croyais pas… Mais ce Sérum Glowzy a vraiment changé ma peau "
    "en deux semaines ! Le lien est juste en dessous."
).split()
DUREE_TRANSCRIPTION_DEMO = 7.4


def transcription_demo() -> Transcription:
    pas = DUREE_TRANSCRIPTION_DEMO / (len(MOTS_DEMO) + 1)
    mots = [Mot(texte, round(0.2 + i * pas, 3), round(0.2 + i * pas + pas * 0.85, 3)) for i, texte in enumerate(MOTS_DEMO)]
    return Transcription(
        source="Vidéos/pub-glowzy-v1.mp4",
        audio=f"{DOSSIER_SOURCES}/audio.wav",
        duree_s=DUREE_TRANSCRIPTION_DEMO,
        infos={"duree_s": DUREE_TRANSCRIPTION_DEMO, "video": True, "resolution": [1080, 1920], "images_par_seconde": 30, "codec_video": "H264"},
        modele="gemini-3.5-transcribe",
        langue="fr-FR",
        texte=" ".join(MOTS_DEMO),
        mots=mots,
        date=datetime.now().astimezone().replace(microsecond=0).isoformat(),
        cout_eur="0.0019",
    )


ADRESSE_DEMO = "https://glowzy.example/products/serum-eclat"


def ecriture_demo() -> EtatScript:
    """Module Script (V2) : page lue, brief pré-rempli, 6 accroches (2 cochées) et 2 scripts relus,
    dont un envoyé dans le module Voix."""
    maintenant = datetime.now().astimezone().replace(microsecond=0)
    brief = Brief(
        prix="",
        promo="Code GLOW20 : 20 % de remise",
        appel_action="Clique sur le lien en dessous",
        mentions="Code GLOW20",
        balises=True,
        styles=True,
    )
    fiche = FicheProduit(
        nom="Sérum éclat Glowzy",
        marque="Glowzy",
        type_produit="Sérum visage",
        prix="29,90 €",
        offre="Livraison offerte dès 25 € ; satisfaite ou remboursée pendant 30 jours",
        benefices=["Teint plus lumineux dès le matin", "Texture fluide qui ne colle pas", "3 gouttes suffisent"],
        distinction="Un sérum éclat léger, seul ou sous le maquillage.",
        problemes=["Teint terne et fatigué"],
        objections=["Peur que ça colle", "Le prix"],
        preuves=["4,7/5 sur 1 280 avis"],
        clientele="Femmes de 25 à 40 ans",
        noms_a_prononcer=["Glowzy"],
    )
    brief.pre_remplir(fiche.valeurs_du_brief())
    brief.pre_remplir({"genre": "femme"})
    page = PageLue(
        ADRESSE_DEMO,
        SHOPIFY,
        (maintenant - timedelta(minutes=25)).isoformat(),
        "Données de la boutique (Shopify, exactes) :\n- Nom : Sérum éclat Glowzy\n- Marque : Glowzy\n- Prix : 29,90 €",
        nom="Sérum éclat Glowzy",
        marque="Glowzy",
        prix="29,90 €",
        devise="EUR",
    )
    accroches = [
        Accroche("J'ai arrêté le fond de teint la semaine dernière.", "temoignage",
                 "Surprend : on attend du maquillage, c'est l'inverse.", cochee=True),
        Accroche("Trois gouttes, et ma sœur m'a demandé ce que j'avais changé.", "temoignage",
                 "La preuve vient d'une autre personne.", cochee=True),
        Accroche("POV : ton teint a l'air d'avoir dormi huit heures.", "pov", "Projette dans le résultat."),
        Accroche("Tu as le teint terne le matin ?", "probleme_solution", "Question directe sur un souci courant.",
                 "Sur Facebook et Instagram, Meta refuse une question qui suppose une caractéristique de la personne."),
        Accroche("Le sérum que je mets avant même mon café.", "routine", "Ancre le produit dans un geste du matin."),
        Accroche("Trois raisons pour lesquelles je ne sors plus sans lui.", "liste", "La liste retient l'attention."),
    ]
    glowzy = EXEMPLES_FOURNIS[0]
    premier, _notes = repliques_depuis_reponse(glowzy.repliques, True, True, False)
    second, _notes = repliques_depuis_reponse(
        [
            {"roles": ["accroche"], "texte": "Trois gouttes, et ma sœur m'a demandé ce que j'avais changé.",
             "style": "amused and intrigued", "style_fr": "amusée et intriguée"},
            {"roles": ["solution", "preuve"],
             "texte": "C'est le sérum éclat Glowzy. Je le mets le matin, ça pénètre direct, ça colle pas, et mon teint a "
             "l'air reposé. Il a 4,7 sur 5 sur plus de mille avis, donc c'est pas que moi. <chuckle>",
             "style": "warm and natural, like talking to a friend", "style_fr": "chaleureuse et naturelle, comme à une amie"},
            {"roles": ["offre", "appel_action"], "texte": "Avec mon code GLOW20, t'as 20 % en moins. Clique sur le lien en dessous.",
             "style": "upbeat and direct", "style_fr": "enjouée et directe"},
        ],
        True, True, False,
    )
    etat = EtatScript(brief=brief, adresse=ADRESSE_DEMO, page=page, fiche=fiche, accroches=accroches)
    for repliques, accroche, quand, cout, envoye, points, corrections in (
        (premier, accroches[0].texte, 44, "0.0161", True,
         [PointRelecture("produit_3s", "leger", "Le produit n'est nommé qu'à la réplique 2, vers 6 secondes.", "modele")], []),
        (second, accroches[1].texte, 41, "0.0174", False, [],
         ["« Résultat garanti dès le premier jour » remplacé par « mon teint a l'air reposé » (promesse invérifiable)."]),
    ):
        script = nouveau_script(
            modele="gemini-3.8-flash", reseau="tiktok", langue="fr-FR", angle="temoignage", duree_visee_s=25,
            repliques=repliques, tutoiement="tu", accroche_imposee=accroche, balises=True, styles=True,
            tokens_entree=9_430, tokens_sortie=4_220, cout_eur=cout,
        )
        script.date = (maintenant - timedelta(minutes=quand)).isoformat()
        script.envoye_le = (maintenant - timedelta(minutes=quand - 2)).isoformat() if envoye else ""
        script.corrections = corrections
        script.relecture = controler(script, brief) + points
        etat.ajouter(script)
    premier_script, second_script = etat.scripts
    premier_script.note, premier_script.retenu = 4, True

    # Lot 2 : une série « Accroches seulement » (même corps que le script 2, trois accroches) et une
    # retouche « plus court » du script 1.
    serie = "serie-demo"
    autres = [
        Accroche("POV : ton teint a l'air d'avoir dormi huit heures.", "pov", alerte=""),
        Accroche("Le sérum que je mets avant même mon café.", "routine",
                 alerte="Évite de promettre un résultat immédiat dans la suite du script."),
    ]
    variantes = [dupliquer(second_script), *variantes_d_accroches(second_script, autres, brief)]
    for lettre, (variante, note) in zip("ABC", zip(variantes, (0, 5, 3)), strict=True):
        variante.origine = ""
        variante.serie, variante.lettre, variante.mode = serie, lettre, "accroches"
        variante.cout_eur, variante.note = "0.0068", note
        variante.date = (maintenant - timedelta(minutes=30)).isoformat()
        variante.relecture = variante.relecture or controler(variante, brief)
        etat.ajouter(variante)
    retouche, _notes = repliques_depuis_reponse(
        [
            {"roles": ["accroche"], "texte": "J'ai arrêté le fond de teint.", "style": "intrigued and conspiratorial",
             "style_fr": "intriguée et complice"},
            {"roles": ["solution", "offre", "appel_action"],
             "texte": "Trois gouttes de sérum Glowzy le matin, et mon teint a l'air reposé. Avec mon code GLOW20, t'as "
             "20 % en moins. Clique sur le lien en dessous.",
             "style": "warm and upbeat", "style_fr": "chaleureuse et enjouée"},
        ],
        True, True, False,
    )
    court = nouveau_script(
        modele="gemini-3.8-flash", reseau="tiktok", langue="fr-FR", angle="temoignage", duree_visee_s=12,
        repliques=retouche, tutoiement="tu", balises=True, styles=True, cout_eur="0.0119",
        origine=premier_script.identifiant, consigne_retouche="Plus court",
    )
    court.date = (maintenant - timedelta(minutes=12)).isoformat()
    court.relecture = controler(court, brief)
    etat.ajouter(court)
    return etat


def son_de_demonstration(secondes: float, frequence: float = 220.0) -> bytes:
    """Petit son doux (WAV) pour les prises de démonstration."""
    total = int(secondes * FREQUENCE_TTS)
    fondu = FREQUENCE_TTS // 20
    echantillons = bytearray()
    for i in range(total):
        volume = min(1.0, i / fondu, (total - i) / fondu) * 0.2
        echantillons += struct.pack("<h", int(volume * 32767 * math.sin(2 * math.pi * frequence * i / FREQUENCE_TTS)))
    return wav_depuis_pcm(bytes(echantillons))


# Bibliothèque de voix de démonstration (noms marqués « démo » : ce ne sont pas de vraies voix Google).
VOIX_DEMO = [
    VoixBibliotheque("demo-camille", "Camille (démo)", "Warm and friendly narrator with a clear, smiling delivery.",
                     "fr-FR", "FR", "Parisian", "female", "medium", "Warm, Friendly", "Commercial"),
    VoixBibliotheque("demo-hugo", "Hugo (démo)", "Deep, confident voice for premium product launches.",
                     "fr-FR", "FR", "Standard French", "male", "low", "Confident", "Narration"),
    VoixBibliotheque("demo-ines", "Inès (démo)", "Bright and playful voice, perfect for social media hooks.",
                     "fr-FR", "FR", "Southern French", "female", "high", "Playful", "Social media"),
    VoixBibliotheque("demo-lucas", "Lucas (démo)", "Relaxed, conversational voice with a soft Belgian accent.",
                     "fr-BE", "BE", "Belgian", "male", "medium", "Friendly", "Conversational"),
    VoixBibliotheque("demo-ava", "Ava (démo)", "Energetic American voice for upbeat ads.",
                     "en-US", "US", "American", "female", "medium", "Energetic", "Commercial"),
]
VOIX_CREEE_DEMO = VoixBibliotheque(
    "voice_demo_lea",
    "Léa, créatrice UGC (démo)",
    "A young woman in her mid-20s with a warm, slightly husky voice and a Parisian French accent. "
    "Spontaneous and playful, like a creator talking to a friend on camera.",
    "fr-FR",
    genre="female",
    type="prompted",
    modele="gemini-3.8-flash-tts",
)


def remplir_donnees_demo(services: Services) -> None:
    connexions = services.connexions
    if not connexions.lister():
        perso = connexions.ajouter("google", "Google perso", CLE_DEMO)
        connexions.enregistrer_test(
            perso.identifiant,
            True,
            "Clé valide, 42 modèles accessibles.",
            [
                "gemini-3.8-flash-tts",
                "gemini-3.8-flash-lite-tts",
                "gemini-3.5-transcribe",
                "gemini-3.5-transcribe-live",
                "gemini-3.1-flash-tts-preview",
                "gemini-3.8-flash",
                "gemini-3.1-pro-preview",
                "gemini-3.5-flash",
            ],
        )
        ancienne = connexions.ajouter("google", "Ancienne clé", CLE_DEMO.replace("4f2c", "9a1b"))
        connexions.enregistrer_test(
            ancienne.identifiant,
            False,
            "Google refuse cette clé : elle n'est pas valide. Vérifie qu'elle a été copiée en entier.",
        )

    maintenant = datetime.now().astimezone().replace(microsecond=0)
    appels = [
        ("gemini-3.8-flash", "script : relecture", 5_120, 1_940, "Sérum Glowzy", timedelta(minutes=20)),
        ("gemini-3.8-flash", "script : écriture", 4_310, 2_280, "Sérum Glowzy", timedelta(minutes=21)),
        ("gemini-3.8-flash-tts", "voix", 412, 18_950, "Sérum Glowzy", timedelta(minutes=5)),
        ("gemini-3.8-flash-tts", "voix", 398, 17_400, "Sérum Glowzy", timedelta(minutes=12)),
        ("gemini-3.8-flash-lite-tts", "essai de voix", 24, 1_150, None, timedelta(hours=2)),
        ("gemini-3.5-transcribe", "transcription", 7_680, 612, "Brosse lissante", timedelta(hours=3)),
    ]
    if not services.couts.lire():
        for modele, operation, entree, sortie, projet, anciennete in appels:
            services.couts.enregistrer("google", modele, operation, entree, sortie, projet, maintenant - anciennete)

    if not services.voix.bibliotheque():
        services.voix.definir_bibliotheque(VOIX_DEMO)
        expiration = (datetime.now().astimezone() + timedelta(days=365)).isoformat(timespec="seconds")
        services.voix.definir_voix_creees([replace(VOIX_CREEE_DEMO, expire_le=expiration)])
        services.voix.definir_description_fr(
            VOIX_CREEE_DEMO.identifiant,
            "Jeune femme d'environ 25 ans, voix chaleureuse et légèrement voilée, accent parisien. "
            "Spontanée et complice, comme face caméra avec une amie.",
        )
        services.voix.basculer_favori("Puck")
        services.voix.basculer_favori("demo-camille")

    if services.projets.projet is None and not services.projets.recents():
        projet = services.projets.creer("Sérum Glowzy", dossier_projets_defaut())
        projet.repliques = [RepliqueProjet([dict(s) for s in r.script], r.style, r.style_fr) for r in REPLIQUES_DEMO]
        projet.prononciations = [Prononciation("Glowzy", "Glo-zi")]
        projet.ecriture = ecriture_demo()
        services.projets.enregistrer()
        # Texte réellement envoyé (prononciation appliquée) : la vitesse de chaque voix se mesure dessus.
        envoyees = repliques_api(REPLIQUES_DEMO, projet.prononciations)
        texte_api = "\n".join(r.texte for r in envoyees)
        for duree, voix, note, frequence in ((10.2, "Kore", 4, 220.0), (10.8, "Leda", 0, 262.0)):
            services.projets.ajouter_prise(
                son_de_demonstration(duree, frequence),
                modele="gemini-3.8-flash-tts",
                voix=voix,
                style="styles par réplique",
                texte_api=texte_api,
                script=joindre_repliques([r.script for r in REPLIQUES_DEMO]),
                repliques=[{"texte_api": r.texte, "style": r.style} for r in envoyees],
                duree_s=duree,
                tokens_entree=120,
                tokens_sortie=int(duree * 25),
                cout_eur="0.0021",
                note=note,
            )
        # Une série de variantes A/B (§5.6) : même script, voix ou style de la 1re réplique différents.
        variantes = (
            ("A", "Kore", REPLIQUES_DEMO[0].style, 9.8, 3, 196.0),
            ("B", "Puck", REPLIQUES_DEMO[0].style, 10.5, 5, 247.0),
            ("C", "Kore", "calm and intimate, slow-paced", 11.6, 0, 294.0),
        )
        retenue = None
        for lettre, voix, style, duree, note, frequence in variantes:
            prise = services.projets.ajouter_prise(
                son_de_demonstration(duree, frequence),
                modele="gemini-3.8-flash-tts",
                voix=voix,
                style="styles par réplique",
                texte_api=texte_api,
                script=joindre_repliques([r.script for r in REPLIQUES_DEMO]),
                repliques=[{"texte_api": envoyees[0].texte, "style": style}, {"texte_api": envoyees[1].texte, "style": REPLIQUES_DEMO[1].style}],
                duree_s=duree,
                tokens_entree=120,
                tokens_sortie=int(duree * 25),
                cout_eur="0.0021",
                note=note,
                serie=1,
                variante=lettre,
            )
            if lettre == "B":
                retenue = prise.identifiant
        services.projets.retenir(retenue)
        # Transcription d'une vidéo (étape 7), avec sa piste son dans « sources ».
        piste = projet.chemin(f"{DOSSIER_SOURCES}/audio.wav")
        piste.parent.mkdir(parents=True, exist_ok=True)
        piste.write_bytes(son_de_demonstration(DUREE_TRANSCRIPTION_DEMO, 175.0))
        projet.transcription = transcription_demo()
        projet.remplacements = [Remplacement("sérum glowzy", "Sérum Glowzy")]
        services.projets.enregistrer()
        services.vitesses.noter_prises(projet.prises)  # (les prises de démonstration ne passent pas par Google)

        # Lot 2 : un brief enregistré dans la bibliothèque, et deux de « Mes meilleurs scripts ».
        etat = projet.ecriture
        if not services.briefs.briefs():
            services.briefs.enregistrer(nom_propose(etat.brief), etat.brief, etat.adresse, etat.page, etat.fiche)
            services.briefs.enregistrer(
                "Brosse lissante (Facebook et Instagram)",
                Brief(produit="Brosse lissante chauffante", reseau="meta", duree_s=20, age="35-44", tutoiement="vous"),
            )
        if not services.exemples.gardes():
            premier = etat.scripts[0]
            services.exemples.ajouter(
                ExempleScript(
                    f"script-{premier.identifiant}", "Sérum éclat Glowzy", premier.langue, premier.reseau, premier.angle,
                    premier.tutoiement, premier.duree_visee_s, "29,90 € ; code GLOW20 (-20 %)",
                    repliques_pour_modele(premier.repliques), note="CPA 9 €",
                )
            )
            premier.garde_comme_exemple = True
            colle = exemple_colle(
                "Gourde isotherme",
                "J'ai arrêté d'acheter des bouteilles d'eau.\n\nCette gourde garde mon eau froide toute la journée, "
                "même dans la voiture. Le lien est en dessous.",
                "fr-FR", "tiktok", "temoignage", note="Meilleur ROAS de septembre",
            )
            if colle is not None:
                services.exemples.ajouter(colle)
            services.projets.enregistrer()
