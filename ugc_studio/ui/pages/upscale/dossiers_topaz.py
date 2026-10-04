"""« Dossiers de Topaz » (V4, lot 3) : où l'app trouve Topaz Video AI et ses modèles. Par défaut, tout
est trouvé seul (dossier d'installation habituel, variables de Windows posées par Topaz, dossiers
habituels des modèles) ; on ne choisit un dossier que si Topaz est installé ailleurs, ou si ses modèles
sont téléchargés dans un autre dossier (préférences de Topaz)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLayout

from ....chemins import chemin_a_afficher
from ...composants.elements import avec_aide, bouton, libelle
from ...composants.fenetre import fenetre_en_bloc
from ...theme import Dimensions, Espacements

DOSSIERS = (
    ("installation", "Topaz Video AI (installation)", "Le dossier où se trouve ffmpeg.exe de Topaz."),
    ("modeles", "Définitions des modèles", "Le dossier des fichiers « prob-4.json »… et de la connexion (auth.tpz)."),
    ("telecharges", "Modèles téléchargés", "Le dossier où Topaz télécharge ses modèles (« prob-v4-….tz »), choisi dans ses préférences."),
)
AIDE = (
    "L'app trouve seule Topaz et ses modèles quand ils sont à leur place habituelle. Choisis un dossier "
    "seulement si Topaz ne le trouve pas : « automatique » reprend la place habituelle."
)


class DialogueDossiersTopaz(QDialog):
    """`choisis` : {"installation": Path | None, "modeles": …, "telecharges": …} (None : automatique) ;
    `automatiques` : les dossiers trouvés seuls, montrés à la place d'un dossier non choisi."""

    def __init__(self, choisis: dict[str, Path | None], automatiques: dict[str, Path | None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dossiers de Topaz")
        self.choisis = dict(choisis)
        self._automatiques = automatiques
        fenetre, self.cadre, disposition = fenetre_en_bloc(self)
        fenetre.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(avec_aide(libelle("Dossiers de Topaz", "titre-bloc", retour_a_la_ligne=False), AIDE))
        grille = QGridLayout()
        grille.setHorizontalSpacing(Espacements.M)
        grille.setVerticalSpacing(Espacements.M)
        self.chemins = {}
        for rang, (cle, nom, aide) in enumerate(DOSSIERS):
            grille.addLayout(avec_aide(libelle(nom, "legende", retour_a_la_ligne=False), aide), rang, 0)
            chemin = libelle("", "secondaire")
            self.chemins[cle] = chemin
            grille.addWidget(chemin, rang, 1)
            grille.addWidget(bouton("Changer…", variante="contour", nom_icone="folder-open", action=lambda c=cle: self.changer(c)), rang, 2, Qt.AlignmentFlag.AlignTop)
        grille.setColumnStretch(1, 1)
        disposition.addLayout(grille)
        bas = QHBoxLayout()
        bas.setSpacing(Espacements.S)
        bas.addWidget(bouton("Tout en automatique", action=self.tout_automatique))
        bas.addStretch(1)
        bas.addWidget(bouton("Annuler", action=self.reject))
        bas.addWidget(bouton("Enregistrer", variante="principal", nom_icone="save", action=self.accept))
        fenetre.addLayout(bas)
        self._actualiser()
        self.resize(Dimensions.DIALOGUE_LARGE_LARGEUR, self.heightForWidth(Dimensions.DIALOGUE_LARGE_LARGEUR))

    def _actualiser(self) -> None:
        for cle, etiquette in self.chemins.items():
            choisi = self.choisis.get(cle)
            if choisi is not None:
                etiquette.setText(chemin_a_afficher(choisi))
            else:
                trouve = self._automatiques.get(cle)
                etiquette.setText(f"{chemin_a_afficher(trouve)} (automatique)" if trouve else "Introuvable (automatique)")

    def changer(self, cle: str) -> None:
        depart = self.choisis.get(cle) or self._automatiques.get(cle) or Path.home()
        choix = QFileDialog.getExistingDirectory(self, dict((c, n) for c, n, _a in DOSSIERS)[cle], str(depart))
        if choix:
            self.definir(cle, Path(choix))

    def definir(self, cle: str, dossier: Path | None) -> None:
        self.choisis[cle] = dossier
        self._actualiser()

    def tout_automatique(self) -> None:
        self.choisis = {cle: None for cle, _n, _a in DOSSIERS}
        self._actualiser()
