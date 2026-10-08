#!/usr/bin/env python3
"""
Дайджест + интерактивный бот с кнопками → Telegram.

Режимы:
  ONCE=1 или без LIVE  — один дайджест (GitHub Actions)
  LIVE=1               — кнопки и команды (нужен постоянно работающий процесс: Termux)
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
# Погода по координатам (Крайний Север — ваши широта/долгота)
GEO_LAT = os.environ.get("GEO_LAT", "")
GEO_LON = os.environ.get("GEO_LON", "")
GEO_CITY = os.environ.get("GEO_CITY", "")  # если задан город — координаты подставятся сами
GEO_LABEL = os.environ.get("GEO_LABEL", "")  # подпись: «Мурманск», «ЯНАО»

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TZ = ZoneInfo("Europe/Moscow")

RSS_FEEDS = {
    "Интерфакс": "https://www.interfax.ru/rss",
    "BFM": "https://www.bfm.ru/news.rss",
}
STOCKS = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "VTBR", "MTSS"]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TgDigestBot/2.0"})

# Кнопки меню
BTN_DIGEST = "📊 Дайджест"
BTN_WEATHER = "🌤 Погода"
BTN_RATES = "💱 Курсы"
BTN_CRYPTO = "₿ Крипта"
BTN_KP = "🧲 Магн. бури"
BTN_NEWS = "📰 Новости"
BTN_SHORT = "⚡ Кратко"

KEYBOARD = {
    "keyboard": [
        [{"text": BTN_DIGEST}, {"text": BTN_SHORT}],
        [{"text": BTN_WEATHER}, {"text": BTN_KP}],
        [{"text": BTN_RATES}, {"text": BTN_CRYPTO}],
        [{"text": BTN_NEWS}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def resolve_geo() -> tuple[float, float, str] | None:
    """Вернуть (lat, lon, label) из env."""
    if GEO_LAT and GEO_LON:
        try:
            lat, lon = float(GEO_LAT), float(GEO_LON)
            label = GEO_LABEL or f"{lat:.2f},{lon:.2f}"
            return lat, lon, label
        except ValueError:
            pass
    if GEO_CITY:
        try:
            r = SESSION.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": GEO_CITY, "count": 1, "language": "ru", "format": "json"},
                timeout=15,
            )
            results = r.json().get("results") or []
            if results:
                p = results[0]
                label = GEO_LABEL or p.get("name") or GEO_CITY
                return float(p["latitude"]), float(p["longitude"]), label
        except Exception as e:
            print("geocode error:", e)
    return None


def get_weather() -> str:
    geo = resolve_geo()
    if not geo:
        return (
            "🌤 <b>Погода</b>\n"
            "Не заданы координаты.\n"
            "В Secrets добавьте:\n"
            "• <code>GEO_LAT</code> и <code>GEO_LON</code>\n"
            "  или <code>GEO_CITY</code> (например Murmansk)\n"
            "• опционально <code>GEO_LABEL</code> — название места"
        )
    lat, lon, label = geo
    try:
        r = SESSION.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "wind_speed_10m,wind_gusts_10m,weather_code,visibility",
                "daily": "sunrise,sunset,daylight_duration",
                "timezone": "Europe/Moscow",
                "forecast_days": 1,
            },
            timeout=15,
        )
        data = r.json()
        cur = data.get("current", {})
        daily = data.get("daily", {})

        def wcode(c):
            table = {
                0: "ясно",
                1: "почти ясно",
                2: "переменная облачность",
                3: "пасмурно",
                45: "туман",
                48: "изморозь",
                51: "морось",
                61: "дождь",
                71: "снег",
                73: "снег",
                75: "сильный снег",
                77: "снежная крупа",
                80: "ливень",
                85: "снегопад",
                95: "гроза",
            }
            return table.get(int(c) if c is not None else -1, f"код {c}")

        t = cur.get("temperature_2m")
        feels = cur.get("apparent_temperature")
        wind = cur.get("wind_speed_10m")
        gust = cur.get("wind_gusts_10m")
        hum = cur.get("relative_humidity_2m")
        vis = cur.get("visibility")
        code = cur.get("weather_code")
        sunrise = (daily.get("sunrise") or ["?"])[0]
        sunset = (daily.get("sunset") or ["?"])[0]
        if isinstance(sunrise, str) and "T" in sunrise:
            sunrise = sunrise.split("T")[1][:5]
        if isinstance(sunset, str) and "T" in sunset:
            sunset = sunset.split("T")[1][:5]
        daylen = (daily.get("daylight_duration") or [None])[0]
        day_h = f"{daylen/3600:.1f} ч" if daylen else "—"

        vis_km = f"{vis/1000:.1f} км" if vis is not None else "—"
        lines = [
            f"🌤 <b>Погода — {esc(label)}</b>",
            f"{wcode(code)}",
            f"Темп: {t}°C (ощущ. {feels}°C)",
            f"Ветер: {wind} м/с, порывы {gust} м/с",
            f"Влажность: {hum}% · видимость: {vis_km}",
            f"Восход {sunrise} · закат {sunset} · день {day_h}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"🌤 Погода\nошибка: {e}"


def get_kp() -> str:
    """Магнитные бури — NOAA planetary K-index."""
    try:
        r = SESSION.get(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            timeout=15,
        )
        rows = r.json()
        # [time_tag, kp, a_running, station_count]
        if len(rows) < 2:
            return "🧲 Магн. бури\nнет данных"
        last = rows[-1]
        kp = float(last[1])
        t = last[0]
        if kp < 4:
            level = "спокойно"
        elif kp < 5:
            level = "неспокойно"
        elif kp < 6:
            level = "буря G1"
        elif kp < 7:
            level = "буря G2"
        elif kp < 8:
            level = "буря G3"
        elif kp < 9:
            level = "буря G4"
        else:
            level = "экстремальная G5"
        return (
            f"🧲 <b>Магнитная активность</b>\n"
            f"Kp = {kp} — {level}\n"
            f"обновлено: {t} UTC\n"
            f"На Севере при Kp≥5 возможны сбои связи и сияние."
        )
    except Exception as e:
        return f"🧲 Магн. бури\nошибка: {e}"


def get_currencies() -> str:
    try:
        data = SESSION.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=15).json()
        v = data["Valute"]
        lines = ["💱 <b>Курсы валют ЦБ РФ</b>"]
        for code in ("USD", "EUR", "CNY"):
            if code in v:
                val = v[code]["Value"]
                prev = v[code].get("Previous", val)
                diff = val - prev
                arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "•")
                lines.append(f"{code}: {val:.2f} ₽ ({arrow}{abs(diff):.2f})")
        return "\n".join(lines)
    except Exception as e:
        return f"💱 Курсы\nошибка: {e}"


def get_key_rate() -> str:
    """Ключевая ставка ЦБ — последний известный из публичного источника."""
    try:
        # MOEX / CBR key rate via cbr.ru XML is heavy; use simple fallback page parse skip
        # Use ISS indicator if available
        r = SESSION.get(
            "https://iss.moex.com/iss/engines/stock/markets/index/securities/RGBI.json",
            params={"iss.meta": "off"},
            timeout=15,
        )
        # Better: known official JSON mirrors often break; keep compact note
        return "🏦 <b>Ставка ЦБ</b>\nсм. cbr.ru (меняется редко, раз в дайджест — вручную при смене)"
    except Exception:
        return "🏦 Ставка ЦБ\n—"


def get_oil() -> str:
    try:
        # Free approximate via public endpoints; CoinGecko doesn't have oil.
        # Use oilpriceapi free? needs key. Use Yahoo-like or skip.
        # MOEX BR oil futures if available
        r = SESSION.get(
            "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json",
            params={"iss.meta": "off", "iss.only": "securities"},
            timeout=20,
        )
        data = r.json()
        cols = data.get("securities", {}).get("columns", [])
        rows = data.get("securities", {}).get("data", [])
        if "SECID" in cols and "PREVSETTLEPRICE" in cols:
            i_id = cols.index("SECID")
            i_p = cols.index("PREVSETTLEPRICE")
            for row in rows:
                sid = str(row[i_id])
                if sid.startswith("BR") and row[i_p]:
                    return f"🛢 <b>Нефть</b> (фьюч. {sid})\n{row[i_p]} USD"
        return "🛢 Нефть\nданные временно недоступны"
    except Exception as e:
        return f"🛢 Нефть\nошибка: {e}"


def get_crypto() -> str:
    try:
        r = SESSION.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "bitcoin,ethereum,tether,the-open-network,solana",
                "vs_currencies": "usd,rub",
            },
            timeout=15,
        )
        data = r.json()
        lines = ["₿ <b>Криптовалюты</b>"]
        mapping = [
            ("bitcoin", "BTC"),
            ("ethereum", "ETH"),
            ("tether", "USDT"),
            ("the-open-network", "TON"),
            ("solana", "SOL"),
        ]
        for key, name in mapping:
            if key in data:
                d = data[key]
                lines.append(f"{name}: ${d.get('usd', 0):,.2f} / {d.get('rub', 0):,.0f} ₽")
        return "\n".join(lines)
    except Exception as e:
        return f"₿ Крипта\nошибка: {e}"


def get_precious_metals() -> str:
    try:
        today = datetime.now(TZ)
        d1 = (today - timedelta(days=7)).strftime("%d/%m/%Y")
        d2 = today.strftime("%d/%m/%Y")
        r = SESSION.get(
            f"https://www.cbr.ru/scripts/xml_metall.asp?date_req1={d1}&date_req2={d2}",
            timeout=15,
        )
        text = r.content.decode("cp1251", errors="replace")
        records = re.findall(
            r'Date="([^"]+)"[^>]*Code="(\d)".*?<Buy>([^<]+)</Buy>',
            text,
            re.DOTALL,
        )
        codes = {"1": "Золото", "2": "Серебро", "3": "Платина", "4": "Палладий"}
        latest: dict[str, float] = {}
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


def get_stocks() -> str:
    try:
        secs = ",".join(STOCKS)
        r = SESSION.get(
            "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json",
            params={
                "securities": secs,
                "iss.meta": "off",
                "iss.only": "marketdata",
            },
            timeout=15,
        )
        md = r.json().get("marketdata", {})
        cols = md.get("columns", [])
        rows = md.get("data", [])
        if not cols or not rows:
            return "📈 Акции\nнедоступны"
        idx_id = cols.index("SECID") if "SECID" in cols else 0
        idx_last = cols.index("LAST") if "LAST" in cols else None
        idx_chg = cols.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in cols else None
        lines = ["📈 <b>Акции</b> (Мосбиржа)"]
        for row in rows:
            sid = row[idx_id]
            last = row[idx_last] if idx_last is not None else None
            if last is None:
                continue
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
    items: list[tuple[str, str]] = []
    for source, url in RSS_FEEDS.items():
        try:
            text = SESSION.get(url, timeout=15).text
            titles = re.findall(
                r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>",
                text,
                re.DOTALL | re.IGNORECASE,
            )
            for t in titles[1:16]:
                t = re.sub(r"<[^>]+>", "", t).strip()
                if t:
                    items.append((source, t))
        except Exception:
            pass
    seen = set()
    unique = []
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
    """Одна строка-сводка в начале."""
    parts = []
    try:
        v = SESSION.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10).json()["Valute"]
        parts.append(f"USD {v['USD']['Value']:.1f}")
        parts.append(f"EUR {v['EUR']['Value']:.1f}")
    except Exception:
        pass
    try:
        c = SESSION.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
            timeout=10,
        ).json()
        parts.append(f"BTC ${c['bitcoin']['usd']:,.0f}")
    except Exception:
        pass
    geo = resolve_geo()
    if geo:
        try:
            lat, lon, label = geo
            w = SESSION.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m",
                    "timezone": "Europe/Moscow",
                },
                timeout=10,
            ).json().get("current", {})
            parts.append(f"{label} {w.get('temperature_2m')}°C ветер {w.get('wind_speed_10m')}м/с")
        except Exception:
            pass
    return "⚡ " + " · ".join(parts) if parts else "⚡ сводка недоступна"


def build_digest(full: bool = True) -> str:
    now = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    if not full:
        return "\n\n".join([
            f"⚡ <b>Кратко {now}</b> (МСК)",
            get_short_summary(),
            get_weather(),
            get_kp(),
            get_currencies(),
            get_crypto(),
        ])
    parts = [
        f"📊 <b>Дайджест на {now}</b> (МСК)",
        get_short_summary(),
        get_weather(),
        get_kp(),
        get_currencies(),
        get_crypto(),
        get_precious_metals(),
        get_oil(),
        get_stocks(),
        get_news(40),
    ]
    return "\n\n".join(parts)


def tg_api(method: str, payload: dict) -> dict:
    r = SESSION.post(f"{TG_API}/{method}", json=payload, timeout=30)
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
        data = tg_api("sendMessage", body)
        print(f"send {i+1}/{len(chunks)}: ok={data.get('ok')}")
        if not data.get("ok"):
            print(data)
            ok = False
    return ok


def handle_text(chat_id: int, text: str) -> None:
    t = (text or "").strip()
    low = t.lower()

    if t in (BTN_DIGEST, "/now", "/digest", "/start") or low in ("дайджест",):
        if t == "/start":
            send_message(
                chat_id,
                "Привет! Кнопки ниже — быстрый доступ.\n"
                "Расписание: 08:00 и 20:00 МСК (через GitHub Actions).\n"
                "Погода берётся по вашим координатам из настроек.",
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
    elif low.startswith("/geo"):
        send_message(
            chat_id,
            "Геоточка задаётся в GitHub Secrets:\n"
            "<code>GEO_LAT</code>, <code>GEO_LON</code>\n"
            "или <code>GEO_CITY</code>=Murmansk\n"
            f"Сейчас: LAT={GEO_LAT or '—'} LON={GEO_LON or '—'} CITY={GEO_CITY or '—'}",
            with_keyboard=True,
        )
    else:
        send_message(
            chat_id,
            "Команды: /now /weather /rates /crypto /kp /news /short\nили кнопки внизу.",
            with_keyboard=True,
        )


def run_live() -> None:
    """Long polling — кнопки работают. Нужен постоянно включённый процесс (Termux)."""
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан")
    print("LIVE mode: long polling…")
    offset = 0
    # сброс webhook на всякий случай
    tg_api("deleteWebhook", {})
    while True:
        try:
            r = SESSION.get(
                f"{TG_API}/getUpdates",
                params={"timeout": 50, "offset": offset},
                timeout=60,
            )
            data = r.json()
            if not data.get("ok"):
                print("getUpdates error", data)
                time.sleep(3)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                text = msg.get("text") or ""
                # опционально: только ваш chat
                if CHAT_ID and str(chat_id) != str(CHAT_ID):
                    continue
                handle_text(chat_id, text)
        except Exception as e:
            print("live loop error:", e)
            time.sleep(5)


def main() -> None:
    if os.environ.get("LIVE", "").lower() in ("1", "true", "yes"):
        run_live()
        return

    print("Собираю дайджест…")
    text = build_digest(True)
    print(f"Длина: {len(text)} символов")
    if not BOT_TOKEN or not CHAT_ID:
        print(text)
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    ok = send_message(CHAT_ID, text, with_keyboard=True)
    print("OK" if ok else "FAILED")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
