"""Comparer des scripts (V2, lot 2, §10.9) : 2 ou 3 scripts côte à côte (accroche, répliques, durée,
relecture). Au départ : la dernière série de variantes, ou une retouche et son original, sinon les
scripts les plus récents (voir `choix_par_defaut`).

« Envoyer dans Voix » sous une colonne envoie ce script dans le module Voix (la fenêtre se ferme ;
l'atelier s'en charge, voir `script_a_envoyer`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from ...ecriture.affichage import nom_angle, texte_du_point
from ...ecriture.brief import RESEAUX
from ...ecriture.scripts import ROLES, ScriptEcrit
from ...estimation import MOTS_PAR_SECONDE
from ..composants.choix_voix import choisir
from ..composants.conseils import entete_de_fenetre
from ..composants.defilement import ZoneDefilante
from ..composants.editeur_script import EditeurScript
from ..composants.elements import bouton, info, libelle, liste_deroulante, pastille, vider_disposition
from ..composants.montant_label import MontantLabel
from ..theme import Dimensions, Espacements

COLONNES = 3
AUCUN = ""


def choix_par_defaut(scripts: list[ScriptEcrit]) -> list[ScriptEcrit]:
    """Ce qu'on veut sans doute comparer, d'après le dernier script écrit : sa série de variantes
    (3 premières lettres) ; ou, pour une retouche ou une copie, le script d'origine puis lui ;
    sinon, les 3 scripts les plus récents."""
    if not scripts:
        return []
    dernier = scripts[-1]
    if dernier.serie:
        return sorted((s for s in scripts if s.serie == dernier.serie), key=lambda s: s.lettre)[:COLONNES]
    origine = next((s for s in scripts if dernier.origine and s.identifiant == dernier.origine), None)
    if origine is not None:
        return [origine, dernier]
    return list(reversed(scripts[-COLONNES:]))


def libelle_du_choix(script: ScriptEcrit) -> str:
    """« Script 5 (variante B) : J'ai arrêté le fond de teint… »."""
    return f"{script.nom()} : {script.accroche()}"


class ColonneComparee(QWidget):
    """Un script de la comparaison : choisi dans la liste en haut, détaillé dessous."""

    def __init__(
        self,
        dialogue: DialogueComparerScripts,
        scripts: list[ScriptEcrit],
        choisi: ScriptEcrit | None,
        mots_par_seconde: float,
        avec_aucun: bool,
    ):
        super().__init__()
        self._dialogue = dialogue
        self._scripts = scripts
        self._mots_par_seconde = mots_par_seconde
        self.setFixedWidth(Dimensions.COLONNE_SCRIPT_COMPARE_LARGEUR)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.M)
        self.liste = liste_deroulante("Script affiché dans cette colonne")
        if avec_aucun:
            self.liste.addItem("Aucun script", AUCUN)
        for script in reversed(scripts):  # le plus récent en haut de la liste
            self.liste.addItem(libelle_du_choix(script), script.identifiant)
        choisir(self.liste, choisi.identifiant if choisi is not None else AUCUN)
        self.liste.currentIndexChanged.connect(lambda _index: self.afficher())
        disposition.addWidget(self.liste)
        self._contenu = QVBoxLayout()
        self._contenu.setSpacing(Espacements.S)
        disposition.addLayout(self._contenu)
        disposition.addStretch(1)
        self.bouton_envoyer = bouton("Envoyer dans Voix", nom_icone="send")
        self.bouton_envoyer.setToolTip("Ses répliques remplacent celles du module Voix")
        self.bouton_envoyer.clicked.connect(lambda: self.script is not None and dialogue.envoyer(self.script))
        disposition.addWidget(self.bouton_envoyer, 0, Qt.AlignmentFlag.AlignLeft)
        self.script: ScriptEcrit | None = None
        self.afficher()

    def afficher(self) -> None:
        identifiant = self.liste.currentData()
        self.script = next((s for s in self._scripts if s.identifiant == identifiant), None)
        vider_disposition(self._contenu)
        self.bouton_envoyer.setVisible(self.script is not None)
        script = self.script
        if script is None:
            self._contenu.addWidget(libelle("Choisis un script dans la liste.", "discret"))
            return
        details = [
            nom_angle(script.angle),
            f"≈ {round(script.duree_estimee(self._mots_par_seconde))} s pour {script.duree_visee_s}",
            f"{script.nombre_de_mots()} mots",
            RESEAUX.get(script.reseau, script.reseau),
        ]
        self._contenu.addWidget(libelle("  ·  ".join(d for d in details if d), "legende"))
        marques = QHBoxLayout()
        marques.setSpacing(Espacements.S)
        if script.note:
            marques.addWidget(libelle(f"{'★' * script.note}{'☆' * (5 - script.note)}", "legende", retour_a_la_ligne=False))
        if script.retenu:
            marques.addWidget(pastille("Retenu"))
        if script.envoye_le:
            marques.addWidget(pastille("Envoyé dans Voix"))
        marques.addStretch(1)
        if script.cout_eur is not None:
            marques.addWidget(MontantLabel(script.cout_eur))
        self._contenu.addLayout(marques)
        for rang, replique in enumerate(script.repliques, start=1):
            roles = " · ".join(ROLES.get(r, r) for r in replique.roles)
            self._contenu.addWidget(libelle(f"Réplique {rang}" + (f" : {roles}" if roles else ""), "intitule"))
            editeur = EditeurScript(hauteur_auto=True)
            editeur.definir_segments(replique.script)
            editeur.setReadOnly(True)
            self._contenu.addWidget(editeur)
            if replique.style:
                self._contenu.addWidget(libelle(f"Style : {replique.style}", "legende", selectionnable=True))
        a_signaler = [p for p in script.relecture if p.gravite != "ok"]
        for correction in script.corrections:
            self._contenu.addWidget(libelle(f"✓ Corrigé : {correction}", "legende"))
        for point in a_signaler:
            self._contenu.addWidget(libelle(f"⚠ {texte_du_point(point)}", "legende-avertissement"))
        if not a_signaler:
            self._contenu.addWidget(libelle("✓ Relecture : rien à signaler", "succes"))


class DialogueComparerScripts(QDialog):
    """`scripts` : ceux du projet (du plus ancien au plus récent) ; `choisis` : ceux à montrer au
    départ (2 ou 3). Après « Envoyer dans Voix » : `script_a_envoyer` (la fenêtre est acceptée)."""

    def __init__(
        self,
        scripts: list[ScriptEcrit],
        choisis: list[ScriptEcrit] | None = None,
        mots_par_seconde: float = MOTS_PAR_SECONDE,
        parent=None,
    ):
        super().__init__(parent)
        self.script_a_envoyer: ScriptEcrit | None = None
        choisis = list(choisis if choisis is not None else choix_par_defaut(scripts))[:COLONNES]
        self.setWindowTitle("Comparer les scripts")
        self.resize(Dimensions.DIALOGUE_COMPARER_SCRIPTS_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(entete_de_fenetre("Comparer les scripts", "comparaison-scripts"))
        disposition.addWidget(
            info(
                "Choisis 2 ou 3 scripts en haut des colonnes : accroche, répliques, durée et relecture, côte à côte.",
                "secondaire",
            )
        )
        zone = ZoneDefilante()
        zone.setWidgetResizable(True)
        zone.setFrameShape(QFrame.Shape.NoFrame)
        interieur = QWidget()
        interieur.setObjectName("contenuDefilant")
        zone.setWidget(interieur)
        interieur.setAutoFillBackground(False)
        zone.viewport().setAutoFillBackground(False)
        ligne = QHBoxLayout(interieur)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.XL)
        self._colonnes: list[ColonneComparee] = []
        for rang in range(COLONNES):
            choisi = choisis[rang] if rang < len(choisis) else None
            colonne = ColonneComparee(self, scripts, choisi, mots_par_seconde, avec_aucun=rang >= 2)
            self._colonnes.append(colonne)
            ligne.addWidget(colonne, 0, Qt.AlignmentFlag.AlignTop)
        ligne.addStretch(1)
        disposition.addWidget(zone, 1)

        bas = QHBoxLayout()
        bas.addStretch(1)
        bas.addWidget(bouton("Fermer", action=self.reject))
        disposition.addLayout(bas)

    def colonnes(self) -> list[ColonneComparee]:
        return list(self._colonnes)

    def envoyer(self, script: ScriptEcrit) -> None:
        self.script_a_envoyer = script
        self.accept()
