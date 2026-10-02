"""Réglages du studio des sous-titres (V2, lot 3 ; cahier des charges §7.9) : un préréglage, puis
six onglets.

- Préréglage (lot 7) : la liste des préréglages (choisir l'un l'applique), « (modifié) » quand le style
  du projet s'en écarte, « Enregistrer… » (nouveau préréglage) et le menu ⋯ (mettre à jour, revenir,
  gérer les préréglages).

- Texte (onglet_texte.py) : police, graisse, taille, casse, ponctuation, remplissage, contour,
  ombre, lueur, fond, espaces (lot 4).
- Mots (onglet_mots.py) : états des mots (à venir, actif, déjà dits, accentués), raccourcis,
  avance de l'allumage (lot 5).
- Animations (onglet_animations.py) : le mot qui devient actif, son retour à « déjà dit »,
  l'apparition et la disparition du sous-titre (lot 6).
- Position : haut, centre ou bas, réglage fin, alignement ; avancé : largeur maximale des lignes.
- Découpage : caractères, mots et lignes au plus, durée minimale, coupure sur la ponctuation ;
  hésitations masquées (réglage partagé avec la transcription, hors du préréglage).

V3.1 : la référence est le préréglage du projet tel qu'il est enregistré (sans lui, le style de
départ) ; dans chaque onglet (sauf Écran, qui dépend de la vidéo), un réglage qui s'en écarte a son
nom en mauve, et le ↺ de son groupe apparaît à côté du titre (definir_reference). Position et
Découpage forment chacun un groupe ; le ↺ « Revenir à 0 % » du réglage fin a disparu : celui du
groupe Position remet la position du préréglage, réglage fin compris.
- Écran : format (suivi de la vidéo quand il y en a une, sinon au choix, dont personnalisé), zone de
  sécurité, marge maximum ; pour un projet sans vidéo, la vidéo choisie seulement pour l'aperçu.

Ce panneau ne fait que montrer et lire les réglages : la page (atelier.py) les applique.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout, QWidget

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
from ....prereglages import Prereglage
from ....style_sous_titres import ALIGNEMENTS, POSITIONS, Position, VideoApercu
from ...composants.choix import ChoixEnBoutons
from ...composants.choix_voix import choisir
from ...composants.elements import (
    ChampNomme,
    bouton,
    case_a_cocher,
    champ_decimal,
    champ_entier,
    conteneur_vertical,
    glissiere,
    info,
    intitule,
    libelle,
    liste_deroulante,
)
from ...composants.onglets import Onglets
from ...composants.section_repliable import SectionRepliable
from ...icones import icone_menu
from ...theme import Espacements
from .onglet_animations import OngletAnimations
from .onglet_mots import OngletMots
from .onglet_texte import RETABLIR, OngletTexte
from .reglages_communs import grille, marque_de, marquer, meme_valeur, nombre_lisible

ONGLET_TEXTE, ONGLET_MOTS, ONGLET_ANIMATIONS, ONGLET_POSITION, ONGLET_DECOUPAGE, ONGLET_ECRAN = range(6)
PAS_REGLAGE_FIN = 10  # la glissière du réglage fin compte en dixièmes de % de la hauteur
SANS_PREREGLAGE = ""  # choix « Aucun préréglage » de la liste
MODIFIE = " (modifié)"


class PanneauReglages(QWidget):
    change = Signal()  # un réglage qui peut changer le découpage (la page le vérifie, puis l'applique)
    position_change = Signal()  # position verticale ou réglage fin : seul l'aperçu change
    masquer_change = Signal(bool)  # « Masquer les hésitations » (réglage partagé avec la transcription)
    choisir_video_demande = Signal()  # « Choisir une vidéo… » (vidéo d'aperçu)
    retirer_video_demande = Signal()
    video_apercu_change = Signal()  # décalage ou son de la vidéo d'aperçu
    # Préréglages (lot 7) : la page s'en charge (bibliothèque, question avant de défaire un ajustement).
    prereglage_choisi = Signal(str)  # identifiant du préréglage choisi dans la liste
    enregistrer_prereglage_demande = Signal()  # « Enregistrer… » : nouveau préréglage avec ce style
    mettre_a_jour_prereglage_demande = Signal()
    revenir_au_prereglage_demande = Signal()
    gerer_prereglages_demande = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        # « Préréglage » au-dessus de sa liste (V3.1), comme le nom de chaque champ.
        disposition.addWidget(ChampNomme("Préréglage", self._ligne_prereglage(), etire=True))
        self.statut_prereglage = libelle("", "secondaire")  # « Préréglage appliqué »… (vide : caché)
        self.statut_prereglage.hide()
        disposition.addSpacing(Espacements.S)
        disposition.addWidget(self.statut_prereglage)
        disposition.addSpacing(Espacements.S)
        self.onglets = Onglets(hauteur_selon_l_onglet=True, en_flux=True)  # six onglets : sur deux lignes si besoin
        self.texte = OngletTexte()
        self.texte.change.connect(self.change.emit)
        self.onglets.addTab(self.texte, "Texte")
        self.mots = OngletMots()
        self.mots.change.connect(self.change.emit)
        self.onglets.addTab(self.mots, "Mots")
        self.animations = OngletAnimations()
        self.animations.change.connect(self.change.emit)
        self.onglets.addTab(self.animations, "Animations")
        self.onglets.addTab(self._onglet_position(), "Position")
        self.onglets.addTab(self._onglet_decoupage(), "Découpage")
        self.onglets.addTab(self._onglet_ecran(), "Écran")
        disposition.addWidget(self.onglets)
        self._apercu = VideoApercu()
        self._resolution_imposee: tuple[int, int] | None | bool = False  # False : liste des formats pas encore remplie
        self._reference: ReglagesSousTitres | None = None  # le préréglage du projet (V3.1), donné par la page

    # --- Préréglage (lot 7) ----------------------------------------------------------------------

    def _ligne_prereglage(self) -> QHBoxLayout:
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.prereglage = liste_deroulante(
            "Un style complet (onglets Texte, Mots, Animations, Position et Découpage) : en choisir un l'applique"
        )
        self.prereglage.activated.connect(lambda _index: self._prereglage_active())
        ligne.addWidget(self.prereglage, 1)
        self.bouton_enregistrer_prereglage = bouton(
            "Enregistrer…", variante="contour", nom_icone="save", action=lambda: self.enregistrer_prereglage_demande.emit()
        )
        self.bouton_enregistrer_prereglage.setToolTip("Enregistrer ce style comme nouveau préréglage")
        ligne.addWidget(self.bouton_enregistrer_prereglage)
        self.bouton_plus_prereglage = bouton("", variante="icone", nom_icone="ellipsis")
        self.bouton_plus_prereglage.setToolTip("Plus d'actions sur les préréglages")
        menu = QMenu(self.bouton_plus_prereglage)
        self.action_mettre_a_jour = menu.addAction(icone_menu("save"), "Mettre à jour ce préréglage")
        self.action_mettre_a_jour.triggered.connect(lambda: self.mettre_a_jour_prereglage_demande.emit())
        self.action_revenir = menu.addAction(icone_menu("rotate-ccw"), "Revenir au préréglage")
        self.action_revenir.triggered.connect(lambda: self.revenir_au_prereglage_demande.emit())
        menu.addSeparator()
        self.action_gerer = menu.addAction(icone_menu("library"), "Gérer les préréglages…")
        self.action_gerer.triggered.connect(lambda: self.gerer_prereglages_demande.emit())
        self.bouton_plus_prereglage.setMenu(menu)
        ligne.addWidget(self.bouton_plus_prereglage)
        return ligne

    def definir_prereglages(self, prereglages: list[Prereglage], origine: str, nom_origine: str, modifie: bool) -> None:
        """La liste des préréglages ; celui du projet (`origine`) est choisi, suivi de « (modifié) »
        quand le style du projet s'en écarte. Sans préréglage (ou s'il a été supprimé depuis) : « Aucun
        préréglage » (ou son ancien nom)."""
        self.prereglage.blockSignals(True)
        self.prereglage.clear()
        existe = any(p.identifiant == origine for p in prereglages)
        if not existe:
            texte = f"{nom_origine} (supprimé)" if origine and nom_origine else "Aucun préréglage"
            self.prereglage.addItem(texte, SANS_PREREGLAGE)
        for prereglage in prereglages:
            texte = prereglage.nom + (MODIFIE if prereglage.identifiant == origine and modifie else "")
            self.prereglage.addItem(texte, prereglage.identifiant)
        choisir(self.prereglage, origine if existe else SANS_PREREGLAGE)
        self.prereglage.blockSignals(False)
        self.action_mettre_a_jour.setEnabled(existe and modifie)
        self.action_revenir.setEnabled(existe and modifie)
        nom = next((p.nom for p in prereglages if p.identifiant == origine), "")
        self.action_mettre_a_jour.setText(f"Mettre à jour « {nom} » avec ce style" if existe else "Mettre à jour ce préréglage")
        self.action_revenir.setText(f"Revenir à « {nom} »" if existe else "Revenir au préréglage")

    def _prereglage_active(self) -> None:
        identifiant = self.prereglage.currentData()
        if identifiant:
            self.prereglage_choisi.emit(identifiant)

    # --- Onglets -------------------------------------------------------------------------------

    def _onglet(self) -> tuple[QWidget, QVBoxLayout]:
        page, contenu = conteneur_vertical(Espacements.M)
        contenu.setContentsMargins(0, Espacements.L, 0, 0)
        return page, contenu

    def _onglet_position(self) -> QWidget:
        page, contenu = self._onglet()
        # Un seul groupe (V3.1), avec le ↺ qui remet la position du préréglage, réglage fin compris.
        self.section_position = SectionRepliable("Position", True)
        self.section_position.ajouter_retablir(self._retablir_position, RETABLIR)
        groupe = self.section_position.contenu
        self.verticale = ChoixEnBoutons(POSITIONS, "Point fixe du sous-titre : son haut, son milieu ou son bas")
        self.reglage_fin = glissiere()
        self.reglage_fin.setToolTip("Décale le sous-titre vers le haut ou vers le bas (en % de la hauteur)")
        self.valeur_reglage_fin = libelle("0 %", "legende", retour_a_la_ligne=False)
        ligne_fin = QHBoxLayout()
        ligne_fin.setSpacing(Espacements.S)
        ligne_fin.addWidget(self.reglage_fin, 1)
        ligne_fin.addWidget(self.valeur_reglage_fin)
        self.alignement = ChoixEnBoutons(ALIGNEMENTS, "Alignement des lignes")
        # La glissière prend toute la largeur de sa colonne (les autres champs gardent la leur).
        # V3.1 : les explications au survol d'une icône « i », après le nom du réglage.
        reglages = grille(
            (
                (
                    "Position",
                    self.verticale,
                    "« Haut » et « Bas » : juste à l'intérieur de la zone de sécurité de la plateforme. Tu peux "
                    "aussi glisser le sous-titre dans l'aperçu.",
                ),
                ("Réglage fin", ligne_fin),
                ("Alignement", self.alignement),
            ),
            etirees=(1,),
        )
        groupe.addLayout(reglages)
        self.avances_position = SectionRepliable("Réglages avancés")
        self.largeur_lignes = champ_decimal(*LIMITES["largeur_lignes_pct"], 1, 0, " %", "Largeur maximale des lignes")
        largeur = grille(
            (
                (
                    "Largeur des lignes",
                    self.largeur_lignes,
                    "En % de la largeur utile (zone de sécurité, ou jusqu'à la marge maximum) : pour un bloc plus étroit.",
                ),
            )
        )
        self.avances_position.contenu.addLayout(largeur)
        groupe.addWidget(self.avances_position)
        contenu.addWidget(self.section_position)
        self._marques_position = [
            (marque_de(reglages.champs["Position"]), "verticale"),
            (marque_de(reglages.champs["Réglage fin"]), "decalage_pct"),
            (marque_de(reglages.champs["Alignement"]), "alignement"),
            (marque_de(largeur.champs["Largeur des lignes"]), "largeur_lignes_pct"),
        ]
        contenu.addStretch(1)
        self.verticale.change.connect(lambda _valeur: self.position_change.emit())
        self.reglage_fin.valueChanged.connect(self._reglage_fin_bouge)
        self.alignement.change.connect(lambda _valeur: self.change.emit())
        self.largeur_lignes.valueChanged.connect(lambda _valeur: self.change.emit())
        return page

    def _onglet_decoupage(self) -> QWidget:
        page, contenu = self._onglet()
        # Un seul groupe (V3.1), avec son ↺ ; « Masquer les hésitations » reste dehors : réglage
        # partagé avec la transcription, il ne fait pas partie d'un préréglage.
        self.section_decoupage = SectionRepliable("Découpage", True)
        self.section_decoupage.ajouter_retablir(self._retablir_decoupage, RETABLIR)
        groupe = self.section_decoupage.contenu
        self.caracteres = champ_entier(*LIMITES["caracteres_max"], info="Nombre maximum de caractères par sous-titre, espaces comprises")
        self.mots_max = champ_entier(*LIMITES["mots_max"], info="Nombre maximum de mots par sous-titre")
        self.lignes = champ_entier(*LIMITES["lignes_max"], info="Nombre maximum de lignes (1 ou 2) : jamais dépassé")
        self.duree_min = champ_decimal(*LIMITES["duree_min_s"], 0.1, 1, " s", "Durée minimale d'affichage d'un sous-titre")
        reglages = grille(
            (
                ("Caractères au plus", self.caracteres),
                ("Mots au plus", self.mots_max),
                ("Lignes au plus", self.lignes),
                ("Durée minimale", self.duree_min),
            )
        )
        groupe.addLayout(reglages)
        zone, self.couper_ponctuation = case_a_cocher(
            "Couper de préférence après la ponctuation", "Une fin de phrase termine alors toujours le sous-titre."
        )
        groupe.addWidget(zone)
        contenu.addWidget(self.section_decoupage)
        self._marques_decoupage = [
            (marque_de(reglages.champs["Caractères au plus"]), "caracteres_max"),
            (marque_de(reglages.champs["Mots au plus"]), "mots_max"),
            (marque_de(reglages.champs["Lignes au plus"]), "lignes_max"),
            (marque_de(reglages.champs["Durée minimale"]), "duree_min_s"),
            (self.couper_ponctuation, "couper_sur_ponctuation"),
        ]
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
        # Les mesures de l'écran (« Vidéo 1080 × 1920, texte de 81 px… ») : une ligne de données, sans
        # ampoule (V3.1).
        self.infos_ecran = libelle("", "legende")
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
        contenu.addWidget(
            intitule(
                "Vidéo d'aperçu",
                "Par exemple ton montage exporté de Premiere Pro : tu vois tes sous-titres sur la vraie image. "
                "Elle n'est pas copiée dans le projet, et elle impose son format.",
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
        self._montrer_taille_perso(self.format.currentData() == FORMAT_PERSONNALISE)
        self.change.emit()

    def _montrer_taille_perso(self, visible: bool) -> None:
        """Le réglage « Taille » (nom et champs) : seulement pour le format personnalisé."""
        self.zone_perso.setVisible(visible)
        self.grille_ecran.champs["Taille"].setVisible(visible)

    # --- Lecture et écriture des réglages --------------------------------------------------------

    def charger(
        self,
        reglages: ReglagesSousTitres,
        resolution_imposee: tuple[int, int] | None,
        masquer: bool,
        transcription: bool,
        video_du_projet: bool,
        hauteur_video: int,
        police_remplacee: bool = False,
        accentues_du_script: int | None = None,
    ) -> None:
        """Montre les réglages du projet. `resolution_imposee` : une vidéo impose son format ;
        `video_du_projet` : le projet a sa propre vidéo (pas de vidéo d'aperçu à choisir) ;
        `hauteur_video` : pour montrer les tailles du style en pixels de la vidéo."""
        self.texte.charger(
            reglages.texte, hauteur_video, max(1, round(hauteur_video * reglages.texte.taille_pct / 100)), police_remplacee
        )
        self.mots.charger(reglages.mots, reglages.texte, hauteur_video, accentues_du_script)
        self.animations.charger(reglages.animations, hauteur_video)
        elements = (
            self.verticale, self.reglage_fin, self.alignement,
            self.largeur_lignes, self.caracteres, self.mots_max, self.lignes, self.duree_min, self.couper_ponctuation,
            self.masquer, self.format, self.largeur_perso, self.hauteur_perso, self.plateforme, self.marge,
            self.decalage_video, self.son_video,
        )
        for element in elements:
            element.blockSignals(True)
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
        self._montrer_taille_perso(resolution_imposee is None and reglages.format == FORMAT_PERSONNALISE)
        choisir(self.plateforme, reglages.plateforme)
        self.marge.setValue(reglages.marge_max_pct)
        self._apercu = reglages.apercu
        self.decalage_video.setValue(reglages.apercu.decalage_s)
        self.son_video.setChecked(reglages.apercu.son_de_la_video)
        for element in elements:
            element.blockSignals(False)
        self._reglage_fin_texte()
        self._montrer_video_apercu(video_du_projet)
        self._actualiser_marques()

    # --- Référence : le préréglage du projet (V3.1) ------------------------------------------------

    def definir_reference(self, reference: ReglagesSousTitres, infobulle: str = RETABLIR) -> None:
        """Ce que les ↺ remettent, dans tous les onglets du préréglage : le préréglage du projet tel
        qu'il est enregistré (sans lui, le style de départ). `infobulle` : « Revenir au préréglage
        « Par défaut » »."""
        self._reference = reference
        self.texte.definir_reference(reference.texte, infobulle)
        self.mots.definir_reference(reference.mots, infobulle)
        self.animations.definir_reference(reference.animations, infobulle)
        for section in (self.section_position, self.section_decoupage):
            section.retablir.setToolTip(infobulle)
        self._actualiser_marques()

    def _position_affichee(self) -> Position:
        return Position(
            self.verticale.valeur(),
            round(self.reglage_fin.value() / PAS_REGLAGE_FIN, 2),
            self.alignement.valeur(),
            round(self.largeur_lignes.value(), 1),
        )

    def _decoupage_affiche(self) -> dict:
        return {
            "caracteres_max": self.caracteres.value(),
            "mots_max": self.mots_max.value(),
            "lignes_max": self.lignes.value(),
            "duree_min_s": round(self.duree_min.value(), 2),
            "couper_sur_ponctuation": self.couper_ponctuation.isChecked(),
        }

    def _actualiser_marques(self) -> None:
        """Onglets Position et Découpage : noms en mauve et ↺ du groupe, comparés au préréglage."""
        reference = self._reference
        if reference is None:
            return
        position = self._position_affichee()
        ecart = False
        for element, nom in self._marques_position:
            change = not meme_valeur(getattr(position, nom), getattr(reference.position, nom))
            marquer(element, change)
            ecart = ecart or change
        self.section_position.montrer_retablir(ecart)
        decoupage = self._decoupage_affiche()
        ecart = False
        for element, nom in self._marques_decoupage:
            change = not meme_valeur(decoupage[nom], getattr(reference, nom))
            marquer(element, change)
            ecart = ecart or change
        self.section_decoupage.montrer_retablir(ecart)

    def _retablir_position(self) -> None:
        """↺ de la position : celle du préréglage, réglage fin compris (la page l'applique)."""
        if self._reference is None:
            return
        position = self._reference.position
        for element in (self.verticale, self.reglage_fin, self.alignement, self.largeur_lignes):
            element.blockSignals(True)
        self.verticale.definir(position.verticale)
        self.reglage_fin.setValue(round(position.decalage_pct * PAS_REGLAGE_FIN))
        self.alignement.definir(position.alignement)
        self.largeur_lignes.setValue(position.largeur_lignes_pct)
        for element in (self.verticale, self.reglage_fin, self.alignement, self.largeur_lignes):
            element.blockSignals(False)
        self._reglage_fin_texte()
        self.change.emit()

    def _retablir_decoupage(self) -> None:
        """↺ du découpage : celui du préréglage (la page vérifie d'abord les sous-titres réorganisés)."""
        if self._reference is None:
            return
        reference = self._reference
        champs = (self.caracteres, self.mots_max, self.lignes, self.duree_min, self.couper_ponctuation)
        for element in champs:
            element.blockSignals(True)
        self.caracteres.setValue(reference.caracteres_max)
        self.mots_max.setValue(reference.mots_max)
        self.lignes.setValue(reference.lignes_max)
        self.duree_min.setValue(reference.duree_min_s)
        self.couper_ponctuation.setChecked(reference.couper_sur_ponctuation)
        for element in champs:
            element.blockSignals(False)
        self.change.emit()

    def _reglage_fin_texte(self) -> None:
        valeur = self.reglage_fin.value()
        signe = "+" if valeur > 0 else ""
        self.valeur_reglage_fin.setText(f"{signe}{nombre_lisible(valeur / PAS_REGLAGE_FIN)} %")

    def _remplir_formats(self, resolution_imposee: tuple[int, int] | None) -> None:
        if resolution_imposee == self._resolution_imposee:
            return  # même liste : elle n'est pas refaite (elle peut être en train de changer de choix)
        self._resolution_imposee = resolution_imposee
        self.format.clear()
        if resolution_imposee:
            largeur, hauteur = resolution_imposee
            self.format.addItem(f"Celui de la vidéo ({largeur} × {hauteur})", FORMAT_AUTO)
            self.info_format.setText("Le format suit la vidéo : le calque transparent doit avoir sa taille exacte.")
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
            texte=self.texte.style(base.texte),
            mots=self.mots.mots(),
            animations=self.animations.animations(),
            position=self._position_affichee(),
            format=format_choisi or base.format,
            largeur_perso=cote_pair(self.largeur_perso.value()),
            hauteur_perso=cote_pair(self.hauteur_perso.value()),
            plateforme=self.plateforme.currentData(),
            marge_max_pct=round(self.marge.value(), 2),
            apercu=base.apercu,
            prereglage=base.prereglage,
            prereglage_nom=base.prereglage_nom,
        )

    def decalage_et_son(self) -> tuple[float, bool]:
        return round(self.decalage_video.value(), 2), self.son_video.isChecked()
