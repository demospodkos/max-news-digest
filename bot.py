#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram digest bot v5."""
from __future__ import annotations
import html, json, os, re, time
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEO_LAT = os.environ.get("GEO_LAT", "").strip()
GEO_LON = os.environ.get("GEO_LON", "").strip()
GEO_CITY = os.environ.get("GEO_CITY", "").strip()
GEO_LABEL = os.environ.get("GEO_LABEL", "").strip()
ERROR_NOTIFY = os.environ.get("ERROR_NOTIFY", "1").lower() in ("1", "true", "yes")
LIVE = os.environ.get("LIVE", "").lower() in ("1", "true", "yes")
POLL = os.environ.get("POLL", "").lower() in ("1", "true", "yes")
if not LIVE and not POLL:
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER") or os.environ.get("FLY_APP_NAME"):
        LIVE = True
TG = f"https://api.telegram.org/bot{BOT_TOKEN}"
ROOT = Path(__file__).resolve().parent
GEO_FILE = ROOT / "geo.json"
OFFSET_FILE = Path(".tg_offset")
PREFS_FILE = ROOT / "prefs.json"
HTTP_TIMEOUT = (2.0, 6.0)
CACHE_TTL = 600
_CACHE: dict = {}
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Moscow")
except Exception:
    TZ = timezone(timedelta(hours=3))
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Mozilla/5.0 (compatible; TgDigestBot/5.0)"
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))
SESSION.mount("http://", HTTPAdapter(max_retries=Retry(total=0)))
CITIES = {"Москва": (55.7558, 37.6173), "СПб": (59.9343, 30.3351), "Новосибирск": (55.0084, 82.9357), "Екатеринбург": (56.8389, 60.6057), "Казань": (55.7961, 49.1064), "Краснодар": (45.0355, 38.9753), "Владивосток": (43.1155, 131.8855)}
TOP_KW = ("цб", "ставка", "нефть", "санкц", "курс", "доллар", "евро", "газ", "опек", "федрезерв", "фрс", "инфляц", "рубл", "бирж", "акци", "крипт", "биткоин", "войн", "перемир", "нато", "трамп", "путин", "правительств")
EVENTS_2026 = [("2026-10-24", "Заседание ЦБ РФ (ключевая ставка)"), ("2026-11-07", "Заседание ЦБ РФ (ориентир)"), ("2026-12-19", "Заседание ЦБ РФ (ориентир)"), ("2026-10-29", "Заседание ФРС (ориентир)"), ("2026-12-10", "Заседание ФРС (ориентир)"), ("2026-11-27", "Thanksgiving — рынки США закрыты"), ("2026-12-25", "Рождество — рынки США/EU закрыты"), ("2026-01-01", "Новый год — рынки закрыты"), ("2026-01-07", "Рождество (РФ) — выходной"), ("2026-02-23", "День защитника Отечества"), ("2026-03-08", "8 Марта"), ("2026-05-01", "Праздник Весны и Труда"), ("2026-05-09", "День Победы"), ("2026-06-12", "День России"), ("2026-11-04", "День народного единства")]

def get(url: str, **kw):
    kw.setdefault("timeout", HTTP_TIMEOUT)
    return SESSION.get(url, **kw)
def post_json(url: str, payload: dict):
    return SESSION.post(url, json=payload, timeout=(2, 12))
def esc(s) -> str:
    return html.escape(str(s), quote=False)
def now_str() -> str:
    return datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
def cache_get(key: str):
    row = _CACHE.get(key)
    if not row: return None
    ts, val = row
    if time.time() - ts > CACHE_TTL:
        _CACHE.pop(key, None); return None
    return val
def cache_set(key: str, val):
    _CACHE[key] = (time.time(), val); return val
def load_prefs() -> dict:
    try:
        if PREFS_FILE.exists():
            return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
    except Exception: pass
    return {"tickers": ["SBER", "GAZP", "LKOH", "ROSN", "GMKN"], "coins": ["bitcoin", "ethereum"], "prefer_short": False, "quiet_start": None, "quiet_end": None, "news_cat": "all", "geo_reminded": None}
def save_prefs(p: dict) -> None:
    try: PREFS_FILE.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e: print("prefs", e)
def in_quiet_hours() -> bool:
    p = load_prefs(); qs, qe = p.get("quiet_start"), p.get("quiet_end")
    if not qs or not qe: return False
    try:
        now = datetime.now(TZ).time()
        h1, m1 = map(int, qs.split(":")); h2, m2 = map(int, qe.split(":"))
        t1, t2 = dtime(h1, m1), dtime(h2, m2)
        if t1 <= t2: return t1 <= now <= t2
        return now >= t1 or now <= t2
    except Exception: return False
def load_geo():
    try:
        if GEO_FILE.exists():
            d = json.loads(GEO_FILE.read_text(encoding="utf-8"))
            if "lat" in d and "lon" in d:
                return float(d["lat"]), float(d["lon"]), d.get("label") or "Telegram"
    except Exception: pass
    return None
def save_geo(lat: float, lon: float, label: str | None = None):
    try:
        GEO_FILE.write_text(json.dumps({"lat": lat, "lon": lon, "label": label or f"{lat:.4f},{lon:.4f}", "source": "telegram", "updated_at": datetime.now(TZ).isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e: print("save_geo", e)
def resolve_geo():
    g = load_geo()
    if g: return g
    if GEO_LAT and GEO_LON:
        try: return float(GEO_LAT), float(GEO_LON), GEO_LABEL or f"{GEO_LAT},{GEO_LON}"
        except ValueError: pass
    if GEO_CITY:
        try:
            r = get("https://geocoding-api.open-meteo.com/v1/search", params={"name": GEO_CITY, "count": 1, "language": "ru"})
            rows = (r.json() or {}).get("results") or []
            if rows:
                p = rows[0]
                return float(p["latitude"]), float(p["longitude"]), GEO_LABEL or p.get("name") or GEO_CITY
        except Exception as e: print("geocode", type(e).__name__)
    return None
def wind_dir_name(deg) -> str:
    try: d = float(deg) % 360
    except Exception: return "—"
    names = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ", "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]
    return names[int((d + 11.25) / 22.5) % 16]
def block_weather() -> str:
    geo = resolve_geo()
    if not geo: return "🌤 <b>Погода</b>\nТочка не задана. «📍 Гео» или «🏙 Город»"
    lat, lon, label = geo
    ck = f"wx:{lat:.3f}:{lon:.3f}"
    cached = cache_get(ck)
    if cached: return cached
    try:
        r = get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "current": "temperature_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m,wind_direction_10m,weather_code,relative_humidity_2m", "daily": "sunrise,sunset", "timezone": "Europe/Moscow", "forecast_days": 1})
        if r.status_code != 200: return f"🌤 Погода\nHTTP {r.status_code}"
        data = r.json(); c = data.get("current") or {}; d = data.get("daily") or {}
        codes = {0: "ясно", 1: "почти ясно", 2: "облачно", 3: "пасмурно", 45: "туман", 61: "дождь", 71: "снег", 73: "снег", 75: "сильный снег", 80: "ливень", 85: "снегопад", 95: "гроза"}
        try: w = codes.get(int(c.get("weather_code")), "—")
        except Exception: w = "—"
        sr = (d.get("sunrise") or ["?"])[0]; ss = (d.get("sunset") or ["?"])[0]
        if isinstance(sr, str) and "T" in sr: sr = sr.split("T")[1][:5]
        if isinstance(ss, str) and "T" in ss: ss = ss.split("T")[1][:5]
        wdir = c.get("wind_direction_10m"); wname = wind_dir_name(wdir)
        text = (f"🌤 <b>Погода — {esc(label)}</b>\n📍 {lat:.3f}, {lon:.3f}\n{w}\nТемп: {c.get('temperature_2m')}°C (ощущ. {c.get('apparent_temperature')}°C)\nВетер: {c.get('wind_speed_10m')} м/с, {wname} ({wdir}°), порывы {c.get('wind_gusts_10m')} м/с\nВлажность: {c.get('relative_humidity_2m')}%\nВосход {sr} · закат {ss}")
        return cache_set(ck, text)
    except Exception as e: return f"🌤 Погода\nошибка: {type(e).__name__}"
def block_kp() -> str:
    ck = "kp"; cached = cache_get(ck)
    if cached: return cached
    try:
        rows = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json").json()
        if not rows: return "🧲 Магн. бури\nнет данных"
        last = rows[-1]
        if isinstance(last, dict):
            kp = float(last.get("Kp") or last.get("kp") or 0); tag = last.get("time_tag") or ""
        else:
            if isinstance(last[0], str) and str(last[0]).lower().startswith("time"): last = rows[-2] if len(rows) > 1 else last
            kp = float(last[1]); tag = last[0]
        lvl = "спокойно" if kp < 4 else "неспокойно" if kp < 5 else "G1" if kp < 6 else "G2" if kp < 7 else "G3" if kp < 8 else "G4+"
        return cache_set(ck, f"🧲 <b>Kp = {kp}</b> — {lvl}\n{tag} UTC")
    except Exception as e: return f"🧲 Магн. бури\nошибка: {type(e).__name__}"
def block_fx() -> str:
    ck = "fx"; cached = cache_get(ck)
    if cached: return cached
    try:
        v = get("https://www.cbr-xml-daily.ru/daily_json.js").json()["Valute"]
        lines = ["💱 <b>Курсы ЦБ</b>"]
        for code in ("USD", "EUR", "CNY"):
            if code not in v: continue
            val = v[code]["Value"]; prev = v[code].get("Previous", val); d = val - prev
            a = "▲" if d > 0 else ("▼" if d < 0 else "•")
            lines.append(f"{code}: {val:.2f} ₽ ({a}{abs(d):.2f})")
        return cache_set(ck, "\n".join(lines))
    except Exception as e: return f"💱 Курсы\nошибка: {type(e).__name__}"
def block_macro() -> str:
    ck = "macro"; cached = cache_get(ck)
    if cached: return cached
    try:
        r = get("https://www.cbr.ru/hd_base/KeyRate/")
        rows = re.findall(r"<td[^>]*>\s*(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*([\d,]+)\s*</td>", r.text)
        if not rows: return "🏛 Макро\nставка ЦБ: нет данных"
        date, rate = rows[0]; rate = rate.replace(",", ".")
        next_cbr = None; today = datetime.now(TZ).date()
        for ds, title in EVENTS_2026:
            if "ЦБ" in title:
                try:
                    d = datetime.strptime(ds, "%Y-%m-%d").date()
                    if d >= today: next_cbr = f"{d.strftime('%d.%m.%Y')} — {title}"; break
                except Exception: pass
        lines = ["🏛 <b>Макро</b>", f"Ключевая ставка ЦБ: <b>{rate}%</b> (на {date})"]
        if next_cbr: lines.append(f"Ближайшее: {esc(next_cbr)}")
        return cache_set(ck, "\n".join(lines))
    except Exception as e: return f"🏛 Макро\nошибка: {type(e).__name__}"
def block_oil() -> str:
    ck = "oil"; cached = cache_get(ck)
    if cached: return cached
    try:
        r = get("https://iss.moex.com/iss/engines/futures/markets/forts/securities.json", params={"iss.meta": "off", "iss.only": "securities,marketdata"})
        md = (r.json().get("marketdata") or {}); mc, mdt = md.get("columns") or [], md.get("data") or []
        if not mc: return "🛢 Нефть\nнет данных"
        i_md_sid = mc.index("SECID"); i_last = mc.index("LAST") if "LAST" in mc else None; i_chg = mc.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in mc else None
        prices = []
        for row in mdt:
            sid = row[i_md_sid]
            if not (isinstance(sid, str) and sid.startswith("BR") and len(sid) <= 5): continue
            last = row[i_last] if i_last is not None else None
            if last is None: continue
            chg = row[i_chg] if i_chg is not None else None
            prices.append((sid, float(last), chg))
        if not prices: return "🛢 Нефть\nнет котировок BR"
        prices.sort(key=lambda x: x[0]); lines = ["🛢 <b>Нефть Brent (MOEX BR)</b>"]
        for sid, last, chg in prices[:3]:
            if chg is not None:
                a = "▲" if chg > 0 else ("▼" if chg < 0 else "•"); lines.append(f"{sid}: ${last:.2f} ({a}{abs(chg):.2f}%)")
            else: lines.append(f"{sid}: ${last:.2f}")
        lines.append("$/баррель"); return cache_set(ck, "\n".join(lines))
    except Exception as e: return f"🛢 Нефть\nошибка: {type(e).__name__}"
def _stooq_last(symbol: str):
    try:
        r = get(f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv")
        lines = [ln for ln in r.text.strip().splitlines() if ln and not ln.lower().startswith("symbol")]
        if not lines: return None
        parts = lines[0].split(",")
        if len(parts) >= 7: return float(parts[6])
    except Exception: pass
    return None
def block_indices() -> str:
    ck = "idx"; cached = cache_get(ck)
    if cached: return cached
    lines = ["📉 <b>Индексы</b>"]
    for code, title in (("IMOEX", "IMOEX"), ("RTSI", "RTSI")):
        try:
            r = get(f"https://iss.moex.com/iss/engines/stock/markets/index/securities/{code}.json", params={"iss.meta": "off", "iss.only": "marketdata"})
            md = r.json().get("marketdata") or {}; cols, data = md.get("columns") or [], md.get("data") or []
            if cols and data:
                i_last = cols.index("CURRENTVALUE") if "CURRENTVALUE" in cols else (cols.index("LAST") if "LAST" in cols else None)
                i_chg = cols.index("LASTCHANGEPRC") if "LASTCHANGEPRC" in cols else None
                row = data[0]
                if i_last is not None and row[i_last] is not None:
                    last = row[i_last]
                    if i_chg is not None and row[i_chg] is not None:
                        chg = float(row[i_chg]); a = "▲" if chg > 0 else ("▼" if chg < 0 else "•"); lines.append(f"{title}: {last} ({a}{abs(chg):.2f}%)")
                    else: lines.append(f"{title}: {last}")
        except Exception as e: print("idx", code, type(e).__name__)
    spx = _stooq_last("%5Espx"); ndq = _stooq_last("%5Endq")
    if spx: lines.append(f"S&P 500: {spx:,.2f}")
    if ndq: lines.append(f"Nasdaq: {ndq:,.2f}")
    if len(lines) == 1: return "📉 Индексы\nнет данных"
    return cache_set(ck, "\n".join(lines))
def block_crypto() -> str:
    ck = "crypto"; cached = cache_get(ck)
    if cached: return cached
    try:
        r = get("https://api.coingecko.com/api/v3/coins/markets", params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 10, "page": 1, "sparkline": "false", "price_change_percentage": "24h"})
        if r.status_code == 429: return "₿ Крипта\nлимит API, позже"
        if r.status_code != 200: return f"₿ Крипта\nHTTP {r.status_code}"
        rows = r.json()
        if not rows: return "₿ Крипта\nнет данных"
        lines = ["₿ <b>Топ-10 крипты</b>"]
        for i, c in enumerate(rows, 1):
            sym = (c.get("symbol") or "?").upper(); price = c.get("current_price") or 0; chg = c.get("price_change_percentage_24h")
            if chg is not None:
                a = "▲" if chg > 0 else ("▼" if chg < 0 else "•"); lines.append(f"{i}. {sym}: ${price:,.2f} ({a}{abs(chg):.1f}% 24ч)")
            else: lines.append(f"{i}. {sym}: ${price:,.2f}")
        prefs = load_prefs(); my = prefs.get("coins") or []
        if my:
            ids = ",".join(my[:8])
            try:
                r2 = get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"})
                if r2.status_code == 200:
                    data = r2.json(); lines.append("<b>Мои монеты</b>")
                    for cid in my[:8]:
                        if cid in data:
                            p = data[cid].get("usd", 0); ch = data[cid].get("usd_24h_change")
                            if ch is not None:
                                a = "▲" if ch > 0 else ("▼" if ch < 0 else "•"); lines.append(f"{cid}: ${p:,.2f} ({a}{abs(ch):.1f}%)")
                            else: lines.append(f"{cid}: ${p:,.2f}")
            except Exception: pass
        return cache_set(ck, "\n".join(lines))
    except Exception as e: return f"₿ Крипта\nошибка: {type(e).__name__}"
def block_metals() -> str:
    ck = "metals"; cached = cache_get(ck)
    if cached: return cached
    lines = ["🥇 <b>Драгметаллы</b>"]
    try:
        today = datetime.now(TZ); d1 = (today - timedelta(days=5)).strftime("%d/%m/%Y"); d2 = today.strftime("%d/%m/%Y")
        r = get(f"https://www.cbr.ru/scripts/xml_metall.asp?date_req1={d1}&date_req2={d2}")
        text = r.content.decode("cp1251", errors="replace")
        rec = re.findall(r'Code="(\d)".*?<Buy>([^<]+)</Buy>', text, re.DOTALL)
        names = {"1": "Au", "2": "Ag", "3": "Pt", "4": "Pd"}; latest = {}
        for code, buy in rec:
            try: latest[code] = float(buy.replace(",", "."))
            except ValueError: pass
        if latest:
            lines.append("₽/г (ЦБ):")
            for c, n in names.items():
                if c in latest: lines.append(f"  {n}: {latest[c]:,.1f}".replace(",", " "))
    except Exception as e: print("metals cbr", type(e).__name__)
    xau = _stooq_last("xauusd"); xag = _stooq_last("xagusd")
    if xau or xag:
        lines.append("$/унц. (мир):")
        if xau: lines.append(f"  Au: ${xau:,.1f}")
        if xag: lines.append(f"  Ag: ${xag:,.2f}")
    if len(lines) == 1: return "🥇 Металлы\nнет данных"
    return cache_set(ck, "\n".join(lines))
def block_stocks() -> str:
    prefs = load_prefs(); tickers = [t.upper().strip() for t in (prefs.get("tickers") or ["SBER", "GAZP", "LKOH", "ROSN", "GMKN"]) if t][:12]
    ck = "stk:" + ",".join(tickers); cached = cache_get(ck)
    if cached: return cached
    try:
        r = get("https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json", params={"securities": ",".join(tickers), "iss.meta": "off", "iss.only": "marketdata"})
        md = r.json().get("marketdata") or {}; cols, rows = md.get("columns") or [], md.get("data") or []
        if not cols or not rows: return "📈 Акции\nнет данных"
        i_id = cols.index("SECID") if "SECID" in cols else 0
        i_last = cols.index("LAST") if "LAST" in cols else None
        i_chg = cols.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in cols else None
        lines = ["📈 <b>Акции</b> (мои тикеры)"]
        for row in rows:
            if i_last is None or row[i_last] is None: continue
            sid, last = row[i_id], row[i_last]
            if i_chg is not None and row[i_chg] is not None:
                chg = row[i_chg]; a = "▲" if chg > 0 else ("▼" if chg < 0 else "•"); lines.append(f"{sid}: {last} ({a}{abs(chg):.2f}%)")
            else: lines.append(f"{sid}: {last}")
        return cache_set(ck, "\n".join(lines) if len(lines) > 1 else "📈 Акции\nнет данных")
    except Exception as e: return f"📈 Акции\nошибка: {type(e).__name__}"
def block_calendar() -> str:
    today = datetime.now(TZ).date(); upcoming = []
    for ds, title in sorted(EVENTS_2026, key=lambda x: x[0]):
        try: d = datetime.strptime(ds, "%Y-%m-%d").date()
        except Exception: continue
        if d < today or d > today + timedelta(days=45): continue
        upcoming.append(f"• {d.strftime('%d.%m')}: {title}")
        if len(upcoming) >= 8: break
    if not upcoming: return "📅 Календарь\nнет событий на 45 дней"
    return "📅 <b>Календарь (45 дн.)</b>\n" + "\n".join(upcoming)
def _clean_xml_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or ""); s = html.unescape(s); return re.sub(r"\s+", " ", s).strip()
def _extract_link(block: str) -> str:
    for pat in (r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", r"<link[^>]+href=[\"\'](.*?)[\"\']", r"<guid[^>]*>(?:<!\[CDATA\[)?(https?://.*?)(?:\]\]>)?</guid>"):
        m = re.search(pat, block, re.I | re.S)
        if m:
            link = _clean_xml_text(m.group(1)).split()[0] if m.group(1) else ""
            if link.startswith("http"): return link
    return ""
def _norm_title(t: str) -> str:
    t = t.lower(); t = re.sub(r"[^\w\sа-яё]", " ", t, flags=re.I); return re.sub(r"\s+", " ", t).strip()[:90]
def _parse_rss_items(text: str, src: str, max_items: int = 12, category: str = "all"):
    out = []; blocks = re.findall(r"<item(?:\s[^>]*)?>(.*?)</item>", text, re.I | re.S)
    cat_kw = {"polit": ("политик", "выбор", "президент", "правитель", "госдум", "нато", "войн"), "econ": ("экономик", "курс", "рубл", "банк", "инфляц", "ставк", "нефть", "бюджет", "налог"), "tech": ("технолог", "ии", "ai", "смартфон", "софт", "хакер", "интернет", "google", "apple"), "world": ("сша", "китай", "европ", "украин", "ближн", "оон", "международ")}
    for block in blocks[: max_items + 4]:
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.I | re.S)
        dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", block, re.I | re.S)
        title = _clean_xml_text(tm.group(1) if tm else ""); desc = _clean_xml_text(dm.group(1) if dm else ""); link = _extract_link(block)
        if not title or title.lower() in (src.lower(), "новости", "news"): continue
        blob = (title + " " + desc).lower()
        if category != "all" and category in cat_kw:
            if not any(k in blob for k in cat_kw[category]): continue
        if desc and (desc.lower().startswith(title.lower()[:40]) or desc == title): desc = ""
        if len(desc) > 160: desc = desc[:157].rsplit(" ", 1)[0] + "…"
        out.append((src, title, desc, link))
        if len(out) >= max_items: break
    return out
def fetch_news(limit: int = 35, category: str = "all") -> list:
    feeds = [("РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", 12), ("Интерфакс", "https://www.interfax.ru/rss.asp", 10), ("ТАСС", "https://tass.ru/rss/v2.xml", 8), ("РИА", "https://ria.ru/export/rss2/index.xml", 8), ("BFM", "https://www.bfm.ru/news.rss", 8), ("Лента", "https://lenta.ru/rss/news", 8)]
    items = []
    for src, url, n in feeds:
        try: items.extend(_parse_rss_items(get(url).text, src, n, category))
        except Exception as e: print("rss", src, type(e).__name__)
    seen, out = set(), []
    for src, title, desc, link in items:
        k = _norm_title(title)
        if k in seen: continue
        near = k[:50]
        if any(near == s[:50] for s in seen): continue
        seen.add(k); out.append((src, title, desc, link))
        if len(out) >= limit: break
    return out
def block_news(limit: int = 35, category: str | None = None) -> str:
    prefs = load_prefs(); cat = category or prefs.get("news_cat") or "all"
    items = fetch_news(limit, cat)
    if not items: return "📰 Новости\nнет данных"
    top, rest = [], []
    for it in items:
        blob = (it[1] + " " + (it[2] or "")).lower()
        score = sum(1 for kw in TOP_KW if kw in blob)
        (top if score >= 1 else rest).append((score, it))
    top.sort(key=lambda x: -x[0]); ordered = [it for _, it in top[:7]] + [it for _, it in rest]; ordered = ordered[:limit]
    cat_label = {"all": "все", "polit": "политика", "econ": "экономика", "tech": "технологии", "world": "мир"}.get(cat, cat)
    lines = [f"📰 <b>Новости</b> ({len(ordered)}, {cat_label})", "<i>Топ дня ★ · заголовок — ссылка на статью</i>"]
    top_titles = {_norm_title(t) for _, (s, t, d, l) in top[:7]}
    for i, (src, title, desc, link) in enumerate(ordered, 1):
        star = "★ " if _norm_title(title) in top_titles else ""
        if link:
            safe = link.replace("&", "&").replace('"', "%22"); head = f'<a href="{safe}">{esc(title)}</a>'
        else: head = esc(title)
        lines.append(f"{i}. {star}<b>[{src}]</b> {head}")
        if desc: lines.append(f"   <i>{esc(desc)}</i>")
    return "\n".join(lines)
def block_short() -> str:
    parts = []
    try:
        v = get("https://www.cbr-xml-daily.ru/daily_json.js").json()["Valute"]
        parts.append(f"USD {v['USD']['Value']:.1f}"); parts.append(f"EUR {v['EUR']['Value']:.1f}")
    except Exception: pass
    try:
        oil = block_oil(); m = re.search(r"\$(\d+[.,]\d+)", oil)
        if m: parts.append(f"Brent ${m.group(1)}")
    except Exception: pass
    try:
        r = get("https://api.coingecko.com/api/v3/simple/price", params={"ids": "bitcoin", "vs_currencies": "usd"})
        if r.status_code == 200: parts.append(f"BTC ${r.json()['bitcoin']['usd']:,.0f}")
    except Exception: pass
    try:
        macro = block_macro(); m = re.search(r"(\d+[.,]\d+)\s*%", macro)
        if m: parts.append(f"ставка {m.group(1)}%")
    except Exception: pass
    try:
        idx = block_indices(); m = re.search(r"IMOEX:\s*([\d.]+)", idx)
        if m: parts.append(f"IMOEX {m.group(1)}")
    except Exception: pass
    if resolve_geo():
        try:
            w = block_weather(); m = re.search(r"Темп:\s*([-\d.]+)°C", w)
            if m: parts.append(f"{m.group(1)}°C")
        except Exception: pass
    return "⚡ " + " · ".join(parts) if parts else "⚡ сводка"
def _safe(fn, fb: str) -> str:
    try: return fn()
    except Exception as e:
        if ERROR_NOTIFY and CHAT_ID and BOT_TOKEN:
            try: post_json(f"{TG}/sendMessage", {"chat_id": CHAT_ID, "text": f"⚠ блок {fb}: {type(e).__name__}"})
            except Exception: pass
        return f"{fb}\n{type(e).__name__}"
def maybe_geo_remind(chat_id) -> None:
    if resolve_geo(): return
    p = load_prefs(); last = p.get("geo_reminded"); today = datetime.now(TZ).strftime("%Y-%m-%d")
    if last == today: return
    if last:
        try:
            d = datetime.strptime(last, "%Y-%m-%d").date()
            if (datetime.now(TZ).date() - d).days < 3: return
        except Exception: pass
    p["geo_reminded"] = today; save_prefs(p)
    send(chat_id, "📍 Напоминание: геоточка не задана.\n«📍 Гео» или «🏙 Город».")
def build_digest(full: bool | None = None) -> str:
    prefs = load_prefs()
    if full is None: full = not prefs.get("prefer_short", False)
    t0 = time.time()
    parts = [f"{'📊' if full else '⚡'} <b>Дайджест {now_str()}</b> МСК", _safe(block_short, "⚡")]
    if not full:
        print(f"digest short {time.time()-t0:.1f}s"); return "\n\n".join(parts)
    parts += [_safe(block_weather, "🌤"), _safe(block_kp, "🧲"), _safe(block_macro, "🏛"), _safe(block_fx, "💱"), _safe(block_oil, "🛢"), _safe(block_indices, "📉"), _safe(block_crypto, "₿"), _safe(block_metals, "🥇"), _safe(block_stocks, "📈"), _safe(block_calendar, "📅"), _safe(lambda: block_news(35), "📰")]
    print(f"digest {time.time()-t0:.1f}s"); return "\n\n".join(parts)
L_DIGEST, L_SHORT, L_WEATHER, L_KP, L_RATES, L_CRYPTO, L_NEWS, L_GEO, L_LOC = "📊 Дайджест", "⚡ Кратко", "🌤 Погода", "🧲 Магн. бури", "💱 Курсы", "₿ Крипта", "📰 Новости", "📍 Точка", "📍 Гео"
L_MACRO, L_IDX, L_CAL, L_CITY, L_HIDE, L_SET = "🏛 Макро", "📉 Индексы", "📅 Календарь", "🏙 Город", "🙈 Скрыть", "⚙️ Настройки"
KEYBOARD = {"keyboard": [[{ "text": L_DIGEST}, {"text": L_SHORT}], [{"text": L_WEATHER}, {"text": L_KP}], [{"text": L_RATES}, {"text": L_MACRO}], [{"text": L_CRYPTO}, {"text": L_IDX}], [{"text": L_NEWS}, {"text": L_CAL}], [{"text": L_GEO}, {"text": L_CITY}], [{"text": L_LOC, "request_location": True}, {"text": L_HIDE}], [{"text": L_SET}]], "resize_keyboard": True, "is_persistent": False, "input_field_placeholder": "Свернуть: ⌄"}
CITY_KB = {"keyboard": [[{ "text": c} for c in list(CITIES.keys())[i:i+2]] for i in range(0, len(CITIES), 2)] + [[{"text": "« Назад"}]], "resize_keyboard": True, "is_persistent": False}
def send(chat_id, text: str, with_kb: bool = True, remove_kb: bool = False) -> bool:
    chunks = []
    while text:
        if len(text) <= 3900: chunks.append(text); break
        cut = text.rfind("\n", 0, 3900)
        if cut < 50: cut = 3900
        chunks.append(text[:cut]); text = text[cut:].lstrip("\n")
    ok = True
    for i, ch in enumerate(chunks):
        body = {"chat_id": chat_id, "text": ch, "parse_mode": "HTML", "disable_web_page_preview": True}
        if i == len(chunks) - 1:
            if remove_kb: body["reply_markup"] = {"remove_keyboard": True}
            elif with_kb: body["reply_markup"] = KEYBOARD
        try:
            data = post_json(f"{TG}/sendMessage", body).json()
            print("send", data.get("ok"), data.get("description", ""))
            if not data.get("ok"):
                body.pop("parse_mode", None)
                if not post_json(f"{TG}/sendMessage", body).json().get("ok"): ok = False
        except Exception as e:
            print("send err", type(e).__name__); ok = False
    return ok
def send_collecting(chat_id, tip: str = "Собираю данные…") -> None:
    try: post_json(f"{TG}/sendMessage", {"chat_id": chat_id, "text": f"⏳ {tip}", "disable_notification": True})
    except Exception: pass
def norm(s: str) -> str:
    s = (s or "").strip().lower(); s = re.sub(r"[^\w\sа-яё]+", " ", s, flags=re.I); return re.sub(r"\s+", " ", s).strip()
def on_location(chat_id, lat: float, lon: float):
    save_geo(lat, lon); send(chat_id, f"📍 Точка: <code>{lat:.5f}</code>, <code>{lon:.5f}</code>\n\n" + block_weather())
def settings_help() -> str:
    p = load_prefs()
    return ("⚙️ <b>Настройки</b>\n\n" f"Тикеры: <code>{', '.join(p.get('tickers') or [])}</code>\n" f"Монеты: <code>{', '.join(p.get('coins') or [])}</code>\n" f"Краткий по умолчанию: {'да' if p.get('prefer_short') else 'нет'}\n" f"Тихие часы: {p.get('quiet_start') or '—'}–{p.get('quiet_end') or '—'}\n" f"Категория новостей: {p.get('news_cat') or 'all'}\n\n" "<b>Команды:</b>\n/tickers SBER GAZP YNDX\n/coins bitcoin ethereum solana\n/short_on | /short_off\n/quiet 22:00 07:00 | /quiet off\n/news_cat all|polit|econ|tech|world\n/hide · /menu")
def on_text(chat_id, text: str):
    raw = (text or "").strip(); n = norm(raw); print(f"MSG raw={raw!r}")
    for name, (lat, lon) in CITIES.items():
        if raw == name or n == name.lower():
            save_geo(lat, lon, name); send(chat_id, f"🏙 Город: {esc(name)}\n\n" + block_weather()); return
    if raw == "« Назад": send(chat_id, "Меню:", with_kb=True); return
    try:
        if raw in ("/start", "/menu"):
            send(chat_id, "Бот онлайн (v5).\nМакро, индексы, топ-10 крипты, календарь, новости со ссылками.\nПогода с направлением ветра. /hide — скрыть кнопки.")
            maybe_geo_remind(chat_id); send_collecting(chat_id, "Собираю дайджест…"); send(chat_id, build_digest(True)); return
        if raw in ("/hide", L_HIDE) or "скрыт" in n:
            send(chat_id, "Клавиатура скрыта. /menu — вернуть.", remove_kb=True, with_kb=False); return
        if raw in (L_SET, "/settings") or "настрой" in n: send(chat_id, settings_help()); return
        if raw.startswith("/tickers"):
            parts = raw.split()[1:]; p = load_prefs()
            if parts: p["tickers"] = [x.upper().strip() for x in parts if x.strip()][:12]; save_prefs(p); _CACHE.clear()
            send(chat_id, f"Тикеры: {', '.join(p.get('tickers') or [])}\n\n" + block_stocks()); return
        if raw.startswith("/coins"):
            parts = raw.split()[1:]; p = load_prefs()
            if parts: p["coins"] = [x.lower().strip() for x in parts if x.strip()][:8]; save_prefs(p); _CACHE.clear()
            send(chat_id, f"Монеты: {', '.join(p.get('coins') or [])}\n\n" + block_crypto()); return
        if raw == "/short_on":
            p = load_prefs(); p["prefer_short"] = True; save_prefs(p); send(chat_id, "По умолчанию — краткий дайджест."); return
        if raw == "/short_off":
            p = load_prefs(); p["prefer_short"] = False; save_prefs(p); send(chat_id, "По умолчанию — полный дайджест."); return
        if raw.startswith("/quiet"):
            parts = raw.split(); p = load_prefs()
            if len(parts) >= 2 and parts[1].lower() == "off":
                p["quiet_start"] = p["quiet_end"] = None; save_prefs(p); send(chat_id, "Тихие часы выключены."); return
            if len(parts) >= 3:
                p["quiet_start"], p["quiet_end"] = parts[1], parts[2]; save_prefs(p); send(chat_id, f"Тихие часы: {parts[1]}–{parts[2]}."); return
            send(chat_id, "Формат: /quiet 22:00 07:00 или /quiet off"); return
        if raw.startswith("/news_cat"):
            parts = raw.split(); cat = parts[1] if len(parts) > 1 else "all"
            if cat not in ("all", "polit", "econ", "tech", "world"):
                send(chat_id, "Категории: all, polit, econ, tech, world"); return
            p = load_prefs(); p["news_cat"] = cat; save_prefs(p); send_collecting(chat_id, "Новости…"); send(chat_id, block_news(35, cat)); return
        if raw in (L_DIGEST, "/now", "/digest") or "дайджест" in n:
            send_collecting(chat_id); send(chat_id, build_digest(True)); maybe_geo_remind(chat_id); return
        if raw in (L_SHORT, "/short") or "кратко" in n: send(chat_id, build_digest(False)); return
        if raw in (L_WEATHER, "/weather") or "погод" in n: send(chat_id, block_weather()); return
        if raw in (L_RATES, "/rates") or "курс" in n or "нефть" in n:
            send_collecting(chat_id); send(chat_id, block_fx() + "\n\n" + block_oil() + "\n\n" + block_metals()); return
        if raw in (L_MACRO, "/macro") or "макро" in n or "ставк" in n: send(chat_id, block_macro()); return
        if raw in (L_IDX, "/index", "/indices") or "индекс" in n:
            send_collecting(chat_id); send(chat_id, block_indices()); return
        if raw in (L_CRYPTO, "/crypto") or "крипт" in n:
            send_collecting(chat_id); send(chat_id, block_crypto()); return
        if raw in (L_KP, "/kp") or "магн" in n or n == "бури": send(chat_id, block_kp()); return
        if raw in (L_NEWS, "/news") or "новост" in n:
            send_collecting(chat_id, "Новости…"); send(chat_id, block_news(35)); return
        if raw in (L_CAL, "/calendar") or "календар" in n: send(chat_id, block_calendar()); return
        if raw in (L_CITY, "/city") or "город" in n:
            post_json(f"{TG}/sendMessage", {"chat_id": chat_id, "text": "Выберите город:", "reply_markup": CITY_KB}); return
        if raw in (L_GEO, "/geo") or "точк" in n:
            g = resolve_geo(); msg = "📍 <b>Геоточка</b>\n"; msg += f"{esc(g[2])}: {g[0]:.4f}, {g[1]:.4f}" if g else "не задана — «📍 Гео» или «🏙 Город»"; send(chat_id, msg); return
        send(chat_id, f"Не понял: {esc(raw)}\nЖмите кнопки или /settings")
    except Exception as e:
        print("on_text", type(e).__name__, e)
        try: send(chat_id, f"Ошибка: {type(e).__name__}")
        except Exception: pass
def read_offset() -> int:
    try:
        if OFFSET_FILE.exists(): return int(OFFSET_FILE.read_text().strip() or "0")
    except Exception: pass
    return 0
def write_offset(off: int) -> None:
    try: OFFSET_FILE.write_text(str(off))
    except Exception as e: print("offset", e)
def process_updates(long_poll: bool = False) -> int:
    if not BOT_TOKEN: print("no token"); return 0
    try: post_json(f"{TG}/deleteWebhook", {})
    except Exception: pass
    offset = read_offset(); handled = 0
    timeout = 25 if long_poll else 0; http_to = (5, 35) if long_poll else (2, 10)
    try:
        r = SESSION.get(f"{TG}/getUpdates", params={"timeout": timeout, "offset": offset}, timeout=http_to)
        data = r.json()
    except requests.exceptions.ReadTimeout: return 0
    except Exception as e: print("getUpdates", type(e).__name__, e); return 0
    if not data.get("ok"): print("getUpdates bad", data); return 0
    for u in data.get("result") or []:
        offset = u["update_id"] + 1
        msg = u.get("message") or u.get("edited_message")
        if not msg: continue
        cid = msg["chat"]["id"]
        if CHAT_ID and str(cid) != str(CHAT_ID).strip(): continue
        if "location" in msg:
            loc = msg["location"]; on_location(cid, float(loc["latitude"]), float(loc["longitude"])); handled += 1
        elif msg.get("text"):
            on_text(cid, msg["text"]); handled += 1
    write_offset(offset)
    if handled: print(f"processed={handled} offset={offset}")
    return handled
def run_live():
    print("LIVE v5"); fail = 0
    while True:
        try: process_updates(long_poll=True); fail = 0
        except Exception as e:
            fail += 1; print("live", type(e).__name__, e); time.sleep(min(30, 2 * fail))
def main():
    if LIVE: run_live(); return
    if POLL: process_updates(long_poll=False); return
    if in_quiet_hours(): print("quiet hours — skip digest"); return
    print("Building digest…"); text = build_digest(True); print("len", len(text))
    if not BOT_TOKEN or not CHAT_ID:
        print(text[:2500]); raise SystemExit("Нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    ok = send(CHAT_ID, text, with_kb=True); print("OK" if ok else "FAILED")
    if not ok: raise SystemExit(1)
if __name__ == "__main__":
    main()
