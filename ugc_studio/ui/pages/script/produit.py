"""Bloc « Produit » du module Script (V2, §10.4) : l'adresse de la page produit, sa lecture, le texte
collé à la main en dernier recours, et la fiche « Ce que l'app a compris »."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from ....ecriture.affichage import date_lisible
from ....ecriture.fiche import FicheProduit
from ....ecriture.page_produit import GOOGLE, LIBELLES_SOURCES, PageLue
from ...composants.elements import BoutonInfo, bloc, bouton, info, libelle, ligne_avec_aide, vider_disposition
from ...composants.montant_label import MontantLabel
from ...composants.section_repliable import SectionRepliable
from ...theme import Dimensions, Espacements, Typo

COPIE_ANCIENNE = "Google a pu lire une copie un peu ancienne de la page : vérifie le prix et la promo."
# V3.1 : au survol de l'icône « i », après « Adresse de la page produit ».
AIDE_LECTURE = (
    "L'app lit d'abord la page elle-même : c'est gratuit et exact pour une boutique Shopify. Si le site "
    "bloque, Google la lit (coût minime) ; sinon, colle le texte du produit."
)
AIDE_FICHE = "Ces informations ont pré-rempli les champs vides du brief, où tu peux les corriger."


def etat_de_la_page(page: PageLue | None) -> str:
    """« Lu par l'app (données Shopify), aujourd'hui à 14:32. »"""
    if page is None:
        return ""
    quand = date_lisible(page.lu_le)
    texte = f"{LIBELLES_SOURCES.get(page.source, page.source)}{', ' + quand if quand else ''}."
    if page.source == GOOGLE:
        texte += " " + COPIE_ANCIENNE
    return texte


class BlocProduit(QWidget):
    """`lire_demande(adresse)`, `texte_colle(texte)`, `prononciation_demandee(noms)`."""

    lire_demande = Signal(str)
    texte_colle = Signal(str)
    prononciation_demandee = Signal(list)
    adresse_modifiee = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        self.cadre, d = bloc("Produit")
        disposition.addWidget(self.cadre)

        self.aide_lecture = BoutonInfo(AIDE_LECTURE)
        d.addLayout(ligne_avec_aide(libelle("Adresse de la page produit", "legende", retour_a_la_ligne=False), self.aide_lecture))
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        self.adresse = QLineEdit()
        self.adresse.setPlaceholderText("https://ta-boutique.com/products/…")
        self.adresse.textEdited.connect(self.adresse_modifiee.emit)
        self.adresse.returnPressed.connect(self._lire)
        ligne.addWidget(self.adresse, 1)
        self.bouton_lire = bouton("Lire la page", nom_icone="globe", action=self._lire)
        self.bouton_lire.setToolTip("L'app lit la page elle-même (gratuit) ; si le site bloque, Google la lit")
        ligne.addWidget(self.bouton_lire)
        d.addLayout(ligne)
        estimation = QHBoxLayout()
        estimation.setSpacing(Espacements.XS)
        estimation.addWidget(libelle("Analyse de la page par le modèle ≈", "legende", retour_a_la_ligne=False))
        self.cout_lecture = MontantLabel(0, Typo.LEGENDE)
        self.cout_lecture.setProperty("role", "legende")
        estimation.addWidget(self.cout_lecture)
        estimation.addStretch(1)
        d.addLayout(estimation)
        # L'état de la page lue (« Lu par l'app (données Shopify), aujourd'hui à 14:32. ») ou une
        # erreur de lecture ; caché tant qu'il n'y a rien à dire.
        self.etat = info()
        self.etat.hide()
        d.addWidget(self.etat)

        # Dernier recours : le texte de la page collé à la main.
        outils = QHBoxLayout()
        outils.setSpacing(Espacements.S)
        self.bouton_coller = bouton("Coller le texte du produit", variante="contour", nom_icone="clipboard-paste")
        self.bouton_coller.setCheckable(True)
        self.bouton_coller.toggled.connect(self._montrer_texte_colle)
        outils.addWidget(self.bouton_coller)
        outils.addStretch(1)
        d.addLayout(outils)
        self.zone_texte = QWidget()
        colonne = QVBoxLayout(self.zone_texte)
        colonne.setContentsMargins(0, 0, 0, 0)
        colonne.setSpacing(Espacements.S)
        self.texte = QPlainTextEdit()
        self.texte.setPlaceholderText("Colle ici le texte de la page produit : description, prix, offre, quelques avis…")
        self.texte.setFixedHeight(Dimensions.CHAMP_TEXTE_COLLE_HAUTEUR)
        colonne.addWidget(self.texte)
        analyser = QHBoxLayout()
        self.bouton_analyser = bouton("Analyser ce texte", nom_icone="text-search", action=self._analyser_texte)
        analyser.addWidget(self.bouton_analyser)
        analyser.addStretch(1)
        colonne.addLayout(analyser)
        self.zone_texte.hide()
        d.addWidget(self.zone_texte)

        # Fiche « Ce que l'app a compris » (repliée : les champs du brief en reprennent l'essentiel).
        self.section_fiche = SectionRepliable("Ce que l'app a compris", aide=AIDE_FICHE)
        self._lignes_fiche = QVBoxLayout()
        self._lignes_fiche.setSpacing(Espacements.XS)
        self.section_fiche.contenu.addLayout(self._lignes_fiche)
        self.zone_noms = QWidget()
        noms = QHBoxLayout(self.zone_noms)
        noms.setContentsMargins(0, 0, 0, 0)
        noms.setSpacing(Espacements.S)
        self.noms = info("")
        noms.addWidget(self.noms, 1)
        self.bouton_prononciation = bouton("Prononciation…", variante="contour", nom_icone="book-a")
        self.bouton_prononciation.setToolTip("Ajouter ces noms au dictionnaire de prononciation du projet, avec ▶ pour tester")
        self.bouton_prononciation.clicked.connect(lambda: self.prononciation_demandee.emit(list(self._noms)))
        noms.addWidget(self.bouton_prononciation, 0, Qt.AlignmentFlag.AlignTop)
        self.section_fiche.contenu.addWidget(self.zone_noms)
        self.section_fiche.hide()
        d.addWidget(self.section_fiche)
        self._noms: list[str] = []

    # --- Affichage ----------------------------------------------------------------------------------

    def definir(self, adresse: str, page: PageLue | None, fiche: FicheProduit | None) -> None:
        self.adresse.setText(adresse)
        self.adresse.setCursorPosition(0)
        if page is not None and page.source == "texte":
            self.texte.setPlainText(page.texte)
        self.afficher_etat(etat_de_la_page(page))  # rien (caché) tant qu'aucune page n'est lue
        self.definir_fiche(fiche)

    def definir_fiche(self, fiche: FicheProduit | None) -> None:
        vider_disposition(self._lignes_fiche)
        if fiche is None or fiche.est_vide():
            self.section_fiche.hide()
            return
        prix = fiche.prix + (f" au lieu de {fiche.prix_barre}" if fiche.prix and fiche.prix_barre else "")
        lignes = (
            ("Nom", " / ".join(v for v in (fiche.nom, fiche.marque) if v)),
            ("Type", fiche.type_produit),
            ("Prix", prix),
            ("Offre", fiche.offre),
            ("Bénéfices", " ; ".join(fiche.benefices)),
            ("Ce qui le distingue", fiche.distinction),
            ("Problèmes résolus", " ; ".join(fiche.problemes)),
            ("Objections probables", " ; ".join(fiche.objections)),
            ("Preuves", " ; ".join(fiche.preuves) or "aucune lue sur la page : colle 2 ou 3 avis dans « Preuves »"),
            ("Clientèle probable", fiche.clientele),
        )
        for titre, valeur in lignes:
            if valeur:
                self._lignes_fiche.addWidget(libelle(f"{titre} : {valeur}", "secondaire", selectionnable=True))
        self._noms = list(fiche.noms_a_prononcer)
        if self._noms:
            self.noms.setText(
                "Noms que la voix pourrait mal prononcer : " + ", ".join(f"« {n} »" for n in self._noms) + "."
            )
        self.zone_noms.setVisible(bool(self._noms))
        self.section_fiche.definir_resume(fiche.nom)
        self.section_fiche.show()

    def afficher_etat(self, message: str, erreur: bool = False) -> None:
        self.etat.afficher_etat(message, erreur)
        self.etat.setVisible(bool(message))

    def occupe(self, occupe: bool, bouton_actif=None) -> None:
        """Pendant un travail : tout est grisé, sauf le bouton qui l'a lancé (le cercle y tourne)."""
        for element in (self.bouton_lire, self.bouton_analyser, self.adresse):
            element.setEnabled(not occupe or element is bouton_actif)

    def definir_estimation(self, montant) -> None:
        if montant is None:
            self.cout_lecture.setText("prix inconnu")
        else:
            self.cout_lecture.definir_montant(montant)

    # --- Actions ------------------------------------------------------------------------------------

    def _lire(self) -> None:
        if self.adresse.text().strip():
            self.lire_demande.emit(self.adresse.text().strip())
        else:
            self.afficher_etat("Colle d'abord l'adresse de la page produit (elle commence par https://).", erreur=True)

    def _montrer_texte_colle(self, visible: bool) -> None:
        self.zone_texte.setVisible(visible)
        if visible:
            self.texte.setFocus()

    def _analyser_texte(self) -> None:
        if self.texte.toPlainText().strip():
            self.texte_colle.emit(self.texte.toPlainText())
        else:
            self.afficher_etat("Colle d'abord le texte de la page produit.", erreur=True)
