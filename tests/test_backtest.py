import pytest

from cryptobot.backtest import engine
from cryptobot.backtest.engine import Day


def _days(prices, scores):
    return [Day(f"2024-01-{i + 1:02d}", p, s, {}) for i, (p, s) in enumerate(zip(prices, scores))]


def test_always_in_market_matches_buy_and_hold():
    days = _days([100, 110, 99, 120], [50] * 4)
    s, bh = engine.simulate(days, fee=0), engine.buy_and_hold(days, fee=0)
    assert s.total_return == pytest.approx(bh.total_return) == pytest.approx(0.2)


def test_never_buys_stays_flat():
    s = engine.simulate(_days([100, 50, 200], [0, 0, 0]))
    assert s.total_return == 0 and s.trades == 0


def test_round_trip_trade_and_fees():
    # Вход на закрытии дня 0 (100), выход на закрытии дня 2 (120): +20% минус две комиссии по 1%.
    s = engine.simulate(_days([100, 110, 120, 60], [20, 0, -20, -20]), fee=0.01)
    assert s.trades == 1
    assert s.total_return == pytest.approx(0.99 * 1.2 * 0.99 - 1)
    assert s.max_drawdown == pytest.approx(-0.01)  # только комиссия; падение до 60 — уже вне позиции


def test_signal_uses_only_past_data():
    closes = [100 * 1.01 ** i for i in range(150)]
    candles = [{"date": f"d{i:03d}", "close": c, "volume": 1.0} for i, c in enumerate(closes)]
    before = engine.score_history(candles, {})
    candles[-1]["close"] = 1.0  # меняем будущее — прошлые оценки не должны измениться
    after = engine.score_history(candles, {})
    assert [d.score for d in before[:-1]] == [d.score for d in after[:-1]]


def test_btc_regime_uses_trailing_average():
    candles = [{"date": f"d{i}", "close": c} for i, c in enumerate([10, 10, 10, 13, 7])]
    assert engine.btc_regime(candles, period=3) == {"d2": False, "d3": True, "d4": False}


def test_filter_blocks_entry_and_forces_exit():
    days = _days([100, 110, 120, 130], [50] * 4)
    s = engine.simulate(days, fee=0, allowed=[False, True, False, True])
    # Вход только на дне 1, принудительный выход на дне 2: заработали 110 -> 120.
    assert s.trades == 1 and s.total_return == pytest.approx(120 / 110 - 1)
