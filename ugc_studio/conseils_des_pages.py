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
            "Plusieurs versions",
            (
                "« Variantes… » écrit de 2 à 6 scripts en un seul lancement : mêmes réglages (une accroche "
                "différente pour chacun), réglages par variante (angle, durée, réseau…) ou accroches seulement "
                "(le même corps, d'autres accroches).",
                "« Retoucher… » : une consigne (« plus court », « plus drôle », « sans tutoiement ») donne un "
                "nouveau script, relu comme les autres ; l'ancien reste.",
                "« Comparer… » met 2 ou 3 scripts côte à côte : accroche, répliques, durée et relecture.",
                "Note tes scripts avec les étoiles et « Retenir » ceux que tu gardes pour tes pubs. Menu ⋯ "
                "d'un script : dupliquer, garder comme exemple, supprimer.",
                "Série « Accroches seulement » : menu ⋯, « Envoyer les accroches en variantes » les envoie dans "
                "le module Voix, une variante de voix par accroche (tests A/B).",
            ),
        ),
        Rubrique(
            "Briefs réutilisables",
            (
                "« Enregistrer » range le brief, avec la page produit lue, dans ta bibliothèque de briefs.",
                "« Charger un brief » le reprend, dans ce projet ou un autre : pratique pour un même produit "
                "décliné par réseau ou par langue.",
            ),
        ),
        Rubrique(
            "Durée et vitesse de parole",
            (
                "Durée vide : 25 s sur TikTok, 10 s sur Snapchat, 20 s sur Facebook et Instagram.",
                "Au départ, l'app compte 2,7 mots par seconde (environ 160 mots par minute). Ensuite, elle "
                "mesure la vitesse de chaque voix sur tes prises (moyenne des 20 dernières).",
                "Le nombre de mots visé et la durée estimée de chaque script suivent la voix du projet, avec "
                "la même vitesse que le module Voix : les deux modules annoncent la même durée.",
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
                "« Garder comme exemple » (menu ⋯ d'un script) range un script parmi les exemples donnés au "
                "modèle : il s'en inspire pour le ton et le rythme, sans le recopier. Au départ, 5 scripts "
                "fournis servent d'exemples.",
                "« Mes meilleurs scripts… » : colle un script qui a marché, note tes exemples (ex. « CPA 9 € ») "
                "ou retire les scripts fournis.",
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
                "« Nombres dits » (projets en français) : à la belge (septante, nonante) ou à la suisse "
                "(septante, huitante, nonante). Seul le texte envoyé à la voix change : le script et les "
                "sous-titres gardent les chiffres.",
                "À Genève, à Neuchâtel et dans le Jura, on dit « quatre-vingts » : choisis « À la belge ».",
            ),
        ),
        Rubrique(
            "Générer et comparer",
            (
                "Flash TTS donne le meilleur jeu d'acteur ; Flash-Lite TTS, plus rapide et moins cher, est "
                "pratique pour essayer un script.",
                "L'estimation (caractères, durée, coût) s'affiche avant de générer. Elle s'ajuste après "
                "chaque génération, avec les vrais chiffres de Google.",
                "La durée estimée suit la vitesse de parole de la voix choisie, mesurée sur tes prises : "
                "laisse la souris sur l'estimation pour la voir.",
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
                "« Corriger les mots » ouvre le module Transcription ; un double-clic sur un sous-titre de la "
                "frise l'ouvre directement sur son premier mot.",
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
                "La casse (TOUT EN MAJUSCULES…) et la ponctuation ne changent que l'affichage : le moment des "
                "mots ne bouge jamais.",
            ),
        ),
        Rubrique(
            "Style du texte",
            (
                "Un nouveau projet prend le préréglage marqué ★ (au départ « Blanc contour noir » : Montserrat "
                "Extra-grasse, blanc, contour noir, le mot dit en jaune). Un projet plus ancien garde son apparence.",
                "Chaque groupe de l'onglet Texte (police, remplissage, contour, ombre, lueur, fond, espaces) se "
                "replie ; ses réglages rares attendent dans « Réglages avancés », et « Rétablir » le remet "
                "comme dans le préréglage du projet (sinon comme au départ).",
                "Les tailles s'affichent en pixels de ta vidéo et sont gardées en % de sa hauteur : un style "
                "garde le même aspect en 9:16, en 4:5 ou en 1:1.",
                "Le contour est dessiné autour des lettres, sans les amincir. Ordre de dessin : ombre, fond, "
                "lueur, contour, puis le texte.",
                "La pipette prend une couleur dans l'aperçu, par exemple celle de ton produit ; Échap annule.",
                "Le contour et le fond comptent dans la largeur d'une ligne : un contour plus épais peut "
                "refaire le découpage (l'ombre et la lueur, non).",
            ),
        ),
        Rubrique(
            "Mots : le mot en train d'être dit",
            (
                "Onglet Mots : trois états, chacun avec son apparence : les mots à venir, le mot actif (en "
                "train d'être dit) et les mots déjà dits. Tout ce qui n'est pas réglé reste « comme le texte ».",
                "Les raccourcis remplissent les états : Surlignage (le mot actif en jaune, un peu plus grand), "
                "Karaoké (les mots dits restent jaunes), Apparition (les mots apparaissent quand ils sont "
                "dits), Mot par mot (un seul mot à la fois). Tout reste modifiable ensuite.",
                "Un réglage changé a son nom en mauve ; ↺ le remet comme le texte.",
                "Un mot invisible garde sa place : rien ne bouge pendant la lecture. Un mot agrandi grandit "
                "autour de son centre, sans pousser ses voisins ; la place qu'il prend compte dans le "
                "découpage, il ne sort jamais de la marge maximum.",
                "Pour le mot actif, le fond surligné peut glisser d'un mot à l'autre (réglages avancés du "
                "fond) ; sur une autre ligne, il apparaît directement sous le mot.",
                "Mots accentués : pour les sous-titres d'une prise, les mots mis en valeur dans son script "
                "(bouton « Accentuer » du module Voix) peuvent avoir leur propre apparence.",
                "Si les mots s'allument un peu tard ou un peu tôt, « Avance de l'allumage » (réglages "
                "avancés) les décale à l'écran, de 200 ms au plus ; le moment des mots ne change pas.",
            ),
        ),
        Rubrique(
            "Animations",
            (
                "Onglet Animations : le mot qui devient actif peut faire un pop, un rebond, un zoom, un fondu "
                "ou glisser vers le haut, avec sa durée et son intensité ; ses réglages avancés (tailles, "
                "opacité et décalage de départ, courbe) partent de ceux de l'animation choisie.",
                "Quand le mot suivant s'allume, le précédent redevient « déjà dit » d'un coup, ou en fondu.",
                "Le sous-titre entier peut apparaître et disparaître (fondu, pop, zoom, glissement) : "
                "l'apparition commence à son début, la disparition finit à sa fin ; les temps ne changent pas.",
                "Le sommet d'un pop compte dans la place : un mot animé ne sort jamais de la marge maximum.",
                "Pour revoir une animation : choisis le sous-titre dans la liste et active la boucle de "
                "l'aperçu.",
            ),
        ),
        Rubrique(
            "Polices et licences",
            (
                "Polices fournies avec l'app (Montserrat, Poppins, Anton, Bebas Neue, Inter) : licence SIL "
                "OFL, libres pour la publicité.",
                "Une police de Windows ou importée (« Importer une police… », .ttf ou .otf) a sa propre "
                "licence : vérifie qu'elle autorise un usage commercial avant de l'utiliser dans une pub.",
                "Une police importée est copiée dans le dossier de l'app : le projet la garde même si le "
                "fichier d'origine est déplacé.",
                "Sur un ordinateur où la police manque, Inter la remplace (un message orange le dit) et le "
                "style garde son nom : rien n'est perdu.",
            ),
        ),
        Rubrique(
            "Préréglages",
            (
                "Un préréglage garde tout le style : onglets Texte, Mots, Animations, Position et Découpage. "
                "Ni le format ni la zone de sécurité : ils dépendent de la vidéo et de la plateforme.",
                "Choisis-en un dans la liste « Préréglage » pour l'appliquer. Dès que tu changes un réglage, "
                "la liste affiche « (modifié) » : ton projet garde sa propre copie du style.",
                "« Enregistrer… » crée un préréglage avec le style du projet. Menu ⋯ : « Mettre à jour » le "
                "préréglage avec tes changements, ou « Revenir » à lui.",
                "Six styles sont fournis (Blanc contour noir, Surligneur, Karaoké, Mot par mot, Bandeau, "
                "Atténué) : modifie-les ou supprime-les, « Rétablir les préréglages fournis » les remet.",
                "Si un préréglage change le découpage et défait un sous-titre réorganisé à la main, l'app te "
                "demande d'abord, comme pour un réglage.",
            ),
        ),
        Rubrique(
            "Frise",
            (
                "Sous l'aperçu, la frise montre toute la pub : un bloc par sous-titre (numéroté), un petit "
                "trait par mot (son texte au survol), et le trait mauve du moment lu.",
                "Un clic y place la lecture ; un clic sur un bloc le choisit, comme dans la liste en dessous.",
                "Glisse le bord commun de deux sous-titres : il saute de mot en mot, et les mots qui vont "
                "changer de sous-titre se colorent. Au relâchement, ils passent de l'un à l'autre, avec les "
                "règles de « Monter le premier mot » et « Descendre le dernier mot » (en rouge : la raison du "
                "refus s'affiche). Le moment des mots, lui, ne change jamais.",
                "Ctrl + molette : zoom ; molette : défilement de la frise agrandie. Échap annule un glissement.",
            ),
        ),
        Rubrique(
            "Aperçu",
            (
                "L'aperçu dessine les sous-titres avec le même moteur que les exports : ce que tu vois "
                "est ce qui est exporté, à la finesse de ton écran près.",
                "Fond « Vidéo » : la vidéo du projet ; « Gris » : un fond neutre ; « Damier » : pour juger un "
                "texte prévu pour le calque transparent.",
                "« 100 % » montre un pixel de la vidéo par pixel de ton écran, pour juger la netteté ; la "
                "zone défile.",
                "La boucle rejoue le sous-titre choisi dans la liste ; la barre Espace lance ou arrête la "
                "lecture. Le sous-titre change exactement sur l'image où son premier mot commence.",
                "Repères : pointillés mauves pour la zone de sécurité, trait rouge pour la marge maximum, "
                "grille des tiers et du milieu.",
                "La vidéo n'est pas copiée dans le projet : si elle a été déplacée, « Retrouver la vidéo… » "
                "te la fait choisir à son nouvel endroit.",
            ),
        ),
        Rubrique(
            "Position et format",
            (
                "« Haut » et « Bas » placent le sous-titre juste à l'intérieur de la zone de sécurité de la "
                "plateforme : le même réglage convient à TikTok comme à Reels. Le réglage fin le décale (tu "
                "peux aussi le glisser dans l'aperçu) ; il s'arrête avant la marge maximum.",
                "Un sous-titre de deux lignes grandit vers le bas (Haut), des deux côtés (Centre) ou vers le "
                "haut (Bas).",
                "L'alignement à gauche ou à droite part du bord de la zone de sécurité ; il peut changer le "
                "découpage, comme la largeur maximale des lignes (réglages avancés).",
                "Avec une vidéo, le format est le sien : le calque transparent doit avoir sa taille exacte. "
                "Sans vidéo, choisis-le (9:16, 4:5…) ou donne une taille personnalisée.",
                "Sous-titres d'une prise de voix : « Choisir une vidéo… » (onglet Écran) montre tes "
                "sous-titres sur ton montage, avec le moment où la voix commence.",
            ),
        ),
        Rubrique(
            "Zone de sécurité et marge maximum",
            (
                "La zone de sécurité dépend de la plateforme choisie : c'est la partie de l'écran que les "
                "boutons de l'application (TikTok, Reels…) ne cachent pas. Le texte y reste normalement.",
                "Une ligne trop large peut déborder jusqu'à la marge maximum, jamais au-delà ; sinon, le "
                "sous-titre est redécoupé.",
                "Les largeurs sont mesurées en pixels par le moteur de dessin, avec la police, la taille, les "
                "espaces, le contour et le fond : « ça tient » veut dire « ça tient une fois dessiné ».",
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
            "Exporter",
            (
                "« Vidéo avec sous-titres… » : ta vidéo avec ses sous-titres incrustés, prête à publier (MP4 et "
                "H.264 au départ). Chaque image garde son moment exact, et le son est copié tel quel.",
                "« Calque transparent… » : les sous-titres seuls, animations comprises, sur un fond transparent "
                "(MOV, ProRes 4444). Pose-le dans Premiere Pro sur une piste au-dessus de ton montage, au même "
                "point de départ : il tombe juste, image par image.",
                "Les deux sont dessinés par le moteur de l'aperçu : ce que tu vois dans le studio est ce qui sort.",
                "« Fichier SRT… » : le texte et le moment de chaque sous-titre, sans style. Premiere Pro et la "
                "plupart des logiciels le lisent, accents compris.",
                "Chaque export passe par sa fenêtre : réglages, résumé avant export (ta source et l'export côte à "
                "côte), puis l'avancement. Ta vidéo n'est jamais modifiée.",
            ),
        ),
    ),
)

EXPORT = PageDeConseils(
    "Exporter le calque transparent",
    (
        Rubrique(
            "Le calque transparent",
            (
                "C'est une vidéo des sous-titres seuls, sur un fond transparent : tout ce que tu vois dans "
                "l'aperçu (mot actif, animations, fond qui glisse), image par image.",
                "Il a la taille et le nombre d'images par seconde de ta vidéo, à partir de 0 s : posé au même "
                "endroit que ta vidéo ou ta voix, il ne se décale jamais, même au bout de 10 minutes.",
                "Sans vidéo (sous-titres d'une voix) : choisis le nombre d'images par seconde de ta séquence "
                "Premiere Pro (30 au départ) ; avec une vidéo d'aperçu, c'est le sien qui est proposé.",
            ),
        ),
        Rubrique(
            "Le poser dans Premiere Pro",
            (
                "Importe le fichier .mov, puis pose-le sur une piste au-dessus de ta vidéo (V2 au-dessus de V1), "
                "au même point de départ que ta vidéo, ou que ta voix pour des sous-titres d'une prise.",
                "Premiere Pro lit sa transparence : seuls les sous-titres apparaissent sur ton montage.",
                "Si tu changes un réglage des sous-titres, exporte un nouveau calque et remplace l'ancien sur la "
                "piste (ferme d'abord le projet Premiere Pro si tu gardes le même nom de fichier).",
            ),
        ),
        Rubrique(
            "Poids et place sur le disque",
            (
                "ProRes 4444 est un format de montage, sans perte visible : jusqu'à environ 40 Mo par seconde en "
                "1080 × 1920 (souvent bien moins, la transparence prend peu de place).",
                "L'app vérifie la place libre avant de commencer ; supprime les anciens calques dont tu n'as plus "
                "besoin.",
            ),
        ),
        Rubrique(
            "Pendant l'export",
            (
                "Les images sont dessinées puis encodées par FFmpeg, intégré à l'app : la barre d'avancement et "
                "le temps restant te disent où il en est.",
                "Au tout premier export, FFmpeg est d'abord préparé (quelques secondes, une seule fois) : il "
                "est rangé avec l'app sur ton ordinateur (100 Mo), dans « AppData\\Local\\UGC Studio ».",
                "« Arrêter » interrompt l'export : rien n'est gardé. Le fichier ne prend son nom qu'une fois "
                "terminé (avant, il s'appelle « … .mov.en-cours »).",
                "Le dossier choisi (celui de la vidéo, celui du projet ou un autre) est retenu pour la prochaine "
                "fois.",
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
                "Les accroches d'une série « Accroches seulement » du module Script arrivent ici, une par "
                "variante : seule la réplique 1 change.",
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

VARIANTES_SCRIPT = PageDeConseils(
    "Variantes de script",
    (
        Rubrique(
            "Trois façons de faire",
            (
                "« Mêmes réglages » : le modèle propose autant d'accroches que de variantes, sur des angles "
                "différents, puis écrit un script complet pour chacune.",
                "« Réglages par variante » : chaque colonne part du brief ; change seulement ce que tu veux "
                "comparer (angle, accroche, durée, réseau, personne qui parle, consigne, modèle). Les valeurs "
                "modifiées sont en mauve.",
                "« Accroches seulement » : un seul script est écrit et relu, puis le modèle propose d'autres "
                "accroches pour sa réplique 1. Le corps reste identique : c'est la bonne façon de tester des "
                "accroches.",
            ),
        ),
        Rubrique(
            "Écriture",
            (
                "Le coût total estimé s'affiche avant de lancer.",
                "Les scripts s'écrivent l'un après l'autre ; « Arrêter » stoppe après celui en cours, et ceux "
                "déjà écrits sont gardés.",
                "Les scripts d'une série portent une lettre (« Script 5 (variante B) ») et restent ensemble "
                "dans la liste ; « Comparer… » les met côte à côte.",
                "Série « Accroches seulement » : menu ⋯ d'un de ses scripts, « Envoyer les accroches en "
                "variantes » ouvre les variantes A/B du module Voix, une par accroche.",
            ),
        ),
    ),
)

COMPARAISON_SCRIPTS = PageDeConseils(
    "Comparer les scripts",
    (
        Rubrique(
            "Comparer",
            (
                "Choisis 2 ou 3 scripts en haut des colonnes : accroche, répliques, durée estimée et relecture "
                "s'affichent côte à côte.",
                "Au départ, la fenêtre montre ta dernière série de variantes, ou une retouche à côté de son "
                "original, sinon tes scripts les plus récents.",
                "« Envoyer dans Voix » sous une colonne envoie ce script dans le module Voix.",
            ),
        ),
        Rubrique(
            "Choisir",
            (
                "Sur la carte d'un script : note-le avec les étoiles, et « Retenir » ceux que tu gardes.",
                "Pour comparer des accroches à l'écoute, écris une série « Accroches seulement », puis envoie-la "
                "en variantes dans le module Voix.",
            ),
        ),
    ),
)

BIBLIOTHEQUE_BRIEFS = PageDeConseils(
    "Bibliothèque de briefs",
    (
        Rubrique(
            "Enregistrer et charger",
            (
                "« Enregistrer » (bloc Brief) range le brief du projet ouvert sous un nom ; un nom déjà pris "
                "remplace l'ancien brief, après confirmation.",
                "« Charger » remplace le brief du projet ouvert. Tes options d'écriture (cases, modèle, nombre "
                "d'accroches) ne changent pas.",
                "« Reprendre aussi la page produit lue » : la page et sa fiche reviennent avec le brief, sans "
                "relire la page ni repayer son analyse.",
            ),
        ),
        Rubrique(
            "Organiser",
            (
                "Menu ⋯ d'un brief : le renommer ou le supprimer.",
                "La bibliothèque sert à tous tes projets : un même produit peut avoir un projet par réseau ou "
                "par langue.",
            ),
        ),
    ),
)

PREREGLAGES = PageDeConseils(
    "Préréglages de sous-titres",
    (
        Rubrique(
            "Les vignettes",
            (
                "Chaque vignette rejoue un exemple de sous-titre avec le préréglage, dessiné par le même moteur "
                "que l'aperçu : mot actif, animations, police et couleurs compris.",
                "★ marque le préréglage des nouveaux projets ; « style du projet » : celui du projet ouvert.",
            ),
        ),
        Rubrique(
            "Créer et modifier",
            (
                "« Nouveau » part du style de départ ; « Dupliquer » (menu ⋯) part d'un préréglage existant.",
                "Pour modifier un préréglage : « Appliquer », règle le style dans le studio, puis « Mettre à "
                "jour ce préréglage » (menu ⋯ à côté de la liste « Préréglage »).",
                "Un projet garde sa propre copie du style : modifier ou supprimer un préréglage ne change pas "
                "les projets déjà faits.",
            ),
        ),
        Rubrique(
            "Partager",
            (
                "« Exporter… » (menu ⋯) écrit un petit fichier .json, lisible : une copie de sécurité, ou un "
                "style à passer sur un autre ordinateur, où « Importer… » l'ajoute à la liste.",
                "Si une police du préréglage manque sur cet ordinateur, Inter la remplace et le préréglage "
                "garde son nom : installe ou importe la police pour la retrouver.",
                "Les polices fournies avec l'app (Montserrat, Poppins, Anton, Bebas Neue, Inter) s'affichent "
                "pareil partout.",
            ),
        ),
    ),
)

MEILLEURS_SCRIPTS = PageDeConseils(
    "Mes meilleurs scripts",
    (
        Rubrique(
            "Comment le modèle s'en sert",
            (
                "Le guide de Google le dit : une demande avec des exemples marche mieux. Pour chaque script, "
                "l'app choisit jusqu'à 3 exemples proches : même langue, puis même réseau, puis même angle.",
                "Le modèle s'en inspire pour le ton et le rythme, sans les recopier. Tes scripts passent avant "
                "les scripts fournis.",
            ),
        ),
        Rubrique(
            "Ajouter, noter, retirer",
            (
                "« Garder comme exemple » (menu ⋯ d'un script) ajoute un script écrit dans l'app.",
                "« Ajouter un script qui a marché… » : colle un script écrit ailleurs, une réplique par "
                "paragraphe, l'accroche en premier.",
                "Ta note (ex. « CPA 9 € », « meilleur ROAS ») accompagne l'exemple : le modèle la lit.",
                "Les 5 scripts fournis parlent de produits imaginaires : retire-les quand tu as assez de vrais "
                "scripts ; « Remettre les exemples fournis » les fait revenir.",
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

EXPORT_VIDEO = PageDeConseils(
    "Exporter la vidéo avec sous-titres",
    (
        Rubrique(
            "Format et codec",
            (
                "MP4 et H.264 (au départ) : accepté partout, TikTok, Instagram, YouTube et Premiere Pro compris.",
                "H.265 : la même image pour un fichier plus léger, mais un encodage plus long ; lu par les "
                "téléphones et les ordinateurs récents.",
                "ProRes 422 HQ (en MOV seulement) : un format de montage, sans perte visible, pour retravailler la "
                "vidéo dans Premiere Pro. Le fichier est très lourd : pas pour publier.",
                "MKV : pour archiver ; Premiere Pro ne le lit pas.",
            ),
        ),
        Rubrique(
            "Débit",
            (
                "Le débit, c'est la quantité d'information par seconde : plus il est haut, plus l'image est fidèle, "
                "et plus le fichier est lourd.",
                "« Identique (+ 10 %) » : celui de ta vidéo, un peu plus, car une vidéo réencodée perd toujours un "
                "peu. C'est le choix de départ.",
                "« Conseillé » : le double du débit conseillé par YouTube pour cette taille d'image, de quoi garder "
                "une belle image après la recompression des plateformes. Proposé pour une vidéo en format de "
                "montage (ProRes), qui à son propre débit donnerait un fichier énorme.",
                "TikTok refuse les fichiers de plus de 500 Mo : le résumé te prévient si l'estimation les dépasse.",
            ),
        ),
        Rubrique(
            "Ce qui est gardé",
            (
                "Chaque image de ta vidéo garde son moment exact, même avec une fréquence variable (iPhone, "
                "enregistrement d'écran) : les sous-titres sont ceux de ce moment.",
                "Le son est copié tel quel, sans aucune perte. S'il ne peut pas aller dans le format choisi (un son "
                "non compressé vers un MP4), il est converti en AAC à 320 kb/s, et le résumé l'indique en mauve.",
                "Les couleurs des sous-titres sont celles de l'aperçu : elles sont converties avec la norme de ta "
                "vidéo (BT.709 pour une vidéo HD).",
                "Une vidéo HDR (iPhone réglé en HDR) arrivera avec la version 3.0.0 ; en attendant, exporte le "
                "calque transparent.",
            ),
        ),
        Rubrique(
            "Pendant l'export",
            (
                "Trois étapes : le dessin des sous-titres, puis l'encodage en deux passages (le premier analyse ta "
                "vidéo, le second répartit le débit là où il sert : la meilleure qualité pour le poids). Le ProRes "
                "n'a qu'un passage.",
                "« Arrêter » interrompt l'export : rien n'est gardé. Les fichiers provisoires vont dans le dossier "
                "temporaire de Windows et sont effacés à la fin.",
                "À la fin, la durée de l'export s'affiche : « Lire la vidéo » l'ouvre dans le lecteur de Windows.",
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
    "variantes-script": VARIANTES_SCRIPT,
    "comparaison-scripts": COMPARAISON_SCRIPTS,
    "bibliotheque-briefs": BIBLIOTHEQUE_BRIEFS,
    "meilleurs-scripts": MEILLEURS_SCRIPTS,
    "prereglages": PREREGLAGES,
    "export": EXPORT,
    "export-video": EXPORT_VIDEO,
}
