"""Actions sur les projets, utilisées depuis le bandeau du haut et depuis la page Voix."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QWidget

from ..chemins import dossier_projets_defaut
from ..projets import ErreurProjet
from ..services import Services
from .dialogues.projet import DialogueNouveauProjet
from .icones import icone
from .ouvrir import ouvrir_dossier
from .theme import Couleurs

NB_RECENTS_MENU = 5


def nouveau_projet(parent: QWidget, services: Services) -> None:
    dialogue = DialogueNouveauProjet(services.projets, parent.window())
    dialogue.open()


def ouvrir_projet(parent: QWidget, services: Services, dossier: Path | None = None) -> None:
    if dossier is None:
        depart = dossier_projets_defaut()
        depart.mkdir(parents=True, exist_ok=True)
        choix = QFileDialog.getExistingDirectory(parent.window(), "Ouvrir un projet (choisis son dossier)", str(depart))
        if not choix:
            return
        dossier = Path(choix)
    try:
        services.projets.ouvrir(dossier)
    except ErreurProjet as erreur:
        QMessageBox.warning(parent.window(), "Ouvrir un projet", str(erreur))


def remplir_menu_projet(menu: QMenu, parent: QWidget, services: Services) -> None:
    """(Re)construit le menu « Projet » : nouveau, ouvrir, récents, dossier du projet."""
    menu.clear()
    menu.addAction(icone("folder-plus", Couleurs.TEXTE_SECONDAIRE), "Nouveau projet…").triggered.connect(
        lambda: nouveau_projet(parent, services)
    )
    menu.addAction(icone("folder-open", Couleurs.TEXTE_SECONDAIRE), "Ouvrir un projet…").triggered.connect(
        lambda: ouvrir_projet(parent, services)
    )
    projet = services.projets.projet
    recents = [(nom, dossier) for nom, dossier in services.projets.recents() if projet is None or dossier != projet.dossier]
    if recents:
        menu.addSeparator()
        titre = menu.addAction("Projets récents")
        titre.setEnabled(False)
        for nom, dossier in recents[:NB_RECENTS_MENU]:
            menu.addAction(nom).triggered.connect(lambda _c=False, d=dossier: ouvrir_projet(parent, services, d))
    if projet is not None:
        menu.addSeparator()
        menu.addAction(icone("folder-open", Couleurs.TEXTE_SECONDAIRE), "Ouvrir le dossier du projet").triggered.connect(
            lambda: ouvrir_dossier(projet.dossier)
        )
