"""Liste des prises du projet (§5.6) : écoute, note ★, renommage, export WAV / MP3, suppression."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ....audio import exporter_mp3
from ....chemins import dossier_documents
from ....fournisseurs.capacites import modele_connu
from ....projets import Prise, copier_fichier
from ....services import Services
from ... import taches
from ...composants.elements import bouton, libelle, vider_disposition
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...icones import icone
from ...ouvrir import ouvrir_dossier
from ...theme import Couleurs, Dimensions, Espacements

journal = logging.getLogger(__name__)
NOTE_MAX = 5


def minutes_secondes(secondes: float) -> str:
    secondes = max(0, round(secondes))
    return f"{secondes // 60}:{secondes % 60:02d}"


def bouton_icone(nom_icone: str, info: str, couleur: str = Couleurs.TEXTE_SECONDAIRE, rempli: bool = False):
    resultat = bouton("", variante="icone")
    resultat.setIcon(icone(nom_icone, couleur, rempli=rempli))
    resultat.setIconSize(QSize(Dimensions.ICONE, Dimensions.ICONE))
    resultat.setToolTip(info)
    return resultat


class LignePrise(QFrame):
    def __init__(self, liste: ListePrises, prise: Prise):
        super().__init__()
        self.setProperty("role", "ligne")
        self.prise = prise
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.M)

        en_lecture = liste.lecteur.en_lecture(liste.chemin(prise))
        self.bouton_lecture = bouton_icone(
            "pause" if en_lecture else "play",
            "Pause" if en_lecture else "Écouter",
            Couleurs.ACCENT_SURVOL,
            rempli=True,
        )
        self.bouton_lecture.clicked.connect(lambda: liste.lecteur.basculer(liste.chemin(prise)))
        disposition.addWidget(self.bouton_lecture)

        textes = QVBoxLayout()
        textes.setSpacing(Espacements.XS)
        ligne_nom = QHBoxLayout()
        ligne_nom.setSpacing(Espacements.S)
        ligne_nom.addWidget(libelle(prise.nom, "titre-bloc", retour_a_la_ligne=False))
        self.etoiles: list = []
        for rang in range(1, NOTE_MAX + 1):
            allumee = rang <= prise.note
            etoile = bouton("", variante="icone")
            etoile.setIcon(
                icone("star", Couleurs.AVERTISSEMENT if allumee else Couleurs.TEXTE_DESACTIVE, rempli=allumee, taille=Dimensions.ETOILE)
            )
            etoile.setIconSize(QSize(Dimensions.ETOILE, Dimensions.ETOILE))
            etoile.setToolTip(f"Noter {rang}/{NOTE_MAX}")
            # Cliquer sur l'étoile déjà sélectionnée retire la note.
            etoile.clicked.connect(lambda _c=False, r=rang: liste.noter(prise.identifiant, 0 if r == prise.note else r))
            self.etoiles.append(etoile)
            ligne_nom.addWidget(etoile)
        ligne_nom.addStretch(1)
        textes.addLayout(ligne_nom)

        details = [_date_lisible(prise.date), prise.voix]
        connu = modele_connu(prise.modele)
        details.append(connu.nom if connu else prise.modele)
        if prise.style:
            details.append(f"style « {prise.style} »")
        textes.addWidget(libelle("  ·  ".join(details), "legende"))
        disposition.addLayout(textes, 1)

        disposition.addWidget(libelle(minutes_secondes(prise.duree_s), "secondaire", retour_a_la_ligne=False))
        if prise.cout_eur is not None:
            disposition.addWidget(MontantLabel(prise.cout_eur))

        plus = bouton_icone("ellipsis", "Plus d'actions")
        menu = QMenu(plus)
        menu.addAction(icone("pencil", Couleurs.TEXTE_SECONDAIRE), "Renommer…").triggered.connect(
            lambda: liste.renommer(prise.identifiant)
        )
        menu.addAction(icone("download", Couleurs.TEXTE_SECONDAIRE), "Exporter en WAV…").triggered.connect(
            lambda: liste.exporter(prise.identifiant, "wav")
        )
        menu.addAction(icone("download", Couleurs.TEXTE_SECONDAIRE), "Exporter en MP3…").triggered.connect(
            lambda: liste.exporter(prise.identifiant, "mp3")
        )
        menu.addAction(icone("folder-open", Couleurs.TEXTE_SECONDAIRE), "Afficher dans le dossier").triggered.connect(
            lambda: ouvrir_dossier(liste.chemin(prise).parent)
        )
        menu.addSeparator()
        menu.addAction(icone("trash", Couleurs.ERREUR), "Supprimer…").triggered.connect(
            lambda: liste.supprimer(prise.identifiant)
        )
        plus.setMenu(menu)
        disposition.addWidget(plus)


def _date_lisible(texte_iso: str) -> str:
    try:
        return datetime.fromisoformat(texte_iso).strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        return texte_iso


class ListePrises(QWidget):
    def __init__(self, services: Services, lecteur: Lecteur):
        super().__init__()
        self._services = services
        self.lecteur = lecteur
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        self._lignes = QVBoxLayout()
        self._lignes.setSpacing(0)
        disposition.addLayout(self._lignes)

        # Barre de lecture (visible pendant l'écoute)
        self.barre = QWidget()
        barre = QHBoxLayout(self.barre)
        barre.setContentsMargins(0, Espacements.M, 0, 0)
        barre.setSpacing(Espacements.M)
        self.titre_lecture = libelle("", "secondaire", retour_a_la_ligne=False)
        barre.addWidget(self.titre_lecture)
        self.position = QSlider(Qt.Orientation.Horizontal)
        self.position.sliderMoved.connect(self.lecteur.aller_a)
        barre.addWidget(self.position, 1)
        self.temps = libelle("0:00 / 0:00", "legende", retour_a_la_ligne=False)
        barre.addWidget(self.temps)
        self.barre.hide()
        disposition.addWidget(self.barre)

        self.lecteur.etat_change.connect(lambda _chemin, _lecture: self.rafraichir())
        self.lecteur.position_change.connect(self._position)
        self.rafraichir()

    # --- Affichage ---------------------------------------------------------------------------

    def chemin(self, prise: Prise) -> Path:
        return self._services.projets.projet.chemin(prise.fichier)

    def rafraichir(self) -> None:
        vider_disposition(self._lignes)
        projet = self._services.projets.projet
        prises = list(reversed(projet.prises)) if projet else []
        if not prises:
            self._lignes.addWidget(
                libelle("Aucune prise pour l'instant : écris ton script puis clique sur « Générer la voix ».", "discret")
            )
        for prise in prises:
            self._lignes.addWidget(LignePrise(self, prise))
        en_cours = next((p for p in prises if str(self.chemin(p)) == self.lecteur.chemin), None)
        self.barre.setVisible(en_cours is not None)
        if en_cours is not None:
            self.titre_lecture.setText(en_cours.nom)

    def lignes(self) -> list[LignePrise]:
        return [
            self._lignes.itemAt(i).widget()
            for i in range(self._lignes.count())
            if isinstance(self._lignes.itemAt(i).widget(), LignePrise)
        ]

    def _position(self, position_ms: int, duree_ms: int) -> None:
        if not self.position.isSliderDown():
            self.position.setRange(0, max(duree_ms, 0))
            self.position.setValue(position_ms)
        self.temps.setText(f"{minutes_secondes(position_ms / 1000)} / {minutes_secondes(duree_ms / 1000)}")

    # --- Actions -----------------------------------------------------------------------------

    def noter(self, identifiant: str, note: int) -> None:
        self._services.projets.modifier_prise(identifiant, note=note)
        self.rafraichir()

    def renommer(self, identifiant: str) -> None:
        prise = self._services.projets.prise(identifiant)
        nom, ok = QInputDialog.getText(self, "Renommer la prise", "Nouveau nom :", text=prise.nom)
        if ok and nom.strip():
            self._services.projets.modifier_prise(identifiant, nom=" ".join(nom.split()))
            self.rafraichir()

    def exporter(self, identifiant: str, format_audio: str) -> None:
        projet = self._services.projets.projet
        prise = self._services.projets.prise(identifiant)
        proposition = dossier_documents() / f"{projet.nom} - {prise.nom}.{format_audio}"
        filtre = "Audio WAV (*.wav)" if format_audio == "wav" else "Audio MP3 (*.mp3)"
        choix, _ = QFileDialog.getSaveFileName(self, f"Exporter en {format_audio.upper()}", str(proposition), filtre)
        if not choix:
            return
        source, destination = self.chemin(prise), Path(choix)
        if format_audio == "wav":
            copier_fichier(source, destination)
            return

        def echec(erreur: Exception) -> None:
            QMessageBox.warning(self.window(), "Export MP3", f"L'export MP3 a échoué : {erreur}")

        taches.lancer(lambda: exporter_mp3(source, destination), lambda _r: None, echec)

    def supprimer(self, identifiant: str) -> None:
        prise = self._services.projets.prise(identifiant)
        boite = QMessageBox(self.window())
        boite.setIcon(QMessageBox.Icon.Warning)
        boite.setWindowTitle("Supprimer la prise")
        boite.setText(f"Supprimer « {prise.nom} » ?")
        boite.setInformativeText("Le fichier audio sera effacé du dossier du projet.")
        confirmer = boite.addButton("Supprimer", QMessageBox.ButtonRole.DestructiveRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.exec()
        if boite.clickedButton() is confirmer:
            if self.lecteur.chemin == str(self.chemin(prise)):
                self.lecteur.arreter()
            self._services.projets.supprimer_prise(identifiant)
            self.rafraichir()
