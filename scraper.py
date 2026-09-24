name: עדכון מחירי רשתות אונליין

# רץ כל יום ב-06:00 שעון ישראל (03:00 UTC) וגם בלחיצה ידנית מלשונית Actions
on:
  schedule:
    - cron: "0 3 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 90

    steps:
      - name: הורדת הקוד
        uses: actions/checkout@v4

      - name: התקנת Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: התקנת תלויות
        run: pip install requests lxml beautifulsoup4 rapidfuzz

      - name: סריקה - 7 רשתות שמוכרות אונליין
        run: python scraper.py --limit 2

      - name: איתור ובדיקת המסד שנבנה
        run: |
          set -e
          DBFILE=$(find . -maxdepth 3 -name 'prices*.db' -printf '%s %p\n' | sort -rn | head -1 | cut -d' ' -f2-)
          if [ -z "$DBFILE" ]; then echo "לא נמצא קובץ מסד"; find . -maxdepth 3 -name '*.db' -ls; exit 1; fi
          echo "DBFILE=$DBFILE" >> "$GITHUB_ENV"
          ls -lh "$DBFILE"
          python -c "import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);print('רשתות:',[r[0] for r in c.execute('SELECT DISTINCT chain FROM prices')]);print('שורות:',c.execute('SELECT COUNT(*) FROM prices').fetchone()[0])" "$DBFILE"

      - name: דחיפה לענף data כקומיט בודד (בלי לנפח את ההיסטוריה)
        run: |
          set -e
          git config user.name "sal-mashve-bot"
          git config user.email "actions@github.com"
          git checkout --orphan data_push
          git rm -rf --cached . >/dev/null 2>&1 || true
          git add -f "$DBFILE"
          git mv "$DBFILE" prices.db 2>/dev/null || { cp "$DBFILE" prices.db && git add -f prices.db; }
          git commit -m "עדכון מחירים אוטומטי $(date -u '+%Y-%m-%d %H:%M UTC')"
          git push -f origin data_push:data
