#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram digest bot — нефть, топ-5 крипты, 30+ новостей (РБК и др.)."""

from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
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

LIVE = os.environ.get("LIVE", "").lower() in ("1", "true", "yes")
POLL = os.environ.get("POLL", "").lower() in ("1", "true", "yes")
if not LIVE and not POLL:
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER") or os.environ.get("FLY_APP_NAME"):
        LIVE = True

TG = f"https://api.telegram.org/bot{BOT_TOKEN}"
ROOT = Path(__file__).resolve().parent
GEO_FILE = ROOT / "geo.json"
OFFSET_FILE = Path(".tg_offset")
HTTP_TIMEOUT = (2.0, 5.0)

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Europe/Moscow")
except Exception:
    TZ = timezone(timedelta(hours=3))

SESSION = requests.Session()
SESSION.headers["User-Agent"] = (
    "Mozilla/5.0 (compatible; TgDigestBot/4.2; +https://github.com/demospodkos/max-news-digest)"
)
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))
SESSION.mount("http://", HTTPAdapter(max_retries=Retry(total=0)))


def get(url: str, **kw):
    kw.setdefault("timeout", HTTP_TIMEOUT)
    return SESSION.get(url, **kw)


def post_json(url: str, payload: dict):
    return SESSION.post(url, json=payload, timeout=(2, 12))


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def now_str() -> str:
    return datetime.now(TZ).strftime("%d.%m.%Y %H:%M")


def load_geo():
    try:
        if GEO_FILE.exists():
            d = json.loads(GEO_FILE.read_text(encoding="utf-8"))
            if "lat" in d and "lon" in d:
                return float(d["lat"]), float(d["lon"]), d.get("label") or "Telegram"
    except Exception:
        pass
    return None


def save_geo(lat: float, lon: float):
    try:
        GEO_FILE.write_text(
            json.dumps(
                {
                    "lat": lat,
                    "lon": lon,
                    "label": f"{lat:.4f},{lon:.4f}",
                    "source": "telegram",
                    "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        print("save_geo", e)


def resolve_geo():
    g = load_geo()
    if g:
        return g
    if GEO_LAT and GEO_LON:
        try:
            return float(GEO_LAT), float(GEO_LON), GEO_LABEL or f"{GEO_LAT},{GEO_LON}"
        except ValueError:
            pass
    if GEO_CITY:
        try:
            r = get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": GEO_CITY, "count": 1, "language": "ru"},
            )
            rows = (r.json() or {}).get("results") or []
            if rows:
                p = rows[0]
                return float(p["latitude"]), float(p["longitude"]), GEO_LABEL or p.get("name") or GEO_CITY
        except Exception as e:
            print("geocode", type(e).__name__)
    return None


def block_weather() -> str:
    geo = resolve_geo()
    if not geo:
        return "🌤 <b>Погода</b>\nТочка не задана. «📍 Гео» или GEO_LAT/GEO_LON / GEO_CITY"
    lat, lon, label = geo
    try:
        r = get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,wind_speed_10m,wind_gusts_10m,weather_code,relative_humidity_2m",
                "daily": "sunrise,sunset",
                "timezone": "Europe/Moscow",
                "forecast_days": 1,
            },
        )
        if r.status_code != 200:
            return f"🌤 Погода\nHTTP {r.status_code}"
        data = r.json()
        c = data.get("current") or {}
        d = data.get("daily") or {}
        codes = {
            0: "ясно", 1: "почти ясно", 2: "облачно", 3: "пасмурно",
            45: "туман", 61: "дождь", 71: "снег", 73: "снег", 75: "сильный снег",
            80: "ливень", 85: "снегопад", 95: "гроза",
        }
        try:
            w = codes.get(int(c.get("weather_code")), "—")
        except Exception:
            w = "—"
        sr = (d.get("sunrise") or ["?"])[0]
        ss = (d.get("sunset") or ["?"])[0]
        if isinstance(sr, str) and "T" in sr:
            sr = sr.split("T")[1][:5]
        if isinstance(ss, str) and "T" in ss:
            ss = ss.split("T")[1][:5]
        return (
            f"🌤 <b>Погода — {esc(label)}</b>\n"
            f"📍 {lat:.3f}, {lon:.3f}\n{w}\n"
            f"Темп: {c.get('temperature_2m')}°C (ощущ. {c.get('apparent_temperature')}°C)\n"
            f"Ветер: {c.get('wind_speed_10m')} м/с, порывы {c.get('wind_gusts_10m')} м/с\n"
            f"Влажность: {c.get('relative_humidity_2m')}%\n"
            f"Восход {sr} · закат {ss}"
        )
    except Exception as e:
        return f"🌤 Погода\nошибка: {type(e).__name__}"


def block_kp() -> str:
    try:
        rows = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json").json()
        if not rows:
            return "🧲 Магн. бури\nнет данных"
        last = rows[-1]
        if isinstance(last, dict):
            kp = float(last.get("Kp") or last.get("kp") or 0)
            tag = last.get("time_tag") or ""
        else:
            if isinstance(last[0], str) and str(last[0]).lower().startswith("time"):
                last = rows[-2] if len(rows) > 1 else last
            kp = float(last[1])
            tag = last[0]
        lvl = (
            "спокойно" if kp < 4 else "неспокойно" if kp < 5 else "G1" if kp < 6
            else "G2" if kp < 7 else "G3" if kp < 8 else "G4+"
        )
        return f"🧲 <b>Kp = {kp}</b> — {lvl}\n{tag} UTC"
    except Exception as e:
        return f"🧲 Магн. бури\nошибка: {type(e).__name__}"


def block_fx() -> str:
    try:
        v = get("https://www.cbr-xml-daily.ru/daily_json.js").json()["Valute"]
        lines = ["💱 <b>Курсы ЦБ</b>"]
        for code in ("USD", "EUR", "CNY"):
            if code not in v:
                continue
            val = v[code]["Value"]
            prev = v[code].get("Previous", val)
            d = val - prev
            a = "▲" if d > 0 else ("▼" if d < 0 else "•")
            lines.append(f"{code}: {val:.2f} ₽ ({a}{abs(d):.2f})")
        return "\n".join(lines)
    except Exception as e:
        return f"💱 Курсы\nошибка: {type(e).__name__}"


def block_oil() -> str:
    """Нефть Brent (фьючерс BR на MOEX), $/барр."""
    try:
        r = get(
            "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json",
            params={"iss.meta": "off", "iss.only": "securities,marketdata"},
        )
        j = r.json()
        secs = j.get("securities") or {}
        md = j.get("marketdata") or {}
        sc, sd = secs.get("columns") or [], secs.get("data") or []
        mc, mdt = md.get("columns") or [], md.get("data") or []
        if not sc or not mc:
            return "🛢 Нефть\nнет данных"
        i_sid = sc.index("SECID")
        i_md_sid = mc.index("SECID")
        i_last = mc.index("LAST") if "LAST" in mc else None
        i_chg = mc.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in mc else None

        prices = []
        for row in mdt:
            sid = row[i_md_sid]
            if not (isinstance(sid, str) and sid.startswith("BR") and len(sid) <= 5):
                continue
            last = row[i_last] if i_last is not None else None
            if last is None:
                continue
            chg = row[i_chg] if i_chg is not None else None
            prices.append((sid, float(last), chg))

        if not prices:
            return "🛢 Нефть\nнет котировок BR"

        prices.sort(key=lambda x: x[0])
        lines = ["🛢 <b>Нефть Brent (MOEX BR)</b>"]
        for sid, last, chg in prices[:3]:
            if chg is not None:
                a = "▲" if chg > 0 else ("▼" if chg < 0 else "•")
                lines.append(f"{sid}: ${last:.2f} ({a}{abs(chg):.2f}%)")
            else:
                lines.append(f"{sid}: ${last:.2f}")
        lines.append("$/баррель")
        return "\n".join(lines)
    except Exception as e:
        return f"🛢 Нефть\nошибка: {type(e).__name__}"


def block_crypto() -> str:
    """Топ-5 криптовалют по капитализации (CoinGecko)."""
    try:
        r = get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 5,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h",
            },
        )
        if r.status_code == 429:
            return "₿ Крипта\nлимит API, позже"
        if r.status_code != 200:
            return f"₿ Крипта\nHTTP {r.status_code}"
        rows = r.json()
        if not rows:
            return "₿ Крипта\nнет данных"
        lines = ["₿ <b>Топ-5 крипты</b>"]
        for i, c in enumerate(rows, 1):
            sym = (c.get("symbol") or "?").upper()
            price = c.get("current_price") or 0
            chg = c.get("price_change_percentage_24h")
            if chg is not None:
                a = "▲" if chg > 0 else ("▼" if chg < 0 else "•")
                lines.append(f"{i}. {sym}: ${price:,.2f} ({a}{abs(chg):.1f}% 24ч)")
            else:
                lines.append(f"{i}. {sym}: ${price:,.2f}")
        return "\n".join(lines)
    except Exception as e:
        return f"₿ Крипта\nошибка: {type(e).__name__}"


def block_metals() -> str:
    try:
        today = datetime.now(TZ)
        d1 = (today - timedelta(days=5)).strftime("%d/%m/%Y")
        d2 = today.strftime("%d/%m/%Y")
        r = get(f"https://www.cbr.ru/scripts/xml_metall.asp?date_req1={d1}&date_req2={d2}")
        text = r.content.decode("cp1251", errors="replace")
        rec = re.findall(r'Code="(\d)".*?<Buy>([^<]+)</Buy>', text, re.DOTALL)
        names = {"1": "Au", "2": "Ag", "3": "Pt", "4": "Pd"}
        latest = {}
        for code, buy in rec:
            try:
                latest[code] = float(buy.replace(",", "."))
            except ValueError:
                pass
        if not latest:
            return "🥇 Металлы\nнет данных"
        lines = ["🥇 <b>Драгметаллы</b> ₽/г"]
        for c, n in names.items():
            if c in latest:
                lines.append(f"{n}: {latest[c]:,.1f}".replace(",", " "))
        return "\n".join(lines)
    except Exception as e:
        return f"🥇 Металлы\nошибка: {type(e).__name__}"


def block_stocks() -> str:
    try:
        r = get(
            "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json",
            params={
                "securities": "SBER,GAZP,LKOH,ROSN,GMKN",
                "iss.meta": "off",
                "iss.only": "marketdata",
            },
        )
        md = r.json().get("marketdata") or {}
        cols, rows = md.get("columns") or [], md.get("data") or []
        if not cols or not rows:
            return "📈 Акции\nнет данных"
        i_id = cols.index("SECID") if "SECID" in cols else 0
        i_last = cols.index("LAST") if "LAST" in cols else None
        i_chg = cols.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in cols else None
        lines = ["📈 <b>Акции</b>"]
        for row in rows:
            if i_last is None or row[i_last] is None:
                continue
            sid, last = row[i_id], row[i_last]
            if i_chg is not None and row[i_chg] is not None:
                chg = row[i_chg]
                a = "▲" if chg > 0 else ("▼" if chg < 0 else "•")
                lines.append(f"{sid}: {last} ({a}{abs(chg):.2f}%)")
            else:
                lines.append(f"{sid}: {last}")
        return "\n".join(lines) if len(lines) > 1 else "📈 Акции\nнет данных"
    except Exception as e:
        return f"📈 Акции\nошибка: {type(e).__name__}"


def _clean_xml_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_rss_items(text: str, src: str, max_items: int = 12):
    """title + description для более содержательных новостей."""
    out = []
    blocks = re.findall(r"<item(?:\s[^>]*)?>(.*?)</item>", text, re.I | re.S)
    if not blocks:
        titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", text, re.I | re.S)
        for t in titles[1: max_items + 1]:
            t = _clean_xml_text(t)
            if t and t.lower() not in (src.lower(), "новости", "news", "rbc"):
                out.append((src, t, ""))
        return out

    for block in blocks[: max_items + 2]:
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.I | re.S)
        dm = re.search(
            r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>",
            block,
            re.I | re.S,
        )
        title = _clean_xml_text(tm.group(1) if tm else "")
        desc = _clean_xml_text(dm.group(1) if dm else "")
        if not title or title.lower() in (src.lower(), "новости", "news"):
            continue
        if desc and (desc.lower().startswith(title.lower()[:40]) or desc == title):
            desc = ""
        if len(desc) > 180:
            desc = desc[:177].rsplit(" ", 1)[0] + "…"
        out.append((src, title, desc))
        if len(out) >= max_items:
            break
    return out


def block_news(limit: int = 35) -> str:
    """30+ новостей: РБК, Интерфакс, ТАСС, РИА, BFM, Лента."""
    feeds = [
        ("РБК", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", 12),
        ("Интерфакс", "https://www.interfax.ru/rss.asp", 10),
        ("ТАСС", "https://tass.ru/rss/v2.xml", 8),
        ("РИА", "https://ria.ru/export/rss2/index.xml", 8),
        ("BFM", "https://www.bfm.ru/news.rss", 8),
        ("Лента", "https://lenta.ru/rss/news", 8),
    ]
    items = []
    for src, url, n in feeds:
        try:
            text = get(url).text
            items.extend(_parse_rss_items(text, src, n))
        except Exception as e:
            print("rss", src, type(e).__name__)

    seen, out = set(), []
    for src, title, desc in items:
        k = title.lower()[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append((src, title, desc))
        if len(out) >= limit:
            break

    if not out:
        return "📰 Новости\nнет данных"

    lines = [f"📰 <b>Новости</b> ({len(out)})"]
    for i, (src, title, desc) in enumerate(out, 1):
        lines.append(f"{i}. <b>[{src}]</b> {esc(title)}")
        if desc:
            lines.append(f"   <i>{esc(desc)}</i>")
    return "\n".join(lines)


def block_short() -> str:
    parts = []
    try:
        v = get("https://www.cbr-xml-daily.ru/daily_json.js").json()["Valute"]
        parts.append(f"USD {v['USD']['Value']:.1f}")
        parts.append(f"EUR {v['EUR']['Value']:.1f}")
    except Exception:
        pass
    try:
        oil = block_oil()
        m = re.search(r"\$(\d+[.,]\d+)", oil)
        if m:
            parts.append(f"Brent ${m.group(1)}")
    except Exception:
        pass
    try:
        r = get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        )
        if r.status_code == 200:
            parts.append(f"BTC ${r.json()['bitcoin']['usd']:,.0f}")
    except Exception:
        pass
    return "⚡ " + " · ".join(parts) if parts else "⚡ сводка"


def _safe(fn, fb: str) -> str:
    try:
        return fn()
    except Exception as e:
        return f"{fb}\n{type(e).__name__}"


def build_digest(full: bool = True) -> str:
    t0 = time.time()
    parts = [
        f"{'📊' if full else '⚡'} <b>Дайджест {now_str()}</b> МСК",
        _safe(block_short, "⚡"),
        _safe(block_weather, "🌤"),
        _safe(block_kp, "🧲"),
        _safe(block_fx, "💱"),
        _safe(block_oil, "🛢"),
        _safe(block_crypto, "₿"),
    ]
    if full:
        parts += [
            _safe(block_metals, "🥇"),
            _safe(block_stocks, "📈"),
            _safe(lambda: block_news(35), "📰"),
        ]
    print(f"digest {time.time()-t0:.1f}s")
    return "\n\n".join(parts)


L_DIGEST = "📊 Дайджест"
L_SHORT = "⚡ Кратко"
L_WEATHER = "🌤 Погода"
L_KP = "🧲 Магн. бури"
L_RATES = "💱 Курсы"
L_CRYPTO = "₿ Крипта"
L_NEWS = "📰 Новости"
L_GEO = "📍 Точка"
L_LOC = "📍 Гео"

KEYBOARD = {
    "keyboard": [
        [{"text": L_DIGEST}, {"text": L_SHORT}],
        [{"text": L_WEATHER}, {"text": L_KP}],
        [{"text": L_RATES}, {"text": L_CRYPTO}],
        [{"text": L_NEWS}, {"text": L_GEO}],
        [{"text": L_LOC, "request_location": True}],
    ],
    "resize_keyboard": True,
    "is_persistent": False,
    "input_field_placeholder": "Свернуть: ⌄",
}


def send(chat_id, text: str, with_kb: bool = True) -> bool:
    chunks = []
    while text:
        if len(text) <= 3900:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, 3900)
        if cut < 50:
            cut = 3900
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    ok = True
    for i, ch in enumerate(chunks):
        body = {
            "chat_id": chat_id,
            "text": ch,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if with_kb and i == len(chunks) - 1:
            body["reply_markup"] = KEYBOARD
        try:
            data = post_json(f"{TG}/sendMessage", body).json()
            print("send", data.get("ok"), data.get("description", ""))
            if not data.get("ok"):
                body.pop("parse_mode", None)
                data2 = post_json(f"{TG}/sendMessage", body).json()
                if not data2.get("ok"):
                    ok = False
        except Exception as e:
            print("send err", type(e).__name__)
            ok = False
    return ok


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\sа-яё]+", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def on_location(chat_id, lat: float, lon: float):
    save_geo(lat, lon)
    send(
        chat_id,
        f"📍 Точка: <code>{lat:.5f}</code>, <code>{lon:.5f}</code>\n"
        f"GEO_LAT={lat:.5f} GEO_LON={lon:.5f}\n\n"
        + block_weather(),
    )


def on_text(chat_id, text: str):
    raw = (text or "").strip()
    n = norm(raw)
    print(f"MSG raw={raw!r} norm={n!r}")
    try:
        if raw == "/start":
            send(
                chat_id,
                "Бот онлайн. Кнопки отвечают сразу.\n"
                "Автодайджест (GitHub): 08:00 и 20:00 МСК.",
            )
            send(chat_id, build_digest(True))
            return
        if raw in (L_DIGEST, "/now", "/digest") or "дайджест" in n or n in ("digest", "now"):
            send(chat_id, build_digest(True))
            return
        if raw in (L_SHORT, "/short") or "кратко" in n:
            send(chat_id, build_digest(False))
            return
        if raw in (L_WEATHER, "/weather") or "погод" in n:
            send(chat_id, block_weather())
            return
        if raw in (L_RATES, "/rates") or "курс" in n or "нефть" in n:
            send(chat_id, block_fx() + "\n\n" + block_oil() + "\n\n" + block_metals())
            return
        if raw in (L_CRYPTO, "/crypto") or "крипт" in n:
            send(chat_id, block_crypto())
            return
        if raw in (L_KP, "/kp") or "магн" in n or n == "бури":
            send(chat_id, block_kp())
            return
        if raw in (L_NEWS, "/news") or "новост" in n:
            send(chat_id, block_news(35))
            return
        if raw in (L_GEO, "/geo") or "точк" in n:
            g = resolve_geo()
            msg = "📍 <b>Геоточка</b>\n"
            msg += f"{esc(g[2])}: {g[0]:.4f}, {g[1]:.4f}" if g else "не задана — «📍 Гео»"
            send(chat_id, msg)
            return
        send(chat_id, f"Не понял: {esc(raw)}\nЖмите кнопки внизу.")
    except Exception as e:
        print("on_text", type(e).__name__, e)
        try:
            send(chat_id, f"Ошибка: {type(e).__name__}")
        except Exception:
            pass


def read_offset() -> int:
    try:
        if OFFSET_FILE.exists():
            return int(OFFSET_FILE.read_text().strip() or "0")
    except Exception:
        pass
    return 0


def write_offset(off: int) -> None:
    try:
        OFFSET_FILE.write_text(str(off))
    except Exception as e:
        print("offset", e)


def process_updates(long_poll: bool = False) -> int:
    if not BOT_TOKEN:
        print("no token")
        return 0
    try:
        post_json(f"{TG}/deleteWebhook", {})
    except Exception:
        pass

    offset = read_offset()
    handled = 0
    timeout = 25 if long_poll else 0
    http_to = (5, 35) if long_poll else (2, 10)

    try:
        r = SESSION.get(
            f"{TG}/getUpdates",
            params={"timeout": timeout, "offset": offset},
            timeout=http_to,
        )
        data = r.json()
    except requests.exceptions.ReadTimeout:
        return 0
    except Exception as e:
        print("getUpdates", type(e).__name__, e)
        return 0

    if not data.get("ok"):
        print("getUpdates bad", data)
        return 0

    for u in data.get("result") or []:
        offset = u["update_id"] + 1
        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue
        cid = msg["chat"]["id"]
        if CHAT_ID and str(cid) != str(CHAT_ID).strip():
            continue
        if "location" in msg:
            loc = msg["location"]
            on_location(cid, float(loc["latitude"]), float(loc["longitude"]))
            handled += 1
        elif msg.get("text"):
            on_text(cid, msg["text"])
            handled += 1

    write_offset(offset)
    if handled:
        print(f"processed={handled} offset={offset}")
    return handled


def run_live():
    print("LIVE — кнопки онлайн")
    fail = 0
    while True:
        try:
            process_updates(long_poll=True)
            fail = 0
        except Exception as e:
            fail += 1
            print("live", type(e).__name__, e)
            time.sleep(min(30, 2 * fail))


def main():
    if LIVE:
        run_live()
        return
    if POLL:
        print("POLL")
        process_updates(long_poll=False)
        return

    print("Building digest…")
    text = build_digest(True)
    print("len", len(text))
    if not BOT_TOKEN or not CHAT_ID:
        print(text[:2000])
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    ok = send(CHAT_ID, text, with_kb=True)
    print("OK" if ok else "FAILED")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
