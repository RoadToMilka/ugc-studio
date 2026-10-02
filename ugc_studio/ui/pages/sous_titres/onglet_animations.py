"""Onglet « Animations » du studio des sous-titres (V2, lot 6 ; cahier des charges §7.5 et §7.12).

- Quand un mot devient actif : aucune, pop, rebond, zoom, fondu ou glissement vers le haut ; durée
  et intensité. Réglages avancés : taille de départ, au sommet et d'arrivée, opacité et décalage de
  départ, courbe (douce, rebond ou régulière) ; tant qu'on ne les change pas, ce sont ceux de
  l'animation choisie.
- Quand il redevient « déjà dit » : instantané ou fondu (durée).
- Sous-titre entier : apparition et disparition (aucune, fondu, pop, zoom, glissement vers le haut
  ou vers le bas), chacune avec sa durée.

Les animations ne changent jamais les temps des sous-titres : l'apparition commence au début du
sous-titre, la disparition se termine à sa fin.

V3.1 : la référence est le préréglage du projet tel qu'il est enregistré (sans lui, le style de
départ, sans animation) ; un réglage qui s'en écarte a son nom en mauve, et le ↺ de son groupe
apparaît à côté du titre (un clic remet le groupe comme dans le préréglage). Jusqu'à la 3.0.3 : un ↺
au bout de chaque réglage avancé changé (« comme l'animation choisie »), et un résumé à côté du titre
d'un groupe fermé.
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
from .onglet_texte import HAUTEUR_PAR_DEFAUT, RETABLIR, ChampExact, ChampPixels
from .reglages_communs import GrilleDeReglages, marque_de, marquer, meme_valeur, valeur_au_chemin

PAS_DUREE_MS = 10
# Groupes de l'onglet → réglages des animations qu'ils contiennent (ce que leur ↺ remet).
GROUPES = {
    "Mot qui devient actif": ("mot",),
    "Retour": ("retour", "retour_duree_ms"),
    "Sous-titre entier": ("apparition", "apparition_duree_ms", "disparition", "disparition_duree_ms"),
}


def _duree(minimum_maximum: tuple[int, int], info_champ: str):
    champ = champ_entier(*minimum_maximum, " ms", info_champ)
    champ.setSingleStep(PAS_DUREE_MS)
    return champ


class OngletAnimations(QWidget):
    change = Signal()  # une animation a changé (la page vérifie le découpage, puis l'applique)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._animations = Animations()
        self._reference = Animations()  # ce que les ↺ remettent : les animations du préréglage (V3.1)
        self._marques: list[tuple] = []  # (nom, chemin du réglage dans les animations)
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
        self._marques.append((marque_de(grille.ligne("Animation", self.type)), "mot.type"))
        self.duree = _duree(AnimationMot.LIMITES["duree_ms"], "Durée de l'animation")
        self.duree.valueChanged.connect(lambda valeur: self._mot(duree_ms=valeur))
        self.intensite = ChampExact(champ_decimal(*AnimationMot.LIMITES["intensite_pct"], 10, 0, " %", "Plus ou moins marquée"))
        self.intensite.champ.valueChanged.connect(lambda _valeur: self._mot(intensite_pct=self.intensite.valeur()))
        self._champs_animes = (grille.ligne("Durée", self.duree), grille.ligne("Intensité", self.intensite.champ))
        self._marques += [(marque_de(self._champs_animes[0]), "mot.duree_ms"), (marque_de(self._champs_animes[1]), "mot.intensite_pct")]
        avances = SectionRepliable("Réglages avancés")
        self.section_avancee = avances
        # Chaque réglage avancé vaut « comme l'animation choisie » (None) tant qu'on ne le change pas.
        self.grille_avancee = GrilleEtat(avances.contenu)
        self.taille_depart = self._pourcentage("taille_depart_pct", "Taille du mot au début de l'animation")
        self.grille_avancee.ligne("Taille de départ", self.taille_depart.champ, "taille_depart_pct")
        self.taille_sommet = self._pourcentage("taille_sommet_pct", "Taille du mot au plus fort de l'animation")
        self.grille_avancee.ligne("Taille au sommet", self.taille_sommet.champ, "taille_sommet_pct")
        self.taille_arrivee = self._pourcentage("taille_arrivee_pct", "Taille du mot à la fin de l'animation")
        self.grille_avancee.ligne("Taille d'arrivée", self.taille_arrivee.champ, "taille_arrivee_pct")
        self.opacite_depart = self._pourcentage("opacite_depart_pct", "Opacité du mot au début de l'animation")
        self.grille_avancee.ligne("Opacité de départ", self.opacite_depart.champ, "opacite_depart_pct")
        self.decalage_depart = ChampPixels(AnimationMot.LIMITES["decalage_depart_pct"], "Décalage de départ, vers le bas (négatif : vers le haut)")
        self.decalage_depart.champ.valueChanged.connect(lambda _valeur: self._mot(decalage_depart_pct=self.decalage_depart.valeur()))
        self.grille_avancee.ligne("Décalage de départ", self.decalage_depart.champ, "decalage_depart_pct")
        self.courbe = liste_deroulante("Douce : ralentit à l'arrivée ; rebond : dépasse un peu, puis revient")
        for code, nom in COURBES.items():
            self.courbe.addItem(nom, code)
        self.courbe.currentIndexChanged.connect(lambda _index: self._mot(courbe=self.courbe.currentData()))
        self.grille_avancee.ligne("Courbe", self.courbe, "courbe")
        self._marques += [(marque, f"mot.{attribut}") for attribut, marque in self.grille_avancee.marques.items()]
        section.contenu.addWidget(avances)
        disposition.addWidget(section)

        # Retour à « déjà dit ».
        section = SectionRepliable("Retour à « déjà dit »", True)
        self.sections["Retour"] = section
        retour = GrilleDeReglages()
        self.retour = ChoixEnBoutons(RETOURS, "Quand le mot suivant devient actif")
        self.retour.change.connect(lambda valeur: self._modifier(retour=valeur))
        self._marques.append((marque_de(retour.ajouter("Transition", self.retour)), "retour"))
        self.retour_duree = _duree(Animations.LIMITES["retour_duree_ms"], "Durée du fondu")
        self.retour_duree.valueChanged.connect(lambda valeur: self._modifier(retour_duree_ms=valeur))
        self._champ_retour_duree = retour.ajouter("Durée", self.retour_duree)
        self._marques.append((marque_de(self._champ_retour_duree), "retour_duree_ms"))
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
        for titre, section in self.sections.items():
            section.ajouter_retablir(lambda groupe=titre: self._retablir(groupe), RETABLIR)
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
        champ_liste = ChampNomme(titre, liste)
        ligne.addWidget(champ_liste)
        champ_duree = ChampNomme("Durée", duree)
        ligne.addWidget(champ_duree)
        grille.addWidget(paire)
        self._marques += [(marque_de(champ_liste), attribut), (marque_de(champ_duree), f"{attribut}_duree_ms")]
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

    def definir_reference(self, animations: Animations, infobulle: str = RETABLIR) -> None:
        """La référence (V3.1) : les animations du préréglage du projet, telles qu'enregistrées (sans
        préréglage, celles du style de départ : aucune). `infobulle` : ce que disent les ↺."""
        self._reference = animations
        for section in self.sections.values():
            section.retablir.setToolTip(infobulle)
        self._actualiser_marques()

    def _retablir(self, groupe: str) -> None:
        """↺ d'un groupe : ses réglages comme dans le préréglage (réglages avancés compris)."""
        self._modifier(**{nom: getattr(self._reference, nom) for nom in GROUPES[groupe]})

    def _actualiser_marques(self) -> None:
        animations, reference = self._animations, self._reference
        for element, chemin in self._marques:
            marquer(element, not meme_valeur(valeur_au_chemin(animations, chemin), valeur_au_chemin(reference, chemin)))
        for titre, noms in GROUPES.items():
            ecart = any(not meme_valeur(getattr(animations, nom), getattr(reference, nom)) for nom in noms)
            self.sections[titre].montrer_retablir(ecart)

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
        self._actualiser_marques()
        anime = mot.type != ANIM_AUCUNE
        for champ in (*self._champs_animes, self.section_avancee):
            champ.setEnabled(anime)
        # Une durée qui ne sert pas : grisée, son nom compris.
        self._champ_retour_duree.setEnabled(animations.retour == RETOUR_FONDU)
        self._champ_apparition_duree.setEnabled(animations.apparition != ANIM_AUCUNE)
        self._champ_disparition_duree.setEnabled(animations.disparition != ANIM_AUCUNE)
