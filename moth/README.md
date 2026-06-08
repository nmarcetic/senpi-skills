# MOTH v3.1 — Deploy Guide

## What it is

Dual-mode autonomous funding strategy on Hyperliquid perps. Uses the top-20 leaderboard (4h window) as an arbiter to decide which side of the trade to be on.

| Mode | Signal | Direction | Timeout |
|---|---|---|---|
| **A — Retail fade** | Funding ≥50% ann + ≥2h, top-20 traders absent (<2 longs) | SHORT | 48h |
| **B — Smart money ride** | ≥2 top-20 traders LONG + funding ≥30% ann + ≥1.5h | LONG | 28h |

Conflict → Mode B wins. No trade if neither fires.

> Runs as a **Hermes cron job** (every 30 min) — no external host required.

---

## Files

```
moth/
├── SKILL.md                    strategy docs + operator spec
├── README.md                   this file
├── runtime.yaml                DSL config (reference for senpi-trading-runtime operators)
├── config/moth-config.json     operator-tunable thresholds
├── scripts/moth-producer.py    reference signal emitter
├── scripts/moth_config.py      config loader
├── references/
│   └── skill-attribution.md   attribution (v3.1.0)
└── tests/
    └── test_moth_producer.py   29 unit + integration tests
```

---

## Quick deploy (Hermes cron)

1. Create strategy wallet (one-time):
```
strategy_create_custom_strategy(
  initialBudget=200,
  positions=[],
  skillName="moth",
  skillVersion="3.1.0"
)
```

2. Create cron job with the MOTH v3.1 prompt (see SKILL.md for full tick procedure).

3. State file auto-initialises at `/opt/data/moth_state.json` on first tick.

MOTH messages you only when a position opens.

---

## Risk stack

Three layers:

1. **Native Hyperliquid SL** — 15% margin stop, market order, fires on-chain
2. **Senpi Ratchet Stop** — profit lock at +8/15/25/40% ROE (Senpi backend manages it)
3. **State file** — daily loss limit ($10), 15% drawdown halt, 2-loss cooldown, 6h per-asset cooldown

---

## Tunable thresholds (`config/moth-config.json`)

| Key | Default | Notes |
|---|---|---|
| `mode_b_funding_threshold` | 30% | Min annualized funding for Mode B (LONG) entry |
| `mode_a_funding_threshold` | 50% | Min annualized funding for Mode A (SHORT) entry |
| `mode_b_persistence_hours` | 1.5 | Min hours funding must persist for Mode B |
| `mode_a_persistence_hours` | 2.0 | Min hours funding must persist for Mode A |
| `leaderboard_min_count` | 2 | Min top-20 traders needed to trigger Mode B |
| `max_leverage` | 5 | Hard cap (Mode B uses leaderboard-median, floor 2x) |
| `margin_per_slot` | 40 | USD per position |
| `daily_loss_limit` | 10 | USD — halt entries if hit |
| `drawdown_halt_pct` | 15 | % from peak — halt entries if hit |
