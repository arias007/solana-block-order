# Solana Block Order Explorer

**Does paying a higher priority fee put your transaction earlier in the block?**

Paste any Solana slot and find out. Live tool, public data, no server.

→ **`app/index.html`** — open it in any browser, or serve the folder statically.

---

## The answer, up front

**No.** Measured across 6 validator clients, 114 slots and 47,327 non-vote
transactions on mainnet (epoch 1069):

| Client | Version | Stake | ρ(position, priority fee) | ρ(position, compute) |
|---|---|---:|---:|---:|
| HarmonicAgave | 4.3.2 | 3.92% | +0.094 | +0.074 |
| JitoLabs | 4.3.2 | 3.84% | +0.021 | +0.027 |
| AgaveBam | 4.3.2 | 2.95% | +0.006 | **+0.203** |
| HarmonicFiredancer | 26.10.4 | 2.24% | +0.017 | +0.057 |
| Firedancer | 26.10.4 | 1.62% | +0.012 | +0.053 |
| FireBAM | 26.10.5 | 1.03% | −0.034 | +0.084 |

Every fee correlation is under 0.1 — under 1% of positional variance explained —
and the sign is inconsistent between clients. Meanwhile **compute correlates
positively with position in all six**, and the last quarter of a block consumes
**1.30×** more compute than the first quarter.

That is the signature of a parallel scheduler writing out transactions in
completion order. Position reflects *when execution finished*, not *what you paid*.

Priority fee buys **admission** to a block. Not **position** inside it.

---

## Why this tool exists

Every explorer shows you the fee you paid. None of them show whether paying more
actually moved you earlier in the block. So I measured it, and then turned the
measurement into something you can run yourself on any slot.

The quartile view is the fastest way to see it. Sort a block's transactions by
price and look at where each quartile lands:

```
HarmonicAgave        0.31  0.65  0.55  0.49
JitoLabs             0.44  0.56  0.49  0.51
AgaveBam             0.44  0.60  0.51  0.45
HarmonicFiredancer   0.40  0.61  0.51  0.48
Firedancer           0.35  0.65  0.52  0.49
FireBAM              0.49  0.54  0.50  0.47
                     ↑     ↑     ↑     ↑
                  cheapest        most expensive
```

If fee sorted the block, this would climb left to right. In five of six clients
the **cheapest** quartile sits closest to the front.

---

## Using the tool

Open `app/index.html`. It calls a public Solana RPC directly from your browser —
no backend, no API key, no tracking.

- **Inspect** a slot number, or leave it blank for the chain head
- **Random recent block** for a quick sample
- Read the verdict line, then the ρ values, then the quartile bars

What each number means:

| Field | Meaning |
|---|---|
| ρ position vs priority fee | Spearman correlation. Near 0 = no ordering effect. |
| ρ position vs compute | Positive = long transactions land later (parallel execution). |
| Block compute used | Above ~70% is where fee-ordering would matter most, if it existed. |
| Zero priority fee | Share of landed transactions that paid nothing extra. |
| Average position by price quartile | 0 = first in block, 1 = last. Should rise monotonically if fee-ordered. |

---

## Reproducing the study

`probe.py` — fetch blocks for chosen validators, extract per-transaction metrics
`analyze.py` — group by block saturation, compare full vs. sparse blocks
`final.py` — the 6-client × 19-slot run behind the table above
`verify.py` — checks the compute-vs-tail hypothesis per slot

Only the Python standard library. No API key.

```sh
python3 final.py        # produces the summary table
python3 analyze.py      # saturation-stratified view
```

### Three RPC gotchas that cost time

1. `getLeaderSchedule`'s `identity` filter accepts **one identity string**, not a
   list. Passing an array returns `-32602 invalid type: sequence`.
2. The slots it returns are **relative to the epoch start**. Add
   `absoluteSlot − slotIndex` before calling `getBlock`, or you silently read
   the wrong blocks.
3. `getBlock` requires `maxSupportedTransactionVersion: 1`; version-0
   transactions return `-32015` otherwise.

---

## Limitations, stated plainly

- **This is observation of produced blocks**, not a controlled experiment where
  I send my own transactions at chosen fee levels. It can detect an ordering
  effect large enough to see in produced blocks — it detects none. It cannot
  rule out an effect smaller than that.
- Arrival timestamps at the leader are not observable from public RPC, so
  "arrival order" and "completion order" cannot be separated directly. The
  compute correlation is the proxy that distinguishes them.
- 19 slots per client rejects a strong ordering effect; it does not characterise
  rare tail behaviour under extreme congestion.
- Vote transactions are excluded by design.

---

## Data

Raw per-slot results are in `final_result.pkl` (Python pickle, ~18 KB) — the
exact numbers behind every cell in the table above.

---

MIT licensed. Issues and counter-examples welcome — if you find a validator that
*does* order by fee, that is the most interesting result in this whole question.
