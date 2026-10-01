"""Atelier des sous-titres (§7, §3.3, §8.1) : des mots horodatés au fichier SRT.

1. Mots : ceux de la transcription du projet (vidéo transcrite dans le module Transcription), ou
   ceux d'une prise de voix : « Créer les sous-titres » transcrit la prise puis cale les mots sur
   son script (orthographe exacte). Les mots se corrigent dans le module Transcription.
2. Réglages : découpage (caractères, mots, lignes, ponctuation, durée minimale), texte affiché
   (majuscules, ponctuation, hésitations) et écran (format, zone de sécurité, marge maximum,
   taille du texte) : les sous-titres sont recalculés à chaque changement.
3. Sous-titres : la liste, écoutable (le sous-titre en cours s'affiche en grand) ; ceux où un mot
   a dû être rapetissé sont signalés en orange. Export SRT pour Premiere Pro.
4. Réorganiser à la main (V1.1) : sur le sous-titre choisi, monter son premier mot, descendre son
   dernier mot, le couper, le fusionner avec le suivant, ou revenir au découpage automatique. Les
   réglages du découpage s'appliquent toujours (une action qui ne les respecte pas est refusée,
   avec la raison) ; un réglage qui défait un ajustement demande d'abord (sous_titres_du_projet.py).
"""

from __future__ import annotations

import bisect
import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)

from ....chemins import dossier_documents
from ....fournisseurs.stt import MODE_VERBATIM
from ....modeles_charges import SOUS_TITRES
from ....projets import FICHIER_AUDIO, ErreurProjet, Projet, nom_de_dossier
from ....script import texte_brut
from ....services import Services
from ....sous_titres import (
    ESPACE_INSECABLE,
    LIMITES,
    NOMS_FORMATS,
    PLATEFORMES,
    MotAffiche,
    ReglagesSousTitres,
    Reorganisation,
    SousTitre,
    ecrire_srt,
    retablir_automatique,
    texte_ajustements_defaits,
)
# Les actions à la main, calculées sans interface (même nom que les méthodes de la page qui les appellent).
from ....sous_titres import couper_avant as calcul_couper
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
from ....transcription import Transcription
from ... import taches
from ...composants.choix_voix import choisir
from ...composants.flux import DispositionFlux
from ...composants.elements import (
    bloc,
    bouton,
    case_a_cocher,
    champ_decimal,
    champ_entier,
    glissiere,
    info,
    libelle,
    liste_deroulante,
    minutes_secondes,
)
from ...composants.lecteur import Lecteur
from ...composants.montant_label import MontantLabel
from ...composants.tableau import Colonne, Tableau
from ...connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ...icones import icone
from ...sous_titres_du_projet import (
    Calcul,
    ajustements,
    calculer as calculer_du_projet,
    confirmer_reglage,
    ranger_ajustements,
)
from ...theme import Couleurs, Dimensions, Espacements, qcolor
from ..base import Page
from ..transcription.atelier import description_source

journal = logging.getLogger(__name__)

TITRE = "Sous-titres"
SOUS_TITRE = "Découpage des sous-titres et export SRT, depuis une prise de voix ou une transcription."
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
    corriger_demande = Signal()  # « Corriger les mots » : ouvrir le module Transcription

    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="sous-titres")
        self._services = services
        self._projet: Projet | None = None
        self._occupe = False
        self.mots: list[MotAffiche] = []
        self.sous_titres: list[SousTitre] = []
        self._calcul: Calcul | None = None
        self._debuts: list[float] = []
        self.lecteur = Lecteur(self)

        # --- Mots des sous-titres ---
        cadre, d = bloc("Mots des sous-titres")
        self.texte_source = libelle("", "secondaire")
        d.addWidget(self.texte_source)
        ligne = QHBoxLayout()
        self.bouton_corriger = bouton(
            "Corriger les mots", variante="contour", nom_icone="pencil", action=lambda: self.corriger_demande.emit()
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
        d.addWidget(self.statut)
        self.contenu.addWidget(cadre)

        # --- Réglages ---
        self.contenu.addWidget(self._bloc_reglages())

        # --- Sous-titres ---
        self.cadre_sous_titres, d = bloc("Sous-titres")
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
        self.apercu = libelle("", "apercu-sous-titre")
        self.apercu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        d.addWidget(self.apercu)
        self._zone_reorganiser(d)
        self.tableau = self._tableau()
        d.addWidget(self.tableau)
        self._actualiser_reorganisation()  # aucun sous-titre choisi : actions désactivées
        export = QHBoxLayout()
        export.setSpacing(Espacements.M)
        self.bouton_exporter = bouton("Exporter en SRT…", variante="principal", nom_icone="download", action=self.exporter_srt)
        export.addWidget(self.bouton_exporter)
        export.addWidget(
            info("Texte et temps de chaque sous-titre, sans style : pour Premiere Pro et la plupart des logiciels.", "legende"), 1
        )
        d.addLayout(export)
        self.statut_export = libelle("", "secondaire")
        d.addWidget(self.statut_export)
        self.contenu.addWidget(self.cadre_sous_titres)

        self.lecteur.etat_change.connect(lambda _chemin, _lecture: self._etat_lecture())
        self.lecteur.position_change.connect(self._position_lue)
        services.projets.abonner(self._projet_change)
        services.prix.abonner(self._mettre_a_jour_estimation)
        self._projet_change(services.projets.projet)

    def _bloc_reglages(self):
        cadre, d = bloc("Réglages")
        colonnes = QHBoxLayout()
        colonnes.setSpacing(Espacements.XL)

        self.caracteres = champ_entier(*LIMITES["caracteres_max"], info="Nombre maximum de caractères par sous-titre, espaces comprises")
        self.mots_max = champ_entier(*LIMITES["mots_max"], info="Nombre maximum de mots par sous-titre")
        self.lignes = champ_entier(*LIMITES["lignes_max"], info="Nombre maximum de lignes (1 ou 2) : jamais dépassé")
        self.duree_min = champ_decimal(*LIMITES["duree_min_s"], 0.1, 1, " s", "Durée minimale d'affichage d'un sous-titre")
        colonnes.addLayout(
            self._grille(
                "Découpage",
                (("Caractères au plus", self.caracteres), ("Mots au plus", self.mots_max), ("Lignes au plus", self.lignes), ("Durée minimale", self.duree_min)),
            ),
            0,  # colonne de champs de nombre : sa largeur naturelle ; le reste va aux listes de l'écran
        )

        self.format = liste_deroulante("Format de la vidéo (les tailles sont proportionnelles à sa hauteur)")
        for identifiant, nom in NOMS_FORMATS.items():
            self.format.addItem(nom, identifiant)
        self.plateforme = liste_deroulante("Zone de sécurité : les bords que l'interface de la plateforme recouvre")
        for plateforme in PLATEFORMES:
            self.plateforme.addItem(plateforme.nom, plateforme.identifiant)
            if plateforme.source:
                self.plateforme.setItemData(self.plateforme.count() - 1, f"Source : {plateforme.source}", Qt.ItemDataRole.ToolTipRole)
        self.marge = champ_decimal(*LIMITES["marge_max_pct"], 0.5, 1, " %", "Marge maximum de chaque bord : le texte ne la dépasse jamais")
        self.taille = champ_decimal(*LIMITES["taille_pct"], 0.1, 1, " %", "Taille du texte, en % de la hauteur de la vidéo")
        colonnes.addLayout(
            self._grille(
                "Écran",
                (("Format", self.format), ("Zone de sécurité", self.plateforme), ("Marge maximum", self.marge), ("Taille du texte", self.taille)),
            ),
            1,
        )
        d.addLayout(colonnes)

        zone, self.couper_ponctuation = case_a_cocher(
            "Couper de préférence après la ponctuation", "Une fin de phrase termine alors toujours le sous-titre."
        )
        d.addWidget(zone)
        zone, self.majuscules = case_a_cocher("Tout en majuscules", "Affichage seulement : le texte des mots ne change pas.")
        d.addWidget(zone)
        zone, self.ponctuation = case_a_cocher("Afficher la ponctuation")
        d.addWidget(zone)
        self.zone_masquer, self.masquer = case_a_cocher(
            "Masquer les hésitations", "« euh », « hum »… (même réglage que dans le module Transcription)."
        )
        d.addWidget(self.zone_masquer)
        self.infos_ecran = info()
        d.addWidget(self.infos_ecran)

        for champ in (self.caracteres, self.mots_max, self.lignes, self.duree_min, self.marge, self.taille):
            champ.valueChanged.connect(lambda _valeur: self._reglage_change())
        for liste in (self.format, self.plateforme):
            liste.currentIndexChanged.connect(lambda _index: self._reglage_change())
        for case in (self.couper_ponctuation, self.majuscules, self.ponctuation):
            case.toggled.connect(lambda _coche: self._reglage_change())
        self.masquer.toggled.connect(self._masquer_change)
        return cadre

    @staticmethod
    def _grille(titre: str, lignes) -> QVBoxLayout:
        colonne = QVBoxLayout()
        colonne.setSpacing(Espacements.S)
        colonne.addWidget(libelle(titre, "intitule"))
        grille = QGridLayout()
        grille.setHorizontalSpacing(Espacements.M)
        grille.setVerticalSpacing(Espacements.S)
        for rang, (texte, element) in enumerate(lignes):
            grille.addWidget(libelle(texte, "legende", retour_a_la_ligne=False), rang, 0)
            grille.addWidget(element, rang, 1, Qt.AlignmentFlag.AlignLeft)
        grille.setColumnStretch(1, 1)
        colonne.addLayout(grille)
        colonne.addStretch(1)
        return colonne

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
        self.lecteur.arreter()
        self._projet = projet
        if projet is None:
            self._services.modeles.choisir(SOUS_TITRES, None)
            return
        self.titre.setText(f"{TITRE} / {projet.nom}")
        self._afficher("", "secondaire")
        self.statut_export.clear()
        self._statut_reorganisation("")
        self.rafraichir()

    def showEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # Les mots ou les prises ont pu changer dans un autre module.
        super().showEvent(evenement)
        if self._projet is not None and not self._occupe:
            self.rafraichir()

    def _afficher(self, message: str, role: str, etiquette=None) -> None:
        etiquette = etiquette or self.statut
        etiquette.setText(message)
        etiquette.setProperty("role", role)
        etiquette.style().unpolish(etiquette)
        etiquette.style().polish(etiquette)

    # --- Affichage ---------------------------------------------------------------------------

    def rafraichir(self) -> None:
        """Met toute la page à jour : source des mots, prises, réglages, sous-titres."""
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
        reglages = self._projet.sous_titres
        transcription = self.transcription
        elements = (
            self.caracteres, self.mots_max, self.duree_min, self.marge, self.taille, self.lignes, self.format,
            self.plateforme, self.couper_ponctuation, self.majuscules, self.ponctuation, self.masquer,
        )
        for element in elements:
            element.blockSignals(True)
        self.caracteres.setValue(reglages.caracteres_max)
        self.mots_max.setValue(reglages.mots_max)
        self.duree_min.setValue(reglages.duree_min_s)
        self.marge.setValue(reglages.marge_max_pct)
        self.taille.setValue(reglages.taille_pct)
        self.lignes.setValue(reglages.lignes_max)
        choisir(self.format, reglages.format)
        choisir(self.plateforme, reglages.plateforme)
        self.couper_ponctuation.setChecked(reglages.couper_sur_ponctuation)
        self.majuscules.setChecked(reglages.majuscules)
        self.ponctuation.setChecked(reglages.ponctuation)
        self.masquer.setChecked(transcription.masquer_hesitations if transcription else True)
        self.zone_masquer.setEnabled(transcription is not None)
        for element in elements:
            element.blockSignals(False)

    def reglages(self) -> ReglagesSousTitres:
        """Réglages tels que choisis dans la page."""
        return ReglagesSousTitres(
            caracteres_max=self.caracteres.value(),
            mots_max=self.mots_max.value(),
            lignes_max=self.lignes.value(),
            couper_sur_ponctuation=self.couper_ponctuation.isChecked(),
            duree_min_s=round(self.duree_min.value(), 2),
            majuscules=self.majuscules.isChecked(),
            ponctuation=self.ponctuation.isChecked(),
            format=self.format.currentData(),
            plateforme=self.plateforme.currentData(),
            marge_max_pct=round(self.marge.value(), 2),
            taille_pct=round(self.taille.value(), 2),
        )

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
        self.calculer()

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
        à la main, puis les affiche."""
        calcul = calculer_du_projet(self._services, self._projet)
        self._calcul = calcul
        self.mots, self.sous_titres = calcul.decoupage.mots, calcul.decoupage.sous_titres
        self._debuts = [s.debut for s in self.sous_titres]
        if calcul.decoupage.defaits:
            self._retirer_les_ajustements_defaits(calcul)
        ecran_video, langue = calcul.ecran, calcul.langue
        typographie = " ; typographie française : espace insécable avant « ! ? : ; »" if langue.startswith("fr") else ""
        self.infos_ecran.setText(
            f"Vidéo {ecran_video.largeur} × {ecran_video.hauteur}, texte de {round(ecran_video.taille_texte)} px (police Inter) : "
            f"une ligne tient en {round(ecran_video.largeur_securite)} px dans la zone de sécurité, "
            f"{round(ecran_video.largeur_max)} px au plus jusqu'à la marge maximum{typographie}."
        )
        self._remplir_tableau()
        self.cadre_sous_titres.setVisible(bool(self.sous_titres))
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
        self._montrer(self.tableau.currentRow() if self.tableau.currentRow() >= 0 else 0)
        self._actualiser_reorganisation()
        self._etat_lecture()

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

    # --- Sous-titre choisi / en cours de lecture ---------------------------------------------

    def _index_au_temps(self, temps: float) -> int:
        index = bisect.bisect_right(self._debuts, temps) - 1
        if 0 <= index < len(self.sous_titres) and temps < self.sous_titres[index].fin:
            return index
        return -1

    def _montrer(self, index: int) -> None:
        """Aperçu : le sous-titre, tel qu'il s'affichera (lignes, majuscules…)."""
        sous_titre = self.sous_titres[index] if 0 <= index < len(self.sous_titres) else None
        self.apercu.setText(sous_titre.texte if sous_titre else "")
        self.apercu.setProperty("signale", bool(sous_titre and sous_titre.signale))
        self.apercu.style().unpolish(self.apercu)
        self.apercu.style().polish(self.apercu)

    def choisir_sous_titre(self, index: int) -> None:
        """Clic sur un sous-titre : il est montré ; la lecture s'y place si elle est en cours."""
        if not 0 <= index < len(self.sous_titres):
            return
        self.tableau.selectRow(index)
        self._montrer(index)
        self._actualiser_reorganisation()
        chemin = self._chemin_audio()
        if chemin is not None and self.lecteur.chemin == str(chemin):
            self.lecteur.aller_a(round(self.sous_titres[index].debut * 1000))

    # --- Lecture -----------------------------------------------------------------------------

    def _chemin_audio(self) -> Path | None:
        transcription = self.transcription
        if self._projet is None or transcription is None or not transcription.audio:
            return None
        return self._projet.chemin(transcription.audio)

    def basculer_lecture(self) -> None:
        chemin = self._chemin_audio()
        if chemin is None or not chemin.exists():
            self._afficher("Piste son introuvable dans le dossier du projet.", "erreur", self.statut_export)
            return
        if self.lecteur.chemin == str(chemin):
            self.lecteur.basculer(chemin)
            return
        choisi = self.tableau.currentRow()
        depart = round(self.sous_titres[choisi].debut * 1000) if 0 <= choisi < len(self.sous_titres) else 0
        self.lecteur.jouer_depuis(chemin, depart)

    def _etat_lecture(self) -> None:
        chemin = self._chemin_audio()
        en_lecture = chemin is not None and self.lecteur.en_lecture(chemin)
        self.bouton_lecture.setIcon(icone("pause" if en_lecture else "play", Couleurs.ACCENT_SURVOL, rempli=True))
        self.bouton_lecture.setToolTip("Pause" if en_lecture else "Écouter avec les sous-titres")

    def _position_lue(self, position_ms: int, duree_ms: int) -> None:
        chemin = self._chemin_audio()
        if chemin is None or self.lecteur.chemin != str(chemin):
            return
        if not self.position.isSliderDown():
            self.position.setRange(0, max(duree_ms, 0))
            self.position.setValue(position_ms)
        self.temps.setText(f"{minutes_secondes(position_ms / 1000)} / {minutes_secondes(duree_ms / 1000)}")
        index = self._index_au_temps(position_ms / 1000)
        self._montrer(index)
        if index >= 0 and index != self.tableau.currentRow():
            self.tableau.selectRow(index)
            self.tableau.scrollToItem(self.tableau.item(index, 0))
            self._actualiser_reorganisation()

    def quitter(self) -> None:
        """La page n'est plus affichée : la lecture s'arrête (et libère le fichier audio)."""
        self.lecteur.arreter()

    # --- Réorganiser à la main (V1.1) ---------------------------------------------------------

    def _statut_reorganisation(self, message: str, role: str = "secondaire") -> None:
        self._afficher(message, role, self.statut_ajustements)
        self.statut_ajustements.setVisible(bool(message))

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

    def _reorganiser(self, faire, message: str) -> None:
        """Applique une action à la main au sous-titre choisi ; si elle ne respecte pas les règles,
        rien ne change et la raison s'affiche."""
        index, transcription = self._choisi(), self.transcription
        if index < 0 or transcription is None or self._calcul is None:
            return
        resultat: Reorganisation = faire(index, self._calcul)
        if not resultat.possible:
            self._statut_reorganisation(resultat.message, "erreur")
            return
        ranger_ajustements(transcription, resultat.ajustements)
        self._services.projets.enregistrer()
        self.calculer()
        self.choisir_sous_titre(min(resultat.choisi, len(self.sous_titres) - 1))
        self._statut_reorganisation(message, "succes")

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
        self.lecteur.arreter()
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

        def echec(erreur: Exception) -> None:
            self._occuper(False)
            self._afficher(f"Sous-titres impossibles : {message_erreur(erreur)}", "erreur")

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
