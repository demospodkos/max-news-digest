# Telegram-бот: утренний и вечерний дайджест

Бот присылает в Telegram сводку: погоду, курсы ЦБ, ключевую ставку, нефть, индексы,
акции, криптовалюты, драгметаллы, магнитные бури, календарь событий и новости со ссылками.
Дайджест приходит по расписанию, а кнопки в чате отвечают мгновенно.

Все источники бесплатные и без API-ключей: Open-Meteo, ЦБ РФ, MOEX, CoinGecko, NOAA, RSS РБК/Интерфакс/ТАСС/РИА/BFM/Лента.

## Что нужно

1. Токен бота от [@BotFather](https://t.me/BotFather) (`/newbot`).
2. Ваш числовой chat id (например, через [@userinfobot](https://t.me/userinfobot)).

Бот отвечает только в чате с этим id. Для другого человека разворачивается отдельный экземпляр со своим токеном.

## Запуск за 1 минуту (локально)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=123:ABC
export TELEGRAM_CHAT_ID=123456789
export GEO_CITY=Moscow
python bot.py          # отправит один дайджест и завершится
LIVE=1 python bot.py   # режим «онлайн»: кнопки отвечают сразу
```

## Хостинг 24/7 (быстрые кнопки)

### Railway
1. https://railway.app → войти через **GitHub** → **New Project** → **Deploy from GitHub repo**.
2. Вкладка **Variables**: `LIVE=1`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEO_CITY` (или `GEO_LAT`/`GEO_LON`).
3. Railway подхватит `Dockerfile` или `Procfile`. Дождитесь статуса **Online** и отправьте боту `/start`.

### Render
1. https://render.com → **New** → **Blueprint** (подхватит `render.yaml`) или **Background Worker**.
2. Start command: `python -u bot.py`, переменные те же.

> На Render бесплатный **Web Service** засыпает. Нужен именно **Background Worker**.

> Файловая система бесплатных хостингов сбрасывается при рестарте: настройки (тикеры, монеты, город)
> тогда пропадут. Если нужны постоянные настройки, подключите диск и укажите `DATA_DIR` (см. ниже).

## Дайджест по расписанию (GitHub Actions)

Workflow `Telegram Digest` отправляет дайджест в 08:00 и 20:00 МСК. В **Settings → Secrets and variables → Actions**
добавьте `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` и при желании `GEO_*`.

Workflow `Button Poller` обрабатывает кнопки раз в 5 минут. Если бот уже запущен на хостинге (`LIVE=1`),
отключите его (Actions → Button Poller → `...` → Disable workflow), иначе ответы будут дублироваться.

## Переменные окружения

| Имя | Обязательно | Зачем |
|-----|-------------|--------|
| `TELEGRAM_BOT_TOKEN` | да | токен бота |
| `TELEGRAM_CHAT_ID` | да | id чата, в котором бот работает |
| `LIVE` | на хостинге | `1` — бот слушает кнопки постоянно |
| `GEO_CITY` | для погоды | название города, например `Murmansk` |
| `GEO_LAT` / `GEO_LON` / `GEO_LABEL` | вместо города | координаты и подпись |
| `BOT_TZ` | нет | часовой пояс, по умолчанию `Europe/Moscow` |
| `DATA_DIR` | нет | папка для `prefs.json`, `geo.json`, `events.json` и offset (постоянный диск) |
| `ERROR_NOTIFY` | нет | `0` — не присылать в чат сообщения об ошибках блоков |

## Команды в чате

`/start`, `/menu`, `/digest`, `/short`, `/weather`, `/rates`, `/macro`, `/index`, `/crypto`, `/news`, `/calendar`, `/geo`, `/city`, `/settings`

Настройки:
`/tickers SBER GAZP YNDX` · `/coins bitcoin ethereum solana` · `/short_on` · `/short_off` ·
`/quiet 22:00 07:00` · `/quiet off` · `/news_cat all|polit|econ|tech|world` · `/hide`

## Календарь событий

Встроенный список охватывает 2026 год, а даты заседаний ЦБ/ФРС в нём ориентировочные.
Чтобы задать свой, положите в `DATA_DIR` (или рядом с `bot.py`) файл `events.json`:

```json
[["2026-12-19", "Заседание ЦБ РФ (ключевая ставка)"], ["2027-01-01", "Новый год: рынки закрыты"]]
```

## Разработка

```bash
pip install -r requirements-dev.txt
python -m pytest
```
