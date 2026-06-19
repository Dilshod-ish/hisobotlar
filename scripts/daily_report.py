#!/usr/bin/env python3
"""
Har kuni 3 sahifali hisobotni Telegram albumiga yuboradi:
  1. Balans varaqasi
  2. Mahsulotlar hisoboti
  3. Debitorlar hisoboti

Mahsulotlar va Debitorlar tablari uchun sheet tuzilishi:
  A ustun: S = bo'lim sarlavhasi
            T = bo'lim yig'indisi
            G = umumiy yig'indi
            (bo'sh) = oddiy qator
  B ustun: nomi
  C ustun: qiymati (son yoki formula)

Kerakli o'zgaruvchilar:
  GOOGLE_API_KEY      - Google Sheets API kaliti
  TELEGRAM_BOT_TOKEN  - Bot token
  TELEGRAM_CHAT_ID    - Chat ID (default: -1002646062763)
  TELEGRAM_THREAD_ID  - Thread ID (default: 1885)
"""
import json, os, re, tempfile
from datetime import datetime
from urllib.parse import quote

import pytz, requests
from playwright.sync_api import sync_playwright

SPREADSHEET_ID  = "1RxuwKXiGBzzEAwmrMsNmioHCMwu1AfeG8WPl9995N84"
BOT_TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID         = os.environ.get("TELEGRAM_CHAT_ID",   "-1002646062763")
THREAD_ID       = int(os.environ.get("TELEGRAM_THREAD_ID", "1885"))
TAB_MAHSULOTLAR = os.environ.get("TAB_MAHSULOTLAR", "Mahsulotlar")
TAB_DEBITORLAR  = os.environ.get("TAB_DEBITORLAR",  "Debitorlar")

_KEY = re.compile(r'^\d+(\.\d+)*$')


# ── Google Sheets ─────────────────────────────────────────────────────────────

def fetch(range_str: str) -> list[list[str]]:
    key = os.environ["GOOGLE_API_KEY"]
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/"
           f"{SPREADSHEET_ID}/values/{quote(range_str)}?key={key}")
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Sheets API {r.status_code} ({range_str}): {r.text[:200]}")
    return r.json().get("values", [])


def read_balans() -> dict[str, str]:
    data = {}
    for row in fetch("A:G"):
        row += [""] * max(0, 7 - len(row))
        if _KEY.match(row[0].strip()): data[row[0].strip()] = row[2].strip()
        if _KEY.match(row[4].strip()): data[row[4].strip()] = row[6].strip()
    if not data:
        raise RuntimeError("Balans ma'lumoti topilmadi")
    return data


def read_table(tab: str) -> list[dict]:
    result = []
    for row in fetch(f"'{tab}'!A:C"):
        while len(row) < 3:
            row.append("")
        m, name, val = row[0].strip().upper(), row[1].strip(), row[2].strip()
        if not name:
            continue
        result.append({
            "type": {"S": "section", "T": "subtotal", "G": "total"}.get(m, "item"),
            "name": name,
            "value": val,
        })
    return result


def read_debitorlar(tab: str) -> tuple[list[dict], list[tuple], list[tuple]]:
    """
    A:C — S/T/G xulosa qatorlari
    A:L — juft ustunlarda (ism, summa) individual debitorlar:
          (A,B), (C,D)             → Mijozlar      (1-2 juft)
          (E,F), (G,H), (I,J), (K,L) → Ta'minotchilar (3-6 juft)
    Qaytaradi: (xulosa_qatorlari, mijozlar, taminotchilar)
    """
    rows = fetch(f"'{tab}'!A:L")
    summary = []
    mijozlar = []
    taminotchilar = []

    for row in rows:
        while len(row) < 12:
            row.append("")
        marker = row[0].strip().upper()

        if marker in ("S", "T", "G"):
            name, val = row[1].strip(), row[2].strip()
            if name:
                summary.append({
                    "type": {"S": "section", "T": "subtotal", "G": "total"}[marker],
                    "name": name,
                    "value": val,
                })
        else:
            # (E,F)=4, (G,H)=6 → Mijozlar; (I,J)=8, (K,L)=10 → Ta'minotchilar
            for col_idx, target in [(4, mijozlar), (6, mijozlar),
                                    (8, taminotchilar), (10, taminotchilar)]:
                name = row[col_idx].strip() if col_idx < len(row) else ""
                val  = row[col_idx + 1].strip() if col_idx + 1 < len(row) else ""
                if name and val:
                    target.append((name, to_float(val)))

    mijozlar.sort(key=lambda x: x[1])
    taminotchilar.sort(key=lambda x: x[1])
    return summary, mijozlar, taminotchilar


# ── Formatting ────────────────────────────────────────────────────────────────

def to_float(s: str) -> float:
    try:
        return float(s.replace(" ", "").replace(" ", "").replace(",", "."))
    except Exception:
        return 0.0


def to_str(f: float) -> str:
    sign = "-" if f < 0 else ""
    i, d = f"{abs(f):,.2f}".split(".")
    return f"{sign}{i.replace(',', ' ')},{d}"


def fmt(s: str) -> tuple[str, str]:
    if not s:
        return "—", "zero"
    f = to_float(s)
    if f < 0:  return to_str(f), "negative"
    if f == 0: return to_str(f), "zero"
    return to_str(f), "positive"


def cell(data: dict, key: str) -> tuple[str, str]:
    s = data.get(key, "").strip()
    if not s:
        return "—", "zero"
    if s.startswith("-") or s in ("0,00", "0.00", "0"):
        return s, "zero"
    return s, "positive"


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
       background: #f0f2f5; padding: 24px; }
.container { max-width: 1100px; margin: 0 auto; }
.header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.header-icon { width: 52px; height: 52px; background: linear-gradient(135deg,#d6e5ff,#e8f0ff);
               border-radius: 12px; display: flex; align-items: center;
               justify-content: center; font-size: 22px; }
.header-text h1 { font-size: 28px; font-weight: 700; color: #1a1a1a; }
.header-text p  { font-size: 14px; color: #888; margin-top: 2px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 16px; }
.card { background: white; border-radius: 14px; overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.card-title { padding: 14px 20px; font-size: 17px; font-weight: 700;
              display: flex; align-items: center; gap: 8px; }
.card-footer { padding: 13px 20px; display: flex; justify-content: space-between;
               align-items: center; border-top: 2px solid #eee; }
.footer-label { font-size: 15px; font-weight: 700; }
.footer-total { font-size: 20px; font-weight: 700; font-family: monospace; }
.section-row { padding: 8px 20px; font-size: 12px; font-weight: 700;
               text-transform: uppercase; letter-spacing: .5px;
               border-bottom: 1px solid #f0f0f0; }
.row { padding: 10px 20px; border-bottom: 1px solid #f5f5f5;
       display: flex; justify-content: space-between; align-items: center; }
.row:last-child { border-bottom: none; }
.row.sub  { padding-left: 36px; background: #fafafa; }
.row-label { font-size: 13.5px; color: #333; }
.row-value { font-size: 13.5px; font-weight: 600; font-family: monospace;
             color: #555; min-width: 140px; text-align: right; }
.row-value.positive  { color: #2e7d32; }
.row-value.zero      { color: #bbb; }
.row-value.negative  { color: #c62828; }
.summary { background: white; border-radius: 14px; padding: 18px 24px;
           display: flex; justify-content: space-between; align-items: center;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.summary-left .label { font-size: 14px; color: #888; }
.summary-left .value { font-size: 26px; font-weight: 700; color: #1a1a1a;
                       font-family: monospace; margin-top: 2px; }
.badge { padding: 8px 18px; border-radius: 8px; font-size: 14px; font-weight: 700;
         background: #e8f5e9; color: #2e7d32; }
.badge.red { background: #fce4ec; color: #c62828; }
.aktiv .card-title  { background: #e8f5e9; color: #2e7d32; }
.aktiv .section-row { background: #f1faf2; color: #2e7d32; }
.aktiv .card-footer { background: #f1faf2; }
.aktiv .footer-total { color: #2e7d32; }
.passiv .card-title  { background: #fce4ec; color: #c62828; }
.passiv .section-row { background: #fff5f7; color: #c62828; }
.passiv .card-footer { background: #fff5f7; }
.passiv .footer-total { color: #c62828; }
.passiv .row-value.positive { color: #c62828; }
.mahsulot .card-title  { background: #e8f5e9; color: #2e7d32; }
.mahsulot .section-row { background: #f1faf2; color: #2e7d32; }
.mahsulot .card-footer { background: #f1faf2; }
.mahsulot .footer-total { color: #2e7d32; }
.debitor .card-title  { background: #e3f2fd; color: #1565c0; }
.debitor .section-row { background: #e8f4fd; color: #1565c0; }
.debitor .card-footer { background: #e3f2fd; }
.debitor .footer-total { color: #1565c0; }
.debitor .row-value.positive { color: #1565c0; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.col-title { padding: 10px 16px; font-size: 14px; font-weight: 700; border-bottom: 1px solid #e3f2fd; color: #1565c0; }
.mijozlar .row-value.positive  { color: #c62828; }
.mijozlar .row-value.negative  { color: #1565c0; }
.date { font-size: 11px; color: #bbb; text-align: right; margin-top: 10px; }
"""


# ── HTML: Balans (sahifa 1) ───────────────────────────────────────────────────

def _r(data: dict, key: str, label: str) -> str:
    text, cls = cell(data, key)
    return (f'<div class="row sub">'
            f'<span class="row-label">{label}</span>'
            f'<span class="row-value {cls}">{text}</span></div>')


def _t(label: str, text: str, cls: str) -> str:
    return (f'<div class="row">'
            f'<span class="row-label"><b>{label}</b></span>'
            f'<span class="row-value {cls}">{text}</span></div>')


def generate_balans_html(data: dict, time_str: str) -> str:
    aktiv_total  = sum(to_float(data.get(k, "")) for k in ("1", "2", "3", "4"))
    passiv_total = sum(to_float(data.get(k, "")) for k in ("5", "6"))
    diff = aktiv_total - passiv_total

    badge_text = "✓ Aktiv ortiq" if diff >= 0 else "✗ Passiv ortiq"
    badge_cls  = "" if diff >= 0 else " red"

    p1t, p1c = cell(data, "1"); p2t, p2c = cell(data, "2")
    p3t, p3c = cell(data, "3"); p4t, p4c = cell(data, "4")
    p5t, p5c = cell(data, "5"); p6t, p6c = cell(data, "6")

    return f"""<!DOCTYPE html>
<html lang="uz">
<head><meta charset="UTF-8"><title>Balans varaqasi</title>
<style>{CSS}</style></head>
<body><div class="container">
  <div class="header">
    <div class="header-icon">📊</div>
    <div class="header-text">
      <h1>Balans varaqasi</h1>
      <p>Aktiv · Passiv · Nazorat &nbsp;|&nbsp; Valyuta: UZS</p>
    </div>
  </div>
  <div class="grid">
    <div class="card aktiv">
      <div class="card-title">📈 Aktiv</div>
      <div class="section-row">1. Pul mablag'lar</div>
      {_r(data, "1.1", "1.1 Naqd pullar")}
      {_r(data, "1.2", "1.2 Bank-hisoblar")}
      {_t("Jami pul mablag'lar", p1t, p1c)}
      <div class="section-row">2. Mahsulotlar</div>
      {_r(data, "2.1", "2.1 Omborxonadagi (zaxira)")}
      {_r(data, "2.2", "2.2 Yo'ldagilar")}
      {_t("Jami mahsulotlar", p2t, p2c)}
      <div class="section-row">3. Debitorlar</div>
      {_r(data, "3.1.1", "3.1 Mijozlar — Avans")}
      {_r(data, "3.1.2", "3.1 Mijozlar — Qarz")}
      {_r(data, "3.2.1", "3.2 Ta'minotchilar — Avans")}
      {_r(data, "3.2.2", "3.2 Ta'minotchilar — Qarz")}
      {_r(data, "3.3",   "3.3 Boshqa debitorlar")}
      {_t("Jami debitorlar", p3t, p3c)}
      <div class="section-row">4. Asosiy vositalar</div>
      {_r(data, "4.1", "4.1 Avtotransport")}
      {_r(data, "4.2", "4.2 Ko'chmas mulk")}
      {_r(data, "4.3", "4.3 Asbob uskunalar")}
      {_r(data, "4.4", "4.4 Inventarlar")}
      {_t("Jami asosiy vositalar", p4t, p4c)}
      <div class="card-footer">
        <span class="footer-label">JAMI AKTIV</span>
        <span class="footer-total">{to_str(aktiv_total)}</span>
      </div>
    </div>
    <div class="card passiv">
      <div class="card-title">📉 Passiv</div>
      <div class="section-row">5. Kreditorlar</div>
      {_r(data, "5.1", "5.1 Bank kreditlari")}
      {_r(data, "5.2", "5.2 Qisqa muddatli qarzlar (zaim)")}
      {_r(data, "5.3", "5.3 Oylik maoshlar")}
      {_r(data, "5.4", "5.4 Boshqa kreditorlar")}
      {_t("Jami kreditorlar", p5t, p5c)}
      <div class="section-row">6. Kapital</div>
      {_r(data, "6.1", "6.1 Ustav fondi")}
      {_r(data, "6.2", "6.2 Taqsimlanmagan foyda")}
      {_t("Jami kapital", p6t, p6c)}
      <div class="card-footer">
        <span class="footer-label">JAMI PASSIV</span>
        <span class="footer-total">{to_str(passiv_total)}</span>
      </div>
    </div>
  </div>
  <div class="summary">
    <div class="summary-left">
      <div class="label">Balans farqi (Aktiv − Passiv)</div>
      <div class="value">{to_str(diff)}</div>
    </div>
    <div class="badge{badge_cls}">{badge_text}</div>
  </div>
  <div class="date">Oxirgi yangilanish: {time_str}</div>
</div></body></html>"""


# ── HTML: Jadval sahifalar (sahifa 2 va 3) ────────────────────────────────────

def _table_rows(items: list[dict]) -> str:
    html = ""
    for item in items:
        if item["type"] == "section":
            html += f'<div class="section-row">{item["name"]}</div>\n'
        elif item["type"] == "item":
            val, cls = fmt(item["value"])
            html += (f'<div class="row sub">'
                     f'<span class="row-label">{item["name"]}</span>'
                     f'<span class="row-value {cls}">{val}</span>'
                     f'</div>\n')
        elif item["type"] == "subtotal":
            val, cls = fmt(item["value"])
            html += (f'<div class="row">'
                     f'<span class="row-label"><b>{item["name"]}</b></span>'
                     f'<span class="row-value {cls}">{val}</span>'
                     f'</div>\n')
    return html


def generate_table_html(title: str, subtitle: str, icon: str,
                        theme: str, items: list[dict], time_str: str) -> str:
    total_item = next((i for i in items if i["type"] == "total"), None)
    total_val  = to_str(to_float(total_item["value"])) if total_item else "—"
    total_name = total_item["name"] if total_item else f"JAMI {title.upper()}"
    main_items = [i for i in items if i["type"] != "total"]

    return f"""<!DOCTYPE html>
<html lang="uz">
<head><meta charset="UTF-8"><title>{title}</title>
<style>{CSS}</style></head>
<body><div class="container">
  <div class="header">
    <div class="header-icon">{icon}</div>
    <div class="header-text">
      <h1>{title}</h1>
      <p>{subtitle} &nbsp;|&nbsp; Valyuta: UZS</p>
    </div>
  </div>
  <div class="card {theme}">
    <div class="card-title">{icon} {title}</div>
    {_table_rows(main_items)}
    <div class="card-footer">
      <span class="footer-label">{total_name}</span>
      <span class="footer-total">{total_val}</span>
    </div>
  </div>
  <div class="date">Oxirgi yangilanish: {time_str}</div>
</div></body></html>"""


def _debtor_col_rows(entries: list[tuple]) -> str:
    neg = sorted([(n, v) for n, v in entries if v < 0], key=lambda x: x[1])       # eng manfiy → 1-o'rinda
    pos = sorted([(n, v) for n, v in entries if v > 0], key=lambda x: x[1], reverse=True)  # eng musbat → 1-o'rinda
    html = ""
    if neg:
        top = neg[:10]
        label = f"Qarzlar (top {len(top)})" if len(neg) > 10 else "Qarzlar"
        html += f'<div class="section-row">{label}</div>\n'
        for name, val in top:
            html += (f'<div class="row sub">'
                     f'<span class="row-label">{name}</span>'
                     f'<span class="row-value negative">{to_str(val)}</span>'
                     f'</div>\n')
    if pos:
        top = pos[:10]
        label = f"Debitorlar (top {len(top)})" if len(pos) > 10 else "Debitorlar"
        html += f'<div class="section-row">{label}</div>\n'
        for name, val in top:
            html += (f'<div class="row sub">'
                     f'<span class="row-label">{name}</span>'
                     f'<span class="row-value positive">{to_str(val)}</span>'
                     f'</div>\n')
    if not html:
        html = '<div class="row sub"><span class="row-label" style="color:#bbb">Ma\'lumot yo\'q</span></div>\n'
    return html


def _mijoz_col_rows(entries: list[tuple]) -> str:
    # Manfiy = qarz (+ ko'rsatiladi), musbat = avans (- ko'rsatiladi)
    neg = sorted([(n, v) for n, v in entries if v < 0], key=lambda x: x[1])       # eng manfiy → 1-o'rinda
    pos = sorted([(n, v) for n, v in entries if v > 0], key=lambda x: x[1], reverse=True)  # eng musbat → 1-o'rinda
    html = ""
    if neg:
        top = neg[:10]
        label = f"Qarzlar (top {len(top)})" if len(neg) > 10 else "Qarzlar"
        html += f'<div class="section-row">{label}</div>\n'
        for name, val in top:
            html += (f'<div class="row sub">'
                     f'<span class="row-label">{name}</span>'
                     f'<span class="row-value negative">{to_str(-val)}</span>'
                     f'</div>\n')
    if pos:
        top = pos[:10]
        label = f"Avans (top {len(top)})" if len(pos) > 10 else "Avans"
        html += f'<div class="section-row">{label}</div>\n'
        for name, val in top:
            html += (f'<div class="row sub">'
                     f'<span class="row-label">{name}</span>'
                     f'<span class="row-value positive">{to_str(-val)}</span>'
                     f'</div>\n')
    if not html:
        html = '<div class="row sub"><span class="row-label" style="color:#bbb">Ma\'lumot yo\'q</span></div>\n'
    return html


def generate_debitorlar_html(summary: list[dict], mijozlar: list[tuple],
                             taminotchilar: list[tuple], time_str: str) -> str:
    total_item = next((i for i in summary if i["type"] == "total"), None)
    total_val  = to_str(to_float(total_item["value"])) if total_item else "—"
    total_name = total_item["name"] if total_item else "JAMI DEBITORLAR"
    summary_rows = [i for i in summary if i["type"] != "total"]

    total_count = len(mijozlar) + len(taminotchilar)

    return f"""<!DOCTYPE html>
<html lang="uz">
<head><meta charset="UTF-8"><title>Debitorlar hisoboti</title>
<style>{CSS}</style></head>
<body><div class="container">
  <div class="header">
    <div class="header-icon">👥</div>
    <div class="header-text">
      <h1>Debitorlar hisoboti</h1>
      <p>Mijozlar · Ta'minotchilar · Boshqa &nbsp;|&nbsp; Valyuta: UZS</p>
    </div>
  </div>
  <div class="card debitor" style="margin-bottom:16px">
    <div class="card-title">👥 Xulosa</div>
    {_table_rows(summary_rows)}
    <div class="card-footer">
      <span class="footer-label">{total_name}</span>
      <span class="footer-total">{total_val}</span>
    </div>
  </div>
  <div class="two-col">
    <div class="card debitor mijozlar">
      <div class="card-title">👤 Mijozlar ({len(mijozlar)} ta)</div>
      {_mijoz_col_rows(mijozlar)}
    </div>
    <div class="card debitor">
      <div class="card-title">🏭 Ta'minotchilar ({len(taminotchilar)} ta)</div>
      {_debtor_col_rows(taminotchilar)}
    </div>
  </div>
  <div class="date">Oxirgi yangilanish: {time_str}</div>
</div></body></html>"""


# ── Screenshot ────────────────────────────────────────────────────────────────

def take_screenshot(html: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False,
                                     mode="w", encoding="utf-8") as f:
        f.write(html)
        html_path = f.name
    png_path = html_path.replace(".html", ".png")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        height = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width": 1200, "height": height + 48})
        page.screenshot(path=png_path, full_page=True)
        browser.close()

    os.unlink(html_path)
    return png_path


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_album(png_paths: list[str], caption: str) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
    media = []
    files = {}
    for i, path in enumerate(png_paths):
        key = f"p{i}"
        media.append({
            "type": "photo",
            "media": f"attach://{key}",
            **({"caption": caption} if i == 0 else {}),
        })
        files[key] = open(path, "rb")

    resp = requests.post(url, data={
        "chat_id": CHAT_ID,
        "message_thread_id": str(THREAD_ID),
        "media": json.dumps(media),
    }, files=files)
    for f in files.values():
        f.close()
    resp.raise_for_status()
    return resp.json()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    tz = pytz.timezone("Asia/Tashkent")
    date_str = datetime.now(tz).strftime("%d.%m.%Y")
    time_str = datetime.now(tz).strftime("%d.%m.%Y, soat %H:%M")

    print("📊 Balans o'qilmoqda...")
    balans = read_balans()
    print(f"   {len(balans)} ta qiymat")

    print("📦 Mahsulotlar o'qilmoqda...")
    mahsulotlar = read_table(TAB_MAHSULOTLAR)
    print(f"   {len(mahsulotlar)} ta qator")

    print("👥 Debitorlar o'qilmoqda...")
    d_summary, d_mijozlar, d_taminotchilar = read_debitorlar(TAB_DEBITORLAR)
    print(f"   {len(d_summary)} xulosa + {len(d_mijozlar)} mijoz + {len(d_taminotchilar)} ta'minotchi")

    print("🖼  HTML generatsiya qilinmoqda...")
    html1 = generate_balans_html(balans, time_str)
    html2 = generate_table_html(
        "Mahsulotlar hisoboti", "Omborxona · Yo'ldagilar",
        "📦", "mahsulot", mahsulotlar, time_str)
    html3 = generate_debitorlar_html(d_summary, d_mijozlar, d_taminotchilar, time_str)

    print("📸 Screenshots olinmoqda...")
    paths = [take_screenshot(h) for h in [html1, html2, html3]]

    print("📨 Telegram'ga yuborilmoqda...")
    caption = f"📊 Kunlik hisobot — {date_str}"
    result = send_album(paths, caption)
    print(f"✓ Yuborildi! {len(result['result'])} ta rasm")

    for path in paths:
        os.unlink(path)


if __name__ == "__main__":
    main()
