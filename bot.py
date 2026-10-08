#!/usr/bin/env python3
"""Дайджест + кнопки + геолокация → Telegram. Не зависает на API."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GEO_MODE = (os.environ.get("GEO_MODE") or "auto").lower()
GEO_LAT = os.environ.get("GEO_LAT", "")
GEO_LON = os.environ.get("GEO_LON", "")
GEO_CITY = os.environ.get("GEO_CITY", "")
GEO_LABEL = os.environ.get("GEO_LABEL", "")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
ROOT = Path(__file__).resolve().parent
GEO_FILE = ROOT / "geo.json"
TIMEOUT = 8  # секунд на любой HTTP-запрос

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Moscow")
except Exception:
    TZ = timezone(timedelta(hours=3), name="MSK")

RSS_FEEDS = {
    "Интерфакс": "https://www.interfax.ru/rss",
    "BFM": "https://www.bfm.ru/news.rss",
}
STOCKS = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "VTBR", "MTSS"]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TgDigestBot/2.3"})

BTN_DIGEST = "📊 Дайджест"
BTN_WEATHER = "🌤 Погода"
BTN_RATES = "💱 Курсы"
BTN_CRYPTO = "₿ Крипта"
BTN_KP = "🧲 Магн. бури"
BTN_NEWS = "📰 Новости"
BTN_SHORT = "⚡ Кратко"
BTN_GEO = "📍 Моя точка"
BTN_SEND_LOC = "📍 Прислать геолокацию"

KEYBOARD = {
    "keyboard": [
        [{"text": BTN_DIGEST}, {"text": BTN_SHORT}],
        [{"text": BTN_WEATHER}, {"text": BTN_KP}],
        [{"text": BTN_RATES}, {"text": BTN_CRYPTO}],
        [{"text": BTN_NEWS}, {"text": BTN_GEO}],
        [{"text": BTN_SEND_LOC, "request_location": True}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def http_get(url: str, **kwargs):
    kwargs.setdefault("timeout", TIMEOUT)
    return SESSION.get(url, **kwargs)


def now_msk() -> datetime:
    return datetime.now(TZ)


# ─── Гео ────────────────────────────────────────────────────────────────────
def load_geo_file() -> dict | None:
    if not GEO_FILE.exists():
        return None
    try:
        data = json.loads(GEO_FILE.read_text(encoding="utf-8"))
        if "lat" in data and "lon" in data:
            return data
    except Exception as e:
        print("geo.json:", e)
    return None


def save_geo_file(lat: float, lon: float, label: str = "", source: str = "telegram") -> None:
    payload = {
        "lat": lat,
        "lon": lon,
        "label": label or f"{lat:.4f},{lon:.4f}",
        "source": source,
        "updated_at": now_msk().isoformat(timespec="seconds"),
    }
    GEO_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def geo_from_ip() -> tuple[float, float, str] | None:
    for url in ("https://ipapi.co/json/", "https://ipinfo.io/json"):
        try:
            d = http_get(url).json()
            if "latitude" in d and "longitude" in d:
                return float(d["latitude"]), float(d["longitude"]), str(d.get("city") or "IP")
            loc = (d.get("loc") or "").split(",")
            if len(loc) == 2:
                return float(loc[0]), float(loc[1]), str(d.get("city") or "IP")
        except Exception as e:
            print("ip geo:", e)
    return None


def geo_from_city(name: str) -> tuple[float, float, str] | None:
    try:
        r = http_get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": name, "count": 1, "language": "ru", "format": "json"},
        )
        results = r.json().get("results") or []
        if results:
            p = results[0]
            return float(p["latitude"]), float(p["longitude"]), GEO_LABEL or p.get("name") or name
    except Exception as e:
        print("geocode:", e)
    return None


def resolve_geo() -> tuple[float, float, str] | None:
    if GEO_MODE in ("auto", "telegram"):
        saved = load_geo_file()
        if saved:
            return float(saved["lat"]), float(saved["lon"]), saved.get("label") or "Telegram"
    if GEO_MODE in ("auto", "city", "telegram"):
        if GEO_LAT and GEO_LON:
            try:
                lat, lon = float(GEO_LAT), float(GEO_LON)
                return lat, lon, GEO_LABEL or f"{lat:.2f},{lon:.2f}"
            except ValueError:
                pass
        if GEO_CITY:
            g = geo_from_city(GEO_CITY)
            if g:
                return g
    if GEO_MODE == "ip" or (GEO_MODE == "auto" and os.environ.get("LIVE")):
        g = geo_from_ip()
        if g:
            return g
    if GEO_CITY:
        return geo_from_city(GEO_CITY)
    return None


# ─── Блоки ──────────────────────────────────────────────────────────────────
def get_weather() -> str:
    geo = resolve_geo()
    if not geo:
        return (
            "🌤 <b>Погода</b>\nТочка не задана.\n"
            "Кнопка <b>📍 Прислать геолокацию</b> (Termux LIVE) или Secrets GEO_LAT/GEO_LON/GEO_CITY"
        )
    lat, lon, label = geo
    try:
        r = http_get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,weather_code,visibility",
                "daily": "sunrise,sunset,daylight_duration",
                "timezone": "Europe/Moscow",
                "forecast_days": 1,
            },
        )
        data = r.json()
        cur = data.get("current", {})
        daily = data.get("daily", {})
        table = {
            0: "ясно", 1: "почти ясно", 2: "переменная облачность", 3: "пасмурно",
            45: "туман", 48: "изморозь", 51: "морось", 61: "дождь", 71: "снег",
            73: "снег", 75: "сильный снег", 77: "снежная крупа", 80: "ливень",
            85: "снегопад", 95: "гроза",
        }
        try:
            code_s = table.get(int(cur.get("weather_code")), "—")
        except (TypeError, ValueError):
            code_s = "—"
        sunrise = (daily.get("sunrise") or ["?"])[0]
        sunset = (daily.get("sunset") or ["?"])[0]
        if isinstance(sunrise, str) and "T" in sunrise:
            sunrise = sunrise.split("T")[1][:5]
        if isinstance(sunset, str) and "T" in sunset:
            sunset = sunset.split("T")[1][:5]
        daylen = (daily.get("daylight_duration") or [None])[0]
        day_h = f"{daylen/3600:.1f} ч" if daylen else "—"
        vis = cur.get("visibility")
        vis_km = f"{vis/1000:.1f} км" if vis is not None else "—"
        return "\n".join([
            f"🌤 <b>Погода — {esc(label)}</b>",
            f"📍 {lat:.4f}, {lon:.4f}",
            code_s,
            f"Темп: {cur.get('temperature_2m')}°C (ощущ. {cur.get('apparent_temperature')}°C)",
            f"Ветер: {cur.get('wind_speed_10m')} м/с, порывы {cur.get('wind_gusts_10m')} м/с",
            f"Влажность: {cur.get('relative_humidity_2m')}% · видимость: {vis_km}",
            f"Восход {sunrise} · закат {sunset} · день {day_h}",
        ])
    except Exception as e:
        return f"🌤 Погода\nошибка: {e}"


def get_kp() -> str:
    try:
        rows = http_get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json").json()
        if len(rows) < 2:
            return "🧲 Магн. бури\nнет данных"
        last = rows[-1]
        kp = float(last[1])
        level = (
            "спокойно" if kp < 4 else "неспокойно" if kp < 5 else "буря G1" if kp < 6
            else "буря G2" if kp < 7 else "буря G3" if kp < 8 else "буря G4" if kp < 9
            else "экстремальная G5"
        )
        return (
            f"🧲 <b>Магнитная активность</b>\nKp = {kp} — {level}\n"
            f"обновлено: {last[0]} UTC\nНа Севере при Kp≥5 возможны сбои связи."
        )
    except Exception as e:
        return f"🧲 Магн. бури\nошибка: {e}"


def get_currencies() -> str:
    try:
        v = http_get("https://www.cbr-xml-daily.ru/daily_json.js").json()["Valute"]
        lines = ["💱 <b>Курсы валют ЦБ РФ</b>"]
        for code in ("USD", "EUR", "CNY"):
            if code in v:
                val, prev = v[code]["Value"], v[code].get("Previous", v[code]["Value"])
                diff = val - prev
                arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "•")
                lines.append(f"{code}: {val:.2f} ₽ ({arrow}{abs(diff):.2f})")
        return "\n".join(lines)
    except Exception as e:
        return f"💱 Курсы\nошибка: {e}"


def get_crypto() -> str:
    try:
        data = http_get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin,ethereum,tether,the-open-network,solana", "vs_currencies": "usd,rub"},
        ).json()
        lines = ["₿ <b>Криптовалюты</b>"]
        for key, name in [
            ("bitcoin", "BTC"), ("ethereum", "ETH"), ("tether", "USDT"),
            ("the-open-network", "TON"), ("solana", "SOL"),
        ]:
            if key in data:
                d = data[key]
                lines.append(f"{name}: ${d.get('usd', 0):,.2f} / {d.get('rub', 0):,.0f} ₽")
        return "\n".join(lines)
    except Exception as e:
        return f"₿ Крипта\nошибка: {e}"


def get_precious_metals() -> str:
    try:
        today = now_msk()
        d1 = (today - timedelta(days=7)).strftime("%d/%m/%Y")
        d2 = today.strftime("%d/%m/%Y")
        r = http_get(f"https://www.cbr.ru/scripts/xml_metall.asp?date_req1={d1}&date_req2={d2}")
        text = r.content.decode("cp1251", errors="replace")
        records = re.findall(r'Date="([^"]+)"[^>]*Code="(\d)".*?<Buy>([^<]+)</Buy>', text, re.DOTALL)
        codes = {"1": "Золото", "2": "Серебро", "3": "Платина", "4": "Палладий"}
        latest = {}
        for _, code, buy in records:
            try:
                latest[code] = float(buy.replace(",", "."))
            except ValueError:
                pass
        if not latest:
            return "🥇 Драгметаллы\nнедоступны"
        lines = ["🥇 <b>Драгметаллы</b> (ЦБ, ₽/г)"]
        for code, name in codes.items():
            if code in latest:
                lines.append(f"{name}: {latest[code]:,.2f}".replace(",", " "))
        return "\n".join(lines)
    except Exception as e:
        return f"🥇 Драгметаллы\nошибка: {e}"


def get_oil() -> str:
    try:
        r = http_get(
            "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json",
            params={"iss.meta": "off", "iss.only": "securities"},
        )
        data = r.json()
        cols = data.get("securities", {}).get("columns", [])
        rows = data.get("securities", {}).get("data", [])
        if "SECID" in cols and "PREVSETTLEPRICE" in cols:
            i_id, i_p = cols.index("SECID"), cols.index("PREVSETTLEPRICE")
            for row in rows:
                sid = str(row[i_id])
                if sid.startswith("BR") and row[i_p]:
                    return f"🛢 <b>Нефть</b> (фьюч. {sid})\n{row[i_p]} USD"
        return "🛢 Нефть\nнедоступно"
    except Exception as e:
        return f"🛢 Нефть\nошибка: {e}"


def get_stocks() -> str:
    try:
        r = http_get(
            "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json",
            params={"securities": ",".join(STOCKS), "iss.meta": "off", "iss.only": "marketdata"},
        )
        md = r.json().get("marketdata", {})
        cols, rows = md.get("columns", []), md.get("data", [])
        if not cols or not rows:
            return "📈 Акции\nнедоступны"
        idx_id = cols.index("SECID") if "SECID" in cols else 0
        idx_last = cols.index("LAST") if "LAST" in cols else None
        idx_chg = cols.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in cols else None
        lines = ["📈 <b>Акции</b> (Мосбиржа)"]
        for row in rows:
            last = row[idx_last] if idx_last is not None else None
            if last is None:
                continue
            sid = row[idx_id]
            chg = row[idx_chg] if idx_chg is not None else None
            if chg is not None:
                arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "•")
                lines.append(f"{sid}: {last} ({arrow}{abs(chg):.2f}%)")
            else:
                lines.append(f"{sid}: {last}")
        return "\n".join(lines) if len(lines) > 1 else "📈 Акции\nнедоступны"
    except Exception as e:
        return f"📈 Акции\nошибка: {e}"


def get_news(limit: int = 40) -> str:
    items = []
    for source, url in RSS_FEEDS.items():
        try:
            text = http_get(url).text
            titles = re.findall(
                r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>",
                text, re.DOTALL | re.IGNORECASE,
            )
            for t in titles[1:16]:
                t = re.sub(r"<[^>]+>", "", t).strip()
                if t:
                    items.append((source, t))
        except Exception as e:
            print("rss", source, e)
    seen, unique = set(), []
    for src, title in items:
        key = title.lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append((src, title))
    unique = unique[:limit]
    if not unique:
        return "📰 Новости\nне удалось получить"
    lines = [f"📰 <b>Новости</b> ({len(unique)})"]
    for i, (src, title) in enumerate(unique, 1):
        lines.append(f"{i}. [{src}] {esc(title)}")
    return "\n".join(lines)


def get_short_summary() -> str:
    parts = []
    try:
        v = http_get("https://www.cbr-xml-daily.ru/daily_json.js").json()["Valute"]
        parts.append(f"USD {v['USD']['Value']:.1f}")
        parts.append(f"EUR {v['EUR']['Value']:.1f}")
    except Exception:
        pass
    try:
        c = http_get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        ).json()
        parts.append(f"BTC ${c['bitcoin']['usd']:,.0f}")
    except Exception:
        pass
    geo = resolve_geo()
    if geo:
        try:
            lat, lon, label = geo
            w = http_get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m",
                    "timezone": "Europe/Moscow",
                },
            ).json().get("current", {})
            parts.append(f"{label} {w.get('temperature_2m')}°C ветер {w.get('wind_speed_10m')}м/с")
        except Exception:
            pass
    return "⚡ " + " · ".join(parts) if parts else "⚡ сводка недоступна"


def _safe(fn, default: str) -> str:
    try:
        return fn()
    except Exception as e:
        return f"{default}\nошибка: {e}"


def build_digest(full: bool = True) -> str:
    now = now_msk().strftime("%d.%m.%Y %H:%M")
    tasks = {
        "short": get_short_summary,
        "weather": get_weather,
        "kp": get_kp,
        "cur": get_currencies,
        "crypto": get_crypto,
    }
    if full:
        tasks.update({
            "metals": get_precious_metals,
            "oil": get_oil,
            "stocks": get_stocks,
            "news": lambda: get_news(40),
        })

    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(fn): key for key, fn in tasks.items()}
        try:
            for fut in as_completed(futs, timeout=25):
                key = futs[fut]
                try:
                    results[key] = fut.result(timeout=1)
                except Exception as e:
                    results[key] = f"блок {key}: {e}"
        except Exception:
            for fut, key in futs.items():
                if key not in results:
                    results[key] = f"блок {key}: таймаут"

    order = ["short", "weather", "kp", "cur", "crypto"]
    if full:
        order += ["metals", "oil", "stocks", "news"]
    title = f"{'📊 <b>Дайджест' if full else '⚡ <b>Кратко'} на {now}</b> (МСК)"
    parts = [title] + [results.get(k, "") for k in order]
    return "\n\n".join(p for p in parts if p)


def geo_status_text() -> str:
    g = resolve_geo()
    saved = load_geo_file()
    lines = ["📍 <b>Геоточка</b>"]
    if g:
        lines.append(f"Сейчас: {esc(g[2])} — {g[0]:.4f}, {g[1]:.4f}")
    else:
        lines.append("не задана")
    if saved:
        lines.append(f"geo.json: {saved.get('updated_at', '—')}")
    lines.append("Кнопка <b>📍 Прислать геолокацию</b> или Secrets GEO_LAT/GEO_LON")
    return "\n".join(lines)


# ─── Telegram ───────────────────────────────────────────────────────────────
def tg_api(method: str, payload: dict | None = None, params: dict | None = None) -> dict:
    if payload is not None:
        r = SESSION.post(f"{TG_API}/{method}", json=payload, timeout=20)
    else:
        r = SESSION.get(f"{TG_API}/{method}", params=params or {}, timeout=55)
    return r.json()


def send_message(chat_id: str | int, text: str, with_keyboard: bool = False) -> bool:
    MAX_LEN = 4000
    chunks = []
    while text:
        if len(text) <= MAX_LEN:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, MAX_LEN)
        if cut < 100:
            cut = MAX_LEN
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    ok = True
    for i, chunk in enumerate(chunks):
        body = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if with_keyboard and i == len(chunks) - 1:
            body["reply_markup"] = KEYBOARD
        try:
            data = tg_api("sendMessage", payload=body)
            print(f"send {i+1}/{len(chunks)}: ok={data.get('ok')}")
            if not data.get("ok"):
                print(data)
                ok = False
        except Exception as e:
            print("send error", e)
            ok = False
    return ok


def handle_location(chat_id: int, lat: float, lon: float) -> None:
    save_geo_file(lat, lon, label=f"{lat:.4f},{lon:.4f}", source="telegram")
    send_message(
        chat_id,
        f"📍 <b>Точка сохранена</b>\n{lat:.5f}, {lon:.5f}\n\n"
        f"Secrets для Actions:\n<code>GEO_LAT</code>={lat:.5f}\n<code>GEO_LON</code>={lon:.5f}\n\n"
        + get_weather(),
        with_keyboard=True,
    )


def handle_text(chat_id: int, text: str) -> None:
    t = (text or "").strip()
    low = t.lower()
    if t in (BTN_DIGEST, "/now", "/digest", "/start") or low == "дайджест":
        if t == "/start":
            send_message(
                chat_id,
                "Привет! Кнопки внизу.\n"
                "📍 — «Прислать геолокацию».\n"
                "Расписание: 08:00 и 20:00 МСК.",
                with_keyboard=True,
            )
        send_message(chat_id, build_digest(True), with_keyboard=True)
    elif t in (BTN_SHORT, "/short") or low == "кратко":
        send_message(chat_id, build_digest(False), with_keyboard=True)
    elif t in (BTN_WEATHER, "/weather") or low == "погода":
        send_message(chat_id, get_weather(), with_keyboard=True)
    elif t in (BTN_RATES, "/rates") or low == "курсы":
        send_message(chat_id, get_currencies() + "\n\n" + get_precious_metals(), with_keyboard=True)
    elif t in (BTN_CRYPTO, "/crypto") or low == "крипта":
        send_message(chat_id, get_crypto(), with_keyboard=True)
    elif t in (BTN_KP, "/kp") or "магн" in low or low == "бури":
        send_message(chat_id, get_kp(), with_keyboard=True)
    elif t in (BTN_NEWS, "/news") or low == "новости":
        send_message(chat_id, get_news(25), with_keyboard=True)
    elif t in (BTN_GEO, "/geo") or "точк" in low:
        send_message(chat_id, geo_status_text(), with_keyboard=True)
    else:
        send_message(
            chat_id,
            "/now /weather /rates /crypto /kp /news /short /geo\n"
            "или кнопка 📍 Прислать геолокацию",
            with_keyboard=True,
        )


def run_live() -> None:
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан")
    print("LIVE mode…")
    offset = 0
    try:
        tg_api("deleteWebhook", payload={})
    except Exception as e:
        print("deleteWebhook:", e)
    while True:
        try:
            data = tg_api("getUpdates", params={"timeout": 40, "offset": offset})
            if not data.get("ok"):
                print("getUpdates", data)
                time.sleep(3)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                if CHAT_ID and str(chat_id) != str(CHAT_ID):
                    continue
                if "location" in msg:
                    loc = msg["location"]
                    handle_location(chat_id, float(loc["latitude"]), float(loc["longitude"]))
                    continue
                text = msg.get("text") or ""
                if text:
                    handle_text(chat_id, text)
        except Exception as e:
            print("live:", e)
            time.sleep(5)


def main() -> None:
    if os.environ.get("LIVE", "").lower() in ("1", "true", "yes"):
        run_live()
        return
    print("Собираю дайджест…")
    text = build_digest(True)
    print(f"Длина: {len(text)} символов")
    if not BOT_TOKEN or not CHAT_ID:
        print(text[:1500])
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    ok = send_message(CHAT_ID, text, with_keyboard=True)
    print("OK" if ok else "FAILED")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
