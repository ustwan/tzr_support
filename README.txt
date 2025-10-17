# TZR Feedback Bot (WebSocket Version)

Telegram бот для приёма обращений через WebSocket соединение с сайтом.

## Архитектура

Bot (WebSocket Client) ──WS──> Django Site ──> Пользователи
         ↓
    Telegram Group
    
НЕТ ВХОДЯЩИХ ПОРТОВ! Бот подключается к сайту (исходящее соединение).

## Конфигурация (.env)

# Telegram
TELEGRAM_BOT_TOKEN=8499545269:AAEXWsNh-YfrncsCiZP31x4V3wDwgdgHHOM
FEEDBACK_TELEGRAM_CHANNEL_ID=-1003105374647

# WebSocket (получить JWT токен на сайте)
SITE_WS_URL=wss://tzreloaded.ru/ws/feedback-bot?token=<JWT>
HMAC_SECRET=<тот же что на сайте>
WS_PING_INTERVAL=20
RECONNECT_BACKOFF=5

## Запуск

docker-compose up -d

## Остановка

docker-compose down

## Логи

docker-compose logs -f feedback-bot

## Функции

- WebSocket клиент к Django сайту (исходящее соединение)
- Приём обращений с сайта через WebSocket
- Приём обращений в ЛС бота (/feedback)
- Rate limiting: 5 обращений / 10 минут
- Уникальные номера тикетов (ticket_site_X, ticket_tg_X)
- Кнопки управления статусами в группе
- Московская таймзона (МСК)
- HMAC подписи сообщений (как в Site Agent)

## Команды бота

/start - Приветствие
/feedback - Создать обращение
/help - Помощь
/cancel - Отменить

## Безопасность

- JWT токен для WebSocket подключения
- HMAC-SHA256 подписи всех сообщений
- TTL сообщений: 45 секунд
- Защита от replay атак (nonce)
- Никаких открытых портов

## Структура файлов

main.py              - Точка входа (запускает WS + Telegram)
telegram_bot.py      - Telegram бот (класс)
ws_client.py         - WebSocket клиент к сайту
hmac_utils.py        - HMAC подписи (как в Site Agent)
ticket_counter.py    - Счётчик тикетов
rate_limiter.py      - Rate limiting
docker-compose.yml   - Docker конфигурация
Dockerfile.bot       - Docker образ
