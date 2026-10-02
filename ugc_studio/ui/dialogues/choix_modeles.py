"""Fenêtre « Choisir les modèles » (V1.1, §4.2 bis) : les modèles à mettre à disposition dans l'app.

Elle liste les modèles accessibles avec ta clé (dernier test réussi) que l'app sait utiliser : voix,
transcription, et texte pour les traductions. Les modèles d'images, de vidéo, de conversation…
ne sont pas proposés : aucun module ne peut s'en servir. Chacun a une case à cocher, ses capacités
et son prix s'il est connu. Un modèle utilisé (colonne « Utilisé dans ») reste coché, et sa case
ne peut pas être décochée : aucun module ne peut se retrouver sans modèle.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QFrame, QHBoxLayout, QVBoxLayout

from ...fournisseurs.capacites import LIBELLES, deviner_capacites, modele_connu
from ...modeles_charges import dans_l_ordre
from ...services import Services
from ..composants.bouton import activer_avec_entree
from ..composants.defilement import zone_defilante
from ..composants.elements import bouton, conteneur_vertical, info, libelle
from ..theme import Dimensions, Espacements


def utilisable(identifiant: str) -> bool:
    """L'app sait-elle se servir de ce modèle (voix, transcription, texte des traductions) ?"""
    return bool(deviner_capacites(identifiant))


def prix_lisibles(services: Services, identifiant: str) -> str:
    """« 0.50 $ / 9.00 $ par million de tokens (entrée / sortie) », ou « prix à saisir »."""
    prix = services.prix.prix(identifiant)
    if prix.entree is None or prix.sortie is None:
        return "Prix inconnu : à saisir dans « Modèles et prix »."
    return f"{prix.entree:f} $ / {prix.sortie:f} $ par million de tokens (entrée / sortie)."


class LigneChoix(QFrame):
    """Un modèle : sa case, ses capacités, son prix, et où il sert."""

    def __init__(self, services: Services, identifiant: str, accessible: bool, une_cle_testee: bool):
        super().__init__()
        self.setProperty("role", "ligne")
        self.identifiant = identifiant
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.XS)

        connu = modele_connu(identifiant)
        self.case = QCheckBox(connu.nom if connu else identifiant)
        self.case.setChecked(services.modeles.est_charge(identifiant))
        self.case.setToolTip(f"Identifiant du modèle chez Google : {identifiant}")
        utilise = services.modeles.utilise_dans(identifiant)
        if utilise:
            self.case.setChecked(True)
            self.case.setEnabled(False)  # un modèle utilisé ne peut pas être retiré
            self.case.setToolTip(f"Utilisé dans : {', '.join(utilise)}. Il reste chargé.")
        disposition.addWidget(self.case)

        # Détails, alignés sur le texte de la case (même retrait que les explications des cases).
        details = QVBoxLayout()
        details.setContentsMargins(Dimensions.CASE_A_COCHER + Espacements.S, 0, 0, 0)
        details.setSpacing(0)
        capacites = connu.capacites if connu else deviner_capacites(identifiant)
        details.addWidget(libelle(" · ".join(LIBELLES[c] for c in sorted(capacites)), "legende"))
        details.addWidget(libelle(prix_lisibles(services, identifiant), "legende"))
        if utilise:
            details.addWidget(libelle(f"Utilisé dans : {', '.join(utilise)}.", "legende"))
        if not accessible and une_cle_testee:
            details.addWidget(libelle("Non accessible avec ta clé.", "legende-avertissement"))
        disposition.addLayout(details)


class DialogueChoixModeles(QDialog):
    """`ouvrir_connexions` : pour aller tester une clé (Réglages → Connexions API)."""

    def __init__(self, services: Services, parent=None, ouvrir_connexions: Callable[[], None] | None = None):
        super().__init__(parent)
        self._services = services
        self.setWindowTitle("Choisir les modèles")
        self.setMinimumSize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle("Choisir les modèles", "titre-bloc"))
        disposition.addWidget(
            info(
                "Coche les modèles à mettre à disposition : seuls ceux-là apparaissent dans les listes "
                "« Modèle » des modules et dans « Modèles et prix ». Un modèle utilisé reste coché : aucun "
                "module ne peut se retrouver sans modèle.",
                "secondaire",
            )
        )

        connexions = services.connexions
        disponibles = connexions.modeles_disponibles()
        une_cle_testee = any(c.dernier_test and c.dernier_test.ok for c in connexions.lister())
        if not une_cle_testee:
            sans_cle = QHBoxLayout()
            sans_cle.setSpacing(Espacements.S)
            sans_cle.addWidget(
                info(
                    "Aucune clé testée : l'app ne sait pas encore quels modèles ta clé permet d'utiliser. "
                    "Teste ta clé dans « Connexions API », puis reviens ici.",
                    "secondaire",
                ),
                1,
            )
            if ouvrir_connexions is not None:
                sans_cle.addWidget(
                    bouton(
                        "Connexions API",
                        variante="contour",
                        nom_icone="key-round",
                        action=lambda: (self.reject(), ouvrir_connexions()),
                    ),
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
            disposition.addLayout(sans_cle)

        zone, contenu = zone_defilante()
        liste_widget, liste = conteneur_vertical(0)
        contenu.addWidget(liste_widget)
        self._lignes: list[LigneChoix] = []
        candidats = dans_l_ordre(m for m in {*disponibles, *services.modeles.charges()} if utilisable(m))
        for identifiant in candidats:
            ligne = LigneChoix(services, identifiant, identifiant in disponibles, une_cle_testee)
            self._lignes.append(ligne)
            liste.addWidget(ligne)
        disposition.addWidget(zone, 1)

        boutons = QHBoxLayout()
        boutons.setSpacing(Espacements.S)
        boutons.addStretch(1)
        boutons.addWidget(bouton("Annuler", action=self.reject))
        enregistrer = bouton("Enregistrer", variante="principal", nom_icone="check", action=self.accept)
        activer_avec_entree(enregistrer, self)
        boutons.addWidget(enregistrer)
        disposition.addLayout(boutons)

    def lignes(self) -> list[LigneChoix]:
        return list(self._lignes)

    def modeles_coches(self) -> list[str]:
        return [ligne.identifiant for ligne in self._lignes if ligne.case.isChecked()]
