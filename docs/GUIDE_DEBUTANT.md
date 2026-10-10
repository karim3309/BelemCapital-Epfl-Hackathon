# Guide pour grands débutants : comprendre notre projet sans rien connaître à la blockchain

> **Pour qui ?** Pour nous trois, en partant de zéro.
> **Comment le lire ?** Dans l'ordre, chapitre par chapitre. Chaque mot technique est expliqué la première fois qu'il apparaît, et il est aussi dans le **glossaire** à la fin.
> **Temps de lecture :** environ 1 heure (45 min pour les chapitres 1-12, 15 min pour le risque et le front). Prenez votre temps : tout le reste du projet repose là-dessus.

---

## Sommaire
1. [La blockchain, c'est quoi ?](#1-la-blockchain-cest-quoi-)
2. [Les jetons (tokens) : de l'argent numérique](#2-les-jetons-tokens--de-largent-numérique)
3. [Les « smart contracts » : des distributeurs automatiques](#3-les-smart-contracts--des-distributeurs-automatiques)
4. [Les dollars numériques : USDC et USDe](#4-les-dollars-numériques--usdc-et-usde)
5. [Faire fructifier son argent : sUSDe, la tirelire](#5-faire-fructifier-son-argent--susde-la-tirelire)
6. [Pendle et le PT : le bon du Trésor numérique](#6-pendle-et-le-pt--le-bon-du-trésor-numérique)
7. [Emprunter avec Morpho : le prêteur sur gages](#7-emprunter-avec-morpho--le-prêteur-sur-gages)
8. [L'oracle : l'expert qui estime la valeur du gage](#8-loracle--lexpert-qui-estime-la-valeur-du-gage)
9. [La position A racontée comme une histoire](#9-la-position-a-racontée-comme-une-histoire)
10. [Les dépendances : un jeu de dominos](#10-les-dépendances--un-jeu-de-dominos)
11. [Notre mission : jouer les détectives](#11-notre-mission--jouer-les-détectives)
12. [Lire notre fichier graph.json sans paniquer](#12-lire-notre-fichier-graphjson-sans-paniquer)
13. [Comment on mesure le risque](#13-comment-on-mesure-le-risque)
14. [Comment lire le front](#14-comment-lire-le-front)
15. [Glossaire](#15-glossaire)
16. [Petit quiz pour vérifier qu'on a compris](#16-petit-quiz-pour-vérifier-quon-a-compris)

---

## 1. La blockchain, c'est quoi ?

### L'image à retenir : un grand cahier de comptes public
Imaginez un **cahier de comptes géant** où l'on note toutes les opérations : « Alice donne 10 € à Bob », « Bob donne 3 € à Chloé »…

Dans une banque classique, ce cahier est **privé** : seule la banque l'a, et il faut lui faire confiance.

Dans une **blockchain**, ce cahier est :
- **public** : tout le monde peut le lire, à tout moment, gratuitement ;
- **copié** sur des milliers d'ordinateurs dans le monde : personne ne peut le falsifier seul ;
- **ineffaçable** : ce qui est écrit reste écrit.

### Pourquoi « chaîne de blocs » ?
On n'écrit pas les opérations une par une. On les regroupe par **pages**, qu'on appelle des **blocs**. Sur **Ethereum** (la blockchain qu'on utilise), une nouvelle page s'ajoute **toutes les 12 secondes** environ. Chaque page porte un **numéro** et est collée à la précédente : c'est la « chaîne ».

> 💡 **Pourquoi c'est important pour nous :** quand on lit des informations, on dit « **au bloc n° 26 162 087** ». C'est comme dire « d’après la page 26 162 087 du cahier », ou encore comme prendre une **photo** à un instant précis. Toutes nos données viennent de la même photo, donc elles sont cohérentes entre elles et n'importe qui peut les revérifier.

### Ethereum
Il existe plusieurs blockchains. **Ethereum** est la plus utilisée pour la finance. Dans notre projet, tout se passe sur le « mainnet » d'Ethereum (le vrai réseau, avec de vrais euros… enfin de vrais dollars, on va voir).
- **mainnet** = le réseau réel (≠ réseaux de test)
- **chain ID = 1** = le numéro d'identification d'Ethereum mainnet. Notre programme vérifie qu'il parle bien au réseau n° 1.

### Une adresse
Sur la blockchain, tout le monde et tout programme a une **adresse**. C'est comme un numéro de compte (IBAN), mais qui ressemble à ça :
```
0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
```
C'est long, illisible, et une seule lettre fausse renvoie ailleurs. **C'est pour ça qu'on ne recopie jamais une adresse de mémoire** : on la lit sur une source officielle et on la vérifie.

### Comment on « lit » la blockchain ? (RPC)
Notre programme n'a pas sa propre copie du cahier : elle est énorme. Il pose ses questions à un serveur qui en a une copie. Ce serveur s'appelle un **nœud**, et le « guichet » pour lui poser des questions s'appelle un **RPC**.
> Analogie : le RPC, c'est le **guichet de la bibliothèque**. On demande « que dit la page X sur tel sujet ? », et le bibliothécaire va lire et nous répond.

**Lire est gratuit.** Écrire (faire une opération) coûte des frais. Notre projet ne fait **que lire**.

---

## 2. Les jetons (tokens) : de l'argent numérique

Un **jeton** (en anglais *token*) est une **ligne dans le cahier** qui dit « telle adresse possède tant d'unités de tel jeton ». Il y a des milliers de jetons différents : des dollars numériques, des parts de placement, des reconnaissances de dette…

Tous les jetons qui suivent la même « norme » se comportent pareil. La norme la plus courante s'appelle **ERC-20**. C'est comme une **prise électrique standard** : n'importe quelle application sait brancher n'importe quel jeton ERC-20.

Un jeton ERC-20 sait toujours répondre à quelques questions de base :
| Question | Exemple de réponse |
|---|---|
| `symbol()` : comment tu t'appelles ? | « USDC » |
| `decimals()` : combien de chiffres après la virgule ? | 6 |
| `totalSupply()` : combien en existe-t-il au total ? | 48 milliards |
| `balanceOf(adresse)` : combien en possède cette adresse ? | 1 000 |

> 💡 **Les décimales, piège classique :** la blockchain ne connaît pas les virgules. Elle stocke des nombres entiers. Avec 6 décimales, « 1 USDC » est stocké comme `1000000`. Notre programme fait la conversion pour vous.

---

## 3. Les « smart contracts » : des distributeurs automatiques

Un **smart contract** (contrat intelligent) est un **programme posé sur la blockchain**. Il a une adresse, comme une personne, et il fonctionne tout seul selon des règles écrites à l'avance.

> **L'image à retenir : le distributeur de boissons.** Vous mettez 2 €, vous appuyez sur B4, et la canette tombe. Personne ne décide : la machine applique ses règles. Et vous pouvez lire sur la vitre combien de canettes il reste.

Les jetons eux-mêmes sont des smart contracts. Les plateformes de prêt, d'échange, de placement… aussi. Tout ce qu'on étudie est fait de smart contracts qui se parlent entre eux.

### Comment on interroge un contrat ?
On appelle une de ses **fonctions de lecture**. Par exemple, on demande au contrat du PT « qui est ton SY ? » en appelant `SY()`, et il répond par une adresse.

Si on appelle une fonction qui **n'existe pas** chez ce contrat, il refuse (on dit qu'il « **revert** »). Ce refus nous est très utile : en essayant plusieurs fonctions, on devine **ce qu'est** un contrat inconnu. C'est ce qu'on appelle **sonder** un contrat.
> Analogie : vous trouvez une machine inconnue. Vous appuyez sur « café » : rien. Sur « billet de train » : un billet sort. Vous savez maintenant que c'est un distributeur de billets.

### DeFi
**DeFi** = *Decentralized Finance* = la finance faite avec des smart contracts, sans banque : prêter, emprunter, placer, échanger. C'est le sujet du hackathon.

---

## 4. Les dollars numériques : USDC et USDe

Sur la blockchain, le prix des cryptomonnaies (comme l'ETH) bouge beaucoup. On a donc créé des jetons qui **valent toujours environ 1 dollar** : les **stablecoins** (« pièces stables »).

### USDC : le dollar « classique »
- Il est émis par une **entreprise américaine, Circle**.
- Pour chaque USDC en circulation, Circle garde **1 vrai dollar** en banque (ou en bons du Trésor).
- **Analogie :** un **ticket de vestiaire**. Vous déposez 1 $, vous recevez un ticket ; vous rendez le ticket, vous récupérez votre dollar.
- **Risque :** il faut faire confiance à Circle, qui peut aussi bloquer des comptes ou modifier son contrat (notre programme a d'ailleurs détecté que le contrat USDC est **modifiable** par Circle, un « proxy upgradeable »).

### USDe : le dollar « fabriqué » par Ethena
L'USDe est plus subtil. **Ethena** ne garde pas des dollars en banque. Elle garde des **cryptomonnaies** (de l'ETH, du bitcoin…) et elle **parie contre elles en même temps**, du même montant.

> **L'image à retenir : le parapluie et la crème solaire.** Vous vendez des parapluies et de la crème solaire. S'il pleut, vous gagnez sur les parapluies et perdez sur la crème ; s'il fait beau, c'est l'inverse. **Au total, votre caisse ne bouge pas, quelle que soit la météo.**
>
> Ethena fait pareil : elle **possède** 1 ETH et **parie** que l'ETH va baisser, du même montant. Si l'ETH monte, elle gagne sur l'un et perd sur l'autre. Au total, la valeur reste stable, environ 1 dollar par USDe.

**Mots à connaître :**
- **couverture (hedge)** : le pari inverse qui neutralise les variations ;
- **contrats perpétuels (« perps »)** : l'outil de pari, qui se trouve sur des **plateformes d'échange centralisées** (« exchanges ») comme Binance, Bybit, OKX… ;
- **custodians** (gardiens) : des entreprises qui **gardent** les cryptos d'Ethena en sécurité, comme un coffre-fort (Copper, Ceffu, Fireblocks).

**⚠️ Le point crucial pour notre projet :** tout ça (quel coffre-fort, quel exchange, quelle quantité) **n'est PAS écrit dans le cahier public**. Ça se passe dans le monde réel, hors blockchain. On ne peut le savoir **que par ce qu'Ethena publie** sur son site. C'est exactement ce qu'on range dans notre fichier `curated.yaml`, avec le lien et la date (voir chapitre 11).

### « Depeg » : quand le dollar numérique ne vaut plus 1 $
Un stablecoin est censé valoir 1 $. S'il se met à valoir 0,95 $, on dit qu'il « **perd son ancrage** », en anglais *depeg*. Pour l'USDe, ça pourrait arriver si un exchange fait faillite, si les paris coûtent trop cher pendant longtemps, etc. **Tout notre travail de risque tourne autour de cette question : que se passe-t-il pour nous si l'USDe « depeg » ?**

---

## 5. Faire fructifier son argent : sUSDe, la tirelire

L'USDe seul ne rapporte rien. Mais Ethena propose de le **déposer dans une tirelire** qui rapporte des intérêts. Les intérêts viennent de ses paris (les acheteurs de paris paient une petite commission régulière) et du staking.

Quand on dépose ses USDe, on reçoit des **sUSDe** (« s » pour *staked*, « déposé »).

> **L'image à retenir : les parts d'une cagnotte qui grossit.** Vous mettez 100 € dans une cagnotte commune et recevez 100 « parts ». La cagnotte gagne des intérêts, mais le nombre de parts ne change pas : c'est **la valeur de chaque part qui monte**.

Ce que notre programme a lu au bloc 26 162 087 :
- **1 sUSDe = 1,2523 USDe.** Celui qui a déposé tôt a gagné 25 % depuis.
- Pour récupérer ses USDe, il faut **attendre 1 jour** (le « cooldown », délai de retrait).

Cette norme de tirelire s'appelle **ERC-4626**. La fonction `convertToAssets()` répond à la question « combien vaut 1 part ? ».

> 💡 **Taux interne ≠ prix de marché.** « 1 sUSDe = 1,2523 USDe » est un calcul **comptable** fait par la tirelire elle-même. Si demain tout le monde veut fuir les sUSDe, ce chiffre ne baissera pas tout seul. Le **prix auquel les gens sont prêts à l'acheter**, lui, pourrait baisser. On appelle ça un « **taux interne** », et on le distingue soigneusement d'un « **prix de marché** ».

---

## 6. Pendle et le PT : le bon du Trésor numérique

### L'idée de Pendle : séparer le capital et les intérêts
**Pendle** est une plateforme qui prend un placement qui rapporte (ici le sUSDe) et le **coupe en deux morceaux** :
- le **PT** (*Principal Token*, « jeton du capital ») : il donne droit au **capital à une date fixe** ;
- le **YT** (*Yield Token*, « jeton du rendement ») : il donne droit **aux intérêts** d'ici là.

> **L'image à retenir : la maison louée.** Une maison rapporte des loyers. Pendle permet de vendre séparément :
> - **le droit de récupérer la maison le 26 novembre** (c'est le PT) ;
> - **le droit de toucher les loyers jusque-là** (c'est le YT).

### Le PT, c'est un bon zéro-coupon
Le PT de notre position s'appelle **PT-sUSDE-26NOV2026**. Il promet : « **le 26 novembre 2026, ce jeton vaudra 1 USDe** ».

Comme il ne rapporte rien d'ici là, il s'achète **moins cher** avant cette date. Aujourd'hui (46 jours avant), il vaut environ **0,993 USDe**. Celui qui l'achète 0,993 et attend gagne 0,007 : c'est son « intérêt fixe ».

> **Analogie :** un **bon d'achat de 100 € valable au 26 novembre**, que vous achetez 99,30 € aujourd'hui. Plus la date approche, plus il vaut près de 100 €.

### Le SY : l'adaptateur
Pour pouvoir couper n'importe quel placement, Pendle l'emballe d'abord dans un format standard, le **SY** (*Standardized Yield*). Ici, le **SY-sUSDE** est un emballage autour du sUSDe.
> **Analogie :** l'**adaptateur de prise électrique** en voyage. Pendle ne sait parler qu'à des SY ; le SY parle au sUSDe.

La chaîne complète, quand on « remonte » le PT :
```
PT-sUSDE  →  se rachète en  →  SY-sUSDE  →  qui contient  →  sUSDe  →  qui contient  →  USDe
```

### Le pool : le bureau de change
Si vous voulez revendre votre PT **avant** le 26 novembre, il faut quelqu'un pour l'acheter. Pendle a un **pool** (une « réserve d'échange ») où l'on échange des PT contre des SY à tout moment. Ce type de programme d'échange automatique s'appelle un **AMM** (*Automated Market Maker*).
> **Analogie :** un **bureau de change** avec deux tiroirs, un de PT, un de SY. Vous déposez des PT dans un tiroir et prenez des SY dans l'autre. Le taux de change bouge selon ce qu'il reste dans chaque tiroir.

**Pourquoi la taille du pool compte :** notre pool contient environ **3,8 millions de dollars**. Si quelqu'un doit vendre beaucoup plus que ça d'un coup, il vide le tiroir et le prix s'effondre. Comme un petit bureau de change qui n'a pas assez de billets.

---

## 7. Emprunter avec Morpho : le prêteur sur gages

### L'image à retenir : le mont-de-piété
Vous avez une montre de valeur. Vous la laissez en **gage** au prêteur, qui vous prête de l'argent en échange. Si vous remboursez, vous récupérez la montre. Si la valeur de la montre baisse trop par rapport à ce que vous devez, le prêteur **la vend** pour se rembourser.

**Morpho** fait exactement ça, avec des smart contracts.
- **Le gage**, appelé **collatéral** : nos PT-sUSDe.
- **L'argent prêté** : des USDC.
- **Qui prête ?** D'autres personnes, ou des « coffres » de placement (**vaults**), qui déposent leurs USDC pour gagner des intérêts. Ici, c'est surtout un vault nommé « Pendle Ecosystem USDC ».

### Un « marché » Morpho
Morpho est **un seul gros programme** qui contient des milliers de petits « guichets » séparés, appelés **marchés**. Chaque marché a ses règles, fixées une fois pour toutes :
1. quel jeton est prêté (USDC) ;
2. quel jeton sert de gage (le PT) ;
3. qui donne le prix du gage (l'**oracle**, chapitre 8) ;
4. comment est calculé le taux d'intérêt ;
5. jusqu'où on peut emprunter (le **LLTV**, voir ci-dessous).

Chaque marché a un **identifiant** (une longue suite de caractères). Cet identifiant est calculé à partir de ces 5 règles : c'est leur **empreinte digitale**. Notre programme recalcule cette empreinte et vérifie qu'elle correspond, ce qui prouve qu'on lit bien le bon marché.

### Les chiffres qui comptent (avec un exemple simple)
Prenons un exemple rond avant les vrais chiffres. Vous déposez un gage qui vaut **100 €** et vous empruntez **87 €**.

| Terme | Définition simple | Exemple |
|---|---|---|
| **LTV** (*Loan-To-Value*) | ce que je dois ÷ ce que vaut mon gage | 87 / 100 = **87 %** |
| **LLTV** (*Liquidation LTV*) | la **limite** à ne pas dépasser, fixée par le marché | **91,5 %** |
| **Liquidation** | si mon LTV dépasse la limite, n'importe qui peut rembourser ma dette et **prendre mon gage avec un bonus** | — |
| **Health factor** (facteur de santé) | à quelle distance je suis de la limite. Au-dessus de 1 : ça va. Égal à 1 : je suis liquidable | 91,5 / 87 = **1,05** |

> Avec un health factor de **1,05**, si la valeur estimée du gage baisse d'environ **5 %**, on touche la limite et on est liquidé.

**Les vrais chiffres de la position A** (bloc 26 162 087) :
- gage : **413 030 PT**, estimés à **409 872 USDC** ;
- dette : **357 217 USDC** (intérêts inclus) ;
- LTV : **87,2 %**, limite **91,5 %**, health factor **1,050** ;
- **liquidable si le prix estimé du PT baisse de 4,75 %** ;
- taux d'emprunt : **3,7 % par an**.

> 💡 **Les intérêts « en retard ».** Morpho ne met à jour les intérêts que quand quelqu'un interagit avec le marché. Entre-temps, la dette affichée est un peu en retard, comme un compteur de taxi qu'on ne regarde que de temps en temps. Notre programme recalcule les intérêts manquants comme Morpho le ferait.

---

## 8. L'oracle : l'expert qui estime la valeur du gage

### Le problème
Un smart contract est **aveugle** : il ne voit pas le monde extérieur et ne sait pas « combien vaut un PT ». Il faut quelqu'un pour **le lui dire**. Ce quelqu'un s'appelle un **oracle**.

> **L'image à retenir : l'expert du mont-de-piété.** Le prêteur ne connaît pas la valeur de votre montre. Il demande à un expert. **Si l'expert dit qu'elle vaut moins, vous êtes liquidé, même si la montre n'a pas changé.**
>
> **Morpho croit l'oracle aveuglément.** Comprendre l'oracle, c'est comprendre **quand** on peut être liquidé.

### Deux façons d'estimer : prix fixé, ou prix de marché
C'est **LE point clé** du projet.

| | **Prix fixé (« fixed »)** | **Prix de marché (« market »)** |
|---|---|---|
| Analogie | l'expert donne le **prix catalogue** de la montre | l'expert regarde **à combien elle se revend** aujourd'hui |
| Avantage | ne panique pas si le marché a un coup de folie passager | colle à la réalité |
| Danger | si la montre perd **vraiment** sa valeur, l'expert ne le voit pas | un mouvement brutal et passager peut déclencher des liquidations |
| Qui prend le risque ? | les **prêteurs** (le gage vaut moins qu'annoncé) | les **emprunteurs** (nous) |

Il existe une 3ᵉ catégorie, le **taux interne** : l'expert demande au fabricant lui-même (comme la tirelire sUSDe, chapitre 5). Ce n'est pas un prix de marché non plus.

### Notre oracle à nous : deux experts et un arbitre
Notre programme a découvert que le marché utilise un **méta-oracle** (conçu par une société appelée Steakhouse). « Méta » veut dire qu'il chapeaute deux oracles.

```
                  ARBITRE (méta-oracle)
                 /                     \
   EXPERT 1 « catalogue »         EXPERT 2 « marché »
   (actif en temps normal)        (de secours)
   prix du PT = formule           prix du PT = formule
   qui ne dépend que du temps     × vrai prix de l'USDe
   et suppose 1 USDe = 1 $        (fourni par Chainlink)
```

- **Expert 1 (prix fixé).** Il applique une **formule** : « le PT vaut 1 moins une petite décote qui diminue avec le temps » (6 % par an). Aujourd'hui, ça donne 0,9924. Le 26 novembre, ça donnera exactement 1. **Il ne regarde jamais le marché**, et il **suppose que 1 USDe vaut toujours 1 $**.
- **Expert 2 (prix de marché).** Même formule, mais **multipliée par le vrai prix de l'USDe**, fourni par **Chainlink**, la plus grosse entreprise d'oracles. Si l'USDe tombe à 0,95 $, son prix baisse de 5 %.
- **L'arbitre.** En temps normal, il écoute l'expert 1. Si les deux experts sont **en désaccord de plus de 0,75 %**, n'importe qui peut lever la main (« contestation »). Si le désaccord **dure encore 16 heures plus tard**, l'arbitre **passe à l'expert 2**.

### Ce que ça veut dire concrètement (scénarios)
| Si l'USDe vaut… | Que se passe-t-il pour nous ? |
|---|---|
| plus de 0,9925 $ | Rien. Les experts sont d'accord à moins de 0,75 %. |
| entre 0,9525 $ et 0,9925 $ | Après 16 h, l'arbitre peut passer à l'expert 2. Notre santé baisse, **mais on n'est pas liquidés**. |
| **moins de 0,9525 $ pendant plus de 16 h** | L'arbitre passe à l'expert 2, le prix estimé baisse de plus de 4,75 % : **on est liquidés**. |
| moins de 0,9525 $ pendant **moins** de 16 h | L'expert 1 reste aux commandes, on n'est pas liquidés. Mais pendant ce temps, **ce sont les prêteurs qui sont exposés** : le gage vaut moins qu'annoncé. |

> 🎯 **À retenir :** ce système **ignore les paniques courtes** (bien pour nous) mais **suit les crises longues** (liquidation). Le délai de **16 heures** est le réglage de risque le plus important de toute notre position.

---

## 9. La position A racontée comme une histoire

Imaginons **Alice**, qui a la position A. Voici ce qu'elle a fait, étape par étape :

1. Alice avait des **USDe** (le dollar d'Ethena).
2. Elle les a mis dans la **tirelire** d'Ethena et a reçu des **sUSDe**, qui rapportent des intérêts.
3. Elle a passé ses sUSDe chez **Pendle** : ils ont été emballés en **SY**, puis coupés, et elle a gardé le **PT**, qui vaudra 1 USDe le 26 novembre 2026.
4. Elle a déposé ses PT en **gage** sur un marché **Morpho**, et a **emprunté des USDC** en échange.
5. Le prix de son gage est donné par le **méta-oracle** (les deux experts + l'arbitre).

Pourquoi faire ça ? Avec les USDC empruntés, Alice peut racheter des PT, les redéposer, emprunter encore… et ainsi **multiplier son rendement fixe**. C'est un montage classique, mais **chaque étape ajoute un risque**. Ce sont ces risques qu'on cartographie.

---

## 10. Les dépendances : un jeu de dominos

### L'idée
Si une pièce du montage casse, tout ce qui est « au-dessus » tombe. C'est un **jeu de dominos**. Notre projet dessine **tous les dominos et leurs liens**, pour qu'une autre équipe puisse calculer « si tel domino tombe, combien on perd ? ».

### Le dessin (simplifié)
Une flèche « A → B » veut dire « **A dépend de B** » : si B casse, A souffre.
```
POSITION D'ALICE
   │ est placée dans
   ▼
MARCHÉ MORPHO ──── prête des ────► USDC ──── émis par ────► Circle
   │        └──── prix donné par ──► MÉTA-ORACLE ──► expert 1 (formule)
   │                                            └──► expert 2 (formule × Chainlink USDe/USD)
   │ garanti par
   ▼
PT-sUSDe ──── échangeable dans ────► POOL PENDLE (bureau de change, 3,8 M$)
   │ se rachète en
   ▼
SY-sUSDe ──► sUSDe ──► USDe ──── émis par ────► Ethena
                                                 ├── garde ses cryptos chez → Copper, Ceffu, Fireblocks
                                                 └── fait ses paris sur     → Binance, Bybit, OKX, Bitget, Deribit
Et tout ça « fonctionne sur » ──► Ethereum
```

### Exemples de « dominos qui tombent »
- **Binance fait faillite** → les paris d'Ethena sont touchés → l'USDe peut perdre son ancrage → le sUSDe, le SY et le PT perdent de la valeur → si ça dure plus de 16 h, l'oracle le voit → **Alice est liquidée**.
- **Le pool Pendle est trop petit** → les liquidateurs ne peuvent pas revendre les PT saisis sans casser le prix → ils hésitent à liquider → **les prêteurs risquent de ne pas être remboursés**.
- **Chainlink se trompe sur le prix de l'USDe** → l'expert 2 se trompe → si l'arbitre l'écoute, liquidation injuste.

Notre programme sait répondre automatiquement à « qui tombe si X tombe ? » :
```bash
PYTHONPATH=src python -m discovery.inspect_graph --impact binance
```

### Le vocabulaire des flèches (traduit)
| Mot anglais dans le fichier | En français | Exemple |
|---|---|---|
| `deployed_in` | « est placé dans » | la position est placée dans le marché |
| `collateralized_by` | « est garanti par » | le marché est garanti par le PT |
| `lends` | « prête » | le marché prête des USDC |
| `priced_by` | « tire son prix de » | le marché tire son prix de l'oracle |
| `redeemable_into` | « s'échange contre » | le PT s'échange contre du SY |
| `issued_by` | « est émis par » | l'USDe est émis par Ethena |
| `settled_on` | « fonctionne sur » | tout fonctionne sur Ethereum |

---

## 11. Notre mission : jouer les détectives

### Ce qu'on nous demande
Notre partie du projet (le **Module de Découverte**, 30 % de la note) doit **trouver tous les dominos tout seul**, à partir d'une seule information de départ : l'identifiant du marché Morpho et l'adresse d'Alice.

Et surtout : **prouver chaque lien**. Pas de « je crois que », pas de « de mémoire ». Le jury veut voir que **rien n'est inventé** (en anglais : *no hallucination*).

### Comment le programme enquête
Comme un détective qui tire un fil :
1. Il demande au marché Morpho : « quelles sont tes 5 règles ? ». Réponse : le gage est le contrat 0xB195…, l'oracle est 0xF8b2…
2. Il demande au contrat 0xB195… : « qui es-tu ? ». Il **sonde** : il répond à `SY()` et `expiry()`, donc c'est un PT Pendle. « Qui est ton SY ? » → 0xBF98…
3. Il demande au SY : « qu'y a-t-il dedans ? » → sUSDe. Au sUSDe : « quel est ton actif ? » → USDe.
4. Il démonte l'oracle de la même façon, expert par expert.
5. Et ainsi de suite, jusqu'à ce qu'il n'y ait plus de fil à tirer.

### Les 3 types de preuves
Chaque lien du graphe dit **d'où il vient**. Il y a trois niveaux de preuve :

| Type | Analogie | Exemple | Fiabilité |
|---|---|---|---|
| **onchain** | un **relevé officiel** lu directement dans le cahier public | « le contrat PT répond que son SY est 0xBF98…, au bloc 26 162 087 » | ⭐⭐⭐ vérifiable par n'importe qui |
| **api** | un **renseignement** donné par le site officiel d'un protocole | « l'API de Morpho dit que tel vault prête à ce marché » | ⭐⭐ on fait confiance au site |
| **curated** (curé) | une **coupure de presse datée** | « la doc d'Ethena, consultée le 10/10/2026, dit que ses gardiens sont Copper, Ceffu… » | ⭐ vrai à cette date, peut vieillir |

> 💡 **« Curé »** ne veut rien dire de religieux : ça vient de l'anglais *curated*, « sélectionné à la main ». C'est ce qu'on a vérifié nous-mêmes dans des sources officielles, en notant le lien et la date. On l'utilise uniquement pour ce qui **n'existe pas** sur la blockchain (qui est derrière une adresse, où sont les coffres d'Ethena…).

Quand c'est possible, on **combine** : on utilise l'API pour **trouver** le pool Pendle (le PT ne connaît pas son pool), puis on le **prouve** dans le cahier public (le pool confirme qu'il contient bien notre PT).

### Pourquoi un « cache » ?
Pendant la démo devant le jury, si le Wi-Fi tombe, on ne peut plus interroger la blockchain. On a donc **enregistré toutes les réponses** dans le dossier `data/cache/`.
> **Analogie :** on a **photocopié toutes les pages** du cahier dont on avait besoin. Le jour J, on lit les photocopies : même résultat, sans réseau.

Comme toutes les questions ont été posées **au même bloc** (la même « photo »), les photocopies sont cohérentes et le résultat est identique à chaque fois.

---

## 12. Lire notre fichier graph.json sans paniquer

`output/graph.json` est le **livrable** que les autres équipes utilisent. Il a trois parties.

### 1) La position
```json
"position": {"id": "morpho:0x5613…:0x03BA…", "value_usd": 409816.56}
```
En français : « La position sur le marché Morpho 0x5613…, de l'utilisateur 0x03BA…, vaut environ 409 817 $. »

### 2) Les nœuds (les dominos)
```json
{"id": "usde", "type": "asset", "label": "USDe", "address": "0x4c9E…", "chain": "ethereum",
 "meta": {"price_usd": 0.9996, "tvl_usd": 4779918261, …}}
```
En français : « Le domino `usde` est un **actif** (un jeton) appelé USDe, à l'adresse 0x4c9E… sur Ethereum. Il vaut 0,9996 $ et il en existe pour 4,78 milliards de dollars. »
- `type` dit **quelle sorte** de domino c'est (jeton, oracle, marché, entreprise…) ;
- `meta` est un sac d'informations supplémentaires utiles aux autres équipes.

### 3) Les arêtes (les liens entre dominos)
```json
{"from": "susde", "to": "usde", "type": "redeemable_into", "weight": 1.0,
 "source": "onchain", "evidence": "sUSDe.asset() = 0x4c9E… @ 0x9D39… #26162087 …"}
```
En français : « **sUSDe s'échange contre USDe**, et le lien est total (`weight` 1.0). C'est prouvé **dans le cahier public** : on a demandé au contrat sUSDe (adresse 0x9D39…) quel était son actif, au bloc 26 162 087, et il a répondu 0x4c9E… (l'USDe). »

Le champ `evidence` est **la preuve**. N'importe qui peut la refaire.

---

## 13. Comment on mesure le risque

Les chapitres 1 à 12 répondent à « **de quoi** dépend la position ? ». Ce chapitre répond à la question que pose
vraiment le brief : **« faut-il rester ou sortir, et pourquoi ? »**. C'est le travail du **moteur de risque**
(`src/risk/`).

### L'image à retenir : faut-il assurer sa voiture ?
- L'assurance coûte une **prime certaine** (vous la payez à coup sûr).
- Sans assurance, vous risquez un **accident** : peu probable, mais cher.
- Assurer vaut le coup si « **probabilité d'accident × coût de l'accident** » dépasse la prime.

Pour notre position, c'est la même chose :
- la « prime », c'est le **coût de sortie** : ce que ça coûte de tout revendre maintenant (certain) ;
- l'« accident », c'est l'**incident** (un depeg, une faillite…), qui ferait perdre une somme si on reste.

### Étape 1 : imaginer un choc
Un **choc**, c'est une phrase du type « *l'USDe tombe à 0,93 $ pendant 24 heures* ». Il a 4 ingrédients :
**où** (quel nœud du graphe), **quoi** (depeg, faillite, panne…), **combien** (−7 %) et **combien de temps** (24 h).

### Étape 2 : faire tomber les dominos
Le moteur fait remonter le choc le long des flèches du graphe, avec **une règle écrite en clair par type de flèche** :

| Flèche | Règle (en français) |
|---|---|
| « s'échange contre » | si l'USDe perd 7 %, le sUSDe, le SY et le PT perdent 7 % aussi |
| « est émis par » | si Ethena perd une partie de ses réserves, l'USDe perd la même part |
| « est placé dans » (Ethena → Binance) | si Binance fait faillite, Ethena perd la petite part de ses réserves qui y était exposée |
| « tire son prix de » | un expert « catalogue » (prix fixé) ne transmet **rien** ; un expert « marché » transmet tout |

### Étape 3 : l'arbitre et sa minuterie de 16 heures
Rappel du chapitre 8 : l'oracle a deux experts et un arbitre. L'arbitre ne passe à l'expert « marché » que si les deux
experts sont en désaccord **pendant 16 heures** (chiffre lu dans le contrat lui-même).
- USDe à 0,93 $ pendant **6 h** : l'arbitre ne bouge pas, rien ne se passe. **Perte : 0 $.**
- USDe à 0,93 $ pendant **24 h** : l'arbitre bascule, le gage est réévalué à la baisse, Alice est liquidée. **Perte : ~37 000 $.**

C'est la découverte la plus importante du projet : **la durée d'un choc compte autant que son ampleur**.

### Étape 4 : qui perd combien ?
- **Si Alice est liquidée**, un « liquidateur » (n'importe qui) rembourse sa dette et repart avec son gage, **plus un
  bonus** d'environ 2,6 % (formule officielle de Morpho). C'est Alice qui paie ce bonus.
- **Si l'oracle ne voit rien** (prix fixé), Alice n'est pas liquidée. Mais si son gage vaut désormais **moins que sa dette**,
  elle peut tout abandonner : c'est alors **le prêteur** qui encaisse le trou. On appelle ça une **dette irrécouvrable**.
  Exemple : un exploit chez Pendle laisserait **152 000 $** de trou aux prêteurs, sans une seule liquidation.

### Étape 5 : combien coûte de sortir ?
On a demandé un **devis** au vrai bureau de change Pendle, sans rien vendre : « si je vendais 413 030 PT, combien
recevrais-je ? ». Le contrat sait répondre à ça (une fonction de *simulation*). Le coût de sortie total additionne :
1. le **glissement** : plus on vend gros, plus le taux se dégrade (environ 0,12 %) ;
2. la conversion vers des USDC pour rembourser la dette (petite, et c'est une hypothèse) ;
3. le **gas** : les frais de transaction d'Ethereum (quelques centimes aujourd'hui) ;
4. le **rendement abandonné** : ce qu'on aurait gagné en restant pendant la semaine.

Total : **854 $**, soit 1,6 % du capital d'Alice (qui vaut 53 133 $).

### Étape 6 : le seuil p* (« p étoile »)
La règle du brief tient en une division :
> **p\* = coût de sortie ÷ perte si l'incident arrive**

- Exemple du brief : sortir coûte 11, l'incident coûterait 60, donc p\* = 11 ÷ 60 ≈ **18 %**.
- Notre position face à l'alerte « USDe −30 % durable » : p\* = 854 ÷ 53 133 ≈ **1,6 %**.

Ce que ça veut dire : **si vous croyez à plus de 1,6 % de chances que l'incident arrive, sortir coûte moins cher que rester.**
Le gros avantage : le manager n'a pas besoin de faire confiance à NOTRE probabilité. Il compare la sienne à p\*.

> 💡 Pourquoi p\* est-il si bas ici ? Parce que la position est à **levier** : Alice a emprunté 87 % de la valeur de son gage.
> Une petite baisse peut donc effacer tout son capital. Un levier rend une position fragile.

### Étape 7 : sortir en partie
Le glissement grandit **plus vite** que la taille vendue : les premiers PT se vendent presque sans perte, les derniers plus
cher. Selon la probabilité qu'on croit, la meilleure réponse est parfois « vendre 35 % » plutôt que tout ou rien. Le moteur
calcule cette fraction pour chaque probabilité de 0 à 100 % : c'est le verdict **PARTIAL x %**.

### Étape 8 : « et sans alerte ? » — le Monte Carlo
Pour estimer le risque d'une semaine normale, on **rejoue la semaine 200 000 fois** sur ordinateur. À chaque fois, chaque
événement (depeg, faillite, exploit…) arrive ou non, au hasard, selon sa fréquence. On obtient :
- la **perte attendue** : la moyenne (environ 130 $ par semaine ici) ;
- la **VaR 95 %** : la perte qu'on ne dépasse que dans 5 % des semaines. Elle vaut **0 $** ici, car dans 99 % des semaines
  il ne se passe rien ;
- l'**ES 99 %** : la moyenne des 1 % pires semaines (environ 13 000 $), pour voir la queue du risque.

### Étape 9 : l'honnêteté sur les chiffres
Chaque paramètre du moteur porte une étiquette (fichier `risk/params.yaml`) :
- **sourcé** : lu dans une doc officielle (lien + date), par exemple la formule du bonus de liquidation de Morpho ;
- **on-chain** : lu dans la blockchain, par exemple les 16 h de l'arbitre ou le devis du bureau de change ;
- **hypothèse** : un choix de notre équipe, justifié en une phrase. Exemple : « une faillite d'exchange majeur environ une
  fois tous les 100 ans par exchange ».

Le programme **refuse de démarrer** si un chiffre n'a pas d'étiquette. Et une **analyse de sensibilité** montre ce qui bouge
quand on change chaque hypothèse.

### Étape 10 : la preuve sur un vrai incident
Le **10 octobre 2025**, l'USDe est tombé à **0,65 $ sur Binance** pendant ~40 minutes, mais il est resté proche de 1 $
on-chain. On a relu l'historique du feed Chainlink : son plus bas ce jour-là était **0,9929 $**. Résultat du replay :
- notre oracle : rien ne se passe (l'écart n'a même pas atteint le seuil) ;
- un oracle qui écouterait Binance : Alice aurait été **liquidée**.

Morale : **la source de l'oracle compte**.

---

## 14. Comment lire le front

Le front (`front/`) est un **deck de diapositives** qui suit les questions d'une risk manager à 3 h du matin. Pour le lancer :
```bash
cd front && npm install && npm run dev
```
puis ouvrez http://localhost:5173. Sans backend, il affiche des réponses réelles enregistrées (`docs/api_examples/`) : pas
besoin d'Internet. ← → change de poche, ↑ ↓ change de question.

| # | Diapositive | Ce qu'elle montre |
|---|---|---|
| 1 | Portefeuille | les poches du détenteur, leur poids, leur verdict |
| 2 | Verdict | **STAY / EXIT** en grand, ce que la sortie éviterait contre ce qu'elle coûte, le seuil p\* |
| 3 | Par quel chemin ? | le graphe prouvé ; clic sur une arête = sa preuve |
| 4 | Combien je perds ? | Monte Carlo et incidents classés, avec leur règle |
| 5 | Combien coûte la sortie ? | coût certain, part sortable maintenant |
| 6 | Et si ça arrive ? | votre probabilité contre p\* : le verdict bascule |
| 7 | Concentration | les dépendances partagées par plusieurs poches |

> Important : le front **ne calcule rien**. Il affiche ce que l'API Python a calculé. Si les chiffres semblent faux,
> c'est dans `src/stacktrace/` qu'il faut regarder.

---

## 15. Glossaire

| Mot | Explication simple |
|---|---|
| **Adresse** | identifiant d'un compte ou d'un programme sur la blockchain (`0x…`, 42 caractères) |
| **AMM / pool** | programme d'échange automatique entre deux jetons ; un « bureau de change » sans guichetier |
| **API** | un service web qui répond à des questions (ici : les sites de Morpho et Pendle) |
| **Bloc** | une « page » du cahier public ; numérotée ; une toutes les ~12 s sur Ethereum |
| **Blockchain** | cahier de comptes public, copié partout, ineffaçable |
| **Cache** | les réponses enregistrées pour pouvoir les relire sans réseau |
| **Chainlink** | entreprise qui fournit des prix (oracles) à la blockchain |
| **Collatéral** | le gage déposé pour emprunter |
| **Cooldown** | délai d'attente avant de pouvoir retirer (1 jour pour sUSDe) |
| **Curated (curé)** | information vérifiée à la main dans une source officielle, avec lien et date |
| **Custodian** | entreprise « coffre-fort » qui garde des cryptos pour quelqu'un |
| **DeFi** | finance décentralisée : prêter, emprunter, placer avec des smart contracts |
| **Depeg** | quand un stablecoin ne vaut plus 1 $ |
| **ERC-20** | la norme standard des jetons |
| **ERC-4626** | la norme standard des « tirelires à parts » |
| **Ethereum** | la blockchain sur laquelle tout se passe ici |
| **Exchange** | plateforme d'échange centralisée (Binance, OKX…) |
| **Health factor** | distance à la liquidation ; < 1 = liquidable |
| **Hedge / couverture** | pari inverse qui neutralise les variations de prix |
| **Liquidation** | vente forcée du gage quand la dette devient trop grande par rapport à lui |
| **LLTV** | la limite dette/gage à ne pas dépasser (91,5 % ici) |
| **LTV** | dette ÷ valeur du gage |
| **Mainnet** | le vrai réseau (par opposition aux réseaux de test) |
| **Marché (Morpho)** | un guichet de prêt avec ses 5 règles fixes |
| **Méta-oracle** | oracle qui choisit entre deux autres oracles |
| **Morpho** | plateforme de prêt/emprunt sur gage |
| **Nœud / RPC** | serveur qui a une copie de la blockchain / le guichet pour l'interroger |
| **Oracle** | le programme qui dit à la blockchain combien vaut quelque chose |
| **Pendle** | plateforme qui sépare capital (PT) et intérêts (YT) |
| **Prix fixé / de marché / taux interne** | prix par formule / prix réel de revente / calcul comptable du fabricant |
| **Proxy upgradeable** | contrat dont le propriétaire peut changer le code (un risque) |
| **PT** | jeton du capital : vaut 1 actif à une date fixe |
| **Revert** | refus d'un contrat (par exemple : fonction inexistante) |
| **Smart contract** | programme posé sur la blockchain qui applique ses règles tout seul |
| **Sonder** | essayer des fonctions pour deviner ce qu'est un contrat |
| **Stablecoin** | jeton qui vaut environ 1 $ (USDC, USDe) |
| **sUSDe** | parts de la tirelire d'Ethena (USDe déposés qui rapportent) |
| **SY** | emballage standard de Pendle (l'« adaptateur de prise ») |
| **Token / jeton** | une unité numérique inscrite dans le cahier |
| **TVL** | *Total Value Locked* : combien d'argent est déposé quelque part |
| **USDC** | dollar numérique de Circle, adossé à de vrais dollars |
| **USDe** | dollar numérique d'Ethena, adossé à des cryptos couvertes |
| **Vault** | coffre de placement qui prête l'argent de ses déposants |
| **YT** | jeton du rendement : touche les intérêts jusqu'à la date |
| **Bonus de liquidation (LIF)** | ce que gagne le liquidateur en plus (≈ 2,6 % ici) ; c'est l'emprunteur qui le paie |
| **Choc** | un incident imaginé : où, quoi, combien, combien de temps |
| **Coût de sortie (C_exit)** | ce que coûte, à coup sûr, de tout revendre maintenant (glissement + conversion + gas + rendement abandonné) |
| **Dette irrécouvrable** | la partie de la dette que le gage ne couvre plus : perdue pour les prêteurs |
| **ES 99 %** | la moyenne des 1 % pires scénarios |
| **Gas** | les frais payés pour faire une transaction sur Ethereum |
| **Glissement (slippage)** | la perte due au fait que plus on vend gros, plus le prix se dégrade |
| **Monte Carlo** | rejouer une période des milliers de fois au hasard pour voir la distribution des pertes |
| **p\* (p étoile)** | le seuil de probabilité : coût de sortie ÷ perte en cas d'incident ; au-dessus, il vaut mieux sortir |
| **Perte attendue** | la perte moyenne sur l'ensemble des scénarios tirés au hasard |
| **Replay** | rejouer un incident réel passé sur la position d'aujourd'hui |
| **Sensibilité** | comment le résultat change si on change une hypothèse |
| **VaR 95 %** | la perte qu'on ne dépasse que dans 5 % des cas |
| **Verdict** | STAY (rester), PARTIAL x % (sortir une partie), EXIT (tout sortir) |

---

## 16. Petit quiz pour vérifier qu'on a compris

Répondez à voix haute entre vous, puis ouvrez le corrigé.

1. Pourquoi dit-on « au bloc n° 26 162 087 » ?
2. Quelle est la différence entre USDC et USDe ?
3. Si 1 sUSDe vaut 1,25 USDe, est-ce un prix de marché ?
4. Que vaudra un PT-sUSDE-26NOV2026 le 26 novembre 2026 ?
5. Alice a un health factor de 1,05. Qu'est-ce que ça veut dire ?
6. L'USDe tombe à 0,90 $ pendant 2 heures, puis remonte. Alice est-elle liquidée ?
7. Et s'il reste à 0,90 $ pendant 3 jours ?
8. Pourquoi « où Ethena garde ses cryptos » est-il dans `curated.yaml` et pas « onchain » ?
9. À quoi sert le dossier `data/cache/` ?
10. Que veut dire la flèche « `susde` → `usde` » de type `redeemable_into` ?
11. Sortir coûte 854 $ et l'incident ferait perdre 53 133 $. Que vaut p\*, et que veut-il dire ?
12. Pourquoi un exploit chez Pendle ne liquide-t-il pas Alice, et qui perd de l'argent ?
13. Pourquoi la VaR 95 % vaut-elle 0 $ alors que la perte attendue n'est pas nulle ?

<details>
<summary><b>Corrigé</b></summary>

1. Pour dire **à quel instant** on a lu les données (la « photo » du cahier). Toutes nos lectures sont faites au même bloc, donc cohérentes et revérifiables.
2. L'USDC est adossé à de **vrais dollars** gardés par Circle. L'USDe est adossé à des **cryptos + des paris inverses** gérés par Ethena.
3. **Non**, c'est un **taux interne** (le calcul comptable de la tirelire). Le prix auquel quelqu'un l'achèterait pourrait être différent.
4. **1 USDe** (payé sous forme de sUSDe, qu'il faudra déstaker pendant 1 jour pour avoir des USDe).
5. Elle est à environ **5 % de la liquidation** : si le prix estimé de son gage baisse d'environ 4,75 %, elle devient liquidable.
6. **Non.** L'arbitre exige 16 h de désaccord avant de passer à l'expert « marché ». Pendant ces 2 h, l'expert « catalogue » reste aux commandes.
7. **Oui, probablement.** Après 16 h, quelqu'un peut faire basculer l'oracle sur le prix de marché. Le prix estimé baisse alors d'environ 10 %, plus que les 4,75 % de marge d'Alice.
8. Parce que ça se passe **dans le monde réel** (entreprises, comptes sur des exchanges), pas dans le cahier public. On ne peut le savoir que par ce qu'Ethena **publie**, d'où le lien et la date.
9. À **rejouer la découverte sans Internet**, avec exactement les mêmes réponses (les « photocopies » du cahier).
10. « Le **sUSDe s'échange contre de l'USDe** » : le sUSDe dépend de l'USDe. Si l'USDe casse, le sUSDe souffre.
11. p\* = 854 ÷ 53 133 ≈ **1,6 %** : si l'on croit à plus de 1,6 % de chances que l'incident arrive, sortir coûte moins cher que rester.
12. Parce que l'oracle principal est **fixe** : il ne voit pas la baisse du PT, donc la santé d'Alice ne bouge pas. Mais son gage vaut moins que sa dette : elle peut abandonner, et ce sont les **prêteurs** qui encaissent le trou (dette irrécouvrable).
13. Parce que dans plus de 95 % (et même 99 %) des semaines simulées, **rien ne se passe**. La perte attendue vient des rares semaines très mauvaises ; l'ES 99 % les montre.
</details>

---

## Et après ?
Quand ce guide est clair pour vous, lisez dans cet ordre :
1. [`POSITION_A.md`](POSITION_A.md) : la même histoire avec tous les vrais chiffres ;
2. [`CONTRACT.md`](CONTRACT.md) : le format exact du fichier livré aux autres équipes ;
3. [`VERIFY.md`](VERIFY.md) : ce que **vous** devez vérifier vous-mêmes ;
4. [`NEXT_STEPS.md`](NEXT_STEPS.md) : la suite du travail.

Et pour **voir** le graphe dans le terminal :
```bash
PYTHONPATH=src python -m discovery.inspect_graph
```
