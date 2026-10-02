"""Règle du §9 : « Aucune valeur de taille, couleur ou espacement n'est écrite en dur ailleurs »
que dans ugc_studio/ui/theme.py. Ce test lit tout le code de l'app et signale les écarts."""

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1] / "ugc_studio"
FICHIER_THEME = RACINE / "ui" / "theme.py"

# Textes interdits hors du thème : couleurs « #RRGGBB », tailles « 12px », couleurs « rgb(…) ».
MOTIF_TEXTE = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b|\b\d+(?:\.\d+)?px\b|\brgba?\(")

# Fonctions Qt de mise en page qui ne doivent recevoir que des valeurs du thème (ou 0).
FONCTIONS_DE_TAILLE = {
    "setContentsMargins",
    "setSpacing",
    "setHorizontalSpacing",
    "setVerticalSpacing",
    "addSpacing",
    "setFixedWidth",
    "setFixedHeight",
    "setFixedSize",
    "setMinimumWidth",
    "setMinimumHeight",
    "setMinimumSize",
    "setMaximumWidth",
    "setMaximumHeight",
    "setMaximumSize",
    "resize",
    "setPixelSize",
    "setPointSize",
    "setIconSize",
    "setMinimumContentsLength",
    "QSize",
    "QColor",
}


def _fichiers():
    return [f for f in sorted(RACINE.rglob("*.py")) if f != FICHIER_THEME]


def _nom_appel(noeud: ast.Call) -> str | None:
    if isinstance(noeud.func, ast.Attribute):
        return noeud.func.attr
    if isinstance(noeud.func, ast.Name):
        return noeud.func.id
    return None


def test_aucune_couleur_ni_taille_en_dur():
    ecarts = []
    for fichier in _fichiers():
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                if MOTIF_TEXTE.search(noeud.value):
                    ecarts.append(f"{fichier.relative_to(RACINE)}:{noeud.lineno} texte « {noeud.value[:40]} »")
            elif isinstance(noeud, ast.Call) and _nom_appel(noeud) in FONCTIONS_DE_TAILLE:
                for argument in [*noeud.args, *(k.value for k in noeud.keywords)]:
                    # Un nombre qui multiplie ou divise une valeur du thème (ex. « 2 × marge »,
                    # pour les deux côtés) n'est pas une valeur de design : il est accepté.
                    facteurs = {
                        id(cote)
                        for binaire in ast.walk(argument)
                        if isinstance(binaire, ast.BinOp) and isinstance(binaire.op, (ast.Mult, ast.Div, ast.FloorDiv))
                        for cote in (binaire.left, binaire.right)
                    }
                    for sous in ast.walk(argument):
                        if (
                            isinstance(sous, ast.Constant)
                            and isinstance(sous.value, (int, float))
                            and not isinstance(sous.value, bool)
                            and sous.value != 0
                            and id(sous) not in facteurs
                        ):
                            ecarts.append(
                                f"{fichier.relative_to(RACINE)}:{noeud.lineno} "
                                f"{_nom_appel(noeud)}(… {sous.value} …)"
                            )
    assert not ecarts, "Valeurs de design écrites en dur (à déplacer dans ui/theme.py) :\n" + "\n".join(ecarts)


# Éléments qui se créent toujours avec une fonction de ui/composants/elements.py.
CREES_PAR_ELEMENTS = {
    "QComboBox": "liste_deroulante()",
    "QSlider": "glissiere()",
    "QSpinBox": "champ_entier()",
    "QDoubleSpinBox": "champ_decimal()",
    # Onglets standard de Qt : trait mauve qui effaçait la ligne de séparation, réglage difficile.
    "QTabWidget": "Onglets() (composants/onglets.py)",
}


def test_elements_crees_avec_les_fonctions_de_l_app():
    """- Une QComboBox créée directement prend comme largeur *minimale* celle de son plus long
      choix : un choix long (nom d'une voix…) élargit toute la page au-delà de la fenêtre et le
      bord droit est coupé.
    - Listes, barres de lecture et champs de nombre créés directement changent de valeur quand la
      molette de la souris passe dessus pendant qu'on fait défiler la page (et bloquent le
      défilement).
    Ils se créent donc toujours avec les fonctions de elements.py, qui règlent ces deux points."""
    autorise = RACINE / "ui" / "composants" / "elements.py"
    ecarts = [
        f"{fichier.relative_to(RACINE)}:{noeud.lineno} {_nom_appel(noeud)}() → {CREES_PAR_ELEMENTS[_nom_appel(noeud)]}"
        for fichier in _fichiers()
        if fichier != autorise
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8")))
        if isinstance(noeud, ast.Call) and _nom_appel(noeud) in CREES_PAR_ELEMENTS
    ]
    assert not ecarts, "Éléments à créer avec les fonctions de elements.py :\n" + "\n".join(ecarts)


CASE_TEXTE_MAX = 48  # caractères


def test_textes_des_cases_a_cocher_courts():
    """Le texte d'une case à cocher ne passe jamais à la ligne : une longue phrase impose sa largeur
    à toute la page, qui déborde à droite quand la fenêtre est étroite (960 px). Les explications
    vont dans l'icône « i » de elements.case_a_cocher() (V3.1), lue au survol."""
    ecarts = [
        f"{fichier.relative_to(RACINE)}:{noeud.lineno} « {noeud.args[0].value} »"
        for fichier in _fichiers()
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8")))
        if isinstance(noeud, ast.Call)
        and _nom_appel(noeud) in ("QCheckBox", "case_a_cocher")
        and noeud.args
        and isinstance(noeud.args[0], ast.Constant)
        and isinstance(noeud.args[0].value, str)
        and len(noeud.args[0].value) > CASE_TEXTE_MAX
    ]
    assert not ecarts, "Texte de case à cocher trop long (mettre l'explication dans l'icône « i ») :\n" + "\n".join(ecarts)


# Constantes qui contiennent un tiret long pour une bonne raison : la ponctuation reconnue dans une
# transcription, et les anciens noms et messages de la v1.0.0, relus pour leur retirer ce tiret.
CONSTANTES_AVEC_TIRET = {"PONCTUATION", "_ANCIEN_NOM_DE_VARIANTE", "_ANCIEN_MESSAGE_CLE_VALIDE"}


def _textes_hors_interface(arbre: ast.AST) -> set[int]:
    """Textes qui ne s'affichent jamais dans l'interface : docstrings, messages du journal
    technique, et constantes de CONSTANTES_AVEC_TIRET."""
    ignores: set[int] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            premier = noeud.body[0] if noeud.body else None
            if isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant):
                ignores.add(id(premier.value))
        elif (
            isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Attribute)
            and isinstance(noeud.func.value, ast.Name)
            and noeud.func.value.id in ("journal", "logging")
        ):
            ignores.update(id(sous) for sous in ast.walk(noeud))
        elif isinstance(noeud, ast.Assign) and any(
            isinstance(cible, ast.Name) and cible.id in CONSTANTES_AVEC_TIRET for cible in noeud.targets
        ):
            ignores.update(id(sous) for sous in ast.walk(noeud.value))
    return ignores


def test_aucun_tiret_long_dans_les_textes_de_l_interface():
    """En français, le tiret long (« — ») ne sert pas de séparateur (décision du 30/09/2026) :
    l'interface met une puce « • » entre un module et un projet (« Voix • Sérum Glowzy », V3.2 ; « / »
    avant), et ailleurs la ponctuation qui convient à l'endroit : parenthèses, point médian « · »,
    deux-points, virgule."""
    ecarts = []
    for fichier in sorted(RACINE.rglob("*.py")):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        ignores = _textes_hors_interface(arbre)
        for noeud in ast.walk(arbre):
            if (
                isinstance(noeud, ast.Constant)
                and isinstance(noeud.value, str)
                and ("—" in noeud.value or "–" in noeud.value)
                and id(noeud) not in ignores
            ):
                ecarts.append(f"{fichier.relative_to(RACINE)}:{noeud.lineno} « {noeud.value[:50]} »")
    assert not ecarts, "Tiret long dans un texte de l'interface :\n" + "\n".join(ecarts)


# Lignes grises qui ne sont pas des infos : exemples de la galerie des styles, crédits.
TEXTES_QUI_NE_SONT_PAS_DES_INFOS = {
    "Texte secondaire : explications et descriptions.",
    "Légende : 12 px, pour les petites indications.",
    "Icônes Lucide (licence ISC) · Police Inter (licence SIL OFL 1.1).",
}
MOTS_D_UNE_PHRASE = 5  # à partir de 5 mots, avec un point final, un texte gris est une phrase d'aide
# L'ampoule : devant les infos (elements.py) et sur le bouton « Conseils » (conseils.py).
FICHIERS_AVEC_AMPOULE = {Path("ui") / "composants" / "elements.py", Path("ui") / "composants" / "conseils.py"}


def _texte_ecrit(noeud: ast.AST) -> str | None:
    """Texte écrit tel quel dans le code : « "…" », ou « f"…{x}…" » (chaque {x} compte pour un mot)."""
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
        return noeud.value
    if isinstance(noeud, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "x" for v in noeud.values)
    return None


def _role(appel: ast.Call) -> str | None:
    if len(appel.args) > 1 and isinstance(appel.args[1], ast.Constant):
        return appel.args[1].value
    for argument in appel.keywords:
        if argument.arg == "role" and isinstance(argument.value, ast.Constant):
            return argument.value.value
    return None


def test_les_phrases_d_aide_sont_des_infos():
    """Chaque phrase d'aide grise (sous un bloc, un champ, en haut d'une fenêtre) commence par la
    même ampoule (§9.4 bis). Elle s'écrit donc avec info() de elements.py, jamais avec un simple
    libelle() gris : ce test signale les libelle() « legende » ou « secondaire » dont le texte est
    une phrase. Et l'ampoule n'est dessinée que par elements.py (et par le bouton « Conseils ») :
    pas d'autre façon d'écrire une info. (Les listes vides ont leur propre style, « discret » : ce ne
    sont pas des infos.)"""
    ecarts = []
    for fichier in _fichiers():
        source = fichier.read_text(encoding="utf-8")
        if fichier.relative_to(RACINE) not in FICHIERS_AVEC_AMPOULE and '"lightbulb"' in source:
            ecarts.append(f"{fichier.relative_to(RACINE)} dessine l'ampoule : utiliser info()")
        for noeud in ast.walk(ast.parse(source)):
            if not (isinstance(noeud, ast.Call) and _nom_appel(noeud) == "libelle" and noeud.args):
                continue
            texte = _texte_ecrit(noeud.args[0])
            if (
                texte is not None
                and _role(noeud) in ("legende", "secondaire")
                and texte.rstrip().endswith(".")
                and len(re.findall(r"\w+", texte)) >= MOTS_D_UNE_PHRASE
                and texte not in TEXTES_QUI_NE_SONT_PAS_DES_INFOS
            ):
                ecarts.append(f"{fichier.relative_to(RACINE)}:{noeud.lineno} « {texte[:60]} »")
    assert not ecarts, "Phrase d'aide à écrire avec info() (ampoule devant) :\n" + "\n".join(ecarts)


# V3.1 (annexe du document de la version) : une phrase d'aide ne reste écrite à l'écran que si elle
# est indispensable pour savoir quoi faire à ce moment ; les autres explications passent dans une
# icône « i » (BoutonInfo, paramètre `aide=`), lue au survol. Nombre d'info() permis par fichier :
# écrire une phrase de plus à l'écran est une décision, pas un réflexe.
INFOS_VISIBLES_PERMISES = {
    "ui/composants/elements.py": 1,  # la fonction info() elle-même
    "ui/galerie.py": 1,  # la galerie des composants
    "ui/pages/transcription/atelier.py": 1,  # quoi déposer
    "ui/composants/correcteur_mots.py": 1,  # cliquer sur un mot pour le corriger (V3.1 : aussi pour les mots importés)
    "ui/pages/script/formulaire.py": 1,  # passer la langue du projet ? (une question)
    "ui/pages/script/produit.py": 2,  # état de la page lue (une donnée) ; noms à faire prononcer
    "ui/pages/script/resultats.py": 2,  # cocher les accroches ; étiquette « IA » de TikTok
    "ui/pages/voix/sans_projet.py": 1,  # sans projet, la page est vide
    "ui/pages/sous_titres/apercu.py": 1,  # pendant la pipette
    "ui/pages/sous_titres/atelier.py": 1,  # pourquoi « Vidéo avec sous-titres » est grisé
    "ui/pages/sous_titres/onglet_mots.py": 1,  # pourquoi l'état « Accentués » ne change rien
    "ui/pages/sous_titres/reglages.py": 1,  # le format suit la vidéo
    "ui/pages/reglages/onglet_modeles.py": 1,  # taux de départ à vérifier (ou la date du taux)
    "ui/dialogues/choix_modeles.py": 1,  # aucune clé testée : quoi faire
    "ui/dialogues/cle_api.py": 1,  # où créer sa clé
    "ui/dialogues/meilleurs_scripts.py": 1,  # une réplique par paragraphe
    "ui/dialogues/prononciation.py": 1,  # comment remplir le tableau
    "ui/dialogues/remplacements.py": 1,  # comment remplir le tableau
    "ui/dialogues/comparer_scripts.py": 1,  # choisir 2 ou 3 scripts
}


def test_phrases_d_aide_ecrites_seulement_si_indispensables():
    compte: dict[str, int] = {}
    for fichier in _fichiers():
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            journal = (
                isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and isinstance(noeud.func.value, ast.Name)
                and noeud.func.value.id in ("journal", "logging")
            )
            if isinstance(noeud, ast.Call) and _nom_appel(noeud) in ("info", "Info") and not journal:
                nom = fichier.relative_to(RACINE).as_posix()
                compte[nom] = compte.get(nom, 0) + 1
    ecarts = [
        f"{nom} : {nombre} info() (permis : {INFOS_VISIBLES_PERMISES.get(nom, 0)})"
        for nom, nombre in sorted(compte.items())
        if nombre > INFOS_VISIBLES_PERMISES.get(nom, 0)
    ]
    assert not ecarts, "Phrase d'aide écrite à l'écran : la mettre dans une icône « i » (aide=…) :\n" + "\n".join(ecarts)
