"""Contenu des fenêtres « Conseils » (V1.1) : un bouton en haut à droite de chaque module et de
chaque fenêtre qui a quelque chose à expliquer ouvre ces conseils, en français.

Ici, seulement le texte (testé sans interface) ; la fenêtre est dans ui/composants/conseils.py.
Pour ajouter un conseil : l'écrire dans la bonne rubrique, en une ou deux phrases, en tutoyant,
avec les noms exacts des boutons de l'app.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conseils import CONSEILS_STYLE, CONSEILS_VOIX
from .ecriture.regles import LIMITE_DE_LA_RELECTURE, RAPPEL_IA_TIKTOK, REGLES


@dataclass(frozen=True)
class Rubrique:
    """Une partie de la fenêtre : un titre, puis quelques conseils."""

    titre: str
    conseils: tuple[str, ...]


@dataclass(frozen=True)
class PageDeConseils:
    """Conseils d'un module ou d'une fenêtre. `titre` : son nom (« Voix », « Créer une voix »)."""

    titre: str
    rubriques: tuple[Rubrique, ...]


# Conseils de Google, en français seulement (l'original anglais reste dans conseils.py).
_STYLES_GOOGLE = Rubrique("Styles : les conseils de Google", tuple(c.francais for c in CONSEILS_STYLE))
_DESCRIPTION_GOOGLE = Rubrique(
    "Décrire une voix : les conseils de Google", tuple(c.francais for c in CONSEILS_VOIX)
)
_EN_ANGLAIS = Rubrique(
    "Pourquoi le style est en anglais",
    (
        "Le style part toujours en anglais chez Google, comme dans tous ses exemples, "
        "ex. « warm and enthusiastic, fast-paced ».",
        "Tu peux l'écrire en français, puis cliquer sur le bouton de traduction à côté du champ : "
        "la traduction coûte une fraction de centime et le français reste affiché dessous, pour "
        "savoir ce qui est envoyé.",
        "L'assistant (crayon à côté du champ) te fait choisir en français et écrit directement la "
        "consigne en anglais.",
        "Le texte du script, lui, reste dans la langue du projet.",
    ),
)

SCRIPT = PageDeConseils(
    "Script",
    (
        Rubrique(
            "Les étapes",
            (
                "« Lire la page » : l'app lit la page produit elle-même (gratuit, exact pour une boutique "
                "Shopify) ; si le site bloque, Google la lit (coût minime) ; sinon, colle le texte du produit.",
                "Le modèle remplit « Ce que l'app a compris », puis les champs vides du brief, marqués « d'après "
                "la page » : rien de ce que tu as tapé n'est écrasé, et chaque champ se corrige à la main.",
                "« Proposer des accroches » : coche celles qui te plaisent, puis « Écrire le script » écrit un "
                "script par accroche cochée. Sans accroche cochée, le modèle choisit lui-même.",
                "Chaque script est relu avant d'arriver : l'app vérifie la durée, les mots interdits et les "
                "mentions obligatoires ; le modèle relit le reste et corrige ce qui est grave.",
                "« Envoyer dans Voix » remplace les répliques du module Voix par celles du script, avec leurs "
                "styles, balises et mots accentués, puis ouvre le module Voix.",
            ),
        ),
        Rubrique(
            "Remplir un brief",
            (
                "Aucun champ n'est obligatoire : remplis ce que tu sais, le reste vient de la page produit.",
                "Rien n'est inventé : sans prix ni chiffre dans le brief ou sur la page, le script n'en donne pas.",
                "Les avis clients sont rarement lisibles sur la page : colle 2 ou 3 avis dans « Preuves ».",
                "Ce qui n'est écrit que dans les images de la page (ex. un logo de certification) n'est pas lu : "
                "ajoute-le au brief si tu veux qu'il serve.",
                "« Personne qui parle » : son genre change les accords en français (« je suis ravie »). Il est "
                "pré-rempli d'après la voix du projet.",
            ),
        ),
        Rubrique(
            "Durée",
            (
                "Durée vide : 25 s sur TikTok, 10 s sur Snapchat, 20 s sur Facebook et Instagram.",
                "L'app compte 2,7 mots par seconde (environ 160 mots par minute), comme le module Voix : chaque "
                "script affiche sa durée estimée, balises comprises.",
            ),
        ),
        Rubrique(
            "Balises, styles, accentuations",
            (
                "Balises : rires, pauses… seulement celles de l'app. Elles arrivent en badges dans le module Voix.",
                "Styles de jeu : seulement si l'émotion change. Les répliques de même émotion reprennent "
                "exactement le même style, en anglais, avec sa traduction.",
                "Accentuations : un mot au plus par réplique, dit avec plus de force ; les sous-titres gardent "
                "l'écriture d'origine.",
            ),
        ),
        Rubrique(
            "Règles publicitaires",
            (
                *(regle.francais for regle in REGLES),
                RAPPEL_IA_TIKTOK,
                LIMITE_DE_LA_RELECTURE,
            ),
        ),
        Rubrique(
            "Modèle, coûts et exemples",
            (
                "Gemini 3.8 Flash par défaut ; Gemini 3.1 Pro (aperçu) est chargé pour comparer sur tes produits.",
                "Le coût est estimé avant chaque demande, puis noté dans le suivi des coûts (« script : "
                "écriture »…) : quelques centimes pour un script complet avec Gemini 3.8 Flash.",
                "« Garder comme exemple » range un script parmi les exemples donnés au modèle : il s'en inspire "
                "pour le ton et le rythme, sans le recopier. Au départ, 5 scripts fournis servent d'exemples.",
            ),
        ),
    ),
)

VOIX = PageDeConseils(
    "Voix",
    (
        _STYLES_GOOGLE,
        _EN_ANGLAIS,
        Rubrique(
            "Balises",
            (
                "Clique dans le texte, puis sur une balise de la palette : elle s'insère à cet endroit. "
                "Un badge s'efface comme une lettre, avec la touche retour arrière.",
                "Les balises s'affichent en français mais partent en anglais chez Google, comme le demande "
                "sa documentation. Laisse la souris sur un badge pour voir le nom envoyé (ex. « <laugh> »).",
                "Un texte collé depuis un autre logiciel garde ses balises : « <laugh> » comme « <rire> » "
                "deviennent des badges.",
                "Une balise sert aux sons ponctuels (rire, soupir, pause) ; l'émotion de toute une réplique "
                "se règle avec son style.",
            ),
        ),
        Rubrique(
            "Répliques",
            (
                "Découpe en répliques quand l'émotion change (ex. hook énergique, puis témoignage calme) : "
                "chaque réplique a son propre style.",
                "Toutes les répliques partent dans la même génération : tu obtiens une seule prise.",
                "Menu ⋯ d'une réplique : « Découper ici » coupe au curseur (la nouvelle réplique garde le "
                "même style), puis Monter, Descendre et Supprimer.",
            ),
        ),
        Rubrique(
            "Accentuer et prononciation",
            (
                "« Accentuer » met le mot sélectionné en MAJUSCULES : le modèle appuie dessus. Les "
                "sous-titres gardent l'écriture d'origine.",
                "« Prononciation » : pour un nom de marque mal prononcé, écris comment le dire (ex. "
                "« Glowzy » se dit « Glo-zi »). Seul le texte envoyé à la voix change : le script et les "
                "sous-titres gardent la bonne orthographe.",
            ),
        ),
        Rubrique(
            "Générer et comparer",
            (
                "Flash TTS donne le meilleur jeu d'acteur ; Flash-Lite TTS, plus rapide et moins cher, est "
                "pratique pour essayer un script.",
                "L'estimation (caractères, durée, coût) s'affiche avant de générer. Elle s'ajuste après "
                "chaque génération, avec les vrais chiffres de Google.",
                "« Écouter pendant la génération » fait entendre le début avant la fin du calcul.",
                "« Variantes… » génère plusieurs versions du script en un seul lancement (tests A/B), puis "
                "ouvre l'écoute comparative.",
                "Chaque génération devient une prise, gardée dans le projet : note-la avec les étoiles. Son "
                "menu ⋯ permet de la renommer, de l'exporter en WAV ou MP3, ou de créer ses sous-titres.",
            ),
        ),
    ),
)

TRANSCRIPTION = PageDeConseils(
    "Transcription",
    (
        Rubrique(
            "Source",
            (
                "Glisse une vidéo ou un audio sur la page, ou clique sur « Choisir un fichier… ». L'app "
                "extrait elle-même la piste son : la vidéo n'est jamais envoyée.",
                "Vidéos MP4, MOV, MKV, M4V, WebM, AVI ; audios WAV, MP3, M4A, AAC, FLAC, OGG, Opus, AIFF, WMA.",
                "Une nouvelle source remplace la transcription actuelle, après confirmation.",
            ),
        ),
        Rubrique(
            "Options",
            (
                "Langue : choisis celle de la vidéo. C'est plus fiable que la détection automatique, "
                "surtout pour une vidéo courte.",
                "« Séparer les voix » : chaque mot reçoit la personne qui parle. Fiable jusqu'à 2 personnes, "
                "expérimental au-delà. Un changement de personne termine toujours un sous-titre.",
                "« Texte seul, nettoyé » (mode « smart » de Google) : un texte propre, sans le moment de "
                "chaque mot. Pratique pour récupérer le script d'une vidéo, mais pas de sous-titres "
                "possibles, ni de voix séparées.",
            ),
        ),
        Rubrique(
            "Remplacements et hésitations",
            (
                "« Remplacements » : pour les noms de marque que la transcription écrit mal. Ils "
                "s'appliquent après chaque transcription, en gardant le moment de chaque mot, et ne coûtent "
                "rien (c'est l'app qui remplace).",
                "« Masquer les hésitations dans les sous-titres » retire « euh », « hum »… de l'affichage ; "
                "l'audio ne change pas. « Hésitations » modifie la liste de chaque langue.",
            ),
        ),
        Rubrique(
            "Corriger les mots",
            (
                "Clique sur un mot pour le choisir : corrige son texte, son début et sa fin (en secondes), "
                "ou utilise « Fusionner avec le suivant », « Couper en deux », « Supprimer ».",
                "Le moment de chaque mot est gardé quand tu corriges son texte : c'est lui qui cale les "
                "sous-titres.",
                "Pendant la lecture, un clic sur un mot fait sauter la lecture à ce mot.",
                "« Copier le texte » copie toute la transcription.",
            ),
        ),
    ),
)

SOUS_TITRES = PageDeConseils(
    "Sous-titres",
    (
        Rubrique(
            "D'où viennent les mots",
            (
                "Les sous-titres partent des mots de la transcription du projet, avec le moment de chaque mot.",
                "Pour une prise du module Voix, « Créer les sous-titres » la transcrit, puis cale le texte "
                "sur son script : l'orthographe du script est gardée (noms de marque, pas de MAJUSCULES "
                "d'accentuation).",
                "« Corriger les mots » ouvre le module Transcription.",
            ),
        ),
        Rubrique(
            "Découpage",
            (
                "Caractères et mots par sous-titre sont deux maximums ; un mot n'est jamais coupé.",
                "Un sous-titre se termine toujours à un changement de personne, après un silence de plus de "
                "0,8 s et, si « Couper de préférence après la ponctuation » est cochée, après une fin de phrase.",
                "L'app choisit le meilleur découpage : des sous-titres bien remplis, de longueurs proches, "
                "qui finissent si possible sur une ponctuation.",
                "La durée minimale allonge les sous-titres trop courts, sans chevaucher le suivant.",
                "« Tout en majuscules » et la ponctuation ne changent que l'affichage : le moment des mots "
                "ne bouge jamais.",
            ),
        ),
        Rubrique(
            "Zone de sécurité et marge maximum",
            (
                "La zone de sécurité dépend de la plateforme choisie : c'est la partie de l'écran que les "
                "boutons de l'application (TikTok, Reels…) ne cachent pas. Le texte y reste normalement.",
                "Une ligne trop large peut déborder jusqu'à la marge maximum, jamais au-delà ; sinon, le "
                "sous-titre est redécoupé.",
                "Les largeurs sont mesurées en pixels, avec la police et la taille du texte.",
            ),
        ),
        Rubrique(
            "Sous-titres en orange",
            (
                "Un mot seul trop large pour la marge maximum est rapetissé (jusqu'à 60 % de la taille du "
                "texte) : son sous-titre passe en orange.",
                "Pour l'éviter : raccourcis ce mot, agrandis la marge maximum ou baisse la taille du texte.",
            ),
        ),
        Rubrique(
            "Réorganiser à la main",
            (
                "Choisis un sous-titre dans la liste, puis « Monter le premier mot », « Descendre le dernier "
                "mot », « Couper » (choisis le mot qui commence le nouveau sous-titre) ou « Fusionner avec le "
                "suivant ».",
                "Le moment des mots ne change jamais : un sous-titre va toujours du début de son premier mot à "
                "la fin de son dernier.",
                "Les réglages du découpage valent aussi à la main : une action qui ne les respecte pas est "
                "refusée, avec la raison et le réglage à changer.",
                "Un sous-titre ajusté est marqué « Ajusté à la main ». Il garde ses mots quand tu changes un "
                "réglage : le reste est redécoupé autour de lui. Si un réglage ne le permet plus, l'app te "
                "demande d'abord.",
                "« Rétablir » remet ce sous-titre, ou tous, au découpage automatique.",
            ),
        ),
        Rubrique(
            "Export",
            (
                "« Exporter en SRT… » : le texte et le moment de chaque sous-titre, sans style. Premiere Pro "
                "et la plupart des logiciels le lisent, accents compris.",
            ),
        ),
    ),
)

REGLAGES = PageDeConseils(
    "Réglages",
    (
        Rubrique(
            "Clés API",
            (
                "Ta clé est rangée dans le coffre-fort de Windows (Gestionnaire d'identification), jamais "
                "dans un fichier ni dans un projet. L'app ne la réaffiche jamais en entier.",
                "« Tester » demande à Google la liste de ses modèles : c'est gratuit. Une clé n'est "
                "enregistrée qu'après un test réussi (sans Internet : « Enregistrer sans tester »).",
                "Les modèles proposés dans l'app sont ceux accessibles avec ta clé lors du dernier test réussi.",
            ),
        ),
        Rubrique(
            "Modèles et prix",
            (
                "Seuls les modèles chargés sont proposés dans l'app : « Choisir les modèles… » en ajoute "
                "ou en retire, parmi ceux que ta clé permet d'utiliser.",
                "La colonne « Utilisé dans » dit où chaque modèle sert en ce moment ; un modèle utilisé ne "
                "peut pas être retiré, pour qu'aucun module ne se retrouve sans modèle.",
                "Les prix sont les tarifs officiels de Google, en dollars par million de tokens. Quand "
                "Google annonce un nouveau tarif, l'app applique le bon à la date de chaque appel.",
                "Tu peux modifier un prix ; « Rétablir les prix par défaut » revient aux tarifs de Google.",
                "Taux de change : saisis-le, ou récupère le taux du jour de la Banque centrale européenne. "
                "Le taux de départ est à vérifier.",
            ),
        ),
        Rubrique(
            "Niveau gratuit de Google",
            (
                "Avec une clé sans moyen de paiement, Google ne facture pas ces modèles (avec des limites "
                "d'usage plus basses). L'app affiche quand même le coût au tarif payant.",
            ),
        ),
        Rubrique(
            "Suivi des coûts",
            (
                "Chaque appel est noté : date, projet, modèle, tokens et coût en euros, calculé avec les "
                "chiffres renvoyés par Google.",
                "Filtre par période, par projet ou par modèle. L'app compte ce qu'elle a consommé : elle ne "
                "connaît pas le solde de ton compte Google.",
            ),
        ),
        Rubrique(
            "Journal et données",
            (
                "En cas de problème, le journal explique ce qui s'est passé. Il ne contient jamais tes clés.",
                "Le dossier de données garde tes connexions (sans les clés), les prix, l'historique des coûts "
                "et les préférences de l'app.",
            ),
        ),
    ),
)

# --- Fenêtres ---------------------------------------------------------------------------------

CREER_UNE_VOIX = PageDeConseils(
    "Créer une voix",
    (
        _DESCRIPTION_GOOGLE,
        Rubrique(
            "Versions et conservation",
            (
                "Chaque création donne une version un peu différente : crée-en plusieurs, écoute-les, puis "
                "« Utiliser cette voix » pour ta préférée.",
                "La description part en anglais, comme les styles : écris-la en français puis traduis-la, "
                "ou utilise l'assistant (crayon à côté du champ).",
                "Google garde une voix créée pendant un an (sa date d'expiration est affichée), et 200 voix "
                "au plus par projet Google.",
                "Chaque création est comptée dans le suivi des coûts. Les voix créées dans Google AI Studio "
                "(même projet Google) apparaissent aussi dans l'app.",
            ),
        ),
    ),
)

STYLE = PageDeConseils(
    "Style",
    (
        _STYLES_GOOGLE,
        _EN_ANGLAIS,
        Rubrique(
            "Catégories et balises",
            (
                "Range tes styles par catégorie (UGC témoignage, unboxing, hook…) : écris un nouveau nom "
                "dans la liste pour créer une catégorie.",
                "Le style retient aussi son modèle, sa voix et sa langue : « Appliquer » les remet en place.",
                "« Balises souvent utilisées » est un pense-bête affiché dans la bibliothèque : ces balises "
                "ne s'insèrent pas toutes seules.",
            ),
        ),
    ),
)

ASSISTANT_STYLE = PageDeConseils(
    "Assistant de style",
    (
        Rubrique(
            "Remplir l'assistant",
            (
                "Choisis une émotion ou une attitude, une deuxième si besoin, puis le rythme et la voix "
                "(facultatifs) : l'app assemble une consigne courte.",
                "Une consigne courte marche mieux, comme Google le conseille : ne remplis que ce qui compte.",
                "La consigne reste modifiable ensuite, dans le champ style.",
            ),
        ),
        Rubrique(
            "Pourquoi en anglais",
            (
                "La consigne est écrite en anglais, comme dans les exemples de Google ; la traduction "
                "française s'affiche dessous pour savoir ce qui est envoyé.",
            ),
        ),
    ),
)

ASSISTANT_DESCRIPTION = PageDeConseils(
    "Assistant de description",
    (
        Rubrique(
            "Remplir l'assistant",
            (
                "Décris les traits permanents : genre, âge, timbre, texture de la voix, accent, rôle. "
                "L'app en fait 1 à 2 phrases, comme Google le conseille.",
                "Le genre choisi est reporté dans le formulaire de création.",
                "L'émotion ne va pas ici : elle se règle ensuite avec les styles des répliques.",
            ),
        ),
        Rubrique(
            "Pourquoi en anglais",
            (
                "La description est écrite en anglais, comme dans les exemples de Google ; la traduction "
                "française s'affiche dessous pour savoir ce qui est envoyé.",
            ),
        ),
    ),
)

BIBLIOTHEQUE_VOIX = PageDeConseils(
    "Bibliothèque de voix",
    (
        Rubrique(
            "Trouver une voix",
            (
                "Les filtres (langue, genre, hauteur, accent, persona, contexte) et la recherche agissent "
                "tout de suite. Au départ, la langue est celle du projet.",
                "La bibliothèque de Google est gardée une semaine ; « Actualiser » la redemande.",
            ),
        ),
        Rubrique(
            "Écouter et choisir",
            (
                "▶ joue un extrait : celui de Google quand il existe (gratuit). Pour les 30 voix de base, "
                "une phrase d'exemple est générée dans la langue du projet (coût minime), puis gardée.",
                "★ met une voix en favori : les favoris passent en tête de la liste des voix, et « Favoris "
                "seulement » les montre seuls.",
                "Un clic sur « Choisir » prend la voix pour ton script.",
            ),
        ),
        Rubrique(
            "Mes voix",
            (
                "Les voix créées avec Voice Design, ici ou dans Google AI Studio (même projet Google). "
                "« Créer une voix » en décrit une nouvelle.",
                "Choisir une voix créée choisit aussi le modèle avec lequel elle a été créée.",
            ),
        ),
    ),
)

BIBLIOTHEQUE_STYLES = PageDeConseils(
    "Bibliothèque de styles",
    (
        Rubrique(
            "Utiliser un style",
            (
                "« Appliquer » met le style sur la réplique, et choisit sa voix et son modèle.",
                "« Enregistrer le style actuel » crée un style à partir de celui de la réplique.",
                "Menu ⋯ d'un style : le modifier, le dupliquer ou le supprimer.",
            ),
        ),
        Rubrique(
            "Ranger ses styles",
            (
                "Les styles sont rangés par catégorie (UGC témoignage, unboxing, hook…) ; une catégorie se "
                "crée en écrivant son nom dans la fenêtre du style.",
            ),
        ),
    ),
)

PRONONCIATION = PageDeConseils(
    "Prononciation",
    (
        Rubrique(
            "Écrire une prononciation",
            (
                "À gauche, le mot comme dans le script ; à droite, comment le dire, écrit comme il se "
                "prononce (ex. « Glowzy » se dit « Glo-zi »).",
                "▶ fait essayer la prononciation d'un mot seul (coût minime, gardé ensuite).",
                "Mots entiers, sans tenir compte des majuscules ; le plus long passe d'abord (« Glowzy Pro » "
                "avant « Glowzy »). Les balises ne changent jamais.",
            ),
        ),
        Rubrique(
            "Ce projet ou tous les projets",
            (
                "« Ce projet » ne sert qu'au projet ouvert ; « Tous les projets », partout. Pour un même mot, "
                "le dictionnaire du projet l'emporte.",
                "Seul le texte envoyé à la voix change : le script et les sous-titres gardent la bonne orthographe.",
            ),
        ),
    ),
)

REMPLACEMENTS = PageDeConseils(
    "Remplacements",
    (
        Rubrique(
            "Comment ça marche",
            (
                "À gauche, un ou plusieurs mots tels que transcrits ; à droite, ce qui doit apparaître "
                "(ex. « sérum anti rides » devient « Sérum Anti-Rides® »).",
                "Les mots sont comparés sans majuscules ni ponctuation collée ; la suite la plus longue "
                "passe d'abord.",
                "Le mot obtenu garde le moment des mots remplacés, du début du premier à la fin du dernier.",
                "Ils s'appliquent après chaque transcription, et tout de suite à la transcription actuelle "
                "quand tu enregistres.",
            ),
        ),
        Rubrique(
            "Ce projet ou tous les projets",
            (
                "« Ce projet » ne sert qu'au projet ouvert ; « Tous les projets », partout. Pour une même "
                "entrée, le dictionnaire du projet l'emporte.",
            ),
        ),
    ),
)

VARIANTES = PageDeConseils(
    "Variantes A/B",
    (
        Rubrique(
            "Deux façons de comparer",
            (
                "« Mêmes réglages » : de 2 à 6 prises identiques. Le modèle interprète le texte un peu "
                "différemment à chaque fois : garde la meilleure.",
                "« Réglages par variante » : chaque colonne part des réglages de base ; change seulement ce "
                "que tu veux comparer (voix, style, modèle, texte d'une réplique). Les valeurs modifiées "
                "sont en mauve.",
                "« Dupliquer la variante » en crée une voisine, pour tester un petit changement.",
            ),
        ),
        Rubrique(
            "Génération",
            (
                "Le coût total estimé s'affiche avant de lancer.",
                "Les variantes partent l'une après l'autre ; « Arrêter » stoppe après celle en cours, et "
                "celles déjà prêtes sont gardées.",
                "Chaque variante devient une prise (« Prise 5 (variante B) »). L'écoute comparative s'ouvre "
                "à la fin de la série.",
            ),
        ),
    ),
)

COMPARAISON = PageDeConseils(
    "Comparer les variantes",
    (
        Rubrique(
            "Écouter",
            (
                "« Lecture enchaînée » joue A, puis B, puis C…, avec un court silence entre deux.",
                "Clique sur une lettre, ou tape A à F (ou 1 à 6) : la variante reprend au même moment du "
                "texte, pour comparer une même phrase.",
                "Espace : lecture ou pause.",
            ),
        ),
        Rubrique(
            "Choisir",
            (
                "Note les variantes avec les étoiles, puis « Garder » la meilleure : une seule variante est "
                "retenue par série, signalée « Retenue » dans la liste des prises.",
                "Cette fenêtre se rouvre depuis le menu ⋯ d'une prise de la série.",
            ),
        ),
    ),
)

CLE_API = PageDeConseils(
    "Clé API",
    (
        Rubrique(
            "Trouver ta clé",
            (
                "Crée ta clé dans Google AI Studio (menu « Get API key ») : le bouton « Ouvrir Google AI "
                "Studio » y mène directement. Copie-la, puis colle-la ici.",
                "Donne-lui un nom qui te parle (ex. « Google perso ») : tu peux avoir plusieurs clés.",
            ),
        ),
        Rubrique(
            "Test et rangement",
            (
                "Le test demande à Google la liste de ses modèles : c'est gratuit. La clé n'est enregistrée "
                "qu'après un test réussi.",
                "Elle est rangée dans le coffre-fort de Windows, jamais dans un fichier ; l'app n'en montre "
                "ensuite que le début et la fin.",
            ),
        ),
        Rubrique(
            "Niveau gratuit de Google",
            (
                "Une clé sans moyen de paiement utilise le niveau gratuit : ces modèles n'y sont pas "
                "facturés, avec des limites d'usage plus basses.",
            ),
        ),
    ),
)

PAGES: dict[str, PageDeConseils] = {
    "script": SCRIPT,
    "voix": VOIX,
    "transcription": TRANSCRIPTION,
    "sous-titres": SOUS_TITRES,
    "reglages": REGLAGES,
    "creer-une-voix": CREER_UNE_VOIX,
    "style": STYLE,
    "assistant-style": ASSISTANT_STYLE,
    "assistant-description": ASSISTANT_DESCRIPTION,
    "bibliotheque-voix": BIBLIOTHEQUE_VOIX,
    "bibliotheque-styles": BIBLIOTHEQUE_STYLES,
    "prononciation": PRONONCIATION,
    "remplacements": REMPLACEMENTS,
    "variantes": VARIANTES,
    "comparaison": COMPARAISON,
    "cle-api": CLE_API,
}
