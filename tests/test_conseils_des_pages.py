"""Textes des fenêtres « Conseils » (conseils_des_pages.py) : en français, et tous utilisés."""

import ast
import re
from pathlib import Path

from ugc_studio.conseils import CONSEILS_STYLE, CONSEILS_VOIX
from ugc_studio.conseils_des_pages import PAGES

RACINE_UI = Path(__file__).resolve().parents[1] / "ugc_studio" / "ui"


def _tous_les_textes():
    for cle, page in PAGES.items():
        yield cle, page.titre
        for rubrique in page.rubriques:
            yield cle, rubrique.titre
            for conseil in rubrique.conseils:
                yield cle, conseil


def test_chaque_page_a_des_conseils():
    for cle, page in PAGES.items():
        assert page.titre and page.rubriques, cle
        for rubrique in page.rubriques:
            assert rubrique.titre and rubrique.conseils, (cle, rubrique.titre)
            for conseil in rubrique.conseils:
                assert conseil == conseil.strip() and conseil.endswith("."), (cle, conseil)


def test_en_francais_seulement():
    """Les conseils de Google s'affichent en français : l'anglais d'origine n'apparaît plus (seul un
    exemple de style, entre guillemets, est en anglais)."""
    textes = [texte for _cle, texte in _tous_les_textes()]
    for original in (*CONSEILS_STYLE, *CONSEILS_VOIX):
        assert all(original.anglais not in texte for texte in textes)
    for cle, texte in _tous_les_textes():
        assert "—" not in texte and "–" not in texte, (cle, texte)  # pas de tiret long


def test_les_conseils_de_google_sont_repris():
    styles = {c.francais for c in CONSEILS_STYLE}
    description = {c.francais for c in CONSEILS_VOIX}
    for cle in ("voix", "style"):
        assert styles <= {conseil for rubrique in PAGES[cle].rubriques for conseil in rubrique.conseils}
    assert description <= {c for rubrique in PAGES["creer-une-voix"].rubriques for c in rubrique.conseils}


def _cles_utilisees() -> dict[str, list[str]]:
    """Pages de conseils demandées par l'interface : entete_de_fenetre(titre, "cle"),
    EnteteDePage(titre, sous_titre, "cle"), SansProjet(…, "cle"), bouton_conseils("cle"),
    conseils="cle", et PAGE_CONSEILS = "cle" (fenêtres d'export, V3 : la fenêtre commune en fait
    son en-tête)."""
    position = {"entete_de_fenetre": 1, "EnteteDePage": 2, "SansProjet": 3, "bouton_conseils": 0}
    utilisees: dict[str, list[str]] = {}
    for fichier in sorted(RACINE_UI.rglob("*.py")):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Assign) and any(getattr(cible, "id", None) == "PAGE_CONSEILS" for cible in noeud.targets):
                if isinstance(noeud.value, ast.Constant) and noeud.value.value:
                    utilisees.setdefault(noeud.value.value, []).append(f"{fichier.name}:{noeud.lineno}")
                continue
            if not isinstance(noeud, ast.Call):
                continue
            nom = getattr(noeud.func, "id", getattr(noeud.func, "attr", None))
            arguments = [k.value for k in noeud.keywords if k.arg == "conseils"]
            if nom in position and len(noeud.args) > position[nom]:
                arguments.append(noeud.args[position[nom]])
            for argument in arguments:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    utilisees.setdefault(argument.value, []).append(f"{fichier.name}:{noeud.lineno}")
    return utilisees


def test_chaque_bouton_ouvre_une_page_qui_existe_et_chaque_page_sert():
    utilisees = _cles_utilisees()
    inconnues = {cle: ou for cle, ou in utilisees.items() if cle not in PAGES}
    assert not inconnues, f"Pages de conseils inconnues : {inconnues}"
    assert set(PAGES) <= set(utilisees), f"Conseils jamais affichés : {set(PAGES) - set(utilisees)}"


def test_les_modules_et_dix_neuf_fenetres():
    # V4 : les outils (modules sans projet) ont leurs conseils, comme les autres modules (V4.1 : Comparer).
    modules = {"script", "voix", "transcription", "sous-titres", "reglages", "upscale", "images", "renommer", "comparer"}
    assert modules <= set(PAGES)
    # Dont 4 au lot 2 de la V2 (variantes, comparaison, briefs, exemples), 1 au lot 7 (préréglages),
    # 2 dans la V3 (fenêtres d'export du calque, lot 1, et de la vidéo, lot 2) et 1 dans la V3.1
    # (« Corriger les mots » des sous-titres importés, lot 6).
    assert len(set(PAGES) - modules) == 19
    assert all(re.fullmatch(r"[a-z-]+", cle) for cle in PAGES)


def test_regles_publicitaires_dans_les_conseils_du_script():
    from ugc_studio.ecriture.regles import REGLES

    conseils = {c for rubrique in PAGES["script"].rubriques for c in rubrique.conseils}
    assert {regle.francais for regle in REGLES} <= conseils
    assert any("étiquette « contenu généré par l'IA »" in c for c in conseils)
