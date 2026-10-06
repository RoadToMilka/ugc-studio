"""Module Images (V4, lot 1 ; cahier des charges §8 bis.1) : toutes les images d'un dossier à la même
taille, réduites ou agrandies, sans Photoshop. Le calcul est dans images/redimensionnement.py.

Le parcours, de haut en bas :
1. Dossier : glisser-déposer ou « Choisir un dossier… ». L'app lit la taille de chaque image (sans les
   décoder : rapide, même pour beaucoup d'images).
2. Taille : le côté (hauteur, largeur ou plus grand côté), la taille en pixels, le filtre et la qualité.
3. Enregistrement : un sous-dossier nommé d'après la taille (« 600 px de haut »), ou un autre dossier.
4. Résumé : combien d'images réduites, agrandies, déjà à la bonne taille ; en orange, ce qui mérite
   un coup d'œil (une image très agrandie, une image du même nom déjà dans le dossier de sortie, un
   fichier illisible) ; puis chaque image, sa taille actuelle et sa nouvelle taille.
5. « Redimensionner » : avancement, « Arrêter », puis « Ouvrir le dossier ».

Ce module ne dépend pas d'un projet : ses réglages sont retenus dans les préférences de l'app.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from ....chemins import chemin_a_afficher, dossier_documents
from ....dossiers import EXTENSIONS_IMAGES
from ....images.redimensionnement import (
    AGRANDIE,
    AGRANDISSEMENT_FORT,
    COMME_L_ORIGINAL,
    COTES,
    FILTRES,
    HAUTEUR,
    INCHANGEE,
    LANCZOS,
    PIXELS_MAX,
    PIXELS_MIN,
    PIXELS_PAR_DEFAUT,
    QUALITES,
    Bilan,
    Cible,
    ImageAPreparer,
    Illisible,
    InfosImage,
    Plan,
    lire_les_images,
    planifier,
    preparer_les_images,
    quantite,
)
from ....services import Services
from ... import taches
from ...composants.barre_avancement import BarreAvancement
from ...composants.bouton import BoutonOccupe
from ...composants.depot_dossier import ZoneDepotDossier, dossier_depose
from ...composants.elements import (
    afficher_message,
    bloc,
    bouton,
    champ_entier,
    champ_nomme,
    champs_en_colonnes,
    libelle,
    liste_deroulante,
)
from ...composants.tableau import Colonne, Tableau
from ...dialogues import messages
from ...ouvrir import ouvrir_dossier
from ...theme import Couleurs, Dimensions, Espacements, Hauteurs, qcolor
from ..base import Page

TITRE = "Images"
SOUS_TITRE = "Toutes les images d'un dossier à la même taille, réduites ou agrandies."

# Préférences (§10) : ce module ne dépend pas d'un projet.
PREF_DOSSIER = "images_dossier"
PREF_COTE = "images_cote"
PREF_PIXELS = "images_pixels"
PREF_FILTRE = "images_filtre"
PREF_QUALITE = "images_qualite"
PREF_SORTIE = "images_sortie"
PREF_SORTIE_AUTRE = "images_sortie_autre"

SOUS_DOSSIER, AUTRE_DOSSIER = "sous_dossier", "autre"

# Noms des formats, tels qu'on les connaît (Pillow dit « JPEG », « WEBP »…).
NOMS_DES_FORMATS = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WebP", "AVIF": "AVIF", "TIFF": "TIFF", "BMP": "BMP"}
FORMATS_ACCEPTES = "JPG, PNG, WebP, AVIF, TIFF ou BMP"

AIDE_DOSSIER = (
    "Les images du dossier lui-même (JPG, PNG, WebP, AVIF, TIFF, BMP), pas celles de ses sous-dossiers. "
    "Tes originaux ne sont jamais modifiés."
)
AIDE_TAILLE = (
    "Toutes les images passent à cette taille : les plus grandes sont réduites, les plus petites agrandies. "
    "L'autre côté suit : les proportions sont gardées."
)
AIDE_FILTRE = (
    "Lanczos : le plus fidèle, en réduction comme en agrandissement. Bicubique : à peine plus doux, presque "
    "sans liseré sur un bord très net qu'on agrandit. Bilinéaire : le plus doux."
)
AIDE_QUALITE = (
    "JPG : « Comme l'original » garde la qualité de chaque image, ni plus lourde ni plus abîmée. WebP et AVIF : "
    "90, ou la qualité choisie ; un WebP sans perte le reste. PNG, TIFF et BMP : toujours sans perte."
)
AIDE_SORTIE = (
    "Par défaut, un sous-dossier du dossier des images, nommé d'après la taille. Une image du même nom déjà "
    "dans le dossier de sortie est remplacée, après confirmation ; tes originaux, jamais."
)

COLONNES = (
    Colonne("Image", texte=True, etiree=True),
    Colonne("Taille actuelle", a_droite=True),
    Colonne("Nouvelle taille", a_droite=True),
    Colonne("Changement"),
)


def _taille(largeur: int, hauteur: int) -> str:
    return f"{largeur} × {hauteur}"


def _facteur(facteur: float) -> str:
    """0,3214 → « × 0,32 » (à la française)."""
    return f"× {facteur:.2f}".replace(".", ",")


def texte_du_changement(image: ImageAPreparer) -> str:
    """« réduite (× 0,32) », « agrandie (× 2,40) », « inchangée »."""
    if image.changement == INCHANGEE:
        return "inchangée"
    mot = "agrandie" if image.changement == AGRANDIE else "réduite"
    return f"{mot} ({_facteur(image.facteur)})"


def alertes_du_plan(plan: Plan) -> list[str]:
    """Ce qui mérite un coup d'œil avant de lancer (en orange) : une image très agrandie, une image du
    même nom déjà dans le dossier de sortie, un fichier illisible."""
    alertes = []
    fortes = len(plan.fortement_agrandies)
    if fortes:
        accord = "e" if fortes == 1 else "es"
        sujet = "elle paraîtra" if fortes == 1 else "elles paraîtront"
        fois = f"{AGRANDISSEMENT_FORT:g}".replace(".", ",")
        alertes.append(f"{quantite(fortes, 'image')} agrandi{accord} plus de {fois} fois : {sujet} plus douce{'s' if fortes > 1 else ''}.")
    existantes = len(plan.existantes)
    if existantes:
        sujet = "elle sera remplacée" if existantes == 1 else "elles seront remplacées"
        alertes.append(f"{quantite(existantes, 'image')} du même nom déjà dans « {plan.dossier_sortie.name} » : {sujet}.")
    if plan.illisibles:
        noms = ", ".join(illisible.chemin.name for illisible in plan.illisibles[:3])
        suite = "…" if len(plan.illisibles) > 3 else ""
        pluriel = "s" if len(plan.illisibles) > 1 else ""
        alertes.append(f"{quantite(len(plan.illisibles), 'fichier')} illisible{pluriel}, ignoré{pluriel} : {noms}{suite}.")
    return alertes


class PageImages(Page):
    # V4, lot 2 : « Trier et renommer » (dossier des images faites) : la fenêtre ouvre le module Renommer.
    renommer_demande = Signal(object)

    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="images")
        self._preferences = services.preferences
        self._dossier: Path | None = None
        self._images: list[InfosImage] = []
        self._illisibles: list[Illisible] = []
        self._plan: Plan | None = None
        self._arret: threading.Event | None = None
        self._occupe = False
        self._bouton_occupe = BoutonOccupe()
        self._lecture = 0  # numéro de la dernière lecture de dossier lancée (une plus ancienne est ignorée)
        self._derniere_sortie: Path | None = None
        autre = self._preferences.lire(PREF_SORTIE_AUTRE)
        self._autre_dossier: Path | None = Path(autre) if isinstance(autre, str) and autre else None
        self.setAcceptDrops(True)

        # --- Dossier ---
        self.cadre_dossier, d = bloc("Dossier", aide=AIDE_DOSSIER)
        self.zone_depot = ZoneDepotDossier("Glisse un dossier d'images ici", FORMATS_ACCEPTES, self.choisir_dossier)
        d.addWidget(self.zone_depot)
        self.ligne_dossier = QWidget()
        ligne = QHBoxLayout(self.ligne_dossier)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.M)
        textes = QVBoxLayout()
        textes.setContentsMargins(0, 0, 0, 0)
        textes.setSpacing(Espacements.XS)
        self.chemin = libelle("", "secondaire")
        textes.addWidget(self.chemin)
        self.compte = libelle("", "legende")
        textes.addWidget(self.compte)
        ligne.addLayout(textes, 1)
        self.bouton_changer = bouton("Changer de dossier…", variante="contour", nom_icone="folder-open", action=self.choisir_dossier)
        ligne.addWidget(self.bouton_changer, 0, Qt.AlignmentFlag.AlignTop)
        self.ligne_dossier.hide()
        d.addWidget(self.ligne_dossier)
        self.contenu.addWidget(self.cadre_dossier)

        # --- Taille ---
        self.cadre_taille, d = bloc("Taille", aide=AIDE_TAILLE)
        self.cote = liste_deroulante()
        for cle, nom in COTES.items():
            self.cote.addItem(nom, cle)
        self.pixels = champ_entier(PIXELS_MIN, PIXELS_MAX, " px")
        self.filtre = liste_deroulante()
        for cle, nom in FILTRES.items():
            self.filtre.addItem(nom, cle)
        self.qualite = liste_deroulante()
        for valeur, nom in QUALITES.items():
            self.qualite.addItem(nom, valeur)
        self._choisir(self.cote, self._preferences.lire(PREF_COTE, HAUTEUR))
        pixels = self._preferences.lire(PREF_PIXELS, PIXELS_PAR_DEFAUT)
        self.pixels.setValue(pixels if isinstance(pixels, int) else PIXELS_PAR_DEFAUT)
        self._choisir(self.filtre, self._preferences.lire(PREF_FILTRE, LANCZOS))
        self._choisir(self.qualite, self._preferences.lire(PREF_QUALITE, COMME_L_ORIGINAL))
        d.addLayout(
            champs_en_colonnes(
                (("Côté", self.cote), ("Taille", self.pixels), ("Filtre", self.filtre), ("Qualité", self.qualite)),
                aides={"Filtre": AIDE_FILTRE, "Qualité": AIDE_QUALITE},
            )
        )
        self.contenu.addWidget(self.cadre_taille)

        # --- Enregistrement ---
        self.cadre_sortie, d = bloc("Enregistrement", aide=AIDE_SORTIE)
        self.sortie = liste_deroulante()
        self.sortie.addItem("", SOUS_DOSSIER)
        self.sortie.addItem("Autre dossier…", AUTRE_DOSSIER)
        self._choisir(self.sortie, self._preferences.lire(PREF_SORTIE, SOUS_DOSSIER))
        d.addWidget(champ_nomme("Enregistrer dans", self.sortie))
        self.ligne_autre = QWidget()
        ligne = QHBoxLayout(self.ligne_autre)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.M)
        self.chemin_autre = libelle("", "legende")
        ligne.addWidget(self.chemin_autre, 1)
        self.bouton_autre = bouton("Changer…", variante="contour", nom_icone="folder-open", action=self.choisir_autre_dossier)
        ligne.addWidget(self.bouton_autre, 0, Qt.AlignmentFlag.AlignTop)
        d.addWidget(self.ligne_autre)
        self.contenu.addWidget(self.cadre_sortie)

        # --- Résumé ---
        self.cadre_resume, d = bloc("Résumé")
        self.resume = libelle("", "secondaire")
        d.addWidget(self.resume)
        self.alertes = libelle("", "avertissement")
        d.addWidget(self.alertes)
        self.tableau = Tableau(COLONNES)
        d.addWidget(self.tableau)
        self.contenu.addWidget(self.cadre_resume)

        # --- Redimensionner ---
        action = QVBoxLayout()
        action.setSpacing(Espacements.S)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_redimensionner = bouton("Redimensionner", variante="principal", nom_icone="scaling", action=self.redimensionner)
        boutons.addWidget(self.bouton_redimensionner)
        self.bouton_arreter = bouton("Arrêter", nom_icone="square", action=self.arreter)
        self.bouton_arreter.hide()
        boutons.addWidget(self.bouton_arreter)
        self.bouton_ouvrir = bouton("Ouvrir le dossier", variante="contour", nom_icone="folder-open", action=self.ouvrir_le_dossier)
        self.bouton_ouvrir.hide()
        boutons.addWidget(self.bouton_ouvrir)
        self.bouton_renommer = bouton("Trier et renommer", variante="contour", nom_icone="list-ordered", action=self.trier_et_renommer)
        self.bouton_renommer.setToolTip("Ouvre le module Renommer sur les images faites : choisis leur ordre, puis renomme-les.")
        self.bouton_renommer.hide()
        boutons.addWidget(self.bouton_renommer)
        boutons.addStretch(1)
        action.addLayout(boutons)
        self.zone_avancement = QWidget()
        avancement = QVBoxLayout(self.zone_avancement)
        avancement.setContentsMargins(0, 0, 0, 0)
        avancement.setSpacing(Espacements.S)
        self.barre = BarreAvancement()
        avancement.addWidget(self.barre)
        self.avancee = libelle("", "legende")
        avancement.addWidget(self.avancee)
        self.zone_avancement.hide()
        action.addWidget(self.zone_avancement)
        self.statut = libelle("", "secondaire")
        action.addWidget(self.statut)
        self.contenu.addLayout(action)

        self.cote.currentIndexChanged.connect(lambda _index: self._reglage_change())
        self.pixels.valueChanged.connect(lambda _valeur: self._reglage_change())
        self.filtre.currentIndexChanged.connect(lambda _index: self._preferences.ecrire(PREF_FILTRE, self.filtre.currentData()))
        self.qualite.currentIndexChanged.connect(lambda _index: self._preferences.ecrire(PREF_QUALITE, self.qualite.currentData()))
        self.sortie.currentIndexChanged.connect(lambda _index: self._sortie_changee())
        self._actualiser()

    @staticmethod
    def _choisir(liste, valeur) -> None:
        index = liste.findData(valeur)
        liste.setCurrentIndex(index if index >= 0 else 0)

    @property
    def occupe(self) -> bool:
        return self._occupe

    # --- Dossier -----------------------------------------------------------------------------

    def choisir_dossier(self) -> None:
        if self._occupe:
            return
        depart = self._dossier or Path(self._preferences.lire(PREF_DOSSIER) or dossier_documents())
        choix = QFileDialog.getExistingDirectory(self, "Choisir un dossier d'images", str(depart))
        if choix:
            self.ouvrir(Path(choix))

    def ouvrir(self, dossier: Path) -> None:
        """Lit les images de `dossier` (en arrière-plan), puis met à jour le résumé."""
        if self._occupe:
            return
        self._dossier = dossier
        self._preferences.ecrire(PREF_DOSSIER, str(dossier))
        self._images, self._illisibles, self._plan = [], [], None
        self._lecture += 1
        numero = self._lecture
        self._cacher_les_boutons_de_fin()
        self.chemin.setText(chemin_a_afficher(dossier))
        self.compte.setText("Lecture des images…")
        self.zone_depot.hide()
        self.ligne_dossier.show()
        self._occuper(True, self.bouton_changer)
        taches.lancer(
            lambda: lire_les_images(dossier),
            lambda resultat, n=numero: self._images_lues(n, resultat),
            lambda erreur, n=numero: self._lecture_echouee(n, erreur),
        )

    def _images_lues(self, numero: int, resultat) -> None:
        if numero != self._lecture:
            return  # un autre dossier a été choisi depuis
        self._images, self._illisibles = resultat
        self._occuper(False)
        self.compte.setText(self._texte_du_compte())
        self._actualiser()

    def _lecture_echouee(self, numero: int, erreur: Exception) -> None:
        if numero != self._lecture:
            return
        self._occuper(False)
        self.compte.setText("")
        self._afficher(f"Impossible de lire ce dossier : {erreur}", "erreur")
        self._actualiser()

    def _texte_du_compte(self) -> str:
        """« 50 images (JPG, PNG, WebP) », ou « Aucune image dans ce dossier (…) »."""
        if not self._images:
            return f"Aucune image dans ce dossier ({FORMATS_ACCEPTES})"
        formats = []
        for image in self._images:
            nom = NOMS_DES_FORMATS.get(image.format, image.format)
            if nom not in formats:
                formats.append(nom)
        return f"{quantite(len(self._images), 'image')} ({', '.join(formats)})"

    def dragEnterEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        donnees = evenement.mimeData()
        if not self._occupe and donnees.hasUrls() and dossier_depose(donnees, EXTENSIONS_IMAGES) is not None:
            evenement.acceptProposedAction()
            self.zone_depot.survol(True)

    def dragLeaveEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        super().dragLeaveEvent(evenement)

    def dropEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        dossier = dossier_depose(evenement.mimeData(), EXTENSIONS_IMAGES)
        if dossier is not None:
            evenement.acceptProposedAction()
            self.ouvrir(dossier)

    # --- Réglages ----------------------------------------------------------------------------

    def cible(self) -> Cible:
        return Cible(self.cote.currentData(), self.pixels.value())

    def dossier_de_sortie(self) -> Path | None:
        if self.sortie.currentData() == AUTRE_DOSSIER:
            return self._autre_dossier
        return self._dossier / self.cible().nom_du_dossier() if self._dossier is not None else None

    def _reglage_change(self) -> None:
        self._preferences.ecrire(PREF_COTE, self.cote.currentData())
        self._preferences.ecrire(PREF_PIXELS, self.pixels.value())
        self._cacher_les_boutons_de_fin()
        self._actualiser()

    def _sortie_changee(self) -> None:
        if self.sortie.currentData() == AUTRE_DOSSIER and self._autre_dossier is None:
            self.choisir_autre_dossier()
            if self._autre_dossier is None:  # pas de dossier choisi : on reste sur le sous-dossier
                self._choisir(self.sortie, SOUS_DOSSIER)
                return
        self._preferences.ecrire(PREF_SORTIE, self.sortie.currentData())
        self._cacher_les_boutons_de_fin()
        self._actualiser()

    def choisir_autre_dossier(self) -> None:
        depart = self._autre_dossier or self._dossier or dossier_documents()
        choix = QFileDialog.getExistingDirectory(self, "Dossier où enregistrer les images", str(depart))
        if choix:
            self.definir_autre_dossier(Path(choix))

    def definir_autre_dossier(self, dossier: Path) -> None:
        self._autre_dossier = dossier
        self._preferences.ecrire(PREF_SORTIE_AUTRE, str(dossier))
        self._actualiser()

    # --- Résumé ------------------------------------------------------------------------------

    def _actualiser(self) -> None:
        """Le plan selon les réglages, puis le résumé, les alertes et le tableau."""
        self.sortie.setItemText(0, f"Sous-dossier « {self.cible().nom_du_dossier()} »")
        autre = self.sortie.currentData() == AUTRE_DOSSIER
        self.ligne_autre.setVisible(autre)
        self.chemin_autre.setText(chemin_a_afficher(self._autre_dossier) if self._autre_dossier else "Aucun dossier choisi")
        self._plan = None
        erreur = ""
        sortie = self.dossier_de_sortie()
        if self._dossier is not None and self._images:
            if sortie is None:
                erreur = "Choisis le dossier où enregistrer les images."
            else:
                try:
                    self._plan = planifier(self._images, self.cible(), sortie, self._illisibles)
                except ValueError:
                    erreur = "Choisis un autre dossier que celui des originaux : ils ne sont jamais remplacés."
        # Le résumé apparaît une fois le dossier lu (pas pendant sa lecture).
        self.cadre_resume.setVisible(self._plan is not None or (self._dossier is not None and not self._occupe))
        plan = self._plan
        if plan is not None:
            self.resume.setText(plan.resume())
            alertes = alertes_du_plan(plan)
            self.alertes.setText("\n".join(alertes))
            self.alertes.setVisible(bool(alertes))
            self.alertes.setProperty("role", "avertissement")
        else:
            self.resume.setText(erreur or ("" if self._images else self._texte_sans_images()))
            self.alertes.setText("")
            self.alertes.hide()
        self.alertes.style().unpolish(self.alertes)
        self.alertes.style().polish(self.alertes)
        self._remplir_le_tableau(plan)
        self._mettre_a_jour_les_boutons()

    def _texte_sans_images(self) -> str:
        if self._dossier is None:
            return ""
        if self._illisibles:
            return alertes_du_plan(Plan(self.cible(), self._dossier, illisibles=self._illisibles))[-1]
        return "Aucune image à redimensionner dans ce dossier."

    def _remplir_le_tableau(self, plan: Plan | None) -> None:
        images = plan.images if plan is not None else []
        self.tableau.setRowCount(len(images))
        for rang, image in enumerate(images):
            infos = image.infos
            cases = (
                infos.chemin.name,
                _taille(infos.largeur, infos.hauteur),
                _taille(*image.finale),
                texte_du_changement(image),
            )
            for colonne, texte in enumerate(cases):
                case = QTableWidgetItem(texte)
                if COLONNES[colonne].a_droite:
                    case.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if image.fortement_agrandie and colonne == len(cases) - 1:
                    case.setForeground(qcolor(Couleurs.AVERTISSEMENT))
                    case.setToolTip("Agrandie plus de 2 fois : elle paraîtra plus douce.")
                self.tableau.setItem(rang, colonne, case)
        self.tableau.contenu_change()
        self.tableau.setVisible(bool(images))
        # Le tableau à la hauteur de ses lignes, jusqu'à sa hauteur habituelle : il défile au-delà.
        hauteur = self.tableau.horizontalHeader().sizeHint().height() + len(images) * Hauteurs.LIGNE_TABLEAU
        self.tableau.setFixedHeight(min(Dimensions.TABLEAU_HAUTEUR_MIN, hauteur))

    def _mettre_a_jour_les_boutons(self) -> None:
        pret = self._plan is not None and bool(self._plan.images)
        actif = self._bouton_occupe.est(self.bouton_redimensionner)
        self.bouton_redimensionner.setEnabled((pret and not self._occupe) or actif)

    # --- Redimensionner ----------------------------------------------------------------------

    def redimensionner(self) -> bool:
        """Lance la fabrication des images (en arrière-plan). Renvoie True si elle commence."""
        plan = self._plan
        if plan is None or not plan.images or self._occupe:
            return False
        existantes = plan.existantes
        if existantes:
            nombre = len(existantes)
            question = f"{quantite(nombre, 'image')} du même nom {'est' if nombre == 1 else 'sont'} déjà dans « {plan.dossier_sortie.name} »."
            if not messages.confirmer(
                self,
                "Remplacer des images",
                question,
                "Elles seront remplacées par les nouvelles. Tes originaux ne changent pas.",
                action="Remplacer",
                icone_action="refresh-cw",
            ):
                return False
        self._arret = threading.Event()
        arret = self._arret
        filtre, qualite = self.filtre.currentData(), self.qualite.currentData()
        self._afficher("", "secondaire")
        self._cacher_les_boutons_de_fin()
        self.barre.definir(0)
        self.avancee.setText(f"0 sur {quantite(len(plan.images), 'image')}")
        self.zone_avancement.show()
        self.bouton_arreter.setEnabled(True)
        self.bouton_arreter.show()
        self._occuper(True, self.bouton_redimensionner)
        taches.lancer_avec_progres(
            lambda progres: preparer_les_images(plan, filtre, qualite, progres, arret),
            self._termine,
            self._echec,
            self._progres,
        )
        return True

    def _progres(self, valeur) -> None:
        faites, total = valeur
        self.barre.definir(faites / max(1, total))
        self.avancee.setText(f"{faites} sur {quantite(total, 'image')}")

    def arreter(self) -> None:
        """« Arrêter » : les images pas encore commencées ne le sont plus (aussi à la fermeture de l'app)."""
        if self._arret is not None and self._occupe:
            self._arret.set()
            self.bouton_arreter.setEnabled(False)
            self.avancee.setText("Arrêt en cours…")

    def _fin(self) -> None:
        self._occuper(False)
        self.zone_avancement.hide()
        self.bouton_arreter.hide()

    def _termine(self, bilan: Bilan) -> None:
        self._fin()
        self._derniere_sortie = bilan.dossier_sortie
        self._actualiser()  # les images faites sont maintenant dans le dossier de sortie
        self.bouton_ouvrir.setVisible(bilan.faites > 0)
        self.bouton_renommer.setVisible(bilan.faites > 0)
        self._afficher(bilan.message(), "avertissement" if bilan.erreurs or bilan.arrete else "succes")

    def _echec(self, erreur: Exception) -> None:
        self._fin()
        self._actualiser()
        self._afficher(f"Impossible d'enregistrer les images : {erreur}", "erreur")

    def _cacher_les_boutons_de_fin(self) -> None:
        self.bouton_ouvrir.hide()
        self.bouton_renommer.hide()

    def trier_et_renommer(self) -> None:
        dossier = self._derniere_sortie
        if dossier is not None and dossier.is_dir():
            self.renommer_demande.emit(dossier)

    def ouvrir_le_dossier(self) -> None:
        dossier = self._derniere_sortie or self.dossier_de_sortie()
        if dossier is not None and dossier.is_dir():
            ouvrir_dossier(dossier)

    # --- Outils -----------------------------------------------------------------------------

    def _occuper(self, occupe: bool, bouton_occupe=None) -> None:
        """Pendant la lecture du dossier ou la fabrication des images : le cercle tourne dans le bouton
        qui a lancé le travail ; les réglages et les autres boutons sont grisés (V3.1)."""
        self._occupe = occupe
        if occupe:
            self._bouton_occupe.occuper(bouton_occupe)
        else:
            self._bouton_occupe.liberer()
        actif = self._bouton_occupe.est
        self.cadre_taille.setEnabled(not occupe)
        self.cadre_sortie.setEnabled(not occupe)
        self.bouton_changer.setEnabled(not occupe or actif(self.bouton_changer))
        self.zone_depot.setEnabled(not occupe or actif(self.zone_depot.bouton_choisir))
        self._mettre_a_jour_les_boutons()

    def _afficher(self, message: str, role: str) -> None:
        # Vert, rouge ou orange : effacé après 8 s (V3.2) ; la ligne garde sa place.
        afficher_message(self.statut, message, role, cacher_vide=False)
