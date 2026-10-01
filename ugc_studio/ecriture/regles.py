"""Liste intégrée des règles publicitaires qui touchent un script (V2, §10.1 et §10.8).

Le modèle relit chaque script avec cette liste, et non « de mémoire » : sa mémoire peut dater, et
une recherche en direct donne souvent des pages non officielles. Chaque règle a sa source et la
date de sa vérification ; la liste est mise à jour avec le cahier des charges.

Chaque règle est écrite deux fois : en français (fenêtre « Conseils », relecture affichée) et en
anglais (consigne donnée au modèle, comme toutes ses consignes). Aucun outil ne garantit qu'une pub
sera acceptée : la plateforme reste seule juge (ce n'est pas un avis juridique).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

VERIFIEES_LE = date(2026, 10, 1)

TIKTOK_TROMPEUR = (
    "TikTok, Misleading and false content",
    "https://ads.tiktok.com/help/article/tiktok-ads-policy-misleading-and-false-content",
)
TIKTOK_CONSEILS_REGLES = (
    "TikTok, Ad policy tips (2024)",
    "https://ads.tiktok.com/business/library/TikTok_Ad_Policy_SMB2024.pdf",
)
META_ATTRIBUTS = (
    "Meta, Personal attributes",
    "https://transparency.meta.com/policies/ad-standards/objectionable-content/personal-attributes/",
)
META_NORMES = ("Meta, Normes publicitaires", "https://transparency.meta.com/policies/ad-standards/")
DIRECTIVE_PRATIQUES_DELOYALES = (
    "Directive 2005/29/CE (pratiques commerciales déloyales), annexe I, point 7",
    "https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32005L0029",
)
MODERN_RETAIL = (
    "Modern Retail, pubs des marques d'hygiène féminine (2023)",
    "https://www.modernretail.co/marketing/feminine-care-brands-are-getting-creative-despite-marketing-limitations/",
)


@dataclass(frozen=True)
class Regle:
    identifiant: str
    francais: str  # affichée dans l'app
    anglais: str  # donnée au modèle
    source: tuple[str, str]  # (nom, adresse)
    reseaux: tuple[str, ...] = ()  # vide : tous les réseaux
    verifiee_le: date = VERIFIEES_LE


REGLES: tuple[Regle, ...] = (
    Regle(
        "promesses",
        "Pas de résultat garanti, immédiat ou exagéré (« effet immédiat », « résultat garanti »). Une promesse "
        "chiffrée de la marque reste possible telle qu'écrite sur la page (« jusqu'à 12 h »), jamais comme une "
        "garantie.",
        "No guaranteed, immediate or exaggerated results ('instant effect', 'guaranteed results', 'get slim legs "
        "right away'). A figure stated by the brand on the product page may be used exactly as written, with its "
        "qualifier ('up to 12 hours'), never as a guarantee.",
        TIKTOK_TROMPEUR,
    ),
    Regle(
        "superlatifs",
        "Pas de superlatif absolu impossible à prouver (« n°1 », « le meilleur au monde », « le seul »).",
        "No absolute superlative that cannot be proven ('number 1', 'the best in the world', 'the only one').",
        TIKTOK_TROMPEUR,
    ),
    Regle(
        "sante",
        "Pas de promesse de santé ou de guérison (« guérit », « soigne », « traite ») pour un produit qui n'est "
        "pas un médicament : parler de confort, de sensation, d'usage au quotidien.",
        "No health or cure claim ('cures', 'heals', 'treats', 'prevents') for a product that is not a medicine; "
        "talk about comfort, feel and everyday use instead.",
        TIKTOK_TROMPEUR,
    ),
    Regle(
        "avant_apres",
        "Pas d'avant/après de poids ou de peau promis (en chiffres ou « regarde la différence ») ; raconter son "
        "ressenti reste possible, sans promettre le même résultat à la personne qui regarde.",
        "No before/after promise about weight or skin (no figures, no 'look at the difference'). The speaker may "
        "tell how they feel, without promising the viewer the same result.",
        META_NORMES,
    ),
    Regle(
        "prix",
        "Prix et promo exactement ceux du brief ou de la page : la vidéo, le texte de la pub et la page doivent "
        "dire la même chose.",
        "Price and discount must be exactly those of the brief or the product page: the video, the ad text and "
        "the landing page must say the same thing.",
        TIKTOK_CONSEILS_REGLES,
    ),
    Regle(
        "urgence",
        "Pas d'urgence ou de rareté inventée (« plus que 2 en stock », « dernier jour ») sans information du "
        "brief ou de la page.",
        "No invented urgency or scarcity ('only 2 left', 'last day', 'ends tonight') unless the brief or the "
        "page states it.",
        DIRECTIVE_PRATIQUES_DELOYALES,
    ),
    Regle(
        "action",
        "Un appel à l'action faisable dans la pub (« Clique sur le lien en dessous ») : pas de « lien dans ma "
        "bio », ni d'action que l'app du réseau ne propose pas.",
        "The call to action must be something the viewer can actually do in this ad on this network (e.g. 'tap "
        "the link below'): no 'link in my bio', no action the app does not offer.",
        TIKTOK_CONSEILS_REGLES,
    ),
    Regle(
        "personnes",
        "Jamais le nom d'une personne réelle (coach, sportif, célébrité, influenceur), même cité par la page : "
        "une recommandation impossible à prouver est un risque.",
        "Never name a real person (coach, athlete, celebrity, influencer), even if the product page mentions one.",
        TIKTOK_TROMPEUR,
    ),
    Regle(
        "intime",
        "Produits intimes (culottes menstruelles, lingerie, hygiène intime) : pas de mot anatomique ni de "
        "description crue ; parler de confort, de protection, de liberté.",
        "Intimate products (period underwear, lingerie, intimate hygiene): no anatomical words and no graphic "
        "description; talk about comfort, protection, freedom and everyday life.",
        MODERN_RETAIL,
    ),
    Regle(
        "attributs",
        "Ne jamais supposer une caractéristique personnelle de la personne qui regarde (santé, âge, poids, "
        "finances, religion…) : « Tu as de l'acné ? » est refusé, « Ma routine anti-boutons tient en 2 "
        "produits » est accepté.",
        "Never assert or imply a personal attribute of the viewer (health or medical condition, age, weight, "
        "financial status, religion, sexual life...). Refused: 'Do you have acne?', 'Tired of your belly fat?'. "
        "Accepted: the speaker talks about themself or about the product ('My anti-blemish routine is just 2 "
        "products').",
        META_ATTRIBUTS,
        reseaux=("meta",),
    ),
)

# Rappel affiché sur chaque script pour TikTok (règles mises à jour en avril 2026).
RAPPEL_IA_TIKTOK = (
    "Voix générée par l'IA : active l'étiquette « contenu généré par l'IA » quand tu publies la pub "
    "(règle TikTok)."
)
LIMITE_DE_LA_RELECTURE = (
    "La relecture limite les refus, elle ne les empêche pas : la plateforme reste seule juge "
    "(ce n'est pas un avis juridique)."
)


def regles_pour(reseau: str) -> list[Regle]:
    """Règles qui s'appliquent à ce réseau (toutes pour « Autre » : on ne sait pas où la pub ira)."""
    return [r for r in REGLES if not r.reseaux or reseau in r.reseaux or reseau == "autre"]


def texte_pour_le_modele(reseau: str) -> str:
    """Les règles du réseau, numérotées, en anglais."""
    return "\n".join(f"{rang}. {regle.anglais}" for rang, regle in enumerate(regles_pour(reseau), start=1))
