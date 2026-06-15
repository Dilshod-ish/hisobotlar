#!/usr/bin/env python3
import csv, io, os, re, tempfile
from datetime import datetime
import pytz, requests
from playwright.sync_api import sync_playwright

SPREADSHEET_ID = "1RxuwKXiGBzzEAwmrMsNmioHCMwu1AfeG8WPl9995N84"
BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "-1002646062763")
THREAD_ID  = int(os.environ.get("TELEGRAM_THREAD_ID", "1885"))
_KEY = re.compile(r'^\d+(\.\d+)*$')

def read_sheet():
    base = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
    data = {}
    for gid in range(3):
        r = requests.get(f"{base}&gid={gid}", timeout=30, allow_redirects=False)
        if r.status_code != 200:
            break
        for row in csv.reader(io.StringIO(r.text)):
            key = row[0].strip() if row else ""
            val = row[2].strip() if len(row) >= 3 else ""
            if _KEY.match(key):
                data[key] = val
    if not data:
        raise RuntimeError("Sheet'dan ma'lumot o'qib bo'lmadi. Share -> Anyone with link -> Viewer qiling.")
    return data

def cell(data, key):
    s = data.get(key, "").strip()
    if not s: return "—", "zero"
    if s.startswith("-") or s in ("0,00","0.00","0"): return s, "zero"
    return s, "positive"

def to_float(s):
    try: return float(s.replace(" ","").replace(",","."))
    except: return 0.0

def to_str(f):
    sign = "-" if f < 0 else ""
    i, d = f"{abs(f):,.2f}".split(".")
    return f"{sign}{i.replace(',', ' ')},{d}"

def rhtml(data, key, label):
    t,c = cell(data, key)
    return f'<div class="row sub"><span class="row-label">{label}</span><span class="row-value {c}">{t}</span></div>'

def thtml(label, t, c):
    return f'<div class="row"><span class="row-label"><b>{label}</b></span><span class="row-value {c}">{t}</span></div>'

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif; background:#f0f2f5; padding:24px; }
.container { max-width:1100px; margin:0 auto; }
.header { display:flex; align-items:center; gap:16px; margin-bottom:24px; }
.header-icon { width:52px; height:52px; background:linear-gradient(135deg,#d6e5ff,#e8f0ff); border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:22px; }
.header-text h1 { font-size:28px; font-weight:700; color:#1a1a1a; }
.header-text p { font-size:14px; color:#888; margin-top:2px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:16px; }
.card { background:white; border-radius:14px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.08); }
.card-title { padding:14px 20px; font-size:17px; font-weight:700; display:flex; align-items:center; gap:8px; }
.aktiv .card-title { background:#e8f5e9; color:#2e7d32; }
.passiv .card-title { background:#fce4ec; color:#c62828; }
.section-header { padding:8px 20px; font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; border-bottom:1px solid #f0f0f0; }
.aktiv .section-header { background:#f1faf2; color:#2e7d32; }
.passiv .section-header { background:#fff5f7; color:#c62828; }
.row { padding:10px 20px; border-bottom:1px solid #f5f5f5; display:flex; justify-content:space-between; align-items:center; }
.row:last-child { border-bottom:none; }
.row.sub { padding-left:36px; background:#fafafa; }
.row-label { font-size:13.5px; color:#333; }
.row-value { font-size:13.5px; font-weight:600; font-family:monospace; color:#555; min-width:110px; text-align:right; }
.row-value.positive { color:#2e7d32; }
.row-value.zero { color:#bbb; }
.card-footer { padding:12px 20px; display:flex; justify-content:space-between; align-items:center; border-top:2px solid #eee; }
.aktiv .card-footer { background:#f1faf2; }
.passiv .card-footer { background:#fff5f7; }
.footer-label { font-size:15px; font-weight:700; }
.aktiv .footer-total { font-size:18px; font-weight:700; color:#2e7d32; font-family:monospace; }
.passiv .footer-total { font-size:18px; font-weight:700; color:#c62828; font-family:monospace; }
.summary { background:white; border-radius:14px; padding:18px 24px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 1px 4px rgba(0,0,0,.08); }
.summary-left .label { font-size:14px; color:#888; }
.summary-left .value { font-size:26px; font-weight:700; color:#1a1a1a; font-family:monospace; margin-top:2px; }
.badge { padding:8px 18px; border-radius:8px; font-size:14px; font-weight:700; background:#e8f5e9; color:#2e7d32; }
.badge.red { background:#fce4ec; color:#c62828; }
.date { font-size:11px; color:#bbb; text-align:right; margin-top:10px; }
"""

def generate_html(data):
    tz = pytz.timezone("Asia/Tashkent")
    date_str = datetime.now(tz).strftime("%d.%m.%Y, soat %H:%M")
    aktiv  = sum(to_float(data.get(k,"")) for k in ("1","2","3","4"))
    passiv = sum(to_float(data.get(k,"")) for k in ("5","6"))
    diff = aktiv - passiv
    bt = "✓ Aktiv ortiq" if diff >= 0 else "✗ Passiv ortiq"
    bc = "" if diff >= 0 else " red"
    p1t,p1c=cell(data,"1"); p2t,p2c=cell(data,"2")
    p3t,p3c=cell(data,"3"); p4t,p4c=cell(data,"4")
    p5t,p5c=cell(data,"5"); p6t,p6c=cell(data,"6")
    return f"""<!DOCTYPE html>
<html lang="uz"><head><meta charset="UTF-8">
<title>Balans varaqasi</title><style>{CSS}</style></head>
<body><div class="container">
  <div class="header"><div class="header-icon">📊</div>
    <div class="header-text"><h1>Balans varaqasi</h1>
    <p>Aktiv · Passiv · Nazorat &nbsp;|&nbsp; Valyuta: UZS</p></div></div>
  <div class="grid">
    <div class="card aktiv"><div class="card-title">📈 Aktiv</div>
      <div class="section-header">1. Pul mablag'lar</div>
      {rhtml(data,"1.1","1.1 Naqd pullar")}
      {rhtml(data,"1.2","1.2 Bank-hisoblar")}
      {thtml("Jami pul mablag'lar",p1t,p1c)}
      <div class="section-header">2. Mahsulotlar</div>
      {rhtml(data,"2.1","2.1 Omborxonadagi (zaxira)")}
      {rhtml(data,"2.2","2.2 Yo'ldagilar")}
      {thtml("Jami mahsulotlar",p2t,p2c)}
      <div class="section-header">3. Debitorlar</div>
      {rhtml(data,"3.1.1","3.1 Mijozlar — Avans")}
      {rhtml(data,"3.1.2","3.1 Mijozlar — Qarz")}
      {rhtml(data,"3.2.1","3.2 Ta'minotchilar — Avans")}
      {rhtml(data,"3.2.2","3.2 Ta'minotchilar — Qarz")}
      {rhtml(data,"3.3","3.3 Boshqa debitorlar")}
      {thtml("Jami debitorlar",p3t,p3c)}
      <div class="section-header">4. Asosiy vositalar</div>
      {rhtml(data,"4.1","4.1 Avtotransport")}
      {rhtml(data,"4.2","4.2 Ko'chmas mulk")}
      {rhtml(data,"4.3","4.3 Asbob uskunalar")}
      {rhtml(data,"4.4","4.4 Inventarlar")}
      {thtml("Jami asosiy vositalar",p4t,p4c)}
      <div class="card-footer">
        <span class="footer-label">JAMI AKTIV</span>
        <span class="aktiv footer-total">{to_str(aktiv)}</span>
      </div></div>
    <div class="card passiv"><div class="card-title">📉 Passiv</div>
      <div class="section-header">5. Kreditorlar</div>
      {rhtml(data,"5.1","5.1 Bank kreditlari")}
      {rhtml(data,"5.2","5.2 Qisqa muddatli qarzlar (zaim)")}
      {rhtml(data,"5.3","5.3 Oylik maoshlar")}
      {rhtml(data,"5.4","5.4 Boshqa kreditorlar")}
      {thtml("Jami kreditorlar",p5t,p5c)}
      <div class="section-header">6. Kapital</div>
      {rhtml(data,"6.1","6.1 Ustav fondi")}
      {rhtml(data,"6.2","6.2 Taqsimlanmagan foyda")}
      {thtml("Jami kapital",p6t,p6c)}
      <div class="card-footer" style="margin-top:auto">
        <span class="footer-label">JAMI PASSIV</span>
        <span class="passiv footer-total">{to_str(passiv)}</span>
      </div></div>
  </div>
  <div class="summary">
    <div class="summary-left">
      <div class="label">Balans farqi (Aktiv − Passiv)</div>
      <div class="value">{to_str(diff)}</div>
    </div>
    <div class="badge{bc}">{bt}</div>
  </div>
  <div class="date">Oxirgi yangilanish: {date_str}</div>
</div></body></html>"""

def take_screenshot(html):
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(html); html_path = f.name
    png_path = html_path.replace(".html", ".png")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width":1200,"height":900})
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        h = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width":1200,"height":h+48})
        page.screenshot(path=png_path, full_page=True)
        browser.close()
    os.unlink(html_path)
    return png_path

def send_photo(png_path, caption):
    with open(png_path,"rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id":CHAT_ID,"message_thread_id":THREAD_ID,"caption":caption},
            files={"photo":f})
    r.raise_for_status(); return r.json()

def main():
    print("📊 Sheet o'qilmoqda..."); data = read_sheet()
    print(f"   {len(data)} ta qiymat")
    print("📸 Screenshot olinmoqda..."); png = take_screenshot(generate_html(data))
    tz = pytz.timezone("Asia/Tashkent")
    res = send_photo(png, f"📊 Balans varaqasi — {datetime.now(tz).strftime('%d.%m.%Y')}")
    print(f"✓ Yuborildi! id={res['result']['message_id']}")
    os.unlink(png)

if __name__ == "__main__":
    main()
