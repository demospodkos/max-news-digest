#!/usr/bin/env python3
"""
Дайджест новостей и курсов → Telegram.
Запускается через GitHub Actions 2 раза в сутки (08:00 и 20:00 МСК).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TZ = ZoneInfo("Europe/Moscow")

RSS_FEEDS = {
    "Интерфакс": "https://www.interfax.ru/rss",
    "BFM": "https://www.bfm.ru/news.rss",
}
STOCKS = ["SBER", "GAZP", "LKOH", "ROSN", "GMKN", "VTBR", "MTSS"]
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TgDigestBot/1.0"})


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
        return f"💱 Курсы валют\nошибка: {e}"


def get_crypto() -> str:
    try:
        r = SESSION.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin,ethereum", "vs_currencies": "usd,rub"},
            timeout=15,
        )
        data = r.json()
        lines = ["₿ <b>Криптовалюты</b>"]
        if "bitcoin" in data:
            b = data["bitcoin"]
            lines.append(f"BTC: ${b.get('usd', 0):,.0f} / {b.get('rub', 0):,.0f} ₽")
        if "ethereum" in data:
            e = data["ethereum"]
            lines.append(f"ETH: ${e.get('usd', 0):,.0f} / {e.get('rub', 0):,.0f} ₽")
        return "\n".join(lines)
    except Exception as e:
        return f"₿ Криптовалюты\nошибка: {e}"


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
        # экранируем HTML
        title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{i}. [{src}] {title}")
    return "\n".join(lines)


def build_digest() -> str:
    now = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    parts = [
        f"📊 <b>Дайджест на {now}</b> (МСК)",
        "",
        get_currencies(),
        "",
        get_crypto(),
        "",
        get_precious_metals(),
        "",
        get_stocks(),
        "",
        get_news(40),
    ]
    return "\n".join(parts).strip()


def send_to_telegram(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы")
        print(text)
        return False

    # Telegram limit ~4096 символов
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
        try:
            r = SESSION.post(
                f"{TG_API}/sendMessage",
                json={
                    "chat_id": CHAT_ID,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            data = r.json()
            print(f"часть {i+1}/{len(chunks)}: ok={data.get('ok')} status={r.status_code}")
            if not data.get("ok"):
                print(data)
                ok = False
        except Exception as e:
            print("send error:", e)
            ok = False
    return ok


def main():
    print("Собираю дайджест...")
    text = build_digest()
    print(f"Длина: {len(text)} символов")
    ok = send_to_telegram(text)
    print("OK" if ok else "FAILED")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
