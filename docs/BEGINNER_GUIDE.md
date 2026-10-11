# A guide for complete beginners: understanding our project without knowing anything about blockchain

> **Who is it for?** The three of us, starting from zero.
> **How to read it?** In order, chapter by chapter. Every technical word is explained the first time it appears, and it is also in the **glossary** at the end.
> **Reading time:** about 1 hour (45 min for chapters 1-12, 15 min for risk and the front). Take your time: the whole rest of the project rests on this.

---

## Contents
1. [What is a blockchain?](#1-what-is-a-blockchain)
2. [Tokens: digital money](#2-tokens-digital-money)
3. ["Smart contracts": vending machines](#3-smart-contracts-vending-machines)
4. [Digital dollars: USDC and USDe](#4-digital-dollars-usdc-and-usde)
5. [Growing your money: sUSDe, the piggy bank](#5-growing-your-money-susde-the-piggy-bank)
6. [Pendle and the PT: the digital Treasury bond](#6-pendle-and-the-pt-the-digital-treasury-bond)
7. [Borrowing with Morpho: the pawnbroker](#7-borrowing-with-morpho-the-pawnbroker)
8. [The oracle: the expert who appraises the pledge](#8-the-oracle-the-expert-who-appraises-the-pledge)
9. [Position A told as a story](#9-position-a-told-as-a-story)
10. [Dependencies: a game of dominoes](#10-dependencies-a-game-of-dominoes)
11. [Our mission: playing detective](#11-our-mission-playing-detective)
12. [Reading our graph.json file without panicking](#12-reading-our-graphjson-file-without-panicking)
13. [How we measure risk](#13-how-we-measure-risk)
14. [How to read the front](#14-how-to-read-the-front)
15. [Glossary](#15-glossary)
16. [A short quiz to check we understood](#16-a-short-quiz-to-check-we-understood)

---

## 1. What is a blockchain?

### The picture to remember: a big public ledger
Imagine a **giant ledger** in which every operation is written down: "Alice gives €10 to Bob", "Bob gives €3 to Chloé"…

In a traditional bank, this ledger is **private**: only the bank has it, and you have to trust it.

In a **blockchain**, this ledger is:
- **public**: anyone can read it, at any time, for free;
- **copied** onto thousands of computers around the world: nobody can forge it on their own;
- **indelible**: what is written stays written.

### Why "chain of blocks"?
Operations are not written one by one. They are grouped into **pages**, called **blocks**. On **Ethereum** (the blockchain we use), a new page is added roughly **every 12 seconds**. Each page has a **number** and is glued to the previous one: that is the "chain".

> 💡 **Why it matters for us:** when we read information, we say "**at block #26,162,087**". It is like saying "according to page 26,162,087 of the ledger", or like taking a **photo** at a precise moment. All our data comes from the same photo, so it is consistent and anyone can re-check it.

### Ethereum
There are several blockchains. **Ethereum** is the most used for finance. In our project, everything happens on Ethereum "mainnet" (the real network, with real euros… well, real dollars, as we'll see).
- **mainnet** = the real network (≠ test networks)
- **chain ID = 1** = the identification number of Ethereum mainnet. Our program checks that it is really talking to network #1.

### An address
On the blockchain, every person and every program has an **address**. It is like an account number (IBAN), but it looks like this:
```
0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
```
It is long, unreadable, and a single wrong letter sends you somewhere else. **That is why we never copy an address from memory**: we read it from an official source and we check it.

### How do we "read" the blockchain? (RPC)
Our program does not have its own copy of the ledger: it is huge. It asks its questions to a server that has a copy. This server is called a **node**, and the "counter" where you ask it questions is called an **RPC**.
> Analogy: the RPC is the **library's front desk**. You ask "what does page X say about this topic?", and the librarian goes to read it and answers.

**Reading is free.** Writing (making an operation) costs fees. Our project **only reads**.

---

## 2. Tokens: digital money

A **token** is a **line in the ledger** that says "this address owns so many units of this token". There are thousands of different tokens: digital dollars, investment shares, IOUs…

All tokens that follow the same "standard" behave the same way. The most common standard is called **ERC-20**. It is like a **standard electrical socket**: any application knows how to plug in any ERC-20 token.

An ERC-20 token can always answer a few basic questions:
| Question | Example answer |
|---|---|
| `symbol()`: what is your name? | "USDC" |
| `decimals()`: how many digits after the decimal point? | 6 |
| `totalSupply()`: how many exist in total? | 48 billion |
| `balanceOf(address)`: how many does this address own? | 1,000 |

> 💡 **Decimals, a classic trap:** the blockchain does not know about decimal points. It stores whole numbers. With 6 decimals, "1 USDC" is stored as `1000000`. Our program does the conversion for you.

---

## 3. "Smart contracts": vending machines

A **smart contract** is a **program placed on the blockchain**. It has an address, like a person, and it runs on its own according to rules written in advance.

> **The picture to remember: the drinks vending machine.** You put in €2, you press B4, and the can drops. Nobody decides: the machine applies its rules. And you can read through the glass how many cans are left.

Tokens themselves are smart contracts. So are lending, exchange and investment platforms. Everything we study is made of smart contracts talking to each other.

### How do we query a contract?
We call one of its **read functions**. For example, we ask the PT contract "who is your SY?" by calling `SY()`, and it answers with an address.

If we call a function that **does not exist** on this contract, it refuses (we say it "**reverts**"). This refusal is very useful to us: by trying several functions, we figure out **what** an unknown contract is. This is called **probing** a contract.
> Analogy: you find an unknown machine. You press "coffee": nothing. "Train ticket": a ticket comes out. Now you know it is a ticket machine.

### DeFi
**DeFi** = *Decentralized Finance* = finance done with smart contracts, without a bank: lending, borrowing, investing, exchanging. It is the topic of the hackathon.

---

## 4. Digital dollars: USDC and USDe

On the blockchain, the price of cryptocurrencies (like ETH) moves a lot. So tokens were created that are **always worth about 1 dollar**: **stablecoins** ("stable coins").

### USDC: the "classic" dollar
- It is issued by an **American company, Circle**.
- For each USDC in circulation, Circle keeps **1 real dollar** in the bank (or in Treasury bills).
- **Analogy:** a **cloakroom ticket**. You hand in $1, you receive a ticket; you give back the ticket, you get your dollar back.
- **Risk:** you have to trust Circle, which can also freeze accounts or change its contract (our program actually detected that the USDC contract is **modifiable** by Circle, an "upgradeable proxy").

### USDe: the dollar "manufactured" by Ethena
USDe is more subtle. **Ethena** does not keep dollars in the bank. It keeps **cryptocurrencies** (ETH, bitcoin…) and **bets against them at the same time**, for the same amount.

> **The picture to remember: umbrellas and sunscreen.** You sell umbrellas and sunscreen. If it rains, you win on the umbrellas and lose on the sunscreen; if it is sunny, it is the other way round. **Overall, your till does not move, whatever the weather.**
>
> Ethena does the same: it **owns** 1 ETH and **bets** that ETH will go down, for the same amount. If ETH goes up, it wins on one and loses on the other. Overall, the value stays stable, about 1 dollar per USDe.

**Words to know:**
- **hedge**: the opposite bet that neutralises the price moves;
- **perpetual contracts ("perps")**: the betting tool, found on **centralised exchange platforms** ("exchanges") such as Binance, Bybit, OKX…;
- **custodians**: companies that **keep** Ethena's crypto safe, like a safe (Copper, Ceffu, Fireblocks).

**⚠️ The crucial point for our project:** all of this (which safe, which exchange, how much) **is NOT written in the public ledger**. It happens in the real world, off-chain. We can only know it **through what Ethena publishes** on its website. That is exactly what we store in our `curated.yaml` file, with the link and the date (see chapter 11).

### "Depeg": when the digital dollar is no longer worth $1
A stablecoin is supposed to be worth $1. If it starts being worth $0.95, we say it "**loses its peg**", or *depegs*. For USDe, this could happen if an exchange goes bankrupt, if the bets cost too much for too long, etc. **All our risk work revolves around this question: what happens to us if USDe "depegs"?**

---

## 5. Growing your money: sUSDe, the piggy bank

USDe on its own earns nothing. But Ethena offers to **deposit it into a piggy bank** that pays interest. The interest comes from its bets (the people on the other side of the bets pay a small regular fee) and from staking.

When you deposit your USDe, you receive **sUSDe** ("s" for *staked*, "deposited").

> **The picture to remember: shares of a growing kitty.** You put €100 into a shared kitty and receive 100 "shares". The kitty earns interest, but the number of shares does not change: it is **the value of each share that goes up**.

What our program read at block 26,162,087:
- **1 sUSDe = 1.2523 USDe.** Whoever deposited early has gained 25% since.
- To get your USDe back, you have to **wait 1 day** (the "cooldown", the withdrawal delay).

This piggy-bank standard is called **ERC-4626**. The function `convertToAssets()` answers the question "how much is 1 share worth?".

> 💡 **Internal rate ≠ market price.** "1 sUSDe = 1.2523 USDe" is an **accounting** calculation done by the piggy bank itself. If tomorrow everyone wants to flee sUSDe, this number will not go down on its own. The **price at which people are willing to buy it**, on the other hand, could go down. We call the first one an "**internal rate**", and we carefully distinguish it from a "**market price**".

---

## 6. Pendle and the PT: the digital Treasury bond

### Pendle's idea: separating capital and interest
**Pendle** is a platform that takes an investment that pays (here sUSDe) and **cuts it into two pieces**:
- the **PT** (*Principal Token*): it entitles you to the **capital at a fixed date**;
- the **YT** (*Yield Token*): it entitles you to **the interest** until then.

> **The picture to remember: the rented house.** A house brings in rent. Pendle lets you sell separately:
> - **the right to get the house back on November 26** (that is the PT);
> - **the right to collect the rent until then** (that is the YT).

### The PT is a zero-coupon bond
The PT in our position is called **PT-sUSDE-26NOV2026**. It promises: "**on November 26, 2026, this token will be worth 1 USDe**".

Since it pays nothing until then, it sells **for less** before that date. Today (46 days before), it is worth about **0.993 USDe**. Whoever buys it at 0.993 and waits gains 0.007: that is their "fixed interest".

> **Analogy:** a **€100 voucher valid on November 26**, which you buy for €99.30 today. The closer the date, the closer it is to €100.

### The SY: the adapter
To be able to cut any investment, Pendle first wraps it in a standard format, the **SY** (*Standardized Yield*). Here, **SY-sUSDE** is a wrapper around sUSDe.
> **Analogy:** the **travel plug adapter**. Pendle can only talk to SYs; the SY talks to sUSDe.

The full chain, when you "walk back up" from the PT:
```
PT-sUSDE  →  redeems into  →  SY-sUSDE  →  which contains  →  sUSDe  →  which contains  →  USDe
```

### The pool: the currency exchange office
If you want to sell your PT **before** November 26, you need someone to buy it. Pendle has a **pool** (an "exchange reserve") where PTs are swapped for SYs at any time. This kind of automatic exchange program is called an **AMM** (*Automated Market Maker*).
> **Analogy:** a **currency exchange office** with two drawers, one of PT, one of SY. You put PTs into one drawer and take SYs from the other. The exchange rate moves according to what is left in each drawer.

**Why the pool's size matters:** our pool holds about **$3.8 million**. If someone has to sell much more than that at once, they empty the drawer and the price collapses. Like a small exchange office that does not have enough banknotes.

---

## 7. Borrowing with Morpho: the pawnbroker

### The picture to remember: the pawnshop
You have a valuable watch. You leave it as a **pledge** with the lender, who lends you money in exchange. If you repay, you get the watch back. If the watch's value falls too much compared to what you owe, the lender **sells it** to get repaid.

**Morpho** does exactly that, with smart contracts.
- **The pledge**, called **collateral**: our PT-sUSDe.
- **The money lent**: USDC.
- **Who lends?** Other people, or investment "safes" (**vaults**), which deposit their USDC to earn interest. Here, it is mostly a vault named "Pendle Ecosystem USDC".

### A Morpho "market"
Morpho is **one single big program** that contains thousands of small separate "counters", called **markets**. Each market has its rules, set once and for all:
1. which token is lent (USDC);
2. which token serves as the pledge (the PT);
3. who gives the price of the pledge (the **oracle**, chapter 8);
4. how the interest rate is calculated;
5. how far you can borrow (the **LLTV**, see below).

Each market has an **identifier** (a long string of characters). This identifier is computed from these 5 rules: it is their **fingerprint**. Our program recomputes this fingerprint and checks that it matches, which proves we are reading the right market.

### The numbers that matter (with a simple example)
Let's take a round example before the real numbers. You deposit a pledge worth **€100** and you borrow **€87**.

| Term | Simple definition | Example |
|---|---|---|
| **LTV** (*Loan-To-Value*) | what I owe ÷ what my pledge is worth | 87 / 100 = **87%** |
| **LLTV** (*Liquidation LTV*) | the **limit** not to exceed, set by the market | **91.5%** |
| **Liquidation** | if my LTV exceeds the limit, anyone can repay my debt and **take my pledge with a bonus** | — |
| **Health factor** | how far I am from the limit. Above 1: fine. Equal to 1: I can be liquidated | 91.5 / 87 = **1.05** |

> With a health factor of **1.05**, if the estimated value of the pledge drops by about **5%**, we hit the limit and get liquidated.

**The real numbers of position A** (block 26,162,087):
- pledge: **413,030 PT**, valued at **409,872 USDC**;
- debt: **357,217 USDC** (interest included);
- LTV: **87.2%**, limit **91.5%**, health factor **1.050**;
- **liquidatable if the estimated PT price drops by 4.75%**;
- borrow rate: **3.7% per year**.

> 💡 **"Lagging" interest.** Morpho only updates interest when someone interacts with the market. In between, the displayed debt lags a little, like a taxi meter you only look at from time to time. Our program recomputes the missing interest the way Morpho would.

---

## 8. The oracle: the expert who appraises the pledge

### The problem
A smart contract is **blind**: it does not see the outside world and does not know "how much a PT is worth". Someone has to **tell it**. That someone is called an **oracle**.

> **The picture to remember: the pawnshop's expert.** The lender does not know what your watch is worth. They ask an expert. **If the expert says it is worth less, you are liquidated, even if the watch has not changed.**
>
> **Morpho trusts the oracle blindly.** Understanding the oracle means understanding **when** you can be liquidated.

### Two ways to appraise: fixed price, or market price
This is **THE key point** of the project.

| | **Fixed price ("fixed")** | **Market price ("market")** |
|---|---|---|
| Analogy | the expert gives the watch's **catalogue price** | the expert looks at **what it resells for** today |
| Advantage | does not panic if the market has a passing fit of madness | sticks to reality |
| Danger | if the watch **really** loses its value, the expert does not see it | a sudden, short-lived move can trigger liquidations |
| Who takes the risk? | the **lenders** (the pledge is worth less than announced) | the **borrowers** (us) |

There is a 3rd category, the **internal rate**: the expert asks the manufacturer itself (like the sUSDe piggy bank, chapter 5). It is not a market price either.

### Our own oracle: two experts and a referee
Our program discovered that the market uses a **meta-oracle** (designed by a company called Steakhouse). "Meta" means it oversees two oracles.

```
                  REFEREE (meta-oracle)
                 /                     \
   EXPERT 1 "catalogue"           EXPERT 2 "market"
   (active in normal times)       (backup)
   PT price = formula             PT price = formula
   that depends only on time      × real USDe price
   and assumes 1 USDe = $1        (provided by Chainlink)
```

- **Expert 1 (fixed price).** It applies a **formula**: "the PT is worth 1 minus a small discount that shrinks over time" (6% per year). Today, that gives 0.9924. On November 26, it will give exactly 1. **It never looks at the market**, and it **assumes 1 USDe is always worth $1**.
- **Expert 2 (market price).** Same formula, but **multiplied by the real USDe price**, provided by **Chainlink**, the biggest oracle company. If USDe falls to $0.95, its price drops by 5%.
- **The referee.** In normal times, it listens to expert 1. If the two experts **disagree by more than 0.75%**, anyone can raise their hand (a "challenge"). If the disagreement **still holds 16 hours later**, the referee **switches to expert 2**.

### What this means in practice (scenarios)
| If USDe is worth… | What happens to us? |
|---|---|
| more than $0.9925 | Nothing. The experts agree within 0.75%. |
| between $0.9525 and $0.9925 | After 16 h, the referee can switch to expert 2. Our health drops, **but we are not liquidated**. |
| **less than $0.9525 for more than 16 h** | The referee switches to expert 2, the estimated price drops by more than 4.75%: **we are liquidated**. |
| less than $0.9525 for **less** than 16 h | Expert 1 stays in charge, we are not liquidated. But during that time, **it is the lenders who are exposed**: the pledge is worth less than announced. |

> 🎯 **Key takeaway:** this system **ignores short panics** (good for us) but **follows long crises** (liquidation). The **16-hour** delay is the most important risk setting of our whole position.

---

## 9. Position A told as a story

Let's imagine **Alice**, who holds position A. Here is what she did, step by step:

1. Alice had **USDe** (Ethena's dollar).
2. She put them into Ethena's **piggy bank** and received **sUSDe**, which pay interest.
3. She took her sUSDe to **Pendle**: they were wrapped into **SY**, then cut, and she kept the **PT**, which will be worth 1 USDe on November 26, 2026.
4. She deposited her PTs as a **pledge** on a **Morpho** market, and **borrowed USDC** in exchange.
5. The price of her pledge is given by the **meta-oracle** (the two experts + the referee).

Why do this? With the borrowed USDC, Alice can buy more PTs, deposit them again, borrow again… and thus **multiply her fixed yield**. It is a classic setup, but **each step adds a risk**. These are the risks we map.

---

## 10. Dependencies: a game of dominoes

### The idea
If one piece of the setup breaks, everything "above" it falls. It is a **game of dominoes**. Our project draws **all the dominoes and their links**, so that another team can compute "if this domino falls, how much do we lose?".

### The drawing (simplified)
An arrow "A → B" means "**A depends on B**": if B breaks, A suffers.
```
ALICE'S POSITION
   │ is placed in
   ▼
MORPHO MARKET ──── lends ────► USDC ──── issued by ────► Circle
   │        └──── priced by ──► META-ORACLE ──► expert 1 (formula)
   │                                       └──► expert 2 (formula × Chainlink USDe/USD)
   │ backed by
   ▼
PT-sUSDe ──── tradable in ────► PENDLE POOL (exchange office, $3.8M)
   │ redeems into
   ▼
SY-sUSDe ──► sUSDe ──► USDe ──── issued by ────► Ethena
                                                 ├── keeps its crypto at → Copper, Ceffu, Fireblocks
                                                 └── places its bets on  → Binance, Bybit, OKX, Bitget, Deribit
And all of this "runs on" ──► Ethereum
```

### Examples of "falling dominoes"
- **Binance goes bankrupt** → Ethena's bets are hit → USDe can lose its peg → sUSDe, the SY and the PT lose value → if it lasts more than 16 h, the oracle sees it → **Alice is liquidated**.
- **The Pendle pool is too small** → liquidators cannot resell the seized PTs without breaking the price → they hesitate to liquidate → **the lenders risk not being repaid**.
- **Chainlink gets the USDe price wrong** → expert 2 is wrong → if the referee listens to it, unfair liquidation.

Our program can automatically answer "who falls if X falls?":
```bash
PYTHONPATH=src python -m discovery.inspect_graph --impact binance
```

### The arrow vocabulary (explained)
| Word in the file | In plain English | Example |
|---|---|---|
| `deployed_in` | "is placed in" | the position is placed in the market |
| `collateralized_by` | "is backed by" | the market is backed by the PT |
| `lends` | "lends" | the market lends USDC |
| `priced_by` | "gets its price from" | the market gets its price from the oracle |
| `redeemable_into` | "can be exchanged for" | the PT can be exchanged for SY |
| `issued_by` | "is issued by" | USDe is issued by Ethena |
| `settled_on` | "runs on" | everything runs on Ethereum |

---

## 11. Our mission: playing detective

### What we are asked to do
Our part of the project (the **Discovery Module**, 30% of the grade) must **find all the dominoes on its own**, starting from a single piece of information: the Morpho market identifier and Alice's address.

And above all: **prove every link**. No "I think that", no "from memory". The jury wants to see that **nothing is made up** (*no hallucination*).

### How the program investigates
Like a detective pulling on a thread:
1. It asks the Morpho market: "what are your 5 rules?". Answer: the pledge is contract 0xB195…, the oracle is 0xF8b2…
2. It asks contract 0xB195…: "who are you?". It **probes**: the contract answers `SY()` and `expiry()`, so it is a Pendle PT. "Who is your SY?" → 0xBF98…
3. It asks the SY: "what is inside you?" → sUSDe. It asks sUSDe: "what is your asset?" → USDe.
4. It takes the oracle apart the same way, expert by expert.
5. And so on, until there is no thread left to pull.

### The 3 types of evidence
Every link in the graph says **where it comes from**. There are three levels of evidence:

| Type | Analogy | Example | Reliability |
|---|---|---|---|
| **onchain** | an **official statement** read directly from the public ledger | "the PT contract answers that its SY is 0xBF98…, at block 26,162,087" | ⭐⭐⭐ verifiable by anyone |
| **api** | **information** given by a protocol's official website | "Morpho's API says this vault lends to this market" | ⭐⭐ we trust the website |
| **curated** | a **dated press clipping** | "Ethena's docs, consulted on 10/10/2026, say its custodians are Copper, Ceffu…" | ⭐ true on that date, can go stale |

> 💡 **"Curated"** means "hand-picked". It is what we checked ourselves in official sources, writing down the link and the date. We use it only for what **does not exist** on the blockchain (who is behind an address, where Ethena's safes are…).

When possible, we **combine**: we use the API to **find** the Pendle pool (the PT does not know its pool), then we **prove** it in the public ledger (the pool confirms that it really contains our PT).

### Why a "cache"?
During the demo in front of the jury, if the Wi-Fi goes down, we can no longer query the blockchain. So we **recorded all the answers** in the `data/cache/` folder.
> **Analogy:** we **photocopied every page** of the ledger we needed. On the big day, we read the photocopies: same result, no network.

Since all the questions were asked **at the same block** (the same "photo"), the photocopies are consistent and the result is identical every time.

---

## 12. Reading our graph.json file without panicking

`output/graph.json` is the **deliverable** the other teams use. It has three parts.

### 1) The position
```json
"position": {"id": "morpho:0x5613…:0x03BA…", "value_usd": 409816.56}
```
In plain English: "The position on Morpho market 0x5613…, of user 0x03BA…, is worth about $409,817."

### 2) The nodes (the dominoes)
```json
{"id": "usde", "type": "asset", "label": "USDe", "address": "0x4c9E…", "chain": "ethereum",
 "meta": {"price_usd": 0.9996, "tvl_usd": 4779918261, …}}
```
In plain English: "The domino `usde` is an **asset** (a token) called USDe, at address 0x4c9E… on Ethereum. It is worth $0.9996 and $4.78 billion of it exists."
- `type` says **what kind** of domino it is (token, oracle, market, company…);
- `meta` is a bag of extra information useful to the other teams.

### 3) The edges (the links between dominoes)
```json
{"from": "susde", "to": "usde", "type": "redeemable_into", "weight": 1.0,
 "source": "onchain", "evidence": "sUSDe.asset() = 0x4c9E… @ 0x9D39… #26162087 …"}
```
In plain English: "**sUSDe can be exchanged for USDe**, and the link is total (`weight` 1.0). It is proven **in the public ledger**: we asked the sUSDe contract (address 0x9D39…) what its asset was, at block 26,162,087, and it answered 0x4c9E… (USDe)."

The `evidence` field is **the proof**. Anyone can redo it.

---

## 13. How we measure risk

Chapters 1 to 12 answer "**what** does the position depend on?". This chapter answers the question the brief
really asks: **"should we stay or exit, and why?"**. That is the job of the **risk engine**
(`src/risk/`).

### The picture to remember: should you insure your car?
- Insurance costs a **certain premium** (you pay it for sure).
- Without insurance, you risk an **accident**: unlikely, but expensive.
- Insuring is worth it if "**probability of an accident × cost of the accident**" exceeds the premium.

For our position, it is the same thing:
- the "premium" is the **exit cost**: what it costs to sell everything now (certain);
- the "accident" is the **incident** (a depeg, a bankruptcy…), which would make us lose a sum if we stay.

### Step 1: imagine a shock
A **shock** is a sentence like "*USDe falls to $0.93 for 24 hours*". It has 4 ingredients:
**where** (which node of the graph), **what** (depeg, bankruptcy, outage…), **how much** (−7%) and **how long** (24 h).

### Step 2: knock down the dominoes
The engine pushes the shock up along the graph's arrows, with **one rule written in plain language per arrow type**:

| Arrow | Rule (in plain English) |
|---|---|
| "can be exchanged for" | if USDe loses 7%, sUSDe, the SY and the PT lose 7% too |
| "is issued by" | if Ethena loses part of its reserves, USDe loses the same share |
| "is placed in" (Ethena → Binance) | if Binance goes bankrupt, Ethena loses the small share of its reserves that was exposed there |
| "gets its price from" | a "catalogue" expert (fixed price) passes on **nothing**; a "market" expert passes on everything |

### Step 3: the referee and its 16-hour timer
Reminder from chapter 8: the oracle has two experts and a referee. The referee only switches to the "market" expert if the two
experts disagree **for 16 hours** (a figure read from the contract itself).
- USDe at $0.93 for **6 h**: the referee does not move, nothing happens. **Loss: $0.**
- USDe at $0.93 for **24 h**: the referee switches, the pledge is revalued downwards, Alice is liquidated. **Loss: ~$37,000.**

This is the most important finding of the project: **the duration of a shock matters as much as its size**.

### Step 4: who loses how much?
- **If Alice is liquidated**, a "liquidator" (anyone) repays her debt and walks away with her pledge, **plus a
  bonus** of about 2.6% (Morpho's official formula). Alice is the one who pays this bonus.
- **If the oracle sees nothing** (fixed price), Alice is not liquidated. But if her pledge is now worth **less than her debt**,
  she can walk away from everything: then **the lender** absorbs the hole. This is called **bad debt**.
  Example: an exploit at Pendle would leave a **$152,000** hole for the lenders, without a single liquidation.

### Step 5: how much does exiting cost?
We asked the real Pendle exchange office for a **quote**, without selling anything: "if I sold 413,030 PT, how much
would I receive?". The contract can answer that (a *simulation* function). The total exit cost adds up:
1. the **slippage**: the bigger the sale, the worse the rate gets (about 0.12%);
2. the conversion to USDC to repay the debt (small, and it is a hypothesis);
3. the **gas**: Ethereum's transaction fees (a few cents today);
4. the **forgone yield**: what we would have earned by staying during the week.

Total: **$854**, i.e. 1.6% of Alice's capital (which is worth $53,133).

### Step 6: the threshold p* ("p-star")
The brief's rule fits in one division:
> **p\* = exit cost ÷ loss if the incident happens**

- The brief's example: exiting costs 11, the incident would cost 60, so p\* = 11 ÷ 60 ≈ **18%**.
- Our position facing the alert "lasting USDe −30%": p\* = 854 ÷ 53,133 ≈ **1.6%**.

What this means: **if you believe there is more than a 1.6% chance the incident happens, exiting costs less than staying.**
The big advantage: the manager does not need to trust OUR probability. They compare their own to p\*.

> 💡 Why is p\* so low here? Because the position is **leveraged**: Alice borrowed 87% of the value of her pledge.
> So a small drop can wipe out all her capital. Leverage makes a position fragile.

### Step 7: exiting partly
Slippage grows **faster** than the size sold: the first PTs sell almost without loss, the last ones cost
more. Depending on the probability you believe in, the best answer is sometimes "sell 35%" rather than all or nothing. The engine
computes this fraction for every probability from 0 to 100%: that is the **PARTIAL x%** verdict.

### Step 8: "and without an alert?" — the Monte Carlo
To estimate the risk of a normal week, we **replay the week 200,000 times** on the computer. Each time, each
event (depeg, bankruptcy, exploit…) happens or not, at random, according to its frequency. We get:
- the **expected loss**: the average (about $130 per week here);
- the **VaR 95%**: the loss exceeded in only 5% of weeks. It is **$0** here, because in 99% of weeks
  nothing happens;
- the **ES 99%**: the average of the worst 1% of weeks (about $13,000), to see the tail of the risk.

### Step 9: honesty about the numbers
Every parameter of the engine carries a label (file `risk/params.yaml`):
- **sourced**: read in official docs (link + date), for example Morpho's liquidation bonus formula;
- **on-chain**: read from the blockchain, for example the referee's 16 h or the exchange office's quote;
- **hypothesis**: a choice made by our team, justified in one sentence. Example: "a major exchange failure roughly
  once every 100 years per exchange".

The program **refuses to start** if a number has no label. And a **sensitivity analysis** shows what moves
when each hypothesis is changed.

### Step 10: the proof on a real incident
On **October 10, 2025**, USDe fell to **$0.65 on Binance** for ~40 minutes, but it stayed close to $1
on-chain. We re-read the history of the Chainlink feed: its low that day was **$0.9929**. Result of the replay:
- our oracle: nothing happens (the gap did not even reach the threshold);
- an oracle listening to Binance: Alice would have been **liquidated**.

Moral: **the oracle's source matters**.

---

## 14. How to read the front

The front (`front/`) is a **slide deck** that follows the questions of a risk manager at 3 a.m. To launch it:
```bash
cd front && npm install && npm run dev
```
then open http://localhost:5173. Without a backend, it shows real recorded answers (`docs/api_examples/`): no
need for Internet. ← → changes pocket, ↑ ↓ changes question.

| # | Slide | What it shows |
|---|---|---|
| 1 | Portfolio | the holder's pockets, their weight, their verdict |
| 2 | Verdict | **STAY / EXIT** in big letters, what exiting would avoid versus what it costs, the threshold p\* |
| 3 | Which path? | the proven graph; click on an edge = its evidence |
| 4 | How much do I lose? | Monte Carlo and ranked incidents, with their rule |
| 5 | What does exiting cost? | certain cost, share that can be exited now |
| 6 | What if it happens? | your probability versus p\*: the verdict flips |
| 7 | Concentration | the dependencies shared by several pockets |

> Important: the front **computes nothing**. It displays what the Python API computed. If the numbers look wrong,
> `src/stacktrace/` is where you need to look.

---

## 15. Glossary

| Word | Simple explanation |
|---|---|
| **Address** | identifier of an account or a program on the blockchain (`0x…`, 42 characters) |
| **AMM / pool** | automatic exchange program between two tokens; an "exchange office" with no clerk |
| **API** | a web service that answers questions (here: the Morpho and Pendle websites) |
| **Block** | a "page" of the public ledger; numbered; one every ~12 s on Ethereum |
| **Blockchain** | public ledger, copied everywhere, indelible |
| **Cache** | the recorded answers, so they can be re-read without a network |
| **Chainlink** | company that provides prices (oracles) to the blockchain |
| **Collateral** | the pledge deposited in order to borrow |
| **Cooldown** | waiting time before you can withdraw (1 day for sUSDe) |
| **Curated** | information checked by hand in an official source, with link and date |
| **Custodian** | "safe" company that keeps crypto for someone |
| **DeFi** | decentralised finance: lending, borrowing, investing with smart contracts |
| **Depeg** | when a stablecoin is no longer worth $1 |
| **ERC-20** | the standard for tokens |
| **ERC-4626** | the standard for "piggy banks with shares" |
| **Ethereum** | the blockchain on which everything happens here |
| **Exchange** | centralised exchange platform (Binance, OKX…) |
| **Health factor** | distance to liquidation; < 1 = liquidatable |
| **Hedge** | opposite bet that neutralises price moves |
| **Liquidation** | forced sale of the pledge when the debt becomes too large compared to it |
| **LLTV** | the debt/pledge limit not to exceed (91.5% here) |
| **LTV** | debt ÷ value of the pledge |
| **Mainnet** | the real network (as opposed to test networks) |
| **Market (Morpho)** | a lending counter with its 5 fixed rules |
| **Meta-oracle** | oracle that chooses between two other oracles |
| **Morpho** | platform for lending/borrowing against a pledge |
| **Node / RPC** | server that has a copy of the blockchain / the counter where you query it |
| **Oracle** | the program that tells the blockchain how much something is worth |
| **Pendle** | platform that separates capital (PT) and interest (YT) |
| **Fixed price / market price / internal rate** | price by formula / real resale price / the manufacturer's accounting calculation |
| **Upgradeable proxy** | contract whose owner can change the code (a risk) |
| **PT** | principal token: worth 1 asset at a fixed date |
| **Revert** | a contract's refusal (for example: function does not exist) |
| **Smart contract** | program placed on the blockchain that applies its rules on its own |
| **Probe** | try functions to figure out what a contract is |
| **Stablecoin** | token worth about $1 (USDC, USDe) |
| **sUSDe** | shares of Ethena's piggy bank (deposited USDe that earn yield) |
| **SY** | Pendle's standard wrapper (the "plug adapter") |
| **Token** | a digital unit recorded in the ledger |
| **TVL** | *Total Value Locked*: how much money is deposited somewhere |
| **USDC** | Circle's digital dollar, backed by real dollars |
| **USDe** | Ethena's digital dollar, backed by hedged crypto |
| **Vault** | investment safe that lends its depositors' money |
| **YT** | yield token: collects the interest until the date |
| **Liquidation bonus (LIF)** | what the liquidator earns on top (≈ 2.6% here); the borrower is the one who pays it |
| **Shock** | an imagined incident: where, what, how much, how long |
| **Exit cost (C_exit)** | what it certainly costs to sell everything now (slippage + conversion + gas + forgone yield) |
| **Bad debt** | the part of the debt the pledge no longer covers: lost for the lenders |
| **ES 99%** | the average of the worst 1% of scenarios |
| **Gas** | the fees paid to make a transaction on Ethereum |
| **Slippage** | the loss due to the fact that the bigger you sell, the worse the price gets |
| **Monte Carlo** | replaying a period thousands of times at random to see the distribution of losses |
| **p\* (p-star)** | the probability threshold: exit cost ÷ loss in case of an incident; above it, exiting is better |
| **Expected loss** | the average loss over all the randomly drawn scenarios |
| **Replay** | replaying a real past incident on today's position |
| **Sensitivity** | how the result changes if a hypothesis is changed |
| **VaR 95%** | the loss exceeded in only 5% of cases |
| **Verdict** | STAY (stay), PARTIAL x% (exit part), EXIT (exit everything) |

---

## 16. A short quiz to check we understood

Answer out loud among yourselves, then open the answer key.

1. Why do we say "at block #26,162,087"?
2. What is the difference between USDC and USDe?
3. If 1 sUSDe is worth 1.25 USDe, is that a market price?
4. What will a PT-sUSDE-26NOV2026 be worth on November 26, 2026?
5. Alice has a health factor of 1.05. What does that mean?
6. USDe falls to $0.90 for 2 hours, then recovers. Is Alice liquidated?
7. And if it stays at $0.90 for 3 days?
8. Why is "where Ethena keeps its crypto" in `curated.yaml` and not "onchain"?
9. What is the `data/cache/` folder for?
10. What does the arrow "`susde` → `usde`" of type `redeemable_into` mean?
11. Exiting costs $854 and the incident would lose $53,133. What is p\*, and what does it mean?
12. Why does an exploit at Pendle not liquidate Alice, and who loses money?
13. Why is the VaR 95% equal to $0 when the expected loss is not zero?

<details>
<summary><b>Answer key</b></summary>

1. To say **at what moment** we read the data (the "photo" of the ledger). All our reads are made at the same block, so they are consistent and can be re-checked.
2. USDC is backed by **real dollars** kept by Circle. USDe is backed by **crypto + opposite bets** managed by Ethena.
3. **No**, it is an **internal rate** (the piggy bank's accounting calculation). The price at which someone would buy it could be different.
4. **1 USDe** (paid in the form of sUSDe, which you will have to unstake for 1 day to get USDe).
5. She is about **5% away from liquidation**: if the estimated price of her pledge drops by about 4.75%, she becomes liquidatable.
6. **No.** The referee requires 16 h of disagreement before switching to the "market" expert. During those 2 h, the "catalogue" expert stays in charge.
7. **Yes, probably.** After 16 h, someone can switch the oracle to the market price. The estimated price then drops by about 10%, more than Alice's 4.75% margin.
8. Because it happens **in the real world** (companies, accounts on exchanges), not in the public ledger. We can only know it through what Ethena **publishes**, hence the link and the date.
9. To **replay the discovery without Internet**, with exactly the same answers (the "photocopies" of the ledger).
10. "**sUSDe can be exchanged for USDe**": sUSDe depends on USDe. If USDe breaks, sUSDe suffers.
11. p\* = 854 ÷ 53,133 ≈ **1.6%**: if you believe there is more than a 1.6% chance the incident happens, exiting costs less than staying.
12. Because the main oracle is **fixed**: it does not see the PT's drop, so Alice's health does not move. But her pledge is worth less than her debt: she can walk away, and it is the **lenders** who absorb the hole (bad debt).
13. Because in more than 95% (and even 99%) of the simulated weeks, **nothing happens**. The expected loss comes from the rare very bad weeks; the ES 99% shows them.
</details>

---

## What next?
Once this guide is clear to you, read in this order:
1. [`POSITION_A.md`](POSITION_A.md): the same story with all the real numbers;
2. [`CONTRACT.md`](CONTRACT.md): the exact format of the file delivered to the other teams;
3. [`VERIFY.md`](VERIFY.md): what **you** must check yourselves;
4. [`AUDIT.md`](AUDIT.md): what is solid, what is missing, and what comes next.

And to **see** the graph in the terminal:
```bash
PYTHONPATH=src python -m discovery.inspect_graph
```
