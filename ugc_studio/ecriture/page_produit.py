"""Lecture d'une page produit par l'app elle-même (V2, §10.4, étape 1) : gratuite, toujours à jour,
et exacte pour une boutique Shopify.

- **Boutique Shopify** : Shopify donne les données du produit à une adresse officielle, celle de la
  page suivie de « .js » (« Ajax API ») : nom, description, prix et prix barré en centimes (donc la
  promo exacte), variantes, marque, type de produit. Si l'adresse désigne une variante précise
  (« ?variant=… »), son prix est retenu ; sinon celui de la première variante disponible, comme la
  page l'affiche.
- **Autre site** : les informations que la plupart des boutiques glissent dans leurs pages pour
  Google (données « JSON-LD » de type Product, balises « og: ») : nom, prix, devise, note moyenne,
  nombre d'avis ; plus le texte visible de la page.

La page est demandée comme le ferait un navigateur. Si rien d'utilisable n'est lu (site qui bloque
les lectures automatiques, page qui ne se remplit qu'une fois ouverte dans un navigateur), une
ErreurLecture explique pourquoi : l'app demande alors à Google de lire la page (redaction.py),
sinon propose de coller le texte.

Le texte lu est une matière pour le modèle, jamais une consigne (voir consignes.py).
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import zlib
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .. import __version__
from ..fournisseurs.base import ErreurFournisseur
from ..fournisseurs.http import requete
from .brief import SYMBOLES_DEVISE

journal = logging.getLogger(__name__)

DELAI_PAGE = 20  # secondes
TAILLE_MAX_PAGE = 5_000_000  # octets lus au plus (une page produit en fait rarement plus de 2 Mo)
TEXTE_MAX = 20_000  # caractères gardés pour le modèle (le début de la page, où est le produit)
TEXTE_VISIBLE_MIN = 400  # en dessous, la page ne montre sans doute pas le produit sans navigateur
VARIANTES_AFFICHEES = 12  # valeurs listées par option (tailles, couleurs…)
AVIS_GARDES = 3

# Sources possibles du texte donné au modèle, et comment l'app le dit.
SHOPIFY = "shopify"
PAGE = "page"
GOOGLE = "google"
TEXTE_COLLE = "texte"
LIBELLES_SOURCES = {
    SHOPIFY: "Lu par l'app (données Shopify)",
    PAGE: "Lu par l'app",
    GOOGLE: "Lu par Google",
    TEXTE_COLLE: "Texte collé",
}


class ErreurLecture(Exception):
    """La page n'a pas pu être lue par l'app. `code` : « adresse », « reseau », « bloquee »,
    « introuvable », « vide » ou « pas_une_page » ; `message` : phrase claire en français."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code

    @property
    def google_peut_essayer(self) -> bool:
        """Une adresse invalide ou une page qui n'existe pas : Google n'y arrivera pas mieux."""
        return self.code not in ("adresse", "introuvable", "pas_une_page")


@dataclass
class PageLue:
    """Ce qui a été lu d'une page produit, et d'où ça vient."""

    adresse: str
    source: str  # SHOPIFY, PAGE, GOOGLE ou TEXTE_COLLE
    lu_le: str  # date et heure de la lecture (ISO)
    texte: str  # ce qui est donné au modèle
    nom: str = ""
    marque: str = ""
    prix: str = ""  # prix exact lu par l'app (ex. « 21,90 € »), vide si inconnu
    prix_barre: str = ""  # prix barré (promo), vide s'il n'y en a pas
    devise: str = ""

    def en_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, brut) -> PageLue | None:
        if not isinstance(brut, dict) or not brut.get("source"):
            return None
        valeurs = {c.name: str(brut.get(c.name) or "") for c in fields(cls)}
        return cls(**valeurs)


def maintenant() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- Adresse -------------------------------------------------------------------------------------


def normaliser_adresse(texte: str) -> str:
    """Adresse complète (« https://… ») à partir de ce qui a été collé ; ErreurLecture si ce n'est
    pas une adresse web."""
    adresse = texte.strip().strip("<>\"'")
    if adresse and "://" not in adresse:
        adresse = "https://" + adresse
    morceaux = urlsplit(adresse)
    hote = morceaux.hostname or ""
    if morceaux.scheme not in ("http", "https") or not hote or ("." not in hote and hote != "localhost"):
        raise ErreurLecture(
            "Cette adresse n'est pas valide : copie-la depuis la barre d'adresse de ton navigateur "
            "(elle commence par https://).",
            "adresse",
        )
    return urlunsplit(morceaux._replace(fragment=""))


def adresse_shopify(adresse: str) -> str | None:
    """Adresse des données Shopify d'une page produit (« …/products/<nom>.js »), ou None si
    l'adresse n'est pas celle d'un produit."""
    morceaux = urlsplit(adresse)
    trouve = re.search(r"/products/([^/?#]+)", morceaux.path)
    if not trouve:
        return None
    chemin = morceaux.path[: trouve.end()].removesuffix(".js").removesuffix(".json") + ".js"
    return urlunsplit(morceaux._replace(path=chemin, query="", fragment=""))


def variante_demandee(adresse: str) -> int | None:
    valeur = parse_qs(urlsplit(adresse).query).get("variant", [""])[0]
    return int(valeur) if valeur.isdigit() else None


# --- Téléchargement ------------------------------------------------------------------------------


def entetes_navigateur(langue: str) -> dict[str, str]:
    """En-têtes d'un navigateur ordinaire : sans eux, beaucoup de boutiques refusent la page."""
    base = langue.split("-")[0]
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/140.0.0.0 Safari/537.36 UGC-Studio/{__version__}"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{langue},{base};q=0.9,en;q=0.5",
    }


def _decoder(corps: bytes, entetes: dict[str, str]) -> str:
    entetes = {k.lower(): v for k, v in entetes.items()}
    encodage = entetes.get("content-encoding", "").lower()
    try:
        if encodage == "gzip":
            corps = gzip.decompress(corps)
        elif encodage == "deflate":
            corps = zlib.decompress(corps)
    except (OSError, zlib.error, EOFError):
        journal.warning("Page compressée illisible (%s)", encodage)
    jeu = re.search(r"charset=([\w-]+)", entetes.get("content-type", ""), re.IGNORECASE)
    if jeu is None:
        jeu = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", corps[:4096], re.IGNORECASE)
        nom = jeu.group(1).decode("ascii", "ignore") if jeu else "utf-8"
    else:
        nom = jeu.group(1)
    try:
        return corps.decode(nom, errors="replace")
    except LookupError:
        return corps.decode("utf-8", errors="replace")


def _telecharger(adresse: str, langue: str, accepter: str | None = None) -> tuple[str, dict[str, str]]:
    """Contenu texte de l'adresse ; ErreurLecture si le site refuse ou si la page n'existe pas."""
    entetes = entetes_navigateur(langue)
    if accepter:
        entetes["Accept"] = accepter
    try:
        reponse = requete("GET", adresse, entetes=entetes, delai=DELAI_PAGE, taille_max=TAILLE_MAX_PAGE)
    except ErreurFournisseur as erreur:
        raise ErreurLecture(
            "Impossible de joindre ce site : vérifie l'adresse et ta connexion Internet.", "reseau"
        ) from erreur
    if reponse.statut in (404, 410):
        raise ErreurLecture(f"Cette page n'existe pas (code {reponse.statut}) : vérifie l'adresse.", "introuvable")
    if reponse.statut >= 400:
        raise ErreurLecture(f"Le site bloque les lectures automatiques (code {reponse.statut}).", "bloquee")
    return _decoder(reponse.corps, reponse.entetes), reponse.entetes


# --- Analyse du HTML -----------------------------------------------------------------------------

# Éléments dont le texte n'est pas du contenu : code, styles, dessins, menus, listes de choix.
# (Le texte caché, lui, est gardé : les onglets « Livraison et retours » d'une page produit sont
# souvent cachés jusqu'au clic, et c'est justement l'offre.)
_IGNORES = {"script", "style", "noscript", "svg", "template", "iframe", "nav", "select", "textarea"}
_BLOCS = {
    "p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "section", "article",
    "header", "footer", "main", "aside", "ul", "ol", "table", "dd", "dt", "blockquote", "summary", "details",
    "figcaption", "label", "button",
}
_VIDES = {"br", "img", "meta", "link", "input", "hr", "source", "wbr", "area", "base", "col", "embed", "param", "track"}


class _AnalyseurHtml(HTMLParser):
    """Lit une page : texte visible, balises « meta », titre et blocs de données JSON-LD."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metas: dict[str, str] = {}
        self.titre = ""
        self.json_ld: list[str] = []
        self.morceaux: list[str] = []
        # Élément ignoré en cours (ex. « script ») et nombre d'éléments du même nom ouverts dedans.
        self._ignore: tuple[str, int] | None = None
        self._dans_titre = False
        self._dans_json_ld = False
        self._json_courant: list[str] = []

    def handle_starttag(self, balise: str, attributs) -> None:
        attributs = {nom: (valeur or "") for nom, valeur in attributs}
        if balise == "meta":
            cle = (attributs.get("property") or attributs.get("name") or attributs.get("itemprop") or "").lower()
            if cle and "content" in attributs and cle not in self.metas:
                self.metas[cle] = unescape(attributs["content"]).strip()
            return
        if balise == "title":
            self._dans_titre = True
        if balise == "script" and "ld+json" in attributs.get("type", "").lower():
            self._dans_json_ld = True
            self._json_courant = []
        if balise in _VIDES:
            if balise == "br" and self._ignore is None:
                self.morceaux.append("\n")
            return
        if self._ignore is not None:
            if balise == self._ignore[0]:
                self._ignore = (balise, self._ignore[1] + 1)
            return
        if balise in _IGNORES:
            self._ignore = (balise, 1)
        elif balise in _BLOCS:
            self.morceaux.append("\n")

    def handle_endtag(self, balise: str) -> None:
        if balise == "title":
            self._dans_titre = False
        if balise == "script" and self._dans_json_ld:
            self._dans_json_ld = False
            self.json_ld.append("".join(self._json_courant))
        if self._ignore is not None:
            if balise == self._ignore[0]:
                profondeur = self._ignore[1] - 1
                self._ignore = (balise, profondeur) if profondeur > 0 else None
            return
        if balise in _BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, donnees: str) -> None:
        if self._dans_json_ld:
            self._json_courant.append(donnees)
            return
        if self._dans_titre:
            if not self.titre:
                self.titre = " ".join(donnees.split())
            return
        if self._ignore is None:
            self.morceaux.append(donnees)

    def texte_visible(self) -> str:
        """Texte de la page, une ligne par bloc, sans les lignes répétées (les thèmes répètent
        souvent le même contenu pour l'écran du téléphone et celui de l'ordinateur)."""
        lignes, vues = [], set()
        for ligne in "".join(self.morceaux).split("\n"):
            ligne = " ".join(ligne.split())
            if len(ligne) < 2 or ligne.casefold() in vues:
                continue
            vues.add(ligne.casefold())
            lignes.append(ligne)
        return "\n".join(lignes)


def _objets(donnees) -> list[dict]:
    """Tous les objets d'un bloc JSON-LD (listes, « @graph » et objets imbriqués compris)."""
    trouves: list[dict] = []
    if isinstance(donnees, list):
        for element in donnees:
            trouves += _objets(element)
    elif isinstance(donnees, dict):
        trouves.append(donnees)
        for valeur in donnees.values():
            if isinstance(valeur, (dict, list)):
                trouves += _objets(valeur)
    return trouves


def _est_produit(objet: dict) -> bool:
    types = objet.get("@type")
    types = types if isinstance(types, list) else [types]
    return any(str(t).lower() in ("product", "productgroup") for t in types)


def produits_json_ld(blocs: list[str]) -> list[dict]:
    """Objets « Product » des données JSON-LD de la page (les blocs illisibles sont ignorés)."""
    produits = []
    for bloc in blocs:
        bloc = bloc.strip().removeprefix("<!--").removesuffix("-->").strip()
        try:
            donnees = json.loads(bloc)
        except ValueError:
            continue
        produits += [o for o in _objets(donnees) if _est_produit(o)]
    return produits


def _texte(valeur) -> str:
    if isinstance(valeur, dict):
        valeur = valeur.get("name") or valeur.get("@value") or ""
    if isinstance(valeur, list):
        valeur = valeur[0] if valeur else ""
    return " ".join(unescape(str(valeur or "")).split())


# --- Prix ----------------------------------------------------------------------------------------


def _decimal(valeur) -> Decimal | None:
    if valeur is None or valeur == "":
        return None
    try:
        return Decimal(str(valeur).replace(",", ".").replace(" ", "").replace(" ", ""))
    except InvalidOperation:
        return None


def formater_prix(montant: Decimal | None, devise: str, langue: str = "fr-FR") -> str:
    """Prix lisible : 21.9 € en français → « 21,90 € » ; en anglais → « €21.90 »."""
    if montant is None:
        return ""
    symbole = SYMBOLES_DEVISE.get(devise, devise)
    chiffres = f"{montant:.2f}"
    if langue.startswith("en"):
        return f"{symbole}{chiffres}" if len(symbole) == 1 else f"{chiffres} {symbole}"
    return f"{chiffres.replace('.', ',')} {symbole}".strip()


def remise(prix: Decimal | None, prix_barre: Decimal | None) -> int:
    """Remise en pourcentage, arrondie vers le bas (une remise ne doit jamais paraître plus forte
    qu'elle n'est : 21,90 € au lieu de 27,90 € font 21,5 %, donc « 21 % ») ; 0 sans prix barré."""
    if prix is None or prix_barre is None or prix_barre <= prix or prix_barre <= 0:
        return 0
    return int((prix_barre - prix) / prix_barre * 100)


def devise_de_la_page(html: str, metas: dict[str, str], produits: list[dict]) -> str:
    for cle in ("og:price:currency", "product:price:currency"):
        if re.fullmatch(r"[A-Za-z]{3}", metas.get(cle, "")):
            return metas[cle].upper()
    for produit in produits:
        for offre in _objets(produit.get("offers")):
            if re.fullmatch(r"[A-Za-z]{3}", str(offre.get("priceCurrency") or "")):
                return str(offre["priceCurrency"]).upper()
    trouve = re.search(r"Shopify\.currency\s*=\s*\{[^}]*\"active\"\s*:\s*\"([A-Z]{3})\"", html)
    return trouve.group(1) if trouve else ""


# --- Shopify -------------------------------------------------------------------------------------


def _valeurs_des_options(produit: dict) -> list[tuple[str, list[str]]]:
    noms = []
    for option in produit.get("options") or []:
        noms.append(str(option.get("name") if isinstance(option, dict) else option))
    resultat = []
    for rang, nom in enumerate(noms[:3], start=1):
        valeurs: list[str] = []
        for variante in produit.get("variants") or []:
            valeur = str(variante.get(f"option{rang}") or "").strip()
            if valeur and valeur not in valeurs:
                valeurs.append(valeur)
        resultat.append((nom, valeurs))
    return resultat


def texte_shopify(produit: dict, variante_id: int | None, devise: str, langue: str) -> tuple[str, dict]:
    """Texte des données Shopify pour le modèle, et les valeurs exactes (nom, marque, prix…)."""
    variantes = [v for v in produit.get("variants") or [] if isinstance(v, dict)]
    choisie = next((v for v in variantes if v.get("id") == variante_id), None)
    if choisie is None:
        choisie = next((v for v in variantes if v.get("available")), variantes[0] if variantes else {})

    def montant(centimes) -> Decimal | None:
        valeur = _decimal(centimes)
        return None if valeur is None else valeur / 100

    prix = montant(choisie.get("price", produit.get("price")))
    prix_barre = montant(choisie.get("compare_at_price", produit.get("compare_at_price")))
    if prix_barre is not None and prix is not None and prix_barre <= prix:
        prix_barre = None
    exacts = {
        "nom": _texte(produit.get("title")),
        "marque": _texte(produit.get("vendor")),
        "prix": formater_prix(prix, devise, langue),
        "prix_barre": formater_prix(prix_barre, devise, langue),
    }
    lignes = ["Données de la boutique (Shopify, exactes) :", f"- Nom : {exacts['nom']}"]
    if exacts["marque"]:
        lignes.append(f"- Marque : {exacts['marque']}")
    if produit.get("type"):
        lignes.append(f"- Type de produit : {_texte(produit.get('type'))}")
    if exacts["prix"]:
        ligne = f"- Prix : {exacts['prix']}"
        if exacts["prix_barre"]:
            ligne += f" au lieu de {exacts['prix_barre']} (remise de {remise(prix, prix_barre)} %)"
        lignes.append(ligne)
    if choisie and choisie.get("id") == variante_id and choisie.get("title"):
        lignes.append(f"- Variante de l'adresse : {_texte(choisie.get('title'))}")
    if choisie and choisie.get("available") is False:
        lignes.append("- Disponibilité : épuisé")
    prix_variantes = sorted(p for p in (montant(v.get("price")) for v in variantes) if p is not None)
    if prix_variantes and prix_variantes[0] != prix_variantes[-1]:
        lignes.append(
            f"- Prix selon les variantes : de {formater_prix(prix_variantes[0], devise, langue)} "
            f"à {formater_prix(prix_variantes[-1], devise, langue)}"
        )
    options = [(nom, valeurs) for nom, valeurs in _valeurs_des_options(produit) if valeurs and nom.lower() != "title"]
    if len(variantes) > 1:
        detail = " ; ".join(
            f"{nom} : {', '.join(valeurs[:VARIANTES_AFFICHEES])}{'…' if len(valeurs) > VARIANTES_AFFICHEES else ''}"
            for nom, valeurs in options
        )
        lignes.append(f"- Variantes ({len(variantes)}) : {detail}" if detail else f"- Variantes : {len(variantes)}")
    etiquettes = produit.get("tags")
    if isinstance(etiquettes, list) and etiquettes:
        lignes.append(f"- Étiquettes : {', '.join(str(e) for e in etiquettes[:20])}")
    description = texte_de_html(str(produit.get("description") or ""))
    if description:
        lignes += ["", "Description du produit :", description]
    return "\n".join(lignes), exacts


def texte_de_html(html: str) -> str:
    analyseur = _AnalyseurHtml()
    analyseur.feed(html)
    analyseur.close()
    return analyseur.texte_visible()


def _lire_shopify(adresse: str, langue: str) -> dict | None:
    adresse_js = adresse_shopify(adresse)
    if adresse_js is None:
        return None
    try:
        contenu, _entetes = _telecharger(adresse_js, langue, "application/json, text/javascript, */*;q=0.1")
        donnees = json.loads(contenu)
    except (ErreurLecture, ValueError) as erreur:
        journal.info("Pas de données Shopify pour cette page (%s)", erreur)
        return None
    if isinstance(donnees, dict) and isinstance(donnees.get("variants"), list) and donnees.get("title"):
        return donnees
    return None


# --- Données de la page (autres sites) -----------------------------------------------------------


def texte_donnees_page(metas: dict[str, str], produits: list[dict], devise: str, langue: str) -> tuple[str, dict]:
    """Données que la boutique glisse dans sa page pour Google (JSON-LD, balises og:)."""
    produit = produits[0] if produits else {}
    offres = _objets(produit.get("offers"))
    offre = offres[0] if offres else {}
    prix = _decimal(offre.get("price") or offre.get("lowPrice"))
    if prix is None:
        prix = _decimal(metas.get("og:price:amount") or metas.get("product:price:amount"))
    devise = str(offre.get("priceCurrency") or devise or "").upper()
    exacts = {
        "nom": _texte(produit.get("name")) or metas.get("og:title", ""),
        "marque": _texte(produit.get("brand")) or metas.get("og:site_name", ""),
        "prix": formater_prix(prix, devise, langue) if devise else "",
        "prix_barre": "",
    }
    lignes = []
    if exacts["nom"]:
        lignes.append(f"- Nom : {exacts['nom']}")
    if exacts["marque"]:
        lignes.append(f"- Marque : {exacts['marque']}")
    if exacts["prix"]:
        lignes.append(f"- Prix : {exacts['prix']}")
    note = produit.get("aggregateRating") if isinstance(produit.get("aggregateRating"), dict) else {}
    if note.get("ratingValue"):
        nombre = note.get("reviewCount") or note.get("ratingCount")
        lignes.append(f"- Note moyenne : {note['ratingValue']}/{note.get('bestRating') or 5}" + (f" ({nombre} avis)" if nombre else ""))
    avis = [a for a in _objets(produit.get("review")) if isinstance(a, dict) and (a.get("reviewBody") or a.get("description"))]
    for un_avis in avis[:AVIS_GARDES]:
        # Le corps de l'avis seulement : jamais le nom de son auteur (une personne réelle).
        lignes.append(f"- Avis : « {_texte(un_avis.get('reviewBody') or un_avis.get('description'))[:300]} »")
    description = _texte(produit.get("description")) or metas.get("og:description") or metas.get("description", "")
    if description:
        lignes.append(f"- Description : {description}")
    if not lignes:
        return "", exacts
    return "\n".join(["Données de la page (pour les moteurs de recherche) :", *lignes]), exacts


# --- Lecture complète ------------------------------------------------------------------------------


def lire_page(adresse: str, langue: str = "fr-FR", devise_par_defaut: str = "EUR") -> PageLue:
    """Lit la page produit (à lancer en tâche de fond). ErreurLecture si rien d'utilisable n'est lu."""
    adresse = normaliser_adresse(adresse)
    html, erreur_page = "", None
    try:
        html, entetes = _telecharger(adresse, langue)
        type_contenu = {k.lower(): v for k, v in entetes.items()}.get("content-type", "text/html").lower()
        if "html" not in type_contenu and "xml" not in type_contenu:
            raise ErreurLecture(
                f"Cette adresse ne mène pas à une page web (contenu « {type_contenu.split(';')[0]} »).", "pas_une_page"
            )
    except ErreurLecture as erreur:
        if not erreur.google_peut_essayer or adresse_shopify(adresse) is None:
            raise
        erreur_page = erreur  # les données Shopify sont parfois lisibles quand la page ne l'est pas

    analyseur = _AnalyseurHtml()
    if html:
        analyseur.feed(html)
        analyseur.close()
    visible = analyseur.texte_visible()
    produits = produits_json_ld(analyseur.json_ld)
    devise = devise_de_la_page(html, analyseur.metas, produits) or devise_par_defaut
    indices_shopify = "cdn.shopify.com" in html or "Shopify.theme" in html

    shopify = _lire_shopify(adresse, langue) if (adresse_shopify(adresse) or indices_shopify) else None
    if shopify is not None:
        donnees, exacts = texte_shopify(shopify, variante_demandee(adresse), devise, langue)
        source = SHOPIFY
    else:
        donnees, exacts = texte_donnees_page(analyseur.metas, produits, devise, langue)
        source = PAGE
        if not produits and len(visible) < TEXTE_VISIBLE_MIN:
            if erreur_page is not None:
                raise erreur_page
            raise ErreurLecture(
                "La page ne contient presque pas de texte : elle ne se remplit sans doute qu'une fois "
                "ouverte dans un navigateur.",
                "vide",
            )
    morceaux = [donnees] if donnees else []
    if visible:
        morceaux.append(f"Texte de la page :\n{visible}")
    texte = "\n\n".join(morceaux)[:TEXTE_MAX]
    return PageLue(
        adresse=adresse,
        source=source,
        lu_le=maintenant(),
        texte=texte,
        nom=exacts["nom"],
        marque=exacts["marque"],
        prix=exacts["prix"],
        prix_barre=exacts["prix_barre"],
        devise=devise,
    )


def page_collee(texte: str, adresse: str = "") -> PageLue:
    """Texte de la page collé à la main (description, prix, quelques avis)."""
    propre = "\n".join(" ".join(ligne.split()) for ligne in texte.splitlines())
    propre = re.sub(r"\n{3,}", "\n\n", propre).strip()[:TEXTE_MAX]
    return PageLue(adresse=adresse.strip(), source=TEXTE_COLLE, lu_le=maintenant(), texte=propre)
