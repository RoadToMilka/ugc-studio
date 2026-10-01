"""Accroches proposées et scripts écrits (V2, §10.6 à §10.11).

- Accroches : une ligne par accroche, à cocher ; « Écrire le script » écrit un script par accroche
  cochée.
- Scripts : une carte par script (le plus récent en haut) : ses répliques dans le même éditeur à
  badges que le module Voix (modifiables à la main), leurs rôles et leurs styles, sa durée estimée,
  sa relecture, son coût ; « Envoyer dans Voix », « Garder comme exemple », ⋯ « Supprimer ».
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QMenu, QVBoxLayout, QWidget

from ....ecriture.brief import ANGLES, RESEAUX
from ....ecriture.consignes import CRITERES
from ....ecriture.regles import LIMITE_DE_LA_RELECTURE, RAPPEL_IA_TIKTOK
from ....ecriture.scripts import ROLES, Accroche, PointRelecture, ScriptEcrit
from ....fournisseurs.capacites import modele_connu
from ...composants.editeur_script import EditeurScript
from ...composants.elements import bouton, info, libelle, pastille, vider_disposition
from ...composants.montant_label import MontantLabel
from ...icones import icone_menu
from ...theme import Couleurs, Espacements
from .produit import date_lisible


def nom_angle(angle: str) -> str:
    return ANGLES.get(angle, "") if angle and angle != "auto" else ""


class LigneAccroche(QFrame):
    """Une accroche : sa case, son texte, son angle et pourquoi elle accroche, et un signal orange si
    elle frôle une règle publicitaire. Un clic n'importe où sur la ligne coche ou décoche."""

    def __init__(self, accroche: Accroche, parent=None):
        super().__init__(parent)
        self.setProperty("role", "ligne")
        self.accroche = accroche
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.S, 0, Espacements.S)
        disposition.setSpacing(Espacements.S)
        self.case = QCheckBox()
        self.case.setChecked(accroche.cochee)
        disposition.addWidget(self.case, 0, Qt.AlignmentFlag.AlignTop)
        textes = QVBoxLayout()
        textes.setSpacing(Espacements.XS)
        textes.addWidget(libelle(accroche.texte))
        details = "  ·  ".join(v for v in (nom_angle(accroche.angle), accroche.pourquoi) if v)
        if details:
            textes.addWidget(libelle(details, "legende"))
        if accroche.alerte:
            textes.addWidget(libelle(f"⚠ {accroche.alerte}", "legende-avertissement"))
        disposition.addLayout(textes, 1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        # Accepté : la ligne reçoit ensuite le relâchement du bouton (Qt l'envoie à qui a accepté l'appui).
        if evenement.button() == Qt.MouseButton.LeftButton:
            evenement.accept()
        else:
            super().mousePressEvent(evenement)

    def mouseReleaseEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        if evenement.button() == Qt.MouseButton.LeftButton and self.rect().contains(evenement.position().toPoint()):
            self.case.toggle()
            evenement.accept()
            return
        super().mouseReleaseEvent(evenement)


class ListeAccroches(QWidget):
    """`cochees_changees` : le nombre d'accroches cochées a changé (le bouton d'écriture le dit)."""

    cochees_changees = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.S)
        self.cadre = QFrame()
        self.cadre.setProperty("role", "bloc")
        interieur = QVBoxLayout(self.cadre)
        interieur.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        interieur.setSpacing(Espacements.M)
        interieur.addWidget(libelle("Accroches", "titre-bloc"))
        interieur.addWidget(
            info(
                "Coche celles qui te plaisent, puis « Écrire le script » : un script complet par accroche cochée. "
                "L'accroche est toujours la réplique 1.",
            )
        )
        self._lignes_disposition = QVBoxLayout()
        self._lignes_disposition.setSpacing(0)
        interieur.addLayout(self._lignes_disposition)
        disposition.addWidget(self.cadre)
        self._lignes: list[LigneAccroche] = []
        self.hide()

    def definir(self, accroches: list[Accroche]) -> None:
        vider_disposition(self._lignes_disposition)
        self._lignes = []
        for accroche in accroches:
            ligne = LigneAccroche(accroche)
            ligne.case.toggled.connect(lambda coche, a=accroche: self._cochee(a, coche))
            self._lignes.append(ligne)
            self._lignes_disposition.addWidget(ligne)
        self.setVisible(bool(accroches))

    def lignes(self) -> list[LigneAccroche]:
        return list(self._lignes)

    def _cochee(self, accroche: Accroche, coche: bool) -> None:
        accroche.cochee = coche
        self.cochees_changees.emit()


class CarteScript(QFrame):
    """Un script écrit. Signaux : `envoyer`, `garder`, `supprimer` (le script), `modifie` (texte
    modifié à la main : le script est à revérifier et à enregistrer)."""

    envoyer = Signal(object)
    garder = Signal(object)
    supprimer = Signal(object)
    modifie = Signal(object)

    def __init__(self, script: ScriptEcrit, numero: int, parent=None):
        super().__init__(parent)
        self.setProperty("role", "bloc")
        self.script = script
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)

        entete = QHBoxLayout()
        entete.setSpacing(Espacements.S)
        entete.addWidget(libelle(f"Script {numero}", "titre-bloc", retour_a_la_ligne=False))
        self.pastille_envoye = pastille("Envoyé dans Voix")
        self.pastille_envoye.setToolTip("Ses répliques ont été envoyées dans le module Voix")
        entete.addWidget(self.pastille_envoye)
        self.pastille_exemple = pastille("Exemple")
        self.pastille_exemple.setToolTip("Gardé comme exemple : le modèle s'en inspire pour les prochains scripts")
        entete.addWidget(self.pastille_exemple)
        entete.addStretch(1)
        if script.cout_eur is not None:
            entete.addWidget(MontantLabel(script.cout_eur))
        plus = bouton("", variante="icone", nom_icone="ellipsis")
        plus.setToolTip("Plus d'actions")
        menu = QMenu(plus)
        menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer le script").triggered.connect(
            lambda: self.supprimer.emit(self.script)
        )
        plus.setMenu(menu)
        entete.addWidget(plus)
        disposition.addLayout(entete)
        self.details = libelle("", "legende")
        disposition.addWidget(self.details)

        self.editeurs: list[EditeurScript] = []
        for rang, replique in enumerate(script.repliques, start=1):
            ligne = QHBoxLayout()
            ligne.setSpacing(Espacements.S)
            ligne.addWidget(libelle(f"Réplique {rang}", "intitule", retour_a_la_ligne=False))
            for role in replique.roles:
                ligne.addWidget(libelle(ROLES.get(role, role), "etiquette", retour_a_la_ligne=False))
            ligne.addStretch(1)
            disposition.addLayout(ligne)
            editeur = EditeurScript(hauteur_auto=True)
            editeur.definir_segments(replique.script)
            editeur.script_modifie.connect(lambda r=replique, e=editeur: self._texte_modifie(r, e))
            self.editeurs.append(editeur)
            disposition.addWidget(editeur)
            if replique.style:
                style = f"Style : {replique.style}" + (f" ({replique.style_fr})" if replique.style_fr else "")
                disposition.addWidget(libelle(style, "legende", selectionnable=True))

        self._relecture = QVBoxLayout()
        self._relecture.setSpacing(Espacements.XS)
        disposition.addLayout(self._relecture)
        if script.reseau == "tiktok":
            disposition.addWidget(info(RAPPEL_IA_TIKTOK))

        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        self.bouton_envoyer = bouton("Envoyer dans Voix", variante="principal", nom_icone="send")
        self.bouton_envoyer.setToolTip("Ses répliques remplacent celles du module Voix, avec styles, balises et accents")
        self.bouton_envoyer.clicked.connect(lambda: self.envoyer.emit(self.script))
        actions.addWidget(self.bouton_envoyer)
        self.bouton_garder = bouton("Garder comme exemple", variante="contour", nom_icone="bookmark-plus")
        self.bouton_garder.setToolTip("Le modèle s'en inspirera (ton, rythme) pour les prochains scripts")
        self.bouton_garder.clicked.connect(lambda: self.garder.emit(self.script))
        actions.addWidget(self.bouton_garder)
        actions.addStretch(1)
        disposition.addLayout(actions)
        self.rafraichir()

    def rafraichir(self) -> None:
        """Durée, relecture et marques (« Envoyé dans Voix », « Exemple »)."""
        script = self.script
        connu = modele_connu(script.modele)
        details = [
            nom_angle(script.angle),
            f"≈ {round(script.duree_estimee())} s pour {script.duree_visee_s} visées",
            f"{script.nombre_de_mots()} mots",
            RESEAUX.get(script.reseau, script.reseau),
            connu.nom if connu else script.modele,
            date_lisible(script.date),
        ]
        self.details.setText("  ·  ".join(d for d in details if d))
        self.pastille_envoye.setVisible(bool(script.envoye_le))
        self.pastille_exemple.setVisible(script.garde_comme_exemple)
        self.bouton_garder.setEnabled(not script.garde_comme_exemple)
        self._afficher_relecture()

    def _afficher_relecture(self) -> None:
        vider_disposition(self._relecture)
        script = self.script
        for correction in script.corrections:
            self._relecture.addWidget(libelle(f"✓ Corrigé avant affichage : {correction}", "legende"))
        a_signaler = [p for p in script.relecture if p.gravite != "ok"]
        for point in a_signaler:
            self._relecture.addWidget(libelle(f"⚠ {texte_du_point(point)}", "legende-avertissement"))
        if not a_signaler:
            self._relecture.addWidget(libelle("✓ Relecture : rien à signaler", "succes"))
        self._relecture.addWidget(info(LIMITE_DE_LA_RELECTURE))

    def _texte_modifie(self, replique, editeur: EditeurScript) -> None:
        replique.script = editeur.segments()
        self.modifie.emit(self.script)


def texte_du_point(point: PointRelecture) -> str:
    """« Langage parlé naturel : une phrase un peu longue. » (le critère, puis l'explication)."""
    if point.par == "modele":
        critere = CRITERES.get(point.critere, point.critere)
        return f"{critere} : {point.explication}" if point.explication else critere
    return point.explication


class ListeScripts(QWidget):
    """Les cartes des scripts, du plus récent au plus ancien."""

    envoyer = Signal(object)
    garder = Signal(object)
    supprimer = Signal(object)
    modifie = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._disposition = QVBoxLayout(self)
        self._disposition.setContentsMargins(0, 0, 0, 0)
        self._disposition.setSpacing(Espacements.L)
        self._cartes: list[CarteScript] = []

    def definir(self, scripts: list[ScriptEcrit]) -> None:
        vider_disposition(self._disposition)
        self._cartes = []
        for numero, script in reversed(list(enumerate(scripts, start=1))):
            carte = CarteScript(script, numero)
            for signal, cible in (
                (carte.envoyer, self.envoyer),
                (carte.garder, self.garder),
                (carte.supprimer, self.supprimer),
                (carte.modifie, self.modifie),
            ):
                signal.connect(cible.emit)
            self._cartes.append(carte)
            self._disposition.addWidget(carte)
        self.setVisible(bool(scripts))

    def cartes(self) -> list[CarteScript]:
        return list(self._cartes)

    def carte(self, script: ScriptEcrit) -> CarteScript | None:
        return next((c for c in self._cartes if c.script is script), None)

