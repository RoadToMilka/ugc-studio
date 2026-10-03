"""Atelier des sous-titres (§7, §3.3, §8.1) : des mots horodatés au fichier SRT, dans un studio.

Disposition (V3.1, lot 5, disposition.py) : en haut, Source à gauche et Exporter à droite ; dessous,
l'Aperçu, l'Apparence et les Sous-titres (trois colonnes qui défilent chacune seule en grande
fenêtre ; aperçu et apparence côte à côte, puis la liste, en fenêtre moyenne) ; la Frise en bas.

1. Source (source.py, V3.1, lot 6 ; « Mots des sous-titres » jusqu'à la 3.0.4) : la vidéo de
   l'aperçu (celle du module Transcription, ou une vidéo importée ici) et les mots des sous-titres
   (ceux du module Transcription, ou des mots importés ici : d'une prise de voix, que « Créer les
   sous-titres » transcrit puis cale sur son script, ou d'un fichier SRT). On passe de l'une à
   l'autre sans rien perdre (sources.py). Les mots du module se corrigent dans le module, les mots
   importés dans la fenêtre « Corriger les mots » (la même correction).
2. Aperçu (apercu.py) : la vidéo, ou un fond gris ou un damier, et les sous-titres dessinés par le
   moteur de dessin, le même que l'export de la V3 ; la zone a la taille de la vidéo affichée.
3. Apparence (reglages.py ; « Réglages » jusqu'à la 3.0.4) : préréglage, onglets Texte (le
   Découpage en tête, la Position dedans depuis la V3.3), Mots, Animations et Écran. Les sous-titres
   sont recalculés à chaque changement ; la position (haut, centre, bas, réglage fin) ne change que
   l'aperçu, jamais le découpage.
4. Sous-titres : « Masquer les hésitations » (V3.3 ; le Découpage était en haut de ce bloc de la V3.1
   à la 3.2.4), puis la liste ; ceux où un mot a dû être rapetissé sont signalés en orange. Réorganiser à la main (V1.1) : sur le sous-titre
   choisi, monter son premier mot, descendre son dernier mot, le couper, le fusionner avec le suivant,
   ou revenir au découpage automatique. Les réglages du découpage s'appliquent toujours (une action
   qui ne les respecte pas est refusée, avec la raison) ; un réglage qui défait un ajustement demande
   d'abord (sous_titres_du_projet.py).
5. Frise (V2, lot 7, composants/frise.py) : en bas, un bloc par sous-titre et un trait par mot ; un
   clic place la lecture ou choisit un sous-titre (synchronisé avec la liste), le bord commun de deux
   sous-titres se glisse de mot en mot (mêmes règles qu'au point 4), un double-clic corrige les mots
   du sous-titre dans le module Transcription.
6. Préréglages (V2, lot 7, prereglages.py) : en haut de l'apparence, le préréglage d'origine du
   projet (« (modifié) » quand son style s'en écarte) ; en choisir un l'applique (avec la question de
   la 1.1.0 s'il défait un ajustement) ; à côté, trois boutons en icône (V3.2) : la bibliothèque (la
   fenêtre « Préréglages de sous-titres »), « Enregistrer » (en crée un) et le menu ⋯ (mettre à jour,
   revenir au préréglage).
7. Exporter (V3) : la vidéo avec ses sous-titres incrustés (lot 2 ; projet avec une vidéo), le
   calque transparent (MOV, ProRes 4444) à poser sur le montage dans Premiere Pro, tous deux
   dessinés par le moteur de l'aperçu (fenêtre d'export : réglages, résumé, avancement), et le
   fichier SRT.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem, QVBoxLayout

from ....alignement import mots_du_script_accentues
from ....chemins import chemin_a_afficher, dossier_documents
from ....exports.plan import SousTitresAExporter, source_du_projet
from ....fournisseurs.stt import MODE_VERBATIM
from ....import_srt import FILTRE, ErreurSrt, est_srt, transcription_depuis_srt
from ....mise_en_page import limites_du_reglage_fin
from ....modeles_charges import SOUS_TITRES
from ....prereglages import appliquer as appliquer_le_prereglage
from ....prereglages import modifie, style_du_projet
from ....projets import ErreurProjet, Projet, nom_de_dossier
from ....rendu.moteur import Moteur
from ....rendu.polices import NOMS_GRAISSES, police_remplacee
from ....script import texte_brut
from ....services import Services
from ....sources import (
    SOURCE_IMPORTEE,
    SOURCE_TRANSCRIPTION,
    a_des_retouches,
    a_une_video,
    audio_des_mots,
    decalage_des_mots,
    mots_des_sous_titres,
    video_de_l_apercu,
    voix_a_caler,
)
from ....sous_titres import (
    ESPACE_INSECABLE,
    MotAffiche,
    Reorganisation,
    SousTitre,
    decales,
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
    hesitations,
    terminer_transcription,
    transcription_de_prise,
    transcrire_source,
)
from ....style_sous_titres import VideoApercu
from ....transcription import Transcription, resolution_video
from ... import taches
from ...composants.apercu import LecteurApercu
from ...composants.bouton import BoutonOccupe, montrer_occupe
from ...composants.choix_voix import choisir
from ...composants.defilement import ColonneDefilante
from ...composants.elements import (
    afficher_message,
    bloc,
    bouton,
    conteneur_vertical,
    info,
    intitule,
    libelle,
    marge_haute_titre,
    minutes_secondes,
    titre_avec,
)
from ...composants.flux import DispositionFlux
from ...composants.frise import FriseSousTitres
from ...composants.menu import Menu
from ...composants.tableau import Colonne, Tableau
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...dialogues import messages
from ...dialogues.corriger_mots import DialogueCorrigerMots
from ...dialogues.export import DialogueExportCalque, DialogueExportVideo
from ...dialogues.prereglages import DialoguePrereglages
from ...extraction import FILTRE_FICHIERS, LecteurInfos
from ...sous_titres_du_projet import (
    Calcul,
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
from .apercu import BlocApercu
from .disposition import GRANDE, DispositionStudio
from .reglages import PanneauReglages
from .source import BlocSource, EtatSource

journal = logging.getLogger(__name__)

TITRE = "Sous-titres"
SOUS_TITRE = "Studio des sous-titres : aperçu sur la vidéo, apparence, découpage et export."
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


def bloc_en_colonne(titre: str, contenu) -> tuple:
    """Bloc dont le contenu défile seul en grande fenêtre (V3.1, lot 5 : Apparence, Sous-titres) : le
    titre reste en haut, et la barre fine prend place dans la marge de droite du bloc (voir
    ColonneDefilante). Renvoie le bloc et la zone qui défile."""
    cadre, disposition = bloc(titre)
    disposition.setContentsMargins(Espacements.XL, marge_haute_titre(), Espacements.S, Espacements.XL)
    colonne = ColonneDefilante(contenu, marge_droite=Espacements.XL - Espacements.S)
    disposition.addWidget(colonne)
    return cadre, colonne


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
        # La page remplit la hauteur de la fenêtre : en grande fenêtre, les colonnes en prennent le reste.
        super().__init__(TITRE, SOUS_TITRE, conseils="sous-titres", remplir_la_hauteur=True)
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
        # V3.1, lot 6 : le module Transcription (relier_transcription), qui importe et transcrit pour
        # la zone Source ; le bouton où tourne le cercle en attendant qu'il ait fini.
        self._module_transcription = None
        self._attente_du_module = BoutonOccupe()

        # --- Aperçu et apparence ---
        self.bloc_apercu = BlocApercu(services.preferences)
        self.toile = self.bloc_apercu.toile
        self.toile.glissable = True  # le sous-titre se glisse verticalement dans l'aperçu
        self.panneau = PanneauReglages()
        self.cadre_apparence, self.colonne_apparence = bloc_en_colonne("Apparence", self.panneau)
        # Raccourcis vers les réglages (tests, autotest).
        panneau = self.panneau
        self.caracteres, self.mots_max, self.lignes, self.duree_min = panneau.caracteres, panneau.mots_max, panneau.lignes, panneau.duree_min
        self.taille, self.casse, self.ponctuation = panneau.texte.taille.champ, panneau.texte.casse, panneau.texte.ponctuation
        self.couper_ponctuation = panneau.couper_ponctuation
        self.format, self.plateforme, self.marge, self.masquer = panneau.format, panneau.plateforme, panneau.marge, panneau.masquer
        self.infos_ecran = panneau.infos_ecran

        # --- Disposition (V3.1, lot 5) : Source et Exporter en haut, les trois colonnes, la frise ---
        self.studio = DispositionStudio(
            self._bloc_source(),
            self._bloc_export(),
            self.bloc_apercu,
            self.cadre_apparence,
            self._bloc_sous_titres(),
            self._bloc_frise(),
            colonnes=(self.colonne_apparence, self.colonne_sous_titres),
            defilement=self.defilement,
        )
        self.studio.mode_change.connect(self._disposition_change)
        self._disposition_change(self.studio.mode)
        self.contenu.addWidget(self.studio, 1)

        self._brancher()
        services.prereglages.abonner(self._actualiser_prereglage)  # renommé, supprimé, mis à jour…
        services.projets.abonner(self._projet_change)
        services.prix.abonner(self._mettre_a_jour_estimation)
        self._projet_change(services.projets.projet)

    # --- Construction ------------------------------------------------------------------------

    def _bloc_source(self):
        """Source (V3.1, lot 6, source.py) : la vidéo de l'aperçu et les mots des sous-titres, en haut
        à gauche de la page. Raccourcis vers ses éléments (tests, autotest) : la ligne qui dit d'où
        viennent les mots, « Corriger les mots », la liste des prises et « Créer les sous-titres »."""
        self.source = source = BlocSource()
        self.cadre_source = source
        self.texte_source, self.bouton_corriger = source.texte_mots, source.bouton_corriger
        self.prises, self.bouton_creer = source.prises, source.bouton_creer
        self.estimation, self.cout_estime = source.estimation, source.cout_estime
        self.statut = source.statut
        self.prises.currentIndexChanged.connect(lambda _index: self._mettre_a_jour_estimation())
        source.video_choisie.connect(self.choisir_la_video)
        source.mots_choisis.connect(self.choisir_les_mots)
        source.importer_demande.connect(self.importer_dans_transcription)
        source.choisir_video_demande.connect(self.choisir_video_apercu)
        source.retirer_video_demande.connect(self.retirer_video_apercu)
        source.son_de_la_video_change.connect(lambda _son: self._video_apercu_change())
        source.decalage_change.connect(lambda _decalage: self._video_apercu_change())
        source.transcrire_demande.connect(self.transcrire_ici)
        source.corriger_demande.connect(self.corriger_les_mots)
        source.creer_demande.connect(self.creer_depuis_la_prise_choisie)
        source.importer_srt_demande.connect(self.importer_srt)
        return source

    def _bloc_sous_titres(self):
        """Sous-titres : la ligne de résumé, « Masquer les hésitations » (V3.3, seul ici : il ne fait pas
        partie d'un préréglage ; le Découpage, en haut de ce bloc de la V3.1 à la 3.2.4, est retourné en
        tête de l'onglet Texte de l'apparence), la réorganisation à la main et la liste. En grande
        fenêtre, le bloc défile seul et la liste prend la place qui reste."""
        contenu, d = conteneur_vertical(Espacements.M)
        self.resume = libelle("", "legende")
        d.addWidget(self.resume)
        d.addWidget(self.panneau.zone_masquer)
        self._zone_reorganiser(d)
        self.tableau = self._tableau()
        d.addWidget(self.tableau, 1)
        self._actualiser_reorganisation()  # aucun sous-titre choisi : actions désactivées
        self.statut_lecture = libelle("", "secondaire")  # lecture impossible dans l'aperçu
        self.statut_lecture.hide()
        d.addWidget(self.statut_lecture)
        self.cadre_sous_titres, self.colonne_sous_titres = bloc_en_colonne("Sous-titres", contenu)
        return self.cadre_sous_titres

    def _disposition_change(self, mode: str) -> None:
        """Trois colonnes (grande fenêtre) : la liste prend la hauteur qui reste dans sa colonne, au
        moins STUDIO_TABLEAU_HAUTEUR_MIN ; sinon, elle a sa hauteur habituelle (la page défile)."""
        grande = mode == GRANDE
        self.tableau.setMinimumHeight(Dimensions.STUDIO_TABLEAU_HAUTEUR_MIN if grande else Dimensions.TABLEAU_HAUTEUR_MIN)

    def montrer(self, element) -> None:
        """Amène un élément à l'écran : dans sa colonne si elle défile seule (grande fenêtre), puis
        dans la page."""
        for colonne in (self.colonne_apparence, self.colonne_sous_titres):
            if colonne.defile and colonne.isAncestorOf(element):
                colonne.ensureWidgetVisible(element)
        self.defilement.ensureWidgetVisible(element)

    def _bloc_frise(self):
        """Frise des sous-titres (V2, lot 7), sur toute la largeur, en bas de la page."""
        self.cadre_frise, d = bloc(
            "Frise",
            aide=(
                "Clic : aller à ce moment, ou choisir un sous-titre. Glisse le bord commun de deux sous-titres : "
                "des mots passent de l'un à l'autre. Double-clic : corriger ses mots. Ctrl + molette : zoom."
            ),
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
        self.cadre_export, d = bloc(
            "Exporter",
            aide=(
                "Vidéo avec sous-titres : la vidéo de l'aperçu, sous-titres incrustés, prête à publier. Calque transparent : "
                "les sous-titres seuls, à poser au-dessus de ton montage dans Premiere Pro. Fichier SRT : le texte "
                "et le moment de chaque sous-titre, sans style."
            ),
        )
        boutons = DispositionFlux(espacement=Espacements.S)  # passe à la ligne si la fenêtre est étroite
        self.bouton_video = bouton("Vidéo avec sous-titres…", variante="principal", nom_icone="clapperboard", action=self.exporter_video)
        self.bouton_video.setToolTip(
            "MP4, MOV ou MKV : la vidéo de l'aperçu et ses sous-titres, chaque image à son moment exact"
        )
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
            "Vidéo avec sous-titres : il faut une vidéo (zone Source, onglet « Vidéo ou audio »). Sinon, "
            "exporte le calque transparent et pose-le sur ton montage.",
            "legende",
        )
        self.info_video.hide()
        d.addWidget(self.info_video)
        self.statut_export = libelle("", "secondaire")
        self.statut_export.hide()
        d.addWidget(self.statut_export)
        d.addStretch(1)  # à côté de Source, les deux blocs ont la même hauteur : le contenu reste en haut
        return self.cadre_export

    def _brancher(self) -> None:
        panneau, apercu, lecteur = self.panneau, self.bloc_apercu, self.lecteur
        panneau.change.connect(self._reglage_change)
        panneau.position_change.connect(self._position_change)
        panneau.masquer_change.connect(self._masquer_change)
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
        self.titre_reorganiser = intitule(
            "Réorganiser à la main",
            "Choisis un sous-titre dans la liste. Le moment des mots ne change jamais, et les réglages du "
            "découpage s'appliquent toujours.",
        )
        d.addWidget(self.titre_reorganiser)
        actions = DispositionFlux(espacement=Espacements.S)  # passe à la ligne si la fenêtre est étroite
        self.bouton_monter = bouton(
            "Monter le premier mot", variante="contour", nom_icone="arrow-up", action=self.monter_premier_mot
        )
        self.bouton_descendre = bouton(
            "Descendre le dernier mot", variante="contour", nom_icone="arrow-down", action=self.descendre_dernier_mot
        )
        self.bouton_couper = bouton("Couper", variante="contour", nom_icone="scissors")
        self.menu_couper = Menu(self.bouton_couper)
        self.menu_couper.aboutToShow.connect(self._remplir_menu_couper)  # les mots du sous-titre choisi
        self.bouton_couper.setMenu(self.menu_couper)
        self.bouton_fusionner = bouton(
            "Fusionner avec le suivant", variante="contour", nom_icone="list-plus", action=self.fusionner_avec_le_suivant
        )
        # V3.1 : l'icône seule (la flèche qui revient), le sens au survol ; un clic ouvre le menu.
        self.bouton_retablir = bouton("", variante="contour", nom_icone="rotate-ccw")
        self.bouton_retablir.setToolTip("Revenir au découpage automatique")
        menu = Menu(self.bouton_retablir)
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
        """Les mots des sous-titres : ceux de la source choisie (module Transcription, ou importés)."""
        return mots_des_sous_titres(self._projet) if self._projet else None

    def _projet_change(self, projet: Projet | None) -> None:
        self._enregistrement_position.stop()
        self.lecteur.arreter()
        self._projet = projet
        if projet is None:
            self._services.modeles.choisir(SOUS_TITRES, None)
            return
        self.titre.setText(titre_avec(TITRE, projet.nom))
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
        """Pipette d'un champ couleur (§7.4) : l'aperçu attend un clic. Si l'aperçu n'est pas à l'écran
        (ex. fenêtre étroite, aperçu au-dessus de l'apparence), la page défile jusqu'à lui."""
        self.toile.commencer_pipette(champ.couleur_prise)
        self.defilement.ensureWidgetVisible(self.bloc_apercu.zone)

    def keyPressEvent(self, evenement) -> None:  # noqa: N802
        """Barre Espace : lecture ou pause (quand aucun bouton ni case n'a la main)."""
        if evenement.key() == Qt.Key.Key_Space and not evenement.isAutoRepeat():
            self.basculer_lecture()
            return
        super().keyPressEvent(evenement)

    def _afficher(self, message: str, role: str, etiquette=None) -> None:
        """Message d'état sous un bloc ; sans message, la ligne disparaît (pas de vide en bas du bloc).
        Vert, rouge ou orange : effacé après 8 s (V3.2)."""
        afficher_message(etiquette or self.statut, message, role)

    # --- Affichage ---------------------------------------------------------------------------

    def rafraichir(self) -> None:
        """Met toute la page à jour : source des mots, prises, réglages, sous-titres, lecture."""
        # Réglages → Modèles et prix, « Utilisé dans » : le modèle qui transcrit une prise.
        self._services.modeles.choisir(SOUS_TITRES, self._modele() if self._projet else None)
        if self._projet is None:
            return
        self._actualiser_la_source()
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
        self.bouton_creer.setEnabled((bool(projet.prises) and not self._occupe) or self.bouton_creer.est_occupe())
        self._mettre_a_jour_estimation()

    def _mettre_a_jour_estimation(self) -> None:
        """Coût estimé : des sous-titres de la prise choisie, et de « Transcrire » (la source du
        module Transcription, avec le modèle choisi là-bas)."""
        projet = self._projet
        identifiant = self.prises.currentData()
        prise = next((p for p in projet.prises if p.identifiant == identifiant), None) if projet else None
        self._estimer(self.estimation, self.cout_estime, prise.duree_s if prise else 0.0, "d'audio à transcrire", self._modele())
        module = projet.transcription if projet else None
        self._estimer(
            self.source.estimation_transcrire, self.source.cout_transcrire, module.duree_s if module else 0.0, "d'audio",
            self._modele_du_module(),
        )

    def _estimer(self, texte, montant, duree: float, quoi: str, modele: str) -> None:
        texte.setText(f"≈ {minutes_secondes(duree)} {quoi}  ·  ≈" if duree else "")
        montant.setVisible(bool(duree))
        if duree:
            cout = estimer_cout(duree, modele, self._services.prix)
            if cout is None:
                montant.setText("prix inconnu")
            else:
                montant.definir_montant(cout)

    # --- Source (V3.1, lot 6) ----------------------------------------------------------------------

    def _actualiser_la_source(self) -> None:
        """La zone Source : les choix, ce que décrit chaque onglet, les boutons utiles."""
        projet = self._projet
        module, mots = projet.transcription, self.transcription
        apercu = projet.sous_titres.apercu
        if projet.sources.video == SOURCE_IMPORTEE:
            texte_video = (
                self._description_video_importee(apercu)
                if apercu.chemin
                else "Aucune vidéo importée : par exemple ton montage exporté de Premiere Pro."
            )
        elif module is not None and module.source and a_une_video(module):
            texte_video = description_source(module)
        elif module is not None and module.source:
            texte_video = f"{description_source(module)} : un audio, sans image (l'aperçu montre un fond gris)."
        else:
            texte_video = "Rien d'importé dans le module Transcription."
        self.source.afficher(
            EtatSource(
                video=projet.sources.video,
                mots=projet.sources.sous_titres,
                texte_video=texte_video,
                texte_mots=self._description_des_mots(),
                module_a_une_source=bool(module and module.source),
                video_importee=bool(apercu.chemin),
                son_de_la_video=apercu.son_de_la_video,
                voix_des_mots=audio_des_mots(projet) is not None,
                corriger=bool(mots and mots.horodatee),
                transcrire=bool(module and module.audio and not module.mots and not module.texte),
                voix_a_caler=voix_a_caler(projet),
                decalage_s=apercu.decalage_s,
            )
        )
        self.bouton_corriger.setToolTip(
            "Corriger un mot ou son moment dans le module Transcription"
            if mots is module
            else "Corriger un mot ou son moment (la même correction que dans le module Transcription)"
        )
        # Pendant un import ou une transcription du module : le cercle tourne dans le bouton qui l'a
        # demandé ; l'autre est grisé.
        attente = self._attente_du_module
        for element in (self.source.bouton_transcrire, self.source.bouton_importer):
            element.setEnabled(attente.bouton is None or attente.est(element))

    @staticmethod
    def _description_video_importee(apercu: VideoApercu) -> str:
        resolution = apercu.resolution
        details = f"  ·  {resolution[0]} × {resolution[1]}" if resolution else ""
        return f"{Path(apercu.chemin).name}{details}"

    def _description_des_mots(self) -> str:
        """La ligne qui dit toujours d'où viennent les mots des sous-titres."""
        projet, mots = self._projet, self.transcription
        if projet.sources.sous_titres == SOURCE_TRANSCRIPTION:
            if mots is None or not mots.source:
                return (
                    "Pas encore de mots : importe une vidéo ou un audio (onglet « Vidéo ou audio »), ou des "
                    "sous-titres (« Importés »)."
                )
            nom = Path(mots.source).name
            if mots.horodatee:
                return f"Les sous-titres viennent de la transcription de {nom} ({len(mots.mots)} mots{self._date(mots)})."
            if mots.texte:
                return (
                    f"La transcription de {nom} est en texte seul (sans le moment de chaque mot) : pas de "
                    "sous-titres possibles. Transcris-la sans « Texte seul » dans le module Transcription."
                )
            return f"Pas encore de mots : {nom} n'est pas encore transcrite. « Transcrire » le fait ici, avec les options du module Transcription."
        if mots is None or not mots.horodatee:
            return "Pas encore de mots importés : crée les sous-titres d'une prise, ou importe un fichier SRT."
        if est_srt(mots):
            nombre = (mots.infos or {}).get("sous_titres", 0)
            return (
                f"Les sous-titres viennent du fichier {Path(mots.source).name} ({nombre} sous-titres, "
                f"{len(mots.mots)} mots ; moment de chaque mot estimé)."
            )
        return (
            f"Les sous-titres viennent de « {mots.source} » : voix générée, calée sur son script "
            f"({len(mots.mots)} mots{self._date(mots)})."
        )

    @staticmethod
    def _date(transcription: Transcription) -> str:
        try:
            return ", " + datetime.fromisoformat(transcription.date).strftime("%d/%m/%Y")
        except ValueError:
            return ""

    def choisir_la_video(self, source: str) -> None:
        """Onglet « Vidéo ou audio » : celle du module Transcription, ou la vidéo importée. Le format
        suit la vidéo choisie : s'il défait un sous-titre réorganisé à la main, la question vient d'abord."""
        projet = self._projet
        if projet is None or source == projet.sources.video:
            return
        avant = projet.sources.video
        projet.sources.video = source
        if not confirmer_reglage(self.window(), self._services, projet):
            projet.sources.video = avant
            self._actualiser_la_source()
            return
        self._services.projets.enregistrer()
        self.rafraichir()

    def choisir_les_mots(self, source: str) -> None:
        """Onglet « Sous-titres » : les mots du module Transcription, ou les mots importés. Chacun
        garde ses retouches : rien ne se perd."""
        projet = self._projet
        if projet is None or source == projet.sources.sous_titres:
            return
        projet.sources.sous_titres = source
        self._services.projets.enregistrer()
        self.tableau.clearSelection()
        self.rafraichir()
        self._au_debut()

    def relier_transcription(self, module) -> None:
        """Le module Transcription (fenêtre principale) : il importe et transcrit pour la zone Source,
        avec ses options ; la fin arrive par ses signaux."""
        self._module_transcription = module
        module.import_termine.connect(self._le_module_a_fini)
        module.transcription_terminee.connect(self._le_module_a_fini)
        module.infos_lues.connect(self._infos_du_module_lues)
        self._mettre_a_jour_estimation()

    def _infos_du_module_lues(self) -> None:
        """Les informations de la source du module (taille de la vidéo…) arrivées après la fin de son
        import : l'aperçu et le format suivent."""
        if self._projet is not None and self.isVisible() and not self._occupe:
            self.rafraichir()

    def _modele_du_module(self) -> str:
        module = self._module_transcription
        return module.options().modele if module is not None else MODELE_PAR_DEFAUT

    def importer_dans_transcription(self) -> None:
        """« Choisir une vidéo ou un audio… » : importée dans le module Transcription (les deux modules
        montrent la même source). Le cercle tourne ici jusqu'à la fin de l'extraction du son."""
        module = self._module_transcription
        if module is None or self._projet is None or self._module_occupe(module):
            return
        chemin = self._choisir_un_fichier("Choisir une vidéo ou un audio", FILTRE_FICHIERS)
        if chemin is None:
            return
        self.lecteur.arreter()  # libère la piste son, qui peut être remplacée
        self._attendre_le_module(self.source.bouton_importer, f"Import de « {chemin.name} » dans le module Transcription…")
        if not module.importer(chemin):
            self._sans_reponse_du_module()  # ex. remplacement annulé (un refus, lui, a déjà répondu)

    def transcrire_ici(self) -> None:
        """« Transcrire » : la source du module Transcription, avec ses options (modèle, langue…)."""
        module = self._module_transcription
        if module is None or self._projet is None or self._module_occupe(module):
            return
        self.lecteur.arreter()
        self._attendre_le_module(self.source.bouton_transcrire, "Transcription en cours… (envoi de l'audio à Google, puis transcription)")
        if not module.transcrire():
            self._sans_reponse_du_module()

    def _module_occupe(self, module) -> bool:
        """Le module Transcription travaille déjà (un import ou une transcription lancés là-bas) : la
        page le dit, plutôt que d'attendre sans rien montrer."""
        if module.occupe:
            self._afficher(
                "Le module Transcription est déjà au travail (import ou transcription) : attends qu'il ait fini.",
                "avertissement",
            )
        return module.occupe

    def _attendre_le_module(self, bouton_occupe, message: str) -> None:
        self._attente_du_module.occuper(bouton_occupe)
        self._afficher(message, "secondaire")
        self._actualiser_la_source()  # l'autre bouton est grisé pendant l'attente

    def _sans_reponse_du_module(self) -> None:
        """Le module n'a rien commencé, et n'a rien dit (sinon _le_module_a_fini a déjà répondu) :
        plus d'attente, plus de message."""
        if self._attente_du_module.bouton is None:
            return
        self._attente_du_module.liberer()
        self._afficher("", "secondaire")
        self._actualiser_la_source()
        self._charger_la_lecture()

    def _le_module_a_fini(self, message: str, role: str) -> None:
        """Import ou transcription du module Transcription terminé : la page suit."""
        attendu = self._attente_du_module.bouton is not None
        self._attente_du_module.liberer()
        if self._projet is None:
            return
        if attendu:
            self._afficher(message, role)
        if attendu or self.isVisible():
            self.rafraichir()
            self._au_debut()

    def importer_srt(self) -> None:
        """« Importer un fichier SRT… » : ses mots deviennent les mots importés (le moment de chaque
        mot est estimé), après confirmation si l'import précédent avait des retouches."""
        if self._projet is None:
            return
        chemin = self._choisir_un_fichier("Importer des sous-titres", FILTRE)
        if chemin is not None:
            self.importer_srt_depuis(chemin)

    def _choisir_un_fichier(self, titre: str, filtre: str) -> Path | None:
        """Un fichier à importer (remplacé dans les tests)."""
        chemin, _ = QFileDialog.getOpenFileName(self, titre, str(dossier_documents()), filtre)
        return Path(chemin) if chemin else None

    def importer_srt_depuis(self, chemin: Path) -> None:
        projet = self._projet
        if projet is None:
            return
        try:
            importes = transcription_depuis_srt(chemin, projet.langue)
        except ErreurSrt as erreur:
            self._afficher(f"Sous-titres non importés : {erreur}", "erreur")
            return
        actuels = projet.sous_titres_importes
        if a_des_retouches(actuels) and not self._confirmer_remplacement(actuels):
            return
        importes.masquer_hesitations = actuels.masquer_hesitations if actuels is not None else True
        projet.sous_titres_importes = importes
        projet.sources.sous_titres = SOURCE_IMPORTEE
        self._services.projets.enregistrer()
        self.tableau.clearSelection()
        self.rafraichir()
        self._au_debut()
        nombre = importes.infos.get("sous_titres", 0)
        self._afficher(
            f"Sous-titres importés de {chemin.name} : {nombre} sous-titres, {len(importes.mots)} mots (moment de "
            "chaque mot estimé, puis ton découpage appliqué).",
            "succes",
        )

    def corriger_les_mots(self, mot: int = -1) -> None:
        """« Corriger les mots » : ceux du module Transcription dans le module (comme avant) ; des mots
        importés dans la fenêtre de correction. `mot` : le mot à choisir (-1 : aucun)."""
        projet, mots = self._projet, self.transcription
        if projet is None or mots is None or not mots.horodatee:
            return
        if mots is projet.transcription:
            self.corriger_demande.emit(mots.mots[mot].debut if 0 <= mot < len(mots.mots) else -1.0)
            return
        self.lecteur.arreter()  # la fenêtre lit la prise
        description = self._description_des_mots()
        fenetre = DialogueCorrigerMots(mots, description, audio_des_mots(projet), hesitations(self._services, mots), self.window(), mot)
        if self._corriger(fenetre) and fenetre.modifie:
            mots.mots = fenetre.mots
            mots.corrigee = True
            self._services.projets.enregistrer()
            self._afficher("Mots corrigés : les sous-titres suivent.", "succes")
        self.rafraichir()

    @staticmethod
    def _corriger(fenetre: DialogueCorrigerMots) -> bool:
        """Ouvre la fenêtre de correction (remplacé dans les tests)."""
        return fenetre.exec() == DialogueCorrigerMots.DialogCode.Accepted

    def _charger_reglages(self) -> None:
        transcription, reglages = self.transcription, self._projet.sous_titres
        imposee = resolution_imposee(self._projet)
        self.panneau.charger(
            reglages,
            imposee,
            transcription.masquer_hesitations if transcription else True,
            transcription is not None,
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
        self.bloc_apercu.actualiser_taille()  # format de la vidéo : la zone et la colonne de l'aperçu
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
        """Des mots changés dans le module Transcription, ou des mots importés corrigés (texte, temps,
        fusion, coupe, suppression, hésitations), défont des sous-titres réorganisés à la main : ils
        sont retirés du projet (leurs mots sont déjà redécoupés automatiquement), et la page dit
        lesquels."""
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
        module = transcription is self._projet.transcription  # sinon : des mots importés, corrigés ici
        self._statut_reorganisation(texte_ajustements_defaits(numeros, module), "avertissement")

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

    def _charger_la_lecture(self) -> None:
        """Ce que lit l'aperçu (V3.1, lot 6) : la vidéo choisie dans la zone Source (celle du module
        Transcription, dès son import, ou la vidéo importée), avec son son ; sous une vidéo importée
        muette, ou sans vidéo, la piste son des mots (une prise, ou l'audio du module). Des mots d'un
        autre enregistrement que la vidéo commencent à « La voix commence à ». Une vidéo introuvable
        (déplacée, supprimée) laisse le fond gris et propose de la retrouver."""
        projet = self._projet
        video = video_de_l_apercu(projet)
        audio = audio_des_mots(projet)
        audio = str(audio) if audio is not None and audio.exists() else ""
        chemin, son_de_la_video, introuvable = "", True, ""
        if video is not None:
            if Path(video.chemin).is_file():
                chemin, son_de_la_video = video.chemin, video.son_de_la_video
            else:
                introuvable = video.chemin
        if self.isVisible():  # page cachée : rien n'est ouvert (la lecture se prépare à son affichage)
            self.lecteur.charger(chemin, audio, decalage_des_mots(projet), son_de_la_video)
        self.bloc_apercu.definir_video_possible(bool(chemin))
        self.bloc_apercu.definir_lecture_possible(bool(chemin or audio))  # rien à lire : un fichier SRT seul
        self.bloc_apercu.ligne_introuvable.setVisible(bool(introuvable))
        if introuvable:
            # Le chemin peut passer à la ligne après chaque « \ » ou « / » (3.2.2) : d'un seul tenant, il
            # élargissait la colonne de l'aperçu, et la vidéo n'était plus aux marges du titre.
            self.bloc_apercu.message_video.setText(
                f"Vidéo introuvable : {chemin_a_afficher(introuvable)}. Elle a peut-être été déplacée ou "
                "supprimée (elle n'est pas copiée dans le projet) : l'aperçu montre un fond gris."
            )
        self._actualiser_toile()

    def basculer_lecture(self) -> None:
        """Lecture ou pause (avant même la transcription : la vidéo se regarde dès son import)."""
        self.lecteur.basculer()

    def _erreur_de_lecture(self, message: str) -> None:
        self._afficher(f"Lecture impossible dans l'aperçu : {message}", "erreur", self.statut_lecture)
        self.bloc_apercu.definir_video_possible(False)

    def quitter(self) -> None:
        """La page n'est plus affichée : la lecture s'arrête (et libère les fichiers)."""
        self.lecteur.arreter()

    # --- Préréglages (V2, lot 7) ----------------------------------------------------------------

    def _actualiser_prereglage(self) -> None:
        """Liste des préréglages, avec celui du projet (« (modifié) » s'il s'en écarte) ; dans les
        onglets, la référence des ↺ et des noms en mauve : ce préréglage tel qu'il est enregistré
        (sans lui, le style de départ ; V3.1)."""
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
        self.panneau.definir_reference(bibliotheque.reference(reglages), bibliotheque.nom_de_reference(reglages))

    def _statut_prereglage(self, message: str, role: str = "succes") -> None:
        self._afficher(message, role, self.panneau.statut_prereglage)

    def _demander_nom(self, titre: str, nom: str) -> str | None:
        """Nom d'un nouveau préréglage (remplacé dans les tests)."""
        texte = messages.demander_texte(self.window(), titre, "Nom du préréglage", nom, action="Enregistrer")
        return texte if texte and texte.strip() else None

    def appliquer_prereglage(self, identifiant: str) -> None:
        """Le style du préréglage remplace celui du projet (format, plateforme et vidéo importée ne
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
        if not self._confirmer(
            "Mettre à jour le préréglage",
            f"Mettre à jour « {origine.nom} » avec le style de ce projet ?",
            "Les projets déjà faits gardent leur propre copie du style : ils ne changent pas.",
            "Mettre à jour",
        ):
            return
        bibliotheque.mettre_a_jour(origine.identifiant, style_du_projet(reglages))
        self._projet.sous_titres = replace(reglages, prereglage_nom=origine.nom)
        self._services.projets.enregistrer()
        self._actualiser_prereglage()
        self._statut_prereglage(f"« {origine.nom} » mis à jour.")

    def _confirmer(self, titre: str, question: str, precision: str, action: str) -> bool:
        """Pose la question (remplacée dans les tests)."""
        return messages.confirmer(self.window(), titre, question, precision, action=action)

    def gerer_prereglages(self) -> None:
        """Menu ⋯ : la fenêtre « Préréglages de sous-titres » ; « Appliquer » y met un préréglage sur le projet."""
        actuel = self._projet.sous_titres.prereglage if self._projet is not None else ""
        fenetre = DialoguePrereglages(self._services, self.window(), actuel, projet_ouvert=self._projet is not None)
        fenetre.exec()
        if fenetre.prereglage_choisi:
            self.appliquer_prereglage(fenetre.prereglage_choisi)
        else:
            self._actualiser_prereglage()

    # --- Vidéo : retrouvée, ou importée dans la zone Source (V3.1) ------------------------------

    def _demander_video(self, titre: str, proposition: str) -> Path | None:
        dossier = str(Path(proposition).parent) if proposition else str(dossier_documents())
        choix, _ = QFileDialog.getOpenFileName(self, titre, dossier, f"{FILTRE_VIDEOS};;{FILTRE_FICHIERS}")
        return Path(choix) if choix else None

    def retrouver_la_video(self) -> None:
        """« Retrouver la vidéo… » : la vidéo de l'aperçu (celle du module Transcription, ou la vidéo
        importée) a été déplacée."""
        projet = self._projet
        video = video_de_l_apercu(projet) if projet is not None else None
        if video is None:
            return
        chemin = self._demander_video("Retrouver la vidéo", video.chemin)
        if chemin is None:
            return
        if video.importee:
            apercu = projet.sous_titres.apercu
            projet.sous_titres = replace(projet.sous_titres, apercu=replace(apercu, chemin=str(chemin)))
        else:
            projet.transcription.source = str(chemin)
        self._services.projets.enregistrer()
        self.rafraichir()

    def choisir_video_apercu(self) -> None:
        """« Choisir une vidéo… » (onglet « Vidéo ou audio », Importée) : par exemple le montage exporté
        de Premiere Pro ; elle remplace la précédente, et devient la vidéo de l'aperçu (et de l'export)."""
        if self._projet is None:
            return
        apercu = self._projet.sous_titres.apercu
        chemin = self._demander_video("Choisir une vidéo", apercu.chemin)
        if chemin is None:
            return
        if self._definir_video_apercu(VideoApercu(str(chemin), apercu.decalage_s, 0, 0, apercu.son_de_la_video), choisie=True):
            self._infos_video.lire(chemin)  # sa résolution fixera le format

    def _definir_video_apercu(self, apercu: VideoApercu, choisie: bool = False) -> bool:
        """La vidéo importée change (`choisie` : elle devient aussi la vidéo de l'aperçu). Son format
        s'impose : s'il défait un sous-titre réorganisé à la main, la question vient d'abord.
        Renvoie True si c'est fait."""
        projet = self._projet
        reglages = replace(projet.sous_titres, apercu=apercu)
        avant = projet.sources.video
        if choisie:
            projet.sources.video = SOURCE_IMPORTEE
        if not confirmer_reglage(self.window(), self._services, projet, reglages=reglages):
            projet.sources.video = avant
            self._actualiser_la_source()
            return False
        projet.sous_titres = reglages
        self._services.projets.enregistrer()
        self.rafraichir()
        return True

    def _infos_video_lues(self, infos: dict) -> None:
        """Résolution de la vidéo importée (zone Source) : elle impose son format, quand elle est choisie."""
        if self._projet is None or not self._projet.sous_titres.apercu.chemin:
            return
        resolution_lue = resolution_video(infos)
        if resolution_lue is None:
            return
        apercu = self._projet.sous_titres.apercu
        self._definir_video_apercu(replace(apercu, largeur=resolution_lue[0], hauteur=resolution_lue[1]))

    def retirer_video_apercu(self) -> None:
        """« Retirer » la vidéo importée (« La voix commence à » reste : il sert aussi avec la vidéo du
        module Transcription)."""
        if self._projet is None:
            return
        self._definir_video_apercu(VideoApercu(decalage_s=self._projet.sous_titres.apercu.decalage_s))

    def _video_apercu_change(self) -> None:
        """« La voix commence à », ou « Son de la vidéo » : seule la lecture change (et les exports)."""
        if self._projet is None:
            return
        decalage, son = round(self.source.decalage.value(), 2), self.source.son_video.isChecked()
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
        """Double-clic sur un bloc de la frise : « Corriger les mots », sur son premier mot (dans le
        module Transcription, ou dans la fenêtre de correction des mots importés)."""
        mots = self.transcription
        if not 0 <= index < len(self.sous_titres) or mots is None:
            return
        debut = self.mots[self.sous_titres[index].premier_mot].debut
        if mots is self._projet.transcription:
            self.corriger_demande.emit(debut)
            return
        rang = next((i for i, mot in enumerate(mots.mots) if mot.debut >= debut - 1e-3), -1)
        self.corriger_les_mots(rang)

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
        """La prise est transcrite (moment de chaque mot), puis les mots sont calés sur son script. Ils
        deviennent les mots importés, choisis (V3.1, lot 6) : ceux du module Transcription restent ;
        un import précédent est remplacé, après confirmation s'il avait des retouches."""
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
        actuelle = projet.sous_titres_importes
        if a_des_retouches(actuelle) and not self._confirmer_remplacement(actuelle):
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
        self._occuper(True)
        self._afficher(f"Transcription de « {prise.nom} », puis calage sur son script…", "secondaire")

        def fin(resultat) -> None:
            self._occuper(False)
            if self._projet is not projet:
                return
            if not resultat.mots:
                self._afficher("Google n'a renvoyé aucun mot : la prise est-elle silencieuse ?", "avertissement")
                return
            fini = terminer_transcription(self._services, transcription, options, resultat)  # mots importés, choisis
            self.tableau.clearSelection()
            self._afficher(f"Sous-titres créés depuis « {prise.nom} » : {len(fini.mots)} mots calés sur le script.", "succes")
            self.rafraichir()
            self._au_debut()

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Sous-titres impossibles : {message_erreur(erreur)}", "erreur")

        taches.lancer(lambda: transcrire_source(adaptateur, wav, options, f"{projet.nom} - {prise.nom}"), fin, echec)

    def _confirmer_remplacement(self, actuelle: Transcription) -> bool:
        """Un nouvel import (prise ou fichier SRT) remplace l'import précédent, qui a des retouches."""
        retouches = []
        if actuelle.corrigee:
            retouches.append("des mots corrigés")
        if actuelle.ajustements_sous_titres:
            retouches.append("des sous-titres réorganisés à la main")
        return messages.confirmer(
            self.window(),
            "Importer des sous-titres",
            "Remplacer les mots importés ?",
            f"Les mots importés de « {Path(actuelle.source).name or actuelle.source} » ont des retouches "
            f"({' et '.join(retouches)}) : elles seront perdues. Les mots du module Transcription, eux, ne changent pas.",
            action="Remplacer",
        )

    def _occuper(self, occupe: bool) -> None:
        """Pendant la création des sous-titres d'une prise : le cercle tourne dans « Créer les
        sous-titres » (V3.1), qui garde son aspect ; la liste des prises est grisée."""
        self._occupe = occupe
        a_prises = bool(self._projet and self._projet.prises)
        montrer_occupe(self.bouton_creer, occupe)
        self.bouton_creer.setEnabled(occupe or a_prises)
        self.prises.setEnabled(not occupe and a_prises)

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
        # Sur le temps de la vidéo (« La voix commence à ») : le fichier se pose sur elle.
        sous_titres, _mots = decales(self.sous_titres, self.mots, decalage_des_mots(self._projet))
        try:
            ecrire_srt(chemin, sous_titres)
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
        """Les sous-titres tels que l'aperçu les montre : mêmes réglages, même taille de vidéo, sur le
        temps de la vidéo (V3.1 : des mots d'un autre enregistrement commencent à « La voix commence
        à »)."""
        if self._projet is None or self._calcul is None or not self.sous_titres:
            return None
        moteur = self._calcul.moteur
        sous_titres, mots = decales(self.sous_titres, self.mots, decalage_des_mots(self._projet))
        return SousTitresAExporter(self._calcul.reglages, moteur.largeur, moteur.hauteur, sous_titres, mots, self._nom_du_style())

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
