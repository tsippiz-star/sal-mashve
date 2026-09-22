"""
scraper.py – מוריד קבצי "שקיפות מחירים" מ-6 רשתות המזון בישראל
ומכניס את המחירים לבסיס נתונים SQLite.

מקורות:
- שופרסל: prices.shufersal.co.il (ציבורי, ללא התחברות)
- רמי לוי, יוחננוף, ויקטורי, אושר עד, טיב טעם: url.publishedprices.co.il (username בלבד)

שימוש:
    python3 scraper.py --chains shufersal,rami-levy --limit 3
    python3 scraper.py --all
"""
import argparse, gzip, os, re, sqlite3, sys, time
from datetime import datetime
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
}

# ─── DB ─────────────────────────────────────────────────
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
def _pick_newest(urls, limit):
    """ממיין לפי חתימת התאריך בשם הקובץ, מסיר כפילויות לפי סניף ומחזיר את החדשים ביותר."""
    def key(u):
        name = u.split("/")[-1].split("?")[0]
        m = re.search(r"(\d{8})[-_]?(\d{6})", name) or re.search(r"(\d{8})", name)
        ts = "".join(m.groups()) if m else "0000"
        parts = name.replace(".gz", "").split("-")
        store = parts[1] if len(parts) > 1 else name
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


def download(url, dest, session=None):
    r = (session or requests).get(url, timeout=90)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    return len(r.content)


def parse_pricefull(path):
    """מפרסר קובץ PriceFull.gz בזרימה (iterparse) - צריכת זיכרון נמוכה."""
    store_id = "0"
    items = []
    try:
        with gzip.open(path, "rb") as f:
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
    ap.add_argument("--chains", default="shufersal", help="פסיק-מופרד: shufersal,rami-levy,...")
    ap.add_argument("--limit", type=int, default=3, help="קבצים לרשת (סניפים)")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    conn = init_db()
    chains = list(CHAINS.keys()) if args.all else args.chains.split(",")
    total = 0
    for c in chains:
        if c not in CHAINS:
            print(f"Unknown chain: {c}")
            continue
        total += scrape_chain(c, conn, args.limit)
    print(f"\n=== Total items across all chains: {total} ===")


if __name__ == "__main__":
    main()
