"""Variantes A/B (§5.6) : préparer plusieurs versions du script, générées en un seul lancement.

Deux onglets :
- « Mêmes réglages » : N générations identiques ; le modèle interprète le texte un peu
  différemment à chaque fois, on garde la meilleure prise ;
- « Réglages par variante » : un tableau où chaque colonne est une variante. Tout part des
  réglages de base (ceux de l'atelier, première colonne) ; on ne change que ce qu'on veut
  comparer (modèle, voix, style ou texte d'une réplique). Les valeurs modifiées sont surlignées
  en mauve. « Dupliquer » crée une variante voisine, à modifier un peu.
Le coût total estimé s'affiche avant le lancement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...balises import FAMILLES
from ...fournisseurs.capacites import modele_connu
from ...generation import tokens_par_seconde
from ...prononciation import Prononciation
from ...script import normaliser, texte_pour_api
from ...services import Services
from ...variantes import (
    LETTRES,
    MODELE,
    STYLE,
    TEXTE,
    VARIANTES_MAX,
    VARIANTES_MIN,
    VARIANTES_PAR_DEFAUT,
    VOIX,
    ReglagesVariante,
    cout_total,
    differences,
    memes_reglages,
)
from ..composants.choix_voix import choisir, remplir_modeles_voix, remplir_voix
from ..composants.editeur_script import EditeurScript
from ..composants.elements import bouton, libelle, liste_deroulante, vider_disposition
from ..composants.montant_label import MontantLabel
from ..theme import Dimensions, Espacements

ONGLET_MEMES_REGLAGES = 0
ONGLET_PAR_VARIANTE = 1


def marquer_modifie(element: QWidget, modifie: bool) -> None:
    """Surligne en mauve (ou non) une valeur qui diffère des réglages de base."""
    if bool(element.property("modifie")) == modifie:
        return
    element.setProperty("modifie", modifie)
    element.style().unpolish(element)
    element.style().polish(element)
    element.update()


@dataclass
class ColonneVariante:
    """Les champs d'une variante dans le tableau (une colonne)."""

    modele: QComboBox
    voix: QComboBox
    styles: list[QLineEdit] = field(default_factory=list)
    textes: list[EditeurScript] = field(default_factory=list)
    bouton_supprimer: QWidget | None = None


class DialogueVariantes(QDialog):
    """`base` : les réglages de l'atelier ; `prononciations` : pour estimer le coût exact."""

    def __init__(
        self,
        services: Services,
        base: ReglagesVariante,
        prononciations: Sequence[Prononciation] = (),
        parent=None,
    ):
        super().__init__(parent)
        self._services = services
        self._base = base.copie()
        self._prononciations = list(prononciations)
        # Au départ : deux variantes identiques à la base (on modifie la B pour la comparer à la A).
        self._variantes: list[ReglagesVariante] = [base.copie() for _ in range(VARIANTES_MIN)]
        self._colonnes: list[ColonneVariante] = []
        self.setWindowTitle("Variantes A/B")
        self.resize(Dimensions.DIALOGUE_VARIANTES_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("Variantes A/B", "titre-bloc"))
        disposition.addWidget(
            libelle(
                "Génère plusieurs versions du même script en un seul lancement, puis compare-les à "
                "l'écoute. Chaque variante devient une prise.",
                "secondaire",
            )
        )
        self.onglets = QTabWidget()
        self.onglets.setDocumentMode(True)
        self.onglets.addTab(self._onglet_memes_reglages(), "Mêmes réglages")
        self.onglets.addTab(self._onglet_par_variante(), "Réglages par variante")
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
        self.bouton_generer = bouton("", variante="principal", nom_icone="audio-lines", action=self.accept)
        bas.addWidget(self.bouton_generer)
        disposition.addLayout(bas)

        self._construire_tableau()

    # --- Onglet « Mêmes réglages » -----------------------------------------------------------

    def _onglet_memes_reglages(self) -> QWidget:
        onglet = QWidget()
        disposition = QVBoxLayout(onglet)
        disposition.setContentsMargins(0, Espacements.L, 0, 0)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(
            libelle(
                "Le modèle interprète le texte un peu différemment à chaque génération : génère "
                "plusieurs prises avec exactement les mêmes réglages, écoute-les, puis garde la meilleure.",
                "secondaire",
            )
        )
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.M)
        ligne.addWidget(libelle("Nombre de variantes", retour_a_la_ligne=False))
        self.nombre = liste_deroulante()
        for nombre in range(VARIANTES_MIN, VARIANTES_MAX + 1):
            self.nombre.addItem(f"{nombre} variantes ({LETTRES[0]} à {LETTRES[nombre - 1]})", nombre)
        choisir(self.nombre, VARIANTES_PAR_DEFAUT)
        self.nombre.currentIndexChanged.connect(lambda _index: self._actualiser())
        ligne.addWidget(self.nombre)
        ligne.addStretch(1)
        disposition.addLayout(ligne)
        disposition.addWidget(libelle(f"Réglages utilisés : {self._resume_base()}.", "legende"))
        disposition.addStretch(1)
        return onglet

    def _resume_base(self) -> str:
        connu = modele_connu(self._base.modele)
        morceaux = [connu.nom if connu else self._base.modele, f"voix {self._services.voix.nom(self._base.voix)}"]
        nombre = len(self._base.repliques)
        morceaux.append(f"{nombre} réplique{'s' if nombre > 1 else ''}")
        return "  ·  ".join(morceaux)

    # --- Onglet « Réglages par variante » ----------------------------------------------------

    def _onglet_par_variante(self) -> QWidget:
        onglet = QWidget()
        disposition = QVBoxLayout(onglet)
        disposition.setContentsMargins(0, Espacements.L, 0, 0)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(
            libelle(
                "Chaque colonne est une variante. Tout part des réglages de base : change seulement ce "
                "que tu veux comparer (voix, style, modèle, texte d'une réplique…). Les valeurs "
                "modifiées sont surlignées en mauve.",
                "secondaire",
            )
        )
        # Le tableau peut être plus large que la fenêtre (jusqu'à 6 variantes) : il défile.
        zone = QScrollArea()
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
        """(Re)construit le tableau à partir des réglages de chaque variante."""
        vider_disposition(self._grille)
        # La grille garde ses anciennes lignes et colonnes (vides) : on remet leurs tailles à zéro.
        for rang in range(self._grille.rowCount()):
            self._grille.setRowMinimumHeight(rang, 0)
        for colonne in range(self._grille.columnCount()):
            self._grille.setColumnMinimumWidth(colonne, 0)
        self._colonnes = []

        # Ligne 0 : titres des colonnes.
        self._grille.addWidget(libelle("Réglages de base", "intitule", retour_a_la_ligne=False), 0, 1)
        for index in range(len(self._variantes)):
            self._grille.addLayout(self._titre_colonne(index), 0, 2 + index)
        ajouter = bouton("Ajouter", variante="discret", nom_icone="plus", action=self.ajouter_variante)
        ajouter.setToolTip("Nouvelle variante, identique aux réglages de base")
        ajouter.setEnabled(len(self._variantes) < VARIANTES_MAX)
        self._grille.addWidget(ajouter, 0, 2 + len(self._variantes), Qt.AlignmentFlag.AlignTop)

        for index, variante in enumerate(self._variantes):
            modele = liste_deroulante()
            remplir_modeles_voix(modele, self._services, variante.modele)
            voix = liste_deroulante()
            remplir_voix(voix, self._services, variante.voix)
            modele.currentIndexChanged.connect(lambda _i: self._actualiser())
            voix.currentIndexChanged.connect(lambda _i, liste=voix, autre=modele: self._voix_changee(liste, autre))
            self._colonnes.append(ColonneVariante(modele, voix))

        rang = 1
        rang = self._ligne("Modèle", self._texte_modele(self._base.modele), [c.modele for c in self._colonnes], rang)
        rang = self._ligne("Voix", self._services.voix.libelle(self._base.voix), [c.voix for c in self._colonnes], rang)
        for indice, replique in enumerate(self._base.repliques):
            self._grille.setRowMinimumHeight(rang, Espacements.L)
            rang += 1
            self._grille.addWidget(libelle(f"Réplique {indice + 1}", "intitule", retour_a_la_ligne=False), rang, 0, 1, 2)
            rang += 1
            styles = []
            textes = []
            for colonne, variante in zip(self._colonnes, self._variantes, strict=True):
                style = QLineEdit(variante.repliques[indice].style)
                style.setPlaceholderText("sans style")
                style.setToolTip("Consigne de jeu, en anglais (comme dans l'atelier)")
                style.textChanged.connect(lambda _t: self._actualiser())
                colonne.styles.append(style)
                styles.append(style)
                texte = EditeurScript(hauteur_auto=True)
                texte.setPlaceholderText("Texte de la réplique")
                texte.definir_segments(variante.repliques[indice].script)
                texte.script_modifie.connect(self._actualiser)
                colonne.textes.append(texte)
                textes.append(self._avec_outils(texte))
            base_style = replique.style.strip() or "sans style"
            rang = self._ligne("Style", base_style, styles, rang)
            rang = self._ligne("Texte", texte_pour_api(normaliser(replique.script)) or "—", textes, rang)

        self._grille.setColumnMinimumWidth(0, Dimensions.COLONNE_TITRES_VARIANTES_LARGEUR)
        for colonne in range(1, 2 + len(self._variantes)):
            self._grille.setColumnMinimumWidth(colonne, Dimensions.COLONNE_VARIANTE_LARGEUR)
        self._actualiser()

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

    def _ligne(self, titre: str, valeur_base: str, champs: list[QWidget], rang: int) -> int:
        self._grille.addWidget(libelle(titre, "legende", retour_a_la_ligne=False), rang, 0, Qt.AlignmentFlag.AlignTop)
        base = libelle(valeur_base, "secondaire")
        base.setMaximumWidth(Dimensions.COLONNE_VARIANTE_LARGEUR)
        self._grille.addWidget(base, rang, 1, Qt.AlignmentFlag.AlignTop)
        for index, champ in enumerate(champs):
            if isinstance(champ, (QComboBox, QLineEdit)):
                champ.setFixedWidth(Dimensions.COLONNE_VARIANTE_LARGEUR)
            self._grille.addWidget(champ, rang, 2 + index, Qt.AlignmentFlag.AlignTop)
        return rang + 1

    def _avec_outils(self, editeur: EditeurScript) -> QWidget:
        """Éditeur du texte d'une variante, avec « Balise » (menu par famille) et « Accentuer »."""
        zone = QWidget()
        zone.setFixedWidth(Dimensions.COLONNE_VARIANTE_LARGEUR)
        disposition = QVBoxLayout(zone)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.XS)
        disposition.addWidget(editeur)
        outils = QHBoxLayout()
        outils.setSpacing(Espacements.XS)
        balise = bouton("Balise", variante="discret", nom_icone="plus")
        balise.setToolTip("Insérer une balise (rire, pause…) à l'endroit du curseur")
        menu = QMenu(balise)
        for famille in FAMILLES:
            sous_menu = menu.addMenu(famille.nom)
            for nom in famille.balises:
                sous_menu.addAction(nom).triggered.connect(lambda _c=False, n=nom, e=editeur: e.inserer_balise(n))
        balise.setMenu(menu)
        outils.addWidget(balise)
        accent = bouton("Accentuer", variante="discret", nom_icone="case-upper", action=editeur.basculer_accent)
        accent.setToolTip("Met le mot sélectionné en valeur (MAJUSCULES pour la voix)")
        outils.addWidget(accent)
        outils.addStretch(1)
        disposition.addLayout(outils)
        return zone

    def _texte_modele(self, identifiant: str) -> str:
        connu = modele_connu(identifiant)
        return connu.nom if connu else identifiant

    def _voix_changee(self, voix: QComboBox, modele: QComboBox) -> None:
        """Une voix créée l'a été avec un modèle précis : on prend ce modèle avec elle (comme dans l'atelier)."""
        creee = self._services.voix.voix(voix.currentData() or "")
        if creee is not None and creee.creee and creee.modele:
            choisir(modele, creee.modele)
        self._actualiser()

    # --- Lecture des champs, différences, coût -----------------------------------------------

    def _lire_colonnes(self) -> None:
        """Recopie le contenu des champs dans les réglages de chaque variante."""
        for colonne, variante in zip(self._colonnes, self._variantes, strict=True):
            variante.modele = colonne.modele.currentData() or variante.modele
            variante.voix = colonne.voix.currentData() or variante.voix
            for indice, (style, texte) in enumerate(zip(colonne.styles, colonne.textes, strict=True)):
                variante.repliques[indice].style = style.text().strip()
                variante.repliques[indice].style_fr = (
                    self._base.repliques[indice].style_fr if style.text().strip() == self._base.repliques[indice].style.strip() else ""
                )
                variante.repliques[indice].script = texte.segments()

    def _actualiser(self) -> None:
        if not hasattr(self, "bouton_generer"):
            return  # construction en cours
        self._lire_colonnes()
        for colonne, variante in zip(self._colonnes, self._variantes, strict=True):
            ecarts = differences(self._base, variante)
            marquer_modifie(colonne.modele, (MODELE, -1) in ecarts)
            marquer_modifie(colonne.voix, (VOIX, -1) in ecarts)
            for indice, (style, texte) in enumerate(zip(colonne.styles, colonne.textes, strict=True)):
                marquer_modifie(style, (STYLE, indice) in ecarts)
                marquer_modifie(texte, (TEXTE, indice) in ecarts)
        variantes = self.variantes()
        nombre = len(variantes)
        self.bouton_generer.setText(f"Générer les {nombre} variantes")
        total = cout_total(
            variantes,
            self._services.prix,
            self._prononciations,
            lambda modele: tokens_par_seconde(self._services, modele),
        )
        self.info_cout.setText(f"Coût total estimé ({nombre} variantes) : ≈")
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

    def colonnes(self) -> list[ColonneVariante]:
        return list(self._colonnes)

    def variantes(self) -> list[ReglagesVariante]:
        """Les variantes à générer, selon l'onglet choisi."""
        if self.onglets.currentIndex() == ONGLET_MEMES_REGLAGES:
            return memes_reglages(self._base, int(self.nombre.currentData() or VARIANTES_PAR_DEFAUT))
        self._lire_colonnes()
        return [v.copie() for v in self._variantes]
