"""Bilan de l'autotest en affichage agrandi, 125 % et 150 % (V4, outils/affichage_agrandi.py) : les
textes coupés font échouer la fabrication, les autres vérifications non réussies sont signalées."""

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))

from affichage_agrandi import debordements, principal  # noqa: E402


def _rapport(dossier: Path, verifications: dict, **autres) -> str:
    dossier.mkdir()
    (dossier / "autotest.json").write_text(json.dumps({"verifications": verifications, **autres}), encoding="utf-8")
    return str(dossier)


def test_debordements_releves_a_toute_profondeur():
    rapport = {
        "debordements": ["page images : texte coupé « Glisse un dossier »"],
        "calque_debordements": [],
        "studio_disposition": {"debordements": ["page Sous-titres en grande fenêtre : bouton « Exporter »"]},
        "fenetres": [{"video_hdr_debordements": ["fenêtre d'export : liste abrégée"]}],
        "verifications": {"sans_debordement": False},
    }
    assert debordements(rapport) == [
        "page images : texte coupé « Glisse un dossier »",
        "page Sous-titres en grande fenêtre : bouton « Exporter »",
        "fenêtre d'export : liste abrégée",
    ]


def test_texte_coupe_fait_echouer(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    a_125 = _rapport(tmp_path / "captures-125", {"sans_debordement": True})
    a_150 = _rapport(tmp_path / "captures-150", {"sans_debordement": False}, debordements=["page images : texte coupé"])
    assert principal([a_125, a_150]) == 1
    sortie = capsys.readouterr().out
    assert "::error title=Textes coupés ou débordements (captures-150)::page images : texte coupé" in sortie


def test_autres_verifications_seulement_signalees(tmp_path, monkeypatch, capsys):
    resume = tmp_path / "resume.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resume))
    dossier = _rapport(tmp_path / "captures-150", {"sans_debordement": True, "disposition_studio": False})
    assert principal([dossier]) == 0
    assert "::warning title=Affichage agrandi (captures-150)::" in capsys.readouterr().out
    assert "Vérifications non réussies : disposition_studio" in resume.read_text(encoding="utf-8")


def test_rapport_absent_fait_echouer(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert principal([str(tmp_path / "captures-125")]) == 1
