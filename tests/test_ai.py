import asyncio
import json

from cryptobot import ai
from cryptobot.analyzer import _headlines, news_signal
from cryptobot.formatting import market_brief


def _verdict(sentiment=0.8, impact="high"):
    return ai.CoinNewsVerdict(
        sentiment=sentiment, impact=impact, relevant_count=2,
        summary="ETF привлекли приток средств.",
        key_events=[ai.KeyEvent(title="Приток в ETF", index=1, impact="positive")],
    )


def test_ai_news_signal_scales_by_impact():
    cn = {"count": 3, "ai": _verdict(0.8, "high")}
    assert news_signal(cn).score == 0.8
    cn["ai"] = _verdict(0.8, "low")
    assert abs(news_signal(cn).score - 0.32) < 1e-9
    assert "ИИ" in news_signal(cn).note


def test_headlines_use_ai_key_events():
    items = [{"title": "a", "link": "l0", "source": "S", "sentiment": 0},
             {"title": "b", "link": "l1", "source": "S", "sentiment": 0}]
    h = _headlines({"items": items, "ai": _verdict()})
    assert h[0]["link"] == "l1" and h[0]["title"] == "Приток в ETF"


def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(ai, "ANTHROPIC_API_KEY", "")
    items = json.dumps([{"source": "S", "title": "t", "summary": ""}])
    assert asyncio.run(ai.analyze_coin_news("Bitcoin", "btc", items)) is None


def test_market_brief_format():
    b = ai.MarketNewsBrief(mood="bullish", summary="Рост <b>", themes=["ETF"], watch=["BTC"])
    text = market_brief(b)
    assert "бычий" in text and "&lt;b&gt;" in text
