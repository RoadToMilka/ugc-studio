"""Réglages du studio des sous-titres (V2, lot 3 ; cahier des charges §7.9) : quatre onglets.

- Texte : taille, casse, ponctuation (police, couleurs, contour et fond : lot 4).
- Position : haut, centre ou bas, réglage fin, alignement ; avancé : largeur maximale des lignes.
- Découpage : caractères, mots et lignes au plus, durée minimale, coupure sur la ponctuation,
  hésitations masquées.
- Écran : format (suivi de la vidéo quand il y en a une, sinon au choix, dont personnalisé), zone de
  sécurité, marge maximum ; pour un projet sans vidéo, la vidéo choisie seulement pour l'aperçu.

Ce panneau ne fait que montrer et lire les réglages : la page (atelier.py) les applique.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ....sous_titres import (
    COTE_MAX,
    COTE_MIN,
    FORMAT_AUTO,
    FORMAT_PAR_DEFAUT,
    FORMAT_PERSONNALISE,
    LIMITES,
    NOMS_FORMATS,
    PLATEFORMES,
    ReglagesSousTitres,
    cote_pair,
)
from ....style_sous_titres import ALIGNEMENTS, CASSES, POSITIONS, Position, StyleTexte, VideoApercu
from ...composants.choix import ChoixEnBoutons
from ...composants.choix_voix import choisir
from ...composants.elements import (
    bouton,
    case_a_cocher,
    champ_decimal,
    champ_entier,
    conteneur_vertical,
    glissiere,
    info,
    libelle,
    liste_deroulante,
)
from ...composants.onglets import Onglets
from ...composants.section_repliable import SectionRepliable
from ...theme import Espacements

ONGLET_TEXTE, ONGLET_POSITION, ONGLET_DECOUPAGE, ONGLET_ECRAN = range(4)
PAS_REGLAGE_FIN = 10  # la glissière du réglage fin compte en dixièmes de % de la hauteur


def nombre_lisible(valeur: float, decimales: int = 1) -> str:
    """2.5 → « 2,5 » ; 3.0 → « 3 »."""
    texte = f"{valeur:.{decimales}f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",").replace("-", "−") or "0"


def grille(lignes, etirees: tuple[int, ...] = ()) -> QGridLayout:
    """Libellés à gauche, champs à droite, à leur largeur naturelle (sauf les lignes `etirees`, qui
    prennent toute la largeur de la colonne : une glissière, par exemple)."""
    disposition = QGridLayout()
    disposition.setHorizontalSpacing(Espacements.M)
    disposition.setVerticalSpacing(Espacements.S)
    for rang, (texte, element) in enumerate(lignes):
        disposition.addWidget(libelle(texte, "legende", retour_a_la_ligne=False), rang, 0)
        alignement = Qt.AlignmentFlag(0) if rang in etirees else Qt.AlignmentFlag.AlignLeft
        if isinstance(element, QWidget):
            disposition.addWidget(element, rang, 1, alignement)
        else:
            disposition.addLayout(element, rang, 1, alignement)
    disposition.setColumnStretch(1, 1)
    return disposition


class PanneauReglages(QWidget):
    change = Signal()  # un réglage qui peut changer le découpage (la page le vérifie, puis l'applique)
    position_change = Signal()  # position verticale ou réglage fin : seul l'aperçu change
    masquer_change = Signal(bool)  # « Masquer les hésitations » (réglage partagé avec la transcription)
    choisir_video_demande = Signal()  # « Choisir une vidéo… » (vidéo d'aperçu)
    retirer_video_demande = Signal()
    video_apercu_change = Signal()  # décalage ou son de la vidéo d'aperçu

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        self.onglets = Onglets()
        self.onglets.addTab(self._onglet_texte(), "Texte")
        self.onglets.addTab(self._onglet_position(), "Position")
        self.onglets.addTab(self._onglet_decoupage(), "Découpage")
        self.onglets.addTab(self._onglet_ecran(), "Écran")
        disposition.addWidget(self.onglets)
        self._apercu = VideoApercu()
        self._resolution_imposee: tuple[int, int] | None | bool = False  # False : liste des formats pas encore remplie

    # --- Onglets -------------------------------------------------------------------------------

    def _onglet(self) -> tuple[QWidget, QVBoxLayout]:
        page, contenu = conteneur_vertical(Espacements.M)
        contenu.setContentsMargins(0, Espacements.L, 0, 0)
        return page, contenu

    def _onglet_texte(self) -> QWidget:
        page, contenu = self._onglet()
        self.taille = champ_decimal(*LIMITES["taille_pct"], 0.1, 1, " %", "Taille du texte, en % de la hauteur de la vidéo")
        self.taille_px = libelle("", "legende", retour_a_la_ligne=False)
        ligne_taille = QHBoxLayout()
        ligne_taille.setSpacing(Espacements.S)
        ligne_taille.addWidget(self.taille)
        ligne_taille.addWidget(self.taille_px)
        self.casse = liste_deroulante("Affichage seulement : le texte des mots ne change pas")
        for code, nom in CASSES.items():
            self.casse.addItem(nom, code)
        contenu.addLayout(grille((("Taille du texte", ligne_taille), ("Casse", self.casse))))
        zone, self.ponctuation = case_a_cocher("Afficher la ponctuation")
        contenu.addWidget(zone)
        contenu.addWidget(info("Police Inter SemiBold, texte blanc avec une ombre légère : la même apparence qu'en V1."))
        contenu.addStretch(1)
        self.taille.valueChanged.connect(lambda _valeur: self.change.emit())
        self.casse.currentIndexChanged.connect(lambda _index: self.change.emit())
        self.ponctuation.toggled.connect(lambda _coche: self.change.emit())
        return page

    def _onglet_position(self) -> QWidget:
        page, contenu = self._onglet()
        self.verticale = ChoixEnBoutons(POSITIONS, "Point fixe du sous-titre : son haut, son milieu ou son bas")
        self.reglage_fin = glissiere()
        self.reglage_fin.setToolTip("Décale le sous-titre vers le haut ou vers le bas (en % de la hauteur)")
        self.valeur_reglage_fin = libelle("0 %", "legende", retour_a_la_ligne=False)
        self.bouton_reglage_fin = bouton("", variante="icone", nom_icone="rotate-ccw", action=lambda: self.reglage_fin.setValue(0))
        self.bouton_reglage_fin.setToolTip("Revenir à 0 %")
        ligne_fin = QHBoxLayout()
        ligne_fin.setSpacing(Espacements.S)
        ligne_fin.addWidget(self.reglage_fin, 1)
        ligne_fin.addWidget(self.valeur_reglage_fin)
        ligne_fin.addWidget(self.bouton_reglage_fin)
        self.alignement = ChoixEnBoutons(ALIGNEMENTS, "Alignement des lignes")
        # La glissière prend toute la largeur de sa colonne (les autres champs gardent la leur).
        contenu.addLayout(
            grille((("Position", self.verticale), ("Réglage fin", ligne_fin), ("Alignement", self.alignement)), etirees=(1,))
        )
        contenu.addWidget(
            info("« Haut » et « Bas » : juste à l'intérieur de la zone de sécurité de la plateforme. Tu peux aussi glisser le sous-titre dans l'aperçu.")
        )
        self.avances_position = SectionRepliable("Réglages avancés")
        self.largeur_lignes = champ_decimal(*LIMITES["largeur_lignes_pct"], 1, 0, " %", "Largeur maximale des lignes")
        self.avances_position.contenu.addLayout(grille((("Largeur des lignes", self.largeur_lignes),)))
        self.avances_position.contenu.addWidget(
            info("En % de la largeur utile (zone de sécurité, ou jusqu'à la marge maximum) : pour un bloc plus étroit.")
        )
        contenu.addWidget(self.avances_position)
        contenu.addStretch(1)
        self.verticale.change.connect(lambda _valeur: self.position_change.emit())
        self.reglage_fin.valueChanged.connect(self._reglage_fin_bouge)
        self.alignement.change.connect(lambda _valeur: self.change.emit())
        self.largeur_lignes.valueChanged.connect(lambda _valeur: self.change.emit())
        return page

    def _onglet_decoupage(self) -> QWidget:
        page, contenu = self._onglet()
        self.caracteres = champ_entier(*LIMITES["caracteres_max"], info="Nombre maximum de caractères par sous-titre, espaces comprises")
        self.mots_max = champ_entier(*LIMITES["mots_max"], info="Nombre maximum de mots par sous-titre")
        self.lignes = champ_entier(*LIMITES["lignes_max"], info="Nombre maximum de lignes (1 ou 2) : jamais dépassé")
        self.duree_min = champ_decimal(*LIMITES["duree_min_s"], 0.1, 1, " s", "Durée minimale d'affichage d'un sous-titre")
        contenu.addLayout(
            grille(
                (
                    ("Caractères au plus", self.caracteres),
                    ("Mots au plus", self.mots_max),
                    ("Lignes au plus", self.lignes),
                    ("Durée minimale", self.duree_min),
                )
            )
        )
        zone, self.couper_ponctuation = case_a_cocher(
            "Couper de préférence après la ponctuation", "Une fin de phrase termine alors toujours le sous-titre."
        )
        contenu.addWidget(zone)
        self.zone_masquer, self.masquer = case_a_cocher(
            "Masquer les hésitations", "« euh », « hum »… (même réglage que dans le module Transcription)."
        )
        contenu.addWidget(self.zone_masquer)
        contenu.addStretch(1)
        for champ in (self.caracteres, self.mots_max, self.lignes, self.duree_min):
            champ.valueChanged.connect(lambda _valeur: self.change.emit())
        self.couper_ponctuation.toggled.connect(lambda _coche: self.change.emit())
        self.masquer.toggled.connect(lambda coche: self.masquer_change.emit(coche))
        return page

    def _onglet_ecran(self) -> QWidget:
        page, contenu = self._onglet()
        self.format = liste_deroulante("Format de la vidéo (les tailles sont proportionnelles à sa hauteur)")
        self.largeur_perso = champ_entier(COTE_MIN, COTE_MAX, " px", "Largeur de la vidéo (nombre pair)")
        self.hauteur_perso = champ_entier(COTE_MIN, COTE_MAX, " px", "Hauteur de la vidéo (nombre pair)")
        for champ in (self.largeur_perso, self.hauteur_perso):
            champ.setSingleStep(2)
        self.zone_perso = QWidget()
        ligne_perso = QHBoxLayout(self.zone_perso)
        ligne_perso.setContentsMargins(0, 0, 0, 0)
        ligne_perso.setSpacing(Espacements.S)
        ligne_perso.addWidget(self.largeur_perso)
        ligne_perso.addWidget(libelle("×", "legende", retour_a_la_ligne=False))
        ligne_perso.addWidget(self.hauteur_perso)
        self.plateforme = liste_deroulante("Zone de sécurité : les bords que l'interface de la plateforme recouvre")
        for plateforme in PLATEFORMES:
            self.plateforme.addItem(plateforme.nom, plateforme.identifiant)
            if plateforme.source:
                self.plateforme.setItemData(self.plateforme.count() - 1, f"Source : {plateforme.source}", Qt.ItemDataRole.ToolTipRole)
        self.marge = champ_decimal(*LIMITES["marge_max_pct"], 0.5, 1, " %", "Marge maximum de chaque bord : le texte ne la dépasse jamais")
        self.grille_ecran = grille(
            (
                ("Format", self.format),
                ("Taille", self.zone_perso),
                ("Zone de sécurité", self.plateforme),
                ("Marge maximum", self.marge),
            )
        )
        contenu.addLayout(self.grille_ecran)
        self.info_format = info()
        contenu.addWidget(self.info_format)
        self.infos_ecran = info()
        contenu.addWidget(self.infos_ecran)
        contenu.addWidget(self._zone_video_apercu())
        contenu.addStretch(1)
        self.format.currentIndexChanged.connect(lambda _index: self._format_change())
        for element in (self.largeur_perso, self.hauteur_perso, self.marge):
            element.valueChanged.connect(lambda _valeur: self.change.emit())
        self.plateforme.currentIndexChanged.connect(lambda _index: self.change.emit())
        return page

    def _zone_video_apercu(self) -> QWidget:
        """Projet sans vidéo (prise de voix) : une vidéo choisie seulement pour l'aperçu (§7.7)."""
        self.zone_video, contenu = conteneur_vertical(Espacements.S)
        contenu.setContentsMargins(0, Espacements.S, 0, 0)
        contenu.addWidget(libelle("Vidéo d'aperçu", "intitule"))
        contenu.addWidget(
            info(
                "Par exemple ton montage exporté de Premiere Pro : tu vois tes sous-titres sur la vraie image. "
                "Elle n'est pas copiée dans le projet, et elle impose son format."
            )
        )
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.bouton_choisir_video = bouton(
            "Choisir une vidéo…", variante="contour", nom_icone="film", action=lambda: self.choisir_video_demande.emit()
        )
        ligne.addWidget(self.bouton_choisir_video)
        self.bouton_retirer_video = bouton(
            "Retirer", variante="contour", nom_icone="trash", action=lambda: self.retirer_video_demande.emit()
        )
        ligne.addWidget(self.bouton_retirer_video)
        ligne.addStretch(1)
        contenu.addLayout(ligne)
        self.nom_video = libelle("", "secondaire")
        contenu.addWidget(self.nom_video)
        self.decalage_video = champ_decimal(0.0, 3600.0, 0.1, 1, " s", "Moment de la vidéo où la voix commence")
        self.ligne_decalage = QWidget()
        disposition = QHBoxLayout(self.ligne_decalage)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("La voix commence à", "legende", retour_a_la_ligne=False))
        disposition.addWidget(self.decalage_video)
        disposition.addStretch(1)
        contenu.addWidget(self.ligne_decalage)
        self.zone_son_video, self.son_video = case_a_cocher(
            "Son de la vidéo", "Sinon : la voix de la prise, sous la vidéo muette."
        )
        contenu.addWidget(self.zone_son_video)
        self.decalage_video.valueChanged.connect(lambda _valeur: self.video_apercu_change.emit())
        self.son_video.toggled.connect(lambda _coche: self.video_apercu_change.emit())
        return self.zone_video

    # --- Réglage fin ---------------------------------------------------------------------------

    def _reglage_fin_bouge(self, valeur: int) -> None:
        pourcentage = valeur / PAS_REGLAGE_FIN
        signe = "+" if pourcentage > 0 else ""
        self.valeur_reglage_fin.setText(f"{signe}{nombre_lisible(pourcentage)} %")
        self.bouton_reglage_fin.setEnabled(valeur != 0)
        self.position_change.emit()

    def definir_limites_reglage_fin(self, bas: float, haut: float) -> None:
        """Le plus grand sous-titre possible reste entre les marges maximum (mise_en_page.py)."""
        self.reglage_fin.blockSignals(True)
        self.reglage_fin.setRange(round(bas * PAS_REGLAGE_FIN), round(haut * PAS_REGLAGE_FIN))
        self.reglage_fin.blockSignals(False)
        self._reglage_fin_texte()

    def montrer_reglage_fin(self, pourcentage: float) -> None:
        """Valeur montrée pendant qu'on glisse le sous-titre dans l'aperçu (sans rien appliquer)."""
        self.reglage_fin.blockSignals(True)
        self.reglage_fin.setValue(round(pourcentage * PAS_REGLAGE_FIN))
        self.reglage_fin.blockSignals(False)
        signe = "+" if pourcentage > 0 else ""
        self.valeur_reglage_fin.setText(f"{signe}{nombre_lisible(pourcentage)} %")

    # --- Format --------------------------------------------------------------------------------

    def _format_change(self) -> None:
        self.zone_perso.setVisible(self.format.currentData() == FORMAT_PERSONNALISE)
        self.change.emit()

    # --- Lecture et écriture des réglages --------------------------------------------------------

    def charger(
        self,
        reglages: ReglagesSousTitres,
        resolution_imposee: tuple[int, int] | None,
        masquer: bool,
        transcription: bool,
        video_du_projet: bool,
    ) -> None:
        """Montre les réglages du projet. `resolution_imposee` : une vidéo impose son format ;
        `video_du_projet` : le projet a sa propre vidéo (pas de vidéo d'aperçu à choisir)."""
        elements = (
            self.taille, self.casse, self.ponctuation, self.verticale, self.reglage_fin, self.alignement,
            self.largeur_lignes, self.caracteres, self.mots_max, self.lignes, self.duree_min, self.couper_ponctuation,
            self.masquer, self.format, self.largeur_perso, self.hauteur_perso, self.plateforme, self.marge,
            self.decalage_video, self.son_video,
        )
        for element in elements:
            element.blockSignals(True)
        self.taille.setValue(reglages.texte.taille_pct)
        choisir(self.casse, reglages.texte.casse)
        self.ponctuation.setChecked(reglages.texte.ponctuation)
        self.verticale.definir(reglages.position.verticale)
        self.alignement.definir(reglages.position.alignement)
        self.largeur_lignes.setValue(reglages.position.largeur_lignes_pct)
        # Toute la plage d'abord : les vraies limites (selon le format et la taille du texte) viennent
        # ensuite du moteur de dessin (definir_limites_reglage_fin).
        etendue = round(Position.LIMITES["decalage_pct"][1] * PAS_REGLAGE_FIN)
        self.reglage_fin.setRange(-etendue, etendue)
        self.reglage_fin.setValue(round(reglages.position.decalage_pct * PAS_REGLAGE_FIN))
        self.caracteres.setValue(reglages.caracteres_max)
        self.mots_max.setValue(reglages.mots_max)
        self.lignes.setValue(reglages.lignes_max)
        self.duree_min.setValue(reglages.duree_min_s)
        self.couper_ponctuation.setChecked(reglages.couper_sur_ponctuation)
        self.masquer.setChecked(masquer)
        self.zone_masquer.setEnabled(transcription)
        self._remplir_formats(resolution_imposee)
        choisir(self.format, FORMAT_AUTO if resolution_imposee else (FORMAT_PAR_DEFAUT if reglages.format == FORMAT_AUTO else reglages.format))
        self.largeur_perso.setValue(reglages.largeur_perso)
        self.hauteur_perso.setValue(reglages.hauteur_perso)
        self.zone_perso.setVisible(resolution_imposee is None and reglages.format == FORMAT_PERSONNALISE)
        choisir(self.plateforme, reglages.plateforme)
        self.marge.setValue(reglages.marge_max_pct)
        self._apercu = reglages.apercu
        self.decalage_video.setValue(reglages.apercu.decalage_s)
        self.son_video.setChecked(reglages.apercu.son_de_la_video)
        for element in elements:
            element.blockSignals(False)
        self._reglage_fin_texte()
        self._montrer_video_apercu(video_du_projet)

    def _reglage_fin_texte(self) -> None:
        valeur = self.reglage_fin.value()
        signe = "+" if valeur > 0 else ""
        self.valeur_reglage_fin.setText(f"{signe}{nombre_lisible(valeur / PAS_REGLAGE_FIN)} %")
        self.bouton_reglage_fin.setEnabled(valeur != 0)

    def _remplir_formats(self, resolution_imposee: tuple[int, int] | None) -> None:
        if resolution_imposee == self._resolution_imposee:
            return  # même liste : elle n'est pas refaite (elle peut être en train de changer de choix)
        self._resolution_imposee = resolution_imposee
        self.format.clear()
        if resolution_imposee:
            largeur, hauteur = resolution_imposee
            self.format.addItem(f"Celui de la vidéo ({largeur} × {hauteur})", FORMAT_AUTO)
            self.info_format.setText("Le format suit la vidéo : l'overlay de la V3 doit avoir sa taille exacte.")
        else:
            for identifiant, nom in NOMS_FORMATS.items():
                self.format.addItem(nom, identifiant)
            self.info_format.setText("")
        self.format.setEnabled(resolution_imposee is None)
        self.info_format.setVisible(resolution_imposee is not None)

    def _montrer_video_apercu(self, video_du_projet: bool) -> None:
        self.zone_video.setVisible(not video_du_projet)
        choisie = bool(self._apercu.chemin)
        self.bouton_retirer_video.setVisible(choisie)
        self.bouton_choisir_video.setText("Changer de vidéo…" if choisie else "Choisir une vidéo…")
        self.nom_video.setVisible(choisie)
        if choisie:
            resolution = self._apercu.resolution
            details = f"  ·  {resolution[0]} × {resolution[1]}" if resolution else ""
            self.nom_video.setText(f"{Path(self._apercu.chemin).name}{details}")
        self.ligne_decalage.setVisible(choisie)
        self.zone_son_video.setVisible(choisie)

    def reglages(self, base: ReglagesSousTitres) -> ReglagesSousTitres:
        """Réglages tels que choisis dans le panneau (la vidéo d'aperçu, elle, vient de `base`)."""
        format_choisi = self.format.currentData() if self.format.isEnabled() else base.format
        return ReglagesSousTitres(
            caracteres_max=self.caracteres.value(),
            mots_max=self.mots_max.value(),
            lignes_max=self.lignes.value(),
            couper_sur_ponctuation=self.couper_ponctuation.isChecked(),
            duree_min_s=round(self.duree_min.value(), 2),
            texte=StyleTexte(
                police=base.texte.police,
                graisse=base.texte.graisse,
                taille_pct=round(self.taille.value(), 2),
                casse=self.casse.currentData(),
                ponctuation=self.ponctuation.isChecked(),
                couleur=base.texte.couleur,
                ombre=base.texte.ombre,
            ),
            position=Position(
                self.verticale.valeur(),
                round(self.reglage_fin.value() / PAS_REGLAGE_FIN, 2),
                self.alignement.valeur(),
                round(self.largeur_lignes.value(), 1),
            ),
            format=format_choisi or base.format,
            largeur_perso=cote_pair(self.largeur_perso.value()),
            hauteur_perso=cote_pair(self.hauteur_perso.value()),
            plateforme=self.plateforme.currentData(),
            marge_max_pct=round(self.marge.value(), 2),
            apercu=base.apercu,
        )

    def decalage_et_son(self) -> tuple[float, bool]:
        return round(self.decalage_video.value(), 2), self.son_video.isChecked()
