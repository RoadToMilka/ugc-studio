"""Module Renommer (V4, lot 2 ; cahier des charges §8 bis.2) : choisir l'ordre des images d'un dossier
en les cliquant, puis les renommer toutes d'un coup avec un masque, comme l'action « Énumération »
d'Ant Renamer. Le calcul et le renommage sont dans renommage.py.

Le parcours, de haut en bas :
1. Dossier : glisser-déposer ou « Choisir un dossier… » (ou « Trier et renommer » à la fin du module
   Images). « Fermer le dossier » le fait oublier à l'app (4.0.4).
2. Ordre : les images en vignettes. Un clic leur donne le numéro suivant (en mauve), un nouveau clic
   le leur retire ; les autres suivent dans l'ordre de l'affichage (numéros gris). Double-clic :
   l'image en grand.
3. Nom : le masque (%num%, %name%, %ext%…), « Démarrer à », « Nombre de chiffres », « Incrémenter de ».
4. Aperçu : chaque image dans l'ordre final, son nom actuel et son nouveau nom ; en rouge, un nom que
   Windows refuserait ; en orange, ce qui mérite un coup d'œil.
5. « Renommer », puis « Annuler le dernier renommage » si besoin.

Ce module ne dépend pas d'un projet : ses réglages sont retenus dans les préférences de l'app.
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from ....chemins import chemin_a_afficher, dossier_documents, dossier_donnees
from ....dossiers import EXTENSIONS_IMAGES
from ....images.vignettes import faire_les_vignettes
from ....renommage import (
    FICHIER_JOURNAL,
    MASQUE_PAR_DEFAUT,
    NOM,
    TRIS,
    ContenuDuDossier,
    JournalDesRenommages,
    Numerotation,
    PlanDeRenommage,
    Renommage,
    RenommageImpossible,
    annuler,
    lire_le_dossier,
    maintenant,
    ordre_final,
    planifier,
    quantite,
    renommer,
    trier,
)
from ....services import Services
from ... import taches
from ...composants.bouton import BoutonOccupe
from ...composants.depot_dossier import ZoneDepotDossier, dossier_depose
from ...composants.elements import (
    ChampNomme,
    afficher_message,
    bloc,
    bouton,
    libelle,
    liste_deroulante,
)
from ...composants.masque import ChampsDuMasque
from ...composants.tableau import Colonne, Tableau
from ...dialogues import messages
from ...theme import Couleurs, Dimensions, Espacements, Hauteurs, qcolor
from ..base import Page
from .grille import GrilleVignettes, qimage_depuis_pillow
from .image_en_grand import FenetreImageEnGrand

TITRE = "Renommer"
SOUS_TITRE = "Choisis l'ordre des images en les cliquant, puis renomme-les toutes d'un coup."

# Préférences (§10) : ce module ne dépend pas d'un projet. Celles du masque sont écrites par ses champs
# (composants/masque.py), sous ce préfixe.
PREFIXE = "renommer"
PREF_DOSSIER = "renommer_dossier"
PREF_MASQUE = f"{PREFIXE}_masque"
PREF_MASQUES_RECENTS = f"{PREFIXE}_masques_recents"
PREF_DEPART = f"{PREFIXE}_depart"
PREF_CHIFFRES = f"{PREFIXE}_chiffres"
PREF_PAS = f"{PREFIXE}_pas"
PREF_TRI = "renommer_tri"

FORMATS_ACCEPTES = "JPG, PNG, WebP, AVIF, TIFF ou BMP"

AIDE_DOSSIER = (
    "Les images du dossier lui-même (JPG, PNG, WebP, AVIF, TIFF, BMP), pas celles de ses sous-dossiers. "
    "Seul leur nom change, jamais leur contenu."
)
AIDE_FERMER = (
    "L'app oublie ce dossier : la zone redevient vide. Tes images ne bougent pas ; tes réglages et "
    "« Annuler le dernier renommage » restent."
)
AIDE_ORDRE = (
    "Clique les images dans l'ordre voulu : la première cliquée prend le premier numéro (en mauve), la "
    "suivante le deuxième… Un nouveau clic lui retire son numéro, et les suivantes remontent. Les autres "
    "suivent, dans l'ordre de l'affichage (numéros gris). Double-clic : l'image en grand."
)
AIDE_NOM = (
    "Le masque est le nouveau nom, avec des balises remplacées pour chaque image, comme dans Ant Renamer :\n"
    "%num% : le numéro (obligatoire)\n"
    "%name% : le nom actuel, sans l'extension\n"
    "%ext% : l'extension, avec son point (.jpg)\n"
    "%folder1% : le nom du dossier (%folder2% : celui du dessus…)\n"
    "%% : le caractère %\n"
    "Exemple : NeMu_JPG_%num%%ext% donne NeMu_JPG_01.jpg, NeMu_JPG_02.jpg…"
)
AIDE_APERCU = (
    "Chaque image dans l'ordre final, avec son nouveau nom. En rouge, un nom que Windows refuserait : rien "
    "n'est renommé tant qu'il en reste. En orange, ce qui mérite un coup d'œil."
)
AIDE_ANNULER = "Remet les anciens noms du dernier renommage. L'app garde la liste des 20 derniers, dans son dossier de données."

# Balises à ajouter au masque d'un clic (à l'endroit du curseur), avec ce qu'elles donnent.
BALISES = (
    ("%num%", "Le numéro (obligatoire)"),
    ("%name%", "Le nom actuel, sans l'extension"),
    ("%ext%", "L'extension, avec son point (.jpg)"),
    ("%folder1%", "Le nom du dossier"),
)

COLONNES = (
    Colonne("N°", a_droite=True),
    Colonne("Nom actuel", texte=True),
    Colonne("Nouveau nom", texte=True, etiree=True),
    Colonne("Remarque", texte=True),
)


def date_lisible(iso: str) -> str:
    """« aujourd'hui à 19:42 », ou « le 03/10/2026 à 19:42 »."""
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    jour = "aujourd'hui" if moment.date() == date.today() else f"le {moment:%d/%m/%Y}"
    return f"{jour} à {moment:%H:%M}"


class PageRenommer(Page):
    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="renommer")
        self._preferences = services.preferences
        self._dossier: Path | None = None
        self._contenu: ContenuDuDossier | None = None
        self._affichage: list[Path] = []  # les images dans l'ordre de l'affichage
        self._choisies: list[Path] = []  # les images cliquées, dans l'ordre des clics
        self._vignettes: dict[Path, QPixmap | None] = {}
        # La date de modification de chaque image quand sa vignette a été demandée (V4, 4.0.2) : une
        # image remplacée depuis (même nom, autre contenu, par exemple un nouveau redimensionnement)
        # reçoit une nouvelle vignette quand le dossier est relu ; elle gardait l'ancienne.
        self._dates_des_vignettes: dict[Path, float] = {}
        self._plan: PlanDeRenommage | None = None
        self._occupe = False
        self._bouton_occupe = BoutonOccupe()
        self._lecture = 0  # numéro de la dernière lecture de dossier lancée (une plus ancienne est ignorée)
        self._serie = 0  # numéro de la dernière série de vignettes lancée (une plus ancienne est ignorée)
        self._arret_vignettes: threading.Event | None = None
        self._avant_le_clic: tuple[Path, list[Path]] | None = None  # pour défaire le clic d'un double-clic
        self._dernier: Renommage | None = self.journal().dernier()
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
        self.bouton_fermer = bouton("Fermer le dossier", variante="contour", nom_icone="x", action=self.fermer_le_dossier)
        self.bouton_fermer.setToolTip(AIDE_FERMER)
        ligne.addWidget(self.bouton_fermer, 0, Qt.AlignmentFlag.AlignTop)
        self.ligne_dossier.hide()
        d.addWidget(self.ligne_dossier)
        self.contenu.addWidget(self.cadre_dossier)

        # --- Ordre ---
        self.cadre_ordre, d = bloc("Ordre", aide=AIDE_ORDRE)
        outils = QHBoxLayout()
        outils.setContentsMargins(0, 0, 0, 0)
        outils.setSpacing(Espacements.M)
        self.tri = liste_deroulante()
        for cle, nom in TRIS.items():
            self.tri.addItem(nom, cle)
        self._choisir(self.tri, self._preferences.lire(PREF_TRI, NOM))
        outils.addWidget(ChampNomme("Afficher par", self.tri))
        self.cliquees = libelle("", "legende")
        outils.addWidget(self.cliquees, 1, Qt.AlignmentFlag.AlignBottom)
        self.bouton_effacer = bouton("Tout effacer", variante="contour", nom_icone="eraser", action=self.tout_effacer)
        self.bouton_effacer.setToolTip("Retire les numéros donnés en cliquant : toutes les images suivent l'ordre de l'affichage.")
        outils.addWidget(self.bouton_effacer, 0, Qt.AlignmentFlag.AlignBottom)
        d.addLayout(outils)
        self.grille = GrilleVignettes()
        self.grille.clic.connect(self.cliquer)
        self.grille.double_clic.connect(self._double_clic)
        d.addWidget(self.grille)
        self.sans_image = libelle("", "discret")
        d.addWidget(self.sans_image)
        self.contenu.addWidget(self.cadre_ordre)

        # --- Nom ---
        # Les champs du masque sont un composant commun avec l'Upscale vidéo (4.1.0) : la même
        # présentation et le même comportement dans toute l'app (demande de l'utilisateur).
        self.cadre_nom, d = bloc("Nom", aide=AIDE_NOM)
        self.champs_nom = ChampsDuMasque(self._preferences, PREFIXE, MASQUE_PAR_DEFAUT, BALISES)
        d.addWidget(self.champs_nom)
        self.masque, self.depart = self.champs_nom.masque, self.champs_nom.depart
        self.chiffres, self.pas = self.champs_nom.chiffres, self.champs_nom.pas
        self.boutons_balises = self.champs_nom.boutons_balises
        self.contenu.addWidget(self.cadre_nom)

        # --- Aperçu ---
        self.cadre_apercu, d = bloc("Aperçu", aide=AIDE_APERCU)
        self.resume = libelle("", "secondaire")
        d.addWidget(self.resume)
        self.alertes = libelle("", "avertissement")
        d.addWidget(self.alertes)
        self.tableau = Tableau(COLONNES)
        d.addWidget(self.tableau)
        self.contenu.addWidget(self.cadre_apercu)

        # --- Renommer ---
        action = QVBoxLayout()
        action.setSpacing(Espacements.S)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_renommer = bouton("Renommer", variante="principal", nom_icone="pen-line", action=self.renommer)
        boutons.addWidget(self.bouton_renommer)
        self.bouton_annuler = bouton("Annuler le dernier renommage", nom_icone="undo-2", action=self.annuler_le_dernier)
        boutons.addWidget(self.bouton_annuler)
        boutons.addStretch(1)
        action.addLayout(boutons)
        self.statut = libelle("", "secondaire")
        action.addWidget(self.statut)
        self.contenu.addLayout(action)

        self.tri.currentIndexChanged.connect(lambda _index: self._tri_change())
        self.champs_nom.change.connect(self._actualiser)
        self._actualiser()

    @staticmethod
    def _choisir(liste, valeur) -> None:
        index = liste.findData(valeur)
        liste.setCurrentIndex(index if index >= 0 else 0)

    @property
    def occupe(self) -> bool:
        return self._occupe

    def journal(self) -> JournalDesRenommages:
        # Lu au moment voulu : le dossier des données peut changer (tests, autotest).
        return JournalDesRenommages(dossier_donnees() / FICHIER_JOURNAL)

    # --- Dossier -----------------------------------------------------------------------------

    def choisir_dossier(self) -> None:
        if self._occupe:
            return
        depart = self._dossier or Path(self._preferences.lire(PREF_DOSSIER) or dossier_documents())
        choix = QFileDialog.getExistingDirectory(self, "Choisir un dossier d'images", str(depart))
        if choix:
            self.ouvrir(Path(choix))

    def ouvrir(self, dossier: Path, garder_l_ordre: bool = False) -> None:
        """Lit les images de `dossier` (en arrière-plan), puis les montre en vignettes. Les numéros
        donnés en cliquant repartent de zéro (sauf `garder_l_ordre` : relecture du même dossier après un
        renommage impossible) ; les vignettes déjà faites pour ce dossier restent."""
        if self._occupe:
            return
        if dossier != self._dossier:
            self._vignettes, self._dates_des_vignettes = {}, {}
            garder_l_ordre = False
        self._dossier = dossier
        self._preferences.ecrire(PREF_DOSSIER, str(dossier))
        if not garder_l_ordre:
            self._choisies = []
        self._contenu, self._affichage, self._plan = None, [], None
        self._arreter_les_vignettes()
        self._lecture += 1
        numero = self._lecture
        self.chemin.setText(chemin_a_afficher(dossier))
        self.compte.setText("Lecture des images…")
        self.zone_depot.hide()
        self.ligne_dossier.show()
        self._occuper(True, self.bouton_changer)
        taches.lancer(
            lambda: lire_le_dossier(dossier),
            lambda contenu, n=numero: self._dossier_lu(n, contenu),
            lambda erreur, n=numero: self._lecture_echouee(n, erreur),
        )

    def fermer_le_dossier(self) -> bool:
        """« Fermer le dossier » (4.0.4) : l'app oublie le dossier, la zone redevient « Glisse un dossier
        d'images ici ». Les fichiers ne bougent pas ; les réglages et « Annuler le dernier renommage »
        restent (l'historique est dans les données de l'app). Si des images ont été cliquées, l'app
        demande d'abord : cet ordre serait perdu. Renvoie True si le dossier est fermé."""
        if self._occupe or self._dossier is None:
            return False
        if self._choisies:
            nombre = len(self._choisies)
            if not messages.confirmer(
                self,
                "Fermer le dossier",
                f"Fermer « {self._dossier.name} » ?",
                f"L'ordre que tu as cliqué ({quantite(nombre, 'image')}) sera perdu. Tes images ne changent pas.",
                action="Fermer le dossier",
                icone_action="x",
            ):
                return False
        self._arreter_les_vignettes()
        self._lecture += 1  # une lecture encore en route serait ignorée
        self._dossier = None
        self._contenu, self._affichage, self._choisies, self._plan = None, [], [], None
        self._vignettes, self._dates_des_vignettes = {}, {}
        self._avant_le_clic = None
        self.grille.remplir([], {})
        self.chemin.setText("")
        self.compte.setText("")
        self.ligne_dossier.hide()
        self.zone_depot.show()
        self._afficher("", "secondaire")
        self._actualiser()
        return True

    def _dossier_lu(self, numero: int, contenu: ContenuDuDossier) -> None:
        if numero != self._lecture:
            return  # un autre dossier a été choisi depuis
        self._contenu = contenu
        presentes = {image.chemin for image in contenu.images}
        self._choisies = [chemin for chemin in self._choisies if chemin in presentes]
        self._occuper(False)
        nombre = len(contenu.images)
        self.compte.setText(quantite(nombre, "image") if nombre else f"Aucune image dans ce dossier ({FORMATS_ACCEPTES})")
        dates = {image.chemin: image.modifiee for image in contenu.images}
        for chemin in [c for c in self._vignettes if c in dates and self._dates_des_vignettes.get(c) != dates[c]]:
            del self._vignettes[chemin]  # image remplacée depuis sa vignette : à refaire
        self._afficher_les_images()
        manquantes = [image.chemin for image in contenu.images if image.chemin not in self._vignettes]
        if manquantes:
            self._dates_des_vignettes.update({chemin: dates[chemin] for chemin in manquantes})
            self._lancer_les_vignettes(manquantes)

    def _lecture_echouee(self, numero: int, erreur: Exception) -> None:
        if numero != self._lecture:
            return
        self._occuper(False)
        self.compte.setText("")
        self._afficher(f"Impossible de lire ce dossier : {erreur}", "erreur")
        self._actualiser()

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

    # --- Vignettes ---------------------------------------------------------------------------

    def _lancer_les_vignettes(self, chemins: list[Path]) -> None:
        """Les vignettes en arrière-plan : elles s'affichent au fur et à mesure."""
        self._arreter_les_vignettes()
        arret = threading.Event()
        self._arret_vignettes = arret
        self._serie += 1
        serie = self._serie
        ratio = self.devicePixelRatioF()
        cote = round(Dimensions.RENOMMER_IMAGE * ratio)
        taches.lancer_avec_progres(
            lambda progres: faire_les_vignettes(chemins, cote, qimage_depuis_pillow, progres, arret),
            lambda _nombre: None,
            None,
            lambda valeur, s=serie: self._vignette_prete(s, valeur, ratio),
        )

    def _vignette_prete(self, serie: int, valeur, ratio: float) -> None:
        if serie != self._serie:
            return  # série arrêtée (autre dossier, renommage) : ce fichier a pu changer de nom
        chemin, image = valeur
        vignette = None
        if isinstance(image, QImage) and not image.isNull():
            vignette = QPixmap.fromImage(image)
            vignette.setDevicePixelRatio(ratio)
        self._vignettes[chemin] = vignette
        self.grille.definir_vignette(chemin, vignette)

    def _arreter_les_vignettes(self) -> None:
        self._serie += 1  # les vignettes encore en route seront ignorées
        if self._arret_vignettes is not None:
            self._arret_vignettes.set()
            self._arret_vignettes = None

    def arreter(self) -> None:
        """À la fermeture de l'app : les vignettes pas encore faites ne le sont plus."""
        self._arreter_les_vignettes()

    # --- Ordre -------------------------------------------------------------------------------

    def _afficher_les_images(self) -> None:
        """Les images dans l'ordre de l'affichage choisi, puis les numéros et l'aperçu."""
        images = self._contenu.images if self._contenu is not None else ()
        self._affichage = [image.chemin for image in trier(images, self.tri.currentData())]
        self.grille.remplir(self._affichage, self._vignettes)
        self._actualiser()

    def _tri_change(self) -> None:
        self._preferences.ecrire(PREF_TRI, self.tri.currentData())
        self._afficher_les_images()

    def cliquer(self, chemin: Path) -> None:
        """Un clic sur une image : elle prend le numéro suivant, ou le perd (les suivantes remontent)."""
        if self._occupe or chemin not in self._affichage:
            return
        self._avant_le_clic = (chemin, list(self._choisies))
        if chemin in self._choisies:
            self._choisies.remove(chemin)
        else:
            self._choisies.append(chemin)
        self._actualiser()

    def _double_clic(self, chemin: Path) -> None:
        """Double-clic : l'image en grand. Le premier clic du double-clic a changé son numéro : l'ordre
        redevient celui d'avant ce clic."""
        if self._avant_le_clic is not None and self._avant_le_clic[0] == chemin:
            self._choisies = self._avant_le_clic[1]
            self._avant_le_clic = None
            self._actualiser()
        self.voir_en_grand(chemin)

    def voir_en_grand(self, chemin: Path) -> FenetreImageEnGrand:
        """L'image en grand, dans une fenêtre (fermée par « Fermer » ou Échap)."""
        fenetre = FenetreImageEnGrand(self, chemin)
        fenetre.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        fenetre.open()
        return fenetre

    def tout_effacer(self) -> None:
        self._choisies = []
        self._actualiser()

    # --- Nom ---------------------------------------------------------------------------------

    def masque_saisi(self) -> str:
        return self.champs_nom.texte()

    def numerotation(self) -> Numerotation:
        return self.champs_nom.numerotation()

    def inserer_balise(self, balise: str) -> None:
        """Ajoute la balise au masque, à l'endroit du curseur (à la fin si on n'a pas cliqué dedans)."""
        self.champs_nom.inserer_balise(balise)

    # --- Aperçu ------------------------------------------------------------------------------

    def _actualiser(self) -> None:
        """Le plan selon l'ordre et le masque, puis les numéros des vignettes, l'aperçu et les boutons."""
        self._plan = None
        if self._contenu is not None and self._contenu.images:
            ordre = ordre_final(self._affichage, self._choisies)
            self._plan = planifier(self._contenu, ordre, self.masque_saisi(), self.numerotation())
        plan = self._plan
        numeros = {}
        if plan is not None:
            if plan.lignes:
                numeros = {ligne.chemin: (ligne.numero, ligne.choisie, bool(ligne.probleme)) for ligne in plan.lignes}
            else:  # masque inutilisable : les numéros seuls, sans nom
                ordre = ordre_final(self._affichage, self._choisies)
                numeros = {chemin: (self.numerotation().numero(rang), choisie, False) for rang, (chemin, choisie) in enumerate(ordre)}
        self.grille.definir_numeros(numeros)
        lu = self._contenu is not None
        avec_images = lu and bool(self._contenu.images)
        self.cadre_ordre.setVisible(lu)
        self.grille.setVisible(avec_images)
        self.sans_image.setText("" if avec_images else f"Aucune image dans ce dossier ({FORMATS_ACCEPTES})")
        self.sans_image.setVisible(lu and not avec_images)
        nombre = len(self._choisies)
        if avec_images:
            self.cliquees.setText(
                f"{nombre} cliquée{'s' if nombre > 1 else ''} sur {len(self._affichage)}, les autres suivent"
                if nombre
                else "Clique les images dans l'ordre voulu"
            )
        else:
            self.cliquees.setText("")
        self.bouton_effacer.setEnabled(bool(nombre) and not self._occupe)
        self.cadre_apercu.setVisible(avec_images)
        if plan is not None:
            self.resume.setText(plan.resume())
            self.resume.setProperty("role", "erreur" if (plan.erreur or plan.problemes) else "secondaire")
            self.alertes.setText("\n".join(plan.alertes))
            self.alertes.setVisible(bool(plan.alertes))
        else:
            self.resume.setText("")
            self.alertes.setText("")
            self.alertes.hide()
        for etiquette in (self.resume, self.alertes):
            etiquette.style().unpolish(etiquette)
            etiquette.style().polish(etiquette)
        self._remplir_le_tableau(plan)
        self._mettre_a_jour_les_boutons()

    def _remplir_le_tableau(self, plan: PlanDeRenommage | None) -> None:
        lignes = plan.lignes if plan is not None else []
        self.tableau.setRowCount(len(lignes))
        for rang, ligne in enumerate(lignes):
            remarque = ligne.probleme or ligne.avertissement or ("garde son nom" if ligne.inchangee else "")
            cases = (ligne.numero, ligne.chemin.name, ligne.nouveau, remarque)
            for colonne, texte in enumerate(cases):
                case = QTableWidgetItem(texte)
                if COLONNES[colonne].a_droite:
                    case.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if colonne == 0 and ligne.choisie:
                    case.setForeground(qcolor(Couleurs.ACCENT_SURVOL))
                    case.setToolTip("Numéro donné en cliquant")
                if colonne >= 2:
                    if ligne.probleme:
                        case.setForeground(qcolor(Couleurs.ERREUR))
                    elif ligne.avertissement:
                        case.setForeground(qcolor(Couleurs.AVERTISSEMENT))
                    elif ligne.inchangee:
                        case.setForeground(qcolor(Couleurs.TEXTE_SECONDAIRE))
                if colonne == 3 and remarque:
                    case.setToolTip(remarque)
                self.tableau.setItem(rang, colonne, case)
        self.tableau.contenu_change()
        self.tableau.setVisible(bool(lignes))
        # Le tableau à la hauteur de ses lignes, jusqu'à sa hauteur habituelle : il défile au-delà.
        hauteur = self.tableau.horizontalHeader().sizeHint().height() + len(lignes) * Hauteurs.LIGNE_TABLEAU
        self.tableau.setFixedHeight(min(Dimensions.TABLEAU_HAUTEUR_MIN, hauteur))

    def _mettre_a_jour_les_boutons(self) -> None:
        pret = self._plan is not None and self._plan.possible
        actif = self._bouton_occupe.est
        self.bouton_renommer.setEnabled((pret and not self._occupe) or actif(self.bouton_renommer))
        dernier = self._dernier
        self.bouton_annuler.setEnabled((dernier is not None and not self._occupe) or actif(self.bouton_annuler))
        if dernier is None:
            self.bouton_annuler.setToolTip(AIDE_ANNULER)
        else:
            self.bouton_annuler.setToolTip(
                f"Remet les anciens noms de {quantite(len(dernier.changements), 'image')} dans « {dernier.dossier.name} » "
                f"(renommées {date_lisible(dernier.date)}).\n{AIDE_ANNULER}"
            )

    # --- Renommer ----------------------------------------------------------------------------

    def renommer(self) -> bool:
        """Renomme les images (en arrière-plan). Renvoie True si le renommage commence."""
        plan = self._plan
        if plan is None or not plan.possible or self._occupe:
            return False
        dossier, changements, masque = plan.dossier, plan.changements(), self.masque_saisi()
        self._arreter_les_vignettes()  # une vignette en route pourrait chercher un fichier déjà renommé
        self._afficher("", "secondaire")
        self._occuper(True, self.bouton_renommer)
        taches.lancer(
            lambda: renommer(dossier, changements),
            lambda nombre: self._renomme(dossier, changements, masque, nombre),
            self._renommage_echoue,
        )
        return True

    def _renomme(self, dossier: Path, changements: list[tuple[str, str]], masque: str, nombre: int) -> None:
        journal = self.journal()
        journal.ajouter(Renommage(dossier, maintenant(), tuple(changements)))
        self._dernier = journal.dernier()
        self.champs_nom.retenir(masque)
        self._occuper(False)
        self._renommer_les_vignettes(dossier, changements)
        self._afficher(f"{quantite(nombre, 'image')} renommée{'s' if nombre > 1 else ''}.", "succes")
        self.ouvrir(dossier)  # les nouveaux noms, dans l'ordre de l'Explorateur

    def _renommage_echoue(self, erreur: Exception) -> None:
        self._occuper(False)
        texte = str(erreur) if isinstance(erreur, RenommageImpossible) else f"Impossible de renommer : {erreur}"
        self._afficher(texte, "erreur")
        if self._dossier is not None:
            # Rien n'a changé, mais le dossier, lui, a pu changer (un fichier disparu) : on le relit, en
            # gardant les numéros donnés en cliquant.
            self.ouvrir(self._dossier, garder_l_ordre=True)

    def _renommer_les_vignettes(self, dossier: Path, changements) -> None:
        """Les vignettes suivent les fichiers renommés : pas besoin de les refaire."""
        if dossier != self._dossier:
            return
        anciennes = {ancien: self._vignettes.pop(dossier / ancien) for ancien, _n in changements if dossier / ancien in self._vignettes}
        dates = {ancien: self._dates_des_vignettes.pop(dossier / ancien) for ancien, _n in changements if dossier / ancien in self._dates_des_vignettes}
        for ancien, nouveau in changements:
            if anciennes.get(ancien) is not None:  # une case vide (vignette impossible) sera refaite
                self._vignettes[dossier / nouveau] = anciennes[ancien]
            if ancien in dates:  # renommer ne change pas la date de modification d'un fichier
                self._dates_des_vignettes[dossier / nouveau] = dates[ancien]

    # --- Annuler -----------------------------------------------------------------------------

    def annuler_le_dernier(self) -> bool:
        """« Annuler le dernier renommage », après confirmation. Renvoie True si l'annulation commence."""
        dernier = self.journal().dernier()
        if dernier is None or self._occupe:
            return False
        nombre = len(dernier.changements)
        if not messages.confirmer(
            self,
            "Annuler le dernier renommage",
            f"Remettre les anciens noms de {quantite(nombre, 'image')} dans « {dernier.dossier.name} » ?",
            f"Renommées {date_lisible(dernier.date)}. Seuls les noms changent, jamais les images.",
            action="Remettre les anciens noms",
            icone_action="undo-2",
        ):
            return False
        self._arreter_les_vignettes()
        self._afficher("", "secondaire")
        self._occuper(True, self.bouton_annuler)
        taches.lancer(lambda: annuler(dernier), lambda n: self._annule(dernier, n), lambda e: self._annulation_echouee(dernier, e))
        return True

    def _annule(self, renommage: Renommage, nombre: int) -> None:
        self._oublier(renommage)
        self._occuper(False)
        self._renommer_les_vignettes(renommage.dossier, renommage.inverse())
        self._afficher(f"Anciens noms remis : {quantite(nombre, 'image')}.", "succes")
        if renommage.dossier == self._dossier:
            self.ouvrir(renommage.dossier)  # les anciens noms, dans l'ordre de l'Explorateur
        else:
            self._actualiser()

    def _annulation_echouee(self, renommage: Renommage, erreur: Exception) -> None:
        self._occuper(False)
        if isinstance(erreur, RenommageImpossible):
            texte = str(erreur)
            if erreur.definitif:  # il ne marchera pas mieux plus tard : on l'oublie
                self._oublier(renommage)
                texte += " Ce renommage ne peut plus être annulé."
        else:
            texte = f"Impossible d'annuler : {erreur}"
        self._afficher(texte, "erreur")
        if renommage.dossier == self._dossier:
            self.ouvrir(renommage.dossier, garder_l_ordre=True)
        else:
            self._actualiser()

    def _oublier(self, renommage: Renommage) -> None:
        journal = self.journal()
        journal.retirer(renommage)
        self._dernier = journal.dernier()

    # --- Outils ------------------------------------------------------------------------------

    def _occuper(self, occupe: bool, bouton_occupe=None) -> None:
        """Pendant la lecture du dossier ou le renommage : le cercle tourne dans le bouton qui a lancé le
        travail ; les réglages et les autres boutons sont grisés (V3.1)."""
        self._occupe = occupe
        if occupe:
            self._bouton_occupe.occuper(bouton_occupe)
        else:
            self._bouton_occupe.liberer()
        actif = self._bouton_occupe.est
        self.cadre_nom.setEnabled(not occupe)
        self.tri.setEnabled(not occupe)
        self.grille.setEnabled(not occupe)
        self.bouton_effacer.setEnabled(bool(self._choisies) and not occupe)
        self.bouton_changer.setEnabled(not occupe or actif(self.bouton_changer))
        self.bouton_fermer.setEnabled(not occupe)
        self.zone_depot.setEnabled(not occupe or actif(self.zone_depot.bouton_choisir))
        self._mettre_a_jour_les_boutons()

    def _afficher(self, message: str, role: str) -> None:
        # Vert, rouge ou orange : effacé après 8 s (V3.2) ; la ligne garde sa place.
        afficher_message(self.statut, message, role, cacher_vide=False)
