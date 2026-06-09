# hermes-agent/

Hermes-native trading strategies for Hyperliquid via Senpi MCP.

These strategies run **entirely inside Hermes** — no Railway, no OpenClaw, no external daemon hosts.
Hermes cron jobs ARE the producer loop. MCP tool calls ARE the execution layer.

## Strategies

| Strategy | Dir | Description | Cron |
|---|---|---|---|
| MOTH v3.1 | `moth/` | Dual-mode funding strategy (retail fade / smart money ride) | 30 min |
| Spider Scalp | `spider-scalp/` | Macro mean-reversion on BTC/ETH/SOL/HYPE + energy | 5 min |
| Spider Swing | `spider-swing/` | Tech/AI multi-day momentum on XYZ equities + crypto alts | 15 min |

## Architecture

```
Hermes cron tick
  └─ Phase 1: Exit check (read state file, check open positions, close if triggered)
  └─ Phase 2: Entry scan (market data, signals, scoring)
  └─ Phase 3: Execution (create_position + ratchet_stop_add)
  └─ Phase 4: State write (update state file)
  └─ Report: Telegram message ONLY on successful position open
```

## State files

| Strategy | State file |
|---|---|
| MOTH | `/opt/data/moth_state.json` |
| Spider Scalp | `/opt/data/spider_scalp_state.json` |
| Spider Swing | `/opt/data/spider_swing_state.json` |

## Design principles

- **Silent by default** — cron sends Telegram message ONLY on position open
- **State-file risk gates** — daily loss limit, drawdown halt, cooldown, consecutive losses
- **Native SL on every position** — first line of defense
- **Ratchet stop on every position** — profit ladder / trailing stop
- **No external dependencies** — no npm packages, no Railway, no Python daemons
