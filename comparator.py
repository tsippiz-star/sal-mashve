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
