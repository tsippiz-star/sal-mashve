"""
facets.py – "כל הסוגים": קבוצת מוצרים עם סינון מרובה לפי מותג/ספק, אחוז שומן, גודל וסוג.
וגם בחירת זנים לירקות ופירות.

הנתונים ברשתות לא מסודרים (המותג לרוב "לא ידוע", השמות קטועים) —
לכן המאפיינים נשלפים מתוך שם המוצר, ומשדות המותג/כמות/יחידה כשהם קיימים.
"""
import re
import sqlite3
from collections import Counter

HEB = "א-ת"
_FINALS = str.maketrans("םןץףך", "מנצפכ")


def _n(s):
    """נרמול לחיפוש: בלי מרכאות, אותיות סופיות רגילות, רווח יחיד."""
    s = re.sub(r"[\"'׳״`]", "", str(s or "")).translate(_FINALS).lower()
    return re.sub(r"\s+", " ", s).strip()


# ─── מותגים מוכרים (מחפשים גם בשדה המותג וגם בשם המוצר) ───
KNOWN_BRANDS = [
    "תנובה", "טרה", "יטבתה", "שטראוס", "דנונה", "יופלה", "מולר", "אסם", "עלית", "נעם", "גלבוע",
    "עמק", "צוריאל", "רימילק", "יכין", "פריניר", "אחלה", "סוגת", "הנסיך", "ויטה", "זוגלובק",
    "תלמה", "נסטלה", "קנור", "בייגל בייגל", "סנו", "פיירי", "לילי", "מילקו", "קוקה קולה", "פריגת",
    "ספרינג", "נביעות", "עוף טוב", "מאמא עוף", "טירת צבי", "אל-על", "סוגת", "וילי פוד", "פרימור",
    "יד מרדכי", "מעדני מיקי", "שופרסל", "רמי לוי", "יוחננוף", "קרפור", "פרי הגליל", "גד", "השף הלבן",
    "הרדוף", "אנגל", "ברמן", "דוידוביץ", "אורגניק", "בלו בנד", "פילדלפיה", "גבינות גד", "משק צוריאל",
    "סוסיא", "רמת הגולן", "שקמה", "מחלבות גד", "קיסריה", "טעמן", "זנגביל", "אריאל", "טייד", "פרסיל",
    "נייס", "סופט", "טאצ'", "קלינקס", "האגיס", "פמפרס", "טבעול", "זוגלובק", "מאסטר שף",
]
_JUNK_BRANDS = {"", "לא ידוע", "unknown", "none", "nan", "כללי", "קריות זול"}
_BRAND_CANON = {"מחלבת יטבתה": "יטבתה", "משק צוריאל": "צוריאל", "גבינות גד": "גד", "מחלבות גד": "גד",
                "שטראוס גרופ": "שטראוס", "מולר- מילקו": "מולר"}


def _word_in(needle, hay):
    """מילה שלמה (עם תחיליות עבריות נפוצות) בתוך טקסט מנורמל."""
    return re.search(rf"(?<![{HEB}])[והבלמש]?{re.escape(needle)}(?![{HEB}])", hay) is not None


def brand_of(name, brand):
    nb, nn = _n(brand), _n(name)
    for kb in KNOWN_BRANDS:
        k = _n(kb)
        if k and (k in nb):
            return _BRAND_CANON.get(kb, kb)
    for kb in KNOWN_BRANDS:
        k = _n(kb)
        if len(k) >= 3 and _word_in(k, nn):
            return _BRAND_CANON.get(kb, kb)
    if nb not in _JUNK_BRANDS and re.search(r"[א-תa-z]", nb):
        short = " ".join(str(brand).replace('בע"מ', "").replace("בע״מ", "").split()[:2]).strip(" -")
        return _BRAND_CANON.get(short, short) or "אחר"
    return "אחר"


# ─── אחוז שומן ───
_FAT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def fat_of(name):
    m = _FAT_RE.search(str(name or ""))
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return f"{v:g}%" if 0 <= v <= 60 else None


# ─── גודל אריזה ───
_SIZE_RE = re.compile(
    rf"(\d+(?:[.,]\d+)?)\s*(ליטר|ל(?![{HEB}])|מ\"ל|מ״ל|מל(?![{HEB}])|מיליליטר|גרם|גר'?(?![{HEB}])|ג(?![{HEB}])|ק\"ג|ק״ג|קג(?![{HEB}])|קילו(?:גרם)?)")


def size_of(name, unit, qty):
    """(כמות בסיסית, 'v' לנפח במ"ל / 'w' למשקל בגרם) או None."""
    m = _SIZE_RE.search(str(name or ""))
    if m:
        v = float(m.group(1).replace(",", "."))
        u = m.group(2)
        if u in ("ליטר", "ל"):
            amt, dim = v * 1000, "v"
        elif u in ('מ"ל', "מ״ל", "מל", "מיליליטר"):
            amt, dim = v, "v"
        elif u.startswith("ק"):
            amt, dim = v * 1000, "w"
        else:
            amt, dim = v, "w"
        if 5 <= amt <= 20000:
            return round(amt), dim
    try:
        q = float(qty or 0)
    except (TypeError, ValueError):
        q = 0
    u = str(unit or "")
    if q > 0:
        if "ליטר" in u or "מיליליטר" in u or 'מ"ל' in u or "מ'ל" in u:
            amt, dim = (q if q >= 10 else q * 1000), "v"
        elif "גרם" in u or "קילו" in u or 'ק"ג' in u:
            amt, dim = (q if q >= 10 else q * 1000), "w"
        else:
            return None
        if 5 <= amt <= 20000:
            return round(amt), dim
    return None


def size_label(amt, dim):
    if dim == "v":
        return f"{amt / 1000:g} ליטר" if amt >= 1000 else f"{amt:g} מ״ל"
    return f"{amt / 1000:g} ק״ג" if amt >= 1000 else f"{amt:g} גרם"


# ─── סוג / מאפיינים ───
TYPE_TAGS = [
    "מהדרין", "דל לקטוז", "ללא לקטוז", "עיזים", "כבשים", "מועשר", "ביו", "יווני", "טרי", "עמיד",
    "קרטון", "בקבוק", "שקית", "כד", "פרוס", "מגורד", "לייט", "קלאסי", "נוגט", "בננה", "חלוה",
    "תות", "וניל", "שוקו", "מארז", "אורגני", "ללא גלוטן", "ללא סוכר", "דל שומן", "מלוח", "חריף",
    "מעושן", "טבעוני", "צמחי", "סויה", "שקדים", "שיבולת שועל", "מוקצף", "גוש", "אצבעות", "משפחתי",
    "מיני", "ענק", "מלא", "לבן", "שחור", "אדום", "ירוק", "צהוב",
]

# מילים שמסמנות מוצר "נגזר" — לא נכנס לקבוצה אם המילה לא הופיעה בחיפוש עצמו
DERIVED = [
    "שוקולד", "משקה", "רוטב", "רסק", "חטיף", "עוגי", "גלידה", "ממרח", "נמס", "מרק", "ופל", "דגני",
    "פודינג", "מעדן", "סבון", "שמפו", "קפה", "תחליב", "אבקת", "נקטר", "מיץ", "מרוסק", "קצוצ",
    "קוביות", "כבוש", "חמוץ", "ממולא", "מיובש", "צ'יפס", "ציפס", "קרקר", "ביסקוויט", "סוכרי", "מסטיק",
    "תבלין", "מרינדה", "קטשופ", "ג'לי", "ריבה", "תרכיז", "לחם", "פיצה", "כריך", "סלט", "קציצ",
    "שניצל", "נקניק", "פשטידה", "בורקס", "מאפה", "עוגה", "עוגת", "קינוח", "שייק", "קרם", "טחינה",
    "חמאה", "כלב", "חתול", "תינוק", "מזון", "פתיתי", "שוקו", "מילקי", "דנונה פרי", "קורנפלקס",
    "אטרי", "איטרי", "נודלס", "פריכי", "פריכונ", "מגדים", "ציטוס", "צנימ", "סרופ", "במילוי", "כיף כף",
    "פסק זמן", "טבלת", "וופל", "בטעם", "ספריי", "תרסיס",
]

FACET_ORDER = [("brand", "מותג / ספק"), ("fat", "אחוז (שומן)"), ("size", "גודל אריזה"), ("type", "סוג / מאפיין")]


_UNIT_WORDS = {_n(w) for w in ["ליטר", "ל", "גרם", "גר", "ג", "מל", 'מ"ל', "מיליליטר", 'ק"ג', "קג", "קילו",
                                "קילוגרם", "יח", "יחידות", "יחידה", "שומן", "במשקל", "ארוז"]}


def _core_tokens(query):
    """מפרק חיפוש: מילות ליבה (שם המוצר), מותגים ואחוזים לבחירה מראש."""
    toks = str(query or "").split()
    core, pre_brand, pre_fat, pre_type = [], [], [], []
    _tags1 = {_n(x): x for x in TYPE_TAGS if " " not in x}
    for t in toks:
        if _n(t) in _tags1:
            pre_type.append(_tags1[_n(t)])
            continue
        if _FAT_RE.fullmatch(t.strip()):
            f = fat_of(t)
            if f:
                pre_fat.append(f)
            continue
        if re.fullmatch(r"[\d.,x×*]+", t) or _n(t) in _UNIT_WORDS or re.fullmatch(r"\d+(?:[.,]\d+)?[א-ת\"'׳״]+", t):
            continue
        kb = next((b for b in KNOWN_BRANDS if _n(b) == _n(t)), None)
        if kb:
            pre_brand.append(_BRAND_CANON.get(kb, kb))
            continue
        # "חלב3%" → "חלב" + 3%
        m = re.match(r"^(.*?)(\d+(?:[.,]\d+)?%)$", t)
        if m and m.group(1):
            core.append(m.group(1))
            f = fat_of(m.group(2))
            if f:
                pre_fat.append(f)
            continue
        core.append(t)
    core = [_n(c) for c in core if _n(c)]
    # שם מוצר מלא (נבחר מההשלמה) → רק שם הסוג, כדי לקבל את כל המשפחה
    if len(core) > 2:
        core = core[:1]
    return core, pre_brand, pre_fat, pre_type


def _head_match(tok, name_n, max_words=2):
    words = name_n.split()[:max_words]
    for i, w in enumerate(words):
        w2 = re.sub(r"\d.*$", "", w)  # "חלב3%" → "חלב"
        # תחילית (החלב) רק במילה הראשונה — כדי ש״סרדינים בשמן״ לא ייחשב שמן
        for cand in (w2, w2[1:] if i == 0 and len(w2) > len(tok) and w2[0] in "הו" else None):
            if not cand:
                continue
            if cand == tok:
                return True
            if len(tok) >= 4 and cand.startswith(tok) and cand[len(tok):] in ("ים", "ות", "ה", "ת", "י"):
                return True
    return False


def family(db_path, query, chains=None):
    """
    כל המוצרים ששייכים ל"סוג" שחיפשו (למשל "חלב"), עם המאפיינים שלהם.
    מחזיר dict: products [{barcode,name,brand,fat,size,dim,type[]}], facets {key:[values]},
    prices {barcode:{chain:price}}, dim ('v'/'w'), pre {key:[values]}.
    """
    core, pre_brand, pre_fat, pre_type = _core_tokens(query)
    empty = {"products": [], "facets": {}, "prices": {}, "dim": "w", "pre": {}, "core": " ".join(core)}
    if not core:
        return empty
    conn = sqlite3.connect(db_path)
    _raw = re.sub(r"[\"'׳״`]", "", str(query or "")).split()
    raw_tok = next((t for t in _raw if _n(t) == core[0] or _n(t).startswith(core[0])), core[0])
    rows = conn.execute(
        "SELECT barcode, MAX(name), MAX(brand), MAX(unit), MAX(qty) FROM prices "
        "WHERE barcode != '' AND price > 0 AND name LIKE ? GROUP BY barcode",
        (f"%{raw_tok[:3]}%",)).fetchall()
    prods = []
    q_all = " ".join(core)
    for bc, name, brand, unit, qty in rows:
        nn = _n(name)
        if not _head_match(core[0], nn):
            _b = brand_of(name, brand)
            if not (_b != "אחר" and _n(_b) in " ".join(nn.split()[:2]) and _head_match(core[0], nn, 3)):
                continue
        if any(t not in nn for t in core[1:]):
            continue
        if any(_n(d) in nn and _n(d) not in q_all for d in DERIVED):
            continue
        sz = size_of(name, unit, qty)
        ndim = size_of(name, "", 0)
        prods.append({"ndim": ndim[1] if ndim else None,"barcode": bc, "name": str(name or "").strip(), "brand": brand_of(name, brand),
                      "fat": fat_of(name), "amt": sz[0] if sz else None, "dim": sz[1] if sz else None,
                      "tags": [t for t in TYPE_TAGS if _n(t) in nn]})
    if not prods:
        conn.close()
        return empty

    # מחירים (ממוצע ארצי לכל רשת)
    bcs = [p["barcode"] for p in prods]
    prices = {}
    for i in range(0, len(bcs), 800):
        part = bcs[i:i + 800]
        for bc, ch, pr in conn.execute(
                f"SELECT barcode, chain, AVG(price) FROM prices WHERE price > 0 AND barcode IN ({','.join('?' * len(part))}) "
                "GROUP BY barcode, chain", part):
            if chains is None or ch in chains:
                prices.setdefault(bc, {})[ch] = round(pr, 2)
    conn.close()
    prods = [p for p in prods if p["barcode"] in prices]
    # קודם מוצרים שנמכרים בהרבה רשתות
    prods.sort(key=lambda p: -len(prices[p["barcode"]]))
    prods = prods[:400]

    dim = Counter(p["ndim"] for p in prods if p.get("ndim")).most_common(1) or \
        Counter(p["dim"] for p in prods if p["dim"]).most_common(1)
    dim = dim[0][0] if dim else "w"
    for p in prods:
        p["size"] = size_label(p["amt"], p.get("ndim") or p["dim"] or dim) if p["amt"] else None

    def _vals(key, min_count=2):
        c = Counter(v for p in prods for v in ([p[key]] if key != "type" else p["tags"]) if v)
        vals = [v for v, k in c.most_common() if k >= min_count]
        if key == "type":
            vals = [v for v in vals if c[v] < len(prods) * 0.95]
        if key == "fat":
            vals.sort(key=lambda s: float(s[:-1]))
        if key == "size":
            vals = vals[:9]
            vals.sort(key=lambda s: next((p["amt"] for p in prods if p["size"] == s), 0))
        if key == "brand" and "אחר" in vals:
            vals.remove("אחר")
            vals.append("אחר")
        return vals[:14]

    facets = {}
    for key, _lbl in FACET_ORDER:
        v = _vals(key)
        if len(v) >= 2:
            facets[key] = v
    pre = {}
    if pre_brand and "brand" in facets:
        pre["brand"] = [b for b in pre_brand if b in facets["brand"]]
    if pre_fat and "fat" in facets:
        pre["fat"] = [f for f in pre_fat if f in facets["fat"]]
    if pre_type and "type" in facets:
        pre["type"] = [f for f in pre_type if f in facets["type"]]
    return {"products": prods, "facets": facets, "prices": prices, "dim": dim,
            "pre": {k: v for k, v in pre.items() if v}, "core": " ".join(core)}


def filter_products(fam, sel):
    """AND בין קטגוריות, OR בתוך קטגוריה. בחירה ריקה = הכל."""
    out = []
    for p in fam["products"]:
        ok = True
        for key, vals in (sel or {}).items():
            if not vals:
                continue
            if key == "type":
                if not any(t in p["tags"] for t in vals):
                    ok = False
            elif p.get(key) not in vals:
                ok = False
            if not ok:
                break
        if ok:
            out.append(p)
    return out


def group_prices(fam, sel, chains, normalize=True):
    """
    לכל רשת: המוצר הזול ביותר מבין המוצרים שנבחרו.
    אם יש בבחירה כמה גדלים ו-normalize — משווים לפי מחיר ליחידת מידה, מוכפל בגודל הנפוץ.
    מחזיר: prices{chain: price|None}, picks{chain: (name, real_price)}, info{n, ref_label, mixed}
    """
    prods = filter_products(fam, sel)
    sizes = Counter(p["amt"] for p in prods if p["amt"])
    mixed = len(sizes) > 1
    ref = sizes.most_common(1)[0][0] if sizes else None
    use_norm = normalize and mixed and ref
    prices, picks = {}, {}
    for c in chains:
        best = None
        for p in prods:
            pr = fam["prices"].get(p["barcode"], {}).get(c)
            if pr is None:
                continue
            if use_norm:
                if not p["amt"]:
                    continue
                val = pr / p["amt"] * ref
            else:
                val = pr
            if best is None or val < best[0]:
                best = (val, p["name"], pr)
        prices[c] = round(best[0], 2) if best else None
        if best:
            picks[c] = (best[1], best[2])
    info = {"n": len(prods), "mixed": mixed, "norm": bool(use_norm),
            "ref_label": size_label(ref, fam["dim"]) if ref else None}
    return prices, picks, info


def sel_summary(sel):
    parts = [", ".join(v) for k, _l in FACET_ORDER for v in [(sel or {}).get(k) or []] if v]
    return " · ".join(parts)


# ═══════════════════════════════════════════════════════
# ירקות ופירות — בחירת זנים
# ═══════════════════════════════════════════════════════
VARIETIES = [
    "שרי", "תמר", "אשכולות", "בלדי", "רומא", "מגי", "לבבות", "מיני", "בייבי", "ענק", "פרסי", "ארוך",
    "חממה", "אדום", "צהוב", "ירוק", "כתום", "לבן", "סגול", "שחור", "גאלה", "פינק ליידי", "גרני סמית",
    "גולדן", "סמיט", "פוג'י", "חרמון", "יונתן", "סטארקינג", "קריפס", "שמוטי", "וולנסיה", "קלמנטינה",
    "מיכל", "האס", "אטינגר", "פוארטה", "ריד", "קיט", "טומי", "מאיה", "מתוק", "אורגני", "מארז",
    "מקולף", "שטוף", "בטטה", "ללא חרצנים", "קנטלופ", "גליה", "צ'רי", "מוזהב", "נאשי",
    "אנה", "גויה", "שושקה", "בהיר", "כהה", "מובחר", "גורמה", "קטן", "ברשת", "בשקית", "בתפזורת",
]


def produce_candidates(db_path, produce_items, global_exc, band, per_kg, chains=None):
    """{ירק: {רשת: [(מחיר לקילו, שם)]}} — כל המועמדים לפי משקל (לא רק הזול)."""
    inc = sorted({k for d in produce_items for k in d["inc"]})
    if not inc:
        return {}
    sql = ("SELECT chain, name, price, unit, qty FROM prices WHERE unit IS NOT NULL AND unit != '' AND ("
           + " OR ".join("name LIKE ?" for _ in inc) + ") AND (unit LIKE '%ק%ג%' OR unit LIKE '%קילו%')")
    conn = sqlite3.connect(db_path)
    rows = conn.execute(sql, [f"%{k}%" for k in inc]).fetchall()
    conn.close()
    out = {d["he"]: {} for d in produce_items}
    for ch, nm, pr, un, qt in rows:
        if chains and ch not in chains:
            continue
        n = str(nm or "")
        for d in produce_items:
            if not any(k in n for k in d["inc"]) or any(k in n for k in d["exc"]) or any(k in n for k in global_exc):
                continue
            v = per_kg(pr, un, qt)
            if not v or v <= 0:
                continue
            lo, hi = band.get(d["he"], (0.0, 1e9))
            if not (lo <= v <= hi):
                continue
            out[d["he"]].setdefault(ch, []).append((round(v, 2), n.strip()))
    return out


def _var_in(var, name_n):
    """זן כמילה (או תחילת מילה — אורגני/אורגנית, אדום/אדומה)."""
    return re.search(rf"(?<![{HEB}])[והב]?{re.escape(_n(var))}", name_n) is not None


def produce_varieties(cands_for_item):
    c = Counter()
    for lst in cands_for_item.values():
        seen = set()
        for _v, nm in lst:
            nn = _n(nm)
            for var in VARIETIES:
                if _var_in(var, nn):
                    seen.add(var)
        c.update(seen)
    return [v for v, k in c.most_common() if k >= 1][:12]


def produce_best(cands_for_item, varieties=None):
    """{רשת: (מחיר לקילו, שם)} — הזול בכל רשת, רק מהזנים שנבחרו (ריק = הכל)."""
    out = {}
    vs = list(varieties or [])
    for ch, lst in cands_for_item.items():
        pool = [x for x in lst if not vs or any(_var_in(v, _n(x[1])) for v in vs)]
        if pool:
            out[ch] = min(pool, key=lambda x: x[0])
    return out
