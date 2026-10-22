"""Текстовый отчёт бэктеста (моноширинный — для терминала и тега <pre> в Telegram)."""
from ..formatting import SIGNAL_NAMES
from .engine import HORIZONS, VERDICTS, CoinReport

SHORT = {
    "АКТИВНО ПОКУПАТЬ": "Акт. покупать",
    "ПОКУПАТЬ": "Покупать",
    "ДЕРЖАТЬ / ЖДАТЬ": "Держать",
    "ПРОДАВАТЬ": "Продавать",
    "АКТИВНО ПРОДАВАТЬ": "Акт. продавать",
}


def _p(x: float | None, digits: int = 1) -> str:
    return "—" if x is None else f"{x * 100:+.{digits}f}%"


def _share(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def pooled(reports: list[CoinReport]) -> tuple[dict, dict, dict]:
    """Сводит качество сигналов и корреляции факторов по всем монетам (взвешивая по числу дней)."""
    buckets = {}
    for v in VERDICTS:
        total = sum(r.buckets[v]["count"] for r in reports)
        b = {"count": total}
        for key in [f"{k}_{h}" for h in HORIZONS for k in ("avg", "hit")]:
            parts = [(r.buckets[v][key], r.buckets[v]["count"]) for r in reports if r.buckets[v][key] is not None]
            w = sum(c for _, c in parts)
            b[key] = sum(x * c for x, c in parts) / w if w else None
        buckets[v] = b
    days = sum(r.days for r in reports)
    baseline = {k: sum(r.baseline[k] * r.days for r in reports) / days for k in reports[0].baseline}
    ic = {}
    for name in reports[0].factor_ic:
        vals = [r.factor_ic[name] for r in reports if name in r.factor_ic]
        ic[name] = sum(vals) / len(vals)
    return buckets, baseline, ic


def signals_table(buckets: dict, baseline: dict) -> list[str]:
    lines = [f"{'Сигнал':<15}{'дней':>6}{'7д ср.':>9}{'верно':>7}{'30д ср.':>9}{'верно':>7}"]
    for v in VERDICTS:
        b = buckets[v]
        lines.append(f"{SHORT[v]:<15}{b['count']:>6}{_p(b['avg_7']):>9}{_share(b['hit_7']):>7}"
                     f"{_p(b['avg_30']):>9}{_share(b['hit_30']):>7}")
    lines.append(f"{'Любой день':<15}{'':>6}{_p(baseline['avg_7']):>9}{'':>7}{_p(baseline['avg_30']):>9}")
    return lines


def ic_table(ic: dict) -> list[str]:
    lines = []
    for name, v in sorted(ic.items(), key=lambda kv: -kv[1]):
        verdict = "помогает" if v > 0.03 else "мешает" if v < -0.03 else "≈ шум"
        lines.append(f"{SIGNAL_NAMES[name]:<18}{v:+.3f}  {verdict}")
    return lines


def coin_report(r: CoinReport, buy: float, sell: float) -> str:
    s, bh = r.strategy, r.buy_hold
    lines = [
        f"{r.symbol}: {r.start} — {r.end} ({r.days} дн.)",
        "",
        f"Стратегия: вход при оценке ≥ {buy:+.0f}, выход при ≤ {sell:+.0f}",
        f"{'':<16}{'Стратегия':>11}{'Купить и держать':>18}",
        f"{'Доходность':<16}{_p(s.total_return, 0):>11}{_p(bh.total_return, 0):>18}",
        f"{'В год':<16}{_p(s.cagr):>11}{_p(bh.cagr):>18}",
        f"{'Макс. просадка':<16}{_p(s.max_drawdown, 0):>11}{_p(bh.max_drawdown, 0):>18}",
        f"{'Шарп':<16}{s.sharpe:>11.2f}{bh.sharpe:>18.2f}",
        f"Сделок: {s.trades}, прибыльных: {_share(s.win_rate)}, в рынке {_share(s.exposure)} времени",
        "",
        "Что было после сигнала:",
        *signals_table(r.buckets, r.baseline),
        "",
        "Предсказательная сила факторов (корреляция с доходностью за 7 дней):",
        *ic_table(r.factor_ic),
    ]
    return "\n".join(lines)


def summary_report(reports: list[CoinReport], buy: float, sell: float) -> str:
    lines = [
        f"Сводка по {len(reports)} монетам. Вход при оценке ≥ {buy:+.0f}, выход при ≤ {sell:+.0f}",
        "",
        f"{'':<7}{'':>9}{'— в год —':>18}{'— просадка —':>16}{'—  Шарп  —':>14}",
        f"{'Монета':<7}{'с':>9}{'Страт.':>9}{'Держ.':>9}{'Страт.':>8}{'Держ.':>8}{'Страт.':>7}{'Держ.':>7}{'Сделок':>8}",
    ]
    beat = 0
    for r in reports:
        s, bh = r.strategy, r.buy_hold
        beat += s.sharpe > bh.sharpe
        lines.append(f"{r.symbol:<7}{r.start[:7]:>9}{_p(s.cagr, 0):>9}{_p(bh.cagr, 0):>9}"
                     f"{_p(s.max_drawdown, 0):>8}{_p(bh.max_drawdown, 0):>8}{s.sharpe:>7.2f}{bh.sharpe:>7.2f}{s.trades:>8}")
    lines.append(f"Шарп (доходность с поправкой на риск) выше у стратегии в {beat} из {len(reports)} монет")
    buckets, baseline, ic = pooled(reports)
    lines += ["", "Что было после сигнала (все монеты вместе):", *signals_table(buckets, baseline),
              "", "Предсказательная сила факторов (корреляция с доходностью за 7 дней):", *ic_table(ic)]
    return "\n".join(lines)
