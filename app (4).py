"""
app.py – אפליקציית ווב מקצועית להשוואת מחירי סל קניות.

הפעלה מקומית:
    streamlit run src/app.py

פריסה בענן: ראי DEPLOY.md
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st

from comparator import compare, CHAINS_HE
from matcher import find_candidates

# ─── הגדרות בסיסיות ────────────────────────────────────
ROOT = Path(__file__).resolve().parent
# מאתר את המסד גם כשהקבצים בשורש הריפו וגם בתוך תיקיית src
# בוחר את המסד הטוב ביותר: קודם כל מי שיש בו הכי הרבה רשתות,
# ואם יש כמה עם אותה כמות — זה עם הכי הרבה שורות (ואז הגדול ביותר).
def _db_score(_p):
    try:
        _con = sqlite3.connect(f"file:{_p}?mode=ro", uri=True)
        _chains = _con.execute("SELECT COUNT(DISTINCT chain) FROM prices").fetchone()[0]
        _rows = _con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        _con.close()
        return (_chains, _rows, _p.stat().st_size)
    except Exception:
        return (0, 0, _p.stat().st_size)


_cands = {*ROOT.glob("prices*.db"), ROOT / "prices.db", ROOT.parent / "prices.db"}
_existing = sorted((x for x in _cands if x.exists()), key=lambda x: x.name)
DB_PATH = max(_existing, key=_db_score) if _existing else ROOT / "prices.db"
import comparator as _comparator
import matcher as _matcher
_comparator.DB_PATH = DB_PATH
_matcher.DB_PATH = DB_PATH
HISTORY_PATH = Path(__file__).parent / "user_history.json"

st.set_page_config(
    page_title="🛒 סל משווה – ישראל",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "About": "השוואת מחירים חכמה בין רשתות המזון בישראל.\n"
                 "נתונים מקבצי שקיפות מחירים רשמיים.",
    },
)

# ─── עיצוב מודרני + RTL + PWA ─────────────────────────
st.markdown("""
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#d32f2f">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="סל משווה">

<style>
/* ─── RTL ─── */
html, body, [class*="css"], .stApp, .main, .block-container {
    direction: rtl !important;
    text-align: right !important;
    font-family: 'Assistant', 'Rubik', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ─── רקע וגרדיאנט ─── */
.stApp {
    background: linear-gradient(180deg, #fef3f2 0%, #ffffff 15%);
}

/* ─── כותרות ─── */
h1 { color: #b71c1c; font-weight: 800; }
h2, h3 { color: #7f1d1d; }

/* ─── כפתורים ─── */
.stButton>button {
    background: linear-gradient(135deg, #d32f2f 0%, #b71c1c 100%);
    color: white;
    font-weight: 700;
    border: none;
    padding: 0.7rem 1.5rem;
    border-radius: 12px;
    box-shadow: 0 4px 6px rgba(211, 47, 47, 0.2);
    transition: transform 0.2s, box-shadow 0.2s;
    font-size: 16px;
}
.stButton>button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 12px rgba(211, 47, 47, 0.3);
}

/* ─── תיבת טקסט ─── */
.stTextArea textarea {
    direction: rtl;
    text-align: right;
    font-size: 16px;
    border-radius: 12px;
    border: 2px solid #fecaca;
    padding: 12px;
    font-family: inherit;
    background: #fffbfb;
}
.stTextArea textarea:focus {
    border-color: #d32f2f;
    box-shadow: 0 0 0 3px rgba(211, 47, 47, 0.1);
}

/* ─── מטריקות ─── */
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    color: #b71c1c;
    font-weight: 800;
}
[data-testid="stMetricLabel"] {
    font-weight: 600;
}

/* ─── כרטיסי תוצאות ─── */
.result-card {
    background: white;
    border-radius: 16px;
    padding: 1rem 1.5rem;
    margin: 0.5rem 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border-right: 4px solid #d32f2f;
}
.winner-card {
    background: linear-gradient(135deg, #fef9c3 0%, #fef08a 100%);
    border-right: 4px solid #eab308;
}

.price-tag {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    background: #f3f4f6;
    font-weight: 600;
    margin: 2px;
}
.price-tag.cheapest {
    background: #dcfce7;
    color: #166534;
    font-weight: 800;
}
.price-tag.expensive {
    background: #fee2e2;
    color: #991b1b;
}

/* ─── עלייה נוחה במובייל ─── */
@media (max-width: 640px) {
    h1 { font-size: 1.5rem !important; }
    .stButton>button { width: 100%; padding: 1rem; font-size: 18px; }
    [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
}

/* ─── הידור scrollbar ─── */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-thumb { background: #d32f2f; border-radius: 8px; }
</style>

<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@400;600;700;800&family=Rubik:wght@400;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)


# ─── פונקציית טעינת סטטוס בסיס ────────────────────
@st.cache_data(ttl=300)
def get_db_info():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    info = conn.execute("""
        SELECT chain, COUNT(*), MAX(updated_at)
        FROM prices GROUP BY chain
    """).fetchall()
    conn.close()
    return info


# ─── שמירת היסטוריה מקומית (בדפדפן) ──────────────
def load_history():
    if "history" not in st.session_state:
        st.session_state.history = []
    return st.session_state.history


def save_to_history(items, result):
    hist = load_history()
    valid = {c: result["totals"][c]["total"] for c in result["chains"]
             if result["totals"][c]["hits"] > 0}
    if not valid:
        return
    cheapest = min(valid.items(), key=lambda x: x[1])
    max_total = max(valid.values())
    hist.insert(0, {
        "date": datetime.now().strftime("%d/%m %H:%M"),
        "items": items,
        "cheapest_chain": cheapest[0],
        "cheapest_total": cheapest[1],
        "savings": max_total - cheapest[1],
    })
    st.session_state.history = hist[:20]  # 20 אחרונים


# ─── כותרת עליונה ─────────────────────────────
col_title, col_status = st.columns([3, 1])
with col_title:
    st.markdown("# 🛒 סל משווה")
    st.markdown("**השוואת מחירים חכמה בין רשתות המזון בישראל** · נתונים חיים מקבצי שקיפות מחירים")

with col_status:
    info = get_db_info()
    if info:
        total = sum(cnt for _, cnt, _ in info)
        st.metric("מחירים במאגר", f"{total:,}")

# ─── בדיקה שיש נתונים ─────────────────────────
if not info:
    st.error("⚠️ אין נתונים ב-DB.")
    st.code("python scraper.py --chains shufersal --limit 5", language="bash")
    st.stop()

# ─── תצוגת מקורות ─────────────────────────────
with st.expander("📊 מקורות הנתונים"):
    cols = st.columns(len(info))
    for col, (chain, cnt, upd) in zip(cols, info):
        with col:
            st.metric(
                CHAINS_HE.get(chain, chain),
                f"{cnt:,}",
                f"עודכן {upd[:10] if upd else '—'}",
            )

st.markdown("---")

# ─── טאבים ─────────────────────────────
# ─── בדיקה גלויה: אילו רשתות נטענו מהמסד ───
ALL_CHAINS = ["shufersal", "rami-levy", "yohananof", "osher-ad",
              "tiv-taam", "keshet", "freshmarket", "paz"]


def _chain_rows(_path):
    """מחזיר [(chain, מספר מוצרים)] מהמסד, או רשימה ריקה אם הקריאה נכשלה."""
    try:
        _con = sqlite3.connect(_path)
        _rows = _con.execute("SELECT chain, COUNT(*) FROM prices GROUP BY chain ORDER BY COUNT(*) DESC").fetchall()
        _con.close()
        return _rows
    except Exception:
        return []


_chain_rows_db = _chain_rows(DB_PATH)
_found_keys = [c for c, _n in _chain_rows_db]
_found_names = [CHAINS_HE.get(c, c) for c in _found_keys]
_missing_names = [CHAINS_HE.get(c, c) for c in ALL_CHAINS if c not in _found_keys]

st.markdown(
    f"**📁 קובץ נתונים שנטען:** `{DB_PATH.name}` — נמצאו **{len(_found_keys)} מתוך 8** רשתות"
)

if _found_names:
    st.markdown("**הרשתות שנמצאו במסד:**")
    st.markdown("  ".join(f"`{n}`" for n in _found_names))

if _missing_names:
    st.markdown("**⚠️ רשתות שלא נמצאו במסד:** " + "  ".join(f"`{n}`" for n in _missing_names))

if len(_found_keys) < 8:
    st.warning(
        f"⚠️ **נטענו רק {len(_found_keys)} מתוך 8 הרשתות.** "
        + (f"חסרות: {', '.join(_missing_names)}. " if _missing_names else "")
        + "סימן שהאפליקציה קוראת קובץ נתונים ישן או חלקי — "
        "בואי נטען את המסד המלא עם 8 הרשתות."
    )

tab_new, tab_data, tab_history, tab_help = st.tabs(["🔍 השוואה חדשה", "🗂️ כל הנתונים", "📊 היסטוריה", "❓ עזרה"])

with tab_new:
    st.markdown("### ✍️ מה יש בסל?")

    # דוגמאות מהירות
    st.markdown("**דוגמאות מהירות:**")
    ex_cols = st.columns(4)
    examples = {
        "🥛 סל בסיסי":  "חלב 3%\nלחם\nביצים\nגבינה צהובה\nעגבניות",
        "🍿 חטיפים":     "במבה\nביסלי\nעוגיות\nגלידה\nשוקולד פרה",
        "🥗 בישול":      "עוף\nאורז\nשמן\nבצל\nמלפפונים",
        "🧴 ניקיון":     "אבקת כביסה\nנייר טואלט\nסבון כלים\nרביע",
    }
    for col, (name, content) in zip(ex_cols, examples.items()):
        with col:
            if st.button(name, key=f"ex_{name}", use_container_width=True):
                st.session_state.shopping_list = content

    default = st.session_state.get("shopping_list",
                                     "חלב 3%\nקוטג'\nביצים L\nבמבה\nלחם אחיד\nיוגורט\nגבינה צהובה")

    txt = st.text_area(
        "רשימת קניות (פריט בכל שורה):",
        default,
        height=200,
        key="input_area",
    )

    compare_btn = st.button("🔍 השווי את הסל", use_container_width=True, type="primary")

    if compare_btn:
        items = [x.strip("•-*.0123456789) ").strip()
                 for x in txt.splitlines() if x.strip()]
        if not items:
            st.warning("הזיני לפחות פריט אחד")
        else:
            with st.spinner(f"🔎 מחפש {len(items)} פריטים ברשתות..."):
                result = compare(items)

            save_to_history(items, result)

            # ─── פריטים לא ברורים ─────────────
            if result["unclear"]:
                st.warning(f"⚠️ **{len(result['unclear'])} פריטים לא זוהו**")
                for u in result["unclear"]:
                    with st.expander(f"❓ {u['query']} – מועמדים אפשריים"):
                        if u["candidates"]:
                            for c in u["candidates"]:
                                st.write(f"- **{c['name']}** ({c['brand']}) — ניקוד {c['score']:.0f}")
                            st.info("💡 שני את השם ב\"רשימת הקניות\" והשווי שוב")
                        else:
                            st.write("אין מועמדים במאגר.")

            if not result["matched"]:
                st.error("😞 לא זוהה אף פריט. נסי שמות ספציפיים יותר.")
                st.stop()

            st.markdown(f"### 📊 תוצאות – {len(result['matched'])} פריטים זוהו")

            # ─── טבלת תוצאות בפורמט כרטיסים ───────
            chains = result["chains"]
            for m in result["matched"]:
                prod = m["product"]
                valid = {c: p for c, p in m["prices"].items() if p is not None}
                if not valid:
                    continue
                min_price = min(valid.values())

                tags_html = ""
                for c in chains:
                    p = m["prices"].get(c)
                    if p is None:
                        continue
                    if p == min_price:
                        tags_html += (f'<span class="price-tag cheapest">'
                                       f'🏆 {CHAINS_HE.get(c,c)} · {p} ₪</span>')
                    else:
                        diff_pct = (p - min_price) / min_price * 100
                        tags_html += (f'<span class="price-tag">'
                                       f'{CHAINS_HE.get(c,c)} · {p} ₪ '
                                       f'<small>(+{diff_pct:.0f}%)</small></span>')

                st.markdown(f"""
                <div class="result-card">
                    <div style="font-weight:700;font-size:1.05rem;color:#1f2937;">
                        {m['query']}
                    </div>
                    <div style="color:#6b7280;font-size:0.85rem;margin:4px 0 8px;">
                        {prod['name']}
                    </div>
                    <div>{tags_html}</div>
                </div>
                """, unsafe_allow_html=True)

            # ─── סיכום סלים בכרטיסים ──────────
            st.markdown("---")
            st.markdown("### 💰 סיכום סלים")
            tot = result["totals"]
            valid_totals = {c: tot[c] for c in chains if tot[c]["hits"] > 0}

            if valid_totals:
                winner = min(valid_totals.items(), key=lambda x: x[1]["total"])
                max_total = max(t["total"] for t in valid_totals.values())

                sum_cols = st.columns(len(valid_totals))
                for i, (c, t) in enumerate(sorted(valid_totals.items(),
                                                    key=lambda x: x[1]["total"])):
                    with sum_cols[i]:
                        is_winner = (c == winner[0])
                        emoji = "🏆" if is_winner else "🏪"
                        delta = None if is_winner else f"+{t['total']-winner[1]['total']:.2f} ₪"
                        st.metric(
                            f"{emoji} {CHAINS_HE.get(c, c)}",
                            f"{t['total']} ₪",
                            delta=delta,
                            delta_color="inverse",
                        )
                        st.caption(f"{t['hits']}/{t['hits']+t['missing']} פריטים נמצאו")

                savings = max_total - winner[1]["total"]
                if savings > 0.5:
                    st.success(
                        f"### 💸 חיסכון של **{savings:.2f} ₪** ב-{CHAINS_HE.get(winner[0], winner[0])} "
                        f"על פני הרשת היקרה!"
                    )


with tab_history:
    st.markdown("### 📊 היסטוריית ההשוואות שלך")
    hist = load_history()
    if not hist:
        st.info("עדיין לא ביצעת השוואות. חזרי לטאב הראשון והתחילי!")
    else:
        total_savings = sum(h["savings"] for h in hist)
        st.metric("💰 חיסכון מצטבר", f"{total_savings:.2f} ₪", f"ב-{len(hist)} השוואות")
        st.markdown("---")
        for i, h in enumerate(hist):
            with st.expander(f"🛒 {h['date']} · {len(h['items'])} פריטים · "
                              f"חיסכון {h['savings']:.2f} ₪"):
                st.write(f"**הרשת הזולה:** {CHAINS_HE.get(h['cheapest_chain'], h['cheapest_chain'])} — **{h['cheapest_total']:.2f} ₪**")
                st.write("**פריטים:**")
                st.write(", ".join(h['items']))


with tab_help:
    st.markdown("""
    ### ❓ שאלות נפוצות

    **איך זה עובד?**
    האתר טוען קבצי "שקיפות מחירים" רשמיים שכל רשת מחויבת לפרסם על פי חוק (2014).
    לכל פריט ברשימה שלך אנחנו מחפשים את המוצר במאגר של כל רשת, ומציגים את המחיר.

    **כמה זה עולה?**
    האתר חינמי לגמרי, לתמיד. הנתונים ציבוריים ומקורם ברשתות עצמן.

    **מה זה "ממוצע ארצי"?**
    לכל רשת יש עשרות סניפים עם הבדלי מחירים קלים. אנחנו מציגים ממוצע של כל הסניפים.

    **פריט לא זוהה?**
    כתבי שם מפורש יותר: במקום "חלב" → "חלב תנובה 3% קרטון".

    **פרטיות:**
    ההיסטוריה שלך נשמרת רק בדפדפן שלך. אנחנו לא שומרים שום מידע אישי.

    ---
    ### 🛠️ פותח על ידי
    פרויקט קוד פתוח. בעיה? רעיון? פנו לצוות.
    """)

# ─── פוטר קטן ──────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#9ca3af;font-size:0.85rem;padding:1rem;'>"
    "🛒 סל משווה · נתונים מקבצי שקיפות מחירים · בנוי בישראל 🇮🇱"
    "</div>",
    unsafe_allow_html=True,
)


# ─── לשונית: כל הנתונים ─────────────────────────
with tab_data:
    st.markdown("### 🗂️ כל המחירים במאגר")
    st.caption("כל הנתונים שנאספו מהרשתות — חיפוש לפי שם מוצר או ברקוד, והורדה לאקסל.")

    import pandas as pd

    CHAIN_KEYS = ["shufersal", "rami-levy", "yohananof", "osher-ad",
                  "tiv-taam", "keshet", "freshmarket", "paz"]
    CHAIN_COLS = [CHAINS_HE.get(c, c) for c in CHAIN_KEYS]

    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("חיפוש (שם מוצר או ברקוד)", "", key="data_q")
    only_shared = c2.checkbox("רק מוצרים ביותר מרשת אחת", value=True, key="data_shared")
    rows_limit = c3.selectbox("כמה שורות להציג", [100, 200, 500, 1000, 5000], index=1, key="data_limit")

    where, params = [], []
    if q.strip():
        where.append("(name LIKE ? OR barcode LIKE ?)")
        params += [f"%{q.strip()}%", f"%{q.strip()}%"]
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    min_chains = 1 if only_shared is False else 2

    price_cols_sql = ",\n".join(
        '               MAX(CASE WHEN chain = \'{c}\' THEN price END) AS "{h}"'.format(c=c, h=CHAINS_HE.get(c, c))
        for c in CHAIN_KEYS
    )
    sql = f"""
        SELECT barcode,
               MAX(name) AS "מוצר",
               MAX(brand) AS "מותג",
{price_cols_sql},
               COUNT(DISTINCT chain) AS "מספר רשתות"
        FROM prices
        {where_sql}
        GROUP BY barcode
        HAVING COUNT(DISTINCT chain) >= {int(min_chains)}
        ORDER BY "מספר רשתות" DESC, "מוצר"
        LIMIT {int(rows_limit)}
    """
    _conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(sql, _conn, params=params)
    _conn.close()

    if df.empty:
        st.info("לא נמצאו מוצרים לחיפוש הזה. נסי מילה אחרת.")
    else:
        df["המחיר הזול"] = df[CHAIN_COLS].min(axis=1).round(2)
        df["הרשת הזולה"] = df[CHAIN_COLS].idxmin(axis=1)
        st.success(f"מוצגים {len(df):,} מוצרים מתוך המאגר")
        st.dataframe(df, use_container_width=True, hide_index=True, height=520)
        st.download_button(
            "⬇️ הורדת הטבלה לאקסל (CSV)",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name="prices_export.csv",
            mime="text/csv",
        )

    # ─── תרשים: איזו רשת היא הזולה ביותר ───
    st.markdown("---")
    st.markdown("### 🏆 איזו רשת יוצאת הזולה ביותר?")
    st.caption("לכל מוצר שבסינון הנוכחי נבדק המחיר בכל 8 הרשתות, וכל פריט נזקף לרשת שהציעה בו את המחיר הנמוך.")

    sql_all = f"""
        SELECT barcode,
{price_cols_sql},
               COUNT(DISTINCT chain) AS n_chains
        FROM prices
        {where_sql}
        GROUP BY barcode
        HAVING COUNT(DISTINCT chain) >= {int(min_chains)}
        LIMIT 60000
    """
    _c2 = sqlite3.connect(DB_PATH)
    df_all = pd.read_sql_query(sql_all, _c2, params=params)
    _c2.close()

    if df_all.empty:
        st.info("אין נתונים לתרשים בסינון הזה.")
    else:
        cheapest = df_all[CHAIN_COLS].idxmin(axis=1).dropna()
        counts = cheapest.value_counts()
        chart_df = counts.to_frame("מוצרים שבהם הרשת זולה")
        chart_df["אחוז מהמוצרים"] = (counts / counts.sum() * 100).round(1)
        chart_df["מקום"] = range(1, len(chart_df) + 1)

        left, right = st.columns([3, 2])
        with left:
            st.bar_chart(chart_df["מוצרים שבהם הרשת זולה"])
        with right:
            st.dataframe(
                chart_df[["מקום", "מוצרים שבהם הרשת זולה", "אחוז מהמוצרים"]],
                use_container_width=True, hide_index=False, height=340,
            )

        top_chain = counts.index[0]
        top_n = int(counts.iloc[0])
        st.success(
            f"👑 **{top_chain}** היא הרשת הזולה ביותר ב‑{top_n:,} מוצרים "
            f"({counts.iloc[0] / counts.sum() * 100:.1f}% מהמוצרים שנבדקו), "
            f"מתוך {int(counts.sum()):,} מוצרים עם מחיר ביותר מרשת אחת."
        )
        st.caption("החישוב מבוסס על הסינון שבחרת למעלה (חיפוש / מספר רשתות). "
                   "שימי לב: זו ספירת 'מי הזול בפריט הבודד' — לא בהכרח הסל הכולל הזול ביותר.")
