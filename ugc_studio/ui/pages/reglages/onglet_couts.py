"""Onglet « Suivi des coûts » (§4.3) : historique filtrable des appels payants, avec totaux."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from ....couts import AppelApi, filtrer, totaux
from ....fournisseurs.capacites import modele_connu
from ....montants import nombre_lisible
from ....services import Services
from ...composants.elements import bloc, info, libelle, liste_deroulante
from ...composants.montant_label import ROLE_MONTANT, DelegueMontant, MontantLabel
from ...composants.tableau import Colonne, Tableau
from ...theme import Dimensions, Espacements, Typo

TOUS = "__tous__"
SANS_PROJET = "__sans_projet__"
LIGNES_MAX = 500  # au-delà, seuls les appels les plus récents sont listés (les totaux restent complets)

# « Entrée » et « Sortie » (et non « Tokens entrée ») : des titres courts, pour que le tableau
# tienne en entier à la plus petite largeur de la fenêtre ; le détail est au survol du titre.
COLONNES = (
    Colonne("Date"),
    Colonne("Projet", texte=True),
    Colonne("Modèle", texte=True, etiree=True),
    Colonne("Opération", texte=True),
    Colonne("Entrée", a_droite=True, aide="Tokens d'entrée (texte ou audio envoyé à Google)"),
    Colonne("Sortie", a_droite=True, aide="Tokens de sortie (audio ou texte renvoyé par Google)"),
    Colonne("Coût", a_droite=True),
)
COLONNE_COUT = len(COLONNES) - 1


def _periode(choix: str, aujourd_hui: date) -> tuple[date | None, date | None]:
    if choix == "jour":
        return aujourd_hui, aujourd_hui
    if choix == "mois":
        return aujourd_hui.replace(day=1), aujourd_hui
    if choix == "mois_precedent":
        fin = aujourd_hui.replace(day=1) - timedelta(days=1)
        return fin.replace(day=1), fin
    if choix == "annee":
        return aujourd_hui.replace(month=1, day=1), aujourd_hui
    return None, None


class OngletCouts(QWidget):
    def __init__(self, services: Services):
        super().__init__()
        self._services = services

        # Comme les autres onglets (V3.1) : 16 px sous les boutons des onglets et entre les blocs ; le
        # tableau prend la hauteur qui reste dans la fenêtre (la page Réglages défile en dessous de
        # sa hauteur minimale).
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, Dimensions.ESPACE_BLOCS, 0, 0)
        disposition.setSpacing(Dimensions.ESPACE_BLOCS)

        # Filtres
        filtres = QHBoxLayout()
        filtres.setSpacing(Espacements.S)
        self.periode = liste_deroulante()
        for texte, valeur in (
            ("Aujourd'hui", "jour"),
            ("Ce mois-ci", "mois"),
            ("Le mois dernier", "mois_precedent"),
            ("Cette année", "annee"),
            ("Tout l'historique", "tout"),
        ):
            self.periode.addItem(texte, valeur)
        self.periode.setCurrentIndex(1)
        self.projet = liste_deroulante()
        self.modele = liste_deroulante()
        for liste in (self.periode, self.projet, self.modele):
            liste.currentIndexChanged.connect(self.rafraichir)
            filtres.addWidget(liste)
        filtres.addStretch(1)
        disposition.addLayout(filtres)

        # Totaux
        cadre, d = bloc()
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.L)
        colonne = QVBoxLayout()
        colonne.setSpacing(0)
        colonne.addWidget(libelle("Total de la période", "legende", retour_a_la_ligne=False))
        self.total = MontantLabel(0, Typo.GRAND_CHIFFRE)
        colonne.addWidget(self.total)
        ligne.addLayout(colonne)
        self.resume = libelle("", "secondaire")
        ligne.addWidget(self.resume, 1, Qt.AlignmentFlag.AlignBottom)
        d.addLayout(ligne)
        self.avertissement = libelle("", "avertissement")
        self.avertissement.hide()
        d.addWidget(self.avertissement)
        disposition.addWidget(cadre)

        # Tableau des appels
        cadre, d = bloc(marges=Espacements.L)
        self.tableau = Tableau(COLONNES)
        self.tableau.setMinimumHeight(Dimensions.TABLEAU_HAUTEUR_MIN)
        # Montants au format §4.4 (petites décimales), dessinés et mesurés par la même règle.
        self.tableau.setItemDelegateForColumn(COLONNE_COUT, DelegueMontant(self.tableau))
        d.addWidget(self.tableau)
        self.vide = libelle(
            "Aucun appel payant sur cette période. Les coûts apparaîtront ici dès la première voix générée.",
            "discret",
        )
        d.addWidget(self.vide)
        disposition.addWidget(cadre, 1)

        disposition.addWidget(
            info(
                "L'app compte ce qu'elle a consommé ; elle ne connaît pas le solde de ton compte Google.",
                "legende",
            )
        )

        self._remplir_listes()
        services.couts.abonner(lambda _appel: self._apres_nouvel_appel())
        self.rafraichir()

    # --- Listes de filtres -------------------------------------------------------------------

    def _remplir_listes(self) -> None:
        tous = self._services.couts.lire()
        for liste, premier, valeurs in (
            (self.projet, "Tous les projets", sorted({a.projet or SANS_PROJET for a in tous})),
            (self.modele, "Tous les modèles", sorted({a.modele for a in tous})),
        ):
            choix = liste.currentData()
            liste.blockSignals(True)
            liste.clear()
            liste.addItem(premier, TOUS)
            for valeur in valeurs:
                if liste is self.projet:
                    texte = "Sans projet" if valeur == SANS_PROJET else valeur
                else:
                    connu = modele_connu(valeur)
                    texte = connu.nom if connu else valeur
                liste.addItem(texte, valeur)
            index = liste.findData(choix)
            liste.setCurrentIndex(max(index, 0))
            liste.blockSignals(False)

    def _apres_nouvel_appel(self) -> None:
        self._remplir_listes()
        self.rafraichir()

    # --- Tableau -----------------------------------------------------------------------------

    def appels_affiches(self) -> list[AppelApi]:
        depuis, jusqu_a = _periode(self.periode.currentData(), date.today())
        appels = self._services.couts.lire(depuis, jusqu_a)
        projet = self.projet.currentData()
        if projet not in (None, TOUS):
            appels = [a for a in appels if (a.projet or SANS_PROJET) == projet]
        modele = self.modele.currentData()
        if modele not in (None, TOUS):
            appels = filtrer(appels, modele=modele)
        return appels

    def rafraichir(self) -> None:
        appels = self.appels_affiches()
        somme = totaux(appels)
        self.total.definir_montant(somme.cout_eur)
        self.resume.setText(
            f"{somme.nombre} appel{'s' if somme.nombre > 1 else ''}  ·  "
            f"{nombre_lisible(somme.tokens_entree)} tokens d'entrée  ·  {nombre_lisible(somme.tokens_sortie)} tokens de sortie"
        )
        self.avertissement.setVisible(somme.sans_prix > 0)
        self.avertissement.setText(
            f"{somme.sans_prix} appel(s) sans prix : renseigne le prix du modèle dans « Modèles et prix »."
        )

        recents = list(reversed(appels))[:LIGNES_MAX]
        self.tableau.setRowCount(len(recents))
        for ligne, appel in enumerate(recents):
            connu = modele_connu(appel.modele)
            valeurs = (
                appel.date.strftime("%d/%m/%Y %H:%M"),
                appel.projet or "Sans projet",
                connu.nom if connu else appel.modele,
                appel.operation,
                nombre_lisible(appel.tokens_entree),
                nombre_lisible(appel.tokens_sortie),
            )
            for colonne, texte in enumerate(valeurs):
                element = QTableWidgetItem(texte)
                if COLONNES[colonne].a_droite:
                    element.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tableau.setItem(ligne, colonne, element)
            cout = QTableWidgetItem()
            cout.setData(ROLE_MONTANT, "" if appel.cout_eur is None else str(appel.cout_eur))  # vide : prix inconnu
            self.tableau.setItem(ligne, COLONNE_COUT, cout)
        self.tableau.contenu_change()
        self.tableau.setVisible(bool(recents))
        self.vide.setVisible(not recents)
