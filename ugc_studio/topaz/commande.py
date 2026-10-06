"""Préréglage Topaz (V4, lot 3 ; cahier des charges §8 bis.3) : la commande « FFmpeg Command » d'un
export de Topaz Video AI, collée une fois dans l'app, puis rejouée sur d'autres vidéos.

Pourquoi coller la commande plutôt que refaire les réglages dans l'app ? Dans Topaz, un curseur
devient dans la commande une valeur précise, parfois convertie ; la recopier évite tout écart. L'app
garde donc tout ce que Topaz a écrit (modèle et réglages de Proteus, encodage, son, cadence…) et ne
change que ce qui est propre à chaque vidéo :
- la vidéo lue et le fichier écrit ;
- la taille finale (voir taille_finale) : dans le filtre de Topaz (`tvai_up`, `w` et `h`) et dans le
  dernier ajustement (`scale`) ;
- le début de la commande qui ne traite qu'un extrait (`-ss`, `-t` : un aperçu) est retiré ;
- le fichier est un MP4 (ou MOV) classique, comme le fichier final de l'interface de Topaz : les
  options qui le découpent en morceaux (« MP4 fragmenté », `-movflags frag_keyframe+empty_moov…`) sont
  retirées, le sommaire du fichier est placé au début (voir mp4_classique ; 4.0.3) ;
- l'app ajoute ce dont elle a besoin pour suivre le travail (`-progress`) et ne rien demander au
  clavier (`-nostdin`).

Exemple de commande (Topaz Video AI 7.1.1, l'export de l'utilisateur du 04/10/2026, chemins abrégés) :
    ffmpeg "-hide_banner" "-t" "0.158" "-ss" "0" "-i" "C:/…/RawBox01.mp4" "-sws_flags" "spline+…"
    "-filter_complex" "tvai_up=model=prob-4:scale=0:w=1080:h=1920:…:estimate=8:blend=0.3:device=-2:
    vram=1:instances=1,scale=w=1080:h=1920:flags=lanczos:threads=0" "-c:v" "h264_nvenc" … "C:/…/RawBox01_805515910.mp4"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PureWindowsPath

FILTRE_TOPAZ = "tvai_up"  # le filtre d'IA de Topaz (Proteus, Artemis…) dans son FFmpeg

# Options placées avant « -i » qui ne servent qu'à un extrait : retirées, pour traiter toute la vidéo.
OPTIONS_D_EXTRAIT = {"-ss", "-t", "-to", "-sseof"}
# Options que l'app décide elle-même (elle les retire de la commande, puis les met à sa façon).
OPTIONS_DE_L_APP = {"-y", "-n", "-nostdin", "-stdin", "-progress", "-stats", "-nostats"}
OPTIONS_DU_GRAPHE = ("-filter_complex", "-vf", "-filter:v")
OPTIONS_SANS_VALEUR = {"-hide_banner", "-y", "-n", "-nostdin", "-stdin", "-stats", "-nostats", "-shortest", "-an", "-vn", "-sn", "-dn"}

# MP4 « fragmenté » (4.0.3) : la commande de Topaz découpe le fichier en morceaux, chacun avec son petit
# sommaire, après un sommaire de départ vide (`-movflags frag_keyframe+empty_moov+delay_moov…`) : le
# fichier reste lisible pendant l'export ou s'il est interrompu. L'interface de Topaz le finalise
# ensuite en MP4 classique ; rejouée telle quelle, la commande laissait un fichier fragmenté : pas de
# durée dans l'Explorateur de Windows, moins bien lu par certains logiciels (constaté par
# l'utilisateur le 06/10/2026). L'app écrit dans un fichier provisoire, effacé si le travail
# s'arrête : ces options ne lui servent pas. Elles ne changent ni l'image, ni le son, ni l'encodage.
DRAPEAUX_DE_FRAGMENTATION = {
    "frag_keyframe", "empty_moov", "delay_moov", "frag_custom", "frag_every_frame", "frag_discont",
    "separate_moof", "default_base_moof", "omit_tfhd_offset", "global_sidx", "skip_sidx", "skip_trailer",
    "dash", "cmaf", "isml",
}
OPTIONS_DE_FRAGMENTATION = {"-frag_duration", "-frag_size", "-min_frag_duration", "-frag_interleave"}  # avec valeur
SOMMAIRE_AU_DEBUT = "faststart"  # le sommaire (« moov ») au début : le fichier s'ouvre et s'importe plus vite


def mp4_classique(options: list[str]) -> list[str]:
    """Les options de sortie sans la fragmentation (voir DRAPEAUX_DE_FRAGMENTATION), et, quand la
    commande règle le conteneur (`-movflags`), avec le sommaire au début. Les autres drapeaux de Topaz
    (`use_metadata_tags`, `write_colr`…) sont gardés."""
    resultat: list[str] = []
    rang = 0
    while rang < len(options):
        morceau = options[rang]
        if morceau in OPTIONS_DE_FRAGMENTATION and rang + 1 < len(options):
            rang += 2
            continue
        if morceau == "-movflags" and rang + 1 < len(options):
            drapeaux = re.findall(r"([+-]?)([A-Za-z0-9_]+)", options[rang + 1])
            gardes = [f"{'-' if signe == '-' else '+'}{nom}" for signe, nom in drapeaux if nom not in DRAPEAUX_DE_FRAGMENTATION and nom != SOMMAIRE_AU_DEBUT]
            resultat += ["-movflags", "".join([f"+{SOMMAIRE_AU_DEBUT}", *gardes])]
            rang += 2
            continue
        resultat.append(morceau)
        rang += 1
    return resultat

# Noms des modèles de Topaz Video AI (les plus courants) : « prob-4 » est Proteus (version 4).
MODELES = {
    "prob": "Proteus",
    "ahq": "Artemis",
    "amq": "Artemis",
    "alq": "Artemis",
    "alqs": "Artemis",
    "aaa": "Artemis",
    "ghq": "Gaia",
    "gcg": "Gaia",
    "iris": "Iris",
    "nyx": "Nyx",
    "rhea": "Rhea",
    "thd": "Theia",
    "thf": "Theia",
    "dtd": "Dione",
    "dtds": "Dione",
    "dtv": "Dione",
    "dtvs": "Dione",
}

# Réglages de Proteus, tels que la note de Topaz (« -metadata videoai=… ») les nomme.
REGLAGES = (
    ("compression", "Revert compression"),
    ("details", "Recover details"),
    ("blur", "Sharpen"),
    ("noise", "Reduce noise"),
    ("halo", "Dehalo"),
    ("preblur", "Anti-alias/deblur"),
)


class CommandeIncomprise(ValueError):
    """La commande collée n'est pas une commande d'export de Topaz Video AI (message pour l'utilisateur)."""


def decouper(commande: str) -> list[str]:
    """Les morceaux d'une commande, comme Windows les sépare : par des espaces, sauf entre guillemets
    (Topaz met chaque morceau entre guillemets ; les « \\ » d'un chemin restent tels quels)."""
    morceaux: list[str] = []
    courant: list[str] = []
    entre_guillemets = False
    commence = False
    for lettre in commande.strip():
        if lettre == '"':
            entre_guillemets = not entre_guillemets
            commence = True
        elif lettre.isspace() and not entre_guillemets:
            if commence:
                morceaux.append("".join(courant))
                courant, commence = [], False
        else:
            courant.append(lettre)
            commence = True
    if entre_guillemets:
        raise CommandeIncomprise("Un guillemet n'est pas refermé : la commande a peut-être été coupée en la copiant.")
    if commence:
        morceaux.append("".join(courant))
    return morceaux


# --- Filtres ----------------------------------------------------------------------------------------


@dataclass
class Filtre:
    """Un filtre de FFmpeg : `tvai_up=model=prob-4:scale=0:w=1080`, `scale=w=1080:h=1920:flags=lanczos`."""

    nom: str
    options: list[tuple[str | None, str]] = field(default_factory=list)  # (nom, valeur) ; nom None : sans nom

    @staticmethod
    def lire(texte: str) -> Filtre:
        nom, _, reste = texte.partition("=")
        options: list[tuple[str | None, str]] = []
        for morceau in reste.split(":") if reste else []:
            cle, egal, valeur = morceau.partition("=")
            options.append((cle, valeur) if egal else (None, morceau))
        return Filtre(nom.strip(), options)

    def ecrire(self) -> str:
        if not self.options:
            return self.nom
        return self.nom + "=" + ":".join(valeur if cle is None else f"{cle}={valeur}" for cle, valeur in self.options)

    def valeur(self, cle: str, defaut: str | None = None) -> str | None:
        return next((v for c, v in self.options if c == cle), defaut)

    def definir(self, cle: str, valeur: str) -> None:
        for rang, (c, _v) in enumerate(self.options):
            if c == cle:
                self.options[rang] = (cle, valeur)
                return
        self.options.append((cle, valeur))


def lire_les_filtres(graphe: str) -> list[list[Filtre]]:
    """Les chaînes d'un graphe de filtres (« ; » entre deux chaînes, « , » entre deux filtres)."""
    return [[Filtre.lire(filtre) for filtre in chaine.split(",") if filtre.strip()] for chaine in graphe.split(";") if chaine.strip()]


def ecrire_les_filtres(chaines: list[list[Filtre]]) -> str:
    return ";".join(",".join(filtre.ecrire() for filtre in chaine) for chaine in chaines)


# --- La taille finale --------------------------------------------------------------------------------

PETIT_COTE_1080P, PETIT_COTE_1440P = 1080, 1440
PETIT_COTE_MIN, PETIT_COTE_MAX = 144, 8640


def pair_le_plus_proche(valeur: float) -> int:
    """Le nombre pair le plus proche (une vidéo H.264 ou H.265 en 4:2:0 n'accepte que des tailles
    paires) : 1077,3 → 1078 ; 1924,75 → 1924."""
    return max(2, 2 * round(valeur / 2))


def taille_finale(largeur: int, hauteur: int, petit_cote: int) -> tuple[int, int]:
    """Taille finale d'une vidéo (telle qu'on la voit, redressée) : son petit côté à `petit_cote` (le
    sens de « 1080p »), l'autre côté calculé pour garder exactement son ratio, au nombre pair le plus
    proche. Jamais d'étirement : 606 × 1080 → 1080 × 1924 (et non 1080 × 1920) ; 1920 × 1080 →
    1920 × 1080 ; une vidéo verticale en 9:16 → 1080 × 1920."""
    if largeur <= 0 or hauteur <= 0:
        raise ValueError("taille inconnue")
    if largeur <= hauteur:
        return petit_cote, pair_le_plus_proche(hauteur * petit_cote / largeur)
    return pair_le_plus_proche(largeur * petit_cote / hauteur), petit_cote


# --- Le préréglage -------------------------------------------------------------------------------------


@dataclass
class Prereglage:
    """Une commande de Topaz comprise (voir en haut du fichier). Les chemins de la vidéo d'origine n'y
    sont pas gardés."""

    nom: str
    avant_entree: list[str]  # options avant « -i » (sans les options d'extrait ni celles de l'app)
    apres_entree: list[str]  # le reste, dans l'ordre de Topaz : filtres, encodage, son… (sans le fichier écrit)
    extension: str  # « .mp4 », « .mov »… : le format du fichier écrit par Topaz

    # --- Ce que dit la commande ---

    def _rang_du_graphe(self) -> int:
        """Place de l'option du graphe de filtres (« -filter_complex » ou « -vf ») dans apres_entree."""
        for rang, morceau in enumerate(self.apres_entree[:-1]):
            if morceau in OPTIONS_DU_GRAPHE and FILTRE_TOPAZ in self.apres_entree[rang + 1]:
                return rang
        raise CommandeIncomprise("Il manque le filtre de Topaz (tvai_up).")

    @property
    def graphe(self) -> str:
        return self.apres_entree[self._rang_du_graphe() + 1]

    def _topaz(self) -> Filtre:
        for chaine in lire_les_filtres(self.graphe):
            for filtre in chaine:
                if filtre.nom == FILTRE_TOPAZ:
                    return filtre
        raise CommandeIncomprise("Il manque le filtre de Topaz (tvai_up).")

    @property
    def modele(self) -> str:
        return self._topaz().valeur("model", "") or ""

    def nom_du_modele(self) -> str:
        """« Proteus (prob-4) »."""
        code = self.modele
        famille = MODELES.get(code.split("-")[0], "")
        return f"{famille} ({code})" if famille else code

    def option(self, nom: str) -> str | None:
        """Valeur d'une option de l'encodage (« -c:v » → « h264_nvenc »), ou None."""
        for rang, morceau in enumerate(self.apres_entree[:-1]):
            if morceau == nom:
                return self.apres_entree[rang + 1]
        return None

    @property
    def automatique(self) -> bool:
        """Mode automatique de Proteus : le moteur de Topaz estime lui-même les réglages (estimate)."""
        estimation = self._topaz().valeur("estimate", "0") or "0"
        try:
            return float(estimation) > 0
        except ValueError:
            return False

    def son_copie(self) -> bool:
        return self.option("-c:a") == "copy" or self.option("-acodec") == "copy"

    def resume(self) -> list[str]:
        """Ce que fait le préréglage, en français, une idée par ligne."""
        topaz = self._topaz()
        lignes = [f"Modèle : {self.nom_du_modele()}" + (", réglages estimés par Topaz sur chaque vidéo (mode automatique)" if self.automatique else "")]
        reglages = []
        for cle, nom in REGLAGES:
            valeur = topaz.valeur(cle)
            if valeur is not None and not self.automatique:
                reglages.append(f"{nom} {_pour_cent(valeur)}")
        melange = topaz.valeur("blend")
        if melange is not None:
            reglages.append(f"Recover original detail {_pour_cent(melange)}")
        if reglages:
            lignes.append("Réglages : " + ", ".join(reglages))
        autres = [filtre.nom for chaine in lire_les_filtres(self.graphe) for filtre in chaine if filtre.nom.startswith("tvai_") and filtre.nom != FILTRE_TOPAZ]
        if autres:
            lignes.append("Autres filtres de Topaz : " + ", ".join(autres))
        encodeur = self.option("-c:v") or self.option("-vcodec") or "?"
        debit = self.option("-b:v")
        controle = self.option("-rc")
        details = [_nom_de_l_encodeur(encodeur)]
        if debit:
            details.append(f"{_debit_lisible(debit)}" + (" constant" if controle == "cbr" else ""))
        qualite = self.option("-global_quality") or self.option("-crf") or self.option("-cq") or self.option("-qp")
        if qualite and not debit:
            details.append(f"qualité {qualite}")
        if self.option("-profile:v"):
            details.append(f"profil {self.option('-profile:v')}")
        lignes.append("Encodage : " + ", ".join(details))
        lignes.append("Son : copié tel quel" if self.son_copie() else ("Son : aucun" if "-an" in self.apres_entree else f"Son : {self.option('-c:a') or 'réencodé'}"))
        if self.option("-fps_mode:v") == "passthrough" or self.option("-vsync") in ("passthrough", "0"):
            lignes.append("Cadence : celle de chaque vidéo, image par image")
        lignes.append(f"Fichier : {self.extension.lstrip('.').upper()}")
        return lignes

    # --- La commande pour une vidéo ---

    def arguments(self, entree: str, sortie: str, largeur: int, hauteur: int) -> list[str]:
        """Les arguments du FFmpeg de Topaz pour une vidéo (sans le programme lui-même) : la commande
        collée, avec cette vidéo, ce fichier, cette taille ; l'avancement est écrit sur la sortie
        standard (« -progress pipe:1 »)."""
        chaines = lire_les_filtres(self.graphe)
        topaz = None
        for chaine in chaines:
            for rang, filtre in enumerate(chaine):
                if filtre.nom == FILTRE_TOPAZ and topaz is None:
                    topaz = filtre
                    filtre.definir("scale", "0")  # le moteur choisit son agrandissement pour arriver à w × h
                    filtre.definir("w", str(largeur))
                    filtre.definir("h", str(hauteur))
                    # Le dernier ajustement de Topaz (`scale`, juste après), à la même taille ; sans lui,
                    # on l'ajoute : la vidéo a exactement la taille annoncée.
                    suivant = chaine[rang + 1] if rang + 1 < len(chaine) else None
                    if suivant is not None and suivant.nom == "scale":
                        suivant.definir("w", str(largeur))
                        suivant.definir("h", str(hauteur))
                    else:
                        chaine.insert(rang + 1, Filtre("scale", [("w", str(largeur)), ("h", str(hauteur)), ("flags", "lanczos")]))
        if topaz is None:
            raise CommandeIncomprise("Il manque le filtre de Topaz (tvai_up).")
        apres = list(self.apres_entree)
        apres[self._rang_du_graphe() + 1] = ecrire_les_filtres(chaines)
        for rang, morceau in enumerate(apres[:-1]):
            if morceau == "-metadata" and apres[rang + 1].startswith("videoai="):
                # La note de Topaz dit la taille : on la met à jour (« Changed resolution to 1080x1924 »).
                apres[rang + 1] = re.sub(r"\d+x\d+", f"{largeur}x{hauteur}", apres[rang + 1])
        # Options de l'app (globales, valables à toute place) : ni clavier, ni nouvelles à l'écran, mais
        # l'avancement en « clé=valeur » sur la sortie standard ; le fichier provisoire est réécrit.
        return [
            *(["-hide_banner"] if "-hide_banner" not in self.avant_entree else []),
            "-nostdin",
            "-nostats",
            "-y",
            "-progress",
            "pipe:1",
            *self.avant_entree,
            "-i",
            entree,
            *mp4_classique(apres),
            sortie,
        ]

    # --- Enregistrement ---

    def en_donnees(self) -> dict:
        return {"nom": self.nom, "avant_entree": self.avant_entree, "apres_entree": self.apres_entree, "extension": self.extension}

    @staticmethod
    def depuis(donnees) -> Prereglage | None:
        try:
            prereglage = Prereglage(
                str(donnees["nom"]),
                [str(m) for m in donnees["avant_entree"]],
                [str(m) for m in donnees["apres_entree"]],
                str(donnees["extension"]),
            )
            prereglage._topaz()
            return prereglage
        except (KeyError, TypeError, ValueError):
            return None


def _pour_cent(valeur: str) -> str:
    """« 0.3 » → « 30 » (Topaz montre ses curseurs de 0 à 100)."""
    try:
        return f"{round(float(valeur) * 100)}"
    except ValueError:
        return valeur


def _debit_lisible(debit: str) -> str:
    """« 24M » → « 24 Mb/s » ; « 8000k » → « 8 Mb/s »."""
    trouve = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM]?)", debit)
    if not trouve:
        return debit
    nombre, unite = float(trouve.group(1)), trouve.group(2).lower()
    mega = nombre / 1000 if unite == "k" else nombre if unite == "m" else nombre / 1_000_000
    return f"{mega:g} Mb/s".replace(".", ",")


def _nom_de_l_encodeur(encodeur: str) -> str:
    noms = {
        "h264_nvenc": "H.264 (carte NVIDIA)",
        "hevc_nvenc": "H.265 (carte NVIDIA)",
        "av1_nvenc": "AV1 (carte NVIDIA)",
        "h264_qsv": "H.264 (Intel)",
        "hevc_qsv": "H.265 (Intel)",
        "h264_amf": "H.264 (carte AMD)",
        "hevc_amf": "H.265 (carte AMD)",
        "libx264": "H.264",
        "libx265": "H.265",
        "prores_ks": "ProRes",
        "ffv1": "FFV1 (sans perte)",
    }
    return noms.get(encodeur, encodeur)


def comprendre(commande: str, nom: str = "") -> Prereglage:
    """La commande collée (« FFmpeg Command » de Topaz) devient un préréglage. CommandeIncomprise si
    ce n'est pas une commande d'export de Topaz Video AI, avec la raison."""
    morceaux = decouper(commande)
    if not morceaux:
        raise CommandeIncomprise("La commande est vide.")
    if PureWindowsPath(morceaux[0].replace("/", "\\")).stem.lower() == "ffmpeg":
        morceaux = morceaux[1:]
    if "-i" not in morceaux:
        raise CommandeIncomprise("Il manque la vidéo lue (« -i ») : copie la commande entière, depuis « ffmpeg ».")
    if morceaux.count("-i") > 1:
        raise CommandeIncomprise("Cette commande lit plusieurs fichiers : le module n'en traite qu'un à la fois.")
    position = morceaux.index("-i")
    if position + 1 >= len(morceaux):
        raise CommandeIncomprise("Il manque la vidéo lue après « -i ».")
    avant = _retirer(morceaux[:position], OPTIONS_D_EXTRAIT | OPTIONS_DE_L_APP)
    reste = _retirer(morceaux[position + 2 :], OPTIONS_DE_L_APP)
    if not reste or reste[-1].startswith("-"):
        raise CommandeIncomprise("Il manque le fichier écrit, à la fin de la commande.")
    sortie = reste[-1]
    reste = reste[:-1]
    if not any(morceau in OPTIONS_DU_GRAPHE and FILTRE_TOPAZ in suivant for morceau, suivant in zip(reste, reste[1:])):
        raise CommandeIncomprise(
            "Ce n'est pas une commande d'export de Topaz Video AI : le filtre de ses modèles (tvai_up) n'y est pas."
        )
    extension = PureWindowsPath(sortie.replace("/", "\\")).suffix.lower() or ".mp4"
    prereglage = Prereglage(nom.strip(), avant, reste, extension)
    if not prereglage.modele:
        raise CommandeIncomprise("Le modèle de Topaz (model=…) n'est pas indiqué dans la commande.")
    if not prereglage.nom:
        prereglage.nom = prereglage.nom_du_modele().split(" (")[0]
    return prereglage


def _retirer(morceaux: list[str], options: set[str]) -> list[str]:
    """Les morceaux sans ces options (et sans leur valeur, pour celles qui en ont une)."""
    resultat: list[str] = []
    rang = 0
    while rang < len(morceaux):
        morceau = morceaux[rang]
        if morceau in options:
            rang += 1 if morceau in OPTIONS_SANS_VALEUR else 2
            continue
        resultat.append(morceau)
        rang += 1
    return resultat
