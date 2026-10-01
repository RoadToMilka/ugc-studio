"""Brief du module Script (V2, §10.5) : l'essentiel toujours visible, le reste en sections repliables.

Aucun champ n'est obligatoire. Un champ rempli par l'app (d'après la page produit, ou d'après la
voix du projet pour le genre de la personne qui parle) porte la marque « d'après la page » jusqu'à
ce que tu le modifies ; l'app ne touche jamais à un champ que tu as tapé.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from ....ecriture.brief import (
    ANGLES,
    CHAMPS_DE_LA_PAGE,
    DUREE_MAX,
    DUREE_MIN,
    GENRES,
    LANGUES_ECRITURE,
    NOMBRE_ACCROCHES_MAX,
    NOMBRE_ACCROCHES_MIN,
    PAYS,
    RESEAUX,
    TRANCHES_AGE,
    TUTOIEMENTS,
    Brief,
    langue_du_projet,
    mots_vises,
    pays_de,
)
from ....estimation import MOTS_PAR_SECONDE
from ....fournisseurs.capacites import LIBELLES, Capacite, deviner_capacites, modele_connu
from ....modeles_charges import CHARGES
from ....projets import LANGUES
from ....services import Services
from ...composants.choix_voix import choisir
from ...composants.elements import bouton, champ_entier, info, libelle, liste_deroulante
from ...composants.section_repliable import SectionRepliable
from ...theme import Dimensions, Espacements

MARQUE_PAGE = "d'après la page"
MARQUE_VOIX = "d'après la voix"

# Champs de chaque section repliable : (nom dans le brief, nom affiché, plusieurs lignes ?, exemple).
SECTIONS = (
    (
        "Produit et offre",
        (
            ("produit", "Nom du produit", False, "ex. Sérum éclat Glowzy"),
            ("type_produit", "Type de produit", False, "ex. sérum visage"),
            ("prix", "Prix", False, "ex. 29,90 €"),
            ("promo", "Promo", False, "ex. code GLOW20 : -20 %"),
            ("offre", "Livraison, garantie, retours", True, "ex. livraison offerte, satisfait ou remboursé 30 jours"),
            ("benefices", "Bénéfices", True, "Un par ligne : ce que le produit change pour la personne"),
            ("distinction", "Ce qui le distingue", True, ""),
            ("description", "Description", True, "Ce que tu veux que le modèle sache en plus"),
        ),
    ),
    (
        "Clientèle",
        (
            ("clientele", "Clientèle", False, "ex. femmes actives, sportifs débutants"),
            ("problemes", "Problèmes", True, "Un par ligne"),
            ("objections", "Objections", True, "ex. trop cher, peur que ça colle"),
            ("preuves", "Preuves", True, "Note, nombre d'avis, 2 ou 3 avis collés, chiffres de la marque"),
        ),
    ),
    (
        "Personne qui parle",
        (
            ("age_personne", "Âge", False, "ex. environ 30 ans"),
            ("profil", "Profil", False, "ex. maman de deux enfants, sportive, étudiant"),
        ),
    ),
    (
        "Contraintes",
        (
            ("appel_action", "Appel à l'action", False, "ex. Clique sur le lien en dessous"),
            ("mentions", "Mentions obligatoires", True, "Une par ligne, reprises telles quelles"),
            ("mots_interdits", "Mots interdits", False, "Séparés par des virgules"),
            ("consigne", "Consigne libre", True, "ex. ton léger, un peu d'humour"),
        ),
    ),
)


class ChampBrief(QWidget):
    """Un champ du brief : son nom, la marque « d'après la page » s'il a été rempli par l'app, la saisie."""

    modifie = Signal(str)  # nom du champ, modifié à la main

    def __init__(self, nom: str, titre: str, plusieurs_lignes: bool, exemple: str = ""):
        super().__init__()
        self.nom = nom
        self._chargement = False
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.XS)
        entete = QHBoxLayout()
        entete.setSpacing(Espacements.S)
        entete.addWidget(libelle(titre, "legende", retour_a_la_ligne=False))
        self.marque = libelle(MARQUE_PAGE, "etiquette", retour_a_la_ligne=False)
        self.marque.setToolTip("Rempli par l'app : modifie-le si besoin, il ne sera plus jamais remplacé.")
        self.marque.hide()
        entete.addWidget(self.marque)
        entete.addStretch(1)
        disposition.addLayout(entete)
        if plusieurs_lignes:
            self.saisie = QPlainTextEdit()
            self.saisie.setFixedHeight(Dimensions.CHAMP_BRIEF_HAUTEUR)
            self.saisie.setTabChangesFocus(True)
            self.saisie.textChanged.connect(self._change)
        else:
            self.saisie = QLineEdit()
            self.saisie.textEdited.connect(lambda _texte: self._change())
        self.saisie.setPlaceholderText(exemple)
        disposition.addWidget(self.saisie)

    def valeur(self) -> str:
        if isinstance(self.saisie, QPlainTextEdit):
            return self.saisie.toPlainText()
        return self.saisie.text()

    def definir(self, valeur: str, marque: str = "") -> None:
        """Valeur écrite par l'app (projet ouvert, page lue) : pas une modification à la main."""
        self._chargement = True
        if self.valeur() != valeur:
            if isinstance(self.saisie, QPlainTextEdit):
                self.saisie.setPlainText(valeur)
            else:
                self.saisie.setText(valeur)
                self.saisie.setCursorPosition(0)
        self._chargement = False
        self.marquer(marque)

    def marquer(self, marque: str) -> None:
        self.marque.setText(marque)
        self.marque.setVisible(bool(marque))

    def _change(self) -> None:
        if not self._chargement:
            self.marquer("")
            self.modifie.emit(self.nom)


def _grille() -> QGridLayout:
    grille = QGridLayout()
    grille.setContentsMargins(0, 0, 0, 0)
    grille.setHorizontalSpacing(Espacements.L)
    grille.setVerticalSpacing(Espacements.M)
    return grille


def _avec_titre(titre: str, element: QWidget) -> QVBoxLayout:
    colonne = QVBoxLayout()
    colonne.setSpacing(Espacements.XS)
    colonne.addWidget(libelle(titre, "legende", retour_a_la_ligne=False))
    colonne.addWidget(element)
    return colonne


class FormulaireBrief(QWidget):
    """Le brief : l'essentiel, quatre sections repliables, puis les options d'écriture.

    `modifie` : le brief a changé (à enregistrer). `langue_projet_demandee` : changer la langue du
    projet pour celle du brief."""

    modifie = Signal()
    langue_projet_demandee = Signal(str)
    exemples_demandes = Signal()  # « Mes meilleurs scripts… »

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self._services = services
        self._brief = Brief()
        self._chargement = False
        self._mots_par_seconde = MOTS_PAR_SECONDE
        self._mots_par_seconde_texte = ""
        self._langue_projet: str | None = None
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(Espacements.M)
        disposition.addWidget(
            info(
                "Remplis ce que tu sais : le reste est déduit de la page produit. Rien n'est inventé : sans "
                "information, le script reste sans chiffre.",
                "secondaire",
            )
        )

        # --- L'essentiel ---
        self.pays = liste_deroulante("Pays visé : il propose la langue, sa variante régionale et la devise")
        for pays in PAYS:
            self.pays.addItem(pays.nom, pays.code)
        self.langue = liste_deroulante("Langue et variante régionale du script")
        self.reseau = liste_deroulante("Réseau où la pub sera diffusée")
        for code, nom in RESEAUX.items():
            self.reseau.addItem(nom, code)
        self.duree = champ_entier(0, DUREE_MAX, " s", "Durée visée en secondes. « Auto » : la durée conseillée pour le réseau")
        self.duree.setSpecialValueText("Auto")
        self.tutoiement = liste_deroulante(
            "Automatique : tutoiement sur TikTok et Snapchat ; ailleurs, vouvoiement pour une clientèle de 35 ans et plus"
        )
        for code, nom in TUTOIEMENTS.items():
            self.tutoiement.addItem(nom, code)
        self.angle = liste_deroulante("Façon de raconter le produit")
        for code, nom in ANGLES.items():
            self.angle.addItem(nom, code)
        essentiel = _grille()
        for colonne, (titre, element) in enumerate((("Pays", self.pays), ("Langue", self.langue), ("Réseau", self.reseau))):
            essentiel.addLayout(_avec_titre(titre, element), 0, colonne)
        duree = QHBoxLayout()
        duree.setContentsMargins(0, 0, 0, 0)
        duree.setSpacing(Espacements.S)
        duree.addWidget(self.duree)
        duree.addStretch(1)
        zone_duree = QWidget()
        zone_duree.setLayout(duree)
        for colonne, (titre, element) in enumerate((("Durée", zone_duree), ("Tutoiement", self.tutoiement), ("Angle", self.angle))):
            essentiel.addLayout(_avec_titre(titre, element), 1, colonne)
        for colonne in range(3):
            essentiel.setColumnStretch(colonne, 1)
        disposition.addLayout(essentiel)
        self.info_duree = libelle("", "legende")
        disposition.addWidget(self.info_duree)

        # Langue du brief différente de celle du projet (voix, transcription) : l'app propose de la changer.
        self.zone_langue_projet = QWidget()
        ligne = QHBoxLayout(self.zone_langue_projet)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(Espacements.S)
        self.info_langue_projet = info("")
        ligne.addWidget(self.info_langue_projet, 1)
        self.bouton_langue_projet = bouton("Changer la langue du projet", variante="contour", nom_icone="languages")
        self.bouton_langue_projet.clicked.connect(self._changer_langue_projet)
        ligne.addWidget(self.bouton_langue_projet, 0, Qt.AlignmentFlag.AlignTop)
        self.zone_langue_projet.hide()
        disposition.addWidget(self.zone_langue_projet)

        # --- Sections repliables ---
        self.champs: dict[str, ChampBrief] = {}
        self.sections: list[SectionRepliable] = []
        self.age = liste_deroulante("Âge de la clientèle : il sert aussi au tutoiement automatique")
        for code, nom in TRANCHES_AGE.items():
            self.age.addItem(nom, code)
        self.genre = liste_deroulante("Genre de la personne qui parle : il change les accords (« je suis ravie »)")
        for code, nom in GENRES.items():
            self.genre.addItem(nom, code)
        for titre, champs in SECTIONS:
            section = SectionRepliable(titre)
            grille = _grille()
            rang, colonne = 0, 0
            if titre == "Clientèle":
                grille.addLayout(_avec_titre("Âge", self.age), 0, 0)
                colonne = 1
            if titre == "Personne qui parle":
                self.marque_genre = libelle(MARQUE_VOIX, "etiquette", retour_a_la_ligne=False)
                self.marque_genre.setToolTip("D'après la voix choisie dans le module Voix")
                self.marque_genre.hide()
                entete = QHBoxLayout()
                entete.setSpacing(Espacements.S)
                entete.addWidget(libelle("Genre", "legende", retour_a_la_ligne=False))
                entete.addWidget(self.marque_genre)
                entete.addStretch(1)
                colonne_genre = QVBoxLayout()
                colonne_genre.setSpacing(Espacements.XS)
                colonne_genre.addLayout(entete)
                colonne_genre.addWidget(self.genre)
                grille.addLayout(colonne_genre, 0, 0)
                colonne = 1
            for nom, titre_champ, plusieurs_lignes, exemple in champs:
                champ = ChampBrief(nom, titre_champ, plusieurs_lignes, exemple)
                champ.modifie.connect(self._champ_modifie)
                self.champs[nom] = champ
                if plusieurs_lignes:
                    if colonne:
                        rang, colonne = rang + 1, 0
                    grille.addWidget(champ, rang, 0, 1, 2)
                    rang += 1
                else:
                    grille.addWidget(champ, rang, colonne)
                    rang, colonne = (rang, 1) if colonne == 0 else (rang + 1, 0)
            grille.setColumnStretch(0, 1)
            grille.setColumnStretch(1, 1)
            section.contenu.addLayout(grille)
            self.sections.append(section)
            disposition.addWidget(section)

        # --- Options d'écriture ---
        options = QHBoxLayout()
        options.setSpacing(Espacements.XL)
        self.balises = QCheckBox("Balises")
        self.styles = QCheckBox("Styles de jeu")
        self.accents = QCheckBox("Accentuations")
        for case in (self.balises, self.styles, self.accents):
            options.addWidget(case)
        options.addStretch(1)
        disposition.addLayout(options)
        disposition.addWidget(
            info(
                "Balises : rires, pauses… (celles de l'app). Styles de jeu : seulement si l'émotion change. "
                "Accentuations : un mot au plus par réplique, dit avec plus de force. Ces choix sont retenus "
                "pour les prochains scripts."
            )
        )
        modele = QHBoxLayout()
        modele.setSpacing(Espacements.L)
        self.modele = liste_deroulante("Modèle de texte qui écrit les scripts (Réglages → Modèles et prix)")
        modele.addLayout(_avec_titre("Modèle", self.modele), 2)
        self.nombre_accroches = champ_entier(NOMBRE_ACCROCHES_MIN, NOMBRE_ACCROCHES_MAX, info="Nombre d'accroches proposées (3 à 10)")
        modele.addLayout(_avec_titre("Accroches proposées", self.nombre_accroches), 1)
        modele.addStretch(1)
        self.bouton_exemples = bouton("Mes meilleurs scripts…", variante="contour", nom_icone="award")
        self.bouton_exemples.setToolTip("Les exemples dont le modèle s'inspire : ajoute les tiens, note-les, retire les autres")
        self.bouton_exemples.clicked.connect(self.exemples_demandes.emit)
        modele.addWidget(self.bouton_exemples, 0, Qt.AlignmentFlag.AlignBottom)
        disposition.addLayout(modele)

        # Signaux : chaque changement met le brief à jour.
        self.pays.currentIndexChanged.connect(self._pays_change)
        for liste in (self.langue, self.reseau, self.tutoiement, self.angle, self.age, self.genre, self.modele):
            liste.currentIndexChanged.connect(lambda _index: self._reglage_change())
        self.duree.valueChanged.connect(lambda _valeur: self._reglage_change())
        self.nombre_accroches.valueChanged.connect(lambda _valeur: self._reglage_change())
        for case in (self.balises, self.styles, self.accents):
            case.toggled.connect(lambda _coche: self._reglage_change())
        services.modeles.abonner(self._remplir_modeles, {CHARGES})
        services.connexions.abonner(self._remplir_modeles)
        self._remplir_langues()
        self._remplir_modeles()

    # --- Brief ---------------------------------------------------------------------------------

    @property
    def brief(self) -> Brief:
        return self._brief

    def definir(self, brief: Brief) -> None:
        """Affiche ce brief (projet ouvert, page lue…) ; les changements suivants s'y écrivent."""
        self._brief = brief
        self._chargement = True
        choisir(self.pays, brief.pays)
        self._remplir_langues()
        choisir(self.langue, brief.langue)
        choisir(self.reseau, brief.reseau)
        self.duree.setValue(brief.duree_s)
        choisir(self.tutoiement, brief.tutoiement)
        choisir(self.angle, brief.angle)
        choisir(self.age, brief.age)
        choisir(self.genre, brief.genre)
        self.balises.setChecked(brief.balises)
        self.styles.setChecked(brief.styles)
        self.accents.setChecked(brief.accents)
        self.nombre_accroches.setValue(brief.nombre_accroches)
        self._remplir_modeles()
        for nom, champ in self.champs.items():
            champ.definir(getattr(brief, nom), MARQUE_PAGE if nom in brief.pre_remplis else "")
        self.marque_genre.setVisible("genre" in brief.pre_remplis and bool(brief.genre))
        self._chargement = False
        self._mettre_a_jour_infos()
        self._resumer_sections()

    def rafraichir_champs(self) -> None:
        """Après un pré-remplissage : les valeurs et les marques des champs remplis par l'app."""
        self.definir(self._brief)

    def definir_vitesse(self, mots_par_seconde: float, texte: str = "") -> None:
        """Vitesse de parole de la voix du projet, mesurée sur tes prises (V2, lot 2) : elle donne le
        nombre de mots de la durée visée. `texte` : « vitesse de Kore mesurée sur 9 prises : 2,7 mots/s »."""
        self._mots_par_seconde = mots_par_seconde
        self._mots_par_seconde_texte = texte
        self._mettre_a_jour_infos()

    def definir_langue_projet(self, langue_projet: str | None) -> None:
        """Langue du projet ouvert ; si elle diffère de celle du brief, l'app propose de la changer."""
        self._langue_projet = langue_projet
        self._mettre_a_jour_infos()

    # --- Changements -------------------------------------------------------------------------------

    def _pays_change(self, _index: int) -> None:
        if self._chargement:
            return
        self._remplir_langues()
        self._reglage_change()

    def _remplir_langues(self) -> None:
        pays = pays_de(self.pays.currentData() or "FR")
        actuelle = self.langue.currentData() or self._brief.langue
        bloque = self.langue.blockSignals(True)
        self.langue.clear()
        for code in pays.langues:
            self.langue.addItem(LANGUES_ECRITURE[code][0], code)
        choisir(self.langue, actuelle if actuelle in pays.langues else pays.langues[0])
        self.langue.blockSignals(bloque)

    def _remplir_modeles(self) -> None:
        """Modèles de texte chargés qui savent donner une réponse structurée (§10.12)."""
        actuel = self.modele.currentData() or self._brief.modele
        bloque = self.modele.blockSignals(True)
        self.modele.clear()
        for identifiant in self._services.modeles.charges():
            capacites = deviner_capacites(identifiant)
            if Capacite.TEXTE_STRUCTURE not in capacites:
                continue
            connu = modele_connu(identifiant)
            self.modele.addItem(connu.nom if connu else identifiant, identifiant)
            details = " · ".join(LIBELLES[c] for c in sorted(capacites))
            self.modele.setItemData(self.modele.count() - 1, f"{identifiant} : {details}", Qt.ItemDataRole.ToolTipRole)
        if actuel and self.modele.findData(actuel) < 0:
            connu = modele_connu(actuel)
            self.modele.addItem(connu.nom if connu else actuel, actuel)  # le modèle du brief reste proposé
        choisir(self.modele, actuel)
        self.modele.blockSignals(bloque)

    def _reglage_change(self) -> None:
        if self._chargement:
            return
        brief = self._brief
        brief.pays = self.pays.currentData() or brief.pays
        brief.langue = self.langue.currentData() or brief.langue
        brief.reseau = self.reseau.currentData() or brief.reseau
        duree = self.duree.value()
        if 0 < duree < DUREE_MIN:
            duree = DUREE_MIN
            bloque = self.duree.blockSignals(True)
            self.duree.setValue(duree)
            self.duree.blockSignals(bloque)
        brief.duree_s = duree
        brief.tutoiement = self.tutoiement.currentData() or brief.tutoiement
        brief.angle = self.angle.currentData() or brief.angle
        brief.age = self.age.currentData() or ""
        genre = self.genre.currentData() or ""
        if genre != brief.genre:
            brief.genre = genre
            brief.modifie_a_la_main("genre")
            self.marque_genre.hide()
        brief.modele = self.modele.currentData() or brief.modele
        brief.nombre_accroches = self.nombre_accroches.value()
        brief.balises = self.balises.isChecked()
        brief.styles = self.styles.isChecked()
        brief.accents = self.accents.isChecked()
        self._mettre_a_jour_infos()
        self.modifie.emit()

    def _champ_modifie(self, nom: str) -> None:
        setattr(self._brief, nom, self.champs[nom].valeur())
        self._brief.modifie_a_la_main(nom)
        self._resumer_sections()
        self.modifie.emit()

    def _changer_langue_projet(self) -> None:
        self.langue_projet_demandee.emit(langue_du_projet(self._brief.langue))

    # --- Affichage ---------------------------------------------------------------------------------

    def _mettre_a_jour_infos(self) -> None:
        brief = self._brief
        duree = brief.duree_visee()
        texte = f"{duree} s ≈ {mots_vises(duree, self._mots_par_seconde)} mots"
        if brief.duree_s == 0:
            texte += f" (durée conseillée pour {RESEAUX.get(brief.reseau, brief.reseau)})"
        if self._mots_par_seconde_texte:
            texte += f"  ·  {self._mots_par_seconde_texte}"
        self.info_duree.setText(texte)
        voulue = langue_du_projet(brief.langue)
        differente = self._langue_projet is not None and voulue != self._langue_projet
        if differente:
            actuelle = LANGUES.get(self._langue_projet, self._langue_projet)
            self.info_langue_projet.setText(
                f"La langue du projet est « {actuelle} » : la passer en « {LANGUES.get(voulue, voulue)} » ? "
                "Elle choisit les voix proposées et sert à la transcription."
            )
        self.zone_langue_projet.setVisible(differente)

    def _resumer_sections(self) -> None:
        for (titre, champs), section in zip(SECTIONS, self.sections):
            remplis = [nom for nom, *_reste in champs if getattr(self._brief, nom).strip()]
            if titre == "Clientèle" and self._brief.age:
                remplis.append("age")
            if titre == "Personne qui parle" and self._brief.genre:
                remplis.append("genre")
            d_apres_la_page = [nom for nom in remplis if nom in self._brief.pre_remplis and nom in CHAMPS_DE_LA_PAGE]
            if not remplis:
                section.definir_resume("")
            elif d_apres_la_page:
                section.definir_resume(f"{len(remplis)} rempli{'s' if len(remplis) > 1 else ''}, dont {len(d_apres_la_page)} {MARQUE_PAGE}")
            else:
                section.definir_resume(f"{len(remplis)} rempli{'s' if len(remplis) > 1 else ''}")
