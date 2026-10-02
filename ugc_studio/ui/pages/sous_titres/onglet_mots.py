"""Onglet « Mots » du studio des sous-titres (V2, lot 5 ; cahier des charges §7.5 et §7.11) : ce qui
change pour le mot en train d'être dit.

- Raccourci (Sous-titre fixe, Surlignage, Karaoké, Apparition, Mot par mot) : remplit les états ;
  tout reste modifiable ensuite (« Personnalisé » quand les états ne sont plus ceux d'un raccourci).
- États : À venir, Mot actif, Déjà dits, et Accentués (les mots mis en valeur dans le script d'une
  prise). Un état à la fois s'affiche, avec ses réglages en groupes repliables.
- Chaque réglage vaut « comme le texte » (onglet Texte) tant qu'on ne le change pas : un réglage
  changé a son libellé en mauve et un bouton ↺ qui le remet « comme le texte ».
- Réglages avancés : avance de l'allumage (les mots s'allument un peu plus tôt ou plus tard).

Les tailles sont montrées en pixels de la vidéo actuelle et rangées en % de sa hauteur (comme dans
l'onglet Texte).
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QVBoxLayout, QWidget

from ....style_sous_titres import (
    ACCENTUES,
    ACTIF,
    DIRECTIONS,
    ETATS,
    RACCOURCIS,
    Contour,
    Degrade,
    EtatMot,
    FondMot,
    Lueur,
    Mots,
    Soulignement,
    StyleTexte,
    appliquer_raccourci,
    raccourci_de,
)
from ...composants.champ_couleur import ChampCouleur
from ...composants.choix import ChoixEnBoutons
from ...composants.choix_voix import choisir
from ...composants.elements import ChampNomme, bouton, case_a_cocher, champ_decimal, champ_entier, info, liste_deroulante
from ...composants.section_repliable import SectionRepliable
from ...theme import Espacements
from .onglet_texte import HAUTEUR_PAR_DEFAUT, ChampExact, ChampPixels
from .reglages_communs import GrilleDeReglages, nombre_lisible

PERSONNALISE = "personnalise"
EXPLICATIONS = {
    "a_venir": "Les mots pas encore dits.",
    ACTIF: "Le mot en train d'être dit.",
    "dits": "Les mots déjà dits.",
    ACCENTUES: "Les mots mis en valeur dans le script d'une prise (bouton « Accentuer » du module Voix).",
}


class GrilleEtat:
    """Réglages d'un état, sous leur nom, côte à côte (voir GrilleDeReglages), avec un bouton ↺
    « comme le texte » à côté du champ d'un réglage changé ; son nom passe en mauve (le texte de sa
    case à cocher, pour un effet qu'on coche). Le bouton garde sa place même caché : les réglages ne
    bougent pas quand il apparaît."""

    def __init__(self, contenu: QVBoxLayout, infobulle_remise: str = "Comme le texte"):
        self.infobulle_remise = infobulle_remise
        self.disposition = GrilleDeReglages()
        contenu.addLayout(self.disposition)
        self.marques: dict[str, tuple] = {}  # attribut de l'état → (nom ou case à cocher, bouton ↺)

    def ligne(self, titre: str | None, element, attribut: str | None = None, retablir=None) -> ChampNomme:
        """Un réglage sous son nom ; sans nom (une case à cocher, qui se nomme elle-même), il prend une
        rangée à lui seul."""
        remise = None
        if attribut is not None:
            remise = bouton("", variante="icone", nom_icone="rotate-ccw", action=retablir)
            remise.setToolTip(self.infobulle_remise)
            garder_la_place = remise.sizePolicy()
            garder_la_place.setRetainSizeWhenHidden(True)
            remise.setSizePolicy(garder_la_place)
        champ = self.disposition.ajouter(titre, element, a_cote=remise)
        if attribut is not None:
            marque = champ.nom if champ.nom is not None else element.findChild(QCheckBox)
            self.marques[attribut] = (marque, remise)
        return champ

    def marquer(self, attribut: str, change: bool) -> None:
        marque, remise = self.marques[attribut]
        if isinstance(marque, QCheckBox):
            nouveau, ancien = change, marque.property("modifie") is True
            if nouveau != ancien:
                marque.setProperty("modifie", nouveau)
                marque.style().unpolish(marque)
                marque.style().polish(marque)
        else:
            role = "legende-modifiee" if change else "legende"
            if marque.property("role") != role:
                marque.setProperty("role", role)
                marque.style().unpolish(marque)
                marque.style().polish(marque)
        remise.setVisible(change)


class OngletMots(QWidget):
    change = Signal()  # un réglage des mots a changé (la page vérifie le découpage, puis l'applique)
    pipette_demandee = Signal(object)  # un champ couleur attend une couleur prise dans l'aperçu

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._mots = Mots()
        self._texte = StyleTexte()
        self._hauteur = HAUTEUR_PAR_DEFAUT
        self._nom = ACTIF
        self._chargement = False
        self.grilles: list[GrilleEtat] = []
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.L, 0, 0)
        disposition.setSpacing(Espacements.M)

        # Raccourci et état réglé.
        self.raccourci = liste_deroulante("Remplit les réglages des états ; tout reste modifiable ensuite")
        for code, nom in RACCOURCIS.items():
            self.raccourci.addItem(nom, code)
        self.raccourci.activated.connect(lambda _index: self._raccourci_choisi())
        self.etat = ChoixEnBoutons(ETATS, "L'état dont tu règles l'apparence")
        self.etat.change.connect(self._etat_choisi)
        haut = GrilleDeReglages()
        haut.ajouter("Raccourci", self.raccourci)
        haut.ajouter("État", self.etat)
        disposition.addLayout(haut)
        self.explication = info()
        disposition.addWidget(self.explication)

        # Mots accentués (état facultatif).
        self.zone_accentues = QWidget()
        accentues = QVBoxLayout(self.zone_accentues)
        accentues.setContentsMargins(0, 0, 0, 0)
        accentues.setSpacing(Espacements.S)
        zone, self.accentues_actifs = case_a_cocher("Utiliser l'état « Accentués »")
        self.accentues_actifs.toggled.connect(self._accentues_coches)
        accentues.addWidget(zone)
        self.info_accentues = info()
        accentues.addWidget(self.info_accentues)
        disposition.addWidget(self.zone_accentues)

        # Réglages de l'état.
        self.zone_etat = QWidget()
        etat = QVBoxLayout(self.zone_etat)
        etat.setContentsMargins(0, 0, 0, 0)
        etat.setSpacing(Espacements.M)
        grille = self._grille(etat)
        zone_visible, self.visible = case_a_cocher("Mot visible")
        self.visible.toggled.connect(lambda coche: self._modifier(visible=coche))
        grille.ligne(None, zone_visible, "visible", lambda: self._modifier(visible=True))
        self.opacite = ChampExact(champ_decimal(0.0, 100.0, 5.0, 0, " %", "Opacité des mots de cet état"))
        self.opacite.champ.valueChanged.connect(lambda _valeur: self._modifier(opacite_pct=self.opacite.valeur()))
        grille.ligne("Opacité", self.opacite.champ, "opacite_pct", lambda: self._modifier(opacite_pct=None))
        self.sections: dict[str, SectionRepliable] = {}
        for titre, construire, ouverte in (
            ("Remplissage", self._groupe_remplissage, True),
            ("Contour", self._groupe_contour, False),
            ("Lueur", self._groupe_lueur, False),
            ("Fond surligné", self._groupe_fond, False),
            ("Soulignement", self._groupe_soulignement, False),
            ("Taille et place", self._groupe_taille, True),
        ):
            section = SectionRepliable(titre, ouverte)
            construire(section.contenu)
            self.sections[titre] = section
            etat.addWidget(section)
        disposition.addWidget(self.zone_etat)

        avances = SectionRepliable("Réglages avancés")
        self.avance = champ_entier(*Mots.LIMITES["avance_ms"], " ms", "Positif : les mots s'allument plus tôt ; négatif : plus tard")
        self.avance.setSingleStep(10)
        self.avance.valueChanged.connect(self._avance_changee)
        avance = GrilleDeReglages()
        avance.ajouter("Avance de l'allumage", self.avance)
        avances.contenu.addLayout(avance)
        avances.contenu.addWidget(
            info("Si les mots s'allument un peu tard ou un peu tôt à ton goût. Le moment des mots, lui, ne change pas.")
        )
        self.section_avancee = avances
        disposition.addWidget(avances)
        disposition.addStretch(1)
        self.etat.definir(ACTIF)
        self._afficher_etat()

    # --- Construction --------------------------------------------------------------------------

    def _grille(self, contenu: QVBoxLayout) -> GrilleEtat:
        grille = GrilleEtat(contenu)
        self.grilles.append(grille)
        return grille

    def _couleur(self, info_champ: str, quand) -> ChampCouleur:
        champ = ChampCouleur(info_champ)
        champ.change.connect(quand)
        champ.pipette_demandee.connect(self.pipette_demandee.emit)
        return champ

    def _pixels(self, limites: tuple[float, float], info_champ: str, quand) -> ChampPixels:
        champ = ChampPixels(limites, info_champ)
        champ.champ.valueChanged.connect(lambda _valeur: quand())
        return champ

    def _groupe_remplissage(self, contenu: QVBoxLayout) -> None:
        grille = self._grille(contenu)
        self.couleur = self._couleur("Couleur des mots de cet état", lambda: self._modifier(couleur=self.couleur.couleur()))
        grille.ligne("Couleur", self.couleur, "couleur", lambda: self._modifier(couleur=None))
        zone, self.degrade = case_a_cocher("Dégradé de deux couleurs")
        self.degrade.toggled.connect(lambda _coche: self._modifier(degrade=self._degrade()))
        grille.ligne(None, zone, "degrade", lambda: self._modifier(degrade=None))
        self.couleur_2 = self._couleur("Seconde couleur du dégradé", lambda: self._modifier(degrade=self._degrade()))
        self.direction = ChoixEnBoutons(DIRECTIONS, "Sens du dégradé, sur chaque ligne")
        self.direction.change.connect(lambda _valeur: self._modifier(degrade=self._degrade()))
        self._champs_degrade = (grille.ligne("Seconde couleur", self.couleur_2), grille.ligne("Sens", self.direction))

    def _groupe_contour(self, contenu: QVBoxLayout) -> None:
        grille = self._grille(contenu)
        zone, self.contour = case_a_cocher("Contour autour des lettres")
        self.contour.toggled.connect(lambda _coche: self._modifier(contour=self._contour()))
        grille.ligne(None, zone, "contour", lambda: self._modifier(contour=None))
        self.contour_couleur = self._couleur("Couleur du contour", lambda: self._modifier(contour=self._contour()))
        self.contour_epaisseur = self._pixels(Contour.LIMITES["epaisseur_pct"], "Épaisseur du contour", lambda: self._modifier(contour=self._contour()))
        self._champs_contour = (grille.ligne("Couleur", self.contour_couleur), grille.ligne("Épaisseur", self.contour_epaisseur.champ))

    def _groupe_lueur(self, contenu: QVBoxLayout) -> None:
        grille = self._grille(contenu)
        zone, self.lueur = case_a_cocher("Lueur autour des lettres")
        self.lueur.toggled.connect(lambda _coche: self._modifier(lueur=self._lueur()))
        grille.ligne(None, zone, "lueur", lambda: self._modifier(lueur=None))
        self.lueur_couleur = self._couleur("Couleur de la lueur", lambda: self._modifier(lueur=self._lueur()))
        self.lueur_taille = self._pixels(Lueur.LIMITES["taille_pct"], "Taille de la lueur", lambda: self._modifier(lueur=self._lueur()))
        self.lueur_intensite = ChampExact(champ_decimal(*Lueur.LIMITES["intensite_pct"], 5, 0, " %", "Intensité de la lueur"))
        self.lueur_intensite.champ.valueChanged.connect(lambda _valeur: self._modifier(lueur=self._lueur()))
        self._champs_lueur = (
            grille.ligne("Couleur", self.lueur_couleur),
            grille.ligne("Taille", self.lueur_taille.champ),
            grille.ligne("Intensité", self.lueur_intensite.champ),
        )

    def _groupe_fond(self, contenu: QVBoxLayout) -> None:
        grille = self._grille(contenu)
        zone, self.fond = case_a_cocher("Fond derrière le mot")
        self.fond.toggled.connect(lambda _coche: self._modifier(fond=self._fond()))
        grille.ligne(None, zone, "fond", lambda: self._modifier(fond=None))
        self.fond_couleur = self._couleur("Couleur du fond", lambda: self._modifier(fond=self._fond()))
        self.fond_marge_x = self._pixels(FondMot.LIMITES["marge_x_pct"], "Marge à gauche et à droite du mot", lambda: self._modifier(fond=self._fond()))
        self.fond_marge_y = self._pixels(FondMot.LIMITES["marge_y_pct"], "Marge en haut et en bas du mot", lambda: self._modifier(fond=self._fond()))
        self.fond_arrondi = self._pixels(FondMot.LIMITES["arrondi_pct"], "Arrondi des coins", lambda: self._modifier(fond=self._fond()))
        self._champs_fond = (
            grille.ligne("Couleur", self.fond_couleur),
            grille.ligne("Marge horizontale", self.fond_marge_x.champ),
            grille.ligne("Marge verticale", self.fond_marge_y.champ),
            grille.ligne("Arrondi", self.fond_arrondi.champ),
        )
        # Mot actif seulement : le fond glisse d'un mot à l'autre.
        self.zone_glisse = SectionRepliable("Réglages avancés")
        zone, self.fond_glisse = case_a_cocher("Le fond glisse d'un mot à l'autre")
        self.fond_glisse.toggled.connect(lambda _coche: self._modifier(fond=self._fond()))
        self.zone_glisse.contenu.addWidget(zone)
        self.fond_duree = champ_entier(*FondMot.LIMITES["duree_glisse_ms"], " ms", "Durée du glissement")
        self.fond_duree.setSingleStep(10)
        self.fond_duree.valueChanged.connect(lambda _valeur: self._modifier(fond=self._fond()))
        glissement = GrilleDeReglages()
        self._champ_fond_duree = glissement.ajouter("Durée", self.fond_duree)
        self.zone_glisse.contenu.addLayout(glissement)
        contenu.addWidget(self.zone_glisse)

    def _groupe_soulignement(self, contenu: QVBoxLayout) -> None:
        grille = self._grille(contenu)
        zone, self.souligne = case_a_cocher("Trait sous le mot")
        self.souligne.toggled.connect(lambda _coche: self._modifier(soulignement=self._soulignement()))
        grille.ligne(None, zone, "soulignement", lambda: self._modifier(soulignement=None))
        self.souligne_couleur = self._couleur("Couleur du trait", lambda: self._modifier(soulignement=self._soulignement()))
        self.souligne_epaisseur = self._pixels(
            Soulignement.LIMITES["epaisseur_pct"], "Épaisseur du trait", lambda: self._modifier(soulignement=self._soulignement())
        )
        self.souligne_distance = self._pixels(
            Soulignement.LIMITES["distance_pct"], "Distance sous la ligne de base", lambda: self._modifier(soulignement=self._soulignement())
        )
        self._champs_souligne = (
            grille.ligne("Couleur", self.souligne_couleur),
            grille.ligne("Épaisseur", self.souligne_epaisseur.champ),
            grille.ligne("Distance", self.souligne_distance.champ),
        )

    def _groupe_taille(self, contenu: QVBoxLayout) -> None:
        grille = self._grille(contenu)
        self.taille = ChampExact(champ_decimal(*EtatMot.LIMITES["taille_pct"], 1, 0, " %", "Agrandissement autour du centre du mot"))
        self.taille.champ.valueChanged.connect(lambda _valeur: self._modifier(taille_pct=self.taille.valeur()))
        grille.ligne("Taille", self.taille.champ, "taille_pct", lambda: self._modifier(taille_pct=None))
        self.decalage = self._pixels(
            EtatMot.LIMITES["decalage_y_pct"], "Décalage vers le bas (négatif : vers le haut)", lambda: self._modifier(decalage_y_pct=self.decalage.valeur())
        )
        grille.ligne("Décalage vertical", self.decalage.champ, "decalage_y_pct", lambda: self._modifier(decalage_y_pct=None))

    # --- Valeurs des groupes ---------------------------------------------------------------------

    def _degrade(self) -> Degrade:
        return Degrade(self.degrade.isChecked(), self.couleur_2.couleur(), self.direction.valeur() or "vertical")

    def _contour(self) -> Contour:
        angles = (self._etat().contour or self._texte.contour).angles
        return Contour(self.contour.isChecked(), self.contour_couleur.couleur(), self.contour_epaisseur.valeur(), angles)

    def _lueur(self) -> Lueur:
        return Lueur(self.lueur.isChecked(), self.lueur_couleur.couleur(), self.lueur_taille.valeur(), self.lueur_intensite.valeur())

    def _fond(self) -> FondMot | None:
        if not self.fond.isChecked():
            return None
        return FondMot(
            self.fond_couleur.couleur(), self.fond_marge_x.valeur(), self.fond_marge_y.valeur(), self.fond_arrondi.valeur(),
            self.fond_glisse.isChecked(), self.fond_duree.value(),
        )

    def _soulignement(self) -> Soulignement | None:
        if not self.souligne.isChecked():
            return None
        return Soulignement(self.souligne_couleur.couleur(), self.souligne_epaisseur.valeur(), self.souligne_distance.valeur())

    # --- États ------------------------------------------------------------------------------------

    def _etat(self) -> EtatMot:
        return self._mots.etat(self._nom)

    def _modifier(self, **changements) -> None:
        """Un réglage de l'état affiché a changé (None : « comme le texte »)."""
        if self._chargement:
            return
        etat = replace(self._etat(), **changements)
        if etat == self._etat():
            return
        self._mots = replace(self._mots, **{self._nom: etat})
        self._afficher_etat()
        self.change.emit()

    def _etat_choisi(self, nom: str) -> None:
        if nom in ETATS and nom != self._nom:
            self._nom = nom
            self._afficher_etat()

    def _raccourci_choisi(self) -> None:
        code = self.raccourci.currentData()
        if code in RACCOURCIS:
            self._mots = appliquer_raccourci(self._mots, code)
            self._afficher_etat()
            self.change.emit()

    def _accentues_coches(self, coche: bool) -> None:
        if self._chargement or coche == self._mots.accentues_actifs:
            return
        self._mots = replace(self._mots, accentues_actifs=coche)
        self._afficher_etat()
        self.change.emit()

    def _avance_changee(self, valeur: int) -> None:
        if self._chargement or valeur == self._mots.avance_ms:
            return
        self._mots = replace(self._mots, avance_ms=valeur)
        self.change.emit()

    # --- Lecture et écriture -------------------------------------------------------------------

    def charger(self, mots: Mots, texte: StyleTexte, hauteur_video: int, accentues_du_script: int | None = None) -> None:
        """Montre les réglages des mots du projet. `accentues_du_script` : nombre de mots accentués
        dans le script de la prise (None : les sous-titres ne viennent pas d'une prise)."""
        self._mots, self._texte = mots, texte
        self._hauteur = max(1, hauteur_video)
        for champ in (
            self.contour_epaisseur, self.lueur_taille, self.fond_marge_x, self.fond_marge_y, self.fond_arrondi,
            self.souligne_epaisseur, self.souligne_distance, self.decalage,
        ):
            champ.definir_hauteur(self._hauteur)
        if accentues_du_script is None:
            self.info_accentues.setText("Ces sous-titres ne viennent pas d'une prise du module Voix : aucun mot accentué.")
        elif accentues_du_script == 0:
            self.info_accentues.setText("Aucun mot accentué dans le script de la prise (bouton « Accentuer » du module Voix).")
        else:
            pluriel = "s" if accentues_du_script > 1 else ""
            self.info_accentues.setText(f"{accentues_du_script} mot{pluriel} accentué{pluriel} dans le script de la prise.")
        self._afficher_etat()

    def mots(self) -> Mots:
        """Réglages des mots tels que dans l'onglet."""
        return self._mots

    def _afficher_etat(self) -> None:
        """Montre l'état choisi : ses valeurs (« comme le texte » quand il n'en a pas), les marques des
        réglages changés, le raccourci correspondant."""
        self._chargement = True
        mots, texte, etat = self._mots, self._texte, self._etat()
        self.etat.definir(self._nom)
        self.explication.setText(EXPLICATIONS.get(self._nom, ""))
        raccourci = raccourci_de(mots)
        if raccourci is None:
            if self.raccourci.findData(PERSONNALISE) < 0:
                self.raccourci.insertItem(0, "Personnalisé", PERSONNALISE)
            choisir(self.raccourci, PERSONNALISE)
        else:
            index = self.raccourci.findData(PERSONNALISE)
            if index >= 0:
                self.raccourci.removeItem(index)
            choisir(self.raccourci, raccourci)
        accentues = self._nom == ACCENTUES
        self.zone_accentues.setVisible(accentues)
        self.accentues_actifs.setChecked(mots.accentues_actifs)
        self.zone_etat.setEnabled(not accentues or mots.accentues_actifs)
        self.zone_glisse.setVisible(self._nom == ACTIF)
        self.avance.setValue(mots.avance_ms)

        self.visible.setChecked(etat.visible)
        self.opacite.definir(etat.opacite_pct if etat.opacite_pct is not None else 100.0)
        self.couleur.definir(etat.couleur or texte.couleur)
        degrade = etat.degrade or texte.degrade
        self.degrade.setChecked(degrade.actif)
        self.couleur_2.definir(degrade.couleur)
        self.direction.definir(degrade.direction)
        contour = etat.contour or texte.contour
        self.contour.setChecked(contour.actif)
        self.contour_couleur.definir(contour.couleur)
        self.contour_epaisseur.definir(contour.epaisseur_pct)
        lueur = etat.lueur or texte.lueur
        self.lueur.setChecked(lueur.active)
        self.lueur_couleur.definir(lueur.couleur)
        self.lueur_taille.definir(lueur.taille_pct)
        self.lueur_intensite.definir(lueur.intensite_pct)
        fond = etat.fond or FondMot()
        self.fond.setChecked(etat.fond is not None)
        self.fond_couleur.definir(fond.couleur)
        self.fond_marge_x.definir(fond.marge_x_pct)
        self.fond_marge_y.definir(fond.marge_y_pct)
        self.fond_arrondi.definir(fond.arrondi_pct)
        self.fond_glisse.setChecked(fond.glisse)
        self.fond_duree.setValue(fond.duree_glisse_ms)
        souligne = etat.soulignement or Soulignement()
        self.souligne.setChecked(etat.soulignement is not None)
        self.souligne_couleur.definir(souligne.couleur)
        self.souligne_epaisseur.definir(souligne.epaisseur_pct)
        self.souligne_distance.definir(souligne.distance_pct)
        self.taille.definir(etat.taille_pct if etat.taille_pct is not None else 100.0)
        self.decalage.definir(etat.decalage_y_pct or 0.0)
        self._chargement = False

        changes = {
            "visible": not etat.visible,
            "opacite_pct": etat.opacite_pct is not None,
            "couleur": etat.couleur is not None,
            "degrade": etat.degrade is not None,
            "contour": etat.contour is not None,
            "lueur": etat.lueur is not None,
            "fond": etat.fond is not None,
            "soulignement": etat.soulignement is not None,
            "taille_pct": etat.taille_pct is not None,
            "decalage_y_pct": etat.decalage_y_pct is not None,
        }
        for grille in self.grilles:
            for attribut in grille.marques:
                grille.marquer(attribut, changes[attribut])
        # Réglages d'un effet décoché : grisés, noms compris (comme dans l'onglet Texte).
        for case, champs in (
            (self.degrade, self._champs_degrade),
            (self.contour, self._champs_contour),
            (self.lueur, self._champs_lueur),
            (self.fond, (*self._champs_fond, self.zone_glisse)),
            (self.souligne, self._champs_souligne),
        ):
            for champ in champs:
                champ.setEnabled(case.isChecked())
        self._champ_fond_duree.setEnabled(self.fond.isChecked() and self.fond_glisse.isChecked())
        resumes = {
            "Remplissage": "comme le texte" if not (changes["couleur"] or changes["degrade"]) else (etat.couleur or texte.couleur).code,
            "Contour": "comme le texte" if not changes["contour"] else ("aucun" if not contour.actif else contour.couleur.code),
            "Lueur": "comme le texte" if not changes["lueur"] else ("aucune" if not lueur.active else lueur.couleur.code),
            "Fond surligné": fond.couleur.code if etat.fond is not None else "aucun",
            "Soulignement": souligne.couleur.code if etat.soulignement is not None else "aucun",
            "Taille et place": f"{nombre_lisible(etat.echelle * 100)} %",
        }
        for titre, resume in resumes.items():
            self.sections[titre].definir_resume(resume)
