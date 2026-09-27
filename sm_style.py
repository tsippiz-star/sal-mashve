"""
sm_style.py – שכבת העיצוב של "סל משווה" (v7).
CSS גלובלי + פונקציות קטנות שמייצרות HTML לכרטיסים.
אין כאן לוגיקה עסקית — רק תצוגה.
"""
import html as _html

import streamlit as st

# ─── צבע לכל רשת (גוון oklch) ───
CHAIN_HUE = {
    "rami-levy": 28, "osher-ad": 255, "hazi-hinam": 350, "yohananof": 145,
    "carrefour": 230, "keshet": 300, "shufersal": 5, "freshmarket": 170,
    "tiv-taam": 55, "paz": 85, "victory": 200,
}

PRODUCE_EMOJI = {
    "עגבניות": "🍅", "מלפפונים": "🥒", "בננות": "🍌", "תפוחים": "🍎",
    "תפוחי אדמה": "🥔", "תפוזים": "🍊", "גזר": "🥕", "בצל": "🧅",
    "פלפלים": "🫑", "ענבים": "🍇", "אגסים": "🍐", "לימונים": "🍋",
    "אבוקדו": "🥑", "כרוב": "🥬", "קישואים": "🥒", "חציל": "🍆",
    "תירס": "🌽", "פטריות": "🍄", "מנגו": "🥭", "אבטיח": "🍉",
    "מלון": "🍈", "תות שדה": "🍓",
}

esc = _html.escape


def fmt(n):
    if n is None:
        return "—"
    return f"{float(n):,.2f}"


def md(s):
    """מציג HTML. מקפל לשורה אחת — כדי ש-Markdown לא יהפוך הזחה לבלוק קוד."""
    s = " ".join(line.strip() for line in str(s).splitlines() if line.strip())
    st.markdown(s, unsafe_allow_html=True)


def chain_mark(cid, name, lg=False):
    hue = CHAIN_HUE.get(cid, 160)
    letter = esc((name or cid or "?").strip()[:1])
    return (f'<span class="cm{" lg" if lg else ""}" '
            f'style="background:oklch(0.58 0.13 {hue})">{letter}</span>')


# ════════════════════════════════════════════════
# CSS
# ════════════════════════════════════════════════
CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700&family=Rubik:wght@500;600;700&display=swap');
:root{
  --green:oklch(0.52 0.11 162); --green-ink:oklch(0.38 0.08 162);
  --green-soft:oklch(0.955 0.03 162); --green-softer:oklch(0.978 0.015 162);
  --amber:oklch(0.78 0.13 70); --amber-soft:oklch(0.96 0.045 80); --amber-ink:oklch(0.48 0.1 60);
  --red-ink:oklch(0.5 0.14 30); --red-soft:oklch(0.96 0.03 30);
  --bg:#FBFAF6; --card:#FFFFFF; --ink:#17231E; --ink-2:#4B5B54; --ink-3:#85938C;
  --line:#E9EDE8; --line-2:#DCE3DD;
  --shadow:0 1px 2px rgba(23,35,30,.04),0 8px 24px rgba(23,35,30,.06);
  --shadow-lg:0 2px 4px rgba(23,35,30,.05),0 20px 48px rgba(23,35,30,.14);
  --font:"Heebo","Rubik","Arial Hebrew",sans-serif; --font-d:"Rubik","Heebo",sans-serif;
}

/* ---------- בסיס ---------- */
html,body,.stApp,[class*="css"],button,input,textarea,select{font-family:var(--font)!important}
.stApp{background:var(--bg)!important;color:var(--ink)}
.stApp,.main,[data-testid="stMain"],.block-container,[data-testid="stMainBlockContainer"]{direction:rtl}
[data-testid="stMarkdownContainer"],.stMarkdown,[data-testid="stCaptionContainer"]{text-align:right}
[data-testid="stHeader"]{background:transparent!important}
.block-container,[data-testid="stMainBlockContainer"]{max-width:1240px!important;padding:1.4rem 1.75rem 6rem!important}
.num{font-variant-numeric:tabular-nums}
[data-testid="stMarkdownContainer"] p{margin-bottom:0}
.stMarkdown,[data-testid="stMarkdown"]{margin-bottom:0!important}
[data-testid="stMarkdownContainer"]>div:last-child{margin-bottom:0!important}
[data-testid="stCaptionContainer"]{color:var(--ink-3)!important}
hr{border-color:var(--line)!important}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#CBD5CF;border-radius:8px}

/* ---------- כפתורים ---------- */
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button,[data-testid="stPopover"] button,[data-testid="stPopoverButton"]{
  border-radius:999px!important;border:1px solid var(--line-2)!important;background:#fff!important;color:var(--ink)!important;
  font-weight:600!important;min-height:44px;padding:.4rem 1.1rem!important;box-shadow:none!important;transition:all .15s!important}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stPopover"] button:hover{border-color:var(--green)!important;color:var(--green-ink)!important}
.stButton>button p,.stDownloadButton>button p,[data-testid="stPopover"] button p{font-weight:inherit!important;font-size:14.5px!important}
button[kind="primary"],button[kind="primaryFormSubmit"],[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"]{
  background:var(--green)!important;border-color:var(--green)!important;color:#fff!important;
  box-shadow:0 6px 16px color-mix(in oklch,var(--green) 30%,transparent)!important}
button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover,[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:var(--green-ink)!important;color:#fff!important}

/* ---------- שדות ---------- */
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div,[data-baseweb="base-input"]{
  border-radius:16px!important;border-color:var(--line-2)!important;background:var(--green-softer)!important}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within{border-color:var(--green)!important;background:#fff!important;box-shadow:0 0 0 4px color-mix(in oklch,var(--green) 14%,transparent)!important}
[data-baseweb="input"] input,textarea{direction:rtl;text-align:right;font-size:16px!important;background:transparent!important}
[data-testid="stWidgetLabel"] p{font-weight:600!important;color:var(--ink-2)!important;font-size:14px!important}
[data-testid="stNumberInput"] button{border-radius:10px!important}
[data-testid="stFileUploader"] section{border-radius:16px!important;border:1.5px dashed var(--line-2)!important;background:var(--green-softer)!important}
[data-testid="stExpander"] details{border:1px solid var(--line)!important;border-radius:18px!important;background:#fff!important;box-shadow:var(--shadow)}
[data-testid="stExpander"] summary{font-weight:600!important;font-size:15px}
[data-testid="stExpander"] summary:hover{color:var(--green-ink)!important}
[data-testid="stDataFrame"]{border-radius:16px!important;overflow:hidden;border:1px solid var(--line)}
div[data-testid="stAlert"]{border-radius:16px!important}
div[role="dialog"],[data-testid="stDialog"] [role="dialog"],[data-testid="stDialog"]>div>div{border-radius:24px!important;direction:rtl}
div[role="dialog"] [data-testid="stMarkdownContainer"],[data-testid="stDialog"] [data-testid="stMarkdownContainer"]{text-align:right}
[data-testid="stPopoverBody"]{border-radius:18px!important;direction:rtl;box-shadow:var(--shadow-lg)!important;border:1px solid var(--line)!important}
.stCheckbox label p{font-size:14.5px!important}

/* ---------- כרטיסים (קונטיינר עם key שמתחיל ב-card) ---------- */
[class*="st-key-card"]{background:var(--card);border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:22px 22px 18px}

/* ---------- כותרת עליונה ---------- */
.st-key-sm_top [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center}
.st-key-sm_top [data-testid="stColumn"],.st-key-sm_top [data-testid="column"]{min-width:0!important}
.st-key-sm_status{align-items:flex-end}
.st-key-sm_status button{min-height:38px!important;padding:4px 14px!important;color:var(--ink-2)!important}
.st-key-sm_status button p{font-size:13px!important;font-weight:500!important}
.logo{display:flex;align-items:center;gap:10px;font-family:var(--font-d);font-weight:700;font-size:22px;letter-spacing:-.2px;white-space:nowrap}
.logo-mark{width:38px;height:38px;border-radius:12px;background:var(--green);display:grid;place-items:center;font-size:19px;box-shadow:0 4px 10px color-mix(in oklch,var(--green) 35%,transparent)}

/* ---------- ניווט ---------- */
.st-key-sm_nav{margin:4px 0 12px;padding-bottom:10px;border-bottom:1px solid var(--line)}
.st-key-sm_nav [data-testid="stButtonGroup"]>div,.st-key-sm_nav [role="radiogroup"]{gap:4px!important;flex-wrap:wrap}
.st-key-sm_nav button{border:0!important;background:transparent!important;border-radius:999px!important;padding:8px 16px!important;
  color:var(--ink-2)!important;min-height:40px;box-shadow:none!important}
.st-key-sm_nav button p{font-size:15px!important;font-weight:500!important;white-space:normal}
.st-key-sm_nav button:hover{background:var(--green-softer)!important;color:var(--ink)!important}
.st-key-sm_nav button[data-testid$="Active"],.st-key-sm_nav button[aria-checked="true"],.st-key-sm_nav button[kind$="Active"]{background:var(--green-soft)!important;color:var(--green-ink)!important}
.st-key-sm_nav button[data-testid$="Active"] p,.st-key-sm_nav button[kind$="Active"] p{font-weight:700!important}

/* ---------- טיפוגרפיה ---------- */
.h-display{font-family:var(--font-d);font-weight:700;font-size:40px;line-height:1.12;letter-spacing:-.6px;margin:6px 0 0;text-wrap:balance;color:var(--ink)}
.h1{font-family:var(--font-d);font-weight:700;font-size:28px;letter-spacing:-.3px;margin:6px 0 0;color:var(--ink)}
.h2{font-family:var(--font-d);font-weight:600;font-size:19px;margin:0;color:var(--ink)}
.sub{color:var(--ink-2);font-size:16px;line-height:1.6;margin:6px 0 14px;text-wrap:pretty}
.tiny{font-size:13px;color:var(--ink-3)}
.sec-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:4px}

/* ---------- רשתות ---------- */
.cm{width:26px;height:26px;border-radius:8px;display:inline-grid;place-items:center;font-size:12.5px;font-weight:700;color:#fff;flex:none;vertical-align:middle}
.cm.lg{width:44px;height:44px;border-radius:13px;font-size:19px}
.chainbar{display:flex;align-items:center;gap:12px}
.chainbar .stack{display:flex}
.chainbar .stack .cm{box-shadow:0 0 0 2px #fff;margin-inline-start:-8px}
.chainbar .stack .cm:first-child{margin-inline-start:0}
.st-key-card_chains [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center}
.st-key-card_chains [data-testid="stColumn"],.st-key-card_chains [data-testid="column"]{min-width:0!important}
.st-key-card_chains [data-testid="stColumn"]:last-child,.st-key-card_chains [data-testid="column"]:last-child{flex:0 0 auto!important;width:auto!important}
.st-key-card_chains{padding:12px 16px!important}
.st-key-card_chains button{min-height:36px!important}

/* ---------- שורות מוצר ברשימה ---------- */
[class*="st-key-row_"],[class*="st-key-srow_"],[class*="st-key-hrow_"]{border-bottom:1px solid var(--line);padding:4px 0 8px;gap:6px!important}
[class*="st-key-row_"] [data-testid="stHorizontalBlock"],[class*="st-key-srow_"] [data-testid="stHorizontalBlock"],[class*="st-key-hrow_"] [data-testid="stHorizontalBlock"],
[class*="st-key-adder"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:6px!important;align-items:center}
/* שורות שלא נשברות במובייל (כותרת עליונה, פס רשתות, כותרת רשימה) */
.st-key-sm_top [data-testid="stHorizontalBlock"],[class*="st-key-card_chains"] [data-testid="stHorizontalBlock"],[class*="st-key-inl"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center}
.st-key-sm_top [data-testid="stColumn"],[class*="st-key-card_chains"] [data-testid="stColumn"],[class*="st-key-inl"] [data-testid="stColumn"],
.st-key-sm_top [data-testid="column"],[class*="st-key-card_chains"] [data-testid="column"],[class*="st-key-inl"] [data-testid="column"]{min-width:0!important;width:auto!important;flex:1 1 auto!important}
.st-key-sm_top [data-testid="stColumn"]:last-child,[class*="st-key-card_chains"] [data-testid="stColumn"]:last-child,[class*="st-key-inl"] [data-testid="stColumn"]:last-child,
.st-key-sm_top [data-testid="column"]:last-child,[class*="st-key-card_chains"] [data-testid="column"]:last-child,[class*="st-key-inl"] [data-testid="column"]:last-child{flex:0 0 auto!important}
[data-testid="InputInstructions"]{display:none!important}
[class*="st-key-row_"] [data-testid="stColumn"],[class*="st-key-row_"] [data-testid="column"],
[class*="st-key-srow_"] [data-testid="stColumn"],[class*="st-key-srow_"] [data-testid="column"],
[class*="st-key-hrow_"] [data-testid="stColumn"],[class*="st-key-hrow_"] [data-testid="column"],
[class*="st-key-adder"] [data-testid="stColumn"],[class*="st-key-adder"] [data-testid="column"]{min-width:0!important;width:auto!important;flex:0 0 auto!important}
[class*="st-key-row_"] [data-testid="stColumn"]:first-child,[class*="st-key-row_"] [data-testid="column"]:first-child,
[class*="st-key-srow_"] [data-testid="stColumn"]:first-child,[class*="st-key-srow_"] [data-testid="column"]:first-child,
[class*="st-key-hrow_"] [data-testid="stColumn"]:first-child,[class*="st-key-hrow_"] [data-testid="column"]:first-child,
[class*="st-key-adder"] [data-testid="stColumn"]:first-child,[class*="st-key-adder"] [data-testid="column"]:first-child{flex:1 1 auto!important}
[class*="st-key-row_"] .stButton>button{min-height:34px!important;width:34px;height:34px;padding:0!important;border-radius:50%!important;font-size:16px}
[class*="st-key-row_"] .stButton>button p{font-size:16px!important}
[class*="st-key-row_"] [data-testid="stColumn"]:last-child .stButton>button{border-color:transparent!important;color:var(--ink-3)!important}
[class*="st-key-row_"] [data-testid="stColumn"]:last-child .stButton>button:hover{background:var(--red-soft)!important;color:var(--red-ink)!important}
[class*="st-key-row_"]:last-of-type{border-bottom:0}
.qty{min-width:34px;text-align:center;font-weight:700;font-size:14.5px;font-variant-numeric:tabular-nums;line-height:34px}
.qty small{font-weight:500;color:var(--ink-3);font-size:11px}
.item{display:flex;align-items:center;gap:12px;min-width:0}
.item-ic{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;font-size:15px;font-weight:700;flex:none}
.item-ic.ok{background:var(--green-soft);color:var(--green-ink)}
.item-ic.unclear{background:var(--amber-soft);color:var(--amber-ink)}
.item-ic.none{background:var(--red-soft);color:var(--red-ink)}
.item-name{font-weight:600;font-size:15.5px;line-height:1.3}
.item-sub{font-size:12.5px;color:var(--ink-3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.item-sub.warn{color:var(--amber-ink);white-space:normal}
.item-sub.err{color:var(--red-ink);white-space:normal}
.item-txt{min-width:0;overflow:hidden}
[class*="st-key-chips_"]{padding-inline-start:46px}
[class*="st-key-chips_"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:6px!important}
[class*="st-key-chips_"] [data-testid="stColumn"],[class*="st-key-chips_"] [data-testid="column"]{flex:0 0 auto!important;width:auto!important;min-width:0!important}
[class*="st-key-chips_"] .stButton>button{min-height:34px!important;padding:4px 12px!important;background:var(--amber-soft)!important;border-color:transparent!important}
[class*="st-key-chips_"] .stButton>button p{font-size:13.5px!important}

/* סלים מוכנים + רשת 2 בטור במובייל */
[class*="st-key-grid2"] .stButton>button{border-radius:16px!important;min-height:70px;width:100%;justify-content:flex-start;text-align:right}
[class*="st-key-grid2"] .stButton>button:hover{transform:translateY(-2px);box-shadow:var(--shadow)!important}
[class*="st-key-grid2"] .stButton>button p{font-size:15px!important;font-weight:700!important}
[class*="st-key-foot"]{border-top:1px dashed var(--line-2);padding-top:12px;margin-top:4px}
[class*="st-key-foot"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:6px!important}
[class*="st-key-foot"] [data-testid="stColumn"],[class*="st-key-foot"] [data-testid="column"]{flex:0 0 auto!important;width:auto!important;min-width:0!important}
[class*="st-key-foot"] button{min-height:36px!important;padding:4px 12px!important;border-color:transparent!important;background:transparent!important;color:var(--ink-2)!important}
[class*="st-key-foot"] button:hover{background:var(--green-softer)!important;color:var(--green-ink)!important}
[class*="st-key-foot"] button p{font-size:13.5px!important}

/* ---------- תוצאות ---------- */
.winner{position:relative;overflow:hidden;border-radius:22px;padding:24px;background:var(--green);color:#fff;box-shadow:0 14px 34px color-mix(in oklch,var(--green) 30%,transparent);margin-bottom:4px}
.winner::after{content:"";position:absolute;inset:auto -60px -90px auto;width:240px;height:240px;border-radius:50%;background:rgba(255,255,255,.07)}
.winner .w-lbl{font-size:14px;opacity:.88}
.winner .w-chain{display:flex;align-items:center;gap:12px;margin-top:8px}
.winner .w-name{font-family:var(--font-d);font-size:32px;font-weight:700;letter-spacing:-.4px}
.winner .w-total{font-family:var(--font-d);font-size:46px;font-weight:700;letter-spacing:-.8px;line-height:1;margin-top:16px}
.winner .w-total small{font-size:22px;font-weight:500;opacity:.85;margin-inline-start:4px}
.savings{display:inline-flex;align-items:center;gap:8px;margin-top:14px;background:var(--amber);color:#3A2600;border-radius:999px;padding:7px 14px;font-weight:700;font-size:14.5px}
.w-note{margin-top:14px;background:rgba(255,255,255,.15);border-radius:12px;padding:10px 12px;font-size:13.5px;line-height:1.55;position:relative;z-index:1}
.rank{display:flex;flex-direction:column;gap:2px;margin-top:10px}
.rank-row{display:grid;grid-template-columns:22px auto minmax(0,1fr) auto;align-items:center;gap:12px;padding:10px 6px;border-radius:12px}
.rank-row.first{background:var(--green-softer)}
.rank-pos{font-size:13px;color:var(--ink-3);font-weight:700;text-align:center}
.rank-name{font-weight:600;font-size:15px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.rank-bar{height:6px;border-radius:999px;background:#EEF1ED;margin-top:6px;overflow:hidden}
.rank-bar i{display:block;height:100%;border-radius:999px;background:var(--green)}
.rank-bar.dim i{background:#C9D3CD}
.rank-price{text-align:left;font-weight:700;font-size:16px;white-space:nowrap}
.rank-diff{font-size:12.5px;color:var(--ink-3);text-align:left}
.badge{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:2px 9px;font-size:12px;font-weight:600}
.badge.warn{background:var(--amber-soft);color:var(--amber-ink)}
.badge.ok{background:var(--green-soft);color:var(--green-ink)}
.bd{border-bottom:1px solid var(--line)}
.bd:last-child{border-bottom:0}
.bd summary{list-style:none;display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:12px;align-items:center;padding:12px 4px;cursor:pointer}
.bd summary::-webkit-details-marker{display:none}
.bd summary:hover .bd-name{color:var(--green-ink)}
.bd-name{font-weight:600;font-size:15px}
.bd-best{font-size:13px;color:var(--ink-3)}
.bd-chev{color:var(--ink-3);transition:transform .2s;font-size:11px}
.bd[open] .bd-chev,.faq[open] .bd-chev{transform:rotate(180deg)}
.bd-body{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px;padding:0 4px 14px}
.bd-cell{display:flex;justify-content:space-between;align-items:center;gap:8px;background:#F6F8F5;border-radius:10px;padding:8px 10px;font-size:13.5px}
.bd-cell.best{background:var(--green-soft);color:var(--green-ink);font-weight:700}
.bd-cell.na{color:var(--ink-3)}
.bd-prod{grid-column:1/-1;font-size:12.5px;color:var(--ink-3);margin-bottom:2px}
.empty{text-align:center;padding:40px 24px}
.empty .em{font-size:44px;margin-bottom:10px}
.miss-line{font-size:14px;line-height:1.6;padding:8px 0;border-bottom:1px dashed var(--line)}
.miss-line:last-child{border-bottom:0}
.sm-alert{display:flex;gap:10px;align-items:flex-start;border-radius:16px;padding:12px 14px;font-size:14.5px;line-height:1.55;margin:4px 0}
.sm-alert.warn{background:var(--amber-soft);color:var(--amber-ink)}
.sm-alert.ok{background:var(--green-soft);color:var(--green-ink)}
.sm-float{display:none}

/* ---------- כל הסוגים (קבוצת מוצרים) ---------- */
.item-ic.group{background:oklch(0.95 0.035 250);color:oklch(0.42 0.1 250);font-size:17px}
.item-sub.grp{color:oklch(0.42 0.1 250);white-space:normal}
[class*="st-key-grp_"]{padding-inline-start:46px;margin-top:-6px}
[class*="st-key-grp_"] .stButton>button{min-height:30px!important;padding:2px 10px!important;border:0!important;background:transparent!important;color:var(--green-ink)!important}
[class*="st-key-grp_"] .stButton>button:hover{background:var(--green-softer)!important}
[class*="st-key-grp_"] .stButton>button p{font-size:13px!important;font-weight:600!important}
[data-testid="stPills"] button,[data-testid="stButtonGroup"] button[data-variant="pills"]{border-radius:999px!important}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-checked="true"],[data-testid="stButtonGroup"] button[aria-pressed="true"],[data-testid="stButtonGroup"] button[data-selected="true"]{
  background:var(--green-soft)!important;border-color:var(--green)!important;color:var(--green-ink)!important}
[data-testid="stButtonGroup"],[data-testid="stButtonGroup"]>div{direction:rtl}
[data-testid="stButtonGroup"] [role="group"],[data-testid="stButtonGroup"] [role="radiogroup"],[data-testid="stButtonGroup"] [role="listbox"]{justify-content:flex-start}
.gp{display:flex;flex-direction:column;gap:2px;margin:6px 0 4px}
.gp-row{display:grid;grid-template-columns:auto 86px minmax(0,1fr) auto;gap:10px;align-items:center;padding:8px 8px;border-radius:12px;font-size:14px}
.gp-row.first{background:var(--green-softer)}
.gp-c{font-weight:600}
.gp-p{color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}
.gp-v{font-weight:700}
.gp-more{margin:6px 0 10px}
.gp-more summary{cursor:pointer;font-size:13.5px;color:var(--green-ink);font-weight:600}
.gp-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.gp-chip{background:#F2F5F1;border-radius:999px;padding:3px 10px;font-size:12.5px;color:var(--ink-2)}
.bd-cell.has-pick{align-items:flex-start}
.bd-cell.has-pick>span:first-child{display:flex;flex-direction:column;min-width:0}
.bd-pick{font-size:11.5px;color:var(--ink-3);font-weight:400;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px}
.bd-body:has(.has-pick){grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}
/* זנים בכרטיס ירק */
[class*="st-key-pcard"] [data-testid="stPopover"] button{min-height:32px!important;padding:2px 10px!important;width:100%;background:#F6F8F5!important;border-color:transparent!important}
[class*="st-key-pcard"] [data-testid="stPopover"] button p{font-size:12.5px!important;font-weight:500!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pc-var{font-size:12px;color:oklch(0.42 0.1 250);font-weight:600;margin-top:2px}
@media (max-width:640px){
  [class*="st-key-grp_"]{padding-inline-start:0}
  .gp-row{grid-template-columns:auto 70px minmax(0,1fr) auto;gap:8px}
}

/* ---------- ירקות ---------- */
.st-key-grid2_produce [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:12px!important}
.st-key-grid2_produce [data-testid="stColumn"],.st-key-grid2_produce [data-testid="column"]{flex:0 0 calc(33.333% - 8px)!important;width:calc(33.333% - 8px)!important;min-width:0!important}
@media (max-width:640px){
  .st-key-grid2_produce [data-testid="stHorizontalBlock"]{gap:10px!important}
  .st-key-grid2_produce [data-testid="stColumn"],.st-key-grid2_produce [data-testid="column"]{flex:0 0 calc(50% - 5px)!important;width:calc(50% - 5px)!important;min-width:0!important}
}
[class*="st-key-pcard"]{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px 12px 8px;gap:6px!important;transition:all .15s}
[class*="st-key-pcardon"]{border-color:var(--green);box-shadow:0 0 0 3px color-mix(in oklch,var(--green) 12%,transparent)}
.pc-top{display:flex;justify-content:space-between;align-items:flex-start}
.pc-em{font-size:30px;line-height:1}
.pc-name{font-weight:700;font-size:15.5px;margin-top:6px}
.pc-price{font-size:20px;font-weight:700;font-family:var(--font-d)}
.pc-price small{font-size:12px;color:var(--ink-3);font-weight:500;font-family:var(--font)}
.pc-where{font-size:12.5px;color:var(--ink-3)}
[class*="st-key-pcard"] [data-baseweb="input"]{background:#fff!important}
.matrix{width:100%;border-collapse:separate;border-spacing:0;font-size:14px}
.matrix th{font-weight:600;color:var(--ink-3);font-size:12.5px;padding:8px 10px;text-align:center;white-space:nowrap;border-bottom:1px solid var(--line)}
.matrix th:first-child,.matrix td:first-child{text-align:right;position:sticky;right:0;background:#fff}
.matrix td{padding:9px 10px;text-align:center;border-bottom:1px solid var(--line);white-space:nowrap}
.matrix td.best{color:var(--green-ink);font-weight:700;background:var(--green-softer)}
.matrix td.na{color:#C3CCC6}
.scroll-x{overflow-x:auto}

/* ---------- חיפוש ---------- */
.prod{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) auto;gap:18px;align-items:center}
.range{position:relative;height:28px}
.range .track{position:absolute;top:12px;left:0;right:0;height:5px;border-radius:9px;background:linear-gradient(to left,var(--green),var(--amber))}
.range .dot{position:absolute;top:8px;width:13px;height:13px;border-radius:50%;background:#fff;border:2px solid #B9C5BE;transform:translateX(50%)}
.range .dot.min{border-color:var(--green)}
.range .dot.max{border-color:var(--amber)}
.hbar-row{display:grid;grid-template-columns:120px minmax(0,1fr) 56px;gap:12px;align-items:center;padding:6px 0;font-size:14px}
.hbar{height:22px;border-radius:7px;background:#F1F4F0;overflow:hidden}
.hbar i{display:block;height:100%;border-radius:7px}
[class*="st-key-srow_"] .stButton>button,[class*="st-key-hrow_"] .stButton>button{min-height:38px!important}

/* ---------- היסטוריה / עזרה / סטטוס ---------- */
.hist-hero{display:flex;gap:20px;align-items:center;background:var(--amber-soft);border:1px solid color-mix(in oklch,var(--amber) 35%,transparent);border-radius:22px;padding:22px;margin-bottom:14px}
.hist-hero .big{font-family:var(--font-d);font-size:40px;font-weight:700;color:var(--amber-ink);line-height:1}
.hist{display:flex;gap:14px;align-items:center;min-width:0}
.steps3{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}
.step-card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:var(--shadow)}
.step-n{width:26px;height:26px;border-radius:50%;background:var(--green-soft);color:var(--green-ink);display:grid;place-items:center;font-size:13px;font-weight:700}
.faq{border-bottom:1px solid var(--line)}
.faq:last-child{border-bottom:0}
.faq summary{list-style:none;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:18px 4px;font-size:16px;font-weight:600;cursor:pointer}
.faq summary::-webkit-details-marker{display:none}
.faq-a{padding:0 4px 18px;color:var(--ink-2);line-height:1.7;font-size:15px}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:6px 0 14px}
.stat{background:#F6F8F5;border-radius:14px;padding:12px 14px}
.stat .v{font-weight:700;font-size:19px;font-family:var(--font-d)}
.stat .l{font-size:12.5px;color:var(--ink-3)}
.chain-line{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:14.5px}
.chain-line:last-child{border-bottom:0}
.footer{text-align:center;color:var(--ink-3);font-size:13px;padding:36px 0 10px}

/* ---------- מובייל ---------- */
@media (max-width:640px){
  .block-container,[data-testid="stMainBlockContainer"]{padding:.8rem 1rem 9rem!important}
  .h-display{font-size:29px}
  .h1{font-size:24px}
  .logo{font-size:19px}
  .logo-mark{width:34px;height:34px}
  .st-key-sm_status button p{font-size:12px!important}
  [class*="st-key-card"]{padding:16px 14px 12px;border-radius:20px}
  .winner{padding:20px}
  .winner .w-name{font-size:26px}
  .winner .w-total{font-size:40px}
  .stat-grid{grid-template-columns:1fr 1fr}
  .steps3{grid-template-columns:1fr}
  .prod{grid-template-columns:minmax(0,1fr) auto;gap:8px}
  .prod .range{grid-column:1/-1;order:3}
  .hbar-row{grid-template-columns:96px minmax(0,1fr) 44px}
  [class*="st-key-chips_"]{padding-inline-start:0}
  /* רשת 2 בטור (סלים מוכנים, ירקות) */
  [class*="st-key-grid2"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:10px!important}
  [class*="st-key-grid2"] [data-testid="stColumn"],[class*="st-key-grid2"] [data-testid="column"]{min-width:calc(50% - 5px)!important;flex:1 1 calc(50% - 5px)!important;width:calc(50% - 5px)!important}
  /* ניווט תחתון */
  .st-key-sm_nav{position:fixed!important;bottom:0;left:0;right:0;z-index:999990;margin:0!important;
    background:rgba(255,255,255,.96);backdrop-filter:blur(14px);border-top:1px solid var(--line);border-bottom:0;
    padding:6px 6px calc(12px + env(safe-area-inset-bottom))!important}
  .st-key-sm_nav [data-testid="stButtonGroup"]>div,.st-key-sm_nav [role="radiogroup"]{display:grid!important;grid-template-columns:repeat(5,1fr);gap:2px!important}
  .st-key-sm_nav button{padding:6px 2px!important;min-height:50px;width:100%}
  .st-key-sm_nav button p{font-size:11.5px!important;line-height:1.25}
  /* פס סיכום צף */
  .sm-float{display:flex;position:fixed;bottom:82px;left:12px;right:12px;z-index:999980;background:var(--ink);color:#fff!important;
    border-radius:18px;padding:12px 14px;align-items:center;justify-content:space-between;gap:10px;box-shadow:var(--shadow-lg);text-decoration:none!important}
  .sm-float .txt{display:flex;flex-direction:column}
  .sm-float .l{font-size:12px;color:rgba(255,255,255,.7)!important}
  .sm-float .v{font-weight:700;font-size:16px;color:#fff!important}
  .st-key-sm_status button{max-width:44vw}
  .st-key-sm_status button p{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .sm-float .go{background:var(--amber);color:#3A2600;border-radius:999px;padding:8px 14px;font-weight:700;font-size:13.5px}
}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ════════════════════════════════════════════════
# רכיבי HTML
# ════════════════════════════════════════════════
def logo_html():
    return '<div class="logo"><span class="logo-mark">🛒</span>סל משווה</div>'


def page_head(title, sub, display=False):
    cls = "h-display" if display else "h1"
    return f'<div class="{cls}">{esc(title)}</div><p class="sub">{esc(sub)}</p>'


def alert(text, kind="warn", icon="⚠️"):
    return f'<div class="sm-alert {kind}"><span>{icon}</span><span>{text}</span></div>'


def chainbar_html(chains, names, total_all):
    stack = "".join(chain_mark(c, names.get(c, c)) for c in chains[:5])
    extra = " · כולן" if len(chains) >= total_all else ""
    return (f'<div class="chainbar"><span class="stack">{stack}</span>'
            f'<span style="font-size:14.5px"><b>משווים {len(chains)} רשתות</b>'
            f'<span class="tiny">{extra}</span></span></div>')


def item_html(q, product_name, status):
    ic = {"ok": "✓", "unclear": "?", "none": "!", "group": "≡"}[status]
    if status == "group":
        sub = f'<div class="item-sub grp">{esc(product_name or "")}</div>'
    elif status == "ok":
        sub = f'<div class="item-sub">{esc(product_name or "")}</div>'
    elif status == "unclear":
        sub = '<div class="item-sub warn">יש כמה אפשרויות — איזו התכוונת?</div>'
    else:
        sub = '<div class="item-sub err">לא מצאנו את המוצר. נסי שם מדויק יותר, למשל ״חלב תנובה 3%״</div>'
    return (f'<div class="item"><span class="item-ic {status}">{ic}</span>'
            f'<div class="item-txt"><div class="item-name">{esc(q)}</div>{sub}</div></div>')


def qty_html(qty, is_kg):
    v = format(qty, "g")
    return f'<div class="qty">{v}{" <small>ק״ג</small>" if is_kg else ""}</div>'


def empty_html(emoji, title, sub):
    return (f'<div class="empty"><div class="em">{emoji}</div><div class="h2">{esc(title)}</div>'
            f'<p class="sub" style="max-width:320px;margin:8px auto 0">{esc(sub)}</p></div>')


def winner_html(cid, name, total, label, savings=None, worst_name=None, note=None):
    sv = ""
    if savings is not None and savings > 0.5:
        sv = f'<div class="savings">חוסכת {fmt(savings)} ₪ לעומת {esc(worst_name or "")}</div>'
    nt = f'<div class="w-note">{note}</div>' if note else ""
    return (f'<div class="winner" id="sm-results"><div class="w-lbl">{esc(label)}</div>'
            f'<div class="w-chain">{chain_mark(cid, name, lg=True)}<span class="w-name">{esc(name)}</span></div>'
            f'<div class="w-total num">{fmt(total)}<small>₪</small></div>{sv}{nt}</div>')


def rank_html(rows, title="כל הרשתות", subtitle=""):
    """rows: [(cid, name, total, n_missing)] ממוין מהזול ליקר."""
    if not rows:
        return ""
    best = rows[0][2]
    mx = max(r[2] for r in rows) or 1
    out = []
    for i, (cid, name, total, miss) in enumerate(rows):
        badge = f'<span class="badge warn">חסרים {miss}</span>' if miss else ""
        diff = "הזולה" if i == 0 else "+" + fmt(total - best)
        out.append(
            f'<div class="rank-row{" first" if i == 0 else ""}"><span class="rank-pos num">{i + 1}</span>'
            f'{chain_mark(cid, name)}<div style="min-width:0"><div class="rank-name">{esc(name)}{badge}</div>'
            f'<div class="rank-bar{"" if i == 0 else " dim"}"><i style="width:{total / mx * 100:.1f}%"></i></div></div>'
            f'<div><div class="rank-price num">{fmt(total)} ₪</div><div class="rank-diff num">{diff}</div></div></div>'
        )
    st_ = f'<div class="tiny" style="margin-top:2px">{subtitle}</div>' if subtitle else ""
    return f'<div class="h2">{esc(title)}</div>{st_}<div class="rank">{"".join(out)}</div>'


def group_preview_html(best_rows, sample_names, n_total):
    """best_rows: [(cid, cname, price_for_compare, product_name, real_price)]"""
    rows = "".join(
        f'<div class="gp-row{" first" if i == 0 else ""}">{chain_mark(c, cn)}<span class="gp-c">{esc(cn)}</span>'
        f'<span class="gp-p" title="{esc(pn)}">{esc(pn)}</span><span class="num gp-v">{fmt(v)} ₪</span></div>'
        for i, (c, cn, v, pn, _rp) in enumerate(best_rows))
    more = ""
    if sample_names:
        chips = "".join(f'<span class="gp-chip">{esc(n)}</span>' for n in sample_names)
        extra = f'<span class="tiny"> ועוד {n_total - len(sample_names)}</span>' if n_total > len(sample_names) else ""
        more = (f'<details class="gp-more"><summary>אילו מוצרים נכללים?</summary>'
                f'<div class="gp-chips">{chips}{extra}</div></details>')
    return f'<div class="gp">{rows}</div>{more}'


def breakdown_html(rows, chains, names):
    """rows: [(query, qty, is_kg, product_name, {chain: price}, picks|None)]"""
    parts = []
    for row in rows:
        q, qty, is_kg, pname, prices = row[:5]
        picks = row[5] if len(row) > 5 else None
        valid = {c: p for c, p in prices.items() if p is not None and c in chains}
        if not valid:
            continue
        mn = min(valid.values())
        mc = min(valid, key=valid.get)
        qlbl = ""
        if qty != 1:
            qlbl = f' <span class="tiny">× {format(qty, "g")}{" ק״ג" if is_kg else ""}</span>'
        cells = []
        for c in sorted(chains, key=lambda c: (prices.get(c) is None, prices.get(c) or 0)):
            p = prices.get(c)
            cls = " na" if p is None else (" best" if p == mn else "")
            val = "לא נמכר" if p is None else f"{fmt(p)} ₪"
            pk = ""
            if picks and c in picks:
                pk = f'<span class="bd-pick">{esc(picks[c][0])}</span>'
            cells.append(f'<div class="bd-cell{cls}{" has-pick" if pk else ""}"><span>{esc(names.get(c, c))}{pk}</span>'
                         f'<span class="num">{val}</span></div>')
        parts.append(
            f'<details class="bd"><summary><span style="min-width:0"><span class="bd-name">{esc(q)}</span>{qlbl}'
            f'<div class="bd-best">הכי זול ב{esc(names.get(mc, mc))}</div></span>'
            f'<span class="num" style="font-weight:700">{fmt(mn * qty)} ₪</span><span class="bd-chev">▼</span></summary>'
            f'<div class="bd-body"><div class="bd-prod">{esc(pname or "")}</div>{"".join(cells)}</div></details>'
        )
    return ('<div class="sec-head"><div class="h2">מחיר לכל מוצר</div><span class="tiny">לחצי על מוצר לפירוט</span></div>'
            + "".join(parts))


def float_html(name, total):
    return (f'<a class="sm-float" href="#sm-results"><span class="txt"><span class="l">הכי זול: {esc(name)}</span>'
            f'<span class="v num">{fmt(total)} ₪</span></span><span class="go">לתוצאות ↓</span></a>')


def produce_card_html(nm, price, chain_id, chain_name, varieties=None):
    em = PRODUCE_EMOJI.get(nm, "🥬")
    mark = chain_mark(chain_id, chain_name) if chain_id else ""
    if price is None:
        pr = '<div class="pc-price" style="color:var(--ink-3);font-size:15px">אין מחיר לפי משקל</div>'
        wh = ""
    else:
        pr = f'<div class="pc-price num">{fmt(price)} <small>₪ לק״ג</small></div>'
        wh = f'<div class="pc-where">הכי זול ב{esc(chain_name)}</div>'
    if varieties:
        wh += f'<div class="pc-var">זן: {esc(", ".join(varieties))}</div>'
    return (f'<div style="padding-bottom:4px"><div class="pc-top"><span class="pc-em">{em}</span>{mark}</div>'
            f'<div class="pc-name">{esc(nm)}</div>{pr}{wh}</div>')


def matrix_html(names_rows, chains, cnames, pmap):
    head = "".join(f"<th>{esc(cnames.get(c, c))}</th>" for c in chains)
    body = []
    for nm in names_rows:
        vals = {c: (pmap.get(nm, {}).get(c) or (None,))[0] for c in chains}
        have = {c: v for c, v in vals.items() if v is not None}
        best = min(have, key=have.get) if have else None
        tds = "".join(
            f'<td class="{"na" if vals[c] is None else ("best" if c == best else "")}">'
            f'{"—" if vals[c] is None else fmt(vals[c])}</td>' for c in chains)
        body.append(f"<tr><td>{PRODUCE_EMOJI.get(nm, '')} {esc(nm)}</td>{tds}</tr>")
    return (f'<div class="scroll-x"><table class="matrix num"><thead><tr><th>ירק / פרי</th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def search_row_html(name, brand, n_chains, prices_sorted, cnames):
    """prices_sorted: [(chain, price)] מהזול ליקר"""
    lo, hi = prices_sorted[0][1], prices_sorted[-1][1]
    span = (hi - lo) or 1
    dots = []
    for i, (c, v) in enumerate(prices_sorted):
        cls = " min" if i == 0 else (" max" if i == len(prices_sorted) - 1 else "")
        dots.append(f'<span class="dot{cls}" title="{esc(cnames.get(c, c))} {fmt(v)}" style="right:{(v - lo) / span * 100:.1f}%"></span>')
    return (f'<div class="prod"><div style="min-width:0"><div style="font-weight:600;font-size:15px">{esc(name)}</div>'
            f'<div class="tiny">{esc(brand or "")}{" · " if brand else ""}{n_chains} רשתות</div></div>'
            f'<div class="range"><div class="track"></div>{"".join(dots)}</div>'
            f'<div style="text-align:left"><div class="num" style="font-weight:700">{fmt(lo)} ₪</div>'
            f'<div class="tiny">{esc(cnames.get(prices_sorted[0][0], prices_sorted[0][0]))}</div></div></div>')


def hbars_html(counts, total):
    """counts: [(chain_name, n)] ממוין יורד"""
    if not counts:
        return ""
    mx = counts[0][1] or 1
    out = []
    for i, (nm, n) in enumerate(counts):
        col = "var(--green)" if i == 0 else "#CBD5CF"
        out.append(f'<div class="hbar-row"><span style="font-weight:{700 if i == 0 else 500}">{esc(nm)}</span>'
                   f'<div class="hbar"><i style="width:{n / mx * 100:.1f}%;background:{col}"></i></div>'
                   f'<span class="num tiny" style="text-align:left">{n / total * 100:.0f}%</span></div>')
    return "".join(out)


def hist_html(cid, cname, total, date, items, savings):
    its = esc(", ".join(items))
    return (f'<div class="hist">{chain_mark(cid, cname, lg=True)}<div style="min-width:0">'
            f'<div style="font-weight:700;font-size:15.5px">{esc(cname)} · <span class="num">{fmt(total)} ₪</span></div>'
            f'<div class="tiny" style="margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{esc(date)} · {its}</div>'
            f'<span class="badge ok" style="margin-top:6px">חסכת {fmt(savings)} ₪</span></div></div>')


FAQ = [
    ("מאיפה המחירים?", "כל רשת מזון בישראל מחויבת בחוק (מ-2014) לפרסם את המחירים שלה בקבצי ״שקיפות מחירים״. אנחנו אוספים את הקבצים האלה כל בוקר מהרשתות, ומשווים ביניהם."),
    ("כמה זה עולה?", "כלום. האתר חינמי לגמרי, בלי פרסומות ובלי הרשמה."),
    ("למה המחיר שונה בסניף שלי?", "לכל רשת יש סניפים עם הבדלי מחיר קטנים. אנחנו מציגים ממוצע ארצי של כל הסניפים — הוא טוב להשוואה בין רשתות, אבל יכול להיות שונה בכמה אגורות מהמדף."),
    ("מוצר לא זוהה — מה עושים?", "כתבי שם מפורש יותר: במקום ״חלב״ → ״חלב תנובה 3%״. אם יש כמה התאמות, נציע לך לבחור את הנכונה ישר ברשימה."),
    ("מה זה ״השוואה הוגנת״?", "אם רשת לא מוכרת אחד המוצרים מהסל שלך, הסכום שלה נראה נמוך יותר באופן לא הוגן. ״השוואה הוגנת״ מחשבת רק את המוצרים שנמכרים בכל הרשתות."),
    ("איך כותבים כמות או משקל?", "לפני שם המוצר: ״3 במבה״, ״2 קילו עגבניות״, ״500 גרם גבינה״, או ״חלב × 2״. אפשר גם לשנות עם כפתורי + / − ליד כל מוצר."),
    ("פרטיות", "הרשימות וההיסטוריה נשמרות רק אצלך, בחלון הדפדפן. אנחנו לא שומרים שום מידע אישי."),
]


def help_html():
    steps = "".join(
        f'<div class="step-card"><span class="step-n">{n}</span><div style="font-weight:700;font-size:16px;margin-top:10px">{t}</div>'
        f'<div class="tiny" style="margin-top:4px">{d}</div></div>'
        for n, t, d in [("1", "בונים סל", "כותבים מוצרים או בוחרים סל מוכן"),
                        ("2", "רואים מיד", "ההשוואה מתעדכנת עם כל מוצר"),
                        ("3", "חוסכים", "קונים ברשת הזולה לסל שלך")])
    faq = "".join(
        f'<details class="faq"{" open" if i == 0 else ""}><summary>{esc(q)}<span class="bd-chev">▼</span></summary>'
        f'<div class="faq-a">{esc(a)}</div></details>' for i, (q, a) in enumerate(FAQ))
    return (f'<div style="max-width:780px"><div class="steps3">{steps}</div>'
            f'<div style="background:#fff;border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:4px 22px">{faq}</div></div>')
