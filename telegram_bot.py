"""
telegram_bot.py – בוט טלגרם דינמי להשוואת סל קניות בישראל.

חוויית משתמש:
1. /start – ברוכה הבאה + הסבר קצר
2. שולחת רשימת קניות (שורה לכל פריט, או פסיק) → הבוט משיב עם:
   • שולחן משווה בין הרשתות
   • הרשת הזולה
   • חיסכון בפועל
3. פריט עמום → מציג 5 מועמדים עם כפתורי בחירה (Inline Keyboard)
4. /list – מציג את הסל הנוכחי
5. /clear – מנקה את הסל
6. /refresh – מוריד נתוני מחירים עדכניים (מנהל בלבד)
7. /history – היסטוריית קניות + חיסכון מצטבר

הפעלה:
    export TELEGRAM_BOT_TOKEN="123456:ABC..."  # מ-@BotFather
    python3 src/telegram_bot.py
"""
import asyncio
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# imports מהפרויקט
sys.path.insert(0, str(Path(__file__).parent))
from comparator import compare, CHAINS_HE
from matcher import find_candidates

# ─── הגדרות ─────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "prices.db"
HISTORY_DB = Path(__file__).parent.parent / "history.db"
ADMIN_IDS = [int(x) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── היסטוריית משתמשים ─────────────────────────
def init_history():
    conn = sqlite3.connect(HISTORY_DB)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS user_baskets (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER,
        created_at TEXT,
        items      TEXT,        -- JSON list
        cheapest   TEXT,        -- chain key
        cheapest_total REAL,
        max_total  REAL,
        savings    REAL
    );
    CREATE TABLE IF NOT EXISTS user_current (
        user_id INTEGER PRIMARY KEY,
        items   TEXT             -- JSON list of shopping items
    );
    """)
    conn.commit()
    return conn


def get_current_basket(user_id: int) -> list[str]:
    import json
    conn = init_history()
    row = conn.execute("SELECT items FROM user_current WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else []


def save_current_basket(user_id: int, items: list[str]):
    import json
    conn = init_history()
    conn.execute("""
        INSERT INTO user_current(user_id, items) VALUES (?,?)
        ON CONFLICT(user_id) DO UPDATE SET items = excluded.items
    """, (user_id, json.dumps(items, ensure_ascii=False)))
    conn.commit()
    conn.close()


def clear_current_basket(user_id: int):
    conn = init_history()
    conn.execute("DELETE FROM user_current WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def save_to_history(user_id, items, totals, chains):
    import json
    conn = init_history()
    valid = {c: totals[c]["total"] for c in chains if totals[c]["hits"] > 0}
    if not valid:
        return
    cheapest = min(valid.items(), key=lambda x: x[1])
    max_total = max(valid.values())
    conn.execute("""
        INSERT INTO user_baskets(user_id, created_at, items, cheapest, cheapest_total, max_total, savings)
        VALUES (?,?,?,?,?,?,?)
    """, (user_id, datetime.now().isoformat(), json.dumps(items, ensure_ascii=False),
          cheapest[0], cheapest[1], max_total, max_total - cheapest[1]))
    conn.commit()
    conn.close()


# ─── פורמט הודעות ───────────────────────────────
def format_comparison(result) -> str:
    """מפרסר תוצאות compare() לטקסט טלגרם יפה."""
    if not result["matched"]:
        return "❌ לא זיהיתי אף פריט. נסי שמות מדויקים יותר, למשל: 'חלב 3% תנובה'."

    lines = [f"📊 <b>השוואת סל</b> • {len(result['matched'])} פריטים\n"]

    # טבלה לכל פריט – רק אם עד 3 רשתות (אחרת הודעה תיפרד)
    chains = result["chains"]

    # פירוט פריטים
    for m in result["matched"]:
        prod = m["product"]
        lines.append(f"🛒 <b>{m['query']}</b>")
        lines.append(f"   <i>{prod['name'][:40]}</i>")
        valid = {c: p for c, p in m["prices"].items() if p is not None}
        if not valid:
            lines.append("   ⚠️ אין נתונים")
            continue
        min_p = min(valid.values())
        for c in chains:
            p = m["prices"].get(c)
            if p is None:
                lines.append(f"      {CHAINS_HE.get(c,c)}: —")
            elif p == min_p:
                lines.append(f"      🏆 {CHAINS_HE.get(c,c)}: <b>{p} ₪</b>")
            else:
                diff = (p - min_p) / min_p * 100
                lines.append(f"      {CHAINS_HE.get(c,c)}: {p} ₪  <i>(+{diff:.0f}%)</i>")
        lines.append("")

    # סיכום סלים
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append("💰 <b>סה\"כ סל לרשת</b>\n")
    totals = result["totals"]
    valid_totals = {c: totals[c] for c in chains if totals[c]["hits"] > 0}
    if valid_totals:
        winner = min(valid_totals.items(), key=lambda x: x[1]["total"])
        max_total = max(t["total"] for t in valid_totals.values())
        for c, t in sorted(valid_totals.items(), key=lambda x: x[1]["total"]):
            emoji = "🏆" if c == winner[0] else "  "
            covered = f"({t['hits']}/{t['hits']+t['missing']})"
            lines.append(f"{emoji} {CHAINS_HE.get(c,c)}: <b>{t['total']} ₪</b> {covered}")

        savings = max_total - winner[1]["total"]
        if savings > 0.5:
            lines.append(f"\n💸 <b>חיסכון של {savings:.2f} ₪</b> ב-{CHAINS_HE.get(winner[0],winner[0])}")

    # פריטים לא ברורים
    if result["unclear"]:
        lines.append(f"\n⚠️ <b>{len(result['unclear'])} פריטים עמומים:</b>")
        for u in result["unclear"]:
            lines.append(f"   • {u['query']}")
        lines.append("<i>שלחי שם מדויק יותר או השתמשי ב-/refine</i>")

    return "\n".join(lines)


# ─── פקודות הבוט ──────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 <b>ברוכה הבאה לבוט השוואת המחירים!</b>\n\n"
        "אני משווה מחירי סל קניות בין <b>שופרסל, רמי לוי, יוחננוף, "
        "ויקטורי, אושר עד וטיב טעם</b> – נתונים חיים מקבצי שקיפות מחירים.\n\n"
        "📝 <b>איך משתמשים:</b>\n"
        "פשוט שלחי לי רשימת קניות – פריט בכל שורה, לדוגמה:\n\n"
        "<code>חלב 3%\n"
        "קוטג' 5%\n"
        "ביצים L\n"
        "לחם אחיד</code>\n\n"
        "⚡ <b>פקודות שימושיות:</b>\n"
        "/list – הצג את הסל הנוכחי\n"
        "/add – הוסף פריטים לסל\n"
        "/clear – נקה סל\n"
        "/compare – השווי את הסל הנוכחי\n"
        "/history – היסטוריה + חיסכון מצטבר\n"
        "/help – עזרה נוספת"
    )
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("🔍 השווי סל"), KeyboardButton("📋 הסל שלי")],
         [KeyboardButton("📊 היסטוריה"), KeyboardButton("🗑️ נקי סל")]],
        resize_keyboard=True,
    )
    await update.message.reply_html(welcome, reply_markup=kb)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = (
        "🆘 <b>עזרה</b>\n\n"
        "• כתבי כל פריט בשורה נפרדת, או הפרידי בפסיקים\n"
        "• ההשוואה: ממוצע ארצי של הרשת (כל הסניפים)\n"
        "• 🏆 = הרשת הזולה לפריט\n"
        "• אם פריט מזוהה שגוי – כתבי שם מדויק יותר\n\n"
        "🔒 <b>פרטיות:</b> ההיסטוריה שלך נשמרת רק אצלך.\n"
        "📡 <b>עדכניות:</b> הנתונים מתעדכנים אוטומטית פעם ביום."
    )
    await update.message.reply_html(txt)


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    items = get_current_basket(update.effective_user.id)
    if not items:
        await update.message.reply_text("🛒 הסל ריק. שלחי לי פריטים כדי להוסיף.")
        return
    txt = f"🛒 <b>הסל שלך ({len(items)} פריטים):</b>\n\n"
    txt += "\n".join(f"{i+1}. {it}" for i, it in enumerate(items))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 השווי", callback_data="compare"),
         InlineKeyboardButton("🗑️ נקי", callback_data="clear")]
    ])
    await update.message.reply_html(txt, reply_markup=kb)


async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    clear_current_basket(update.effective_user.id)
    await update.message.reply_text("🗑️ הסל נוקה.")


async def cmd_compare(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    items = get_current_basket(user_id)
    if not items:
        await update.message.reply_text("🛒 הסל ריק – שלחי לי פריטים קודם.")
        return
    await do_comparison(update, ctx, items)


async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = init_history()
    rows = conn.execute("""
        SELECT created_at, cheapest, cheapest_total, savings
        FROM user_baskets WHERE user_id = ?
        ORDER BY id DESC LIMIT 10
    """, (update.effective_user.id,)).fetchall()

    total_savings = conn.execute("""
        SELECT COALESCE(SUM(savings),0), COUNT(*) FROM user_baskets WHERE user_id = ?
    """, (update.effective_user.id,)).fetchone()
    conn.close()

    if not rows:
        await update.message.reply_text("📊 אין היסטוריה עדיין.")
        return
    lines = ["📊 <b>10 סלים אחרונים:</b>\n"]
    for created, ch, tot, sav in rows:
        d = created[:10]
        lines.append(f"• {d} – {CHAINS_HE.get(ch, ch)}: <b>{tot:.2f} ₪</b> (חסכת {sav:.2f})")
    lines.append(f"\n💰 <b>חיסכון מצטבר: {total_savings[0]:.2f} ₪</b> ב-{total_savings[1]} סלים")
    await update.message.reply_html("\n".join(lines))


async def cmd_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ פקודה זמינה למנהלים בלבד.")
        return
    await update.message.reply_text("🔄 מוריד נתונים חדשים... יקח ~2 דקות.")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(__file__).parent / "scraper.py"),
        "--chains", "shufersal", "--limit", "5",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    await update.message.reply_text(f"✅ עדכון הושלם.\n\n<pre>{stdout.decode()[-500:]}</pre>",
                                     parse_mode="HTML")


# ─── טיפול בהודעות טקסט ─────────────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # קיצורי דרך של Reply-Keyboard
    if text in ("🔍 השווי סל",):
        await cmd_compare(update, ctx); return
    if text in ("📋 הסל שלי",):
        await cmd_list(update, ctx); return
    if text in ("📊 היסטוריה",):
        await cmd_history(update, ctx); return
    if text in ("🗑️ נקי סל",):
        await cmd_clear(update, ctx); return

    # פרסור רשימת פריטים
    items = []
    for line in text.replace(",", "\n").splitlines():
        line = line.strip("•-*.0123456789) ").strip()
        if line:
            items.append(line)
    if not items:
        return

    # שמור בסל וספרי למשתמש
    current = get_current_basket(user_id)
    current.extend(items)
    save_current_basket(user_id, current)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 השווי סל עכשיו", callback_data="compare")],
        [InlineKeyboardButton("➕ הוסיפי עוד", callback_data="add_more"),
         InlineKeyboardButton("🗑️ נקי", callback_data="clear")],
    ])
    await update.message.reply_html(
        f"✅ נוספו <b>{len(items)}</b> פריטים. סה\"כ בסל: <b>{len(current)}</b>",
        reply_markup=kb,
    )


# ─── ההשוואה בפועל ─────────────────────────
async def do_comparison(update, ctx, items):
    if not DB_PATH.exists():
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text(
            "⚠️ אין נתונים ב-DB. הרץ:\n<code>python3 src/scraper.py --chains shufersal</code>",
            parse_mode="HTML",
        )
        return

    target = update.callback_query.message if update.callback_query else update.message
    msg = await target.reply_text(f"🔎 מחפש {len(items)} פריטים...")

    # מרים על thread נפרד – RapidFuzz חוסם
    result = await asyncio.to_thread(compare, items)

    txt = format_comparison(result)
    # תיקון בטלגרם: הודעה גדולה מחולקת
    for chunk in [txt[i:i+3800] for i in range(0, len(txt), 3800)]:
        await target.reply_html(chunk)
    try:
        await msg.delete()
    except Exception:
        pass

    save_to_history(update.effective_user.id, items, result["totals"], result["chains"])


# ─── כפתורים inline ──────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "compare":
        items = get_current_basket(user_id)
        if items:
            await do_comparison(update, ctx, items)
        else:
            await query.message.reply_text("🛒 הסל ריק.")
    elif data == "clear":
        clear_current_basket(user_id)
        await query.message.reply_text("🗑️ נוקה.")
    elif data == "add_more":
        await query.message.reply_text("✍️ שלחי לי פריטים נוספים.")


# ─── הפעלה ─────────────────────────────
def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️  Missing TELEGRAM_BOT_TOKEN environment variable.")
        print("Get one from @BotFather in Telegram, then:")
        print('  export TELEGRAM_BOT_TOKEN="123456:ABC..."')
        sys.exit(1)

    init_history()
    app = Application.builder().token(token).build()

    # commands
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("list",    cmd_list))
    app.add_handler(CommandHandler("clear",   cmd_clear))
    app.add_handler(CommandHandler("compare", cmd_compare))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("refresh", cmd_refresh))

    # inline buttons + text
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # הרישום של הפקודות בתפריט של טלגרם
    async def on_startup(a):
        await a.bot.set_my_commands([
            BotCommand("start",   "🏠 התחלה"),
            BotCommand("list",    "🛒 הסל שלי"),
            BotCommand("compare", "🔍 השווי סל"),
            BotCommand("clear",   "🗑️ נקי סל"),
            BotCommand("history", "📊 היסטוריה"),
            BotCommand("help",    "🆘 עזרה"),
        ])
    app.post_init = on_startup

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
