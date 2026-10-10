# StackTrace · front en diapositives

Le front du backend v2 (`src/stacktrace/api.py`). Une seule question par écran, dans l'ordre où une risk manager les pose
à 3 h du matin, et le verdict **STAY / EXIT** toujours visible.

| # | Diapositive | Ce qu'elle montre | Route de l'API |
|---|---|---|---|
| 1 | Portefeuille | les poches du détenteur, leur poids, leur verdict, la perte attendue totale | `/pockets`, `/book` |
| 2 | Verdict | **STAY / EXIT** en très grand, la phrase du backend, ce que la sortie éviterait contre ce qu'elle coûte, la question p\* | `/risk` |
| 3 | Par quel chemin ? | le graphe prouvé ; survol = chemin de contagion, clic = preuves de chaque arête ; oracles hors marché en ambre | `/graph` |
| 4 | Combien je perds ? | Monte Carlo (perte attendue, VaR), incidents classés avec leur règle et leur chemin | `/risk` |
| 5 | Combien coûte la sortie ? | coût certain, part sortable maintenant, détail coffre ou devis de glissement, marchés | `/risk` |
| 6 | Et si ça arrive ? | votre estimation de probabilité contre p\*, la sévérité (en direct), le verdict qui bascule, le chemin surligné | `/incident` |
| 7 | Concentration | les dépendances partagées par plusieurs poches | `/book` |

**Clavier** : ← → poche précédente / suivante, ↑ ↓ ou molette : diapositive suivante.

## Lancer

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # vérification des types + build de production
```

### Deux sources de données

| Source | Quand | Ce qui s'affiche |
|---|---|---|
| **Enregistrée** | par défaut, et dès que l'API ne répond pas | les réponses réelles de `docs/api_examples/` (mainnet, bloc #26162868), importées directement : une seule copie |
| **En direct** | l'API tourne et vous la choisissez | n'importe quel détenteur, le bloc courant (renouvelé toutes les 2 min) |

Le front cherche l'API en arrière-plan (`/health`) et propose de passer en direct ; le choix est mémorisé. La pastille en
haut à droite dit toujours d'où viennent les chiffres (bloc, âge) et permet de changer d'adresse d'API.

Forcer une source : `?source=recorded`, `?source=live`, `?api=http://hote:8000`, `?holder=0x…`, ou à la compilation
`VITE_SOURCE=recorded|live` et `VITE_API_URL=…`.

En enregistré, seules les poches enregistrées ont tout leur détail (Belem RWA EURCV : graphe, risque, incident ; l'emprunt
PST/USDC : risque). Pour les autres, le front affiche la ligne du portefeuille et dit que le détail se calcule en direct :
il n'invente jamais une réponse.

### En direct

À la racine du dépôt, avec `ETH_RPC_URL` dans `.env` :

```bash
PYTHONPATH=src python -m stacktrace.api          # http://127.0.0.1:8000
```

Le premier calcul d'un bloc est lent (docs/API.md) : `/pockets` ~5 s, `/risk` 10 à 30 s, `/book` ~1 min 30. Le front
ordonne ses appels pour que la poche affichée arrive d'abord : poches → risque de la poche → graphe et portefeuille.

### Serveur de rejeu (mode direct sans RPC)

```bash
npm run replay-api -- --port 8000 --latency 1500
```

Il répond aux vraies routes de l'API avec les réponses enregistrées (mêmes codes d'erreur : 404 avec la liste des poches,
422 de validation). Une requête non enregistrée reçoit un 422 explicite, jamais une réponse fabriquée. `--latency` simule
la lenteur du premier appel.

## Ce que le front calcule, et ce qu'il ne calcule pas

Il ne calcule **aucun risque**. Tout chiffre de perte, de coût, de seuil ou de verdict vient de l'API. Il fait seulement :

- des parcours du graphe : disposition en couches, chemin entre la poche et un nœud (« qui est touché si X casse »), part
  de la poche qui passe par un nœud (produit des poids d'arêtes du chemin le plus large) ;
- la comparaison de votre estimation au seuil **p\*** que le backend publie (« sortez si vous croyez à plus de p\* ») tant
  que le calcul exact `/incident` n'est pas revenu, ou en mode enregistré. Le texte dit alors que c'est la règle du seuil.

## Structure

```
src/
  api/types.ts          contrat de l'API (docs/API.md)
  api/client.ts         appels HTTP, délais, erreurs FastAPI
  api/recorded.ts       réponses enregistrées (docs/api_examples/)
  api/source.tsx        source en direct ou enregistrée, détection de l'API
  api/hooks.ts          requêtes React Query et ordre des appels
  state/selection.tsx   détenteur, poche, incident ; vue combinée d'une poche
  lib/graph.ts          disposition et chemins du graphe (aucun risque)
  lib/format.ts         nombres à la française (« 643 $ », « 0,6 % »)
  components/           en-tête, pastille de source, rail, graphe, fiche de preuves, états
  slides/               les 7 diapositives
scripts/replay-api.mjs  serveur de rejeu
```

React 18, TypeScript, Vite, Tailwind CSS 3, react-force-graph-2d, Framer Motion, TanStack Query.

## Design

Fond noir, un seul bleu d'accent, trois couleurs d'état qui ne servent qu'à ça : vert STAY, rouge EXIT, ambre pour ce qui
ne suit pas le marché. Deux graisses. Pas de bordures ni d'ombres : l'espace sépare. Le verdict est le plus grand texte du
deck.
