"""Atelier des sous-titres (§7, §3.3, §8.1) : des mots horodatés au fichier SRT.

1. Mots : ceux de la transcription du projet (vidéo transcrite dans le module Transcription), ou
   ceux d'une prise de voix : « Créer les sous-titres » transcrit la prise puis cale les mots sur
   son script (orthographe exacte). Les mots se corrigent dans le module Transcription.
2. Réglages : découpage (caractères, mots, lignes, ponctuation, durée minimale), texte affiché
   (majuscules, ponctuation, hésitations) et écran (format, zone de sécurité, marge maximum,
   taille du texte) : les sous-titres sont recalculés à chaque changement.
3. Sous-titres : la liste, écoutable (le sous-titre en cours s'affiche en grand) ; ceux où un mot
   a dû être rapetissé sont signalés en orange. Export SRT pour Premiere Pro.
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
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)

from ....chemins import dossier_documents
from ....fournisseurs.stt import MODE_VERBATIM
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
    SousTitre,
    creer_sous_titres,
    ecran,
    ecrire_srt,
)
from ....stt import (
    MODELE_PAR_DEFAUT,
    Options,
    estimer_cout,
    hesitations,
    langue_de,
    terminer_transcription,
    transcription_de_prise,
    transcrire_source,
)
from ....transcription import Transcription, resolution_video
from ... import taches
from ...composants.choix_voix import choisir
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
from ...mesure_texte import mesure_sous_titres
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
    if sous_titre.trop_large:
        return "Trop large, même réduit : raccourcis ce mot"
    if sous_titre.echelle < 1:
        return f"Mot rapetissé à {round(sous_titre.echelle * 100)} %"
    return ""


class AtelierSousTitres(Page):
    corriger_demande = Signal()  # « Corriger les mots » : ouvrir le module Transcription

    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="sous-titres")
        self._services = services
        self._projet: Projet | None = None
        self._occupe = False
        self.mots: list[MotAffiche] = []
        self.sous_titres: list[SousTitre] = []
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
        self.tableau = self._tableau()
        d.addWidget(self.tableau)
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
            return
        self.titre.setText(f"{TITRE} / {projet.nom}")
        self._afficher("", "secondaire")
        self.statut_export.clear()
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
        self._projet.sous_titres = self.reglages()
        self._services.projets.enregistrer()
        self.calculer()

    def _masquer_change(self, masquer: bool) -> None:
        transcription = self.transcription
        if transcription is None:
            return
        transcription.masquer_hesitations = masquer
        self._services.projets.enregistrer()
        self.calculer()

    def calculer(self) -> None:
        """(Re)calcule les sous-titres d'après les mots et les réglages, puis les affiche."""
        transcription, reglages = self.transcription, self._projet.sous_titres
        resolution_source = resolution_video(transcription.infos) if transcription else None
        ecran_video = ecran(reglages, resolution_source)
        mots = transcription.mots if transcription is not None and transcription.horodatee else []
        langue = langue_de(transcription, self._projet)
        self.mots, self.sous_titres = creer_sous_titres(
            mots,
            reglages,
            langue,
            ecran_video,
            mesure_sous_titres(ecran_video),
            hesitations(self._services, transcription),
            transcription.masquer_hesitations if transcription else True,
            transcription.duree_s if transcription and transcription.duree_s else None,
        )
        self._debuts = [s.debut for s in self.sous_titres]
        typographie = " ; typographie française : espace insécable avant « ! ? : ; »" if langue.startswith("fr") else ""
        self.infos_ecran.setText(
            f"Vidéo {ecran_video.largeur} × {ecran_video.hauteur}, texte de {round(ecran_video.taille_texte)} px (police Inter) : "
            f"une ligne tient en {round(ecran_video.largeur_securite)} px dans la zone de sécurité, "
            f"{round(ecran_video.largeur_max)} px au plus jusqu'à la marge maximum{typographie}."
        )
        self._remplir_tableau()
        self.cadre_sous_titres.setVisible(bool(self.sous_titres))
        signales = sum(1 for s in self.sous_titres if s.signale)
        morceaux = [f"{len(self.sous_titres)} sous-titres", f"{len(self.mots)} mots"]
        if self.sous_titres:
            morceaux.append(minutes_secondes(self.sous_titres[-1].fin))
        if signales:
            morceaux.append(f"{signales} signalé{'s' if signales > 1 else ''} en orange (mot rapetissé pour tenir dans l'écran)")
        self.resume.setText("  ·  ".join(morceaux))
        self.bouton_exporter.setEnabled(bool(self.sous_titres))
        self._montrer(self.tableau.currentRow() if self.tableau.currentRow() >= 0 else 0)
        self._etat_lecture()

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

    def quitter(self) -> None:
        """La page n'est plus affichée : la lecture s'arrête (et libère le fichier audio)."""
        self.lecteur.arreter()

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
        boite.setInformativeText(
            f"Les sous-titres viennent aujourd'hui de « {Path(actuelle.source).name or actuelle.source} ». "
            "Ses mots et ses corrections seront remplacés par ceux de la prise."
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
