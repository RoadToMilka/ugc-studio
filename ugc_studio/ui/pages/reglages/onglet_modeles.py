"""Onglet « Modèles et prix » (§4.2) : capacités des modèles, prix modifiables, taux de change."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ....fournisseurs.capacites import LIBELLES, deviner_capacites, modele_connu
from ....prix import lire_decimal, recuperer_taux_bce
from ....services import Services
from ... import taches
from ...composants.elements import bloc, bouton, libelle, vider_disposition
from ...theme import Dimensions, Espacements
from ..base import zone_defilante


def _texte(valeur: Decimal | None) -> str:
    return "" if valeur is None else format(valeur, "f")


def _marquer_invalide(champ: QLineEdit, invalide: bool) -> None:
    champ.setProperty("invalide", invalide)
    champ.style().unpolish(champ)
    champ.style().polish(champ)


def champ_nombre(texte: str, indication: str = "") -> QLineEdit:
    champ = QLineEdit(texte)
    champ.setFixedWidth(Dimensions.CHAMP_NOMBRE_LARGEUR)
    champ.setPlaceholderText(indication)
    return champ


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
                "Prix en dollars par million de tokens. Coût d'un appel = tokens × prix ÷ 1 000 000 × taux "
                "de change ; les nombres de tokens sont ceux renvoyés par l'API.",
                "secondaire",
            )
        )
        self._grille = QGridLayout()
        self._grille.setHorizontalSpacing(Espacements.L)
        self._grille.setVerticalSpacing(Espacements.M)
        self._grille.setColumnStretch(0, 1)
        d.addLayout(self._grille)
        actions = QHBoxLayout()
        actions.addWidget(bouton("Rétablir les prix par défaut", variante="discret", nom_icone="rotate-ccw", action=self._retablir))
        actions.addStretch(1)
        d.addLayout(actions)
        contenu.addWidget(cadre)

        self._champs_prix: dict[str, tuple[QLineEdit, QLineEdit]] = {}
        services.connexions.abonner(self.rafraichir)
        services.prix.abonner(self._rafraichir_taux)
        self.rafraichir()
        self._rafraichir_taux()

    # --- Taux --------------------------------------------------------------------------------

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
        self._champs_prix.clear()

        for colonne, titre in enumerate(("Modèle", "Capacités", "Accès", "Entrée $/M", "Sortie $/M")):
            self._grille.addWidget(libelle(titre, "legende", retour_a_la_ligne=False), 0, colonne)

        disponibles = self._services.connexions.modeles_disponibles()
        une_cle_testee = any(
            c.dernier_test and c.dernier_test.ok for c in self._services.connexions.lister()
        )
        detectes = {m for m in disponibles if deviner_capacites(m)}
        for ligne, identifiant in enumerate(self._services.prix.identifiants(detectes), start=1):
            connu = modele_connu(identifiant)
            capacites = connu.capacites if connu else deviner_capacites(identifiant)

            nom = QVBoxLayout()
            nom.setSpacing(0)
            nom.addWidget(libelle(connu.nom if connu else identifiant, retour_a_la_ligne=False))
            note = connu.note if connu else "Détecté avec ta clé : renseigne ses prix."
            nom.addWidget(libelle(f"{identifiant} — {note}" if note else identifiant, "legende"))
            self._grille.addLayout(nom, ligne, 0)

            self._grille.addWidget(
                libelle(" · ".join(LIBELLES[c] for c in sorted(capacites)), "legende"), ligne, 1
            )

            if identifiant in disponibles:
                acces = libelle("✓ Accessible", "succes", retour_a_la_ligne=False)
            elif une_cle_testee:
                acces = libelle("Non accessible", "discret", retour_a_la_ligne=False)
            else:
                acces = libelle("Teste une clé", "discret", retour_a_la_ligne=False)
            self._grille.addWidget(acces, ligne, 2)

            prix = self._services.prix.prix(identifiant)
            entree = champ_nombre(_texte(prix.entree), "à saisir")
            sortie = champ_nombre(_texte(prix.sortie), "à saisir")
            for champ in (entree, sortie):
                champ.editingFinished.connect(lambda ident=identifiant: self._prix_saisi(ident))
            self._grille.addWidget(entree, ligne, 3)
            self._grille.addWidget(sortie, ligne, 4)
            self._champs_prix[identifiant] = (entree, sortie)

    def _prix_saisi(self, identifiant: str) -> None:
        entree, sortie = self._champs_prix[identifiant]
        valeurs = []
        for champ in (entree, sortie):
            try:
                valeurs.append(lire_decimal(champ.text()))
                _marquer_invalide(champ, False)
            except ValueError:
                _marquer_invalide(champ, True)
                return
        actuel = self._services.prix.prix(identifiant)
        if (actuel.entree, actuel.sortie) != tuple(valeurs):
            self._services.prix.definir_prix(identifiant, *valeurs)

    def _retablir(self) -> None:
        self._services.prix.retablir_defauts()
        self.rafraichir()
