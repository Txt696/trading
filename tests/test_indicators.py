from cryptobot import indicators as ind
from cryptobot.analyzer import Signal, combine, rsi_signal, trend_signal, verdict
from cryptobot.sources.news import sentiment


def test_sma_and_ema():
    values = [float(i) for i in range(1, 11)]
    assert ind.sma(values, 5) == 8.0
    assert ind.ema([5.0] * 30, 10) == 5.0
    assert ind.sma(values, 20) is None


def test_rsi_extremes():
    assert ind.rsi([float(i) for i in range(50)]) == 100.0
    assert ind.rsi([float(i) for i in range(50, 0, -1)]) < 1


def test_macd_positive_in_uptrend():
    prices = [100 * 1.01 ** i for i in range(80)]
    assert ind.macd(prices)["macd"] > 0


def test_bollinger_position():
    prices = [100.0, 101.0] * 15 + [110.0]
    assert ind.bollinger(prices)["position"] > 0.9


def test_trend_signal_direction():
    assert trend_signal([100 * 1.01 ** i for i in range(120)]).score == 1
    assert trend_signal([100 * 0.99 ** i for i in range(120)]).score == -1


def test_rsi_signal_oversold_is_bullish():
    assert rsi_signal([100 * 0.97 ** i for i in range(60)]).score > 0


def test_combine_and_verdict():
    assert combine([Signal("trend", 1, ""), Signal("rsi", 1, "")]) == 100
    assert combine([Signal("trend", -1, ""), Signal("rsi", 1, "")]) < 0
    assert verdict(60) == "АКТИВНО ПОКУПАТЬ"
    assert verdict(0) == "ДЕРЖАТЬ / ЖДАТЬ"
    assert verdict(-60) == "АКТИВНО ПРОДАВАТЬ"


def test_news_sentiment():
    assert sentiment("Bitcoin surges to record high on ETF inflows") > 0
    assert sentiment("Exchange hacked, token plunges amid lawsuit") < 0


def test_bear_regime_blocks_buys_but_keeps_sells():
    from cryptobot.analyzer import BEAR_VERDICT, apply_regime
    bear, bull = {"bullish": False}, {"bullish": True}
    assert apply_regime("ПОКУПАТЬ", bear) == BEAR_VERDICT
    assert apply_regime("ДЕРЖАТЬ / ЖДАТЬ", bear) == BEAR_VERDICT
    assert apply_regime("ПРОДАВАТЬ", bear) == "ПРОДАВАТЬ"
    assert apply_regime("ПОКУПАТЬ", bull) == "ПОКУПАТЬ"
    assert apply_regime("ПОКУПАТЬ", None) == "ПОКУПАТЬ"
