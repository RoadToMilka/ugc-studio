"""Sous-titres du projet ouvert (V1.1) : calculés au même endroit pour la page Sous-titres et pour
le module Transcription (case « Masquer les hésitations »), avec la question posée avant un
réglage qui défait un sous-titre réorganisé à la main.

Pourquoi un seul endroit ? Tous les réglages qui changent les sous-titres (découpage, texte
affiché, écran, hésitations) passent par confirmer_reglage() : la vérification refait le calcul du
découpage avec le nouveau réglage (une fraction de seconde pour une pub), et aucun ajustement fait
à la main n'est défait sans ton choix.

V2, lot 3 : la largeur des lignes est mesurée par le moteur de dessin (rendu/moteur.py), le même
qui dessine l'aperçu ; le format est celui de la vidéo du projet, ou de la vidéo choisie seulement
pour l'aperçu, sinon celui choisi.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtWidgets import QMessageBox, QWidget

from ..projets import Projet
from ..rendu.moteur import Moteur
from ..services import Services
from ..sous_titres import (
    Ajustement,
    Decoupage,
    Ecran,
    Mesure,
    ReglagesSousTitres,
    calculer_sous_titres,
    ecran,
    resolution,
    texte_reglage_qui_defait,
)
from ..stt import hesitations, langue_de
from ..transcription import Transcription, resolution_video


@dataclass
class Calcul:
    """Sous-titres calculés, avec l'écran et la mesure du texte qui ont servi (pour vérifier une
    action faite à la main avec exactement les mêmes règles), et le moteur qui les dessine."""

    decoupage: Decoupage
    reglages: ReglagesSousTitres
    ecran: Ecran
    mesure: Mesure
    langue: str
    moteur: Moteur | None = None


def video_du_projet(projet: Projet) -> tuple[int, int] | None:
    """Résolution de la vidéo transcrite dans le projet (None : pas de vidéo, ex. une prise de voix)."""
    transcription = projet.transcription
    if transcription is None or transcription.prise:
        return None
    return resolution_video(transcription.infos)


def resolution_imposee(projet: Projet, reglages: ReglagesSousTitres | None = None) -> tuple[int, int] | None:
    """Résolution qu'impose une vidéo (§7.1) : celle du projet, sinon celle choisie seulement pour
    l'aperçu. None : le format choisi s'applique."""
    reglages = reglages if reglages is not None else projet.sous_titres
    return video_du_projet(projet) or reglages.apercu.resolution


def ajustements(transcription: Transcription | None) -> list[Ajustement]:
    """Sous-titres réorganisés à la main, tels qu'enregistrés dans le projet."""
    if transcription is None:
        return []
    return [Ajustement(debut, fin) for debut, fin in transcription.ajustements_sous_titres]


def ranger_ajustements(transcription: Transcription, liste: Iterable[Ajustement]) -> None:
    """Range les ajustements dans la transcription (le projet reste à enregistrer)."""
    tries = sorted(set(liste), key=lambda a: (a.debut, a.fin))
    transcription.ajustements_sous_titres = [[a.debut, a.fin] for a in tries]


def calculer(
    services: Services,
    projet: Projet,
    reglages: ReglagesSousTitres | None = None,
    masquer: bool | None = None,
) -> Calcul:
    """Sous-titres du projet, avec ses réglages (ou ceux donnés, pour essayer un nouveau réglage)."""
    transcription = projet.transcription
    reglages = reglages if reglages is not None else projet.sous_titres
    if masquer is None:
        masquer = transcription.masquer_hesitations if transcription is not None else True
    source = resolution_imposee(projet, reglages)
    ecran_video = ecran(reglages, source)
    moteur = Moteur(reglages, *resolution(reglages, source))
    mesure = moteur.mesure
    langue = langue_de(transcription, projet)
    mots = transcription.mots if transcription is not None and transcription.horodatee else []
    decoupage = calculer_sous_titres(
        mots,
        reglages,
        langue,
        ecran_video,
        mesure,
        hesitations(services, transcription),
        masquer,
        transcription.duree_s if transcription is not None and transcription.duree_s else None,
        ajustements(transcription),
    )
    return Calcul(decoupage, reglages, ecran_video, mesure, langue, moteur)


def ajustements_defaits_par(
    services: Services,
    projet: Projet,
    reglages: ReglagesSousTitres | None = None,
    masquer: bool | None = None,
) -> list[tuple[int, str, Ajustement, tuple]]:
    """Ajustements faits à la main que ce nouveau réglage défait : (numéro du sous-titre
    aujourd'hui, son texte aujourd'hui, ajustement, raisons)."""
    transcription = projet.transcription
    if transcription is None or not transcription.ajustements_sous_titres:
        return []
    actuel = calculer(services, projet).decoupage
    nouveau = calculer(services, projet, reglages, masquer).decoupage
    deja_defaits = {defait.ajustement for defait in actuel.defaits}  # mots corrigés entre-temps
    aujourd_hui = {
        s.ajustement: (numero, s.texte) for numero, s in enumerate(actuel.sous_titres, 1) if s.ajustement is not None
    }
    return [
        (*aujourd_hui[defait.ajustement], defait.ajustement, defait.refus)
        for defait in nouveau.defaits
        if defait.ajustement not in deja_defaits and defait.ajustement in aujourd_hui
    ]


def demander(parent: QWidget | None, texte: str, plusieurs: bool) -> bool:
    """« Garder le réglage actuel » (False) ou « Appliquer et défaire cet ajustement » (True)."""
    boite = QMessageBox(parent)
    boite.setIcon(QMessageBox.Icon.Question)
    boite.setWindowTitle("Changer ce réglage ?")
    boite.setText(texte)
    if plusieurs:
        boite.setInformativeText(
            "« Garder le réglage actuel » : rien ne change ; tu peux modifier ces sous-titres, puis changer "
            "le réglage. « Appliquer et défaire ces ajustements » : le réglage change, et ces sous-titres "
            "reviennent au découpage automatique."
        )
    else:
        boite.setInformativeText(
            "« Garder le réglage actuel » : rien ne change ; tu peux modifier ce sous-titre, puis changer "
            "le réglage. « Appliquer et défaire cet ajustement » : le réglage change, et ce sous-titre "
            "revient au découpage automatique."
        )
    garder = boite.addButton("Garder le réglage actuel", QMessageBox.ButtonRole.RejectRole)
    appliquer = boite.addButton(
        "Appliquer et défaire ces ajustements" if plusieurs else "Appliquer et défaire cet ajustement",
        QMessageBox.ButtonRole.AcceptRole,
    )
    boite.setDefaultButton(garder)
    boite.setEscapeButton(garder)
    boite.exec()
    return boite.clickedButton() is appliquer


def confirmer_reglage(
    parent: QWidget | None,
    services: Services,
    projet: Projet,
    reglages: ReglagesSousTitres | None = None,
    masquer: bool | None = None,
) -> bool:
    """Avant d'appliquer un réglage des sous-titres : s'il défait des sous-titres réorganisés à la
    main, la question est posée, en les nommant. True : appliquer (ces ajustements sont alors
    retirés du projet, que l'appelant enregistre avec le réglage) ; False : garder le réglage actuel."""
    concernes = ajustements_defaits_par(services, projet, reglages, masquer)
    if not concernes:
        return True
    texte = texte_reglage_qui_defait([(numero, texte, refus) for numero, texte, _a, refus in concernes])
    if not demander(parent, texte, len(concernes) > 1):
        return False
    retires = {ajustement for _n, _t, ajustement, _r in concernes}
    transcription = projet.transcription
    ranger_ajustements(transcription, [a for a in ajustements(transcription) if a not in retires])
    return True
