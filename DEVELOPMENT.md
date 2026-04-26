# Task Assistant (Python) — Production Backend

## Quick Start

### Local Development (Docker Compose)

```bash
cp .env.example .env
docker compose up
```

This will start:
- FastAPI API on http://localhost:8000
- PostgreSQL on localhost:5432
- Redis on localhost:6379
- Celery worker for async jobs
- Celery beat for scheduled jobs

Health check: `curl http://localhost:8000/healthz`

### Without Docker

```bash
# Install dependencies
pip install -e "."

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload

# In separate terminal: start Celery worker
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO

# In third terminal: start Celery beat scheduler
celery -A app.workers.celery_app.celery_app beat --loglevel=INFO
```

## Architecture

- **API Layer**: [FastAPI](https://fastapi.tiangolo.com/) with Pydantic schemas
- **Data Layer**: SQLAlchemy ORM + Alembic migrations + PostgreSQL
- **Async Jobs**: Celery + Redis + Beat scheduler
- **NLP**: Gemini API + rule-based date parsing + confidence scoring
- **Integrations**: Meta WhatsApp Cloud API, email inbound, Google Calendar API

## Key Endpoints

- `GET /healthz` — Health check
- `POST /webhooks/whatsapp` — Inbound WhatsApp messages
- `POST /webhooks/email` — Inbound emails (with signature validation)
- `POST /webhooks/calendar` — Calendar event sync
- `POST /tasks` — Create a task
- `GET /tasks/open/{user_id}` — List open tasks
- `PATCH /tasks/{task_id}` — Update task
- `POST /tasks/{task_id}/complete` — Mark task as done
- `GET /agenda/day?user_id=...&target_date=YYYY-MM-DD` — Day agenda
- `GET /agenda/week?user_id=...&pivot_date=YYYY-MM-DD` — Week agenda

## Configuration (.env)

```
APP_ENV=dev  # dev, stage, prod
APP_NAME=Task Assistant API
APP_TIMEZONE=Asia/Almaty
APP_DEBUG=true

DATABASE_URL=postgresql+psycopg://assistant:assistant@localhost:5432/assistant
REDIS_URL=redis://localhost:6379/0

GEMINI_API_KEY=<your-api-key>
GEMINI_MODEL=gemini-1.5-flash

WHATSAPP_VERIFY_TOKEN=<your-verify-token>
WHATSAPP_ACCESS_TOKEN=<your-access-token>
WHATSAPP_PHONE_NUMBER_ID=<your-phone-number-id>

GOOGLE_CALENDAR_CLIENT_ID=<your-client-id>
GOOGLE_CALENDAR_CLIENT_SECRET=<your-secret>

EMAIL_INBOUND_SECRET=<your-secret>
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test
pytest tests/test_health.py -v
```

## How To Access The Assistant Locally

After starting the API (`uvicorn app.main:app --reload`), use:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

Primary interaction channels:

1. REST tasks and agenda endpoints (`/tasks`, `/agenda/day`, `/agenda/week`).
2. Integration webhooks (`/webhooks/whatsapp`, `/webhooks/email`, `/webhooks/calendar`).
3. Background execution via Celery worker and beat for NLP/reminders.

## Deployment

### Docker

```bash
docker build -t task-assistant:latest .
docker run \
  --env-file .env.prod \
  -p 8000:8000 \
  task-assistant:latest
```

### Docker Compose (with services)

```bash
docker compose -f docker-compose.yml up -d
```

## Monitoring

Logs are structured in JSON format for easy parsing:

```bash
# Watch logs from all services
docker compose logs -f

# Follow API logs
docker compose logs -f api
```

## Development

### Code style

```bash
ruff check app tests
ruff format app tests
mypy app
```

### Database migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add new column"

# Apply migrations
alembic upgrade head

# Rollback one revision
alembic downgrade -1
```

### Celery tasks

Tasks are defined in `app/workers/jobs.py` and scheduled in `app/workers/celery_app.py`.

To debug a task:
```bash
# Run task synchronously in Python shell
from app.workers.jobs import process_whatsapp_inbound
process_whatsapp_inbound(...)
```

## Support

For issues or questions, check the technical specification at `docs/ai-assistant-tech-spec.md`.
