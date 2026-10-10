# Demo script (5 minutes): "at 3 a.m., Léa has only one question"

Common thread: the questions of Léa, the on-call risk manager (framing note §1).
1. Am I exposed, and through which path?
2. How much can I lose?
3. How much does exiting cost?
4. Do I exit everything, part of it, or do I wait?

Numbers: real responses recorded at block **#26162868** (`docs/api_examples/`), replayed **without network**.

## Before the demo (once)
```bash
python -m pytest -q
```
```bash
cd front && npm install && npm run dev
```
Open http://localhost:5173 in full screen (1280 px or more). The pill at the top right must say **Recorded**.
**Turn off the Wi-Fi**: everything must work.

"Live" option (RPC required, `/book` takes ~1 min 30 on the first call): `PYTHONPATH=src python -m stacktrace.api`,
then choose "Live" in the pill. Only do this after warming up the API.

---

## 0:00 — The portfolio (30 s)
**Screen:** slide 1, 11 pockets, $26.4M.
**Say:** "We start from a single real address. The tool finds all its pockets, and every amount is proven on-chain
at the same block. The brief talks about a book in ten pockets: here is a real one."

## 0:30 — The verdict for one pocket (40 s) — *Decision, 25%*
**Action:** pocket **Belem RWA EURCV**, slide 2.
**Say:** "STAY. Exiting now costs $643, but only 22% of the pocket can be withdrawn right away. The threshold:
exit if you put the main risk above 0.6%."

## 1:10 — Which path? (60 s) — *Discovery, 30%*
**Action:** slide 3, hover over the mGLOeuro market, click an edge to show its evidence.
**Say:** "The graph is built by the code: vault, adapters, markets, collaterals, oracles. Every edge carries its
evidence: contract, function, result, block. And it reveals the hidden concentration: 85.8% of the vault is lent against a single
collateral, mGLOeuro, whose price is set by an administrator. It does not follow the market."

## 2:10 — How much do I lose, what does exiting cost (50 s) — *Impact, 30%*
**Action:** slides 4 and 5.
**Say:** "If mGLOeuro loses value, its oracle does not move: nobody is liquidated in time, and it is the borrowers'
bad debt that the lenders pay, computed borrower by borrower."
**Action:** move on (→) to the pocket **Borrow USDC against PST**, slide 5.
**Say:** "Here, exiting costs 13% of the capital, and beyond 25% of the debt the market can no longer absorb the
sale. That is the brief's trade-off: exiting is expensive and certain; staying is cheap, but uncertain."

## 3:00 — What if it happens? (70 s) — *Decision, 25%*
**Action:** go back to **Belem RWA EURCV**, slide 6, incident "mGLOeuro collateral drop", severity 30%.
Raise "Your estimate" from 0 to 20%.
**Say:** "We do not ask Léa to estimate a loss: we ask her whether she believes in more than p\* (here 0.7% over the week, i.e. an event that happens roughly
once every 3 years). Above the threshold,
the verdict flips to EXIT, and only for the part that can be exited now: 22%."

## 4:10 — Concentration (30 s)
**Action:** slide 7.
**Say:** "Morpho is present in all 11 pockets, Chainlink ETH/USD in 4, Circle in 4: the same dependency
hidden in several pockets."

## 4:40 — Closing line (20 s)
"Every number has a status: sourced, on-chain, or displayed hypothesis. Our probabilities are hypotheses: that is
why the decision rests on p\*. At 3 a.m., Léa has only one question: do I believe in more than p\*?"

---

## Plan B if something breaks
- Blank page → check that `npm run dev` is running, reload; force `http://localhost:5173/?source=recorded`.
- Nothing works anymore → in a terminal: `PYTHONPATH=src python -m risk.run` (risk sheet for position A, offline).
