---
name: moth-strategy
description: >-
  MOTH v3.0 — Dual-mode funding strategy on Hyperliquid perps.
  Mode A (SHORT): fades assets with extreme funding (≥50% ann, ≥2h) where top-20
  leaderboard traders are absent — pure retail sentiment crowding, no smart money.
  Mode B (LONG): rides assets where ≥2 top-20 traders are long AND funding is elevated
  (≥30% ann, ≥1.5h) — smart money validated momentum with funding tailwind.
  Conflict (both modes fire): Mode B wins. Leaderboard is the arbiter.
  Full native risk stack: Hyperliquid SL, Senpi ratchet stop, persistent state file.
  Runs as Hermes cron job every 30 min — no external runtime host required.
license: MIT
metadata:
  author: nikola
  version: "3.0.0"
  platform: senpi
  exchange: hyperliquid
  requires:
    - senpi-trading-runtime>=1.1.0
    - senpi_runtime_helpers
---

# 🦋 MOTH v3.0 — Dual-Mode Funding Strategy

**Two signals. Two modes. One strategy.**

Funding tells you the crowd is stretched. The leaderboard tells you if smart money validated it.

| Scenario | Leaderboard | Funding | Action |
|---|---|---|---|
| **Mode A — Retail fade** | < 2 top-20 longs | ≥50% ann, ≥2h | SHORT — fade retail, collect funding |
| **Mode B — Smart money ride** | ≥2 top-20 longs | ≥30% ann, ≥1.5h | LONG — follow smart money, ride momentum |
| Conflict (both fire on same asset) | — | — | Mode B wins |
| Neither fires | — | — | No trade |

> *The moth is attracted to the light — but now it knows the difference between a candle (retail noise) and a floodlight (smart money momentum).*

---

## Signal Logic (every 30 min)

### Mode A — SHORT (retail fade)
1. `market_get_funding_history()` — find assets with annualized funding ≥50%, persisting ≥2h, longs paying (direction=SHORT), trend INTENSIFYING or STABLE
2. Cross-reference against `leaderboard_get_top(limit=20)` — **filter OUT any asset where ≥2 top-20 traders are long** (that's smart money, not retail)
3. Remaining candidates: pure retail crowding → enter SHORT at 2x leverage
4. Score = `(funding_ann / 100) × (persistence / 6) × 1.0`

### Mode B — LONG (smart money momentum ride)
1. `leaderboard_get_top(limit=20)` — build hot list of assets with ≥2 top-20 traders LONG
2. For each: check `market_get_funding_history()` — keep if funding ≥30% ann, ≥1.5h, longs paying, trend INTENSIFYING or STABLE
3. Enter LONG at median leverage of top-5 traders (capped 5x, floor 2x)
4. Score = `(funding_ann / 100) × (persistence / 6) × leaderboard_count × 1.5`
   (1.5× multiplier — smart money confirmation is higher conviction)

**Take top-scored candidate across both modes. Mode B always beats Mode A on the same asset.**

---

## Exits (enforced natively by Hermes cron)

| Trigger | Action |
|---|---|
| ROE ≤ -15% | CLOSE (max loss — backed by native SL) |
| Position age ≥ 36h | CLOSE (hard timeout) |
| Age ≥ 3h AND -5% < ROE < +2% | CLOSE (weak cut — deadweight) |
| Ratchet breach (peak locked) | CLOSE |

## Risk Guardrails (`/opt/data/moth_state.json`)

| Guardrail | Value |
|---|---|
| Daily loss limit | $10 (5% of budget) → halt entries |
| Drawdown halt | 15% from peak → halt entries |
| Consecutive losses | 2 → 2h cooldown |
| Per-asset cooldown | 6h after any loss on that ticker |
| Max entries per day | 4 |

## Risk Enforcement Layers

**Layer 1 — Native Hyperliquid SL**
Every `create_position` includes `stopLoss: {percentage: 15, orderType: MARKET}`. Fires natively even if cron is down.

**Layer 2 — Senpi Ratchet Stop (profit lock)**
`ratchet_stop_add()` after every entry:
- +8% ROE → lock 40% of high-water
- +15% → lock 60%
- +25% → lock 75%
- +40% → lock 88%

**Layer 3 — Persistent state file**
`/opt/data/moth_state.json` tracks across ticks: daily PnL, peak value, consecutive losses, cooldowns, open position metadata.

## Operator Spec

| Field | Value |
|---|---|
| Universe | Dynamic — leaderboard-derived (Mode B) + all extreme-funding assets (Mode A) |
| Mode A direction | SHORT only (retail fade) |
| Mode B direction | LONG only (momentum ride) |
| Tick cadence | 30 min (Hermes cron) |
| Mode A leverage | 2x (conservative — no smart money validation) |
| Mode B leverage | Median of top-5 traders, cap 5x, floor 2x |
| Margin per slot | 20% of budget ($40 on $200) |
| Slots | 3 concurrent (can mix modes) |
| Mode A funding threshold | ≥50% annualized, ≥2h persistence |
| Mode B funding threshold | ≥30% annualized, ≥1.5h persistence |

## File Inventory

```
moth/
├── SKILL.md                         ← this file (v3.0.0)
├── README.md                        ← deploy instructions
├── runtime.yaml                     ← runtime config (v3.0 dual-mode)
├── config/moth-config.json          ← operator-tunable thresholds
├── scripts/moth-producer.py         ← reference signal emitter
├── scripts/moth_config.py           ← config loader
├── references/skill-attribution.md ← attribution
└── tests/
    ├── __init__.py
    └── test_moth_producer.py        ← 29 unit + integration tests
```

State file (runtime, not committed):
```
/opt/data/moth_state.json            ← persistent risk state across cron ticks
```

## Skill Attribution

When creating a strategy with this skill, include `skill_name` and `skill_version` in the call. See `references/skill-attribution.md` for details.
