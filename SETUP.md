# 🚀 Установка Gemini API и развертывание проекта

## 📋 Содержание
1. [Получение Gemini API ключа](#получение-gemini-api-ключа)
2. [Установка зависимостей](#установка-зависимостей)
3. [Конфигурация окружения](#конфигурация-окружения)
4. [Запуск на локальной машине](#запуск-на-локальной-машине)
5. [Развертывание на сервере](#развертывание-на-сервере)
6. [Тестирование](#тестирование)

---

## 🔑 Получение Gemini API ключа

### Шаг 1: Регистрация и создание ключа

1. Перейти на **[Google AI Studio](https://aistudio.google.com/app/apikey)**
2. Нажать **"Create API key in new project"** (или выберите существующий проект)
3. Google создаст ключ автоматически
4. **Скопировать ключ** - вы его больше не увидите!

### Шаг 2: Сохранить ключ в `.env` файл

```bash
# Скопируйте в корневую папку проекта (.env файл)
export GEMINI_API_KEY="ваш_скопированный_ключ_тут"
```

### 💰 Стоимость и ограничения

| План | Статус | Возможности |
|------|--------|-----------|
| **Free** | ✅ Бесплатно | • 15 запросов/мин<br>• 1M токенов/день<br>• Идеально для разработки |
| **Pay-as-you-go** | 💳 Платный | • Unlimited запросы<br>• $0.075/1M входящих токенов<br>• $0.3/1M исходящих токенов |

**Для вашего проекта:** Бесплатного плана достаточно на 500+ сообщений в день.

---

## 📦 Установка зависимостей

### Шаг 1: Python окружение (обязательно 3.11+)

```bash
# Проверить версию Python
python --version  # должно быть >= 3.11

# (Опционально) Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

### Шаг 2: Установить новые зависимости

```bash
# Обновить pip
pip install --upgrade pip setuptools wheel

# Установить проект с новыми зависимостями
pip install -e .

# Или если вы не в папке проекта:
cd /path/to/assistant-whatsapp
pip install -e .
```

### Проверка установки

```bash
python -c "import google.generativeai; import tenacity; print('✅ Зависимости установлены')"
```

---

## 🔧 Конфигурация окружения

### Шаг 1: Создать `.env` файл

**На локальной машине (`/home/diana/Documents/GitHub/assistant-whatsapp/.env`):**

```env
# ===== Gemini API =====
GEMINI_API_KEY=sk-...  # Ваш ключ из Google AI Studio
GEMINI_MODEL=gemini-1.5-flash  # Или gemini-2.0-flash для большей скорости

# ===== Database =====
DATABASE_URL=postgresql+psycopg://assistant:assistant@localhost:5432/assistant
REDIS_URL=redis://localhost:6379/0

# ===== WhatsApp =====
WHATSAPP_VERIFY_TOKEN=your_verify_token
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_GRAPH_VERSION=v20.0

# ===== App Settings =====
APP_ENV=dev
APP_DEBUG=true
APP_TIMEZONE=Asia/Almaty  # Или ваша временная зона
APP_NAME=Task Assistant API

# ===== Опционально: Google Calendar =====
GOOGLE_CALENDAR_CLIENT_ID=your_client_id
GOOGLE_CALENDAR_CLIENT_SECRET=your_client_secret
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/oauth/google/callback

# ===== Опционально: Email =====
EMAIL_INBOUND_SECRET=your_email_secret
```

**На сервере (переменные окружения системы):**

```bash
# Установить через export в ~/.bashrc или ~/.zshrc
export GEMINI_API_KEY="ваш_ключ"
export DATABASE_URL="postgresql+psycopg://..."
export REDIS_URL="redis://..."
export WHATSAPP_ACCESS_TOKEN="..."
# и т.д.

# Или через systemd environment file (лучше всего)
sudo nano /etc/default/assistant-whatsapp
# Добавить все переменные там
```

---

## 🏃 Запуск на локальной машине

### Шаг 1: Запустить Docker services (PostgreSQL, Redis)

```bash
cd /home/diana/Documents/GitHub/assistant-whatsapp

# Запустить только базы данных
docker-compose up postgres redis -d

# Проверить статус
docker-compose ps
```

### Шаг 2: Запустить миграции

```bash
# Автоматически при запуске через docker-compose
docker-compose up migrate -d

# Или вручную
alembic upgrade head
```

### Шаг 3: Запустить FastAPI сервер (разработка)

```bash
# Вариант 1: Uvicorn с автообновлением
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Вариант 2: Python напрямую
python -m app.main

# Вариант 3: Через Docker
docker-compose up api -d
```

### Шаг 4: Запустить Celery worker и beat scheduler

```bash
# В отдельном терминале - Celery Worker
celery -A app.workers.celery_app worker --loglevel=info

# В еще одном терминале - Celery Beat Scheduler  
celery -A app.workers.celery_app beat --loglevel=info

# Или через Docker
docker-compose up worker beat -d
```

### Проверка локально

```bash
# API Swagger документация
curl http://localhost:8000/docs

# Health check
curl http://localhost:8000/healthz

# Тестовое сообщение (если чита работает)
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test-user", "title":"Test task"}'
```

---

## 🖥️ Развертывание на сервере

### Выбор сервера

**Рекомендуемые конфигурации:**

| Размер | CPU | RAM | Диск | Цена* | Провайдер |
|--------|-----|-----|------|-------|-----------|
| **Micro** | 1-2 | 1GB | 20GB | $5-10 | DigitalOcean, Linode |
| **Small** | 2 | 2-4GB | 50GB | $15-25 | AWS t3.small, DigitalOcean |
| **Medium** | 2-4 | 4-8GB | 100GB | $30-50 | AWS t3.medium, Hetzner |

*Ваш проект работает отлично даже на **Micro** с 1GB RAM!

### Установка на сервере

#### Option 1: Docker Compose (рекомендуется)

```bash
# 1. SSH на сервер
ssh root@your_server_ip

# 2. Установить Docker и Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 3. Клонировать проект
cd /opt
git clone https://github.com/your-repo/assistant-whatsapp.git
cd assistant-whatsapp

# 4. Создать .env с переменными окружения (ВАЖНО!)
nano .env
# Вставить переменные (см. пример выше)

# 5. Запустить все сервисы
docker-compose up -d

# 6. Проверить логи
docker-compose logs -f api
```

#### Option 2: Systemd сервис

```bash
# 1. Установить зависимости
sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql-client redis-tools git

# 2. Клонировать и настроить
cd /opt
git clone https://github.com/your-repo/assistant-whatsapp.git
cd assistant-whatsapp
python3.11 -m venv venv
source venv/bin/activate
pip install -e .

# 3. Создать сервисный файл
sudo nano /etc/systemd/system/assistant-api.service
```

Содержимое `/etc/systemd/system/assistant-api.service`:

```ini
[Unit]
Description=WhatsApp Task Assistant API
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/assistant-whatsapp
Environment="PATH=/opt/assistant-whatsapp/venv/bin"
EnvironmentFile=/etc/default/assistant-whatsapp
ExecStart=/opt/assistant-whatsapp/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 4. Запустить сервис
sudo systemctl daemon-reload
sudo systemctl enable assistant-api
sudo systemctl start assistant-api
sudo systemctl status assistant-api

# 5. Проверить логи
sudo journalctl -u assistant-api -f
```

### Firewall и обратный прокси (Nginx)

```bash
# Установить Nginx
sudo apt install -y nginx

# Создать конфиг
sudo nano /etc/nginx/sites-available/assistant-api
```

Содержимое конфига:

```nginx
upstream assistant_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name api.yourdomain.com;

    client_max_body_size 10M;

    location / {
        proxy_pass http://assistant_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
    }

    location /webhooks/whatsapp {
        proxy_pass http://assistant_api;
        proxy_set_header Host $host;
    }
}
```

```bash
# Включить конфиг
sudo ln -s /etc/nginx/sites-available/assistant-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# SSL сертификат (Let's Encrypt)
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

---

## ✅ Тестирование

### Локально

```bash
# 1. Проверить, что API запущен
curl http://localhost:8000/healthz
# Ответ: {"status":"ok"}

# 2. Проверить Gemini интеграцию
python -c "
import asyncio
from app.services.gemini_client import GeminiClient

async def test():
    client = GeminiClient()
    result = await client.is_healthy()
    print(f'Gemini API: {\"✅ OK\" if result else \"❌ Failed\"}')

asyncio.run(test())
"

# 3. Тестировать задачу
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "title": "Купить молоко",
    "description": "Молоко для кофе",
    "priority": "medium"
  }'

# 4. Проверить парсинг уведомлений (в 15 часов)
python -c "
from app.services.reminder_service import ReminderService
from datetime import datetime
import pytz

db = None  # Используем None для теста
rs = ReminderService(db)
now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=pytz.UTC)

# Тест "в 15 часов"
result = rs.parse_notification_text('позвони в 15 часов', 'Asia/Almaty', now)
print(f'Парсинг \"в 15 часов\": {result}')

# Тест "за 2 часа до 15"
result = rs.parse_notification_text('встреча в 15, напомни за 2 часа', 'Asia/Almaty', now)
print(f'Парсинг \"в 15, за 2 часа\": {result}')
"
```

### На сервере

```bash
# 1. Проверить сервис работает
curl https://api.yourdomain.com/healthz

# 2. Проверить логи
docker-compose logs --tail=50 api
# или
sudo journalctl -u assistant-api --tail=50

# 3. Проверить базу данных
docker-compose exec postgres psql -U assistant -d assistant -c "SELECT COUNT(*) FROM tasks;"

# 4. Проверить Redis
docker-compose exec redis redis-cli ping
```

---

## 📊 Мониторинг и логирование

### Структура логов

Все логи сохраняются с:
- ✅ Уровнями: DEBUG, INFO, WARNING, ERROR
- ✅ Микросекундной точностью
- ✅ Именами модулей и функций
- ✅ Stack traces для ошибок

### Полезные команды

```bash
# Следить за логами API
docker-compose logs -f api --tail=100

# Проверить ошибки Celery
docker-compose logs -f worker

# Синхронизировать с Gemini API через логи
docker-compose logs api | grep -i gemini

# Исчекать ошибки БД
docker-compose logs api | grep -i "database\|postgresql"
```

---

## 🚨 Решение проблем

### Gemini API возвращает 429 (Rate Limit)

✅ **Решение:** Уже встроено!
- Автоматический retry с exponential backoff
- 3 попытки с увеличивающейся задержкой (1-30 сек)
- Fallback на rule-based парсинг

### "в 15 часов" не работает

✅ **Решено в обновлении:**
- Regex теперь поддерживает часы без минут
- Автоматически устанавливает минуты = 00
- Работает: "в 15", "в 15 часов", "в 15:30"

### WhatsApp сообщение не отправляется

1. Проверить WHATSAPP_ACCESS_TOKEN в .env
2. Проверить, что номер телефона правильный
3. Проверить логи: `docker-compose logs api | grep -i whatsapp`
4. Убедиться, что WhatsApp API включен

---

## 🎉 Готово!

Ваш проект полностью интегрирован с Gemini API и готов к использованию!

**Проверка перед production:**

- [ ] GEMINI_API_KEY добавлен
- [ ] DATABASE_URL указан правильно
- [ ] REDIS работает
- [ ] WhatsApp токены установлены
- [ ] HTTPS сертификат на сервере
- [ ] Мониторинг логов настроен
- [ ] Backup база данных

**Поддержка:**
- 📖 Документация: [README.md](README.md)
- 🐛 Проблемы: Проверьте логи в Docker или systemd
- 💬 Вопросы: Смотрите [DEVELOPMENT.md](DEVELOPMENT.md)
