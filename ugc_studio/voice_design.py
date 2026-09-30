"""Assistant de description pour Voice Design (§5.4 bis).

Google conseille une description courte (1 à 2 phrases) des **traits permanents** de la voix :
âge, genre, timbre, texture vocale, accent régional, et un rôle (persona) qui l'ancre. L'assistant
propose ces choix en français et assemble directement la description **en anglais** (envoyée à
Google), avec sa traduction française. Aucun appel à l'API.

Exemple : « jeune femme ~25 ans, voix chaleureuse et légèrement voilée, accent parisien, créatrice
UGC » → « A young woman in her mid-20s with a warm, slightly husky voice and a Parisian French
accent. Spontaneous and playful, like a creator talking to a friend on camera. »
"""

from __future__ import annotations

# Genre : (choix affiché, nom français, nom anglais, possessif anglais, code Google du champ « gender »)
GENRES: tuple[tuple[str, str, str, str, str], ...] = (
    ("femme", "femme", "woman", "her", "female"),
    ("homme", "homme", "man", "his", "male"),
    ("neutre", "personne", "person", "their", "neutral"),
)
# Âge : (français, adjectif anglais facultatif, tranche d'âge anglaise)
AGES: tuple[tuple[str, str, str], ...] = (
    ("environ 20 ans", "young", "early 20s"),
    ("environ 25 ans", "young", "mid-20s"),
    ("environ 30 ans", "", "30s"),
    ("environ 40 ans", "", "40s"),
    ("environ 50 ans", "", "50s"),
    ("environ 65 ans", "", "60s"),
)
TIMBRES: tuple[tuple[str, str], ...] = (
    ("chaleureuse", "warm"),
    ("claire", "clear"),
    ("grave", "deep"),
    ("douce", "soft"),
    ("lumineuse", "bright"),
    ("posée", "calm"),
    ("puissante", "powerful"),
)
TEXTURES: tuple[tuple[str, str], ...] = (
    ("légèrement voilée", "slightly husky"),
    ("veloutée", "velvety"),
    ("soufflée", "breathy"),
    ("rauque", "raspy"),
    ("cristalline", "crystal-clear"),
    ("nette et précise", "crisp"),
)
ACCENTS: tuple[tuple[str, str], ...] = (
    ("français standard", "a neutral standard French accent"),
    ("parisien", "a Parisian French accent"),
    ("du Sud de la France", "a Southern French accent"),
    ("belge", "a Belgian French accent"),
    ("québécois", "a Québécois French accent"),
    ("suisse romand", "a Swiss French accent"),
    ("flamand", "a Flemish accent"),
    ("néerlandais", "a Dutch accent"),
    ("américain", "a General American accent"),
    ("britannique", "a British accent"),
)
# Rôle : (choix affiché, phrase française au masculin, au féminin, phrase anglaise)
PERSONAS: tuple[tuple[str, str, str, str], ...] = (
    (
        "créateur·rice UGC",
        "Spontané et complice, comme face caméra avec un ami.",
        "Spontanée et complice, comme face caméra avec une amie.",
        "Spontaneous and playful, like a creator talking to a friend on camera.",
    ),
    (
        "ami·e complice",
        "Complice, comme en confidence avec un ami proche.",
        "Complice, comme en confidence avec une amie proche.",
        "Friendly and confiding, like sharing a secret with a close friend.",
    ),
    (
        "coach énergique",
        "Énergique et motivant, comme un coach sportif.",
        "Énergique et motivante, comme une coach sportive.",
        "Energetic and motivating, like a fitness coach.",
    ),
    (
        "expert·e rassurant·e",
        "Calme et rassurant, comme un expert de confiance.",
        "Calme et rassurante, comme une experte de confiance.",
        "Calm and reassuring, like a trusted expert.",
    ),
    (
        "vendeur·se passionné·e",
        "Enthousiaste et convaincant, comme un vendeur passionné.",
        "Enthousiaste et convaincante, comme une vendeuse passionnée.",
        "Enthusiastic and persuasive, like a passionate salesperson.",
    ),
    (
        "narrateur·rice documentaire",
        "Posé et captivant, comme un narrateur de documentaire.",
        "Posée et captivante, comme une narratrice de documentaire.",
        "Measured and captivating, like a documentary narrator.",
    ),
    (
        "animateur·rice radio",
        "Dynamique et charismatique, comme un animateur radio.",
        "Dynamique et charismatique, comme une animatrice radio.",
        "Upbeat and charismatic, like a radio host.",
    ),
)


def _trouver(table, francais: str):
    return next((ligne for ligne in table if ligne[0] == francais), None)


def code_genre(genre: str) -> str:
    """« femme » → « female » (champ « gender » de l'API) ; vide si non précisé."""
    ligne = _trouver(GENRES, genre)
    return ligne[4] if ligne else ""


def assembler_description(
    genre: str, age: str = "", timbre: str = "", texture: str = "", accent: str = "", persona: str = ""
) -> tuple[str, str]:
    """Choix en français → (description anglaise, traduction française), en 1 à 2 phrases."""
    ligne_genre = _trouver(GENRES, genre) or GENRES[0]
    _choix, francais_genre, anglais_genre, possessif, code = ligne_genre
    ligne_age = _trouver(AGES, age)

    # Qui : « A young woman in her mid-20s » / « Jeune femme d'environ 25 ans »
    if ligne_age:
        adjectif = f"{ligne_age[1]} " if ligne_age[1] else ""
        anglais = f"A {adjectif}{anglais_genre} in {possessif} {ligne_age[2]}"
        francais = f"{'Jeune ' + francais_genre if ligne_age[1] else francais_genre.capitalize()} d'{ligne_age[0]}"
    else:
        anglais = f"A {anglais_genre}"
        francais = francais_genre.capitalize()

    # Voix : « with a warm, slightly husky voice » / « voix chaleureuse et légèrement voilée »
    qualites_en = [ligne[1] for table, choix in ((TIMBRES, timbre), (TEXTURES, texture)) if (ligne := _trouver(table, choix))]
    qualites_fr = [choix for table, choix in ((TIMBRES, timbre), (TEXTURES, texture)) if _trouver(table, choix)]
    ligne_accent = _trouver(ACCENTS, accent)
    if qualites_en:
        anglais += f" with a {', '.join(qualites_en)} voice"
        francais += f", voix {' et '.join(qualites_fr)}"
        if ligne_accent:
            anglais += f" and {ligne_accent[1]}"
    elif ligne_accent:
        anglais += f" with {ligne_accent[1]}"
    if ligne_accent:
        francais += f", accent {ligne_accent[0]}"
    anglais += "."
    francais += "."

    # Rôle : une 2e phrase courte
    ligne_persona = _trouver(PERSONAS, persona)
    if ligne_persona:
        anglais += f" {ligne_persona[3]}"
        francais += f" {ligne_persona[2] if code == 'female' else ligne_persona[1]}"
    return anglais, francais
