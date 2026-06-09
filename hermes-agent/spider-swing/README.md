# SPIDER SWING — Hermes-Native

Hermes-native port of Spider v5.1.1 swing leg. Tech/AI multi-day momentum on dynamic XYZ equities + crypto alts.

## Quick Deploy

1. Create strategy wallet (empty positions, $100+ budget):
```
strategy_create_custom_strategy(initialBudget=100, positions=[], skillName="spider-swing", skillVersion="1.0.0", strategyName="spider-swing", slippage=3)
```

2. Note the `strategyWalletAddress` and `id` from the response.

3. Create Hermes cron (every 15 min) with the cron prompt from `SKILL.md`, passing wallet address and strategy ID.

4. State files `/opt/data/spider_swing_state.json` and `/opt/data/spider_swing_firstseen.json` are auto-created on first tick.

## What it trades

Dynamic universe: semis/AI/space XYZ equities (auto-catches Pre-IPO listings) + SUI/ONDO/HYPE/NIL/GRASS/ZEC. LONG only. 10x max. 7d max hold.

## Files

- `SKILL.md` — full strategy spec and cron tick logic
