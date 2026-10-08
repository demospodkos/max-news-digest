# Дайджест в Telegram — без ПК и без Termux

## Что работает

| Функция | Как |
|---------|-----|
| Дайджест 08:00 и 20:00 МСК | GitHub Actions по расписанию |
| **Кнопки** (погода, курсы…) | GitHub проверяет нажатия **каждые 5 минут** |
| Геолокация «📍 Гео» | Тоже через опрос раз в 5 мин |

Ответ на кнопку обычно приходит **за 1–5 минут**, не мгновенно — так устроен бесплатный GitHub без сервера.

## Secrets (Settings → Secrets → Actions)

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEO_LAT` + `GEO_LON` или `GEO_CITY` (погода)

## Ручной запуск

Actions → **Telegram Digest** → Run workflow  
Actions → **Button Poller** → Run workflow (сразу обработать кнопки)
