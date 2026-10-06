"""« Nouveau préréglage Topaz » (V4, lot 3) : on colle la commande « FFmpeg Command » d'un export de
Topaz Video AI ; l'app la lit aussitôt et dit en français ce qu'elle a compris (modèle, réglages,
encodage, son…), ou pourquoi ce n'est pas une commande de Topaz. On lui donne un nom, et c'est prêt."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLayout, QLineEdit, QPlainTextEdit

from ....topaz.commande import CommandeIncomprise, Prereglage, comprendre
from ...composants.elements import ChampNomme, avec_aide, bouton, libelle
from ...composants.fenetre import fenetre_en_bloc
from ...theme import Dimensions, Espacements

OU_TROUVER = (
    "Dans Topaz Video AI, exporte une vidéo avec tes réglages habituels, puis dans la file d'export : le "
    "menu ⋯ de cette vidéo, « FFmpeg Command », et copie la commande. Colle-la ici : l'app garde tous tes "
    "réglages, et ne change que la vidéo, le fichier écrit et la taille."
)


class DialoguePrereglage(QDialog):
    """Après exec() accepté : `prereglage` (le préréglage compris, avec son nom)."""

    def __init__(self, parent=None, noms_pris: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Nouveau préréglage Topaz")
        self.prereglage: Prereglage | None = None
        self._noms_pris = noms_pris or []
        fenetre, self.cadre, disposition = fenetre_en_bloc(self)
        fenetre.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        disposition.setSpacing(Espacements.M)
        disposition.addLayout(avec_aide(libelle("Nouveau préréglage Topaz", "titre-bloc", retour_a_la_ligne=False), OU_TROUVER))
        self.commande = QPlainTextEdit()
        self.commande.setFixedHeight(Dimensions.CHAMP_TEXTE_COLLE_HAUTEUR)
        self.commande.setTabChangesFocus(True)
        self.commande.setPlaceholderText('ffmpeg "-hide_banner" … "-filter_complex" "tvai_up=model=prob-4:…" …')
        self.commande.textChanged.connect(self._actualiser)
        disposition.addWidget(ChampNomme("Commande « FFmpeg Command » de Topaz", self.commande, etire=True))
        self.nom = QLineEdit()
        self.nom.setPlaceholderText("ex. Proteus 1080p")
        self.nom.textChanged.connect(lambda _texte: self._actualiser_le_bouton())
        disposition.addWidget(ChampNomme("Nom du préréglage", self.nom, etire=True))
        self.compris = libelle("", "legende")
        disposition.addWidget(self.compris)

        bas = QHBoxLayout()
        bas.setSpacing(Espacements.S)
        bas.addStretch(1)
        bas.addWidget(bouton("Annuler", action=self.reject))
        self.bouton_creer = bouton("Créer le préréglage", variante="principal", nom_icone="plus", action=self._creer)
        bas.addWidget(self.bouton_creer)
        fenetre.addLayout(bas)  # sous le bloc, sur le fond de l'app (V3.2)
        self.resize(Dimensions.DIALOGUE_LARGE_LARGEUR, self.heightForWidth(Dimensions.DIALOGUE_LARGE_LARGEUR))
        self._compris: Prereglage | None = None
        self._actualiser()
        self.commande.setFocus()

    def _actualiser(self) -> None:
        """Relit la commande à chaque changement : ce que l'app a compris, ou pourquoi elle ne la comprend pas."""
        texte = self.commande.toPlainText().strip()
        self._compris = None
        if not texte:
            self.compris.setText("")
        else:
            try:
                self._compris = comprendre(texte)
            except CommandeIncomprise as erreur:
                self.compris.setText(str(erreur))
                self.compris.setProperty("role", "erreur")
            else:
                self.compris.setText("Compris :\n" + "\n".join(self._compris.resume()))
                self.compris.setProperty("role", "legende")
                if not self.nom.text().strip():
                    self.nom.setText(self._compris.nom)
        self.compris.style().unpolish(self.compris)
        self.compris.style().polish(self.compris)
        self._actualiser_le_bouton()

    def _nom_choisi(self) -> str:
        return " ".join(self.nom.text().split())

    def _actualiser_le_bouton(self) -> None:
        self.bouton_creer.setEnabled(self._compris is not None and bool(self._nom_choisi()))
        remplace = self._nom_choisi() in self._noms_pris
        self.bouton_creer.setToolTip("Un préréglage porte déjà ce nom : il sera remplacé." if remplace else "")

    def _creer(self) -> None:
        if self._compris is None or not self._nom_choisi():
            return
        self._compris.nom = self._nom_choisi()
        self.prereglage = self._compris
        self.accept()
