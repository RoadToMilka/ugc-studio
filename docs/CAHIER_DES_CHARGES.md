# UGC Studio — Cahier des charges

> Version du document : 1.6 — 29/09/2026 (plan de réalisation de la V1 en 8 étapes, précisions montants, design et distribution)
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
| Audio / vidéo | FFmpeg (embarqué dans l'app) | Extraction audio, lecture des infos source, encodage |
| Rendu des sous-titres | Dessin image par image en Python (Qt QPainter), puis assemblage par FFmpeg | Contrôle total du design ; aperçu identique à l'export |
| Stockage des clés API | Coffre-fort Windows via la bibliothèque `keyring` | Clés chiffrées, jamais dans un fichier ni sur GitHub |
| Données locales | Fichiers JSON dans `%APPDATA%\UGC Studio\` | Styles, préréglages, projets, historique des coûts |
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

### 3.3 Lien TTS → sous-titres

Le TTS ne renvoie pas le timing des mots. Chaîne prévue :
1. l'audio généré passe automatiquement dans le STT (horodatage mot par mot) ;
2. le texte transcrit est **aligné sur le script d'origine** (connu exactement), pour corriger les erreurs de transcription ;
3. le résultat arrive dans le Studio sous-titres.

Bouton unique : **« Créer les sous-titres de cette prise »**.

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
| `stt` | Gemini 3.5 Transcribe |
| `stt_mots_horodates` | horodatage par mot (obligatoire pour l'animation) |
| `stt_vocabulaire` | vocabulaire personnalisé |
| `texte` | génération de script (V2) |

L'app **croise** « modèles disponibles avec tes clés » × « capacités requises par la tâche » : un menu déroulant ne montre que les modèles compatibles. Un modèle STT sans horodatage par mot est affiché mais marqué « incompatible avec l'animation ». Les options d'interface non supportées par le modèle choisi sont grisées (ex. palette de balises).

Ajouter un fournisseur = écrire un nouvel adaptateur ; le reste de l'app ne change pas.

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

### 4.2 Catalogue des modèles et prix

- Liste des modèles connus avec leurs capacités.
- **Prix modifiables** par modèle : entrée et sortie, en $ par million de tokens (les tarifs changent — ex. Gemini 3.8 Flash TTS doublera au 01/01/2027).
- Valeurs par défaut V1 (à vérifier au moment du code) :
  - `gemini-3.8-flash-tts` : 0,50 $ / M tokens texte entrée — 9,00 $ / M tokens audio sortie
  - `gemini-3.8-flash-lite-tts` : 0,50 $ / 6,00 $
  - `gemini-3.5-transcribe` : prix à vérifier dans la doc officielle au moment du code
- **Taux de change USD → EUR** modifiable (champ manuel ; mise à jour automatique optionnelle plus tard).

### 4.3 Suivi des coûts

- Chaque appel API enregistre : date, projet, modèle, tokens entrée, tokens sortie, coût € (calculé avec les compteurs de tokens renvoyés par l'API).
- **Pendant une tâche** : affichage en temps réel des tokens et du coût.
- Historique filtrable par jour / mois / projet / modèle, avec totaux.
- Limite : l'app compte **ce qu'elle a consommé** ; elle ne connaît pas le solde du compte Google.

### 4.4 Affichage des montants

Format imposé : `0.000 €` (3 décimales minimum)
- partie entière + 1re décimale en taille normale ;
- 2e et 3e décimales en **plus petit** (≈ 70 % de la taille) ;
- ex. `0.0` + `07` €. Composant réutilisable `MontantLabel`.
- Un montant non nul qui s'afficherait `0.000 €` (ex. 0.0004 € pour un essai de voix) reçoit des décimales supplémentaires jusqu'au premier chiffre utile (6 au maximum) : `0.0` + `004` €. Un coût réel n'apparaît jamais comme gratuit.
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

- **Dictionnaire de prononciation (mots de marque)** : l'API n'a pas de paramètre dédié aux noms de marque. L'app garde donc une liste « mot écrit → façon de le prononcer » (ex. « Glowzy » → « Glo-zi »). Au moment de générer, **seul le texte envoyé au TTS** est remplacé ; le script affiché et les sous-titres gardent l'orthographe correcte (grâce à l'alignement sur le script, §3.3). Bouton ▶ pour tester la prononciation d'un mot seul (coût minime). Dictionnaires globaux ou par projet.
- **Aide à l'accentuation** : bouton « Accentuer » qui met le mot sélectionné en MAJUSCULES (le modèle appuie sur les mots en capitales). Ces majuscules n'impactent pas les sous-titres (le texte des sous-titres est géré séparément, cf. §7.2).
- Compteur de caractères et **estimation du coût** avant génération.

### 5.3 Découpage en répliques

- Le script peut être découpé en **répliques** (blocs). Chaque réplique a son propre champ **style** (optionnel) — utile quand l'émotion change en cours de pub (ex. hook énergique → témoignage calme).
- Le style de réplique est envoyé dans `speech_metadata.style`.

### 5.4 Choix de la voix

- **Voix de base** (30 voix Google) avec leur caractère (Puck — Upbeat, Kore — Firm, Leda — Youthful…).
- **Bibliothèque étendue** interrogée via l'API (`voices.list`) avec **filtres** : langue, accent, genre, hauteur (grave/moyenne/aiguë), persona, contexte d'usage, recherche texte.
- Bouton **▶ écouter** un extrait pour chaque voix (génération d'une phrase test, coût affiché).
- **Favoris** de voix.
- *(V4)* Voice Replication (clonage à partir de 30 s, **uniquement avec l'accord de la personne**).

### 5.4 bis Voice Design — créer ses voix (V1)

Création de voix personnalisées **dans l'app** (API `POST /v1beta/voices`, `type: "prompted"`), sans passer par Google AI Studio.

- Champs : nom, langue, genre, modèle (Flash TTS ou Flash-Lite TTS), **description**.
- **Assistant de description structurée** : champs guidés (âge, genre, timbre, texture de voix, accent régional, persona / rôle) assemblés automatiquement en 1–2 phrases, modifiables ensuite en texte libre. Ex. : « Jeune femme d'environ 25 ans, française, voix légèrement voilée, spontanée et complice, comme si elle parlait à une amie face caméra. »
- Google renvoie un **extrait audio** → écoute immédiate → garder ou ajuster la description et recommencer.
- Gestion : liste, réécoute (`voices.get` renvoie l'extrait), renommage, suppression, **date d'expiration** affichée (conservation 1 an), compteur **x / 200 voix**.
- Les voix créées dans Google AI Studio (même projet) apparaissent aussi dans l'app.
- Coût éventuel de création : à vérifier au moment du code ; affiché s'il existe.

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

Les styles sont liés à un fournisseur (chaque fournisseur a sa propre syntaxe).

**Assistant de style structuré** : style = *émotion / attitude* + *rythme / prosodie* (optionnel), ex. « chaleureux et enthousiaste, débit rapide », « chuchoté, complice ». Champs guidés assemblés en une consigne courte, modifiable en texte libre.

**Panneau « Conseils Google »** (visible dans l'éditeur de styles et à côté du champ style des répliques) :
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
- Les exemples et conseils Google sont affichés **en anglais d'origine**, avec leur traduction française.
- Le texte du script (ce que la voix prononce) reste bien sûr dans la langue du projet.

### 5.6 Génération et prises

- Bouton **Générer** → lecture immédiate dans l'app.
- Chaque génération = une **prise** conservée dans le projet (horodatée, avec voix/style/coût utilisés).
- Comparer, renommer, noter (★), supprimer les prises.
- Export audio : **WAV 24 kHz mono** (sortie native) ; option MP3.
- **Variantes** (tests A/B de pubs) : générer plusieurs versions d'un même script en un seul lancement.
  - **Mode « mêmes réglages »** : N générations identiques ; le modèle varie naturellement l'interprétation → on garde la meilleure prise.
  - **Mode « réglages par variante »** : tableau où chaque colonne est une variante. Tout part des réglages de base ; pour chaque variante on modifie seulement ce qu'on veut comparer (voix, style, modèle, consigne d'une réplique, balises). Les valeurs modifiées sont surlignées en mauve pour voir d'un coup d'œil ce qui change.
  - Bouton « dupliquer la variante » pour créer une variante voisine avec un petit changement.
  - Coût total estimé affiché avant le lancement.
  - Écoute comparative : lecture enchaînée ou bascule instantanée A/B au même moment du texte ; note ★ et choix de la variante retenue.
  - Chaque variante devient une prise normale (§5.6).
- **Écoute pendant la génération** (streaming) : option pour entendre le début avant la fin du calcul.

### 5.6 bis Limites du modèle (doc officielle)

- Entrée max : **8 192 tokens** de texte ; sortie max : **16 384 tokens** audio. Un script trop long est découpé automatiquement en répliques, générées puis recollées.
- Multi-voix dans une seule requête : 2 voix de base maximum ; avec des voix personnalisées, une requête par réplique puis assemblage (V4).
- **Mode de traitement** : Standard uniquement. Le mode *Batch* (gros lots de variantes, résultats différés) pourra être ajouté plus tard si besoin ; *Flex* et *Priority* ne sont pas retenus.
- Formats de sortie possibles : WAV (défaut), PCM brut, mu-law, A-law, fréquence réglable. L'app garde WAV 24 kHz.
- Pas d'horodatage des mots en sortie : d'où la chaîne TTS → STT (§3.3).
- Bouton **« Créer les sous-titres de cette prise »** (cf. §3.3).

### 5.7 Langue

- Français par défaut ; sélecteur de langue par projet : anglais (US), anglais (UK), espagnol (Espagne), italien, néerlandais (Belgique), néerlandais (Pays-Bas), allemand.
- La langue filtre la bibliothèque de voix.

---

## 6. Module Transcription (STT)

### 6.1 Modèle V1

`gemini-3.5-transcribe` avec **horodatage mot par mot activé** (limite : 30 min par requête — largement suffisant pour des pubs).

### 6.2 Entrée

- Glisser-déposer ou bouton : vidéo (MP4, MOV, MKV…) ou audio (WAV, MP3, M4A…).
- Extraction automatique de la piste son via FFmpeg.
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
- Formats acceptés par l'API : WAV, MP3, AIFF, AAC, OGG, FLAC, M4A, Opus, WebM… La vidéo n'est pas acceptée : l'app extrait toujours l'audio avec FFmpeg (en FLAC ou WAV, sans perte) avant l'envoi.
- Envoi via l'API Files (fichier téléversé puis référencé).

### 6.4 Éditeur de transcription

- Texte affiché mot par mot, synchronisé avec la lecture (le mot en cours est surligné).
- Clic sur un mot → la lecture saute à ce moment.
- Corriger l'orthographe d'un mot sans perdre son timing ; fusionner / couper des mots ; ajuster finement début/fin d'un mot.
- Le horodatage par mot dégrade légèrement la précision : l'édition manuelle est prévue pour ça.

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

---

## 8. Exports

### 8.1 Fichiers de sous-titres

- **SRT** : texte + timecodes (compatible Premiere Pro et la plupart des outils). Respecte le découpage paramétré. Ne contient aucun style.
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

### 9.5 Typographie

- Police : **Inter** (embarquée dans l'app)
- Tailles : **12** (légendes), **14** (texte courant), **16** (titres de bloc), **20** (titres de page), **24** (grands chiffres, ex. coût)

### 9.6 Disposition générale

- Barre latérale gauche : Voix, Transcription, Sous-titres, Réglages (icônes + libellés).
- En haut : nom du projet, **compteur de coût de la session** (format §4.4).
- Zone centrale : contenu du module.

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
- FFmpeg et la police Inter sont inclus dans l'app : rien à installer.
- *(plus tard)* Installateur qui crée l'icône sur le bureau et dans le menu Démarrer.

---

## 12. Découpage en versions

### V1 — Socle utilisable
- Réglages : connexions API (Google), test de clé, catalogue de prix, taux de change, suivi et historique des coûts, affichage `0.0`+`07`.
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
| 7. Transcription | 0.7.0 | Import, extraction FFmpeg, transcription mot par mot, options, éditeur |
| 8. Sous-titres | 0.8.0 | Prise TTS → sous-titres (alignement sur le script), découpage §7.3, export SRT |
| V1 complète | 1.0.0 | Finitions et Release définitive |

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
- **Prix exacts** de Gemini 3.5 Transcribe et syntaxe exacte des API au moment du code (la doc évolue vite — toujours vérifier la doc officielle avant d'écrire un adaptateur).
- Valeurs précises des **zones de sécurité** par plateforme (à documenter au moment de la V2).

---

## 14. Règles de travail pour le développement

- L'utilisateur débute : **expliquer le pourquoi** de chaque étape et de chaque choix, sans jargon non expliqué.
- Modifications de code présentées de façon ciblée (ce qui change et pourquoi), pas en remplaçant des fichiers entiers sans explication.
- Corriger la **cause** d'un problème plutôt que le contourner.
- Aucune action demandant un terminal à l'utilisateur.
- Mettre à jour ce document quand une décision change.
- Une étape = une branche + une **Pull Request** dont la description explique ce qui change et pourquoi. Quand la fabrication automatique est verte, Claude fusionne la PR, la Release est publiée, et l'étape suivante démarre **sans attendre la validation** de l'utilisateur, qui teste quand il est disponible et signale les problèmes.
