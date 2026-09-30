# UGC Studio — Cahier des charges

> Version du document : 3.0 — 30/09/2026 (V1 complète, version 1.0.0 ; molette de la souris, §9.6)
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
| Audio / vidéo | FFmpeg : pour la V1, celui de Qt Multimedia (déjà inclus avec Qt) ; FFmpeg en ligne de commande ajouté pour les exports vidéo (V3) | Extraction audio et lecture des infos source (V1), encodage (V3). Passer par Qt évite d'alourdir le `.exe` d'environ 80 Mo tant qu'on n'encode pas de vidéo |
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

1. **Voix (TTS)** — script, voix, styles, balises, génération, historique des prises.
2. **Transcription (STT)** — import vidéo/audio, extraction du son, transcription mot par mot, correction.
3. **Studio sous-titres** — découpage, style, mot actif, aperçu, export.
4. **Réglages** — connexions API, catalogue des modèles et prix, taux de change, suivi des coûts, préférences.
5. *(V2)* **Script** — aide à l'écriture de scripts UGC avec un modèle de texte (Claude, GPT, Gemini…).

### 3.2 Notion de Projet

Un **Projet** = un dossier qui regroupe tout : script, prises audio, vidéo source (référence), transcription, style de sous-titres, réglages d'export. Rouvrir un projet restaure l'état complet.

- Contenu du dossier : `projet.json` (nom, langue, réglages de voix, répliques du script avec leur style, dictionnaire de prononciation du projet, liste des prises et séries de variantes, transcription et dictionnaire de remplacements du projet, réglages des sous-titres), `prises\prise-001.wav`, `prise-002.wav`… et `sources\audio.wav` (piste son de la source transcrite, ou de la prise dont on a créé les sous-titres).
- Format du fichier : version 4 depuis l'étape 8 (réglages des sous-titres ; un projet plus ancien s'ouvre avec les réglages par défaut). Version 3 depuis l'étape 7 (transcription). Version 2 depuis l'étape 4 (script en répliques) ; un projet de l'étape 3 (un seul script, un seul style) est converti à l'ouverture en une seule réplique.
- Enregistrement **automatique** (moins d'une seconde après chaque modification, et à la fermeture de l'app).
- Menu **Projet** en cliquant sur le nom du projet dans le bandeau : nouveau projet, ouvrir un projet, projets récents (10 retenus), ouvrir le dossier du projet.
- Au démarrage, le dernier projet utilisé est rouvert automatiquement.

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

**V1 : adaptateur Google uniquement.** Fournisseurs prévus ensuite : OpenAI, ElevenLabs, Anthropic (texte uniquement — pas de TTS/STT chez Anthropic).

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

- Liste des modèles connus avec leurs capacités.
- **Prix par défaut = tarifs officiels de Google** ([page des tarifs](https://ai.google.dev/gemini-api/docs/pricing?hl=fr), tarif « Standard » du niveau payant), vérifiés le 30/09/2026, en $ par million de tokens :

| Modèle | Entrée | Sortie | Ordre de grandeur (Google) |
|---|---|---|---|
| `gemini-3.8-flash-tts` | 0,50 $ (texte) | 9,00 $ (audio) | 0,00225 $ pour 10 s d'audio |
| `gemini-3.8-flash-lite-tts` | 0,50 $ | 6,00 $ | |
| `gemini-3.5-transcribe` | 2,00 $ (audio) | 12,00 $ (texte) | ≈ 0,005 $ par minute transcrite |
| `gemini-3.8-flash` (texte : traduction des styles) | 0,75 $ | 3,75 $ | réflexion comprise en sortie |
| `gemini-3.1-flash-tts-preview` | 1,00 $ | 20,00 $ | ancienne génération |
| `gemini-2.5-pro-preview-tts` | 1,00 $ | 20,00 $ | ancienne génération |
| `gemini-2.5-flash-preview-tts` | 0,50 $ | 10,00 $ | ancienne génération |

- **Changements de prix annoncés** : Google double les prix des modèles 3.8 **à partir du 01/01/2027** (Flash TTS : 1,00 $ / 18,00 $ ; Flash-Lite TTS : 1,00 $ / 12,00 $ ; Flash : 1,50 $ / 7,50 $). Chaque modèle a donc une liste de tarifs datés ; l'app applique **automatiquement** le tarif en vigueur le jour de l'appel et affiche le prochain changement sous le modèle.
- **Prix modifiables** par modèle (entrée et sortie). Un prix saisi à la main est signalé (« Prix modifié à la main », avec le tarif Google) et s'applique jusqu'au prochain changement de tarif annoncé par Google : l'information la plus récente l'emporte.
- **Ordre de grandeur en euros** sous chaque prix : coût d'une minute de voix (≈ 250 tokens de texte + 60 s × 25 tokens audio) ou d'une minute transcrite (60 s × 25 tokens audio + ≈ 175 tokens de texte), d'après les chiffres de la page des tarifs.
- Modèles listés : les modèles principaux (3.8 Flash TTS, 3.8 Flash-Lite TTS, 3.5 Transcribe, 3.8 Flash pour les traductions) toujours ; les anciennes générations et les modèles inconnus seulement s'ils sont accessibles avec une clé. Les anciennes générations de voix n'ont ni balises ni Voice Design (doc officielle). Les modèles « Live » (temps réel, ex. `gemini-3.5-transcribe-live`) utilisent une autre API et ne sont jamais proposés.
- **Niveau gratuit** de Google (clé sans moyen de paiement) : ces modèles n'y sont pas facturés (limites d'usage plus basses). L'app affiche quand même le coût au tarif payant ; une note le rappelle.
- Bouton « Page des tarifs Google » pour vérifier les prix.
- **Taux de change USD → EUR** modifiable (champ manuel), ou récupéré en un clic auprès de la Banque centrale européenne (taux de référence du jour). Valeur de départ : 0,86, signalée « à vérifier ».
- Prix et taux rangés dans `prix.json` (seuls les prix modifiés y sont écrits ; bouton « Rétablir les prix par défaut »).

### 4.3 Suivi des coûts

- Chaque appel API enregistre : date, projet, modèle, tokens entrée, tokens sortie, coût € (calculé avec les compteurs de tokens renvoyés par l'API).
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

## 5. Module Voix (TTS)

### 5.1 Modèles V1

- `gemini-3.8-flash-tts` (par défaut — qualité et jeu d'acteur maximum)
- `gemini-3.8-flash-lite-tts` (rapide, moins cher)

### 5.2 Éditeur de script

- Grand champ de texte.
- **Insertion de balises à la position du curseur** : on clique dans le texte, puis sur une balise de la palette.
- Les balises s'affichent comme des **badges colorés** (pastille arrondie) ; le texte envoyé à l'API contient la vraie balise (`<laugh>`).
- Un badge se supprime comme un caractère (retour arrière) et se déplace par couper/coller.
- **Couleur par famille** :

| Famille | Balises |
|---|---|
| Pauses | `<short pause>` `<long pause>` |
| Rires | `<laugh>` `<laughter>` `<giggle>` `<chuckle>` `<chuckles>` `<snicker>` `<cackle>` |
| Souffle | `<breath>` `<heavy breath>` `<exhales>` `<sigh>` `<sighs>` `<phew>` `<pff>` `<pant>` `<yawn>` |
| Réactions | `<gasp>` `<cheer>` `<shout>` `<scream>` `<shriek>` `<argh>` `<groan>` `<grunt>` `<tsk>` `<snort>` |
| Voix | `<whispers>` `<whispering>` `<throat-clearing>` `<cough>` `<sneeze>` |
| Émotions fortes | `<cry>` `<sob>` `<whimper>` `<moan>` `<growl>` `<grr>` `<hiss>` |

(Liste issue de la doc officielle Gemini TTS ; les balises restent en anglais même pour un texte français.)

- **Dictionnaire de prononciation (mots de marque)** : l'API n'a pas de paramètre dédié aux noms de marque. L'app garde donc une liste « mot écrit → façon de le prononcer » (ex. « Glowzy » → « Glo-zi »). Au moment de générer, **seul le texte envoyé au TTS** est remplacé ; le script affiché et les sous-titres gardent l'orthographe correcte (grâce à l'alignement sur le script, §3.3). Bouton ▶ pour tester la prononciation d'un mot seul (coût minime, noté « essai de prononciation » ; l'audio est gardé en cache). Dictionnaires globaux (`prononciations.json`) ou par projet ; pour un même mot, celui du projet l'emporte.
  - Remplacement : mots entiers, sans tenir compte des majuscules ; le mot le plus long d'abord (« Glowzy Pro » avant « Glowzy ») ; les balises ne sont jamais modifiées.
  - Fenêtre « Prononciation » (bouton sous le script) : deux onglets, « Ce projet » et « Tous les projets ».
- **Aide à l'accentuation** : bouton « Accentuer » qui met le mot sélectionné en MAJUSCULES (le modèle appuie sur les mots en capitales). Ces majuscules n'impactent pas les sous-titres (le texte des sous-titres est géré séparément, cf. §7.2).
- Compteur de caractères et **estimation du coût** avant génération : tokens d'entrée ≈ caractères ÷ 4 ; durée d'après le nombre de mots (≈ 160 mots/min) et les pauses ; tokens audio ≈ durée × tokens par seconde. Ce dernier chiffre (25 au départ, d'après la page des tarifs de Google) est **ajusté automatiquement** après chaque génération avec les vrais nombres renvoyés par Google.
- Affichage d'un mot accentué : en MAJUSCULES et en mauve dans l'éditeur ; l'écriture d'origine est conservée pour les sous-titres.
- Copier/coller : entre éditeurs de l'app, badges et accents sont conservés ; un texte collé depuis un autre logiciel voit ses balises `<laugh>`… transformées en badges.

### 5.3 Découpage en répliques

- Le script peut être découpé en **répliques** (blocs). Chaque réplique a son propre champ **style** (optionnel) — utile quand l'émotion change en cours de pub (ex. hook énergique → témoignage calme).
- Le style de réplique est envoyé dans `speech_metadata.style`.
- Toutes les répliques partent **dans la même requête** (une entrée de texte par réplique, chacune avec son style) : une seule prise. Si le total dépasse les limites du modèle (§5.6 bis), les répliques sont réparties sur plusieurs requêtes, puis les audios sont recollés.
- Interface : les répliques s'affichent l'une sous l'autre (« Réplique 1 », « Réplique 2 »…), chacune avec son champ style et son éditeur à badges, qui grandit avec le texte. Bouton « Ajouter une réplique » ; menu ⋯ de chaque réplique : **Découper ici** (la fin de la réplique, après le curseur, devient une nouvelle réplique avec le même style), Monter, Descendre, Supprimer. La palette de balises et « Accentuer » agissent sur la dernière réplique utilisée.
- Chaque prise retient le texte et le style envoyés pour chaque réplique ; la liste des prises indique « N répliques » quand il y en a plusieurs.

### 5.4 Choix de la voix

- **Voix de base** (30 voix Google) avec leur caractère (Puck — Upbeat, Kore — Firm, Leda — Youthful…).
- **Bibliothèque étendue** interrogée via l'API (`voices.list`) avec **filtres** : langue, accent, genre, hauteur (grave/moyenne/aiguë), persona, contexte d'usage, recherche texte.
  - Requête : `GET /v1beta/voices?page_size=1000&type=prebuilt` (pages suivantes avec `page_token`). La bibliothèque (plusieurs centaines de voix) est gardée une semaine dans `voix.json` ; bouton « Actualiser ».
  - Les filtres agissent dans l'app, instantanément ; au départ, la langue du projet est choisie. Au plus 100 lignes affichées (au-delà : « affine les filtres »).
  - Fenêtre « Bibliothèque de voix » (bouton 📚 à côté de la liste des voix) : onglets « Voix Google » et « Mes voix » ; chaque voix s'écoute (▶) et se choisit en un clic.
- Bouton **▶ écouter** un extrait pour chaque voix. Voix créées et voix de la bibliothèque étendue : l'extrait fourni par Google (`GET /v1beta/voices/{id}`, gratuit) s'il existe. 30 voix de base (elles parlent toutes les langues) : une phrase d'exemple générée dans la langue du projet, coût noté « essai de voix ». Chaque extrait est gardé en cache.
- **Favoris** de voix (★) : en tête de la liste des voix de l'atelier (puis les voix créées, puis les 30 voix de base) et filtre « Favoris seulement » dans la bibliothèque.
- Choisir une voix créée choisit aussi le modèle avec lequel elle a été créée.
- *(V4)* Voice Replication (clonage à partir de 30 s, **uniquement avec l'accord de la personne**).

### 5.4 bis Voice Design — créer ses voix (V1)

Création de voix personnalisées **dans l'app** (API `POST /v1beta/voices`, `type: "prompted"`), sans passer par Google AI Studio.

- Champs : nom, langue, genre, modèle (Flash TTS ou Flash-Lite TTS), **description**.
- **Assistant de description structurée** : champs guidés (âge, genre, timbre, texture de voix, accent régional, persona / rôle) assemblés automatiquement en 1–2 phrases, modifiables ensuite en texte libre. Ex. : « Jeune femme d'environ 25 ans, française, voix légèrement voilée, spontanée et complice, comme si elle parlait à une amie face caméra. »
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

**Panneau « Conseils Google »** (toujours visible à côté du formulaire) :
- Mettre ici les **traits permanents** : âge, genre, timbre, texture vocale, accent régional.
- Description **courte et précise : 1 à 2 phrases**.
- Éviter les paragraphes longs et les descriptions **contradictoires**.
- L'émotion et le jeu se règlent ensuite avec des styles courts, pas dans la description.

**Vérifications en direct** : avertissement au-delà de 2 phrases / ~40 mots.

### 5.5 Bibliothèque de styles personnalisés

Un **style** enregistré contient :
- nom, catégorie (UGC témoignage, unboxing, placement influenceur, hook, pub classique… — catégories libres, créables par l'utilisateur) ;
- fournisseur + modèle ;
- voix ;
- consigne de style (courte — voir conseils ci-dessous) ;
- balises par défaut éventuelles ;
- langue.

Actions : créer, modifier, dupliquer, supprimer, **appliquer en un clic**. Quelques exemples fournis au départ (modifiables/supprimables).
- Rangement : `styles.json` dans le dossier de données de l'app.
- Accès : bouton 📚 à côté du champ style de chaque réplique. « Appliquer » met la consigne (et sa traduction) sur la réplique, et choisit la voix et le modèle du style. « Enregistrer le style actuel » crée un style à partir de celui de la réplique.
- Fenêtre de création / modification : nom, catégorie (liste modifiable), modèle, voix, langue, style (avec assistant et traduction), balises souvent utilisées (noms de la palette, vérifiés), et le panneau « Conseils Google » à côté.

Les styles sont liés à un fournisseur (chaque fournisseur a sa propre syntaxe).

**Assistant de style structuré** : style = *émotion / attitude* + *rythme / prosodie* (optionnel), ex. « chaleureux et enthousiaste, débit rapide », « chuchoté, complice ». Champs guidés assemblés en une consigne courte, modifiable en texte libre.

**Panneau « Conseils Google »** (visible dans l'éditeur de styles et sous le script, repliable — le choix est retenu) :
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
- Les exemples et conseils Google sont affichés **en anglais d'origine**, avec leur traduction française.
- Le texte du script (ce que la voix prononce) reste bien sûr dans la langue du projet.

### 5.6 Génération et prises

- Bouton **Générer** → lecture immédiate dans l'app.
- Chaque génération = une **prise** conservée dans le projet (horodatée, avec voix/style/coût utilisés).
- Comparer, renommer, noter (★), supprimer les prises.
- Export audio : **WAV 24 kHz mono** (sortie native) ; option MP3 (encodeur LAME, 192 kb/s).
- Appel technique (Gemini 3.8 TTS) : API **Interactions** (`POST /v1beta/interactions`) — texte dans `input` (avec l'annotation `speech_metadata.style` quand un style est donné), voix dans `generation_config.speech_config`. Réponse : WAV 24 kHz mono en base64, et nombres de tokens (`usage`) pour le coût.
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
  - Bouton **« Variantes… »** à côté de « Générer la voix ». Fenêtre à deux onglets :
    - « Mêmes réglages » : de 2 à 6 variantes (lettres A à F) ;
    - « Réglages par variante » : colonne « Réglages de base » (ceux de l'atelier), puis une colonne par variante (2 au départ, A et B, identiques à la base). Lignes : modèle, voix, puis pour chaque réplique son style et son texte (sous chaque texte : menu « Balise » par famille et « Accentuer »). Choisir une voix créée choisit aussi son modèle, comme dans l'atelier. Icônes « Dupliquer la variante » et « Supprimer » (au moins 2 variantes) en tête de colonne, « Ajouter » à droite.
    - En bas : coût total estimé (prix de chaque modèle, dictionnaire de prononciation compris) et « Générer les N variantes ».
  - Génération : les variantes partent **l'une après l'autre** (pour rester sous les limites de débit de Google). Chacune devient une prise « Prise N — variante B », marquée de sa série (`serie`, `variante` dans `projet.json`). Bouton « Arrêter » pendant la série : elle s'arrête après la variante en cours. Si une variante échoue, la série s'arrête ; les variantes déjà prêtes sont gardées.
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

---

## 6. Module Transcription (STT)

### 6.1 Modèle V1

`gemini-3.5-transcribe` avec **horodatage mot par mot activé** (limite : 30 min par requête — largement suffisant pour des pubs).

### 6.2 Entrée

- Glisser-déposer ou bouton : vidéo (MP4, MOV, MKV…) ou audio (WAV, MP3, M4A…).
- Extraction automatique de la piste son (décodage par FFmpeg, à travers Qt Multimedia).
- Lecture des infos de la source (résolution, fps exacts, débit, codec, couleurs/HDR, durée) — réutilisées pour l'export.

### 6.3 Options

**Incompatibilités officielles de l'API (doc Google, sept. 2026) — elles dictent la conception :**
- l'horodatage par mot (`timestamp_granularities: ["word"]`) ne fonctionne qu'en mode **verbatim** ;
- il est **incompatible avec le vocabulaire personnalisé** (`custom_vocabulary`) ;
- le mode **smart** est incompatible avec l'horodatage et avec la séparation des voix ;
- la séparation des voix (`diarization_mode: "speaker"`) est incompatible avec le vocabulaire personnalisé.

Comme les sous-titres animés exigent l'horodatage par mot, l'app propose :

- **Langue** : détection auto ou langue forcée (`language_codes`, recommandé pour les vidéos courtes).
- **Séparation des voix** (jusqu'à 8 personnes, fiable jusqu'à 2 ; au-delà expérimental) : chaque mot reçoit un locuteur (`spk_1`, `spk_2`…). Utile pour une pub à deux personnes : style de sous-titre différent par personne (V2).
- **Dictionnaire de remplacements** (local, gratuit) : « sérum anti rides » → « Sérum Anti-Rides® », appliqué automatiquement après chaque transcription. Dictionnaires globaux ou par projet.
- **Correction manuelle** de n'importe quel mot dans l'éditeur (§6.4) — solution principale pour les erreurs ponctuelles.
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

- Préréglages : **9:16** (TikTok, Reels, Snap, Shorts), **4:5** (fil Facebook/Instagram), **3:4**, **1:1**, **16:9**, **personnalisé** (largeur × hauteur).
- Si une vidéo est importée, son format est repris automatiquement.
- Toutes les tailles et positions sont exprimées **en proportion de la hauteur de la vidéo** : un style garde le même aspect quel que soit le format.

### 7.2 Texte affiché

- Le texte des sous-titres est distinct du texte TTS (pas de balises, pas de majuscules d'accentuation).
- Option **TOUT EN MAJUSCULES** (affichage uniquement).
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

- Police : choix parmi les polices installées sur Windows + import de fichiers `.ttf` / `.otf` ; graisse.
- Taille (proportionnelle à la hauteur vidéo).
- Couleur du texte.
- **Contour** : oui/non, couleur, épaisseur.
- **Ombre** : oui/non, couleur, opacité, flou, décalage X/Y.
- **Fond** derrière le sous-titre : oui/non, couleur, opacité, marge intérieure, arrondi.
- Interlignage, espacement des lettres.
- Position verticale (haut / centre / bas + réglage fin), alignement.

### 7.5 Mot actif (mot en cours de prononciation)

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

### 7.7 Aperçu

- Lecteur vidéo (ou fond neutre si audio seul) avec les sous-titres rendus **exactement comme à l'export** (même moteur de dessin).
- Repères activables : zone de sécurité (pointillés mauves), marge maximum (rouge), grille.
- Choix de la plateforme pour la zone de sécurité.
- Timeline des sous-titres : blocs déplaçables/redimensionnables, sous-titres signalés en orange (cf. §7.3), édition du texte au double-clic.

### 7.8 Mise en œuvre (étape 8)

Page **Sous-titres** : mots des sous-titres (transcription du projet, ou « Créer les sous-titres » d'une prise, §3.3 ; « Corriger les mots » ouvre le module Transcription), réglages, liste des sous-titres, écoute, export SRT. Les sous-titres sont recalculés à chaque changement de réglage (`sous_titres.py`, testé sans interface) ; seuls les réglages sont enregistrés dans le projet.

**Réglages par défaut** : 24 caractères (espaces comprises) et 5 mots au plus par sous-titre, 2 lignes au plus, coupe de préférence après la ponctuation, durée minimale 0,6 s ; ponctuation affichée, pas de majuscules, hésitations masquées (réglage partagé avec la transcription) ; format « celui de la vidéo » (sinon 9:16), zone de sécurité TikTok, marge maximum 5 %, texte à 4 % de la hauteur de la vidéo.

**Texte affiché (§7.2)** : sans les hésitations masquées ; une ponctuation transcrite à part rejoint son mot ; ponctuation masquée = retirée autour des mots (gardée à l'intérieur : « l'huile », « anti-rides », « 3.5 ») ; typographie : en français, espace insécable avant « ! ? ; : » (pas dans « 10:30 ») et à l'intérieur des guillemets « », dans les autres langues pas d'espace avant ; jamais d'espace avant « , . … ». TOUT EN MAJUSCULES à la fin. Les temps des mots ne changent jamais.

**Découpage (§7.3)** :
- Un sous-titre se termine toujours : après une fin de phrase (« . ! ? … », si « couper sur la ponctuation » est coché), à un changement de personne, ou après un silence de plus de 0,8 s.
- Caractères et mots : deux maximums (un mot plus long que la limite de caractères reste seul) ; un mot n'est jamais coupé.
- Parmi tous les découpages possibles, l'app retient le meilleur (programmation dynamique) : des sous-titres bien remplis et de longueurs proches (l'écart au maximum de caractères compte au carré), qui finissent si possible sur une ponctuation (bonus), en restant de préférence dans la zone de sécurité (petite pénalité pour la marge).

**Écran (§7.3)** : la largeur de chaque ligne est mesurée en pixels par Qt, avec la police Inter SemiBold (celle de l'app, en attendant le style complet de la V2) à la taille du texte (en % de la hauteur de la vidéo).
- Formats : celui de la vidéo importée (dimensions remises à l'endroit pour une vidéo de téléphone enregistrée « couchée », rotation de 90°), sinon 9:16 (1080 × 1920), 4:5 (1080 × 1350), 3:4 (1080 × 1440), 1:1 (1080 × 1080), 16:9 (1920 × 1080). Le format personnalisé arrive en V2.
- Ordre : une ligne dans la zone de sécurité ; sinon deux lignes équilibrées dans la zone (si 2 lignes permises ; retour à la ligne de préférence après une ponctuation) ; sinon la même chose jusqu'à la marge maximum ; sinon le sous-titre est redécoupé (aucune taille ne change). Un mot seul trop large est rapetissé jusqu'à tenir dans la marge maximum, sans descendre sous 60 % de la taille du texte : il est signalé en orange (liste des sous-titres et aperçu), avec le conseil de le raccourcir s'il ne tient toujours pas.
- Sous-titres centrés : la zone de sécurité retient le plus large des deux côtés (ex. YouTube Shorts : 10 % des deux côtés). Si elle est plus large que la zone de la marge maximum, c'est la marge maximum qui compte.

**Zones de sécurité (écran 9:16, en part des bords)** :

| Plateforme | Gauche | Droite | Haut | Bas | Source |
|---|---|---|---|---|---|
| TikTok | 11,1 % (120 px) | 11,1 % (120 px) | 12,5 % | 34,4 % | Modèle de zone de sécurité de TikTok Ads (avril 2025) ; à droite, 300 px sous le milieu de l'écran (boutons) : utilisé avec la position verticale (V2) |
| Instagram, Facebook (Reels, Stories) | 6 % | 6 % | 14 % | 35 % | Guide des publicités Meta |
| YouTube Shorts | 0 % | 10 % | 10 % | 25 % | Google Ads, emplacement Shorts |
| Snapchat | 3,7 % (40 px) | 3,7 % | 10,4 % | 19,3 % | Valeurs courantes, non confirmées par Snapchat |
| Aucune | — | — | — | — | Marge maximum seulement |

Seuls les côtés servent en V1 (largeur des lignes) ; le haut et le bas serviront à placer les sous-titres (V2).

**Temps** : un sous-titre va du début de son premier mot à la fin du dernier ; s'il dure moins que la durée minimale, il est prolongé jusqu'au sous-titre suivant au plus (et jusqu'à la fin de l'audio pour le dernier), puis avancé jusqu'au précédent au plus ; un trou de 0,3 s au plus entre deux sous-titres est comblé (pas de clignotement).

**Liste et écoute** : numéro, temps, texte (lignes comprises), remarque ; les sous-titres signalés sont en orange. Pendant l'écoute, le sous-titre en cours est surligné et affiché en grand (aperçu simple ; l'aperçu fidèle sur la vidéo arrive en V2). Clic sur un sous-titre : il est montré, et la lecture s'y place si elle est en cours (sinon « ▶ » part de lui). Changer de module arrête la lecture de la page quittée (et libère la piste son).

---

## 8. Exports

### 8.1 Fichiers de sous-titres

- **SRT** : texte + timecodes (compatible Premiere Pro et la plupart des outils). Respecte le découpage paramétré. Ne contient aucun style. Écrit en UTF-8 **avec BOM** (sans lui, Premiere Pro lit mal les lettres accentuées) et fins de ligne Windows (CRLF) ; temps au format `00:00:01,250` ; blocs séparés par une ligne vide. Nom proposé : celui du projet, dans Documents.
- *(option)* **ASS** : pour d'autres logiciels ; styles simples uniquement.

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

- Boutons et champs : **36 px**
- Petits boutons (icônes) : 28 px

### 9.4 bis Boutons

- Tous les boutons de l'app sont dessinés par un **composant maison** (`ui/composants/bouton.py`), comme les entrées de la barre latérale : le bouton standard de Qt colle l'icône au texte (≈ 4 px) sans réglage possible.
- L'icône et le texte sont toujours **centrés en hauteur** (le texte est centré sur la hauteur de ses majuscules).
- **Écart icône → texte identique partout** : 12 px (`Dimensions.ECART_ICONE_TEXTE`), dans la barre latérale, les boutons, le bandeau (flèche après le nom du projet) et les menus.
- Icônes : 16 px dans les boutons avec texte et les menus, 20 px dans la barre latérale et les petits boutons-icônes (⋯, lecture).
- Variantes : normal, principal (contour mauve), discret (sans cadre), icône (carré de 28 px), projet (nom du projet dans le bandeau). Contour de focus seulement en navigation au clavier (touche Tab).

### 9.5 Typographie

- Police : **Inter** (embarquée dans l'app)
- Tailles : **12** (légendes), **14** (texte courant), **16** (titres de bloc), **20** (titres de page), **24** (grands chiffres, ex. coût)

### 9.6 Disposition générale

- Barre latérale gauche : Voix, Transcription, Sous-titres, Réglages (icônes + libellés).
- En haut : nom du projet, **compteur de coût de la session** (format §4.4).
- Zone centrale : contenu du module.
- **Tout tient dans la largeur minimale de la fenêtre (960 px)** : rien n'est coupé à droite. Les listes déroulantes prennent la largeur de leur plus long choix quand il y a de la place, et rétrécissent sinon (texte abrégé par « … », menu ouvert complet) ; elles se créent toujours avec `liste_deroulante()` (vérifié par un test).
- **Molette de la souris** : faire défiler une page ne change jamais une valeur au passage. Listes déroulantes, champs de nombre et barres de lecture ne réagissent à la molette qu'après un clic dedans ; sinon la page défile. Ils se créent toujours avec `liste_deroulante()`, `champ_entier()`, `champ_decimal()` et `glissiere()` (vérifié par un test).
- Le texte d'une case à cocher ne passe jamais à la ligne : il reste court (48 caractères au plus, vérifié par un test) et l'explication va dans une légende dessous, qui passe à la ligne (`case_a_cocher()`). L'autotest vérifie chaque page à cette largeur, et chaque fenêtre de dialogue, puis signale les éléments qui dépassent (ou, si rien n'est encore coupé, les plus larges). Toute erreur inattendue pendant l'autotest le fait échouer.

### 9.7 Valeurs complémentaires

- Également définies dans `theme.py` : largeur de la barre latérale, taille des icônes, petits arrondis de 4 px (cases à cocher, barres de défilement), pastilles d'information de 20 px de haut, taille de la fenêtre au premier lancement (au plus 92 % de l'écran) et taille minimale.
- Icônes : collection **Lucide** (licence ISC, incluse), recolorées avec les couleurs du thème.
- Un test automatique refuse toute couleur, taille ou marge écrite en dur hors de `theme.py`.

---

## 10. Données et sécurité

- Clés API : coffre-fort Windows uniquement (`keyring`). Jamais dans le code, les projets, les logs ni GitHub.
- Dossier de données : `%APPDATA%\UGC Studio\` (styles, préréglages, catalogue de prix, historique des coûts, liste des projets).
- Projets : dossier choisi par l'utilisateur (par défaut `Documents\UGC Studio\Projets\`).
- Journal d'erreurs lisible, accessible depuis Réglages, sans aucune clé API.

---

## 11. Distribution

- Chaque version publiée = une **Release GitHub** avec le `.exe` construit automatiquement (GitHub Actions, machine Windows, PyInstaller).
- Fabrication automatique à chaque envoi de code : tests, fabrication de `UGC-Studio.exe`, démarrage du `.exe` en mode autotest (vérifications + captures d'écran de chaque module), rapport joint au run.
- Le numéro de version est dans `ugc_studio/__init__.py`. Quand il change sur la branche `main`, une Release `v<version>` est publiée automatiquement. Les versions `0.x` (étapes de la V1) sont marquées « pré-version ».
- La police Inter et le décodeur audio/vidéo (FFmpeg, fourni avec Qt Multimedia) sont inclus dans l'app : rien à installer. FFmpeg en ligne de commande sera ajouté avec les exports vidéo (V3).
- *(plus tard)* Installateur qui crée l'icône sur le bureau et dans le menu Démarrer.

---

## 12. Découpage en versions

### V1 — Socle utilisable
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

**État** : V1 terminée le 30/09/2026 (Release v1.0.0). Suite prévue : V2 — Studio de style.

### V2 — Studio de style
- Style du texte complet (§7.4), mot actif (§7.5), préréglages de style (§7.6).
- Aperçu vidéo fidèle avec zones de sécurité et timeline (§7.7).
- Formats vidéo (§7.1).
- Module Script (aide à l'écriture avec un modèle de texte).

### V3 — Exports vidéo
- Overlay transparent MOV ProRes 4444 (§8.2).
- Vidéo finale incrustée, choix débit / conteneur / codec, HDR (§8.3, §8.4).
- Résumé avant export (§8.5).

### V4 — Voix avancées et fournisseurs
- Voice Replication (avec consentement), multi-voix.
- Adaptateurs OpenAI, ElevenLabs, Anthropic.
- Installateur Windows.

---

## 13. Points ouverts

- Liste définitive des **catégories de pub** et de leur ton (l'utilisateur les créera dans la bibliothèque de styles ; quelques exemples fournis par défaut).
- Disponibilité de voix avec un vrai **accent flamand** (à vérifier ; sinon création avec Voice Design).
- Syntaxe exacte des API au moment du code (la doc évolue vite — toujours vérifier la doc officielle avant d'écrire un adaptateur). Les prix de Gemini 3.5 Transcribe sont connus depuis la v1.9 (§4.2).
- **Zones de sécurité** par plateforme : documentées au §7.8 (TikTok, Meta et YouTube d'après leurs guides ; Snapchat à confirmer). À revoir avec la position verticale des sous-titres (V2) : la zone de TikTok s'élargit à droite sous le milieu de l'écran.
- **Durée de conservation des voix créées** (Voice Design) : la documentation officielle « Voice Design » indique 1 an et 200 voix par projet ; le guide « Get_Started_Voices » indique 7 jours. L'app affiche la date renvoyée par Google (`expire_time`).

---

## 14. Règles de travail pour le développement

- L'utilisateur débute : **expliquer le pourquoi** de chaque étape et de chaque choix, sans jargon non expliqué.
- Modifications de code présentées de façon ciblée (ce qui change et pourquoi), pas en remplaçant des fichiers entiers sans explication.
- Corriger la **cause** d'un problème plutôt que le contourner.
- Aucune action demandant un terminal à l'utilisateur.
- Mettre à jour ce document quand une décision change.
- Une étape = une branche + une **Pull Request** dont la description explique ce qui change et pourquoi. Quand la fabrication automatique est verte, Claude fusionne la PR, la Release est publiée, et l'étape suivante démarre **sans attendre la validation** de l'utilisateur, qui teste quand il est disponible et signale les problèmes.
