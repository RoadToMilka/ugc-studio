"""Zone « Source » de la page Sous-titres (V3.1, lot 6 ; cahier des charges §7.14) : d'où viennent
la vidéo de l'aperçu et les mots des sous-titres (voir sources.py).

Deux onglets. Dans chacun, deux choix : « Module Transcription » ou « Importée(s) » ; on passe de l'un
à l'autre sans rien perdre.
- **Vidéo ou audio** : celle du module Transcription (la même que là-bas ; « Choisir une vidéo ou un
  audio… » l'y importe, pour les deux modules), ou une vidéo importée ici (« Choisir une vidéo… »,
  « Son de la vidéo »). C'est elle que montre l'aperçu, et que reprend l'export « Vidéo avec
  sous-titres ».
- **Sous-titres** : les mots du module Transcription (« Transcrire » ici, avec les options du module,
  quand ils manquent ; « Corriger les mots » ouvre le module), ou des mots importés : d'une prise de
  voix (« Créer les sous-titres ») ou d'un fichier SRT. « Corriger les mots » ouvre alors une fenêtre
  de correction, la même que dans le module Transcription.
Une ligne dit toujours d'où viennent les mots. « La voix commence à » s'affiche quand la vidéo et les
mots ne viennent pas du même enregistrement.

Ce bloc ne fait que montrer (afficher : EtatSource) et demander (signaux) : la page s'en charge.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ....sources import SOURCE_IMPORTEE, SOURCE_TRANSCRIPTION
from ...composants.choix import ChoixEnBoutons
from ...composants.elements import (
    BoutonInfo,
    ChampNomme,
    afficher_message,
    bouton,
    case_a_cocher,
    champ_decimal,
    libelle,
    ligne_avec_aide,
    liste_deroulante,
    marge_haute_titre,
)
from ...composants.montant_label import MontantLabel
from ...composants.onglets import Onglets
from ...composants.zone import DispositionDeZone
from ...theme import Dimensions, Espacements

ONGLET_VIDEO, ONGLET_MOTS = range(2)
DECALAGE_MAX_S = 3600.0  # « La voix commence à » : une heure au plus (comme VideoApercu.LIMITES)


@dataclass(frozen=True)
class EtatSource:
    """Ce que montre la zone Source (calculé par la page)."""

    video: str = SOURCE_TRANSCRIPTION  # choix de l'onglet « Vidéo ou audio »
    mots: str = SOURCE_TRANSCRIPTION  # choix de l'onglet « Sous-titres »
    texte_video: str = ""
    texte_mots: str = ""
    module_a_une_source: bool = False  # une vidéo ou un audio dans le module Transcription
    video_importee: bool = False  # une vidéo importée ici
    son_de_la_video: bool = True
    voix_des_mots: bool = False  # les mots ont leur piste son (pas ceux d'un fichier SRT) : « Son de la vidéo »
    corriger: bool = False  # des mots à corriger
    transcrire: bool = False  # la source du module Transcription n'a pas encore de mots
    voix_a_caler: bool = False  # « La voix commence à »
    decalage_s: float = 0.0


class BlocSource(QFrame):
    video_choisie = Signal(str)  # SOURCE_TRANSCRIPTION ou SOURCE_IMPORTEE
    mots_choisis = Signal(str)
    importer_demande = Signal()  # une vidéo ou un audio pour le module Transcription
    choisir_video_demande = Signal()  # une vidéo importée ici
    retirer_video_demande = Signal()
    son_de_la_video_change = Signal(bool)
    decalage_change = Signal(float)
    transcrire_demande = Signal()
    corriger_demande = Signal()
    creer_demande = Signal()  # les sous-titres de la prise choisie
    importer_srt_demande = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "bloc")
        disposition = DispositionDeZone(self)  # la place en trop en bas du bloc (V3.3)
        disposition.setContentsMargins(Espacements.XL, marge_haute_titre(), Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        self.titre = libelle("Source", "titre-bloc")
        disposition.addWidget(self.titre)
        self.onglets = Onglets(hauteur_selon_l_onglet=True, separateur=False)
        self.onglets.addTab(self._onglet_video(), "Vidéo ou audio")
        self.onglets.addTab(self._onglet_mots(), "Sous-titres")
        self.onglets.setCurrentIndex(ONGLET_MOTS)  # le plus utile au départ : d'où viennent les mots
        disposition.addWidget(self.onglets)
        self.ligne_decalage = self._ligne_decalage()
        disposition.addWidget(self.ligne_decalage)
        self.statut = libelle("", "secondaire")  # message d'état (vide : caché)
        self.statut.hide()
        disposition.addWidget(self.statut)
        disposition.addStretch(1)  # à côté d'Exporter, les deux blocs ont la même hauteur : le contenu reste en haut

    # --- Construction ------------------------------------------------------------------------

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        disposition = QVBoxLayout(page)
        disposition.setContentsMargins(0, Espacements.M, 0, 0)
        disposition.setSpacing(Espacements.M)
        return page, disposition

    @staticmethod
    def _ligne(texte: QWidget, *boutons: QWidget) -> QHBoxLayout:
        """Une ligne qui décrit, et ses boutons au bout."""
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.M)
        ligne.addWidget(texte, 1)
        for element in boutons:
            ligne.addWidget(element, 0, Qt.AlignmentFlag.AlignVCenter)
        return ligne

    def _onglet_video(self) -> QWidget:
        page, d = self._page()
        self.choix_video = ChoixEnBoutons({SOURCE_TRANSCRIPTION: "Module Transcription", SOURCE_IMPORTEE: "Importée"})
        self.choix_video.change.connect(self.video_choisie.emit)
        d.addWidget(
            ChampNomme(
                "Vidéo de l'aperçu",
                self.choix_video,
                aide=(
                    "La vidéo que montre l'aperçu, et que reprend l'export « Vidéo avec sous-titres ». Celle du "
                    "module Transcription est la même que là-bas : l'importer ici l'importe pour les deux modules."
                ),
            )
        )
        self.texte_video = libelle("", "secondaire")
        self.bouton_importer = bouton(
            "Choisir une vidéo ou un audio…", variante="contour", nom_icone="folder-open", action=self.importer_demande.emit
        )
        self.bouton_importer.setToolTip("Importée dans le module Transcription : elle sert aux deux modules")
        self.bouton_choisir_video = bouton(
            "Choisir une vidéo…", variante="contour", nom_icone="film", action=self.choisir_video_demande.emit
        )
        self.bouton_choisir_video.setToolTip("Par exemple ton montage exporté de Premiere Pro (elle n'est pas copiée dans le projet)")
        self.bouton_retirer_video = bouton("Retirer", variante="contour", nom_icone="trash", action=self.retirer_video_demande.emit)
        d.addLayout(self._ligne(self.texte_video, self.bouton_importer, self.bouton_choisir_video, self.bouton_retirer_video))
        self.zone_son_video, self.son_video = case_a_cocher(
            "Son de la vidéo", "Décoché : la voix des sous-titres (une prise), sous la vidéo muette, aussi dans l'export."
        )
        self.son_video.toggled.connect(self.son_de_la_video_change.emit)
        d.addWidget(self.zone_son_video)
        return page

    def _onglet_mots(self) -> QWidget:
        page, d = self._page()
        self.choix_mots = ChoixEnBoutons({SOURCE_TRANSCRIPTION: "Module Transcription", SOURCE_IMPORTEE: "Importés"})
        self.choix_mots.change.connect(self.mots_choisis.emit)
        d.addWidget(
            ChampNomme(
                "Mots des sous-titres",
                self.choix_mots,
                aide=(
                    "Ceux du module Transcription, ou des mots importés ici : d'une prise de voix ou d'un fichier "
                    "SRT. Chaque source garde ses mots et ses retouches : tu passes de l'une à l'autre sans rien "
                    "perdre. Un nouvel import ne remplace que l'import précédent."
                ),
            )
        )
        self.texte_mots = libelle("", "secondaire")
        self.bouton_corriger = bouton("Corriger les mots", variante="contour", nom_icone="pencil", action=self.corriger_demande.emit)
        d.addLayout(self._ligne(self.texte_mots, self.bouton_corriger))

        # Module Transcription, pas encore transcrite : « Transcrire » ici, avec le coût estimé.
        self.zone_transcrire = QWidget()
        ligne = QHBoxLayout(self.zone_transcrire)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.M)
        self.bouton_transcrire = bouton("Transcrire", variante="principal", nom_icone="audio-lines", action=self.transcrire_demande.emit)
        self.bouton_transcrire.setToolTip("Avec les options choisies dans le module Transcription (modèle, langue…)")
        ligne.addWidget(self.bouton_transcrire)
        self.estimation_transcrire, self.cout_transcrire = self._estimation()
        ligne.addLayout(self.estimation_transcrire.ligne)
        ligne.addStretch(1)
        d.addWidget(self.zone_transcrire)

        # Importés : d'une prise de voix, ou d'un fichier SRT.
        self.zone_importes = QWidget()
        importes = QVBoxLayout(self.zone_importes)
        importes.setContentsMargins(0, 0, 0, 0)
        importes.setSpacing(Espacements.XS)
        grille = QGridLayout()
        grille.setHorizontalSpacing(Espacements.S)
        grille.setVerticalSpacing(Dimensions.ECART_NOM_CHAMP)  # le nom au-dessus de la liste (V3.2)
        self.prises = liste_deroulante("Prise dont créer les sous-titres")
        grille.addLayout(
            ligne_avec_aide(
                libelle("Prise", "legende", retour_a_la_ligne=False),
                BoutonInfo(
                    "Depuis une voix générée : la prise est transcrite (moment de chaque mot), puis calée sur son "
                    "script, dont l'orthographe exacte est gardée."
                ),
            ),
            0,
            0,
        )
        grille.addWidget(self.prises, 1, 0)
        self.bouton_creer = bouton("Créer les sous-titres", variante="principal", nom_icone="captions", action=self.creer_demande.emit)
        grille.addWidget(self.bouton_creer, 1, 1)
        grille.setColumnStretch(0, 1)
        importes.addLayout(grille)
        self.estimation, self.cout_estime = self._estimation()
        importes.addLayout(self.estimation.ligne)
        importes.addSpacing(Espacements.S)
        srt = QHBoxLayout()
        srt.setSpacing(Espacements.S)
        self.bouton_srt = bouton("Importer un fichier SRT…", variante="contour", nom_icone="file-text", action=self.importer_srt_demande.emit)
        self.bouton_srt.setToolTip(
            "Des sous-titres faits ailleurs (Premiere Pro, CapCut…) : le moment de chaque mot est estimé, puis ton "
            "découpage s'applique"
        )
        srt.addWidget(self.bouton_srt)
        srt.addStretch(1)
        importes.addLayout(srt)
        d.addWidget(self.zone_importes)
        return page

    @staticmethod
    def _estimation():
        """« ≈ 0:12 d'audio à transcrire · ≈ 0.00 € » : le texte et le montant, sur une ligne."""
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.XS)
        texte = libelle("", "legende", retour_a_la_ligne=False)
        ligne.addWidget(texte)
        cout = MontantLabel(0)
        cout.setProperty("role", "legende")
        ligne.addWidget(cout)
        ligne.addStretch(1)
        texte.ligne = ligne
        return texte, cout

    def _ligne_decalage(self) -> QWidget:
        """« La voix commence à » : le moment de la vidéo où commence la voix des sous-titres (le nom à
        gauche : se lit comme une phrase, V3.1, §9.4 ter)."""
        zone = QWidget()
        ligne = QHBoxLayout(zone)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.M)
        texte = libelle("La voix commence à", "legende", retour_a_la_ligne=False)
        aide = BoutonInfo(
            "Les mots ne viennent pas du même enregistrement que la vidéo (ex. les sous-titres d'une prise sur ton "
            "montage) : le moment de la vidéo où la voix commence. Il vaut aussi pour les exports."
        )
        ligne.addLayout(ligne_avec_aide(texte, aide, fin=False))
        self.decalage = champ_decimal(0.0, DECALAGE_MAX_S, 0.1, 1, " s", "Moment de la vidéo où la voix commence")
        self.decalage.valueChanged.connect(lambda valeur: self.decalage_change.emit(round(valeur, 2)))
        ligne.addWidget(self.decalage)
        ligne.addStretch(1)
        return zone

    # --- Affichage ---------------------------------------------------------------------------

    def afficher(self, etat: EtatSource) -> None:
        """Montre l'état calculé par la page (sans rien redemander : les signaux sont bloqués)."""
        for element in (self.choix_video, self.choix_mots, self.son_video, self.decalage):
            element.blockSignals(True)
        self.choix_video.definir(etat.video)
        self.choix_mots.definir(etat.mots)
        self.son_video.setChecked(etat.son_de_la_video)
        self.decalage.setValue(etat.decalage_s)
        for element in (self.choix_video, self.choix_mots, self.son_video, self.decalage):
            element.blockSignals(False)
        module = etat.video == SOURCE_TRANSCRIPTION
        self.texte_video.setText(etat.texte_video)
        self.bouton_importer.setVisible(module)
        self.bouton_importer.setText("Changer de source…" if etat.module_a_une_source else "Choisir une vidéo ou un audio…")
        self.bouton_choisir_video.setVisible(not module)
        self.bouton_choisir_video.setText("Changer de vidéo…" if etat.video_importee else "Choisir une vidéo…")
        self.bouton_retirer_video.setVisible(not module and etat.video_importee)
        # Décoché, la voix des mots remplace le son de la vidéo : sans voix (fichier SRT), rien à choisir.
        self.zone_son_video.setVisible(not module and etat.video_importee and etat.voix_des_mots)
        self.texte_mots.setText(etat.texte_mots)
        self.bouton_corriger.setVisible(etat.corriger)
        self.zone_transcrire.setVisible(etat.mots == SOURCE_TRANSCRIPTION and etat.transcrire)
        self.zone_importes.setVisible(etat.mots == SOURCE_IMPORTEE)
        self.ligne_decalage.setVisible(etat.voix_a_caler)

    def afficher_statut(self, message: str, role: str) -> None:
        """Message d'état sous le bloc ; sans message, la ligne disparaît. Vert, rouge ou orange :
        effacé après 8 s (V3.2)."""
        afficher_message(self.statut, message, role)
