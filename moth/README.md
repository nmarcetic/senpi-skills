# MOTH v1.0.0 — Deploy Guide

## What it is

Outcome market funding fade on Hyperliquid prediction markets. Detects extreme
funding on binary resolution tickers, enters opposite the crowded side to collect
the funding stream, and hard-exits before resolution.

## Prerequisites

- Running OpenClaw / Senpi runtime host (Railway, VPS, etc.)
- `@senpi-ai/runtime` npm package installed (`npm install @senpi-ai/runtime@latest`)
- Python 3.10+ with `senpi_runtime_helpers` (ships inside `senpi-trading-runtime`)
- A funded Senpi strategy wallet (minimum $100, recommended $200+)
- Your Senpi auth token (`SENPI_AUTH_TOKEN`)

## Environment variables

Set these before deploying:

```bash
export MOTH_WALLET="0x<your-strategy-wallet-address>"
export SENPI_AUTH_TOKEN="eyJ..."
export TELEGRAM_CHAT_ID="<your-telegram-chat-id>"
export MOTH_DECISION_MODEL="claude-sonnet-4-20250514"   # or gemini-2.5-pro
```

## Deploy steps

### 1. Create a strategy wallet via Senpi

```json
{
  "tool": "strategy_create_custom_strategy",
  "args": {
    "initialBudget": 200,
    "positions": [],
    "strategyName": "moth",
    "skill_name": "moth",
    "skill_version": "1.0.0"
  }
}
```

Copy the `strategyWalletAddress` → set as `MOTH_WALLET`.

### 2. Register the runtime

```bash
openclaw senpi runtime create --path /path/to/senpi-skills/moth/runtime.yaml
openclaw senpi runtime list   # confirm registered as moth-tracker
openclaw senpi status
```

### 3. (Optional) Populate expiry registry

Edit `config/moth-config.json` and add known expiry timestamps:

```json
"expiry_registry": {
  "TRUMP-WINS-2026-YES": 1780000000
}
```

### 4. Launch the producer daemon

```bash
nohup python3 -u /path/to/senpi-skills/moth/scripts/moth-producer.py \
  > /tmp/moth-producer.log 2>&1 &
disown
```

### 5. Verify liveness

```bash
ps -ef | grep moth-producer | grep -v grep        # exactly one process
grep daemon_tick_finished /tmp/moth-producer.log | tail -3   # "status":"ok"
```

## Tuning

Edit `config/moth-config.json`:

| Parameter | Default | Notes |
|---|---|---|
| `min_funding_annualized_pct` | 50 | Raise to 80+ for only extreme signals |
| `min_persistence_hours` | 6 | Raise to 12 for higher conviction |
| `min_oi_usd` | 100000 | Lower only if you accept liquidity risk |
| `min_days_to_expiry` | 1.0 | Never lower below 0.5 |
| `force_close_hours_before_expiry` | 6 | **Do not lower below 4** |
| `leverage` | 2 | **Hard max 2x — do not raise** |

## ⚠️ Critical warnings

1. **LEVERAGE CAP IS 2x — NON-NEGOTIABLE.** Outcome markets resolve to 0 or 1.
   If you're on the wrong side at expiry with 10x leverage, you lose everything.

2. **Expiry gate is in the producer.** The DSL cannot know about resolution dates.
   The `force_close_hours_before_expiry` gate only prevents NEW entries. You must
   monitor open positions manually or via the expiry registry as resolution approaches.

3. **Liquidity.** Outcome market books are thin. The 20s execution timeout in
   `runtime.yaml` accounts for this but very illiquid tickers may not fill.
   The `min_oi_usd: 100000` gate is your first defence.
