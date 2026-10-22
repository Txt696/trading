from html import escape

from .analyzer import Analysis

DISCLAIMER = (
    "\n<i>⚠️ Это не финансовый совет. Сигналы основаны на индикаторах и новостях "
    "и часто ошибаются. Не вкладывайте больше, чем готовы потерять.</i>"
)

EMOJI = {
    "АКТИВНО ПОКУПАТЬ": "🟢🟢",
    "ПОКУПАТЬ": "🟢",
    "ДЕРЖАТЬ / ЖДАТЬ": "⚪️",
    "ПРОДАВАТЬ": "🔴",
    "АКТИВНО ПРОДАВАТЬ": "🔴🔴",
}

SIGNAL_NAMES = {
    "trend": "Тренд",
    "momentum": "Импульс",
    "rsi": "RSI",
    "bollinger": "Боллинджер",
    "volume": "Объём",
    "news": "Новости",
    "sentiment": "Настроение рынка",
}


def price(p: float) -> str:
    if p >= 1000:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    return f"${p:.6f}".rstrip("0")


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x:+.1f}%"


def bar(score: float) -> str:
    return "🟩" if score > 0.2 else "🟥" if score < -0.2 else "⬜️"


def full_report(a: Analysis) -> str:
    lines = [
        f"<b>{escape(a.name)} ({a.symbol})</b>" + (f" · #{a.market_cap_rank}" if a.market_cap_rank else ""),
        f"Цена: <b>{price(a.price)}</b>",
        f"24ч: {pct(a.change_24h)} · 7д: {pct(a.change_7d)} · 30д: {pct(a.change_30d)}",
        "",
        f"{EMOJI[a.verdict]} <b>{a.verdict}</b>",
        f"Оценка: <b>{a.score:+.0f}</b> из ±100 · уверенность: {a.confidence}",
        "",
        "<b>Факторы:</b>",
    ]
    lines += [f"{bar(s.score)} {SIGNAL_NAMES[s.name]}: {escape(s.note)}" for s in a.signals]
    r = a.risk
    lines += [
        "",
        f"<b>Риск:</b> дневная волатильность {r['volatility']:.1f}%",
        f"Ожидаемый диапазон на неделю: {price(r['range_low'])} – {price(r['range_high'])}",
    ]
    if a.score >= 15:
        lines.append(f"Ориентир стоп-лосса: {price(r['stop_loss'])} · цели: {price(r['take_profit'])}")
    if a.headlines:
        lines += ["", "<b>Новости:</b>"]
        lines += [f"• <a href=\"{escape(h['link'])}\">{escape(h['title'])}</a> ({escape(h['source'])})"
                  for h in a.headlines]
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def short_line(a: Analysis) -> str:
    return (f"{EMOJI[a.verdict]} <b>{a.symbol}</b> {price(a.price)} ({pct(a.change_24h)}) — "
            f"{a.verdict.lower()}, {a.score:+.0f}")


def ranking(results: list[Analysis], title: str) -> str:
    if not results:
        return "Не удалось получить данные, попробуйте позже."
    buys = [a for a in results if a.score >= 15]
    sells = [a for a in results if a.score <= -15]
    lines = [f"<b>{title}</b>", ""]
    lines += [short_line(a) for a in results]
    lines.append("")
    lines.append("<b>Лучшие для покупки:</b> " + (", ".join(a.symbol for a in buys[:3]) or "нет явных сигналов"))
    lines.append("<b>Кандидаты на продажу:</b> " + (", ".join(a.symbol for a in sells[::-1][:3]) or "нет явных сигналов"))
    lines.append("\nПодробно по монете: /analyze BTC")
    lines.append(DISCLAIMER)
    return "\n".join(lines)
