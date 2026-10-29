"""
extras.py – יכולות מתקדמות של "סל משווה" (v8):
מבצעים · דמי משלוח · סל מפוצל · מותג פרטי · היסטוריית מחירים ושרינקפלציה ·
מדד הסל האישי · סריקת ברקוד · שמירה בדפדפן · קישור שיתוף.

אין כאן ממשק — רק לוגיקה. כל פונקציה עובדת גם כשהטבלאות החדשות עוד לא קיימות במסד
(למשל לפני הסריקה הראשונה עם הסקרייפר החדש) ומחזירה תוצאה ריקה.
"""
import base64
import json
import math
import sqlite3
import zlib
from datetime import date, timedelta
from functools import lru_cache

# ═══════════════════════════════════════════════════════
# דמי משלוח לפי כתבות צרכנות עדכניות (ynet, ערוץ 14). לעדכן כשמשתנה.
# מבנה: דמי משלוח ₪ · (סכום מעליו המשלוח מוזל, המחיר המוזל) או None · מינימום הזמנה ₪ · הערה
#   שופרסל  — 35.90 (ynet: "גם שופרסל מייקרת את המשלוח")
#   רמי לוי — 35.90 (ynet: "רמי לוי אונליין מעלה את דמי המשלוח ל-35.90")
#   קרפור, טיב טעם — 29.90; טיב טעם: משלוח חינם מעל 750 ₪ (בתוקף עד 31/12/2027)
#   קשת טעמים — 29.90, ומעל 750 ₪ רק 14.90
#   חצי חינם — מינימום הזמנה 500 ₪ ; יוחננוף — איסוף עצמי בלבד (15 ₪)
#   ברוב הרשתות מינימום ההזמנה 250–350 ₪
# ═══════════════════════════════════════════════════════
DELIVERY = {
    "shufersal":   {"fee": 35.90, "tier": None,          "min": 250, "note": ""},
    "rami-levy":   {"fee": 35.90, "tier": None,          "min": 250, "note": "חברי מועדון האשראי של הרשת משלמים פחות"},
    "carrefour":   {"fee": 29.90, "tier": None,          "min": 250, "note": ""},
    "tiv-taam":    {"fee": 29.90, "tier": (750, 0.0),    "min": 300, "note": "משלוח חינם מעל 750 ₪"},
    "keshet":      {"fee": 29.90, "tier": (750, 14.90),  "min": 300, "note": "מעל 750 ₪ המשלוח 14.90"},
    "hazi-hinam":  {"fee": 35.90, "tier": None,          "min": 500, "note": "מינימום הזמנה 500 ₪"},
    "yohananof":   {"fee": 15.00, "tier": None,          "min": 250, "note": "איסוף עצמי בלבד — 15 ₪"},
    "freshmarket": {"fee": 29.90, "tier": None,          "min": 300, "note": "הערכה"},
    "victory":     {"fee": 35.90, "tier": None,          "min": 250, "note": "לפעמים משלוח חינם בימי ראשון"},
}
DELIVERY_UPDATED = "לפי כתבות ynet וערוץ 14 · עודכן 27/09/2026"
DELIVERY_SOURCES = [
    ("ynet — שופרסל מייקרת את המשלוח", "https://www.ynet.co.il/economy/article/rjycerl7me"),
    ("ynet — רמי לוי מעלה את דמי המשלוח", "https://www.ynet.co.il/economy/article/hkx4wmuc11g"),
    ("ערוץ 14 — הרשת הזולה לקניות אונליין", "https://www.c14.co.il/article/1633775"),
]


def delivery_for(chain, basket_total):
    """(דמי משלוח, מתחת למינימום?) — None אם לרשת אין משלוח."""
    d = DELIVERY.get(chain)
    if not d:
        return None, False
    fee = d["fee"]
    if d.get("tier") and basket_total >= d["tier"][0]:
        fee = d["tier"][1]
    return fee, (d.get("min") is not None and basket_total < d["min"])


# ═══════════════════════════════════════════════════════
# עוזר עגלה — קישור חיפוש ישיר לכל מוצר באתר הרשת
# VERIFIED = נבדק שהקישור פותח תוצאות חיפוש (28/09/2026). השאר — לפי מבנה האתר, לא נבדק (האתר חוסם בדיקה אוטומטית)
# ═══════════════════════════════════════════════════════
SEARCH_URLS = {
    "shufersal":   "https://www.shufersal.co.il/online/he/search?text={q}",
    "tiv-taam":    "https://www.tivtaam.co.il/search/{q}",
    "keshet":      "https://www.keshet-teamim.co.il/search/{q}",
    "freshmarket": "https://www.freshmarket.co.il/search/{q}",
    "carrefour":   "https://www.carrefour.co.il/search/{q}",
    "rami-levy":   "https://www.rami-levy.co.il/he/online/search?q={q}",
    "yohananof":   "https://yochananof.co.il/search?q={q}",
    "hazi-hinam":  "https://shop.hazi-hinam.co.il/search?q={q}",
}
SEARCH_VERIFIED = {"shufersal", "tiv-taam", "keshet", "freshmarket"}

_UNIT_RE = None


def search_term(name):
    """שם מוצר → מילת חיפוש קצרה שהאתרים מבינים: בלי גדלים, אחוזים ומרכאות, עד 4 מילים."""
    import re
    global _UNIT_RE
    if _UNIT_RE is None:
        _UNIT_RE = re.compile(r"(\d+([.,]\d+)?\s*(%|גרם|גר'?|ג'?|ק\"?ג|ליטר|ל'?|מ\"?ל|יח'?|יחידות)?)|[\"'׳״*+×/]")
    t = _UNIT_RE.sub(" ", str(name or ""))
    words = [w for w in t.split() if len(w) > 1][:4]
    return " ".join(words) or str(name or "")


def search_url(chain, name):
    import urllib.parse
    tpl = SEARCH_URLS.get(chain)
    if not tpl:
        return None
    return tpl.format(q=urllib.parse.quote(search_term(name)))


def delivery_note(chain):
    d = DELIVERY.get(chain) or {}
    return d.get("note") or ""


# ═══════════════════════════════════════════════════════
# מותג פרטי
# ═══════════════════════════════════════════════════════
PRIVATE_LABEL = {
    "shufersal": ["שופרסל"], "rami-levy": ["רמי לוי", "רמילוי"], "yohananof": ["יוחננוף"],
    "osher-ad": ["אושר עד"], "tiv-taam": ["טיב טעם"], "carrefour": ["קרפור"],
    "hazi-hinam": ["חצי חינם"], "keshet": ["קשת טעמים"], "freshmarket": ["פרשמרקט"],
    "victory": ["ויקטורי"], "paz": ["yellow", "יילו"],
}


def _norm(s):
    return str(s or "").replace('"', "").replace("'", "").replace("׳", "").replace("״", "").lower()


def is_private_label(chain, name, brand):
    t = _norm(name) + " " + _norm(brand)
    return any(_norm(k) in t for k in PRIVATE_LABEL.get(chain, []))


# ═══════════════════════════════════════════════════════
# עזרי מסד
# ═══════════════════════════════════════════════════════
def has_table(db, table):
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        ok = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None
        c.close()
        return ok
    except Exception:
        return False


# ═══════════════════════════════════════════════════════
# מבצעים
# ═══════════════════════════════════════════════════════
def promos_for(db, barcodes, chains):
    """{(barcode, chain): [(min_qty, price_for_min_qty, descr, ends), ...]} — רק מבצעים פתוחים לכלל הלקוחות."""
    if not barcodes or not has_table(db, "promos"):
        return {}
    today = date.today().isoformat()
    out = {}
    conn = sqlite3.connect(db)
    bcs = list(barcodes)
    for i in range(0, len(bcs), 800):
        part = bcs[i:i + 800]
        q = (f"SELECT barcode, chain, min_qty, price, descr, ends FROM promos "
             f"WHERE barcode IN ({','.join('?' * len(part))}) AND (ends IS NULL OR ends = '' OR ends >= ?)")
        for bc, ch, mq, pr, ds, en in conn.execute(q, part + [today]):
            if ch in chains and pr and pr > 0 and mq and mq > 0:
                out.setdefault((bc, ch), []).append((float(mq), float(pr), ds or "", en or ""))
    conn.close()
    return out


def line_cost(unit_price, qty, promos):
    """עלות שורה (כמות × מחיר) עם המבצע המשתלם ביותר. מחזיר (עלות, תיאור מבצע או None)."""
    if unit_price is None:
        return None, None
    base = unit_price * qty
    best, best_d = base, None
    for mq, pr, ds, _en in promos or []:
        if pr / mq >= unit_price - 0.005:          # לא באמת הנחה
            continue
        if qty + 1e-9 < mq:                         # לא הגיעו לכמות המבצע
            continue
        sets = math.floor(qty / mq + 1e-9)
        cost = sets * pr + (qty - sets * mq) * unit_price
        if cost < best - 0.005:
            best, best_d = cost, (ds or f"{mq:g} ב-{pr:g}")
    return round(best, 2), best_d


def promo_hint(unit_price, qty, promos):
    """מבצע שעוד לא מנוצל: 'עוד 1 ותקבלי 2 ב-20' — מחזיר טקסט או None."""
    for mq, pr, ds, _en in sorted(promos or [], key=lambda x: x[0]):
        if pr / mq < unit_price - 0.005 and qty + 1e-9 < mq:
            need = mq - qty
            return f"עוד {need:g} ← {ds or f'{mq:g} ב-{pr:g}'} (חוסכת {unit_price * mq - pr:.2f} ₪)"
    return None


# ═══════════════════════════════════════════════════════
# סל מפוצל (2 רשתות)
# ═══════════════════════════════════════════════════════
def split_basket(rows, chains, single_best_total, delivery=False, max_chains=7):
    """
    rows: [{'q': str, 'cost': {chain: line_cost|None}}]
    מחפש את זוג הרשתות שבו הסל המלא (כל הפריטים) הכי זול.
    מחזיר dict או None: {a, b, total, a_items, b_items, a_sum, b_sum, fees}
    """
    if len(rows) < 2:
        return None
    # רק רשתות שיש בהן לפחות חצי מהסל
    cand = [c for c in chains if sum(r["cost"].get(c) is not None for r in rows) >= max(1, len(rows) // 2)]
    cand = sorted(cand, key=lambda c: sum(r["cost"].get(c) or 0 for r in rows))[:max_chains]
    best = None
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            ta, tb, ia, ib, ok = 0.0, 0.0, [], [], True
            for r in rows:
                ca, cb = r["cost"].get(a), r["cost"].get(b)
                if ca is None and cb is None:
                    ok = False
                    break
                if cb is None or (ca is not None and ca <= cb):
                    ta += ca
                    ia.append(r["q"])
                else:
                    tb += cb
                    ib.append(r["q"])
            if not ok or not ia or not ib:
                continue
            fees = 0.0
            if delivery:
                fa, _ = delivery_for(a, ta)
                fb, _ = delivery_for(b, tb)
                if fa is None or fb is None:
                    continue
                fees = fa + fb
            total = round(ta + tb + fees, 2)
            if best is None or total < best["total"]:
                best = {"a": a, "b": b, "total": total, "a_items": ia, "b_items": ib,
                        "a_sum": round(ta, 2), "b_sum": round(tb, 2), "fees": round(fees, 2)}
    if best and single_best_total is not None:
        best["saving"] = round(single_best_total - best["total"], 2)
        # שהרשת "הגדולה" תהיה a
        if len(best["b_items"]) > len(best["a_items"]):
            best["a"], best["b"] = best["b"], best["a"]
            best["a_items"], best["b_items"] = best["b_items"], best["a_items"]
            best["a_sum"], best["b_sum"] = best["b_sum"], best["a_sum"]
    return best


# ═══════════════════════════════════════════════════════
# היסטוריית מחירים · שרינקפלציה · מדד אישי   (קובץ נפרד: history.db)
# price_history(chain, barcode, day, price, qty) — שורה רק כשמשהו השתנה
# product_names(barcode, day, name, unit)        — שורה רק כשהשם השתנה
# ═══════════════════════════════════════════════════════
def history_days(hdb):
    if not hdb or not has_table(hdb, "price_history"):
        return []
    c = sqlite3.connect(hdb)
    d = [r[0] for r in c.execute("SELECT DISTINCT day FROM price_history ORDER BY day")]
    c.close()
    return d


def price_series(hdb, barcode, chains=None):
    """{chain: [(day, price)]} — להצגת גרף מחיר של מוצר."""
    if not hdb or not has_table(hdb, "price_history"):
        return {}
    c = sqlite3.connect(hdb)
    out = {}
    for ch, day, pr in c.execute("SELECT chain, day, price FROM price_history WHERE barcode=? ORDER BY day", (barcode,)):
        if chains is None or ch in chains:
            out.setdefault(ch, []).append((day, pr))
    c.close()
    return out


def changes(hdb, size_of, days=30, chains=None, limit=400):
    """
    שינויים מהתקופה האחרונה: עליות, ירידות ושרינקפלציה (האריזה קטנה והמחיר ליחידה עלה).
    size_of(name, unit, qty) -> (amt, dim) | None
    """
    empty = {"up": [], "down": [], "shrink": [], "since": None, "days": 0}
    hd = history_days(hdb)
    if len(hd) < 2:
        return dict(empty, days=len(hd))
    since = (date.fromisoformat(hd[-1]) - timedelta(days=days)).isoformat()
    c = sqlite3.connect(hdb)
    rows = c.execute("""
        WITH cur AS (SELECT * FROM price_history WHERE day > ?),
             prev AS (
                SELECT h.chain, h.barcode, h.day, h.price, h.qty,
                       ROW_NUMBER() OVER (PARTITION BY h.chain, h.barcode ORDER BY h.day DESC) AS rn
                FROM price_history h JOIN cur ON cur.chain = h.chain AND cur.barcode = h.barcode AND h.day < cur.day)
        SELECT cur.chain, cur.barcode, cur.day, cur.price, cur.qty, prev.day, prev.price, prev.qty,
               (SELECT name FROM product_names n WHERE n.barcode = cur.barcode AND n.day <= cur.day ORDER BY n.day DESC LIMIT 1),
               (SELECT unit FROM product_names n WHERE n.barcode = cur.barcode AND n.day <= cur.day ORDER BY n.day DESC LIMIT 1),
               (SELECT name FROM product_names n WHERE n.barcode = cur.barcode AND n.day <= prev.day ORDER BY n.day DESC LIMIT 1),
               (SELECT unit FROM product_names n WHERE n.barcode = cur.barcode AND n.day <= prev.day ORDER BY n.day DESC LIMIT 1)
        FROM cur JOIN prev ON prev.chain = cur.chain AND prev.barcode = cur.barcode AND prev.rn = 1
    """, (since,)).fetchall()
    c.close()
    up, down, shrink = [], [], []
    for ch, bc, d1, p1, q1, d0, p0, q0, n1, u1, n0, u0 in rows:
        if chains and ch not in chains:
            continue
        s1, s0 = size_of(n1, u1, q1), size_of(n0, u0, q0)
        rec = {"chain": ch, "barcode": bc, "name": n1 or n0 or bc, "day": d1, "prev_day": d0, "old": p0, "new": p1,
               "old_amt": s0[0] if s0 else None, "new_amt": s1[0] if s1 else None,
               "dim": (s1 or s0 or (None, None))[1]}
        if s0 and s1 and s1[1] == s0[1] and s1[0] < s0[0] * 0.98 and p1 >= p0 * 0.98:
            rec["unit_change"] = (p1 / s1[0]) / (p0 / s0[0]) - 1
            shrink.append(rec)
        elif p0 and p1 > p0 + 0.009:
            rec["pct"] = p1 / p0 - 1
            up.append(rec)
        elif p0 and p1 < p0 - 0.009:
            rec["pct"] = p1 / p0 - 1
            down.append(rec)
    shrink.sort(key=lambda r: -r["unit_change"])
    up.sort(key=lambda r: -r["pct"])
    down.sort(key=lambda r: r["pct"])
    return {"up": up[:limit], "down": down[:limit], "shrink": shrink[:limit], "since": since, "days": len(hd)}


def price_on(hdb, barcodes, day):
    """{(barcode, chain): price} — המחיר האחרון הידוע עד תאריך נתון."""
    if not barcodes or not hdb or not has_table(hdb, "price_history"):
        return {}
    c = sqlite3.connect(hdb)
    out = {}
    for bc in barcodes:
        for ch, pr in c.execute("""
            SELECT chain, price FROM price_history h
            WHERE barcode = ? AND day = (SELECT MAX(day) FROM price_history x
                                         WHERE x.barcode = h.barcode AND x.chain = h.chain AND x.day <= ?)
        """, (bc, day)):
            out[(bc, ch)] = pr
    c.close()
    return out


def basket_index(hdb, items, chains, days=30):
    """
    מדד הסל האישי: לכל רשת — הסל היום מול הסל לפני כ-`days` ימים (רק מוצרים שיש להם מחיר בשני התאריכים).
    items: [(barcode, qty)]
    """
    hd = history_days(hdb)
    if len(hd) < 2 or not items:
        return None
    today = hd[-1]
    target = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    base_day = max([d for d in hd if d <= target] or [hd[0]])
    if base_day == today:
        return None
    bcs = [b for b, _ in items]
    now, then = price_on(hdb, bcs, today), price_on(hdb, bcs, base_day)
    res = {}
    for c in chains:
        tn = tt = 0.0
        n = 0
        for b, q in items:
            if (b, c) in now and (b, c) in then:
                tn += now[(b, c)] * q
                tt += then[(b, c)] * q
                n += 1
        if n and tt > 0:
            res[c] = {"now": round(tn, 2), "then": round(tt, 2), "pct": tn / tt - 1, "n": n}
    return {"from": base_day, "to": today, "chains": res} if res else None


# ═══════════════════════════════════════════════════════
# ברקוד מתמונה
# ═══════════════════════════════════════════════════════
def decode_barcode(image_bytes):
    """מחזיר את מספר הברקוד מתמונה, או None. דורש zxing-cpp (ב-requirements)."""
    try:
        import io
        import zxingcpp
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        for r in zxingcpp.read_barcodes(img):
            t = (r.text or "").strip()
            if t.isdigit() and len(t) >= 7:
                return t
    except Exception:
        return None
    return None


# ═══════════════════════════════════════════════════════
# שמירה ושיתוף
# ═══════════════════════════════════════════════════════
def pack_items(items):
    """רשימה → מחרוזת קצרה לקישור שיתוף."""
    slim = [{"q": i["q"], "n": i.get("name", ""), "qty": i["qty"], "kg": i["kg"],
             "b": i.get("barcode"), "g": i.get("group")} for i in items]
    raw = json.dumps(slim, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")


def unpack_items(s):
    try:
        pad = "=" * (-len(s) % 4)
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(s + pad)).decode("utf-8"))
        return [d for d in data if isinstance(d, dict) and d.get("q")]
    except Exception:
        return []


def items_to_text(items):
    lines = []
    for i in items:
        q = format(i["qty"], "g")
        lines.append((f"{q} ק״ג " if i["kg"] else (f"{q} × " if i["qty"] != 1 else "")) + i["q"])
    return "\n".join(lines)
