"""
scraper.py (v8 – כולל מבצעים והיסטוריית מחירים) – מוריד קבצי "שקיפות מחירים" מ-6 רשתות המזון בישראל
ומכניס את המחירים לבסיס נתונים SQLite.

מקורות:
- שופרסל: prices.shufersal.co.il (ציבורי, ללא התחברות)
- רמי לוי, יוחננוף, אושר עד, טיב טעם, קשת, פרשמרקט, פז: url.publishedprices.co.il (username בלבד)
- קרפור: prices.carrefour.co.il (אתר שקיפות עצמאי)
- חצי חינם: shop.hazi-hinam.co.il/Prices (אתר שקיפות עצמאי, קישורי blob ישירים)
- ויקטורי / מחסני השוק: laibcatalog.co.il (אתר שקיפות עצמאי) - טרם הוטמע

שימוש:
    python3 scraper.py --chains shufersal,rami-levy --limit 3
    python3 scraper.py --all
"""
import argparse, gzip, os, re, sqlite3, sys, time
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / "data"
DB_PATH  = Path(__file__).parent / "prices.db"
DATA_DIR.mkdir(exist_ok=True)

# ─── הגדרות רשתות ────────────────────────────────────────
CHAINS = {
    "shufersal": {
        "he_name": "שופרסל",
        "type":    "shufersal",
        "url":     "https://prices.shufersal.co.il/FileObject/UpdateCategory?catID=2&storeId=0",
    },
    "rami-levy":  {"he_name": "רמי לוי",   "type": "cerberus", "username": "RamiLevi"},
    "yohananof":  {"he_name": "יוחננוף",   "type": "cerberus", "username": "yohananof"},
    "victory":    {"he_name": "ויקטורי",   "type": "cerberus", "username": "Victory"},
    "osher-ad":   {"he_name": "אושר עד",   "type": "cerberus", "username": "osherad"},
    "tiv-taam":   {"he_name": "טיב טעם",   "type": "cerberus", "username": "TivTaam"},
    "keshet":      {"he_name": "קשת טעמים", "type": "cerberus", "username": "keshet"},
    "freshmarket": {"he_name": "פרשמרקט",  "type": "cerberus", "username": "freshmarket"},
    "paz":         {"he_name": "פז / Yellow", "type": "cerberus", "username": "Paz"},
    # ─── נוספו 24/09/2026 ───
    "carrefour":  {"he_name": "קרפור",    "type": "carrefour",
                   "url": "https://prices.carrefour.co.il/"},
    "hazi-hinam": {"he_name": "חצי חינם",  "type": "hazi-hinam",
                   "url": "https://shop.hazi-hinam.co.il/Prices",
                   "blob": "https://hazihinamprod01.blob.core.windows.net/regulatories"},
}

# ─── DB ─────────────────────────────────────────────────
# ─── סינון: רק רשתות שמוכרות גם אונליין ───
# אותה רשימה בדיוק כמו ב-app.py. כדי לסרוק את כל הרשתות: --all
ONLINE_CHAINS = ["shufersal", "rami-levy", "yohananof", "tiv-taam",
                 "keshet", "freshmarket", "paz",
                 "carrefour", "hazi-hinam"]
ONLINE_ONLY = True


def active_chains(all_chains=False):
    """רשימת הרשתות לסריקה: רק אונליין כברירת מחדל."""
    if all_chains or not ONLINE_ONLY:
        return list(CHAINS.keys())
    _online = [c for c in CHAINS.keys() if c in ONLINE_CHAINS]
    return _online or list(CHAINS.keys())


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS prices (
        chain      TEXT NOT NULL,
        store_id   TEXT NOT NULL,
        barcode    TEXT NOT NULL,
        name       TEXT,
        brand      TEXT,
        price      REAL,
        unit       TEXT,
        qty        REAL,
        updated_at TEXT,
        PRIMARY KEY (chain, store_id, barcode)
    );
    CREATE INDEX IF NOT EXISTS idx_barcode ON prices(barcode);
    CREATE INDEX IF NOT EXISTS idx_name    ON prices(name);
    CREATE INDEX IF NOT EXISTS idx_chain   ON prices(chain);

    -- ─── v8: מבצעים + היסטוריית מחירים ───
    CREATE TABLE IF NOT EXISTS promos (
        chain      TEXT NOT NULL,
        barcode    TEXT NOT NULL,
        promo_id   TEXT NOT NULL,
        min_qty    REAL,
        price      REAL,          -- המחיר הכולל לכמות min_qty
        descr      TEXT,
        ends       TEXT,
        PRIMARY KEY (chain, barcode, promo_id)
    ) WITHOUT ROWID;
    CREATE INDEX IF NOT EXISTS idx_promo_bc ON promos(barcode);

    CREATE TABLE IF NOT EXISTS scrape_log (
        chain     TEXT PRIMARY KEY,
        last_run  TEXT,
        files     INTEGER,
        items     INTEGER,
        error     TEXT
    );
    """)
    conn.commit()
    return conn


# ─── שופרסל (שרת פתוח) ─────────────────────────────────
def _pick_newest(urls, limit, store_idx=1):
    """ממיין לפי חתימת התאריך בשם הקובץ, מסיר כפילויות לפי סניף ומחזיר את החדשים ביותר."""
    def key(u):
        name = u.split("/")[-1].split("?")[0]
        m = re.search(r"(\d{8})[-_]?(\d{6})", name) or re.search(r"(\d{8})", name)
        ts = "".join(m.groups()) if m else "0000"
        parts = name.replace(".gz", "").split("-")
        store = parts[store_idx] if len(parts) > store_idx else name
        return ts, store
    seen, out = set(), []
    for u in sorted(urls, key=key, reverse=True):
        _, store = key(u)
        if store in seen:
            continue
        seen.add(store)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def list_shufersal_files(limit=3):
    r = requests.get(CHAINS["shufersal"]["url"], timeout=30)
    r.raise_for_status()
    links = [unescape(l) for l in re.findall(r'href="([^"]+PriceFull[^"]+\.gz[^"]*)"', r.text)]
    return _pick_newest(links, limit)


# ─── Cerberus – url.publishedprices.co.il ──────────────
def cerberus_session(username):
    """מתחבר לפורטל שקיפות המחירים (username בלבד) ומחזיר session + csrftoken עדכני."""
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    resp = s.get("https://url.publishedprices.co.il/login", timeout=30)
    csrf = BeautifulSoup(resp.text, "html.parser").find("meta", {"name": "csrftoken"})
    if not csrf:
        raise RuntimeError("csrftoken not found")
    s.post("https://url.publishedprices.co.il/login/user",
           data={"username": username, "password": "", "csrftoken": csrf["content"]},
           timeout=30)
    page = s.get("https://url.publishedprices.co.il/file", timeout=30)
    fresh = BeautifulSoup(page.text, "html.parser").find("meta", {"name": "csrftoken"})
    return s, (fresh["content"] if fresh else csrf["content"])


def list_cerberus_files(username, limit=3, search="PriceFull"):
    """מחזיר את כתובות ההורדה של הקבצים החדשים ביותר (סניף אחד לכל קובץ)."""
    s, token = cerberus_session(username)
    r = s.post("https://url.publishedprices.co.il/file/json/dir",
               data={"sEcho": 1, "iColumns": 5, "iDisplayStart": 0,
                     "iDisplayLength": 200, "sSearch": search, "csrftoken": token},
               timeout=30)
    rows = r.json().get("aaData") or []
    names = []
    for row in rows:
        name = row.get("fname") if isinstance(row, dict) else None
        if not name:
            m = re.search(r'href="([^"]+\.gz)"', str(row))
            name = m.group(1) if m else None
        if name and name.lower().endswith(".gz"):
            names.append("https://url.publishedprices.co.il/file/d/" + name)
    return _pick_newest(names, limit), s


def list_carrefour_files(limit=3, kind="PriceFull"):
    """קרפור: השמות במערך JS בעמוד הבית; הקישור = origin + '/' + path + '/' + name.
    האתר מחזיר 404 זמני תחת עומס - לכן מאמתים עם ניסיונות חוזרים."""
    cfg = CHAINS["carrefour"]
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    r = s.get(cfg["url"], timeout=45)
    r.raise_for_status()
    m = re.search(r"const path\s*=\s*'([^']+)'", r.text)
    folder = m.group(1) if m else datetime.now().strftime("%Y%m%d")
    names = [n for n in re.findall(r'"name"\s*:\s*"([^"]+\.gz)"', r.text) if n.startswith(kind)]
    if not names:
        names = re.findall(r"(" + kind + r"[^\"'\s<>]*\.gz)", r.text)
    names = sorted({n.split("/")[-1] for n in names},
                   key=lambda n: (re.search(r"(\d{8})-(\d{6})", n).group(0)
                                  if re.search(r"(\d{8})-(\d{6})", n) else "0"), reverse=True)

    def _url(n):
        # התאריך שבשם הקובץ (-YYYYMMDD-) — לא 8 הספרות הראשונות של קוד הרשת (באג שגרם ל-404)
        d = re.search(r"-(20\d{6})-\d{4,6}\.gz$", n) or re.search(r"-(20\d{6})", n)
        return f"{cfg['url'].rstrip('/')}/{d.group(1) if d else folder}/{n}"

    urls, seen = [], set()
    for n in names:
        if len(urls) >= limit:
            break
        parts = n.replace(".gz", "").split("-")
        store = parts[2] if len(parts) > 2 else n
        if store in seen:
            continue
        seen.add(store)
        urls.append(_url(n))
    if not urls and names:
        for n in names:
            parts = n.replace(".gz", "").split("-")
            store = parts[2] if len(parts) > 2 else n
            if store in seen:
                continue
            seen.add(store)
            urls.append(_url(n))
            if len(urls) >= limit:
                break
    return urls





BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")



# ─── חצי חינם — אתר מוגן Cloudflare. מנסים requests, ואם נחסם — דפדפן אמיתי (Playwright) ───
# אם שניהם נחסמים: מחזירים רשימה ריקה — הרשת מדולגת והמחירים הקיימים שלה נשארים במסד.
def _hazi_rows_from_html(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    out = []
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        a = tr.find("a", href=True)
        if len(tds) >= 3 and a:
            out.append((tds[2].get_text(strip=True), a["href"]))
    return out


def _hazi_fetch(url):
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": BROWSER_UA, "Accept-Language": "he-IL,he;q=0.9"})
        if r.status_code == 200 and "<table" in r.text:
            return r.text
    except Exception:
        pass
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
            pg = b.new_context(user_agent=BROWSER_UA, locale="he-IL", timezone_id="Asia/Jerusalem").new_page()
            pg.goto(url, timeout=90000, wait_until="domcontentloaded")
            for _ in range(20):
                pg.wait_for_timeout(2000)
                if pg.query_selector("table tbody tr"):
                    break
            html = pg.content()
            b.close()
            return html if "<table" in html else None
    except Exception as e:
        print(f"  ! חצי חינם (דפדפן): {e}")
        return None


def list_hazi_hinam_files(limit=3, kind="PriceFull"):
    """kind: PriceFull / PromoFull. t=1 מחירים, t=2 מבצעים."""
    cfg = CHAINS["hazi-hinam"]
    t = "2" if kind.startswith("Promo") else "1"
    rows = []
    for back in (0, 1):
        d = (datetime.now() - timedelta(days=back)).strftime("%Y-%m-%d")
        html = _hazi_fetch(f"{cfg['url']}?d={d}&t={t}&f=null")
        if html:
            rows += _hazi_rows_from_html(html)
        if rows:
            break
    if not rows:
        print("  ⚠️ חצי חינם חסמה את הגישה — נשארים המחירים מהסריקה הקודמת")
        return []
    urls = [urljoin(cfg["url"], href) for name, href in rows if kind in name or (kind == "PriceFull" and "Price" in name)]
    return _pick_newest(urls, limit, store_idx=2)


def download(url, dest, session=None, attempts=3):
    """מוריד קובץ עם ניסיונות חוזרים וכותרת דפדפן (חלק מהאתרים חוסמים User-Agent רובוטי)."""
    last = None
    for _i in range(attempts):
        try:
            if session is not None:
                r = session.get(url, timeout=90)
            else:
                r = requests.get(url, timeout=90, headers={"User-Agent": BROWSER_UA,
                                                           "Accept": "*/*"})
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            return len(r.content)
        except Exception as e:
            last = e
            time.sleep(2.0)
    raise last


def parse_pricefull(path):
    """מפרסר קובץ PriceFull.gz בזרימה (iterparse) - צריכת זיכרון נמוכה."""
    store_id = "0"
    items = []
    try:
        with gzip.open(path, "rb") as f:
            if f.read(3) != b"\xef\xbb\xbf":    # לחלק מהקבצים יש BOM (למשל קרפור)
                f.seek(0)
            for _, el in ET.iterparse(f, events=("end",)):
                tag = el.tag.split("}")[-1]
                if tag == "StoreID" and store_id == "0":
                    store_id = (el.text or "").strip() or "0"
                elif tag == "Item":
                    try:
                        price = float(el.findtext("ItemPrice") or 0)
                    except ValueError:
                        price = 0
                    barcode = (el.findtext("ItemCode") or "").strip()
                    if barcode and price > 0:
                        items.append({
                            "barcode":    barcode,
                            "name":       (el.findtext("ItemName") or "").strip(),
                            "brand":      (el.findtext("ManufactureName") or el.findtext("ManufacturerName") or "").strip(),
                            "price":      price,
                            "unit":       (el.findtext("UnitOfMeasure") or el.findtext("UnitQty") or "").strip(),
                            "qty":        float(el.findtext("Quantity") or 0),
                            "updated_at": el.findtext("PriceUpdateTime") or "",
                        })
                    el.clear()
    except Exception as e:
        print(f"  ! parse error: {e}")
        return None, []
    if not items:
        return None, []
    return store_id, items



# ═══════════════════════════════════════════════════════
# v8 — מבצעים (PromoFull) · לכלל הלקוחות בלבד, בלי קופונים ומועדונים
# ═══════════════════════════════════════════════════════
def list_promo_files(chain_key, limit=1):
    cfg = CHAINS[chain_key]
    if cfg["type"] == "shufersal":
        r = requests.get(cfg["url"].replace("catID=2", "catID=4"), timeout=30)
        links = [unescape(l) for l in re.findall(r'href="([^"]+PromoFull[^"]+\.gz[^"]*)"', r.text)]
        if not links:
            r = requests.get(cfg["url"].replace("catID=2", "catID=3"), timeout=30)
            links = [unescape(l) for l in re.findall(r'href="([^"]+Promo[^"]+\.gz[^"]*)"', r.text)]
        return _pick_newest(links, limit), None
    if cfg["type"] == "cerberus":
        return list_cerberus_files(cfg["username"], limit, search="PromoFull")
    if cfg["type"] == "carrefour":
        return list_carrefour_files(limit, kind="PromoFull"), None
    if cfg["type"] == "hazi-hinam":
        return list_hazi_hinam_files(limit, kind="PromoFull"), None
    return [], None


def _num(x):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def parse_promofull(path):
    """[(barcode, promo_id, min_qty, price_total, descr, ends)] — רק מבצעים כמותיים/מחיר לכלל הלקוחות."""
    out = []
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with gzip.open(path, "rb") as f:
            if f.read(3) != b"\xef\xbb\xbf":
                f.seek(0)
            for _, el in ET.iterparse(f, events=("end",)):
                if el.tag.split("}")[-1] != "Promotion":
                    continue
                g = lambda t: (el.findtext(t) or el.findtext(".//" + t) or "").strip()
                club = g("ClubID")
                if club and not club.startswith("0"):          # מועדון בלבד
                    el.clear(); continue
                if g("AdditionalIsCoupon") == "1":               # קופון
                    el.clear(); continue
                ends = g("PromotionEndDateTime")[:10]
                if ends and ends < today:
                    el.clear(); continue
                pid, descr = g("PromotionID"), g("PromotionDescription")
                min_qty_top = _num(g("MinQty")) or 1.0
                for it in el.iter():
                    if it.tag.split("}")[-1] not in ("PromotionItem", "Item"):
                        continue
                    bc = (it.findtext("ItemCode") or "").strip()
                    if not bc or set(bc) == {"0"}:
                        continue
                    mq = _num(it.findtext("MinQty")) or min_qty_top or 1.0
                    dp = _num(it.findtext("DiscountedPrice")) or _num(g("DiscountedPrice"))
                    if not dp or dp <= 0 or mq <= 0:
                        continue
                    # DiscountedPrice הוא לרוב המחיר הכולל לכמות ("2 ב-20" → 20). אם נראה כמחיר ליחידה — מכפילים
                    total = dp if mq == 1 or "ב" in descr else dp * mq
                    out.append((bc, pid, mq, round(total, 2), descr, ends))
                el.clear()
    except Exception as e:
        print(f"  ! promo parse error: {e}")
    return out


def scrape_promos(chain_key, conn, limit=1):
    try:
        urls, session = list_promo_files(chain_key, limit)
    except Exception as e:
        print(f"  ! promos list: {e}")
        return 0
    if not urls:
        return 0
    conn.execute("DELETE FROM promos WHERE chain = ?", (chain_key,))
    n = 0
    for url in urls:
        fname = "promo_" + url.split("/")[-1].split("?")[0]
        path = DATA_DIR / chain_key / fname
        try:
            download(url, path, session=session)
            rows = parse_promofull(path)
            conn.executemany("INSERT OR REPLACE INTO promos VALUES (?,?,?,?,?,?,?)",
                             [(chain_key,) + r for r in rows])
            n += len(rows)
        except Exception as e:
            print(f"  ! promo {fname}: {e}")
    conn.commit()
    print(f"  ✓ מבצעים: {n}")
    return n


HISTORY_PATH = Path(__file__).parent / "history.db"


def snapshot_history(conn, keep_days=400, history_path=None, day=None):
    """תמונת מצב יומית לקובץ נפרד (history.db): מחיר ממוצע + גודל לכל ברקוד ורשת.
    נשמר רק מה שהשתנה מאז הפעם הקודמת — כך הקובץ נשאר קטן גם אחרי חודשים."""
    hp = str(history_path or HISTORY_PATH)
    day = day or datetime.now().strftime("%Y-%m-%d")
    conn.execute("ATTACH DATABASE ? AS hist", (hp,))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS hist.price_history (
            chain TEXT NOT NULL, barcode TEXT NOT NULL, day TEXT NOT NULL,
            price REAL, qty REAL, PRIMARY KEY (chain, barcode, day)) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS hist.idx_hist_day ON price_history(day);
        -- שם + יחידה נשמרים רק כשהם משתנים (לזיהוי שרינקפלציה)
        CREATE TABLE IF NOT EXISTS hist.product_names (
            barcode TEXT NOT NULL, day TEXT NOT NULL, name TEXT, unit TEXT,
            PRIMARY KEY (barcode, day)) WITHOUT ROWID;
    """)
    # ריצה שנייה באותו יום: מוחקים קודם את היום, ורק אז משווים לתמונה הקודמת
    conn.execute("DELETE FROM hist.price_history WHERE day = ?", (day,))
    conn.execute("DELETE FROM hist.product_names WHERE day = ?", (day,))
    conn.executescript("""
        DROP TABLE IF EXISTS temp._today;
        CREATE TEMP TABLE _today AS
            SELECT chain, barcode, ROUND(AVG(price), 2) AS price, MAX(qty) AS qty, MAX(unit) AS unit, MAX(name) AS name
            FROM main.prices WHERE price > 0 GROUP BY chain, barcode;
        DROP TABLE IF EXISTS temp._last;
        CREATE TEMP TABLE _last AS
            SELECT h.chain, h.barcode, h.price, h.qty FROM hist.price_history h
            JOIN (SELECT chain, barcode, MAX(day) AS d FROM hist.price_history GROUP BY chain, barcode) m
              ON m.chain = h.chain AND m.barcode = h.barcode AND m.d = h.day;
    """)
    conn.execute("""
        INSERT INTO hist.price_history (chain, barcode, day, price, qty)
        SELECT t.chain, t.barcode, ?, t.price, t.qty
        FROM temp._today t LEFT JOIN temp._last l ON l.chain = t.chain AND l.barcode = t.barcode
        WHERE l.barcode IS NULL OR ABS(l.price - t.price) >= 0.005 OR IFNULL(l.qty, 0) != IFNULL(t.qty, 0)
    """, (day,))
    conn.executescript("""
        DROP TABLE IF EXISTS temp._names;
        CREATE TEMP TABLE _names AS SELECT barcode, MAX(name) AS name, MAX(unit) AS unit FROM temp._today GROUP BY barcode;
        DROP TABLE IF EXISTS temp._lastname;
        CREATE TEMP TABLE _lastname AS
            SELECT n.barcode, n.name FROM hist.product_names n
            JOIN (SELECT barcode, MAX(day) AS d FROM hist.product_names GROUP BY barcode) m
              ON m.barcode = n.barcode AND m.d = n.day;
    """)
    conn.execute("""
        INSERT OR REPLACE INTO hist.product_names (barcode, day, name, unit)
        SELECT t.barcode, ?, t.name, t.unit FROM temp._names t
        LEFT JOIN temp._lastname l ON l.barcode = t.barcode
        WHERE l.barcode IS NULL OR IFNULL(l.name, '') != IFNULL(t.name, '')
    """, (day,))
    conn.execute("DELETE FROM hist.price_history WHERE day < date('now', ?)", (f"-{int(keep_days)} days",))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM hist.price_history WHERE day = ?", (day,)).fetchone()[0]
    conn.execute("DETACH DATABASE hist")
    print(f"\n📈 היסטוריה ({Path(hp).name}): נשמרו {n:,} שינויים ליום {day}")


# ─── פונקציה מרכזית ───────────────────────────────────
def scrape_chain(chain_key, conn, limit=3):
    cfg = CHAINS[chain_key]
    chain_dir = DATA_DIR / chain_key
    chain_dir.mkdir(exist_ok=True)
    print(f"\n[{cfg['he_name']}]")
    total_items = 0
    files = []
    session = None
    try:
        if cfg["type"] == "shufersal":
            urls = list_shufersal_files(limit)
        elif cfg["type"] == "carrefour":
            urls = list_carrefour_files(limit)
        elif cfg["type"] == "hazi-hinam":
            urls = list_hazi_hinam_files(limit)
        else:
            urls, session = list_cerberus_files(cfg["username"], limit)
        print(f"  Found {len(urls)} files")
        for url in urls:
            fname = url.split("/")[-1].split("?")[0]
            path = chain_dir / fname
            try:
                size = download(url, path, session=session)
                store_id, items = parse_pricefull(path)
                if store_id is None:
                    continue
                # insert
                conn.executemany("""
                    INSERT OR REPLACE INTO prices
                    (chain, store_id, barcode, name, brand, price, unit, qty, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [(chain_key, store_id, i["barcode"], i["name"], i["brand"],
                       i["price"], i["unit"], i["qty"], i["updated_at"]) for i in items])
                conn.commit()
                total_items += len(items)
                print(f"  ✓ store={store_id}: {len(items)} items ({size//1024}KB)")
                files.append(fname)
            except Exception as e:
                print(f"  ! {fname}: {e}")
        conn.execute("INSERT OR REPLACE INTO scrape_log VALUES (?,?,?,?,?)",
                     (chain_key, datetime.now().isoformat(), len(files), total_items, None))
        conn.commit()
        return total_items
    except Exception as e:
        conn.execute("INSERT OR REPLACE INTO scrape_log VALUES (?,?,?,?,?)",
                     (chain_key, datetime.now().isoformat(), 0, 0, str(e)))
        conn.commit()
        print(f"  ✗ ERROR: {e}")
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", default="", help="פסיק-מופרד: shufersal,rami-levy,... (ריק = רק רשתות אונליין)")
    ap.add_argument("--limit", type=int, default=3, help="קבצים לרשת (סניפים)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-promos", action="store_true", help="בלי הורדת מבצעים")
    args = ap.parse_args()

    conn = init_db()
    if args.all:
        chains = list(CHAINS.keys())
    elif args.chains.strip():
        chains = [c.strip() for c in args.chains.split(",") if c.strip()]
    else:
        chains = active_chains()
        _skipped = [c for c in CHAINS.keys() if c not in chains]
        print(f"ℹ️ סורק רק רשתות שמוכרות אונליין ({len(chains)}): {', '.join(chains)}")
        if _skipped:
            print(f"⏭️ מדלג על {len(_skipped)}: {', '.join(_skipped)}   (לסרוק הכל: --all)")
    total = 0
    for c in chains:
        if c not in CHAINS:
            print(f"Unknown chain: {c}")
            continue
        total += scrape_chain(c, conn, args.limit)
        if not args.no_promos:
            scrape_promos(c, conn, 1)
    print(f"\n=== Total items across all chains: {total} ===")
    snapshot_history(conn)


if __name__ == "__main__":
    main()
