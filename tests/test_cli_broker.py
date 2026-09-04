"""Orders reach Alpaca through the CLI; the SDK is never asked to place one."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from deltaforge.live import cli_broker
from deltaforge.live.cli_broker import CliBroker, CliError, CliOrder


@pytest.fixture
def broker(monkeypatch):
    # No network: the SDK clients are stubbed, and the CLI binary is a fake path.
    monkeypatch.setattr(cli_broker.Broker, "__init__", lambda self, k, s, paper=True: None)
    monkeypatch.setenv("ALPACA_SECRET_KEY", "leaked-from-shell")
    b = CliBroker("KEY", "SECRET", paper=True, binary="/fake/alpaca")
    return b


def _fake_run(calls, stdout="{}", returncode=0, stderr=""):
    def run(argv, env, capture_output, text, timeout):
        calls.append((argv, env))
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return run


def test_buy_to_open_is_a_cli_limit_order_with_intent(broker, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, json.dumps({"id": "ord-1", "status": "accepted"})))
    assert broker.buy_to_open("SPY260908C00500000", 3, 4.567) == "ord-1"
    argv, env = calls[0]
    assert argv[:3] == ["/fake/alpaca", "order", "submit"]
    flags = dict(zip(argv[3::2], argv[4::2]))
    assert flags["--symbol"] == "SPY260908C00500000" and flags["--qty"] == "3"
    assert flags["--side"] == "buy" and flags["--position-intent"] == "buy_to_open"
    assert flags["--type"] == "limit" and flags["--limit-price"] == "4.57" and flags["--time-in-force"] == "day"
    # Credentials travel in the subprocess env only, and shell leftovers do not.
    assert env["ALPACA_API_KEY"] == "KEY" and env["ALPACA_SECRET_KEY"] == "SECRET" and env["ALPACA_PAPER"] == "true"


def test_sell_to_close_floors_the_limit_at_a_penny(broker, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, json.dumps({"id": "ord-2"})))
    broker.sell_to_close("X", 1, 0.0)
    flags = dict(zip(calls[0][0][3::2], calls[0][0][4::2]))
    assert flags["--side"] == "sell" and flags["--position-intent"] == "sell_to_close" and flags["--limit-price"] == "0.01"


def test_error_objects_raise_even_when_exit_code_is_zero(broker, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run([], json.dumps({"code": 40410000, "error": "order not found"}), returncode=0))
    with pytest.raises(CliError, match="order not found"):
        broker.get_order("nope")


def test_nonzero_exit_without_output_raises(broker, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run([], stdout="", returncode=2, stderr="boom"))
    with pytest.raises(CliError, match="exit 2"):
        broker.get_order("x")


def test_cancel_swallows_errors_like_the_sdk_broker(broker, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run([], json.dumps({"error": "already filled"})))
    broker.cancel("ord-3")  # must not raise


def test_get_order_parses_fills_and_the_helpers_read_them(broker, monkeypatch):
    payload = {"id": "ord-4", "status": "filled", "filled_avg_price": "21.5", "filled_at": "2026-09-03T14:34:21.123Z"}
    monkeypatch.setattr(subprocess, "run", _fake_run([], json.dumps(payload)))
    o = broker.get_order("ord-4")
    assert isinstance(o, CliOrder) and CliBroker.is_filled(o)
    assert CliBroker.fill_price(o) == 21.5 and CliBroker.filled_at(o) == "2026-09-03T14:34:21+00:00"


def test_unfilled_order_reads_as_empty(broker, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run([], json.dumps({"id": "o", "status": "accepted", "filled_avg_price": None, "filled_at": None})))
    o = broker.get_order("o")
    assert not CliBroker.is_filled(o) and CliBroker.fill_price(o) is None and CliBroker.filled_at(o) == ""
