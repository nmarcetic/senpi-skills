# 🎯 Sniper Strategy v1.0.0

**Whale consensus following on Hyperliquid perps**

Sniper monitors the top-10 Hyperliquid traders (4h rolling leaderboard) and enters positions when 3 or more whales hold the same asset in the same direction — with no opposing positions (clean consensus only).

---

## Strategy Spec

| Parameter | Value |
|---|---|
| **Assets** | BTC, ETH, HYPE, SOL |
| **Capital** | $500 margin per trade |
| **Leverage** | 3x CROSS |
| **Consensus threshold** | ≥ 3/10 top whales, same direction |
| **Mixed signal** | Skip (any whale on opposite side = no entry) |
| **Check cadence** | Every 4 hours |
| **Total budget** | $2,000 (4 assets × $500) |

---

## Entry Ladder (TP/SL decay on re-entries)

| Entry # | TP ROE | SL ROE | Notes |
|---|---|---|---|
| Entry 1 | 10% | 30% | Fresh signal |
| Re-entry 1 | 8% | 20% | TP hit, consensus still holds |
| Re-entry 2 | 5% | 15% | Progressive tighten, 3rd leg |
| Max | — | — | No re-entry after 3rd entry |

Re-entry only fires if whale consensus is still intact after TP. Once 3 entries on the same asset cycle are exhausted, that asset is skipped until the next clearly independent signal (direction flip or whale rotation).

---

## Consensus Rules

- **Clean long**: ≥ 3 of top-10 whales hold LONG, zero hold SHORT → enter LONG
- **Clean short**: ≥ 3 of top-10 whales hold SHORT, zero hold LONG → enter SHORT
- **Mixed**: any whale on opposite side → **no entry**
- **Direction flip mid-position**: consensus switches direction → close immediately, re-enter on new consensus

---

## Risk Management

- SL tightens progressively on re-entries (less room as the move ages)
- TP also shrinks (capturing progressively smaller bounces)
- Position closes if whale consensus flips direction
- No position opened if wallet has no withdrawable margin

---

## Architecture

```
Hermes cron (every 4h, no_agent=true)
  └── sniper.py
        ├── Phase 1: Exit check (TP/SL hit detection)
        ├── Phase 2: Consensus scan (top-10 whale positions)
        └── Phase 3: Execute (create_position with TP/SL)
              └── Silent stdout = $0/tick
              └── Signal stdout = delivered to Nikola on Telegram
```

---

## Files

| File | Purpose |
|---|---|
| `sniper.py` | Main execution script (`/opt/data/scripts/sniper.py`) |
| `README.md` | This file |
| `SKILL.md` | Hermes skill manifest |

**State file:** `/opt/data/sniper_state.json`
**Strategy ID:** `9ea76a8f-7d3e-43ec-9b32-dc13e5b7c794`

---

## Deploy

Strategy already live (created 2026-07-02). Cron running every 4h.

To redeploy from scratch:
```bash
# 1. Create strategy
mcp_senpi_strategy_create_custom_strategy(
  initialBudget=2000,
  positions=[],
  strategyName="sniper",
  skillName="sniper",
  skillVersion="1.0.0"
)

# 2. Seed state
echo '{"open_positions": {}, "last_check": null, "version": "1.0.0"}' > /opt/data/sniper_state.json

# 3. Schedule cron (every 4h, no_agent=true)
```

---

## Signal Example

```
🟢 LONG HYPE | 4/10 whales | Entry 41.20 | TP 10% / SL 30% ROE
🔴 SHORT BTC  | 3/10 whales | Entry 61500 | TP 10% / SL 30% ROE
```

Silent ticks (no consensus) produce zero output = $0 LLM cost.

---

*Built 2026-07-02 — Hermes-native, no OpenClaw, no Railway.*
