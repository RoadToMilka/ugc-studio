"""Bloc « Aperçu » du studio des sous-titres (V2, lot 3 ; cahier des charges §7.7 et §7.9).

La toile (composants/apercu.py) et ses commandes : lecture et pause (bouton, ou barre Espace),
barre de position, temps, boucle sur le sous-titre choisi, fond (vidéo, gris ou damier), zoom
(« Ajusté » ou « 100 % ») et repères (zone de sécurité, marge maximum, grille). Le fond, le zoom, les
repères et la boucle sont retenus d'une fois sur l'autre (préférences de l'app).

Le studio : l'aperçu à gauche et les réglages à droite ; l'un sous l'autre quand la fenêtre est
étroite (DispositionStudio).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ....preferences import Preferences
from ...composants.apercu import FOND_GRIS, FOND_VIDEO, FONDS, ZOOM_AJUSTE, ZOOMS, ToileApercu, ZoneApercu
from ...composants.choix import ChoixEnBoutons
from ...composants.elements import bouton, case_a_cocher, glissiere, info, libelle
from ...composants.flux import DispositionFlux
from ...icones import icone
from ...theme import Couleurs, Dimensions, Espacements

CLE_PREFERENCES = "apercu_sous_titres"


class BlocApercu(QFrame):
    def __init__(self, preferences: Preferences, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "bloc")
        self._preferences = preferences
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("Aperçu", "titre-bloc"))

        self.toile = ToileApercu()
        self.zone = ZoneApercu(self.toile)
        disposition.addWidget(self.zone)
        self.info_pipette = info("Pipette : clique dans l'aperçu sur la couleur à prendre (Échap : annuler).")
        self.info_pipette.hide()
        self.toile.pipette_change.connect(self.info_pipette.setVisible)
        disposition.addWidget(self.info_pipette)

        # Vidéo déplacée ou supprimée (elle n'est pas copiée dans le projet).
        self.ligne_introuvable = QWidget()
        ligne = QVBoxLayout(self.ligne_introuvable)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.S)
        self.message_video = libelle("", "legende-avertissement")
        ligne.addWidget(self.message_video)
        boutons = QHBoxLayout()
        self.bouton_retrouver = bouton("Retrouver la vidéo…", variante="contour", nom_icone="folder-open")
        boutons.addWidget(self.bouton_retrouver)
        boutons.addStretch(1)
        ligne.addLayout(boutons)
        self.ligne_introuvable.hide()
        disposition.addWidget(self.ligne_introuvable)

        # Lecture.
        lecture = QHBoxLayout()
        lecture.setSpacing(Espacements.S)
        self.bouton_lecture = bouton("", variante="icone")
        lecture.addWidget(self.bouton_lecture)
        self.position = glissiere()
        lecture.addWidget(self.position, 1)
        self.temps = libelle("0:00 / 0:00", "legende", retour_a_la_ligne=False)
        lecture.addWidget(self.temps)
        self.bouton_boucle = bouton("", variante="icone")
        self.bouton_boucle.setCheckable(True)
        self.bouton_boucle.setIcon(icone("repeat", Couleurs.TEXTE_SECONDAIRE, couleur_active=Couleurs.ACCENT_SURVOL))
        self.bouton_boucle.setToolTip("Rejouer en boucle le sous-titre choisi")
        lecture.addWidget(self.bouton_boucle)
        disposition.addLayout(lecture)
        self.definir_lecture(False)

        # Fond et zoom.
        options = DispositionFlux(espacement=Espacements.M)
        self.fond = ChoixEnBoutons(FONDS, "Fond de l'aperçu : la vidéo, un gris neutre, ou un damier (overlay transparent)")
        self.zoom = ChoixEnBoutons(ZOOMS, "« 100 % » : un pixel de la vidéo par pixel de l'écran, pour juger la netteté")
        for titre, choix in (("Fond", self.fond), ("Zoom", self.zoom)):
            groupe = QWidget()
            rangee = QHBoxLayout(groupe)
            rangee.setContentsMargins(0, 0, 0, 0)
            rangee.setSpacing(Espacements.S)
            rangee.addWidget(libelle(titre, "legende", retour_a_la_ligne=False))
            rangee.addWidget(choix)
            options.addWidget(groupe)
        disposition.addLayout(options)

        # Repères.
        reperes = DispositionFlux(espacement=Espacements.M)
        reperes.addWidget(libelle("Repères", "legende", retour_a_la_ligne=False))
        zone, self.repere_zone = case_a_cocher("Zone de sécurité")
        reperes.addWidget(zone)
        zone, self.repere_marge = case_a_cocher("Marge maximum")
        reperes.addWidget(zone)
        zone, self.repere_grille = case_a_cocher("Grille")
        reperes.addWidget(zone)
        disposition.addLayout(reperes)
        disposition.addStretch(1)  # deux colonnes de hauteurs différentes : la place en trop va en bas

        self._lire_preferences()
        self.fond.change.connect(lambda _fond: self._appliquer_options())
        self.zoom.change.connect(lambda zoom: (self.zone.definir_zoom(zoom), self._retenir()))
        for case in (self.repere_zone, self.repere_marge, self.repere_grille):
            case.toggled.connect(lambda _coche: self._appliquer_options())
        self.bouton_boucle.toggled.connect(lambda _coche: self._retenir())

    def sizeHint(self) -> QSize:  # noqa: N802
        """Largeur de la colonne de l'aperçu, quand le studio a deux colonnes."""
        return QSize(Dimensions.STUDIO_COLONNE_APERCU_LARGEUR, super().sizeHint().height())

    # --- Lecture -------------------------------------------------------------------------------

    def definir_lecture(self, en_lecture: bool) -> None:
        self.bouton_lecture.setIcon(icone("pause" if en_lecture else "play", Couleurs.ACCENT_SURVOL, rempli=True))
        self.bouton_lecture.setToolTip("Pause (barre Espace)" if en_lecture else "Lecture (barre Espace)")

    # --- Fond, zoom, repères -------------------------------------------------------------------

    def definir_video_possible(self, possible: bool) -> None:
        """Sans vidéo (ou vidéo introuvable), le choix « Vidéo » est grisé et l'aperçu montre le gris."""
        self.fond.bouton(FOND_VIDEO).setEnabled(possible)
        self._appliquer_options(retenir=False)

    def _fond_affiche(self) -> str:
        fond = self.fond.valeur()
        if fond == FOND_VIDEO and not self.fond.bouton(FOND_VIDEO).isEnabled():
            return FOND_GRIS
        return fond

    def _appliquer_options(self, retenir: bool = True) -> None:
        self.toile.definir_fond(self._fond_affiche())
        self.toile.definir_reperes(self.repere_zone.isChecked(), self.repere_marge.isChecked(), self.repere_grille.isChecked())
        if retenir:
            self._retenir()

    def _lire_preferences(self) -> None:
        options = self._preferences.lire(CLE_PREFERENCES, {})
        options = options if isinstance(options, dict) else {}
        self.fond.definir(options.get("fond") if options.get("fond") in FONDS else FOND_VIDEO)
        zoom = options.get("zoom") if options.get("zoom") in ZOOMS else ZOOM_AJUSTE
        self.zoom.definir(zoom)
        self.zone.definir_zoom(zoom)
        reperes = options.get("reperes")
        zone, marge, grille = reperes if isinstance(reperes, list) and len(reperes) == 3 else (True, True, False)
        for case, coche in ((self.repere_zone, zone), (self.repere_marge, marge), (self.repere_grille, grille)):
            case.blockSignals(True)
            case.setChecked(bool(coche))
            case.blockSignals(False)
        self.bouton_boucle.blockSignals(True)
        self.bouton_boucle.setChecked(bool(options.get("boucle", False)))
        self.bouton_boucle.blockSignals(False)
        self._appliquer_options(retenir=False)

    def _retenir(self) -> None:
        self._preferences.ecrire(
            CLE_PREFERENCES,
            {
                "fond": self.fond.valeur(),
                "zoom": self.zoom.valeur(),
                "reperes": [self.repere_zone.isChecked(), self.repere_marge.isChecked(), self.repere_grille.isChecked()],
                "boucle": self.bouton_boucle.isChecked(),
            },
        )
        try:
            self._preferences.enregistrer()
        except OSError:
            pass  # une préférence d'affichage non retenue n'empêche rien


class DispositionStudio(QWidget):
    """L'aperçu à gauche (largeur fixe) et les réglages à droite ; l'un sous l'autre quand la page a
    moins de STUDIO_DEUX_COLONNES_MIN pixels de large, ou moins que ce que demandent les deux colonnes
    (un onglet des réglages peut demander plus de place : voir largeur_deux_colonnes)."""

    def __init__(self, apercu: QWidget, reglages: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self._apercu, self._reglages = apercu, reglages
        self._disposition = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._disposition.setContentsMargins(0, 0, 0, 0)
        self._disposition.setSpacing(Espacements.XL)
        self._disposition.addWidget(apercu, 0)
        self._disposition.addWidget(reglages, 1)
        self._deux_colonnes: bool | None = None
        self._adapter(Dimensions.STUDIO_DEUX_COLONNES_MIN)

    @property
    def deux_colonnes(self) -> bool:
        return bool(self._deux_colonnes)

    def largeur_deux_colonnes(self) -> int:
        """Largeur qu'il faut pour deux colonnes : la colonne de l'aperçu, l'espace entre les deux, et
        le minimum des réglages (il dépend de l'onglet affiché et des groupes ouverts). Sans cette
        vérification, des réglages plus larges que leur colonne garderaient le studio sur deux colonnes
        trop larges pour la page : son bord droit serait coupé."""
        besoin = self._apercu.sizeHint().width() + self._disposition.spacing() + self._reglages.minimumSizeHint().width()
        return max(Dimensions.STUDIO_DEUX_COLONNES_MIN, besoin)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Largeur minimale : celle d'une seule colonne. Sans cela, sur deux colonnes, le studio ne
        pourrait pas devenir plus étroit que ses deux colonnes : il n'y aurait jamais assez peu de place
        pour passer sur une colonne, et le bord droit de la page serait coupé."""
        largeur = max(self._apercu.minimumSizeHint().width(), self._reglages.minimumSizeHint().width())
        return QSize(largeur, super().minimumSizeHint().height())

    def resizeEvent(self, evenement) -> None:  # noqa: N802
        self._adapter(evenement.size().width())
        super().resizeEvent(evenement)

    def event(self, evenement) -> bool:
        if evenement.type() == QEvent.Type.LayoutRequest:
            self._adapter(self.width())  # les réglages demandent une autre place (onglet, groupe ouvert)
        return super().event(evenement)

    def _adapter(self, largeur: int) -> None:
        limite = self.largeur_deux_colonnes()
        if self._deux_colonnes:
            deux = largeur >= limite
        else:
            # Pour repasser sur deux colonnes, il faut un peu plus de place : sans cette marge, la barre de
            # défilement de la page (qui apparaît ou disparaît selon la disposition) ferait changer la
            # disposition en boucle autour de la limite.
            marge = 0 if self._deux_colonnes is None else Dimensions.BARRE_DEFILEMENT + Espacements.S
            deux = largeur >= limite + marge
        if deux == self._deux_colonnes:
            return
        self._deux_colonnes = deux
        self._disposition.setDirection(QBoxLayout.Direction.LeftToRight if deux else QBoxLayout.Direction.TopToBottom)
        # Deux colonnes : l'aperçu garde sa largeur (BlocApercu.sizeHint) ; l'un sous l'autre : toute la largeur.
        politique = QSizePolicy.Policy.Fixed if deux else QSizePolicy.Policy.Preferred
        self._apercu.setSizePolicy(politique, QSizePolicy.Policy.Preferred)
