"""
backfill_history.py – בונה את history.db מגרסאות ישנות של prices.db (חד-פעמי).

למה: ההיסטוריה נאספת מהסריקה היומית קדימה. כדי שלשונית "מה השתנה" לא תתחיל ריקה,
הכלי הזה מוריד את הגרסאות הקודמות של קובצי המסד מהריפו בגיטהאב, ומכניס כל אחת
כ"תמונת מצב" לפי התאריך שבה היא הועלתה.

הרצה (פעם אחת — ה-workflow עושה את זה אוטומטית אם history.db עוד לא קיים):
    python tools/backfill_history.py --repo tsippiz-star/sal-mashve --out history.db
"""
import argparse
import json
import sqlite3
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scraper  # noqa: E402  (snapshot_history)


def _get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "sal-mashve-backfill"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if raw else json.loads(data)


def list_versions(repo, branch="main"):
    """[(date, sha, path)] לכל גרסה של כל קובץ prices*.db שהיה אי פעם בריפו."""
    tree = _get(f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1")
    paths = [t["path"] for t in tree.get("tree", []) if t["path"].startswith("prices") and t["path"].endswith(".db")]
    out = []
    for p in paths:
        commits = _get(f"https://api.github.com/repos/{repo}/commits?path={urllib.parse.quote(p)}&per_page=100")
        for c in commits:
            out.append((c["commit"]["committer"]["date"][:10], c["sha"], p))
    return sorted(set(out))


def chains_in(db):
    try:
        c = sqlite3.connect(db)
        n = c.execute("SELECT COUNT(DISTINCT chain) FROM prices").fetchone()[0]
        c.close()
        return n
    except Exception:
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="tsippiz-star/sal-mashve")
    ap.add_argument("--out", default="history.db")
    ap.add_argument("--min-chains", type=int, default=3, help="לדלג על קבצים ישנים עם מעט רשתות")
    args = ap.parse_args()

    versions = list_versions(args.repo)
    print(f"נמצאו {len(versions)} גרסאות של קובצי מסד")
    # לכל תאריך — הגרסה עם הכי הרבה רשתות
    best = {}
    tmp = Path(tempfile.mkdtemp())
    for day, sha, path in versions:
        f = tmp / f"{sha[:10]}.db"
        try:
            f.write_bytes(_get(f"https://raw.githubusercontent.com/{args.repo}/{sha}/{urllib.parse.quote(path)}", raw=True))
        except Exception as e:
            print(f"  ! {path}@{sha[:7]}: {e}")
            continue
        n = chains_in(f)
        print(f"  {day}  {path:<18} {n} רשתות")
        if n >= args.min_chains and n >= best.get(day, (0, None))[0]:
            best[day] = (n, f)

    for day in sorted(best):
        conn = sqlite3.connect(best[day][1])
        scraper.snapshot_history(conn, keep_days=100000, history_path=args.out, day=day)
        conn.close()

    c = sqlite3.connect(args.out)
    c.execute("VACUUM")
    days = [r[0] for r in c.execute("SELECT DISTINCT day FROM price_history ORDER BY day")]
    c.close()
    print(f"\n✓ {args.out}: {len(days)} ימי היסטוריה — {', '.join(days)}")


if __name__ == "__main__":
    main()
