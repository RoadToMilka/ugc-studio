"""Module Upscale vidéo (V4, lot 3 ; cahier des charges §8 bis.3) : des vidéos agrandies et améliorées
par un modèle de Topaz Video AI (Proteus), avec le moteur de Topaz installé sur l'ordinateur et
exactement les réglages de l'utilisateur (préréglage tiré d'une commande de Topaz). Le calcul et le
lancement sont dans topaz/.

Le parcours, de haut en bas :
1. Topaz : trouvé tout seul (sinon « Dossiers de Topaz… »), et ce qui manquerait pour lancer.
2. Préréglage : la commande d'un export de Topaz, collée une fois (« Nouveau… »), et ce qu'elle fait.
3. Taille : la résolution visée sur le petit côté (1080p, 1440p…) ; l'autre côté suit le ratio de
   chaque vidéo, sans jamais l'étirer.
4. Vidéos : glisser-déposer ou « Ajouter des vidéos… » ; chaque vidéo, sa taille actuelle et finale.
5. Enregistrement : à côté de chaque vidéo (« Sérum (upscale).mp4 »), ou dans un autre dossier.
6. « Lancer » : une vidéo après l'autre, avancement, « Arrêter » ; puis « Ouvrir le dossier », et
   « Comparer à un export de Topaz… » pour vérifier que le résultat est le même.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from ....chemins import chemin_a_afficher, dossier_documents, dossier_donnees
from ....exports.ffmpeg import preparer_ffmpeg
from ....services import Services
from ....topaz.commande import PETIT_COTE_1080P, PETIT_COTE_1440P, PETIT_COTE_MAX, PETIT_COTE_MIN, Prereglage
from ....topaz.comparaison import ComparaisonImpossible, comparer
from ....topaz.installation import DOSSIER_PAR_DEFAUT, Topaz, trouver_topaz
from ....topaz.prereglages import FICHIER as FICHIER_PREREGLAGES
from ....topaz.prereglages import PrereglagesTopaz
from ....topaz.upscale import (
    EXTENSIONS_VIDEOS,
    Avancement,
    Resultat,
    Travail,
    Video,
    duree_lisible,
    lire_la_video,
    planifier,
    upscaler,
)
from ... import taches
from ...composants.barre_avancement import BarreAvancement
from ...composants.bouton import BoutonOccupe
from ...composants.depot_dossier import ZoneDepotDossier, fichiers_deposes
from ...composants.elements import (
    ChampNomme,
    afficher_message,
    bloc,
    bouton,
    champ_entier,
    libelle,
    liste_deroulante,
)
from ...composants.tableau import Colonne, Tableau
from ...dialogues import messages
from ...ouvrir import ouvrir_dossier
from ...theme import Couleurs, Dimensions, Espacements, Hauteurs, qcolor
from ..base import Page
from .dossiers_topaz import DialogueDossiersTopaz
from .prereglage import DialoguePrereglage

TITRE = "Upscale vidéo"
SOUS_TITRE = "Tes vidéos agrandies par Topaz Video AI, avec tes propres réglages."

# Préférences (§10) : ce module ne dépend pas d'un projet.
PREF_PREREGLAGE = "upscale_prereglage"
PREF_PETIT_COTE = "upscale_petit_cote"
PREF_PETIT_COTE_LIBRE = "upscale_petit_cote_libre"
PREF_SORTIE = "upscale_sortie"
PREF_SORTIE_AUTRE = "upscale_sortie_autre"
PREF_DOSSIERS_TOPAZ = "upscale_dossiers_topaz"  # {"installation": …, "modeles": …, "telecharges": …}
PREF_DERNIER_DOSSIER = "upscale_dernier_dossier"

AUTRE = 0
RESOLUTIONS = {
    PETIT_COTE_1080P: "1080p (petit côté 1080 px)",
    PETIT_COTE_1440P: "1440p (petit côté 1440 px)",
    2160: "4K (petit côté 2160 px)",
    AUTRE: "Autre…",
}
A_COTE, AUTRE_DOSSIER = "a_cote", "autre"
FORMATS_ACCEPTES = "MP4, MOV, MKV, AVI, WebM…"

AIDE_TOPAZ = (
    "L'app lance le moteur de Topaz installé sur ton ordinateur (sa ligne de commande, permise avec ta licence "
    "à vie de Topaz Video AI), avec la connexion de l'app Topaz : il faut s'y être connecté une fois. C'est ta "
    "carte graphique qui travaille, comme dans Topaz : évite d'exporter dans Topaz en même temps."
)
AIDE_PREREGLAGE = (
    "Un préréglage, c'est la commande d'un de tes exports de Topaz (« Nouveau… ») : modèle, réglages de "
    "Proteus, encodage, débit, son et cadence repris tels quels. Seuls la vidéo, le fichier écrit et la "
    "taille changent pour chaque vidéo."
)
AIDE_TAILLE = (
    "La résolution visée porte sur le petit côté, comme « 1080p » : 1080 de large pour une vidéo verticale, "
    "1080 de haut pour une vidéo horizontale. L'autre côté garde exactement le ratio de chaque vidéo (jamais "
    "d'étirement), arrondi au nombre pair le plus proche : 606 × 1080 donne 1080 × 1924."
)
AIDE_VIDEOS = (
    "Les vidéos sont lues avant de lancer (taille telle qu'on la voit, même enregistrée couchée, durée). Une "
    "vidéo après l'autre : c'est la carte graphique qui travaille. Tes vidéos d'origine ne sont jamais modifiées."
)
AIDE_SORTIE = (
    "Par défaut, à côté de chaque vidéo : « Sérum (upscale).mp4 ». Aucun fichier n'est écrasé : si ce nom est "
    "pris, « Sérum (upscale) (2).mp4 »."
)
AIDE_COMPARER = (
    "Choisis une vidéo faite ici, puis la même exportée par Topaz avec le même réglage : l'app mesure leur "
    "ressemblance image par image (au-dessus de 99 %, aucune différence visible)."
)

COLONNES = (
    Colonne("Vidéo", texte=True, etiree=True),
    Colonne("Taille actuelle", a_droite=True),
    Colonne("Taille finale", a_droite=True),
    Colonne("Durée", a_droite=True),
    Colonne("État", texte=True),
)
EN_ATTENTE = "en attente"


def _taille(largeur: int, hauteur: int) -> str:
    return f"{largeur} × {hauteur}"


class PageUpscale(Page):
    def __init__(self, services: Services):
        super().__init__(TITRE, SOUS_TITRE, conseils="upscale")
        self._preferences = services.preferences
        self._topaz: Topaz | None = None
        self._prereglage: Prereglage | None = None  # le préréglage choisi (relu à chaque changement de liste)
        self._videos: list[Video] = []
        self._etats: dict[Path, tuple[str, str]] = {}  # source : (état, rôle de couleur : "", "succes", "erreur"…)
        self._faites: set[Path] = set()  # agrandies pendant cette session : pas relancées
        self._travaux: list[Travail] = []
        self._en_cours: list[Travail] = []
        self._arret: threading.Event | None = None
        self._occupe = False
        self._bouton_occupe = BoutonOccupe()
        self._derniere_sortie: Path | None = None
        autre = self._preferences.lire(PREF_SORTIE_AUTRE)
        self._autre_dossier: Path | None = Path(autre) if isinstance(autre, str) and autre else None
        self.setAcceptDrops(True)

        # --- Topaz ---
        self.cadre_topaz, d = bloc("Topaz", aide=AIDE_TOPAZ)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.M)
        textes = QVBoxLayout()
        textes.setContentsMargins(0, 0, 0, 0)
        textes.setSpacing(Espacements.XS)
        self.etat_topaz = libelle("", "secondaire")
        textes.addWidget(self.etat_topaz)
        self.problemes_topaz = libelle("", "avertissement")
        textes.addWidget(self.problemes_topaz)
        ligne.addLayout(textes, 1)
        self.bouton_dossiers = bouton("Dossiers de Topaz…", variante="contour", nom_icone="folder-open", action=self.choisir_les_dossiers)
        ligne.addWidget(self.bouton_dossiers, 0, Qt.AlignmentFlag.AlignTop)
        d.addLayout(ligne)
        self.contenu.addWidget(self.cadre_topaz)

        # --- Préréglage ---
        self.cadre_prereglage, d = bloc("Préréglage", aide=AIDE_PREREGLAGE)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.S)
        self.prereglage = liste_deroulante()
        ligne.addWidget(self.prereglage, 1)
        self.bouton_nouveau = bouton("Nouveau…", variante="contour", nom_icone="plus", action=self.nouveau_prereglage)
        ligne.addWidget(self.bouton_nouveau)
        self.bouton_supprimer = bouton("Supprimer", variante="contour", nom_icone="trash", action=self.supprimer_prereglage)
        ligne.addWidget(self.bouton_supprimer)
        d.addLayout(ligne)
        self.resume_prereglage = libelle("", "legende")
        d.addWidget(self.resume_prereglage)
        self.contenu.addWidget(self.cadre_prereglage)

        # --- Taille ---
        self.cadre_taille, d = bloc("Taille", aide=AIDE_TAILLE)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.L)
        self.resolution = liste_deroulante()
        for valeur, nom in RESOLUTIONS.items():
            self.resolution.addItem(nom, valeur)
        self._choisir(self.resolution, self._preferences.lire(PREF_PETIT_COTE, PETIT_COTE_1080P))
        ligne.addWidget(ChampNomme("Résolution visée", self.resolution))
        self.petit_cote = champ_entier(PETIT_COTE_MIN, PETIT_COTE_MAX, " px")
        libre = self._preferences.lire(PREF_PETIT_COTE_LIBRE, PETIT_COTE_1080P)
        self.petit_cote.setValue(libre if isinstance(libre, int) else PETIT_COTE_1080P)
        self.champ_petit_cote = ChampNomme("Petit côté", self.petit_cote)
        ligne.addWidget(self.champ_petit_cote)
        ligne.addStretch(1)
        d.addLayout(ligne)
        self.contenu.addWidget(self.cadre_taille)

        # --- Vidéos ---
        self.cadre_videos, d = bloc("Vidéos", aide=AIDE_VIDEOS)
        self.zone_depot = ZoneDepotDossier("Glisse des vidéos ici", FORMATS_ACCEPTES, self.ajouter_des_videos, "Ajouter des vidéos…")
        d.addWidget(self.zone_depot)
        self.ligne_videos = QWidget()
        ligne = QHBoxLayout(self.ligne_videos)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.S)
        self.compte = libelle("", "legende")
        ligne.addWidget(self.compte, 1)
        self.bouton_ajouter = bouton("Ajouter des vidéos…", variante="contour", nom_icone="plus", action=self.ajouter_des_videos)
        ligne.addWidget(self.bouton_ajouter)
        self.bouton_retirer = bouton("Retirer", variante="contour", nom_icone="trash", action=self.retirer_la_video)
        ligne.addWidget(self.bouton_retirer)
        self.bouton_vider = bouton("Vider la liste", variante="contour", nom_icone="eraser", action=self.vider_la_liste)
        ligne.addWidget(self.bouton_vider)
        self.ligne_videos.hide()
        d.addWidget(self.ligne_videos)
        self.tableau = Tableau(COLONNES)
        self.tableau.itemSelectionChanged.connect(self._mettre_a_jour_les_boutons)
        d.addWidget(self.tableau)
        self.contenu.addWidget(self.cadre_videos)

        # --- Enregistrement ---
        self.cadre_sortie, d = bloc("Enregistrement", aide=AIDE_SORTIE)
        self.sortie = liste_deroulante()
        self.sortie.addItem("À côté de chaque vidéo", A_COTE)
        self.sortie.addItem("Autre dossier…", AUTRE_DOSSIER)
        self._choisir(self.sortie, self._preferences.lire(PREF_SORTIE, A_COTE))
        d.addWidget(ChampNomme("Enregistrer", self.sortie))
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

        # --- Lancer ---
        action = QVBoxLayout()
        action.setSpacing(Espacements.S)
        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_lancer = bouton("Lancer", variante="principal", nom_icone="play", action=self.lancer)
        boutons.addWidget(self.bouton_lancer)
        self.bouton_arreter = bouton("Arrêter", nom_icone="square", action=self.arreter)
        self.bouton_arreter.hide()
        boutons.addWidget(self.bouton_arreter)
        self.bouton_ouvrir = bouton("Ouvrir le dossier", variante="contour", nom_icone="folder-open", action=self.ouvrir_le_dossier)
        self.bouton_ouvrir.hide()
        boutons.addWidget(self.bouton_ouvrir)
        boutons.addStretch(1)
        self.bouton_comparer = bouton("Comparer à un export de Topaz…", variante="contour", nom_icone="git-compare-arrows", action=self.comparer)
        self.bouton_comparer.setToolTip(AIDE_COMPARER)
        boutons.addWidget(self.bouton_comparer)
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

        self.prereglage.currentIndexChanged.connect(lambda _index: self._prereglage_change())
        self.resolution.currentIndexChanged.connect(lambda _index: self._taille_changee())
        self.petit_cote.valueChanged.connect(lambda _valeur: self._taille_changee())
        self.sortie.currentIndexChanged.connect(lambda _index: self._sortie_changee())
        self._remplir_les_prereglages(self._preferences.lire(PREF_PREREGLAGE))
        self.chercher_topaz()
        self._actualiser()

    @staticmethod
    def _choisir(liste, valeur) -> None:
        index = liste.findData(valeur)
        liste.setCurrentIndex(index if index >= 0 else 0)

    @property
    def occupe(self) -> bool:
        return self._occupe

    # --- Topaz -------------------------------------------------------------------------------

    def _dossiers_choisis(self) -> dict[str, Path | None]:
        enregistres = self._preferences.lire(PREF_DOSSIERS_TOPAZ, {})
        enregistres = enregistres if isinstance(enregistres, dict) else {}
        return {cle: (Path(enregistres[cle]) if isinstance(enregistres.get(cle), str) and enregistres[cle] else None) for cle in ("installation", "modeles", "telecharges")}

    def chercher_topaz(self) -> None:
        """Topaz, d'après les dossiers choisis (ou trouvés seuls), puis son état."""
        choisis = self._dossiers_choisis()
        prereglage = self.prereglage_choisi()
        self._topaz = trouver_topaz(choisis["installation"], choisis["modeles"], choisis["telecharges"], prereglage.modele if prereglage else "prob-4")
        self._actualiser_topaz()

    def definir_topaz(self, topaz: Topaz | None) -> None:
        """Pour les tests et l'autotest : un faux Topaz à la place du vrai."""
        self._topaz = topaz
        self._actualiser_topaz()
        self._mettre_a_jour_les_boutons()

    def _actualiser_topaz(self) -> None:
        topaz = self._topaz
        if topaz is None:
            dossier = self._dossiers_choisis()["installation"] or DOSSIER_PAR_DEFAUT
            self.etat_topaz.setText(f"Topaz Video AI introuvable dans « {chemin_a_afficher(dossier)} ».")
            self.etat_topaz.setProperty("role", "erreur")
            self.problemes_topaz.setText("Installe-le, ou choisis son dossier (« Dossiers de Topaz… »).")
            self.problemes_topaz.show()
        else:
            prereglage = self.prereglage_choisi()
            problemes = topaz.problemes(prereglage.modele if prereglage else "")
            self.etat_topaz.setText(f"{topaz.nom()} : {'à vérifier' if problemes else 'prêt'}")
            self.etat_topaz.setProperty("role", "avertissement" if problemes else "succes")
            self.etat_topaz.setToolTip(f"Dossier : {topaz.dossier}")
            self.problemes_topaz.setText("\n".join(problemes))
            self.problemes_topaz.setVisible(bool(problemes))
        self.etat_topaz.style().unpolish(self.etat_topaz)
        self.etat_topaz.style().polish(self.etat_topaz)

    def choisir_les_dossiers(self) -> None:
        if self._occupe:
            return
        topaz = self._topaz
        automatiques = {
            "installation": topaz.dossier if topaz else DOSSIER_PAR_DEFAUT,
            "modeles": topaz.modeles if topaz else None,
            "telecharges": topaz.donnees if topaz else None,
        }
        dialogue = DialogueDossiersTopaz(self._dossiers_choisis(), automatiques, self)
        if dialogue.exec():
            self.definir_les_dossiers(dialogue.choisis)

    def definir_les_dossiers(self, choisis: dict[str, Path | None]) -> None:
        self._preferences.ecrire(PREF_DOSSIERS_TOPAZ, {cle: str(dossier) if dossier else "" for cle, dossier in choisis.items()})
        self.chercher_topaz()
        self._mettre_a_jour_les_boutons()

    # --- Préréglages -------------------------------------------------------------------------

    def _prereglages(self) -> PrereglagesTopaz:
        return PrereglagesTopaz(dossier_donnees() / FICHIER_PREREGLAGES)

    def _remplir_les_prereglages(self, choisi: str | None) -> None:
        self.prereglage.blockSignals(True)
        self.prereglage.clear()
        for nom in self._prereglages().noms():
            self.prereglage.addItem(nom, nom)
        index = self.prereglage.findData(choisi) if choisi else -1
        self.prereglage.setCurrentIndex(index if index >= 0 else 0)
        self.prereglage.blockSignals(False)
        self._prereglage_change()

    def prereglage_choisi(self) -> Prereglage | None:
        return self._prereglage

    def _prereglage_change(self) -> None:
        nom = self.prereglage.currentData()
        self._prereglage = prereglage = self._prereglages().trouver(nom) if nom else None
        if prereglage is not None:
            self._preferences.ecrire(PREF_PREREGLAGE, prereglage.nom)
            self.resume_prereglage.setText("\n".join(prereglage.resume()))
        else:
            self.resume_prereglage.setText("Aucun préréglage : « Nouveau… », puis colle la commande d'un export de Topaz")
        self.prereglage.setVisible(prereglage is not None)
        self.bouton_supprimer.setVisible(prereglage is not None)
        self._actualiser_topaz()
        self._actualiser()

    def nouveau_prereglage(self) -> None:
        if self._occupe:
            return
        dialogue = DialoguePrereglage(self, self._prereglages().noms())
        if dialogue.exec() and dialogue.prereglage is not None:
            self.ajouter_le_prereglage(dialogue.prereglage)

    def ajouter_le_prereglage(self, prereglage: Prereglage) -> None:
        self._prereglages().enregistrer(prereglage)
        self._remplir_les_prereglages(prereglage.nom)
        self._afficher(f"Préréglage « {prereglage.nom} » créé.", "succes")

    def supprimer_prereglage(self) -> None:
        prereglage = self.prereglage_choisi()
        if prereglage is None or self._occupe:
            return
        if not messages.confirmer(
            self,
            "Supprimer le préréglage",
            f"Supprimer le préréglage « {prereglage.nom} » ?",
            "Tes vidéos et Topaz ne changent pas : seul ce préréglage disparaît de l'app.",
            action="Supprimer",
            icone_action="trash",
        ):
            return
        self._prereglages().supprimer(prereglage.nom)
        self._remplir_les_prereglages(None)

    # --- Taille et enregistrement ------------------------------------------------------------

    def petit_cote_vise(self) -> int:
        valeur = self.resolution.currentData()
        return self.petit_cote.value() if valeur == AUTRE else int(valeur)

    def _taille_changee(self) -> None:
        self._preferences.ecrire(PREF_PETIT_COTE, self.resolution.currentData())
        self._preferences.ecrire(PREF_PETIT_COTE_LIBRE, self.petit_cote.value())
        self._actualiser()

    def dossier_de_sortie(self) -> Path | None:
        """L'autre dossier choisi ; None : à côté de chaque vidéo."""
        return self._autre_dossier if self.sortie.currentData() == AUTRE_DOSSIER else None

    def _sortie_changee(self) -> None:
        if self.sortie.currentData() == AUTRE_DOSSIER and self._autre_dossier is None:
            self.choisir_autre_dossier()
            if self._autre_dossier is None:  # pas de dossier choisi : on reste à côté des vidéos
                self._choisir(self.sortie, A_COTE)
                return
        self._preferences.ecrire(PREF_SORTIE, self.sortie.currentData())
        self._actualiser()

    def choisir_autre_dossier(self) -> None:
        depart = self._autre_dossier or dossier_documents()
        choix = QFileDialog.getExistingDirectory(self, "Dossier où enregistrer les vidéos", str(depart))
        if choix:
            self.definir_autre_dossier(Path(choix))

    def definir_autre_dossier(self, dossier: Path) -> None:
        self._autre_dossier = dossier
        self._preferences.ecrire(PREF_SORTIE_AUTRE, str(dossier))
        self._actualiser()

    # --- Vidéos ------------------------------------------------------------------------------

    def ajouter_des_videos(self) -> None:
        if self._occupe:
            return
        depart = self._preferences.lire(PREF_DERNIER_DOSSIER) or str(dossier_documents())
        filtre = "Vidéos (" + " ".join(f"*{extension}" for extension in EXTENSIONS_VIDEOS) + ")"
        choix, _filtre = QFileDialog.getOpenFileNames(self, "Ajouter des vidéos", depart, filtre)
        if choix:
            self.ajouter([Path(chemin) for chemin in choix])

    def ajouter(self, chemins: list[Path]) -> None:
        """Ajoute ces vidéos à la file (pas deux fois la même), après les avoir lues en arrière-plan."""
        nouvelles = [chemin for chemin in dict.fromkeys(chemins) if chemin not in {v.source for v in self._videos}]
        if not nouvelles or self._occupe:
            return
        self._preferences.ecrire(PREF_DERNIER_DOSSIER, str(nouvelles[0].parent))
        self._afficher("", "secondaire")
        self.compte.setText("Lecture des vidéos…")
        self.zone_depot.hide()
        self.ligne_videos.show()
        self._occuper(True, self.bouton_ajouter)

        def lire() -> list[Video]:
            ffmpeg = preparer_ffmpeg()  # le FFmpeg de l'app, recopié du .exe à la première fois
            return [lire_la_video(chemin, ffmpeg) for chemin in nouvelles]

        taches.lancer(lire, self._videos_lues, self._lecture_echouee)

    def _videos_lues(self, videos: list[Video]) -> None:
        self._occuper(False)
        self._videos += videos
        for video in videos:
            self._etats[video.source] = (f"illisible : {video.erreur}", "erreur") if video.erreur else (EN_ATTENTE, "")
        self._actualiser()

    def _lecture_echouee(self, erreur: Exception) -> None:
        self._occuper(False)
        self._afficher(f"Impossible de lire les vidéos : {erreur}", "erreur")
        self._actualiser()

    def retirer_la_video(self) -> None:
        rang = self.tableau.currentRow()
        if self._occupe or not 0 <= rang < len(self._videos):
            return
        video = self._videos.pop(rang)
        self._etats.pop(video.source, None)
        self._faites.discard(video.source)
        self._actualiser()

    def vider_la_liste(self) -> None:
        if self._occupe:
            return
        self._videos, self._etats, self._faites = [], {}, set()
        self._actualiser()

    def dragEnterEvent(self, evenement) -> None:  # noqa: N802 : nom imposé par Qt
        donnees = evenement.mimeData()
        if not self._occupe and donnees.hasUrls() and fichiers_deposes(donnees, EXTENSIONS_VIDEOS):
            evenement.acceptProposedAction()
            self.zone_depot.survol(True)

    def dragLeaveEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        super().dragLeaveEvent(evenement)

    def dropEvent(self, evenement) -> None:  # noqa: N802
        self.zone_depot.survol(False)
        chemins = fichiers_deposes(evenement.mimeData(), EXTENSIONS_VIDEOS)
        if chemins:
            evenement.acceptProposedAction()
            self.ajouter(chemins)

    # --- Résumé ------------------------------------------------------------------------------

    def _actualiser(self) -> None:
        """Les travaux selon les réglages (les vidéos déjà agrandies mises à part), puis le tableau."""
        self.champ_petit_cote.setVisible(self.resolution.currentData() == AUTRE)
        autre = self.sortie.currentData() == AUTRE_DOSSIER
        self.ligne_autre.setVisible(autre)
        self.chemin_autre.setText(chemin_a_afficher(self._autre_dossier) if self._autre_dossier else "Aucun dossier choisi")
        prereglage = self.prereglage_choisi()
        extension = prereglage.extension if prereglage else ".mp4"
        a_faire = [video for video in self._videos if video.source not in self._faites]
        self._travaux = planifier(a_faire, self.petit_cote_vise(), extension, self.dossier_de_sortie())
        avec_videos = bool(self._videos)
        self.zone_depot.setVisible(not avec_videos and not self._occupe)
        self.ligne_videos.setVisible(avec_videos or self._occupe)
        if avec_videos:
            duree = sum(video.duree_s for video in self._videos if not video.erreur)
            self.compte.setText(f"{len(self._videos)} vidéo{'s' if len(self._videos) > 1 else ''} · {duree_lisible(duree)} en tout")
        self._remplir_le_tableau()
        self._mettre_a_jour_les_boutons()

    def _remplir_le_tableau(self) -> None:
        finales = {travail.video.source: travail.finale for travail in self._travaux}
        self.tableau.setRowCount(len(self._videos))
        for rang, video in enumerate(self._videos):
            etat, role = self._etats.get(video.source, (EN_ATTENTE, ""))
            finale = finales.get(video.source)
            cases = (
                video.source.name,
                _taille(video.largeur, video.hauteur) if not video.erreur else "",
                _taille(*finale) if finale else "",
                duree_lisible(video.duree_s) if not video.erreur else "",
                etat,
            )
            for colonne, texte in enumerate(cases):
                case = QTableWidgetItem(texte)
                if COLONNES[colonne].a_droite:
                    case.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if colonne == 0:
                    case.setToolTip(str(video.source))
                if colonne == len(cases) - 1 and role:
                    case.setForeground(qcolor({"succes": Couleurs.SUCCES, "erreur": Couleurs.ERREUR, "avertissement": Couleurs.AVERTISSEMENT}.get(role, Couleurs.TEXTE)))
                    case.setToolTip(etat)
                self.tableau.setItem(rang, colonne, case)
        self.tableau.contenu_change()
        self.tableau.setVisible(bool(self._videos))
        hauteur = self.tableau.horizontalHeader().sizeHint().height() + len(self._videos) * Hauteurs.LIGNE_TABLEAU
        self.tableau.setFixedHeight(min(Dimensions.TABLEAU_HAUTEUR_MIN, hauteur))

    def _mettre_a_jour_les_boutons(self) -> None:
        pret = self._topaz is not None and self.prereglage_choisi() is not None and bool(self._travaux)
        actif = self._bouton_occupe.est
        self.bouton_lancer.setEnabled((pret and not self._occupe) or actif(self.bouton_lancer))
        self.bouton_retirer.setEnabled(not self._occupe and self.tableau.currentRow() >= 0)
        self.bouton_vider.setEnabled(not self._occupe and bool(self._videos))
        self.bouton_comparer.setEnabled(not self._occupe or actif(self.bouton_comparer))
        if self._topaz is None:
            self.bouton_lancer.setToolTip("Topaz Video AI introuvable : « Dossiers de Topaz… »")
        elif self.prereglage_choisi() is None:
            self.bouton_lancer.setToolTip("Crée d'abord un préréglage (« Nouveau… »)")
        else:
            self.bouton_lancer.setToolTip("")

    # --- Lancer ------------------------------------------------------------------------------

    def lancer(self) -> bool:
        """Lance la file (en arrière-plan). Renvoie True si elle commence."""
        prereglage, topaz, travaux = self.prereglage_choisi(), self._topaz, list(self._travaux)
        if self._occupe or prereglage is None or topaz is None or not travaux:
            return False
        problemes = topaz.problemes(prereglage.modele)
        if problemes and not messages.confirmer(
            self,
            "Lancer quand même",
            "Topaz n'a peut-être pas tout ce qu'il lui faut :",
            "\n".join(problemes) + "\nSi Topaz marche bien depuis son interface, tu peux essayer quand même.",
            action="Lancer quand même",
            icone_action="play",
        ):
            return False
        self._en_cours = travaux
        for travail in travaux:
            self._etats[travail.video.source] = (EN_ATTENTE, "")
        self._arret = threading.Event()
        arret = self._arret
        self._afficher("", "secondaire")
        self.bouton_ouvrir.hide()
        self.barre.definir(0)
        self.avancee.setText(f"Vidéo 1 sur {len(travaux)} : {travaux[0].video.source.name}")
        self.zone_avancement.show()
        self.bouton_arreter.setEnabled(True)
        self.bouton_arreter.show()
        self._occuper(True, self.bouton_lancer)
        self._remplir_le_tableau()
        taches.lancer_avec_progres(
            lambda progres: upscaler(travaux, prereglage, topaz, progres, arret),
            self._termine,
            self._echec,
            self._progres,
        )
        return True

    def _progres(self, avancement: Avancement) -> None:
        travail = self._en_cours[avancement.rang]
        pour_cent = round(avancement.fraction * 100)
        self.barre.definir((avancement.rang + avancement.fraction) / max(1, avancement.total))
        self.avancee.setText(
            f"Vidéo {avancement.rang + 1} sur {avancement.total} : {travail.video.source.name} · {pour_cent} % · "
            f"{duree_lisible(avancement.ecoule_s)}"
        )
        self._etats[travail.video.source] = (f"en cours ({pour_cent} %)", "")
        self._remplir_le_tableau()

    def arreter(self) -> None:
        """« Arrêter » : Topaz s'arrête tout de suite, la vidéo en cours est abandonnée (aussi à la
        fermeture de l'app)."""
        if self._arret is not None and self._occupe:
            self._arret.set()
            self.bouton_arreter.setEnabled(False)
            self.avancee.setText("Arrêt en cours…")

    def _fin(self) -> None:
        self._occuper(False)
        self.zone_avancement.hide()
        self.bouton_arreter.hide()

    def _termine(self, resultats: list[Resultat]) -> None:
        self._fin()
        reussis = [resultat for resultat in resultats if resultat.reussi]
        erreurs = [resultat for resultat in resultats if resultat.erreur]
        arrete = any(resultat.arrete for resultat in resultats)
        for resultat in resultats:
            source = resultat.travail.video.source
            if resultat.reussi:
                self._faites.add(source)
                self._etats[source] = (f"faite en {duree_lisible(resultat.duree_s)} : {resultat.travail.destination.name}", "succes")
            elif resultat.arrete:
                self._etats[source] = ("arrêtée", "avertissement")
            else:
                self._etats[source] = (f"erreur : {resultat.erreur.splitlines()[-1] if resultat.erreur else ''}", "erreur")
        if reussis:
            self._derniere_sortie = reussis[0].travail.destination.parent
        self.bouton_ouvrir.setVisible(bool(reussis))
        duree = sum(resultat.duree_s for resultat in resultats)
        message = f"{len(reussis)} vidéo{'s' if len(reussis) > 1 else ''} agrandie{'s' if len(reussis) > 1 else ''} en {duree_lisible(duree)}."
        if arrete:
            message = f"Arrêté : {message}"
        if erreurs:
            message += f" {len(erreurs)} en erreur (voir le tableau : le message de Topaz est au survol)."
        self._afficher(message, "avertissement" if (erreurs or arrete) else "succes")
        self._actualiser()

    def _echec(self, erreur: Exception) -> None:
        self._fin()
        self._afficher(f"Impossible de lancer Topaz : {erreur}", "erreur")
        self._actualiser()

    def ouvrir_le_dossier(self) -> None:
        if self._derniere_sortie is not None and self._derniere_sortie.is_dir():
            ouvrir_dossier(self._derniere_sortie)

    # --- Comparer ----------------------------------------------------------------------------

    def comparer(self) -> None:
        """« Comparer à un export de Topaz… » : deux vidéos choisies, comparées en arrière-plan."""
        if self._occupe:
            return
        depart = str(self._derniere_sortie or self._preferences.lire(PREF_DERNIER_DOSSIER) or dossier_documents())
        filtre = "Vidéos (" + " ".join(f"*{extension}" for extension in EXTENSIONS_VIDEOS) + ")"
        premiere, _f = QFileDialog.getOpenFileName(self, "Vidéo faite par l'app", depart, filtre)
        if not premiere:
            return
        seconde, _f = QFileDialog.getOpenFileName(self, "La même, exportée par Topaz", str(Path(premiere).parent), filtre)
        if seconde:
            self.comparer_les_videos(Path(premiere), Path(seconde))

    def comparer_les_videos(self, premiere: Path, seconde: Path) -> None:
        self._afficher(f"Comparaison de « {premiere.name} » et « {seconde.name} »…", "secondaire")
        self._occuper(True, self.bouton_comparer)
        taches.lancer(lambda: comparer(premiere, seconde), self._compare, self._comparaison_echouee)

    def _compare(self, comparaison) -> None:
        self._occuper(False)
        self._afficher(comparaison.message(), "succes" if comparaison.ssim >= 0.99 else "avertissement")

    def _comparaison_echouee(self, erreur: Exception) -> None:
        self._occuper(False)
        texte = str(erreur) if isinstance(erreur, ComparaisonImpossible) else f"Impossible de comparer : {erreur}"
        self._afficher(texte, "erreur")

    # --- Outils ------------------------------------------------------------------------------

    def _occuper(self, occupe: bool, bouton_occupe=None) -> None:
        self._occupe = occupe
        if occupe:
            self._bouton_occupe.occuper(bouton_occupe)
        else:
            self._bouton_occupe.liberer()
        actif = self._bouton_occupe.est
        for cadre in (self.cadre_topaz, self.cadre_prereglage, self.cadre_taille, self.cadre_sortie):
            cadre.setEnabled(not occupe)
        self.bouton_ajouter.setEnabled(not occupe or actif(self.bouton_ajouter))
        self.zone_depot.setEnabled(not occupe)
        self._mettre_a_jour_les_boutons()

    def _afficher(self, message: str, role: str) -> None:
        # Vert, rouge ou orange : effacé après 8 s (V3.2) ; la ligne garde sa place.
        afficher_message(self.statut, message, role, cacher_vide=False)
