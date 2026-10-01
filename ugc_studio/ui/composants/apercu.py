"""Aperçu fidèle des sous-titres (V2, lot 3 ; cahier des charges §7.7).

- ToileApercu : la vidéo (l'image que le lecteur affiche), ou un fond gris, ou un damier ; par-dessus,
  les sous-titres dessinés par le moteur de dessin (rendu/moteur.py, le même que l'export de la V3),
  puis les repères : zone de sécurité de la plateforme (pointillés mauves), marge maximum (trait
  rouge), grille (tiers et milieu de l'écran). On peut y glisser le sous-titre verticalement.
- ZoneApercu : la toile entière dans la place disponible (« Ajusté »), ou à 100 % (un pixel de la
  vidéo par pixel de l'écran, la zone défile) pour juger la netteté.
- LecteurApercu : lit la vidéo (Qt Multimedia : chaque image arrive dans un « puits vidéo »,
  QVideoSink) ou seulement le son d'une prise. Le temps des sous-titres est celui de l'image
  réellement affichée (son moment de présentation), pas une horloge à part : le sous-titre change
  exactement au bon moment.
"""

from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QWidget

from ...mise_en_page import limites_du_reglage_fin
from ...rendu.moteur import Moteur
from ...sous_titres import FORMAT_PAR_DEFAUT, FORMATS, MotAffiche, SousTitre
from ..theme import CouleursApercu, Dimensions, Opacites, qcolor
from .lecteur import VARIABLE_SANS_AUDIO

journal = logging.getLogger(__name__)

FOND_VIDEO, FOND_GRIS, FOND_DAMIER = "video", "gris", "damier"
FONDS = {FOND_VIDEO: "Vidéo", FOND_GRIS: "Gris", FOND_DAMIER: "Damier"}
ZOOM_AJUSTE, ZOOM_REEL = "ajuste", "reel"
ZOOMS = {ZOOM_AJUSTE: "Ajusté", ZOOM_REEL: "100 %"}
INTERVALLE_SON_SEUL_MS = 16  # son seul : position relue environ 60 fois par seconde
ECART_VOIX_TOLERE_S = 0.15  # voix d'une prise sous une vidéo muette : recalée au-delà


class ToileApercu(QWidget):
    """La vidéo (ou un fond), le sous-titre affiché et les repères."""

    glissement = Signal(float)  # pendant qu'on glisse le sous-titre : réglage fin visé (% de la hauteur)
    glissement_fini = Signal(float)  # au relâchement

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._moteur: Moteur | None = None
        self._mots: list[MotAffiche] = []
        self._sous_titre: SousTitre | None = None
        self._image = None  # image de la vidéo affichée (QVideoFrame), ou None
        self._fond = FOND_GRIS
        self._reperes = {"zone": True, "marge": True, "grille": False}
        self._zoom_reel = False
        self.glissable = False
        # Pendant un glissement : (y du pointeur au départ, réglage fin de départ, réglage fin visé).
        self._glisse: tuple[float, float, float] | None = None
        self._damier: QPixmap | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # --- Contenu ---------------------------------------------------------------------------------

    def definir(self, moteur: Moteur | None, mots: list[MotAffiche]) -> None:
        """Nouveau calcul des sous-titres (réglage changé, mots corrigés) : nouveau moteur."""
        self._moteur, self._mots = moteur, mots
        self._sous_titre = None
        self.update()

    def montrer(self, sous_titre: SousTitre | None) -> None:
        if sous_titre is not self._sous_titre:
            self._sous_titre = sous_titre
            self.update()

    @property
    def sous_titre(self) -> SousTitre | None:
        return self._sous_titre

    def definir_image(self, image) -> None:
        """Image de la vidéo à afficher (QVideoFrame), ou None (pas de vidéo)."""
        self._image = image
        if self._fond == FOND_VIDEO:
            self.update()

    def definir_fond(self, fond: str) -> None:
        self._fond = fond if fond in FONDS else FOND_GRIS
        self.update()

    def definir_reperes(self, zone: bool, marge: bool, grille: bool) -> None:
        self._reperes = {"zone": zone, "marge": marge, "grille": grille}
        self.update()

    def taille_video(self) -> tuple[int, int]:
        if self._moteur is None:
            return FORMATS[FORMAT_PAR_DEFAUT]
        return self._moteur.largeur, self._moteur.hauteur

    def montre_la_video(self) -> bool:
        """La vidéo est-elle dessinée en fond (et non le gris, faute d'image) ?"""
        return self._fond == FOND_VIDEO and self._image is not None

    # --- Géométrie -------------------------------------------------------------------------------

    def rect_video(self) -> QRectF:
        """Place de la vidéo dans la toile : entière et centrée (« Ajusté »), ou à 100 %. Son coin
        tombe pile sur un pixel de l'écran : le texte reste net."""
        largeur, hauteur = self.taille_video()
        ratio = self.devicePixelRatioF()
        if self._zoom_reel:
            return QRectF(0, 0, largeur / ratio, hauteur / ratio)
        echelle = min(self.width() / largeur, self.height() / hauteur)
        visible_l, visible_h = largeur * echelle, hauteur * echelle
        x = round((self.width() - visible_l) / 2 * ratio) / ratio
        y = round((self.height() - visible_h) / 2 * ratio) / ratio
        return QRectF(x, y, visible_l, visible_h)

    def rect_du_sous_titre(self) -> QRectF | None:
        """Rectangle du texte du sous-titre affiché, dans la toile (pour le glisser)."""
        if self._moteur is None or self._sous_titre is None:
            return None
        bloc = self._moteur.bloc(self._sous_titre, self._mots)
        cible = self.rect_video()
        echelle = cible.width() / self._moteur.largeur
        return QRectF(cible.x() + bloc.x * echelle, cible.y() + bloc.y * echelle, bloc.largeur * echelle, bloc.hauteur * echelle)

    # --- Dessin ----------------------------------------------------------------------------------

    def paintEvent(self, _evenement) -> None:  # noqa: N802 — nom imposé par Qt
        peintre = QPainter(self)
        peintre.fillRect(self.rect(), qcolor(CouleursApercu.AUTOUR))
        cible = self.rect_video()
        self._dessiner_fond(peintre, cible)
        if self._moteur is not None and self._sous_titre is not None:
            echelle = cible.width() / self._moteur.largeur
            origine = cible.topLeft()
            if self._glisse is not None:  # le sous-titre suit le pointeur
                decale = (self._glisse[2] - self._moteur.reglages.position.decalage_pct) / 100 * cible.height()
                origine = QPointF(origine.x(), origine.y() + decale)
            self._moteur.dessiner(peintre, origine, echelle, self._sous_titre, self._mots, self.devicePixelRatioF())
        self._dessiner_reperes(peintre, cible)
        peintre.end()

    def _motif_damier(self) -> QPixmap:
        if self._damier is None:
            cote = Dimensions.DAMIER_CASE
            motif = QPixmap(2 * cote, 2 * cote)
            motif.fill(qcolor(CouleursApercu.DAMIER_CLAIR))
            peintre = QPainter(motif)
            peintre.fillRect(0, 0, cote, cote, qcolor(CouleursApercu.DAMIER_FONCE))
            peintre.fillRect(cote, cote, cote, cote, qcolor(CouleursApercu.DAMIER_FONCE))
            peintre.end()
            self._damier = motif
        return self._damier

    def _dessiner_fond(self, peintre: QPainter, cible: QRectF) -> None:
        if self.montre_la_video():
            from PySide6.QtMultimedia import QVideoFrame

            peintre.fillRect(cible, Qt.GlobalColor.black)
            peintre.save()
            peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            # paint() de Qt tient compte de la rotation d'une vidéo de téléphone (image « couchée »).
            options = QVideoFrame.PaintOptions()
            options.paintFlags = QVideoFrame.PaintOptions.PaintFlag.DontDrawSubtitles  # pas ceux du fichier
            self._image.paint(peintre, cible, options)
            peintre.restore()
        elif self._fond == FOND_DAMIER:
            peintre.save()
            peintre.setBrushOrigin(cible.topLeft())
            peintre.fillRect(cible, QBrush(self._motif_damier()))
            peintre.restore()
        else:
            peintre.fillRect(cible, qcolor(CouleursApercu.FOND_NEUTRE))

    def _dessiner_reperes(self, peintre: QPainter, cible: QRectF) -> None:
        if self._moteur is None:
            return
        zone = self._moteur.zone
        echelle = cible.width() / zone.largeur

        def rect(gauche: float, haut: float, droite: float, bas: float) -> QRectF:
            return QRectF(cible.x() + gauche * echelle, cible.y() + haut * echelle, (droite - gauche) * echelle, (bas - haut) * echelle)

        def crayon(couleur: str, opacite: float) -> QPen:
            stylo = QPen(qcolor(couleur, opacite), Dimensions.REPERE_EPAISSEUR)
            stylo.setCosmetic(True)  # 1 px à l'écran, quel que soit le zoom
            return stylo

        peintre.save()
        peintre.setBrush(Qt.BrushStyle.NoBrush)
        if self._reperes["grille"]:
            peintre.setPen(crayon(CouleursApercu.GRILLE, Opacites.GRILLE))
            for part in (1 / 3, 1 / 2, 2 / 3):
                x, y = cible.x() + cible.width() * part, cible.y() + cible.height() * part
                peintre.drawLine(QPointF(x, cible.top()), QPointF(x, cible.bottom()))
                peintre.drawLine(QPointF(cible.left(), y), QPointF(cible.right(), y))
        if self._reperes["marge"] and (zone.marge_x > 0 or zone.marge_y > 0):
            peintre.setPen(crayon(CouleursApercu.MARGE_MAXIMUM, Opacites.REPERES))
            peintre.drawRect(rect(zone.marge_x, zone.marge_y, zone.largeur - zone.marge_x, zone.hauteur - zone.marge_y))
        securite = (zone.securite_gauche, zone.securite_haut, zone.securite_droite, zone.securite_bas)
        if self._reperes["zone"] and securite != (0, 0, zone.largeur, zone.hauteur):
            stylo = crayon(CouleursApercu.ZONE_DE_SECURITE, Opacites.REPERES)
            stylo.setDashPattern(list(Dimensions.REPERE_POINTILLES))
            peintre.setPen(stylo)
            peintre.drawRect(rect(*securite))
        peintre.restore()

    # --- Glisser le sous-titre verticalement (§7.4) ----------------------------------------------

    def _limites(self) -> tuple[float, float]:
        moteur = self._moteur
        return limites_du_reglage_fin(moteur.reglages, moteur.zone, moteur.metriques)

    def mousePressEvent(self, evenement) -> None:  # noqa: N802
        rect = self.rect_du_sous_titre()
        if (
            self.glissable
            and evenement.button() == Qt.MouseButton.LeftButton
            and rect is not None
            and rect.contains(evenement.position())
        ):
            depart = self._moteur.reglages.position.decalage_pct
            self._glisse = (evenement.position().y(), depart, depart)
            evenement.accept()
            return
        super().mousePressEvent(evenement)

    def mouseMoveEvent(self, evenement) -> None:  # noqa: N802
        if self._glisse is not None:
            y_depart, depart, _vise = self._glisse
            hauteur = self.rect_video().height()
            bas, haut = self._limites()
            vise = min(max(depart + (evenement.position().y() - y_depart) / hauteur * 100, bas), haut)
            self._glisse = (y_depart, depart, vise)
            self.update()
            self.glissement.emit(vise)
            return
        rect = self.rect_du_sous_titre()
        dessus = self.glissable and rect is not None and rect.contains(evenement.position())
        self.setCursor(Qt.CursorShape.SizeVerCursor if dessus else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(evenement)

    def mouseReleaseEvent(self, evenement) -> None:  # noqa: N802
        if self._glisse is not None:
            vise = self._glisse[2]
            self._glisse = None
            self.glissement_fini.emit(vise)
            self.update()
            return
        super().mouseReleaseEvent(evenement)


class ZoneApercu(QScrollArea):
    """La toile dans la page : sa hauteur suit le format de la vidéo (sans dépasser
    APERCU_HAUTEUR_MAX) ; à 100 %, la toile prend la taille réelle de la vidéo et la zone défile."""

    def __init__(self, toile: ToileApercu, parent: QWidget | None = None):
        super().__init__(parent)
        self.toile = toile
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(toile)
        politique = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        politique.setHeightForWidth(True)
        self.setSizePolicy(politique)
        self.definir_zoom(ZOOM_AJUSTE)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, largeur: int) -> int:  # noqa: N802
        largeur_video, hauteur_video = self.toile.taille_video()
        hauteur = largeur * hauteur_video / largeur_video
        return round(min(max(hauteur, Dimensions.APERCU_HAUTEUR_MIN), Dimensions.APERCU_HAUTEUR_MAX))

    def sizeHint(self) -> QSize:  # noqa: N802
        largeur = Dimensions.STUDIO_COLONNE_APERCU_LARGEUR
        return QSize(largeur, self.heightForWidth(largeur))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(Dimensions.APERCU_LARGEUR_MIN, Dimensions.APERCU_HAUTEUR_MIN)

    @property
    def zoom(self) -> str:
        return ZOOM_REEL if self.toile._zoom_reel else ZOOM_AJUSTE

    def definir_zoom(self, zoom: str) -> None:
        reel = zoom == ZOOM_REEL
        self.toile._zoom_reel = reel
        if reel:
            self.setWidgetResizable(False)
            largeur, hauteur = self.toile.taille_video()
            ratio = self.toile.devicePixelRatioF()
            self.toile.resize(round(largeur / ratio), round(hauteur / ratio))
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.centrer_sur_le_sous_titre()
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setWidgetResizable(True)
        self.toile.update()

    def actualiser_taille(self) -> None:
        """Le format de la vidéo a changé : nouvelle hauteur de la zone (et taille de la toile à 100 %)."""
        self.updateGeometry()
        if self.toile._zoom_reel:
            self.definir_zoom(ZOOM_REEL)

    def centrer_sur_le_sous_titre(self) -> None:
        """À 100 % : la partie visible montre le sous-titre (sinon le bas de l'écran, où il se place)."""
        rect = self.toile.rect_du_sous_titre()
        if rect is None:
            largeur, hauteur = self.toile.size().width(), self.toile.size().height()
            rect = QRectF(0, hauteur * 2 / 3, largeur, 0)
        centre = rect.center()
        self.ensureVisible(round(centre.x()), round(centre.y()), self.viewport().width() // 2, self.viewport().height() // 2)


class LecteurApercu(QObject):
    """Lecture de l'aperçu : la vidéo (avec son son, ou muette sous la voix d'une prise), ou le son
    seul d'une prise. Une seule source à la fois ; arreter() libère les fichiers (sinon Windows
    empêche de les déplacer)."""

    image = Signal(object)  # image de la vidéo à afficher (QVideoFrame)
    temps_change = Signal(float)  # temps des sous-titres affiché, en secondes
    position_change = Signal(int, int)  # (position, durée) de la vidéo ou du son, en millisecondes
    etat_change = Signal(bool)  # en lecture ?
    erreur = Signal(str)  # vidéo ou son illisible

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._actif = not os.environ.get(VARIABLE_SANS_AUDIO)  # tests : aucune lecture réelle
        self._source: tuple = ("", "", 0.0, True)
        self._video = None  # QMediaPlayer de la vidéo
        self._voix = None  # QMediaPlayer du son seul (prise), ou de la voix sous une vidéo muette
        self._sorties: list = []
        self._puits = None
        self._decalage = 0.0  # moment de la vidéo où commencent les sous-titres (vidéo d'aperçu)
        self._temps = 0.0
        self._duree_ms = 0
        self._boucle: tuple[float, float] | None = None
        self._repere_voix = (0, time.monotonic())  # dernière position connue du son seul
        self._minuteur = QTimer(self)
        self._minuteur.setInterval(INTERVALLE_SON_SEUL_MS)
        self._minuteur.timeout.connect(self._avancer_son_seul)

    # --- Source --------------------------------------------------------------------------------

    @property
    def video(self) -> str:
        return self._source[0]

    @property
    def temps(self) -> float:
        return self._temps

    def charger(self, video: str = "", audio: str = "", decalage: float = 0.0, son_de_la_video: bool = True) -> None:
        """Nouvelle source (rien ne change si c'est la même). `video` : chemin d'une vidéo ;
        `audio` : piste son des sous-titres (prise) ; `decalage` : moment de la vidéo où la voix
        commence (vidéo choisie seulement pour l'aperçu)."""
        source = (video or "", audio or "", float(decalage), bool(son_de_la_video))
        if source == self._source and (self._video is not None or self._voix is not None or not self._actif):
            return
        self.arreter()
        self._source = source
        self._decalage = float(decalage)
        if not self._actif or not (video or audio):
            return
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
        except ImportError:
            journal.warning("Qt Multimedia indisponible : pas de lecture dans l'aperçu", exc_info=True)
            return
        if video:
            self._video = QMediaPlayer(self)
            self._puits = QVideoSink(self)
            self._video.setVideoSink(self._puits)
            self._puits.videoFrameChanged.connect(self._image_recue)
            if son_de_la_video or not audio:
                sortie = QAudioOutput(self)
                self._sorties.append(sortie)
                self._video.setAudioOutput(sortie)
            self._brancher(self._video)
            self._video.setSource(QUrl.fromLocalFile(video))
            self._video.pause()  # première image affichée dès le chargement
        if audio and (not video or not son_de_la_video):
            self._voix = QMediaPlayer(self)
            sortie = QAudioOutput(self)
            self._sorties.append(sortie)
            self._voix.setAudioOutput(sortie)
            if video:  # voix sous la vidéo muette : la vidéo donne le temps
                self._voix.errorOccurred.connect(lambda _code, message: self.erreur.emit(message or "son illisible"))
            else:
                self._brancher(self._voix)
                self._voix.positionChanged.connect(self._position_son_seul)
            self._voix.setSource(QUrl.fromLocalFile(audio))

    def _brancher(self, lecteur) -> None:
        """Signaux du lecteur qui donne le temps (la vidéo, sinon le son seul)."""
        lecteur.playbackStateChanged.connect(lambda _etat: self._etat_lecture())
        lecteur.durationChanged.connect(self._duree_lue)
        lecteur.errorOccurred.connect(lambda _code, message: self.erreur.emit(message or "fichier illisible"))

    def arreter(self) -> None:
        """Arrête la lecture et libère les fichiers."""
        self._minuteur.stop()
        for lecteur in (self._video, self._voix):
            if lecteur is not None:
                lecteur.blockSignals(True)
                lecteur.stop()
                lecteur.setSource(QUrl())
                lecteur.deleteLater()
        for objet in (self._puits, *self._sorties):
            if objet is not None:
                objet.deleteLater()
        self._video = self._voix = self._puits = None
        self._sorties = []
        self._duree_ms = 0
        self._source = ("", "", 0.0, True)
        self.image.emit(None)
        self.etat_change.emit(False)

    # --- Lecture -------------------------------------------------------------------------------

    def _maitre(self):
        return self._video if self._video is not None else self._voix

    def en_lecture(self) -> bool:
        maitre = self._maitre()
        if maitre is None:
            return False
        from PySide6.QtMultimedia import QMediaPlayer

        return maitre.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def basculer(self) -> None:
        """Lecture ou pause (bouton ▶, barre Espace)."""
        maitre = self._maitre()
        if maitre is None:
            return
        if self.en_lecture():
            maitre.pause()
            if self._voix is not None and self._video is not None:
                self._voix.pause()
            return
        maitre.play()
        if self._voix is not None and self._video is None:
            self._repere_voix = (self._voix.position(), time.monotonic())
            self._minuteur.start()

    def definir_boucle(self, debut: float | None, fin: float | None = None) -> None:
        """Boucle sur un sous-titre (de `debut` à `fin`, en secondes), ou plus de boucle (None)."""
        self._boucle = (debut, fin) if debut is not None and fin is not None and fin > debut else None

    def aller_a(self, temps: float) -> None:
        """Place la lecture à ce temps des sous-titres (en secondes)."""
        self._temps = max(0.0, temps)
        if self._video is not None:
            self._video.setPosition(round((self._temps + self._decalage) * 1000))
            if self._voix is not None:
                self._voix.setPosition(round(self._temps * 1000))
        elif self._voix is not None:
            position = round(self._temps * 1000)
            self._voix.setPosition(position)
            self._repere_voix = (position, time.monotonic())
        self.temps_change.emit(self._temps)

    def aller_a_position(self, position_ms: int) -> None:
        """Place la lecture à cette position de la vidéo (ou du son), en millisecondes (barre de position)."""
        decalage = self._decalage if self._video is not None else 0.0
        self.aller_a(position_ms / 1000 - decalage)

    # --- Temps ---------------------------------------------------------------------------------

    def _duree_lue(self, duree_ms: int) -> None:
        self._duree_ms = max(0, int(duree_ms))
        maitre = self._maitre()
        self.position_change.emit(maitre.position() if maitre is not None else 0, self._duree_ms)

    def _etat_lecture(self) -> None:
        en_lecture = self.en_lecture()
        if not en_lecture:
            self._minuteur.stop()
        self.etat_change.emit(en_lecture)

    def _image_recue(self, image) -> None:
        """Nouvelle image de la vidéo : c'est elle qui donne le temps des sous-titres."""
        if self._video is None:
            return
        debut = image.startTime() if image is not None and image.isValid() else -1
        position_ms = debut / 1000 if debut >= 0 else self._video.position()
        self.image.emit(image if image is not None and image.isValid() else None)
        self._publier(position_ms / 1000 - self._decalage, round(position_ms))
        self._caler_la_voix()

    def _caler_la_voix(self) -> None:
        """Voix d'une prise sous une vidéo muette : elle suit la vidéo (recalée si elle s'en écarte)."""
        if self._voix is None or self._video is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer

        voix_en_lecture = self._voix.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        if not self.en_lecture() or self._temps < 0:
            if voix_en_lecture:
                self._voix.pause()
            return
        attendu = round(self._temps * 1000)
        if not voix_en_lecture:
            self._voix.setPosition(attendu)
            self._voix.play()
        elif abs(self._voix.position() - attendu) > ECART_VOIX_TOLERE_S * 1000:
            self._voix.setPosition(attendu)

    def _position_son_seul(self, position_ms: int) -> None:
        self._repere_voix = (position_ms, time.monotonic())
        if not self.en_lecture():
            self._publier(position_ms / 1000, position_ms)

    def _avancer_son_seul(self) -> None:
        """Son seul : la position connue avance avec le temps écoulé depuis (Qt ne la donne que
        toutes les 50 ms environ)."""
        if self._voix is None or self._video is not None:
            return
        position, instant = self._repere_voix
        if self.en_lecture():
            position += (time.monotonic() - instant) * 1000
        if self._duree_ms:
            position = min(position, self._duree_ms)
        self._publier(position / 1000, round(position))

    def _publier(self, temps: float, position_ms: int) -> None:
        self._temps = temps
        self.temps_change.emit(temps)
        self.position_change.emit(max(0, position_ms), self._duree_ms)
        if self._boucle is not None and self.en_lecture() and temps >= self._boucle[1]:
            self.aller_a(self._boucle[0])
