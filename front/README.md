# StackTrace · slide-deck front

The front of backend v2 (`src/stacktrace/api.py`). One question per screen, in the order a risk manager asks them
at 3 a.m., with the **STAY / EXIT** verdict always visible.

| # | Slide | What it shows | API route |
|---|---|---|---|
| 1 | Portfolio | the holder's pockets, their weight, their verdict, the total expected loss | `/pockets`, `/book` |
| 2 | Verdict | **STAY / EXIT** in very large type, the backend's sentence, what exiting would avoid versus what it costs, the p\* question | `/risk` |
| 3 | Which path? | the proven graph; hover = contagion path, click = evidence for every edge; off-market oracles in amber | `/graph` |
| 4 | How much do I lose? | Monte Carlo (expected loss, VaR), incidents ranked with their rule and their path | `/risk` |
| 5 | What does exiting cost? | certain cost, share exitable now, vault details or slippage quotes, markets | `/risk` |
| 6 | What if it happens? | your probability estimate against p\*, the severity (live), the verdict that flips, the highlighted path | `/incident` |
| 7 | Concentration | the dependencies shared by several pockets | `/book` |

**Keyboard**: ← → previous / next pocket, ↑ ↓ or mouse wheel: next slide.

## Run

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # type check + production build
```

### Two data sources

| Source | When | What is shown |
|---|---|---|
| **Recorded** | by default, and whenever the API does not answer | the real responses from `docs/api_examples/` (mainnet, block #26162868), imported directly: a single copy |
| **Live** | the API is running and you pick it | any holder, the current block (refreshed every 2 min) |

The front looks for the API in the background (`/health`) and offers to go live; the choice is remembered. The pill in
the top-right corner always says where the numbers come from (block, age) and lets you change the API address.

Force a source: `?source=recorded`, `?source=live`, `?api=http://host:8000`, `?holder=0x…` (or `?holder=book:rockawayx`, the curator book; `?holder=vault:0x…`, one whole vault), or at build time
`VITE_SOURCE=recorded|live` and `VITE_API_URL=…`.

In recorded mode, only the recorded pockets have their full details (Belem RWA EURCV: graph, risk, incident; the
PST/USDC borrow: risk). For the others, the front shows the portfolio row and says the details are computed live:
it never makes up a response.

More recordings: `PYTHONPATH=src python -m stacktrace.record book:rockawayx` (from the repo root, live RPC) writes every
answer into `docs/api_examples/recordings/<holder>/`. Commit it: the front and the replay server pick up every
folder there by themselves, and the portfolio slide offers each recorded holder as a one-click choice.

### Live

At the root of the repository, with `ETH_RPC_URL` in `.env`:

```bash
PYTHONPATH=src python -m stacktrace.api          # http://127.0.0.1:8000
```

The first computation for a block is slow (docs/API.md): `/pockets` ~5 s, `/risk` 10 to 30 s, `/book` ~1 min 30. The
front orders its calls so the displayed pocket arrives first: pockets → risk of the pocket → graph and portfolio.

### Replay server (live mode without an RPC)

```bash
npm run replay-api -- --port 8000 --latency 1500
```

It answers the real API routes with the recorded responses (same error codes: 404 with the list of pockets, 422 for
validation). A request that was not recorded gets an explicit 422, never a made-up response. `--latency` simulates the
slowness of the first call.

## What the front computes, and what it does not

It computes **no risk**. Every loss, cost, threshold or verdict number comes from the API. It only does:

- graph traversals: layered layout, path between the pocket and a node ("who is hit if X breaks"), share of the
  pocket that goes through a node (product of the edge weights along the widest path);
- the comparison of your estimate with the **p\*** threshold the backend publishes ("exit if you believe in more
  than p\*") until the exact `/incident` computation comes back, or in recorded mode. The text then says it is the
  threshold rule.

## Structure

```
src/
  api/types.ts          API contract (docs/API.md)
  api/client.ts         HTTP calls, timeouts, FastAPI errors
  api/recorded.ts       recorded responses (docs/api_examples/)
  api/source.tsx        live or recorded source, API detection
  api/hooks.ts          React Query requests and call ordering
  state/selection.tsx   holder, pocket, incident; combined view of a pocket
  lib/graph.ts          graph layout and paths (no risk)
  lib/format.ts         en-US numbers ("$643", "0.6%"), matching the backend's sentences
  components/           header, source pill, rail, graph, evidence sheet, states
  slides/               the 7 slides
scripts/replay-api.mjs  replay server
```

React 18, TypeScript, Vite, Tailwind CSS 3, react-force-graph-2d, Framer Motion, TanStack Query.

## Design

Black background, a single accent blue, three state colours used for nothing else: green STAY, red EXIT, amber for
whatever does not follow the market. Two font weights. No borders or shadows: space separates. The verdict is the
largest text in the deck.
