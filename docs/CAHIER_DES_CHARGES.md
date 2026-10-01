# UGC Studio : cahier des charges

> Version du document : 3.15, 02/10/2026 (V3 en préparation, §12 ; V2 terminée, version 2.0.0 : lots 1 et 2, module Script, §4 bis ; lot 3, studio des sous-titres, §7.9 ; lot 4, style du texte, §7.10 ; lot 5, mots, §7.11 ; lot 6, animations, §7.12 ; lot 7, frise et préréglages, §7.13 ; suivi au §12.3. V1.1 terminée, version 1.1.0, §12.2)
> Référence unique pour le développement. Toute règle écrite ici fait foi ; en cas de doute pendant le code, on revient à ce document (et on le met à jour si une décision change).

---

## 1. Objectif

Application Windows de bureau pour produire des **publicités e-commerce UGC / influenceur** (TikTok, Snap, Reels, Facebook) :

1. générer la voix off (TTS) ;
2. transcrire une vidéo ou un audio en texte horodaté mot par mot (STT) ;
3. créer, styliser et animer les sous-titres (façon Submagic) ;
4. exporter soit un fichier de sous-titres, soit un overlay vidéo transparent pour Premiere Pro, soit la vidéo finale avec sous-titres incrustés.

**Workflow actuel remplacé :** montage Premiere → voix ElevenLabs → import audio dans Premiere → Submagic pour les sous-titres → export final.
**Workflow cible :** montage Premiere → UGC Studio (voix + sous-titres + export) → Premiere ou publication directe.

**Utilisateur :** débutant en programmation. L'app se lance par une icône sur le bureau, sans terminal ni manipulation de dossiers. Interface en français.

---

## 2. Choix techniques

| Élément | Choix | Pourquoi |
|---|---|---|
| Langage | Python 3.12 | Lisible, grand écosystème audio/vidéo |
| Interface | PySide6 (Qt) | Interface de bureau moderne, thème sombre personnalisable |
| Audio / vidéo | FFmpeg : pour la V1, celui de Qt Multimedia (déjà inclus avec Qt) ; FFmpeg en ligne de commande ajouté pour les exports vidéo (V3), en **version GPL** (décision du 02/10/2026) : elle seule contient les encodeurs x264 et x265 | Extraction audio et lecture des infos source (V1), encodage (V3) : x264 et x265 donnent la meilleure qualité pour un poids de fichier donné, et x265 garde le HDR des vidéos d'iPhone. Passer par Qt évite d'alourdir l'app tant qu'on n'encode pas de vidéo (le `ffmpeg.exe` de la version GPL « essentials » 9.0.2 pèse environ 100 Mo) |
| Rendu des sous-titres | Dessin image par image en Python (Qt QPainter), puis assemblage par FFmpeg | Contrôle total du design ; aperçu identique à l'export |
| Stockage des clés API | Coffre-fort Windows via la bibliothèque `keyring` | Clés chiffrées, jamais dans un fichier ni sur GitHub |
| Données locales | Fichiers JSON dans `%APPDATA%\UGC Studio\` | Styles, préréglages, projets, historique des coûts |
| Appels aux API | Requêtes HTTP directes (module `urllib` de Python), d'après l'API REST officielle ; le SDK officiel `google-genai` sert de référence pour les formats | Aucune bibliothèque en plus, code lisible, testable sans Internet |
| Distribution | `.exe` construit par GitHub Actions (PyInstaller, machine Windows), publié dans les Releases GitHub | Aucun outil à installer côté utilisateur |
| Code source | Dépôt privé GitHub `RoadToMilka/ugc-studio` | Historique, sauvegarde, build automatique |

Le `.exe` n'est pas signé : au premier lancement, Windows affiche « Windows a protégé votre ordinateur » → *Informations complémentaires* → *Exécuter quand même*.

---

## 3. Architecture

### 3.1 Modules

Dans l'ordre de la barre latérale (le module Script en tête depuis la V2 : c'est la première étape d'une pub) :

1. **Script** *(V2, depuis la 1.2.0)* : écriture de scripts UGC avec un modèle de texte (Google seulement en V2 ; OpenAI et Anthropic avec leurs adaptateurs, V4), à partir de la page produit et d'un brief, puis envoi dans le module Voix (§4 bis).
2. **Voix (TTS)** : script, voix, styles, balises, génération, historique des prises.
3. **Transcription (STT)** : import vidéo/audio, extraction du son, transcription mot par mot, correction.
4. **Studio sous-titres** : découpage, style, mot actif, aperçu fidèle sur la vidéo, export (studio depuis la 1.4.0, §7.9).
5. **Réglages** : connexions API, catalogue des modèles et prix, taux de change, suivi des coûts, préférences.

### 3.2 Notion de Projet

Un **Projet** = un dossier qui regroupe tout : script, prises audio, vidéo source (référence), transcription, style de sous-titres, réglages d'export. Rouvrir un projet restaure l'état complet.

- Contenu du dossier : `projet.json` (nom, langue, réglages de voix, répliques du script avec leur style, dictionnaire de prononciation du projet, liste des prises et séries de variantes, transcription avec ses sous-titres réorganisés à la main, dictionnaire de remplacements du projet, réglages des sous-titres, module Script : brief, page produit lue avec son adresse et sa date, fiche comprise, accroches, scripts écrits avec leur relecture et leur coût), `prises\prise-001.wav`, `prise-002.wav`… et `sources\audio.wav` (piste son de la source transcrite, ou de la prise dont on a créé les sous-titres).
- Format du fichier : version 7 depuis la V2, lot 3 (sous-titres rangés en trois parties, « style », « ecran » et « apercu », §7.9 ; un projet plus ancien s'ouvre avec l'apparence de la V1, qui garde exactement son découpage). Version 6 depuis la V2, lot 1 (module Script, §4 bis ; un projet plus ancien s'ouvre sans script). Le lot 2 y ajoute des informations sans changer de format (numéro, note, script retenu, série de variantes et retouche de chaque script ; nombres dits dans les réglages de voix) : un projet de la 1.2.0 s'ouvre tel quel, ses scripts numérotés dans leur ordre d'écriture. Version 5 depuis la V1.1 (sous-titres réorganisés à la main, §7.8 ; un projet plus ancien s'ouvre sans ajustement). Version 4 depuis l'étape 8 (réglages des sous-titres ; un projet plus ancien s'ouvre avec les réglages par défaut). Version 3 depuis l'étape 7 (transcription). Version 2 depuis l'étape 4 (script en répliques) ; un projet de l'étape 3 (un seul script, un seul style) est converti à l'ouverture en une seule réplique.
- Enregistrement **automatique** (moins d'une seconde après chaque modification, et à la fermeture de l'app).
- Menu **Projet** en cliquant sur le nom du projet dans le bandeau : nouveau projet, ouvrir un projet, projets récents (10 retenus), ouvrir le dossier du projet.
- Au démarrage, le dernier projet utilisé est rouvert automatiquement.
- Langue du projet : choisie à la création ; le module Script propose de la changer quand la langue du brief diffère (§4 bis.2).

### 3.3 Lien TTS → sous-titres

Le TTS ne renvoie pas le timing des mots. Chaîne prévue :
1. l'audio généré passe automatiquement dans le STT (horodatage mot par mot) ;
2. le texte transcrit est **aligné sur le script d'origine** (connu exactement), pour corriger les erreurs de transcription ;
3. le résultat arrive dans le Studio sous-titres.

Bouton unique : **« Créer les sous-titres de cette prise »**.

**Mise en œuvre (étape 8)** :
- Où : menu ⋯ d'une prise (module Voix), ou page Sous-titres (liste des prises + « Créer les sous-titres », avec le coût estimé).
- La prise (WAV 24 kHz mono 16 bits, sans perte) est envoyée telle quelle à Google (mode verbatim, horodatage par mot, langue du projet). Quand la transcription réussit, son audio est copié dans `sources\audio.wav` et elle devient **la transcription du projet** : ses mots se corrigent dans le module Transcription (et une nouvelle transcription y refait l'alignement). Remplacer une autre transcription (ex. d'une vidéo) demande confirmation ; en cas d'échec, rien n'est remplacé.
- Alignement (`alignement.py`) : script de la prise sans balises (`texte_brut`), coupé en mots (une ponctuation isolée ne reste jamais seule : « semaines ! », « « Salut »). Les deux suites de mots sont comparées sans majuscules, accents ni ponctuation (comme un outil de comparaison de textes) : mot identique → temps du mot transcrit ; mots différents (« 2 » / « deux », « Glowzy » / « glowzi ») → passage transcrit partagé selon la longueur des mots ; mot du script absent → dans le silence entre ses voisins (au début ou à la fin : le temps de le dire, ≈ 70 ms par lettre ; sans silence : il partage le temps d'un voisin) ; mot transcrit absent du script (rire, hésitation) → ignoré. Les temps restent croissants (20 ms minimum par mot).

### 3.4 Système d'adaptateurs (multi-fournisseurs)

Chaque fournisseur d'IA est géré par un **adaptateur** (un module Python isolé) qui expose :
- `tester_cle()` → la clé fonctionne-t-elle ;
- `lister_modeles()` → modèles accessibles avec cette clé ;
- les fonctions de la tâche (`generer_voix`, `transcrire`, `lister_voix`, …).

Un **tableau de capacités** décrit chaque modèle :

| Capacité | Exemple |
|---|---|
| `tts` | Gemini 3.8 Flash TTS |
| `tts_balises` | balises `<laugh>` supportées |
| `tts_voice_design` | création de voix par description |
| `tts_multi_voix` | 2 voix dans une requête |
| `tts_flux` | audio envoyé par morceaux pendant le calcul (écoute pendant la génération, §5.6) |
| `stt` | Gemini 3.5 Transcribe |
| `stt_mots_horodates` | horodatage par mot (obligatoire pour l'animation) |
| `stt_vocabulaire` | vocabulaire personnalisé |
| `texte` | génération de script (V2) |

L'app **croise** « modèles disponibles avec tes clés » × « capacités requises par la tâche » : un menu déroulant ne montre que les modèles compatibles. Un modèle STT sans horodatage par mot est affiché mais marqué « incompatible avec l'animation ». Les options d'interface non supportées par le modèle choisi sont grisées (ex. palette de balises).

Ajouter un fournisseur = écrire un nouvel adaptateur ; le reste de l'app ne change pas.

Un modèle absent du tableau mais accessible avec une clé est reconnu d'après son nom (`…-tts` → voix, `…transcribe…` → transcription) : il apparaît dans « Modèles et prix » avec des prix à renseigner.

**V1 : adaptateur Google uniquement.** Fournisseurs prévus ensuite : OpenAI, ElevenLabs, Anthropic (texte uniquement : pas de TTS/STT chez Anthropic).

---

## 4. Module Réglages

### 4.1 Connexions API

Écran entièrement dans l'app (aucun passage par Windows ou une ligne de commande) :
- **Ajouter** : choix du fournisseur dans une liste, champ clé (masqué), nom libre (« Google perso »).
- **Tester** : voyant vert / rouge + message clair en cas d'erreur.
- **Remplacer**, **renommer**, **supprimer** (avec confirmation).
- Plusieurs clés par fournisseur possibles ; une clé « par défaut » par fournisseur.
- La clé n'est jamais réaffichée en clair après enregistrement (seulement `AIza…4f2c`).
- Rangement : la clé dans le Gestionnaire d'identification de Windows (entrée « UGC Studio ») ; nom, fournisseur, aperçu, clé par défaut et résultat du dernier test dans `connexions.json`.
- Test de clé = demande de la liste des modèles (gratuit). La clé n'est enregistrée qu'après un test réussi ; sans Internet, bouton « Enregistrer sans tester ».
- Les modèles accessibles lors du dernier test réussi sont retenus : ce sont eux que les menus proposent (croisement avec les capacités, §3.4).

### 4.2 Catalogue des modèles et prix

- Liste des **modèles chargés** (§4.2 bis). Pour chacun : son nom, une courte description et ses capacités, chacun sur une seule ligne (abrégé par « … » quand la fenêtre est étroite, texte complet au survol) ; l'identifiant technique (`gemini-3.8-flash-tts`) ne s'affiche qu'au survol du nom (il faisait doublon). Colonnes : Modèle, **Utilisé dans** (§4.2 ter), Accès, prix d'entrée et de sortie.
- **Prix par défaut = tarifs officiels de Google** ([page des tarifs](https://ai.google.dev/gemini-api/docs/pricing?hl=fr), tarif « Standard » du niveau payant), vérifiés le 30/09/2026, en $ par million de tokens :

| Modèle | Entrée | Sortie | Ordre de grandeur (Google) |
|---|---|---|---|
| `gemini-3.8-flash-tts` | 0,50 $ (texte) | 9,00 $ (audio) | 0,00225 $ pour 10 s d'audio |
| `gemini-3.8-flash-lite-tts` | 0,50 $ | 6,00 $ | |
| `gemini-3.5-transcribe` | 2,00 $ (audio) | 12,00 $ (texte) | ≈ 0,005 $ par minute transcrite |
| `gemini-3.8-flash` (texte : scripts, traduction des styles) | 0,75 $ | 3,75 $ | réflexion comprise en sortie ; ≈ 0,05 $ par script complet |
| `gemini-3.1-pro-preview` (texte : scripts, aperçu) | 2,00 $ | 12,00 $ | jusqu'à 200 000 tokens envoyés (4,00 $ et 18,00 $ au-delà) ; vérifié le 01/10/2026 |
| `gemini-3.1-flash-tts-preview` | 1,00 $ | 20,00 $ | ancienne génération |
| `gemini-2.5-pro-preview-tts` | 1,00 $ | 20,00 $ | ancienne génération |
| `gemini-2.5-flash-preview-tts` | 0,50 $ | 10,00 $ | ancienne génération |

- **Changements de prix annoncés** : Google double les prix des modèles 3.8 **à partir du 01/01/2027** (Flash TTS : 1,00 $ / 18,00 $ ; Flash-Lite TTS : 1,00 $ / 12,00 $ ; Flash : 1,50 $ / 7,50 $). Chaque modèle a donc une liste de tarifs datés ; l'app applique **automatiquement** le tarif en vigueur le jour de l'appel et affiche le prochain changement sous le modèle.
- **Prix modifiables** par modèle (entrée et sortie). Un prix saisi à la main est signalé (« Prix modifié à la main », avec le tarif Google) et s'applique jusqu'au prochain changement de tarif annoncé par Google : l'information la plus récente l'emporte.
- **Ordre de grandeur en euros** sous chaque prix : coût d'une minute de voix (≈ 250 tokens de texte + 60 s × 25 tokens audio), d'une minute transcrite (60 s × 25 tokens audio + ≈ 175 tokens de texte), d'après les chiffres de la page des tarifs, ou d'un script complet du module Script (≈ 19 000 tokens envoyés et 9 000 reçus : lecture de la page, accroches, écriture, relecture).
- Les anciennes générations de voix n'ont ni balises ni Voice Design (doc officielle). Les modèles « Live » (temps réel, ex. `gemini-3.5-transcribe-live`) utilisent une autre API et ne sont jamais proposés.
- Modèles de texte (V2) : deux capacités en plus, « Réponse structurée » et « Lecture de pages web ». Un modèle de texte Gemini 3 ou suivant absent du catalogue (ex. `gemini-3.5-flash`) est reconnu d'après son nom (sauf images, vidéo, musique, vecteurs, agents) ; les plus anciens ne comprennent pas tous les réglages envoyés par l'app (niveau de réflexion) et ne sont pas proposés.
- **Niveau gratuit** de Google (clé sans moyen de paiement) : ces modèles n'y sont pas facturés (limites d'usage plus basses). L'app affiche quand même le coût au tarif payant ; une note le rappelle.
- Bouton « Page des tarifs Google » pour vérifier les prix.

### 4.2 bis Modèles chargés (depuis la 1.0.5)

- L'app garde la liste des **modèles chargés**, c'est-à-dire mis à disposition dans l'app (`modeles.json`). Au départ : les modèles utilisés (Gemini 3.8 Flash TTS, 3.5 Transcribe, 3.8 Flash pour les scripts et les traductions), plus **3.8 Flash-Lite TTS**, pratique et lié à Flash TTS, et **Gemini 3.1 Pro (aperçu)**, à comparer à 3.8 Flash pour les scripts (V2). Un fichier de la 1.1.0 (format 1) reçoit une seule fois Gemini 3.1 Pro (format 2) ; retiré ensuite, il ne revient pas. Les anciennes générations et les modèles inconnus n'y sont plus d'office.
- L'onglet « Modèles et prix » et les listes « Modèle » des modules (Script, Voix, Variantes, Créer une voix, Style, Transcription) ne proposent que les modèles chargés (et, comme avant, accessibles avec la clé et capables de la tâche). Le modèle déjà choisi reste toujours dans sa liste.
- Bouton **« Choisir les modèles… »** : une fenêtre liste les modèles accessibles avec la clé (dernier test réussi) que l'app sait utiliser (voix, transcription, texte des scripts et des traductions ; ni images, ni vidéo, ni « Live »), avec une case à cocher, les capacités et le prix s'il est connu. Sans clé testée, elle l'explique et renvoie vers « Connexions API ».
- Un modèle **utilisé** (§4.2 ter) reste coché et ne peut pas être décoché (l'infobulle dit où il sert) : aucun module ne peut se retrouver sans modèle.
- Sécurités : un projet (ou une voix créée, un style) qui se sert d'un modèle non chargé le recharge automatiquement, sans rien changer dans le projet. Les prix saisis à la main sont gardés, même si le modèle est retiré puis rechargé.

### 4.2 ter Colonne « Utilisé dans »

Où le modèle sert **en ce moment**, mis à jour en direct : **Script** (modèle choisi dans le brief du module Script, projet ouvert), **Voix** (modèle choisi dans le module Voix, projet ouvert ; ou modèle d'une voix créée ou d'un style enregistré), **Transcription** (modèle choisi dans ses options), **Sous-titres** (modèle qui transcrit une prise pour créer ses sous-titres), **Traductions** (Gemini 3.8 Flash : traduction des styles et des descriptions de voix). Modèle chargé mais pas utilisé : « Aucun ». Chaque module déclare lui-même le modèle qu'il utilise (`modeles_charges.py`).
- **Taux de change USD → EUR** modifiable (champ manuel), ou récupéré en un clic auprès de la Banque centrale européenne (taux de référence du jour). Valeur de départ : 0,86, signalée « à vérifier ».
- Prix et taux rangés dans `prix.json` (seuls les prix modifiés y sont écrits ; bouton « Rétablir les prix par défaut »).

### 4.3 Suivi des coûts

- Chaque appel API enregistre : date, projet, modèle, tokens entrée, tokens sortie, coût € (calculé avec les compteurs de tokens renvoyés par l'API). Une page web lue par Google (outil « URL context ») est facturée comme du texte envoyé mais comptée à part (`total_tool_use_tokens`) : l'app l'ajoute aux tokens d'entrée.
- Une tâche en plusieurs appels (module Script : écriture puis relecture, retouche puis relecture, accroches puis scripts d'une série de variantes) note chaque appel dès qu'il est terminé, même si le suivant échoue.
- **Pendant une tâche** : affichage en temps réel des tokens et du coût.
- Historique filtrable par période (aujourd'hui, ce mois-ci, le mois dernier, cette année, tout), projet et modèle, avec totaux (coût, nombre d'appels, tokens). Les 500 appels les plus récents de la période sont listés ; les totaux portent sur toute la période.
- Rangement : un fichier par mois, `couts\AAAA-MM.jsonl`, une ligne par appel (le coût est calculé et figé au moment de l'appel).
- Un appel dont le modèle n'a pas de prix renseigné est compté à part et signalé.
- Limite : l'app compte **ce qu'elle a consommé** ; elle ne connaît pas le solde du compte Google.

### 4.4 Affichage des montants

Format imposé : `0.0000 €` (4 décimales minimum)
- partie entière + 1re et 2e décimales en taille et couleur normales ;
- 3e et 4e décimales en **plus petit** (≈ 70 % de la taille) et **plus sombre** (texte secondaire), pour ne pas attirer l'œil ;
- ex. `0.00` + `71` €. Composant réutilisable `MontantLabel`.
- Un montant non nul qui s'afficherait `0.0000 €` (ex. 0.00004 €) reçoit des décimales supplémentaires jusqu'au premier chiffre utile (6 au maximum) : `0.00` + `004` €. Un coût réel n'apparaît jamais comme gratuit.
- Calculs en nombres décimaux exacts (`Decimal`), arrondi au plus proche (5 vers le haut).

---

## 4 bis. Module Script (V2, depuis la 1.2.0)

Écriture de scripts de pub UGC avec un modèle de texte, puis envoi dans le module Voix. Le module est en tête de la barre latérale (Script, Voix, Transcription, Sous-titres, Réglages). Recherches et choix détaillés : document « UGC Studio - V2 Studio de style et Script » (projet ECOM BUILDR), §10 et annexe A. Le code est dans `ugc_studio/ecriture/` (sans interface, testé seul) et `ugc_studio/ui/pages/script/`.

### 4 bis.1 Lecture de la page produit

« Lire la page » enchaîne trois étapes, pour ne jamais bloquer :
1. **L'app lit la page elle-même**, comme un navigateur (gratuit, toujours à jour).
   - Boutique **Shopify** : données officielles du produit à l'adresse de la page suivie de « .js » (nom, marque, type, étiquettes, description, prix et prix barré en centimes, variantes). Si l'adresse désigne une variante (`?variant=…`), son prix est retenu ; sinon celui de la première variante disponible, comme la page l'affiche. Ces données sont lues même si la page elle-même est refusée.
   - Autre site : données « JSON-LD » de type Product (nom, marque, prix, devise, note moyenne, nombre d'avis, extraits d'avis sans le nom de leur auteur) et balises « og: ».
   - Plus le texte visible de la page : menus, listes de choix, code et dessins ignorés ; texte caché gardé (les onglets « Livraison et retours » le sont souvent jusqu'au clic) ; lignes répétées gardées une fois ; 20 000 caractères au plus.
2. Rien d'utilisable (site qui bloque, page remplie par le navigateur) : **Google lit la page** avec l'outil officiel « URL context » (pages publiques seulement, contenu facturé comme du texte envoyé). Google peut lire une copie ancienne : l'app le signale (« vérifie le prix et la promo »). Si Google refuse l'outil pour le modèle choisi, un autre modèle chargé qui sait lire les pages essaie. Une adresse invalide ou une page qui n'existe pas (404) ne part pas chez Google.
3. Sinon : **« Coller le texte du produit »**, puis « Analyser ce texte ».

Le modèle analyse ce qui a été lu (réflexion basse) et remplit la **fiche « Ce que l'app a compris »** (réponse structurée) : nom, marque, type, prix et prix barré, offre (livraison, garantie, retours), 3 à 5 bénéfices, ce qui le distingue, problèmes résolus, objections probables, preuves, clientèle probable, noms que la voix pourrait mal prononcer.
- Les prix exacts lus par l'app (Shopify) l'emportent sur ceux du modèle. La remise est arrondie vers le bas (21,5 % → 21 %) : elle ne paraît jamais plus forte qu'elle n'est.
- La fiche **pré-remplit les champs vides du brief**, marqués « d'après la page » jusqu'à ce qu'on les modifie ; un champ tapé à la main n'est jamais écrasé ; une nouvelle page remplace ce qui était encore « d'après la page ». Les corrections se font dans le brief (une seule place pour corriger).
- Sans clé API, l'app lit quand même la page et pré-remplit nom, prix et promo ; elle explique comment obtenir l'analyse.
- Noms à prononcer : « Prononciation… » ouvre le dictionnaire avec ces noms ajoutés à celui du projet (▶ avec la voix du projet ; une ligne laissée sans prononciation n'est pas gardée).
- L'app dit toujours ce qui s'est passé : « Lu par l'app (données Shopify), aujourd'hui à 14:32. », « Lu par Google… », « Texte collé… », ou la raison d'un échec.
- Adresse, page lue (texte donné au modèle, source, date, valeurs exactes) et fiche sont enregistrées dans le projet.

### 4 bis.2 Brief

- Aucun champ obligatoire ; rien n'est inventé : sans information, le script reste sans chiffre.
- **Essentiel** : Pays (France, Belgique, Suisse, Luxembourg, Canada, puis États-Unis, Royaume-Uni, Espagne, Italie, Pays-Bas, Allemagne), qui propose la langue et sa variante régionale (Belgique : français ou néerlandais ; Suisse : français ou allemand) et la devise ; Langue ; Réseau (TikTok, Snapchat, Facebook et Instagram, Autre) ; Durée (« Auto » : 25 s sur TikTok, 10 s sur Snapchat, 20 s sur Facebook et Instagram, 20 s pour Autre ; nombre de mots affiché, à la vitesse de parole de la voix du projet, §4 bis.7) ; Tutoiement (Automatique : tutoiement sur TikTok et Snapchat ; ailleurs, vouvoiement pour une clientèle de 35 ans et plus) ; Angle (Laisser le modèle choisir, Témoignage, Problème-solution, Unboxing, Routine, Comparaison, Avant/après raconté, Point de vue « POV », Liste).
- **Sections repliables**, avec un résumé quand elles sont fermées (« 8 remplis, dont 7 d'après la page ») : Produit et offre (nom, type, prix, promo, livraison, garantie et retours, bénéfices, ce qui le distingue, description) ; Clientèle (âge, clientèle, problèmes, objections, preuves) ; Personne qui parle (genre, pré-rempli d'après la voix du projet car il change les accords ; âge ; profil) ; Contraintes (appel à l'action, mentions obligatoires reprises telles quelles, mots interdits, consigne libre).
- **Options**, retenues d'une fois sur l'autre : Balises (décochée au départ), Styles de jeu (cochée), Accentuations (décochée), Modèle, nombre d'accroches (3 à 10, 6 au départ). Sur la même ligne : « Mes meilleurs scripts… » (§4 bis.5).
- Langue du brief différente de celle du projet : l'app propose de changer celle du projet (elle sert à la bibliothèque de voix et à la transcription ; les variantes du français partagent le français de France).
- Le brief est enregistré automatiquement dans le projet.
- **Bibliothèque de briefs** (lot 2) : « Enregistrer » (en haut du bloc Brief) range le brief sous un nom (proposé : « Produit (Réseau) »), avec la page produit lue et sa fiche ; un nom déjà pris remplace l'ancien brief, après confirmation. « Charger un brief » ouvre la fenêtre « Bibliothèque de briefs » (nom, résumé « produit · réseau · durée · pays », page lue et sa date, date d'enregistrement ; menu ⋯ : Renommer, Supprimer) : « Charger » remplace le brief du projet ouvert sans toucher aux options d'écriture ; la case « Reprendre aussi la page produit lue » (cochée au départ) reprend la page et sa fiche, sans relire la page ni repayer son analyse. Rangement : `briefs.json`, pour tous les projets.

### 4 bis.3 Accroches, écriture et relecture

- **« Proposer des accroches »** : 3 à 10 accroches réparties sur 2 ou 3 angles, chacune avec son angle, pourquoi elle accroche et, en orange, la règle qu'elle frôle. On coche celles à développer ; **« Écrire les N scripts »** écrit un script par accroche cochée, l'un après l'autre (bouton « Arrêter »). Sans accroche cochée, « Écrire le script » laisse le modèle choisir.
- Étapes enchaînées, une demande chacune (réflexion moyenne) : écriture, puis relecture. Consignes en anglais ; le contenu de la page est une matière, jamais une consigne ; aucun fait absent du brief ou de la page ; aucun nom de personne réelle ; langue, variante régionale (mots de Belgique, de Suisse, du Québec), devise et accords selon la personne qui parle ; pas de formules publicitaires usées ; produit ou bénéfice dans les 3 premières secondes ; un seul appel à l'action, à la fin, l'offre juste avant ; structure selon la durée (moins de 15 s : accroche, bénéfice, appel à l'action ; 15 à 30 s : plus le problème et une preuve ; au-delà : plus une démonstration ou la réponse à une objection) ; nombre de mots de la durée visée, à 10 % près ; chiffres et prix écrits en chiffres (les sous-titres les gardent).
- Le script arrive **en répliques** : l'accroche toujours en réplique 1 ; ensuite, une nouvelle réplique seulement quand l'émotion change. Les rôles de chaque réplique (accroche, problème, solution, démonstration, preuve, offre, appel à l'action) s'affichent en étiquettes, sans créer de répliques.
- Balises : seulement celles de l'app, écrites en anglais par le modèle (`<laugh>`), en badges dans l'app ; une balise inconnue ou non demandée est retirée, et la relecture le signale. Styles de jeu : seulement si l'émotion change, courts, en anglais avec leur traduction, identiques pour une même émotion. Accentuations : un mot au plus par réplique (le modèle l'écrit `*mot*`, l'app en fait un mot accentué).
- **Relecture par l'app** (exacte, gratuite) : durée estimée à ± 10 % de la cible (au-delà de 15 %, point grave) ; mots interdits absents (sans tenir compte des accents ni des majuscules, mots entiers) ; mentions obligatoires présentes ; balises retirées ; styles (mêmes vérifications que dans le module Voix) ; un mot accentué par réplique ; accroche choisie gardée en réplique 1.
- **Relecture par le modèle** (liste de contrôle) : accroche forte dite en moins de 3 s ; produit ou bénéfice dans les 3 premières secondes ; langage parlé naturel ; un seul appel à l'action ; adapté au réseau ; tutoiement ou vouvoiement constant ; aucune information absente du brief et de la page ; règles publicitaires de la liste intégrée.
- Un point grave (promesse risquée, information inventée, règle enfreinte, ou problème mesuré par l'app) est **corrigé avant l'affichage** ; la carte du script dit ce qui a été corrigé, puis l'app revérifie le script corrigé. Point léger : ⚠ avec l'explication. Info : « La relecture limite les refus, elle ne les empêche pas : la plateforme reste seule juge (ce n'est pas un avis juridique). »
- **Liste intégrée des règles publicitaires** (`ecriture/regles.py`, chacune avec sa source et sa date de vérification, 01/10/2026) : pas de résultat garanti, immédiat ou exagéré (une promesse chiffrée de la marque reste possible telle qu'écrite sur la page) ; pas de superlatif impossible à prouver ; pas de promesse de santé ou de guérison ; pas d'avant/après de poids ou de peau promis ; prix et promo exactement ceux du brief ou de la page ; pas d'urgence ou de rareté inventée ; appel à l'action faisable dans la pub ; jamais le nom d'une personne réelle ; produits intimes sans vocabulaire anatomique ni description crue ; pour Facebook et Instagram, aucune caractéristique personnelle supposée de la personne qui regarde (règle « Personal attributes » de Meta : « Tu as de l'acné ? » refusé). Toutes s'appliquent pour « Autre ». Rappel sur chaque script TikTok : activer l'étiquette « contenu généré par l'IA » (règle TikTok d'avril 2026).

### 4 bis.4 Scripts et envoi dans Voix

- Une **carte par script**, numérotée à sa création (« Script 3 » ; le numéro ne change plus, même après une suppression ; les scripts écrits avec la 1.2.0 sont numérotés dans leur ordre à l'ouverture), le plus récent en haut ; les variantes d'une même série restent ensemble, dans l'ordre A, B, C (« Script 5 (variante B) »). Sur la carte : angle, durée estimée (même formule et même vitesse de parole que le module Voix, balises comprises) pour la durée visée, nombre de mots, réseau, modèle, date, coût réel ; sa place dans sa série (« Série « Accroches seulement » : variante B sur 3 ») et ce dont il vient (« Retouche du script 3 : « Plus court » », « Copie du script 3 ») ; chaque réplique avec ses rôles, son texte dans l'éditeur à badges du module Voix (**modifiable à la main** : l'app revérifie alors ce qui se compte et garde l'avis du modèle) et son style ; la relecture.
- **« Envoyer dans Voix »** : les répliques du script remplacent celles du module Voix, avec styles, balises et mots accentués, après confirmation si le module Voix contient déjà un texte (« Remplacer les 2 répliques actuelles du module Voix par ce script ? ») ; le module Voix s'ouvre, prêt pour « Générer l'audio ». La carte affiche « Envoyé dans Voix ». Un script en français règle aussi les nombres dits dans le module Voix (à la belge pour le français de Belgique, à la suisse pour celui de Suisse, à la française sinon, §5.7).
- Dans le module Voix, un avertissement orange signale une voix dont le genre ne correspond pas à la personne qui parle du brief (accords du texte).
- Sous les répliques : **« Envoyer dans Voix »**, **« Retoucher… »** (§4 bis.4 bis), **« Retenir »** (devient « Retenu », avec la pastille « Retenu » : un script gardé pour ses pubs ; « Retenir » et non « Garder », pour ne pas le confondre avec « Garder comme exemple », alors que dans le module Voix « Garder » retient une variante de sa série) et la **note ★** (0 à 5 ; un clic sur l'étoile de la note actuelle la retire).
- Menu ⋯ : **« Dupliquer »** (une copie à modifier à la main, sans coût, ni envoyée, ni notée, ni retenue) ; **« Garder comme exemple »** (le script rejoint les exemples donnés au modèle, §4 bis.5, et la carte affiche « Exemple » ; dans ce menu depuis le lot 2, pour que la carte tienne dans une fenêtre de 960 px) ; « Envoyer les N accroches en variantes » (série « Accroches seulement », §4 bis.4 bis) ; « Supprimer le script » (après confirmation ; l'exemple gardé reste).

### 4 bis.4 bis Variantes, retouche et comparaison (lot 2)

- **« Variantes… »** (à côté de « Écrire le script ») ouvre la fenêtre « Variantes de script », à trois onglets :
  - **Mêmes réglages** (2 à 6 scripts) : une demande d'accroches, une par variante, chacune sur un angle différent (toutes sur l'angle du brief s'il est imposé), puis un script complet par accroche. Le coût des accroches est réparti entre les scripts.
  - **Réglages par variante** : colonne « Brief », puis une colonne par variante (2 au départ, A et B identiques au brief). Lignes : angle, accroche imposée (facultatif), durée (« Auto »), réseau, personne qui parle, profil, consigne libre, modèle. Valeurs modifiées surlignées en mauve, comme dans le module Voix ; icônes « Dupliquer la variante » et « Supprimer » (2 au moins) en tête de colonne ; « Ajouter une variante » (6 au plus).
  - **Accroches seulement** (2 à 6 scripts) : un script écrit et relu, puis une demande d'autres accroches pour sa réplique 1 (2 de plus que nécessaire : une accroche qui répète celle du script, ou qui contient un mot interdit, est écartée). Chaque variante garde exactement le même corps ; l'app la revérifie (durée, mots interdits, mentions) ; le signal orange d'une accroche devient un point ⚠ de sa relecture, et les points du modèle sur l'ancienne accroche ne sont pas repris. Le coût de la série est réparti entre ses scripts.
  - Coût total estimé avant de lancer ; scripts écrits l'un après l'autre (« Arrêter » : après le script en cours). Les scripts d'une série partagent un identifiant de série et portent leur lettre et leur mode. Message de fin : « Comparer… », ou, pour « Accroches seulement », l'envoi en variantes de voix.
- **« Envoyer les N accroches en variantes »** (menu ⋯ d'un script d'une série « Accroches seulement ») : le script de la variante A part dans le module Voix (même confirmation qu'« Envoyer dans Voix »), puis la fenêtre « Variantes A/B » du module Voix s'ouvre sur « Réglages par variante », une variante par accroche : seule la réplique 1 change, surlignée en mauve. Les scripts de la série sont marqués « Envoyé dans Voix ».
- **« Retoucher… »** : fenêtre avec la consigne, des suggestions en un clic (« Plus court » et « Plus long », qui changent aussi la durée visée d'un quart ; « Plus drôle », « Plus d'énergie », « Plus simple », « Plus naturel »), la durée visée, le tutoiement et le coût estimé (retouche et relecture). Le nouveau script garde le réseau et la langue du script retouché ; il est relu comme un script écrit, la relecture ayant pour consigne de ne jamais défaire la retouche ; l'ancien reste. Coûts : « script : retouche », puis « script : relecture ».
- **« Comparer… »** (au-dessus des scripts, à partir de 2 scripts) : fenêtre « Comparer les scripts », 3 colonnes (la troisième peut rester vide). Chacune choisit son script dans une liste et montre angle, durée estimée, mots, réseau, note, marques, coût, répliques (éditeur à badges en lecture seule), styles et relecture, avec « Envoyer dans Voix » dessous. Au départ : la dernière série de variantes ; ou une retouche (ou une copie) à côté de son original ; sinon les 3 scripts les plus récents.

### 4 bis.5 Exemples (« Mes meilleurs scripts »)

- Chaque demande d'accroches ou de script reçoit jusqu'à 3 exemples proches : même langue (variante exacte d'abord), puis même réseau, puis même angle ; les scripts gardés passent avant les scripts fournis. Les exemples sont adaptés aux options du brief (sans balises, styles ou accentuations non demandés) ; le modèle s'en inspire pour le ton et le rythme, sans les recopier. Sans exemple dans la langue du brief, les autres servent pour la structure et le rythme seulement.
- Au départ, 5 scripts fournis (annexe A du document V2, produits fictifs : sérum Glowzy, hachoir Choppy, brosse Brosso, écouteurs Runbeat, batterie Voltie). Rangement : `scripts_exemples.json` (scripts gardés, scripts fournis retirés).
- Fenêtre **« Mes meilleurs scripts »** (lot 2, bouton « Mes meilleurs scripts… » à côté du modèle) : « Tes scripts » (gardés ou collés, du plus récent au plus ancien, chacun avec le champ « Ta note », ex. « CPA 9 € », lue par le modèle avec l'exemple), puis « Fournis avec l'app » (pastille « Fourni », « Pourquoi il marche ») ; menu ⋯ « Retirer des exemples… » (après confirmation) ; « Ajouter un script qui a marché… » : produit, texte (une réplique par paragraphe, l'accroche en premier ; un texte d'un seul bloc est coupé après sa première ligne, ou sa première phrase), langue, réseau, angle, tutoiement, durée (« Auto » : estimée d'après le texte), note ; « Remettre les exemples fournis » quand des scripts fournis ont été retirés. Après la fenêtre, la marque « Exemple » des scripts suit la bibliothèque.

### 4 bis.6 Modèle de texte et coûts

- Liste « Modèle » : les modèles de texte chargés qui savent donner une réponse structurée (capacités au survol). Par défaut **Gemini 3.8 Flash** ; **Gemini 3.1 Pro (aperçu)** chargé pour comparer sur de vrais produits (« aperçu » : Google peut le modifier ou le retirer).
- Coût **estimé avant chaque demande** (analyse de la page, accroches, script écrit et relu, multiplié par le nombre de scripts à écrire), puis noté appel par appel dans le suivi des coûts : « script : lecture de page », « script : accroches », « script : écriture », « script : relecture », « script : retouche » (lot 2). Variantes : coût total de la série estimé avant de lancer. Ordre de grandeur : 4 à 7 centimes de dollar pour un script complet avec Gemini 3.8 Flash. Température : celle par défaut (recommandation de Google pour Gemini 3).
- API Gemini (Interactions, documentation vérifiée le 01/10/2026) : réponse structurée par `response_format: {"type": "text", "mime_type": "application/json", "schema": …}` ; lecture d'une page par `tools: [{"type": "url_context"}]`, statut de chaque page (`success`, `error`, `paywall`, `unsafe`) dans les étapes `url_context_result` ; contenu lu compté dans `usage.total_tool_use_tokens`, ajouté aux tokens d'entrée.

### 4 bis.7 Vitesse de parole (lot 2)

- Au départ, 2,7 mots par seconde (environ 160 mots par minute). Chaque prise générée donne une mesure : mots dits (les balises ne comptent pas) ÷ temps de parole, c'est-à-dire la durée de la prise moins le temps estimé de ses balises (mêmes valeurs que l'estimation : pause courte 0,5 s, pause longue 1,2 s, autres 0,6 s). Les petits silences du début et de la fin restent comptés : la durée estimée d'un script correspond ainsi à la durée réelle de ses prises. (Le document V2 prévoyait aussi le temps de parole exact donné par les sous-titres d'une prise : écarté, car il exclut ces silences et l'estimation deviendrait trop courte.)
- Une mesure par prise ; mesure ignorée si la prise est trop courte (moins de 4 mots ou d'1 s) ou incohérente (moins d'1 ou plus de 6 mots par seconde) ; 50 mesures gardées par voix.
- Vitesse d'une voix : total des mots ÷ total des temps de ses 20 dernières prises ; sans prise de cette voix, de toutes les prises (« vitesse mesurée sur 12 prises d'autres voix ») ; sans aucune prise, 2,7.
- Les prises d'un projet qui s'ouvre et qui ne sont pas encore mesurées (ex. créées avec la 1.2.0) le sont à l'ouverture.
- Module Script : vitesse de la voix du projet. Sous la durée : « 25 s ≈ 65 mots (durée conseillée pour TikTok) · vitesse de Kore mesurée sur 9 prises : 2,6 mots/s ». Elle donne le nombre de mots demandé au modèle, la durée estimée des cartes et leur contrôle de durée (revérifié quand la vitesse change, par exemple après une nouvelle prise ou un changement de voix).
- Module Voix : durée et coût estimés avec la vitesse de la voix choisie, variantes A/B comprises ; au survol de l'estimation : « Durée estimée avec la vitesse de Kore mesurée sur 9 prises : 2,6 mots/s ».
- Rangement : `vitesses.json`, toutes voix et tous projets confondus (le document V2 parlait des préférences ; un fichier à part les garde légères).

---

## 5. Module Voix (TTS)

### 5.1 Modèles V1

- `gemini-3.8-flash-tts` (par défaut : qualité et jeu d'acteur maximum)
- `gemini-3.8-flash-lite-tts` (rapide, moins cher)

### 5.2 Éditeur de script

- Grand champ de texte.
- **Insertion de balises à la position du curseur** : on clique dans le texte, puis sur une balise de la palette.
- Les balises s'affichent comme des **badges colorés** (pastille arrondie) avec leur **nom français** (« rire ») ; le texte envoyé à l'API contient la vraie balise, en anglais (`<laugh>`). Le nom anglais s'affiche au survol d'un badge ou d'une balise de la palette (« Envoyé à Google : <laugh> »).
- Le nom du badge est **centré à l'œil** : le milieu des minuscules tombe au milieu de la pastille (centré par Qt, il paraissait 1 à 2 px trop bas). Même règle pour les autres pastilles (« Retenue », « Par défaut »).
- Un badge se supprime comme un caractère (retour arrière) et se déplace par couper/coller.
- **Couleur par famille** :

| Famille | Balises : nom affiché (`nom envoyé à Google`) |
|---|---|
| Pauses | pause courte (`short pause`), pause longue (`long pause`) |
| Rires | rire (`laugh`), éclats de rire (`laughter`), gloussement (`giggle`), petit rire (`chuckle`), rit doucement (`chuckles`), ricanement (`snicker`), rire strident (`cackle`) |
| Souffle | respiration (`breath`), respiration lourde (`heavy breath`), souffle (`exhales`), soupir (`sigh`), soupire (`sighs`), ouf (`phew`), pff (`pff`), halètement (`pant`), bâillement (`yawn`) |
| Réactions | souffle coupé (`gasp`), cri de joie (`cheer`), cri (`shout`), hurlement (`scream`), cri perçant (`shriek`), argh (`argh`), plainte (`groan`), grognement (`grunt`), tss (`tsk`), reniflement (`snort`) |
| Voix | chuchote (`whispers`), en chuchotant (`whispering`), raclement de gorge (`throat-clearing`), toux (`cough`), éternuement (`sneeze`) |
| Émotions fortes | pleurs (`cry`), sanglot (`sob`), geignement (`whimper`), gémissement (`moan`), grondement (`growl`), grr (`grr`), sifflement (`hiss`) |

(Liste issue de la doc officielle Gemini TTS. Les balises sont **envoyées en anglais**, même pour un texte français : la documentation de Google le demande, « If your transcript is in a non-English language, continue to use English inline tags for best results ». Elles sont enregistrées en anglais dans les projets, et affichées en français dans l'app : palette, badges, menu « Balise » des variantes, bibliothèque de styles, champ « Balises souvent utilisées », messages. Noms français validés le 30/09/2026, rangés dans `balises.py`.)

- **Dictionnaire de prononciation (mots de marque)** : l'API n'a pas de paramètre dédié aux noms de marque. L'app garde donc une liste « mot écrit → façon de le prononcer » (ex. « Glowzy » → « Glo-zi »). Au moment de générer, **seul le texte envoyé au TTS** est remplacé ; le script affiché et les sous-titres gardent l'orthographe correcte (grâce à l'alignement sur le script, §3.3). Bouton ▶ pour tester la prononciation d'un mot seul (coût minime, noté « essai de prononciation » ; l'audio est gardé en cache). Dictionnaires globaux (`prononciations.json`) ou par projet ; pour un même mot, celui du projet l'emporte.
  - Remplacement : mots entiers, sans tenir compte des majuscules ; le mot le plus long d'abord (« Glowzy Pro » avant « Glowzy ») ; les balises ne sont jamais modifiées.
  - Fenêtre « Prononciation » (bouton sous le script) : deux onglets, « Ce projet » et « Tous les projets ».
- **Aide à l'accentuation** : bouton « Accentuer » qui met le mot sélectionné en MAJUSCULES (le modèle appuie sur les mots en capitales). Ces majuscules n'impactent pas les sous-titres (le texte des sous-titres est géré séparément, cf. §7.2).
- Compteur de caractères et **estimation du coût** avant génération : tokens d'entrée ≈ caractères ÷ 4 ; durée d'après le nombre de mots (≈ 160 mots/min) et les pauses ; tokens audio ≈ durée × tokens par seconde. Ce dernier chiffre (25 au départ, d'après la page des tarifs de Google) est **ajusté automatiquement** après chaque génération avec les vrais nombres renvoyés par Google.
- Affichage d'un mot accentué : en MAJUSCULES et en mauve dans l'éditeur ; l'écriture d'origine est conservée pour les sous-titres.
- Copier/coller : entre éditeurs de l'app, badges et accents sont conservés ; un texte collé depuis un autre logiciel voit ses balises transformées en badges, qu'elles soient écrites en anglais (`<laugh>`) ou en français (`<rire>`, avec ou sans accents ni majuscules). Vers un autre logiciel, les balises sont copiées avec leur vrai nom anglais.

### 5.3 Découpage en répliques

- Le script peut être découpé en **répliques** (blocs). Chaque réplique a son propre champ **style** (optionnel), utile quand l'émotion change en cours de pub (ex. hook énergique → témoignage calme).
- Le style de réplique est envoyé dans `speech_metadata.style`.
- Toutes les répliques partent **dans la même requête** (une entrée de texte par réplique, chacune avec son style) : une seule prise. Si le total dépasse les limites du modèle (§5.6 bis), les répliques sont réparties sur plusieurs requêtes, puis les audios sont recollés.
- Interface : les répliques s'affichent l'une sous l'autre (« Réplique 1 », « Réplique 2 »…), chacune avec son champ style et son éditeur à badges, qui grandit avec le texte. Bouton « Ajouter une réplique » ; menu ⋯ de chaque réplique : **Découper ici** (la fin de la réplique, après le curseur, devient une nouvelle réplique avec le même style), Monter, Descendre, Supprimer. La palette de balises et « Accentuer » agissent sur la dernière réplique utilisée.
- Chaque prise retient le texte et le style envoyés pour chaque réplique ; la liste des prises indique « N répliques » quand il y en a plusieurs.

### 5.4 Choix de la voix

- **Voix de base** (30 voix Google) avec leur caractère (Puck · Upbeat, Kore · Firm, Leda · Youthful…).
- **Bibliothèque étendue** interrogée via l'API (`voices.list`) avec **filtres** : langue, accent, genre, hauteur (grave/moyenne/aiguë), persona, contexte d'usage, recherche texte.
  - Requête : `GET /v1beta/voices?page_size=1000&type=prebuilt` (pages suivantes avec `page_token`). La bibliothèque (plus de 2 000 voix) est gardée une semaine dans son propre fichier, `bibliotheque_voix.json` ; bouton « Actualiser ». Favoris, noms, traductions et voix créées sont dans `voix.json`, un petit fichier (jusqu'à la 1.0.3, la bibliothèque y était aussi, et chaque ★ réécrivait tout ; elle est déplacée automatiquement à la première ouverture).
  - Les filtres agissent dans l'app ; au départ, la langue du projet est choisie. Le nombre exact de voix trouvées est affiché (« 81 voix (sur 2 089) »). **20 voix affichées**, puis « Afficher 20 voix de plus » (avec le nombre restant), autant de fois que voulu ; changer un filtre revient aux 20 premières. La recherche attend une courte pause dans la frappe (0,3 s).
  - Rapidité (1.0.4) : ★ ne change que l'étoile de sa ligne ; chaque changement ne prévient que les écrans concernés (la réponse de « Mes voix » ne reconstruit pas la liste des voix de Google) ; les voix sont rangées par identifiant (une recherche parmi 2 000 voix sans les parcourir).
  - Fenêtre « Bibliothèque de voix » (bouton 📚 à côté de la liste des voix) : onglets « Voix Google » et « Mes voix » ; chaque voix s'écoute (▶) et se choisit en un clic.
- Bouton **▶ écouter** un extrait pour chaque voix. Voix créées et voix de la bibliothèque étendue : l'extrait fourni par Google (`GET /v1beta/voices/{id}`, gratuit) s'il existe. 30 voix de base (elles parlent toutes les langues) : une phrase d'exemple générée dans la langue du projet, coût noté « essai de voix ». Chaque extrait est gardé en cache.
- **Favoris** de voix (★) : en tête de la liste des voix de l'atelier (puis les voix créées, puis les 30 voix de base) et filtre « Favoris seulement » dans la bibliothèque.
- Choisir une voix créée choisit aussi le modèle avec lequel elle a été créée.
- *(V4)* Voice Replication (clonage à partir de 30 s, **uniquement avec l'accord de la personne**).

### 5.4 bis Voice Design : créer ses voix (V1)

Création de voix personnalisées **dans l'app** (API `POST /v1beta/voices`, `type: "prompted"`), sans passer par Google AI Studio.

- Champs : nom, langue, genre, modèle (Flash TTS ou Flash-Lite TTS), **description**.
- **Assistant de description structurée** : champs guidés (âge, genre, timbre, texture de voix, accent régional, persona / rôle) assemblés automatiquement en 1 ou 2 phrases, modifiables ensuite en texte libre. Ex. : « Jeune femme d'environ 25 ans, française, voix légèrement voilée, spontanée et complice, comme si elle parlait à une amie face caméra. »
- Google renvoie un **extrait audio** → écoute immédiate → garder ou ajuster la description et recommencer.
- Gestion : liste, réécoute (`voices.get` renvoie l'extrait), renommage, suppression, **date d'expiration** affichée (conservation 1 an), compteur **x / 200 voix**.
- Les voix créées dans Google AI Studio (même projet) apparaissent aussi dans l'app.
- Coût éventuel de création : à vérifier au moment du code ; affiché s'il existe.
- Mise en œuvre (étape 5) :
  - Création : `POST /v1beta/voices` avec `store: true`, `voice.type: "prompted"`, `display_name`, `language_code`, `gender`, `model`, `prompted.input` (la description, en anglais). La réponse contient l'identifiant `voice_…`, `expire_time`, un extrait (`sample_audio`, joué aussitôt) et `usage` : les tokens sont comptés au prix du modèle, opération « création de voix ».
  - Chaque création donne une version un peu différente : la fenêtre « Créer une voix » liste les versions créées (▶, Supprimer, « Utiliser cette voix »), et « Créer une autre version » en crée une nouvelle avec la même description.
  - La description suit les mêmes règles que les styles : envoyée en anglais, traduction française affichée, bouton « Traduire en anglais », vérifications en direct (dont description en français).
  - L'assistant de description propose genre, âge, timbre, texture, accent régional et rôle ; il assemble 1 à 2 phrases en anglais (ex. « A young woman in her mid-20s with a warm, slightly husky voice and a Parisian French accent. Spontaneous and playful, like a creator talking to a friend on camera. ») et reporte le genre dans le formulaire.
  - Renommer : l'API ne permet pas de renommer une voix ; le nouveau nom est gardé dans l'app (`voix.json`).
  - Liste « Mes voix » : `GET /v1beta/voices?type=prompted&type=replicated`, redemandée au plus toutes les heures (et sur « Actualiser »).

**Conseils de Google** (fenêtre « Conseils » de « Créer une voix », en français ; jusqu'à la 1.0.2, une colonne à côté du formulaire) :
- Mettre ici les **traits permanents** : âge, genre, timbre, texture vocale, accent régional.
- Description **courte et précise : 1 à 2 phrases**.
- Éviter les paragraphes longs et les descriptions **contradictoires**.
- L'émotion et le jeu se règlent ensuite avec des styles courts, pas dans la description.

**Vérifications en direct** : avertissement au-delà de 2 phrases / ~40 mots.

### 5.5 Bibliothèque de styles personnalisés

Un **style** enregistré contient :
- nom, catégorie (UGC témoignage, unboxing, placement influenceur, hook, pub classique… ; catégories libres, créables par l'utilisateur) ;
- fournisseur + modèle ;
- voix ;
- consigne de style (courte : voir conseils ci-dessous) ;
- balises par défaut éventuelles ;
- langue.

Actions : créer, modifier, dupliquer, supprimer, **appliquer en un clic**. Quelques exemples fournis au départ (modifiables/supprimables).
- Rangement : `styles.json` dans le dossier de données de l'app.
- Accès : bouton 📚 à côté du champ style de chaque réplique. « Appliquer » met la consigne (et sa traduction) sur la réplique, et choisit la voix et le modèle du style. « Enregistrer le style actuel » crée un style à partir de celui de la réplique.
- Fenêtre de création / modification : nom, catégorie (liste modifiable), modèle, voix, langue, style (avec assistant et traduction), balises souvent utilisées (noms de la palette, vérifiés) ; les conseils de Google sont derrière le bouton « Conseils » de la fenêtre.

Les styles sont liés à un fournisseur (chaque fournisseur a sa propre syntaxe).

**Assistant de style structuré** : style = *émotion / attitude* + *rythme / prosodie* (optionnel), ex. « chaleureux et enthousiaste, débit rapide », « chuchoté, complice ». Champs guidés assemblés en une consigne courte, modifiable en texte libre. Il s'ouvre avec le bouton **crayon** à côté du champ style (comme l'assistant de description de Voice Design) : une baguette magique faisait penser à une génération automatique.

**Conseils de Google pour les styles** (fenêtres « Conseils » du module Voix et de la fenêtre d'un style, en français ; jusqu'à la 1.0.2, un bloc repliable sous le script et une colonne à côté du formulaire) :
- Style **court** (quelques mots) : émotion, attitude, rythme, volume, hauteur/inflexion.
- **Tester d'abord sans style** : la plupart des générations n'en ont pas besoin.
- Pour une ambiance constante, **réutiliser exactement la même consigne** d'une réplique à l'autre.
- Si l'émotion change en cours de texte → **découper en répliques** avec un style chacune, plutôt qu'une longue consigne.
- **Pas de traits permanents** dans le style (âge, genre, nom, accent) → ils vont dans la voix (Voice Design ou choix de voix).
- **Pas de méta-consignes** du type « garde la même voix », « ne change pas de timbre » : elles augmentent la dérive.
- Les événements ponctuels (rire, soupir, pause) se mettent en **balises dans le texte**, pas dans le style.

**Vérifications en direct** dans le champ style (avertissements non bloquants) :
- plus de ~10 mots ;
- mots évoquant un trait permanent (« ans », « homme », « femme », « accent », « voix grave »…) ;
- méta-consignes (« même voix », « garde le timbre »…) ;
- sons ponctuels écrits dans le style (« rire », « soupir »…) → proposition de les convertir en balises.

**Langue des consignes : anglais envoyé à Google, traduction française affichée.**
Les styles et les descriptions de voix (§5.4 bis) sont toujours **envoyés en anglais**, comme dans les exemples Google.
- L'assistant structuré assemble directement la consigne en anglais ; la **traduction française** s'affiche juste en dessous, en lecture seule, pour comprendre ce qui est envoyé.
- En texte libre, on peut écrire en anglais, ou écrire en français puis cliquer **« Traduire en anglais »** : l'app traduit avec un modèle de texte Gemini (même clé API, coût minime affiché) et montre les deux versions avant d'enregistrer.
  - Modèle : `gemini-3.8-flash`, avec le niveau de réflexion le plus bas qu'il accepte (`thinking_level: "low"` ; « minimal » n'existe pas pour ce modèle), et une consigne système qui demande une traduction fidèle et courte. Coût noté « traduction » dans le suivi (ordre de grandeur : 0,0002 € par style).
  - Un style modifié à la main après traduction perd sa traduction affichée (elle ne lui correspond plus).
  - Vérification en direct supplémentaire : un style qui semble écrit en français (accents, mots français courants) est signalé, avec l'invitation à le traduire.
- Les conseils de Google s'affichent **en français** (fenêtres « Conseils ») ; seul l'exemple de style reste en anglais, puisque c'est ce qui est envoyé.
- Le texte du script (ce que la voix prononce) reste bien sûr dans la langue du projet.

### 5.6 Génération et prises

- Bouton **« Générer l'audio »** → lecture immédiate dans l'app. (Il s'appelait « Générer la voix » jusqu'à la 1.0.0 : on le confondait avec « Créer une voix ».)
- Chaque génération = une **prise** conservée dans le projet (horodatée, avec voix/style/coût utilisés).
- Comparer, renommer, noter (★), supprimer les prises.
- La durée et le coût estimés avant de générer suivent la vitesse de parole de la voix choisie, mesurée sur les prises (§4 bis.7).
- Export audio : **WAV 24 kHz mono** (sortie native) ; option MP3 (encodeur LAME, 192 kb/s).
- Appel technique (Gemini 3.8 TTS) : API **Interactions** (`POST /v1beta/interactions`) : texte dans `input` (avec l'annotation `speech_metadata.style` quand un style est donné), voix dans `generation_config.speech_config`. Réponse : WAV 24 kHz mono en base64, et nombres de tokens (`usage`) pour le coût.
- En cas de surcharge passagère de Google (erreur 5xx), un nouvel essai est fait automatiquement après 3 s.
- **Variantes** (tests A/B de pubs) : générer plusieurs versions d'un même script en un seul lancement.
  - **Mode « mêmes réglages »** : N générations identiques ; le modèle varie naturellement l'interprétation → on garde la meilleure prise.
  - **Mode « réglages par variante »** : tableau où chaque colonne est une variante. Tout part des réglages de base ; pour chaque variante on modifie seulement ce qu'on veut comparer (voix, style, modèle, consigne d'une réplique, balises). Les valeurs modifiées sont surlignées en mauve pour voir d'un coup d'œil ce qui change.
  - Bouton « dupliquer la variante » pour créer une variante voisine avec un petit changement.
  - Coût total estimé affiché avant le lancement.
  - Écoute comparative : lecture enchaînée ou bascule instantanée A/B au même moment du texte ; note ★ et choix de la variante retenue.
  - Chaque variante devient une prise normale (§5.6).
- **Écoute pendant la génération** (streaming) : option pour entendre le début avant la fin du calcul.
- Mise en œuvre (étape 6) :
  - Bouton **« Variantes… »** à côté de « Générer l'audio ». Fenêtre à deux onglets :
    - « Mêmes réglages » : de 2 à 6 variantes (lettres A à F) ;
    - « Réglages par variante » : colonne « Réglages de base » (ceux de l'atelier), puis une colonne par variante (2 au départ, A et B, identiques à la base). Lignes : modèle, voix, puis pour chaque réplique son style et son texte (sous chaque texte : menu « Balise » par famille et « Accentuer »). Choisir une voix créée choisit aussi son modèle, comme dans l'atelier. Icônes « Dupliquer la variante » et « Supprimer » (au moins 2 variantes) en tête de colonne, « Ajouter » à droite.
    - En bas : coût total estimé (prix de chaque modèle, dictionnaire de prononciation compris) et « Générer les N variantes ».
  - Génération : les variantes partent **l'une après l'autre** (pour rester sous les limites de débit de Google). Chacune devient une prise « Prise N (variante B) », marquée de sa série (`serie`, `variante` dans `projet.json`). Bouton « Arrêter » pendant la série : elle s'arrête après la variante en cours. Si une variante échoue, la série s'arrête ; les variantes déjà prêtes sont gardées.
  - **Écoute comparative** : fenêtre « Comparer les variantes » ouverte à la fin de la série (au moins 2 variantes prêtes), et depuis le menu ⋯ d'une prise de la série.
    - « Lecture enchaînée » : A, puis B, puis C… (0,6 s de silence entre deux).
    - Bascule : clic sur une lettre, ou touches A à F (ou 1 à 6). La variante choisie reprend **au même moment du texte** : même proportion de sa durée, puisque les variantes n'ont pas exactement la même durée. Chaque variante a son propre lecteur, chargé à l'ouverture : la bascule est immédiate. Espace : lecture ou pause.
    - Chaque ligne montre ce qui distingue la variante (réglages qui changent dans la série ; « Mêmes réglages » sinon), sa durée, sa note ★ et « Garder » : une seule variante retenue par série, signalée par la pastille « Retenue » dans la liste des prises.
  - **Écoute pendant la génération** : case « Écouter pendant la génération » sous le bouton (cochée au départ ; le choix est retenu). Pour les modèles qui envoient leur audio en flux (capacité « Écoute en direct » : Gemini 3.8 Flash TTS et Flash-Lite TTS), la requête part avec `stream: true`.
    - Google envoie des événements (server-sent events) : des « step.delta » portent chacun un morceau d'audio (PCM brut `audio/l16`, 24 kHz, mono, 16 bits little-endian, en base64), puis « interaction.completed » donne le statut et les tokens (coût) ; le flux se termine par « [DONE] ».
    - La lecture démarre dès 0,3 s d'avance. L'audio est converti au format de la carte son si elle n'accepte pas celui du TTS (fréquence, stéréo, nombres à virgule).
    - Sans sortie audio utilisable : génération d'un bloc et lecture de la prise à la fin, comme avant. Une prise lancée à la main arrête l'écoute en cours.
    - Les variantes A/B ne sont pas écoutées pendant leur génération : on les compare ensuite.

### 5.6 bis Limites du modèle (doc officielle)

- Entrée max : **8 192 tokens** de texte ; sortie max : **16 384 tokens** audio. Un script trop long est découpé automatiquement (aux fins de phrases, avec 20 % de marge sous ces limites), les morceaux sont générés puis recollés avec 0,25 s de silence.
- Multi-voix dans une seule requête : 2 voix de base maximum ; avec des voix personnalisées, une requête par réplique puis assemblage (V4).
- **Mode de traitement** : Standard uniquement. Le mode *Batch* (gros lots de variantes, résultats différés) pourra être ajouté plus tard si besoin ; *Flex* et *Priority* ne sont pas retenus.
- Formats de sortie possibles : WAV (défaut), PCM brut, mu-law, A-law, fréquence réglable. L'app garde WAV 24 kHz.
- Pas d'horodatage des mots en sortie : d'où la chaîne TTS → STT (§3.3).
- Bouton **« Créer les sous-titres de cette prise »** (cf. §3.3).

### 5.7 Langue

- Français par défaut ; sélecteur de langue par projet : anglais (US), anglais (UK), espagnol (Espagne), italien, néerlandais (Belgique), néerlandais (Pays-Bas), allemand.
- La langue filtre la bibliothèque de voix.
- La langue n'est pas envoyée au TTS en V1 : le modèle la reconnaît dans le texte. Elle sert à la phrase d'extrait des voix et, plus tard, à la transcription.
- **Nombres dits** (V2, lot 2 ; projets en français, ligne « Nombres dits » du bloc « Voix et modèle ») : à la française, à la belge (septante, nonante) ou à la suisse (septante, huitante, nonante). Comme le dictionnaire de prononciation, seul le texte envoyé à la voix change (appliqué après lui) : le script et les sous-titres gardent les chiffres. Seuls les nombres qui se lisent autrement qu'en France sont écrits en lettres (70 à 79 et 90 à 99, plus 80 à 89 à la suisse, y compris dans 170, 1 290 ou 1990) ; un prix est écrit en entier, dans l'ordre où on le dit (« 29,90 € » → « vingt-neuf euros nonante » ; CHF → francs) ; « 90 % » → « nonante pour cent » ; un nombre collé à des lettres (code promo « GLOW20 »), une heure (« 14:30 ») ou un numéro qui commence par 0 ne change pas ; les balises restent intactes. « Envoyer dans Voix » d'un script en français choisit la variante d'après sa langue. « À la belge » convient aussi à Genève, Neuchâtel et au Jura (« quatre-vingts ») ; « huitante » se dit dans les cantons de Vaud, du Valais et de Fribourg. Enregistré dans le projet (`voix.nombres`) ; l'estimation compte le texte réellement envoyé.

---

## 6. Module Transcription (STT)

### 6.1 Modèle V1

`gemini-3.5-transcribe` avec **horodatage mot par mot activé** (limite : 30 min par requête, largement suffisant pour des pubs).

### 6.2 Entrée

- Glisser-déposer ou bouton : vidéo (MP4, MOV, MKV…) ou audio (WAV, MP3, M4A…).
- Extraction automatique de la piste son (décodage par FFmpeg, à travers Qt Multimedia).
- Lecture des infos de la source (résolution, fps exacts, débit, codec, couleurs/HDR, durée), réutilisées pour l'export.

### 6.3 Options

**Incompatibilités officielles de l'API (doc Google, sept. 2026), qui dictent la conception :**
- l'horodatage par mot (`timestamp_granularities: ["word"]`) ne fonctionne qu'en mode **verbatim** ;
- il est **incompatible avec le vocabulaire personnalisé** (`custom_vocabulary`) ;
- le mode **smart** est incompatible avec l'horodatage et avec la séparation des voix ;
- la séparation des voix (`diarization_mode: "speaker"`) est incompatible avec le vocabulaire personnalisé.

Comme les sous-titres animés exigent l'horodatage par mot, l'app propose :

- **Langue** : détection auto ou langue forcée (`language_codes`, recommandé pour les vidéos courtes).
- **Séparation des voix** (jusqu'à 8 personnes, fiable jusqu'à 2 ; au-delà expérimental) : chaque mot reçoit un locuteur (`spk_1`, `spk_2`…). Utile pour une pub à deux personnes : style de sous-titre différent par personne (V2).
- **Dictionnaire de remplacements** (local, gratuit) : « sérum anti rides » → « Sérum Anti-Rides® », appliqué automatiquement après chaque transcription. Dictionnaires globaux ou par projet.
- **Correction manuelle** de n'importe quel mot dans l'éditeur (§6.4) : solution principale pour les erreurs ponctuelles.
- Pas de vocabulaire personnalisé côté API en V1 (incompatible avec l'horodatage par mot) : non retenu, le dictionnaire + la correction manuelle suffisent.
- **Masquer les hésitations dans les sous-titres** (remplace le mode smart) : l'app retire elle-même « euh », « hum »… de l'affichage en conservant les temps des autres mots. Liste de mots modifiable par langue. L'audio n'est pas modifié.
- Le **mode smart** reste disponible uniquement pour une transcription texte sans timing (copier un script depuis une vidéo concurrente, par ex.).

### 6.3 bis Limites et formats

- Durée max : 1 h en texte seul, **30 min** avec horodatage ou séparation des voix. Au-delà, l'app découpe l'audio en morceaux et recolle les temps.
- Formats acceptés par l'API : WAV, MP3, AIFF, AAC, OGG, FLAC, M4A, Opus, WebM… La vidéo n'est pas acceptée : l'app extrait toujours l'audio (WAV 16 kHz mono 16 bits, sans perte pour la parole) avant l'envoi. Une prise TTS (WAV 24 kHz mono) est envoyée telle quelle (§3.3).
- Envoi via l'API Files (fichier téléversé puis référencé).

### 6.4 Éditeur de transcription

- Texte affiché mot par mot, synchronisé avec la lecture (le mot en cours est surligné).
- Clic sur un mot → la lecture saute à ce moment.
- Corriger l'orthographe d'un mot sans perdre son timing ; fusionner / couper des mots ; ajuster finement début/fin d'un mot.
- Le horodatage par mot dégrade légèrement la précision : l'édition manuelle est prévue pour ça.

### 6.5 Mise en œuvre (étape 7)

- **Import** : glisser-déposer sur la page (ou « Choisir un fichier… »). Vidéos MP4, MOV, MKV, M4V, WebM, AVI ; audios WAV, MP3, M4A, AAC, FLAC, OGG, Opus, AIFF, WMA.
  - Piste son : un WAV 16 bits de moins de 5 min (ex. une prise) est préparé en Python ; tout le reste est décodé par Qt Multimedia (`QAudioDecoder`, qui s'appuie sur FFmpeg), directement en 16 kHz mono. Résultat rangé dans le projet : `sources\audio.wav`. La source d'origine n'est pas copiée (son chemin est gardé).
  - Infos de la source lues par Qt Multimedia : durée, résolution, images par seconde, codecs, débits, HDR (Qt 6.8 et plus). Gardées dans `projet.json`.
  - Une nouvelle source remplace la transcription actuelle, après confirmation.
- **Envoi** : API Files de Google (téléversement « resumable » : `POST /upload/v1beta/files`, puis envoi des octets à l'adresse de l'en-tête `x-goog-upload-url`). Le fichier déposé est supprimé après la transcription (sinon Google l'efface au bout de 48 h).
- **Requête** : `POST /v1beta/interactions`, entrée `{"type": "audio", "uri": …, "mime_type": "audio/wav"}`, `generation_config.transcription_config` : `language_codes` (vide = détection automatique) et `mode` : `{"type": "verbatim", "timestamp_granularities": ["word"]}` (+ `"diarization_mode": "speaker"` si les voix sont séparées), ou `"smart"` pour le texte seul.
- **Réponse** : mots dans les annotations `word_info` du texte (`text`, `start_offset` / `end_offset` au format « 1.250s », `speaker`). Coût d'après `usage`, noté « transcription ». Estimation avant l'envoi : ≈ 25 tokens par seconde d'audio en entrée, ≈ 175 tokens de texte par minute en sortie.
- **Longues sources** : au-delà de 30 min (1 h en texte seul), coupe toutes les 25 min, chaque coupure placée dans le passage le plus silencieux à ± 10 s ; temps recalés et recollés. Les numéros de personne peuvent changer d'un morceau à l'autre.
- **Options** : modèle (ceux qui donnent le moment de chaque mot), langue (celle du projet au départ, ou « Détection automatique »), « Séparer les voix », « Texte seul, nettoyé » (mode smart : grise la séparation des voix ; pas de sous-titres possibles), « Remplacements », « Hésitations », « Masquer les hésitations dans les sous-titres » (coché au départ).
- **Dictionnaire de remplacements** : fenêtre à deux onglets (« Ce projet » / « Tous les projets », `remplacements.json`). Suites de mots comparées sans majuscules ni ponctuation collée ; la plus longue d'abord ; le mot obtenu va du début du premier mot à la fin du dernier et garde la ponctuation qui suivait. Appliqué après chaque transcription, et tout de suite à la transcription actuelle quand on enregistre le dictionnaire.
- **Hésitations** : liste par langue, modifiable (« Hésitations… », séparées par des virgules ; préférence `hesitations`). Au départ : français « euh, heu, euhm, hum, hmm, mmh, mh, bah » ; anglais « uh, um, uhm, er, erm, hmm, mm, mhm » ; espagnol, italien, néerlandais, allemand. Dans l'éditeur : en gris, barrées si elles sont masquées.
- **Éditeur** : texte mot par mot (une personne par paragraphe « Personne 2 : » quand les voix sont séparées) ; mot en cours de lecture surligné en mauve léger, mot choisi en mauve. Clic sur un mot : il est choisi, et la lecture s'y place si elle est en cours (sinon, « ▶ » part de ce mot). Panneau du mot choisi : texte, début et fin (secondes, virgule acceptée) et « Appliquer » ; « Fusionner avec le suivant » (le texte réuni garde l'espace), « Couper en deux » (à l'espace, sinon au milieu ; temps partagé selon les lettres), « Supprimer ». Un ajustement ne chevauche jamais les voisins (ils sont raccourcis, 20 ms minimum par mot). « Copier le texte ».

---

## 7. Studio sous-titres

### 7.1 Formats de vidéo

- Préréglages : **9:16** (TikTok, Reels, Snap, Shorts), **4:5** (fil Facebook/Instagram), **3:4**, **1:1**, **16:9**, **personnalisé** (largeur × hauteur, de 240 à 4 096 px, arrondis à un nombre pair).
- Si une vidéo est importée, **son format s'impose** (liste grisée, « Celui de la vidéo (1080 × 1920) ») : l'overlay de la V3 doit avoir sa taille exacte. Une vidéo choisie seulement pour l'aperçu (projet sans vidéo, §7.9) l'impose aussi.
- Toutes les tailles et positions sont exprimées **en proportion de la hauteur de la vidéo** : un style garde le même aspect quel que soit le format.

### 7.2 Texte affiché

- Le texte des sous-titres est distinct du texte TTS (pas de balises, pas de majuscules d'accentuation).
- **Casse** (affichage uniquement) : comme écrit, TOUT EN MAJUSCULES ou tout en minuscules (V2 ; en V1, la case « Tout en majuscules », reprise à l'ouverture d'un ancien projet).
- Typographie automatique selon la langue (ex. français : espace insécable avant `! ? : ;`).
- Ponctuation affichée ou masquée (option).

### 7.3 Règles de découpage

**Paramètres :**
- nombre maximum de **caractères** par sous-titre ;
- nombre maximum de **mots** par sous-titre ;
- nombre maximum de **lignes** (1 ou 2) ;
- coupe préférentielle sur la ponctuation (option, activée par défaut) ;
- durée minimale d'affichage d'un sous-titre (réglable).

**Priorité : les caractères l'emportent sur les mots.** Un mot n'est jamais coupé en deux.

**Deux limites d'écran, toujours actives :**
- **Zone de sécurité** (souple) : dépend de la plateforme choisie (TikTok, Reels, Snap, Facebook…). Le texte doit normalement y rester.
- **Marge maximum** (stricte) : par défaut **5 %** de chaque bord de l'écran, réglable. Le texte ne la dépasse **jamais**.

**Ordre de décision quand un sous-titre est trop large :**
1. Regroupement normal selon la limite de caractères, puis de mots.
2. Ne tient pas dans la zone de sécurité → le texte **peut déborder** dans la marge, jusqu'à la marge maximum.
3. Ne tient toujours pas → **redécoupage** : le dernier mot passe au sous-titre suivant (aucune taille ne change).
4. Un **mot seul** reste trop large → **uniquement dans ce cas**, sa taille est réduite pour tenir dans la marge maximum (avec une taille minimum). Le sous-titre est signalé **en orange** dans la timeline.

**Règles absolues :**
- Le nombre de lignes maximum n'est **jamais** dépassé (1 ligne → jamais de 2e ; 2 lignes → jamais de 3e).
- On ne change **jamais** la taille d'un mot quand d'autres mots sont affichés avec lui.
- La largeur est mesurée **en pixels réels** avec la police et la taille choisies (pas seulement en caractères).

### 7.4 Style du texte

Fait au lot 4 de la V2 (détails au §7.10) ; position et alignement : lot 3 (§7.9).

- Police : polices fournies avec l'app, polices installées sur Windows, et import de fichiers `.ttf` / `.otf` ; graisse (celles de la police).
- Taille (proportionnelle à la hauteur de la vidéo), casse, ponctuation.
- Couleur du texte, ou dégradé de deux couleurs ; toutes les couleurs ont leur opacité, et se prennent aussi dans l'aperçu (pipette).
- **Contour** : oui/non, couleur, épaisseur, angles arrondis ou nets ; dessiné autour des lettres.
- **Ombre** : oui/non, couleur et opacité, flou, décalage X/Y, portée par le texte ou par le fond.
- **Lueur** : oui/non, couleur, taille, intensité.
- **Fond** : aucun, derrière chaque mot, derrière chaque ligne ou un seul bloc ; couleur et opacité, marges intérieures, arrondi, bordure.
- Interlignage, espace entre les lettres, espace entre les mots.
- Position verticale (haut / centre / bas + réglage fin), alignement.

### 7.5 Mot actif (mot en cours de prononciation)

États des mots (à venir, actif, déjà dits, accentués) faits au lot 5 de la V2 (§7.11) ; animations (« pop », apparition…) au lot 6 (§7.12).

Options **combinables** :
- couleur du texte du mot actif ;
- contour propre au mot actif (couleur, épaisseur) ;
- fond surligné derrière le mot (couleur, marge, arrondi) ;
- agrandissement « pop » (échelle, durée de l'animation) ;
- lueur / glow (couleur, intensité) ;
- soulignement ;
- apparence des **autres mots** : opacité ou couleur atténuée ;
- mode d'animation :
  - **surlignage** : tout le sous-titre est visible, le mot actif s'allume au bon moment ;
  - **apparition** : les mots apparaissent un par un.

### 7.6 Préréglages de style

- Enregistrer la combinaison complète (texte + mot actif + découpage + position) sous un nom.
- Appliquer, dupliquer, modifier, supprimer.
- Fait au lot 7 de la V2 (§7.13), avec les 6 styles fournis, le préréglage des nouveaux projets (★), l'export et l'import.

### 7.7 Aperçu

- Lecteur vidéo (ou fond neutre si audio seul) avec les sous-titres rendus **exactement comme à l'export** (même moteur de dessin). Fait au lot 3 de la V2 (§7.9).
- Repères activables : zone de sécurité (pointillés mauves), marge maximum (rouge), grille. Fait (§7.9).
- Choix de la plateforme pour la zone de sécurité.
- Timeline des sous-titres (lot 7 de la V2) : les bords se déplacent **de mot en mot** entre deux sous-titres voisins (le moment des mots ne change jamais), sous-titres signalés en orange (cf. §7.3), double-clic : « Corriger les mots » (module Transcription). Fait : la « Frise » (§7.13).

### 7.8 Mise en œuvre (étape 8)

Page **Sous-titres** : mots des sous-titres (transcription du projet, ou « Créer les sous-titres » d'une prise, §3.3 ; « Corriger les mots » ouvre le module Transcription), réglages, liste des sous-titres, réorganisation à la main (V1.1), écoute, export SRT. Les sous-titres sont recalculés à chaque changement de réglage (`sous_titres.py`, testé sans interface) ; seuls les réglages et les sous-titres réorganisés à la main sont enregistrés dans le projet.

**Réglages par défaut** : 24 caractères (espaces comprises) et 5 mots au plus par sous-titre, 2 lignes au plus, coupe de préférence après la ponctuation, durée minimale 0,6 s ; ponctuation affichée, pas de majuscules, hésitations masquées (réglage partagé avec la transcription) ; format « celui de la vidéo » (sinon 9:16), zone de sécurité TikTok, marge maximum 5 %, texte à 4 % de la hauteur de la vidéo. Style du texte d'un nouveau projet (V2, §7.10) : Montserrat Extra-grasse, blanc, contour noir.

**Texte affiché (§7.2)** : sans les hésitations masquées ; une ponctuation transcrite à part rejoint son mot ; ponctuation masquée = retirée autour des mots (gardée à l'intérieur : « l'huile », « anti-rides », « 3.5 ») ; typographie : en français, espace insécable avant « ! ? ; : » (pas dans « 10:30 ») et à l'intérieur des guillemets « », dans les autres langues pas d'espace avant ; jamais d'espace avant « , . … ». « Tout en majuscules » à la fin. Les temps des mots ne changent jamais.

**Découpage (§7.3)** :
- Un sous-titre se termine toujours : après une fin de phrase (« . ! ? … », si « couper sur la ponctuation » est coché), à un changement de personne, ou après un silence de plus de 0,8 s.
- Caractères et mots : deux maximums (un mot plus long que la limite de caractères reste seul) ; un mot n'est jamais coupé.
- Parmi tous les découpages possibles, l'app retient le meilleur (programmation dynamique) : des sous-titres bien remplis et de longueurs proches (l'écart au maximum de caractères compte au carré), qui finissent si possible sur une ponctuation (bonus), en restant de préférence dans la zone de sécurité (petite pénalité pour la marge).

**Écran (§7.3)** : la largeur de chaque ligne est mesurée en pixels par le moteur de dessin (V2, §7.9 ; en V1 par Qt), avec la police du style (en V1 : Inter SemiBold) à la taille du texte (en % de la hauteur de la vidéo, arrondie au pixel), ses espaces, et ce que le contour et le fond ajoutent de chaque côté (V2, §7.10).
- Formats : celui de la vidéo importée (dimensions remises à l'endroit pour une vidéo de téléphone enregistrée « couchée », rotation de 90°), sinon 9:16 (1080 × 1920), 4:5 (1080 × 1350), 3:4 (1080 × 1440), 1:1 (1080 × 1080), 16:9 (1920 × 1080), ou personnalisé (V2).
- Ordre : une ligne dans la zone de sécurité ; sinon deux lignes équilibrées dans la zone (si 2 lignes permises ; retour à la ligne de préférence après une ponctuation) ; sinon la même chose jusqu'à la marge maximum ; sinon le sous-titre est redécoupé (aucune taille ne change). Un mot seul trop large est rapetissé jusqu'à tenir dans la marge maximum, sans descendre sous 60 % de la taille du texte : il est signalé en orange (liste des sous-titres et aperçu), avec le conseil de le raccourcir s'il ne tient toujours pas.
- Sous-titres centrés : la zone de sécurité retient le plus large des deux côtés (ex. YouTube Shorts : 10 % des deux côtés). Si elle est plus large que la zone de la marge maximum, c'est la marge maximum qui compte.

**Zones de sécurité (écran 9:16, en part des bords)** :

| Plateforme | Gauche | Droite | Haut | Bas | Source |
|---|---|---|---|---|---|
| TikTok | 11,1 % (120 px) | 11,1 % (120 px) | 12,5 % | 34,4 % | Modèle de zone de sécurité de TikTok Ads (avril 2025). La réserve « 300 px à droite sous le milieu de l'écran » n'est pas appliquée (lot 3) : le modèle officiel (fichier à télécharger dans le gestionnaire de publicités) n'a pas pu être relu, des sources de 2026 citent 140 px sur toute la hauteur, et elle rétrécirait toutes les lignes (découpage des anciens projets changé) |
| Instagram, Facebook (Reels, Stories) | 6 % | 6 % | 14 % | 35 % | Guide des publicités Meta |
| YouTube Shorts | 0 % | 10 % | 10 % | 25 % | Google Ads, emplacement Shorts |
| Snapchat | 3,7 % (40 px) | 3,7 % | 10,4 % | 19,3 % | Valeurs courantes, non confirmées par Snapchat |
| Aucune | 0 % | 0 % | 0 % | 0 % | Marge maximum seulement |

Les côtés donnent la largeur des lignes ; le haut et le bas placent les sous-titres (« Haut » et « Bas », V2, §7.9).

**Temps** : un sous-titre va du début de son premier mot à la fin du dernier ; s'il dure moins que la durée minimale, il est prolongé jusqu'au sous-titre suivant au plus (et jusqu'à la fin de l'audio pour le dernier), puis avancé jusqu'au précédent au plus ; un trou de 0,3 s au plus entre deux sous-titres est comblé (pas de clignotement).

**Réorganiser à la main (V1.1)** : sous l'aperçu, « Réorganiser à la main » agit sur le sous-titre choisi dans la liste (boutons désactivés tant qu'aucun n'est choisi ; les infobulles citent les vrais mots).
- Actions : « Monter le premier mot » (au sous-titre précédent), « Descendre le dernier mot » (au suivant), « Couper » (menu « Couper avant « mot » » : le mot choisi commence le nouveau sous-titre), « Fusionner avec le suivant », « Rétablir » (le découpage automatique de ce sous-titre, ou de tous). Monter ou descendre le seul mot d'un sous-titre le fait disparaître. Le résultat se voit tout de suite (liste et aperçu), avec un message d'une ligne (ex. « « a » passe à la fin du sous-titre 3. »).
- **Le temps des mots ne change jamais** : un sous-titre va du début de son premier mot à la fin de son dernier, avec la durée minimale et le comblement des petits trous, comme les autres.
- **Mêmes règles que le découpage automatique** : caractères et mots au plus (un mot seul peut les dépasser), lignes au plus et place à l'écran jusqu'à la marge maximum, fin de phrase (si « Couper de préférence après la ponctuation » est cochée), changement de personne, silence de plus de 0,8 s. Une action qui ne les respecte pas est **refusée** (rien ne change) avec la raison et le réglage à changer, ex. « Impossible : le sous-titre 5 ferait 26 caractères, et « Caractères au plus » est réglé sur 24. » ; « Impossible : le sous-titre 1 aurait 4 mots, et « Mots au plus » est réglé sur 3. » ; « … ne tiendrait pas sur une ligne dans l'écran, et « Lignes au plus » est réglé sur 1 » ; « … serait trop large pour l'écran, même jusqu'à la marge maximum (réglages « Taille du texte » et « Marge maximum ») ».
- Remarque **« Ajusté à la main »** dans la liste (après « Mot rapetissé… » s'il y a lieu) ; le résumé compte les sous-titres ajustés.
- Enregistrement : chaque sous-titre ajusté est rangé dans la transcription (`ajustements_sous_titres`) sous la forme [début, fin] : du début de son premier mot à la fin de son dernier. Ses mots sont ceux dont le **milieu** tombe dans ce moment ; un mot n'appartient qu'à un ajustement. Si deux mots voisins se recouvrent dans le temps, la borne passe à mi-chemin entre leurs milieux ; deux mots au même moment ne peuvent pas être séparés (action refusée : « corrige d'abord leur moment »). Pourquoi le temps plutôt que la place des mots : l'ajustement suit ainsi les mots corrigés dans le module Transcription (fusion, coupe, suppression) et les réglages du texte affiché.
- Calcul : les sous-titres ajustés gardent leurs mots ; les mots entre eux sont découpés automatiquement (même programmation dynamique). Un ajustement qui ne respecte plus les règles est défait : ses mots reviennent au découpage automatique.
- **Réglage qui défait un ajustement** : tous les réglages des sous-titres (y compris « Masquer les hésitations », ici et dans le module Transcription) passent par `ui/sous_titres_du_projet.py` : avant d'appliquer un réglage, le découpage est recalculé avec lui. S'il défait des ajustements, la question est posée en les nommant, ex. « Ce réglage défait ton ajustement du sous-titre 4 (« Mais ce Sérum Glowzy a ») : 22 caractères, pour 20 au plus. » (une ligne par sous-titre s'il y en a plusieurs). « Garder le réglage actuel » (choix par défaut) : rien ne change, le champ reprend sa valeur. « Appliquer et défaire cet ajustement » : le réglage change et ces sous-titres reviennent au découpage automatique.
- **Mots corrigés dans le module Transcription** (texte, temps, fusion, coupe, suppression, remplacements, liste des hésitations) : jamais bloqués. Un ajustement devenu impossible est défait, et la page Sous-titres le dit (message orange) : « Des mots ont changé dans le module Transcription : ton ajustement du sous-titre 4 (« … ») ne tient plus (26 caractères, pour 24 au plus). Il revient au découpage automatique. »
- Une nouvelle transcription (autre source, autre prise, ou nouvelle transcription de la même source) efface les ajustements ; les confirmations déjà demandées le précisent quand il y en a.
- L'export SRT reprend exactement la liste affichée.

**Liste et écoute** : numéro, temps, texte (lignes comprises), remarque ; les sous-titres signalés sont en orange. Pendant la lecture, le sous-titre en cours est surligné dans la liste. Clic sur un sous-titre : il est choisi, et l'aperçu (la lecture) se place sur lui. Changer de module arrête la lecture de la page quittée (et libère les fichiers). Le grand texte de l'aperçu simple de la V1 est remplacé par l'aperçu fidèle (§7.9).

### 7.9 Studio (V2, lot 3, version 1.4.0)

La page Sous-titres devient un **studio** : le bloc « Mots des sous-titres » (inchangé), puis l'**aperçu** à gauche (400 px) et les **réglages** à droite ; l'un sous l'autre quand la page a moins de 880 px de large (fenêtre étroite), ou moins que ce que demandent les deux colonnes (depuis le lot 4 : l'onglet affiché peut demander plus de place). Dessous, la liste des sous-titres, « Réorganiser à la main » et l'export SRT (inchangés). Choix détaillés : document « UGC Studio - V2 Studio de style et Script », §3 à §7.

**Moteur de dessin commun** (`rendu/moteur.py`) :
- Le texte devient des **formes** (le contour exact de chaque lettre) à la taille réelle de la vidéo ; l'aperçu les dessine en plus petit, l'export de la V3 les dessinera à 100 % sur un fond transparent (`image()` : une image transparente à la taille de la vidéo). Un test vérifie que l'aperçu à 100 % et cette image sont identiques au pixel près. À chaque instant, le sous-titre est **une seule image transparente**, posée d'un coup sur la vidéo (aperçu) ou sur le fond transparent (export), même quand quelque chose bouge (fond qui glisse, lot 5) : poser plusieurs couches l'une après l'autre sur la vidéo arrondirait leurs bords et leurs transparences d'un ou deux niveaux sur 255, et l'aperçu ne serait plus exactement l'export.
- Le **découpage** mesure la largeur des lignes avec ce moteur (« ça tient » = « ça tient une fois dessiné »). Police du lot 3 : Inter SemiBold à la taille du texte arrondie au pixel, exactement la mesure de la V1 : le découpage d'un projet de la 1.1.0 ou de la 1.3.0 ne change pas (vérifié par un test).
- Place des lignes et des mots : `mise_en_page.py` (sans interface, testé seul). Une ligne a exactement la largeur mesurée par le découpage ; un mot commence là où finit la ligne, moins la largeur de ce qui le suit.
- Apparence du lot 3 : celle de la V1, texte blanc avec une **ombre légère** (noire à 55 %, floutée de 0,4 % de la hauteur, décalée de 0,2 % vers le bas). Ordre de dessin : ombre, remplissage (contour, fond et lueur : lot 4, §7.10). Un sous-titre dessiné est gardé en mémoire pour chaque taille d'affichage : pendant la lecture, l'aperçu le recopie.

**Aperçu** (`ui/composants/apercu.py`, `ui/pages/sous_titres/apercu.py`) :
- Fond : la **vidéo** du projet, un **gris** neutre, ou un **damier** (pour juger un texte prévu pour l'overlay transparent). Zoom : **Ajusté** (la vidéo entière, 540 px de haut au plus) ou **100 %** (un pixel de la vidéo par pixel de l'écran ; l'aperçu défile).
- Lecture et pause (bouton, ou barre Espace), barre de position, temps, **boucle** sur le sous-titre choisi dans la liste.
- **Repères** (cases) : zone de sécurité de la plateforme (pointillés mauves), marge maximum (trait rouge), grille (tiers et milieu, traits fins). Fond, zoom, repères et boucle sont retenus d'une fois sur l'autre (préférences).
- **Synchronisation** : le temps des sous-titres est celui de l'image réellement affichée (son moment de présentation, donné par Qt Multimedia) : le sous-titre change exactement sur la bonne image. Son seul (prise de voix) : la position du son, affinée entre deux nouvelles de Qt (qui la donne toutes les 50 ms).
- Le sous-titre se **glisse verticalement** dans l'aperçu (curseur ↕ au survol) : le réglage fin suit, dans ses limites.
- Projet ouvert : l'aperçu montre le premier sous-titre, sans le choisir dans la liste.
- **Vidéo introuvable** (déplacée ou supprimée : elle n'est pas copiée dans le projet) : message orange, fond gris, son de la piste du projet, et « Retrouver la vidéo… ».
- Vidéo de téléphone en HDR (couleurs étendues) : l'image peut paraître un peu terne dans l'aperçu (ses couleurs sont converties pour un écran normal) ; le texte, lui, est exact. La gestion du HDR est un sujet de la V3 (§8.3).
- **Projet sans vidéo** (prise de voix, audio importé) : onglet Écran, « Vidéo d'aperçu » : « Choisir une vidéo… » (ex. le montage exporté de Premiere Pro), « La voix commence à » (décalage, en secondes), « Son de la vidéo » (sinon la voix de la prise, sous la vidéo muette, recalée sur elle au-delà de 0,15 s d'écart), « Retirer ». Sa résolution, lue par Qt Multimedia, impose le format.

**Réglages en onglets** (`ui/pages/sous_titres/reglages.py`) :
- **Texte** : taille (en % de la hauteur, avec les pixels à côté), casse, ponctuation ; info : police et apparence (lot 4 : tout le style du texte, §7.10).
- **Position** : Haut, Centre ou Bas (« Haut » : juste sous le haut de la zone de sécurité ; « Bas » : juste au-dessus de son bas ; « Centre » : milieu de l'écran) ; **réglage fin** (glissière, en dixièmes de % de la hauteur, bouton « Revenir à 0 % ») ; **alignement** gauche, centre ou droite ; réglages avancés : **largeur des lignes** (30 à 100 % de la largeur utile). Point fixe du bloc : son haut, son milieu ou son bas (un sous-titre de 2 lignes grandit vers le bas, des deux côtés, ou vers le haut). Le bloc ne dépasse jamais la marge maximum (en haut et en bas : en % de la hauteur) ; la glissière s'arrête à temps pour le plus grand sous-titre possible (« Lignes au plus »).
- **Découpage** : caractères, mots et lignes au plus, durée minimale, coupure après la ponctuation, hésitations masquées.
- **Écran** : format (§7.1), zone de sécurité, marge maximum, mesures de l'écran (« Vidéo 1080 × 1920, texte de 77 px (Inter SemiBold) : une ligne tient en 840 px… »), vidéo d'aperçu.
- Largeur utile d'une ligne selon l'alignement : centré, la zone de sécurité retient le plus large des deux côtés (comme en V1) ; à gauche, la ligne part du bord gauche de la zone (jamais de la marge maximum) et va jusqu'au bord droit de la zone (souple), ou jusqu'à la marge maximum (strict) ; à droite, l'inverse. La largeur des lignes la réduit d'autant.
- Haut, centre, bas et réglage fin ne changent que l'aperçu (jamais le découpage : la liste n'est pas recalculée ; enregistré quand la glissière s'arrête). Alignement, largeur des lignes, format, taille… refont le découpage, avec la question de la V1.1 s'ils défont un ajustement fait à la main.

**Projet au format 7** : `sous_titres` est rangé en trois parties, la forme écrite qui servira aussi aux préréglages exportés (lot 7) :

```json
"sous_titres": {
  "style": {
    "texte": {"police": "Inter", "graisse": 600, "taille_pct": 4.0, "casse": "normale", "ponctuation": true,
              "couleur": {"code": "#FFFFFF", "opacite": 100.0},
              "ombre": {"active": true, "couleur": {"code": "#000000", "opacite": 55.0},
                        "flou_pct": 0.4, "decalage_x_pct": 0.0, "decalage_y_pct": 0.2}},
    "position": {"verticale": "bas", "decalage_pct": 0.0, "alignement": "centre", "largeur_lignes_pct": 100.0},
    "decoupage": {"caracteres_max": 24, "mots_max": 5, "lignes_max": 2, "couper_sur_ponctuation": true, "duree_min_s": 0.6}
  },
  "ecran": {"format": "auto", "largeur": 1080, "hauteur": 1920, "plateforme": "tiktok", "marge_max_pct": 5.0},
  "apercu": {"chemin": "", "decalage_s": 0.0, "largeur": 0, "hauteur": 0, "son_de_la_video": true}
}
```

- Tailles en % de la hauteur de la vidéo ; couleurs « #RRGGBB » avec une opacité de 0 à 100 % (ce sont des choix de la vidéo, pas des couleurs de l'interface : elles ne sont pas dans `theme.py`). « auto » : le format de la vidéo, sinon 9:16 (valeur des projets de la V1).
- Lecture tolérante (`style_sous_titres.py`) : une valeur absente ou illisible garde sa valeur par défaut, une valeur hors limites est ramenée dans les limites, un choix inconnu est ignoré.
- Projet des formats 4 à 6 : « Tout en majuscules », la ponctuation et la taille passent dans le style du texte ; apparence de la V1 ; en bas de la zone de sécurité, centré.

**Autotest** : une petite vidéo de test (AVI « Motion JPEG », écrite par l'app elle-même, `avi.py` et `rendu/video_test.py`) remplace la vidéo de démonstration : le `.exe` doit en recevoir la première image (taille et couleur vérifiées), puis la lire 1,5 s (le temps avance). Captures : studio sur la vidéo, damier et grille, zoom 100 %, chaque onglet, sous-titre en haut à gauche.

### 7.10 Style du texte (V2, lot 4, version 1.5.0)

Onglet **Texte** du studio (`ui/pages/sous_titres/onglet_texte.py`) : tout ce qui vaut pour tous les mots, en groupes repliables (§9.4 octies) ; les réglages rares attendent dans « Réglages avancés », replié dans le groupe ; chaque groupe a son bouton **« Rétablir »** (valeurs de départ des nouveaux projets ; au lot 7, celles du préréglage d'origine). Les réglages d'un effet décoché sont grisés. Choix détaillés : document « UGC Studio - V2 Studio de style et Script », §6.

| Groupe | Réglages | Nouveau projet |
|---|---|---|
| Police | recherche, police (fournies d'abord, puis importées et de Windows ; chaque nom écrit dans sa police), graisse (celles de la police), « Importer une police… » | Montserrat Extra-grasse (800) |
| Taille et casse | taille (% de la hauteur, pixels à côté), casse, ponctuation | 4 % (77 px en 1080 × 1920), comme écrit, ponctuation affichée |
| Remplissage | couleur ; dégradé de deux couleurs (vertical, horizontal ou en biais), sur chaque ligne | blanc |
| Contour | case, couleur, épaisseur ; avancé : angles arrondis ou nets | oui, noir, 0,3 % (6 px) |
| Ombre | case, couleur (son opacité fait la force de l'ombre), flou, décalages horizontal et vertical ; avancé : portée par le texte ou par le fond | non |
| Lueur | case, couleur, taille, intensité | non |
| Fond | aucun, derrière chaque mot, derrière chaque ligne ou un seul bloc ; couleur, marges intérieures horizontale et verticale, arrondi ; avancé : bordure (couleur, épaisseur) | aucun |
| Espaces | interlignage (% de celui de la police), espace entre les lettres, espace entre les mots | 100 %, 0, 0 |

- **Tailles** : affichées en pixels de la vidéo actuelle, rangées en % de sa hauteur (un style garde le même aspect dans tous les formats), à trois décimales comme dans le projet. Un champ n'affiche qu'un arrondi : tant qu'on n'y touche pas, la valeur exacte du projet est gardée (changer une couleur ne change rien d'autre).
- **Couleurs** (`ui/composants/champ_couleur.py`) : pastille (menu : couleurs proposées, « Autre couleur… », pipette), code « #RRGGBB », opacité (0 à 100 %), bouton **pipette**. Pipette : le prochain clic dans l'aperçu prend la couleur affichée sous le pointeur (vidéo, fond ou sous-titre ; pas les repères) ; Échap ou un clic ailleurs annule ; une info le dit sous l'aperçu ; quand la page est étroite, elle défile jusqu'à l'aperçu. Ces couleurs sont des choix de la vidéo, pas de l'interface : elles ne sont pas dans `theme.py`.
- **Polices** (`rendu/polices.py`) :
  - fournies, libres pour la publicité (licence SIL OFL, fichiers de licence à côté des polices) : Montserrat et Poppins (graisses 500 à 900), Anton, Bebas Neue, Inter (400 à 700) ; chargées au démarrage ;
  - importées (`.ttf`, `.otf`) : copiées dans `%APPDATA%\UGC Studio\polices\` (un projet les garde si le fichier d'origine est déplacé ; même nom mais autre contenu : « nom (2).ttf »), chargées à chaque démarrage ; un fichier qui n'est pas une police lisible est refusé avec un message ;
  - de Windows : celles que Qt trouve. Une police de Windows ou importée a sa propre licence (info dans le groupe, rubrique « Polices et licences » des conseils) ;
  - Windows range parfois les graisses d'une police sous des familles à part (« Montserrat ExtraBold ») : le style retient la famille de base et la graisse, l'app retrouve la famille à demander (comme pour Inter, §9.5) ;
  - **police absente** (autre ordinateur, police désinstallée) : Inter la remplace (à la graisse la plus proche), un message orange le dit dans l'onglet, et le style garde le nom et la graisse de la police : rien n'est perdu pour l'ordinateur où elle existe.
- **Dessin** (`rendu/moteur.py`), dans cet ordre : ombre, fond (et sa bordure), lueur, contour, remplissage.
  - Contour : un trait deux fois plus épais, dessiné sous le texte : la moitié visible est **autour** des lettres, qui gardent leur épaisseur.
  - Fond : rectangles arrondis derrière chaque mot, chaque ligne, ou tout le bloc (de la ligne la plus à gauche à la plus à droite), de la hauteur des lettres (accents et jambages compris) plus la marge verticale. Deux fonds de ligne qui se touchent forment une seule forme (pas de double opacité) : l'interlignage les écarte.
  - Lueur : la silhouette du texte et de son contour, élargie de la moitié de la taille du halo, puis floutée ; l'intensité règle son opacité.
  - Ombre « portée par le fond » : celle du fond (sinon : celle des lettres et de leur contour).
  - Dégradé : sur chaque ligne, de la couleur du texte (en haut, à gauche) à la seconde couleur.
  - Flous calculés une fois par sous-titre et par taille d'affichage, gardés en mémoire (§7.9).
- **Débord** : le contour et le fond (marge intérieure et bordure) dépassent du texte. Ils comptent dans la largeur mesurée par le découpage (« ça tient une fois dessiné ») et dans la boîte du sous-titre : c'est la boîte visible qui reste entre les marges maximum, part du bord de la zone de sécurité (alignement à gauche ou à droite) et règle la course du réglage fin. Un mot seul trop large est rapetissé, pas son débord. L'ombre et la lueur, floues et légères, n'en font pas partie.
- **Espaces** : l'espace entre les lettres s'ajoute après chaque lettre sauf la dernière (une ligne reste centrée sur ses lettres) ; l'espace entre les mots s'ajoute à chaque espace.
- Un réglage qui change la largeur du texte (police, graisse, taille, espaces, contour, marges du fond) refait le découpage, avec la question de la 1.1.0 s'il défait un ajustement fait à la main (§7.8) ; les autres ne changent que le dessin.
- **Style de départ** des nouveaux projets : `ressources/style_de_depart.json` (Montserrat Extra-grasse, blanc, contour noir de 0,3 %, sans ombre). Depuis le lot 7, un nouveau projet prend le préréglage marqué ★ (§7.13) ; ce style de départ sert quand aucun ne l'est. Un projet plus ancien (1.1.0 à 1.4.0) garde son apparence et son découpage : Inter SemiBold, blanc, ombre légère, sans contour ni fond (les valeurs par défaut du style).
- **Forme écrite** du style du texte (projet au format 7, numéro inchangé : un projet de la 1.4.0, à qui manquent les nouveaux groupes, les reçoit avec leurs valeurs par défaut). Choix possibles : `direction` vertical, horizontal ou biais ; `angles` arrondis ou nets ; `portee` texte ou fond ; `mode` du fond aucun, mot, ligne ou bloc.

```json
"texte": {
  "police": "Montserrat", "graisse": 800, "taille_pct": 4.0, "casse": "normale", "ponctuation": true,
  "couleur": {"code": "#FFFFFF", "opacite": 100.0},
  "degrade": {"actif": false, "couleur": {"code": "#FACC15", "opacite": 100.0}, "direction": "vertical"},
  "contour": {"actif": true, "couleur": {"code": "#000000", "opacite": 100.0}, "epaisseur_pct": 0.3, "angles": "arrondis"},
  "ombre": {"active": false, "couleur": {"code": "#000000", "opacite": 55.0}, "flou_pct": 0.4,
            "decalage_x_pct": 0.0, "decalage_y_pct": 0.2, "portee": "texte"},
  "lueur": {"active": false, "couleur": {"code": "#F59E0B", "opacite": 100.0}, "taille_pct": 1.0, "intensite_pct": 80.0},
  "fond": {"mode": "aucun", "couleur": {"code": "#000000", "opacite": 60.0}, "marge_x_pct": 0.8, "marge_y_pct": 0.3,
           "arrondi_pct": 0.6, "bordure": false, "bordure_couleur": {"code": "#FFFFFF", "opacite": 100.0},
           "bordure_epaisseur_pct": 0.15},
  "espaces": {"interligne_pct": 100.0, "lettres_pct": 0.0, "mots_pct": 0.0}
}
```

**Conseils** de la page : rubriques « Style du texte » et « Polices et licences ».

**Autotest** : polices fournies chargées à la bonne graisse (Montserrat 700 et 800, Poppins 700 et 800, Anton, Bebas Neue) ; style de départ du projet de démonstration ; onglet Texte avec tous ses groupes ouverts (capture du panneau entier) ; six styles proches de ceux de l'annexe B du document V2, faits avec les seuls réglages de l'onglet (une image à la taille de la vidéo, recadrée sur le sous-titre : contour, fond par mot, dégradé, grand texte en majuscules, bandeau par ligne, lueur) ; pipette (elle prend le gris du fond, pas les repères).

### 7.11 Mots (V2, lot 5, version 1.6.0)

Onglet **Mots** du studio, entre Texte et Position (`ui/pages/sous_titres/onglet_mots.py`) : ce qui change pour le mot en train d'être dit. Choix détaillés : document « UGC Studio - V2 Studio de style et Script », §8.

- **Raccourci** (liste) : Sous-titre fixe, Surlignage, Karaoké, Apparition, Mot par mot. Il remplit les trois états ; tout reste modifiable ensuite (la liste montre alors « Personnalisé »). Surlignage : le mot actif en jaune (#FFD43B), à 108 %. Karaoké : le mot actif en jaune (#FACC15), à 106 %, et les mots déjà dits restent jaunes. Apparition : les mots à venir sont invisibles (chaque mot apparaît quand il est dit, puis reste). Mot par mot : seul le mot actif est visible. Les accentués et l'avance de l'allumage ne changent pas.
- **États** (boutons) : À venir, Mot actif, Déjà dits, Accentués. Un état à la fois s'affiche, avec ses réglages : visibilité (un mot invisible garde sa place), opacité ; puis en groupes repliables : remplissage (couleur, dégradé), contour, lueur, **fond surligné** derrière le mot (couleur, marges, arrondi ; pour le mot actif, réglage avancé : il **glisse** d'un mot à l'autre, avec sa durée), **soulignement** (couleur, épaisseur, distance sous la ligne de base), taille (agrandissement autour du centre du mot) et décalage vertical.
- **« Comme le texte »** : chaque réglage d'un état vaut celui de l'onglet Texte tant qu'on ne le change pas (le champ montre la valeur du texte). Un réglage changé a son libellé en mauve et un bouton ↺ (« Comme le texte ») qui le rétablit. Un nouveau projet, comme un projet plus ancien, commence en « Sous-titre fixe » (aucun état réglé).
- **Accentués** (facultatif, case « Utiliser l'état « Accentués » ») : pour les sous-titres d'une prise, les mots mis en valeur dans son script (bouton « Accentuer » du module Voix) prennent cet état, sauf quand ils sont actifs. Ils sont retrouvés à chaque calcul en comparant les mots du script et ceux des sous-titres, comme l'alignement (`alignement.marquer_les_accentues`) : rien n'est enregistré dans la transcription, et un mot corrigé depuis dans le module Transcription n'est plus reconnu. L'onglet dit combien de mots accentués compte le script (ou que les sous-titres ne viennent pas d'une prise). Couleur au départ : jaune.
- Réglages avancés : **avance de l'allumage**, de −200 à +200 ms (positif : les mots s'allument plus tôt). Le moment des mots ne change pas.

**Règles** (`rendu/moteur.py`) :
- Le mot actif est le dernier mot du sous-titre déjà commencé, à l'instant affiché (avance comprise) : pendant un petit silence entre deux mots, le dernier dit reste allumé ; avant le premier mot (sous-titre affiché un peu plus tôt pour la durée minimale), aucun ; après le dernier, il reste allumé jusqu'à la fin du sous-titre. Les mots d'avant sont « déjà dits », ceux d'après « à venir ».
- Les mots d'un même état sont dessinés ensemble (lueur, contour, remplissage, soulignement), puis posés avec l'opacité de l'état (un contour ne se voit pas à travers des lettres à moitié transparentes) ; le mot actif en dernier, par-dessus ses voisins. L'ombre suit les mots visibles (à moitié transparente pour un état à moitié transparent) ; le fond « derrière chaque mot » de l'onglet Texte suit l'état de son mot (invisible avec lui, agrandi avec lui) ; ceux derrière chaque ligne ou en bloc restent.
- **Place** : agrandissements et décalages autour du centre du mot, sans pousser ses voisins (la place des mots est calculée une fois pour le sous-titre entier : rien ne bouge pendant la lecture). Le plus grand agrandissement prévu, le contour, le fond surligné et le soulignement des états comptent dans la place : dans la largeur mesurée par le découpage (le plus large mot d'une ligne, agrandi, dépasse de chaque côté de la moitié de ce qu'il gagne), et dans la boîte du sous-titre (en haut et en bas : ce que gagne la hauteur des lettres) ; rien ne sort jamais de la marge maximum.
- **Fond qui glisse** : il part du fond du mot précédent et arrive sous le mot actif en sa durée (courbe douce) ; sur une autre ligne, il ne glisse pas. C'est la seule chose redessinée à chaque image : un sous-titre avec un mot actif donné est dessiné une fois par taille d'affichage et gardé en mémoire (48 dessins au plus), fond du mot actif compris, et l'aperçu ne se redessine que quand le mot actif change. Pendant le glissement, l'image de chaque instant est refaite à partir de deux couches gardées en mémoire (ce qui passe sous le fond, puis les lettres), avec le fond entre les deux : une seule image, comme toujours (§7.9).
- Forme écrite (projet au format 7, numéro inchangé ; un projet de la 1.5.0, sans « mots », s'ouvre en sous-titre fixe) : `sous_titres.style.mots`, avec `a_venir`, `actif`, `dits`, `accentues` (chacun : `visible`, puis `opacite_pct`, `couleur`, `degrade`, `contour`, `lueur`, `fond` (`couleur`, `marge_x_pct`, `marge_y_pct`, `arrondi_pct`, `glisse`, `duree_glisse_ms`), `soulignement` (`couleur`, `epaisseur_pct`, `distance_pct`), `taille_pct`, `decalage_y_pct` ; `null` : comme le texte), `accentues_actifs` et `avance_ms`.

```json
"mots": {
  "a_venir": {"visible": true, "opacite_pct": null, "couleur": null, "degrade": null, "contour": null, "lueur": null,
              "fond": null, "soulignement": null, "taille_pct": null, "decalage_y_pct": null},
  "actif": {"visible": true, "opacite_pct": null, "couleur": {"code": "#FFD43B", "opacite": 100.0}, "degrade": null,
            "contour": null, "lueur": null, "fond": null, "soulignement": null, "taille_pct": 108.0, "decalage_y_pct": null},
  "dits": {"visible": true, "opacite_pct": null, "couleur": null, "degrade": null, "contour": null, "lueur": null,
           "fond": null, "soulignement": null, "taille_pct": null, "decalage_y_pct": null},
  "accentues_actifs": false,
  "accentues": {"visible": true, "opacite_pct": null, "couleur": {"code": "#FFD43B", "opacite": 100.0}, "degrade": null,
                "contour": null, "lueur": null, "fond": null, "soulignement": null, "taille_pct": null, "decalage_y_pct": null},
  "avance_ms": 0
}
```

**Conseils** de la page : rubrique « Mots : le mot en train d'être dit ».

**Autotest** : sur la vidéo de démonstration, l'aperçu placé pendant « Sérum » : Surlignage, Karaoké et Apparition appliqués depuis l'onglet (le mot actif est bien « Sérum » ; une image à la taille de la vidéo, recadrée sur le sous-titre, pour chacun), puis un fond qui glisse de « Sérum » à « Glowzy » (capture au milieu du glissement) ; le sous-titre fixe revient ensuite.

### 7.12 Animations (V2, lot 6, version 1.7.0)

Onglet **Animations** du studio, entre Mots et Position (`ui/pages/sous_titres/onglet_animations.py`). Choix détaillés : document « UGC Studio - V2 Studio de style et Script », §8.

- **Mot qui devient actif** : aucune, pop, rebond, zoom, fondu ou glissement vers le haut ; durée (180 ms au départ) et intensité (100 % : l'animation telle quelle ; 50 % : deux fois moins marquée). Réglages avancés : taille de départ, au sommet et d'arrivée, opacité de départ, décalage de départ, courbe (douce, rebond ou régulière) ; tant qu'on ne les change pas, ce sont ceux de l'animation choisie (le champ les montre ; un réglage changé a son libellé en mauve et ↺ « Comme l'animation choisie »).

| Animation | Départ | Sommet | Arrivée | Opacité de départ | Décalage de départ | Courbe |
|---|---|---|---|---|---|---|
| Pop | 100 % | 116 % | 100 % | 100 % | 0 | douce |
| Rebond | 100 % | 120 % | 100 % | 100 % | 0 | rebond |
| Zoom | 92 % | (aucun) | 100 % | 100 % | 0 | douce |
| Fondu | 100 % | (aucun) | 100 % | 0 % | 0 | douce |
| Glissement vers le haut | 100 % | (aucun) | 100 % | 0 % | 1,5 % plus bas | douce |

- **Retour à « déjà dit »** : instantané ou fondu (150 ms au départ) : le mot précédent garde de moins en moins son apparence de mot actif.
- **Sous-titre entier** : apparition et disparition (aucune, fondu, pop, zoom, glissement vers le haut ou vers le bas), chacune avec sa durée (200 ms au départ). Une animation ne dure jamais plus de la moitié du sous-titre.

**Règles** (`rendu/moteur.py`) :
- Les animations ne changent jamais les temps : l'animation du mot commence quand il devient actif (avance de l'allumage comprise), l'apparition au début du sous-titre, la disparition finit à sa fin.
- Taille autour du centre du mot (ou du bloc, pour le sous-titre entier), sans pousser les voisins. Avec un sommet, la taille va du départ au sommet pendant la première moitié de l'animation, puis du sommet à l'arrivée ; sinon du départ à l'arrivée. L'opacité et le décalage vont de leur valeur de départ à la normale, selon la courbe. Le sommet (multiplié par la taille du mot actif, ex. 108 % × 116 %) et le décalage de départ comptent dans la place (§7.11) : un mot animé ne sort jamais de la marge maximum.
- Pendant son animation, le mot actif (avec son ombre) est dessiné à part une fois (gardé en mémoire), puis posé à chaque image avec sa taille, son opacité et son décalage du moment ; le reste du sous-titre ne change pas, fond surligné du mot actif compris (il ne s'anime pas avec le mot). L'aperçu se redessine à chaque image tant qu'une animation est en cours. Comme toujours, l'image de l'instant est assemblée en une seule image avant d'être posée (`image_de_l_instant`) : aperçu à 100 % et export identiques au pixel près, même au milieu d'une animation (§7.9).
- Une animation du mot, ou un retour en fondu, suffit à suivre le mot actif, même en « Sous-titre fixe » (onglet Mots).
- Forme écrite (projet au format 7, numéro inchangé ; un projet de la 1.6.0, sans « animations », n'en a aucune) : `sous_titres.style.animations`, avec `mot` (`type`, `duree_ms`, `intensite_pct`, puis `taille_depart_pct`, `taille_sommet_pct`, `taille_arrivee_pct`, `opacite_depart_pct`, `decalage_depart_pct`, `courbe`, à `null` : ceux de l'animation), `retour` (`instantane` ou `fondu`), `retour_duree_ms`, `apparition`, `apparition_duree_ms`, `disparition`, `disparition_duree_ms` (`aucune`, `fondu`, `pop`, `zoom`, `haut`, `bas`).

**Conseils** de la page : rubrique « Animations ».

**Autotest** : un pop de 400 ms sur le mot qui devient actif et un fondu de 400 ms à l'apparition du sous-titre, appliqués depuis l'onglet ; captures au sommet du pop de « Sérum » et au milieu de l'apparition (images à la taille de la vidéo, recadrées sur le sous-titre) ; l'aperçu doit se savoir en mouvement à ces moments ; puis plus d'animation.

### 7.13 Frise et préréglages (V2, lot 7, version 2.0.0)

**Frise** (`ui/composants/frise.py`) : bloc « Frise » sous l'aperçu et les réglages, sur toute la largeur. Choix détaillés : document « UGC Studio - V2 Studio de style et Script », §5.3.

- En haut, les graduations du temps (une toutes les 1, 2, 5, 10… secondes, au moins 64 px d'écart) ; puis un bloc par sous-titre, de son début à sa fin, numéroté ; en dessous, un trait par mot (son texte au survol) ; le trait mauve du moment lu.
- Clic : la lecture va à ce moment. Clic sur un bloc : il est choisi (contour mauve), dans la frise comme dans la liste des sous-titres (les deux restent synchronisées), et la lecture va au moment cliqué. Double-clic sur un bloc : « Corriger les mots » ouvre le module Transcription sur son premier mot.
- Bloc signalé (un mot rapetissé, §7.3) : contour et numéro orange. Ajusté à la main : un point mauve. Les mots du sous-titre choisi sont mauves.
- **Bord commun** de deux sous-titres qui se touchent (la fin de l'un est le début de l'autre) : un trait fin le signale, le pointeur devient une double flèche. Glissé, il saute de mot en mot (au milieu du silence entre deux mots) ; chaque sous-titre garde au moins un mot. Les mots qui vont changer de sous-titre se colorent : en mauve, ou en rouge si une règle du découpage serait enfreinte, avec la raison au survol. Au relâchement, ils passent d'un sous-titre à l'autre (`sous_titres.deplacer_la_limite` : mêmes règles et mêmes messages que « Monter le premier mot » et « Descendre le dernier mot ») ; le résultat, ou la raison du refus, s'affiche sous la frise. Échap annule. Un bord séparé de son voisin par un silence ne se glisse pas : il suit le moment des mots, qui ne change jamais.
- Molette : défilement de la frise agrandie (sinon, la page défile) ; Ctrl + molette : zoom autour du pointeur, de toute la pub jusqu'à 24 fois plus large ; une barre de défilement apparaît alors, et la frise suit la lecture.

**Préréglages** (`prereglages.py`, testé sans interface ; fenêtre `ui/dialogues/prereglages.py`) :

- Un préréglage = un nom et la partie « style » d'un projet (onglets Texte, Mots, Animations, Position et Découpage), sous la même forme écrite. Ni le format, ni la plateforme, ni la vidéo d'aperçu.
- Rangement : `%APPDATA%\UGC Studio\prereglages_sous_titres.json` (`version_format`, `par_defaut` : l'identifiant du ★, `prereglages` : identifiant, nom, fourni, style). Noms uniques (« Nom (2) »), 60 caractères au plus.
- **Fournis** (`ressources/prereglages_sous_titres.json`) : les 6 styles de l'annexe B du document V2, faits avec les seuls réglages de l'app ; modifiables, supprimables ; « Rétablir les préréglages fournis » les remet comme à l'origine (sans toucher aux autres, ni au choix du ★). Au premier lancement, ★ sur « Blanc contour noir ».

| Préréglage | Texte | Mots | Animations | Position, découpage |
|---|---|---|---|---|
| Blanc contour noir | Montserrat Extra-grasse, 4,2 %, blanc, contour noir 0,313 % | actif : jaune #FFD43B, 108 % | pop, 180 ms | Centre + 11 % (61 % de la hauteur) |
| Surligneur | Poppins Grasse, 4,1 %, ombre noire à 55 % (flou 0,938 %, 0,313 % vers le bas), 1,875 % entre les mots | actif : fond #7C3AED, marges 0,938 % et 0,156 %, arrondi 1,25 % | zoom, 140 ms | Centre + 11 % |
| Karaoké | Poppins Extra-grasse, 4,1 %, contour noir 0,313 % | actif : #FACC15, 106 % ; déjà dits : #FACC15 | pop, 180 ms, sommet 114 % | Centre + 11 % |
| Mot par mot | Anton, MAJUSCULES, 7,8 %, contour noir 0,469 %, ombre noire à 45 % (flou 1,563 %, 0,938 % vers le bas) | à venir : invisibles | pop, 200 ms : départ 60 % et opacité 0, sommet 112 % | Centre ; 2 mots, 1 ligne |
| Bandeau | Montserrat Grasse, 3,4 %, #111827, fond par ligne blanc (marges 1,875 % et 0,625 %, arrondi 1,563 %), interlignage 152 % | sous-titre fixe | aucune | Centre + 12 % |
| Atténué | Bebas Neue, MAJUSCULES, 6,3 %, 0,078 % entre les lettres, ombre noire à 60 % (flou 0,625 %, 0,313 % vers le bas) | à venir et déjà dits : 45 % ; actif : lueur #F59E0B, 2,188 % | aucune | Centre + 11 % |

- En haut des réglages du studio : « Préréglage » et la liste ; celui du projet est choisi, suivi de « (modifié) » dès que le style du projet s'en écarte (position comprise). Un projet plus ancien affiche « Aucun préréglage » ; un préréglage supprimé depuis, « Nom (supprimé) ». Choisir un préréglage l'applique (la question de la 1.1.0 vient d'abord s'il défait un ajustement fait à la main). « Enregistrer… » : un nouveau préréglage avec le style du projet, qui devient le sien. Menu ⋯ : « Mettre à jour « Nom » avec ce style » (après confirmation : les autres projets gardent leur copie), « Revenir à « Nom » », « Gérer les préréglages… ». Un message sous la liste dit ce qui a été fait. « Rétablir » (onglet Texte) remet les valeurs du préréglage du projet.
- Fenêtre **« Préréglages de sous-titres »** (bouton « Conseils » en haut à droite) : une carte par préréglage, avec sa **vignette animée** (« Mais ce sérum Glowzy a tout changé ! » rejoué en boucle, 20 images par seconde, découpé et dessiné par le moteur de l'aperçu avec les réglages du préréglage, chaque sous-titre centré), son nom (suivi d'une pastille ★ pour celui des nouveaux projets, le sens au survol), sa police (« absente : Inter la remplace » si elle manque), « style du projet », « fourni » ; « Appliquer » (grisé sans projet ouvert) ; menu ⋯ : Dupliquer, Renommer…, Exporter…, « Utiliser pour les nouveaux projets (★) » (ou « Ne plus l'utiliser… »), Supprimer…. En bas : Nouveau (à partir du style de départ), Importer…, Rétablir les préréglages fournis, Fermer.
- **Export** : un fichier `.json` lisible (`type` : `prereglages_sous_titres`, puis le nom et le style de chaque préréglage). **Import** : ajoutés à la liste, avec de nouveaux identifiants et un nom unique ; un fichier illisible est refusé avec un message, sans jamais être modifié ; une police absente de l'ordinateur est signalée (Inter la remplace, le préréglage garde son nom).
- Le projet garde sa **propre copie** du style et retient son préréglage d'origine ; modifier ou supprimer un préréglage ne change pas un projet déjà fait. **Nouveaux projets** : le style du préréglage ★ ; sans ★, le style de départ (§7.10).
- Forme écrite (projet au format 7, numéro inchangé ; un projet de la 1.7.0 n'a pas de préréglage d'origine) : `sous_titres.prereglage`, à côté de `style`, `ecran` et `apercu`.

```json
"prereglage": {"identifiant": "fourni-blanc-contour-noir", "nom": "Blanc contour noir"}
```

**Écarts choisis** (par rapport au document V2) : « Enregistrer… » enregistre directement un nouveau préréglage, et le menu ⋯ n'a donc pas de doublon « Enregistrer comme nouveau » ; l'interface dit « Frise » (le document disait « timeline », mot anglais) ; le ★ du premier lancement est sur « Blanc contour noir » (le document ne le fixait pas).

**Tests** : le service des tests n'a pas de ★ (un nouveau projet y garde le style de départ, sur lequel sont écrits les tests des autres réglages) ; le ★ a ses propres tests.

**Conseils** de la page : rubriques « Préréglages » et « Frise » ; fenêtre « Préréglages de sous-titres » : vignettes, créer et modifier, partager.

**Autotest** : sur le projet de démonstration, qui part du préréglage ★ sans « (modifié) » : la frise (un bloc par sous-titre, un clic sur un bloc le choisit dans la liste, un bord commun glissé d'un mot, capture pendant le glissement, puis le découpage automatique rétabli) ; les 6 préréglages fournis appliqués depuis la liste (une image à la taille de la vidéo, recadrée sur le sous-titre, pendant « Sérum ») ; « (modifié) » après un réglage changé (capture avec la ligne « Préréglage » à l'écran) ; la fenêtre des préréglages et ses vignettes (au milieu de « sérum ») : les 6 cartes visibles sans faire défiler, chaque nom écrit en entier, ★ compris ; puis tout revient comme au début.

---

## 8. Exports

### 8.1 Fichiers de sous-titres

- **SRT** : texte + timecodes (compatible Premiere Pro et la plupart des outils). Respecte le découpage paramétré. Ne contient aucun style. Écrit en UTF-8 **avec BOM** (sans lui, Premiere Pro lit mal les lettres accentuées) et fins de ligne Windows (CRLF) ; temps au format `00:00:01,250` ; blocs séparés par une ligne vide. Nom proposé : celui du projet, dans Documents.
- *(option, pas prévue pour le moment : décision de l'utilisateur du 01/10/2026)* **ASS** : pour d'autres logiciels ; styles simples uniquement.

### 8.2 Overlay transparent

- **MOV + ProRes 4444 avec couche alpha** : uniquement les sous-titres animés sur fond transparent, à poser au-dessus du montage dans Premiere Pro.
- Même résolution et **même fréquence exacte** que la source (sinon décalage progressif).

### 8.3 Vidéo finale (sous-titres incrustés)

La vidéo importée est réencodée avec les sous-titres (une recompression est inévitable dès qu'on modifie les pixels).

**Modes de débit :**
- **Identique à la source** (défaut) : même débit, affiché en Mb/s (avec une petite marge pour compenser la recompression).
- **Débit personnalisé** : valeur saisie en Mb/s.

**Conteneur et codec (choix séparés) :**

| Conteneur | Codecs | Premiere Pro | Usage |
|---|---|---|---|
| MP4 (défaut) | H.264, H.265 | ✅ | Publication, vidéo finale |
| MOV | H.264, H.265, ProRes | ✅ | Montage, overlay transparent |
| MKV | H.264, H.265 | ⚠️ Non compatible | Archivage (avertissement visible) |

- Combinaisons impossibles grisées ; « fond transparent » force MOV + ProRes 4444.
- **Audio copié sans recompression.**
- **Couleurs préservées** : détection du HDR / 10 bits (vidéos iPhone) et conservation des métadonnées de couleur.

### 8.4 Fréquence d'images

- Vidéo importée : reprise **exacte** de la fréquence source, y compris 29,97 / 23,976 / 59,94.
- Sans vidéo (audio seul) : choix manuel, 30 i/s par défaut, 60 ou valeur libre.

### 8.5 Résumé avant export

Fenêtre obligatoire avant chaque export vidéo, comparant **Source** et **Export** :
résolution, fréquence, débit vidéo, codec / conteneur, audio, couleurs (SDR/HDR, profondeur), durée, **taille estimée** (débit × durée).
Toute valeur différente de la source est **surlignée**.

### 8.6 Export audio

WAV (natif) ou MP3 des prises TTS.

---

## 9. Interface (système de design)

Toutes les valeurs ci-dessous sont centralisées dans **un seul fichier de thème** (`ugc_studio/ui/theme.py`). Aucune valeur de taille, couleur ou espacement n'est écrite en dur ailleurs.

### 9.1 Couleurs (thème sombre)

| Rôle | Valeur |
|---|---|
| Fond de l'app | `#0F0F14` |
| Surface (blocs, panneaux) | `#17171F` |
| Surface surélevée (menus, fenêtres) | `#1F1F2A` |
| Bordure neutre | `#2A2A38` |
| **Accent mauve** | `#8B5CF6` |
| Accent survol | `#A78BFA` |
| Accent pressé | `#7C3AED` |
| Texte principal | `#F4F4F8` |
| Texte secondaire | `#A1A1B5` |
| Texte désactivé | `#5C5C70` |
| Succès | `#22C55E` |
| Avertissement (orange) | `#F59E0B` |
| Erreur | `#EF4444` |

Le mauve sert aux contours des éléments clés (champ actif, bloc sélectionné, bouton principal), aux focus et aux repères.
- Bouton principal : contour mauve et fond légèrement teinté de mauve (18 %).
- Élément sélectionné (ex. module actif de la barre latérale) : contour mauve et fond mauve très léger (12 %).

### 9.2 Espacements

Uniquement : **4, 8, 12, 16, 24, 32 px**.

### 9.3 Arrondis

- Boutons, champs, badges : **8 px**
- Blocs, panneaux, fenêtres : **12 px**
- Badges de balises : entièrement arrondis (pastille)

### 9.4 Hauteurs

- Boutons et champs : **36 px** (champs de nombre compris, depuis le lot 2 de la V2 : Qt leur donnait quelques pixels de plus, qui les décalaient des listes posées sur la même ligne)
- Petits boutons (icônes) : 28 px

### 9.4 bis Boutons

- Tous les boutons de l'app sont dessinés par un **composant maison** (`ui/composants/bouton.py`), comme les entrées de la barre latérale : le bouton standard de Qt colle l'icône au texte (≈ 4 px) sans réglage possible.
- L'icône et le texte sont toujours **centrés en hauteur** (le texte est centré sur la hauteur de ses majuscules).
- **Écart icône → texte identique partout** : 12 px (`Dimensions.ECART_ICONE_TEXTE`), dans la barre latérale, les boutons, le bandeau (flèche après le nom du projet) et les menus.
- Icônes : 16 px dans les boutons avec texte et les menus, 20 px dans la barre latérale et les petits boutons-icônes (⋯, lecture).
- **Quatre styles** (depuis la 1.0.2), les mêmes dans toute l'app :
  - **Principal** : fond mauve léger et contour mauve. L'action principale d'une zone (« Générer l'audio », « Transcrire », « Enregistrer »…).
  - **Normal** (dit secondaire) : fond gris clair et contour fin. Les autres actions (« Tester la clé », « Annuler »…).
  - **Contour** : pas de fond, contour gris bien visible. Les outils d'un bloc (« Accentuer », « Prononciation », « Remplacements »…) et les onglets non choisis. Il remplace l'ancien style « discret », sans cadre, qu'on ne reconnaissait pas comme un bouton.
  - **Icône** : carré de 28 px, icône seule, sans fond ni contour (⋯, lecture, favori).
  - Plus le nom du projet dans le bandeau (style « projet »).
- **Sélectionné** (un état, pas un style) : contour mauve et fond mauve très léger, comme le module actif de la barre latérale. Pour l'onglet actif et la lettre de la variante en écoute (fenêtre de comparaison).
- Contour de focus seulement en navigation au clavier (touche Tab).

### 9.4 ter Onglets et infos

- **Onglets en boutons** (`ui/composants/onglets.py`), partout où il y a des onglets (Réglages, Bibliothèque de voix, Prononciation, Remplacements, Variantes) : une ligne de séparation, 16 px d'espace, puis une rangée de boutons ; l'onglet actif a l'allure « sélectionné », les autres le style « contour ». Les onglets standard de Qt, qui soulignaient l'onglet actif d'un trait mauve par-dessus la ligne, ne se créent plus (vérifié par un test). Studio des sous-titres (six onglets, lot 6) : les boutons passent à la ligne quand la colonne des réglages est étroite ; sur une seule rangée, ils imposaient leur largeur à la colonne, et le studio passait sur une colonne dès 1 020 px.
- **Infos avec une ampoule** : chaque phrase d'aide (sous un bloc, un champ ou une case à cocher, en haut d'une fenêtre) commence par l'icône Lucide « lightbulb », à la taille des icônes des boutons (16 px, donc le même trait), dans la couleur du texte secondaire, à 8 px du texte et centrée sur sa première ligne. Sous une case à cocher, l'ampoule tombe sous la case et le texte s'aligne sur celui de la case.
- Pas d'ampoule pour un nom de champ, une donnée (durée, coût, détails d'une voix, « Mot 3 sur 120 »), une traduction, un message d'état (en cours, succès, erreur en rouge), un avertissement orange ni une liste vide (texte « discret »).
- Un seul composant, `info()` de `elements.py` : un test signale toute phrase d'aide grise écrite autrement.

### 9.4 quater Bouton « Conseils »

- Bouton **« Conseils »** (ampoule, style contour) **en haut à droite**, sur la ligne du titre : dans chaque module (Voix, Transcription, Sous-titres, Réglages, avec ou sans projet ouvert) et dans les fenêtres qui ont quelque chose à expliquer : Créer une voix, Style (nouveau ou modifié), Assistant de style, Assistant de description, Bibliothèque de voix, Bibliothèque de styles, Prononciation, Remplacements, Variantes A/B, Comparer les variantes, Ajouter une clé API. Pas de bouton dans les petites fenêtres (nouveau projet, renommer, confirmations).
- Il ouvre la fenêtre « Voix / Conseils » (ou « Créer une voix / Conseils »…) : des rubriques, chacune avec quelques conseils courts, **en français seulement** (seul un exemple de style reste en anglais, puisque c'est ce qui est envoyé à Google). Les textes sont rangés dans `conseils_des_pages.py` ; un test vérifie que chaque bouton ouvre une page qui existe et que chaque page sert.
- Ce qui disparaît : le bloc « Conseils Google pour les styles » sous le script (et son bouton Masquer / Afficher), et la colonne « Conseils Google » en anglais des fenêtres Style et Créer une voix (ces fenêtres passent à 760 px de large). Leur contenu, traduit, est dans les fenêtres « Conseils ».
- Bibliothèque de styles : « Nouveau style » et « Enregistrer le style actuel » passent en bas à gauche, le coin en haut à droite étant pour « Conseils ».
- Les avertissements en direct sous les champs (style trop long, trait permanent…) ne changent pas.

### 9.4 quinquies Listes déroulantes intégrées au champ

- Au clic, la liste s'ouvre **collée sous le champ, de la même largeur**, par-dessus ce qui est dessous (rien ne bouge). Le **choix actuel reste en haut** : c'est le champ lui-même, au contour mauve ; la liste, bordée de mauve elle aussi, montre les **autres choix, décalés vers la droite**, dans leur ordre habituel. Près du bas de l'écran, elle s'ouvre vers le haut.
- **8 choix visibles** au plus (le style « Fusion » de Qt pouvait prendre toute la hauteur de l'écran et posait la liste par-dessus le champ) ; au-delà, une barre de défilement fine (10 px), arrondie et légèrement transparente, et un fondu en haut et en bas de la liste.
- Clavier : ↑ ↓, Entrée, Échap, et une lettre pour sauter au premier choix qui commence par elle.
- Texte trop long, dans le champ fermé comme dans la liste : abrégé par « … » (Qt le coupait au milieu d'une lettre), texte complet au survol. Les séparations (favoris, voix créées, voix de base) restent : une fine ligne.
- Un seul endroit : `liste_deroulante()` (toutes les listes de l'app) et `composants/liste_deroulante.py`. Filet de sécurité : `LISTES_INTEGREES = False` dans `theme.py` remet la liste standard de Qt.

### 9.4 sexies Fondu en haut et en bas

- Quand une page, un onglet, une fenêtre ou une liste défile, un dégradé de **24 px** de la couleur du fond adoucit le bord où du contenu est caché : pas de fondu en haut quand on est tout en haut. Il laisse passer les clics. (`composants/defilement.py`, pour toutes les zones qui défilent.)

### 9.4 septies Tableaux

Suivi des coûts et liste des sous-titres (un seul composant, `composants/tableau.py`) :
1. **Une seule ligne par case** : un texte trop long finit par « … », texte complet au survol. Seule exception : le texte d'un sous-titre sur 2 lignes, qui montre sa vraie mise en page.
2. Quand la place manque, les **colonnes de texte** (projet, modèle, opération, texte, remarque) se resserrent d'abord, jusqu'à 88 px. Les dates, nombres et montants gardent **toujours** leur largeur complète.
3. En dernier recours, une **barre de défilement horizontale** fine apparaît en bas du tableau : aucune colonne n'est jamais cachée sans moyen d'aller la voir. L'autotest vérifie chaque tableau à la plus petite largeur de la fenêtre.
- Suivi des coûts : colonnes « Entrée » et « Sortie » (tokens, détail au survol du titre) au lieu de « Tokens entrée » et « Tokens sortie », pour que le tableau tienne en entier à 960 px, coût compris.
- Modèles et prix (lot 5) : nom, description et capacités du modèle, chacun sur une seule ligne (abrégés par « … », texte complet au survol).

### 9.4 octies Sections repliables et marques (V2)

- **Section repliable** (`composants/section_repliable.py`) : un titre cliquable (flèche vers la droite fermée, vers le bas ouverte ; mauve clair au survol) qui montre ou cache son contenu, décalé sous le texte du titre. Fermée, elle peut afficher un court résumé à côté du titre. Utilisée par le brief du module Script et la fiche « Ce que l'app a compris ».
- **Étiquettes** grises (rôle « etiquette », comme les capacités d'un modèle) : marque « d'après la page » (ou « d'après la voix ») sur un champ rempli par l'app, rôles des répliques d'un script (« Accroche », « Preuve »…).
- Boutons du module Script : principal « Écrire le script » (et « Envoyer dans Voix » sur chaque carte de script ; « Écrire les N scripts », « Retoucher », « Ajouter » dans les fenêtres) ; normal « Lire la page », « Proposer des accroches », « Analyser ce texte », « Variantes… », « Comparer… », « Charger » (bibliothèque de briefs), « Ajouter un script qui a marché… » ; contour « Coller le texte du produit », « Changer la langue du projet », « Prononciation… », « Charger un brief », « Enregistrer », « Mes meilleurs scripts… », « Retoucher… », « Retenir », suggestions de retouche, « Remettre les exemples fournis » ; icône ⋯ et étoiles de la note.
- Une accroche se coche d'un clic n'importe où sur sa ligne : son texte passe à la ligne, ce qu'une case à cocher ne sait pas faire.

### 9.4 nonies Studio des sous-titres (V2, lot 3)

- **Choix en boutons** (`composants/choix.py`) : deux ou trois choix exclusifs côte à côte (Haut, Centre, Bas ; Gauche, Centre, Droite ; Vidéo, Gris, Damier ; Ajusté, 100 %) ; le choix actif a l'allure « sélectionné » des boutons, comme un onglet. Pourquoi : tous les choix restent visibles et se changent d'un clic.
- Aperçu : autour de la vidéo, un fond plus sombre que l'app ; fond neutre gris moyen (un texte blanc ou noir y reste lisible) ; damier de cases de 12 px. Repères : traits de 1 px à l'écran quel que soit le zoom ; zone de sécurité en pointillés mauves (4 px, 4 px), marge maximum en rouge, grille en blanc à 35 %. Couleurs dans `theme.CouleursApercu`.
- Boutons : icône lecture et pause, **boucle** (icône Lucide « repeat », mauve quand elle est active) ; contour « Retrouver la vidéo… », « Choisir une vidéo… » (icône « film »), « Retirer » ; icône « Revenir à 0 % » du réglage fin.
- Largeurs : colonne de l'aperçu 400 px, studio sur deux colonnes à partir de 880 px de large (plus si l'onglet affiché des réglages demande plus de place : 400 px, l'espace, et le minimum des réglages ; sinon le bord droit serait coupé), aperçu de 200 à 540 px de haut.
- **Champ couleur** (lot 4) : sur une ligne, la pastille (carré de la couleur, sur un damier quand elle est transparente ; un clic ouvre le menu), le code, l'opacité et le bouton pipette (icône Lucide « pipette »). Couleurs proposées dans le menu : celles des styles de l'annexe B du document V2.
- **Onglet Texte** (lot 4) : groupes en sections repliables (Police, Taille et casse, Remplissage ouverts au départ) ; un groupe replié montre un résumé (ex. le code de la couleur du contour et son épaisseur) ; « Réglages avancés » replié dans le groupe ; « Rétablir » en bouton contour (icône « rotate-ccw ») ; « Importer une police… » en bouton contour (icône « type ») ; réglages d'un effet décoché grisés, libellés compris.
- Pendant la pipette : curseur en croix sur l'aperçu, et une info sous l'aperçu.
- **Onglet Mots** (lot 5) : « Raccourci » en liste déroulante (« Personnalisé » en tête quand les états ne sont plus ceux d'un raccourci), « État » en choix en boutons, puis les réglages de l'état en grille à trois colonnes : libellé, champ, bouton icône ↺ (« rotate-ccw », infobulle « Comme le texte »), visible seulement pour un réglage changé, dont le libellé passe en mauve (rôle `legende-modifiee`, couleur `ACCENT_SURVOL`). Groupes repliables comme l'onglet Texte (Remplissage et Taille et place ouverts au départ), réglages d'un effet décoché grisés.
- **Onglet Animations** (lot 6) : trois groupes (Mot qui devient actif, Retour à « déjà dit », Sous-titre entier) ; animation, courbe, apparition et disparition en listes déroulantes, durées en millisecondes (± 10 ms aux flèches), retour en choix en boutons (Instantané, Fondu) ; réglages avancés du mot repliés, avec ↺ « Comme l'animation choisie » ; durée et intensité grisées sans animation. Six onglets de réglages : Texte, Mots, Animations, Position, Découpage, Écran.
- **Préréglage** (lot 7) : en haut des réglages, une ligne « Préréglage », la liste (qui s'étire), « Enregistrer… » en bouton contour (icône « save ») et le bouton icône ⋯ (menu : « save », « rotate-ccw », « library »). **Frise** (lot 7) : fond de l'app, blocs arrondis (4 px) en surface surélevée avec contour neutre, choisi : contour mauve de 2 px et fond mauve léger, signalé : orange ; graduations et textes en légende (12 px) ; hauteurs dans `theme.Dimensions` (graduations 18 px, blocs 36 px, mots 12 px), bord saisissable à 6 px près. **Vignettes** (lot 7) : 240 × 108 px, fond neutre gris, coins de 8 px ; cartes de la fenêtre des préréglages en blocs, côte à côte, passant à la ligne, la ligne du nom à la hauteur d'une pastille (cartes alignées avec ou sans ★) ; fenêtre de 880 × 680 px (la hauteur maximale d'une fenêtre de dialogue) : les 6 préréglages fournis s'y voient sans faire défiler, en 2 rangées de 3.
- Les onglets des réglages prennent la hauteur de l'onglet affiché (option `hauteur_selon_l_onglet` des onglets en boutons ; ailleurs, la hauteur reste celle du plus haut) : pas de grand vide sous un onglet court. Une ligne qui ne sert pas disparaît avec son libellé (« Taille » hors format personnalisé), et un message d'état vide ne laisse pas de ligne vide en bas d'un bloc.

### 9.5 Typographie

- Police : **Inter** (embarquée dans l'app)
- Tailles : **12** (légendes), **14** (texte courant), **16** (titres de bloc), **20** (titres de page), **24** (grands chiffres, ex. coût)

### 9.6 Disposition générale

- Barre latérale gauche : Voix, Transcription, Sous-titres, Réglages (icônes + libellés).
- En haut : nom du projet, **compteur de coût de la session** (format §4.4).
- Zone centrale : contenu du module. Titre de page : **« Module / Projet »** (ex. « Voix / Sérum Glowzy ») ; barre de titre de Windows : « UGC Studio / Sérum Glowzy ».
- **Pleine largeur** : les blocs prennent toute la largeur disponible, dans tous les modules (jusqu'à la 1.0.0, les pages étaient bridées à 960 px et calées à gauche : en plein écran, un grand vide restait à droite).
- **Pas de tiret long** (« — ») comme séparateur dans l'interface : « / » entre un module et un projet, ailleurs la ponctuation qui convient (parenthèses, point médian « · », deux-points, virgule). Ex. « Prise 5 (variante C) », « Kore · Ferme · féminine ». Les noms donnés automatiquement par la v1.0.0 (« Prise 5 — variante C ») et le message de test de clé enregistré sont corrigés à la lecture ; un nom choisi à la main ne change jamais. Vérifié par un test.
- **Tout tient dans la largeur minimale de la fenêtre (960 px)** : rien n'est coupé à droite. Les listes déroulantes prennent la largeur de leur plus long choix quand il y a de la place, et rétrécissent sinon (texte abrégé par « … », menu ouvert complet) ; elles se créent toujours avec `liste_deroulante()` (vérifié par un test).
- **Molette de la souris** : faire défiler une page ne change jamais une valeur au passage. Listes déroulantes, champs de nombre et barres de lecture ne réagissent à la molette qu'après un clic dedans ; sinon la page défile. Ils se créent toujours avec `liste_deroulante()`, `champ_entier()`, `champ_decimal()` et `glissiere()` (vérifié par un test).
- Le texte d'une case à cocher ne passe jamais à la ligne : il reste court (48 caractères au plus, vérifié par un test) et l'explication va dessous, en info avec une ampoule, qui passe à la ligne (`case_a_cocher()`). L'autotest vérifie chaque page à cette largeur, et chaque fenêtre de dialogue, puis signale les éléments qui dépassent (ou, si rien n'est encore coupé, les plus larges). Toute erreur inattendue pendant l'autotest le fait échouer.

### 9.7 Valeurs complémentaires

- Également définies dans `theme.py` : largeur de la barre latérale, taille des icônes, petits arrondis de 4 px (cases à cocher, barres de défilement), pastilles d'information de 20 px de haut, taille de la fenêtre au premier lancement (au plus 92 % de l'écran) et taille minimale.
- Icônes : collection **Lucide** (licence ISC, incluse), recolorées avec les couleurs du thème.
- Un test automatique refuse toute couleur, taille ou marge écrite en dur hors de `theme.py`.

---

## 10. Données et sécurité

- Clés API : coffre-fort Windows uniquement (`keyring`). Jamais dans le code, les projets, les logs ni GitHub.
- Dossier de données : `%APPDATA%\UGC Studio\` (styles, préréglages, catalogue de prix, historique des coûts, liste des projets, modèles chargés, exemples de scripts `scripts_exemples.json`, bibliothèque de briefs `briefs.json`, vitesses de parole mesurées `vitesses.json`, polices importées pour les sous-titres `polices\`, préréglages de sous-titres `prereglages_sous_titres.json` ; options d'écriture du module Script retenues dans les préférences).
- Lecture d'une page produit (module Script) : une seule demande, celle de l'utilisateur, avec les en-têtes d'un navigateur ordinaire ; 5 Mo lus au plus ; aucune clé envoyée au site.
- Projets : dossier choisi par l'utilisateur (par défaut `Documents\UGC Studio\Projets\`).
- Journal d'erreurs lisible, accessible depuis Réglages, sans aucune clé API.

---

## 11. Distribution

- Chaque version publiée = une **Release GitHub** avec le `.exe` construit automatiquement (GitHub Actions, machine Windows, PyInstaller).
- Fabrication automatique à chaque envoi de code : tests, fabrication de `UGC-Studio.exe`, démarrage du `.exe` en mode autotest (vérifications, dont la lecture d'une vidéo de test depuis la 1.4.0, + captures d'écran de chaque module), rapport joint au run.
- Le numéro de version est dans `ugc_studio/__init__.py`. Quand il change sur la branche `main`, une Release `v<version>` est publiée automatiquement. Les versions `0.x` (étapes de la V1) sont marquées « pré-version ».
- Les polices (Inter pour l'interface ; Montserrat, Poppins, Anton et Bebas Neue pour les sous-titres, avec leurs licences) et le décodeur audio/vidéo (FFmpeg, fourni avec Qt Multimedia) sont inclus dans l'app : rien à installer. FFmpeg en ligne de commande, en version GPL, sera ajouté avec les exports vidéo (V3 ; façon de l'inclure : §13).
- *(plus tard)* Installateur qui crée l'icône sur le bureau et dans le menu Démarrer.

---

## 12. Découpage en versions

### V1 : socle utilisable
- Réglages : connexions API (Google), test de clé, catalogue de prix, taux de change, suivi et historique des coûts, affichage `0.00`+`71`.
- Architecture d'adaptateurs + tableau de capacités (adaptateur Google seul).
- Voix : éditeur avec badges de balises, dictionnaire de prononciation, variantes, **Voice Design** (création de voix + conseils Google), assistant de style avec conseils Google, répliques et styles, voix de base + bibliothèque filtrable, bibliothèque de styles personnalisés, génération, prises, export WAV/MP3.
- Transcription : import vidéo/audio, extraction audio, transcription mot par mot, langue, séparation des voix, dictionnaire de remplacements, masquage des hésitations, éditeur de transcription.
- Lien « prise TTS → sous-titres » avec alignement sur le script.
- Sous-titres : règles de découpage complètes (§7.3), export **SRT**.
- Projets (sauvegarde/réouverture).
- Thème sombre complet (§9).
- Build `.exe` automatique via GitHub Actions.

#### 12.1 Étapes de réalisation de la V1

Chaque étape est publiée (Pull Request + Release avec le `.exe`) dès qu'elle est prête ; la suivante démarre sans attendre de validation.

| Étape | Version | Contenu |
|---|---|---|
| 1. Socle | 0.1.0 | Structure du code, thème sombre (§9), fenêtre principale, police Inter, journal d'erreurs, stockage JSON, fabrication automatique du `.exe` |
| 2. Réglages & API | 0.2.0 | Connexions API (coffre-fort Windows), test de clé, adaptateurs + tableau de capacités, catalogue de prix, taux de change, suivi et historique des coûts |
| 3. Projets + Voix de base | 0.3.0 | Projets, éditeur de script avec badges de balises, voix de base, génération, prises, export WAV/MP3, estimation du coût |
| 4. Voix : styles | 0.4.0 | Répliques, styles et assistant, traduction FR → EN, conseils Google, bibliothèque de styles, dictionnaire de prononciation, accentuation |
| 5. Voix : bibliothèque | 0.5.0 | Bibliothèque étendue filtrable, favoris, écoute d'extraits, Voice Design |
| 6. Voix : variantes | 0.6.0 | Variantes A/B (2 modes), écoute comparative, écoute pendant la génération |
| 7. Transcription | 0.7.0 | Import, extraction de la piste son (FFmpeg via Qt), transcription mot par mot, options, éditeur |
| 8. Sous-titres | 0.8.0 | Prise TTS → sous-titres (alignement sur le script), découpage §7.3, export SRT |
| V1 complète | 1.0.0 | Finitions (la molette de la souris ne change plus une valeur en faisant défiler une page ; réglages des sous-titres plus lisibles) et Release définitive |

**État** : V1 terminée le 30/09/2026 (Release v1.0.0). V1.1 (retouches de l'interface, §12.2) terminée le 01/10/2026 (Release v1.1.0). V2 (§12.3) terminée le 01/10/2026 (Release v2.0.0) : lots 1 et 2 (module Script), versions 1.2.0 et 1.3.0 ; lot 3 (studio), version 1.4.0 ; lot 4 (style du texte), version 1.5.0 ; lot 5 (mots), version 1.6.0 ; lot 6 (animations), version 1.7.0 ; lot 7 (frise et préréglages), version 2.0.0.

#### 12.2 V1.1 : retouches de l'interface

Demandes de l'utilisateur du 30/09/2026, réécrites et validées dans le document « UGC Studio - V1.1.0 Retouches interface » (projet ECOM BUILDR). Réalisées en lots ; chaque lot est publié (Pull Request + Release) pour être testé au fur et à mesure.

| Lot | Version | Contenu |
|---|---|---|
| 1 | 1.0.1 | Titres « Module / Projet », plus de tiret long, « Voix et modèle », « Générer l'audio », « Tout en majuscules », sous-titre « Balises », balises en français (nom anglais au survol et envoyé à Google), pastilles centrées à l'œil, crayon à la place de la baguette magique, pages en pleine largeur, identifiant du modèle au survol |
| 2 | 1.0.2 | Quatre styles de boutons, onglets en boutons, infos avec une ampoule |
| 3 | 1.0.3 | Bouton « Conseils » et fenêtres de conseils (modules et fenêtres), en français |
| 4 | 1.0.4 | Fondu en haut et en bas, listes déroulantes intégrées au champ, bibliothèque de voix plus rapide, tableaux quand la fenêtre rétrécit |
| 5 | 1.0.5 | Modèles chargés, fenêtre « Choisir les modèles », colonne « Utilisé dans » |
| 6 | 1.1.0 | Réorganisation des sous-titres à la main (monter, descendre, couper, fusionner, rétablir), mêmes règles que le découpage automatique, question avant un réglage qui défait un ajustement ; format de projet 5 |

Coins arrondis de la fenêtre : non pour le moment (Windows 10 dessine des coins carrés ; les arrondir demanderait de redessiner toute la barre de titre, avec un vrai risque de bugs).

### V2 : Studio de style et module Script
- Module Script (§4 bis) : aide à l'écriture avec un modèle de texte, envoi dans le module Voix.
- Style du texte complet (§7.4), mot actif (§7.5), préréglages de style (§7.6).
- Aperçu vidéo fidèle avec zones de sécurité et timeline (§7.7).
- Formats vidéo (§7.1).

#### 12.3 V2 : lots

Demande de l'utilisateur du 01/10/2026, réécrite et validée dans le document « UGC Studio - V2 Studio de style et Script » (projet ECOM BUILDR ; réponses : oui à toutes les questions). Même méthode que la V1.1 : une branche et une Pull Request par lot, fabrication automatique verte, captures relues, fusion et Release, puis le lot suivant sans attendre de validation.

| Lot | Version | Contenu | État |
|---|---|---|---|
| 1 | 1.2.0 | **Script (1)** : page Script, lecture de la page produit (app, Shopify, Google, texte collé), fiche comprise, brief, accroches, écriture, relecture, durée estimée, exemples (« Garder comme exemple », 5 scripts fournis), envoi dans Voix, coûts ; modèles de texte reconnus, Gemini 3.1 Pro au catalogue ; projet au format 6 | Fait |
| 2 | 1.3.0 | **Script (2)** : variantes (3 modes), comparaison, retouche, copie, ★ et « Retenir », bibliothèque de briefs, fenêtre « Mes meilleurs scripts », vitesse mesurée sur les prises (aussi pour Voix), accroches envoyées en variantes de voix, nombres dits à la belge ou à la suisse ; champs de nombre à la hauteur des autres champs | Fait |
| 3 | 1.4.0 | **Studio (1)** : moteur de dessin commun, aperçu fidèle (vidéo, fond neutre, damier, zoom, boucle), repères, formats dont personnalisé, position verticale et alignement, sous-titre glissé dans l'aperçu, vidéo d'aperçu pour un projet sans vidéo, « Retrouver la vidéo… » ; projet au format 7 (§7.9) | Fait |
| 4 | 1.5.0 | **Studio (2)** : style du texte complet (polices fournies, de Windows et importées ; graisse, casse, couleurs avec opacité, dégradés, pipette, contour, ombre, lueur, fond par mot, par ligne ou en bloc, espaces), découpage mesuré avec le style, style de départ des nouveaux projets (§7.10) | Fait |
| 5 | 1.6.0 | **Studio (3)** : mots : raccourcis, trois états (à venir, actif, déjà dits) entièrement réglables, fond qui glisse, mots accentués du script, avance de l'allumage ; agrandissement compté dans la place (§7.11) | Fait |
| 6 | 1.7.0 | **Studio (4)** : animations du mot actif, retour à « déjà dit », apparition et disparition du sous-titre ; sommet compté dans la place (§7.12) | Fait |
| 7 | 2.0.0 | **Studio (5)** : frise (bords de mot en mot, double-clic, zoom), préréglages (liste du studio et « (modifié) », fenêtre, vignettes animées, les 6 styles fournis, ★ des nouveaux projets, nouveau, export et import), finitions (§7.13) | Fait |

Style par personne (pubs à deux voix) : reporté à la V3. Vidéo qui contient une prise (caler les mots transcrits sur le script) : à décider plus tard (02/10/2026).

### V3 : exports vidéo
Priorité de l'utilisateur (02/10/2026) : exporter la vidéo et les sous-titres d'une vidéo ou d'un audio **terminés**, importés dans l'app. L'assemblage de la voix et de la vidéo reste dans Premiere Pro pour le moment : une vidéo sans son y est montée avec la voix, puis réimportée dans l'app, qui refait ses sous-titres à partir d'elle.
- FFmpeg en ligne de commande, version GPL (x264, x265) (§2).
- Overlay transparent MOV ProRes 4444 (§8.2).
- Vidéo finale incrustée, choix débit / conteneur / codec, HDR (§8.3, §8.4).
- Résumé avant export (§8.5).
- Style par personne (pubs à deux voix), reporté de la V2 (§12.3).
- Pas prévus pour le moment : assemblage de la voix et d'une vidéo dans l'app (Premiere Pro s'en charge) ; export ASS (§8.1). À décider plus tard : vidéo qui contient une prise (§12.3).

### V4 : voix avancées et fournisseurs
- Voice Replication (avec consentement), multi-voix.
- Adaptateurs OpenAI, ElevenLabs, Anthropic.
- Installateur Windows.

---

## 13. Points ouverts

- Liste définitive des **catégories de pub** et de leur ton (l'utilisateur les créera dans la bibliothèque de styles ; quelques exemples fournis par défaut).
- Disponibilité de voix avec un vrai **accent flamand** (à vérifier ; sinon création avec Voice Design).
- Syntaxe exacte des API au moment du code (la doc évolue vite : toujours vérifier la doc officielle avant d'écrire un adaptateur). Les prix de Gemini 3.5 Transcribe sont connus depuis la v1.9 (§4.2).
- **Zones de sécurité** par plateforme : documentées au §7.8 (TikTok, Meta et YouTube d'après leurs guides ; Snapchat à confirmer). TikTok : la réserve à droite sous le milieu de l'écran (300 px d'après une ancienne note, 140 px sur toute la hauteur d'après des sources de 2026) n'est pas appliquée tant que le modèle officiel n'a pas été relu (lot 3, §7.8).
- **Lecture de pages par Google avec Gemini 3.8 Flash** (module Script) : les deux pages de Google sur l'outil « URL context » ne listaient pas les mêmes modèles (01/10/2026). Si Google refuse l'outil pour un modèle, l'app essaie un autre modèle chargé qui sait lire les pages, sinon propose de coller le texte. À confirmer au premier vrai essai.
- **Qualité des scripts** : consignes et exemples s'affineront avec les retours de l'utilisateur sur de vrais produits (lot 2).
- **FFmpeg (V3)** : version GPL précise (proposée : 9.0.2 « essentials » de gyan.dev, l'une des deux sources Windows indiquées par ffmpeg.org) et façon de l'inclure : dans le `.exe` (environ 100 Mo de plus, à décompresser à chaque lancement) ou téléchargé une seule fois au premier export (vérifié par son empreinte SHA-256). À trancher dans le document V3.
- **Durée de conservation des voix créées** (Voice Design) : la documentation officielle « Voice Design » indique 1 an et 200 voix par projet ; le guide « Get_Started_Voices » indique 7 jours. L'app affiche la date renvoyée par Google (`expire_time`).

---

## 14. Règles de travail pour le développement

- L'utilisateur débute : **expliquer le pourquoi** de chaque étape et de chaque choix, sans jargon non expliqué.
- Modifications de code présentées de façon ciblée (ce qui change et pourquoi), pas en remplaçant des fichiers entiers sans explication.
- Corriger la **cause** d'un problème plutôt que le contourner.
- Aucune action demandant un terminal à l'utilisateur.
- Mettre à jour ce document quand une décision change.
- Une étape = une branche + une **Pull Request** dont la description explique ce qui change et pourquoi. Quand la fabrication automatique est verte, Claude fusionne la PR, la Release est publiée, et l'étape suivante démarre **sans attendre la validation** de l'utilisateur, qui teste quand il est disponible et signale les problèmes.
- **Tests d'interface** (lot 5) : après chaque test, les fenêtres qu'il a ouvertes sont vraiment supprimées (`tests/conftest.py`), et un fichier de police n'est déclaré à Qt qu'une fois par lancement (`ui/polices.py`, `declarer_police`). Sans cela, les fenêtres des tests précédents restaient en mémoire et chaque préparation de l'app les repeignait toutes, avec une copie de plus des polices : la série ralentissait au fil des tests (415 s au lot 3, 1 290 s au lot 4, plus de 1 900 s au lot 5).
