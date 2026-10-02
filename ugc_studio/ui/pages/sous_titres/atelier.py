"""Atelier des sous-titres (§7, §3.3, §8.1) : des mots horodatés au fichier SRT, dans un studio.

1. Mots : ceux de la transcription du projet (vidéo transcrite dans le module Transcription), ou
   ceux d'une prise de voix : « Créer les sous-titres » transcrit la prise puis cale les mots sur
   son script (orthographe exacte). Les mots se corrigent dans le module Transcription.
2. Studio (V2, lot 3) : l'aperçu fidèle à gauche (apercu.py : la vidéo, ou un fond gris ou un
   damier, et les sous-titres dessinés par le moteur de dessin, le même que l'export de la V3), les
   réglages à droite (reglages.py : Texte, Position, Découpage, Écran). Les sous-titres sont
   recalculés à chaque changement ; la position (haut, centre, bas, réglage fin) ne change que
   l'aperçu, jamais le découpage.
3. Sous-titres : la liste ; ceux où un mot a dû être rapetissé sont signalés en orange.
4. Réorganiser à la main (V1.1) : sur le sous-titre choisi, monter son premier mot, descendre son
   dernier mot, le couper, le fusionner avec le suivant, ou revenir au découpage automatique. Les
   réglages du découpage s'appliquent toujours (une action qui ne les respecte pas est refusée,
   avec la raison) ; un réglage qui défait un ajustement demande d'abord (sous_titres_du_projet.py).
5. Frise (V2, lot 7, composants/frise.py) : sous le studio, un bloc par sous-titre et un trait par
   mot ; un clic place la lecture ou choisit un sous-titre (synchronisé avec la liste), le bord
   commun de deux sous-titres se glisse de mot en mot (mêmes règles qu'au point 4), un double-clic
   corrige les mots du sous-titre dans le module Transcription.
6. Préréglages (V2, lot 7, prereglages.py) : en haut des réglages, le préréglage d'origine du projet
   (« (modifié) » quand son style s'en écarte) ; en choisir un l'applique (avec la question de la
   1.1.0 s'il défait un ajustement), « Enregistrer… » en crée un, le menu ⋯ met à jour, revient au
   préréglage ou ouvre la fenêtre « Préréglages de sous-titres ».
7. Exporter (V3) : la vidéo avec ses sous-titres incrustés (lot 2 ; projet avec une vidéo), le
   calque transparent (MOV, ProRes 4444) à poser sur le montage dans Premiere Pro, tous deux
   dessinés par le moteur de l'aperçu (fenêtre d'export : réglages, résumé, avancement), et le
   fichier SRT.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QInputDialog, QMenu, QMessageBox, QTableWidgetItem, QVBoxLayout

from ....alignement import mots_du_script_accentues
from ....chemins import dossier_documents
from ....exports.plan import SousTitresAExporter, source_du_projet
from ....fournisseurs.stt import MODE_VERBATIM
from ....mise_en_page import limites_du_reglage_fin
from ....modeles_charges import SOUS_TITRES
from ....prereglages import appliquer as appliquer_le_prereglage
from ....prereglages import modifie, style_du_projet
from ....projets import FICHIER_AUDIO, ErreurProjet, Projet, nom_de_dossier
from ....rendu.moteur import Moteur
from ....rendu.polices import NOMS_GRAISSES, police_remplacee
from ....script import texte_brut
from ....services import Services
from ....sous_titres import (
    ESPACE_INSECABLE,
    MotAffiche,
    Reorganisation,
    SousTitre,
    ecrire_srt,
    resolution,
    retablir_automatique,
    sous_titre_au_temps,
    texte_ajustements_defaits,
)
# Les actions à la main, calculées sans interface (même nom que les méthodes de la page qui les appellent).
from ....sous_titres import couper_avant as calcul_couper
from ....sous_titres import deplacer_la_limite as calcul_limite
from ....sous_titres import descendre_dernier_mot as calcul_descendre
from ....sous_titres import fusionner_avec_le_suivant as calcul_fusionner
from ....sous_titres import monter_premier_mot as calcul_monter
from ....stt import (
    MODELE_PAR_DEFAUT,
    Options,
    estimer_cout,
    terminer_transcription,
    transcription_de_prise,
    transcrire_source,
)
from ....style_sous_titres import VideoApercu
from ....transcription import Transcription, resolution_video
from ... import taches
from ...composants.apercu import LecteurApercu
from ...composants.choix_voix import choisir
from ...composants.elements import bloc, bouton, info, libelle, liste_deroulante, minutes_secondes
from ...composants.flux import DispositionFlux
from ...composants.frise import FriseSousTitres
from ...composants.montant_label import MontantLabel
from ...composants.tableau import Colonne, Tableau
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues.export import DialogueExportCalque, DialogueExportVideo
from ...dialogues.prereglages import DialoguePrereglages
from ...extraction import FILTRE_FICHIERS, LecteurInfos
from ...sous_titres_du_projet import (
    Calcul,
    a_sa_video,
    ajustements,
    calculer as calculer_du_projet,
    confirmer_reglage,
    ranger_ajustements,
    resolution_imposee,
    script_de_la_prise,
)
from ...theme import Couleurs, Dimensions, Espacements, qcolor
from ..base import Page
from ..transcription.atelier import description_source
from .apercu import BlocApercu, DispositionStudio
from .reglages import PanneauReglages

journal = logging.getLogger(__name__)

TITRE = "Sous-titres"
SOUS_TITRE = "Studio des sous-titres : aperçu sur la vidéo, réglages, découpage et export SRT."
# Le texte d'un sous-titre garde ses 2 lignes (sa vraie mise en page) ; les autres cases tiennent
# sur une ligne (voir composants/tableau.py).
COLONNES = (
    Colonne("N°", a_droite=True),
    Colonne("Temps"),
    Colonne("Texte", texte=True, etiree=True),
    Colonne("Remarque", texte=True),
)
COLONNE_TEXTE = 2
COLONNE_REMARQUE = 3
DELAI_ENREGISTREMENT_POSITION_MS = 400  # réglage fin : enregistré quand la glissière s'arrête
FILTRE_VIDEOS = "Vidéos (*.mp4 *.mov *.mkv *.m4v *.webm *.avi)"


def temps_lisible(secondes: float) -> str:
    """72.25 → « 1:12,25 »."""
    minutes, reste = divmod(max(0.0, secondes), 60)
    return f"{int(minutes)}:{reste:05.2f}".replace(".", ",")


def remarque(sous_titre: SousTitre) -> str:
    remarques = []
    if sous_titre.trop_large:
        remarques.append("Trop large, même réduit : raccourcis ce mot")
    elif sous_titre.echelle < 1:
        remarques.append(f"Mot rapetissé à {round(sous_titre.echelle * 100)} %")
    if sous_titre.ajuste:
        remarques.append("Ajusté à la main")
    return "  ·  ".join(remarques)


class AtelierSousTitres(Page):
    # « Corriger les mots » : ouvrir le module Transcription, sur le mot qui commence à ce moment
    # (double-clic sur un bloc de la frise) ; -1 : sans choisir de mot.
    corriger_demande = Signal(float)

    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="sous-titres")
        self._services = services
        self._projet: Projet | None = None
        self._occupe = False
        self.mots: list[MotAffiche] = []
        self.sous_titres: list[SousTitre] = []
        self._calcul: Calcul | None = None
        self._debuts: list[float] = []
        self.lecteur = LecteurApercu(self)
        self._infos_video = LecteurInfos(self)  # résolution d'une vidéo choisie pour l'aperçu
        self._infos_video.pretes.connect(self._infos_video_lues)
        self._enregistrement_position = QTimer(self)
        self._enregistrement_position.setSingleShot(True)
        self._enregistrement_position.setInterval(DELAI_ENREGISTREMENT_POSITION_MS)
        self._enregistrement_position.timeout.connect(self._services.projets.enregistrer)

        self.contenu.addWidget(self._bloc_mots())

        # --- Studio : aperçu et réglages ---
        self.bloc_apercu = BlocApercu(services.preferences)
        self.toile = self.bloc_apercu.toile
        self.toile.glissable = True  # le sous-titre se glisse verticalement dans l'aperçu
        cadre_reglages, d = bloc("Réglages")
        self.panneau = PanneauReglages()
        d.addWidget(self.panneau)
        self.studio = DispositionStudio(self.bloc_apercu, cadre_reglages)
        self.contenu.addWidget(self.studio)
        self.contenu.addWidget(self._bloc_frise())
        # Raccourcis vers les réglages (tests, autotest).
        panneau = self.panneau
        self.caracteres, self.mots_max, self.lignes, self.duree_min = panneau.caracteres, panneau.mots_max, panneau.lignes, panneau.duree_min
        self.taille, self.casse, self.ponctuation = panneau.texte.taille.champ, panneau.texte.casse, panneau.texte.ponctuation
        self.couper_ponctuation = panneau.couper_ponctuation
        self.format, self.plateforme, self.marge, self.masquer = panneau.format, panneau.plateforme, panneau.marge, panneau.masquer
        self.infos_ecran = panneau.infos_ecran

        # --- Sous-titres ---
        self.cadre_sous_titres, d = bloc("Sous-titres")
        self.resume = libelle("", "legende")
        d.addWidget(self.resume)
        self._zone_reorganiser(d)
        self.tableau = self._tableau()
        d.addWidget(self.tableau)
        self._actualiser_reorganisation()  # aucun sous-titre choisi : actions désactivées
        self.statut_lecture = libelle("", "secondaire")  # lecture impossible dans l'aperçu
        self.statut_lecture.hide()
        d.addWidget(self.statut_lecture)
        self.contenu.addWidget(self.cadre_sous_titres)
        self.contenu.addWidget(self._bloc_export())

        self._brancher()
        services.prereglages.abonner(self._actualiser_prereglage)  # renommé, supprimé, mis à jour…
        services.projets.abonner(self._projet_change)
        services.prix.abonner(self._mettre_a_jour_estimation)
        self._projet_change(services.projets.projet)

    # --- Construction ------------------------------------------------------------------------

    def _bloc_mots(self):
        cadre, d = bloc("Mots des sous-titres")
        self.texte_source = libelle("", "secondaire")
        d.addWidget(self.texte_source)
        ligne = QHBoxLayout()
        self.bouton_corriger = bouton(
            "Corriger les mots", variante="contour", nom_icone="pencil", action=lambda: self.corriger_demande.emit(-1.0)
        )
        self.bouton_corriger.setToolTip("Corriger un mot ou son moment dans le module Transcription")
        ligne.addWidget(self.bouton_corriger)
        ligne.addStretch(1)
        d.addLayout(ligne)
        d.addWidget(
            info(
                "Depuis une voix générée : la prise est transcrite (moment de chaque mot), puis calée sur son "
                "script, dont l'orthographe exacte est gardée. Pour une vidéo, passe par le module Transcription.",
                "legende",
            )
        )
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.prises = liste_deroulante("Prise dont créer les sous-titres")
        self.prises.currentIndexChanged.connect(lambda _index: self._mettre_a_jour_estimation())
        ligne.addWidget(self.prises, 1)
        self.bouton_creer = bouton(
            "Créer les sous-titres", variante="principal", nom_icone="captions", action=self.creer_depuis_la_prise_choisie
        )
        ligne.addWidget(self.bouton_creer)
        d.addLayout(ligne)
        estimation = QHBoxLayout()
        estimation.setSpacing(Espacements.XS)
        self.estimation = libelle("", "legende", retour_a_la_ligne=False)
        estimation.addWidget(self.estimation)
        self.cout_estime = MontantLabel(0)
        self.cout_estime.setProperty("role", "legende")
        estimation.addWidget(self.cout_estime)
        estimation.addStretch(1)
        d.addLayout(estimation)
        self.statut = libelle("", "secondaire")
        self.statut.hide()
        d.addWidget(self.statut)
        return cadre

    def _bloc_frise(self):
        """Frise des sous-titres (V2, lot 7), sur toute la largeur, sous l'aperçu et les réglages."""
        self.cadre_frise, d = bloc("Frise")
        d.addWidget(
            info(
                "Clic : aller à ce moment, ou choisir un sous-titre. Glisse le bord commun de deux sous-titres : "
                "des mots passent de l'un à l'autre. Double-clic : corriger ses mots. Ctrl + molette : zoom.",
                "legende",
            )
        )
        self.frise = FriseSousTitres()
        d.addWidget(self.frise)
        self.statut_frise = libelle("", "secondaire")
        self.statut_frise.hide()
        d.addWidget(self.statut_frise)
        return self.cadre_frise

    def _bloc_export(self):
        """Exporter (V3) : la vidéo avec sous-titres (bouton principal), le calque transparent pour
        Premiere Pro, et le fichier SRT. Chaque export vidéo passe par sa fenêtre (réglages, résumé
        avant export, avancement)."""
        self.cadre_export, d = bloc("Exporter")
        d.addWidget(
            info(
                "Vidéo avec sous-titres : ta vidéo, sous-titres incrustés, prête à publier. Calque transparent : "
                "les sous-titres seuls, à poser au-dessus de ton montage dans Premiere Pro. Fichier SRT : le texte "
                "et le moment de chaque sous-titre, sans style.",
                "legende",
            )
        )
        boutons = DispositionFlux(espacement=Espacements.S)  # passe à la ligne si la fenêtre est étroite
        self.bouton_video = bouton("Vidéo avec sous-titres…", variante="principal", nom_icone="clapperboard", action=self.exporter_video)
        self.bouton_video.setToolTip("MP4, MOV ou MKV : ta vidéo et ses sous-titres, chaque image à son moment exact")
        boutons.addWidget(self.bouton_video)
        self.bouton_calque = bouton("Calque transparent…", nom_icone="film", action=self.exporter_calque)
        self.bouton_calque.setToolTip("MOV, ProRes 4444 avec transparence, à la taille et aux images de ta vidéo")
        boutons.addWidget(self.bouton_calque)
        self.bouton_exporter = bouton("Fichier SRT…", variante="contour", nom_icone="download", action=self.exporter_srt)
        self.bouton_exporter.setToolTip("Texte et temps de chaque sous-titre, sans style : pour Premiere Pro et la plupart des logiciels")
        boutons.addWidget(self.bouton_exporter)
        d.addLayout(boutons)
        # Grisé sans vidéo (sous-titres d'une voix, d'un audio) : l'explication est dessous.
        self.info_video = info(
            "Vidéo avec sous-titres : seulement pour une vidéo importée dans le module Transcription. Ici, "
            "exporte le calque transparent et pose-le sur ton montage.",
            "legende",
        )
        self.info_video.hide()
        d.addWidget(self.info_video)
        self.statut_export = libelle("", "secondaire")
        self.statut_export.hide()
        d.addWidget(self.statut_export)
        return self.cadre_export

    def _brancher(self) -> None:
        panneau, apercu, lecteur = self.panneau, self.bloc_apercu, self.lecteur
        panneau.change.connect(self._reglage_change)
        panneau.position_change.connect(self._position_change)
        panneau.masquer_change.connect(self._masquer_change)
        panneau.choisir_video_demande.connect(self.choisir_video_apercu)
        panneau.retirer_video_demande.connect(self.retirer_video_apercu)
        panneau.video_apercu_change.connect(self._video_apercu_change)
        panneau.texte.pipette_demandee.connect(self.prendre_une_couleur)
        panneau.mots.pipette_demandee.connect(self.prendre_une_couleur)
        panneau.prereglage_choisi.connect(self.appliquer_prereglage)
        panneau.enregistrer_prereglage_demande.connect(self.enregistrer_prereglage)
        panneau.mettre_a_jour_prereglage_demande.connect(self.mettre_a_jour_prereglage)
        panneau.revenir_au_prereglage_demande.connect(self.revenir_au_prereglage)
        panneau.gerer_prereglages_demande.connect(self.gerer_prereglages)
        apercu.bouton_lecture.clicked.connect(self.basculer_lecture)
        apercu.position.sliderMoved.connect(lecteur.aller_a_position)
        apercu.bouton_boucle.toggled.connect(lambda _coche: self._actualiser_boucle())
        apercu.bouton_retrouver.clicked.connect(self.retrouver_la_video)
        self.toile.glissement.connect(panneau.montrer_reglage_fin)
        self.toile.glissement_fini.connect(self._position_glissee)
        lecteur.image.connect(self.toile.definir_image)
        lecteur.temps_change.connect(self._temps_lu)
        lecteur.position_change.connect(self._position_lue)
        lecteur.etat_change.connect(apercu.definir_lecture)
        lecteur.erreur.connect(self._erreur_de_lecture)
        frise = self.frise.toile
        frise.temps_demande.connect(self._aller_a)
        frise.sous_titre_clique.connect(self.choisir_sous_titre)
        frise.correction_demandee.connect(self._corriger_le_sous_titre)
        frise.limite_deplacee.connect(self.deplacer_la_limite)
        frise.definir_verification(self._verifier_la_limite)

    def _zone_reorganiser(self, d: QVBoxLayout) -> None:
        """« Réorganiser à la main » : les actions sur le sous-titre choisi dans la liste."""
        self.titre_reorganiser = libelle("Réorganiser à la main", "intitule")
        d.addWidget(self.titre_reorganiser)
        d.addWidget(
            info(
                "Choisis un sous-titre dans la liste. Le moment des mots ne change jamais, et les réglages du "
                "découpage s'appliquent toujours.",
                "legende",
            )
        )
        actions = DispositionFlux(espacement=Espacements.S)  # passe à la ligne si la fenêtre est étroite
        self.bouton_monter = bouton(
            "Monter le premier mot", variante="contour", nom_icone="arrow-up", action=self.monter_premier_mot
        )
        self.bouton_descendre = bouton(
            "Descendre le dernier mot", variante="contour", nom_icone="arrow-down", action=self.descendre_dernier_mot
        )
        self.bouton_couper = bouton("Couper", variante="contour", nom_icone="scissors")
        self.menu_couper = QMenu(self.bouton_couper)
        self.menu_couper.aboutToShow.connect(self._remplir_menu_couper)  # les mots du sous-titre choisi
        self.bouton_couper.setMenu(self.menu_couper)
        self.bouton_fusionner = bouton(
            "Fusionner avec le suivant", variante="contour", nom_icone="list-plus", action=self.fusionner_avec_le_suivant
        )
        self.bouton_retablir = bouton("Rétablir", variante="contour", nom_icone="rotate-ccw")
        self.bouton_retablir.setToolTip("Revenir au découpage automatique")
        menu = QMenu(self.bouton_retablir)
        self.action_retablir = menu.addAction("Rétablir le découpage automatique de ce sous-titre")
        self.action_retablir.triggered.connect(lambda: self.retablir(tous=False))
        self.action_retablir_tous = menu.addAction("Rétablir le découpage automatique de tous les sous-titres")
        self.action_retablir_tous.triggered.connect(lambda: self.retablir(tous=True))
        self.bouton_retablir.setMenu(menu)
        for element in (self.bouton_monter, self.bouton_descendre, self.bouton_couper, self.bouton_fusionner, self.bouton_retablir):
            actions.addWidget(element)
        d.addLayout(actions)
        self.statut_ajustements = libelle("", "secondaire")
        self.statut_ajustements.hide()
        d.addWidget(self.statut_ajustements)

    def _tableau(self) -> Tableau:
        tableau = Tableau(COLONNES)
        tableau.setMinimumHeight(Dimensions.TABLEAU_HAUTEUR_MIN)
        tableau.cellClicked.connect(lambda rang, _colonne: self.choisir_sous_titre(rang))
        return tableau

    # --- Projet ------------------------------------------------------------------------------

    @property
    def transcription(self) -> Transcription | None:
        return self._projet.transcription if self._projet else None

    def _projet_change(self, projet: Projet | None) -> None:
        self._enregistrement_position.stop()
        self.lecteur.arreter()
        self._projet = projet
        if projet is None:
            self._services.modeles.choisir(SOUS_TITRES, None)
            return
        self.titre.setText(f"{TITRE} / {projet.nom}")
        self._afficher("", "secondaire")
        self._afficher("", "secondaire", self.statut_export)
        self._afficher("", "secondaire", self.statut_lecture)
        self._statut_reorganisation("")
        self.rafraichir()

    def showEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # Les mots ou les prises ont pu changer dans un autre module.
        super().showEvent(evenement)
        if self._projet is not None and not self._occupe:
            self.rafraichir()

    def prendre_une_couleur(self, champ) -> None:
        """Pipette d'un champ couleur (§7.4) : l'aperçu attend un clic. Quand la page est étroite (aperçu
        au-dessus des réglages), elle défile jusqu'à l'aperçu."""
        self.toile.commencer_pipette(champ.couleur_prise)
        if not self.studio.deux_colonnes:
            self.defilement.ensureWidgetVisible(self.bloc_apercu.zone)

    def keyPressEvent(self, evenement) -> None:  # noqa: N802
        """Barre Espace : lecture ou pause (quand aucun bouton ni case n'a la main)."""
        if evenement.key() == Qt.Key.Key_Space and not evenement.isAutoRepeat():
            self.basculer_lecture()
            return
        super().keyPressEvent(evenement)

    def _afficher(self, message: str, role: str, etiquette=None) -> None:
        """Message d'état sous un bloc ; sans message, la ligne disparaît (pas de vide en bas du bloc)."""
        etiquette = etiquette or self.statut
        etiquette.setText(message)
        etiquette.setVisible(bool(message))
        etiquette.setProperty("role", role)
        etiquette.style().unpolish(etiquette)
        etiquette.style().polish(etiquette)

    # --- Affichage ---------------------------------------------------------------------------

    def rafraichir(self) -> None:
        """Met toute la page à jour : source des mots, prises, réglages, sous-titres, lecture."""
        # Réglages → Modèles et prix, « Utilisé dans » : le modèle qui transcrit une prise.
        self._services.modeles.choisir(SOUS_TITRES, self._modele() if self._projet else None)
        if self._projet is None:
            return
        transcription = self.transcription
        if transcription is not None and transcription.horodatee:
            self.texte_source.setText(f"{description_source(transcription)}  ·  {len(transcription.mots)} mots")
        elif transcription is not None and transcription.texte:
            self.texte_source.setText("La transcription du projet est en texte seul (sans le moment de chaque mot) : pas de sous-titres possibles.")
        else:
            self.texte_source.setText("Pas encore de mots : crée les sous-titres d'une prise ci-dessous, ou transcris une vidéo.")
        self.bouton_corriger.setVisible(bool(transcription and transcription.horodatee))
        self._remplir_prises()
        self._charger_reglages()
        self.calculer()
        self._charger_la_lecture()
        if self.sous_titres and self.lecteur.temps < self.sous_titres[0].debut:
            self._au_debut()  # avant le premier sous-titre : l'aperçu montre le premier

    def _remplir_prises(self) -> None:
        projet, actuel = self._projet, self.prises.currentData()
        self.prises.blockSignals(True)
        self.prises.clear()
        for prise in reversed(projet.prises):
            self.prises.addItem(f"{prise.nom}  ·  {minutes_secondes(prise.duree_s)}", prise.identifiant)
        if not projet.prises:
            self.prises.addItem("Aucune prise : génère d'abord une voix (module Voix)", None)
        transcription = self.transcription
        choisir(self.prises, actuel or (transcription.prise if transcription else ""))
        self.prises.setEnabled(bool(projet.prises))
        self.prises.blockSignals(False)
        self.bouton_creer.setEnabled(bool(projet.prises) and not self._occupe)
        self._mettre_a_jour_estimation()

    def _mettre_a_jour_estimation(self) -> None:
        identifiant = self.prises.currentData()
        prise = next((p for p in self._projet.prises if p.identifiant == identifiant), None) if self._projet else None
        self.estimation.setText(f"≈ {minutes_secondes(prise.duree_s)} d'audio à transcrire  ·  ≈" if prise else "")
        self.cout_estime.setVisible(prise is not None)
        if prise is not None:
            cout = estimer_cout(prise.duree_s, self._modele(), self._services.prix)
            if cout is None:
                self.cout_estime.setText("prix inconnu")
            else:
                self.cout_estime.definir_montant(cout)

    def _charger_reglages(self) -> None:
        transcription, reglages = self.transcription, self._projet.sous_titres
        imposee = resolution_imposee(self._projet)
        self.panneau.charger(
            reglages,
            imposee,
            transcription.masquer_hesitations if transcription else True,
            transcription is not None,
            a_sa_video(transcription),
            resolution(reglages, imposee)[1],
            police_remplacee(reglages.texte),
            self._accentues_du_script(),
        )
        self._actualiser_prereglage()

    def _accentues_du_script(self) -> int | None:
        """Mots accentués dans le script de la prise des sous-titres (None : pas une prise)."""
        script = script_de_la_prise(self._projet, self.transcription)
        if script is None:
            return None
        return sum(1 for _texte, accentue in mots_du_script_accentues(script) if accentue)

    def reglages(self):
        """Réglages tels que choisis dans la page."""
        return self.panneau.reglages(self._projet.sous_titres)

    def _reglage_change(self) -> None:
        if self._projet is None:
            return
        reglages = self.reglages()
        # Un réglage qui défait un sous-titre réorganisé à la main demande d'abord (V1.1).
        if not confirmer_reglage(self.window(), self._services, self._projet, reglages=reglages):
            self._charger_reglages()  # « Garder le réglage actuel » : les champs reprennent leur valeur
            return
        self._projet.sous_titres = reglages
        self._services.projets.enregistrer()
        self._charger_reglages()  # format personnalisé affiché ou caché, limites du réglage fin…
        self.calculer()

    def _position_change(self) -> None:
        """Haut, centre ou bas, réglage fin : seul l'aperçu change (jamais le découpage)."""
        if self._projet is None or self._calcul is None:
            return
        reglages = replace(self._projet.sous_titres, position=self.reglages().position)
        self._projet.sous_titres = reglages
        self._calcul.reglages = reglages
        moteur = self._calcul.moteur
        self._calcul.moteur = Moteur(reglages, moteur.largeur, moteur.hauteur)
        self._actualiser_limites()
        self.toile.definir(self._calcul.moteur, self.mots)
        self._actualiser_toile()
        self._actualiser_prereglage()  # la position fait partie du style : « (modifié) »
        self._enregistrement_position.start()

    def _position_glissee(self, decalage: float) -> None:
        """Sous-titre glissé dans l'aperçu : le réglage fin prend la nouvelle valeur."""
        self.panneau.montrer_reglage_fin(decalage)
        self._position_change()

    def _masquer_change(self, masquer: bool) -> None:
        transcription = self.transcription
        if transcription is None:
            return
        if not confirmer_reglage(self.window(), self._services, self._projet, masquer=masquer):
            self._charger_reglages()
            return
        transcription.masquer_hesitations = masquer
        self._services.projets.enregistrer()
        self.calculer()

    def calculer(self) -> None:
        """(Re)calcule les sous-titres d'après les mots, les réglages et les sous-titres réorganisés
        à la main, puis les affiche (liste et aperçu)."""
        calcul = calculer_du_projet(self._services, self._projet)
        self._calcul = calcul
        self.mots, self.sous_titres = calcul.decoupage.mots, calcul.decoupage.sous_titres
        self._debuts = [s.debut for s in self.sous_titres]
        if calcul.decoupage.defaits:
            self._retirer_les_ajustements_defaits(calcul)
        ecran_video, langue, moteur = calcul.ecran, calcul.langue, calcul.moteur
        typographie = " ; typographie française : espace insécable avant « ! ? : ; »" if langue.startswith("fr") else ""
        style = calcul.reglages.texte
        police_utilisee = "Inter" if moteur.police_remplacee else style.police
        self.infos_ecran.setText(
            f"Vidéo {ecran_video.largeur} × {ecran_video.hauteur}, texte de {moteur.taille_px} px ({police_utilisee} "
            f"{NOMS_GRAISSES.get(style.graisse, style.graisse)}) : "
            f"une ligne tient en {round(ecran_video.largeur_securite)} px dans la zone de sécurité, "
            f"{round(ecran_video.largeur_max)} px au plus jusqu'à la marge maximum{typographie}."
        )
        self.panneau.texte.taille_px.setText(f"{moteur.taille_px} px")
        self._actualiser_limites()
        self.toile.definir(moteur, self.mots)
        self.bloc_apercu.zone.actualiser_taille()
        self._remplir_tableau()
        transcription = self.transcription
        self.frise.toile.definir(self.sous_titres, self.mots, (transcription.duree_s or 0.0) if transcription else 0.0)
        self.frise.toile.definir_choisi(self._choisi())
        self.cadre_frise.setVisible(bool(self.sous_titres))
        self.cadre_sous_titres.setVisible(bool(self.sous_titres))
        self.cadre_export.setVisible(bool(self.sous_titres))
        signales = sum(1 for s in self.sous_titres if s.signale)
        ajustes = sum(1 for s in self.sous_titres if s.ajuste)
        morceaux = [f"{len(self.sous_titres)} sous-titres", f"{len(self.mots)} mots"]
        if self.sous_titres:
            morceaux.append(minutes_secondes(self.sous_titres[-1].fin))
        if ajustes:
            morceaux.append(f"{ajustes} ajusté{'s' if ajustes > 1 else ''} à la main")
        if signales:
            morceaux.append(f"{signales} signalé{'s' if signales > 1 else ''} en orange (mot rapetissé pour tenir dans l'écran)")
        self.resume.setText("  ·  ".join(morceaux))
        self.bouton_exporter.setEnabled(bool(self.sous_titres))
        self.bouton_calque.setEnabled(bool(self.sous_titres))
        avec_video = self._projet is not None and source_du_projet(self._projet).video
        self.bouton_video.setEnabled(bool(self.sous_titres) and avec_video)
        self.info_video.setVisible(bool(self.sous_titres) and not avec_video)
        self._actualiser_toile()
        self._actualiser_reorganisation()
        self._actualiser_boucle()

    def _actualiser_limites(self) -> None:
        moteur = self._calcul.moteur
        bas, haut = limites_du_reglage_fin(moteur.reglages, moteur.zone, moteur.metriques)
        self.panneau.definir_limites_reglage_fin(bas, haut)

    def _retirer_les_ajustements_defaits(self, calcul: Calcul) -> None:
        """Des mots changés dans le module Transcription (texte, temps, fusion, coupe, suppression,
        hésitations) défont des sous-titres réorganisés à la main : ils sont retirés du projet (leurs
        mots sont déjà redécoupés automatiquement), et la page dit lesquels."""
        transcription = self.transcription
        defaits = calcul.decoupage.defaits
        retires = {defait.ajustement for defait in defaits}
        ranger_ajustements(transcription, [a for a in ajustements(transcription) if a not in retires])
        self._services.projets.enregistrer()
        numeros = []
        for defait in defaits:
            numero = next(
                (rang for rang, s in enumerate(self.sous_titres, 1) if s.premier_mot <= defait.premier_mot < s.dernier_mot), 0
            )
            numeros.append((numero, defait))
        self._statut_reorganisation(texte_ajustements_defaits(numeros), "avertissement")

    def _remplir_tableau(self) -> None:
        self.tableau.setRowCount(len(self.sous_titres))
        orange = QBrush(qcolor(Couleurs.AVERTISSEMENT))
        for rang, sous_titre in enumerate(self.sous_titres):
            valeurs = (
                str(rang + 1),
                f"{temps_lisible(sous_titre.debut)} → {temps_lisible(sous_titre.fin)}",
                sous_titre.texte.replace(ESPACE_INSECABLE, " "),
                remarque(sous_titre),
            )
            for colonne, texte in enumerate(valeurs):
                element = QTableWidgetItem(texte)
                if COLONNES[colonne].a_droite:
                    element.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if sous_titre.signale:
                    element.setForeground(orange)
                    element.setToolTip(
                        "Un mot seul était trop large pour l'écran : il est affiché plus petit. "
                        "Raccourcis-le, ou baisse la taille du texte."
                    )
                self.tableau.setItem(rang, colonne, element)
        self.tableau.contenu_change()

    # --- Aperçu : sous-titre affiché, sous-titre choisi ----------------------------------------

    def _actualiser_toile(self) -> None:
        """L'aperçu montre le sous-titre du moment affiché (celui de l'image de la vidéo), avec le mot
        en train d'être dit."""
        index = sous_titre_au_temps(self.sous_titres, self.lecteur.temps, self._debuts)
        self.toile.montrer(self.sous_titres[index] if index >= 0 else None)
        self.toile.definir_temps(self.lecteur.temps)
        self.frise.toile.definir_temps(self.lecteur.temps)

    def _au_debut(self) -> None:
        """Projet ouvert : l'aperçu montre le premier sous-titre (sans le choisir dans la liste)."""
        if self.sous_titres and not self.lecteur.en_lecture():
            self.lecteur.aller_a(self.sous_titres[0].debut)

    def _temps_lu(self, _temps: float) -> None:
        self._actualiser_toile()
        if not self.lecteur.en_lecture():
            return
        index = sous_titre_au_temps(self.sous_titres, self.lecteur.temps, self._debuts)
        if index >= 0 and index != self.tableau.currentRow() and not self.bloc_apercu.bouton_boucle.isChecked():
            self.tableau.selectRow(index)
            self.tableau.scrollToItem(self.tableau.item(index, 0))
            self.frise.toile.definir_choisi(index)
            self._actualiser_reorganisation()

    def _position_lue(self, position_ms: int, duree_ms: int) -> None:
        apercu = self.bloc_apercu
        if not apercu.position.isSliderDown():
            apercu.position.setRange(0, max(duree_ms, 0))
            apercu.position.setValue(position_ms)
        apercu.temps.setText(f"{minutes_secondes(position_ms / 1000)} / {minutes_secondes(duree_ms / 1000)}")

    def choisir_sous_titre(self, index: int, temps: float | None = None) -> None:
        """Clic sur un sous-titre (liste ou frise) : il est choisi dans les deux, et l'aperçu (la
        lecture) se place sur lui : à son début, ou au moment cliqué dans la frise."""
        if not 0 <= index < len(self.sous_titres):
            return
        self.tableau.selectRow(index)
        self.frise.toile.definir_choisi(index)
        self._actualiser_reorganisation()
        self._actualiser_boucle()
        sous_titre = self.sous_titres[index]
        self.lecteur.aller_a(sous_titre.debut if temps is None else min(max(temps, sous_titre.debut), sous_titre.fin))
        self._actualiser_toile()

    def _aller_a(self, temps: float) -> None:
        """Clic dans la frise, hors d'un bloc : la lecture va à ce moment."""
        self.lecteur.aller_a(temps)
        self._actualiser_toile()

    def _actualiser_boucle(self) -> None:
        index = self._choisi()
        if self.bloc_apercu.bouton_boucle.isChecked() and index >= 0:
            self.lecteur.definir_boucle(self.sous_titres[index].debut, self.sous_titres[index].fin)
        else:
            self.lecteur.definir_boucle(None)

    # --- Lecture -----------------------------------------------------------------------------

    def _chemin_audio(self) -> Path | None:
        transcription = self.transcription
        if self._projet is None or transcription is None or not transcription.audio:
            return None
        return self._projet.chemin(transcription.audio)

    def _charger_la_lecture(self) -> None:
        """Ce que lit l'aperçu : la vidéo transcrite (avec son son) ; sinon la piste son des
        sous-titres (prise), sous la vidéo choisie pour l'aperçu s'il y en a une. Une vidéo
        introuvable (déplacée, supprimée) laisse le fond gris et propose de la retrouver."""
        transcription, reglages = self.transcription, self._projet.sous_titres
        audio = self._chemin_audio()
        audio = str(audio) if audio is not None and audio.exists() else ""
        video, decalage, son_de_la_video, introuvable = "", 0.0, True, ""
        if a_sa_video(transcription):
            if Path(transcription.source).is_file():
                video, audio = transcription.source, ""
            else:
                introuvable = transcription.source
        elif reglages.apercu.chemin:
            if Path(reglages.apercu.chemin).is_file():
                video, decalage, son_de_la_video = reglages.apercu.chemin, reglages.apercu.decalage_s, reglages.apercu.son_de_la_video
            else:
                introuvable = reglages.apercu.chemin
        if transcription is None or not transcription.horodatee:
            video = audio = ""
        if self.isVisible():  # page cachée : rien n'est ouvert (la lecture se prépare à son affichage)
            self.lecteur.charger(video, audio, decalage, son_de_la_video)
        self.bloc_apercu.definir_video_possible(bool(video))
        self.bloc_apercu.ligne_introuvable.setVisible(bool(introuvable))
        if introuvable:
            self.bloc_apercu.message_video.setText(
                f"Vidéo introuvable : {introuvable}. Elle a peut-être été déplacée ou supprimée "
                "(elle n'est pas copiée dans le projet) : l'aperçu montre un fond gris."
            )
        self._actualiser_toile()

    def basculer_lecture(self) -> None:
        if not self.sous_titres:
            return
        self.lecteur.basculer()

    def _erreur_de_lecture(self, message: str) -> None:
        self._afficher(f"Lecture impossible dans l'aperçu : {message}", "erreur", self.statut_lecture)
        self.bloc_apercu.definir_video_possible(False)

    def quitter(self) -> None:
        """La page n'est plus affichée : la lecture s'arrête (et libère les fichiers)."""
        self.lecteur.arreter()

    # --- Préréglages (V2, lot 7) ----------------------------------------------------------------

    def _actualiser_prereglage(self) -> None:
        """Liste des préréglages, avec celui du projet (« (modifié) » s'il s'en écarte) ; « Rétablir »
        de l'onglet Texte remet les valeurs de ce préréglage."""
        if self._projet is None:
            return
        bibliotheque, reglages = self._services.prereglages, self._projet.sous_titres
        origine = bibliotheque.prereglage(reglages.prereglage)
        self.panneau.definir_prereglages(
            bibliotheque.prereglages,
            reglages.prereglage,
            reglages.prereglage_nom,
            origine is not None and modifie(reglages, origine),
        )
        texte = appliquer_le_prereglage(reglages, origine).texte if origine is not None else None
        self.panneau.texte.definir_reference(texte)

    def _statut_prereglage(self, message: str, role: str = "succes") -> None:
        self._afficher(message, role, self.panneau.statut_prereglage)

    def _demander_nom(self, titre: str, nom: str) -> str | None:
        """Nom d'un nouveau préréglage (remplacé dans les tests)."""
        texte, ok = QInputDialog.getText(self.window(), titre, "Nom du préréglage :", text=nom)
        return texte if ok and texte.strip() else None

    def appliquer_prereglage(self, identifiant: str) -> None:
        """Le style du préréglage remplace celui du projet (format, plateforme et vidéo d'aperçu ne
        changent pas). S'il défait un ajustement fait à la main, la question de la 1.1.0 vient d'abord."""
        prereglage = self._services.prereglages.prereglage(identifiant)
        if self._projet is None or prereglage is None:
            return
        reglages = appliquer_le_prereglage(self._projet.sous_titres, prereglage)
        if not confirmer_reglage(self.window(), self._services, self._projet, reglages=reglages):
            self._charger_reglages()  # « Garder le réglage actuel » : la liste revient au préréglage du projet
            return
        self._projet.sous_titres = reglages
        self._services.projets.enregistrer()
        self._charger_reglages()
        self.calculer()
        self._statut_prereglage(f"Préréglage « {prereglage.nom} » appliqué.")

    def revenir_au_prereglage(self) -> None:
        """Menu ⋯ : le style du projet redevient celui de son préréglage d'origine."""
        if self._projet is not None:
            self.appliquer_prereglage(self._projet.sous_titres.prereglage)

    def enregistrer_prereglage(self) -> None:
        """« Enregistrer… » : le style du projet devient un nouveau préréglage (et celui du projet)."""
        if self._projet is None:
            return
        bibliotheque = self._services.prereglages
        reglages = self._projet.sous_titres
        proposition = bibliotheque.nom_libre(f"{reglages.prereglage_nom} (perso)" if reglages.prereglage_nom else "Mon style")
        nom = self._demander_nom("Enregistrer comme nouveau préréglage", proposition)
        if nom is None:
            return
        cree = bibliotheque.ajouter(nom, style_du_projet(reglages))
        self._projet.sous_titres = replace(reglages, prereglage=cree.identifiant, prereglage_nom=cree.nom)
        self._services.projets.enregistrer()
        self._actualiser_prereglage()
        self._statut_prereglage(f"Préréglage « {cree.nom} » enregistré : tu le retrouves pour tes autres projets.")

    def mettre_a_jour_prereglage(self) -> None:
        """Menu ⋯ : le préréglage d'origine prend le style du projet (les autres projets gardent le leur)."""
        if self._projet is None:
            return
        bibliotheque, reglages = self._services.prereglages, self._projet.sous_titres
        origine = bibliotheque.prereglage(reglages.prereglage)
        if origine is None:
            return
        boite = QMessageBox(self.window())
        boite.setIcon(QMessageBox.Icon.Question)
        boite.setWindowTitle("Mettre à jour le préréglage")
        boite.setText(f"Mettre à jour « {origine.nom} » avec le style de ce projet ?")
        boite.setInformativeText("Les projets déjà faits gardent leur propre copie du style : ils ne changent pas.")
        oui = boite.addButton("Mettre à jour", QMessageBox.ButtonRole.AcceptRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        if not self._confirmer(boite, oui):
            return
        bibliotheque.mettre_a_jour(origine.identifiant, style_du_projet(reglages))
        self._projet.sous_titres = replace(reglages, prereglage_nom=origine.nom)
        self._services.projets.enregistrer()
        self._actualiser_prereglage()
        self._statut_prereglage(f"« {origine.nom} » mis à jour.")

    @staticmethod
    def _confirmer(boite: QMessageBox, oui) -> bool:
        """Pose la question (remplacé dans les tests)."""
        boite.exec()
        return boite.clickedButton() is oui

    def gerer_prereglages(self) -> None:
        """Menu ⋯ : la fenêtre « Préréglages de sous-titres » ; « Appliquer » y met un préréglage sur le projet."""
        actuel = self._projet.sous_titres.prereglage if self._projet is not None else ""
        fenetre = DialoguePrereglages(self._services, self.window(), actuel, projet_ouvert=self._projet is not None)
        fenetre.exec()
        if fenetre.prereglage_choisi:
            self.appliquer_prereglage(fenetre.prereglage_choisi)
        else:
            self._actualiser_prereglage()

    # --- Vidéo : retrouvée, ou choisie seulement pour l'aperçu ----------------------------------

    def _demander_video(self, titre: str, proposition: str) -> Path | None:
        dossier = str(Path(proposition).parent) if proposition else str(dossier_documents())
        choix, _ = QFileDialog.getOpenFileName(self, titre, dossier, f"{FILTRE_VIDEOS};;{FILTRE_FICHIERS}")
        return Path(choix) if choix else None

    def retrouver_la_video(self) -> None:
        """« Retrouver la vidéo… » : la vidéo du projet (ou d'aperçu) a été déplacée."""
        if self._projet is None:
            return
        transcription = self.transcription
        if a_sa_video(transcription):
            chemin = self._demander_video("Retrouver la vidéo transcrite", transcription.source)
            if chemin is None:
                return
            transcription.source = str(chemin)
        else:
            apercu = self._projet.sous_titres.apercu
            chemin = self._demander_video("Retrouver la vidéo d'aperçu", apercu.chemin)
            if chemin is None:
                return
            self._projet.sous_titres = replace(self._projet.sous_titres, apercu=replace(apercu, chemin=str(chemin)))
        self._services.projets.enregistrer()
        self.rafraichir()

    def choisir_video_apercu(self) -> None:
        """Projet sans vidéo : une vidéo seulement pour l'aperçu (ex. le montage exporté de Premiere)."""
        if self._projet is None:
            return
        apercu = self._projet.sous_titres.apercu
        chemin = self._demander_video("Choisir une vidéo pour l'aperçu", apercu.chemin)
        if chemin is None:
            return
        self._definir_video_apercu(VideoApercu(str(chemin), apercu.decalage_s, 0, 0, apercu.son_de_la_video))
        self._infos_video.lire(chemin)  # sa résolution fixera le format

    def _definir_video_apercu(self, apercu: VideoApercu) -> None:
        reglages = replace(self._projet.sous_titres, apercu=apercu)
        if not confirmer_reglage(self.window(), self._services, self._projet, reglages=reglages):
            return
        self._projet.sous_titres = reglages
        self._services.projets.enregistrer()
        self.rafraichir()

    def _infos_video_lues(self, infos: dict) -> None:
        """Résolution de la vidéo d'aperçu : elle impose son format (comme la vidéo d'un projet)."""
        if self._projet is None or not self._projet.sous_titres.apercu.chemin:
            return
        resolution_lue = resolution_video(infos)
        if resolution_lue is None:
            return
        apercu = self._projet.sous_titres.apercu
        self._definir_video_apercu(replace(apercu, largeur=resolution_lue[0], hauteur=resolution_lue[1]))

    def retirer_video_apercu(self) -> None:
        if self._projet is None:
            return
        self._definir_video_apercu(VideoApercu())

    def _video_apercu_change(self) -> None:
        """Décalage de la voix, ou son de la vidéo : seule la lecture change."""
        if self._projet is None:
            return
        decalage, son = self.panneau.decalage_et_son()
        apercu = replace(self._projet.sous_titres.apercu, decalage_s=decalage, son_de_la_video=son)
        self._projet.sous_titres = replace(self._projet.sous_titres, apercu=apercu)
        self._services.projets.enregistrer()
        self._charger_la_lecture()

    # --- Réorganiser à la main (V1.1) ---------------------------------------------------------

    def _statut_reorganisation(self, message: str, role: str = "secondaire") -> None:
        self._afficher(message, role, self.statut_ajustements)

    def _choisi(self) -> int:
        """Indice du sous-titre choisi dans la liste (-1 : aucun)."""
        index = self.tableau.currentRow()
        if 0 <= index < len(self.sous_titres) and self.tableau.selectionModel().isRowSelected(index):
            return index
        return -1

    def _actualiser_reorganisation(self) -> None:
        """Actions possibles sur le sous-titre choisi, avec ses vrais mots dans les infobulles."""
        index, nombre = self._choisi(), len(self.sous_titres)
        choisi = self.sous_titres[index] if index >= 0 else None
        self.bouton_monter.setEnabled(choisi is not None and index > 0)
        self.bouton_descendre.setEnabled(choisi is not None and index + 1 < nombre)
        self.bouton_couper.setEnabled(choisi is not None and choisi.dernier_mot - choisi.premier_mot > 1)
        self.bouton_fusionner.setEnabled(choisi is not None and index + 1 < nombre)
        ajustes = any(s.ajuste for s in self.sous_titres)
        self.bouton_retablir.setEnabled(ajustes)
        self.action_retablir.setEnabled(choisi is not None and choisi.ajuste)
        self.action_retablir_tous.setEnabled(ajustes)
        if choisi is None:
            aide = "Choisis d'abord un sous-titre dans la liste."
            for element in (self.bouton_monter, self.bouton_descendre, self.bouton_couper, self.bouton_fusionner):
                element.setToolTip(aide)
            return
        premier, dernier = self.mots[choisi.premier_mot].texte, self.mots[choisi.dernier_mot - 1].texte
        self.bouton_monter.setToolTip(f"« {premier} » passe à la fin du sous-titre {index}" if index > 0 else "")
        self.bouton_descendre.setToolTip(
            f"« {dernier} » passe au début du sous-titre {index + 2}" if index + 1 < nombre else ""
        )
        self.bouton_couper.setToolTip("Couper ce sous-titre en deux : choisis le mot qui commence le nouveau sous-titre")
        self.bouton_fusionner.setToolTip(f"Réunir les sous-titres {index + 1} et {index + 2}" if index + 1 < nombre else "")

    def _remplir_menu_couper(self) -> None:
        """Menu « Couper » : un choix par mot qui peut commencer le nouveau sous-titre."""
        self.menu_couper.clear()
        index = self._choisi()
        if index < 0:
            return
        choisi = self.sous_titres[index]
        for mot in range(choisi.premier_mot + 1, choisi.dernier_mot):
            texte = self.mots[mot].texte.replace("&", "&&")  # « & » seul soulignerait la lettre suivante
            action = self.menu_couper.addAction(f"Couper avant « {texte} »")
            action.triggered.connect(lambda _coche=False, m=mot: self.couper_avant(m))

    def _reorganiser(self, faire, message: str, index: int | None = None, statut=None) -> None:
        """Applique une action à la main au sous-titre choisi (ou `index`) ; si elle ne respecte pas
        les règles, rien ne change et la raison s'affiche (sous la liste, ou `statut`)."""
        index = self._choisi() if index is None else index
        transcription = self.transcription
        afficher = self._statut_reorganisation if statut is None else (lambda texte, role: self._afficher(texte, role, statut))
        if index < 0 or transcription is None or self._calcul is None:
            return
        resultat: Reorganisation = faire(index, self._calcul)
        if not resultat.possible:
            afficher(resultat.message, "erreur")
            return
        ranger_ajustements(transcription, resultat.ajustements)
        self._services.projets.enregistrer()
        self.calculer()
        self.choisir_sous_titre(min(resultat.choisi, len(self.sous_titres) - 1))
        afficher(message, "succes")

    def _verifier_la_limite(self, index: int, mot: int) -> str:
        """Pendant le glissement d'un bord de la frise : la raison d'un refus (vide : possible)."""
        calcul = self._calcul
        if calcul is None:
            return ""
        try:
            resultat = calcul_limite(calcul.decoupage, index, mot, calcul.reglages, calcul.ecran, calcul.mesure)
        except ValueError as erreur:
            return str(erreur)
        return resultat.message

    def deplacer_la_limite(self, index: int, mot: int) -> None:
        """Bord commun glissé dans la frise : `mot` commence désormais le sous-titre `index + 1`."""
        if not 0 <= index < len(self.sous_titres) - 1:
            return
        depart = self.sous_titres[index + 1].premier_mot
        if mot == depart or not self.sous_titres[index].premier_mot < mot < self.sous_titres[index + 1].dernier_mot:
            return
        deplaces = self.mots[mot:depart] if mot < depart else self.mots[depart:mot]
        texte = " ".join(m.texte for m in deplaces).replace(ESPACE_INSECABLE, " ")
        numero = index + 2 if mot < depart else index + 1
        verbe = "passe" if len(deplaces) == 1 else "passent"
        self._reorganiser(
            lambda i, c: calcul_limite(c.decoupage, i, mot, c.reglages, c.ecran, c.mesure),
            f"« {texte} » {verbe} au sous-titre {numero}.",
            index=index,
            statut=self.statut_frise,
        )

    def _corriger_le_sous_titre(self, index: int) -> None:
        """Double-clic sur un bloc de la frise : « Corriger les mots », sur son premier mot."""
        if 0 <= index < len(self.sous_titres):
            self.corriger_demande.emit(self.mots[self.sous_titres[index].premier_mot].debut)

    def monter_premier_mot(self) -> None:
        index = self._choisi()
        if index <= 0:
            return
        mot = self.mots[self.sous_titres[index].premier_mot].texte
        self._reorganiser(
            lambda i, c: calcul_monter(c.decoupage, i, c.reglages, c.ecran, c.mesure),
            f"« {mot} » passe à la fin du sous-titre {index}.",
        )

    def descendre_dernier_mot(self) -> None:
        index = self._choisi()
        if index < 0 or index + 1 >= len(self.sous_titres):
            return
        choisi = self.sous_titres[index]
        mot = self.mots[choisi.dernier_mot - 1].texte
        numero = index + 2 if choisi.dernier_mot - choisi.premier_mot > 1 else index + 1  # numéro après l'action
        self._reorganiser(
            lambda i, c: calcul_descendre(c.decoupage, i, c.reglages, c.ecran, c.mesure),
            f"« {mot} » passe au début du sous-titre {numero}.",
        )

    def couper_avant(self, mot: int) -> None:
        """Coupe le sous-titre choisi : `mot` (indice dans les mots affichés) commence le nouveau sous-titre."""
        index = self._choisi()
        if index < 0 or not self.sous_titres[index].premier_mot < mot < self.sous_titres[index].dernier_mot:
            return
        self._reorganiser(
            lambda i, c: calcul_couper(c.decoupage, i, mot, c.reglages, c.ecran, c.mesure),
            f"Sous-titre {index + 1} coupé avant « {self.mots[mot].texte} ».",
        )

    def fusionner_avec_le_suivant(self) -> None:
        index = self._choisi()
        if index < 0 or index + 1 >= len(self.sous_titres):
            return
        self._reorganiser(
            lambda i, c: calcul_fusionner(c.decoupage, i, c.reglages, c.ecran, c.mesure),
            f"Sous-titres {index + 1} et {index + 2} réunis.",
        )

    def retablir(self, tous: bool = False) -> None:
        """« Rétablir » : ce sous-titre (ou tous) revient au découpage automatique."""
        index, transcription = self._choisi(), self.transcription
        if transcription is None or self._calcul is None:
            return
        if tous:
            resultat = retablir_automatique(self._calcul.decoupage)
            message = "Découpage automatique rétabli pour tous les sous-titres."
        else:
            if index < 0 or not self.sous_titres[index].ajuste:
                return
            resultat = retablir_automatique(self._calcul.decoupage, index)
            message = f"Sous-titre {index + 1} : découpage automatique rétabli."
        ranger_ajustements(transcription, resultat.ajustements)
        self._services.projets.enregistrer()
        self.calculer()
        if index >= 0:
            self.choisir_sous_titre(min(index, len(self.sous_titres) - 1))
        self._statut_reorganisation(message, "succes")

    # --- Créer les sous-titres d'une prise (§3.3) ---------------------------------------------

    def _modele(self) -> str:
        transcription = self.transcription
        return transcription.modele if transcription and transcription.modele else MODELE_PAR_DEFAUT

    def creer_depuis_la_prise_choisie(self) -> None:
        identifiant = self.prises.currentData()
        if identifiant:
            self.creer_depuis_prise(identifiant)

    def creer_depuis_prise(self, identifiant: str) -> None:
        """La prise est transcrite (moment de chaque mot), puis les mots sont calés sur son script."""
        projet = self._projet
        if projet is None or self._occupe:
            return
        try:
            prise = self._services.projets.prise(identifiant)
        except ErreurProjet as erreur:
            self._afficher(str(erreur), "erreur")
            return
        choisir(self.prises, identifiant)
        if not texte_brut(prise.script).strip():
            self._afficher(f"Le script de « {prise.nom} » est vide : rien à sous-titrer.", "erreur")
            return
        actuelle = self.transcription
        if actuelle is not None and actuelle.horodatee and actuelle.prise != identifiant and not self._confirmer_remplacement(actuelle):
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        try:
            transcription, wav = transcription_de_prise(projet, prise)
        except OSError as erreur:
            self._afficher(f"Fichier de la prise illisible : {erreur}", "erreur")
            return
        transcription.masquer_hesitations = actuelle.masquer_hesitations if actuelle else True
        options = Options(self._modele(), projet.langue, MODE_VERBATIM, False, FOURNISSEUR)
        self.lecteur.arreter()  # libère la piste son, qui va être remplacée
        self._occuper(True)
        self._afficher(f"Transcription de « {prise.nom} », puis calage sur son script…", "secondaire")

        def fin(resultat) -> None:
            self._occuper(False)
            if self._projet is not projet:
                return
            if not resultat.mots:
                self._afficher("Google n'a renvoyé aucun mot : la prise est-elle silencieuse ?", "avertissement")
                return
            chemin = projet.chemin(FICHIER_AUDIO)
            try:
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.write_bytes(wav)  # l'audio de la prise devient celui des sous-titres
            except OSError as erreur:
                self._afficher(f"Audio de la prise non copié dans le projet : {erreur}", "erreur")
                return
            fini = terminer_transcription(self._services, transcription, options, resultat)
            self.tableau.clearSelection()
            self._afficher(f"Sous-titres créés depuis « {prise.nom} » : {len(fini.mots)} mots calés sur le script.", "succes")
            self.rafraichir()
            self._au_debut()

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Sous-titres impossibles : {message_erreur(erreur)}", "erreur")
            self._charger_la_lecture()

        taches.lancer(lambda: transcrire_source(adaptateur, wav, options, f"{projet.nom} - {prise.nom}"), fin, echec)

    def _confirmer_remplacement(self, actuelle: Transcription) -> bool:
        boite = QMessageBox(self.window())
        boite.setIcon(QMessageBox.Icon.Question)
        boite.setWindowTitle("Créer les sous-titres")
        boite.setText("Remplacer les mots actuels ?")
        ajustes = (
            " Les sous-titres réorganisés à la main reviendront au découpage automatique."
            if actuelle.ajustements_sous_titres
            else ""
        )
        boite.setInformativeText(
            f"Les sous-titres viennent aujourd'hui de « {Path(actuelle.source).name or actuelle.source} ». "
            f"Ses mots et ses corrections seront remplacés par ceux de la prise.{ajustes}"
        )
        remplacer = boite.addButton("Remplacer", QMessageBox.ButtonRole.AcceptRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.exec()
        return boite.clickedButton() is remplacer

    def _occuper(self, occupe: bool) -> None:
        self._occupe = occupe
        self.bouton_creer.setEnabled(not occupe and bool(self._projet and self._projet.prises))
        self.prises.setEnabled(not occupe and bool(self._projet and self._projet.prises))

    # --- Export SRT (§8.1) --------------------------------------------------------------------

    def _demander_fichier(self, proposition: Path) -> Path | None:
        choix, _ = QFileDialog.getSaveFileName(self, "Exporter les sous-titres (SRT)", str(proposition), "Sous-titres SRT (*.srt)")
        return Path(choix) if choix else None

    def exporter_srt(self) -> None:
        if self._projet is None or not self.sous_titres:
            return
        chemin = self._demander_fichier(dossier_documents() / f"{nom_de_dossier(self._projet.nom)}.srt")
        if chemin is None:
            return
        if chemin.suffix.lower() != ".srt":
            chemin = chemin.with_name(chemin.name + ".srt")
        try:
            ecrire_srt(chemin, self.sous_titres)
        except OSError as erreur:
            self._afficher(f"Fichier non enregistré : {erreur}", "erreur", self.statut_export)
            return
        journal.info("Sous-titres exportés : %s (%d)", chemin, len(self.sous_titres))
        self._afficher(f"Fichier enregistré : {chemin.name} ({len(self.sous_titres)} sous-titres).", "succes", self.statut_export)

    # --- Exports vidéo (V3) ------------------------------------------------------------------

    def _nom_du_style(self) -> str:
        """Le préréglage du projet, tel que la liste « Préréglage » le montre (« Karaoké (modifié) »)."""
        reglages = self._projet.sous_titres
        origine = self._services.prereglages.prereglage(reglages.prereglage)
        if origine is None:
            return reglages.prereglage_nom or ""
        return f"{origine.nom} (modifié)" if modifie(reglages, origine) else origine.nom

    def contenu_a_exporter(self) -> SousTitresAExporter | None:
        """Les sous-titres tels que l'aperçu les montre : mêmes réglages, même taille de vidéo."""
        if self._projet is None or self._calcul is None or not self.sous_titres:
            return None
        moteur = self._calcul.moteur
        return SousTitresAExporter(
            self._calcul.reglages, moteur.largeur, moteur.hauteur, list(self.sous_titres), list(self.mots), self._nom_du_style()
        )

    def dialogue_calque(self) -> DialogueExportCalque | None:
        """La fenêtre d'export du calque, prête à s'ouvrir (None : rien à exporter)."""
        contenu = self.contenu_a_exporter()
        if contenu is None:
            return None
        if self.lecteur.en_lecture():
            self.lecteur.basculer()  # pause : l'aperçu ne tourne pas pendant l'export
        return DialogueExportCalque(self._services, self._projet, contenu, self.window())

    def exporter_calque(self) -> None:
        dialogue = self.dialogue_calque()
        if dialogue is None:
            return
        dialogue.exec()
        if dialogue.fichier is not None:
            self._afficher(f"Calque enregistré : {dialogue.fichier.name}.", "succes", self.statut_export)

    def dialogue_video(self) -> DialogueExportVideo | None:
        """La fenêtre d'export de la vidéo avec sous-titres (None : rien à exporter, ou pas de vidéo)."""
        contenu = self.contenu_a_exporter()
        if contenu is None or not source_du_projet(self._projet).video:
            return None
        if self.lecteur.en_lecture():
            self.lecteur.basculer()
        return DialogueExportVideo(self._services, self._projet, contenu, self.window())

    def exporter_video(self) -> None:
        dialogue = self.dialogue_video()
        if dialogue is None:
            return
        dialogue.exec()
        if dialogue.fichier is not None:
            self._afficher(f"Vidéo enregistrée : {dialogue.fichier.name}.", "succes", self.statut_export)

    # --- Pour l'autotest ---------------------------------------------------------------------

    def reglages_du_projet(self):
        """Réglages des sous-titres du projet ouvert."""
        return self._projet.sous_titres if self._projet is not None else None
