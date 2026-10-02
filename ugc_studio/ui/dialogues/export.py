"""Fenêtres d'export (V3, §8.5) : une seule fenêtre par export, toujours obligatoire.

1. Réglages en haut : calque transparent (lot 1 : images par seconde d'un projet sans vidéo) ou
   vidéo avec sous-titres (lot 2 : format, codec, débit) ; pour une vidéo HDR, « Convertir en SDR »
   (lot 3 : sinon, le HDR est gardé) ; puis dossier et nom.
2. Dessous, le **résumé avant export**, mis à jour à chaque réglage changé : la source et l'export
   côte à côte ; toute valeur différente de la source est en mauve (comme les valeurs modifiées des
   variantes A/B), les avertissements en orange, ce qui empêche l'export en rouge.
3. « Exporter » lance l'export dans la même fenêtre : l'étape en cours et sa barre d'avancement, le
   temps restant estimé, et « Arrêter » (rien n'est gardé d'un export arrêté). À la fin : la durée de
   l'export, le nom et le poids du fichier, « Ouvrir le dossier » (et « Lire la vidéo »).

Les deux fenêtres partagent tout cela (DialogueExport) ; chacune ajoute ses réglages, son résumé et
son export. Le choix du dossier (celui de la vidéo source, celui du projet, ou un autre), la
fréquence d'un projet sans vidéo et les réglages de la vidéo sont retenus (préférences).
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
from ...exports.ffmpeg import NormeHDR, analyser, ffmpeg_a_preparer, norme_hdr, preparer_ffmpeg, programme_ffmpeg
from ...exports.plan import (
    DOSSIER_AUTRE,
    DOSSIER_PROJET,
    DOSSIER_SOURCE,
    EXTENSION_CALQUE,
    SUFFIXE_CALQUE,
    PlanCalque,
    Resume,
    Source,
    SousTitresAExporter,
    debit_lisible,
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
from ...exports.video import (
    CODECS,
    CODECS_POSSIBLES,
    CONTENEURS,
    DEBIT_CONSEILLE,
    DEBIT_IDENTIQUE,
    DEBIT_PERSONNALISE,
    DEBIT_PERSONNALISE_MAX,
    DEBIT_PERSONNALISE_MIN,
    EXTENSIONS,
    H264,
    MP4,
    PRORES,
    SUFFIXE_VIDEO,
    PlanVideo,
    codecs_possibles,
    debit_conseille,
    debit_hdr_de_youtube,
    debit_par_defaut,
    debit_prores,
    plan_video,
    resume_video,
)
from ...projets import Projet
from ...services import Services
from .. import taches
from ..composants.barre_avancement import BarreAvancement
from ..composants.choix import ChoixEnBoutons
from ..composants.conseils import entete_de_fenetre
from ..composants.defilement import zone_defilante
from ..composants.elements import Info, bouton, case_a_cocher, champ_decimal, info, libelle, libelle_abrege
from ..composants.tableau import Colonne, Tableau
from ..ouvrir import montrer_dans_l_explorateur, ouvrir_fichier
from ..theme import Couleurs, Dimensions, Espacements, Hauteurs, qcolor

journal = logging.getLogger(__name__)

PREF_DOSSIER = "export_dossier"  # « source », « projet » ou « autre » (les deux exports)
PREF_DOSSIER_AUTRE = "export_dossier_autre"  # le dernier dossier choisi avec « Changer… »
PREF_FREQUENCE = "export_calque_frequence"  # projet sans vidéo : « apercu », « 30 », « 60 » ou « autre »
PREF_FREQUENCE_LIBRE = "export_calque_frequence_libre"
PREF_CONTENEUR = "export_video_conteneur"  # « mp4 », « mov », « mkv »
PREF_CODEC = "export_video_codec"  # « h264 », « h265 », « prores »
PREF_DEBIT = "export_video_debit"  # « identique », « conseille », « personnalise »
PREF_DEBIT_PERSONNALISE = "export_video_debit_personnalise"  # en Mb/s

FREQUENCE_APERCU = "apercu"
FREQUENCE_LIBRE = "autre"
FREQUENCES_PROPOSEES = {"30": Fraction(30), "60": Fraction(60)}

# Les noms des lignes (« Images par seconde ») restent toujours en entier ; s'il manque de la place,
# ce sont les colonnes Source et Export qui se resserrent (texte abrégé, complet au survol).
COLONNES_RESUME = (
    Colonne(""),
    Colonne("Source", texte=True),
    Colonne("Export", texte=True, etiree=True),
)
RESTE_APRES_S = 1.0  # le temps restant s'affiche après une seconde (avant, l'estimation serait fausse)


def _changer_de_role(etiquette, role: str) -> None:
    etiquette.setProperty("role", role)
    etiquette.style().unpolish(etiquette)
    etiquette.style().polish(etiquette)


class DialogueExport(QDialog):
    """Ce que les fenêtres d'export ont en commun. Une fenêtre fille définit ses réglages
    (_ajouter_les_reglages), son résumé (plan, resume) et son export (_creer_l_export)."""

    TITRE = ""
    PAGE_CONSEILS = ""
    INFO = ""
    SUFFIXE = ""  # nom proposé : « Sérum Glowzy (calque) »
    ENREGISTRE = ""  # « Calque enregistré », « Vidéo enregistrée »
    AVEC_LECTURE = False  # bouton « Lire la vidéo » à la fin

    def __init__(self, services: Services, projet: Projet, contenu: SousTitresAExporter, parent: QWidget | None = None):
        super().__init__(parent)
        self._services, self._projet, self._contenu = services, projet, contenu
        self._preferences = services.preferences
        self._ffmpeg = programme_ffmpeg()  # None au premier export d'une version : FFmpeg est à recopier
        self._ffmpeg_en_preparation = False
        self._erreur_ffmpeg = ""
        self.source: Source = source_du_projet(projet)
        self.analyse_finie = False
        self._autre = Path(self._preferences.lire(PREF_DOSSIER_AUTRE, "") or projet.dossier)
        self._export = None  # export en cours (ExportDuCalque, ExportVideo)
        self._debut_etape: float | None = None
        self._nom_etape = ""
        self._etape_finale = True
        self._une_seule_etape = True
        self.fichier: Path | None = None  # le fichier écrit
        self.dessin_s = 0.0  # export fini : temps passé à dessiner les images (autotest, journal)
        self.images_dessinees = 0
        self.duree_s: float | None = None
        self._ouvert = True
        self.setWindowTitle(self.TITRE)
        self.setMinimumWidth(Dimensions.DIALOGUE_LARGEUR)
        self.resize(Dimensions.DIALOGUE_EXPORT_LARGEUR, Dimensions.DIALOGUE_EXPORT_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre(self.TITRE, self.PAGE_CONSEILS))
        disposition.addWidget(info(self.INFO, "secondaire"))
        zone, contenu_zone = zone_defilante()
        contenu_zone.setSpacing(Espacements.L)
        self.reglages = self._zone_reglages()
        contenu_zone.addWidget(self.reglages)
        contenu_zone.addWidget(libelle("Résumé avant export", "intitule"))
        self.etat_analyse = libelle("", "legende")
        self.etat_analyse.hide()
        contenu_zone.addWidget(self.etat_analyse)
        self.tableau = Tableau(COLONNES_RESUME, Hauteurs.LIGNE_RESUME)
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
        self.bouton_lire = bouton("Lire la vidéo", nom_icone="play", action=self.lire_la_video)
        self.bouton_lire.hide()
        boutons.addWidget(self.bouton_lire)
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
        grille.setVerticalSpacing(Espacements.S)
        grille.setColumnStretch(1, 1)
        rang = self._ajouter_les_reglages(grille)
        rang = self._ajouter_la_ligne_hdr(grille, rang)

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
        self.nom = QLineEdit(nom_propose(self.source, self._projet, self.SUFFIXE))
        self.nom.setPlaceholderText("Nom du fichier")
        self.nom.textChanged.connect(lambda _texte: self._actualiser())
        ligne.addWidget(self.nom, 1)
        self.texte_extension = libelle(self.extension(), "secondaire", retour_a_la_ligne=False)
        ligne.addWidget(self.texte_extension)
        grille.addLayout(ligne, rang, 1)
        return zone

    def _ajouter_les_reglages(self, grille: QGridLayout) -> int:
        """Les réglages propres à l'export, en haut de la grille ; renvoie le rang suivant."""
        return 0

    def _ajouter_la_ligne_hdr(self, grille: QGridLayout, rang: int) -> int:
        """Vidéo HDR (lot 3) : le HDR est gardé ; « Convertir en SDR » le ramène en BT.709. La ligne
        n'apparaît que pour une vidéo HDR (d'après ce qu'en lit FFmpeg) ; le choix n'est pas retenu :
        le HDR suit la vidéo source (décision du 02/10/2026)."""
        self.titre_hdr = libelle("Couleurs", "legende", retour_a_la_ligne=False)
        grille.addWidget(self.titre_hdr, rang, 0, Qt.AlignmentFlag.AlignTop)
        self.zone_sdr, self.case_sdr = case_a_cocher("Convertir en SDR", " ")
        self.info_hdr = self.zone_sdr.findChild(Info)
        self.case_sdr.toggled.connect(lambda _coche: self._actualiser())
        grille.addWidget(self.zone_sdr, rang, 1)
        self.titre_hdr.hide()
        self.zone_sdr.hide()
        return rang + 1

    def norme_hdr(self) -> NormeHDR | None:
        """La norme HDR de la vidéo source (None : SDR, pas de vidéo, ou pas encore lue)."""
        return norme_hdr(self.source.couleurs) if self.source.video else None

    def convertir_en_sdr(self) -> bool:
        return self.norme_hdr() is not None and self.case_sdr.isChecked()

    def _explication_hdr(self, norme: NormeHDR) -> str:
        """L'explication sous « Convertir en SDR » (propre à chaque export)."""
        return ""

    def _actualiser_la_ligne_hdr(self) -> None:
        norme = self.norme_hdr()
        self.titre_hdr.setVisible(norme is not None)
        self.zone_sdr.setVisible(norme is not None)
        if norme is not None and self.info_hdr is not None:
            self.info_hdr.setText(self._explication_hdr(norme))

    def extension(self) -> str:
        return EXTENSION_CALQUE

    def sortie(self) -> Path:
        nom = nom_propre(self.nom.text()) if self.nom.text().strip() else ""
        return self.dossier() / f"{nom}{self.extension()}"

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

    def _video_a_analyser(self) -> Path | None:
        return self.source.chemin if self.source.video else self.source.video_d_apercu

    def _lancer_l_analyse(self) -> None:
        """FFmpeg lit la vidéo (sans la décoder, une seconde ou deux) : moment exact de chaque image,
        vrais débits, nom exact des codecs, couleurs. En attendant, « Exporter » attend.

        Au tout premier export (et après un changement de version de FFmpeg), FFmpeg est d'abord
        recopié depuis le .exe (une seconde ou deux, dans une tâche de fond : la fenêtre répond)."""
        if self._ffmpeg is None and not self._erreur_ffmpeg and ffmpeg_a_preparer():
            self._ffmpeg_en_preparation = True
            self.etat_analyse.setText("Préparation de FFmpeg (la première fois seulement, quelques secondes)…")
            self.etat_analyse.show()
            self._actualiser()  # pas de message « FFmpeg introuvable » pendant la préparation
            taches.lancer(preparer_ffmpeg, self._ffmpeg_prepare, self._ffmpeg_en_echec)
            return
        video = self._video_a_analyser()
        if video is None or not video.is_file() or self._ffmpeg is None:
            self.analyse_finie = True
            self.etat_analyse.hide()  # « Préparation de FFmpeg… » s'il vient d'être recopié
            self._actualiser()
            return
        self.etat_analyse.setText("FFmpeg lit ta vidéo (moment exact de chaque image, débits, couleurs)…")
        self.etat_analyse.show()
        ffmpeg = self._ffmpeg
        taches.lancer(lambda: analyser(video, ffmpeg), self._analyse_lue, lambda _erreur: self._analyse_lue(None))

    def _ffmpeg_prepare(self, chemin: Path) -> None:
        self._ffmpeg_en_preparation = False
        if not self._ouvert:
            return
        self._ffmpeg = chemin
        self._lancer_l_analyse()

    def _ffmpeg_en_echec(self, erreur: Exception) -> None:
        self._ffmpeg_en_preparation = False
        # Une erreur de Windows (disque plein…) : son texte seul, dans la langue de Windows, sans son code.
        texte = erreur.strerror if isinstance(erreur, OSError) and erreur.strerror else str(erreur)
        self._erreur_ffmpeg = texte.strip().rstrip(".") or type(erreur).__name__
        if not self._ouvert:
            return
        self.analyse_finie = True
        self.etat_analyse.hide()
        self._actualiser()

    def _analyse_lue(self, analyse) -> None:
        if not self._ouvert:
            return
        self.analyse_finie = True
        self.etat_analyse.hide()
        if self.source.video:
            self.source = source_du_projet(self._projet, analyse)
        self._analyse_recue(analyse)
        self._actualiser()

    def _analyse_recue(self, analyse) -> None:
        """Ce que la fenêtre fille fait de l'analyse (fréquence d'une vidéo d'aperçu, débit…)."""

    # --- Résumé ---------------------------------------------------------------------------------

    def plan(self):
        raise NotImplementedError

    def resume(self) -> Resume:
        raise NotImplementedError

    def _erreurs_communes(self, resume: Resume) -> Resume:
        if self._erreur_ffmpeg:
            resume.erreurs.append(f"FFmpeg n'a pas pu être préparé : {self._erreur_ffmpeg}. L'export est impossible.")
        elif self._ffmpeg is None and not self._ffmpeg_en_preparation:
            resume.erreurs.append("FFmpeg est introuvable : l'export est impossible (il devrait être intégré à l'app).")
        if not self._contenu.sous_titres:
            resume.erreurs.append("Pas de sous-titres à exporter.")
        return resume

    def texte_des_sous_titres(self) -> str:
        return texte_des_sous_titres(len(self._contenu.sous_titres), self._contenu.style)

    def _actualiser_les_reglages(self) -> None:
        """Les réglages propres à la fenêtre fille (textes, choix possibles…)."""

    def _actualiser(self) -> None:
        self._actualiser_la_ligne_hdr()
        self._actualiser_les_reglages()
        self.texte_extension.setText(self.extension())
        resume = self.resume()
        self.chemin_dossier.setText(str(self.dossier()))
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
        tableau.setFixedHeight(entete + len(resume.lignes) * Hauteurs.LIGNE_RESUME + 2 * Dimensions.BORDURE)
        tableau.setVisible(bool(resume.lignes))

    def _afficher_les_messages(self, resume: Resume) -> None:
        while self.messages.count():
            element = self.messages.takeAt(0).widget()
            if element is not None:
                element.hide()  # tout de suite : il n'est effacé qu'au prochain passage de la boucle de Qt
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

    def _creer_l_export(self, plan):
        """L'export (un QObject avec les signaux avance, termine, echec, arrete, et parfois etape)."""
        raise NotImplementedError

    def _retenir_les_choix(self) -> None:
        """Les réglages propres à la fenêtre fille, retenus pour le prochain export."""

    def _premiere_etape(self) -> str:
        return ""

    def exporter(self) -> None:
        resume = self.resume()
        if not resume.possible or self._export is not None or self._ffmpeg is None or not self.analyse_finie:
            return
        plan = self.plan()
        if plan is None:
            return
        self._preferences.ecrire(PREF_DOSSIER, self.choix_dossier.valeur())
        self._retenir_les_choix()
        self._preferences.enregistrer()
        self._export = self._creer_l_export(plan)
        self._export.avance.connect(self._avance)
        self._export.termine.connect(self._termine)
        self._export.echec.connect(self._echec)
        self._export.arrete.connect(self._arrete)
        if hasattr(self._export, "etape"):
            self._export.etape.connect(self._nouvelle_etape)
        self._pendant_l_export(True)
        self._une_seule_etape = not hasattr(self._export, "etape")
        self._nouvelle_etape(self._premiere_etape(), self._une_seule_etape)
        self._avance(0, max(1, getattr(plan, "nombre_images", 1)))
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
            self.bouton_lire.hide()
            self.bouton_fermer.hide()

    def _nouvelle_etape(self, nom: str, finale: bool = False) -> None:
        self._nom_etape, self._etape_finale = nom, finale
        self._debut_etape = time.monotonic()
        self.barre.definir(0)
        self.reste.setText("")
        self.etape.setText(nom)

    def _avance(self, fait: int, total: int) -> None:
        self.barre.definir(fait / total if total else 1.0)
        if fait >= total and self._etape_finale:
            self.etape.setText("Finalisation du fichier…")
            self.reste.setText("")
            return
        self.etape.setText(f"{self._nom_etape} : {fait} sur {total}")
        ecoule = time.monotonic() - (self._debut_etape or time.monotonic())
        if 0 < fait < total and ecoule >= RESTE_APRES_S:
            suffixe = "" if self._une_seule_etape else " pour cette étape"
            self.reste.setText(f"Environ {duree_d_export_lisible(ecoule / fait * (total - fait))} restantes{suffixe}")

    def _termine(self, fichier: Path) -> None:
        export = self._export
        self.duree_s = export.duree_s if export is not None else 0.0
        if export is not None:
            self.dessin_s, self.images_dessinees = export.dessin_s, export.images_dessinees
        self._export = None
        self.fichier = fichier
        self._pendant_l_export(False)
        self.bouton_annuler.hide()
        self.bouton_exporter.hide()
        self.bouton_fermer.show()
        self.bouton_dossier.show()
        self.bouton_lire.setVisible(self.AVEC_LECTURE)
        poids = poids_lisible(fichier.stat().st_size) if fichier.is_file() else ""
        self._statut(f"{self.ENREGISTRE} en {duree_d_export_lisible(self.duree_s or 0)} : {fichier.name} ({poids}).", "succes")
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

    def lire_la_video(self) -> None:
        """La vidéo exportée, dans le lecteur de Windows (celui choisi pour ce genre de fichier)."""
        if self.fichier is not None:
            ouvrir_fichier(self.fichier)

    # --- Fermeture ------------------------------------------------------------------------------

    def done(self, resultat: int) -> None:
        """Fermer la fenêtre pendant un export l'arrête : rien d'inachevé ne reste."""
        self.arreter()
        self._ouvert = False
        super().done(resultat)


# --- Calque transparent (lot 1) ------------------------------------------------------------------


class DialogueExportCalque(DialogueExport):
    """Exporter le calque transparent (MOV, ProRes 4444) des sous-titres du projet."""

    TITRE = "Exporter le calque transparent"
    PAGE_CONSEILS = "export"
    INFO = (
        "Les sous-titres seuls, sur un fond transparent : pose ce calque au-dessus de ton montage dans "
        "Premiere Pro, au même point de départ que ta vidéo ou ta voix."
    )
    SUFFIXE = SUFFIXE_CALQUE
    ENREGISTRE = "Calque enregistré"
    _frequence_apercu: Fraction | None = None  # vidéo d'aperçu d'un projet sans vidéo (une fois lue)

    def _ajouter_les_reglages(self, grille: QGridLayout) -> int:
        rang = 0
        grille.addWidget(libelle("Format", "legende", retour_a_la_ligne=False), rang, 0)
        format_ = libelle("MOV · ProRes 4444 avec transparence, lu par Premiere Pro", "secondaire")
        format_.setToolTip("Le format de montage d'Apple : sans perte visible, il garde la transparence")
        grille.addWidget(format_, rang, 1)
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
        return rang

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
            ligne.setStretch(ligne.count() - 1, 0)  # le texte prend toute la ligne (sans passer à la ligne)
            return
        self.texte_frequence.hide()
        ligne.setStretch(ligne.count() - 1, 1)  # les boutons restent à gauche
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

    def _analyse_recue(self, analyse) -> None:
        if not self.source.video and analyse is not None and analyse.images is not None:
            self._frequence_apercu = analyse.images.frequence
            self._preparer_la_frequence()

    def _explication_hdr(self, norme: NormeHDR) -> str:
        return (
            f"Ta vidéo est en HDR ({norme.nom}) : le calque aussi, sous-titres au blanc de référence (ils "
            "n'éblouissent pas) ; pose-le dans une séquence HDR de Premiere Pro. Coche pour une séquence SDR (BT.709)."
        )

    def plan(self) -> PlanCalque:
        return plan_du_calque(
            self.source, self._contenu.largeur, self._contenu.hauteur, self.frequence_choisie(), self.sortie(),
            self.convertir_en_sdr(),
        )

    def resume(self) -> Resume:
        plan = self.plan()
        return self._erreurs_communes(resume_calque(self.source, plan, self.texte_des_sous_titres(), place_libre(plan.sortie.parent)))

    def _actualiser_les_reglages(self) -> None:
        if self.source.video:
            self.texte_frequence.setText(
                f"{texte_frequence(self.source.frequence)} : celle de ta vidéo (le calque tombe juste, image par image)"
                if self.source.frequence is not None
                else "Celle de ta vidéo"
            )

    def _premiere_etape(self) -> str:
        return "Images du calque"

    def _retenir_les_choix(self) -> None:
        if self.choix_frequence is not None:
            self._preferences.ecrire(PREF_FREQUENCE, self.choix_frequence.valeur())
            self._preferences.ecrire(PREF_FREQUENCE_LIBRE, self.frequence_libre.value())

    def _creer_l_export(self, plan: PlanCalque):
        from ...exports.calque import ExportDuCalque, ImagesDuCalque

        contenu = self._contenu
        images = ImagesDuCalque(contenu.reglages, contenu.largeur, contenu.hauteur, contenu.sous_titres, contenu.mots)
        return ExportDuCalque(plan, images, self._ffmpeg, self)


# --- Vidéo avec sous-titres (lot 2) ----------------------------------------------------------------


class DialogueExportVideo(DialogueExport):
    """Exporter la vidéo du projet avec ses sous-titres incrustés (MP4, MOV ou MKV)."""

    TITRE = "Exporter la vidéo avec sous-titres"
    PAGE_CONSEILS = "export-video"
    INFO = (
        "Ta vidéo avec ses sous-titres incrustés, prête à publier : chaque image garde son moment exact, "
        "les couleurs restent celles de l'aperçu, et le son est copié tel quel."
    )
    SUFFIXE = SUFFIXE_VIDEO
    ENREGISTRE = "Vidéo enregistrée"
    AVEC_LECTURE = True

    def _ajouter_les_reglages(self, grille: QGridLayout) -> int:
        rang = 0
        grille.addWidget(libelle("Format", "legende", retour_a_la_ligne=False), rang, 0)
        self.choix_conteneur = ChoixEnBoutons(dict(CONTENEURS), "Le format du fichier (conteneur)")
        conteneur = self._preferences.lire(PREF_CONTENEUR, MP4)
        self.choix_conteneur.definir(conteneur if conteneur in CONTENEURS else MP4)
        self.choix_conteneur.change.connect(lambda _valeur: self._conteneur_choisi())
        grille.addLayout(self._a_gauche(self.choix_conteneur), rang, 1)
        rang += 1

        grille.addWidget(libelle("Codec", "legende", retour_a_la_ligne=False), rang, 0)
        self.choix_codec = ChoixEnBoutons(dict(CODECS), "La façon de compresser l'image")
        codec = self._preferences.lire(PREF_CODEC, H264)
        # Le codec voulu (retenu, ou cliqué) : quand il n'est pas possible (ProRes hors MOV, H.264 en
        # HDR), un autre est choisi, et le voulu revient dès qu'il redevient possible.
        self._codec_voulu = codec if codec in CODECS else H264
        self.choix_codec.definir(self._codec_voulu)
        self.choix_codec.change.connect(self._codec_choisi)
        grille.addLayout(self._a_gauche(self.choix_codec), rang, 1)
        rang += 1

        grille.addWidget(libelle("Débit", "legende", retour_a_la_ligne=False), rang, 0, Qt.AlignmentFlag.AlignTop)
        colonne = QVBoxLayout()
        colonne.setSpacing(Espacements.S)
        self.choix_debit = ChoixEnBoutons(
            {DEBIT_IDENTIQUE: "Identique (+ 10 %)", DEBIT_CONSEILLE: "Conseillé", DEBIT_PERSONNALISE: "Personnalisé"},
            "La quantité d'information par seconde : plus elle est haute, plus l'image est fidèle et le fichier lourd",
        )
        self._debit_retenu = self._preferences.lire(PREF_DEBIT, "")
        self.choix_debit.definir(self._debit_retenu if self._debit_retenu in (DEBIT_IDENTIQUE, DEBIT_CONSEILLE, DEBIT_PERSONNALISE) else DEBIT_IDENTIQUE)
        self.choix_debit.change.connect(lambda _valeur: self._actualiser())
        colonne.addLayout(self._a_gauche(self.choix_debit))
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.debit_personnalise = champ_decimal(DEBIT_PERSONNALISE_MIN, DEBIT_PERSONNALISE_MAX, 0.5, 1, " Mb/s", "Débit de la vidéo")
        retenu = self._preferences.lire(PREF_DEBIT_PERSONNALISE, None)
        self.debit_personnalise.setValue(float(retenu) if retenu else 16.0)
        self.debit_personnalise.valueChanged.connect(lambda _valeur: self._actualiser())
        ligne.addWidget(self.debit_personnalise)
        self.texte_debit = libelle("", "legende")
        ligne.addWidget(self.texte_debit, 1)
        colonne.addLayout(ligne)
        grille.addLayout(colonne, rang, 1)
        rang += 1
        return rang

    @staticmethod
    def _a_gauche(element: QWidget) -> QHBoxLayout:
        ligne = QHBoxLayout()
        ligne.addWidget(element)
        ligne.addStretch(1)
        return ligne

    def _conteneur_choisi(self) -> None:
        self._actualiser()

    def _codec_choisi(self, codec: str) -> None:
        self._codec_voulu = codec
        self._actualiser()

    def _hdr_garde(self) -> bool:
        return self.norme_hdr() is not None and not self.case_sdr.isChecked()

    def _explication_hdr(self, norme: NormeHDR) -> str:
        return (
            f"Ta vidéo est en HDR ({norme.nom}) : elle le reste (H.265 en 10 bits, ou ProRes), sous-titres au "
            "blanc de référence (ils n'éblouissent pas). Coche pour une plateforme ou un écran qui affiche mal "
            "le HDR : couleurs ramenées en SDR (BT.709)."
        )

    def extension(self) -> str:
        return EXTENSIONS[self.choix_conteneur.valeur()] if hasattr(self, "choix_conteneur") else EXTENSIONS[MP4]

    def _analyse_recue(self, analyse) -> None:
        """Le débit par défaut dépend de la vidéo : identique à la source (+ 10 %), sauf pour un format de
        montage ou un débit inconnu (« Conseillé pour la publication »). Un choix retenu reste, sauf
        « Identique » quand la vidéo est dans un format de montage."""
        defaut = debit_par_defaut(self.source)
        retenu = self._debit_retenu
        if retenu not in (DEBIT_IDENTIQUE, DEBIT_CONSEILLE, DEBIT_PERSONNALISE) or (retenu == DEBIT_IDENTIQUE and defaut == DEBIT_CONSEILLE):
            self.choix_debit.definir(defaut)
        if not self._preferences.lire(PREF_DEBIT_PERSONNALISE, None):
            images = analyse.images if analyse is not None else None
            if images is not None:
                largeur, hauteur = analyse.taille_affichee
                conseille = debit_conseille(largeur, hauteur, images.frequence, self._hdr_garde())
                self.debit_personnalise.setValue(conseille / 1_000_000)

    def plan(self) -> PlanVideo | None:
        return plan_video(
            self.source, self.choix_conteneur.valeur(), self.choix_codec.valeur(), self.choix_debit.valeur(),
            self.debit_personnalise.value(), self.sortie(), self.convertir_en_sdr(),
        )

    def resume(self) -> Resume:
        if not self.analyse_finie:
            return self._erreurs_communes(Resume())  # FFmpeg lit encore la vidéo : rien à comparer
        plan = self.plan()
        libre = place_libre(plan.sortie.parent) if plan is not None else None
        return self._erreurs_communes(resume_video(self.source, plan, self.texte_des_sous_titres(), libre))

    def _actualiser_les_reglages(self) -> None:
        conteneur = self.choix_conteneur.valeur()
        hdr = self._hdr_garde()
        possibles = codecs_possibles(conteneur, hdr)
        for codec in CODECS:
            possible = codec in possibles
            if possible:
                explication = ""
            elif codec not in CODECS_POSSIBLES[conteneur]:
                explication = "Le ProRes ne va que dans un MOV"
            else:
                explication = "Pas de HDR en H.264 : coche « Convertir en SDR » pour l'utiliser"
            self.choix_codec.bouton(codec).setEnabled(possible)
            self.choix_codec.bouton(codec).setToolTip(explication)
        self.choix_codec.definir(self._codec_voulu if self._codec_voulu in possibles else possibles[0])
        prores = self.choix_codec.valeur() == PRORES
        self.choix_debit.setVisible(not prores)
        self.debit_personnalise.setVisible(not prores and self.choix_debit.valeur() == DEBIT_PERSONNALISE)
        analyse = self.source.analyse
        if prores and analyse is not None and analyse.images is not None:
            largeur, hauteur = analyse.taille_affichee
            self.texte_debit.setText(f"ProRes 422 HQ : débit fixé par le format (≈ {debit_lisible(debit_prores(largeur, hauteur, analyse.images.frequence))})")
        elif prores:
            self.texte_debit.setText("ProRes 422 HQ : débit fixé par le format")
        elif self.choix_debit.valeur() == DEBIT_CONSEILLE and analyse is not None and analyse.images is not None:
            largeur, hauteur = analyse.taille_affichee
            conseille = debit_conseille(largeur, hauteur, analyse.images.frequence, hdr)
            en_hdr = hdr and debit_hdr_de_youtube(largeur, hauteur)  # sous la 720p, YouTube n'en donne qu'en SDR
            youtube = "le double du débit conseillé par YouTube" + (" en HDR" if en_hdr else "")
            self.texte_debit.setText(f"{debit_lisible(conseille)} pour la publication : {youtube}")
        elif self.choix_debit.valeur() == DEBIT_IDENTIQUE and analyse is not None and analyse.images is not None and analyse.images.debit:
            plan = self.plan()
            debit = debit_lisible(plan.debit) if plan is not None and plan.debit else ""
            self.texte_debit.setText(f"{debit} : celui de ta vidéo ({debit_lisible(analyse.images.debit)}), plus 10 % pour compenser la recompression")
        else:
            self.texte_debit.setText("")
        self.texte_debit.setVisible(bool(self.texte_debit.text()))

    def _premiere_etape(self) -> str:
        return "Dessin des sous-titres"

    def _retenir_les_choix(self) -> None:
        self._preferences.ecrire(PREF_CONTENEUR, self.choix_conteneur.valeur())
        codec = self.choix_codec.valeur()
        if self._codec_voulu in CODECS_POSSIBLES[self.choix_conteneur.valeur()]:
            codec = self._codec_voulu  # écarté seulement par le HDR (H.264) : il reviendra pour une vidéo SDR
        self._preferences.ecrire(PREF_CODEC, codec)
        self._preferences.ecrire(PREF_DEBIT, self.choix_debit.valeur())
        if self.choix_debit.valeur() == DEBIT_PERSONNALISE:
            self._preferences.ecrire(PREF_DEBIT_PERSONNALISE, self.debit_personnalise.value())

    def _creer_l_export(self, plan: PlanVideo):
        from ...exports.composition import CalqueDeLaVideo, ExportVideo

        contenu = self._contenu
        calque = CalqueDeLaVideo(contenu.reglages, plan.largeur, plan.hauteur, contenu.sous_titres, contenu.mots, plan.calque_16_bits)
        return ExportVideo(plan, calque, self._ffmpeg, self)
