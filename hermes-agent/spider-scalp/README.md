# SPIDER SCALP — Hermes-Native

Hermes-native port of Spider v5.1.1 scalp leg. Macro mean-reversion on BTC/ETH/SOL/HYPE + energy.

## Quick Deploy

1. Create strategy wallet (empty positions, $100+ budget):
```
strategy_create_custom_strategy(initialBudget=100, positions=[], skillName="spider-scalp", skillVersion="1.0.0", strategyName="spider-scalp", slippage=3)
```

2. Note the `strategyWalletAddress` and `id` from the response.

3. Create Hermes cron (every 5 min) with the cron prompt from `SKILL.md`, passing wallet address and strategy ID.

4. State file `/opt/data/spider_scalp_state.json` is auto-created on first tick.

## What it trades

RSI extremes + 15m MA stretch on BTC/ETH/SOL/HYPE/BRENTOIL/CL. Both directions. 5x. 2h max hold.

## Files

- `SKILL.md` — full strategy spec and cron tick logic
