"""Fenêtre d'export (V3, §8.5) : une seule fenêtre par export, toujours obligatoire.

1. Réglages en haut (lot 1, calque transparent : images par seconde d'un projet sans vidéo,
   dossier, nom).
2. Dessous, le **résumé avant export**, mis à jour à chaque réglage changé : la source et l'export
   côte à côte ; toute valeur différente de la source est en mauve (comme les valeurs modifiées des
   variantes A/B), les avertissements en orange, ce qui empêche l'export en rouge.
3. « Exporter » lance l'export dans la même fenêtre : une barre d'avancement, le temps restant
   estimé, et « Arrêter » (rien n'est gardé d'un export arrêté). À la fin : la durée de l'export,
   le nom et le poids du fichier, « Ouvrir le dossier ».

Le choix du dossier (celui de la vidéo source, celui du projet, ou un autre) et la fréquence d'un
projet sans vidéo sont retenus pour le prochain export (préférences).
"""

from __future__ import annotations

import logging
import time
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...exports.cadence import FREQUENCE_MAX, FREQUENCE_MIN, FREQUENCE_SANS_VIDEO, frequence_exacte, texte_frequence
from ...exports.ffmpeg import analyser, programme_ffmpeg
from ...exports.plan import (
    DOSSIER_AUTRE,
    DOSSIER_PROJET,
    DOSSIER_SOURCE,
    EXTENSION_CALQUE,
    PlanCalque,
    Resume,
    Source,
    SousTitresAExporter,
    duree_d_export_lisible,
    nom_propose,
    nom_propre,
    place_libre,
    plan_du_calque,
    poids_lisible,
    resume_calque,
    source_du_projet,
    texte_des_sous_titres,
)
from ...projets import Projet
from ...services import Services
from .. import taches
from ..composants.barre_avancement import BarreAvancement
from ..composants.choix import ChoixEnBoutons
from ..composants.conseils import entete_de_fenetre
from ..composants.defilement import zone_defilante
from ..composants.elements import bouton, champ_decimal, info, libelle, libelle_abrege
from ..composants.tableau import Colonne, Tableau
from ..ouvrir import montrer_dans_l_explorateur
from ..theme import Couleurs, Dimensions, Espacements, Hauteurs, qcolor

journal = logging.getLogger(__name__)

PREF_DOSSIER = "export_dossier"  # « source », « projet » ou « autre »
PREF_DOSSIER_AUTRE = "export_dossier_autre"  # le dernier dossier choisi avec « Changer… »
PREF_FREQUENCE = "export_calque_frequence"  # projet sans vidéo : « apercu », « 30 », « 60 » ou « autre »
PREF_FREQUENCE_LIBRE = "export_calque_frequence_libre"

FREQUENCE_APERCU = "apercu"
FREQUENCE_LIBRE = "autre"
FREQUENCES_PROPOSEES = {"30": Fraction(30), "60": Fraction(60)}

COLONNES_RESUME = (
    Colonne("", texte=True),
    Colonne("Source", texte=True),
    Colonne("Export", texte=True, etiree=True),
)
RESTE_APRES_S = 1.0  # le temps restant s'affiche après une seconde (avant, l'estimation serait fausse)


def _changer_de_role(etiquette, role: str) -> None:
    etiquette.setProperty("role", role)
    etiquette.style().unpolish(etiquette)
    etiquette.style().polish(etiquette)


class DialogueExportCalque(QDialog):
    """Exporter le calque transparent (MOV, ProRes 4444) des sous-titres du projet."""

    def __init__(self, services: Services, projet: Projet, contenu: SousTitresAExporter, parent: QWidget | None = None):
        super().__init__(parent)
        self._services, self._projet, self._contenu = services, projet, contenu
        self._preferences = services.preferences
        self._ffmpeg = programme_ffmpeg()
        self.source: Source = source_du_projet(projet)
        self.analyse_finie = False
        self._frequence_apercu: Fraction | None = None  # vidéo d'aperçu d'un projet sans vidéo
        self._autre = Path(self._preferences.lire(PREF_DOSSIER_AUTRE, "") or projet.dossier)
        self._export = None  # ExportDuCalque en cours
        self._debut_export: float | None = None
        self.fichier: Path | None = None  # le calque écrit
        self._ouvert = True
        self.setWindowTitle("Exporter le calque transparent")
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)
        self.resize(Dimensions.DIALOGUE_EXPORT_LARGEUR, Dimensions.DIALOGUE_EXPORT_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre("Exporter le calque transparent", "export"))
        disposition.addWidget(
            info(
                "Les sous-titres seuls, sur un fond transparent : pose ce calque au-dessus de ton montage dans "
                "Premiere Pro, au même point de départ que ta vidéo ou ta voix.",
                "secondaire",
            )
        )
        zone, contenu_zone = zone_defilante()
        contenu_zone.setSpacing(Espacements.L)
        self.reglages = self._zone_reglages()
        contenu_zone.addWidget(self.reglages)
        contenu_zone.addWidget(libelle("Résumé avant export", "intitule"))
        self.etat_analyse = libelle("", "legende")
        self.etat_analyse.hide()
        contenu_zone.addWidget(self.etat_analyse)
        self.tableau = Tableau(COLONNES_RESUME)
        self.tableau.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tableau.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        contenu_zone.addWidget(self.tableau)
        self.messages = QVBoxLayout()
        self.messages.setSpacing(Espacements.XS)
        contenu_zone.addLayout(self.messages)
        contenu_zone.addStretch(1)
        disposition.addWidget(zone, 1)

        # Avancement (pendant l'export) et message de fin.
        self.zone_avancement = QWidget()
        avancement = QVBoxLayout(self.zone_avancement)
        avancement.setContentsMargins(0, 0, 0, 0)
        avancement.setSpacing(Espacements.S)
        self.etape = libelle("", "secondaire")
        avancement.addWidget(self.etape)
        self.barre = BarreAvancement()
        avancement.addWidget(self.barre)
        self.reste = libelle("", "legende")
        avancement.addWidget(self.reste)
        self.zone_avancement.hide()
        disposition.addWidget(self.zone_avancement)
        self.statut = libelle("", "secondaire")
        self.statut.hide()
        disposition.addWidget(self.statut)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_dossier = bouton("Ouvrir le dossier", nom_icone="folder-open", action=self.ouvrir_le_dossier)
        self.bouton_dossier.hide()
        boutons.addWidget(self.bouton_dossier)
        boutons.addStretch(1)
        self.bouton_annuler = bouton("Annuler", action=self.reject)
        boutons.addWidget(self.bouton_annuler)
        self.bouton_arreter = bouton("Arrêter", nom_icone="square", action=self.arreter)
        self.bouton_arreter.hide()
        boutons.addWidget(self.bouton_arreter)
        self.bouton_exporter = bouton("Exporter", variante="principal", nom_icone="download", action=self.exporter)
        boutons.addWidget(self.bouton_exporter)
        self.bouton_fermer = bouton("Fermer", variante="principal", action=self.accept)
        self.bouton_fermer.hide()
        boutons.addWidget(self.bouton_fermer)
        disposition.addLayout(boutons)

        self._actualiser()
        self._lancer_l_analyse()

    # --- Réglages -------------------------------------------------------------------------------

    def _zone_reglages(self) -> QWidget:
        zone = QWidget()
        grille = QGridLayout(zone)
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setHorizontalSpacing(Espacements.L)
        grille.setVerticalSpacing(Espacements.M)
        grille.setColumnStretch(1, 1)
        rang = 0

        grille.addWidget(libelle("Format", "legende", retour_a_la_ligne=False), rang, 0)
        grille.addWidget(libelle("MOV · ProRes 4444 avec transparence (format de montage d'Apple, lu par Premiere Pro)", "secondaire"), rang, 1)
        rang += 1

        grille.addWidget(libelle("Images par seconde", "legende", retour_a_la_ligne=False), rang, 0, Qt.AlignmentFlag.AlignTop)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.choix_frequence: ChoixEnBoutons | None = None  # projet sans vidéo (placé en tête de ligne)
        self.texte_frequence = libelle("", "secondaire")
        ligne.addWidget(self.texte_frequence, 1)
        self.frequence_libre = champ_decimal(FREQUENCE_MIN, FREQUENCE_MAX, 1.0, 3, " i/s", "Images par seconde du calque")
        self.frequence_libre.setValue(float(self._preferences.lire(PREF_FREQUENCE_LIBRE, 25.0) or 25.0))
        self.frequence_libre.valueChanged.connect(lambda _valeur: self._actualiser())
        self.frequence_libre.hide()
        ligne.addWidget(self.frequence_libre)
        ligne.addStretch(1)
        self._ligne_frequence = ligne
        grille.addLayout(ligne, rang, 1)
        rang += 1
        self._preparer_la_frequence()

        grille.addWidget(libelle("Dossier", "legende", retour_a_la_ligne=False), rang, 0, Qt.AlignmentFlag.AlignTop)
        colonne = QVBoxLayout()
        colonne.setSpacing(Espacements.S)
        choix = {}
        dossier_source = self.source.dossier
        if dossier_source is not None and dossier_source.is_dir():
            choix[DOSSIER_SOURCE] = "Celui de la vidéo" if (self.source.video or self.source.video_d_apercu) else "Celui de l'audio"
        choix[DOSSIER_PROJET] = "Celui du projet"
        choix[DOSSIER_AUTRE] = "Autre"
        self.choix_dossier = ChoixEnBoutons(choix, "Où ranger le fichier exporté")
        prefere = self._preferences.lire(PREF_DOSSIER, DOSSIER_SOURCE)
        self.choix_dossier.definir(prefere if prefere in choix else next(iter(choix)))
        self.choix_dossier.change.connect(self._dossier_choisi)
        ligne = QHBoxLayout()
        ligne.addWidget(self.choix_dossier)
        ligne.addStretch(1)
        colonne.addLayout(ligne)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.chemin_dossier = libelle_abrege("", "legende")
        ligne.addWidget(self.chemin_dossier, 1)
        self.bouton_changer = bouton("Changer…", variante="contour", nom_icone="folder-open", action=self.changer_de_dossier)
        ligne.addWidget(self.bouton_changer)
        colonne.addLayout(ligne)
        grille.addLayout(colonne, rang, 1)
        rang += 1

        grille.addWidget(libelle("Nom", "legende", retour_a_la_ligne=False), rang, 0)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.nom = QLineEdit(nom_propose(self.source, self._projet))
        self.nom.setPlaceholderText("Nom du fichier")
        self.nom.textChanged.connect(lambda _texte: self._actualiser())
        ligne.addWidget(self.nom, 1)
        ligne.addWidget(libelle(EXTENSION_CALQUE, "secondaire", retour_a_la_ligne=False))
        grille.addLayout(ligne, rang, 1)
        return zone

    def _preparer_la_frequence(self) -> None:
        """Avec une vidéo : sa fréquence exacte, sans choix (sinon le calque se décalerait peu à peu).
        Sans vidéo : 30 au départ, 60, une valeur libre, ou celle de la vidéo d'aperçu (une fois lue)."""
        ligne = self._ligne_frequence
        if self.choix_frequence is not None:
            ligne.removeWidget(self.choix_frequence)
            self.choix_frequence.deleteLater()
            self.choix_frequence = None
        if self.source.video:
            self.texte_frequence.show()
            self.frequence_libre.hide()
            return
        self.texte_frequence.hide()
        choix = {}
        if self._frequence_apercu is not None:
            choix[FREQUENCE_APERCU] = f"{texte_frequence(self._frequence_apercu)} (vidéo d'aperçu)"
        choix.update({cle: cle for cle in FREQUENCES_PROPOSEES})
        choix[FREQUENCE_LIBRE] = "Autre"
        self.choix_frequence = ChoixEnBoutons(choix, "Images par seconde du calque (celles de ta séquence Premiere Pro)")
        prefere = self._preferences.lire(PREF_FREQUENCE, FREQUENCE_APERCU)
        if prefere not in choix:
            prefere = FREQUENCE_APERCU if FREQUENCE_APERCU in choix else "30"
        self.choix_frequence.definir(prefere)
        self.choix_frequence.change.connect(lambda _valeur: self._actualiser())
        ligne.insertWidget(0, self.choix_frequence)

    def frequence_choisie(self) -> Fraction | None:
        """Projet sans vidéo : la fréquence choisie (None : celle de la vidéo, imposée)."""
        if self.source.video or self.choix_frequence is None:
            return None
        valeur = self.choix_frequence.valeur()
        self.frequence_libre.setVisible(valeur == FREQUENCE_LIBRE)
        if valeur == FREQUENCE_APERCU and self._frequence_apercu is not None:
            return self._frequence_apercu
        if valeur == FREQUENCE_LIBRE:
            return frequence_exacte(self.frequence_libre.value()) or FREQUENCE_SANS_VIDEO
        return FREQUENCES_PROPOSEES.get(valeur, FREQUENCE_SANS_VIDEO)

    def dossier(self) -> Path:
        choix = self.choix_dossier.valeur()
        if choix == DOSSIER_SOURCE and self.source.dossier is not None:
            return self.source.dossier
        if choix == DOSSIER_AUTRE:
            return self._autre
        return self._projet.dossier

    def _dossier_choisi(self, choix: str) -> None:
        if choix == DOSSIER_AUTRE and not self._preferences.lire(PREF_DOSSIER_AUTRE, ""):
            self.changer_de_dossier()
        self._actualiser()

    def _demander_un_dossier(self, depart: Path) -> Path | None:
        """Choix d'un dossier (remplacé dans les tests)."""
        choix = QFileDialog.getExistingDirectory(self, "Dossier de l'export", str(depart))
        return Path(choix) if choix else None

    def changer_de_dossier(self) -> None:
        choisi = self._demander_un_dossier(self._autre if self._autre.is_dir() else self._projet.dossier)
        if choisi is not None:
            self._autre = choisi
            self._preferences.ecrire(PREF_DOSSIER_AUTRE, str(choisi))
            self._preferences.enregistrer()
            self.choix_dossier.definir(DOSSIER_AUTRE)
        self._actualiser()

    # --- Analyse de la vidéo par FFmpeg ---------------------------------------------------------------

    def _lancer_l_analyse(self) -> None:
        """FFmpeg lit la vidéo (sans la décoder, une seconde ou deux) : moment exact de chaque image,
        vrais débits, nom exact des codecs. En attendant, « Exporter » attend."""
        video = self.source.chemin if self.source.video else self.source.video_d_apercu
        if video is None or not video.is_file() or self._ffmpeg is None:
            self.analyse_finie = True
            self._actualiser()
            return
        self.etat_analyse.setText("FFmpeg lit ta vidéo (moment exact de chaque image, débits)…")
        self.etat_analyse.show()
        ffmpeg = self._ffmpeg
        taches.lancer(lambda: analyser(video, ffmpeg), self._analyse_lue, lambda _erreur: self._analyse_lue(None))

    def _analyse_lue(self, analyse) -> None:
        if not self._ouvert:
            return
        self.analyse_finie = True
        self.etat_analyse.hide()
        if self.source.video:
            self.source = source_du_projet(self._projet, analyse)
        elif analyse is not None and analyse.images is not None:
            self._frequence_apercu = analyse.images.frequence
            self._preparer_la_frequence()
        self._actualiser()

    # --- Résumé ---------------------------------------------------------------------------------

    def plan(self) -> PlanCalque:
        nom = nom_propre(self.nom.text()) if self.nom.text().strip() else ""
        sortie = self.dossier() / f"{nom}{EXTENSION_CALQUE}"
        return plan_du_calque(self.source, self._contenu.largeur, self._contenu.hauteur, self.frequence_choisie(), sortie)

    def resume(self) -> Resume:
        plan = self.plan()
        sous_titres = texte_des_sous_titres(len(self._contenu.sous_titres), self._contenu.style)
        resume = resume_calque(self.source, plan, sous_titres, place_libre(plan.sortie.parent))
        if self._ffmpeg is None:
            resume.erreurs.append("FFmpeg est introuvable : l'export est impossible (il devrait être intégré à l'app).")
        if not self._contenu.sous_titres:
            resume.erreurs.append("Pas de sous-titres à exporter.")
        return resume

    def _actualiser(self) -> None:
        if self.source.video:
            self.texte_frequence.setText(
                f"{texte_frequence(self.source.frequence)} : celle de ta vidéo (le calque tombe juste, image par image)"
                if self.source.frequence is not None
                else "Celle de ta vidéo"
            )
        plan, resume = self.plan(), self.resume()
        self.chemin_dossier.setText(str(plan.sortie.parent))
        self.bouton_changer.setVisible(self.choix_dossier.valeur() == DOSSIER_AUTRE)
        self._remplir_le_tableau(resume)
        self._afficher_les_messages(resume)
        self.bouton_exporter.setEnabled(resume.possible and self.analyse_finie and self._export is None)

    def _remplir_le_tableau(self, resume: Resume) -> None:
        tableau = self.tableau
        tableau.setRowCount(len(resume.lignes))
        mauve = QBrush(qcolor(Couleurs.ACCENT_SURVOL))
        for rang, ligne in enumerate(resume.lignes):
            for colonne, texte in enumerate((ligne.titre, ligne.source, ligne.export)):
                element = QTableWidgetItem(texte)
                if colonne == 0:
                    element.setForeground(QBrush(qcolor(Couleurs.TEXTE_SECONDAIRE)))
                if colonne == 2 and ligne.differente:
                    element.setForeground(mauve)
                    element.setToolTip("Différent de la source")
                tableau.setItem(rang, colonne, element)
        tableau.contenu_change()
        entete = tableau.horizontalHeader().sizeHint().height()
        tableau.setFixedHeight(entete + len(resume.lignes) * Hauteurs.CONTROLE + 2 * Dimensions.BORDURE)

    def _afficher_les_messages(self, resume: Resume) -> None:
        while self.messages.count():
            element = self.messages.takeAt(0).widget()
            if element is not None:
                element.deleteLater()
        for texte, role in [*((t, "erreur") for t in resume.erreurs), *((t, "avertissement") for t in resume.avertissements)]:
            message = libelle(texte, role)
            self.messages.addWidget(message)
            message.show()  # tout de suite (sinon Qt ne l'affiche qu'au prochain passage de la boucle)

    def messages_affiches(self) -> list[str]:
        """Avertissements et erreurs affichés sous le résumé (pour les tests et l'autotest)."""
        textes = []
        for rang in range(self.messages.count()):
            element = self.messages.itemAt(rang).widget()
            if element is not None and not element.isHidden():
                textes.append(element.text())
        return textes

    # --- Export ---------------------------------------------------------------------------------

    def exporter(self) -> None:
        from ...exports.calque import ExportDuCalque, ImagesDuCalque

        resume = self.resume()
        if not resume.possible or self._export is not None or self._ffmpeg is None:
            return
        plan = self.plan()
        self._preferences.ecrire(PREF_DOSSIER, self.choix_dossier.valeur())
        if self.choix_frequence is not None:
            self._preferences.ecrire(PREF_FREQUENCE, self.choix_frequence.valeur())
            self._preferences.ecrire(PREF_FREQUENCE_LIBRE, self.frequence_libre.value())
        self._preferences.enregistrer()
        contenu = self._contenu
        images = ImagesDuCalque(contenu.reglages, contenu.largeur, contenu.hauteur, contenu.sous_titres, contenu.mots)
        self._export = ExportDuCalque(plan, images, self._ffmpeg, self)
        self._export.avance.connect(self._avance)
        self._export.termine.connect(self._termine)
        self._export.echec.connect(self._echec)
        self._export.arrete.connect(self._arrete)
        self._debut_export = time.monotonic()
        self._pendant_l_export(True)
        self.etape.setText(f"Images du calque : 0 sur {plan.nombre_images}")
        self.barre.definir(0)
        self.reste.setText("")
        self._export.demarrer()

    def _pendant_l_export(self, en_cours: bool) -> None:
        self.reglages.setEnabled(not en_cours)
        self.zone_avancement.setVisible(en_cours)
        self.bouton_annuler.setVisible(not en_cours)
        self.bouton_exporter.setVisible(not en_cours)
        self.bouton_arreter.setVisible(en_cours)
        if en_cours:
            self.statut.hide()
            self.bouton_dossier.hide()
            self.bouton_fermer.hide()

    def _avance(self, fait: int, total: int) -> None:
        self.barre.definir(fait / total if total else 1.0)
        if fait >= total:
            self.etape.setText("Finalisation du fichier…")
            self.reste.setText("")
            return
        self.etape.setText(f"Images du calque : {fait} sur {total}")
        ecoule = time.monotonic() - (self._debut_export or time.monotonic())
        if fait > 0 and ecoule >= RESTE_APRES_S:
            self.reste.setText(f"Environ {duree_d_export_lisible(ecoule / fait * (total - fait))} restantes")

    def _termine(self, fichier: Path) -> None:
        duree = self._export.duree_s if self._export is not None else 0.0
        self._export = None
        self.fichier = fichier
        self._pendant_l_export(False)
        self.bouton_annuler.hide()
        self.bouton_exporter.hide()
        self.bouton_fermer.show()
        self.bouton_dossier.show()
        poids = poids_lisible(fichier.stat().st_size) if fichier.is_file() else ""
        self._statut(f"Calque enregistré en {duree_d_export_lisible(duree or 0)} : {fichier.name} ({poids}).", "succes")
        self._actualiser()

    def _echec(self, message: str) -> None:
        self._export = None
        self._pendant_l_export(False)
        self._statut(message, "erreur")
        self._actualiser()

    def _arrete(self) -> None:
        self._export = None
        self._pendant_l_export(False)
        self._statut("Export arrêté : rien n'a été gardé.", "secondaire")
        self._actualiser()

    def _statut(self, message: str, role: str) -> None:
        self.statut.setText(message)
        _changer_de_role(self.statut, role)
        self.statut.show()

    def arreter(self) -> None:
        if self._export is not None:
            self._export.arreter()

    def en_cours(self) -> bool:
        return self._export is not None

    def ouvrir_le_dossier(self) -> None:
        if self.fichier is not None:
            montrer_dans_l_explorateur(self.fichier)

    # --- Fermeture ------------------------------------------------------------------------------

    def done(self, resultat: int) -> None:
        """Fermer la fenêtre pendant un export l'arrête : rien d'inachevé ne reste."""
        self.arreter()
        self._ouvert = False
        super().done(resultat)
