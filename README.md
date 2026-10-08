# Дайджест + быстрые кнопки (Telegram)

## Быстрые кнопки = хостинг 24/7

GitHub Actions оставьте для дайджеста по расписанию.  
Для **мгновенных кнопок** запустите бота на бесплатном хостинге (2–5 минут с телефона).

---

## Вариант A — Railway (удобнее с телефона)

1. Откройте https://railway.app → войти через **GitHub**
2. **New Project** → **Deploy from GitHub repo** → `max-news-digest`
3. После деплоя: вкладка **Variables** → добавьте:

| Variable | Значение |
|----------|----------|
| `LIVE` | `1` |
| `TELEGRAM_BOT_TOKEN` | токен от @BotFather |
| `TELEGRAM_CHAT_ID` | ваш числовой id |
| `GEO_LAT` | широта (или пусто) |
| `GEO_LON` | долгота (или пусто) |
| `GEO_CITY` | например `Murmansk` |

4. **Settings** → убедитесь, что start command: `python -u bot.py`  
   (или Railway подхватит Dockerfile / Procfile)
5. Дождитесь статуса **Online**
6. В Telegram: `/start` — кнопки отвечают сразу

---

## Вариант B — Render

1. https://render.com → Sign in with GitHub  
2. **New** → **Background Worker** (не Web Service)  
3. Repo: `max-news-digest`  
4. Start command: `python -u bot.py`  
5. Environment: те же переменные, что выше (`LIVE=1`, токен, chat_id…)  
6. Create Worker → дождитесь Live  

⚠️ Free Web Service на Render засыпает — нужен именно **Background Worker**.

---

## Расписание дайджеста (GitHub)

По-прежнему 08:00 и 20:00 МСК через Actions.  
Кнопки обрабатывает хостинг — без задержки 5 минут.

Если и хостинг, и старый **Button Poller** оба отвечают — отключите poll:  
Actions → Button Poller → `...` → Disable workflow  
(чтобы не было двойных ответов).

---

## Переменные

| Имя | Обязательно | Зачем |
|-----|-------------|--------|
| `TELEGRAM_BOT_TOKEN` | да | токен бота |
| `TELEGRAM_CHAT_ID` | да | ваш id |
| `LIVE` | да на хосте | `1` = кнопки онлайн |
| `GEO_LAT` / `GEO_LON` | для погоды | координаты |
| `GEO_CITY` | или город | `Murmansk` |
