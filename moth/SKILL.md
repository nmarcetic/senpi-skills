---
name: moth-strategy
description: >-
  MOTH v1.0.0 — Outcome market funding fade on Hyperliquid prediction markets.
  Detects extreme, persistent funding on outcome (binary) tickers where one
  side is crowded by sentiment rather than information. Enters opposite to the
  crowded side to collect the funding stream. Hard expiry gate (force-close
  6h before resolution) is the primary risk control — outcome markets resolve
  to 0 or 1, making expiry the single non-negotiable exit. DSL mean_reversion
  preset banks the snapback fast; Phase 1 max_loss 15% cuts adverse moves.
  Leverage capped at 2x — binary resolution risk demands conservative sizing.
  Named for the moth: attracted to the funding light, disciplined enough not
  to burn on expiry.
license: MIT
metadata:
  author: nikola
  version: "1.0.0"
  platform: senpi
  exchange: hyperliquid
  requires:
    - senpi-trading-runtime>=1.1.0
    - senpi_runtime_helpers
---

# 🦋 MOTH v1.0.0 — Outcome Market Funding Fade

**Collect funding from sentiment-crowded prediction markets. Exit before they resolve.**

Outcome markets on Hyperliquid are binary: price converges to 0 or 1 at resolution.
When sentiment crowds one side (e.g. everyone buying YES), funding becomes extreme —
YES holders pay NO holders every hour. MOTH enters the uncrowded side, collects the
funding stream while crowding persists, and hard-exits before the resolution cliff.

## Signal logic

Every 5 minutes:

1. Scan all instruments via `market_list_instruments` — filter to outcome tickers
   (detected by ticker pattern: contain `-YES`, `-NO`, `-WILL`, `-WINS`, or have
   markPx between 0.01 and 0.99 with OI > $100k)
2. For each candidate: check annualized funding > `min_funding_annualized_pct` (default 50%)
   and persistence > `min_persistence_hours` (default 6h)
3. Check days-to-expiry > `min_days_to_expiry` (default 1.0) — never enter within 24h
4. Check price not already resolving: 0.05 < price < 0.95
5. Score by funding magnitude × persistence hours — emit highest-conviction signal

## Exits (all DSL-managed, producer does NOT close)

| Trigger | Action |
|---|---|
| Phase 1: ROE drops 15% from entry | Cut loss |
| Phase 2 ratchet: ROE > 5% | Start locking in gains |
| hard_timeout: 48h | Force-close regardless |
| weak_peak_cut: 2h at < 2% ROE | Cut deadweight |
| **Expiry gate (producer)** | Emit NO-OP / stop emitting new signals for expiring tickers |

> ⚠️ **The expiry gate is in the producer, not the DSL.** The producer stops emitting
> signals for any ticker within `force_close_hours_before_expiry` (default 6h) of
> resolution. Open positions in expiring tickers are left to DSL's hard_timeout
> (48h) or the operator should monitor manually. A future runtime version will
> support native expiry-aware exits.

## Operator spec

| Field | Value |
|---|---|
| Universe | Hyperliquid outcome tickers (auto-detected) |
| Signal | Funding fade — enter opposite crowded side |
| Tick cadence | 300s |
| Leverage | 2x (hard cap — binary resolution risk) |
| Margin per slot | 20% of budget |
| Slots | 3 concurrent |
| DSL preset | `mean_reversion` (tight, fast snapback) |
| Hard timeout | 48h |

## File inventory

```
moth/
├── SKILL.md                          ← this file
├── README.md                         ← deploy instructions
├── runtime.yaml                      ← runtime config
├── config/moth-config.json           ← operator tunables
├── scripts/moth-producer.py          ← signal emitter
├── scripts/moth_config.py            ← SDK boilerplate
└── references/skill-attribution.md  ← attribution
```

## Skill Attribution

When creating a strategy with this skill, include `skill_name` and `skill_version`
in the call. See `references/skill-attribution.md` for details.
