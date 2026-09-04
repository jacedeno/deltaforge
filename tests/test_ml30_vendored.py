"""The live bot's signal code ships in the repo; only backtest-only symbols need the external checkout."""

import importlib
import sys

import pytest


def _reload_bridge(monkeypatch, repo_path: str):
    monkeypatch.setenv("ML30_REPO_PATH", repo_path)
    for m in [k for k in sys.modules if k == "deltaforge.settings" or k.startswith("deltaforge.ml30")]:
        del sys.modules[m]
    import deltaforge.ml30_bridge as bridge

    return importlib.reload(bridge)


def test_live_surface_imports_without_external_repo(monkeypatch, tmp_path):
    bridge = _reload_bridge(monkeypatch, str(tmp_path / "nowhere"))
    assert not bridge.external_repo_available()
    # Everything run_paper_bot.py touches resolves from the vendored package.
    assert bridge.EntryLogic and bridge.add_indicators and bridge.calculate_initial_stop
    assert bridge.AlpacaHistoricalClient and bridge.AlpacaClientError and bridge.Direction
    assert bridge.settings_with_credentials("k", "s").alpaca.api_key.get_secret_value() == "k"
    assert bridge.ml30_commit().endswith("(vendored)")


def test_backtest_only_symbols_explain_what_is_missing(monkeypatch, tmp_path):
    bridge = _reload_bridge(monkeypatch, str(tmp_path / "nowhere"))
    with pytest.raises(RuntimeError, match="live bot does not need it"):
        _ = bridge.Coordinator


def test_vendored_modules_do_not_reach_outside_the_package():
    import deltaforge.ml30 as pkg
    from pathlib import Path

    for f in Path(pkg.__file__).parent.glob("*.py"):
        for line in f.read_text().splitlines():
            if line.startswith(("from ", "import ")):
                assert not line.startswith(("from strategy", "from config", "from data", "from backtest")), (f.name, line)
