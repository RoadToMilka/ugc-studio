"""Atelier de transcription (§6) : importer une vidéo ou un audio, le transcrire mot par mot,
puis corriger la transcription en l'écoutant.

1. Source : glisser-déposer ou « Choisir un fichier… ». La piste son est extraite (WAV 16 kHz
   mono, dans le dossier « sources » du projet) et les informations de la source sont gardées.
2. Options : modèle, langue (détection automatique ou langue forcée), séparation des voix,
   texte seul (mode « smart », sans les temps), dictionnaire de remplacements, hésitations.
3. Transcription : texte mot par mot synchronisé avec la lecture ; clic sur un mot pour le
   choisir, le corriger sans perdre son timing, le fusionner, le couper, le supprimer ou ajuster
   son début et sa fin (composants/correcteur_mots.py, le même que la fenêtre « Corriger les mots »
   des sous-titres importés, V3.1).

V3.1 (lot 6) : la page Sous-titres peut importer ici une vidéo ou un audio, et la transcrire, avec
les options choisies ici (importer, transcrire, et les signaux import_termine, transcription_terminee
et infos_lues) : les deux modules montrent la même source.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
)

from ....audio import duree_wav
from ....chemins import dossier_documents
from ....fournisseurs.capacites import MODELES_CONNUS, Capacite, modele_connu, modeles_pour
from ....fournisseurs.stt import MODE_SMART, MODE_VERBATIM
from ....modeles_charges import TRANSCRIPTION
from ....projets import FICHIER_AUDIO, LANGUES, Projet, liberer_la_piste_son
from ....services import Services
from ....sources import mots_des_sous_titres
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
    appliquer_remplacements,
    fusionner_remplacements,
    index_au_temps,
    resolution_video,
)
from ... import taches
from ...composants.bouton import BoutonOccupe
from ...composants.choix_voix import choisir, propose
from ...composants.correcteur_mots import CorrecteurDeMots
from ...composants.editeur_transcription import nom_de_personne
from ...composants.elements import (
    afficher_message,
    bloc,
    bouton,
    case_a_cocher,
    champs_en_colonnes,
    glissiere,
    info,
    libelle,
    liste_deroulante,
    minutes_secondes,
    titre_avec,
)
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues import messages
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
        # Textes qui passent à la ligne : jamais posés avec un alignement dans la disposition (Qt leur
        # donnait une largeur réduite mais la hauteur d'une ligne, et la fin était coupée, voir libelle()).
        # Le titre est centré dans toute la largeur ; l'info, entre deux ressorts, à sa largeur.
        disposition.addWidget(libelle("Glisse une vidéo ou un audio ici", "intitule", centre=True))
        ligne_info = QHBoxLayout()
        ligne_info.addStretch(1)
        ligne_info.addWidget(
            info("Vidéo (MP4, MOV, MKV…) ou audio (WAV, MP3, M4A…) : la piste son est extraite automatiquement.", "legende")
        )
        ligne_info.addStretch(1)
        disposition.addLayout(ligne_info)
        ligne = QHBoxLayout()
        ligne.addStretch(1)
        self.bouton_choisir = bouton("Choisir un fichier…", nom_icone="folder-open", action=choisir_fichier)
        ligne.addWidget(self.bouton_choisir)
        ligne.addStretch(1)
        disposition.addLayout(ligne)

    def survol(self, actif: bool) -> None:
        self.setProperty("survol", actif)
        self.style().unpolish(self)
        self.style().polish(self)


class AtelierTranscription(Page):
    # V3.1, lot 6 : la fin d'un import ou d'une transcription demandés depuis la page Sous-titres
    # (message, rôle : « succes », « erreur »…).
    import_termine = Signal(str, str)
    transcription_terminee = Signal(str, str)
    infos_lues = Signal()  # les informations de la source (taille de la vidéo…), arrivées après son import

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
        self._bouton_occupe = BoutonOccupe()  # le bouton où tourne le cercle pendant le travail (V3.1)
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
        # Le texte mot par mot et le mot choisi (composants/correcteur_mots.py).
        self.correcteur = CorrecteurDeMots()
        self.correcteur.mot_clique.connect(self.choisir_mot)
        self.correcteur.corrige.connect(self._mots_corriges)
        self.correcteur.refuse.connect(lambda raison: self._afficher(raison, "erreur"))
        d.addWidget(self.correcteur)
        correcteur = self.correcteur
        self.editeur, self.panneau_mot, self.titre_mot = correcteur.editeur, correcteur.panneau, correcteur.titre_mot
        self.champ_mot, self.champ_debut, self.champ_fin = correcteur.champ_mot, correcteur.champ_debut, correcteur.champ_fin
        self.bouton_appliquer, self.bouton_fusionner = correcteur.bouton_appliquer, correcteur.bouton_fusionner
        self.bouton_couper, self.bouton_supprimer = correcteur.bouton_couper, correcteur.bouton_supprimer
        self.texte_smart = QPlainTextEdit()
        self.texte_smart.setReadOnly(True)
        self.texte_smart.setMinimumHeight(Dimensions.EDITEUR_HAUTEUR_MIN)
        d.addWidget(self.texte_smart)
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

    @property
    def occupe(self) -> bool:
        """Une extraction du son ou une transcription en cours (V3.1 : la page Sous-titres le sait)."""
        return self._occupe

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
        self.titre.setText(titre_avec("Transcription", projet.nom))
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
        # Vert, rouge ou orange : effacé après 8 s (V3.2) ; la ligne garde sa place.
        afficher_message(self.statut, message, role, cacher_vide=False)

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
            self.correcteur.setVisible(horodatee)
            self.texte_smart.setVisible(not horodatee)
            if horodatee:
                self.correcteur.afficher(
                    transcription.mots, self._hesitations(), transcription.masquer_hesitations, transcription.duree_s or None
                )
            else:
                self.texte_smart.setPlainText(transcription.texte)
            self.resume.setText(self._resume(transcription))
        self.bouton_transcrire.setEnabled(a_source and (not self._occupe or self._bouton_occupe.est(self.bouton_transcrire)))
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

    def importer(self, chemin: Path) -> bool:
        """Nouvelle source : extraction de la piste son, lecture de ses informations. Renvoie True si
        l'import commence (la fin arrive avec le signal import_termine)."""
        if self._projet is None or self._occupe:
            return False
        if chemin.suffix.lower() not in EXTENSIONS_ACCEPTEES:
            message = f"Format non pris en charge : {chemin.suffix or chemin.name}."
            self._afficher(message, "erreur")
            self.import_termine.emit(message, "erreur")
            return False
        transcription = self.transcription
        if transcription and transcription.mots and not self._confirmer_remplacement():
            return False
        self.lecteur.arreter()
        self._source_en_cours = chemin
        self._infos_en_attente = {}
        # Le cercle tourne dans le bouton d'import affiché (« Choisir un fichier… » ou « Changer de
        # source… »), aussi quand le fichier a été glissé dans la page.
        self._occuper(True, self.bouton_changer if self.bouton_changer.isVisible() else self.zone_depot.bouton_choisir)
        self._afficher(f"Extraction de la piste son de « {chemin.name} »…", "secondaire")
        self.extracteur.extraire(chemin)
        self.infos.lire(chemin)
        return True

    def _confirmer_remplacement(self) -> bool:
        transcription = self.transcription
        ajustes = (
            " Les sous-titres réorganisés à la main reviendront au découpage automatique."
            if transcription is not None and transcription.ajustements_sous_titres
            else ""
        )
        return messages.confirmer(
            self.window(),
            "Nouvelle source",
            "Remplacer la transcription actuelle ?",
            f"La nouvelle source devra être transcrite à son tour.{ajustes}",
            action="Remplacer",
        )

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
            liberer_la_piste_son(projet)  # des sous-titres importés d'avant la 3.1.0 gardent la leur
            chemin.write_bytes(wav)
        except OSError as erreur:
            message = f"Piste son non enregistrée dans le projet : {erreur}"
            self._afficher(message, "erreur")
            self.import_termine.emit(message, "erreur")
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
        self.import_termine.emit(f"« {source.name} » importée ({minutes_secondes(duree)}) : prête à être transcrite.", "succes")

    def _extraction_echouee(self, raison: str) -> None:
        self._occuper(False)
        nom = self._source_en_cours.name if self._source_en_cours else "ce fichier"
        self._source_en_cours = None
        message = f"Impossible de lire la piste son de « {nom} » : {raison}."
        self._afficher(message, "erreur")
        self.import_termine.emit(message, "erreur")

    def _infos_pretes(self, infos: dict) -> None:
        """Informations de la source (arrivent pendant ou après l'extraction)."""
        self._infos_en_attente = infos
        transcription = self.transcription
        if transcription and self._source_en_cours is None and transcription.source and not transcription.infos:
            transcription.infos = infos
            self._services.projets.enregistrer()
            self.rafraichir()
            self.infos_lues.emit()
        elif transcription and self._source_en_cours is not None and transcription.source == str(self._source_en_cours):
            transcription.infos = infos
            self._services.projets.enregistrer()
            self.rafraichir()
            self.infos_lues.emit()  # la page Sous-titres suit (vidéo de l'aperçu, format)

    def _occuper(self, occupe: bool, bouton=None) -> None:
        """Pendant l'extraction de la piste son ou la transcription : le cercle tourne dans `bouton`
        (celui qui a lancé le travail), qui garde son aspect ; les autres sont grisés (V3.1)."""
        self._occupe = occupe
        if occupe:
            self._bouton_occupe.occuper(bouton)
        else:
            self._bouton_occupe.liberer()
        actif = self._bouton_occupe.est
        a_source = bool(self.transcription and self.transcription.audio)
        self.bouton_transcrire.setEnabled((not occupe and a_source) or actif(self.bouton_transcrire))
        self.bouton_changer.setEnabled(not occupe or actif(self.bouton_changer))
        self.zone_depot.setEnabled(not occupe or actif(self.zone_depot.bouton_choisir))

    # --- Transcrire --------------------------------------------------------------------------

    def options(self) -> Options:
        return Options(
            self.modele.currentData() or MODELE_PAR_DEFAUT,
            self.langue.currentData() or AUTO,
            MODE_SMART if self.texte_seul.isChecked() else MODE_VERBATIM,
            self.separation.isChecked() and not self.texte_seul.isChecked(),
            FOURNISSEUR,
        )

    def transcrire(self) -> bool:
        """Transcrit la source avec les options choisies ici. Renvoie True si la transcription
        commence (la fin arrive avec le signal transcription_terminee)."""
        projet, transcription = self._projet, self.transcription
        if self._occupe:
            return False
        if projet is None or transcription is None or not transcription.audio:
            return self._refuser_la_transcription("Importe d'abord une vidéo ou un audio.")
        chemin = projet.chemin(transcription.audio)
        if not chemin.exists():
            return self._refuser_la_transcription("Piste son introuvable dans le dossier du projet : importe à nouveau la source.")
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            return self._refuser_la_transcription(message_erreur(erreur))
        options = self.options()
        wav = chemin.read_bytes()
        self.lecteur.arreter()
        self._occuper(True, self.bouton_transcrire)
        self._afficher("Transcription en cours… (envoi de l'audio à Google, puis transcription)", "secondaire")

        def fin(resultat) -> None:
            self._occuper(False)
            if self._projet is not projet:
                return
            fini = terminer_transcription(self._services, transcription, options, resultat)
            self.editeur.choisir(-1)
            if options.mode == MODE_VERBATIM and not fini.mots:
                message, role = "Google n'a renvoyé aucun mot : la source est-elle silencieuse ?", "avertissement"
            elif options.mode == MODE_VERBATIM:
                suite = f" (source coupée en {resultat.morceaux} morceaux)" if resultat.morceaux > 1 else ""
                message, role = f"Transcription prête : {len(fini.mots)} mots{suite}.", "succes"
            else:
                message, role = "Texte prêt (mode « smart », sans le moment de chaque mot).", "succes"
            self._afficher(message, role)
            self.rafraichir()
            self.transcription_terminee.emit(message, role)

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            message = f"Transcription impossible : {message_erreur(erreur)}"
            self._afficher(message, "erreur")
            self.transcription_terminee.emit(message, "erreur")

        taches.lancer(lambda: transcrire_source(adaptateur, wav, options, projet.nom), fin, echec)
        return True

    def _refuser_la_transcription(self, message: str) -> bool:
        self._afficher(message, "erreur")
        self.transcription_terminee.emit(message, "erreur")
        return False

    # --- Options qui s'appliquent tout de suite ------------------------------------------------

    def _masquer_change(self, masquer: bool) -> None:
        transcription = self.transcription
        if transcription is None:
            return
        # Même réglage que dans la page Sous-titres : s'il défait un sous-titre réorganisé à la
        # main, la même question est posée (V1.1) ; seulement quand les sous-titres sont faits de ces
        # mots (V3.1 : ils peuvent venir de mots importés).
        concerne = mots_des_sous_titres(self._projet) is transcription
        if concerne and not confirmer_reglage(self.window(), self._services, self._projet, masquer=masquer):
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
        texte = messages.demander_texte(
            self.window(),
            "Hésitations",
            f"Hésitations en {LANGUES.get(langue, langue).split(' (')[0].lower()}",
            ", ".join(actuelles),
            action="Enregistrer",
            precision="Sépare les mots par des virgules.",
        )
        if texte is None:
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

    # --- Mot choisi (§6.4, composants/correcteur_mots.py) ---------------------------------------

    def choisir_mot(self, index: int) -> None:
        """Clic sur un mot : il est choisi pour être corrigé ; la lecture se place à ce moment."""
        transcription = self.transcription
        if transcription is None or not 0 <= index < len(transcription.mots):
            return
        self.correcteur.choisir(index)
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

    def _mots_corriges(self, message: str) -> None:
        """Une correction faite dans le texte : enregistrée, puis réaffichée."""
        transcription = self.transcription
        if transcription is not None:
            transcription.corrigee = True
        self._services.projets.enregistrer()
        self._afficher(message, "succes")
        self.rafraichir()

    def appliquer_mot(self) -> None:
        self.correcteur.appliquer_mot()

    def fusionner_mot(self) -> None:
        self.correcteur.fusionner_mot()

    def couper_mot(self) -> None:
        self.correcteur.couper_mot()

    def supprimer_mot(self) -> None:
        self.correcteur.supprimer_mot()

    def copier_texte(self) -> None:
        transcription = self.transcription
        if transcription is None:
            return
        texte = " ".join(m.texte for m in transcription.mots) if transcription.mots else transcription.texte
        QGuiApplication.clipboard().setText(texte)
        self._afficher("Texte copié : colle-le où tu veux (Ctrl+V).", "succes")
