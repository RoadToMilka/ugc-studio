"""Le masque d'un nom de fichier, comme l'action « Énumération » d'Ant Renamer (V4 : module Renommer ;
4.1.0 : aussi l'Upscale vidéo, à la demande de l'utilisateur, pour la même présentation partout) :

- « Masque » : une liste modifiable, avec les 10 derniers masques utilisés ;
- « Démarrer à », « Nombre de chiffres », « Incrémenter de » ;
- une rangée de petits boutons qui ajoutent une balise à l'endroit du curseur.

Les réglages sont retenus dans les préférences, sous un préfixe propre au module (« renommer_masque »,
« upscale_masque »…) : un masque d'images et un masque de vidéos ne se mélangent pas. Le calcul des
noms est dans renommage.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from ...renommage import (
    CHIFFRES_MAX,
    CHIFFRES_MIN,
    DEPART_MAX,
    DEPART_MIN,
    PAS_MAX,
    PAS_MIN,
    Numerotation,
    masques_recents,
)
from ..theme import Espacements, Hauteurs
from .elements import ChampNomme, bouton, champ_entier, liste_deroulante

AIDE_CHIFFRES = "2 : 01, 02… Au-delà de 99, le numéro s'allonge tout seul (100)."


class ChampsDuMasque(QWidget):
    """Le masque et sa numérotation, à poser dans un bloc (même espacement que le bloc).

    `prefixe` : celui des préférences du module (« renommer ») ; `balises` : (balise, ce qu'elle
    donne), une par petit bouton ; `aide_masque` : une icône « i » devant « Masque » (quand le bloc
    n'explique pas déjà le masque)."""

    change = Signal()  # le masque ou la numérotation ont changé

    def __init__(
        self,
        preferences,
        prefixe: str,
        masque_par_defaut: str,
        balises: Sequence[tuple[str, str]],
        aide_masque: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._preferences = preferences
        self._masque_par_defaut = masque_par_defaut
        self.cle_masque = f"{prefixe}_masque"
        self.cle_recents = f"{prefixe}_masques_recents"
        self.cle_depart = f"{prefixe}_depart"
        self.cle_chiffres = f"{prefixe}_chiffres"
        self.cle_pas = f"{prefixe}_pas"
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.M)  # comme entre deux lignes d'un bloc

        champs = QHBoxLayout()
        champs.setContentsMargins(0, 0, 0, 0)
        champs.setSpacing(Espacements.L)
        self.masque = liste_deroulante()
        self.masque.setEditable(True)
        self.masque.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.masque.setFixedHeight(Hauteurs.CONTROLE)
        self._remplir(self._preferences.lire(self.cle_masque) or masque_par_defaut)
        champs.addWidget(ChampNomme("Masque", self.masque, etire=True, aide=aide_masque), 1)
        self.depart = champ_entier(DEPART_MIN, DEPART_MAX)
        self.chiffres = champ_entier(CHIFFRES_MIN, CHIFFRES_MAX)
        self.pas = champ_entier(PAS_MIN, PAS_MAX)
        numerotation = Numerotation()
        for champ, cle, defaut in (
            (self.depart, self.cle_depart, numerotation.depart),
            (self.chiffres, self.cle_chiffres, numerotation.chiffres),
            (self.pas, self.cle_pas, numerotation.pas),
        ):
            valeur = self._preferences.lire(cle, defaut)
            champ.setValue(valeur if isinstance(valeur, int) else defaut)
        champs.addWidget(ChampNomme("Démarrer à", self.depart))
        champs.addWidget(ChampNomme("Nombre de chiffres", self.chiffres, aide=AIDE_CHIFFRES))
        champs.addWidget(ChampNomme("Incrémenter de", self.pas))
        disposition.addLayout(champs)

        rangee = QHBoxLayout()
        rangee.setContentsMargins(0, 0, 0, 0)
        rangee.setSpacing(Espacements.S)
        self.boutons_balises = []
        for balise, explication in balises:
            ajout = bouton(balise, variante="contour", action=lambda b=balise: self.inserer_balise(b))
            ajout.setToolTip(f"Ajouter {balise} au masque : {explication[:1].lower()}{explication[1:]}.")
            rangee.addWidget(ajout)
            self.boutons_balises.append(ajout)
        rangee.addStretch(1)
        disposition.addLayout(rangee)

        self.masque.editTextChanged.connect(lambda _texte: self._masque_change())
        for champ, cle in ((self.depart, self.cle_depart), (self.chiffres, self.cle_chiffres), (self.pas, self.cle_pas)):
            champ.valueChanged.connect(lambda valeur, c=cle: self._numerotation_changee(c, valeur))

    def texte(self) -> str:
        return self.masque.currentText()

    def numerotation(self) -> Numerotation:
        return Numerotation(self.depart.value(), self.chiffres.value(), self.pas.value())

    def _recents(self) -> list[str]:
        recents = self._preferences.lire(self.cle_recents, [])
        return [m for m in recents if isinstance(m, str) and m] if isinstance(recents, list) else []

    def _remplir(self, masque: str) -> None:
        """Les masques récents dans la liste du champ (comme Ant Renamer), `masque` dans le champ."""
        self.masque.blockSignals(True)
        self.masque.clear()
        self.masque.addItems(self._recents() or [self._masque_par_defaut])
        self.masque.setEditText(masque)
        self.masque.blockSignals(False)

    def retenir(self, masque: str) -> None:
        """Un masque qui vient de servir (renommage, upscale) : en tête des masques récents."""
        self._preferences.ecrire(self.cle_recents, masques_recents(self._recents(), masque))
        self._remplir(masque)

    def inserer_balise(self, balise: str) -> None:
        """Ajoute la balise au masque, à l'endroit du curseur (à la fin si on n'a pas cliqué dedans)."""
        champ = self.masque.lineEdit()
        champ.insert(balise)
        champ.setFocus()

    def _masque_change(self) -> None:
        self._preferences.ecrire(self.cle_masque, self.texte())
        self.change.emit()

    def _numerotation_changee(self, cle: str, valeur: int) -> None:
        self._preferences.ecrire(cle, valeur)
        self.change.emit()
