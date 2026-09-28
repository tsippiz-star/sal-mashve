"""
app.py – סל משווה · השוואת מחירי סל קניות בין רשתות המזון בישראל.
עיצוב v7 — "מזמין וידידותי".

הפעלה מקומית:
    streamlit run app.py

קבצים נדרשים באותה תיקייה: comparator.py, matcher.py, sm_style.py, prices.db
"""
import io as _io
import re as _re
import sqlite3
import time
import datetime as _dt
from datetime import datetime, timedelta as _tdelta, timezone as _tz
from pathlib import Path

import pandas as pd
import streamlit as st

from comparator import CHAINS_HE, produce_prices, PRODUCE_ITEMS
from matcher import match_item, find_candidates
import sm_style as ui
try:
    import facets as fx          # "כל הסוגים" + זנים לירקות
    HAS_FACETS = True
except Exception:                # אם facets.py לא הועלה — האתר ממשיך לעבוד בלי התכונה הזו
    fx = None
    HAS_FACETS = False

APP_VERSION = "db-look v8 · מבצעים, משלוח, סל מפוצל, היסטוריה · 2026-09-27"
ROOT = Path(__file__).resolve().parent

# ═══════════════════════════════════════════════════════
# 1) בחירת קובץ המסד — ללא שינוי מהגרסה הקודמת
#    1) הכי הרבה רשתות  2) הכי הרבה שורות  3) קובץ בשם prices.db  4) הגודל
# ═══════════════════════════════════════════════════════
def _db_stats(_p):
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

# רשתות שמוכרות גם אונליין (ברירת המחדל בהשוואה)
ONLINE_CHAINS = ["shufersal", "rami-levy", "yohananof", "tiv-taam",
                 "keshet", "freshmarket", "paz", "carrefour", "hazi-hinam"]
# ─── אתרי הקנייה אונליין של הרשתות (נבדקו ידנית · 27/09/2026) ───
# רשת שלא מופיעה כאן = אין לה קנייה אונליין, והכפתור יפנה לרשת הזולה הבאה שיש לה.
STORE_URLS = {
    "shufersal":   "https://www.shufersal.co.il/online/he/",
    "rami-levy":   "https://www.rami-levy.co.il/he",
    "yohananof":   "https://yochananof.co.il/",
    "tiv-taam":    "https://www.tivtaam.co.il/",
    "keshet":      "https://www.keshet-teamim.co.il/",
    "freshmarket": "https://www.freshmarket.co.il/",
    "carrefour":   "https://www.carrefour.co.il/",
    "hazi-hinam":  "https://shop.hazi-hinam.co.il/",
    "victory":     "https://www.victoryonline.co.il/",
}

ALL_CHAINS = ["shufersal", "rami-levy", "yohananof", "osher-ad",
              "tiv-taam", "keshet", "freshmarket", "paz", "carrefour", "hazi-hinam"]

# ─── משיכת המסד המתעדכן אוטומטית (ענף data, מה-Action היומי) ───
REMOTE_DB_URL = "https://raw.githubusercontent.com/tsippiz-star/sal-mashve/data/prices.db"
REMOTE_DB_PATH = Path("/tmp/prices_live.db")
REMOTE_MAX_AGE_HOURS = 6


def _fetch_remote_db():
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
    if _rc >= 3:
        DB_PATH, DB_INFO = _remote_db, (_rc, _rr, _rs)
        DB_SCAN.append((_remote_db, (_rc, _rr, _rs)))
        REMOTE_USED = True

import comparator as _comparator
import matcher as _matcher
_comparator.DB_PATH = DB_PATH
_matcher.DB_PATH = DB_PATH

# ─── v8: קובץ היסטוריית המחירים (נבנה בסריקה היומית, ענף data) ───
HISTORY_URL = "https://raw.githubusercontent.com/tsippiz-star/sal-mashve/data/history.db"
HISTORY_PATH = Path("/tmp/history_live.db")


def _fetch_history_db():
    import urllib.request as _ur
    local = ROOT / "history.db"
    try:
        if HISTORY_PATH.exists() and (time.time() - HISTORY_PATH.stat().st_mtime) < REMOTE_MAX_AGE_HOURS * 3600:
            return str(HISTORY_PATH)
        _req = _ur.Request(HISTORY_URL, headers={"User-Agent": "sal-mashve-app"})
        with _ur.urlopen(_req, timeout=60) as _r:
            HISTORY_PATH.with_suffix(".part").write_bytes(_r.read())
        HISTORY_PATH.with_suffix(".part").replace(HISTORY_PATH)
        return str(HISTORY_PATH)
    except Exception:
        if HISTORY_PATH.exists():
            return str(HISTORY_PATH)
        return str(local) if local.exists() else None


HISTORY_DB = _fetch_history_db()

try:
    import extras as xx          # v8: מבצעים, משלוח, סל מפוצל, היסטוריה, שיתוף
    HAS_EXTRAS = True
except Exception:
    xx = None
    HAS_EXTRAS = False

try:                             # שמירת הרשימה בדפדפן (localStorage)
    from streamlit_js_eval import streamlit_js_eval
    HAS_JS = True
except Exception:
    HAS_JS = False

# ═══════════════════════════════════════════════════════
# 2) הגדרות עמוד + עיצוב
# ═══════════════════════════════════════════════════════
st.set_page_config(
    page_title="סל משווה – הסל הכי זול בישראל",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"About": "השוואת מחירים חכמה בין רשתות המזון בישראל.\nנתונים מקבצי שקיפות מחירים רשמיים."},
)
ui.inject_css()
st.markdown('<link rel="manifest" href="/static/manifest.json"><meta name="theme-color" content="#1F7A5A">'
            '<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="סל משווה">',
            unsafe_allow_html=True)


def cname(c):
    return CHAINS_HE.get(c, c)


# ═══════════════════════════════════════════════════════
# 3) נתונים ומצב
# ═══════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def get_db_info(_path_str):
    if not Path(_path_str).exists():
        return None
    conn = sqlite3.connect(_path_str)
    info = conn.execute("SELECT chain, COUNT(*), MAX(updated_at) FROM prices GROUP BY chain ORDER BY COUNT(*) DESC").fetchall()
    conn.close()
    return info


@st.cache_data(ttl=300)
def _db_misc(_path_str):
    try:
        _c = sqlite3.connect(f"file:{_path_str}?mode=ro", uri=True)
        _b = _c.execute("SELECT COUNT(DISTINCT barcode) FROM prices").fetchone()[0]
        _u = _c.execute("SELECT MAX(updated_at) FROM prices").fetchone()[0]
        _c.close()
        return (_b or 0), (_u or "")
    except Exception:
        return 0, ""


info = get_db_info(str(DB_PATH))
_uniq, _last_upd = _db_misc(str(DB_PATH))
total_rows = sum(cnt for _, cnt, _ in info) if info else 0
_found_keys = [c for c, _n, _u in (info or [])]
_missing_names = [cname(c) for c in ONLINE_CHAINS if c not in _found_keys]

# ─── השוואה מול גיטהאב — האם צריך Reboot ───
GITHUB_REPO = "tsippiz-star/sal-mashve"
GITHUB_BRANCH = "main"
_IL = _tz(_tdelta(hours=3))


@st.cache_data(ttl=600, show_spinner=False)
def _github_db_info():
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
_all_names = sorted(_env_files) if not _gh_info else sorted(set(_env_files) | set(_gh_info))
_rows_cmp, _need_reboot = [], []
for _name in _all_names:
    _ep = _env_files.get(_name)
    _gp = _gh_info.get(_name) or {}
    _env_dt = datetime.fromtimestamp(_ep.stat().st_mtime, _tz.utc) if _ep else None
    _gh_size, _gh_iso = _gp.get("size"), _gp.get("commit")
    _gh_dt = datetime.fromisoformat(_gh_iso.replace("Z", "+00:00")) if _gh_iso else None
    if _ep is not None and _ep == REMOTE_DB_PATH:
        _state = "✅ עדכון יומי (ענף data)"
    elif _gh_size is None:
        _state = "— לא נמצא בגיטהאב"
    elif _ep is None:
        _state = "🔄 נדרש Reboot — הקובץ עוד לא הגיע לסביבה"
        _need_reboot.append(f"{_name} חסר בסביבה")
    elif _ep.stat().st_size != _gh_size:
        _state = "🔄 נדרש Reboot — גרסה שונה מזו שבגיטהאב"
        _need_reboot.append(f"{_name} בגודל שונה")
    elif _gh_dt and _env_dt and _gh_dt > _env_dt + _tdelta(minutes=2):
        _state = "🔄 נדרש Reboot — בגיטהאב יש גרסה חדשה יותר"
        _need_reboot.append(f"{_name} חדש יותר בגיטהאב")
    else:
        _state = "✅ מעודכן"
    _rows_cmp.append({
        "קובץ": _name,
        "תאריך בסביבה": _env_dt.astimezone(_IL).strftime("%d/%m/%Y %H:%M") if _env_dt else "❌ לא קיים",
        "תאריך בגיטהאב": _gh_dt.astimezone(_IL).strftime("%d/%m/%Y %H:%M") if _gh_dt else "—",
        "גודל בסביבה (MB)": round(_ep.stat().st_size / 1048576, 1) if _ep else "❌",
        "גודל בגיטהאב (MB)": round(_gh_size / 1048576, 1) if _gh_size is not None else "—",
        "מצב": _state,
    })

DATA_OK = bool(info) and not _missing_names and not _need_reboot

# ─── session state ───
ss = st.session_state
ss.setdefault("items", [])
ss.setdefault("history", [])
ss.setdefault("uid", 0)
ss.setdefault("seeded", False)

# ═══════════════════════════════════════════════════════
# 4) לוגיקת הסל
# ═══════════════════════════════════════════════════════
_KG = r'(?:ק"?ג|קילו(?:גרם)?|קילוגרם|קג)'


def _qty_and_name(_line):
    """כמות ושם מוצר. תומך גם במשקל: '2 קילו עגבניות' / 'עגבניות 1.5 ק"ג' / '500 גרם עגבניות'."""
    _s = str(_line).strip()
    _m = _re.match(rf"^\s*(\d+(?:[.,]\d+)?)\s*{_KG}\s+(.+)$", _s)
    if _m:
        return float(_m.group(1).replace(",", ".")), _m.group(2).strip(), True
    _m = _re.match(rf"^(.+?)\s+(\d+(?:[.,]\d+)?)\s*{_KG}\s*$", _s)
    if _m:
        return float(_m.group(2).replace(",", ".")), _m.group(1).strip(), True
    _m = _re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:גרם|גר'|גר)\s+(.+)$", _s)
    if _m:
        return float(_m.group(1).replace(",", ".")) / 1000.0, _m.group(2).strip(), True
    _m = _re.match(r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s*(?:גרם|גר'|גר)\s*$", _s)
    if _m:
        return float(_m.group(2).replace(",", ".")) / 1000.0, _m.group(1).strip(), True
    _m1 = _re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*[xX*×]?\s+(.+)$", _s)
    if _m1:
        return float(_m1.group(1).replace(",", ".")), _m1.group(2).strip(), False
    _m2 = _re.match(r"^(.+?)\s*[xX*×]\s*(\d+(?:[.,]\d+)?)$", _s)
    if _m2:
        return float(_m2.group(2).replace(",", ".")), _m2.group(1).strip(), False
    return 1.0, _s, False


@st.cache_data(show_spinner=False, ttl=3600)
def _match_cached(q, _db):
    prod = match_item(q)
    if prod:
        return {"barcode": prod["barcode"], "name": prod["name"], "brand": prod.get("brand", "")}, []
    return None, find_candidates(q, 4)


@st.cache_data(show_spinner=False, ttl=3600)
def _prices_for(barcode, _db):
    """ממוצע ארצי לכל רשת (כמו price_by_barcode) + יחידת מידה."""
    conn = sqlite3.connect(_db)
    rows = conn.execute("SELECT chain, AVG(price) FROM prices WHERE barcode = ? AND price > 0 GROUP BY chain", (barcode,)).fetchall()
    u = conn.execute("SELECT MAX(unit) FROM prices WHERE barcode = ?", (barcode,)).fetchone()
    conn.close()
    return {c: round(p, 2) for c, p in rows if p}, (u[0] if u and u[0] else "")


def _new_item(q, qty=1.0, kg=False, prod=None, cands=None):
    ss.uid += 1
    return {"uid": ss.uid, "q": q, "qty": qty, "kg": kg,
            "barcode": prod["barcode"] if prod else None,
            "name": prod["name"] if prod else "",
            "status": "ok" if prod else ("unclear" if cands else "none"),
            "cands": cands or []}


def add_lines(lines):
    n = 0
    for line in lines:
        if not str(line).strip():
            continue
        qty, q, kg = _qty_and_name(line)
        prod, cands = _match_cached(q, str(DB_PATH))
        ex = next((x for x in ss["items"] if prod and x["barcode"] == prod["barcode"]), None) or \
            next((x for x in ss["items"] if x["q"].replace(" ", "") == q.replace(" ", "")), None)
        if ex:
            ex["qty"] = round(ex["qty"] + qty, 3)
        else:
            ss["items"].append(_new_item(q, qty, kg, prod, cands))
        n += 1
    return n


def _toast(msg, icon="✅"):
    try:
        st.toast(msg, icon=icon)
    except Exception:
        pass


# ─── השלמה אוטומטית ───
try:
    from streamlit_searchbox import st_searchbox
    HAS_SEARCHBOX = True
except Exception:   # אם הרכיב לא מותקן — חוזרים לשדה הרגיל, הכול ממשיך לעבוד
    HAS_SEARCHBOX = False

_QUOTES_RE = "[" + _re.escape(chr(34) + "'׳״") + "]"
_KG_LBL = " ק״ג"

SEARCHBOX_STYLE = {
    "wrapper": {"direction": "rtl", "fontFamily": "Heebo, Rubik, Arial, sans-serif"},
    "clear": {"icon": "cross", "clearable": "always", "width": 18, "height": 18, "stroke": "#85938C"},
    "dropdown": {"rotate": True, "width": 22, "height": 22, "fill": "#85938C"},
    "searchbox": {
        "control": {"direction": "rtl", "borderRadius": 16, "minHeight": 52, "fontSize": 16.5,
                    "backgroundColor": "#F5FAF7", "borderColor": "#DCE3DD"},
        "placeholder": {"color": "#85938C"},
        "input": {"direction": "rtl"},
        "menuList": {"direction": "rtl", "fontSize": 15, "maxHeight": 330},
        "option": {"color": "#17231E", "backgroundColor": "#FFFFFF", "highlightColor": "#E7F3EC"},
        "optionEmpty": "hidden",
    },
}


@st.cache_resource(show_spinner=False, ttl=3600)
def _catalog(_db):
    """קטלוג להשלמה: שם, מותג, מספר רשתות, המחיר הזול והרשת הזולה. נטען פעם אחת לזיכרון."""
    conn = sqlite3.connect(_db)
    df = pd.read_sql_query(
        "SELECT barcode, chain, MAX(name) AS name, MAX(brand) AS brand, AVG(price) AS price "
        "FROM prices WHERE barcode != '' AND name != '' AND price > 0 GROUP BY barcode, chain", conn)
    conn.close()
    if df.empty:
        return df
    df = df.sort_values("price")
    g = df.groupby("barcode", sort=False)
    cat = pd.DataFrame({
        "name": g["name"].first(), "brand": g["brand"].first(),
        "n": g["chain"].nunique(), "min": g["price"].first().round(2), "best": g["chain"].first(),
    }).reset_index()
    cat["key"] = (cat["name"].fillna("") + " " + cat["brand"].fillna("")).str.replace(_QUOTES_RE, "", regex=True).str.lower()
    return cat.sort_values("n", ascending=False).reset_index(drop=True)


def search_products(term):
    """לרכיב ההשלמה: [(תווית, ערך)]. השורה הראשונה = הוספת הטקסט בדיוק כפי שנכתב."""
    term = str(term or "").strip()
    if not term:
        return []
    qty, q, kg = _qty_and_name(term)
    out = [("➕ הוספת ״" + term + "״", {"raw": term})]
    toks = [t for t in _re.sub(_QUOTES_RE, "", q.lower()).split() if t]
    cat = _catalog(str(DB_PATH))
    if not toks or cat is None or cat.empty:
        return out
    m = cat["key"].str.contains(toks[0], regex=False)
    for t in toks[1:]:
        m &= cat["key"].str.contains(t, regex=False)
    qlbl = (format(qty, "g") + (_KG_LBL if kg else "") + " × ") if qty != 1 else ""
    for _, r in cat[m].head(8).iterrows():
        br = str(r["brand"] or "")
        brand = (" · " + br) if br and br.lower() not in ("לא ידוע", "none", "unknown", "nan") else ""
        lbl = f"{qlbl}{r['name']}{brand}  —  מ-{r['min']:.2f} ₪ ב{cname(r['best'])} · {r['n']} רשתות"
        out.append((lbl, {"barcode": r["barcode"], "name": r["name"], "qty": qty, "kg": kg}))
    return out


def cb_pick_suggestion(val):
    if not val:
        return
    if "raw" in val:
        add_lines([s for s in _re.split(r"\n|,(?=\s*\D)", val["raw"]) if s.strip()])
        return
    ex = next((x for x in ss["items"] if x["barcode"] == val["barcode"]), None)
    if ex:
        ex["qty"] = round(ex["qty"] + val["qty"], 3)
    else:
        nm = str(val["name"])
        ss["items"].append(_new_item(nm if len(nm) <= 40 else nm[:39] + "…", val["qty"], val["kg"],
                                     {"barcode": val["barcode"], "name": nm}))


# ─── callbacks ───
def cb_add():
    txt = ss.get("adder_text", "")
    lines = [s for s in _re.split(r"\n|,(?=\s*\D)", txt) if s.strip()]
    if add_lines(lines):
        ss["adder_text"] = ""


def cb_qty(uid, d):
    for it in ss["items"]:
        if it["uid"] == uid:
            step = 0.5 if it["kg"] else 1.0
            it["qty"] = max(step, round(it["qty"] + d * step, 3))


def cb_remove(uid):
    ss["items"] = [x for x in ss["items"] if x["uid"] != uid]


def cb_pick(uid, cand):
    for it in ss["items"]:
        if it["uid"] == uid:
            it.update(barcode=cand["barcode"], name=cand["name"], status="ok", cands=[], group=None)


def _group_desc(it):
    fam = _family(it["group"]["query"], str(DB_PATH))
    n = len(fx.filter_products(fam, it["group"]["sel"]))
    s = fx.sel_summary(it["group"]["sel"])
    return f"כל הסוגים{' · ' + s if s else ''} · {n} מוצרים — נלקח הזול בכל רשת"


@st.dialog("כל הסוגים", width="large")
def group_dialog(uid):
    it = next((x for x in ss["items"] if x["uid"] == uid), None)
    if not it:
        return
    base_q = it.get("group", {}).get("query") if it.get("group") else it["q"]
    fam = _family(base_q, str(DB_PATH))
    if not fam["products"]:
        ui.md(ui.alert(f"לא מצאתי משפחת מוצרים עבור ״{ui.esc(base_q)}״. נסי שם כללי יותר (למשל ״חלב״ או ״יוגורט״)."))
        return
    cur = (it.get("group") or {}).get("sel") or fam["pre"]
    ui.md(f'<p class="sub" style="margin-top:0">בחרי מה מתאים לך — כמה שרוצה בכל קטגוריה. '
          f'בכל רשת נחשב <b>המוצר הזול ביותר</b> מבין מה שבחרת. קטגוריה שלא בחרת בה כלום = הכל.</p>')
    sel = {}
    for key, label in fx.FACET_ORDER:
        vals = fam["facets"].get(key)
        if not vals:
            continue
        sel[key] = st.pills(label, vals, selection_mode="multi", key=f"fx_{uid}_{key}",
                            default=[v for v in cur.get(key, []) if v in vals]) or []
    norm = True
    matched = fx.filter_products(fam, sel)
    sizes = {p["amt"] for p in matched if p["amt"]}
    if len(sizes) > 1:
        norm = st.toggle("להשוות לפי מחיר ליחידת מידה (מומלץ כשיש כמה גדלים)", value=(it.get("group") or {}).get("norm", True),
                         key=f"fx_{uid}_norm")
    prices, picks, info = fx.group_prices(fam, sel, _selected_chains, normalize=norm)
    have = {c: p for c, p in prices.items() if p is not None}
    if not matched:
        ui.md(ui.alert("אין מוצרים שעונים על כל הבחירות יחד. נסי להסיר בחירה אחת."))
    else:
        ref = f" · מחיר מנורמל ל-{info['ref_label']}" if info["norm"] else ""
        ui.md(f'<div class="sec-head" style="margin-top:6px"><div class="h2" style="font-size:16px">{len(matched)} מוצרים מתאימים</div>'
              f'<span class="tiny">הזול בכל רשת{ref}</span></div>')
        ui.md(ui.group_preview_html(
            sorted(((c, cname(c), have[c], picks[c][0], picks[c][1]) for c in have), key=lambda x: x[2])[:6],
            [p["name"] for p in matched[:12]], len(matched)))
    b1, b2, b3 = st.columns([1.3, 1, 1])
    with b1:
        if st.button("שמירה", type="primary", use_container_width=True, disabled=not matched, key=f"fx_{uid}_ok"):
            it["group"] = {"query": base_q, "sel": {k: v for k, v in sel.items() if v}, "norm": norm}
            it.update(status="ok", cands=[])
            _toast("עודכן: " + it["q"])
            st.rerun()
    with b2:
        if it.get("group") and st.button("מוצר אחד בלבד", use_container_width=True, key=f"fx_{uid}_single",
                                        help="חזרה למוצר הספציפי שזוהה בהתחלה"):
            it["group"] = None
            it["status"] = "ok" if it["barcode"] else "none"
            st.rerun()
    with b3:
        if st.button("ביטול", use_container_width=True, key=f"fx_{uid}_cancel"):
            st.rerun()


def cb_clear():
    ss["items"] = []


def cb_quick(lines, title):
    ss["items"] = []
    add_lines(lines)
    _toast(f"נטען {title} · {len(lines)} מוצרים")


def cb_paste():
    add_lines(str(ss.get("paste_text", "")).splitlines())
    ss["paste_text"] = ""
    _toast("הרשימה נוספה לסל")


def cb_add_barcode(barcode, name):
    if any(x["barcode"] == barcode for x in ss["items"]):
        _toast("המוצר כבר בסל", "ℹ️")
        return
    ss["items"].append(_new_item(name[:40], 1.0, False, {"barcode": barcode, "name": name}))
    _toast(f"{name[:30]} נוסף לסל")


def cb_nav_guard():
    if ss.get("nav") is None:
        ss["nav"] = ss.get("_last_nav", TABS[0])


def cb_reuse(idx):
    h = ss["history"][idx]
    ss["items"] = [dict(x, uid=i + 1000 * (idx + 1) + ss.uid) for i, x in enumerate(h["list"])]
    ss.uid += len(h["list"]) + 1000
    ss["nav"] = TABS[0]
    _toast("הסל נטען מחדש")


def _qlabel(it):
    return it["q"] + (f" × {format(it['qty'], 'g')}" + (" ק״ג" if it["kg"] else "") if it["qty"] != 1 else "")


@st.cache_data(show_spinner=False, ttl=3600)
def _family(query, _db):
    return fx.family(_db, query)


def _group_row(it, chains):
    """מחיר לכל רשת לפריט מסוג 'קבוצה': הזול מבין כל המוצרים שעונים על הסינון."""
    fam = _family(it["group"]["query"], str(DB_PATH))
    prices, picks, info = fx.group_prices(fam, it["group"]["sel"], chains, normalize=it["group"].get("norm", True))
    return prices, picks, info


def compute(items, chains):
    rows = []
    for it in items:
        if it.get("group"):
            prices, picks, info = _group_row(it, chains)
            if info["n"] == 0:
                continue
            rows.append({"it": it, "prices": prices, "unit": "", "picks": picks, "info": info})
            continue
        if not it["barcode"]:
            continue
        pr, unit = _prices_for(it["barcode"], str(DB_PATH))
        rows.append({"it": it, "prices": {c: pr.get(c) for c in chains}, "unit": unit})
    # ─── v8: מבצעים — עלות כל שורה עם המבצע המשתלם ביותר ───
    use_promos = bool(HAS_EXTRAS and ss.get("opt_promos", True))
    pmap = {}
    if use_promos:
        bcs = {r["it"]["barcode"] for r in rows if r["it"].get("barcode") and not r["it"].get("group")}
        pmap = _promos_cached(tuple(sorted(bcs)), tuple(chains), str(DB_PATH))
    for r in rows:
        r["cost"], r["deal"], r["hint"] = {}, {}, {}
        for c in chains:
            p = r["prices"].get(c)
            if p is None:
                r["cost"][c] = None
                continue
            pr = pmap.get((r["it"].get("barcode"), c)) if use_promos and not r["it"].get("group") else None
            if pr:
                cost, deal = xx.line_cost(p, r["it"]["qty"], pr)
                hint = xx.promo_hint(p, r["it"]["qty"], pr)
            else:
                cost, deal, hint = round(p * r["it"]["qty"], 2), None, None
            r["cost"][c] = cost
            if deal:
                r["deal"][c] = deal
            if hint:
                r["hint"][c] = hint
    totals = {}
    for c in chains:
        t, miss, saved = 0.0, [], 0.0
        for r in rows:
            cst = r["cost"][c]
            if cst is None:
                miss.append(_qlabel(r["it"]))
            else:
                t += cst
                saved += r["prices"][c] * r["it"]["qty"] - cst
        totals[c] = {"total": round(t, 2), "hits": len(rows) - len(miss), "missing": miss,
                     "promo_saved": round(saved, 2)}
    eligible = [c for c in chains if totals[c]["hits"] > 0]
    common = [r for r in rows if eligible and all(r["cost"][c] is not None for c in eligible)]
    fair = {c: round(sum(r["cost"][c] for r in common), 2) for c in eligible}
    # ─── v8: קנייה אונליין — דמי משלוח ומינימום הזמנה ───
    deliver = bool(HAS_EXTRAS and ss.get("opt_delivery", False))
    fees = {}
    if deliver:
        for c in eligible:
            f, under = xx.delivery_for(c, totals[c]["total"])
            fees[c] = {"fee": f, "under_min": under}
    return {"rows": rows, "totals": totals, "eligible": eligible, "common": common, "fair": fair,
            "fees": fees, "deliver": deliver}


@st.cache_data(show_spinner=False, ttl=1800)
def _promos_cached(bcs, chains, _db):
    return xx.promos_for(_db, list(bcs), list(chains)) if HAS_EXTRAS else {}


def door_total(res, c, fair=False):
    """סה״כ לרשת — כולל משלוח אם בחרו 'קונה אונליין'."""
    base = res["fair"][c] if fair else res["totals"][c]["total"]
    if res.get("deliver"):
        f = (res["fees"].get(c) or {}).get("fee")
        if f is None:
            return None
        return round(base + f, 2)
    return base


@st.cache_data(show_spinner=False, ttl=1800)
def _basket_index_cached(items_t, chains_t, _hdb):
    return xx.basket_index(_hdb, list(items_t), list(chains_t), 30) if HAS_EXTRAS else None


@st.cache_data(show_spinner=False, ttl=3600)
def _private_label_catalog(chain, _db):
    """מוצרי המותג הפרטי של רשת: [(barcode, name, price)]"""
    if not HAS_EXTRAS:
        return []
    words = xx.PRIVATE_LABEL.get(chain, [])
    if not words:
        return []
    conn = sqlite3.connect(_db)
    cond = " OR ".join(["name LIKE ? OR brand LIKE ?"] * len(words))
    args = [x for w in words for x in (f"%{w}%", f"%{w}%")]
    rows = conn.execute(f"SELECT barcode, MAX(name), AVG(price) FROM prices WHERE chain = ? AND price > 0 AND ({cond}) "
                        "GROUP BY barcode", [chain] + args).fetchall()
    conn.close()
    return [(b, n, round(p, 2)) for b, n, p in rows]


def private_label_swaps(res, chain):
    """לכל מוצר בסל: האם יש מותג פרטי של הרשת מאותו סוג, ובכמה הוא זול (או יקר) יותר."""
    cat = _private_label_catalog(chain, str(DB_PATH))
    if not cat or not HAS_FACETS:
        return []
    out = []
    for r in res["rows"]:
        it = r["it"]
        cur = r["cost"].get(chain)
        if cur is None or it.get("group"):
            continue
        core = fx._core_tokens(it["q"])[0]
        if not core:
            continue
        cands = [(b, n, p) for b, n, p in cat if b != it.get("barcode") and fx._head_match(core[0], fx._n(n), 3)]
        if not cands:
            continue
        # מחיר לאותה כמות (לפי גודל אריזה אם אפשר)
        mine = fx.size_of(it.get("name") or it["q"], "", 0)
        best = None
        for b, n, p in cands:
            s = fx.size_of(n, "", 0)
            val = p * it["qty"]
            if mine and s and s[1] == mine[1] and s[0]:
                val = p / s[0] * mine[0] * it["qty"]
            if best is None or val < best[2]:
                best = (b, n, round(val, 2))
        if best:
            out.append({"q": it["q"], "cur": cur, "pl_name": best[1], "pl": best[2], "diff": round(cur - best[2], 2)})
    return out


def share_block():
    """קישור שיתוף + העתקת הרשימה."""
    if not HAS_EXTRAS or not ss["items"]:
        return
    code = xx.pack_items(ss["items"])
    base = ""
    try:
        base = str(st.context.url or "").split("?")[0]
    except Exception:
        pass
    link = f"{base}?list={code}" if base else f"?list={code}"
    with st.expander("🔗 שיתוף הרשימה"):
        ui.md('<div class="tiny" style="margin-bottom:6px">מי שיפתח את הקישור יראה בדיוק את אותה רשימה. לשלוח בוואטסאפ, במייל או להעתיק.</div>')
        st.code(link, language=None)
        _txt = "הרשימה שלי בסל משווה 🛒\n" + xx.items_to_text(ss["items"]) + "\n\n" + link
        import urllib.parse as _up
        c1, c2 = st.columns(2)
        with c1:
            st.link_button("שליחה בוואטסאפ", "https://wa.me/?text=" + _up.quote(_txt), use_container_width=True)
        with c2:
            st.download_button("הורדה כטקסט", _txt.encode("utf-8"), file_name="הרשימה_שלי.txt",
                               use_container_width=True)
        ui.md('<div class="tiny" style="margin-top:6px">הרשימה נשמרת גם אוטומטית בדפדפן הזה — כשתחזרי לאתר היא תחכה לך.</div>')


def _persist_list():
    """שמירה אוטומטית בדפדפן (localStorage) — בלי הרשמה ובלי שרת."""
    if not HAS_EXTRAS or not HAS_JS:
        return
    code = xx.pack_items(ss["items"]) if ss["items"] else ""
    if ss.get("_saved_code") == code:
        return
    ss["_saved_code"] = code
    streamlit_js_eval(js_expressions=f"localStorage.setItem('sal_mashve_list', '{code}')",
                      key=f"ls_set_{abs(hash(code)) % 10**8}")


def _restore_items(slim):
    out = []
    for d in slim:
        ss.uid += 1
        out.append({"uid": ss.uid, "q": d["q"], "qty": float(d.get("qty") or 1), "kg": bool(d.get("kg")),
                    "barcode": d.get("b"), "name": d.get("n") or "", "status": "ok" if (d.get("b") or d.get("g")) else "none",
                    "cands": [], "group": d.get("g")})
    return out


def save_history(res):
    el = res["eligible"]
    if not el:
        return
    s = sorted(el, key=lambda c: res["totals"][c]["total"])
    ss["history"].insert(0, {
        "date": datetime.now(_IL).strftime("%d/%m %H:%M"),
        "items": [x["q"] for x in ss["items"]],
        "chain": s[0], "total": res["totals"][s[0]]["total"],
        "savings": round(res["totals"][s[-1]]["total"] - res["totals"][s[0]]["total"], 2),
        "list": [dict(x) for x in ss["items"]],
    })
    ss["history"] = ss["history"][:20]
    _toast("הסל נשמר ב״הסלים שלי״")


# ═══════════════════════════════════════════════════════
# 5) חלונית "מצב הנתונים" (כל הפירוט הטכני)
# ═══════════════════════════════════════════════════════
@st.dialog("מצב הנתונים", width="large")
def data_status_dialog():
    if DATA_OK:
        ui.md(ui.alert(f"כל {len(_found_keys)} הרשתות נטענו בהצלחה, והנתונים מעודכנים.", "ok", "✓"))
    else:
        if _missing_names:
            ui.md(ui.alert(f"נטענו רק {len(_found_keys)} מתוך {len(ONLINE_CHAINS)} הרשתות. חסרות: {', '.join(_missing_names)}. "
                           "כנראה שהאפליקציה קוראת קובץ נתונים ישן או חלקי — ראי ״קבצי הנתונים״ למטה."))
        if _need_reboot:
            ui.md(ui.alert("נדרש Reboot: " + " · ".join(_need_reboot) +
                           " — בתפריט ⋯ ← Reboot app. בלי זה האפליקציה תמשיך לעבוד עם הגרסה הישנה.", "warn", "🔄"))
    ui.md(f'<div class="stat-grid">'
          f'<div class="stat"><div class="v num">{total_rows:,}</div><div class="l">מחירים במאגר</div></div>'
          f'<div class="stat"><div class="v num">{_uniq:,}</div><div class="l">מוצרים ייחודיים</div></div>'
          f'<div class="stat"><div class="v">{len(_found_keys)}</div><div class="l">רשתות</div></div>'
          f'<div class="stat"><div class="v num" style="font-size:15px">{ui.esc((_last_upd or "—")[:16])}</div><div class="l">עדכון אחרון</div></div></div>')
    ui.md('<div class="h2" style="font-size:16px;margin-bottom:4px">רשתות במאגר</div>' + "".join(
        f'<div class="chain-line">{ui.chain_mark(c, cname(c))}<span style="flex:1">{ui.esc(cname(c))}</span>'
        f'<span class="tiny num">{n:,} מחירים · עודכן {ui.esc((u or "—")[:10])}</span><span class="badge ok">✓</span></div>'
        for c, n, u in (info or [])))
    if _missing_names:
        ui.md("".join(f'<div class="chain-line"><span class="cm" style="background:#CBD5CF">?</span>'
                      f'<span style="flex:1">{ui.esc(n)}</span><span class="badge warn">לא במאגר</span></div>' for n in _missing_names))
    st.write("")
    with st.expander("📁 קבצי הנתונים — למה נבחר הקובץ הזה?", expanded=bool(_missing_names)):
        st.caption(f"קובץ שנטען: `{DB_PATH.name}` · גרסת קוד: `{APP_VERSION}`"
                   + (" · הנתונים נמשכו מהעדכון האוטומטי היומי (ענף data)" if REMOTE_USED else ""))
        st.dataframe(pd.DataFrame([{
            "קובץ": _pth.name, "רשתות": _ch, "שורות": _rw, "גודל (MB)": round(_sz / 1048576, 1),
            "עודכן": _dt.datetime.fromtimestamp(_pth.stat().st_mtime).strftime("%d/%m %H:%M"),
            "נבחר": "✅" if _pth == DB_PATH else ""} for _pth, (_ch, _rw, _sz) in DB_SCAN]),
            use_container_width=True, hide_index=True)
        st.caption("סדר העדיפויות: 1) הכי הרבה רשתות · 2) הכי הרבה שורות · 3) קובץ בשם prices.db · 4) הגודל.")
    with st.expander("🕒 השוואה מול גיטהאב — האם צריך Reboot?", expanded=bool(_need_reboot)):
        if not _gh_info:
            st.info("לא הצלחתי לקרוא את גיטהאב כרגע (אין רשת או הגבלת קצב). אפשר לנסות שוב בעוד דקה.")
        else:
            st.dataframe(pd.DataFrame(_rows_cmp), use_container_width=True, hide_index=True)
            if not _need_reboot:
                st.caption("✅ הקבצים שבסביבה תואמים את מה שבגיטהאב — אין צורך ב-Reboot.")
    c1, c2 = st.columns([1, 1.4], vertical_alignment="center")
    with c1:
        if st.button("🔄 לאתר מחדש את קובץ הנתונים", use_container_width=True,
                     help="סורק שוב את קובצי prices*.db, מנקה את הזיכרון הפנימי ובוחר את הקובץ עם הכי הרבה רשתות"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()
    with c2:
        st.caption(f"סריקה אחרונה: {datetime.now(_IL).strftime('%d/%m/%Y %H:%M:%S')}")


# ═══════════════════════════════════════════════════════
# 6) כותרת עליונה + ניווט
# ═══════════════════════════════════════════════════════
# ─── v8: טעינת הרשימה — קודם מקישור שיתוף (?list=), אחר כך מהדפדפן ───
if HAS_EXTRAS and not ss.get("_loaded_list"):
    _qp = st.query_params.get("list")
    if _qp:
        _got = xx.unpack_items(_qp)
        if _got:
            ss["items"] = _restore_items(_got)
            ss["_from_share"] = len(_got)
        ss["_loaded_list"] = True
        st.query_params.clear()
    elif HAS_JS:
        _stored = streamlit_js_eval(js_expressions="localStorage.getItem('sal_mashve_list') || ''", key="ls_get")
        if _stored is not None:                       # None = הרכיב עוד לא ענה
            if _stored and not ss["items"]:
                _got = xx.unpack_items(_stored)
                if _got:
                    ss["items"] = _restore_items(_got)
                    ss["_from_storage"] = len(_got)
            ss["_loaded_list"] = True
    else:
        ss["_loaded_list"] = True

ss.setdefault("opt_simple", False)
if ss.get("opt_simple"):
    ui.md('<style>html{font-size:19px}.st-key-sm_nav{display:none!important}.h-display{font-size:44px}'
          '[class*="st-key-grp_"],[class*="st-key-foot"],.st-key-card_breakdown,.st-key-card_index{display:none!important}'
          '.item-name{font-size:19px!important}.rank-name,.rank-price{font-size:18px!important}</style>')

with st.container(key="sm_top"):
    _l, _r = st.columns([3, 2], vertical_alignment="center")
    with _l:
        ui.md(ui.logo_html())
    with _r:
        with st.container(key="sm_status"):
            st.toggle("🔍 תצוגה פשוטה", key="opt_simple",
                      help="טקסט גדול, מסך אחד, רק מה שחשוב — נוח למבוגרים ולמסך קטן")
            _upd_txt = (_last_upd or "")[:10]
            if DATA_OK:
                _lbl = f"🟢 מחירים מעודכנים · {_upd_txt}" if _upd_txt else "🟢 מחירים מעודכנים"
            else:
                _lbl = "🟠 מצב הנתונים"
            if st.button(_lbl, key="btn_status"):
                data_status_dialog()

if not info:
    ui.md(ui.alert("אין נתונים במסד. הריצי את הסקרייפר: <code>python scraper.py --chains shufersal --limit 5</code>"))
    st.stop()

TABS = ["🛒 השוואת סל", "🥕 ירקות ופירות", "🔍 כל המחירים", "📈 מה השתנה", "🧾 הסלים שלי", "💬 איך זה עובד"]
if ss.get("nav") not in TABS:          # שדרוג מגרסה קודמת / תצוגה פשוטה
    ss["nav"] = TABS[0]
with st.container(key="sm_nav"):
    st.segmented_control("ניווט", TABS, default=TABS[0], key="nav",
                         label_visibility="collapsed", on_change=cb_nav_guard)
tab = TABS[0] if ss.get("opt_simple") else (ss.get("nav") or TABS[0])
ss["_last_nav"] = tab

if ss.get("_from_share"):
    ui.md(ui.alert(f"נפתחה רשימה משותפת · {ss.pop('_from_share')} מוצרים", "ok", "🔗"))
elif ss.get("_from_storage"):
    ui.md(ui.alert(f"הרשימה שלך מהפעם הקודמת חזרה · {ss.pop('_from_storage')} מוצרים", "ok", "👋"))

if not DATA_OK:
    _cA, _cB = st.columns([5, 1.2], vertical_alignment="center")
    with _cA:
        ui.md(ui.alert(("חסרות רשתות במאגר: " + ", ".join(_missing_names) + ". ") if _missing_names else
                       "בגיטהאב יש גרסה חדשה יותר של הנתונים — נדרש Reboot."))
    with _cB:
        if st.button("לפרטים", key="btn_status2", use_container_width=True):
            data_status_dialog()

# ─── בחירת רשתות (משותף לכל הלשוניות) ───
_available = [c for c in ALL_CHAINS if c in _found_keys] + [c for c in _found_keys if c not in ALL_CHAINS]
ss.setdefault("_chains", [c for c in _available if c in ONLINE_CHAINS] or _available)
_selected_chains = [c for c in ss["_chains"] if c in _found_keys]


def cb_chains():
    ss["_chains"] = list(ss.get("chains_w") or [])


def chains_card(key):
    with st.container(key=f"card_chains{key}"):
        a, b = st.columns([4, 1], vertical_alignment="center", gap="small")
        with a:
            ui.md(ui.chainbar_html(_selected_chains, CHAINS_HE, len(_available)))
        with b:
            with st.popover("שינוי"):
                ui.md('<div class="h2" style="font-size:16px">אילו רשתות להשוות?</div>'
                      '<div class="tiny" style="margin:2px 0 8px">ברירת המחדל: רשתות שמוכרות גם אונליין. צריך לפחות 2.</div>')
                ss["chains_w"] = list(_selected_chains)
                st.multiselect("רשתות", options=_available, key="chains_w", on_change=cb_chains,
                               format_func=cname, label_visibility="collapsed")
    if len(_selected_chains) < 2:
        ui.md(ui.alert("בחרי לפחות 2 רשתות כדי להשוות."))


QUICK = [
    ("🥛 סל בסיסי", "חלב, לחם, ביצים…", ["2 חלב 3%", "לחם אחיד", "ביצים", "גבינה צהובה", "קוטג'", "עגבניות"]),
    ("🍿 חטיפים", "במבה, ביסלי, גלידה", ["3 במבה", "2 ביסלי", "עוגיות", "גלידה", "שוקולד פרה"]),
    ("🍳 בישול לשבוע", "עוף, אורז, ירקות", ["עוף", "אורז", "שמן", "בצל", "מלפפונים"]),
    ("🧽 ניקיון", "כביסה, כלים, נייר", ["אבקת כביסה", "נייר טואלט", "סבון כלים", "אקונומיקה"]),
]

# ═══════════════════════════════════════════════════════
# 7) לשונית: השוואת סל
# ═══════════════════════════════════════════════════════
if tab == TABS[0]:
    ui.md(ui.page_head("מה קונים היום? נמצא לך את הסל הכי זול.",
                       "מוסיפים מוצרים — ורואים מיד באיזו רשת זה יוצא הכי משתלם. מחירים רשמיים, מתעדכנים כל בוקר.",
                       display=True))
    col_list, col_res = st.columns([1.05, 1], gap="large")

    # ─────────── עמודת הרשימה ───────────
    with col_list:
        chains_card("_b")
        with st.container(key="card_list"):
            n_items = len(ss["items"])
            with st.container(key="inl_head"):
                h1, h2 = st.columns([4, 1], vertical_alignment="center")
            with h1:
                ui.md(f'<div class="h2">הרשימה שלי{f" <span class=tiny>· {n_items} מוצרים</span>" if n_items else ""}</div>')
            with h2:
                if n_items:
                    st.button("ניקוי", key="btn_clear", on_click=cb_clear)

            if HAS_SEARCHBOX:
                # השלמה אוטומטית תוך כדי הקלדה (streamlit-searchbox)
                with st.container(key="adder_sb"):
                    st_searchbox(
                        search_products,
                        placeholder="מה להוסיף? למשל: 2 חלב, קוטג׳, 1.5 קילו עגבניות…",
                        key="adder_search",
                        clear_on_submit=True,
                        submit_function=cb_pick_suggestion,
                        debounce=250,
                        style_overrides=SEARCHBOX_STYLE,
                    )
                ui.md('<div class="tiny" style="margin:2px 0 4px">מתחילים להקליד ובוחרים מוצר מהרשימה — '
                      'או בוחרים בשורה הראשונה כדי להוסיף בדיוק מה שכתבת.</div>')
            else:
                with st.form("adder_form", clear_on_submit=False, border=False):
                    with st.container(key="adder"):
                        fa, fb = st.columns([5, 1.2], vertical_alignment="bottom")
                        with fa:
                            st.text_input("מוצר", key="adder_text", label_visibility="collapsed",
                                          placeholder="מה להוסיף? למשל: 2 חלב, קוטג׳, 1.5 קילו עגבניות…")
                        with fb:
                            st.form_submit_button("הוספה", type="primary", on_click=cb_add, use_container_width=True)

            if n_items:
                for it in ss["items"]:
                    with st.container(key=f"row_{it['uid']}"):
                        c0, c1, c2, c3, c4 = st.columns([10, 1, 1, 1, 1], vertical_alignment="center")
                        with c0:
                            if it.get("group"):
                                ui.md(ui.item_html(it["q"], _group_desc(it), "group"))
                            else:
                                ui.md(ui.item_html(it["q"], it["name"], it["status"]))
                        with c1:
                            st.button("+", key=f"p_{it['uid']}", on_click=cb_qty, args=(it["uid"], 1))
                        with c2:
                            ui.md(ui.qty_html(it["qty"], it["kg"]))
                        with c3:
                            st.button("−", key=f"m_{it['uid']}", on_click=cb_qty, args=(it["uid"], -1))
                        with c4:
                            st.button("✕", key=f"x_{it['uid']}", on_click=cb_remove, args=(it["uid"],), help="הסרה")
                        if HAS_FACETS:
                          with st.container(key=f"grp_{it['uid']}"):
                            if st.button("עריכת הסוגים" if it.get("group") else "כל הסוגים ← מותג, אחוז שומן, גודל",
                                         key=f"g_{it['uid']}", icon=":material/tune:",
                                         help="בחרי כמה מותגים / אחוזי שומן / גדלים — ובכל רשת יילקח הזול מביניהם"):
                                group_dialog(it["uid"])
                        if it["status"] == "unclear" and it["cands"] and not it.get("group"):
                            with st.container(key=f"chips_{it['uid']}"):
                                ccols = st.columns(len(it["cands"]))
                                for j, cd in enumerate(it["cands"]):
                                    with ccols[j]:
                                        _nm = cd["name"] if len(cd["name"]) <= 30 else cd["name"][:29] + "…"
                                        st.button(_nm, key=f"c_{it['uid']}_{j}", on_click=cb_pick, args=(it["uid"], cd),
                                                  help=f"{cd['name']} · {cd.get('brand', '')}")
            else:
                ui.md('<div class="tiny" style="margin:6px 0 2px;font-weight:600;color:var(--ink-2)">או התחילי מסל מוכן:</div>')
                with st.container(key="grid2_quick"):
                    qc = st.columns(4)
                    for i, (t, d, lines) in enumerate(QUICK):
                        with qc[i]:
                            st.button(f"{t}  \n{d}", key=f"q_{i}", on_click=cb_quick, args=(lines, t), use_container_width=True)

            with st.container(key="foot_list"):
                f1, f2, f3, f4 = st.columns(4)
                with f1:
                    with st.popover("📋 הדבקת רשימה"):
                        ui.md('<div class="tiny" style="margin-bottom:6px">מוצר בכל שורה. אפשר כמות לפני השם: ״3 במבה״, ״2 קילו עגבניות״, ״חלב × 2״.</div>')
                        st.text_area("רשימה", key="paste_text", height=180, label_visibility="collapsed",
                                     placeholder="2 חלב 3%\nלחם אחיד\nביצים\nקוטג'")
                        st.button("הוספה לסל", key="btn_paste", type="primary", on_click=cb_paste, use_container_width=True)
                with f2:
                    with st.popover("📄 העלאת קובץ"):
                        uploaded = st.file_uploader("CSV / TXT / Excel", type=["csv", "txt", "xlsx", "xls"], key="list_upload",
                                                    help="עמודה של שמות מוצרים, ואם יש גם עמודת כמות — היא תיקרא אוטומטית")
                        st.download_button("⬇️ תבנית רשימה", "מוצר,כמות\nחלב 3%,2\nלחם אחיד,1\nביצים L,12\nקוטג',1\n".encode("utf-8-sig"),
                                           file_name="תבנית_רשימת_קניות.csv", mime="text/csv", use_container_width=True)
                with f3:
                    _csv = "מוצר,כמות\n" + "\n".join(f"{x['q']},{format(x['qty'], 'g')}" for x in ss["items"]) + "\n"
                    st.download_button("💾 שמירת הרשימה", _csv.encode("utf-8-sig"), file_name="הרשימה_שלי.csv",
                                       mime="text/csv", disabled=not n_items)
                with f4:
                    _save_clicked = st.button("🧾 שמירה לסלים שלי", key="btn_hist", disabled=not n_items)
                if HAS_EXTRAS:
                    with st.popover("📷 סריקת ברקוד"):
                        ui.md('<div class="tiny" style="margin-bottom:6px">מצלמים את הברקוד של המוצר (או כותבים את המספר) — והוא נכנס לסל.</div>')
                        _bc_img = st.camera_input("צילום ברקוד", key="bc_cam", label_visibility="collapsed")
                        _bc_txt = st.text_input("או מספר ברקוד", key="bc_txt", placeholder="7290000000000")
                        _bc = None
                        if _bc_img is not None and ss.get("_bc_img_id") != getattr(_bc_img, "file_id", None):
                            ss["_bc_img_id"] = getattr(_bc_img, "file_id", None)
                            _bc = xx.decode_barcode(_bc_img.getvalue())
                            if not _bc:
                                ui.md(ui.alert("לא הצלחתי לקרוא את הברקוד. נסי לצלם מקרוב יותר, בתאורה טובה, או כתבי את המספר."))
                        if st.button("הוספה לפי מספר", key="bc_add", disabled=not str(_bc_txt).strip()):
                            _bc = "".join(ch for ch in str(_bc_txt) if ch.isdigit())
                        if _bc:
                            _conn = sqlite3.connect(DB_PATH)
                            _row = _conn.execute("SELECT MAX(name) FROM prices WHERE barcode = ?", (_bc,)).fetchone()
                            _conn.close()
                            if _row and _row[0]:
                                cb_add_barcode(_bc, str(_row[0]))
                                st.rerun()
                            else:
                                ui.md(ui.alert(f"הברקוד {ui.esc(_bc)} לא נמצא במאגר."))

            # קריאת קובץ שהועלה (פעם אחת לכל קובץ)
            if uploaded is not None and ss.get("_upl_id") != getattr(uploaded, "file_id", uploaded.name):
                ss["_upl_id"] = getattr(uploaded, "file_id", uploaded.name)
                try:
                    if uploaded.name.lower().endswith((".xlsx", ".xls")):
                        _df_up = pd.read_excel(uploaded)
                    else:
                        _raw = uploaded.getvalue().decode("utf-8-sig", errors="replace")
                        _lr = [l for l in _raw.splitlines() if l.strip()]
                        _df_up = pd.read_csv(_io.StringIO(_raw)) if _lr and "," in _lr[0] else pd.DataFrame({"מוצר": [l.strip() for l in _lr]})
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
                                pass
                        _parsed.append(f"{_pref}{_nm}".strip())
                    if _parsed:
                        add_lines(_parsed)
                        _toast(f"נטענו {len(_parsed)} פריטים מהקובץ")
                        st.rerun()
                    else:
                        ui.md(ui.alert("לא נמצאו פריטים בקובץ — ודאי שיש בו עמודה עם שמות מוצרים."))
                except Exception as _e:
                    ui.md(ui.alert(f"לא הצלחתי לקרוא את הקובץ: {ui.esc(str(_e))}"))

    # ─────────── עמודת התוצאות ───────────
    with col_res:
        if HAS_EXTRAS and not ss.get("opt_simple"):
            with st.container(key="opt_bar"):
                o1, o2, o3 = st.columns([1, 1, 1.1], vertical_alignment="center")
                with o1:
                    st.toggle("🏷️ עם מבצעים", value=True, key="opt_promos",
                              help="מחשב את המחיר אחרי מבצעי כמות (2 ב-20 וכו') שפתוחים לכל הלקוחות. בלי מועדונים וקופונים.")
                with o2:
                    st.toggle("🚚 קונה אונליין", value=False, key="opt_delivery",
                              help="מוסיף לכל רשת את דמי המשלוח שלה (ומשלוח חינם מעל סכום מסוים) — הזולה עד הדלת.")
                with o3:
                    with st.popover("⚙️ עוד אפשרויות", use_container_width=True):
                        st.toggle("להציע סל מפוצל ל-2 רשתות", value=True, key="opt_split")
                        st.number_input("רק כשחוסכים לפחות (₪)", min_value=0, max_value=500, value=20, step=5,
                                        key="opt_split_min")
                        st.divider()
                        st.number_input("כמה נפשות בבית? (0 = לא להציג)", min_value=0, max_value=15, value=0,
                                        key="opt_people")
                        st.selectbox("כל כמה זמן קונים את הסל הזה?", ["כל שבוע", "כל שבועיים", "פעם בחודש"],
                                     key="opt_freq")
                        st.divider()
                        ui.md('<div class="h2" style="font-size:15px;margin-bottom:4px">🚚 דמי משלוח לפי רשת</div>'
                              + "".join(
                                  f'<div class="dl-row">{ui.chain_mark(c, cname(c))}<span>{ui.esc(cname(c))}</span>'
                                  f'<b class="num">{ui.fmt(d["fee"])} ₪</b>'
                                  f'<span class="tiny">מינ׳ {d["min"]} ₪{" · " + ui.esc(d["note"]) if d.get("note") else ""}</span></div>'
                                  for c, d in xx.DELIVERY.items() if c in _available)
                              + f'<div class="tiny" style="margin-top:6px">{xx.DELIVERY_UPDATED} · '
                              + " · ".join(f'<a href="{u}" target="_blank">{ui.esc(t)}</a>' for t, u in xx.DELIVERY_SOURCES)
                              + '</div>')
        res = compute(ss["items"], _selected_chains) if len(_selected_chains) >= 2 else None
        if res and _save_clicked:
            save_history(res)
        if not res or not res["rows"] or not res["eligible"]:
            with st.container(key="card_empty"):
                ui.md(ui.empty_html("🧺", "הסל עדיין ריק",
                                    "הוסיפי מוצרים — וההשוואה בין הרשתות תופיע כאן מיד, בלי ללחוץ על שום כפתור."))
        else:
            tot, el = res["totals"], res["eligible"]
            any_missing = any(tot[c]["missing"] for c in el)
            mode = "all"
            if any_missing and res["common"]:
                mode = st.segmented_control("אופן ההשוואה", ["כל הסל", "השוואה הוגנת"], default="כל הסל",
                                            key="cmp_mode", label_visibility="collapsed") or "כל הסל"
                mode = "fair" if mode == "השוואה הוגנת" else "all"
            _dl = res.get("deliver")
            _el_d = [c for c in el if door_total(res, c, mode == "fair") is not None]   # באונליין: רק רשתות עם משלוח
            if _dl and not _el_d:
                _el_d = el
            if mode == "fair":
                vals = sorted(((c, door_total(res, c, True) or res["fair"][c], 0) for c in _el_d), key=lambda x: x[1])
                label = f"הזולה בהשוואה הוגנת · {len(res['common'])} פריטים משותפים"
            else:
                # קודם כל מי שכוללת את הכי הרבה מהסל, ורק אז לפי מחיר — כדי שרשת עם פריטים חסרים לא תנצח בטעות
                vals = sorted(((c, door_total(res, c) or tot[c]["total"], len(tot[c]["missing"])) for c in _el_d),
                              key=lambda x: (x[2], x[1]))
                _full = vals[0][2] == 0
                label = (f"הכי זול לסל שלך · {len(res['rows'])} פריטים" if _full else
                         f"הכי זול מבין הרשתות שיש בהן הכי הרבה מהסל · {len(res['rows']) - vals[0][2]} מתוך {len(res['rows'])} פריטים")
            if _dl:
                label += " · כולל משלוח"
            best, worst = vals[0], vals[-1]
            note_parts = []
            if mode == "all" and tot[best[0]]["missing"]:
                note_parts.append(f"שימי לב: ב{ui.esc(cname(best[0]))} חסר {ui.esc(', '.join(tot[best[0]]['missing']))}, "
                                  "ולכן המחיר נראה נמוך יותר. בחרי ״השוואה הוגנת״ למעלה.")
            if _dl:
                _fb = res["fees"].get(best[0]) or {}
                if _fb.get("fee") is not None:
                    _mn = (xx.DELIVERY.get(best[0]) or {}).get("min")
                    _nt = xx.delivery_note(best[0])
                    note_parts.append(("🚚 משלוח חינם" if _fb["fee"] == 0 else f"🚚 כולל {ui.fmt(_fb['fee'])} ₪ משלוח")
                                      + (f" · ⚠️ מתחת למינימום ההזמנה ({_mn} ₪) — חסרים עוד "
                                         f"{ui.fmt(_mn - tot[best[0]]['total'])} ₪" if _fb.get("under_min") and _mn else "")
                                      + (f" · {ui.esc(_nt)}" if _nt and "הערכה" not in _nt else ""))
            if tot[best[0]].get("promo_saved", 0) > 0.5 and mode == "all":
                note_parts.append(f"🏷️ כולל {ui.fmt(tot[best[0]]['promo_saved'])} ₪ הנחה ממבצעים")
            note = "<br>".join(note_parts) or None
            ui.md(ui.winner_html(best[0], cname(best[0]), best[1], label, worst[1] - best[1], cname(worst[0]), note))

            # ─── v8: לאדם / לחודש ───
            _ppl = int(ss.get("opt_people", 0) or 0)
            _per = ss.get("opt_freq", "כל שבוע")
            if _ppl > 0:
                _mult = {"כל שבוע": 4.33, "כל שבועיים": 2.17, "פעם בחודש": 1.0}.get(_per, 4.33)
                ui.md(f'<div class="per-row"><span>👤 לאדם: <b class="num">{ui.fmt(best[1] / _ppl)} ₪</b></span>'
                      f'<span>📅 לחודש ({_per}): <b class="num">{ui.fmt(best[1] * _mult)} ₪</b></span>'
                      f'<span>💰 חיסכון בשנה: <b class="num">{ui.fmt((worst[1] - best[1]) * _mult * 12)} ₪</b></span></div>')

            # ─── v8: סל מפוצל ───
            if HAS_EXTRAS and ss.get("opt_split", True) and mode == "all" and len(res["rows"]) >= 2:
                _sp = xx.split_basket([{"q": _qlabel(r["it"]), "cost": r["cost"]} for r in res["rows"]],
                                      [c for c in _selected_chains if c in el], best[1] if best[2] == 0 else None,
                                      delivery=bool(_dl))
                _thr = float(ss.get("opt_split_min", 20) or 20)
                if _sp and _sp.get("saving") is not None and _sp["saving"] >= _thr:
                    ui.md(ui.split_html(_sp, cname))

            # ─── כפתור: לקנות אונליין ברשת הזולה ───
            _online = [(c, t) for c, t, _m in vals if c in STORE_URLS]
            if _online:
                _bc, _bt = _online[0]
                _is_winner = _bc == best[0]
                with st.container(key="buy_online"):
                    st.link_button(f"🛒  לקנייה אונליין ב{cname(_bc)}", STORE_URLS[_bc], type="primary",
                                   use_container_width=True)
                    if _is_winner:
                        _sub = "נפתח בחלון חדש, באתר הרשת. את המוצרים מוסיפים לעגלה שם."
                    else:
                        _sub = (f"ל{ui.esc(cname(best[0]))} אין קנייה אונליין — {ui.esc(cname(_bc))} היא הזולה הבאה שמוכרת אונליין "
                                f"(<b class='num'>{ui.fmt(_bt)} ₪</b>, +{ui.fmt(_bt - best[1])} ₪).")
                    ui.md(f'<div class="buy-sub">{_sub}</div>')
                    _others = [(c, t) for c, t in _online[1:4]]
                    if _others:
                        with st.popover("או לקנות ברשת אחרת"):
                            ui.md('<div class="tiny" style="margin-bottom:8px">הרשתות הבאות בדירוג שמוכרות אונליין:</div>')
                            for c, t in _others:
                                st.link_button(f"{cname(c)} · {ui.fmt(t)} ₪ (+{ui.fmt(t - _bt)})", STORE_URLS[c],
                                               use_container_width=True)

            with st.container(key="card_rank"):
                sub = (f"רק {len(res['common'])} הפריטים שנמכרים בכל הרשתות — כך אף רשת לא מקבלת יתרון על פריט חסר."
                       if mode == "fair" else
                       "משוקלל לפי הכמויות. רשתות שכוללות את כל הסל מופיעות ראשונות.")
                ui.md(ui.rank_html([(c, cname(c), t, m) for c, t, m in vals], subtitle=sub))

            # אזהרות משקל
            _w = [r for r in res["rows"] if r["it"]["kg"]]
            _not_kg = [r["it"]["q"] for r in _w if not r["it"].get("group") and not any(k in str(r["unit"]) for k in ("גרם", "קילו", 'ק"ג', "קג"))]
            if _not_kg:
                ui.md(ui.alert("אלה זוהו כמוצר לפי יחידה/אריזה ולא לפי משקל: " + ui.esc(", ".join(_not_kg)) +
                               " — להשוואה לפי קילו עברי ללשונית 🥕 ירקות ופירות."))

            with st.container(key="card_breakdown"):
                ui.md(ui.breakdown_html(
                    [(r["it"]["q"], r["it"]["qty"], r["it"]["kg"],
                      (_group_desc(r["it"]) if r["it"].get("group") else r["it"]["name"]),
                      {c: (r["cost"][c] / r["it"]["qty"] if r["cost"].get(c) is not None and r["it"]["qty"] else None)
                       for c in _selected_chains},
                      r.get("picks"), r.get("deal"), r.get("hint")) for r in res["rows"]],
                    _selected_chains, CHAINS_HE))

            # ─── v8: מותג פרטי ───
            if HAS_EXTRAS and not ss.get("opt_simple"):
                _pl = private_label_swaps(res, best[0])
                if _pl:
                    with st.expander(f"🏷️ מה אם אעבור למותג הפרטי של {cname(best[0])}?"):
                        ui.md(ui.private_label_html(_pl))

            # ─── v8: המדד האישי ───
            if HAS_EXTRAS and HISTORY_DB and not ss.get("opt_simple"):
                _bi = _basket_index_cached(tuple((r["it"]["barcode"], r["it"]["qty"]) for r in res["rows"]
                                                 if r["it"].get("barcode") and not r["it"].get("group")),
                                           tuple(el), HISTORY_DB)
                if _bi:
                    with st.container(key="card_index"):
                        ui.md(ui.index_html(_bi, cname))

            # ─── v8: שיתוף ───
            share_block()

            if any_missing:
                with st.expander("⚖️ הוגנות ההשוואה — מי לא כללה איזה פריט"):
                    st.caption("רשת שלא מוכרת פריט מהסל שלך מקבלת יתרון לא הוגן, כי הפריט פשוט לא נספר לה.")
                    ui.md("".join(
                        f'<div class="miss-line"><b>{ui.esc(cname(c))}</b> — לא כללה {len(tot[c]["missing"])}: '
                        f'{ui.esc(" · ".join(tot[c]["missing"]))}</div>'
                        for c in sorted(el, key=lambda c: -len(tot[c]["missing"])) if tot[c]["missing"]))
                    if not res["common"]:
                        st.info("אין אפילו פריט אחד שכל הרשתות כללו — לכן אי אפשר להציג השוואה הוגנת מלאה.")

            _unid = [x["q"] for x in ss["items"] if not x["barcode"]]
            if _unid:
                st.caption("לא נכללו בחישוב (לא זוהו): " + " · ".join(_unid))
            ui.md(ui.float_html(cname(best[0]), best[1]))

# ═══════════════════════════════════════════════════════
# 8) לשונית: ירקות ופירות לפי קילו
# ═══════════════════════════════════════════════════════
elif tab == TABS[1]:
    ui.md(ui.page_head("ירקות ופירות, לפי קילו",
                       "המחיר הכי זול לק״ג בכל רשת. בוחרים כמה קילו — ומקבלים את הסל הירוק הזול."))
    chains_card("_p")

    def _cb_var(nm):
        ss.setdefault("prod_var", {})[nm] = list(ss.get(f"pv_{nm}") or [])

    @st.cache_data(show_spinner=False, ttl=3600)
    def _produce_all(chains_t, _db):
        return produce_prices(PRODUCE_ITEMS, chains=list(chains_t))

    @st.cache_data(show_spinner=False, ttl=3600)
    def _produce_cands(chains_t, _db):
        from comparator import GLOBAL_EXC, PRODUCE_BAND, per_kg
        return fx.produce_candidates(_db, PRODUCE_ITEMS, GLOBAL_EXC, PRODUCE_BAND, per_kg, chains=list(chains_t))

    ss.setdefault("prod_var", {})
    with st.spinner("מחשב מחיר לקילו בכל רשת…"):
        if HAS_FACETS:
            _pcands = _produce_cands(tuple(_selected_chains), str(DB_PATH))
            # הזול לקילו בכל רשת — מתוך הזנים שנבחרו (אם נבחרו)
            _pmap = {nm: fx.produce_best(_pcands.get(nm, {}), ss["prod_var"].get(nm)) for nm in _pcands}
        else:
            _pcands = {}
            _pmap = _produce_all(tuple(_selected_chains), str(DB_PATH))
    _pchains = [c for c in _available if c in _selected_chains and any(c in v for v in _pmap.values())]
    _names = [x["he"] for x in PRODUCE_ITEMS]
    _default_on = {"עגבניות", "מלפפונים", "בננות", "תפוחי אדמה", "בצל"}
    for nm in _names:
        ss.setdefault(f"prod_kg_{nm}", 1.0 if nm in _default_on else 0.0)

    if not _pchains:
        ui.md(ui.alert("לא נמצאו מוצרים לפי משקל ברשתות שנבחרו."))
    else:
        g_col, r_col = st.columns([1.6, 1], gap="large")
        with g_col:
            with st.container(key="grid2_produce"):
                # שורה אחת של עמודות שנשברת אוטומטית (3 בטור במחשב, 2 בטור בטלפון) — ראו CSS grid2_produce
                cols = st.columns(len(_names))
                i0 = 0
                if True:
                    for j, nm in enumerate(_names):
                        have = {c: v[0] for c, v in _pmap.get(nm, {}).items() if c in _pchains}
                        bc = min(have, key=have.get) if have else None
                        on = float(ss.get(f"prod_kg_{nm}", 0) or 0) > 0
                        with cols[j]:
                            with st.container(key=f"pcard{'on' if on else ''}_{i0 + j}"):
                                _vsel = ss["prod_var"].get(nm) or []
                                ui.md(ui.produce_card_html(nm, have.get(bc) if bc else None, bc, cname(bc) if bc else "", _vsel))
                                _vopts = fx.produce_varieties(_pcands.get(nm, {})) if HAS_FACETS else []
                                if len(_vopts) >= 1:
                                    with st.popover("בחירת זנים" if not _vsel else f"זנים ({len(_vsel)})",
                                                    use_container_width=True):
                                        ui.md(f'<div class="h2" style="font-size:15px">אילו זנים של {ui.esc(nm)}?</div>'
                                              '<div class="tiny" style="margin:2px 0 8px">בכל רשת נלקח הזול לק״ג מבין הזנים שבחרת. בלי בחירה = כל הזנים.</div>')
                                        st.pills("זנים", _vopts, selection_mode="multi", key=f"pv_{nm}",
                                                 default=[v for v in _vsel if v in _vopts], label_visibility="collapsed",
                                                 on_change=_cb_var, args=(nm,))
                                st.number_input(f"{nm} (ק\"ג)", min_value=0.0, step=0.5, key=f"prod_kg_{nm}", format="%.1f",
                                                label_visibility="collapsed", disabled=not have)

        _pick = [nm for nm in _names if float(ss.get(f"prod_kg_{nm}", 0) or 0) > 0]
        _totals = {}
        for c in _pchains:
            s, cnt, miss = 0.0, 0, []
            for nm in _pick:
                v = _pmap.get(nm, {}).get(c)
                if v is None:
                    miss.append(nm)
                else:
                    s += v[0] * float(ss[f"prod_kg_{nm}"])
                    cnt += 1
            _totals[c] = {"total": round(s, 2), "items": cnt, "missing": miss}
        _sorted = sorted(_totals.items(), key=lambda kv: kv[1]["total"])

        with r_col:
            if not _pick or _sorted[0][1]["total"] <= 0 and _sorted[-1][1]["total"] <= 0:
                with st.container(key="card_pempty"):
                    ui.md(ui.empty_html("🥕", "הוסיפי ירקות לסל", "כתבי כמה קילו ליד כל ירק או פרי."))
            else:
                # קודם הרשתות שיש בהן הכי הרבה מהסל, ורק אז לפי מחיר
                _el = sorted([(c, v) for c, v in _sorted if v["items"] > 0],
                             key=lambda cv: (len(cv[1]["missing"]), cv[1]["total"]))
                kg_sum = sum(float(ss[f"prod_kg_{nm}"]) for nm in _pick)
                (bc_, bv), (wc_, wv) = _el[0], _el[-1]
                ui.md(ui.winner_html(bc_, cname(bc_), bv["total"],
                                     f"הסל הירוק שלך · {len(_pick)} פריטים · {format(kg_sum, 'g')} ק״ג",
                                     wv["total"] - bv["total"], cname(wc_),
                                     (f"ב{ui.esc(cname(bc_))} אין מחיר לפי משקל עבור: {ui.esc(', '.join(bv['missing']))}"
                                      if bv["missing"] else None)))
                _pon = [c for c, _v in _el if c in STORE_URLS]
                if _pon:
                    with st.container(key="buy_online_p"):
                        st.link_button(f"🛒  לקנייה אונליין ב{cname(_pon[0])}", STORE_URLS[_pon[0]], type="primary",
                                       use_container_width=True)
                        ui.md('<div class="buy-sub">נפתח בחלון חדש, באתר הרשת.'
                              + ("" if _pon[0] == bc_ else f" ל{ui.esc(cname(bc_))} אין קנייה אונליין, לכן מוצגת הזולה הבאה.")
                              + '</div>')
                with st.container(key="card_prank"):
                    ui.md(ui.rank_html([(c, cname(c), v["total"], len(v["missing"])) for c, v in _el]))
                _rows_tot = [{"רשת": cname(c), 'סה"כ לסל (₪)': v["total"], "פריטים שנמצאו": v["items"],
                              "חסרים": len(v["missing"])} for c, v in _sorted]

        st.write("")
        with st.expander("📊 טבלת מחיר לקילו בכל הרשתות"):
            ui.md(ui.matrix_html(_names, _pchains, CHAINS_HE, _pmap))
            _df_p = pd.DataFrame([{"ירק / פרי": nm, **{cname(c): (_pmap.get(nm, {}).get(c) or (None,))[0] for c in _pchains}}
                                  for nm in _names])
            st.download_button("⬇️ הורדת טבלת המחירים לקילו (CSV)", _df_p.to_csv(index=False).encode("utf-8-sig"),
                               file_name="ירקות_ופירות_לפי_קילו.csv", mime="text/csv")
        with st.expander("🔍 איזה מוצר נבחר לכל רשת (ולמה המחיר הזה)"):
            _src = [{"ירק / פרי": nm, "רשת": cname(c), "המוצר שנבחר": v[1], "₪ לקילו": v[0]}
                    for nm in _names for c, v in _pmap.get(nm, {}).items() if c in _pchains]
            if _src:
                st.dataframe(pd.DataFrame(_src).sort_values(["ירק / פרי", "₪ לקילו"]),
                             use_container_width=True, hide_index=True, height=320)
            st.caption("הבחירה: המוצר הזול ביותר לקילו בכל רשת מבין המוצרים שנמכרים לפי משקל (ק״ג / קילוגרם).")

# ═══════════════════════════════════════════════════════
# 9) לשונית: כל המחירים (חיפוש)
# ═══════════════════════════════════════════════════════
elif tab == TABS[2]:
    ui.md(ui.page_head("כל המחירים במאגר", "חפשי מוצר לפי שם או ברקוד, ובדקי כמה הוא עולה בכל רשת."))
    chains_card("_s")
    CHAIN_KEYS = [c for c in _available if c in _selected_chains]
    CHAIN_COLS = [cname(c) for c in CHAIN_KEYS]

    s1, s2, s3 = st.columns([2.4, 1, 1], vertical_alignment="bottom")
    q = s1.text_input("חיפוש", "", key="data_q", placeholder="🔍  חפשי מוצר, מותג או ברקוד…", label_visibility="collapsed")
    only_shared = s2.checkbox("רק מוצרים ביותר מרשת אחת", value=True, key="data_shared")
    rows_limit = s3.selectbox("כמה שורות", [100, 200, 500, 1000, 5000], index=1, key="data_limit", label_visibility="collapsed",
                              format_func=lambda n: f"עד {n:,} שורות")

    where, params = [], []
    if q.strip():
        where.append("(name LIKE ? OR barcode LIKE ?)")
        params += [f"%{q.strip()}%", f"%{q.strip()}%"]
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    min_chains = 2 if only_shared else 1
    price_cols_sql = ",\n".join(
        '               MAX(CASE WHEN chain = \'{c}\' THEN price END) AS "{h}"'.format(c=c, h=cname(c)) for c in CHAIN_KEYS)

    if not CHAIN_KEYS:
        ui.md(ui.alert("בחרי רשתות להצגה."))
    else:
        sql = f"""
            SELECT barcode, MAX(name) AS "מוצר", MAX(brand) AS "מותג",
{price_cols_sql},
                   COUNT(DISTINCT chain) AS "מספר רשתות"
            FROM prices {where_sql}
            GROUP BY barcode HAVING COUNT(DISTINCT chain) >= {int(min_chains)}
            ORDER BY "מספר רשתות" DESC, "מוצר" LIMIT {int(rows_limit)}"""
        _conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(sql, _conn, params=params)
        _conn.close()

        left, right = st.columns([1.7, 1], gap="large")
        with left:
            with st.container(key="card_search"):
                if df.empty:
                    ui.md(ui.empty_html("🔍", "לא נמצא", "נסי מילה אחרת, או חלק מהברקוד."))
                else:
                    df["המחיר הזול"] = df[CHAIN_COLS].min(axis=1).round(2)
                    df["הרשת הזולה"] = df[CHAIN_COLS].idxmin(axis=1)
                    ui.md(f'<div class="sec-head"><div class="h2">{"תוצאות" if q.strip() else "מוצרים נפוצים"}</div>'
                          f'<span class="tiny">{len(df):,} מוצרים</span></div>')
                    _rev = {cname(c): c for c in CHAIN_KEYS}
                    for i, r in df.head(25).iterrows():
                        ps = sorted(((_rev[h], float(r[h])) for h in CHAIN_COLS if pd.notna(r[h])), key=lambda x: x[1])
                        if not ps:
                            continue
                        with st.container(key=f"srow_{i}"):
                            a, b = st.columns([12, 1], vertical_alignment="center")
                            with a:
                                ui.md(ui.search_row_html(r["מוצר"], r["מותג"], len(ps), ps, CHAINS_HE))
                            with b:
                                st.button("＋", key=f"add_{r['barcode']}", help="הוספה לסל",
                                          on_click=cb_add_barcode, args=(r["barcode"], str(r["מוצר"])))
                    if len(df) > 25:
                        st.caption(f"מוצגים 25 הראשונים — הטבלה המלאה ({len(df):,}) למטה.")
            if not df.empty:
                with st.expander(f"🗂️ הטבלה המלאה ({len(df):,} מוצרים) + הורדה לאקסל"):
                    st.dataframe(df, use_container_width=True, hide_index=True, height=480)
                    st.download_button("⬇️ הורדת הטבלה (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                                       file_name="prices_export.csv", mime="text/csv")

        with right:
            sql_all = f"""SELECT barcode,
{price_cols_sql},
                   COUNT(DISTINCT chain) AS n_chains
            FROM prices {where_sql}
            GROUP BY barcode HAVING COUNT(DISTINCT chain) >= {int(min_chains)} LIMIT 60000"""
            _c2 = sqlite3.connect(DB_PATH)
            df_all = pd.read_sql_query(sql_all, _c2, params=params)
            _c2.close()
            with st.container(key="card_wins"):
                ui.md('<div class="h2">מי הזולה ביותר?</div>'
                      '<div class="tiny" style="margin:2px 0 12px">באחוז כמה מהמוצרים כל רשת מציעה את המחיר הנמוך ביותר</div>')
                if df_all.empty or len(CHAIN_COLS) < 2:
                    st.caption("אין נתונים לתרשים בסינון הזה.")
                else:
                    counts = df_all[CHAIN_COLS].idxmin(axis=1).dropna().value_counts()
                    ui.md(ui.hbars_html([(k, int(v)) for k, v in counts.items()], int(counts.sum())))
                    ui.md(f'<div class="tiny" style="margin-top:12px;line-height:1.6">👑 <b>{ui.esc(counts.index[0])}</b> זולה ב-'
                          f'{int(counts.iloc[0]):,} מוצרים מתוך {int(counts.sum()):,}. '
                          'זו ספירה לפי מוצר בודד — לא בהכרח הסל הכולל הזול.</div>')

# ═══════════════════════════════════════════════════════
# 9ב) לשונית: מה השתנה — שרינקפלציה, עליות וירידות מחיר
# ═══════════════════════════════════════════════════════
elif tab == TABS[3]:
    ui.md(ui.page_head("מה השתנה במחירים",
                       "מוצרים שהאריזה שלהם קטנה והמחיר נשאר (שרינקפלציה), ומה התייקר או הוזל בתקופה האחרונה."))
    chains_card("_c")
    if not HAS_EXTRAS or not HAS_FACETS:
        ui.md(ui.alert("הלשונית הזו דורשת את הקבצים extras.py ו-facets.py בריפו."))
    else:
        _days = st.segmented_control("תקופה", [7, 30, 90], default=30, key="chg_days",
                                     format_func=lambda d: f"{d} ימים אחרונים", label_visibility="collapsed") or 30

        @st.cache_data(show_spinner=False, ttl=1800)
        def _changes_cached(days, chains_t, _hdb):
            return xx.changes(_hdb, fx.size_of, days, list(chains_t))

        _ch = _changes_cached(int(_days), tuple(_selected_chains), HISTORY_DB) if HISTORY_DB else None
        if not _ch or _ch["days"] < 2:
            _n = (_ch or {}).get("days", 0)
            with st.container(key="card_chg_empty"):
                ui.md(ui.empty_html("📈", "אוספים נתונים",
                                    f"הסריקה היומית שומרת תמונת מצב כל בוקר. נשמרו עד עכשיו {_n} ימים — "
                                    "מהיום השני יופיעו כאן שינויים, ואחרי שבוע התמונה תהיה מלאה."))
        else:
            ui.md(ui.changes_summary_html(len(_ch["shrink"]), len(_ch["up"]), len(_ch["down"]), _ch["since"]))
            _t1, _t2, _t3 = st.tabs([f"🔍 שרינקפלציה ({len(_ch['shrink'])})",
                                     f"📈 התייקרו ({len(_ch['up'])})", f"📉 הוזלו ({len(_ch['down'])})"])
            with _t1:
                ui.md('<div class="tiny" style="margin:4px 0 10px">האריזה קטנה, והמחיר נשאר או עלה — בפועל התייקרות סמויה. '
                      'האחוז הוא השינוי במחיר ליחידת מידה.</div>')
                ui.md(ui.changes_list_html(_ch["shrink"][:60], cname, "shrink") or ui.empty_html("✅", "לא נמצאה שרינקפלציה", "בתקופה הזו."))
            with _t2:
                ui.md(ui.changes_list_html(_ch["up"][:60], cname, "up") or ui.empty_html("✅", "אין עליות", "בתקופה הזו."))
            with _t3:
                ui.md(ui.changes_list_html(_ch["down"][:60], cname, "down") or ui.empty_html("—", "אין ירידות", "בתקופה הזו."))

# ═══════════════════════════════════════════════════════
# 10) לשונית: הסלים שלי
# ═══════════════════════════════════════════════════════
elif tab == TABS[4]:
    ui.md(ui.page_head("הסלים שלי", "ההשוואות ששמרת נשמרות רק אצלך, בחלון הדפדפן הזה."))
    hist = ss["history"]
    if not hist:
        with st.container(key="card_hempty"):
            ui.md(ui.empty_html("🧾", "עוד אין סלים שמורים", "אחרי השוואה, לחצי ״🧾 שמירה לסלים שלי״ מתחת לרשימה."))
    else:
        tot_sv = sum(h["savings"] for h in hist)
        ui.md(f'<div class="hist-hero"><span style="font-size:40px">💰</span><div>'
              f'<div class="tiny" style="color:var(--amber-ink);font-weight:600">חסכת עד עכשיו</div>'
              f'<div class="big num">{ui.fmt(tot_sv)} ₪</div><div class="tiny" style="margin-top:4px">ב-{len(hist)} השוואות</div></div></div>')
        with st.container(key="card_hist"):
            for i, h in enumerate(hist):
                with st.container(key=f"hrow_{i}"):
                    a, b = st.columns([5, 1.3], vertical_alignment="center")
                    with a:
                        ui.md(ui.hist_html(h["chain"], cname(h["chain"]), h["total"], h["date"], h["items"], h["savings"]))
                    with b:
                        st.button("שוב את הסל הזה", key=f"reuse_{i}", on_click=cb_reuse, args=(i,), use_container_width=True)

# ═══════════════════════════════════════════════════════
# 11) לשונית: איך זה עובד
# ═══════════════════════════════════════════════════════
else:
    ui.md(ui.page_head("איך זה עובד", "שלושה צעדים, בלי הרשמה."))
    ui.md(ui.help_html())

ui.md('<div class="footer">סל משווה · מחירים מקבצי שקיפות המחירים הרשמיים של הרשתות · חינם ובלי הרשמה · בנוי בישראל</div>')

# טעינה מוקדמת של קטלוג ההשלמה (אחרי שהעמוד כבר הוצג) — כך ההקלדה הראשונה מהירה
if HAS_SEARCHBOX:
    _catalog(str(DB_PATH))

# v8: שמירת הרשימה בדפדפן — בסוף כל ריצה, כדי שתכלול את כל השינויים
if ss.get("_loaded_list"):
    _persist_list()
