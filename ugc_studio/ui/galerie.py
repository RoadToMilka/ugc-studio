"""Galerie des composants : une planche qui montre tous les éléments stylés de l'app.

Elle sert à vérifier le thème d'un coup d'œil (la fabrication automatique en fait une capture
d'écran à chaque version). Elle n'apparaît pas dans l'app.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout

from ..script import depuis_texte
from .composants.barre_avancement import BarreAvancement
from .composants.editeur_script import EditeurScript
from .composants.elements import avec_aide, bloc, bouton, champ_decimal, champ_entier, info, libelle, liste_deroulante, pastille
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
        # Les quatre styles (§9.4 bis), du plus important au moins important, puis l'état
        # « sélectionné » (onglet actif) et les boutons désactivés.
        ligne = QHBoxLayout()
        ligne.addWidget(bouton("Générer l'audio", variante="principal", nom_icone="audio-lines"))
        ligne.addWidget(bouton("Tester la clé", nom_icone="key-round"))
        ligne.addWidget(bouton("Accentuer", variante="contour", nom_icone="case-upper"))
        ligne.addWidget(bouton("", variante="icone", nom_icone="ellipsis"))
        ligne.addStretch(1)
        d.addLayout(ligne)
        ligne = QHBoxLayout()
        selectionne = bouton("Onglet actif", variante="contour")
        selectionne.setCheckable(True)
        selectionne.setChecked(True)
        ligne.addWidget(selectionne)
        ligne.addWidget(bouton("Autre onglet", variante="contour"))
        ligne.addStretch(1)
        d.addLayout(ligne)
        ligne = QHBoxLayout()
        for texte_bouton, variante in (("Désactivé", None), ("Principal désactivé", "principal"), ("Contour désactivé", "contour")):
            inactif = bouton(texte_bouton, variante=variante)
            inactif.setEnabled(False)
            ligne.addWidget(inactif)
        ligne.addStretch(1)
        d.addLayout(ligne)
        d.addWidget(info("Info indispensable : une phrase qui dit quoi faire, précédée de l'ampoule."))
        d.addLayout(avec_aide(libelle("Titre avec icône « i »", "intitule", retour_a_la_ligne=False), "L'explication, au survol."))
        occupe = bouton("Bouton occupé", variante="principal", nom_icone="audio-lines")
        occupe.definir_occupe(True)
        ligne = QHBoxLayout()
        ligne.addWidget(occupe)
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
        liste = liste_deroulante()
        liste.addItems(["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
        d.addWidget(liste)
        inactif_champ = QLineEdit("Champ désactivé")
        inactif_champ.setEnabled(False)
        d.addWidget(inactif_champ)
        nombres = QHBoxLayout()
        entier = champ_entier(8, 120, info="Caractères au plus")
        entier.setValue(24)
        nombres.addWidget(entier)
        decimal = champ_decimal(0.0, 5.0, 0.1, 1, " s", "Durée minimale")
        decimal.setValue(0.6)
        nombres.addWidget(decimal)
        nombres.addStretch(1)
        d.addLayout(nombres)
        cases = QHBoxLayout()
        coche = QCheckBox("Tout en majuscules")
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
        cadre, d = bloc("Montants (§4.4) et script avec balises")
        montants = QVBoxLayout()
        for valeur, taille in ((0, Typo.COURANT), (0.0071, Typo.TITRE_BLOC), (12.3456, Typo.TITRE_PAGE), (0.000042, Typo.GRAND_CHIFFRE)):
            montants.addWidget(MontantLabel(valeur, taille))
        d.addLayout(montants)
        # Éditeur de script : badges de balises (nom français, texte centré à l'œil).
        texte = EditeurScript()
        texte.definir_segments(depuis_texte("Salut ! <laugh> J'ai testé <short pause> ce sérum pendant deux semaines… <sigh>"))
        d.addWidget(texte)
        # Barre d'avancement d'un export (V3).
        d.addWidget(libelle("Images du calque : 412 sur 930", "secondaire"))
        avancement = BarreAvancement()
        avancement.definir(412 / 930)
        d.addWidget(avancement)
        d.addStretch(1)
        grille.addWidget(cadre, 1, 1)
