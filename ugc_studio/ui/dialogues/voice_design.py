"""Voice Design (§5.4 bis) : créer une voix à partir d'une description, sans passer par Google AI Studio.

1. On décrit la voix (nom, langue, genre, modèle, description en anglais de 1 à 2 phrases ; assistant
   et traduction disponibles). Les conseils de Google sont derrière le bouton « Conseils ».
2. « Créer la voix » : Google crée la voix, la garde 1 an (200 voix au maximum par projet) et renvoie
   un extrait, joué aussitôt.
3. Chaque création donne une version un peu différente : on peut en créer d'autres avec la même
   description, les écouter, supprimer celles qui ne plaisent pas, puis « Utiliser cette voix ».
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout

from ...fournisseurs.capacites import MODELES_CONNUS, Capacite
from ...fournisseurs.voix import RequeteVoiceDesign, VoixBibliotheque
from ...projets import LANGUE_PAR_DEFAUT, LANGUES
from ...services import Services
from ...voix_locales import GENRES, MAX_VOIX_CREEES, date_lisible
from .. import taches
from ..composants.champ_style import ChampDescription
from ..composants.choix_voix import propose
from ..composants.conseils import entete_de_fenetre
from ..composants.elements import TOUTE_LA_RANGEE, bouton, champs_en_colonnes, conteneur_vertical, info, libelle, liste_deroulante
from ..connexion_ia import FOURNISSEUR, adaptateur_par_defaut, message_erreur
from ..extraits import EcouteVoix
from ..theme import Dimensions, Espacements


class LigneVersion(QFrame):
    """Une version créée pendant cette séance : ▶, supprimer, utiliser."""

    def __init__(self, dialogue: DialogueVoiceDesign, voix: VoixBibliotheque, numero: int):
        super().__init__()
        self.setProperty("role", "ligne")
        self.voix = voix
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.S, 0, Espacements.S)
        disposition.setSpacing(Espacements.S)
        expiration = date_lisible(voix.expire_le)
        textes = QVBoxLayout()
        textes.setSpacing(0)
        textes.addWidget(libelle(f"Version {numero} : {voix.nom}", "intitule", retour_a_la_ligne=False))
        textes.addWidget(libelle(f"Gardée par Google jusqu'au {expiration}" if expiration else voix.identifiant, "legende"))
        disposition.addLayout(textes, 1)
        ecouter = bouton("", variante="icone", nom_icone="play", action=lambda: dialogue.ecouter(voix))
        ecouter.setToolTip("Réécouter l'extrait")
        disposition.addWidget(ecouter, 0, Qt.AlignmentFlag.AlignVCenter)
        self.bouton_supprimer = bouton(
            "Supprimer", variante="contour", nom_icone="trash", action=lambda: dialogue.supprimer(self)
        )
        disposition.addWidget(self.bouton_supprimer, 0, Qt.AlignmentFlag.AlignVCenter)
        disposition.addWidget(
            bouton("Utiliser cette voix", variante="principal", action=lambda: dialogue.utiliser(voix)),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )


class DialogueVoiceDesign(QDialog):
    def __init__(
        self,
        services: Services,
        ecoute: EcouteVoix,
        parent=None,
        langue: str = LANGUE_PAR_DEFAUT,
        modele: str = "gemini-3.8-flash-tts",
    ):
        super().__init__(parent)
        self._services = services
        self._ecoute = ecoute
        self.voix_creee: VoixBibliotheque | None = None
        self._versions: list[LigneVersion] = []
        self.setWindowTitle("Créer une voix")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre("Créer une voix (Voice Design)", "creer-une-voix"))
        disposition.addWidget(
            info(
                "Décris la voix : Google en crée une nouvelle et te fait écouter un extrait. Chaque création donne "
                "une version un peu différente : crée-en plusieurs si besoin, puis garde ta préférée.",
                "secondaire",
            )
        )

        gauche = QVBoxLayout()
        gauche.setSpacing(Espacements.M)
        self.nom = QLineEdit()
        self.nom.setPlaceholderText("ex. Léa, créatrice UGC")
        self.langue = liste_deroulante()
        for code, nom in LANGUES.items():
            self.langue.addItem(nom, code)
        self.langue.setCurrentIndex(max(0, self.langue.findData(langue)))
        self.genre = liste_deroulante()
        for code, nom in GENRES.items():
            self.genre.addItem(nom, code)
        self.modele = liste_deroulante()
        for connu in MODELES_CONNUS:  # modèles chargés qui savent créer une voix
            if Capacite.TTS_VOICE_DESIGN in connu.capacites and propose(services, connu.identifiant, modele):
                self.modele.addItem(connu.nom, connu.identifiant)
        self.modele.setCurrentIndex(max(0, self.modele.findData(modele)))
        self.description = ChampDescription(services)
        self.description.assistant_utilise.connect(self._assistant_utilise)
        # Champs sous leur nom (V3.1), deux par rangée ; la description prend toute la rangée.
        gauche.addLayout(
            champs_en_colonnes(
                (
                    ("Nom", self.nom),
                    ("Langue", self.langue),
                    ("Genre", self.genre),
                    ("Modèle", self.modele),
                    ("Description", self.description, TOUTE_LA_RANGEE),
                )
            )
        )

        self.titre_versions = libelle("Versions créées", "intitule")
        self.titre_versions.hide()
        gauche.addWidget(self.titre_versions)
        self._versions_widget, self._liste_versions = conteneur_vertical(0)
        gauche.addWidget(self._versions_widget)
        gauche.addStretch(1)
        disposition.addLayout(gauche, 1)

        bas = QHBoxLayout()
        bas.setSpacing(Espacements.S)
        self.statut = libelle("", "secondaire")
        bas.addWidget(self.statut, 1)
        bas.addWidget(bouton("Fermer", action=self.reject))
        self.bouton_creer = bouton("Créer la voix", variante="principal", nom_icone="plus", action=self.creer)
        bas.addWidget(self.bouton_creer)
        disposition.addLayout(bas)

    # --- Actions -----------------------------------------------------------------------------

    def _afficher(self, message: str, role: str = "secondaire") -> None:
        self.statut.setText(message)
        self.statut.setProperty("role", role)
        self.statut.style().unpolish(self.statut)
        self.statut.style().polish(self.statut)

    def _assistant_utilise(self, dialogue) -> None:
        """L'assistant connaît le genre choisi : on le reporte dans le champ Genre."""
        index = self.genre.findData(dialogue.code_genre())
        if index >= 0:
            self.genre.setCurrentIndex(index)

    def versions(self) -> list[LigneVersion]:
        return list(self._versions)

    def creer(self) -> None:
        nom = " ".join(self.nom.text().split())
        description = self.description.consigne()
        if not nom:
            self._afficher("Donne un nom à la voix.", "erreur")
            return
        if not description:
            self._afficher("Écris la description de la voix (ou utilise l'assistant ✨).", "erreur")
            return
        if len(self._services.voix.voix_creees()) >= MAX_VOIX_CREEES:
            self._afficher(
                f"Tu as déjà {MAX_VOIX_CREEES} voix créées, le maximum chez Google : supprimes-en une d'abord.",
                "erreur",
            )
            return
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        requete = RequeteVoiceDesign(
            self.modele.currentData(),
            nom,
            description,
            self.langue.currentData() or "",
            self.genre.currentData() or "",
        )
        description_fr = self.description.consigne_fr()
        self.bouton_creer.setEnabled(False)
        self._afficher("Création de la voix chez Google… (quelques secondes)")

        def fin(resultat) -> None:
            self.bouton_creer.setEnabled(True)
            self.bouton_creer.setText("Créer une autre version")
            voix = resultat.voix
            projet = self._services.projets.projet
            self._services.couts.enregistrer(
                FOURNISSEUR,
                requete.modele,
                "création de voix",
                resultat.tokens_entree,
                resultat.tokens_sortie,
                projet=projet.nom if projet is not None else None,
            )
            self._services.voix.ajouter_voix_creee(voix)
            self._services.voix.definir_description_fr(voix.identifiant, description_fr)
            ligne = LigneVersion(self, voix, len(self._versions) + 1)
            self._versions.append(ligne)
            self._liste_versions.addWidget(ligne)
            self.titre_versions.show()
            self._afficher(f"Voix « {voix.nom} » créée : écoute l'extrait.", "succes")
            if voix.extrait_wav:
                self._ecoute.garder_et_jouer(voix.identifiant, voix.extrait_wav)

        def echec(erreur: Exception) -> None:
            self.bouton_creer.setEnabled(True)
            self._afficher(f"Voix non créée : {message_erreur(erreur)}", "erreur")

        taches.lancer(lambda: adaptateur.creer_voix(requete), fin, echec)

    def ecouter(self, voix: VoixBibliotheque) -> None:
        self._ecoute.ecouter(voix.identifiant, voix.modele or self.modele.currentData(), voix.langue or "fr-FR")

    def utiliser(self, voix: VoixBibliotheque) -> None:
        self.voix_creee = voix
        self.accept()

    def supprimer(self, ligne: LigneVersion) -> None:
        """Supprime cette version chez Google (elle ne compte plus dans les 200)."""
        try:
            adaptateur = adaptateur_par_defaut(self._services)
        except Exception as erreur:  # noqa: BLE001 — message clair affiché
            self._afficher(message_erreur(erreur), "erreur")
            return
        ligne.bouton_supprimer.setEnabled(False)
        identifiant = ligne.voix.identifiant

        def fin(_resultat) -> None:
            self._services.voix.retirer_voix(identifiant)
            if ligne in self._versions:
                self._versions.remove(ligne)
            ligne.hide()
            ligne.deleteLater()
            self._afficher("Version supprimée.")

        def echec(erreur: Exception) -> None:
            ligne.bouton_supprimer.setEnabled(True)
            self._afficher(f"Version non supprimée : {message_erreur(erreur)}", "erreur")

        taches.lancer(lambda: adaptateur.supprimer_voix(identifiant), fin, echec)
