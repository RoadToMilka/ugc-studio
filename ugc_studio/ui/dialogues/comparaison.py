"""Écoute comparative d'une série de variantes (§5.6).

- « Lecture enchaînée » : A, puis B, puis C… chacune depuis le début.
- Bascule A/B : pendant l'écoute, cliquer sur une lettre (ou taper A, B, C… ou 1, 2, 3…) passe à
  cette variante **au même moment du texte**, sans repartir du début. Espace : lecture ou pause.
- Chaque variante se note (★) ; « Garder » marque la variante retenue (une seule par série).
Chaque variante reste une prise normale : elle est aussi dans la liste des prises.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout

from ...fournisseurs.capacites import modele_connu
from ...projets import Prise
from ...services import Services
from ...variantes import LETTRES, MODELE, STYLE, TEXTE, VOIX, Reglage, champs_differents, valeur_de_prise
from ..composants.bouton import Bouton
from ..composants.comparateur import ComparateurAudio
from ..composants.elements import (
    bouton,
    conteneur_vertical,
    glissiere,
    info,
    libelle,
    minutes_secondes,
    vider_disposition,
)
from ..composants.etoiles import boutons_etoiles
from ..icones import icone
from ..pages.base import zone_defilante
from ..theme import Couleurs, Dimensions, Espacements

EXTRAIT_TEXTE = 40  # caractères montrés d'un texte de réplique modifié

TOUCHES_VARIANTES = {
    **{getattr(Qt.Key, f"Key_{lettre}"): index for index, lettre in enumerate(LETTRES)},
    **{getattr(Qt.Key, f"Key_{index + 1}"): index for index in range(len(LETTRES))},
}


def _extrait(texte: str) -> str:
    return texte if len(texte) <= EXTRAIT_TEXTE else texte[: EXTRAIT_TEXTE - 1].rstrip() + "…"


class LigneVariante(QFrame):
    """Une variante : sa lettre (pour l'écouter), ce qui la distingue, sa durée, sa note, « Garder »."""

    def __init__(self, dialogue: DialogueComparaison, index: int, prise: Prise, champs: list[Reglage]):
        super().__init__()
        self.setProperty("role", "ligne")
        self.prise = prise
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(0, Espacements.M, 0, Espacements.M)
        disposition.setSpacing(Espacements.M)

        self.lettre = Bouton(prise.variante or LETTRES[index])
        self.lettre.setCheckable(True)
        self.lettre.setToolTip(f"Écouter la variante {prise.variante} (touche {prise.variante})")
        self.lettre.clicked.connect(lambda: dialogue.ecouter(index))
        disposition.addWidget(self.lettre, 0, Qt.AlignmentFlag.AlignVCenter)

        textes = QVBoxLayout()
        textes.setSpacing(0)
        textes.addWidget(libelle(prise.nom, "intitule", retour_a_la_ligne=False))
        textes.addWidget(libelle(dialogue.description(prise, champs), "legende"))
        disposition.addLayout(textes, 1)

        disposition.addWidget(libelle(minutes_secondes(prise.duree_s), "secondaire", retour_a_la_ligne=False))
        self.etoiles = boutons_etoiles(prise.note, lambda note: dialogue.noter(prise.identifiant, note))
        etoiles = QHBoxLayout()
        etoiles.setSpacing(0)
        for etoile in self.etoiles:
            etoiles.addWidget(etoile)
        disposition.addLayout(etoiles)
        self.bouton_garder = bouton(
            "Retenue" if prise.retenue else "Garder",
            variante="principal" if prise.retenue else None,
            nom_icone="award",
            action=lambda: dialogue.retenir(prise.identifiant),
        )
        self.bouton_garder.setToolTip(
            "Variante retenue (clique pour annuler)" if prise.retenue else "Retenir cette variante pour la pub"
        )
        disposition.addWidget(self.bouton_garder, 0, Qt.AlignmentFlag.AlignVCenter)


class DialogueComparaison(QDialog):
    def __init__(self, services: Services, serie: int, parent=None):
        super().__init__(parent)
        self._services = services
        self.serie = serie
        self._prises = services.projets.serie(serie)
        projet = services.projets.projet
        self.comparateur = ComparateurAudio(
            [projet.chemin(p.fichier) for p in self._prises],
            [round(p.duree_s * 1000) for p in self._prises],
            self,
        )
        self.comparateur.etat_change.connect(self._etat_change)
        self.comparateur.position_change.connect(self._position_change)
        self._lignes: list[LigneVariante] = []
        self.setWindowTitle("Comparer les variantes")
        self.resize(Dimensions.DIALOGUE_LARGE_LARGEUR, Dimensions.DIALOGUE_LARGE_HAUTEUR)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(Espacements.XL, Espacements.XL, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(libelle(f"Comparer les variantes de la série {serie}", "titre-bloc"))
        disposition.addWidget(
            info(
                "« Lecture enchaînée » joue A, puis B, puis C… Pendant l'écoute, clique sur une lettre "
                "(ou tape A, B, C…) pour passer à cette variante au même moment du texte. Espace : "
                "lecture ou pause.",
                "secondaire",
            )
        )
        self.commun = libelle("", "legende")
        disposition.addWidget(self.commun)

        # Lecteur : lecture enchaînée, lecture / pause, position dans la variante écoutée.
        lecteur = QHBoxLayout()
        lecteur.setSpacing(Espacements.M)
        self.bouton_enchainer = bouton("Lecture enchaînée", nom_icone="list-music", action=self.comparateur.enchainer)
        lecteur.addWidget(self.bouton_enchainer)
        self.bouton_lecture = bouton("", variante="icone", action=self.comparateur.basculer_lecture)
        lecteur.addWidget(self.bouton_lecture)
        self.ecoutee = libelle("", "intitule", retour_a_la_ligne=False)
        lecteur.addWidget(self.ecoutee)
        self.position = glissiere()
        self.position.sliderMoved.connect(self.comparateur.aller_a)
        lecteur.addWidget(self.position, 1)
        self.temps = libelle("0:00 / 0:00", "legende", retour_a_la_ligne=False)
        lecteur.addWidget(self.temps)
        disposition.addLayout(lecteur)

        zone, contenu = zone_defilante(largeur_max=None)
        self._liste_widget, self._liste = conteneur_vertical(0)
        contenu.addWidget(self._liste_widget)
        disposition.addWidget(zone, 1)

        bas = QHBoxLayout()
        bas.setSpacing(Espacements.S)
        self.statut = libelle("", "secondaire")
        bas.addWidget(self.statut, 1)
        bas.addWidget(bouton("Fermer", action=self.accept))
        disposition.addLayout(bas)

        self._remplir()
        self._etat_change()
        self._position_change(0, self.comparateur.duree() if self._prises else 0)

    # --- Affichage ---------------------------------------------------------------------------

    def description(self, prise: Prise, champs: list[Reglage]) -> str:
        """Ce qui distingue cette variante des autres (ex. « voix Puck · style « calm » »)."""
        if not champs:
            return "Mêmes réglages : seule l'interprétation du modèle change."
        plusieurs = max((len(p.repliques) for p in self._prises), default=0) > 1
        morceaux = []
        for reglage in champs:
            nom, indice = reglage
            valeur = valeur_de_prise(prise, reglage)
            numero = f" {indice + 1}" if plusieurs else ""
            if nom == MODELE:
                connu = modele_connu(valeur)
                morceaux.append(connu.nom if connu else valeur)
            elif nom == VOIX:
                morceaux.append(f"voix {self._services.voix.nom(valeur)}")
            elif nom == STYLE:
                morceaux.append(f"style{numero} « {valeur} »" if valeur else f"réplique{numero} sans style")
            elif nom == TEXTE:
                morceaux.append(f"texte{numero} « {_extrait(valeur)} »")
        return "  ·  ".join(morceaux)

    def _texte_commun(self, champs: list[Reglage]) -> str:
        if not self._prises:
            return ""
        premiere = self._prises[0]
        morceaux = []
        if (MODELE, -1) not in champs:
            connu = modele_connu(premiere.modele)
            morceaux.append(connu.nom if connu else premiere.modele)
        if (VOIX, -1) not in champs:
            morceaux.append(f"voix {self._services.voix.nom(premiere.voix)}")
        return ("En commun : " + "  ·  ".join(morceaux)) if morceaux else ""

    def _remplir(self) -> None:
        vider_disposition(self._liste)
        self._prises = self._services.projets.serie(self.serie)
        champs = champs_differents(self._prises)
        self.commun.setText(self._texte_commun(champs))
        self.commun.setVisible(bool(self.commun.text()))
        self._lignes = [LigneVariante(self, index, prise, champs) for index, prise in enumerate(self._prises)]
        for ligne in self._lignes:
            self._liste.addWidget(ligne)
        if not self._prises:
            self._liste.addWidget(libelle("Les prises de cette série ont été supprimées.", "discret"))
        self._etat_change()

    def lignes(self) -> list[LigneVariante]:
        return list(self._lignes)

    def _etat_change(self) -> None:
        comparateur = self.comparateur
        for index, ligne in enumerate(self._lignes):
            ligne.lettre.setChecked(index == comparateur.actif)
        lecture = comparateur.en_lecture
        self.bouton_lecture.setIcon(icone("pause" if lecture else "play", Couleurs.ACCENT_SURVOL, rempli=True))
        self.bouton_lecture.setToolTip("Pause (Espace)" if lecture else "Lecture (Espace)")
        if self._prises:
            self.ecoutee.setText(f"Variante {self._prises[comparateur.actif].variante}")
        self.bouton_enchainer.setEnabled(len(self._prises) > 1)

    def _position_change(self, position_ms: int, duree_ms: int) -> None:
        if not self.position.isSliderDown():
            self.position.setRange(0, max(duree_ms, 0))
            self.position.setValue(position_ms)
        self.temps.setText(f"{minutes_secondes(position_ms / 1000)} / {minutes_secondes(duree_ms / 1000)}")

    # --- Actions -----------------------------------------------------------------------------

    def ecouter(self, index: int) -> None:
        """Passe à la variante `index` au même moment du texte (et lance la lecture)."""
        if not 0 <= index < len(self._prises):
            return
        self.comparateur.basculer(index)
        if not self.comparateur.en_lecture:
            self.comparateur.jouer()
        self._etat_change()

    def noter(self, identifiant: str, note: int) -> None:
        self._services.projets.modifier_prise(identifiant, note=note)
        self._remplir()

    def retenir(self, identifiant: str) -> None:
        self._services.projets.retenir(identifiant)
        prise = self._services.projets.prise(identifiant)
        self.statut.setText(f"{prise.nom} retenue." if prise.retenue else "Plus aucune variante retenue.")
        self._remplir()

    def keyPressEvent(self, evenement) -> None:  # noqa: N802 — nom imposé par Qt
        if evenement.key() == Qt.Key.Key_Space:
            self.comparateur.basculer_lecture()
            return
        index = TOUCHES_VARIANTES.get(evenement.key())
        if index is not None and index < len(self._prises):
            self.ecouter(index)
            return
        super().keyPressEvent(evenement)

    def done(self, resultat: int) -> None:
        self.comparateur.arreter()  # libère les fichiers audio
        super().done(resultat)
