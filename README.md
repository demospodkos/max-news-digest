# Дайджест → Telegram + погода по геоточке

## Геолокация (вариант 3 — Telegram)

**Самый точный способ:**

1. Запустите бота в **Termux** (`LIVE=1 python bot.py`)
2. В чате с ботом: **скрепка → Геопозиция** → отправьте точку
3. Бот сохранит её в `geo.json` и сразу пришлёт погоду

Для **GitHub Actions** после этого добавьте в Secrets координаты, которые бот пришлёт в ответе:
- `GEO_LAT`
- `GEO_LON`

На Actions **нельзя** брать погоду по IP раннера — получите Амстердам/США, не Мурманск.

### Режимы `GEO_MODE`

| Режим | Поведение |
|--------|-----------|
| `auto` (по умолчанию) | geo.json → Secrets LAT/LON → GEO_CITY → IP только в LIVE |
| `telegram` | только сохранённая точка / Secrets |
| `city` | GEO_CITY или LAT/LON |
| `ip` | только IP (только Termux!) |

---

## Кнопки

Работают в **LIVE**-режиме (Termux):

📊 Дайджест · ⚡ Кратко · 🌤 Погода · 🧲 Магн. бури · 💱 Курсы · ₿ Крипта · 📰 Новости · 📍 Моя точка

```bash
pkg install python git
pip install requests
git clone https://github.com/demospodkos/max-news-digest.git
cd max-news-digest
export TELEGRAM_BOT_TOKEN='...'
export TELEGRAM_CHAT_ID='...'
LIVE=1 python bot.py
```

---

## GitHub Actions (08:00 и 20:00 МСК)

Secrets:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEO_LAT` + `GEO_LON` (после отправки точки боту)
- опционально `GEO_LABEL`, `GEO_CITY`

Actions → Telegram Digest → Run workflow — ручная проверка.
