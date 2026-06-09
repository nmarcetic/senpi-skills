---
name: spider-swing
description: >-
  SPIDER SWING v1.0 — Hermes-native port of Spider v5.1.1 swing leg.
  Tech & AI multi-day momentum on a dynamic XYZ-equity universe (semis/AI/space
  include-set + auto-catches fresh Pre-IPO listings) plus static crypto alts
  (SUI/ONDO/HYPE/NIL/GRASS/ZEC). LONG only. 4h+1h trend structure + 24h
  relative strength + SM consensus. Conviction leverage clamped 10x.
  Wide let-winners-run DSL with 7d staleness backstop.
  Runs as Hermes cron every 15 minutes — no external runtime required.
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

# 🕷️ SPIDER SWING v1.0 — Hermes-Native Port

Hermes-native port of the Spider v5.1.1 swing leg. No Railway, no OpenClaw — Hermes cron IS the daemon.

## Universe

**Dynamic — rebuilt every tick by `build_universe()`:**

Static crypto alts (always included):
`SUI / ONDO / HYPE / NIL / GRASS / ZEC`

Dynamic XYZ equities — eligible if:
1. `dayNtlVlm ≥ $5M` (liquid) AND
2. Either: bare ticker is in curated include-set OR first-seen < 21 days ago AND not in exclude-set

**Include-set** (semis / AI / space / fintech):
`NVDA AMD INTC MRVL MU TSM ASML ARM SMSN SKHX DRAM SNDK DELL LITE CRWV PLTR ORCL GOOGL META MSFT AMZN AAPL NFLX IBM COIN MSTR CRCL HOOD SPCX RKLB CBRS`

**Exclude-set** (commodities / FX / indices — caught by fresh-listing filter but should not be auto-added):
`GOLD SILVER BRENTOIL CL EUR GBP JPY XYZ100`

First-seen ledger: `/opt/data/spider_swing_firstseen.json`
(Seeded on first run: all current names marked as already-old so only truly NEW listings trigger auto-catch)

Cap: top 20 by 24h volume from eligible XYZ set, to bound candle fetch cost.

## Signal Scoring (minScore: 5, LONG only)

| Component | Points | Source |
|---|---|---|
| 4h trend structure | +3 BULLISH / −4 BEARISH | `market_get_asset_data` 4h candles |
| 1h trend confirmation | +2 BULLISH / −1 BEARISH | 1h candles |
| 24h relative strength | +3 (≥8%) / +2 (≥4%) / +1 (≥1%) / −1 (<0%) | markPx vs prevDayPx from instrument context |
| RSI room | +1 (RSI1h < 50) / −2 (RSI1h > 78, overbought) | 1h candles |
| Funding | +1 (negative funding, longs collect) / −1 (crowded long, >30% ann) | instrument context |
| SM consensus bonus | +2 (≥2 top-20 LONG) / −2 (≥2 top-20 SHORT) | `leaderboard_get_markets` — crypto alts only; XYZ has no leaderboard data |

**LONG only** — a bearish 4h structure drives score below minScore 5 → no trade.
Requires BOTH 4h AND 1h bullish to clear the floor.

Take top-scored candidate. If score < 5, no trade this tick.

## Execution

- **Leverage**: min(10x, venue_max) — clamp to asset cap (GRASS/NIL cap at 3x, most XYZ at 10x)
- **Margin**: 28% of account value per position
- **Max slots**: 3 concurrent positions
- **Order type**: `FEE_OPTIMIZED_LIMIT` with `ensureExecutionAsTaker: true`, 60s timeout
- **Stop loss**: 22% of margin (wide — ride through noise; ratchet stop is the real exit manager)
- **Ratchet stop**: tiered ROE ladder (see below)

## DSL — Wide Let-Winners-Run

Phase 1 (loss protection):
- Max loss: **22%** of margin
- Hard timeout: **7d** (staleness backstop — if still alive after a week with no ratchet trigger, thesis is stale)
- NO weak_peak_cut, NO dead_weight_cut, NO time-based exits below 7d — this leg HOLDS through drawdowns

Phase 2 (profit ladder via ratchet stop):
```
15%  ROE → lock 0%   (break-even protection)
30%  ROE → lock 45%
60%  ROE → lock 68%
100% ROE → lock 80%
150% ROE → lock 90%
```

## Risk Gates (`/opt/data/spider_swing_state.json`)

| Gate | Value |
|---|---|
| Daily loss limit | 15% of account → halt entries (resets at UTC midnight) |
| Drawdown halt | 25% from session peak → halt entries |
| Consecutive losses | 4 → 90min cooldown |
| Per-asset cooldown | 4h after any close on that ticker |
| Max entries per day | 12 (bypass if all open positions are profitable) |

## Cron Tick Logic (every 15 min)

### Phase 1 — Exit Check
1. Read `/opt/data/spider_swing_state.json`
2. `strategy_get_clearinghouse_state(wallet)` — enumerate open positions (both `main` and `xyz`)
3. For each open position:
   - Check age vs hard_timeout (7d) → CLOSE if exceeded (reason: `staleness_backstop`)
   - Check native SL and ratchet stop are still active (ratchet_stop_list) — re-add if missing
4. Update state: record realized closes, update daily_loss, consecutive_losses

### Phase 2 — Universe Build
1. `market_list_instruments()` — get full instrument board with volumes + max_leverage
2. Read `/opt/data/spider_swing_firstseen.json`; update with any new XYZ tickers (first-seen = now)
3. Build eligible universe:
   - Crypto alts: always included
   - XYZ: filter by volume ≥ $5M, include-set OR (first_seen < 21d AND not in exclude-set)
   - Cap to top 20 XYZ by volume
4. Skip assets already held

### Phase 3 — Entry Scan (only if gates allow)
1. Check risk gates: daily_loss < 15%, drawdown < 25%, not in cooldown, open_slots > 0
2. One `leaderboard_get_markets()` call — extract SM consensus per ticker
3. For each candidate asset:
   - `market_get_asset_data(asset, candle_intervals=["4h","1h"])` 
   - For XYZ assets: use `dex="xyz"`
   - Compute 4h trend (EMA alignment or price vs MA), 1h trend, 24h RS, RSI, funding, SM bonus
   - Score LONG direction
4. Sort by score descending, take top scorer if score ≥ 5

### Phase 4 — Execute
1. Compute leverage: `min(10, venue_max_for_asset)` — read from `market_list_instruments` result
2. Compute margin: `account_value * 0.28` (max $30 for $100 wallet — 3 slots × 28% = 84% max committed)
3. `create_position(coin, direction="LONG", leverage, margin, orderType="FEE_OPTIMIZED_LIMIT", feeOptimizedLimitOptions={ensureExecutionAsTaker:true, executionTimeoutSeconds:60}, stopLoss={percentage:22, orderType:"MARKET"})`
4. `ratchet_stop_add(strategyId, asset, strategyWalletAddress, ratchetStopConfig={tiered:{tiers:[{triggerRoe:15,lockRoe:0},{triggerRoe:30,lockRoe:45},{triggerRoe:60,lockRoe:68},{triggerRoe:100,lockRoe:80},{triggerRoe:150,lockRoe:90}]}})`
5. Write to state: open_time, entry_score, leverage_used, venue_max
6. Write `/opt/data/spider_swing_firstseen.json` if updated

### Phase 5 — Report
- ONLY send Telegram message if a position was successfully opened
- Format: `🕷️ SWING opened LONG {coin} @ {price} | score={score} | margin=${margin} | {leverage}x | 24h_rs={rs}%`
- Silent on all other outcomes

## XYZ Asset Handling

- XYZ equities require `dex="xyz"` on `market_get_asset_data`
- XYZ positions appear in clearinghouse `xyz.assetPositions`
- Account value: `max(main.crossMarginSummary.accountValue, xyz.crossMarginSummary.accountValue)` — NOT summed
- Leverage clamping: XYZ assets generally cap at 10x; some (like SKHX) may cap lower — always read from instruments

## Cost Budget

~15-25 MCP calls per tick across universe scan + top-3 candidate deep-dives.
At 15-min cadence: ~96 ticks/day × ~20 calls avg = ~$2.50/day estimated.

## Skill Attribution

When creating the strategy wallet, include:
```json
"skillName": "spider-swing",
"skillVersion": "1.0.0"
```
