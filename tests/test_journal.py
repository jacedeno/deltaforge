import sqlite3

import pytest

from deltaforge.live.journal import Journal, TradeRecord

REC = dict(
    symbol="PFE", occ="PFE260814C00024500", strike=24.5, expiry="2026-08-14",
    dte_at_entry=12, signal_ts="2026-07-27T18:00:00+00:00", entry_price=24.84,
    stop_price=24.61, target_price=25.56, risk_per_share=0.23, contracts=2,
    delta_at_entry=0.55, limit_price=0.62,
)


@pytest.fixture
def journal(tmp_path) -> Journal:
    j = Journal(tmp_path / "df.db")
    yield j
    j.close()


def test_pending_then_filled_then_closed(journal):
    tid = journal.open_pending(TradeRecord(**REC))
    assert [r["status"] for r in journal.open_trades()] == ["pending"]

    journal.mark_filled(tid, fill=0.64, order_id="o1", fees=1.30, filled_at="2026-07-27T18:01:00+00:00")
    row = journal.open_trades()[0]
    assert row["status"] == "open"
    assert row["entry_fill"] == 0.64
    assert row["debit"] == pytest.approx(0.64 * 100 * 2)

    journal.mark_closed(tid, exit_fill=0.90, order_id="o2", reason="target",
                        fees_total=2.60, underlying=25.6, closed_at="2026-07-29T18:00:00+00:00")
    assert journal.open_trades() == []


def test_pnl_is_net_of_fees(journal):
    tid = journal.open_pending(TradeRecord(**REC))
    journal.mark_filled(tid, 0.50, "o1", 1.30, "t")
    journal.mark_closed(tid, 0.80, "o2", "target", 2.60, 25.0, "t2")
    conn = sqlite3.connect(journal.path)
    conn.row_factory = sqlite3.Row
    pnl = conn.execute("SELECT pnl FROM trades WHERE id=?", (tid,)).fetchone()["pnl"]
    conn.close()
    # (0.80 - 0.50) * 100 * 2 contracts = $60 gross, minus $2.60 round trip.
    assert pnl == pytest.approx(60.0 - 2.60)


def test_deployed_debit_counts_only_open(journal):
    a = journal.open_pending(TradeRecord(**REC))
    journal.mark_filled(a, 1.00, "o1", 1.30, "t")
    b = journal.open_pending(TradeRecord(**{**REC, "symbol": "F", "occ": "F260814C00012000"}))
    journal.mark_filled(b, 0.50, "o3", 1.30, "t")
    assert journal.deployed_debit() == pytest.approx(200.0 + 100.0)

    journal.mark_closed(b, 0.60, "o4", "stop", 2.60, 12.0, "t2")
    assert journal.deployed_debit() == pytest.approx(200.0)


def test_aborted_entry_is_recorded_not_dropped(journal):
    tid = journal.open_pending(TradeRecord(**REC))
    journal.abort(tid, "unfilled")
    assert journal.open_trades() == []
    conn = sqlite3.connect(journal.path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT status, exit_reason FROM trades WHERE id=?", (tid,)).fetchone()
    conn.close()
    assert row["status"] == "aborted" and row["exit_reason"] == "unfilled"


def test_open_symbols_blocks_duplicate_underlying(journal):
    tid = journal.open_pending(TradeRecord(**REC))
    journal.mark_filled(tid, 0.64, "o1", 1.30, "t")
    assert journal.open_symbols() == {"PFE"}


def test_dashboard_can_read_while_bot_holds_the_file(journal, tmp_path):
    """WAL mode: the dashboard opens the same file read-only, concurrently."""
    tid = journal.open_pending(TradeRecord(**REC))
    journal.mark_filled(tid, 0.64, "o1", 1.30, "t")
    ro = sqlite3.connect(f"file:{journal.path}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    rows = list(ro.execute("SELECT symbol, status FROM trades"))
    ro.close()
    assert [(r["symbol"], r["status"]) for r in rows] == [("PFE", "open")]
