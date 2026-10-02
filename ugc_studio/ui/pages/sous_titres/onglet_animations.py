"""Onglet « Animations » du studio des sous-titres (V2, lot 6 ; cahier des charges §7.5 et §7.12).

- Quand un mot devient actif : aucune, pop, rebond, zoom, fondu ou glissement vers le haut ; durée
  et intensité. Réglages avancés : taille de départ, au sommet et d'arrivée, opacité et décalage de
  départ, courbe (douce, rebond ou régulière) ; tant qu'on ne les change pas, ce sont ceux de
  l'animation choisie (↺ les y remet).
- Quand il redevient « déjà dit » : instantané ou fondu (durée).
- Sous-titre entier : apparition et disparition (aucune, fondu, pop, zoom, glissement vers le haut
  ou vers le bas), chacune avec sa durée.

Les animations ne changent jamais les temps des sous-titres : l'apparition commence au début du
sous-titre, la disparition se termine à sa fin.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ....style_sous_titres import (
    ANIM_AUCUNE,
    ANIMATIONS_DU_MOT,
    ANIMATIONS_DU_SOUS_TITRE,
    COURBES,
    RETOUR_FONDU,
    RETOURS,
    AnimationMot,
    Animations,
)
from ...composants.choix import ChoixEnBoutons
from ...composants.choix_voix import choisir
from ...composants.elements import ChampNomme, champ_decimal, champ_entier, liste_deroulante
from ...composants.section_repliable import SectionRepliable
from ...theme import Espacements
from .onglet_mots import GrilleEtat
from .onglet_texte import HAUTEUR_PAR_DEFAUT, ChampExact, ChampPixels
from .reglages_communs import GrilleDeReglages, nombre_lisible

PAS_DUREE_MS = 10


def _duree(minimum_maximum: tuple[int, int], info_champ: str):
    champ = champ_entier(*minimum_maximum, " ms", info_champ)
    champ.setSingleStep(PAS_DUREE_MS)
    return champ


class OngletAnimations(QWidget):
    change = Signal()  # une animation a changé (la page vérifie le découpage, puis l'applique)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._animations = Animations()
        self._hauteur = HAUTEUR_PAR_DEFAUT
        self._chargement = False
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.L, 0, 0)
        disposition.setSpacing(Espacements.M)
        self.sections: dict[str, SectionRepliable] = {}

        # Le mot qui devient actif.
        section = SectionRepliable("Mot qui devient actif", True)
        self.sections["Mot qui devient actif"] = section
        grille = GrilleEtat(section.contenu)
        self.type = liste_deroulante("Animation du mot quand il devient actif")
        for code, nom in ANIMATIONS_DU_MOT.items():
            self.type.addItem(nom, code)
        self.type.currentIndexChanged.connect(lambda _index: self._mot(type=self.type.currentData() or ANIM_AUCUNE))
        grille.ligne("Animation", self.type)
        self.duree = _duree(AnimationMot.LIMITES["duree_ms"], "Durée de l'animation")
        self.duree.valueChanged.connect(lambda valeur: self._mot(duree_ms=valeur))
        self.intensite = ChampExact(champ_decimal(*AnimationMot.LIMITES["intensite_pct"], 10, 0, " %", "Plus ou moins marquée"))
        self.intensite.champ.valueChanged.connect(lambda _valeur: self._mot(intensite_pct=self.intensite.valeur()))
        self._champs_animes = (grille.ligne("Durée", self.duree), grille.ligne("Intensité", self.intensite.champ))
        avances = SectionRepliable("Réglages avancés")
        self.section_avancee = avances
        self.grille_avancee = GrilleEtat(avances.contenu, "Comme l'animation choisie")
        self.taille_depart = self._pourcentage("taille_depart_pct", "Taille du mot au début de l'animation")
        self.grille_avancee.ligne("Taille de départ", self.taille_depart.champ, "taille_depart_pct", lambda: self._mot(taille_depart_pct=None))
        self.taille_sommet = self._pourcentage("taille_sommet_pct", "Taille du mot au plus fort de l'animation")
        self.grille_avancee.ligne("Taille au sommet", self.taille_sommet.champ, "taille_sommet_pct", lambda: self._mot(taille_sommet_pct=None))
        self.taille_arrivee = self._pourcentage("taille_arrivee_pct", "Taille du mot à la fin de l'animation")
        self.grille_avancee.ligne("Taille d'arrivée", self.taille_arrivee.champ, "taille_arrivee_pct", lambda: self._mot(taille_arrivee_pct=None))
        self.opacite_depart = self._pourcentage("opacite_depart_pct", "Opacité du mot au début de l'animation")
        self.grille_avancee.ligne("Opacité de départ", self.opacite_depart.champ, "opacite_depart_pct", lambda: self._mot(opacite_depart_pct=None))
        self.decalage_depart = ChampPixels(AnimationMot.LIMITES["decalage_depart_pct"], "Décalage de départ, vers le bas (négatif : vers le haut)")
        self.decalage_depart.champ.valueChanged.connect(lambda _valeur: self._mot(decalage_depart_pct=self.decalage_depart.valeur()))
        self.grille_avancee.ligne("Décalage de départ", self.decalage_depart.champ, "decalage_depart_pct", lambda: self._mot(decalage_depart_pct=None))
        self.courbe = liste_deroulante("Douce : ralentit à l'arrivée ; rebond : dépasse un peu, puis revient")
        for code, nom in COURBES.items():
            self.courbe.addItem(nom, code)
        self.courbe.currentIndexChanged.connect(lambda _index: self._mot(courbe=self.courbe.currentData()))
        self.grille_avancee.ligne("Courbe", self.courbe, "courbe", lambda: self._mot(courbe=None))
        section.contenu.addWidget(avances)
        disposition.addWidget(section)

        # Retour à « déjà dit ».
        section = SectionRepliable("Retour à « déjà dit »", True)
        self.sections["Retour"] = section
        retour = GrilleDeReglages()
        self.retour = ChoixEnBoutons(RETOURS, "Quand le mot suivant devient actif")
        self.retour.change.connect(lambda valeur: self._modifier(retour=valeur))
        retour.ajouter("Transition", self.retour)
        self.retour_duree = _duree(Animations.LIMITES["retour_duree_ms"], "Durée du fondu")
        self.retour_duree.valueChanged.connect(lambda valeur: self._modifier(retour_duree_ms=valeur))
        self._champ_retour_duree = retour.ajouter("Durée", self.retour_duree)
        section.contenu.addLayout(retour)
        disposition.addWidget(section)

        # Le sous-titre entier.
        section = SectionRepliable(
            "Sous-titre entier",
            True,
            aide=(
                "Les animations ne changent pas les temps : l'apparition commence au début du sous-titre, la "
                "disparition finit à sa fin."
            ),
        )
        self.sections["Sous-titre entier"] = section
        entier = GrilleDeReglages()
        section.contenu.addLayout(entier)
        self.apparition, self.apparition_duree, self._champ_apparition_duree = self._entree_sortie(entier, "Apparition", "apparition")
        self.disparition, self.disparition_duree, self._champ_disparition_duree = self._entree_sortie(entier, "Disparition", "disparition")
        disposition.addWidget(section)
        disposition.addStretch(1)
        self._afficher()

    # --- Construction --------------------------------------------------------------------------

    def _pourcentage(self, attribut: str, info_champ: str) -> ChampExact:
        champ = ChampExact(champ_decimal(*AnimationMot.LIMITES[attribut], 1, 0, " %", info_champ))
        champ.champ.valueChanged.connect(lambda _valeur: self._mot(**{attribut: champ.valeur()}))
        return champ

    def _entree_sortie(self, grille: GrilleDeReglages, titre: str, attribut: str):
        """L'animation et sa durée, chacune sous son nom ; la paire passe à la ligne d'un bloc."""
        liste = liste_deroulante(f"{titre} du sous-titre entier")
        for code, nom in ANIMATIONS_DU_SOUS_TITRE.items():
            liste.addItem(nom, code)
        liste.currentIndexChanged.connect(lambda _index: self._modifier(**{attribut: liste.currentData() or ANIM_AUCUNE}))
        duree = _duree(Animations.LIMITES[f"{attribut}_duree_ms"], f"Durée : {titre.lower()}")
        duree.valueChanged.connect(lambda valeur: self._modifier(**{f"{attribut}_duree_ms": valeur}))
        paire = QWidget()
        ligne = QHBoxLayout(paire)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.L)
        ligne.addWidget(ChampNomme(titre, liste))
        champ_duree = ChampNomme("Durée", duree)
        ligne.addWidget(champ_duree)
        grille.addWidget(paire)
        return liste, duree, champ_duree

    # --- Modifications --------------------------------------------------------------------------

    def _modifier(self, **changements) -> None:
        if self._chargement:
            return
        nouvelles = replace(self._animations, **changements)
        if nouvelles == self._animations:
            return
        self._animations = nouvelles
        self._afficher()
        self.change.emit()

    def _mot(self, **changements) -> None:
        if self._chargement:
            return
        self._modifier(mot=replace(self._animations.mot, **changements))

    # --- Lecture et écriture -------------------------------------------------------------------

    def charger(self, animations: Animations, hauteur_video: int) -> None:
        self._animations = animations
        self._hauteur = max(1, hauteur_video)
        self.decalage_depart.definir_hauteur(self._hauteur)
        self._afficher()

    def animations(self) -> Animations:
        return self._animations

    def _afficher(self) -> None:
        self._chargement = True
        animations = self._animations
        mot = animations.mot
        profil = mot.profil()
        choisir(self.type, mot.type)
        self.duree.setValue(mot.duree_ms)
        self.intensite.definir(mot.intensite_pct)
        self.taille_depart.definir(profil.depart)
        self.taille_sommet.definir(profil.sommet)
        self.taille_arrivee.definir(profil.arrivee)
        self.opacite_depart.definir(profil.opacite_depart)
        self.decalage_depart.definir(profil.decalage_depart)
        choisir(self.courbe, profil.courbe)
        self.retour.definir(animations.retour)
        self.retour_duree.setValue(animations.retour_duree_ms)
        choisir(self.apparition, animations.apparition)
        self.apparition_duree.setValue(animations.apparition_duree_ms)
        choisir(self.disparition, animations.disparition)
        self.disparition_duree.setValue(animations.disparition_duree_ms)
        self._chargement = False
        for attribut in self.grille_avancee.marques:
            self.grille_avancee.marquer(attribut, getattr(mot, attribut) is not None)
        anime = mot.type != ANIM_AUCUNE
        for champ in (*self._champs_animes, self.section_avancee):
            champ.setEnabled(anime)
        # Une durée qui ne sert pas : grisée, son nom compris.
        self._champ_retour_duree.setEnabled(animations.retour == RETOUR_FONDU)
        self._champ_apparition_duree.setEnabled(animations.apparition != ANIM_AUCUNE)
        self._champ_disparition_duree.setEnabled(animations.disparition != ANIM_AUCUNE)
        resume_mot = ANIMATIONS_DU_MOT.get(mot.type, "").lower()
        if anime:
            resume_mot += f", {mot.duree_ms} ms, {nombre_lisible(mot.intensite_pct)} %"
        self.sections["Mot qui devient actif"].definir_resume(resume_mot)
        self.sections["Retour"].definir_resume(RETOURS.get(animations.retour, "").lower())
        self.sections["Sous-titre entier"].definir_resume(
            f"{ANIMATIONS_DU_SOUS_TITRE.get(animations.apparition, '').lower()}, {ANIMATIONS_DU_SOUS_TITRE.get(animations.disparition, '').lower()}"
        )
