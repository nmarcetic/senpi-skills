---
name: spider-scalp
description: >-
  SPIDER SCALP v1.0 — Hermes-native port of Spider v5.1.1 scalp leg.
  Macro mean-reversion on BTC/ETH/SOL/HYPE + xyz:BRENTOIL/xyz:CL.
  Fades RSI extremes + 15m MA stretch with 1h trend filter. BOTH directions.
  Strict 5x leverage. Fast 2h max hold. DSL tight fast-capture profit ladder.
  Runs as Hermes cron every 5 minutes — no external runtime required.
license: Apache-2.0
metadata:
  author: nikola
  version: "1.0.0"
  platform: senpi
  exchange: hyperliquid
  original_skill: spider
  original_version: "5.1.1"
  ported_by: hermes-agent
---

# 🕷️ SPIDER SCALP v1.0 — Hermes-Native Port

Hermes-native port of the Spider v5.1.1 scalp leg. No Railway, no OpenClaw — Hermes cron IS the daemon.

## Universe

`BTC / ETH / SOL / HYPE` (main DEX) + `xyz:BRENTOIL / xyz:CL` (XYZ DEX, use `dex="xyz"`)

## Signal Scoring (minScore: 4, both directions)

Pick the more extreme side (oversold → LONG, overbought → SHORT), then score:

| Component | Points | Source |
|---|---|---|
| RSI extreme | +3 (≤20/≥80) / +2 (≤25/≥75) / +1 (≤30/≥70) | `market_get_asset_data` 15m candles |
| 15m MA stretch | +2 (≥1.6% from 20-bar MA) / +1 (≥0.8%) | 15m candles |
| 1h trend filter | +1 (fading WITH higher-TF bias) / −2 (against strong trend) | 1h candles |
| Funding tiebreak | +1 (shorts pay a LONG / longs pay a SHORT) | instrument context |

**Knife guard**: −2 if longing with bearish 1h trend or shorting with bullish 1h trend. Prevents fading strong momentum.

Take the highest-scoring asset. If score < 4, no trade this tick.

## Execution

- **Leverage**: 5x strict (clamped to venue max — e.g. xyz:CL may cap lower)
- **Margin**: 15% of account value per position
- **Max slots**: 4 concurrent positions
- **Order type**: `FEE_OPTIMIZED_LIMIT` with `ensureExecutionAsTaker: true`, 20s timeout
- **Stop loss**: 5% of margin (native SL on open)
- **Ratchet stop**: tiered ROE ladder (see below)

## DSL — Tight Fast-Capture

Phase 1 (loss protection):
- Max loss: **5%** of margin
- Hard timeout: **2h** (close regardless of P&L)
- Weak peak cut: if age > 30min AND peak ROE < 1.5% → CLOSE (deadweight)
- Dead weight cut: if age > 25min AND ROE flat (< 0.5% move in last 10min) → CLOSE

Phase 2 (profit ladder via ratchet stop):
```
3%  ROE → lock 35%
6%  ROE → lock 55%
12% ROE → lock 70%
25% ROE → lock 85%
```

## Risk Gates (`/opt/data/spider_scalp_state.json`)

| Gate | Value |
|---|---|
| Daily loss limit | 10% of account → halt entries |
| Drawdown halt | 20% from session peak → halt entries |
| Consecutive losses | 5 → 30min cooldown |
| Per-asset cooldown | 10min after any close on that ticker |
| Max entries per day | 18 (fee-sensitive) |

## Cron Tick Logic (every 5 min)

### Phase 1 — Exit Check
1. Read `/opt/data/spider_scalp_state.json`
2. `strategy_get_clearinghouse_state(wallet)` — enumerate open positions
3. For each open position:
   - Check age vs hard_timeout (2h) → CLOSE if exceeded
   - Check weak_peak_cut: age > 30min AND state.peak_roe[coin] < 1.5% → CLOSE
   - Check dead_weight_cut: age > 25min AND abs(current_roe - prev_roe) < 0.5% → CLOSE
4. Update state: record closed positions, update daily_loss, consecutive_losses

### Phase 2 — Entry Scan (only if gates allow)
1. Check risk gates: daily_loss < 10%, drawdown < 20%, not in cooldown, open_slots > 0
2. For each asset in universe (skip already-held):
   - `market_get_asset_data(asset, candle_intervals=["15m","1h"])` 
   - For XYZ assets: use `dex="xyz"`
   - Compute RSI on 15m closes (14-period), 20-bar MA stretch, 1h trend
   - Score both directions, pick better side
3. Sort candidates by score descending, take top scorer if score ≥ 4

### Phase 3 — Execute
1. Compute margin: `account_value * 0.15` (max $25 floor, $30 cap for $100 wallet)
2. `create_position(coin, direction, leverage=5, margin, orderType="FEE_OPTIMIZED_LIMIT", feeOptimizedLimitOptions={ensureExecutionAsTaker:true, executionTimeoutSeconds:20}, stopLoss={percentage:5, orderType:"MARKET"})`
3. `ratchet_stop_add(strategyId, asset, strategyWalletAddress, ratchetStopConfig={tiered:{tiers:[{triggerRoe:3,lockRoe:35},{triggerRoe:6,lockRoe:55},{triggerRoe:12,lockRoe:70},{triggerRoe:25,lockRoe:85}]}})`
4. Write to state: open_time, direction, entry_score, peak_roe=0

### Phase 4 — Report
- ONLY send Telegram message if a position was successfully opened
- Format: `🕷️ SCALP opened [LONG/SHORT] {coin} @ {price} | score={score} | margin=${margin} | 5x`
- Silent on all other outcomes (exits, halts, no-signal ticks)

## XYZ Asset Handling

- `xyz:BRENTOIL` and `xyz:CL` require `dex="xyz"` on `market_get_asset_data`
- XYZ positions appear in clearinghouse `xyz.assetPositions` (not `main`)
- Account value: take `max(main.accountValue, xyz.accountValue)` — same wallet, NOT summed

## Skill Attribution

When creating the strategy wallet, include:
```json
"skillName": "spider-scalp",
"skillVersion": "1.0.0"
```
