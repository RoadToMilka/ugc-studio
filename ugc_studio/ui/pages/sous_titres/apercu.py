"""Bloc « Aperçu » du studio des sous-titres (V2, lot 3 ; cahier des charges §7.7 et §7.9).

La toile (composants/apercu.py) et ses commandes : lecture et pause (bouton, ou barre Espace),
barre de position, temps, boucle sur le sous-titre choisi, fond (vidéo, gris ou damier), zoom
(« Ajusté » ou « 100 % ») et repères (zone de sécurité, marge maximum, grille). Le fond, le zoom, les
repères et la boucle sont retenus d'une fois sur l'autre (préférences de l'app).

V3.1 (lot 5) : la zone de l'aperçu a exactement la taille de la vidéo affichée, centrée dans le bloc
(plus de bandes sombres de chaque côté). En fenêtre moyenne ou petite, la vidéo prend la largeur du
bloc, 540 px de haut au plus ; en grande fenêtre, le bloc a la hauteur des trois colonnes, et la
vidéo prend la hauteur qui reste sous son titre et au-dessus des commandes (largeur_pour_hauteur :
la largeur de la colonne qui va avec). Les commandes passent à la ligne quand la colonne est étroite.
La disposition de la page : disposition.py.

V3.1 (lot 6) : sans vidéo ni son (des sous-titres d'un fichier SRT, sans vidéo), la lecture est
grisée ; un clic sur un sous-titre le montre toujours.

V3.2 (lot 4) : « Fond » et « Zoom » au-dessus de leurs boutons, comme le nom d'un champ (à gauche
jusqu'à la 3.1.3), côte à côte quand la place le permet ; « Repères » au-dessus de ses cases, sur une
ligne quand la place le permet. En grande fenêtre, la vidéo vise 640 px de haut (hauteur_pour_video,
utilisée par disposition.py), et le bloc est assez large pour « Fond » et « Zoom » côte à côte.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ....preferences import Preferences
from ...composants.apercu import FOND_GRIS, FOND_VIDEO, FONDS, ZOOM_AJUSTE, ZOOMS, ToileApercu, ZoneApercu
from ...composants.choix import ChoixEnBoutons
from ...composants.elements import ChampNomme, bouton, case_a_cocher, glissiere, info, libelle, marge_haute_titre
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
        disposition.setContentsMargins(Espacements.XL, marge_haute_titre(), Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("Aperçu", "titre-bloc"))

        self.toile = ToileApercu()
        self.zone = ZoneApercu(self.toile)
        disposition.addWidget(self.zone, 0, Qt.AlignmentFlag.AlignHCenter)  # à la taille de la vidéo, centrée
        self._hauteur_imposee: int | None = None  # grande fenêtre : la hauteur des colonnes
        self._largeur_voulue: int | None = None  # grande fenêtre : la largeur qui va avec
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
        self._lecture = lecture
        self._lecture_possible, self._en_lecture = True, False
        self.definir_lecture(False)

        # Fond et zoom : chacun sous son nom (V3.2), côte à côte quand la place le permet, 16 px entre
        # eux comme entre deux réglages.
        options = DispositionFlux(espacement=Espacements.L, espacement_vertical=Espacements.M)
        self.fond = ChoixEnBoutons(FONDS, "Fond de l'aperçu : la vidéo, un gris neutre, ou un damier (calque transparent)")
        self.zoom = ChoixEnBoutons(ZOOMS, "« 100 % » : un pixel de la vidéo par pixel de l'écran, pour juger la netteté")
        self.champ_fond, self.champ_zoom = ChampNomme("Fond", self.fond), ChampNomme("Zoom", self.zoom)
        options.addWidget(self.champ_fond)
        options.addWidget(self.champ_zoom)
        disposition.addLayout(options)
        self._options = options

        # Repères : leur nom au-dessus des cases (V3.2), qui se suivent sur une ligne quand la place le
        # permet ; 8 px visibles entre le nom et les cases, comme sous le nom d'un champ.
        reperes = DispositionFlux(espacement=Espacements.M)
        zone, self.repere_zone = case_a_cocher("Zone de sécurité")
        reperes.addWidget(zone)
        zone, self.repere_marge = case_a_cocher("Marge maximum")
        reperes.addWidget(zone)
        zone, self.repere_grille = case_a_cocher("Grille")
        reperes.addWidget(zone)
        groupe_reperes = QVBoxLayout()
        groupe_reperes.setContentsMargins(0, 0, 0, 0)
        groupe_reperes.setSpacing(Dimensions.ECART_NOM_CHAMP)
        self.nom_reperes = libelle("Repères", "legende", retour_a_la_ligne=False)
        groupe_reperes.addWidget(self.nom_reperes)
        groupe_reperes.addLayout(reperes)
        disposition.addLayout(groupe_reperes)
        self._reperes = reperes
        disposition.addStretch(1)  # deux colonnes de hauteurs différentes : la place en trop va en bas

        self._lire_preferences()
        self.fond.change.connect(lambda _fond: self._appliquer_options())
        self.zoom.change.connect(lambda zoom: (self.zone.definir_zoom(zoom), self._retenir()))
        for case in (self.repere_zone, self.repere_marge, self.repere_grille):
            case.toggled.connect(lambda _coche: self._appliquer_options())
        self.bouton_boucle.toggled.connect(lambda _coche: self._retenir())

    # --- Taille : la zone à la taille de la vidéo (V3.1, lot 5) -----------------------------------

    def _bords(self) -> int:
        """Largeur prise par le bloc autour de son contenu : ses marges (24 px de chaque côté) et sa
        bordure (1 px de chaque côté, que Qt retire aussi de la place du contenu ; jusqu'à la 3.1.3,
        elle était oubliée : la zone avait 2 px de plus que la place, et « Fond » et « Zoom » passaient
        à la ligne dans une colonne à leur largeur exacte)."""
        self.ensurePolished()  # la bordure vient de la feuille de style
        cadre, marges = self.contentsMargins(), self.layout().contentsMargins()
        return cadre.left() + cadre.right() + marges.left() + marges.right()

    def largeur_min(self, sur_une_ligne: bool = False) -> int:
        """Largeur du bloc sous laquelle les commandes ne tiennent plus (la plus longue rangée qui ne
        passe pas à la ligne : « Fond » et ses trois choix). `sur_une_ligne` (grande fenêtre, V3.2) :
        assez large pour « Fond » et « Zoom » côte à côte, et les trois repères sur une ligne ; le bloc
        garde ainsi sa hauteur la plus basse, et la vidéo la place la plus haute."""
        options, reperes = self._options, self._reperes
        if sur_une_ligne:
            commandes = max(self._lecture.minimumSize().width(), options.largeur_sur_une_ligne(), reperes.largeur_sur_une_ligne())
        else:
            commandes = max(self._lecture.minimumSize().width(), options.minimumSize().width(), reperes.minimumSize().width())
        return commandes + self._bords()

    def _bornee(self, largeur_video: int, sur_une_ligne: bool = False) -> int:
        """La largeur du bloc pour une vidéo de cette largeur : au moins celle des commandes (voir
        largeur_min), au plus STUDIO_APERCU_LARGEUR_MAX (une vidéo 16:9 laisse ainsi de la place aux
        autres colonnes)."""
        largeur = largeur_video + self._bords()
        return max(self.largeur_min(sur_une_ligne), min(largeur, Dimensions.STUDIO_APERCU_LARGEUR_MAX))

    def largeur_naturelle(self) -> int:
        """Fenêtre moyenne : la largeur de la colonne de l'aperçu, celle de la vidéo à 540 px de haut
        au plus (304 px pour une vidéo 9:16)."""
        largeur_video, hauteur_video = self.toile.taille_video()
        return self._bornee(round(Dimensions.APERCU_HAUTEUR_MAX * largeur_video / hauteur_video))

    def _hauteur_sans_la_video(self, largeur: int) -> int:
        """Hauteur du bloc sans la vidéo, pour cette largeur : titre, commandes (qui passent à la
        ligne si besoin), marges et espaces."""
        hauteur = self.heightForWidth(largeur)  # -1 si rien ne dépend de la largeur
        return (hauteur if hauteur >= 0 else self.sizeHint().height()) - self.zone.height()

    def largeur_pour_hauteur(self, hauteur: int) -> int:
        """Grande fenêtre : la largeur du bloc pour que la vidéo, entière, prenne la hauteur qui reste
        quand le bloc a cette hauteur ; assez large, au moins, pour « Fond » et « Zoom » côte à côte
        (V3.2). Les commandes passent à la ligne selon la largeur : le calcul est refait une fois avec
        la largeur trouvée."""
        largeur_video, hauteur_video = self.toile.taille_video()
        largeur = self.largeur_min(sur_une_ligne=True)
        for _passage in range(2):
            reste = max(Dimensions.APERCU_HAUTEUR_MIN, hauteur - self._hauteur_sans_la_video(largeur))
            largeur = self._bornee(round(reste * largeur_video / hauteur_video), sur_une_ligne=True)
        return largeur

    def hauteur_pour_video(self, hauteur_video_voulue: int) -> int:
        """Grande fenêtre (V3.2) : la hauteur du bloc pour une vidéo de cette hauteur (640 px visés), à
        la largeur qui va avec ; moins haute si la vidéo, plus large que haute, atteint d'abord la
        largeur maximale de la colonne (STUDIO_APERCU_LARGEUR_MAX)."""
        largeur_video, hauteur_video = self.toile.taille_video()
        largeur = self._bornee(round(hauteur_video_voulue * largeur_video / hauteur_video), sur_une_ligne=True)
        place = largeur - self._bords()
        hauteur = min(hauteur_video_voulue, round(place * hauteur_video / largeur_video))
        return self._hauteur_sans_la_video(largeur) + max(hauteur, Dimensions.APERCU_HAUTEUR_MIN)

    def definir_hauteur_imposee(self, hauteur: int | None) -> None:
        """Grande fenêtre : le bloc a cette hauteur (celle des colonnes), et la vidéo prend la place qui
        reste. None : la vidéo prend la largeur du bloc, 540 px de haut au plus."""
        if hauteur != self._hauteur_imposee:
            self._hauteur_imposee = hauteur
            self.ajuster_la_zone()

    def ajuster_la_zone(self) -> None:
        """La zone prend la taille de la vidéo affichée, entière, dans la place du bloc."""
        largeur = self.width() - self._bords()
        if self._hauteur_imposee is None:
            hauteur = Dimensions.APERCU_HAUTEUR_MAX
        else:
            hauteur = self._hauteur_imposee - self._hauteur_sans_la_video(self.width())
        taille = self.zone.taille_pour(largeur, hauteur)
        if taille != self.zone.size():
            self.zone.setFixedSize(taille)

    def actualiser_taille(self) -> None:
        """Le format de la vidéo a changé : nouvelle taille de la zone (et de la toile à 100 %)."""
        self.zone.actualiser_taille()
        self.ajuster_la_zone()
        self.updateGeometry()  # la colonne de l'aperçu change de largeur

    def resizeEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        super().resizeEvent(evenement)
        self.ajuster_la_zone()

    def definir_largeur_voulue(self, largeur: int | None) -> None:
        """La largeur de la colonne de l'aperçu, choisie par la disposition de la page (grande
        fenêtre : largeur_pour_hauteur) ; None : largeur_naturelle."""
        if largeur != self._largeur_voulue:
            self._largeur_voulue = largeur
            self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802
        """À côté de l'apparence, la colonne de l'aperçu prend cette largeur (taille fixe dans ce sens)."""
        return QSize(self._largeur_voulue or self.largeur_naturelle(), super().sizeHint().height())

    # --- Lecture -------------------------------------------------------------------------------

    def definir_lecture(self, en_lecture: bool) -> None:
        self._en_lecture = en_lecture
        self.bouton_lecture.setIcon(icone("pause" if en_lecture else "play", Couleurs.ACCENT_SURVOL, rempli=True))
        if not self._lecture_possible:
            self.bouton_lecture.setToolTip("Rien à lire : ni vidéo ni son. Clique sur un sous-titre pour le voir")
        else:
            self.bouton_lecture.setToolTip("Pause (barre Espace)" if en_lecture else "Lecture (barre Espace)")

    def definir_lecture_possible(self, possible: bool) -> None:
        """Ni vidéo ni son (V3.1 : des sous-titres d'un fichier SRT, sans vidéo) : ▶ et la barre de
        position sont grisés ; un clic sur un sous-titre (liste ou frise) le montre dans l'aperçu."""
        self._lecture_possible = possible
        self.bouton_lecture.setEnabled(possible)
        self.position.setEnabled(possible)
        self.definir_lecture(self._en_lecture and possible)

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
