# Dependency Risk — stay or exit

A single-screen tool for one question a portfolio manager asks at 3am during an
incident: **should we stay in this position, or exit?**

It discovers what a DeFi position actually depends on, prices the loss that
dependency set implies, and turns the two numbers into a signal.

Built for the BelemCapital EPFL Hackathon 2026 — *DeFi Risk Dependency Challenge*.

---

## Run it

```bash
npm install
npm run dev      # http://localhost:5173
```

```bash
npm run build    # typecheck + production bundle
npm run preview  # serve the build
```

Node 20+. No API keys, no backend — the dataset ships with the app and renders
immediately.

---

## The screen

One idea per section, top to bottom.

**A — Analyse a position.** Paste a contract address or pick one of three
presets: Pendle PT-sUSDE (Ethereum), Aave USDC supply (Ethereum), Kamino SOL
vault (Solana). Three real addresses resolve; anything else falls back to the
current position and says so.

**B — Dependency graph.** Five layers deep, laid out along the depth axis —
settlement chain at the start, your position at the end. Node colour is the
layer, node size is the capital at risk inside that dependency, and arrows
follow the direction risk travels. A live incident gets a pulsing red ring.
Click any node for its probability, its loss-given-incident and what it
contributes to the total.

**C — The decision.** Expected loss and where it comes from on the left; STAY or
EXIT, the one-line reason and the confidence on the right. The scenario toggle
opens four stress levers that re-run the model as you drag them.

---

## How the loss number is built

Nothing in the UI is a hand-written total. Every dependency carries two inputs:

| input | meaning |
| --- | --- |
| `incident_prob` | probability of a loss-causing incident over 30 days |
| `loss_given_incident` | share of position value lost if it happens |

A node contributes `p × LGD`. Expected loss is the sum across the dependency
set. The stacked bar is that sum grouped by layer, so the bar and the headline
can never disagree.

The decision rule is a comparison, not a score:

```
EXIT  when  expected loss  >  execution cost to exit
STAY  otherwise
```

Execution cost is slippage + market impact + gas. The **break-even threshold**
is the exit cost expressed as a multiple of today's expected loss — how much
worse things have to get before the verdict flips. Because expected loss is
linear in oracle failure probability, the app also solves for the exact oracle
probability that reaches break-even, and says so in plain English.

Confidence is derived, not asserted: it comes from the margin between expected
loss and exit cost, capped by the confidence published with the dataset, and
drops one tier whenever a scenario lever has been moved by hand.

### Scenario levers

| lever | range | what it scales |
| --- | --- | --- |
| Oracle failure probability | 0–100% | layer 3 incident probability |
| Liquidation cascade factor | 1×–5× | layer 5 incident probability |
| Slippage on exit | 0–30% | the slippage component of exit cost |
| TVL drain speed | Slow / Fast | layers 1, 2 and 4 incident probability |

The **Stress** preset doubles every one of them, so expected loss lands at
exactly 2× the base case — by construction, not by a magic multiplier.

---

## Data

`src/data/mock.ts` is a 09 Oct 2026 snapshot: dependency sets, TVL, incident
probabilities and exit-cost decompositions for the three positions, with the
transmission path written out for every node. The module is the contract —
swapping it for an indexer adapter runs the same engine on live chain state
without touching a component.

---

## Structure

```
src/
  data/mock.ts                 positions, dependency edges, per-node risk inputs
  lib/risk.ts                  the engine: scenarios in, assessment out
  components/
    PositionInput.tsx          section A
    DependencyGraph.tsx        section B
    NodePanel.tsx              node detail drawer
    RiskSignal.tsx             section C, left — impact breakdown
    VerdictPanel.tsx           section C, right — stay / exit
    ScenarioDrawer.tsx         stress levers
  App.tsx
```

React 18 · TypeScript · Vite · Tailwind CSS v3 · react-force-graph-2d ·
Framer Motion (drawer transitions only).

---

## Design

Dark, Apple-minimal, deliberately plain. Black ground, one accent blue, and
three status colours — green, amber, red — that only ever mean safe, warning and
risk. Two font weights. No borders, no shadows, no gradients: whitespace does
the separating. The verdict is the largest thing on the page because it is the
only thing that matters at 3am.
