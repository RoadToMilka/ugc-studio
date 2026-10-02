"""Atelier de transcription (§6) : importer une vidéo ou un audio, le transcrire mot par mot,
puis corriger la transcription en l'écoutant.

1. Source : glisser-déposer ou « Choisir un fichier… ». La piste son est extraite (WAV 16 kHz
   mono, dans le dossier « sources » du projet) et les informations de la source sont gardées.
2. Options : modèle, langue (détection automatique ou langue forcée), séparation des voix,
   texte seul (mode « smart », sans les temps), dictionnaire de remplacements, hésitations.
3. Transcription : texte mot par mot synchronisé avec la lecture ; clic sur un mot pour le
   choisir, le corriger sans perdre son timing, le fusionner, le couper, le supprimer ou ajuster
   son début et sa fin.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from ....audio import duree_wav
from ....chemins import dossier_documents
from ....fournisseurs.capacites import MODELES_CONNUS, Capacite, modele_connu, modeles_pour
from ....fournisseurs.stt import MODE_SMART, MODE_VERBATIM
from ....modeles_charges import TRANSCRIPTION
from ....prix import lire_decimal
from ....projets import FICHIER_AUDIO, LANGUES, Projet
from ....services import Services
from ....stt import (
    MODELE_PAR_DEFAUT,
    PREFERENCE_HESITATIONS,
    Options,
    estimer_cout,
    hesitations,
    langue_de,
    terminer_transcription,
    transcrire_source,
)
from ....transcription import (
    Transcription,
    ajuster,
    appliquer_remplacements,
    corriger,
    couper,
    fusionner,
    fusionner_remplacements,
    index_au_temps,
    resolution_video,
    supprimer,
)
from ... import taches
from ...composants.choix_voix import choisir, propose
from ...composants.editeur_transcription import EditeurTranscription, nom_de_personne
from ...composants.elements import (
    bloc,
    bouton,
    case_a_cocher,
    champs_en_colonnes,
    glissiere,
    info,
    libelle,
    liste_deroulante,
    minutes_secondes,
)
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues.remplacements import DialogueRemplacements
from ...extraction import EXTENSIONS_ACCEPTEES, FILTRE_FICHIERS, ExtracteurAudio, LecteurInfos
from ...icones import icone
from ...sous_titres_du_projet import confirmer_reglage
from ...theme import Couleurs, Dimensions, Espacements
from ..base import Page

journal = logging.getLogger(__name__)

AUTO = ""  # langue : détection automatique
MEME_MOMENT_S = 1e-3  # deux temps à moins d'une milliseconde : le même moment


def fichiers_acceptes(urls) -> list[Path]:
    """Fichiers locaux d'un glisser-déposer que l'app sait importer."""
    chemins = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
    return [c for c in chemins if c.suffix.lower() in EXTENSIONS_ACCEPTEES]


def description_source(transcription: Transcription) -> str:
    """« pub.mp4 · 0:42 · 1080 × 1920 · 30 images/s · H264 », ou pour une prise TTS :
    « Prise 3 · 0:12 · voix générée, alignée sur son script »."""
    if transcription.prise:
        morceaux = [transcription.source or "Prise"]
    else:
        morceaux = [Path(transcription.source).name or "source"]
    if transcription.duree_s:
        morceaux.append(minutes_secondes(transcription.duree_s))
    if transcription.prise:
        morceaux.append("voix générée, alignée sur son script")
    infos = transcription.infos or {}
    resolution = resolution_video(infos)
    if resolution:
        morceaux.append(f"{resolution[0]} × {resolution[1]}")
    if infos.get("images_par_seconde"):
        morceaux.append(f"{float(infos['images_par_seconde']):g} images/s")
    if infos.get("codec_video"):
        morceaux.append(str(infos["codec_video"]))
    if infos.get("hdr"):
        morceaux.append("HDR")
    return "  ·  ".join(morceaux)


class ZoneDepot(QFrame):
    """Cadre en pointillés : « Glisse une vidéo ou un audio ici » (le dépôt marche sur toute la page)."""

    def __init__(self, choisir_fichier, parent=None):
        super().__init__(parent)
        self.setProperty("role", "depot")
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.S)
        disposition.addWidget(libelle("Glisse une vidéo ou un audio ici", "intitule"), 0, Qt.AlignmentFlag.AlignHCenter)
        disposition.addWidget(
            info("Vidéo (MP4, MOV, MKV…) ou audio (WAV, MP3, M4A…) : la piste son est extraite automatiquement.", "legende"),
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        ligne = QHBoxLayout()
        ligne.addStretch(1)
        ligne.addWidget(bouton("Choisir un fichier…", nom_icone="folder-open", action=choisir_fichier))
        ligne.addStretch(1)
        disposition.addLayout(ligne)

    def survol(self, actif: bool) -> None:
        self.setProperty("survol", actif)
        self.style().unpolish(self)
        self.style().polish(self)


class AtelierTranscription(Page):
    def __init__(self, services: Services):
        super().__init__(
            "Transcription",
            "Le texte d'une vidéo ou d'un audio, mot par mot, pour créer les sous-titres.",
            conseils="transcription",
        )
        self._services = services
        self._projet: Projet | None = None
        self._source_en_cours: Path | None = None
        self._infos_en_attente: dict = {}
        self._occupe = False
        self.lecteur = Lecteur(self)
        self.extracteur = ExtracteurAudio(self)
        self.extracteur.progression.connect(self._progression_extraction)
        self.extracteur.termine.connect(self._extraction_terminee)
        self.extracteur.echec.connect(self._extraction_echouee)
        self.infos = LecteurInfos(self)
        self.infos.pretes.connect(self._infos_pretes)
        self.setAcceptDrops(True)

        # --- Source ---
        cadre, d = bloc("Source")
        self.zone_depot = ZoneDepot(self.choisir_fichier)
        d.addWidget(self.zone_depot)
        self.ligne_source = QHBoxLayout()
        self.ligne_source.setSpacing(Espacements.S)
        self.texte_source = libelle("", "secondaire")
        self.ligne_source.addWidget(self.texte_source, 1)
        self.bouton_changer = bouton("Changer de source…", variante="contour", nom_icone="folder-open", action=self.choisir_fichier)
        self.ligne_source.addWidget(self.bouton_changer)
        d.addLayout(self.ligne_source)
        self.contenu.addWidget(cadre)

        # --- Options ---
        cadre, d = bloc("Options")
        self.modele = liste_deroulante("Modèle de transcription")
        self.modele.currentIndexChanged.connect(lambda _index: self._modele_change())
        self.langue = liste_deroulante("Langue parlée dans la source")
        self.langue.addItem("Détection automatique", AUTO)
        for code, nom in LANGUES.items():
            self.langue.addItem(nom, code)
        # Sous leur nom, côte à côte (V3.1), comme les champs du brief du module Script.
        d.addLayout(champs_en_colonnes((("Modèle", self.modele), ("Langue", self.langue))))
        self.zone_separation, self.separation = case_a_cocher(
            "Séparer les voix", "Chaque mot reçoit la personne qui parle (fiable jusqu'à 2 personnes)."
        )
        d.addWidget(self.zone_separation)
        zone, self.texte_seul = case_a_cocher(
            "Texte seul, nettoyé (mode « smart »)", "Sans le moment de chaque mot : pas de sous-titres possibles."
        )
        self.texte_seul.toggled.connect(self._texte_seul_change)
        d.addWidget(zone)
        outils = QHBoxLayout()
        outils.setSpacing(Espacements.S)
        remplacements = bouton("Remplacements", variante="contour", nom_icone="book-a", action=self.ouvrir_remplacements)
        remplacements.setToolTip("Dictionnaire de remplacements : corrige automatiquement les noms de marque…")
        outils.addWidget(remplacements)
        hesitations = bouton("Hésitations", variante="contour", nom_icone="pencil", action=self.modifier_hesitations)
        hesitations.setToolTip("Liste des hésitations (« euh », « hum »…) de la langue de la transcription")
        outils.addWidget(hesitations)
        outils.addStretch(1)
        d.addLayout(outils)
        zone, self.masquer = case_a_cocher(
            "Masquer les hésitations dans les sous-titres",
            "« euh », « hum »… disparaissent des sous-titres ; l'audio et les autres mots ne changent pas.",
        )
        self.masquer.toggled.connect(self._masquer_change)
        d.addWidget(zone)
        self.contenu.addWidget(cadre)

        # --- Transcrire ---
        generation = QVBoxLayout()
        generation.setSpacing(Espacements.S)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.M)
        self.bouton_transcrire = bouton("Transcrire", variante="principal", nom_icone="audio-lines", action=self.transcrire)
        ligne.addWidget(self.bouton_transcrire)
        estimation = QHBoxLayout()
        estimation.setSpacing(Espacements.XS)
        self.estimation = libelle("", "legende", retour_a_la_ligne=False)
        estimation.addWidget(self.estimation)
        self.cout_estime = MontantLabel(0)
        self.cout_estime.setProperty("role", "legende")
        estimation.addWidget(self.cout_estime)
        ligne.addLayout(estimation)
        ligne.addStretch(1)
        generation.addLayout(ligne)
        self.statut = libelle("", "secondaire")
        generation.addWidget(self.statut)
        self.contenu.addLayout(generation)

        # --- Transcription ---
        self.cadre_transcription, d = bloc("Transcription")
        self.resume = libelle("", "legende")
        d.addWidget(self.resume)
        lecture = QHBoxLayout()
        lecture.setSpacing(Espacements.M)
        self.bouton_lecture = bouton("", variante="icone", action=self.basculer_lecture)
        lecture.addWidget(self.bouton_lecture)
        self.position = glissiere()
        self.position.sliderMoved.connect(self.lecteur.aller_a)
        lecture.addWidget(self.position, 1)
        self.temps = libelle("0:00 / 0:00", "legende", retour_a_la_ligne=False)
        lecture.addWidget(self.temps)
        d.addLayout(lecture)
        self.editeur = EditeurTranscription()
        self.editeur.mot_clique.connect(self.choisir_mot)
        d.addWidget(self.editeur)
        self.texte_smart = QPlainTextEdit()
        self.texte_smart.setReadOnly(True)
        self.texte_smart.setMinimumHeight(Dimensions.EDITEUR_HAUTEUR_MIN)
        d.addWidget(self.texte_smart)
        self.panneau_mot = self._panneau_mot()
        d.addWidget(self.panneau_mot)
        copier = QHBoxLayout()
        copier.addWidget(bouton("Copier le texte", variante="contour", nom_icone="copy", action=self.copier_texte))
        copier.addStretch(1)
        d.addLayout(copier)
        self.contenu.addWidget(self.cadre_transcription)

        self.lecteur.etat_change.connect(lambda _chemin, _lecture: self._etat_lecture())
        self.lecteur.position_change.connect(self._position_lue)
        services.projets.abonner(self._projet_change)
        services.connexions.abonner(self._remplir_modeles)
        services.prix.abonner(self._mettre_a_jour_estimation)
        self._remplir_modeles()
        self._projet_change(services.projets.projet)

    def _panneau_mot(self) -> QFrame:
        """« Mot choisi » : corriger son texte, ses temps ; fusionner, couper, supprimer."""
        panneau = QFrame()
        disposition = QVBoxLayout(panneau)
        disposition.setContentsMargins(0, Espacements.S, 0, 0)
        disposition.setSpacing(Espacements.S)
        self.titre_mot = info("Clique sur un mot pour le corriger.")
        disposition.addWidget(self.titre_mot)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.champ_mot = QLineEdit()
        self.champ_mot.setPlaceholderText("Texte du mot")
        self.champ_mot.returnPressed.connect(self.appliquer_mot)
        ligne.addWidget(self.champ_mot, 1)
        ligne.addWidget(libelle("Début", "legende", retour_a_la_ligne=False))
        self.champ_debut = QLineEdit()
        self.champ_debut.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
        self.champ_debut.setToolTip("Début du mot, en secondes (ex. 1.25)")
        self.champ_debut.returnPressed.connect(self.appliquer_mot)
        ligne.addWidget(self.champ_debut)
        ligne.addWidget(libelle("Fin", "legende", retour_a_la_ligne=False))
        self.champ_fin = QLineEdit()
        self.champ_fin.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
        self.champ_fin.setToolTip("Fin du mot, en secondes")
        self.champ_fin.returnPressed.connect(self.appliquer_mot)
        ligne.addWidget(self.champ_fin)
        self.bouton_appliquer = bouton("Appliquer", nom_icone="check", action=self.appliquer_mot)
        ligne.addWidget(self.bouton_appliquer)
        disposition.addLayout(ligne)
        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        self.bouton_fusionner = bouton("Fusionner avec le suivant", variante="contour", nom_icone="list-plus", action=self.fusionner_mot)
        actions.addWidget(self.bouton_fusionner)
        self.bouton_couper = bouton("Couper en deux", variante="contour", nom_icone="scissors", action=self.couper_mot)
        actions.addWidget(self.bouton_couper)
        self.bouton_supprimer = bouton("Supprimer", variante="contour", nom_icone="trash", action=self.supprimer_mot)
        actions.addWidget(self.bouton_supprimer)
        actions.addStretch(1)
        disposition.addLayout(actions)
        return panneau

    # --- Projet ------------------------------------------------------------------------------

    @property
    def transcription(self) -> Transcription | None:
        return self._projet.transcription if self._projet else None

    def _projet_change(self, projet: Projet | None) -> None:
        self.lecteur.arreter()
        self.extracteur.annuler()
        self._projet = projet
        self._source_en_cours = None
        if projet is None:
            return
        self.titre.setText(f"Transcription / {projet.nom}")
        transcription = projet.transcription
        choisir(self.langue, transcription.langue if transcription and transcription.date else projet.langue)
        if transcription and transcription.modele:
            choisir(self.modele, transcription.modele)
        self.separation.setChecked(bool(transcription and transcription.separation_voix))
        self.texte_seul.setChecked(bool(transcription and transcription.mode == MODE_SMART))
        self.masquer.blockSignals(True)
        self.masquer.setChecked(transcription.masquer_hesitations if transcription else True)
        self.masquer.blockSignals(False)
        self._afficher(f"Langue du projet : {LANGUES.get(projet.langue, projet.langue)}", "secondaire")
        self.editeur.choisir(-1)
        self.rafraichir()

    def _remplir_modeles(self) -> None:
        """Modèles de transcription chargés et accessibles avec les clés (ceux qui donnent le moment
        de chaque mot)."""
        actuel = self.modele.currentData() or MODELE_PAR_DEFAUT
        disponibles = self._services.connexions.modeles_disponibles(FOURNISSEUR)
        choix = [
            c
            for c in modeles_pour({Capacite.STT, Capacite.STT_MOTS_HORODATES}, disponibles)
            if c.compatible and propose(self._services, c.identifiant, actuel)
        ]
        self.modele.blockSignals(True)
        self.modele.clear()
        if choix:
            for c in choix:
                self.modele.addItem(c.nom, c.identifiant)
        else:
            for connu in MODELES_CONNUS:
                if Capacite.STT in connu.capacites and propose(self._services, connu.identifiant, actuel):
                    self.modele.addItem(connu.nom, connu.identifiant)
        choisir(self.modele, actuel)
        self.modele.blockSignals(False)
        self._modele_change()

    def _modele_change(self) -> None:
        """Réglages → Modèles et prix, colonne « Utilisé dans » : le modèle choisi ici."""
        self._services.modeles.choisir(TRANSCRIPTION, self.modele.currentData())

    # --- Affichage ---------------------------------------------------------------------------

    def _afficher(self, message: str, role: str) -> None:
        self.statut.setText(message)
        self.statut.setProperty("role", role)
        self.statut.style().unpolish(self.statut)
        self.statut.style().polish(self.statut)

    def _hesitations(self) -> set[str]:
        return hesitations(self._services, self.transcription)

    def showEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # La transcription peut avoir changé ailleurs (ex. sous-titres créés depuis une prise).
        super().showEvent(evenement)
        if self._projet is not None and not self._occupe:
            self.rafraichir()

    def rafraichir(self) -> None:
        """Met la page à jour d'après la transcription du projet."""
        transcription = self.transcription
        if transcription is not None and self.masquer.isChecked() != transcription.masquer_hesitations:
            self.masquer.blockSignals(True)  # réglage partagé avec la page Sous-titres
            self.masquer.setChecked(transcription.masquer_hesitations)
            self.masquer.blockSignals(False)
        a_source = bool(transcription and transcription.audio)
        self.zone_depot.setVisible(not a_source)
        self.texte_source.setVisible(a_source)
        self.bouton_changer.setVisible(a_source)
        if a_source:
            self.texte_source.setText(description_source(transcription))
        a_texte = bool(transcription and (transcription.mots or transcription.texte))
        self.cadre_transcription.setVisible(a_texte)
        if a_texte:
            horodatee = transcription.horodatee
            self.editeur.setVisible(horodatee)
            self.panneau_mot.setVisible(horodatee)
            self.texte_smart.setVisible(not horodatee)
            if horodatee:
                self.editeur.afficher(transcription.mots, self._hesitations(), transcription.masquer_hesitations)
            else:
                self.texte_smart.setPlainText(transcription.texte)
            self.resume.setText(self._resume(transcription))
            self._mot_choisi_change()
        self.bouton_transcrire.setEnabled(a_source and not self._occupe)
        self._etat_lecture()
        self._mettre_a_jour_estimation()

    def _resume(self, transcription: Transcription) -> str:
        morceaux = []
        if transcription.horodatee:
            morceaux.append(f"{len(transcription.mots)} mots")
            personnes = sorted({m.locuteur for m in transcription.mots if m.locuteur})
            if len(personnes) > 1:
                morceaux.append(", ".join(nom_de_personne(p) for p in personnes))
        else:
            morceaux.append("texte seul (mode « smart ») : pas de sous-titres possibles")
        connu = modele_connu(transcription.modele)
        if transcription.modele:
            morceaux.append(connu.nom if connu else transcription.modele)
        morceaux.append(LANGUES.get(transcription.langue, "langue détectée automatiquement"))
        try:
            morceaux.append(datetime.fromisoformat(transcription.date).strftime("%d/%m/%Y à %H:%M"))
        except ValueError:
            pass
        if transcription.cout_eur:
            morceaux.append(f"{transcription.cout_eur} €")
        return "  ·  ".join(morceaux)

    def _mettre_a_jour_estimation(self) -> None:
        transcription = self.transcription
        duree = transcription.duree_s if transcription else 0.0
        self.estimation.setText(f"≈ {minutes_secondes(duree)} d'audio  ·  ≈" if duree else "")
        self.cout_estime.setVisible(bool(duree))
        if duree:
            cout = estimer_cout(duree, self.modele.currentData() or MODELE_PAR_DEFAUT, self._services.prix)
            if cout is None:
                self.cout_estime.setText("prix inconnu")
            else:
                self.cout_estime.definir_montant(cout)

    def _texte_seul_change(self, actif: bool) -> None:
        self.zone_separation.setEnabled(not actif)  # incompatibles chez Google

    # --- Source ------------------------------------------------------------------------------

    def choisir_fichier(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(self, "Choisir une vidéo ou un audio", str(dossier_documents()), FILTRE_FICHIERS)
        if chemin:
            self.importer(Path(chemin))

    def dragEnterEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        if evenement.mimeData().hasUrls() and fichiers_acceptes(evenement.mimeData().urls()) and self._projet:
            evenement.acceptProposedAction()
            self.zone_depot.survol(True)

    def dragLeaveEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        super().dragLeaveEvent(evenement)

    def dropEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        fichiers = fichiers_acceptes(evenement.mimeData().urls())
        if fichiers:
            evenement.acceptProposedAction()
            self.importer(fichiers[0])

    def importer(self, chemin: Path) -> None:
        """Nouvelle source : extraction de la piste son, lecture de ses informations."""
        if self._projet is None or self._occupe:
            return
        if chemin.suffix.lower() not in EXTENSIONS_ACCEPTEES:
            self._afficher(f"Format non pris en charge : {chemin.suffix or chemin.name}.", "erreur")
            return
        transcription = self.transcription
        if transcription and transcription.mots and not self._confirmer_remplacement():
            return
        self.lecteur.arreter()
        self._source_en_cours = chemin
        self._infos_en_attente = {}
        self._occuper(True)
        self._afficher(f"Extraction de la piste son de « {chemin.name} »…", "secondaire")
        self.extracteur.extraire(chemin)
        self.infos.lire(chemin)

    def _confirmer_remplacement(self) -> bool:
        boite = QMessageBox(self.window())
        boite.setIcon(QMessageBox.Icon.Question)
        boite.setWindowTitle("Nouvelle source")
        boite.setText("Remplacer la transcription actuelle ?")
        transcription = self.transcription
        ajustes = (
            " Les sous-titres réorganisés à la main reviendront au découpage automatique."
            if transcription is not None and transcription.ajustements_sous_titres
            else ""
        )
        boite.setInformativeText(f"La nouvelle source devra être transcrite à son tour.{ajustes}")
        remplacer = boite.addButton("Remplacer", QMessageBox.ButtonRole.AcceptRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.exec()
        return boite.clickedButton() is remplacer

    def _progression_extraction(self, part: float) -> None:
        if self._source_en_cours is not None:
            self._afficher(f"Extraction de la piste son de « {self._source_en_cours.name} »… {round(part * 100)} %", "secondaire")

    def _extraction_terminee(self, wav: bytes) -> None:
        self._occuper(False)
        projet, source = self._projet, self._source_en_cours
        if projet is None or source is None:
            return
        chemin = projet.chemin(FICHIER_AUDIO)
        try:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            chemin.write_bytes(wav)
        except OSError as erreur:
            self._afficher(f"Piste son non enregistrée dans le projet : {erreur}", "erreur")
            return
        duree = round(duree_wav(wav), 3)
        projet.transcription = Transcription(
            source=str(source),
            audio=FICHIER_AUDIO,
            duree_s=duree,
            infos=dict(self._infos_en_attente),
            langue=self.langue.currentData() or AUTO,
            masquer_hesitations=self.masquer.isChecked(),
        )
        self._services.projets.enregistrer()
        self.editeur.choisir(-1)
        self._afficher(f"Piste son prête ({minutes_secondes(duree)}) : clique sur « Transcrire ».", "succes")
        self.rafraichir()

    def _extraction_echouee(self, raison: str) -> None:
        self._occuper(False)
        nom = self._source_en_cours.name if self._source_en_cours else "ce fichier"
        self._source_en_cours = None
        self._afficher(f"Impossible de lire la piste son de « {nom} » : {raison}.", "erreur")

    def _infos_pretes(self, infos: dict) -> None:
        """Informations de la source (arrivent pendant ou après l'extraction)."""
        self._infos_en_attente = infos
        transcription = self.transcription
        if transcription and self._source_en_cours is None and transcription.source and not transcription.infos:
            transcription.infos = infos
            self._services.projets.enregistrer()
            self.rafraichir()
        elif transcription and self._source_en_cours is not None and transcription.source == str(self._source_en_cours):
            transcription.infos = infos
            self._services.projets.enregistrer()
            self.rafraichir()

    def _occuper(self, occupe: bool) -> None:
        self._occupe = occupe
        self.bouton_transcrire.setEnabled(not occupe and bool(self.transcription and self.transcription.audio))
        self.bouton_changer.setEnabled(not occupe)
        self.zone_depot.setEnabled(not occupe)

    # --- Transcrire --------------------------------------------------------------------------

    def options(self) -> Options:
        return Options(
            self.modele.currentData() or MODELE_PAR_DEFAUT,
            self.langue.currentData() or AUTO,
            MODE_SMART if self.texte_seul.isChecked() else MODE_VERBATIM,
            self.separation.isChecked() and not self.texte_seul.isChecked(),
            FOURNISSEUR,
        )

    def transcrire(self) -> None:
        projet, transcription = self._projet, self.transcription
        if projet is None or transcription is None or not transcription.audio:
            self._afficher("Importe d'abord une vidéo ou un audio.", "erreur")
            return
        chemin = projet.chemin(transcription.audio)
        if not chemin.exists():
            self._afficher("Piste son introuvable dans le dossier du projet : importe à nouveau la source.", "erreur")
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        options = self.options()
        wav = chemin.read_bytes()
        self.lecteur.arreter()
        self._occuper(True)
        self._afficher("Transcription en cours… (envoi de l'audio à Google, puis transcription)", "secondaire")

        def fin(resultat) -> None:
            self._occuper(False)
            if self._projet is not projet:
                return
            fini = terminer_transcription(self._services, transcription, options, resultat)
            self.editeur.choisir(-1)
            if options.mode == MODE_VERBATIM and not fini.mots:
                self._afficher("Google n'a renvoyé aucun mot : la source est-elle silencieuse ?", "avertissement")
            elif options.mode == MODE_VERBATIM:
                suite = f" (source coupée en {resultat.morceaux} morceaux)" if resultat.morceaux > 1 else ""
                self._afficher(f"Transcription prête : {len(fini.mots)} mots{suite}.", "succes")
            else:
                self._afficher("Texte prêt (mode « smart », sans le moment de chaque mot).", "succes")
            self.rafraichir()

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Transcription impossible : {message_erreur(erreur)}", "erreur")

        taches.lancer(lambda: transcrire_source(adaptateur, wav, options, projet.nom), fin, echec)

    # --- Options qui s'appliquent tout de suite ------------------------------------------------

    def _masquer_change(self, masquer: bool) -> None:
        transcription = self.transcription
        if transcription is None:
            return
        # Même réglage que dans la page Sous-titres : s'il défait un sous-titre réorganisé à la
        # main, la même question est posée (V1.1).
        if not confirmer_reglage(self.window(), self._services, self._projet, masquer=masquer):
            self.masquer.blockSignals(True)  # « Garder le réglage actuel »
            self.masquer.setChecked(not masquer)
            self.masquer.blockSignals(False)
            return
        transcription.masquer_hesitations = masquer
        self._services.projets.enregistrer()
        self.rafraichir()

    def ouvrir_remplacements(self) -> None:
        dialogue = DialogueRemplacements(self._services, self.window())
        if dialogue.exec():
            self.appliquer_dictionnaire()

    def appliquer_dictionnaire(self) -> None:
        """Dictionnaire modifié : appliqué tout de suite à la transcription (sans la refaire)."""
        transcription = self.transcription
        if transcription is None or not transcription.mots:
            return
        entrees = fusionner_remplacements(self._services.remplacements.entrees, self._projet.remplacements)
        mots = appliquer_remplacements(transcription.mots, entrees)
        if mots != transcription.mots:
            transcription.mots = mots
            self._services.projets.enregistrer()
            self.editeur.choisir(-1)
            self._afficher("Dictionnaire de remplacements appliqué à la transcription.", "succes")
        self.rafraichir()

    def modifier_hesitations(self) -> None:
        langue = langue_de(self.transcription, self._projet)
        code = langue.split("-")[0]
        actuelles = sorted(self._hesitations())
        texte, ok = QInputDialog.getText(
            self,
            "Hésitations",
            f"Hésitations en {LANGUES.get(langue, langue).split(' (')[0].lower()} (séparées par des virgules) :",
            text=", ".join(actuelles),
        )
        if not ok:
            return
        personnalisees = dict(self._services.preferences.lire(PREFERENCE_HESITATIONS, {}) or {})
        personnalisees[code] = [m.strip() for m in texte.split(",") if m.strip()]
        self._services.preferences.ecrire(PREFERENCE_HESITATIONS, personnalisees)
        self._services.preferences.enregistrer()
        self.rafraichir()

    # --- Lecture -----------------------------------------------------------------------------

    def _chemin_audio(self) -> Path | None:
        transcription = self.transcription
        if self._projet is None or transcription is None or not transcription.audio:
            return None
        return self._projet.chemin(transcription.audio)

    def basculer_lecture(self) -> None:
        chemin = self._chemin_audio()
        if chemin is None or not chemin.exists():
            return
        if self.lecteur.chemin == str(chemin):
            self.lecteur.basculer(chemin)
            return
        choisi = self.editeur.mot_choisi
        mots = self.transcription.mots
        depart = round(mots[choisi].debut * 1000) if 0 <= choisi < len(mots) else 0
        self.lecteur.jouer_depuis(chemin, depart)

    def _etat_lecture(self) -> None:
        chemin = self._chemin_audio()
        en_lecture = chemin is not None and self.lecteur.en_lecture(chemin)
        self.bouton_lecture.setIcon(icone("pause" if en_lecture else "play", Couleurs.ACCENT_SURVOL, rempli=True))
        self.bouton_lecture.setToolTip("Pause" if en_lecture else "Écouter la source")

    def _position_lue(self, position_ms: int, duree_ms: int) -> None:
        chemin = self._chemin_audio()
        if chemin is None or self.lecteur.chemin != str(chemin):
            return
        if not self.position.isSliderDown():
            self.position.setRange(0, max(duree_ms, 0))
            self.position.setValue(position_ms)
        self.temps.setText(f"{minutes_secondes(position_ms / 1000)} / {minutes_secondes(duree_ms / 1000)}")
        transcription = self.transcription
        if transcription and transcription.mots:
            self.editeur.mettre_en_lecture(index_au_temps(transcription.mots, position_ms / 1000))

    # --- Mot choisi (§6.4) ---------------------------------------------------------------------

    def choisir_mot(self, index: int) -> None:
        """Clic sur un mot : il est choisi pour être corrigé ; la lecture se place à ce moment."""
        transcription = self.transcription
        if transcription is None or not 0 <= index < len(transcription.mots):
            return
        self.editeur.choisir(index)
        self._mot_choisi_change()
        chemin = self._chemin_audio()
        if chemin is not None and self.lecteur.chemin == str(chemin):
            self.lecteur.aller_a(round(transcription.mots[index].debut * 1000))

    def choisir_mot_au_temps(self, temps: float) -> None:
        """Depuis la frise des sous-titres (double-clic sur un bloc) : le premier mot qui commence à ce
        moment (ou après) est choisi, prêt à être corrigé."""
        transcription = self.transcription
        if transcription is None or not transcription.mots:
            return
        self.rafraichir()  # les mots affichés sont ceux du projet, même si la page n'a pas encore été montrée
        mots = transcription.mots
        index = next((i for i, mot in enumerate(mots) if mot.debut >= temps - MEME_MOMENT_S), len(mots) - 1)
        self.choisir_mot(index)

    def _mot_choisi_change(self) -> None:
        transcription = self.transcription
        index = self.editeur.mot_choisi
        valide = transcription is not None and 0 <= index < len(transcription.mots)
        for element in (self.champ_mot, self.champ_debut, self.champ_fin, self.bouton_appliquer, self.bouton_couper, self.bouton_supprimer):
            element.setEnabled(valide)
        self.bouton_fusionner.setEnabled(valide and index < len(transcription.mots) - 1)
        if not valide:
            self.titre_mot.setText("Clique sur un mot pour le corriger (son moment dans l'audio est gardé).")
            for champ in (self.champ_mot, self.champ_debut, self.champ_fin):
                champ.clear()
            return
        mot = transcription.mots[index]
        personne = f" · {nom_de_personne(mot.locuteur)}" if mot.locuteur else ""
        self.titre_mot.afficher_etat(f"Mot {index + 1} sur {len(transcription.mots)}{personne}")  # donnée : sans ampoule
        self.champ_mot.setText(mot.texte)
        self.champ_debut.setText(f"{mot.debut:.2f}")
        self.champ_fin.setText(f"{mot.fin:.2f}")

    def _modifier(self, action, message: str, choisi: int | None = None) -> None:
        """Applique une correction aux mots, enregistre, puis réaffiche."""
        transcription = self.transcription
        try:
            action(transcription.mots)
        except ValueError as erreur:
            self._afficher(str(erreur), "erreur")
            return
        self._services.projets.enregistrer()
        self.editeur.choisir(-1 if choisi is None else min(choisi, len(transcription.mots) - 1))
        self._afficher(message, "succes")
        self.rafraichir()

    def appliquer_mot(self) -> None:
        index = self.editeur.mot_choisi
        transcription = self.transcription
        if transcription is None or not 0 <= index < len(transcription.mots):
            return
        try:
            debut = float(lire_decimal(self.champ_debut.text()))
            fin = float(lire_decimal(self.champ_fin.text()))
        except ValueError:
            self._afficher("Début et fin : des secondes, ex. 1.25", "erreur")
            return

        def action(mots) -> None:
            corriger(mots, index, self.champ_mot.text())
            ajuster(mots, index, debut, fin, transcription.duree_s or None)

        self._modifier(action, "Mot corrigé.", index)

    def fusionner_mot(self) -> None:
        index = self.editeur.mot_choisi
        self._modifier(lambda mots: fusionner(mots, index), "Mots fusionnés : corrige le texte si besoin.", index)

    def couper_mot(self) -> None:
        index = self.editeur.mot_choisi
        self._modifier(lambda mots: couper(mots, index), "Mot coupé en deux.", index)

    def supprimer_mot(self) -> None:
        index = self.editeur.mot_choisi
        self._modifier(lambda mots: supprimer(mots, index), "Mot supprimé.", index)

    def copier_texte(self) -> None:
        transcription = self.transcription
        if transcription is None:
            return
        texte = " ".join(m.texte for m in transcription.mots) if transcription.mots else transcription.texte
        QGuiApplication.clipboard().setText(texte)
        self._afficher("Texte copié : colle-le où tu veux (Ctrl+V).", "succes")
