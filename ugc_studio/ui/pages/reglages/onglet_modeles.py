"""Onglet « Modèles et prix » (§4.2) : capacités des modèles, prix modifiables, taux de change.

Les prix par défaut sont les tarifs officiels de Google (page des tarifs, tarif « Standard »),
avec les changements de prix déjà annoncés (ex. hausse du 01/01/2027). Pour chaque modèle,
l'onglet donne aussi un ordre de grandeur parlant : le coût d'une minute de voix ou d'une minute
transcrite, en euros.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ....fournisseurs.capacites import (
    ADRESSE_TARIFS_GOOGLE,
    LIBELLES,
    PRIX_VERIFIES_LE,
    deviner_capacites,
    modele_connu,
)
from ....prix import lire_decimal, recuperer_taux_bce
from ....services import Services
from ... import taches
from ...composants.elements import bloc, bouton, libelle, separateur, vider_disposition
from ...composants.montant_label import MontantLabel
from ...ouvrir import ouvrir_page_web
from ...theme import Dimensions, Espacements, Typo
from ..base import zone_defilante

NATURES = {"texte": "texte envoyé", "audio": "audio"}
COLONNES = ("Modèle", "Capacités", "Accès", "Entrée $/M", "Sortie $/M")
NB_COLONNES = len(COLONNES)


def _texte(valeur: Decimal | None) -> str:
    return "" if valeur is None else format(valeur, "f")


def _prix_lisibles(entree: Decimal | None, sortie: Decimal | None) -> str:
    """« 1.00 $ / 18.00 $ »."""
    return " / ".join(f"{_texte(v)} $" if v is not None else "?" for v in (entree, sortie))


def _marquer_invalide(champ: QLineEdit, invalide: bool) -> None:
    champ.setProperty("invalide", invalide)
    champ.style().unpolish(champ)
    champ.style().polish(champ)


def champ_nombre(texte: str, indication: str = "") -> QLineEdit:
    champ = QLineEdit(texte)
    champ.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
    champ.setPlaceholderText(indication)
    return champ


@dataclass
class LigneModele:
    """Les éléments d'une ligne du tableau qui changent quand un prix ou le taux change."""

    identifiant: str
    entree: QLineEdit
    sortie: QLineEdit
    zone_minute: QWidget  # « ≈ 0.0117 € par minute de voix »
    cout_minute: MontantLabel
    zone_remarques: QWidget
    personnalise: QLabel  # « Prix modifié à la main (tarif Google : …) »
    hausse: QLabel  # « Nouveau tarif Google le 01/01/2027 : … »


class OngletModeles(QWidget):
    def __init__(self, services: Services):
        super().__init__()
        self._services = services

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        zone, contenu = zone_defilante(marges=(0, Espacements.XL, 0, Espacements.XXL))
        disposition.addWidget(zone)

        # --- Taux de change ---
        cadre, d = bloc("Taux de change")
        d.addWidget(libelle("Les prix des fournisseurs sont en dollars ; l'app affiche les coûts en euros.", "secondaire"))
        ligne = QHBoxLayout()
        ligne.setSpacing(Espacements.S)
        ligne.addWidget(libelle("1 $ =", retour_a_la_ligne=False))
        self.champ_taux = champ_nombre(_texte(services.prix.taux_usd_eur))
        self.champ_taux.editingFinished.connect(self._taux_saisi)
        ligne.addWidget(self.champ_taux)
        ligne.addWidget(libelle("€", retour_a_la_ligne=False))
        ligne.addSpacing(Espacements.M)
        self.bouton_bce = bouton(
            "Récupérer le taux du jour (BCE)", variante="discret", nom_icone="refresh-cw", action=self.taux_du_jour
        )
        ligne.addWidget(self.bouton_bce)
        ligne.addStretch(1)
        d.addLayout(ligne)
        self.info_taux = libelle("", "legende")
        d.addWidget(self.info_taux)
        contenu.addWidget(cadre)

        # --- Modèles ---
        cadre, d = bloc("Modèles et prix")
        d.addWidget(
            libelle(
                "Tarifs officiels de Google (tarif « Standard », paiement à l'usage), vérifiés le "
                f"{PRIX_VERIFIES_LE:%d/%m/%Y}, en dollars par million de tokens. Coût d'un appel = tokens × prix "
                "÷ 1 000 000 × taux de change ; les nombres de tokens sont ceux renvoyés par l'API. Quand Google "
                "annonce un nouveau tarif, l'app l'applique automatiquement à sa date.",
                "secondaire",
            )
        )
        self._grille = QGridLayout()
        self._grille.setHorizontalSpacing(Espacements.L)
        self._grille.setVerticalSpacing(0)
        self._grille.setColumnStretch(0, 1)
        d.addLayout(self._grille)
        d.addWidget(
            libelle(
                "Niveau gratuit de Google (clé sans moyen de paiement) : ces modèles n'y sont pas facturés, avec des "
                "limites d'utilisation plus basses. L'app affiche quand même le coût au tarif payant.",
                "legende",
            )
        )
        actions = QHBoxLayout()
        actions.setSpacing(Espacements.S)
        actions.addWidget(bouton("Rétablir les prix par défaut", variante="discret", nom_icone="rotate-ccw", action=self._retablir))
        actions.addWidget(
            bouton(
                "Page des tarifs Google",
                variante="discret",
                nom_icone="external-link",
                action=lambda: ouvrir_page_web(ADRESSE_TARIFS_GOOGLE),
            )
        )
        actions.addStretch(1)
        d.addLayout(actions)
        contenu.addWidget(cadre)

        self._lignes: dict[str, LigneModele] = {}
        services.connexions.abonner(self.rafraichir)
        services.prix.abonner(self._prix_changes)
        self.rafraichir()
        self._rafraichir_taux()

    # Accès utilisé par les tests : {modèle: (champ entrée, champ sortie)}.
    @property
    def _champs_prix(self) -> dict[str, tuple[QLineEdit, QLineEdit]]:
        return {ident: (ligne.entree, ligne.sortie) for ident, ligne in self._lignes.items()}

    def ligne(self, identifiant: str) -> LigneModele | None:
        return self._lignes.get(identifiant)

    # --- Taux --------------------------------------------------------------------------------

    def _prix_changes(self) -> None:
        """Prix ou taux modifié : on met à jour les textes sans reconstruire le tableau
        (le champ en cours de saisie garde ainsi le curseur)."""
        self._rafraichir_taux()
        for ligne in self._lignes.values():
            self._actualiser(ligne)

    def _rafraichir_taux(self) -> None:
        prix = self._services.prix
        if not self.champ_taux.hasFocus():
            self.champ_taux.setText(_texte(prix.taux_usd_eur))
        if prix.taux_source == "BCE":
            info = f"Taux de la Banque centrale européenne du {prix.taux_date}."
        elif prix.taux_source == "manuel":
            info = f"Taux saisi à la main le {prix.taux_date}."
        else:
            info = "Taux de départ, à vérifier : saisis le taux du jour ou récupère-le auprès de la BCE."
        self.info_taux.setText(info)

    def _taux_saisi(self) -> None:
        try:
            taux = lire_decimal(self.champ_taux.text())
        except ValueError:
            taux = None
        if not taux:
            _marquer_invalide(self.champ_taux, True)
            return
        _marquer_invalide(self.champ_taux, False)
        if taux != self._services.prix.taux_usd_eur:
            self._services.prix.definir_taux(taux)

    def taux_du_jour(self) -> None:
        self.bouton_bce.setEnabled(False)
        self.info_taux.setText("Récupération du taux auprès de la BCE…")

        def fin(resultat) -> None:
            taux, jour = resultat
            self.bouton_bce.setEnabled(True)
            self._services.prix.definir_taux(taux, source="BCE", le=jour)

        def echec(erreur: Exception) -> None:
            self.bouton_bce.setEnabled(True)
            self.info_taux.setText(f"Taux non récupéré : {getattr(erreur, 'message', erreur)}")

        taches.lancer(recuperer_taux_bce, fin, echec)

    # --- Prix --------------------------------------------------------------------------------

    def rafraichir(self) -> None:
        vider_disposition(self._grille)
        for ligne_grille in range(self._grille.rowCount()):  # la grille garde ses anciennes lignes
            self._grille.setRowMinimumHeight(ligne_grille, 0)
        self._lignes.clear()

        for colonne, titre in enumerate(COLONNES):
            self._grille.addWidget(libelle(titre, "legende", retour_a_la_ligne=False), 0, colonne)

        disponibles = self._services.connexions.modeles_disponibles()
        une_cle_testee = any(
            c.dernier_test and c.dernier_test.ok for c in self._services.connexions.lister()
        )
        detectes = {m for m in disponibles if deviner_capacites(m)}
        rang = 1
        for identifiant in self._services.prix.identifiants(detectes):
            # Avant chaque modèle : un fin trait horizontal, avec de l'espace au-dessus et en dessous.
            self._grille.setRowMinimumHeight(rang, Espacements.XL)
            self._grille.addWidget(separateur(), rang, 0, 1, NB_COLONNES, Qt.AlignmentFlag.AlignVCenter)
            self._ajouter_modele(identifiant, rang + 1, identifiant in disponibles, une_cle_testee)
            rang += 3

    def _ajouter_modele(self, identifiant: str, rang: int, accessible: bool, une_cle_testee: bool) -> None:
        """Deux lignes de la grille : nom, capacités, accès et prix ; puis les remarques sur le prix
        et le coût d'une minute (sous les prix)."""
        connu = modele_connu(identifiant)
        capacites = connu.capacites if connu else deviner_capacites(identifiant)

        # Ligne 1
        nom = QVBoxLayout()
        nom.setSpacing(0)
        # Le nom peut passer à la ligne : sur une fenêtre étroite, un long nom (« Gemini 2.5 Flash
        # Preview TTS ») élargirait sinon tout l'onglet au-delà de la partie visible.
        # L'identifiant technique (« gemini-3.8-flash-tts ») ferait doublon avec le nom : il reste
        # lisible au survol du nom, utile en cas de souci.
        titre = libelle(connu.nom if connu else identifiant)
        titre.setToolTip(f"Identifiant du modèle chez Google : {identifiant}")
        nom.addWidget(titre)
        note = connu.note if connu else "Détecté avec ta clé : renseigne ses prix."
        if note:
            nom.addWidget(libelle(note, "legende"))
        self._grille.addLayout(nom, rang, 0)
        self._grille.addWidget(libelle(" · ".join(LIBELLES[c] for c in sorted(capacites)), "legende"), rang, 1)
        if accessible:
            acces = libelle("✓ Accessible", "succes", retour_a_la_ligne=False)
        elif une_cle_testee:
            acces = libelle("Non accessible", "discret", retour_a_la_ligne=False)
        else:
            acces = libelle("Teste une clé", "discret", retour_a_la_ligne=False)
        self._grille.addWidget(acces, rang, 2)
        entree = champ_nombre("", "à saisir")
        sortie = champ_nombre("", "à saisir")
        if connu is not None:
            entree.setToolTip(f"Entrée ({NATURES.get(connu.entree, connu.entree)}) : dollars par million de tokens")
            sortie.setToolTip(f"Sortie ({NATURES.get(connu.sortie, connu.sortie)} produit) : dollars par million de tokens")
        for champ in (entree, sortie):
            champ.editingFinished.connect(lambda ident=identifiant: self._prix_saisi(ident))
        self._grille.addWidget(entree, rang, 3)
        self._grille.addWidget(sortie, rang, 4)

        # Ligne 2 : remarques sur le prix, puis coût d'une minute sous les prix
        zone_remarques = QWidget()
        remarques = QVBoxLayout(zone_remarques)
        remarques.setContentsMargins(0, Espacements.XS, 0, 0)
        remarques.setSpacing(0)
        personnalise = libelle("", "legende")
        hausse = libelle("", "legende-avertissement")
        remarques.addWidget(personnalise)
        remarques.addWidget(hausse)
        self._grille.addWidget(zone_remarques, rang + 1, 0, 1, 3, Qt.AlignmentFlag.AlignTop)

        zone_minute = QWidget()
        minute = QHBoxLayout(zone_minute)
        minute.setContentsMargins(0, Espacements.XS, 0, 0)
        minute.setSpacing(Espacements.XS)
        minute.addWidget(libelle("≈", "legende", retour_a_la_ligne=False))
        cout_minute = MontantLabel(0, Typo.COURANT)
        minute.addWidget(cout_minute)
        reference = connu.reference.libelle if connu and connu.reference else ""
        minute.addWidget(libelle(reference, "legende", retour_a_la_ligne=False))
        minute.addStretch(1)
        self._grille.addWidget(zone_minute, rang + 1, 3, 1, 2, Qt.AlignmentFlag.AlignTop)

        ligne = LigneModele(identifiant, entree, sortie, zone_minute, cout_minute, zone_remarques, personnalise, hausse)
        self._lignes[identifiant] = ligne
        self._actualiser(ligne)

    def _actualiser(self, ligne: LigneModele) -> None:
        prix = self._services.prix
        actuel = prix.prix(ligne.identifiant)
        for champ, valeur in ((ligne.entree, actuel.entree), (ligne.sortie, actuel.sortie)):
            if not champ.hasFocus() and champ.text() != _texte(valeur):
                champ.setText(_texte(valeur))

        cout = prix.cout_reference_eur(ligne.identifiant)
        ligne.zone_minute.setVisible(cout is not None)
        if cout is not None:
            ligne.cout_minute.definir_montant(cout)

        tarif = prix.tarif_google(ligne.identifiant)
        if actuel.personnalise and tarif is not None:
            ligne.personnalise.setText(
                f"Prix modifié à la main (tarif Google : {_prix_lisibles(tarif.entree, tarif.sortie)})."
            )
        ligne.personnalise.setVisible(actuel.personnalise and tarif is not None)

        prochain = prix.prochain_tarif_google(ligne.identifiant)
        if prochain is not None:
            ligne.hausse.setText(
                f"Nouveau tarif Google le {prochain.depuis:%d/%m/%Y} : "
                f"{_prix_lisibles(prochain.entree, prochain.sortie)}, appliqué automatiquement."
            )
        ligne.hausse.setVisible(prochain is not None)
        ligne.zone_remarques.setVisible(not ligne.personnalise.isHidden() or not ligne.hausse.isHidden())

    def _prix_saisi(self, identifiant: str) -> None:
        ligne = self._lignes[identifiant]
        valeurs = []
        for champ in (ligne.entree, ligne.sortie):
            try:
                valeurs.append(lire_decimal(champ.text()))
                _marquer_invalide(champ, False)
            except ValueError:
                _marquer_invalide(champ, True)
                return
        for champ, valeur in zip((ligne.entree, ligne.sortie), valeurs, strict=True):
            champ.setText(_texte(valeur))  # « 18,00 » s'affiche « 18.00 », comme les autres prix
        actuel = self._services.prix.prix(identifiant)
        if (actuel.entree, actuel.sortie) != tuple(valeurs):
            self._services.prix.definir_prix(identifiant, *valeurs)

    def _retablir(self) -> None:
        # D'abord quitter le champ en cours de saisie : sinon, en le quittant plus tard, sa valeur
        # serait enregistrée à nouveau par-dessus le prix rétabli.
        for ligne in self._lignes.values():
            for champ in (ligne.entree, ligne.sortie):
                if champ.hasFocus():
                    champ.clearFocus()
                _marquer_invalide(champ, False)
        self._services.prix.retablir_defauts()  # met à jour les lignes (voir _prix_changes)
