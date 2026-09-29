"""Galerie des composants : une planche qui montre tous les éléments stylés de l'app.

Elle sert à vérifier le thème d'un coup d'œil (la fabrication automatique en fait une capture
d'écran à chaque version). Elle n'apparaît pas dans l'app.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QTextEdit, QVBoxLayout

from .composants.elements import bloc, bouton, libelle, pastille
from .composants.montant_label import MontantLabel
from .theme import Dimensions, Espacements, Typo


class GalerieComposants(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("racine")
        self.setWindowTitle("Galerie des composants")
        self.resize(Dimensions.FENETRE_LARGEUR, Dimensions.FENETRE_HAUTEUR)

        grille = QGridLayout(self)
        grille.setContentsMargins(Espacements.XXL, Espacements.XXL, Espacements.XXL, Espacements.XXL)
        grille.setHorizontalSpacing(Espacements.XL)
        grille.setVerticalSpacing(Espacements.XL)

        # Textes
        cadre, d = bloc("Textes")
        d.addWidget(libelle("Titre de page", "titre-page"))
        d.addWidget(libelle("Titre de bloc", "titre-bloc"))
        d.addWidget(libelle("Texte courant : l'aperçu est identique à l'export."))
        d.addWidget(libelle("Texte secondaire : explications et descriptions.", "secondaire"))
        d.addWidget(libelle("Légende : 12 px, pour les petites indications.", "legende"))
        d.addWidget(libelle("Texte discret (désactivé)", "discret"))
        etats = QHBoxLayout()
        etats.addWidget(libelle("● Clé valide", "succes", retour_a_la_ligne=False))
        etats.addWidget(libelle("● Attention", "avertissement", retour_a_la_ligne=False))
        etats.addWidget(libelle("● Clé refusée", "erreur", retour_a_la_ligne=False))
        etats.addWidget(pastille("Étape 2"))
        etats.addStretch(1)
        d.addLayout(etats)
        d.addStretch(1)
        grille.addWidget(cadre, 0, 0)

        # Boutons
        cadre, d = bloc("Boutons")
        ligne = QHBoxLayout()
        ligne.addWidget(bouton("Générer", variante="principal", nom_icone="mic"))
        ligne.addWidget(bouton("Tester la clé", nom_icone="key-round"))
        ligne.addWidget(bouton("Annuler", variante="discret"))
        ligne.addWidget(bouton("Ouvrir le dossier", variante="discret", nom_icone="folder-open"))
        ligne.addWidget(bouton("", variante="icone", nom_icone="ellipsis"))
        ligne.addStretch(1)
        d.addLayout(ligne)
        ligne = QHBoxLayout()
        inactif = bouton("Désactivé")
        inactif.setEnabled(False)
        ligne.addWidget(inactif)
        inactif_principal = bouton("Principal désactivé", variante="principal")
        inactif_principal.setEnabled(False)
        ligne.addWidget(inactif_principal)
        ligne.addStretch(1)
        d.addLayout(ligne)
        d.addStretch(1)
        grille.addWidget(cadre, 0, 1)

        # Champs
        cadre, d = bloc("Champs")
        champ = QLineEdit("Google perso")
        d.addWidget(champ)
        vide = QLineEdit()
        vide.setPlaceholderText("Nom de la clé (ex. « Google perso »)")
        d.addWidget(vide)
        liste = QComboBox()
        liste.addItems(["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
        d.addWidget(liste)
        inactif_champ = QLineEdit("Champ désactivé")
        inactif_champ.setEnabled(False)
        d.addWidget(inactif_champ)
        cases = QHBoxLayout()
        coche = QCheckBox("TOUT EN MAJUSCULES")
        coche.setChecked(True)
        cases.addWidget(coche)
        cases.addWidget(QCheckBox("Masquer les hésitations"))
        inactive = QCheckBox("Option indisponible")
        inactive.setEnabled(False)
        cases.addWidget(inactive)
        cases.addStretch(1)
        d.addLayout(cases)
        d.addStretch(1)
        grille.addWidget(cadre, 1, 0)

        # Montants et texte long
        cadre, d = bloc("Montants (§4.4) et texte")
        montants = QVBoxLayout()
        for valeur, taille in ((0, Typo.COURANT), (0.0071, Typo.TITRE_BLOC), (12.3456, Typo.TITRE_PAGE), (0.000042, Typo.GRAND_CHIFFRE)):
            montants.addWidget(MontantLabel(valeur, taille))
        d.addLayout(montants)
        texte = QTextEdit()
        texte.setPlainText("Salut ! <laugh> J'ai testé ce sérum pendant deux semaines…")
        d.addWidget(texte)
        d.addStretch(1)
        grille.addWidget(cadre, 1, 1)
