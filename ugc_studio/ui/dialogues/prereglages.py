"""Fenêtre « Préréglages de sous-titres » (V2, lot 7 ; cahier des charges §7.13).

Une carte par préréglage : sa vignette animée (un exemple de sous-titre dessiné par le moteur de
l'aperçu, mot actif et animations compris), son nom, ★ pour celui des nouveaux projets.
« Appliquer » le met sur le projet ouvert (la page pose d'abord la question de la 1.1.0 s'il défait
un ajustement fait à la main). Menu ⋯ : Dupliquer, Renommer…, Exporter…, ★ pour les nouveaux
projets, Supprimer… En bas : Nouveau, Importer…, Rétablir les préréglages fournis.

Un préréglage se modifie dans le studio : l'appliquer, changer ses réglages, puis « Mettre à jour
ce préréglage » (menu ⋯ à côté de la liste des préréglages).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QMenu, QMessageBox, QVBoxLayout, QWidget

from ...chemins import dossier_documents
from ...prereglages import EXTENSION, ErreurPrereglage, Prereglage, appliquer
from ...projets import nom_de_dossier
from ...rendu.moteur import Moteur
from ...rendu.polices import police_remplacee
from ...services import Services
from ...sous_titres import ReglagesSousTitres, creer_sous_titres, ecran, resolution, sous_titre_au_temps
from ...style_sous_titres import style_de_depart
from ...transcription import Mot
from ..composants.conseils import entete_de_fenetre
from ..composants.defilement import zone_defilante
from ..composants.elements import Pastille, bouton, libelle, libelle_abrege, pastille, vider_disposition
from ..composants.flux import DispositionFlux
from ..icones import icone_menu
from ..theme import Arrondis, Couleurs, CouleursApercu, Dimensions, Espacements, Hauteurs, qcolor

# Exemple rejoué en boucle par les vignettes : (mot, début, fin), en secondes.
EXEMPLE = (
    ("Mais", 0.20, 0.50),
    ("ce", 0.55, 0.70),
    ("sérum", 0.75, 1.20),
    ("Glowzy", 1.25, 1.85),
    ("a", 1.95, 2.05),
    ("tout", 2.10, 2.40),
    ("changé", 2.45, 2.95),
    ("!", 2.95, 3.00),
)
PAUSE_S = 0.8  # vignette : pause avant de recommencer
LANGUE_EXEMPLE = "fr-FR"
FILTRE = f"Préréglages de sous-titres (*{EXTENSION})"


class VignettePrereglage(QWidget):
    """Un exemple de sous-titre dessiné avec le préréglage, au moment `temps` de sa boucle."""

    def __init__(self, prereglage: Prereglage, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(Dimensions.VIGNETTE_LARGEUR, Dimensions.VIGNETTE_HAUTEUR)
        reglages = appliquer(ReglagesSousTitres(), prereglage)
        largeur, hauteur = resolution(reglages)
        self.moteur = Moteur(reglages, largeur, hauteur)
        mots = [Mot(texte, debut, fin) for texte, debut, fin in EXEMPLE]
        self.mots, self.sous_titres = creer_sous_titres(mots, reglages, LANGUE_EXEMPLE, ecran(reglages), self.moteur.mesure)
        self._debuts = [s.debut for s in self.sous_titres]
        self.duree = (self.sous_titres[-1].fin if self.sous_titres else 0.0) + PAUSE_S
        # Le plus grand sous-titre tient dans la vignette ; chacun y est centré (sa place à l'écran
        # ne compte pas ici).
        self._blocs = [self.moteur.bloc(s, self.mots) for s in self.sous_titres]
        utile_l, utile_h = self.width() - 2 * Espacements.M, self.height() - 2 * Espacements.M
        plus_large = max((b.largeur for b in self._blocs), default=1.0)
        plus_haut = max((b.hauteur for b in self._blocs), default=1.0)
        self.echelle = min(utile_l / max(plus_large, 1.0), utile_h / max(plus_haut, 1.0))
        self.temps = 0.0

    def definir_temps(self, temps: float) -> None:
        self.temps = temps % self.duree if self.duree > 0 else 0.0
        self.update()

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(qcolor(CouleursApercu.FOND_NEUTRE))
        peintre.drawRoundedRect(QRectF(self.rect()), Arrondis.CONTROLE, Arrondis.CONTROLE)
        index = sous_titre_au_temps(self.sous_titres, self.temps, self._debuts)
        if index >= 0:
            bloc = self._blocs[index]
            ratio = self.devicePixelRatioF()
            image, x, y = self.moteur.image_de_l_instant(self.sous_titres[index], self.mots, self.echelle, ratio, self.temps)
            # Le milieu du sous-titre au milieu de la vignette.
            origine = QPointF(
                self.width() / 2 - (bloc.x + bloc.largeur / 2) * self.echelle,
                self.height() / 2 - (bloc.y + bloc.hauteur / 2) * self.echelle,
            )
            peintre.drawImage(QPointF(origine.x() + x / ratio, origine.y() + y / ratio), image)
        peintre.end()


class CartePrereglage(QFrame):
    """Un préréglage : vignette, nom, « Appliquer » et le menu ⋯."""

    def __init__(self, dialogue: DialoguePrereglages, prereglage: Prereglage, par_defaut: bool, du_projet: bool):
        super().__init__()
        self.setProperty("role", "bloc")
        self.prereglage = prereglage
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.M, Espacements.M, Espacements.M, Espacements.M)
        disposition.setSpacing(Espacements.S)
        self.vignette = VignettePrereglage(prereglage)
        disposition.addWidget(self.vignette)
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.nom = libelle_abrege(prereglage.nom, "intitule")
        # Ligne du nom aussi haute avec ou sans ★ : les cartes d'une même rangée restent alignées.
        self.nom.setMinimumHeight(Hauteurs.PASTILLE)
        ligne.addWidget(self.nom, 1)
        self.etoile: Pastille | None = None
        if par_defaut:
            # Juste « ★ » (le sens au survol) : avec « ★ Nouveaux projets », le nom n'avait plus la
            # place de s'écrire (« Blanc conto… »).
            self.etoile = pastille("★")
            self.etoile.setToolTip("Le style des nouveaux projets")
            ligne.addWidget(self.etoile)
        disposition.addLayout(ligne)
        texte = ReglagesSousTitres.depuis_dict({"style": prereglage.style}).texte
        details = [texte.police + (" (absente : Inter la remplace)" if police_remplacee(texte) else "")]
        if du_projet:
            details.append("style du projet")
        if prereglage.fourni:
            details.append("fourni")
        self.details = libelle_abrege("  ·  ".join(details), "legende")
        disposition.addWidget(self.details)
        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        self.bouton_appliquer = bouton("Appliquer", action=lambda: dialogue.appliquer(prereglage.identifiant))
        self.bouton_appliquer.setEnabled(dialogue.projet_ouvert)
        self.bouton_appliquer.setToolTip("Mettre ce style sur le projet ouvert" if dialogue.projet_ouvert else "Ouvre d'abord un projet")
        actions.addWidget(self.bouton_appliquer)
        actions.addStretch(1)
        plus = bouton("", variante="icone", nom_icone="ellipsis")
        plus.setToolTip("Plus d'actions")
        menu = QMenu(plus)
        menu.addAction(icone_menu("copy"), "Dupliquer").triggered.connect(lambda: dialogue.dupliquer(prereglage.identifiant))
        menu.addAction(icone_menu("square-pen"), "Renommer…").triggered.connect(lambda: dialogue.renommer(prereglage.identifiant))
        menu.addAction(icone_menu("download"), "Exporter…").triggered.connect(lambda: dialogue.exporter(prereglage.identifiant))
        if par_defaut:
            menu.addAction(icone_menu("star"), "Ne plus l'utiliser pour les nouveaux projets").triggered.connect(
                lambda: dialogue.definir_par_defaut("")
            )
        else:
            menu.addAction(icone_menu("star"), "Utiliser pour les nouveaux projets (★)").triggered.connect(
                lambda: dialogue.definir_par_defaut(prereglage.identifiant)
            )
        menu.addSeparator()
        menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer…").triggered.connect(
            lambda: dialogue.supprimer(prereglage.identifiant)
        )
        plus.setMenu(menu)
        self.menu = menu
        actions.addWidget(plus)
        disposition.addLayout(actions)
        self.setFixedWidth(Dimensions.VIGNETTE_LARGEUR + 2 * Espacements.M)


class DialoguePrereglages(QDialog):
    """`actuel` : le préréglage d'origine du projet ouvert ("" : aucun) ; `projet_ouvert` : sans
    projet, « Appliquer » est grisé. Après la fenêtre, `prereglage_choisi` : celui à appliquer."""

    def __init__(self, services: Services, parent: QWidget | None = None, actuel: str = "", projet_ouvert: bool = True):
        super().__init__(parent)
        self._services = services
        self._actuel = actuel
        self.projet_ouvert = projet_ouvert
        self.prereglage_choisi: str | None = None
        self.setWindowTitle("Préréglages de sous-titres")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)
        self.resize(Dimensions.DIALOGUE_PREREGLAGES_LARGEUR, Dimensions.DIALOGUE_PREREGLAGES_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(
            entete_de_fenetre(
                "Préréglages de sous-titres",
                "prereglages",
                aide=(
                    "Un préréglage garde tout le style : onglets Texte, Mots, Animations, Position et Découpage. "
                    "Le projet en garde sa propre copie : modifier un préréglage ne change pas les projets déjà faits."
                ),
            )
        )
        self.zone, contenu = zone_defilante()  # les cartes défilent s'il y en a plus de 6
        self._grille = DispositionFlux(espacement=Espacements.M)
        contenu.addLayout(self._grille)
        contenu.addStretch(1)
        disposition.addWidget(self.zone, 1)
        self.statut = libelle("", "secondaire")
        self.statut.hide()
        disposition.addWidget(self.statut)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        self.bouton_nouveau = bouton("Nouveau", nom_icone="plus", action=self.nouveau)
        self.bouton_nouveau.setToolTip("Un préréglage à partir de zéro (le style de départ)")
        boutons.addWidget(self.bouton_nouveau)
        self.bouton_importer = bouton("Importer…", variante="contour", nom_icone="folder-open", action=self.importer)
        boutons.addWidget(self.bouton_importer)
        self.bouton_retablir = bouton(
            "Rétablir les préréglages fournis", variante="contour", nom_icone="rotate-ccw", action=self.retablir_fournis
        )
        boutons.addWidget(self.bouton_retablir)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Fermer", action=self.reject))
        disposition.addLayout(boutons)

        self.cartes: list[CartePrereglage] = []
        self._horloge = QElapsedTimer()
        self._animation = QTimer(self)
        self._animation.setInterval(round(1000 / Dimensions.VIGNETTE_IMAGES_PAR_SECONDE))
        self._animation.timeout.connect(self._animer)
        services.prereglages.abonner(self.rafraichir)
        # Fenêtre détruite sans avoir été fermée normalement : on se désabonne quand même.
        rappel = self.rafraichir
        self.destroyed.connect(lambda: services.prereglages.desabonner(rappel))
        self.rafraichir()

    # --- Affichage -----------------------------------------------------------------------------

    def rafraichir(self) -> None:
        vider_disposition(self._grille)
        bibliotheque = self._services.prereglages
        self.cartes = [
            CartePrereglage(self, p, p.identifiant == bibliotheque.par_defaut, p.identifiant == self._actuel)
            for p in bibliotheque.prereglages
        ]
        for carte in self.cartes:
            self._grille.addWidget(carte)
        if not self.cartes:
            self._grille.addWidget(libelle("Aucun préréglage : crée-en un, ou rétablis ceux fournis.", "discret"))
        self._animer()

    def carte(self, identifiant: str) -> CartePrereglage | None:
        return next((c for c in self.cartes if c.prereglage.identifiant == identifiant), None)

    def showEvent(self, evenement) -> None:  # noqa: N802
        super().showEvent(evenement)
        self._horloge.start()
        self._animation.start()

    def hideEvent(self, evenement) -> None:  # noqa: N802
        self._animation.stop()
        super().hideEvent(evenement)

    def done(self, resultat: int) -> None:
        # Fenêtre fermée : plus d'animation, et plus prévenue des changements de la bibliothèque.
        self._animation.stop()
        self._services.prereglages.desabonner(self.rafraichir)
        super().done(resultat)

    def _animer(self) -> None:
        temps = self._horloge.elapsed() / 1000 if self._horloge.isValid() else 0.0
        for carte in self.cartes:
            carte.vignette.definir_temps(temps)

    def montrer_temps(self, temps: float) -> None:
        """Toutes les vignettes à ce moment de leur boucle (autotest : captures)."""
        self._animation.stop()
        for carte in self.cartes:
            carte.vignette.definir_temps(temps)

    def _afficher(self, message: str, role: str = "succes") -> None:
        self.statut.setText(message)
        self.statut.setVisible(bool(message))
        self.statut.setProperty("role", role)
        self.statut.style().unpolish(self.statut)
        self.statut.style().polish(self.statut)

    # --- Questions (remplacées dans les tests) -------------------------------------------------

    def _demander_nom(self, titre: str, nom: str) -> str | None:
        texte, ok = QInputDialog.getText(self, titre, "Nom du préréglage :", text=nom)
        return texte if ok and texte.strip() else None

    def _confirmer(self, titre: str, question: str, action: str) -> bool:
        boite = QMessageBox(self)
        boite.setIcon(QMessageBox.Icon.Question)
        boite.setWindowTitle(titre)
        boite.setText(question)
        oui = boite.addButton(action, QMessageBox.ButtonRole.AcceptRole)
        boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        boite.exec()
        return boite.clickedButton() is oui

    def _fichier_a_importer(self) -> Path | None:
        choix, _ = QFileDialog.getOpenFileName(self, "Importer des préréglages", str(dossier_documents()), FILTRE)
        return Path(choix) if choix else None

    def _fichier_d_export(self, nom: str) -> Path | None:
        proposition = dossier_documents() / f"{nom_de_dossier(nom)}{EXTENSION}"
        choix, _ = QFileDialog.getSaveFileName(self, "Exporter le préréglage", str(proposition), FILTRE)
        if not choix:
            return None
        chemin = Path(choix)
        return chemin if chemin.suffix.lower() == EXTENSION else chemin.with_name(chemin.name + EXTENSION)

    # --- Actions -------------------------------------------------------------------------------

    def appliquer(self, identifiant: str) -> None:
        self.prereglage_choisi = identifiant
        self.accept()

    def nouveau(self) -> None:
        bibliotheque = self._services.prereglages
        nom = self._demander_nom("Nouveau préréglage", bibliotheque.nom_libre("Nouveau préréglage"))
        if nom is None:
            return
        depart = ReglagesSousTitres(texte=style_de_depart())
        cree = bibliotheque.ajouter(nom, depart.en_dict()["style"])
        self._afficher(f"« {cree.nom} » créé : applique-le, règle-le dans le studio, puis « Mettre à jour ce préréglage ».")

    def dupliquer(self, identifiant: str) -> None:
        try:
            copie = self._services.prereglages.dupliquer(identifiant)
        except ErreurPrereglage as erreur:
            self._afficher(str(erreur), "erreur")
            return
        self._afficher(f"Copie créée : « {copie.nom} ».")

    def renommer(self, identifiant: str) -> None:
        bibliotheque = self._services.prereglages
        prereglage = bibliotheque.prereglage(identifiant)
        if prereglage is None:
            return
        nom = self._demander_nom("Renommer le préréglage", prereglage.nom)
        if nom is None:
            return
        try:
            renomme = bibliotheque.renommer(identifiant, nom)
        except ErreurPrereglage as erreur:
            self._afficher(str(erreur), "erreur")
            return
        self._afficher(f"Renommé : « {renomme.nom} ».")

    def exporter(self, identifiant: str) -> None:
        bibliotheque = self._services.prereglages
        prereglage = bibliotheque.prereglage(identifiant)
        if prereglage is None:
            return
        chemin = self._fichier_d_export(prereglage.nom)
        if chemin is None:
            return
        try:
            bibliotheque.exporter([identifiant], chemin)
        except ErreurPrereglage as erreur:
            self._afficher(str(erreur), "erreur")
            return
        self._afficher(f"Préréglage exporté : {chemin.name} (à importer sur un autre ordinateur, ou à garder en copie).")

    def importer(self) -> None:
        chemin = self._fichier_a_importer()
        if chemin is None:
            return
        try:
            ajoutes = self._services.prereglages.importer(chemin)
        except ErreurPrereglage as erreur:
            self._afficher(str(erreur), "erreur")
            return
        noms = ", ".join(f"« {p.nom} »" for p in ajoutes)
        absentes = sorted(
            {
                texte.police
                for texte in (ReglagesSousTitres.depuis_dict({"style": p.style}).texte for p in ajoutes)
                if police_remplacee(texte)
            }
        )
        message = f"Importé : {noms}."
        if absentes:
            polices = ", ".join(f"« {police} »" for police in absentes)
            message += f" Police absente de cet ordinateur ({polices}) : Inter la remplace, le préréglage garde son nom."
        self._afficher(message, "avertissement" if absentes else "succes")

    def definir_par_defaut(self, identifiant: str) -> None:
        bibliotheque = self._services.prereglages
        bibliotheque.definir_par_defaut(identifiant)
        prereglage = bibliotheque.prereglage(identifiant)
        if prereglage is None:
            self._afficher("Plus de préréglage pour les nouveaux projets : ils prendront le style de départ.")
        else:
            self._afficher(f"Les nouveaux projets prendront « {prereglage.nom} ».")

    def supprimer(self, identifiant: str) -> None:
        bibliotheque = self._services.prereglages
        prereglage = bibliotheque.prereglage(identifiant)
        if prereglage is None:
            return
        question = f"Supprimer le préréglage « {prereglage.nom} » ? Les projets qui l'utilisent gardent leur style."
        if prereglage.fourni:
            question += " « Rétablir les préréglages fournis » le remettra."
        if not self._confirmer("Supprimer le préréglage", question, "Supprimer"):
            return
        bibliotheque.supprimer(identifiant)
        self._afficher(f"« {prereglage.nom} » supprimé.")

    def retablir_fournis(self) -> None:
        question = (
            "Remettre les 6 préréglages fournis comme à l'origine ? Ceux que tu as modifiés ou supprimés "
            "reviennent ; tes propres préréglages ne changent pas."
        )
        if not self._confirmer("Rétablir les préréglages fournis", question, "Rétablir"):
            return
        self._services.prereglages.retablir_fournis()
        self._afficher("Préréglages fournis rétablis.")
