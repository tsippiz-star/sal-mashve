"""
comparator.py – השוואת סל קניות בין הרשתות.

לוגיקה: לכל פריט → זיהוי ברקוד → ממוצע ארצי של כל רשת (על כל הסניפים).
"""
import sqlite3
from pathlib import Path
from matcher import match_item, find_candidates

DB_PATH = Path(__file__).parent / "prices.db"

CHAINS_HE = {
    "shufersal": "שופרסל",
    "rami-levy": "רמי לוי",
    "yohananof": "יוחננוף",
    "victory":   "ויקטורי",
    "osher-ad":  "אושר עד",
    "tiv-taam":  "טיב טעם",
    "keshet":      "קשת טעמים",
    "freshmarket": "פרשמרקט",
    "paz":         "פז / Yellow",
    "carrefour":   "קרפור",
    "hazi-hinam":  "חצי חינם",
}


def price_by_barcode(barcode: str, chain: str, conn) -> float | None:
    """ממוצע ארצי של המחיר לפי רשת ולפי ברקוד."""
    row = conn.execute("""
        SELECT AVG(price), COUNT(*)
        FROM prices
        WHERE chain = ? AND barcode = ?
    """, (chain, barcode)).fetchone()
    if row and row[0]:
        return round(row[0], 2)
    return None


def compare(shopping_list: list[str]):
    """
    מקבל רשימת שמות פריטים, מחזיר:
    {
      "matched":  [{query, product, prices:{chain: price|None}}],
      "unclear":  [{query, candidates: [...]}],   # דורש בחירת המשתמש
      "totals":   {chain: {"total": X, "hits": N, "missing": M}}
    }
    """
    conn = sqlite3.connect(DB_PATH)
    matched, unclear = [], []
    chains = [c[0] for c in conn.execute("SELECT DISTINCT chain FROM prices").fetchall()]

    for q in shopping_list:
        q = q.strip()
        if not q:
            continue
        prod = match_item(q)
        if prod:
            prices = {c: price_by_barcode(prod["barcode"], c, conn) for c in chains}
            _u = conn.execute("SELECT MAX(unit) FROM prices WHERE barcode = ?", (prod["barcode"],)).fetchone()
            prod["unit"] = (_u[0] if _u and _u[0] else "") or ""
            matched.append({"query": q, "product": prod, "prices": prices})
        else:
            unclear.append({"query": q, "candidates": find_candidates(q, 5)})

    # חישוב סה"כ לרשת
    totals = {}
    for c in chains:
        total, hits, miss = 0.0, 0, 0
        for m in matched:
            p = m["prices"].get(c)
            if p is not None:
                total += p
                hits += 1
            else:
                miss += 1
        totals[c] = {"total": round(total, 2), "hits": hits, "missing": miss}

    conn.close()
    return {"matched": matched, "unclear": unclear, "totals": totals, "chains": chains}


if __name__ == "__main__":
    from pprint import pprint
    r = compare(["חלב 3%", "ניילון נצמד", "רוטב טבסקו", "משהו שלא קיים"])
    for m in r["matched"]:
        print(f"{m['query']:20s} → {m['product']['name']}")
        for c, p in m['prices'].items():
            print(f"   {CHAINS_HE.get(c,c):10s} {p if p else '—'}")
    print("\nTotals:")
    pprint(r["totals"])


# ═══════════════════════════════════════════════════════
# ─── ירקות ופירות לפי משקל (קילו) ──────────────────────
# ═══════════════════════════════════════════════════════
# מילים שפוסלות מוצר מכל השוואת ירקות/פירות (שתייה, מעובד, מזון לבעלי חיים...)
GLOBAL_EXC = ["מיץ", "משקה", "קריסטל", "מים", "סודה", "תרכיז", "ליטר", 'מ"ל', "מיליליטר",
              "אלכוהול", "יין", "בירה", "שוקולד", "עוג", "גלידה", "חטיף", "צ'יפס", "קלוי",
              "מטוגנ", "מבושל", "ממולא", "כבוש", "חמוץ", "משומר", "שימור", "קפוא", "מיובש",
              "יבש", "אבקת", "תמצית", "ריבה", "ממרח", "רטב", "סלט", "לחם", "פיצה", "פסטה",
              "דגני", "תינוק", "מזון", "כלב", "חתול", "תוסף", "ויטמין", "משובח", "פרימיום",
              # מותגי שתייה (השמות במאגר קטועים, לכן חוסמים לפי מותג)
              "תפוזינה", "ספרינג", "שוופס", "קריסטל", "נביעות", "פריגת", "מוגז", "תה",
              "קולה", "פפסי", "ספרייט", "פאנטה", "אשכולית", "תרכיז",
              "סירופ", "בטעם", "טעם", "גאמפ", "גאם", "סוכריה", "מסטיק", "חמאת",
              "נקטר", "איילנד", "מיץ טבעי", "שייק"]

# טווח מחיר סביר לקילו (₪) - מונע תפיסת מוצרי קצה/מותג יקר בטעות
PRODUCE_BAND = {
    "עגבניות": (1.0, 20.0), "מלפפונים": (1.0, 20.0), "בננות": (1.0, 25.0),
    "תפוחים": (1.0, 25.0), "תפוחי אדמה": (0.5, 15.0), "תפוזים": (1.0, 20.0),
    "גזר": (0.5, 15.0), "בצל": (0.5, 15.0), "פלפלים": (1.0, 25.0),
    "ענבים": (1.0, 40.0), "אגסים": (1.0, 30.0), "לימונים": (1.0, 20.0),
    "אבוקדו": (2.0, 40.0), "כרוב": (0.5, 15.0), "קישואים": (1.0, 20.0),
    "חציל": (1.0, 20.0), "תירס": (1.0, 25.0), "פטריות": (5.0, 60.0),
    "מנגו": (2.0, 40.0), "אבטיח": (0.5, 15.0), "מלון": (1.0, 20.0),
    "תות שדה": (3.0, 60.0),
}


def per_kg(price, unit, qty):
    """מחיר לקילו מתוך מחיר/יחידת מידה/כמות. מחזיר None אם היחידה אינה לפי משקל."""
    try:
        p = float(price or 0)
        q = float(qty or 0)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    u = str(unit or "")
    if ("ק" in u and "ג" in u) or "קילו" in u:          # ק"ג / קילוגרם
        return p / q if q > 0 else p
    if "גרם" in u or "גר'" in u:                         # 100 גרם / גרם
        if q > 0:
            return p / (q / 1000.0)
        return p * 10 if "100" in u else None
    return None


PRODUCE_ITEMS = [
    {"he": "עגבניות",     "inc": ["עגבני"],                      "exc": ["רוטב", "רסק", "מרוסק", "קובי", "כוס", "ממרח", "גבינה", "צ'יפס", "יבש", "מיובש", "ממולא", "מטוגנ", "שימור"]},
    {"he": "מלפפונים",    "inc": ["מלפפון"],                     "exc": ["חמוץ", "כבוש", "ביצה", "צ'יפס"]},
    {"he": "בננות",       "inc": ["בננה"],                       "exc": ["צ'יפס", "יבש", "מיובש", "צימוק", "שוקולד", "עוג"]},
    {"he": "תפוחים",      "inc": ["תפוח עץ", "תפוחים"],          "exc": ["אדמה", "יבש", "מיובש", "רסק", "מיץ"]},
    {"he": "תפוחי אדמה",  "inc": ["תפוח אדמה", "תפוחי אדמה"],    "exc": ["צ'יפס", "קפוא", "מטוגנ", "פירה", "מיובש"]},
    {"he": "תפוזים",      "inc": ["תפוז"],                       "exc": ["מיץ", "שוקולד", "יבש"]},
    {"he": "גזר",         "inc": ["גזר"],                        "exc": ["מיץ", "עוג", "קפוא", "כבוש"]},
    {"he": "בצל",         "inc": ["בצל"],                        "exc": ["מיובש", "מטוגנ", "צ'יפס", "גרוס", "יבש", "כבוש"]},
    {"he": "פלפלים",      "inc": ["פלפל"],                       "exc": ["חריף", "קלוי", "ממולא", "רסק", "שמן", "טחון", "מטוגנ"]},
    {"he": "ענבים",       "inc": ["ענב"],                        "exc": ["צימוק", "מיץ", "יבש"]},
    {"he": "אגסים",       "inc": ["אגס"],                        "exc": ["רסק", "מיץ", "יבש"]},
    {"he": "לימונים",     "inc": ["לימון"],                      "exc": ["מיץ", "עוג", "רסק"]},
    {"he": "אבוקדו",      "inc": ["אבוקדו"],                     "exc": []},
    {"he": "כרוב",        "inc": ["כרוב"],                       "exc": ["כבוש", "סלט", "מיץ"]},
    {"he": "קישואים",     "inc": ["קישוא"],                      "exc": ["מטוגנ", "קפוא", "ממולא"]},
    {"he": "חציל",        "inc": ["חציל"],                       "exc": ["מטוגנ", "קלוי", "רסק", "ממולא", "קפוא"]},
    {"he": "תירס",        "inc": ["תירס"],                       "exc": ["שימור", "קפוא", "גרעין", "פופקורן"]},
    {"he": "פטריות",      "inc": ["פטריות"],                     "exc": ["ממולא", "מרוקאי"]},
    {"he": "מנגו",        "inc": ["מנגו"],                       "exc": []},
    {"he": "אבטיח",       "inc": ["אבטיח"],                      "exc": ["גרעין", "מיובש"]},
    {"he": "מלון",        "inc": ["מלון"],                       "exc": ["גרעין", "מיובש"]},
    {"he": "תות שדה",     "inc": ["תות שדה"],                    "exc": ["ריבה", "גלידה", "מיובש"]},
]


def produce_prices(items=None, chains=None):
    """{ירק/פרי: {chain: (מחיר לקילו, שם המוצר)}} - הזול ביותר לקילו בכל רשת.
    רק מוצרים שנמכרים לפי משקל (ק"ג / גרם)."""
    defs = items or PRODUCE_ITEMS
    inc = sorted({k for d in defs for k in d["inc"]})
    if not inc:
        return {}
    sql = ("SELECT chain, name, price, unit, qty FROM prices "
           "WHERE unit IS NOT NULL AND unit != '' "
           "AND (" + " OR ".join("name LIKE ?" for _ in inc) + ") "
           "AND (unit LIKE '%ק%ג%' OR unit LIKE '%קילו%')")
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(sql, [f"%{k}%" for k in inc]).fetchall()
    conn.close()
    out = {d["he"]: {} for d in defs}
    for ch, nm, pr, un, qt in rows:
        if chains and ch not in chains:
            continue
        n = str(nm or "")
        for d in defs:
            if not any(k in n for k in d["inc"]):
                continue
            if any(k in n for k in d["exc"]):
                continue
            if any(k in n for k in GLOBAL_EXC):
                continue
            v = per_kg(pr, un, qt)
            if not v or v <= 0:
                continue
            _lo, _hi = PRODUCE_BAND.get(d["he"], (0.0, 1e9))
            if not (_lo <= v <= _hi):
                continue
            cur = out[d["he"]].get(ch)
            if cur is None or v < cur[0]:
                out[d["he"]][ch] = (round(v, 2), n.strip())
    return out


if __name__ == "__main__":
    pass
