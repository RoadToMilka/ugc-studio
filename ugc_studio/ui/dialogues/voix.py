"""Bibliothèque de voix (§5.4) : les voix de Google, filtrables, et « Mes voix » (Voice Design).

- « Voix Google » : la bibliothèque étendue (plus de 2 000 voix), avec filtres (langue, genre,
  hauteur, accent, persona, contexte, recherche) et favoris ★. Elle est gardée en mémoire une
  semaine ; « Actualiser » la redemande à Google. 20 voix s'affichent, puis 20 de plus à chaque clic
  sur « Afficher 20 voix de plus » : construire des centaines de lignes d'un coup rendait la
  fenêtre lente.
- « Mes voix » : les voix créées avec Voice Design (ici ou dans Google AI Studio), avec leur date
  d'expiration et le compteur x / 200. On peut les écouter, les renommer, les supprimer.
Chaque voix s'écoute (▶) et se choisit pour le projet en un clic.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ...fournisseurs.capacites import modele_connu
from ...fournisseurs.voix import VoixBibliotheque
from ...montants import nombre_lisible
from ...projets import LANGUE_PAR_DEFAUT, LANGUES
from ...services import Services
from ...voix_locales import (
    BIBLIOTHEQUE,
    GENRES,
    HAUTEURS,
    MAX_VOIX_CREEES,
    NOMS,
    TRADUCTIONS,
    VOIX_CREEES,
    date_lisible,
    est_expiree,
    voix_de_base_en_bibliotheque,
)
from .. import taches
from ..composants.bouton import montrer_occupe
from ..composants.conseils import entete_de_fenetre
from ..composants.elements import (
    BoutonInfo,
    afficher_message,
    bouton,
    conteneur_vertical,
    libelle,
    ligne_avec_aide,
    liste_deroulante,
    vider_disposition,
)
from ..composants.lecteur import Lecteur
from ..composants.menu import Menu
from ..composants.onglets import Onglets
from ..connexion_ia import adaptateur_par_defaut, message_erreur
from ..extraits import EcouteVoix
from ..icones import icone, icone_menu
from ..composants.defilement import zone_defilante
from ..theme import Couleurs, Dimensions, Espacements

LIGNES_PAR_PAGE = 20  # voix affichées d'un coup ; « Afficher 20 voix de plus » ajoute les suivantes
DELAI_RECHERCHE_MS = 300  # la recherche attend une courte pause dans la frappe avant de filtrer
FILTRES_PAR_LIGNE = 3
TOUS = ""


def nom_langue(code: str) -> str:
    return LANGUES.get(code, code)


def details_voix(voix: VoixBibliotheque) -> str:
    """« Français · féminine · grave · accent parisien · Warm, Friendly · Commercial »."""
    morceaux = [
        nom_langue(voix.langue) if voix.langue else "",
        GENRES.get(voix.genre, voix.genre),
        f"voix {HAUTEURS[voix.hauteur]}" if voix.hauteur in HAUTEURS else "",
        f"accent {voix.accent}" if voix.accent else "",
        voix.persona,
        voix.contexte,
    ]
    return "  ·  ".join(m for m in morceaux if m)


class LigneVoix(QFrame):
    """Une voix : ★ favori, nom et détails, ▶ écouter, Choisir (et ⋯ pour une voix créée)."""

    def __init__(self, dialogue: DialogueBibliothequeVoix, voix: VoixBibliotheque):
        super().__init__()
        self.setProperty("role", "ligne")
        self.voix = voix
        services = dialogue.services
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.M)

        self.etoile = bouton("", variante="icone", action=lambda: dialogue.basculer_favori(self))
        self.etoile.setIconSize(QSize(Dimensions.ETOILE, Dimensions.ETOILE))
        self.afficher_favori(services.voix.est_favori(voix.identifiant))
        disposition.addWidget(self.etoile, 0, Qt.AlignmentFlag.AlignTop)

        textes = QVBoxLayout()
        textes.setSpacing(0)
        textes.addWidget(libelle(services.voix.nom(voix.identifiant), "intitule", retour_a_la_ligne=False))
        details = details_voix(voix)
        if voix.creee:
            connu = modele_connu(voix.modele)
            expiration = date_lisible(voix.expire_le)
            morceaux = [connu.nom if connu else voix.modele]
            if est_expiree(voix):
                morceaux.append("expirée")
            elif expiration:
                morceaux.append(f"expire le {expiration}")
            details = "  ·  ".join(m for m in (details, *morceaux) if m)
        if details:
            textes.addWidget(libelle(details, "legende"))
        if voix.description:
            textes.addWidget(libelle(voix.description, "secondaire", selectionnable=True))
        traduction = services.voix.description_fr(voix.identifiant)
        if traduction:
            textes.addWidget(libelle(f"Traduction : {traduction}", "legende"))
        disposition.addLayout(textes, 1)

        ecouter = bouton("", variante="icone", nom_icone="play")
        ecouter.clicked.connect(lambda: dialogue.ecouter(voix, ecouter))  # le cercle y tourne (V3.1)
        ecouter.setToolTip("Écouter un extrait de cette voix")
        disposition.addWidget(ecouter, 0, Qt.AlignmentFlag.AlignVCenter)
        self.bouton_choisir = bouton("Choisir", action=lambda: dialogue.choisir(voix))
        self.bouton_choisir.setEnabled(not est_expiree(voix))
        disposition.addWidget(self.bouton_choisir, 0, Qt.AlignmentFlag.AlignVCenter)
        if voix.creee:
            plus = bouton("", variante="icone", nom_icone="ellipsis")
            plus.setToolTip("Renommer ou supprimer cette voix")
            menu = Menu(plus)
            menu.addAction(icone_menu("pencil"), "Renommer…").triggered.connect(lambda: dialogue.renommer(voix))
            menu.addSeparator()
            menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer…").triggered.connect(
                lambda: dialogue.supprimer(voix)
            )
            plus.setMenu(menu)
            disposition.addWidget(plus, 0, Qt.AlignmentFlag.AlignVCenter)

    def afficher_favori(self, favori: bool) -> None:
        couleur = Couleurs.AVERTISSEMENT if favori else Couleurs.TEXTE_DESACTIVE
        self.etoile.setIcon(icone("star", couleur, rempli=favori, taille=Dimensions.ETOILE))
        self.etoile.setToolTip("Retirer des favoris" if favori else "Ajouter aux favoris")


class DialogueBibliothequeVoix(QDialog):
    """`modele` et `langue` : ceux du projet (écoute des extraits, voix créées)."""

    def __init__(self, services: Services, lecteur: Lecteur, parent=None, modele: str = "gemini-3.8-flash-tts",
                 langue: str = LANGUE_PAR_DEFAUT, onglet: int = 0):
        super().__init__(parent)
        self.services = services
        self._modele = modele
        self._langue = langue
        self.voix_choisie: VoixBibliotheque | None = None
        # Au départ, le filtre de langue montre la langue du projet… dès qu'elle est dans la liste :
        # la bibliothèque peut arriver après la liste « Mes voix » (deux demandes en parallèle).
        self._langue_en_attente = True
        self._lignes: list[LigneVoix] = []
        self._lignes_creees: list[LigneVoix] = []
        self._filtrees: list[VoixBibliotheque] = []
        self._ecoute = EcouteVoix(services, lecteur, self._afficher)
        self.setWindowTitle("Bibliothèque de voix")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre("Bibliothèque de voix", "bibliotheque-voix"))
        self.onglets = Onglets()
        self.onglets.addTab(self._onglet_google(), "Voix Google")
        self.onglets.addTab(self._onglet_mes_voix(), "Mes voix")
        disposition.addWidget(self.onglets, 1)

        bas = QHBoxLayout()
        bas.setSpacing(Espacements.S)
        self.statut = libelle("", "secondaire")
        bas.addWidget(self.statut, 1)
        bas.addWidget(bouton("Fermer", action=self.reject))
        disposition.addLayout(bas)

        # Chaque liste ne se reconstruit que quand ce qu'elle montre change (un favori ne
        # reconstruit rien : seule l'étoile de sa ligne change).
        self._abonnements = (
            (self._remplir_filtres, {BIBLIOTHEQUE}),
            (self._remplir_voix_creees, {VOIX_CREEES, NOMS, TRADUCTIONS}),
        )
        for fonction, sujets in self._abonnements:
            services.voix.abonner(fonction, sujets)
        # Fenêtre détruite sans avoir été fermée normalement : on se désabonne quand même.
        abonnements = self._abonnements
        self.destroyed.connect(lambda: [services.voix.desabonner(fonction) for fonction, _s in abonnements])
        self._charger_bibliotheque(forcer=False)
        self._charger_voix_creees(forcer=False)
        self.onglets.setCurrentIndex(onglet)

    def done(self, resultat: int) -> None:
        for fonction, _sujets in self._abonnements:
            self.services.voix.desabonner(fonction)
        super().done(resultat)

    # --- Construction ------------------------------------------------------------------------

    def _onglet_google(self) -> QWidget:
        onglet = QWidget()
        disposition = QVBoxLayout(onglet)
        disposition.setContentsMargins(0, Espacements.M, 0, 0)
        disposition.setSpacing(Espacements.S)

        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher dans les noms et descriptions…")
        self._minuteur_recherche = QTimer(self)
        self._minuteur_recherche.setSingleShot(True)
        self._minuteur_recherche.setInterval(DELAI_RECHERCHE_MS)
        self._minuteur_recherche.timeout.connect(self._filtrer)
        self.recherche.textChanged.connect(lambda _texte: self._minuteur_recherche.start())
        ligne.addWidget(self.recherche, 1)
        self.favoris_seulement = QCheckBox("Favoris seulement")
        self.favoris_seulement.toggled.connect(self._filtrer)
        ligne.addWidget(self.favoris_seulement)
        self.bouton_actualiser_google = bouton(
            "Actualiser", variante="contour", nom_icone="refresh-cw", action=lambda: self._charger_bibliotheque(True)
        )
        ligne.addWidget(self.bouton_actualiser_google)
        disposition.addLayout(ligne)

        # Six filtres sur deux lignes de trois : sur une seule ligne, chaque liste serait trop
        # étroite pour lire son choix (« Toutes les hauteurs » deviendrait « Toute… »).
        filtres = QGridLayout()
        filtres.setHorizontalSpacing(Espacements.S)
        filtres.setVerticalSpacing(Espacements.S)
        self.filtre_langue = liste_deroulante("Langue")
        self.filtre_genre = liste_deroulante("Genre")
        self.filtre_hauteur = liste_deroulante("Hauteur de la voix")
        self.filtre_accent = liste_deroulante("Accent")
        self.filtre_persona = liste_deroulante("Persona")
        self.filtre_contexte = liste_deroulante("Contexte d'usage")
        # Langue choisie à la main : elle n'est plus remplacée par celle du projet.
        self.filtre_langue.activated.connect(lambda _index: setattr(self, "_langue_en_attente", False))
        for rang, liste in enumerate(
            (
                self.filtre_langue,
                self.filtre_genre,
                self.filtre_hauteur,
                self.filtre_accent,
                self.filtre_persona,
                self.filtre_contexte,
            )
        ):
            liste.currentIndexChanged.connect(self._filtrer)
            filtres.addWidget(liste, rang // FILTRES_PAR_LIGNE, rang % FILTRES_PAR_LIGNE)
        for colonne in range(FILTRES_PAR_LIGNE):
            filtres.setColumnStretch(colonne, 1)
        disposition.addLayout(filtres)

        self.info_liste = libelle("", "legende")
        disposition.addWidget(self.info_liste)
        zone, contenu = zone_defilante(largeur_max=None)
        self._liste_widget, self._liste = conteneur_vertical(0)
        contenu.addWidget(self._liste_widget)
        self.bouton_plus = bouton("", variante="contour", nom_icone="chevron-down", action=self.afficher_plus)
        self.bouton_plus.hide()
        contenu.addWidget(self.bouton_plus, 0, Qt.AlignmentFlag.AlignLeft)
        disposition.addWidget(zone, 1)
        return onglet

    def _onglet_mes_voix(self) -> QWidget:
        onglet = QWidget()
        disposition = QVBoxLayout(onglet)
        disposition.setContentsMargins(0, Espacements.M, 0, 0)
        disposition.setSpacing(Espacements.S)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        textes = QVBoxLayout()
        textes.setSpacing(0)
        self.compteur = libelle("", "intitule", retour_a_la_ligne=False)
        # D'où viennent ces voix : au survol de l'icône « i » devant le compteur (V3.1 ; après lui jusqu'à la 3.1.0).
        textes.addLayout(
            ligne_avec_aide(
                self.compteur, BoutonInfo("Voix créées avec Voice Design, ici ou dans Google AI Studio (même projet Google).")
            )
        )
        ligne.addLayout(textes, 1)
        self.bouton_actualiser_creees = bouton(
            "Actualiser", variante="contour", nom_icone="refresh-cw", action=lambda: self._charger_voix_creees(True)
        )
        ligne.addWidget(self.bouton_actualiser_creees)
        ligne.addWidget(bouton("Créer une voix", variante="principal", nom_icone="plus", action=self.creer_voix))
        disposition.addLayout(ligne)
        zone, contenu = zone_defilante(largeur_max=None)
        self._liste_creees_widget, self._liste_creees = conteneur_vertical(0)
        contenu.addWidget(self._liste_creees_widget)
        disposition.addWidget(zone, 1)
        return onglet

    # --- Chargement --------------------------------------------------------------------------

    def _afficher(self, message: str, role: str = "secondaire") -> None:
        # Vert ou rouge : effacé après 8 s (V3.2) ; la ligne garde sa place à côté des boutons.
        afficher_message(self.statut, message, role, cacher_vide=False)

    def _charger_bibliotheque(self, forcer: bool) -> None:
        if not forcer and self.services.voix.bibliotheque_a_jour():
            self._remplir_filtres()
            return
        try:
            adaptateur = adaptateur_par_defaut(self.services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            self._remplir_filtres()
            return
        self._afficher("Chargement de la bibliothèque de Google…")
        # Le cercle tourne dans « Actualiser » pendant le chargement (V3.1) : il ne se reclique pas.
        montrer_occupe(self.bouton_actualiser_google, True)

        def fin(voix: list[VoixBibliotheque]) -> None:
            montrer_occupe(self.bouton_actualiser_google, False)
            self._afficher(f"Bibliothèque à jour : {len(voix)} voix.")
            self.services.voix.definir_bibliotheque(voix)  # met aussi la liste à jour (voir _voix_changees)

        def echec(erreur: Exception) -> None:
            montrer_occupe(self.bouton_actualiser_google, False)
            self._afficher(f"Bibliothèque non chargée : {message_erreur(erreur)}", "erreur")
            self._remplir_filtres()

        taches.lancer(lambda: adaptateur.lister_voix(("prebuilt",)), fin, echec)

    def _charger_voix_creees(self, forcer: bool) -> None:
        if not forcer and self.services.voix.voix_creees_a_jour():
            self._remplir_voix_creees()
            return
        try:
            adaptateur = adaptateur_par_defaut(self.services)
        except Exception:  # noqa: BLE001 — sans clé, on montre ce qui est déjà connu
            self._remplir_voix_creees()
            return

        montrer_occupe(self.bouton_actualiser_creees, True)

        def fin(voix: list[VoixBibliotheque]) -> None:
            montrer_occupe(self.bouton_actualiser_creees, False)
            self.services.voix.definir_voix_creees(voix)

        def echec(erreur: Exception) -> None:
            montrer_occupe(self.bouton_actualiser_creees, False)
            self._afficher(f"Liste de tes voix non mise à jour : {message_erreur(erreur)}", "erreur")
            self._remplir_voix_creees()

        taches.lancer(lambda: adaptateur.lister_voix(("prompted", "replicated")), fin, echec)

    # --- Voix Google : filtres et liste ---------------------------------------------------------

    def _toutes(self) -> list[VoixBibliotheque]:
        return self.services.voix.bibliotheque() or voix_de_base_en_bibliotheque()

    def _remplir_filtres(self) -> None:
        voix = self._toutes()
        valeurs = {
            self.filtre_langue: ("Toutes les langues", sorted({v.langue for v in voix if v.langue}), nom_langue),
            self.filtre_genre: ("Tous les genres", sorted({v.genre for v in voix if v.genre}), lambda g: GENRES.get(g, g)),
            self.filtre_hauteur: (
                "Toutes les hauteurs",
                [h for h in HAUTEURS if any(v.hauteur == h for v in voix)],
                lambda h: f"voix {HAUTEURS[h]}",
            ),
            self.filtre_accent: ("Tous les accents", sorted({v.accent for v in voix if v.accent}), str),
            self.filtre_persona: ("Toutes les personas", sorted({v.persona for v in voix if v.persona}), str),
            self.filtre_contexte: ("Tous les contextes", sorted({v.contexte for v in voix if v.contexte}), str),
        }
        for liste, (tous, choix, texte) in valeurs.items():
            actuel = liste.currentData()
            if liste is self.filtre_langue and self._langue_en_attente:
                actuel = self._langue  # au départ : la langue du projet
            liste.blockSignals(True)
            liste.clear()
            liste.addItem(tous, TOUS)
            for valeur in choix:
                liste.addItem(texte(valeur), valeur)
            index = liste.findData(actuel) if actuel else -1
            if liste is self.filtre_langue and index >= 0:
                self._langue_en_attente = False
            liste.setCurrentIndex(max(0, index))
            liste.blockSignals(False)
        self._filtrer()

    def voix_filtrees(self) -> list[VoixBibliotheque]:
        recherche = self.recherche.text().strip().lower()
        filtres = (
            (self.filtre_langue, "langue"),
            (self.filtre_genre, "genre"),
            (self.filtre_hauteur, "hauteur"),
            (self.filtre_accent, "accent"),
            (self.filtre_persona, "persona"),
            (self.filtre_contexte, "contexte"),
        )
        resultat = []
        for voix in self._toutes():
            if any(liste.currentData() and getattr(voix, champ) != liste.currentData() for liste, champ in filtres):
                continue
            if self.favoris_seulement.isChecked() and not self.services.voix.est_favori(voix.identifiant):
                continue
            if recherche and recherche not in f"{voix.nom} {voix.description}".lower():
                continue
            resultat.append(voix)
        # Favoris d'abord, puis par nom.
        return sorted(resultat, key=lambda v: (not self.services.voix.est_favori(v.identifiant), v.nom.lower()))

    def _filtrer(self, *_args) -> None:
        """Nouveaux filtres : le nombre exact de voix trouvées, puis les 20 premières."""
        self._minuteur_recherche.stop()  # recherche en attente : elle est faite maintenant
        self._filtrees = self.voix_filtrees()
        vider_disposition(self._liste)
        self._lignes = []
        self.afficher_plus()
        trouvees, total = len(self._filtrees), len(self._toutes())
        if not trouvees:
            self.info_liste.setText(f"Aucune voix ne correspond à ces filtres (sur {nombre_lisible(total)}).")
        elif trouvees == total:
            self.info_liste.setText(f"{nombre_lisible(total)} voix.")
        else:
            self.info_liste.setText(f"{nombre_lisible(trouvees)} voix (sur {nombre_lisible(total)}).")

    def afficher_plus(self) -> None:
        """Ajoute les 20 voix suivantes sous celles déjà affichées (sans reconstruire ces dernières)."""
        debut = len(self._lignes)
        for voix in self._filtrees[debut : debut + LIGNES_PAR_PAGE]:
            ligne = LigneVoix(self, voix)
            self._lignes.append(ligne)
            self._liste.addWidget(ligne)
        restantes = len(self._filtrees) - len(self._lignes)
        if restantes > LIGNES_PAR_PAGE:
            texte = f"Afficher {LIGNES_PAR_PAGE} voix de plus ({nombre_lisible(restantes)} restantes)"
        elif restantes > 1:
            texte = f"Afficher les {restantes} dernières voix"
        else:
            texte = "Afficher la dernière voix"
        self.bouton_plus.setText(texte)
        self.bouton_plus.setVisible(restantes > 0)

    def lignes(self) -> list[LigneVoix]:
        return list(self._lignes)

    # --- Mes voix -----------------------------------------------------------------------------

    def _remplir_voix_creees(self) -> None:
        vider_disposition(self._liste_creees)
        self._lignes_creees = []
        creees = self.services.voix.voix_creees()
        self.compteur.setText(f"{len(creees)} / {MAX_VOIX_CREEES} voix créées")
        if not creees:
            self._liste_creees.addWidget(
                libelle("Aucune voix créée pour l'instant : « Créer une voix » pour décrire la tienne.", "discret")
            )
        for voix in creees:
            ligne = LigneVoix(self, voix)
            self._lignes_creees.append(ligne)
            self._liste_creees.addWidget(ligne)

    def lignes_creees(self) -> list[LigneVoix]:
        return list(self._lignes_creees)

    # --- Actions -----------------------------------------------------------------------------

    def basculer_favori(self, ligne: LigneVoix) -> None:
        """★ : seule l'étoile change (celle de la voix dans les deux onglets), rien n'est reconstruit."""
        favori = self.services.voix.basculer_favori(ligne.voix.identifiant)
        for autre in (*self._lignes, *self._lignes_creees):
            if autre.voix.identifiant == ligne.voix.identifiant:
                autre.afficher_favori(favori)

    def ecouter(self, voix: VoixBibliotheque, bouton_ecoute=None) -> None:
        """▶ d'une voix ; le cercle tourne dans ce ▶ pendant la préparation de l'extrait."""
        modele = voix.modele if voix.creee and voix.modele else self._modele
        self._ecoute.ecouter(voix.identifiant, modele, voix.langue or self._langue, bouton_ecoute)

    def choisir(self, voix: VoixBibliotheque) -> None:
        self.voix_choisie = voix
        self.accept()

    def creer_voix(self) -> None:
        from .voice_design import DialogueVoiceDesign

        dialogue = DialogueVoiceDesign(self.services, self._ecoute, self, langue=self._langue, modele=self._modele)
        if dialogue.exec() and dialogue.voix_creee is not None:
            self.choisir(dialogue.voix_creee)

    def renommer(self, voix: VoixBibliotheque) -> None:
        nom, ok = QInputDialog.getText(
            self, "Renommer la voix", "Nouveau nom (dans l'app) :", text=self.services.voix.nom(voix.identifiant)
        )
        if ok:
            self.services.voix.renommer(voix.identifiant, nom)

    def supprimer(self, voix: VoixBibliotheque, confirmer: bool = True) -> None:
        if confirmer:
            reponse = QMessageBox.question(
                self,
                "Supprimer la voix",
                f"Supprimer la voix « {self.services.voix.nom(voix.identifiant)} » chez Google ? "
                "Les prises déjà générées avec elle sont gardées.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reponse != QMessageBox.StandardButton.Yes:
                return
        try:
            adaptateur = adaptateur_par_defaut(self.services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        self._afficher("Suppression en cours…")

        def fin(_resultat) -> None:
            self._afficher("Voix supprimée.")
            self.services.voix.retirer_voix(voix.identifiant)

        def echec(erreur: Exception) -> None:
            self._afficher(f"Voix non supprimée : {message_erreur(erreur)}", "erreur")

        taches.lancer(lambda: adaptateur.supprimer_voix(voix.identifiant), fin, echec)
