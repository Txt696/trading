import datetime as dt
import json
import logging
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from . import ai, config
from .analyzer import analyze, analyze_many
from .formatting import DISCLAIMER, full_report, market_brief, pct, price, ranking
from .sources import coingecko, fear_greed, news

log = logging.getLogger(__name__)

HELP = (
    "<b>Крипто-аналитик</b>\n\n"
    "Я собираю данные из CoinGecko, индекса страха и жадности и новостных лент "
    "(CoinDesk, Cointelegraph, Decrypt, The Block, Bitcoin Magazine), считаю технические "
    "индикаторы и выдаю сигнал по монете. Новости анализирует ИИ (Claude), если подключён ключ.\n\n"
    "/analyze <code>BTC</code> — подробный анализ монеты\n"
    "/top — рейтинг монет из списка наблюдения\n"
    "/market — общее состояние рынка\n"
    "/trending — что сейчас в тренде\n"
    "/news — ИИ-сводка и свежие заголовки\n"
    "/subscribe — ежедневная сводка\n"
    "/unsubscribe — отписаться\n"
    + DISCLAIMER
)


async def reply(update: Update, text: str) -> None:
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, HELP)


async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, "Укажите монету, например: /analyze BTC")
        return
    query = " ".join(context.args)
    await update.effective_message.chat.send_action("typing")
    try:
        coin = await coingecko.resolve_coin(query)
        if not coin:
            await reply(update, f"Монета «{escape(query)}» не найдена.")
            return
        await reply(update, full_report(await analyze(coin["id"])))
    except Exception:
        log.exception("analyze failed")
        await reply(update, "Не удалось получить данные (возможно, лимит API). Попробуйте через минуту.")


async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.chat.send_action("typing")
    try:
        await reply(update, ranking(await analyze_many(config.WATCHLIST), "Рейтинг сигналов"))
    except Exception:
        log.exception("top failed")
        await reply(update, "Не удалось получить данные, попробуйте позже.")


async def market_text() -> str:
    g = await coingecko.global_data()
    fg = await fear_greed.fear_greed()
    cap = g.get("total_market_cap", {}).get("usd", 0)
    lines = [
        "<b>Состояние рынка</b>",
        f"Капитализация: ${cap / 1e12:.2f} трлн ({pct(g.get('market_cap_change_percentage_24h_usd'))} за 24ч)",
        f"Доминация BTC: {g.get('market_cap_percentage', {}).get('btc', 0):.1f}%",
        f"Доминация ETH: {g.get('market_cap_percentage', {}).get('eth', 0):.1f}%",
    ]
    if fg:
        lines.append(f"Страх и жадность: {fg['value']} ({fg['label']}), среднее за неделю {fg['week_avg']:.0f}")
    return "\n".join(lines)


async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await reply(update, await market_text())
    except Exception:
        log.exception("market failed")
        await reply(update, "Не удалось получить данные, попробуйте позже.")


async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        items = await coingecko.trending()
        lines = ["<b>В тренде на CoinGecko</b>", ""]
        for c in items[:10]:
            p = c.get("data", {}).get("price")
            ch = c.get("data", {}).get("price_change_percentage_24h", {}).get("usd")
            lines.append(f"• <b>{escape(c['symbol'])}</b> {escape(c['name'])}"
                         + (f" — {price(p)} ({pct(ch)})" if isinstance(p, (int, float)) else "")
                         + (f" · #{c['market_cap_rank']}" if c.get("market_cap_rank") else ""))
        lines.append("\n<i>Популярность ≠ сигнал к покупке. Проверьте через /analyze.</i>")
        await reply(update, "\n".join(lines))
    except Exception:
        log.exception("trending failed")
        await reply(update, "Не удалось получить данные, попробуйте позже.")


async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.chat.send_action("typing")
    items = await news.all_news()
    if not items:
        await reply(update, "Новостные ленты недоступны.")
        return
    parts = []
    brief = await news.market_brief()
    if brief:
        parts.append(market_brief(brief))
    # По два свежих заголовка из каждого источника.
    by_source: dict[str, list[dict]] = {}
    for n in items:
        by_source.setdefault(n["source"], []).append(n)
    lines = ["<b>Свежие новости</b>"]
    lines += [f"• <a href=\"{escape(n['link'])}\">{escape(n['title'])}</a> ({escape(n['source'])})"
              for group in by_source.values() for n in group[:2]]
    parts.append("\n".join(lines))
    await reply(update, "\n\n".join(parts))


# --- подписки ---

def load_subscribers() -> set[int]:
    try:
        return set(json.loads(config.SUBSCRIBERS_FILE.read_text()))
    except (FileNotFoundError, ValueError):
        return set()


def save_subscribers(subs: set[int]) -> None:
    config.SUBSCRIBERS_FILE.write_text(json.dumps(sorted(subs)))


async def subscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs = load_subscribers()
    subs.add(update.effective_chat.id)
    save_subscribers(subs)
    await reply(update, f"Готово! Сводка будет приходить ежедневно в {config.DIGEST_HOUR_UTC:02d}:00 UTC.")


async def unsubscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    subs = load_subscribers()
    subs.discard(update.effective_chat.id)
    save_subscribers(subs)
    await reply(update, "Вы отписались от рассылки.")


async def daily_digest(context: ContextTypes.DEFAULT_TYPE) -> None:
    subs = load_subscribers()
    if not subs:
        return
    try:
        text = await market_text() + "\n\n" + ranking(await analyze_many(config.WATCHLIST), "Сигналы дня")
    except Exception:
        log.exception("digest failed")
        return
    for chat_id in subs:
        try:
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            log.warning("cannot send digest to %s", chat_id)


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Задайте TELEGRAM_BOT_TOKEN в .env или переменных окружения")
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler(["analyze", "a"], analyze_cmd))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("trending", trending_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("subscribe", subscribe_cmd))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_cmd))
    app.job_queue.run_daily(daily_digest, time=dt.time(hour=config.DIGEST_HOUR_UTC, tzinfo=dt.timezone.utc))
    log.info("Бот запущен, ИИ-анализ новостей: %s", "включён" if ai.enabled() else "выключен")
    app.run_polling()


if __name__ == "__main__":
    main()
