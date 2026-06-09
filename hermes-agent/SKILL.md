---
name: hermes-agent
description: >-
  Hermes-native trading strategies for Hyperliquid via Senpi MCP.
  No Railway, no OpenClaw — Hermes cron jobs ARE the daemon loop.
  Contains MOTH (dual-mode funding fade) and Spider (scalp + swing momentum).
  Each strategy is fully self-contained: signal logic, risk gates, state file,
  DSL exits — all encoded in the Hermes cron prompt.
license: Apache-2.0
metadata:
  author: nikola
  version: "1.0.0"
  platform: senpi
  exchange: hyperliquid
---

# Hermes-Agent — Hermes-Native Senpi Strategies

This directory contains trading strategies ported to run natively inside Hermes.

## Philosophy

> "You are the runtime, my friend."

The Senpi ecosystem was designed around Railway-hosted OpenClaw daemons. But Hermes can call MCP tools directly, maintain state files, and run cron jobs. That's all a trading daemon IS.

**Hermes pattern:**
- Cron job = producer tick
- MCP tools = signal scanner + execution layer
- State file = risk gate memory + position tracking
- Ratchet stop = DSL profit ladder (native Senpi engine)

## Strategies

| Strategy | Dir | Style | Universe | Cron |
|---|---|---|---|---|
| MOTH v3.1 | `moth/` | Funding fade / smart money ride | Any asset with extreme funding | 30 min |
| Spider Scalp v1.0 | `spider-scalp/` | Macro mean-reversion | BTC/ETH/SOL/HYPE + energy | 5 min |
| Spider Swing v1.0 | `spider-swing/` | Tech/AI multi-day momentum | Dynamic XYZ + crypto alts | 15 min |

## MOTH + Spider — Do They Conflict?

| | MOTH | Spider Scalp | Spider Swing |
|---|---|---|---|
| Universe | Any (funding-driven) | BTC/ETH/SOL/HYPE + energy | XYZ equities + alts |
| Direction | SHORT (Mode A) or LONG (Mode B) | Both | LONG only |
| Hold time | 28–48h | < 2h | Days–weeks |
| Signal | Funding extreme + leaderboard | RSI extreme + MA stretch | 4h/1h trend + RS |
| Overlap risk | Medium (may trade same asset) | Low (different timeframe) | Low (different universe) |

MOTH and Spider Scalp can both trade BTC/ETH/HYPE but on completely different timeframes and signals — a 48h funding fade and a 2h mean-reversion scalp can coexist on the same wallet ecosystem. Different wallets means no position conflict.

## Cost estimates (combined)

| Strategy | Cron | Est. $/day |
|---|---|---|
| MOTH | 30 min | ~$2.30 |
| Spider Scalp | 5 min | ~$1.50 |
| Spider Swing | 15 min | ~$2.50 |
| **Total** | | **~$6.30/day** |
