"""Module Script (V2, §3.1 du cahier des charges) : écrire des scripts de pub UGC, puis les envoyer
dans le module Voix.

Le travail est découpé en étapes enchaînées, comme le conseille le guide officiel de Google pour
les tâches complexes :

1. lecture de la page produit (page_produit.py) : par l'app elle-même (gratuit, exact pour une
   boutique Shopify), sinon par Google (outil « URL context »), sinon texte collé ;
2. analyse de ce qui a été lu → fiche « Ce que l'app a compris » (fiche.py), qui pré-remplit les
   champs vides du brief (brief.py) ;
3. accroches (facultatif), puis écriture du script en répliques (consignes.py, redaction.py) ;
4. relecture : ce qui se compte est vérifié par l'app (controles.py), le reste par le modèle avec
   une liste de règles publicitaires intégrée, datée et sourcée (regles.py) ;
5. affichage, puis envoi dans le module Voix (scripts.py : répliques avec balises, styles et mots
   accentués).

Les exemples donnés au modèle (exemples.py) sont tes meilleurs scripts, plus 5 scripts fournis.
Ici, rien ne dépend de l'interface : tout se teste sans fenêtre.
"""
