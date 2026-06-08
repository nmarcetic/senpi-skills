---
name: moth-strategy
description: >-
  MOTH v1.1.0 — Outcome market funding fade on Hyperliquid prediction markets.
  Detects extreme, persistent funding on outcome (binary) tickers where one
  side is crowded by sentiment rather than information. Enters opposite to the
  crowded side to collect the funding stream. Hard expiry gate (force-close
  6h before resolution) is the primary risk control — outcome markets resolve
  to 0 or 1, making expiry the single non-negotiable exit. Full risk stack:
  native Hyperliquid SL (15% margin), Senpi ratchet stop (profit lock tiers),
  and persistent state file for daily loss limit, drawdown halt, consecutive
  loss cooldown, and per-asset cooldown. Runs as Hermes cron job — no external
  runtime host required.
  Leverage capped at 2x — binary resolution risk demands conservative sizing.
  Named for the moth: attracted to the funding light, disciplined enough not
  to burn on expiry.
license: MIT
metadata:
  author: nikola
  version: "1.1.0"
  platform: senpi
  exchange: hyperliquid
  requires:
    - senpi-trading-runtime>=1.1.0
    - senpi_runtime_helpers
---

# 🦋 MOTH v1.1.0 — Outcome Market Funding Fade

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

## Exits (all enforced natively by Hermes cron — no external runtime needed)

| Trigger | Action |
|---|---|
| Expiry gate: ≤ 6h to resolution | CLOSE immediately (market) |
| Price resolved: markPx < 0.05 or > 0.95 | CLOSE immediately |
| Phase 1: ROE ≤ -15% | CLOSE (max loss) |
| Hard timeout: position age > 48h | CLOSE |
| Weak cut: > 2h open AND ROE < 2% | CLOSE (cut deadweight) |
| Profit ratchet: ROE drops below locked level | CLOSE (via ratchet stop) |

## Risk guardrails (enforced via state file `/opt/data/moth_state.json`)

| Guardrail | Value |
|---|---|
| Daily loss limit | 5% of budget ($10) → halt entries |
| Drawdown halt | 15% from peak → halt entries |
| Consecutive losses | 2 → 2h entry cooldown |
| Per-asset cooldown | 6h after any loss on a ticker |
| Max entries per day | 4 |

## Risk enforcement layers

**Layer 1 — Native Hyperliquid SL**
Every `create_position` call includes `stopLoss: {percentage: 15, orderType: MARKET}`.
Hyperliquid enforces this natively — fires even if cron is down.

**Layer 2 — Senpi Ratchet Stop (profit lock)**
After every open, `ratchet_stop_add()` is called with 5 tiered ROE locks:
- +5% ROE → lock 30% of high-water
- +10% → lock 50%
- +15% → lock 65%
- +25% → lock 80%
- +40% → lock 90%
Senpi backend manages trailing stop updates automatically.

**Layer 3 — Persistent state file**
`/opt/data/moth_state.json` tracks daily PnL, peak account value, consecutive losses,
cooldown timestamps, and per-asset cooldowns across cron ticks.

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
├── runtime.yaml                      ← runtime config (reference — Hermes cron is the runtime)
├── config/moth-config.json           ← operator tunables
├── scripts/moth-producer.py          ← signal emitter (reference implementation)
├── scripts/moth_config.py            ← SDK boilerplate
├── references/skill-attribution.md  ← attribution
└── tests/
    ├── __init__.py
    └── test_moth_producer.py         ← 29 unit + integration tests
```

State file (runtime, not committed):
```
/opt/data/moth_state.json             ← persistent risk state across cron ticks
```

## Skill Attribution

When creating a strategy with this skill, include `skill_name` and `skill_version`
in the call. See `references/skill-attribution.md` for details.
