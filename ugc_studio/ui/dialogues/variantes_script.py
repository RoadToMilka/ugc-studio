"""Variantes de script (V2, lot 2, §10.9) : plusieurs scripts du même produit en un seul lancement.

Trois onglets (voir ecriture/variantes.py) :
- « Mêmes réglages » : 2 à 6 scripts du même brief, chacun sur une accroche différente ;
- « Réglages par variante » : un tableau, une colonne par variante ; chaque variante part du brief
  et ne change que ce qu'on veut comparer (les valeurs modifiées sont surlignées en mauve, comme
  dans les variantes A/B du module Voix) ;
- « Accroches seulement » : le même corps de script, 2 à 6 accroches.
Le coût total estimé s'affiche avant le lancement.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...ecriture.brief import ANGLES, DUREE_MAX, DUREE_MIN, GENRES, RESEAUX, Brief
from ...ecriture.exemples import ExempleScript
from ...ecriture.variantes import (
    ACCROCHES,
    LETTRES,
    MEMES,
    PAR_VARIANTE,
    REGLAGES,
    VARIANTES_MAX,
    VARIANTES_MIN,
    VARIANTES_PAR_DEFAUT,
    ReglagesScript,
    cout_estime,
    differences,
)
from ...estimation import MOTS_PAR_SECONDE
from ...fournisseurs.capacites import Capacite, deviner_capacites, modele_connu
from ...services import Services
from ..composants.choix_voix import choisir
from ..composants.conseils import entete_de_fenetre
from ..composants.defilement import ZoneDefilante
from ..composants.elements import bouton, champ_entier, info, libelle, liste_deroulante, vider_disposition
from ..composants.montant_label import MontantLabel
from ..composants.onglets import Onglets
from ..theme import Dimensions, Espacements, Hauteurs
from .variantes import marquer_modifie

ONGLETS = (MEMES, PAR_VARIANTE, ACCROCHES)
ONGLET_MEMES_REGLAGES, ONGLET_PAR_VARIANTE, ONGLET_ACCROCHES = range(len(ONGLETS))


def resume_du_brief(brief: Brief) -> str:
    """« TikTok · 25 s · angle au choix du modèle · Gemini 3.8 Flash »."""
    connu = modele_connu(brief.modele)
    angle = ANGLES.get(brief.angle, "") if brief.angle != "auto" else "angle au choix du modèle"
    morceaux = [RESEAUX.get(brief.reseau, brief.reseau), f"{brief.duree_visee()} s", angle, connu.nom if connu else brief.modele]
    return "  ·  ".join(m for m in morceaux if m)


def texte_d_un_reglage(nom: str, reglages: ReglagesScript, brief: Brief) -> str:
    """Valeur d'un réglage de base, telle qu'elle s'affiche dans la colonne « Brief »."""
    if nom == "angle":
        return ANGLES.get(reglages.angle, reglages.angle)
    if nom == "accroche":
        return reglages.accroche or "aucune (le modèle l'écrit)"
    if nom == "duree_s":
        return f"{reglages.duree_s} s" if reglages.duree_s else f"Auto ({brief.duree_visee()} s)"
    if nom == "reseau":
        return RESEAUX.get(reglages.reseau, reglages.reseau)
    if nom == "genre":
        return GENRES.get(reglages.genre, reglages.genre)
    if nom == "modele":
        connu = modele_connu(reglages.modele)
        return connu.nom if connu else reglages.modele
    return getattr(reglages, nom) or "vide"


@dataclass
class ColonneScript:
    """Les champs d'une variante dans le tableau (une colonne), un par réglage."""

    champs: dict[str, QWidget]


class DialogueVariantesScript(QDialog):
    """`brief` : le brief du projet (point de départ de chaque variante) ; `page`, `exemples` et
    `mots_par_seconde` : pour estimer le coût exact."""

    def __init__(
        self,
        services: Services,
        brief: Brief,
        page: str = "",
        exemples: list[ExempleScript] | None = None,
        mots_par_seconde: float = MOTS_PAR_SECONDE,
        parent=None,
    ):
        super().__init__(parent)
        self._services = services
        self._brief = Brief.depuis_dict(brief.en_dict())
        self._page = page
        self._exemples = list(exemples or [])
        self._mots_par_seconde = mots_par_seconde
        self._base = ReglagesScript.depuis_brief(self._brief)
        # Au départ : deux variantes identiques au brief (on modifie la B pour la comparer à la A).
        self._variantes: list[ReglagesScript] = [self._base.copie() for _ in range(VARIANTES_MIN)]
        self._colonnes: list[ColonneScript] = []
        self.setWindowTitle("Variantes de script")
        self.resize(Dimensions.DIALOGUE_VARIANTES_LARGEUR, Dimensions.DIALOGUE_SCRIPTS_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre("Variantes de script", "variantes-script"))
        disposition.addWidget(
            info(
                "Écris plusieurs scripts du même produit en un seul lancement, puis compare-les (« Comparer… »). "
                "Chaque script est relu avant d'arriver.",
                "secondaire",
            )
        )
        self.onglets = Onglets()
        self.onglets.addTab(self._onglet_nombre(MEMES), "Mêmes réglages")
        self.onglets.addTab(self._onglet_par_variante(), "Réglages par variante")
        self.onglets.addTab(self._onglet_nombre(ACCROCHES), "Accroches seulement")
        self.onglets.currentChanged.connect(lambda _index: self._actualiser())
        disposition.addWidget(self.onglets, 1)

        bas = QHBoxLayout()
        bas.setSpacing(Espacements.S)
        estimation = QHBoxLayout()
        estimation.setSpacing(Espacements.XS)
        self.info_cout = libelle("", "secondaire", retour_a_la_ligne=False)
        estimation.addWidget(self.info_cout)
        self.cout = MontantLabel(0)
        estimation.addWidget(self.cout)
        bas.addLayout(estimation)
        bas.addStretch(1)
        bas.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_ecrire = bouton("", variante="principal", nom_icone="pen-line", action=self.accept)
        bas.addWidget(self.bouton_ecrire)
        disposition.addLayout(bas)

        self._construire_tableau()

    # --- Onglets « Mêmes réglages » et « Accroches seulement » -----------------------------------

    def _onglet_nombre(self, mode: str) -> QWidget:
        onglet = QWidget()
        disposition = QVBoxLayout(onglet)
        disposition.setContentsMargins(0, Espacements.L, 0, 0)
        disposition.setSpacing(Espacements.M)
        if mode == MEMES:
            explication = (
                "Le modèle propose autant d'accroches que de variantes, sur des angles différents, puis écrit "
                "un script complet pour chacune : des scripts vraiment différents, du même brief."
            )
        else:
            explication = (
                "Un seul script est écrit et relu, puis le modèle propose d'autres accroches pour sa réplique 1 : "
                "le corps reste identique. Idéal pour tester des accroches, ensuite envoyées en variantes dans "
                "le module Voix."
            )
        disposition.addWidget(info(explication, "secondaire"))
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.M)
        ligne.addWidget(libelle("Nombre de variantes", retour_a_la_ligne=False))
        nombre = liste_deroulante()
        for valeur in range(VARIANTES_MIN, VARIANTES_MAX + 1):
            nombre.addItem(f"{valeur} variantes ({LETTRES[0]} à {LETTRES[valeur - 1]})", valeur)
        choisir(nombre, VARIANTES_PAR_DEFAUT)
        nombre.currentIndexChanged.connect(lambda _index: self._actualiser())
        ligne.addWidget(nombre)
        ligne.addStretch(1)
        disposition.addLayout(ligne)
        if mode == MEMES:
            self.nombre_memes = nombre
        else:
            self.nombre_accroches = nombre
        disposition.addWidget(libelle(f"Brief utilisé : {resume_du_brief(self._brief)}", "legende"))
        disposition.addStretch(1)
        return onglet

    # --- Onglet « Réglages par variante » ------------------------------------------------------

    def _onglet_par_variante(self) -> QWidget:
        onglet = QWidget()
        disposition = QVBoxLayout(onglet)
        disposition.setContentsMargins(0, Espacements.L, 0, 0)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(
            info(
                "Chaque colonne est une variante. Tout part du brief : change seulement ce que tu veux comparer "
                "(angle, accroche, durée…). Les valeurs modifiées sont surlignées en mauve.",
                "secondaire",
            )
        )
        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        self.bouton_ajouter = bouton("Ajouter une variante", variante="contour", nom_icone="plus", action=self.ajouter_variante)
        self.bouton_ajouter.setToolTip("Nouvelle variante, identique au brief (6 au maximum)")
        actions.addWidget(self.bouton_ajouter)
        actions.addStretch(1)
        disposition.addLayout(actions)
        # Le tableau peut être plus large que la fenêtre (jusqu'à 6 variantes) : il défile.
        zone = ZoneDefilante()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.Shape.NoFrame)
        interieur = QWidget()
        interieur.setObjectName("contenuDefilant")
        zone.setWidget(interieur)
        interieur.setAutoFillBackground(False)
        zone.viewport().setAutoFillBackground(False)
        enveloppe = QVBoxLayout(interieur)
        enveloppe.setContentsMargins(0, 0, 0, 0)
        self._grille = QGridLayout()
        self._grille.setHorizontalSpacing(Espacements.L)
        self._grille.setVerticalSpacing(Espacements.S)
        enveloppe.addLayout(self._grille)
        enveloppe.addStretch(1)
        disposition.addWidget(zone, 1)
        return onglet

    def _construire_tableau(self) -> None:
        vider_disposition(self._grille)
        for rang in range(self._grille.rowCount()):
            self._grille.setRowMinimumHeight(rang, 0)
        for colonne in range(self._grille.columnCount()):
            self._grille.setColumnMinimumWidth(colonne, 0)
        self._colonnes = []
        self._grille.addWidget(libelle("Brief", "intitule", retour_a_la_ligne=False), 0, 1)
        for index in range(len(self._variantes)):
            self._grille.addLayout(self._titre_colonne(index), 0, 2 + index)
        self.bouton_ajouter.setEnabled(len(self._variantes) < VARIANTES_MAX)
        for variante in self._variantes:
            self._colonnes.append(ColonneScript({nom: self._champ(nom, variante) for nom in REGLAGES}))
        for rang, (nom, titre) in enumerate(REGLAGES.items(), start=1):
            # Titre et valeur du brief centrés sur la hauteur d'un champ (sur la ligne du texte des champs).
            etiquette = libelle(titre, "legende", retour_a_la_ligne=False)
            etiquette.setFixedHeight(Hauteurs.CONTROLE)
            self._grille.addWidget(etiquette, rang, 0, Qt.AlignmentFlag.AlignTop)
            base = libelle(texte_d_un_reglage(nom, self._base, self._brief), "secondaire")
            base.setMaximumWidth(Dimensions.COLONNE_VARIANTE_LARGEUR)
            base.setMinimumHeight(Hauteurs.CONTROLE)
            base.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._grille.addWidget(base, rang, 1, Qt.AlignmentFlag.AlignTop)
            for index, colonne in enumerate(self._colonnes):
                champ = colonne.champs[nom]
                if isinstance(champ, (QComboBox, QLineEdit)):  # un champ de nombre garde sa largeur
                    champ.setFixedWidth(Dimensions.COLONNE_VARIANTE_LARGEUR)
                self._grille.addWidget(champ, rang, 2 + index, Qt.AlignmentFlag.AlignTop)
        self._grille.setColumnMinimumWidth(0, Dimensions.COLONNE_TITRES_VARIANTES_SCRIPT_LARGEUR)
        for colonne in range(1, 2 + len(self._variantes)):
            self._grille.setColumnMinimumWidth(colonne, Dimensions.COLONNE_VARIANTE_LARGEUR)
        self._actualiser()

    def _champ(self, nom: str, variante: ReglagesScript) -> QWidget:
        """Champ d'un réglage pour une variante ; chaque changement met le coût et le mauve à jour."""
        if nom in ("angle", "reseau", "genre", "modele"):
            liste = liste_deroulante()
            if nom == "angle":
                choix = ANGLES.items()
            elif nom == "reseau":
                choix = RESEAUX.items()
            elif nom == "genre":
                choix = GENRES.items()
            else:
                choix = self._modeles(variante.modele)
            for code, texte in choix:
                liste.addItem(texte, code)
            choisir(liste, getattr(variante, nom))
            liste.currentIndexChanged.connect(lambda _index: self._actualiser())
            return liste
        if nom == "duree_s":
            duree = champ_entier(0, DUREE_MAX, " s", "Durée visée. « Auto » : la durée conseillée pour le réseau")
            duree.setSpecialValueText("Auto")
            duree.setValue(variante.duree_s)
            duree.valueChanged.connect(lambda _valeur: self._actualiser())
            return duree
        texte = QLineEdit(getattr(variante, nom))
        texte.setCursorPosition(0)  # un texte long se lit depuis son début
        texte.setPlaceholderText(
            {"accroche": "le modèle l'écrit", "profil": "ex. sportive", "consigne": "ex. ton léger"}.get(nom, "")
        )
        texte.textChanged.connect(lambda _texte: self._actualiser())
        return texte

    def _modeles(self, actuel: str) -> list[tuple[str, str]]:
        """Modèles de texte chargés qui savent donner une réponse structurée (comme la liste du brief)."""
        resultat = []
        for identifiant in self._services.modeles.charges():
            if Capacite.TEXTE_STRUCTURE in deviner_capacites(identifiant):
                connu = modele_connu(identifiant)
                resultat.append((identifiant, connu.nom if connu else identifiant))
        if actuel and all(code != actuel for code, _nom in resultat):
            connu = modele_connu(actuel)
            resultat.append((actuel, connu.nom if connu else actuel))
        return resultat

    def _titre_colonne(self, index: int) -> QHBoxLayout:
        titre = QHBoxLayout()
        titre.setSpacing(Espacements.XS)
        titre.addWidget(libelle(f"Variante {LETTRES[index]}", "intitule", retour_a_la_ligne=False))
        titre.addStretch(1)
        dupliquer = bouton("", variante="icone", nom_icone="copy-plus", action=lambda: self.dupliquer_variante(index))
        dupliquer.setToolTip("Dupliquer la variante (pour en créer une voisine, avec un petit changement)")
        dupliquer.setEnabled(len(self._variantes) < VARIANTES_MAX)
        titre.addWidget(dupliquer)
        supprimer = bouton("", variante="icone", nom_icone="trash", action=lambda: self.supprimer_variante(index))
        supprimer.setToolTip("Supprimer la variante")
        supprimer.setEnabled(len(self._variantes) > VARIANTES_MIN)
        titre.addWidget(supprimer)
        return titre

    # --- Lecture des champs, différences, coût -----------------------------------------------

    def _lire_colonnes(self) -> None:
        for colonne, variante in zip(self._colonnes, self._variantes, strict=True):
            for nom, champ in colonne.champs.items():
                if isinstance(champ, QComboBox):
                    valeur = champ.currentData()
                    setattr(variante, nom, valeur if valeur is not None else getattr(variante, nom))
                elif isinstance(champ, QLineEdit):
                    setattr(variante, nom, " ".join(champ.text().split()))
                else:
                    duree = champ.value()
                    setattr(variante, nom, duree if duree == 0 or duree >= DUREE_MIN else DUREE_MIN)

    def _actualiser(self) -> None:
        if not hasattr(self, "bouton_ecrire"):
            return  # construction en cours
        self._lire_colonnes()
        for colonne, variante in zip(self._colonnes, self._variantes, strict=True):
            ecarts = differences(self._base, variante)
            for nom, champ in colonne.champs.items():
                marquer_modifie(champ, nom in ecarts)
        nombre = self.nombre()
        self.bouton_ecrire.setText(f"Écrire les {nombre} scripts")
        total = cout_estime(
            self.mode(),
            self._brief,
            self._page,
            self._exemples,
            self._services.prix,
            nombre,
            self.variantes(),
            self._mots_par_seconde,
        )
        self.info_cout.setText(f"Coût total estimé ({nombre} scripts) : ≈")
        if total is None:
            self.cout.setText("prix inconnu")
        else:
            self.cout.definir_montant(total)

    # --- Actions -----------------------------------------------------------------------------

    def ajouter_variante(self) -> None:
        if len(self._variantes) >= VARIANTES_MAX:
            return
        self._lire_colonnes()
        self._variantes.append(self._base.copie())
        self._construire_tableau()

    def dupliquer_variante(self, index: int) -> None:
        if len(self._variantes) >= VARIANTES_MAX:
            return
        self._lire_colonnes()
        self._variantes.insert(index + 1, self._variantes[index].copie())
        self._construire_tableau()

    def supprimer_variante(self, index: int) -> None:
        if len(self._variantes) <= VARIANTES_MIN:
            return
        self._lire_colonnes()
        del self._variantes[index]
        self._construire_tableau()

    def colonnes(self) -> list[ColonneScript]:
        return list(self._colonnes)

    # --- Résultat ------------------------------------------------------------------------------

    def mode(self) -> str:
        return ONGLETS[self.onglets.currentIndex()]

    def nombre(self) -> int:
        """Nombre de scripts à écrire, selon l'onglet choisi."""
        if self.mode() == PAR_VARIANTE:
            return len(self._variantes)
        liste = self.nombre_memes if self.mode() == MEMES else self.nombre_accroches
        return int(liste.currentData() or VARIANTES_PAR_DEFAUT)

    def variantes(self) -> list[ReglagesScript]:
        """Réglages de chaque variante (onglet « Réglages par variante »)."""
        return [v.copie() for v in self._variantes]
