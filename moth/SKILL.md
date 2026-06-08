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
  version: "2.2.0"
  platform: senpi
  exchange: hyperliquid
  requires:
    - senpi-trading-runtime>=1.1.0
    - senpi_runtime_helpers
---

# 🦋 MOTH v2.2.0 — Leaderboard Crowding Fade

**Fade assets where top-20 leaderboard traders are crowded LONG and funding is extreme. Fully dynamic universe — no hardcoded tickers.**

Smart money builds the trade, retail piles in, funding starts paying the other side. MOTH enters SHORT, collects the funding stream while crowding persists, exits when the crowd unwinds or profit locks trigger.

> *Named for the moth: attracted to the funding light, disciplined enough not to burn.*

## Signal logic

Every 15 minutes:

1. Pull top-20 leaderboard (4h window) — build `hot_list` of assets with **≥2 top-20 traders LONG**
2. For each hot-list asset: check `market_get_funding_history` — keep if:
   - Annualized funding **≥ 30%**
   - Persistence **≥ 1.5h** (confirmed signal, not a single-tick spike)
   - `funding_direction = SHORT` (longs are paying — correct crowding direction)
   - Trend INTENSIFYING or STABLE
3. Score = `(funding_ann_pct / 100) × (persistence_hours / 6) × leaderboard_count`
4. Enter **SHORT** on top candidate — 1 new position per tick max
5. Leverage = median leverage of top-5 traders on that asset, capped at 5x, floor 2x

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
| Universe | 100% leaderboard-derived — top-20 (4h window), ≥2 traders long |
| Signal | Leaderboard crowding + funding fade — SHORT only |
| Tick cadence | 15 min (Hermes cron) |
| Leverage | Median of top-5 traders on asset, cap 5x, floor 2x |
| Margin per slot | 20% of budget ($40 on $200) |
| Slots | 3 concurrent |
| DSL preset | Phase1 max_loss 15%, Phase2 ratchet tiers (8/15/25/40%), hard_timeout 36h, weak_cut 3h |
| Persistence threshold | 1.5h (early entry — catches crowding while still building) |
| Funding threshold | ≥30% annualized, direction SHORT (longs paying) |

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
