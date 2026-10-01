"""Onglet « Texte » du studio des sous-titres (V2, lot 4 ; cahier des charges §7.4 et §7.9) : tout ce
qui vaut pour tous les mots.

Groupes (chacun se replie ; ses réglages rares attendent dans « Réglages avancés ») : Police, Taille
et casse, Remplissage, Contour, Ombre, Lueur, Fond, Espaces. Chaque groupe a son bouton « Rétablir »
(les valeurs de départ des nouveaux projets). Les réglages d'un effet décoché (contour, ombre…) sont
grisés : on voit ce qu'il y a à régler, sans le confondre avec ce qui est actif.

Les tailles sont montrées en pixels de la vidéo actuelle (« Contour : 6 px ») et rangées en % de sa
hauteur : un style garde le même aspect dans tous les formats. Une valeur qu'on ne touche pas reste
exactement celle du projet (un champ n'affiche qu'un chiffre après la virgule) : changer une couleur
ne refait jamais le découpage.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ....rendu.polices import NOMS_GRAISSES, ErreurPolice, existe, familles, graisse_proche, graisses, importer_police
from ....style_sous_titres import (
    ANGLES,
    CASSES,
    DIRECTIONS,
    FOND_AUCUN,
    FONDS,
    PORTEES,
    Contour,
    Degrade,
    Espaces,
    Fond,
    Lueur,
    Ombre,
    StyleTexte,
    style_de_depart,
)
from ...composants.champ_couleur import ChampCouleur
from ...composants.choix import ChoixEnBoutons
from ...composants.choix_voix import choisir
from ...composants.elements import bouton, case_a_cocher, champ_decimal, info, libelle, liste_deroulante
from ...composants.section_repliable import SectionRepliable
from ...theme import Espacements, Typo
from .reglages_communs import grille, nombre_lisible

HAUTEUR_PAR_DEFAUT = 1920


class ChampExact:
    """Un champ à virgule qui rend la valeur exacte du projet tant qu'on ne le change pas (il n'en
    affiche qu'un arrondi). `facteur` : valeur affichée = valeur rangée × facteur."""

    def __init__(self, champ, facteur: float = 1.0):
        self.champ = champ
        self.facteur = facteur
        self._exacte = 0.0
        self._affichee: float | None = None

    def definir(self, valeur: float) -> None:
        self._exacte = valeur
        self.champ.setValue(valeur * self.facteur)
        self._affichee = self.champ.value()

    def valeur(self) -> float:
        if self._affichee is not None and self.champ.value() == self._affichee:
            return self._exacte
        # Trois chiffres après la virgule, comme dans le projet (style_sous_titres.en_dict) : la
        # valeur utilisée est celle qui sera relue.
        return round(self.champ.value() / self.facteur, 3)


class ChampPixels(ChampExact):
    """Champ en pixels de la vidéo actuelle, rangé en % de sa hauteur."""

    def __init__(self, limites_pct: tuple[float, float], info_champ: str, pas: float = 0.5):
        super().__init__(champ_decimal(0.0, 1.0, pas, 1, " px", info_champ), HAUTEUR_PAR_DEFAUT / 100)
        self.limites = limites_pct

    def definir_hauteur(self, hauteur: int) -> None:
        self.facteur = max(1, hauteur) / 100
        self.champ.setRange(self.limites[0] * self.facteur, self.limites[1] * self.facteur)

    def texte(self) -> str:
        return f"{nombre_lisible(self.champ.value())} px"


def _zone(contenu) -> QWidget:
    """Rangée de réglages qu'on grise d'un coup (libellés compris)."""
    zone = QWidget()
    zone.setLayout(contenu)
    contenu.setContentsMargins(0, 0, 0, 0)
    return zone


class OngletTexte(QWidget):
    change = Signal()  # un réglage du texte a changé (la page vérifie le découpage, puis l'applique)
    pipette_demandee = Signal(object)  # un champ couleur attend une couleur prise dans l'aperçu

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._hauteur = HAUTEUR_PAR_DEFAUT
        self._style = StyleTexte()
        self._chargement = False
        self._liste_des_polices: tuple | None = None  # ce que montre la liste (pour ne la refaire qu'au besoin)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.L, 0, 0)
        disposition.setSpacing(Espacements.M)
        self.police_absente = libelle("", "legende-avertissement")
        self.police_absente.hide()
        disposition.addWidget(self.police_absente)
        self.sections: dict[str, SectionRepliable] = {}
        for titre, construire, ouverte in (
            ("Police", self._groupe_police, True),
            ("Taille et casse", self._groupe_taille, True),
            ("Remplissage", self._groupe_remplissage, True),
            ("Contour", self._groupe_contour, False),
            ("Ombre", self._groupe_ombre, False),
            ("Lueur", self._groupe_lueur, False),
            ("Fond", self._groupe_fond, False),
            ("Espaces", self._groupe_espaces, False),
        ):
            section = SectionRepliable(titre, ouverte)
            construire(section.contenu)
            self.sections[titre] = section
            disposition.addWidget(section)
        disposition.addStretch(1)
        self._actualiser_etats()

    # --- Construction --------------------------------------------------------------------------

    def _signaler(self, *_arguments) -> None:
        self._actualiser_etats()
        if not self._chargement:
            self.change.emit()

    def _bouton_retablir(self, contenu: QVBoxLayout, action) -> None:
        ligne = QHBoxLayout()
        retablir = bouton("Rétablir", variante="contour", nom_icone="rotate-ccw", action=action)
        retablir.setToolTip("Revenir aux valeurs de départ des nouveaux projets")
        ligne.addWidget(retablir)
        ligne.addStretch(1)
        contenu.addLayout(ligne)

    def _couleur(self, info_champ: str) -> ChampCouleur:
        champ = ChampCouleur(info_champ)
        champ.change.connect(self._signaler)
        champ.pipette_demandee.connect(self.pipette_demandee.emit)
        return champ

    def _pixels(self, limites: tuple[float, float], info_champ: str) -> ChampPixels:
        champ = ChampPixels(limites, info_champ)
        champ.champ.valueChanged.connect(self._signaler)
        return champ

    def _decimal(self, limites: tuple[float, float], pas: float, decimales: int, suffixe: str, info_champ: str) -> ChampExact:
        champ = ChampExact(champ_decimal(*limites, pas, decimales, suffixe, info_champ))
        champ.champ.valueChanged.connect(self._signaler)
        return champ

    def _groupe_police(self, contenu: QVBoxLayout) -> None:
        self.recherche_police = QLineEdit()
        self.recherche_police.setPlaceholderText("Nom de police")  # court : tient dans le champ, sans « … »
        self.recherche_police.setClearButtonEnabled(True)
        self.recherche_police.textChanged.connect(lambda _texte: self._remplir_polices())
        self.police = liste_deroulante("Polices fournies, puis importées et de Windows (tape une lettre pour y sauter)")
        self.police.activated.connect(lambda _index: self._police_choisie())
        self.graisse = liste_deroulante("Graisse : les épaisseurs que propose la police")
        self.graisse.activated.connect(self._signaler)
        contenu.addLayout(grille((("Rechercher", self.recherche_police), ("Police", self.police), ("Graisse", self.graisse))))
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.bouton_importer = bouton("Importer une police…", variante="contour", nom_icone="type", action=self.importer_police)
        ligne.addWidget(self.bouton_importer)
        ligne.addStretch(1)
        contenu.addLayout(ligne)
        self.statut_police = libelle("", "legende-erreur")
        self.statut_police.hide()
        contenu.addWidget(self.statut_police)
        contenu.addWidget(
            info(
                "Polices fournies : libres pour la publicité (licence SIL OFL). Une police de Windows ou importée a "
                "sa propre licence : vérifie qu'elle autorise un usage commercial."
            )
        )
        self._bouton_retablir(contenu, lambda: self._retablir(police=True))

    def _groupe_taille(self, contenu: QVBoxLayout) -> None:
        self.taille = self._decimal(StyleTexte.LIMITES["taille_pct"], 0.1, 1, " %", "Taille du texte, en % de la hauteur de la vidéo")
        self.taille_px = libelle("", "legende", retour_a_la_ligne=False)
        ligne_taille = QHBoxLayout()
        ligne_taille.setSpacing(Espacements.S)
        ligne_taille.addWidget(self.taille.champ)
        ligne_taille.addWidget(self.taille_px)
        self.casse = liste_deroulante("Affichage seulement : le texte des mots ne change pas")
        for code, nom in CASSES.items():
            self.casse.addItem(nom, code)
        contenu.addLayout(grille((("Taille du texte", ligne_taille), ("Casse", self.casse))))
        zone, self.ponctuation = case_a_cocher("Afficher la ponctuation")
        contenu.addWidget(zone)
        self.casse.currentIndexChanged.connect(self._signaler)
        self.ponctuation.toggled.connect(self._signaler)
        self._bouton_retablir(contenu, lambda: self._retablir(taille=True))

    def _groupe_remplissage(self, contenu: QVBoxLayout) -> None:
        self.couleur = self._couleur("Couleur du texte (la première du dégradé)")
        contenu.addLayout(grille((("Couleur", self.couleur),)))
        zone, self.degrade = case_a_cocher("Dégradé de deux couleurs")
        self.degrade.toggled.connect(self._signaler)
        contenu.addWidget(zone)
        self.couleur_2 = self._couleur("Seconde couleur du dégradé")
        self.direction = ChoixEnBoutons(DIRECTIONS, "Sens du dégradé, sur chaque ligne")
        self.direction.change.connect(self._signaler)
        self.zone_degrade = _zone(grille((("Seconde couleur", self.couleur_2), ("Sens", self.direction))))
        contenu.addWidget(self.zone_degrade)
        self._bouton_retablir(contenu, lambda: self._retablir(remplissage=True))

    def _groupe_contour(self, contenu: QVBoxLayout) -> None:
        zone, self.contour = case_a_cocher("Contour autour des lettres")
        self.contour.toggled.connect(self._signaler)
        contenu.addWidget(zone)
        self.contour_couleur = self._couleur("Couleur du contour")
        self.contour_epaisseur = self._pixels(Contour.LIMITES["epaisseur_pct"], "Épaisseur du contour, autour des lettres")
        self.contour_angles = ChoixEnBoutons(ANGLES, "Angles du contour : arrondis ou nets")
        self.contour_angles.change.connect(self._signaler)
        avances = SectionRepliable("Réglages avancés")
        avances.contenu.addLayout(grille((("Angles", self.contour_angles),)))
        self.zone_contour = QWidget()
        rangees = QVBoxLayout(self.zone_contour)
        rangees.setContentsMargins(0, 0, 0, 0)
        rangees.setSpacing(Espacements.M)
        rangees.addLayout(grille((("Couleur", self.contour_couleur), ("Épaisseur", self.contour_epaisseur.champ))))
        rangees.addWidget(avances)
        contenu.addWidget(self.zone_contour)
        self._bouton_retablir(contenu, lambda: self._retablir(contour=True))

    def _groupe_ombre(self, contenu: QVBoxLayout) -> None:
        zone, self.ombre = case_a_cocher("Ombre portée")
        self.ombre.toggled.connect(self._signaler)
        contenu.addWidget(zone)
        self.ombre_couleur = self._couleur("Couleur de l'ombre (son opacité : la force de l'ombre)")
        self.ombre_flou = self._pixels(Ombre.LIMITES["flou_pct"], "Flou de l'ombre")
        self.ombre_x = self._pixels(Ombre.LIMITES["decalage_x_pct"], "Décalage vers la droite (négatif : vers la gauche)")
        self.ombre_y = self._pixels(Ombre.LIMITES["decalage_y_pct"], "Décalage vers le bas (négatif : vers le haut)")
        self.ombre_portee = ChoixEnBoutons(PORTEES, "L'ombre suit les lettres, ou le fond derrière elles")
        self.ombre_portee.change.connect(self._signaler)
        avances = SectionRepliable("Réglages avancés")
        avances.contenu.addLayout(grille((("Portée", self.ombre_portee),)))
        self.zone_ombre = QWidget()
        rangees = QVBoxLayout(self.zone_ombre)
        rangees.setContentsMargins(0, 0, 0, 0)
        rangees.setSpacing(Espacements.M)
        rangees.addLayout(
            grille(
                (
                    ("Couleur", self.ombre_couleur),
                    ("Flou", self.ombre_flou.champ),
                    ("Décalage horizontal", self.ombre_x.champ),
                    ("Décalage vertical", self.ombre_y.champ),
                )
            )
        )
        rangees.addWidget(avances)
        contenu.addWidget(self.zone_ombre)
        self._bouton_retablir(contenu, lambda: self._retablir(ombre=True))

    def _groupe_lueur(self, contenu: QVBoxLayout) -> None:
        zone, self.lueur = case_a_cocher("Lueur autour des lettres")
        self.lueur.toggled.connect(self._signaler)
        contenu.addWidget(zone)
        self.lueur_couleur = self._couleur("Couleur de la lueur")
        self.lueur_taille = self._pixels(Lueur.LIMITES["taille_pct"], "Taille de la lueur")
        self.lueur_intensite = self._decimal(Lueur.LIMITES["intensite_pct"], 5, 0, " %", "Intensité de la lueur")
        self.zone_lueur = _zone(
            grille((("Couleur", self.lueur_couleur), ("Taille", self.lueur_taille.champ), ("Intensité", self.lueur_intensite.champ)))
        )
        contenu.addWidget(self.zone_lueur)
        self._bouton_retablir(contenu, lambda: self._retablir(lueur=True))

    def _groupe_fond(self, contenu: QVBoxLayout) -> None:
        self.fond = liste_deroulante("Fond derrière le texte")
        for code, nom in FONDS.items():
            self.fond.addItem(nom, code)
        self.fond.currentIndexChanged.connect(self._signaler)
        contenu.addLayout(grille((("Fond", self.fond),)))
        self.fond_couleur = self._couleur("Couleur du fond")
        self.fond_marge_x = self._pixels(Fond.LIMITES["marge_x_pct"], "Marge intérieure à gauche et à droite du texte")
        self.fond_marge_y = self._pixels(Fond.LIMITES["marge_y_pct"], "Marge intérieure en haut et en bas du texte")
        self.fond_arrondi = self._pixels(Fond.LIMITES["arrondi_pct"], "Arrondi des coins du fond")
        zone, self.fond_bordure = case_a_cocher("Bordure autour du fond")
        self.fond_bordure.toggled.connect(self._signaler)
        self.fond_bordure_couleur = self._couleur("Couleur de la bordure")
        self.fond_bordure_epaisseur = self._pixels(Fond.LIMITES["bordure_epaisseur_pct"], "Épaisseur de la bordure")
        self.zone_bordure = _zone(
            grille((("Couleur", self.fond_bordure_couleur), ("Épaisseur", self.fond_bordure_epaisseur.champ)))
        )
        avances = SectionRepliable("Réglages avancés")
        avances.contenu.addWidget(zone)
        avances.contenu.addWidget(self.zone_bordure)
        self.zone_fond = QWidget()
        rangees = QVBoxLayout(self.zone_fond)
        rangees.setContentsMargins(0, 0, 0, 0)
        rangees.setSpacing(Espacements.M)
        rangees.addLayout(
            grille(
                (
                    ("Couleur", self.fond_couleur),
                    ("Marge horizontale", self.fond_marge_x.champ),
                    ("Marge verticale", self.fond_marge_y.champ),
                    ("Arrondi", self.fond_arrondi.champ),
                )
            )
        )
        rangees.addWidget(avances)
        contenu.addWidget(self.zone_fond)
        self._bouton_retablir(contenu, lambda: self._retablir(fond=True))

    def _groupe_espaces(self, contenu: QVBoxLayout) -> None:
        self.interligne = self._decimal(Espaces.LIMITES["interligne_pct"], 5, 0, " %", "Interlignage, en % de celui de la police")
        self.lettres = self._pixels(Espaces.LIMITES["lettres_pct"], "Espace ajouté entre les lettres (négatif : plus serré)")
        self.mots = self._pixels(Espaces.LIMITES["mots_pct"], "Espace ajouté entre les mots (négatif : plus serré)")
        contenu.addLayout(
            grille(
                (
                    ("Interlignage", self.interligne.champ),
                    ("Entre les lettres", self.lettres.champ),
                    ("Entre les mots", self.mots.champ),
                )
            )
        )
        self._bouton_retablir(contenu, lambda: self._retablir(espaces=True))

    def _actualiser_etats(self) -> None:
        """Réglages d'un effet décoché : grisés."""
        self.zone_degrade.setEnabled(self.degrade.isChecked())
        self.zone_contour.setEnabled(self.contour.isChecked())
        self.zone_ombre.setEnabled(self.ombre.isChecked())
        self.zone_lueur.setEnabled(self.lueur.isChecked())
        self.zone_fond.setEnabled(self.fond.currentData() not in (None, FOND_AUCUN))
        self.zone_bordure.setEnabled(self.fond_bordure.isChecked())

    # --- Polices -------------------------------------------------------------------------------

    def _remplir_polices(self) -> None:
        """Liste des polices, filtrée par la recherche ; la police du style y reste toujours. Elle
        n'est refaite que si la recherche, la police du style ou les polices de l'ordinateur ont changé
        (des centaines sous Windows)."""
        recherche = self.recherche_police.text().strip().casefold()
        actuelle = self._style.police
        toutes = familles()
        cle = (recherche, actuelle, tuple(toutes))
        if cle == self._liste_des_polices:
            choisir(self.police, actuelle)
            return
        self._liste_des_polices = cle
        self.police.blockSignals(True)
        self.police.clear()
        for famille in toutes:
            if recherche and recherche not in famille.casefold() and famille != actuelle:
                continue
            self.police.addItem(famille, famille)
            # Le nom s'écrit dans sa police (son aperçu), sauf une police de symboles, illisible.
            if QFontDatabase.WritingSystem.Latin in QFontDatabase.writingSystems(famille):
                apercu = QFont(famille)
                apercu.setPixelSize(Typo.COURANT)
                self.police.setItemData(self.police.count() - 1, apercu, Qt.ItemDataRole.FontRole)
        if self.police.findData(actuelle) < 0:  # police introuvable sur cet ordinateur : elle reste affichée
            self.police.insertItem(0, f"{actuelle} (absente)", actuelle)
        choisir(self.police, actuelle)
        self.police.blockSignals(False)

    def _remplir_graisses(self, famille: str, graisse: int) -> None:
        """Graisses de la police. Police absente de cet ordinateur : seulement celle du style (elle
        est gardée telle quelle, pour l'ordinateur où la police existe)."""
        self.graisse.blockSignals(True)
        self.graisse.clear()
        for valeur in graisses(famille) if existe(famille) else [graisse]:
            self.graisse.addItem(f"{NOMS_GRAISSES.get(valeur, str(valeur))} ({valeur})", valeur)
        index = self.graisse.findData(graisse_proche(famille, graisse) if existe(famille) else graisse)
        self.graisse.setCurrentIndex(max(index, 0))
        self.graisse.blockSignals(False)

    def _police_choisie(self) -> None:
        famille = self.police.currentData()
        if not famille:
            return
        self._remplir_graisses(famille, self.graisse.currentData() or self._style.graisse)
        self._signaler()

    def importer_police(self) -> None:
        choix, _filtre = QFileDialog.getOpenFileName(self, "Importer une police", "", "Polices (*.ttf *.otf)")
        if not choix:
            return
        self.importer_fichier(Path(choix))

    def importer_fichier(self, chemin: Path) -> None:
        """La police est copiée dans le dossier de l'app, puis choisie."""
        try:
            famille = importer_police(chemin)
        except ErreurPolice as erreur:
            self.statut_police.setText(str(erreur))
            self.statut_police.show()
            return
        self.statut_police.hide()
        self._style = replace(self._style, police=famille)
        self._remplir_polices()
        self._remplir_graisses(famille, self._style.graisse)
        self._signaler()

    # --- Lecture et écriture -------------------------------------------------------------------

    def charger(self, style: StyleTexte, hauteur_video: int, taille_px: int, police_remplacee: bool) -> None:
        """Montre le style du projet, avec les tailles en pixels de cette vidéo."""
        self._chargement = True
        self._style = style
        self._hauteur = max(1, hauteur_video)
        for champ in (
            self.contour_epaisseur, self.ombre_flou, self.ombre_x, self.ombre_y, self.lueur_taille,
            self.fond_marge_x, self.fond_marge_y, self.fond_arrondi, self.fond_bordure_epaisseur, self.lettres, self.mots,
        ):
            champ.definir_hauteur(self._hauteur)
        self._remplir_polices()
        self._remplir_graisses(style.police, style.graisse)
        self.taille.definir(style.taille_pct)
        self.taille_px.setText(f"{taille_px} px")
        choisir(self.casse, style.casse)
        self.ponctuation.setChecked(style.ponctuation)
        self.couleur.definir(style.couleur)
        self.degrade.setChecked(style.degrade.actif)
        self.couleur_2.definir(style.degrade.couleur)
        self.direction.definir(style.degrade.direction)
        self.contour.setChecked(style.contour.actif)
        self.contour_couleur.definir(style.contour.couleur)
        self.contour_epaisseur.definir(style.contour.epaisseur_pct)
        self.contour_angles.definir(style.contour.angles)
        self.ombre.setChecked(style.ombre.active)
        self.ombre_couleur.definir(style.ombre.couleur)
        self.ombre_flou.definir(style.ombre.flou_pct)
        self.ombre_x.definir(style.ombre.decalage_x_pct)
        self.ombre_y.definir(style.ombre.decalage_y_pct)
        self.ombre_portee.definir(style.ombre.portee)
        self.lueur.setChecked(style.lueur.active)
        self.lueur_couleur.definir(style.lueur.couleur)
        self.lueur_taille.definir(style.lueur.taille_pct)
        self.lueur_intensite.definir(style.lueur.intensite_pct)
        choisir(self.fond, style.fond.mode)
        self.fond_couleur.definir(style.fond.couleur)
        self.fond_marge_x.definir(style.fond.marge_x_pct)
        self.fond_marge_y.definir(style.fond.marge_y_pct)
        self.fond_arrondi.definir(style.fond.arrondi_pct)
        self.fond_bordure.setChecked(style.fond.bordure)
        self.fond_bordure_couleur.definir(style.fond.bordure_couleur)
        self.fond_bordure_epaisseur.definir(style.fond.bordure_epaisseur_pct)
        self.interligne.definir(style.espaces.interligne_pct)
        self.lettres.definir(style.espaces.lettres_pct)
        self.mots.definir(style.espaces.mots_pct)
        self._chargement = False
        self._actualiser_etats()
        self.police_absente.setText(
            f"La police « {style.police} » n'est pas installée sur cet ordinateur : Inter la remplace (le style garde son nom)."
        )
        self.police_absente.setVisible(police_remplacee)
        self._actualiser_resumes()

    def _actualiser_resumes(self) -> None:
        """Résumé de chaque groupe replié (ex. pour le contour : son code couleur et « 6 px »)."""
        style = self._style
        resumes = {
            "Contour": f"{style.contour.couleur.code}, {self.contour_epaisseur.texte()}" if style.contour.actif else "aucun",
            "Ombre": f"{style.ombre.couleur.code} à {round(style.ombre.couleur.opacite)} %" if style.ombre.active else "aucune",
            "Lueur": f"{style.lueur.couleur.code}, {self.lueur_taille.texte()}" if style.lueur.active else "aucune",
            "Fond": FONDS.get(style.fond.mode, "").lower(),
            "Espaces": f"interlignage {nombre_lisible(style.espaces.interligne_pct)} %",
        }
        for titre, resume in resumes.items():
            self.sections[titre].definir_resume(resume)

    def style(self, base: StyleTexte) -> StyleTexte:
        """Style tel que réglé dans l'onglet."""
        famille = self.police.currentData() or base.police
        return StyleTexte(
            police=famille,
            graisse=int(self.graisse.currentData() or base.graisse),
            taille_pct=self.taille.valeur(),
            casse=self.casse.currentData() or base.casse,
            ponctuation=self.ponctuation.isChecked(),
            couleur=self.couleur.couleur(),
            degrade=Degrade(self.degrade.isChecked(), self.couleur_2.couleur(), self.direction.valeur() or base.degrade.direction),
            contour=Contour(
                self.contour.isChecked(), self.contour_couleur.couleur(), self.contour_epaisseur.valeur(),
                self.contour_angles.valeur() or base.contour.angles,
            ),
            ombre=Ombre(
                self.ombre.isChecked(), self.ombre_couleur.couleur(), self.ombre_flou.valeur(),
                self.ombre_x.valeur(), self.ombre_y.valeur(), self.ombre_portee.valeur() or base.ombre.portee,
            ),
            lueur=Lueur(self.lueur.isChecked(), self.lueur_couleur.couleur(), self.lueur_taille.valeur(), self.lueur_intensite.valeur()),
            fond=Fond(
                self.fond.currentData() or base.fond.mode, self.fond_couleur.couleur(), self.fond_marge_x.valeur(),
                self.fond_marge_y.valeur(), self.fond_arrondi.valeur(), self.fond_bordure.isChecked(),
                self.fond_bordure_couleur.couleur(), self.fond_bordure_epaisseur.valeur(),
            ),
            espaces=Espaces(self.interligne.valeur(), self.lettres.valeur(), self.mots.valeur()),
        )

    def _retablir(self, **groupes) -> None:
        """« Rétablir » : ce groupe reprend les valeurs de départ des nouveaux projets."""
        depart, actuel = style_de_depart(), self.style(self._style)
        changements = {}
        if groupes.get("police"):
            changements.update(police=depart.police, graisse=depart.graisse)
        if groupes.get("taille"):
            changements.update(taille_pct=depart.taille_pct, casse=depart.casse, ponctuation=depart.ponctuation)
        if groupes.get("remplissage"):
            changements.update(couleur=depart.couleur, degrade=depart.degrade)
        for nom in ("contour", "ombre", "lueur", "fond", "espaces"):
            if groupes.get(nom):
                changements[nom] = getattr(depart, nom)
        nouveau = replace(actuel, **changements)
        self.charger(nouveau, self._hauteur, round(self._hauteur * nouveau.taille_pct / 100), not self.police_absente.isHidden())
        self.change.emit()
