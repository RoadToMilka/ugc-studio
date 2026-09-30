"""Listes « modèle de voix » et « voix », partagées par l'atelier et la fenêtre des variantes."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from ...fournisseurs.capacites import MODELES_CONNUS, Capacite, modeles_pour
from ...fournisseurs.google_voix import VOIX_GOOGLE
from ...services import Services
from ..connexion_ia import FOURNISSEUR

MODELE_VOIX_PAR_DEFAUT = "gemini-3.8-flash-tts"


def choisir(liste: QComboBox, valeur: str) -> None:
    """Sélectionne le choix dont la donnée vaut `valeur` (s'il existe)."""
    index = liste.findData(valeur)
    if index >= 0:
        liste.setCurrentIndex(index)


def remplir_modeles_voix(liste: QComboBox, services: Services, actuel: str | None) -> bool:
    """Modèles de voix accessibles avec les clés testées (croisement avec les capacités, §3.4).

    Sans clé testée : les modèles principaux du catalogue, et la fonction renvoie False (l'atelier
    invite alors à tester une clé)."""
    disponibles = services.connexions.modeles_disponibles(FOURNISSEUR)
    compatibles = [c for c in modeles_pour({Capacite.TTS}, disponibles) if c.compatible]
    liste.blockSignals(True)
    liste.clear()
    if compatibles:
        for choix in compatibles:
            liste.addItem(choix.nom, choix.identifiant)
    else:
        for modele in MODELES_CONNUS:
            if Capacite.TTS in modele.capacites and modele.principal:
                liste.addItem(modele.nom, modele.identifiant)
    choisir(liste, actuel or MODELE_VOIX_PAR_DEFAUT)
    liste.blockSignals(False)
    return bool(compatibles)


def selectionner_voix(liste: QComboBox, services: Services, identifiant: str) -> None:
    """Choisit une voix dans la liste, en l'ajoutant en tête si elle n'y est pas encore."""
    if liste.findData(identifiant) < 0:
        liste.insertItem(0, services.voix.libelle(identifiant), identifiant)
    liste.setCurrentIndex(liste.findData(identifiant))


def remplir_voix(liste: QComboBox, services: Services, actuelle: str) -> None:
    """Tes favoris ★, puis tes voix créées, puis les 30 voix de base (sans doublon)."""
    gestion = services.voix
    favoris = gestion.favoris()
    creees = [v.identifiant for v in gestion.voix_creees() if v.identifiant not in favoris]
    base = [v.nom for v in VOIX_GOOGLE if v.nom not in favoris]
    liste.blockSignals(True)
    liste.clear()
    for groupe, prefixe in ((favoris, "★ "), (creees, ""), (base, "")):
        if not groupe:
            continue
        if liste.count():
            liste.insertSeparator(liste.count())
        for identifiant in groupe:
            liste.addItem(prefixe + gestion.libelle(identifiant), identifiant)
    selectionner_voix(liste, services, actuelle)
    liste.blockSignals(False)
