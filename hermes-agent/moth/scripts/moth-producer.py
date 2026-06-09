#!/usr/bin/env python3
# Senpi MOTH Producer v1.0.0
# Copyright 2026 Nikola / Senpi (https://senpi.ai)
# Licensed under MIT
# Source: https://github.com/Senpi-ai/senpi-skills
"""MOTH v3.1 Producer — Leaderboard crowding fade signal emitter.

Dual-mode funding strategy on Hyperliquid perps:
- Mode A (SHORT): fades extreme funding when top-20 traders are absent
- Mode B (LONG): rides momentum when smart money is in AND funding confirms

This producer is the reference implementation for senpi-trading-runtime operators.
For Hermes cron deployment, the cron prompt IS the runtime — this script is not used.

Environment variables:
  SENPI_AUTH_TOKEN             — REQUIRED. Bearer token for MCP + signal POST.
  MOTH_WALLET                  — REQUIRED. Moth strategy wallet address.
  SENPI_MCP_URL                — optional (default https://mcp.prod.senpi.ai/mcp)
  MOTH_DECISION_MODEL          — bare LLM model name (no provider prefix)
  EXTERNAL_SCANNER_NAME        — optional override (default "moth_signals")
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── SDK path resolution ───────────────────────────────────────────────────────
_sdk_candidates = [
    str(Path(__file__).resolve().parents[2] / "senpi-trading-runtime"),
    str(Path.home() / "skills" / "senpi-trading-runtime"),
]
_sdk_path = next(
    (p for p in _sdk_candidates if (Path(p) / "senpi_runtime_helpers").is_dir()),
    _sdk_candidates[0],
)
if _sdk_path not in sys.path:
    sys.path.insert(0, _sdk_path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moth_config as cfg  # noqa: E402

from senpi_runtime_helpers import SenpiClient, producer_daemon, tick_cache  # type: ignore  # noqa: E402

# ── Identity ──────────────────────────────────────────────────────────────────
# Agent-specific wallet env var — do NOT fall back to a generic STRATEGY_ADDRESS.
# Per fleet contamination rules: a shared env var in a multi-agent deploy silently
# emits to the wrong wallet.
MOTH_WALLET = os.environ.get("MOTH_WALLET", "")
SCANNER_NAME = os.environ.get("EXTERNAL_SCANNER_NAME", "moth_signals")
LOCK_NAME = f"moth-{MOTH_WALLET[2:10]}" if len(MOTH_WALLET) > 10 else "moth-dev"

# ── Outcome ticker detection ──────────────────────────────────────────────────
# Outcome market tickers on Hyperliquid follow patterns like:
#   TRUMP-WINS-YES, FED-CUTS-JULY-YES, BTCABOVE100K-YES, etc.
# They always trade between 0 and 1 (probability). We detect by:
#   1. Name contains known outcome suffixes/keywords
#   2. markPx in (0.01, 0.99) AND OI > min threshold
_OUTCOME_KEYWORDS = ("-YES", "-NO", "-WILL", "-WINS", "-ABOVE", "-BELOW", "-BEFORE", "-PASSES")


def _is_outcome_ticker(name: str, mark_px: float, oi_usd: float, min_oi_usd: float) -> bool:
    """Return True if this instrument looks like an outcome/prediction market ticker."""
    name_upper = name.upper()
    has_keyword = any(kw in name_upper for kw in _OUTCOME_KEYWORDS)
    price_in_range = 0.01 < mark_px < 0.99
    has_oi = oi_usd >= min_oi_usd
    return (has_keyword or price_in_range) and has_oi


def _annualized_funding_pct(hourly_rate: float) -> float:
    """Convert per-hour funding rate to annualized %. Correct: ×8760, not ×3×365."""
    return abs(hourly_rate) * 8760 * 100


def _check_expiry_hours(name: str, expiry_registry: dict) -> float | None:
    """
    Return hours until expiry for a known ticker, or None if unknown.

    Expiry data is not yet natively available in the Hyperliquid MCP surface
    for outcome tickers. This function checks a producer-maintained registry
    (loaded from config or populated from market metadata when available).

    In production the operator should populate expiry_registry from the
    Hyperliquid API or Senpi docs. Unknown tickers are treated conservatively
    (allowed to trade, but logged as unverified).
    """
    if name in expiry_registry:
        expiry_ts = expiry_registry[name]
        now_ts = time.time()
        return max(0.0, (expiry_ts - now_ts) / 3600.0)
    return None  # Unknown — conservative: allow but flag


# ── Main tick ─────────────────────────────────────────────────────────────────

client = SenpiClient()
mcp = tick_cache(client)


def run_one_tick() -> None:
    """Single producer tick — scan outcome tickers, emit highest-conviction signal."""

    config = cfg.load_config()

    min_funding_annualized = float(config.get("min_funding_annualized_pct", 50.0))
    min_persistence_hours = float(config.get("min_persistence_hours", 6.0))
    min_oi_usd = float(config.get("min_oi_usd", 100_000.0))
    min_days_to_expiry = float(config.get("min_days_to_expiry", 1.0))
    force_close_hours = float(config.get("force_close_hours_before_expiry", 6.0))
    leverage = int(config.get("leverage", 2))
    max_leverage = 2  # hard cap — binary resolution risk
    leverage = min(leverage, max_leverage)
    expiry_registry: dict = config.get("expiry_registry", {})  # {ticker: unix_ts}

    # ── 1. Pull full instrument list ──────────────────────────────────────────
    resp = mcp("market_list_instruments")
    instruments = resp.get("data", resp).get("instruments", [])

    if not instruments:
        print(f"[MOTH] No instruments returned — skipping tick", flush=True)
        return

    # ── 2. Identify candidate outcome tickers ─────────────────────────────────
    candidates = []
    for inst in instruments:
        name = inst.get("name", "")
        ctx = inst.get("context") or {}
        mark_px_raw = ctx.get("markPx") or ctx.get("midPx") or "0"
        oi_raw = ctx.get("openInterest") or "0"

        try:
            mark_px = float(mark_px_raw)
            oi = float(oi_raw)
            oi_usd = oi * mark_px
        except (ValueError, TypeError):
            continue

        if not _is_outcome_ticker(name, mark_px, oi_usd, min_oi_usd):
            continue

        # Price gate — not already resolved
        if mark_px <= 0.05 or mark_px >= 0.95:
            continue

        # Expiry gate — never enter within force_close_hours of resolution
        hours_left = _check_expiry_hours(name, expiry_registry)
        min_hours_required = min_days_to_expiry * 24.0
        if hours_left is not None:
            if hours_left < force_close_hours:
                print(f"[MOTH] Skipping {name}: {hours_left:.1f}h until expiry < {force_close_hours}h gate", flush=True)
                continue
            if hours_left < min_hours_required:
                print(f"[MOTH] Skipping {name}: {hours_left:.1f}h until expiry < {min_hours_required:.1f}h minimum", flush=True)
                continue

        # Funding check
        funding_hourly_raw = ctx.get("funding") or "0"
        try:
            funding_hourly = float(funding_hourly_raw)
        except (ValueError, TypeError):
            funding_hourly = 0.0

        funding_ann_pct = _annualized_funding_pct(funding_hourly)

        if funding_ann_pct < min_funding_annualized:
            continue

        # ── Persistence check via funding history ─────────────────────────────
        # Pull last 24h of hourly funding; count hours where |funding| was elevated
        try:
            hist_resp = mcp("market_get_asset_data", {
                "asset": name,
                "candle_intervals": [],
                "include_funding": True,
                "include_order_book": False,
            })
            hist_data = hist_resp.get("data", hist_resp)
            funding_history = hist_data.get("funding_history", [])

            # Count consecutive recent hours with elevated funding in same direction
            sign = 1 if funding_hourly > 0 else -1
            min_hourly_threshold = min_funding_annualized / (8760 * 100)
            persistent_hours = 0
            for row in sorted(funding_history, key=lambda r: r.get("time", 0), reverse=True):
                row_rate = float(row.get("fundingRate", 0))
                if row_rate * sign > min_hourly_threshold * 0.5:  # same direction, half threshold
                    persistent_hours += 1
                else:
                    break  # non-consecutive — stop

        except Exception as e:
            print(f"[MOTH] Could not fetch funding history for {name}: {e}", flush=True)
            persistent_hours = 0

        if persistent_hours < min_persistence_hours:
            continue

        # Score: funding magnitude × persistence (prefer strongly persistent signals)
        score = min(1.0, (funding_ann_pct / 200.0) * (persistent_hours / 24.0))

        candidates.append({
            "name": name,
            "mark_px": mark_px,
            "oi_usd": oi_usd,
            "funding_hourly": funding_hourly,
            "funding_ann_pct": funding_ann_pct,
            "persistent_hours": persistent_hours,
            "hours_left": hours_left,
            "score": score,
            "leverage": leverage,
        })

    if not candidates:
        print(f"[MOTH] No qualifying outcome tickers this tick", flush=True)
        return

    # ── 3. Pick highest-conviction signal ─────────────────────────────────────
    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]

    # Direction: fade the crowded side
    # Positive funding → longs (YES buyers) are paying → we go SHORT (buy NO / sell YES)
    # Negative funding → shorts (NO buyers) are paying → we go LONG (buy YES)
    direction = "SHORT" if best["funding_hourly"] > 0 else "LONG"

    print(
        f"[MOTH] Signal: {best['name']} {direction} | "
        f"funding={best['funding_ann_pct']:.1f}% ann | "
        f"persistent={best['persistent_hours']:.0f}h | "
        f"price={best['mark_px']:.3f} | "
        f"oi_usd=${best['oi_usd']:,.0f} | "
        f"score={best['score']:.3f}",
        flush=True,
    )

    # ── 4. Emit signal ────────────────────────────────────────────────────────
    # asset and direction are TOP-LEVEL args — NEVER inside data={}
    client.push_signal(
        address=MOTH_WALLET,
        scanner=SCANNER_NAME,
        asset=best["name"],
        direction=direction,
        score=best["score"],
        signal_type="OUTCOME_FUNDING_FADE",
        data={
            # All keys here MUST match config.fields in runtime.yaml
            "funding_annualized_pct": round(best["funding_ann_pct"], 2),
            "persistent_hours": round(best["persistent_hours"], 1),
            "mark_px": round(best["mark_px"], 4),
            "oi_usd": round(best["oi_usd"]),
            "hours_to_expiry": round(best["hours_left"], 1) if best["hours_left"] is not None else -1.0,
            "leverage_used": best["leverage"],
        },
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not MOTH_WALLET:
        raise EnvironmentError(
            "MOTH_WALLET env var is not set. "
            "Set it to the strategy wallet address before launching the producer."
        )

    producer_daemon(
        fn=run_one_tick,
        interval_seconds=300,   # 5-minute tick — outcome markets are slow
        name=LOCK_NAME,
        wallet=MOTH_WALLET,
        scanner=SCANNER_NAME,
    )
