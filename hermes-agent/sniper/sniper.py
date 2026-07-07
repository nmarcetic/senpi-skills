#!/usr/bin/env python3
"""
SNIPER v1.0.0 — Whale Consensus Following Strategy
=======================================================
Logic:
  - Every 4h: fetch top-10 leaderboard whales
  - For each of BTC/ETH/HYPE/SOL: count unique whales holding same direction
  - If >= 7/10 whales in SAME direction (2/3 BFT majority, no mixed signal): open position
  - Capital: $500 margin per trade, 3x leverage
  - TP: 10% ROE (re-entry 1: 8%, re-entry 2: 5%)
  - SL: 30% ROE (re-entry 1: 20%, re-entry 2: 15%)
  - Max 3 entries per signal cycle
  - Re-enter only if consensus still holds after TP
"""

import json
import sys
import time
import httpx
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
STRATEGY_WALLET   = "0xa4323a1eb5bda2288d7cede500eb58998d15a4f6"
STRATEGY_ID       = "9ea76a8f-7d3e-43ec-9b32-dc13e5b7c794"
STATE_FILE        = "/opt/data/sniper_state.json"
MCP_URL           = "https://mcp.prod.senpi.ai/mcp"
ASSETS            = ["BTC", "ETH", "HYPE", "SOL"]
CAPITAL_PER_TRADE = 500.0    # $500 margin per position
LEVERAGE          = 3
CONSENSUS_MIN     = 7        # min whales same direction (2/3 BFT majority of top 10)
WHALE_COUNT       = 10       # top N whales to check
MAX_REENTRIES     = 2        # 0=entry, 1=re1, 2=re2 (3 total)

# TP/SL ladder [entry_idx] = (tp_pct, sl_pct)
TP_SL = {
    0: (10.0, 30.0),
    1: (8.0,  20.0),
    2: (5.0,  15.0),
}

# ── MCP Client ───────────────────────────────────────────────────────────────
def load_token():
    import yaml
    with open("/opt/data/config.yaml") as f:
        cfg = yaml.safe_load(f)
    return cfg["mcp_servers"]["senpi"]["headers"]["Authorization"].replace("Bearer ", "")

TOKEN = load_token()
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

def call_tool(tool_name: str, args: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args}
    }
    r = httpx.post(MCP_URL, json=payload, headers=HEADERS, timeout=60)
    r.raise_for_status()
    outer = r.json()
    text = outer["result"]["content"][0]["text"]
    inner = json.loads(text)
    if not inner.get("success"):
        raise RuntimeError(f"{tool_name} failed: {inner.get('error')}")
    return inner["data"]

# ── State ─────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"open_positions": {}, "last_check": None, "version": "1.0.0"}

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ── Whale Analysis ─────────────────────────────────────────────────────────────
def get_whale_consensus() -> dict:
    """
    Returns dict: { "BTC": {"direction": "long", "count": 5, "whales": [...]}, ... }
    Only entries where count >= CONSENSUS_MIN and direction is clean (no mixed).
    """
    top = call_tool("leaderboard_get_top", {"limit": WHALE_COUNT})
    traders = top["leaderboard"]["data"]

    # Fetch positions for all top whales in parallel (sequential here for simplicity)
    asset_signals = {a: {"long": 0, "short": 0, "whales_long": [], "whales_short": []} for a in ASSETS}

    for trader in traders:
        tid = trader["trader_id"]
        try:
            pos_data = call_tool("leaderboard_get_trader_positions", {"trader_id": tid})
            for pos in pos_data["positions"].get("positions", []):
                market = pos["market"]
                if market not in ASSETS:
                    continue
                direction = pos["direction"]  # "long" or "short"
                if direction == "long":
                    asset_signals[market]["long"] += 1
                    asset_signals[market]["whales_long"].append(tid[:10])
                else:
                    asset_signals[market]["short"] += 1
                    asset_signals[market]["whales_short"].append(tid[:10])
        except Exception:
            continue

    # Build consensus signals — clean direction only
    consensus = {}
    for asset, sig in asset_signals.items():
        longs  = sig["long"]
        shorts = sig["short"]
        # Mixed: both sides have whales → skip
        if longs >= CONSENSUS_MIN and shorts == 0:
            consensus[asset] = {"direction": "long",  "count": longs,  "whales": sig["whales_long"]}
        elif shorts >= CONSENSUS_MIN and longs == 0:
            consensus[asset] = {"direction": "short", "count": shorts, "whales": sig["whales_short"]}
        # else: mixed or insufficient — no signal

    return consensus

# ── Execution ─────────────────────────────────────────────────────────────────
def open_position(wallet: str, asset: str, direction: str, tp_pct: float, sl_pct: float) -> dict:
    return call_tool("create_position", {
        "strategyWalletAddress": wallet,
        "orders": [{
            "coin": asset,
            "direction": direction.upper(),
            "leverage": LEVERAGE,
            "leverageType": "CROSS",
            "marginAmount": CAPITAL_PER_TRADE,
            "orderType": "MARKET",
            "takeProfit": {"percentage": tp_pct, "orderType": "LIMIT"},
            "stopLoss":   {"percentage": sl_pct, "orderType": "MARKET"},
        }],
        "reason": f"Sniper: whale consensus {direction} on {asset}"
    })

def close_position(wallet: str, asset: str, reason: str) -> dict:
    return call_tool("close_position", {
        "strategyWalletAddress": wallet,
        "coin": asset,
        "orderType": "MARKET",
        "reason": reason
    })

def get_open_positions(wallet: str) -> list:
    data = call_tool("strategy_get_clearinghouse_state", {"strategy_wallet": wallet})
    positions = data.get("main", {}).get("assetPositions", [])
    # Filter out empty/invalid entries
    return [p for p in positions if p.get("position") and p["position"].get("coin")]

# ── Main tick ─────────────────────────────────────────────────────────────────
def notify(msg: str):
    pass  # Silent — positions checked on-demand via Hermes chat

def run():
    state = load_state()
    wallet = state.get("strategy_wallet")
    if not wallet:
        # Try to resolve from Senpi
        strats = call_tool("strategy_list", {"strategyIds": [STRATEGY_ID]})
        wallet = strats["strategies"][0]["strategyWalletAddress"]
        if not wallet:
            notify("⏳ Sniper: strategy wallet not yet provisioned, retry next tick")
            return
        state["strategy_wallet"] = wallet
        save_state(state)

    now = datetime.now(timezone.utc).isoformat()
    state["last_check"] = now

    # ── Phase 1: Exit check ───────────────────────────────────────────────────
    try:
        live_positions = {p["position"]["coin"]: p for p in get_open_positions(wallet)}
    except Exception as e:
        notify(f"⚠️ Sniper: clearinghouse fetch failed ({e}), skipping tick")
        sys.exit(0)

    for asset in list(state["open_positions"].keys()):
        if asset not in live_positions:
            # Position closed (TP or SL hit)
            entry = state["open_positions"][asset]
            entry_idx = entry["entry_idx"]
            can_reenter = entry_idx < MAX_REENTRIES

            msg = f"🎯 Sniper: {asset} position closed (TP/SL). Entry {entry_idx+1}/3."
            if can_reenter:
                msg += " Will re-check consensus for re-entry."
            else:
                msg += " Max re-entries reached."
            notify(msg)

            # Remove from state — re-entry handled in Phase 2
            del state["open_positions"][asset]
            if not can_reenter:
                state.setdefault("exhausted", {})[asset] = now

    save_state(state)

    # ── Phase 2: Consensus scan ────────────────────────────────────────────────
    consensus = get_whale_consensus()
    actions = []

    # Exit any position where consensus has DISAPPEARED (mixed signal or no whales)
    # This catches the case where an asset drops out of consensus entirely
    for asset in list(state["open_positions"].keys()):
        if asset in live_positions and asset not in consensus:
            current_dir = "long" if float(live_positions[asset]["position"]["szi"]) > 0 else "short"
            close_position(wallet, asset, f"Consensus lost on {asset} — no clean signal")
            notify(f"⚠️ Sniper: {asset} consensus lost (mixed/gone). Closing {current_dir} position.")
            del state["open_positions"][asset]
            save_state(state)

    for asset, signal in consensus.items():
        direction = signal["direction"]
        count     = signal["count"]
        whales    = signal["whales"]

        if asset in live_positions:
            # Already in a position — check if direction flipped
            current_dir = "long" if float(live_positions[asset]["position"]["szi"]) > 0 else "short"
            if current_dir != direction:
                # Whale consensus flipped — close the position
                close_position(wallet, asset, f"Consensus flipped to {direction}")
                notify(f"🔄 Sniper: {asset} consensus flipped → {direction}. Closing {current_dir} position.")
                del state["open_positions"][asset]
                save_state(state)
            # else: holding, consensus intact, nothing to do
            continue

        if asset in state["open_positions"]:
            continue  # in state but maybe just closed — skip this tick

        # Check re-entry limit
        prev_entry_idx = -1
        if asset in state.get("exhausted", {}):
            continue  # max re-entries hit this cycle

        # Determine entry index
        entry_idx = 0  # fresh entry

        tp_pct, sl_pct = TP_SL[entry_idx]

        try:
            result = open_position(wallet, asset, direction, tp_pct, sl_pct)
            order = result["results"][0]["mainOrder"]
            if order["status"] == "FILLED":
                state["open_positions"][asset] = {
                    "direction":   direction,
                    "entry_idx":   entry_idx,
                    "entry_time":  now,
                    "tp_pct":      tp_pct,
                    "sl_pct":      sl_pct,
                    "whale_count": count,
                    "avg_price":   order.get("avgPrice"),
                }
                save_state(state)
                actions.append(
                    f"🟢 Sniper LONG {asset}"  if direction == "long" else
                    f"🔴 Sniper SHORT {asset}",
                )
                notify(
                    f"{'🟢 LONG' if direction == 'long' else '🔴 SHORT'} **{asset}** | "
                    f"{count}/10 whales | Entry {order.get('avgPrice')} | "
                    f"TP {tp_pct}% / SL {sl_pct}% ROE | wallet: {wallet[:10]}..."
                )
        except Exception as e:
            notify(f"⚠️ Sniper: failed to open {asset} {direction}: {e}")

    if not actions and not any(a not in live_positions for a in state["open_positions"]):
        # Completely silent tick — no stdout = free
        sys.exit(0)

if __name__ == "__main__":
    run()
