"""Module Script (V2) : lecture d'une page produit par l'app (Shopify, autre site, refus), avec un
serveur local qui imite les boutiques (aucun accès à Internet)."""

import json
from decimal import Decimal

import pytest

from serveur_factice import ServeurFactice
from ugc_studio.ecriture.page_produit import (
    PAGE,
    SHOPIFY,
    TEXTE_COLLE,
    ErreurLecture,
    PageLue,
    adresse_shopify,
    formater_prix,
    lire_page,
    normaliser_adresse,
    page_collee,
    remise,
    texte_de_html,
)

HTML = {"Content-Type": "text/html; charset=utf-8"}

# Extrait d'une page produit Shopify (thème, menu, bandeau, onglet « Livraison » caché jusqu'au clic).
PAGE_SHOPIFY = """<!doctype html><html><head><title>Culotte menstruelle Léa</title>
<meta property="og:price:amount" content="21,90"><meta property="og:price:currency" content="EUR">
<script>Shopify.theme = {"name": "Dawn"};</script><style>.a{color:red}</style></head>
<body><nav><a>Culottes</a><a>Maillots</a></nav>
<div class="annonce">Livraison offerte en France métropolitaine</div>
<main><h1>Culotte menstruelle Léa</h1><p>Au sec jusqu'à 12H, 4 couches absorbantes.</p>
<select><option>XS</option><option>6XL</option></select>
<details><summary>Livraison et retours</summary><div hidden>Échanges gratuits pendant 30 jours.</div></details>
<div class="mobile">Au sec jusqu'à 12H, 4 couches absorbantes.</div></main>
<svg><text>dessin</text></svg></body></html>"""

PRODUIT_SHOPIFY = {
    "title": "Culotte menstruelle Léa",
    "vendor": "Mademoiselle Culotte",
    "type": "Culotte menstruelle",
    "tags": ["menstruelle", "flux abondant"],
    "price": 2190,
    "compare_at_price": 2790,
    "options": ["Couleur", "Taille"],
    "description": "<p>Une culotte <strong>douce</strong> et absorbante.</p>",
    "variants": [
        {"id": 1, "title": "Noir / XS", "option1": "Noir", "option2": "XS", "price": 2190, "compare_at_price": 2790, "available": True},
        {"id": 2, "title": "Noir / S", "option1": "Noir", "option2": "S", "price": 2190, "compare_at_price": 2790, "available": True},
        {"id": 3, "title": "Lot de 5", "option1": "Lot", "option2": "M", "price": 10950, "compare_at_price": None, "available": False},
    ],
}


@pytest.fixture
def serveur():
    s = ServeurFactice()
    yield s
    s.arreter()


def test_boutique_shopify(serveur):
    serveur.programmer(200, PAGE_SHOPIFY.encode("utf-8"), HTML)
    serveur.programmer(200, PRODUIT_SHOPIFY)
    page = lire_page(f"{serveur.url}/products/culotte-lea?variant=2", "fr-FR")
    assert page.source == SHOPIFY
    assert (page.nom, page.marque, page.prix, page.prix_barre, page.devise) == (
        "Culotte menstruelle Léa",
        "Mademoiselle Culotte",
        "21,90 €",
        "27,90 €",
        "EUR",
    )
    html, donnees = serveur.requetes
    assert html["chemin"] == "/products/culotte-lea?variant=2"
    assert donnees["chemin"] == "/products/culotte-lea.js"
    # Demandée comme un navigateur, dans la langue du brief.
    assert "Mozilla/5.0" in html["entetes"]["user-agent"] and html["entetes"]["accept-language"].startswith("fr-FR")
    texte = page.texte
    assert "Prix : 21,90 € au lieu de 27,90 € (remise de 21 %)" in texte  # 21,5 % : jamais arrondi vers le haut
    assert "Variante de l'adresse : Noir / S" in texte
    assert "Prix selon les variantes : de 21,90 € à 109,50 €" in texte
    assert "Couleur : Noir, Lot ; Taille : XS, S, M" in texte
    assert "Une culotte douce et absorbante." in texte
    # Texte de la page : bandeau et onglet caché gardés ; menu, listes de choix, code et dessins ignorés.
    assert "Livraison offerte en France métropolitaine" in texte
    assert "Échanges gratuits pendant 30 jours." in texte
    for absent in ("Maillots", "6XL", "color:red", "Shopify.theme", "dessin"):
        assert absent not in texte
    assert texte.count("Au sec jusqu'à 12H") == 1  # ligne répétée (téléphone, ordinateur) gardée une fois


def test_variante_par_defaut_la_premiere_disponible(serveur):
    produit = {**PRODUIT_SHOPIFY, "variants": [dict(PRODUIT_SHOPIFY["variants"][2]), dict(PRODUIT_SHOPIFY["variants"][0])]}
    serveur.programmer(200, PAGE_SHOPIFY.encode("utf-8"), HTML)
    serveur.programmer(200, produit)
    page = lire_page(f"{serveur.url}/products/culotte-lea")
    assert page.prix == "21,90 €" and "Variante de l'adresse" not in page.texte


def test_donnees_shopify_lues_meme_si_la_page_est_refusee(serveur):
    serveur.programmer(403, b"Access denied", HTML)
    serveur.programmer(200, PRODUIT_SHOPIFY)
    page = lire_page(f"{serveur.url}/products/culotte-lea", devise_par_defaut="EUR")
    assert page.source == SHOPIFY and page.prix == "21,90 €"


def test_autre_boutique_avec_donnees_pour_google(serveur):
    donnees = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": "Barre SmartWorkout",
                "brand": {"@type": "Brand", "name": "SmartWorkout"},
                "description": "Supporte jusqu'à 165 kg de résistance.",
                "offers": {"@type": "Offer", "price": "44.90", "priceCurrency": "EUR"},
                "aggregateRating": {"ratingValue": "4.7", "reviewCount": "312"},
                "review": [{"author": {"name": "Julien Martin"}, "reviewBody": "Solide et compacte."}],
            }
        ],
    }
    html = (
        "<html><head><script type='application/ld+json'>" + json.dumps(donnees) + "</script></head>"
        "<body><h1>Barre SmartWorkout</h1><p>Garantie de 60 jours.</p></body></html>"
    )
    serveur.programmer(200, html.encode("utf-8"), HTML)
    page = lire_page(f"{serveur.url}/barre-smartworkout")
    assert page.source == PAGE
    assert (page.nom, page.marque, page.prix) == ("Barre SmartWorkout", "SmartWorkout", "44,90 €")
    assert "Note moyenne : 4.7/5 (312 avis)" in page.texte
    assert "« Solide et compacte. »" in page.texte
    assert "Julien Martin" not in page.texte  # jamais le nom d'une personne réelle
    assert "Garantie de 60 jours." in page.texte
    assert len(serveur.requetes) == 1  # pas une boutique Shopify : pas de demande « .js »


def test_site_qui_bloque(serveur):
    serveur.programmer(403, b"<html>Captcha</html>", HTML)
    with pytest.raises(ErreurLecture) as erreur:
        lire_page(f"{serveur.url}/produit")
    assert erreur.value.code == "bloquee" and erreur.value.google_peut_essayer
    assert "403" in erreur.value.message


def test_page_introuvable(serveur):
    serveur.programmer(404, b"<html>Not found</html>", HTML)
    with pytest.raises(ErreurLecture) as erreur:
        lire_page(f"{serveur.url}/produit")
    assert erreur.value.code == "introuvable" and not erreur.value.google_peut_essayer


def test_page_remplie_par_le_navigateur(serveur):
    serveur.programmer(200, b"<html><body><div id='app'></div><script>charger()</script></body></html>", HTML)
    with pytest.raises(ErreurLecture) as erreur:
        lire_page(f"{serveur.url}/produit")
    assert erreur.value.code == "vide" and erreur.value.google_peut_essayer


def test_adresse_qui_n_est_pas_une_page(serveur):
    serveur.programmer(200, b"%PDF-1.7", {"Content-Type": "application/pdf"})
    with pytest.raises(ErreurLecture) as erreur:
        lire_page(f"{serveur.url}/notice.pdf")
    assert erreur.value.code == "pas_une_page"


def test_adresses():
    assert normaliser_adresse(" mademoiselleculotte.com/products/lea#avis ") == "https://mademoiselleculotte.com/products/lea"
    for invalide in ("", "bonjour", "ftp://site.fr/x", "https://"):
        with pytest.raises(ErreurLecture) as erreur:
            normaliser_adresse(invalide)
        assert erreur.value.code == "adresse"
    assert adresse_shopify("https://b.fr/collections/x/products/barre?variant=4") == "https://b.fr/collections/x/products/barre.js"
    assert adresse_shopify("https://b.fr/products/barre.json") == "https://b.fr/products/barre.js"
    assert adresse_shopify("https://b.fr/pages/contact") is None


def test_prix_lisibles():
    assert formater_prix(Decimal("21.9"), "EUR") == "21,90 €"
    assert formater_prix(Decimal("21.9"), "USD", "en-US") == "$21.90"
    assert formater_prix(Decimal("21.9"), "CHF", "fr-CH") == "21,90 CHF"
    assert formater_prix(None, "EUR") == ""
    assert remise(Decimal("44.90"), Decimal("49.90")) == 10
    assert remise(Decimal("10"), None) == 0


def test_texte_colle():
    page = page_collee("  Culotte Léa  \n\n\n\n 21,90 €  ", "https://x.fr/p")
    assert page.source == TEXTE_COLLE and page.texte == "Culotte Léa\n\n21,90 €" and page.adresse == "https://x.fr/p"
    assert PageLue.depuis_dict(page.en_dict()) == page
    assert PageLue.depuis_dict({}) is None


def test_texte_de_html_sans_balise_non_fermee():
    """Un élément ignoré se ferme toujours au bon endroit, même avec des éléments imbriqués."""
    texte = texte_de_html("<p>Avant</p><nav><nav>menu</nav>encore menu</nav><p>Après</p>")
    assert texte == "Avant\nAprès"
