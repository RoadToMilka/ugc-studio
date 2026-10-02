"""Accroches proposées et scripts écrits (V2, §10.6 à §10.11).

- Accroches : une ligne par accroche, à cocher ; « Écrire le script » écrit un script par accroche
  cochée.
- Scripts : une carte par script (le plus récent en haut ; les variantes d'une même série restent
  ensemble, dans l'ordre A, B, C) : ses répliques dans le même éditeur à badges que le module Voix
  (modifiables à la main), leurs rôles et leurs styles, sa durée estimée, sa relecture, son coût.
  Actions : « Envoyer dans Voix », « Retoucher… », « Retenir », la note ★, et dans ⋯ : dupliquer,
  garder comme exemple, envoyer les accroches en variantes (série « Accroches seulement »),
  supprimer. (« Garder comme exemple » est dans ⋯ depuis le lot 2 : la carte tient ainsi dans une
  fenêtre de 960 px.)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QMenu, QVBoxLayout, QWidget

from ....ecriture.affichage import date_lisible, nom_angle, ordre_d_affichage, texte_d_origine, texte_du_point
from ....ecriture.brief import RESEAUX
from ....ecriture.regles import LIMITE_DE_LA_RELECTURE, RAPPEL_IA_TIKTOK
from ....ecriture.scripts import ROLES, Accroche, ScriptEcrit
from ....ecriture.variantes import ACCROCHES
from ....estimation import MOTS_PAR_SECONDE
from ....fournisseurs.capacites import modele_connu
from ...composants.editeur_script import EditeurScript
from ...composants.elements import (
    BoutonInfo,
    bouton,
    info,
    libelle,
    ligne_avec_aide,
    marge_haute_titre,
    pastille,
    vider_disposition,
)
from ...composants.etoiles import boutons_etoiles
from ...composants.montant_label import MontantLabel
from ...icones import icone_menu
from ...theme import Couleurs, Espacements, Hauteurs


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
        interieur.setContentsMargins(Espacements.XL, marge_haute_titre(), Espacements.XL, Espacements.XL)
        interieur.setSpacing(Espacements.M)
        # V3.1 : ce qu'il faut faire reste écrit ; le reste de l'explication passe dans l'icône « i ».
        interieur.addLayout(
            ligne_avec_aide(
                libelle("Accroches", "titre-bloc", retour_a_la_ligne=False),
                BoutonInfo("Un script complet par accroche cochée. L'accroche est toujours la réplique 1."),
            )
        )
        interieur.addWidget(info("Coche celles qui te plaisent, puis « Écrire le script »."))
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
    """Un script écrit. Signaux (avec le script) : `envoyer`, `retoucher`, `retenir`, `noter` (et la
    note), `dupliquer`, `garder` (comme exemple), `accroches_en_variantes`, `supprimer`, `modifie`
    (texte modifié à la main : le script est à revérifier et à enregistrer).

    `origine` : sa place dans sa série de variantes et ce dont il vient (« Retouche du script 3 :
    « plus court » », voir ecriture/affichage.py) ; `taille_serie` : nombre de scripts de sa série."""

    envoyer = Signal(object)
    retoucher = Signal(object)
    retenir = Signal(object)
    noter = Signal(object, int)
    dupliquer = Signal(object)
    garder = Signal(object)
    accroches_en_variantes = Signal(object)
    supprimer = Signal(object)
    modifie = Signal(object)

    def __init__(
        self,
        script: ScriptEcrit,
        mots_par_seconde: float = MOTS_PAR_SECONDE,
        origine: str = "",
        taille_serie: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.setProperty("role", "bloc")
        self.script = script
        self._mots_par_seconde = mots_par_seconde
        disposition = QVBoxLayout(self)
        # Le titre à 24 px du haut, comme à gauche (V3.2) ; le ⋯ de sa ligne est centré sur lui.
        haut = marge_haute_titre(hauteur_ligne=Hauteurs.PETIT_BOUTON)
        disposition.setContentsMargins(Espacements.XL, haut, Espacements.XL, Espacements.XL)
        disposition.setSpacing(Espacements.M)

        entete = QHBoxLayout()
        entete.setSpacing(Espacements.S)
        self.titre = libelle(script.nom(), "titre-bloc", retour_a_la_ligne=False)
        entete.addWidget(self.titre)
        self.pastille_envoye = pastille("Envoyé dans Voix")
        self.pastille_envoye.setToolTip("Ses répliques ont été envoyées dans le module Voix")
        entete.addWidget(self.pastille_envoye)
        self.pastille_retenu = pastille("Retenu")
        self.pastille_retenu.setToolTip("Retenu pour tes pubs (bouton « Retenu » pour annuler)")
        entete.addWidget(self.pastille_retenu)
        self.pastille_exemple = pastille("Exemple")
        self.pastille_exemple.setToolTip("Gardé comme exemple : le modèle s'en inspire pour les prochains scripts")
        entete.addWidget(self.pastille_exemple)
        entete.addStretch(1)
        if script.cout_eur is not None:
            entete.addWidget(MontantLabel(script.cout_eur))
        plus = bouton("", variante="icone", nom_icone="ellipsis")
        plus.setToolTip("Plus d'actions : dupliquer, garder comme exemple, supprimer…")
        menu = QMenu(plus)
        menu.addAction(icone_menu("copy-plus"), "Dupliquer").triggered.connect(lambda: self.dupliquer.emit(self.script))
        self.action_garder = menu.addAction(icone_menu("bookmark-plus"), "Garder comme exemple")
        self.action_garder.setToolTip("Le modèle s'en inspirera (ton, rythme) pour les prochains scripts")
        self.action_garder.triggered.connect(lambda: self.garder.emit(self.script))
        self.action_variantes = None
        if script.mode == ACCROCHES and taille_serie >= 2:
            self.action_variantes = menu.addAction(
                icone_menu("git-compare-arrows"), f"Envoyer les {taille_serie} accroches en variantes"
            )
            self.action_variantes.triggered.connect(lambda: self.accroches_en_variantes.emit(self.script))
        menu.addSeparator()
        menu.addAction(icone_menu("trash", Couleurs.ERREUR), "Supprimer le script").triggered.connect(
            lambda: self.supprimer.emit(self.script)
        )
        menu.setToolTipsVisible(True)
        plus.setMenu(menu)
        entete.addWidget(plus)
        disposition.addLayout(entete)
        self.details = libelle("", "legende")
        disposition.addWidget(self.details)
        self.origine = libelle(origine, "legende")
        self.origine.setVisible(bool(origine))
        disposition.addWidget(self.origine)

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
        self.bouton_retoucher = bouton("Retoucher…", variante="contour", nom_icone="wand-sparkles")
        self.bouton_retoucher.setToolTip("Une consigne (« plus court », « plus drôle »…) donne un nouveau script ; celui-ci reste")
        self.bouton_retoucher.clicked.connect(lambda: self.retoucher.emit(self.script))
        actions.addWidget(self.bouton_retoucher)
        self.bouton_retenir = bouton("Retenir", variante="contour", nom_icone="pin")
        self.bouton_retenir.clicked.connect(lambda: self.retenir.emit(self.script))
        actions.addWidget(self.bouton_retenir)
        actions.addStretch(1)
        self._etoiles = QHBoxLayout()
        self._etoiles.setSpacing(0)
        actions.addLayout(self._etoiles)
        disposition.addLayout(actions)
        self.etoiles = []
        self.rafraichir()

    def definir_vitesse(self, mots_par_seconde: float) -> None:
        """Vitesse de parole de la voix du projet (mesurée sur les prises) : la durée estimée change."""
        self._mots_par_seconde = mots_par_seconde
        self.rafraichir()

    def rafraichir(self) -> None:
        """Durée, relecture, note et marques (« Envoyé dans Voix », « Retenu », « Exemple »)."""
        script = self.script
        connu = modele_connu(script.modele)
        details = [
            nom_angle(script.angle),
            f"≈ {round(script.duree_estimee(self._mots_par_seconde))} s pour {script.duree_visee_s} visées",
            f"{script.nombre_de_mots()} mots",
            RESEAUX.get(script.reseau, script.reseau),
            connu.nom if connu else script.modele,
            date_lisible(script.date),
        ]
        self.details.setText("  ·  ".join(d for d in details if d))
        self.pastille_envoye.setVisible(bool(script.envoye_le))
        self.pastille_retenu.setVisible(script.retenu)
        self.pastille_exemple.setVisible(script.garde_comme_exemple)
        self.action_garder.setEnabled(not script.garde_comme_exemple)
        self.action_garder.setText("Gardé comme exemple" if script.garde_comme_exemple else "Garder comme exemple")
        self.bouton_retenir.setText("Retenu" if script.retenu else "Retenir")
        if script.retenu:
            self.bouton_retenir.definir_icone("check")
        else:
            self.bouton_retenir.definir_icone("pin")
        self.bouton_retenir.setToolTip(
            "Script retenu : clique pour annuler" if script.retenu else "Retenir ce script pour tes pubs (marqué « Retenu »)"
        )
        vider_disposition(self._etoiles)
        self.etoiles = boutons_etoiles(script.note, lambda note: self.noter.emit(self.script, note))
        for etoile in self.etoiles:
            self._etoiles.addWidget(etoile)
        self._afficher_relecture()

    def _afficher_relecture(self) -> None:
        vider_disposition(self._relecture)
        script = self.script
        # « Relecture », avec sa limite au survol de l'icône « i » (V3.1 : une phrase de moins par carte).
        self._relecture.addLayout(
            ligne_avec_aide(libelle("Relecture", "intitule", retour_a_la_ligne=False), BoutonInfo(LIMITE_DE_LA_RELECTURE))
        )
        for correction in script.corrections:
            self._relecture.addWidget(libelle(f"✓ Corrigé avant affichage : {correction}", "legende"))
        a_signaler = [p for p in script.relecture if p.gravite != "ok"]
        for point in a_signaler:
            self._relecture.addWidget(libelle(f"⚠ {texte_du_point(point)}", "legende-avertissement"))
        if not a_signaler:
            self._relecture.addWidget(libelle("✓ Rien à signaler", "succes"))

    def _texte_modifie(self, replique, editeur: EditeurScript) -> None:
        replique.script = editeur.segments()
        self.modifie.emit(self.script)


class ListeScripts(QWidget):
    """Les cartes des scripts (voir `ordre_d_affichage`). Ses signaux relaient ceux des cartes."""

    envoyer = Signal(object)
    retoucher = Signal(object)
    retenir = Signal(object)
    noter = Signal(object, int)
    dupliquer = Signal(object)
    garder = Signal(object)
    accroches_en_variantes = Signal(object)
    supprimer = Signal(object)
    modifie = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._disposition = QVBoxLayout(self)
        self._disposition.setContentsMargins(0, 0, 0, 0)
        self._disposition.setSpacing(Espacements.L)
        self._cartes: list[CarteScript] = []
        self._mots_par_seconde = MOTS_PAR_SECONDE

    def definir(self, scripts: list[ScriptEcrit], mots_par_seconde: float | None = None) -> None:
        if mots_par_seconde is not None:
            self._mots_par_seconde = mots_par_seconde
        vider_disposition(self._disposition)
        self._cartes = []
        for script in ordre_d_affichage(scripts):
            taille = sum(1 for s in scripts if script.serie and s.serie == script.serie)
            carte = CarteScript(script, self._mots_par_seconde, texte_d_origine(script, scripts), taille)
            for signal, cible in (
                (carte.envoyer, self.envoyer),
                (carte.retoucher, self.retoucher),
                (carte.retenir, self.retenir),
                (carte.noter, self.noter),
                (carte.dupliquer, self.dupliquer),
                (carte.garder, self.garder),
                (carte.accroches_en_variantes, self.accroches_en_variantes),
                (carte.supprimer, self.supprimer),
                (carte.modifie, self.modifie),
            ):
                signal.connect(cible.emit)
            self._cartes.append(carte)
            self._disposition.addWidget(carte)
        self.setVisible(bool(scripts))

    def definir_vitesse(self, mots_par_seconde: float) -> None:
        self._mots_par_seconde = mots_par_seconde
        for carte in self._cartes:
            carte.definir_vitesse(mots_par_seconde)

    def cartes(self) -> list[CarteScript]:
        return list(self._cartes)

    def carte(self, script: ScriptEcrit) -> CarteScript | None:
        return next((c for c in self._cartes if c.script is script), None)
