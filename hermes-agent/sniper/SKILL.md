---
name: sniper-strategy
description: >-
  Whale consensus following strategy: monitors top-10 Hyperliquid leaderboard
  traders every 4h, enters BTC/ETH/HYPE/SOL when ≥3 whales hold same direction
  with no opposing positions. 3x leverage, $500/trade, progressive TP/SL decay
  on re-entries (10%→8%→5% TP, 30%→20%→15% SL).
version: 1.0.0
tags: [senpi, hyperliquid, whale-following, trading, mcp, defi]
---

# Sniper Strategy v1.0.0

Hermes-native whale consensus strategy. See README.md for full spec.

## Quick Reference

- **Strategy ID:** `9ea76a8f-7d3e-43ec-9b32-dc13e5b7c794`
- **State file:** `/opt/data/sniper_state.json`
- **Script:** `/opt/data/scripts/sniper.py`
- **Cron:** every 4h, `no_agent=true`, `deliver="origin"`

## Entry Logic

```python
# Consensus check per asset
if long_whales >= 3 and short_whales == 0:
    enter("LONG")
elif short_whales >= 3 and long_whales == 0:
    enter("SHORT")
else:
    pass  # mixed or low signal — skip
```

## TP/SL Ladder

| Entry | TP | SL |
|---|---|---|
| 1st | 10% | 30% |
| Re-1 | 8% | 20% |
| Re-2 | 5% | 15% |

## Files

- `README.md` — full strategy documentation
- `SKILL.md` — this manifest
- Script at `/opt/data/scripts/sniper.py`
