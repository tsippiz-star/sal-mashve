import time
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
# ─── בחירת קובץ המסד: סדר עדיפויות מפורש ───
# 1) הכי הרבה רשתות   2) הכי הרבה שורות   3) קובץ בשם prices.db   4) הגודל
# כך שגם אם הישן (שופרסל בלבד) יושב בשם prices.db, הוא לא ייבחר לעולם
# כל עוד קיים קובץ עם יותר רשתות.
APP_VERSION = "db-pick v3 · 2026-09-23"


def _db_stats(_p):
    """(רשתות, שורות, גודל) — עובד גם כששם הקובץ מכיל רווחים וסוגריים."""
    _size = _p.stat().st_size
    for _target, _is_uri in ((f"file:{_p}?mode=ro", True), (str(_p), False)):
        try:
            _con = sqlite3.connect(_target, uri=_is_uri)
            _chains = _con.execute("SELECT COUNT(DISTINCT chain) FROM prices").fetchone()[0]
            _rows = _con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
            _con.close()
            return (_chains, _rows, _size)
        except Exception:
            continue
    return (0, 0, _size)


def _db_score(_p):
    _chains, _rows, _size = _db_stats(_p)
    return (_chains, _rows, 1 if _p.name == "prices.db" else 0, _size)


_cands = {*ROOT.glob("prices*.db"), ROOT / "prices.db", ROOT.parent / "prices.db"}
_existing = sorted((x for x in _cands if x.exists()), key=lambda x: x.name)
DB_SCAN = [(_x, _db_stats(_x)) for _x in _existing]
DB_PATH = max(_existing, key=_db_score) if _existing else ROOT / "prices.db"
DB_INFO = _db_stats(DB_PATH)

# ─── רשתות שמוכרות גם אונליין (אפשר לערוך את הרשימה כאן) ───
ONLINE_CHAINS = ["shufersal", "rami-levy", "yohananof", "tiv-taam",
                 "keshet", "freshmarket", "paz"]


def _filter_chains(_result, _keep_chains):
    """מצמצם את תוצאת ההשוואה לרשתות שנבחרו."""
    _keep = [c for c in _result["chains"] if c in _keep_chains]
    if len(_keep) < 2:
        return _result
    _result["chains"] = _keep
    for _m in _result.get("matched", []):
        _m["prices"] = {c: v for c, v in _m["prices"].items() if c in _keep}
    if "totals" in _result:
        _result["totals"] = {c: v for c, v in _result["totals"].items() if c in _keep}
    return _result



# ─── משיכת המסד המתעדכן אוטומטית (ענף data, מה-Action היומי) ───
REMOTE_DB_URL = "https://raw.githubusercontent.com/tsippiz-star/sal-mashve/data/prices.db"
REMOTE_DB_PATH = Path("/tmp/prices_live.db")
REMOTE_MAX_AGE_HOURS = 6


def _fetch_remote_db():
    """מוריד את המסד המעודכן (עד פעם ב-6 שעות). מחזיר נתיב או None."""
    import urllib.request as _ur
    try:
        if REMOTE_DB_PATH.exists() and (time.time() - REMOTE_DB_PATH.stat().st_mtime) < REMOTE_MAX_AGE_HOURS * 3600:
            return REMOTE_DB_PATH
        _req = _ur.Request(REMOTE_DB_URL, headers={"User-Agent": "sal-mashve-app"})
        _part = REMOTE_DB_PATH.with_suffix(".part")
        with _ur.urlopen(_req, timeout=90) as _r, open(_part, "wb") as _f:
            while True:
                _buf = _r.read(1 << 20)
                if not _buf:
                    break
                _f.write(_buf)
        _part.replace(REMOTE_DB_PATH)
        return REMOTE_DB_PATH
    except Exception:
        return REMOTE_DB_PATH if REMOTE_DB_PATH.exists() else None


REMOTE_USED = False
_remote_db = _fetch_remote_db()
if _remote_db is not None:
    _rc, _rr, _rs = _db_stats(_remote_db)
    if _rc >= 3:   # המקור מתעדכן יומית — מעדיפים אותו על קובץ מקומי שעלול להיות ישן
        DB_PATH, DB_INFO = _remote_db, (_rc, _rr, _rs)
        DB_SCAN.append((_remote_db, (_rc, _rr, _rs)))
        REMOTE_USED = True


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
# ─── בדיקה גלויה: אילו רשתות נטענו, מאיזה קובץ ובאיזו גרסת קוד ───
import datetime as _dt
import pandas as pd

ALL_CHAINS = ["shufersal", "rami-levy", "yohananof", "osher-ad",
              "tiv-taam", "keshet", "freshmarket", "paz"]


def _chain_rows(_path):
    try:
        _con = sqlite3.connect(str(_path))
        _rows = _con.execute(
            "SELECT chain, COUNT(*) FROM prices GROUP BY chain ORDER BY COUNT(*) DESC"
        ).fetchall()
        _con.close()
        return _rows
    except Exception:
        return []


_chain_rows_db = _chain_rows(DB_PATH)
_found_keys = [c for c, _n in _chain_rows_db]
_found_names = [CHAINS_HE.get(c, c) for c in _found_keys]
_missing_names = [CHAINS_HE.get(c, c) for c in ONLINE_CHAINS if c not in _found_keys]

st.caption(
    f"📁 קובץ נתונים שנטען: `{DB_PATH.name}` · רשתות בקובץ: "
    f"**{len(_found_keys)} מתוך {len(ONLINE_CHAINS)}** · גרסת קוד: `{APP_VERSION}`"
)
if REMOTE_USED:
    st.caption("🔄 הנתונים נמשכו מהעדכון האוטומטי היומי (ענף data)")

if _found_names:
    st.markdown("**הרשתות שנמצאו במסד:**")
    st.markdown("  ".join(f"`{n}`" for n in _found_names))

if _missing_names:
    st.markdown("**⚠️ רשתות שלא נמצאו במסד:** " + "  ".join(f"`{n}`" for n in _missing_names))

if len(_found_keys) < len(ONLINE_CHAINS):
    st.warning(
        f"⚠️ **נטענו רק {len(_found_keys)} מתוך {len(ONLINE_CHAINS)} הרשתות שמוכרות אונליין.** "
        + (f"חסרות: {', '.join(_missing_names)}. " if _missing_names else "")
        + "סימן שהאפליקציה קוראת קובץ נתונים ישן או חלקי — "
        "פִּתחי את 'למה נבחר הקובץ הזה?' למטה כדי לראות את כל הקבצים שנמצאו בריפו."
    )
else:
    st.success(f"✅ כל {len(ONLINE_CHAINS)} הרשתות האונליין נטענו בהצלחה.")

with st.expander("🔎 למה נבחר הקובץ הזה? (כל קבצי הנתונים שנמצאו)", expanded=len(_found_keys) < 8):
    st.dataframe(
        pd.DataFrame([
            {
                "קובץ": _pth.name,
                "רשתות": _ch,
                "שורות": _rw,
                "גודל (MB)": round(_sz / 1048576, 1),
                "עודכן": _dt.datetime.fromtimestamp(_pth.stat().st_mtime).strftime("%d/%m %H:%M"),
                "נבחר": "✅" if _pth == DB_PATH else "",
            }
            for _pth, (_ch, _rw, _sz) in DB_SCAN
        ]),
        use_container_width=True, hide_index=True,
    )
    st.caption(
        "סדר העדיפויות: 1) הכי הרבה רשתות · 2) הכי הרבה שורות · "
        "3) קובץ בשם prices.db · 4) הגודל. "
        "כלומר קובץ עם 8 רשתות תמיד ינצח את הקובץ הישן עם הרשת הבודדת, "
        "לא משנה איך הם נקראים."
    )

# ─── השוואה: הקובץ שבסביבה מול הקובץ בגיטהאב ───
from datetime import datetime as _dtime, timedelta as _tdelta, timezone as _tz

GITHUB_REPO = "tsippiz-star/sal-mashve"
GITHUB_BRANCH = "main"
_IL = _tz(_tdelta(hours=3))  # שעון ישראל


@st.cache_data(ttl=600, show_spinner=False)
def _github_db_info():
    """{שם קובץ: (תאריך הקומיט האחרון, גודל)} עבור קובצי המסד בגיטהאב."""
    import json as _json
    import urllib.parse as _up
    import urllib.request as _ur

    def _get(_url):
        _req = _ur.Request(_url, headers={"User-Agent": "sal-mashve-app"})
        with _ur.urlopen(_req, timeout=8) as _r:
            return _json.load(_r)

    try:
        _tree = _get(f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/{GITHUB_BRANCH}?recursive=1")
    except Exception:
        return {}

    _out = {}
    for _e in _tree.get("tree", []):
        _n = _e.get("path", "")
        if _e.get("type") == "blob" and _n.startswith("prices") and _n.endswith(".db"):
            _out[_n] = {"size": _e.get("size", 0), "commit": None}

    for _n in list(_out)[:6]:
        try:
            _c = _get(f"https://api.github.com/repos/{GITHUB_REPO}/commits?path={_up.quote(_n)}&per_page=1")
            if _c:
                _out[_n]["commit"] = _c[0]["commit"]["committer"]["date"]
        except Exception:
            pass
    return _out


_gh_info = _github_db_info()
_env_files = {_p.name: _p for _p, _ in DB_SCAN}
_gh_names = set(_gh_info)
_all_names = sorted(_env_files) if not _gh_info else sorted(set(_env_files) | _gh_names)

_rows_cmp, _need_reboot = [], []
for _name in _all_names:
    _ep = _env_files.get(_name)
    _gp = _gh_info.get(_name) or {}
    _env_dt = _dtime.fromtimestamp(_ep.stat().st_mtime, _tz.utc) if _ep else None
    _env_txt = _env_dt.astimezone(_IL).strftime("%d/%m/%Y %H:%M") if _env_dt else "❌ לא קיים"
    _gh_size = _gp.get("size")
    _gh_iso = _gp.get("commit")
    _gh_dt = _dtime.fromisoformat(_gh_iso.replace("Z", "+00:00")) if _gh_iso else None
    _gh_txt = _gh_dt.astimezone(_IL).strftime("%d/%m/%Y %H:%M") if _gh_dt else "—"

    if _gh_size is None:                                     # קובץ שלא נמצא בגיטהאב
        _state = "— לא נמצא בגיטהאב"
    elif _ep is None:                                        # קיים בגיטהאב, חסר בסביבה
        _state = "🔄 נדרש Reboot — הקובץ עוד לא הגיע לסביבה"
        _need_reboot.append(f"`{_name}` חסר בסביבה")
    elif _ep.stat().st_size != _gh_size:                     # גדלים שונים = תוכן שונה
        _state = "🔄 נדרש Reboot — בסביבה גרסה שונה מזו שבגיטהאב"
        _need_reboot.append(f"`{_name}` בגודל שונה")
    elif _gh_dt and _env_dt and _gh_dt > _env_dt + _tdelta(minutes=2):
        _state = "🔄 נדרש Reboot — בגיטהאב יש גרסה חדשה יותר"
        _need_reboot.append(f"`{_name}` חדש יותר בגיטהאב")
    else:
        _state = "✅ מעודכן"

    _rows_cmp.append({
        "קובץ": _name,
        "תאריך בסביבה": _env_txt,
        "תאריך בגיטהאב": _gh_txt,
        "גודל בסביבה (MB)": round(_ep.stat().st_size / 1048576, 1) if _ep else "❌",
        "גודל בגיטהאב (MB)": round(_gh_size / 1048576, 1) if _gh_size is not None else "—",
        "מצב": _state,
    })

with st.expander("🕒 השוואה מול גיטהאב — האם צריך Reboot?", expanded=bool(_need_reboot)):
    if not _gh_info:
        st.info(
            "לא הצלחתי לקרוא את גיטהאב כרגע (אין רשת או הגבלת קצב של ה-API). "
            "אפשר לנסות שוב בעוד דקה, או פשוט ללחוץ Reboot."
        )
    else:
        st.dataframe(pd.DataFrame(_rows_cmp), use_container_width=True, hide_index=True)
        st.caption(
            "אם תאריך הקומיט בגיטהאב חדש מהתאריך שבסביבה — או שהגדלים שונים — "
            "הגרסה שהאפליקציה מריצה אינה המעודכנת, ונדרש Reboot."
        )

if _gh_info and _need_reboot:
    st.error(
        "🔄 **נדרש Reboot:** " + " · ".join(_need_reboot)
        + " — נכנסים לתפריט **⋯ → Reboot app**. "
        "בלי זה האפליקציה תמשיך לעבוד עם הגרסה הישנה שבזיכרון שלה."
    )
elif _gh_info and _all_names:
    st.success("✅ הקבצים שבסביבה תואמים את מה שבגיטהאב — אין צורך ב-Reboot.")

# ─── כפתור: לאתר מחדש את קובץ המסד בלי Reboot ───
_bcol1, _bcol2 = st.columns([1, 2])
with _bcol1:
    if st.button("🔄 לאתר מחדש את קובץ הנתונים", help="סורק שוב את כל קובצי prices*.db שבסביבת האפליקציה, מנקה את הזיכרון הפנימי ובוחר את הקובץ עם הכי הרבה רשתות"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
with _bcol2:
    st.caption(
        f"סריקה אחרונה: **{_dt.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}** · "
        "הלחיצה סורקת מחדש את הקבצים שבסביבת האפליקציה, מנקה זיכרון פנימי וטוענת את הקובץ הטוב ביותר. "
        "אם קובץ חדש עדיין לא הגיע לסביבה — הוא לא יימצא עד שהאפליקציה תתרענן מול גיטהאב."
    )

_ALL_CHAIN_KEYS = ["shufersal", "rami-levy", "yohananof", "osher-ad",
                   "tiv-taam", "keshet", "freshmarket", "paz"]
_default_chains = [c for c in _ALL_CHAIN_KEYS if c in ONLINE_CHAINS]

_selected_chains = st.multiselect(
    "🛒 אילו רשתות ייכללו בהשוואה ובנתונים?",
    options=_ALL_CHAIN_KEYS,
    default=_default_chains,
    format_func=lambda c: CHAINS_HE.get(c, c),
    key="chains_selected",
    help="ברירת המחדל היא רשתות שמוכרות גם אונליין. אפשר להוסיף או להסיר כל רשת — "
         "הבחירה חלה על ההשוואה ועל לשונית כל הנתונים.",
)
st.caption(f"🛒 נבחרו {len(_selected_chains)} רשתות: "
           + " · ".join(CHAINS_HE.get(c, c) for c in _selected_chains)
           + ("" if len(_selected_chains) >= 2 else "  ⚠️ בחרי לפחות 2 רשתות"))

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

    # ─── הרשימה שלי: העלאת קובץ + הזנה ידנית ───
    st.markdown("---")
    st.markdown("### 📋 הרשימה שלי")
    st.caption("כל משתמש רואה רק את הרשימה שלו — היא נשמרת בדפדפן של מי שהזין אותה ואינה משותפת עם אחרים.")

    up_col, tpl_col, save_col = st.columns([2, 1, 1])
    with up_col:
        uploaded = st.file_uploader(
            "העלאת רשימה מהמחשב (CSV / TXT / Excel)",
            type=["csv", "txt", "xlsx", "xls"],
            key="list_upload",
            help="קובץ עם עמודה של שמות מוצרים, ואם יש גם עמודת כמות — היא תיקרא אוטומטית",
        )
    with tpl_col:
        st.download_button(
            "⬇️ תבנית רשימה",
            "מוצר,כמות\nחלב 3%,2\nלחם אחיד,1\nביצים L,12\nקוטג',1\n".encode("utf-8-sig"),
            file_name="תבנית_רשימת_קניות.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with save_col:
        _cur = [x.strip() for x in str(st.session_state.get("shopping_list", "")).splitlines() if x.strip()]
        st.download_button(
            "⬇️ שמירת הרשימה שלי",
            ("מוצר,כמות\n" + "\n".join(_cur) + "\n").encode("utf-8-sig"),
            file_name="הרשימה_שלי.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if uploaded is not None:
        try:
            _fname = uploaded.name.lower()
            if _fname.endswith((".xlsx", ".xls")):
                _df_up = pd.read_excel(uploaded)
            else:
                _raw = uploaded.getvalue().decode("utf-8-sig", errors="replace")
                _lines_raw = [l for l in _raw.splitlines() if l.strip()]
                if _lines_raw and "," in _lines_raw[0]:
                    import io as _io
                    _df_up = pd.read_csv(_io.StringIO(_raw))
                else:
                    _df_up = pd.DataFrame({"מוצר": [l.strip() for l in _lines_raw]})

            _cols = {str(c).strip().lower(): c for c in _df_up.columns}
            _name_col = next((_cols[k] for k in ("מוצר", "פריט", "שם", "product", "name", "item") if k in _cols), _df_up.columns[0])
            _qty_col = next((_cols[k] for k in ("כמות", "מס'", "quantity", "qty", "count") if k in _cols), None)

            _parsed = []
            for _, _r in _df_up.iterrows():
                _nm = str(_r.get(_name_col, "") or "").strip()
                if not _nm or _nm.lower() in ("nan", "none"):
                    continue
                _pref = ""
                if _qty_col is not None:
                    try:
                        _q = float(_r.get(_qty_col))
                        _pref = f"{int(_q) if _q == int(_q) else _q} "
                    except Exception:
                        _pref = ""
                _parsed.append(f"{_pref}{_nm}".strip())

            if _parsed:
                _txt_new = "\n".join(_parsed)
                st.session_state["shopping_list"] = _txt_new
                st.session_state["input_area"] = _txt_new
                st.success(f"✅ נטענו {len(_parsed)} פריטים מהקובץ `{uploaded.name}`")
                st.rerun()
            else:
                st.warning("לא נמצאו פריטים בקובץ — ודאי שיש בו עמודה עם שמות מוצרים.")
        except Exception as _e:
            st.error(f"לא הצלחתי לקרוא את הקובץ: {_e}")

    st.markdown("**או הזיני ידנית — שורה לכל מוצר (אפשר להוסיף שורות בטבלה):**")
    _rows_init = pd.DataFrame([{"מוצר": "", "כמות": 1}] * 5)
    tbl_out = None
    try:
        tbl_out = st.data_editor(
            _rows_init, num_rows="dynamic", use_container_width=True, hide_index=True,
            key="items_table",
            column_config={
                "מוצר": st.column_config.TextColumn("מוצר", width="large"),
                "כמות": st.column_config.NumberColumn("כמות", min_value=0.0, step=1.0),
            },
        )
    except TypeError:
        tbl_out = st.data_editor(_rows_init, num_rows="dynamic", use_container_width=True,
                                 hide_index=True, key="items_table")
    st.caption("הפריטים שהוזנו בטבלה מתווספים אוטומטית להשוואה — אין צורך להעתיק אותם.")

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
        # ─── איסוף הפריטים יחד עם הכמויות (מהטקסט וגם מהטבלה) ───
        import re as _re

        def _qty_and_name(_line):
            """מחלץ כמות ושם מוצר משורה — '2 חלב 3%' / 'חלב 3% x2' / 'חלב 3%'."""
            _s = str(_line).strip()
            _m1 = _re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*[xX*×]?\s+(.+)$", _s)
            if _m1:
                return float(_m1.group(1).replace(",", ".")), _m1.group(2).strip()
            _m2 = _re.match(r"^(.+?)\s*[xX*×]\s*(\d+(?:[.,]\d+)?)$", _s)
            if _m2:
                return float(_m2.group(2).replace(",", ".")), _m2.group(1).strip()
            return 1.0, _s

        _pairs = []
        for _line in txt.splitlines():
            if _line.strip():
                _pairs.append(_qty_and_name(_line))

        try:
            _tbl = tbl_out if isinstance(tbl_out, pd.DataFrame) else pd.DataFrame(tbl_out)
            for _, _r in _tbl.iterrows():
                _nm2 = str(_r.get("מוצר", "") or "").strip()
                if not _nm2 or _nm2.lower() in ("nan", "none"):
                    continue
                try:
                    _q2 = float(_r.get("כמות", 1) or 1)
                except Exception:
                    _q2 = 1.0
                _pairs.append((_q2 if _q2 > 0 else 1.0, _nm2))
        except Exception:
            pass

        # איחוד לפי שם מוצר — כמויות של אותו מוצר מחוברות זו לזו
        qty_of, items = {}, []
        for _q, _n in _pairs:
            _key = _n.replace(" ", "").lower()
            if not _key:
                continue
            if _key in qty_of:
                qty_of[_key] = qty_of[_key] + _q
            else:
                qty_of[_key] = _q
                items.append(_n)

        if not items:
            st.warning("הזיני לפחות פריט אחד")
        else:
            with st.spinner(f"🔎 מחפש {len(items)} פריטים ברשתות..."):
                result = compare(items)

            # סינון לרשתות עם מכירה אונליין (לפי המתג שלמעלה)
            result = _filter_chains(result, _selected_chains)
            st.caption("🛒 הושוו " + " · ".join(CHAINS_HE.get(c, c) for c in result["chains"]))

            # ─── הסיכום משוקלל לפי הכמות (2 חלב = פעמיים המחיר) ───
            def _qty_for(_name):
                _k = str(_name).replace(" ", "").lower()
                if _k in qty_of:
                    return qty_of[_k]
                return qty_of.get(str(_name).strip().replace(" ", "").lower(), 1.0)

            _weighted = {}
            for _c in result["chains"]:
                _tot, _hits, _miss = 0.0, 0, 0
                for _m in result["matched"]:
                    _pr = _m["prices"].get(_c)
                    if _pr is None:
                        _miss += 1
                    else:
                        _hits += 1
                        _tot += _pr * _qty_for(_m["query"])
                _weighted[_c] = {"total": round(_tot, 2), "hits": _hits, "missing": _miss}
            result["totals"] = _weighted

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
                _q_item = _qty_for(m["query"])

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
                        {m['query']}{(' × ' + format(_q_item, 'g')) if _q_item > 1 else ''}
                    </div>
                    <div style="color:#6b7280;font-size:0.85rem;margin:4px 0 8px;">
                        {prod['name']}
                    </div>
                    <div>{tags_html}</div>
                    {('<div style="margin-top:6px;font-size:0.85rem;color:#374151;">סה&quot;כ לפריט זה ברשת הזולה: ' + format(min_price * _q_item, '.2f') + ' ₪</div>') if _q_item > 1 else ''}
                </div>
                """, unsafe_allow_html=True)

            # ─── סיכום סלים בכרטיסים ──────────
            st.markdown("---")
            st.markdown("### 💰 סיכום סלים")
            _qty_items = [i for i in items if _qty_for(i) > 1]
            st.caption("הסיכום משוקלל לפי הכמויות שהזנת — "
                       + (", ".join(f"{i} × {format(_qty_for(i), 'g')}" for i in _qty_items)
                          if _qty_items else "כל פריט נספר ביחידה אחת."))
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


                # ─── ⚖️ הוגנות ההשוואה: מי לא כללה איזה פריט ───
                st.markdown("---")
                st.markdown("### ⚖️ הוגנות ההשוואה — מי לא כללה איזה פריט")
                st.caption("רשת שלא מוכרת פריט מהסל שלך מקבלת יתרון לא הוגן, כי הפריט פשוט לא נספר לה.")

                _eligible = [c for c in chains if result["totals"][c]["hits"] > 0]
                _missing_by_chain = {}
                for _c in _eligible:
                    _its = []
                    for _m in result["matched"]:
                        if _m["prices"].get(_c) is None:
                            _q = _qty_for(_m["query"])
                            _its.append(str(_m["query"]) + (f" × {format(_q, 'g')}" if _q > 1 else ""))
                    if _its:
                        _missing_by_chain[_c] = _its

                if _missing_by_chain:
                    for _c, _its in sorted(_missing_by_chain.items(), key=lambda x: (-len(x[1]), x[0])):
                        st.warning(
                            f"**{CHAINS_HE.get(_c, _c)}** לא כללה {len(_its)} פריטים מהסל: " + " · ".join(_its)
                        )
                    if winner[0] in _missing_by_chain:
                        st.error(
                            f"⚠️ שימי לב: הרשת הזולה הכוללת — **{CHAINS_HE.get(winner[0], winner[0])}** — "
                            f"לא כללה {len(_missing_by_chain[winner[0]])} פריטים מהסל. "
                            "הסיכום שלה אינו הוגן מול רשתות שכללו את הסל במלואו."
                        )
                else:
                    st.success("✅ כל הרשתות כללו את כל פריטי הסל — ההשוואה הוגנת לחלוטין.")

                # השוואה הוגנת: רק הפריטים שקיימים בכל הרשתות
                _common = [m for m in result["matched"]
                           if _eligible and all(m["prices"].get(c) is not None for c in _eligible)]
                if _eligible and _common and len(_common) < len(result["matched"]):
                    st.markdown(
                        f"**השוואה הוגנת — רק {len(_common)} מתוך {len(result['matched'])} הפריטים "
                        f"שקיימים בכל {len(_eligible)} הרשתות:**"
                    )
                    _fair = {_c: round(sum(m["prices"][_c] * _qty_for(m["query"]) for m in _common), 2)
                             for _c in _eligible}
                    _fair_sorted = sorted(_fair.items(), key=lambda x: x[1])
                    st.dataframe(
                        pd.DataFrame([
                            {"רשת": CHAINS_HE.get(_c, _c),
                             'סה"כ הוגן (₪)': _t,
                             "פער מהזולה (₪)": round(_t - _fair_sorted[0][1], 2)}
                            for _c, _t in _fair_sorted
                        ]),
                        use_container_width=True, hide_index=True,
                    )
                    st.success(
                        f"🏆 בהשוואה הוגנת הזולה היא **{CHAINS_HE.get(_fair_sorted[0][0], _fair_sorted[0][0])}** "
                        f"— {_fair_sorted[0][1]} ₪ לפריטים המשותפים."
                    )
                elif _eligible and not _common:
                    st.info("אין אפילו פריט אחד שכל הרשתות כללו — לכן אי אפשר להציג השוואה הוגנת מלאה.")
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

    CHAIN_KEYS = ["shufersal", "rami-levy", "yohananof", "osher-ad",
                  "tiv-taam", "keshet", "freshmarket", "paz"]
    CHAIN_KEYS = [c for c in CHAIN_KEYS if c in _selected_chains]
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
