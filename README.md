# Дайджест + кнопки → Telegram

**Два режима:**

| Режим | Что делает | Где работает |
|--------|------------|-------------|
| Расписание | Полный дайджест 08:00 и 20:00 МСК | GitHub Actions (уже настроено) |
| Кнопки / команды | Ответ сразу на нажатие | Нужен **постоянный** процесс (Termux на телефоне) |

GitHub Actions **не держит** бота онлайн 24/7 — поэтому кнопки «вживую» только через Termux (или любой VPS).

---

## Уже в дайджесте

- ⚡ Краткая сводка (USD/EUR/BTC + погода)
- 🌤 **Погода по геоточке** (Open-Meteo, без ключа)
- 🧲 Магнитные бури (Kp, NOAA)
- 💱 Курсы ЦБ, ₿ крипта (BTC ETH USDT TON SOL)
- 🥇 Драгметаллы, 🛢 нефть, 📈 акции, 📰 40 новостей
- Клавиатура-кнопки приходит **вместе с дайджестом**

---

## Погода по геотегу

В GitHub → **Settings → Secrets and variables → Actions** добавьте:

**Вариант A — координаты (точнее для Севера):**
- `GEO_LAT` = `68.96`  (пример: Мурманск)
- `GEO_LON` = `33.08`
- `GEO_LABEL` = `Мурманск` (необязательно)

**Вариант B — город:**
- `GEO_CITY` = `Murmansk` или `Norilsk` или `Salekhard`

Узнать координаты: карты Google/Яндекс → точка → широта, долгота.

После добавления секретов снова **Run workflow** — в дайджесте появится погода.

---

## Кнопки (Termux на Android)

1. Установите [Termux](https://f-droid.org/packages/com.termux/) с F-Droid  
2. В Termux:
```bash
pkg update && pkg install python git
pip install requests
git clone https://github.com/demospodkos/max-news-digest.git
cd max-news-digest
export TELEGRAM_BOT_TOKEN='ваш_токен'
export TELEGRAM_CHAT_ID='ваш_id'
export GEO_LAT='68.96'
export GEO_LON='33.08'
export GEO_LABEL='Мурманск'
LIVE=1 python bot.py
```
3. В Telegram нажмите `/start` — появятся кнопки:
   - 📊 Дайджест · ⚡ Кратко
   - 🌤 Погода · 🧲 Магн. бури
   - 💱 Курсы · ₿ Крипта
   - 📰 Новости

Чтобы не гасло: `pkg install termux-services` и держите сессию, или запускайте в `tmux`.

---

## Секреты GitHub (обязательные)

| Secret | Значение |
|--------|----------|
| `TELEGRAM_BOT_TOKEN` | токен от @BotFather |
| `TELEGRAM_CHAT_ID` | ваш числовой id |
| `GEO_LAT` / `GEO_LON` или `GEO_CITY` | точка для погоды |
| `GEO_LABEL` | подпись места (опционально) |

---

## Расписание Actions

08:00 и 20:00 МСК. Ручной запуск: Actions → Telegram Digest → Run workflow.
