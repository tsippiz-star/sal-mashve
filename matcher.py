"""
matcher.py – התאמת שם חופשי ("חלב 3% תנובה") למוצר במאגר.

לוגיקה:
1. RapidFuzz – התאמת מחרוזות מהירה. אם ניקוד ≥ 88 → קיבלנו.
2. אחרת – נחזיר את 5 המועמדים הטובים ביותר ל-UI, המשתמש יבחר.
3. אופציונלי (GPT-4o-mini) – יבחר לבד. הופעל רק אם קיים OPENAI_API_KEY.
"""
import os, sqlite3, json
from pathlib import Path
from functools import lru_cache
from rapidfuzz import fuzz, process

DB_PATH = Path(__file__).parent.parent / "prices.db"

# ─── טעינת קטלוג מוצרים ייחודי לזיכרון ───────────────
@lru_cache(maxsize=1)
def load_catalog():
    """מחזיר: {barcode: (name, brand)} + [(idx, "name brand"), ...] לחיפוש."""
    conn = sqlite3.connect(DB_PATH)
    # ממוצע ארצי לפי ברקוד
    rows = conn.execute("""
        SELECT barcode,
               MAX(name)  AS name,
               MAX(brand) AS brand
        FROM prices
        WHERE barcode != '' AND name != ''
        GROUP BY barcode
    """).fetchall()
    conn.close()
    catalog = {}
    search_strings = []
    for bc, name, brand in rows:
        catalog[bc] = (name, brand or "")
        search_strings.append(f"{name} {brand or ''}".strip())
    return catalog, search_strings, list(catalog.keys())


def find_candidates(query: str, top_k=5):
    """מחזיר top_k מועמדים: [(barcode, name, brand, score)]"""
    catalog, search_strings, barcodes = load_catalog()
    if not search_strings:
        return []
    matches = process.extract(query, search_strings, scorer=fuzz.WRatio, limit=top_k)
    result = []
    for text, score, idx in matches:
        bc = barcodes[idx]
        name, brand = catalog[bc]
        result.append({"barcode": bc, "name": name, "brand": brand, "score": score})
    return result


def match_item(query: str, threshold=88):
    """
    מזהה מוצר מטקסט חופשי.
    מחזיר: {barcode, name, brand, score, method} או None.
    """
    cands = find_candidates(query, top_k=5)
    if not cands:
        return None
    top = cands[0]
    if top["score"] >= threshold:
        top["method"] = "fuzzy"
        return top
    # ננסה AI (רק אם יש מפתח)
    if os.getenv("OPENAI_API_KEY"):
        try:
            ai = ai_pick(query, cands)
            if ai:
                ai["method"] = "ai"
                return ai
        except Exception as e:
            print("AI error:", e)
    # לא בטוחים – מחזירים None + המועמדים ל-UI
    return None


def ai_pick(query, candidates):
    from openai import OpenAI
    client = OpenAI()
    opts = "\n".join(f"{i}. {c['name']} ({c['brand']})" for i, c in enumerate(candidates))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user",
                   "content": f"""משתמש רשם ברשימת קניות: "{query}"
מוצרים אפשריים:
{opts}
איזה הכי מתאים? החזר JSON: {{"index": מספר או -1, "confidence": 0-1}}."""}],
        response_format={"type": "json_object"},
        temperature=0
    )
    data = json.loads(resp.choices[0].message.content)
    if data.get("index", -1) < 0 or data.get("confidence", 0) < 0.7:
        return None
    return candidates[data["index"]]


if __name__ == "__main__":
    # דוגמה
    for q in ["חלב 3%", "קוטג'", "במבה אסם", "ניילון נצמד"]:
        m = match_item(q)
        print(f"\nQuery: {q}")
        if m:
            print(f"  → [{m['barcode']}] {m['name']} ({m['brand']}) score={m['score']:.1f}")
        else:
            print("  → ambiguous, showing candidates:")
            for c in find_candidates(q):
                print(f"     {c['score']:>5.1f}  [{c['barcode']}] {c['name']} ({c['brand']})")
