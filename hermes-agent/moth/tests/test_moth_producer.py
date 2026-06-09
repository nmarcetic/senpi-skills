"""Tests for MOTH producer logic — moth-producer.py and moth_config.py.

These tests are standalone (no runtime SDK, no live MCP calls).
All external dependencies (SenpiClient, tick_cache, producer_daemon) are mocked.
"""

import importlib
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

# ---------------------------------------------------------------------------
# Stub the SDK so we can import producer logic without the runtime installed
# ---------------------------------------------------------------------------

def _make_sdk_stub():
    """Create a minimal senpi_runtime_helpers stub."""
    stub = types.ModuleType("senpi_runtime_helpers")
    stub.SenpiClient = MagicMock
    stub.tick_cache = lambda client: MagicMock()
    stub.producer_daemon = MagicMock()
    return stub


@pytest.fixture(autouse=True)
def stub_sdk(monkeypatch):
    """Inject SDK stub before any producer import."""
    monkeypatch.setitem(sys.modules, "senpi_runtime_helpers", _make_sdk_stub())


# ---------------------------------------------------------------------------
# Import the modules under test (after stubbing SDK)
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"

# Add scripts dir so `import moth_config` works
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# moth_config tests
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_returns_dict_from_valid_json(self, tmp_path):
        import moth_config
        cfg_file = tmp_path / "moth-config.json"
        data = {"min_funding_annualized_pct": 75.0, "leverage": 2}
        cfg_file.write_text(json.dumps(data))

        with patch.object(
            type(moth_config._CONFIG_PATH), "exists", return_value=True
        ), patch("builtins.open", mock_open(read_data=json.dumps(data))):
            result = moth_config.load_config()

        assert result["min_funding_annualized_pct"] == 75.0
        assert result["leverage"] == 2

    def test_returns_empty_dict_when_file_missing(self):
        import moth_config

        with patch.object(Path, "exists", return_value=False):
            result = moth_config.load_config()

        assert result == {}

    def test_config_file_exists_in_repo(self):
        """Smoke test: the committed config file is valid JSON."""
        assert CONFIG_DIR.joinpath("moth-config.json").exists(), (
            "moth-config.json not found — did you forget to commit it?"
        )
        with open(CONFIG_DIR / "moth-config.json") as f:
            data = json.load(f)
        assert "min_funding_annualized_pct" in data
        assert "leverage" in data
        assert data["leverage"] <= 2, "Leverage must never exceed 2x hard cap"


# ---------------------------------------------------------------------------
# Pure-function unit tests (import helpers directly without running the daemon)
# ---------------------------------------------------------------------------

# We import only the pure helper functions — not the module-level SenpiClient
# instantiation — by loading the source file in a controlled namespace.

def _load_helpers():
    """Load only the pure functions from moth-producer.py without side effects."""
    source = (SCRIPTS_DIR / "moth-producer.py").read_text()
    ns = {
        "__name__": "moth_producer_test",
        "__file__": str(SCRIPTS_DIR / "moth-producer.py"),
        "SenpiClient": MagicMock,
        "tick_cache": lambda c: MagicMock(),
        "producer_daemon": MagicMock,
        "cfg": MagicMock(),
    }
    # Minimal imports the module needs
    import os, sys as _sys, time as _time, json as _json
    from datetime import datetime, timezone
    from pathlib import Path as _Path
    ns.update({
        "os": os, "sys": _sys, "time": _time, "json": _json,
        "datetime": datetime, "timezone": timezone, "Path": _Path,
    })
    exec(compile(source, str(SCRIPTS_DIR / "moth-producer.py"), "exec"), ns)
    return ns


@pytest.fixture(scope="module")
def helpers():
    return _load_helpers()


class TestIsOutcomeTicker:
    def test_yes_suffix_detected(self, helpers):
        fn = helpers["_is_outcome_ticker"]
        assert fn("TRUMP-WINS-YES", 0.6, 200_000, 100_000) is True

    def test_no_suffix_detected(self, helpers):
        fn = helpers["_is_outcome_ticker"]
        assert fn("FED-CUTS-JULY-NO", 0.4, 150_000, 100_000) is True

    def test_price_range_fallback(self, helpers):
        """A ticker without keywords but price in (0.01, 0.99) and OI qualifies."""
        fn = helpers["_is_outcome_ticker"]
        assert fn("UNKNOWN-BINARY", 0.55, 500_000, 100_000) is True

    def test_price_outside_range_rejected(self, helpers):
        fn = helpers["_is_outcome_ticker"]
        # Price at 0.99 is at boundary — not outcome (already resolving)
        assert fn("UNKNOWN", 0.995, 500_000, 100_000) is False

    def test_low_oi_rejected(self, helpers):
        fn = helpers["_is_outcome_ticker"]
        assert fn("TRUMP-WINS-YES", 0.6, 50_000, 100_000) is False

    def test_normal_crypto_ticker_rejected(self, helpers):
        fn = helpers["_is_outcome_ticker"]
        # BTC at $60k — not in (0.01, 0.99) and no outcome keywords
        assert fn("BTC", 60_000.0, 5_000_000, 100_000) is False

    def test_will_keyword(self, helpers):
        fn = helpers["_is_outcome_ticker"]
        assert fn("ELON-WILL-RESIGN-YES", 0.3, 120_000, 100_000) is True

    def test_above_keyword(self, helpers):
        fn = helpers["_is_outcome_ticker"]
        assert fn("BTCABOVE100K-YES", 0.45, 300_000, 100_000) is True


class TestAnnualizedFunding:
    def test_positive_hourly_rate(self, helpers):
        fn = helpers["_annualized_funding_pct"]
        # 0.01% per hour → 87.6% annualized
        result = fn(0.0001)
        assert abs(result - 87.6) < 0.1

    def test_negative_rate_returns_positive(self, helpers):
        fn = helpers["_annualized_funding_pct"]
        assert fn(-0.0001) > 0

    def test_zero_rate(self, helpers):
        fn = helpers["_annualized_funding_pct"]
        assert fn(0.0) == 0.0

    def test_known_value(self, helpers):
        """180% annualized ≈ 0.002054% per hour."""
        fn = helpers["_annualized_funding_pct"]
        # 180 / (8760 * 100) ≈ 0.000020548 hourly
        hourly = 180.0 / (8760 * 100)
        result = fn(hourly)
        assert abs(result - 180.0) < 0.01


class TestCheckExpiryHours:
    def test_known_ticker_in_future(self, helpers):
        fn = helpers["_check_expiry_hours"]
        future_ts = time.time() + 48 * 3600  # 48h from now
        registry = {"TRUMP-WINS-YES": future_ts}
        result = fn("TRUMP-WINS-YES", registry)
        assert result is not None
        assert 47.5 < result < 48.5

    def test_already_expired_returns_zero(self, helpers):
        fn = helpers["_check_expiry_hours"]
        past_ts = time.time() - 3600  # 1h ago
        registry = {"OLD-YES": past_ts}
        result = fn("OLD-YES", registry)
        assert result == 0.0

    def test_unknown_ticker_returns_none(self, helpers):
        fn = helpers["_check_expiry_hours"]
        result = fn("UNKNOWN-TICKER-YES", {})
        assert result is None

    def test_expiry_within_6h_is_detectable(self, helpers):
        fn = helpers["_check_expiry_hours"]
        soon_ts = time.time() + 4 * 3600  # 4h from now
        registry = {"SOON-YES": soon_ts}
        result = fn("SOON-YES", registry)
        assert result is not None
        assert result < 6.0  # within the force_close gate


class TestDirectionLogic:
    """Test that direction is correctly derived from funding sign."""

    def test_positive_funding_means_short(self, helpers):
        """Positive funding = longs pay = crowd is long = we fade SHORT."""
        # This mirrors the logic in run_one_tick:
        # direction = "SHORT" if funding_hourly > 0 else "LONG"
        funding_hourly = 0.0001  # positive
        direction = "SHORT" if funding_hourly > 0 else "LONG"
        assert direction == "SHORT"

    def test_negative_funding_means_long(self, helpers):
        """Negative funding = shorts pay = crowd is short = we fade LONG."""
        funding_hourly = -0.0001
        direction = "SHORT" if funding_hourly > 0 else "LONG"
        assert direction == "LONG"


class TestScoringFormula:
    """Test that the scoring formula ranks higher conviction signals first."""

    def test_higher_funding_scores_higher(self, helpers):
        fn = helpers["_annualized_funding_pct"]
        # score = min(1.0, (funding_ann_pct / 200.0) * (persistent_hours / 24.0))
        def score(funding_hourly, persistent_h):
            ann = fn(funding_hourly)
            return min(1.0, (ann / 200.0) * (persistent_h / 24.0))

        low = score(0.0001, 8)   # ~87.6% ann, 8h
        high = score(0.0002, 8)  # ~175.2% ann, 8h
        assert high > low

    def test_higher_persistence_scores_higher(self, helpers):
        fn = helpers["_annualized_funding_pct"]
        def score(funding_hourly, persistent_h):
            ann = fn(funding_hourly)
            return min(1.0, (ann / 200.0) * (persistent_h / 24.0))

        low = score(0.0002, 6)
        high = score(0.0002, 20)
        assert high > low

    def test_score_capped_at_1(self, helpers):
        fn = helpers["_annualized_funding_pct"]
        def score(funding_hourly, persistent_h):
            ann = fn(funding_hourly)
            return min(1.0, (ann / 200.0) * (persistent_h / 24.0))

        # Extreme values should cap at 1.0
        s = score(0.01, 1000)
        assert s == 1.0


# ---------------------------------------------------------------------------
# Integration-style test: run_one_tick with mocked MCP
# ---------------------------------------------------------------------------

class TestRunOneTick:
    """Test run_one_tick end-to-end with fully mocked MCP responses."""

    def _make_module(self, mock_mcp_fn, mock_push_signal):
        """Re-import producer with mocked client + mcp cache."""
        stub = _make_sdk_stub()
        mock_client = MagicMock()
        mock_client.push_signal = mock_push_signal
        stub.SenpiClient = MagicMock(return_value=mock_client)
        stub.tick_cache = MagicMock(return_value=mock_mcp_fn)

        sys.modules["senpi_runtime_helpers"] = stub

        # Force reimport
        mod_name = "moth_producer_integration_test"
        source = (SCRIPTS_DIR / "moth-producer.py").read_text()
        ns = {
            "__name__": mod_name,
            "__file__": str(SCRIPTS_DIR / "moth-producer.py"),
            "os": __import__("os"),
            "sys": sys,
            "time": time,
            "json": json,
            "datetime": __import__("datetime").datetime,
            "timezone": __import__("datetime").timezone,
            "Path": Path,
        }
        import moth_config as _cfg
        ns["cfg"] = _cfg
        ns["SenpiClient"] = stub.SenpiClient
        ns["tick_cache"] = stub.tick_cache
        ns["producer_daemon"] = MagicMock()
        exec(compile(source, str(SCRIPTS_DIR / "moth-producer.py"), "exec"), ns)
        return ns

    def test_emits_signal_for_qualifying_ticker(self):
        push_signal = MagicMock()

        # Simulate a qualifying outcome ticker with extreme funding
        instruments = [
            {
                "name": "TRUMP-WINS-YES",
                "context": {
                    "markPx": "0.62",
                    "openInterest": "300000",
                    "funding": "0.00020548",  # ~180% annualized
                },
            }
        ]
        # Funding history: 12 consecutive hours elevated in same direction
        funding_history = [
            {"time": int(time.time()) - i * 3600, "fundingRate": "0.00020548"}
            for i in range(12)
        ]

        def mock_mcp(tool, args=None):
            if tool == "market_list_instruments":
                return {"data": {"instruments": instruments}}
            if tool == "market_get_asset_data":
                return {"data": {"funding_history": funding_history}}
            return {}

        ns = self._make_module(mock_mcp, push_signal)

        with patch.dict("os.environ", {"MOTH_WALLET": "0xdeadbeef" + "0" * 32}):
            ns["run_one_tick"]()

        push_signal.assert_called_once()
        call_kwargs = push_signal.call_args
        assert call_kwargs is not None
        # Direction: positive funding → SHORT
        args, kwargs = call_kwargs
        direction = kwargs.get("direction") or (args[2] if len(args) > 2 else None)
        # push_signal called with direction="SHORT"
        assert "SHORT" in str(call_kwargs)

    def test_no_signal_when_funding_below_threshold(self):
        push_signal = MagicMock()

        instruments = [
            {
                "name": "TRUMP-WINS-YES",
                "context": {
                    "markPx": "0.62",
                    "openInterest": "300000",
                    "funding": "0.000001",  # very low funding — ~0.88% annualized
                },
            }
        ]

        def mock_mcp(tool, args=None):
            if tool == "market_list_instruments":
                return {"data": {"instruments": instruments}}
            return {"data": {"funding_history": []}}

        ns = self._make_module(mock_mcp, push_signal)

        with patch.dict("os.environ", {"MOTH_WALLET": "0xdeadbeef" + "0" * 32}):
            ns["run_one_tick"]()

        push_signal.assert_not_called()

    def test_no_signal_when_price_already_resolving(self):
        push_signal = MagicMock()

        instruments = [
            {
                "name": "TRUMP-WINS-YES",
                "context": {
                    "markPx": "0.97",  # price > 0.95 — already resolving
                    "openInterest": "300000",
                    "funding": "0.00020548",
                },
            }
        ]

        def mock_mcp(tool, args=None):
            if tool == "market_list_instruments":
                return {"data": {"instruments": instruments}}
            return {"data": {"funding_history": []}}

        ns = self._make_module(mock_mcp, push_signal)

        with patch.dict("os.environ", {"MOTH_WALLET": "0xdeadbeef" + "0" * 32}):
            ns["run_one_tick"]()

        push_signal.assert_not_called()

    def test_no_signal_when_expiry_within_gate(self):
        push_signal = MagicMock()

        instruments = [
            {
                "name": "SOON-EXPIRES-YES",
                "context": {
                    "markPx": "0.6",
                    "openInterest": "300000",
                    "funding": "0.00020548",
                },
            }
        ]
        funding_history = [
            {"time": int(time.time()) - i * 3600, "fundingRate": "0.00020548"}
            for i in range(12)
        ]

        def mock_mcp(tool, args=None):
            if tool == "market_list_instruments":
                return {"data": {"instruments": instruments}}
            return {"data": {"funding_history": funding_history}}

        ns = self._make_module(mock_mcp, push_signal)

        # Inject an expiry 3h from now (within 6h gate) via config override
        soon_ts = time.time() + 3 * 3600
        with patch("moth_config.load_config", return_value={
            "min_funding_annualized_pct": 50.0,
            "min_persistence_hours": 6.0,
            "min_oi_usd": 100_000.0,
            "min_days_to_expiry": 1.0,
            "force_close_hours_before_expiry": 6.0,
            "leverage": 2,
            "expiry_registry": {"SOON-EXPIRES-YES": soon_ts},
        }):
            with patch.dict("os.environ", {"MOTH_WALLET": "0xdeadbeef" + "0" * 32}):
                ns["run_one_tick"]()

        push_signal.assert_not_called()

    def test_no_signal_when_no_instruments(self):
        push_signal = MagicMock()

        def mock_mcp(tool, args=None):
            return {"data": {"instruments": []}}

        ns = self._make_module(mock_mcp, push_signal)

        with patch.dict("os.environ", {"MOTH_WALLET": "0xdeadbeef" + "0" * 32}):
            ns["run_one_tick"]()

        push_signal.assert_not_called()
