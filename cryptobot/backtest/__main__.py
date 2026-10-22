"""Бэктест сигналов бота: python -m cryptobot.backtest [BTC ETH ...] [--buy 15] [--sell -15]"""
import argparse
import asyncio

from ..analyzer import WEIGHTS
from . import data, engine, report

DEFAULT = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "LINK"]


async def main() -> None:
    ap = argparse.ArgumentParser(description="Проверка сигналов бота на истории")
    ap.add_argument("symbols", nargs="*", default=DEFAULT, help="тикеры, торгуемые к USDT на OKX")
    ap.add_argument("--buy", type=float, default=15, help="порог оценки для входа (по умолчанию 15)")
    ap.add_argument("--sell", type=float, default=-15, help="порог оценки для выхода (по умолчанию -15)")
    ap.add_argument("--fee", type=float, default=0.001, help="комиссия за сделку (0.001 = 0.1%%)")
    ap.add_argument("--start", help="начало периода, например 2022-01-01")
    ap.add_argument("--end", help="конец периода, например 2022-12-31")
    ap.add_argument("--weights", help="свои веса факторов, например trend=40,momentum=30,volume=30 "
                    "(не указанные факторы получают вес 0)")
    ap.add_argument("--btc-filter", type=int, metavar="N",
                    help="торговать, только когда BTC выше своей N-дневной средней (например 200)")
    ap.add_argument("--details", action="store_true", help="подробный отчёт по каждой монете")
    args = ap.parse_args()
    weights = WEIGHTS
    if args.weights:
        weights = {k: float(v) for k, v in (pair.split("=") for pair in args.weights.split(","))}
        if unknown := set(weights) - set(WEIGHTS):
            ap.error(f"неизвестные факторы: {', '.join(unknown)}; доступны: {', '.join(WEIGHTS)}")
        print("Веса:", ", ".join(f"{k}={v:g}" for k, v in weights.items()))

    fg = await data.fear_greed_history()
    regime = engine.btc_regime(await data.candles("BTC"), args.btc_filter) if args.btc_filter else None
    reports = []
    for sym in args.symbols:
        try:
            candles = await data.candles(sym)
            r = await asyncio.to_thread(engine.run, sym.upper(), candles, fg, args.buy, args.sell, args.fee, args.start, weights, args.end, regime)
        except Exception as e:
            print(f"{sym}: пропущено — {e}")
            continue
        reports.append(r)
        if args.details:
            print(report.coin_report(r, args.buy, args.sell), "\n" + "-" * 60)
    if reports:
        print(report.summary_report(reports, args.buy, args.sell))
        if regime is not None:
            print("\n" + report.variants_report(reports, args.btc_filter))


asyncio.run(main())
