# Prompt to finish the project (parts 2 and 3 + "X-Ray" front end)

## Before launching
1. **Put the Belem brief in the repo** as `docs/BRIEF.md` (copy-paste of the text, or the PDF in `docs/`). The prompt relies on it to know exactly what parts 2 and 3 ask for. Without a brief, it will start from the hypothesis written below and will flag it to you.
2. Open a Claude Code session on the repo, branch `feature/discovery-position-a` up to date, at maximum effort.
3. Paste **the whole block below**.

---

```text
You are the Tech Lead of the StackTrace team (Belem DeFi Risk hackathon). You work AUTONOMOUSLY during a
long session: the team (3 beginners) reads in the meantime and will come back afterwards to understand everything and refine it.
Your goal: deliver PARTS 2 AND 3 of the project, with an "X-Ray" front end that can be demonstrated offline.

══════════════════════════════════════════════════════════════════════════════
0. READ BEFORE ANYTHING ELSE (skip nothing)
══════════════════════════════════════════════════════════════════════════════
- CLAUDE.md in full (rules, FROZEN vocabulary, method), README.md, docs/BEGINNER_GUIDE.md,
  docs/POSITION_A.md, docs/CONTRACT.md, docs/AUDIT.md, docs/NEXT_STEPS.md, then output/graph.json.
- docs/BRIEF.md (or the brief's PDF in docs/): it is THE reference for the exact content of parts 2 and 3
  and for the grading criteria. Summarise for me in 10 lines what parts 2 and 3 ask for and how
  they are graded, then carry on without waiting.
- If there is NO brief: start from the following hypothesis, write it at the top of docs/PARTS_2_3.md, and flag it
  in your final report:
    Part 2 = risk engine: propagate shocks through the graph and measure the effect on the position;
    Part 3 = presentation: an interface that makes the graph, the evidence and the scenarios understandable.

══════════════════════════════════════════════════════════════════════════════
1. NON-NEGOTIABLE RULES
══════════════════════════════════════════════════════════════════════════════
- The Discovery Module (src/discovery/, output/graph.json, data/cache/) is FINISHED and its JSON contract is
  FROZEN. You CONSUME it, you do not modify it. Exception: a real bug, which you fix with a test and which
  you record in docs/AUDIT.md.
- Zero hallucination, as for discovery:
  · no address or endpoint taken from your memory;
  · NO invented risk parameter (liquidation bonus, Morpho formulas, thresholds...). Every parameter lives
    in a risk/params.yaml file with, as appropriate:
      `source: <official URL>` (Morpho, Pendle, Ethena, Chainlink, Steakhouse docs...) + `as_of`, or
      `source: onchain` (already in graph.json, cite the field), or
      `hypothesis: true` + a one-sentence justification (scenario parameter chosen by us).
    The front end displays these three statuses differently. A strict loader rejects a parameter without a status.
  · Example: Morpho Blue's liquidation incentive formula (a function of the LLTV) must be found in
    Morpho's official docs or code, with the URL. Do not copy it from memory.
- Everything must work OFFLINE for the demo: no CDN at runtime, no remote font, no network call
  from the front end. The JS libraries are copied into the repo (vendor) with their version and their licence.
- Stack: Python 3.11 (risk engine, like discovery: web3.py is NOT needed, we read graph.json),
  networkx. Static front end: HTML + CSS + JavaScript with no build step, served by `python -m http.server`.
  At most one vendored graph library (e.g. D3 or Cytoscape.js, pinned version).
  Justify your choice in 3 lines.
- Pedagogy (CLAUDE.md): every module starts with a docstring that explains the concept as in
  BEGINNER_GUIDE.md (analogies, zero undefined jargon). No big opaque blocks.
- Git: new branch feature/risk-and-xray from feature/discovery-position-a. Small and
  frequent commits, with a clear message. Push at the end (and at every big step). Do not touch main.

══════════════════════════════════════════════════════════════════════════════
2. PART 2 — RISK ENGINE (src/risk/)
══════════════════════════════════════════════════════════════════════════════
Goal: answer "if SUCH a shock happens, what becomes of position A?", relying ONLY on graph.json
and risk/params.yaml.

2.1 Propagation model (src/risk/propagate.py)
  - A shock = (target node, nature, intensity, duration). It propagates AGAINST the arrows (project
    convention: from = dependent, to = dependency).
  - One rule per edge type, documented and tested:
      redeemable_into: the value of the `from` follows that of the `to` (× internal rate read from meta);
      issued_by / deployed_in towards the off-chain layer: an issuer or counterparty shock translates into
        an impairment of the issued asset (intensity = scenario parameter, hypothesis: true);
      priced_by: an oracle transmits the shock ONLY according to its pricing_mode (market transmits, fixed does not
        transmit, internal_rate transmits only a shock on the rate, hybrid = meta-oracle logic);
      collateralized_by / lends: the market absorbs the change in the collateral / the lent asset.
  - META-ORACLE: faithfully simulate the rule sourced in meta.switch_rule (deviationThreshold threshold, challenge
    timelock, healing), with the deviation formula from the Steakhouse docs. This is THE strong point of our analysis:
    the duration of the shock matters as much as its size.
  - No network caching is needed (no network call), but the computation must be deterministic.

2.2 Effect on the position (src/risk/position.py)
  - From meta.position: new oracle price → new health factor → liquidatable yes/no.
  - If liquidatable: estimated loss = liquidation bonus (SOURCED formula) + collateral exit cost.
  - Exit cost: price slippage on the Pendle pool. Start with a simple, documented model
    based on reserve_pt / reserve_sy (say honestly that it is an approximation). If you have time,
    replace it with an ON-CHAIN simulation via Pendle's RouterStatic: address and function name found
    in the official docs, call made through the discovery cache (prompt S2 of docs/NEXT_STEPS.md).
  - On the lenders' side too: potentially bad debt (collateral × true price < debt) when the oracle
    is fixed and does not see the shock.

2.3 Scenarios (risk/scenarios.yaml), at a minimum:
  - S-USDe: USDe depeg to {$0.99, $0.98, $0.95, $0.93, $0.90, $0.85} × duration {1 h, 6 h, 16 h, 24 h, 72 h};
  - S-EXCH: failure of one of Ethena's hedge exchanges (Binance alone, then several) → hypothetical
    impairment of USDe (parameter hypothesis: true, clearly displayed);
  - S-CUST: failure of a custodian (Copper / Ceffu / Fireblocks);
  - S-ORACLE: Chainlink USDe/USD feed frozen or wrong;
  - S-POOL: Pendle pool liquidity divided by 2 / by 10;
  - S-USDC: USDC depeg (the borrowed asset);
  - S-TIME: simple passage of time until maturity (the PT converges to 1, the debt accrues at borrow_apy).

2.4 Outputs
  - output/risk.json: a contract you define, documented in docs/RISK_CONTRACT.md (fields, units, meaning).
    For each scenario: propagation path (list of graph.json edges, with their evidence), oracle price
    before/after, health factor before/after, liquidatable, estimated loss, who loses (borrower / lenders),
    and the list of parameters used with their status (source / onchain / hypothesis).
  - output/risk_grid.json: the USDe grid (price × duration) precomputed, to feed the front end's slider.
  - A synthetic risk score ONLY if the brief asks for it. Otherwise, do not make one up: expose
    clear metrics.
  - CLI: `python -m risk.run` (reads output/graph.json, writes output/risk*.json, prints a summary in English).
  - risk.json validator (like discovery/validate.py) run on every run.

2.5 Tests (tests/risk/)
  - unit propagation rules (small hand-made graphs);
  - meta-oracle: short shock → no switch; long shock → switch; healing;
  - consistency: zero shock → HF unchanged; HF after switch = HF × (backup price / primary price);
  - the thresholds in POSITION_A.md (switch as soon as USDe < ~$0.9925; liquidation below ~$0.9525 after 16 h)
    must come out of the engine NATURALLY. Otherwise, find out who is wrong (the engine or the doc) and fix it.

══════════════════════════════════════════════════════════════════════════════
3. PART 3 — "X-RAY" FRONT END (web/)
══════════════════════════════════════════════════════════════════════════════
Concept: we put position A "through the X-ray". What looks like a simple deposit + a loan reveals
its SKELETON: all the hidden layers down to Ethereum and the off-chain companies.

Art direction:
  - near-black bluish background, lines and nodes in cyan / bright white (glow), slight
    radiographic film texture, discreet calibration grid, mono typography for the data;
  - a horizontal SCAN LINE that sweeps the screen on load and reveals the layers one by one, from top to
    bottom: Position → Morpho market → Oracle(s) → PT / Pendle pool → SY → sUSDe → USDe → Ethena → custodians /
    exchanges → Ethereum;
  - a layout in HORIZONTAL LAYERS (like vertebrae), not a "spaghetti ball" graph:
    dependency depth reads from top to bottom;
  - colour code for the EVIDENCE on each edge: onchain = bright solid line, api = dotted,
    curated = thin amber line + "dated document" icon;
  - colour code for the PRICE on the oracles: fixed / market / internal_rate / hybrid (visible legend);
  - when a scenario is active, the "fractures" appear in red/magenta and propagate along the
    path, like a crack on an X-ray.
  - Respect prefers-reduced-motion (no animation if the user declines it) and a readable contrast.

Features (in this order of priority):
  1. "Skeleton" view of graph.json: hover = plain name; click = side panel "bone card":
     plain-language explanation of the node type (text taken from the glossary in BEGINNER_GUIDE.md), useful meta
     (price, TVL, pricing mode, upgradeable proxy?), and the list of edges with their full EVIDENCE
     (Etherscan link for addresses, clickable URL for api/curated, block number).
  2. "Vital signs" banner for the position: HF, LTV / LLTV, distance to liquidation, value,
     debt, snapshot block and date.
  3. SCENARIO mode: a USDe price slider + a duration slider, wired to risk_grid.json (no risk
     computation in the JS: it only reads the results of the Python engine, the single source of truth). Shows
     the state of the meta-oracle's referee (primary / challenge in progress / switched), the HF, and
     "LIQUIDATED / not liquidated / lenders exposed".
  4. IMPACT mode: click a node (e.g. Binance), "what happens if it breaks?", and the path to the
     position lights up (ancestors computed from graph.json).
  5. List of the risk.json scenarios (cards); click = the fracture animates on the skeleton.
  6. "Explain it to me" mode: a guided tour in 6-8 steps that tells Alice's story (BEGINNER_GUIDE
     §9) while highlighting the layers. This is what we will show the jury.
- Data: the front end loads output/graph.json, output/risk.json and output/risk_grid.json (copied or served
  from web/data/ by a small script `python -m risk.export_web`). If a file is missing, a clear message.
- Launch: `python -m http.server 8000 -d web` → http://localhost:8000. Docs in web/README.md.
- Check VISUALLY with the built-in browser: screenshots of the loading, of the full view, of a
  click on a node, of a USDe $0.93 / 24 h scenario, of Binance impact mode, and at mobile width (375 px).
  Fix whatever is ugly, unreadable or overflows. Keep 3-4 screenshots in docs/screens/ for the README.

══════════════════════════════════════════════════════════════════════════════
4. WORKING METHOD (mandatory)
══════════════════════════════════════════════════════════════════════════════
- Order: (a) minimal risk engine + tests → (b) risk.json + grid → (c) skeleton front end + bone card
  → (d) scenarios + impact → (e) guided tour + visual polish → (f) docs and demo.
  The front end must be showable from the end of (c), in case time runs out.
- After EACH step: AUDIT of the whole project against the brief, CLAUDE.md and this prompt (unsourced
  parameter? evidence lost along the way? broken contract? missing test? front end calling the network? text
  incomprehensible to a beginner?). Fix, then record the audit in docs/AUDIT.md (same format as
  audits 1 to 4). Start again until the audit finds nothing important.
- `python -m pytest` must stay green from start to finish (including the 67 discovery tests).
- Before the final push: simulate a teammate, with a fresh clone, without network → tests, `python -m risk.run`,
  front end served locally, everything works.

══════════════════════════════════════════════════════════════════════════════
5. EXPECTED DELIVERABLES
══════════════════════════════════════════════════════════════════════════════
- src/risk/ (+ tests), risk/params.yaml, risk/scenarios.yaml, output/risk.json, output/risk_grid.json
- web/ (index.html, css, js, vendor/ with versions and licences, README.md)
- docs/PARTS_2_3.md: what parts 2 and 3 ask for (according to the brief) → what we did → where it is
- docs/RISK_CONTRACT.md, docs/DEMO.md (5-minute demo script, PowerShell AND bash commands, what to say
  on each screen), docs/screens/
- docs/BEGINNER_GUIDE.md extended with 2 new chapters in the SAME very plain-language style:
  "How we measure risk" and "How to read the X-Ray"
- README.md updated (screenshots, commands), docs/AUDIT.md extended
- Final report in the chat: what is done, what is not, the hypotheses (parameters
  hypothesis: true), the decisions the team must validate, and the 5 most important points to
  understand for the final presentation.
```

---

## What this prompt guarantees (and why it is written this way)
- **The brief is authoritative.** I do not know the exact text of parts 2 and 3. The prompt therefore forces reading it first, and otherwise writing down in black and white the hypothesis adopted.
- **No hallucination on the risk side either.** Every number in the engine has a visible status: sourced, on-chain or hypothesis. The jury will see the same rigour as in discovery.
- **A single source of truth.** Python computes, the front end displays. No second risk engine hidden in the JavaScript.
- **A failure-proof demo.** Everything works offline, including the JS libraries.
- **A front end that can be shown early.** The working order makes it possible to have something to show even if the session is cut off.
- **You stay in control.** The beginner guide is extended, the demo is written, and the final report lists what you must validate.
