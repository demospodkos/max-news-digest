#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram digest bot — hard timeouts, never hangs."""

from __future__ import annotations

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

TG = f"https://api.telegram.org/bot{BOT_TOKEN}"
ROOT = Path(__file__).resolve().parent
GEO_FILE = ROOT / "geo.json"
HTTP_TIMEOUT = (2, 4)

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Moscow")
except Exception:
    TZ = timezone(timedelta(hours=3))

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "TgDigestBot/3.1"
_adapter = HTTPAdapter(max_retries=Retry(total=0, connect=0, read=0, redirect=0))
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)


def get(url: str, **kw):
    kw.setdefault("timeout", HTTP_TIMEOUT)
    return SESSION.get(url, **kw)


def post(url: str, **kw):
    kw.setdefault("timeout", (3, 10))
    return SESSION.post(url, **kw)


def esc(s) -> str:
    return str(s).replace("&", "&").replace("<", "<").replace(">", ">")


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


def resolve_geo():
    g = load_geo()
    if g:
        return g
    if GEO_LAT and GEO_LON:
        try:
            return float(GEO_LAT), float(GEO_LON), GEO_LABEL or f"{GEO_LAT},{GEO_LON}"
        except ValueError:
            pass
    city = GEO_CITY or ""
    if city:
        try:
            r = get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "ru"},
            )
            rows = (r.json() or {}).get("results") or []
            if rows:
                p = rows[0]
                return float(p["latitude"]), float(p["longitude"]), GEO_LABEL or p.get("name") or city
        except Exception as e:
            print("geocode fail", e)
    return None


def block_weather() -> str:
    geo = resolve_geo()
    if not geo:
        return (
            "🌤 <b>Погода</b>\n"
            "Точка не задана. Кнопка «📍 Прислать геолокацию» "
            "или Secrets GEO_LAT/GEO_LON / GEO_CITY"
        )
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
            f"📍 {lat:.3f}, {lon:.3f}\n"
            f"{w}\n"
            f"Темп: {c.get('temperature_2m')}°C (ощущ. {c.get('apparent_temperature')}°C)\n"
            f"Ветер: {c.get('wind_speed_10m')} м/с, порывы {c.get('wind_gusts_10m')} м/с\n"
            f"Влажность: {c.get('relative_humidity_2m')}%\n"
            f"Восход {sr} · закат {ss}"
        )
    except Exception as e:
        return f"🌤 Погода\nошибка: {type(e).__name__}"


def block_kp() -> str:
    try:
        r = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")
        rows = r.json()
        if not rows:
            return "🧲 Магн. бури\nнет данных"
        last = rows[-1]
        if isinstance(last, dict):
            kp = float(last.get("Kp") or last.get("kp") or 0)
            tag = last.get("time_tag") or last.get("time") or ""
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


def block_crypto() -> str:
    try:
        r = get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin,ethereum", "vs_currencies": "usd,rub"},
        )
        if r.status_code == 429:
            return "₿ Крипта\nлимит API, позже"
        data = r.json()
        lines = ["₿ <b>Крипта</b>"]
        for k, n in (("bitcoin", "BTC"), ("ethereum", "ETH")):
            if k in data:
                lines.append(
                    f"{n}: ${data[k].get('usd', 0):,.0f} / {data[k].get('rub', 0):,.0f} ₽"
                )
        return "\n".join(lines) if len(lines) > 1 else "₿ Крипта\nнет данных"
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
            sid = row[i_id]
            last = row[i_last]
            if i_chg is not None and row[i_chg] is not None:
                chg = row[i_chg]
                a = "▲" if chg > 0 else ("▼" if chg < 0 else "•")
                lines.append(f"{sid}: {last} ({a}{abs(chg):.2f}%)")
            else:
                lines.append(f"{sid}: {last}")
        return "\n".join(lines) if len(lines) > 1 else "📈 Акции\nнет данных"
    except Exception as e:
        return f"📈 Акции\nошибка: {type(e).__name__}"


def block_news(limit: int = 20) -> str:
    items = []
    for src, url in (
        ("Интерфакс", "https://www.interfax.ru/rss"),
        ("BFM", "https://www.bfm.ru/news.rss"),
    ):
        try:
            text = get(url).text
            titles = re.findall(
                r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>",
                text,
                re.I | re.S,
            )
            for t in titles[1:12]:
                t = re.sub(r"<[^>]+>", "", t).strip()
                if t and t.lower() not in (src.lower(), "новости", "news"):
                    items.append((src, t))
        except Exception as e:
            print("rss", src, type(e).__name__)
    seen, out = set(), []
    for src, title in items:
        k = title.lower()[:70]
        if k in seen:
            continue
        seen.add(k)
        out.append((src, title))
        if len(out) >= limit:
            break
    if not out:
        return "📰 Новости\nнет данных"
    lines = [f"📰 <b>Новости</b> ({len(out)})"]
    for i, (src, title) in enumerate(out, 1):
        lines.append(f"{i}. [{src}] {esc(title)}")
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
        r = get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        )
        if r.status_code == 200:
            parts.append(f"BTC ${r.json()['bitcoin']['usd']:,.0f}")
    except Exception:
        pass
    return "⚡ " + " · ".join(parts) if parts else "⚡ сводка"


def build_digest(full: bool = True) -> str:
    t0 = time.time()
    parts = [f"{'📊' if full else '⚡'} <b>Дайджест {now_str()}</b> МСК", block_short()]
    parts.append(block_weather())
    parts.append(block_kp())
    parts.append(block_fx())
    parts.append(block_crypto())
    if full:
        parts.append(block_metals())
        parts.append(block_stocks())
        parts.append(block_news(25))
    print(f"digest built in {time.time()-t0:.1f}s")
    return "\n\n".join(parts)


BTN = {
    "digest": "📊 Дайджест",
    "short": "⚡ Кратко",
    "weather": "🌤 Погода",
    "kp": "🧲 Магн. бури",
    "rates": "💱 Курсы",
    "crypto": "₿ Крипта",
    "news": "📰 Новости",
    "geo": "📍 Моя точка",
    "loc": "📍 Прислать геолокацию",
}

KEYBOARD = {
    "keyboard": [
        [{"text": BTN["digest"]}, {"text": BTN["short"]}],
        [{"text": BTN["weather"]}, {"text": BTN["kp"]}],
        [{"text": BTN["rates"]}, {"text": BTN["crypto"]}],
        [{"text": BTN["news"]}, {"text": BTN["geo"]}],
        [{"text": BTN["loc"], "request_location": True}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


def tg(method: str, **kwargs) -> dict:
    if "json" in kwargs or method in ("deleteWebhook", "sendMessage"):
        r = post(f"{TG}/{method}", **kwargs)
    else:
        r = get(f"{TG}/{method}", **kwargs)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text[:200]}


def send(chat_id, text: str, keyboard: bool = False) -> bool:
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
        if keyboard and i == len(chunks) - 1:
            body["reply_markup"] = KEYBOARD
        try:
            data = tg("sendMessage", json=body)
            print("send", data.get("ok"), data.get("description", ""))
            if not data.get("ok"):
                ok = False
        except Exception as e:
            print("send err", e)
            ok = False
    return ok


def on_location(chat_id, lat: float, lon: float):
    save_geo(lat, lon)
    send(
        chat_id,
        f"📍 Точка сохранена\n<code>{lat:.5f}</code>, <code>{lon:.5f}</code>\n\n"
        f"Для Actions Secrets:\nGEO_LAT={lat:.5f}\nGEO_LON={lon:.5f}\n\n"
        + block_weather(),
        keyboard=True,
    )


def on_text(chat_id, text: str):
    t = (text or "").strip()
    low = t.lower()
    if t in (BTN["digest"], "/now", "/digest", "/start") or low == "дайджест":
        if t == "/start":
            send(
                chat_id,
                "Привет! Кнопки внизу.\n"
                "📍 Прислать геолокацию — для погоды.\n"
                "Автодайджест: 08:00 и 20:00 МСК.",
                keyboard=True,
            )
        send(chat_id, "⏳ Собираю…", keyboard=False)
        send(chat_id, build_digest(True), keyboard=True)
    elif t in (BTN["short"], "/short") or low == "кратко":
        send(chat_id, build_digest(False), keyboard=True)
    elif t in (BTN["weather"], "/weather") or low == "погода":
        send(chat_id, block_weather(), keyboard=True)
    elif t in (BTN["rates"], "/rates") or low == "курсы":
        send(chat_id, block_fx() + "\n\n" + block_metals(), keyboard=True)
    elif t in (BTN["crypto"], "/crypto") or low == "крипта":
        send(chat_id, block_crypto(), keyboard=True)
    elif t in (BTN["kp"], "/kp") or "магн" in low:
        send(chat_id, block_kp(), keyboard=True)
    elif t in (BTN["news"], "/news") or low == "новости":
        send(chat_id, block_news(20), keyboard=True)
    elif t in (BTN["geo"], "/geo") or "точк" in low:
        g = resolve_geo()
        msg = "📍 <b>Геоточка</b>\n"
        msg += f"{g[2]}: {g[0]:.4f}, {g[1]:.4f}" if g else "не задана"
        send(chat_id, msg, keyboard=True)
    else:
        send(chat_id, "Кнопки внизу или /now /weather /rates", keyboard=True)


def run_live():
    if not BOT_TOKEN:
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN")
    print("LIVE mode started (Ctrl+C to stop)")
    try:
        tg("deleteWebhook", json={})
    except Exception as e:
        print("deleteWebhook", e)
    offset = 0
    while True:
        try:
            r = SESSION.get(
                f"{TG}/getUpdates",
                params={"timeout": 25, "offset": offset},
                timeout=(5, 35),
            )
            data = r.json()
            if not data.get("ok"):
                print("getUpdates bad", data)
                time.sleep(2)
                continue
            for u in data.get("result") or []:
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message")
                if not msg:
                    continue
                cid = msg["chat"]["id"]
                if CHAT_ID and str(cid) != str(CHAT_ID):
                    continue
                if "location" in msg:
                    loc = msg["location"]
                    on_location(cid, float(loc["latitude"]), float(loc["longitude"]))
                elif msg.get("text"):
                    on_text(cid, msg["text"])
        except requests.exceptions.ReadTimeout:
            continue
        except Exception as e:
            print("loop", type(e).__name__, e)
            time.sleep(3)


def main():
    if LIVE:
        run_live()
        return
    print("Building digest…")
    text = build_digest(True)
    print("len", len(text))
    if not BOT_TOKEN or not CHAT_ID:
        print(text[:2000])
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    ok = send(CHAT_ID, text, keyboard=True)
    print("OK" if ok else "FAILED")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
