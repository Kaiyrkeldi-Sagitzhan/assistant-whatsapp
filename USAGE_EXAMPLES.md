# Task Summary - Usage Examples

## Overview

The summary feature provides three levels of task summaries:

1. **Daily Summary** - Tasks only for today's date
2. **Weekly Summary** - Tasks for the next 7 days, grouped by day (with date and day of week)
3. **Monthly Summary** - Tasks grouped by 7-day weeks

## User-Facing Functions (Easiest to Use)

The `app/user_summary.py` module provides simple functions for users:

```python
from app.user_summary import (
    get_my_day_summary,
    get_my_week_summary,
    get_my_month_summary,
    print_my_day_summary,
    print_my_week_summary,
    print_my_month_summary
)

# Get data as dictionaries
day = get_my_day_summary("user-uuid-here")
week = get_my_week_summary("user-uuid-here")
month = get_my_month_summary("user-uuid-here")

# Or print formatted output directly
print_my_day_summary("user-uuid-here")
print_my_week_summary("user-uuid-here")
print_my_month_summary("user-uuid-here")
```

## Send Summary via WhatsApp

The `ReminderService` can generate and send summaries directly to users via WhatsApp:

```python
from app.services.reminder_service import ReminderService
from sqlalchemy.orm import Session

# In your code with a db session:
service = ReminderService(db)

# Send daily summary via WhatsApp
service.send_summary_via_whatsapp(user_id, "day")

# Send weekly summary via WhatsApp
service.send_summary_via_whatsapp(user_id, "week")

# Send monthly summary via WhatsApp
service.send_summary_via_whatsapp(user_id, "month")

# With specific date
from datetime import date
service.send_summary_via_whatsapp(user_id, "day", target_date=date(2026, 4, 26))
```

Returns `True` if sent successfully, `False` otherwise.

## Task Notifications & Commands

The `TaskService` provides methods to send proactive notifications to users:

### Send Task Notification
```python
from app.services.task_service import TaskService

service = TaskService(db)

# Send WhatsApp notification about a specific task
service.send_task_notification(task_id, custom_message="Don't forget this!")
```

### Send Event Notification
```python
# Send WhatsApp notification about an upcoming calendar event
service.send_event_notification(event_id, reminder_minutes=30)
```

### Broadcast Message to Multiple Users
```python
# Send announcement to multiple users
results = service.broadcast_message(
    user_ids=[user1_id, user2_id, user3_id],
    message="Server maintenance scheduled for tonight at 2 AM",
    subject="⚠️ Important Announcement"
)
print(f"Sent: {results['success']}, Failed: {results['failed']}")
```

### Send Task Digest
```python
# Send daily/weekly/overdue task digest via WhatsApp
service.send_task_digest(user_id, digest_type="daily")
service.send_task_digest(user_id, digest_type="weekly")
service.send_task_digest(user_id, digest_type="overdue")
```

### Setup Auto Reminders
```python
from datetime import timedelta

# Set up automatic reminders for multiple tasks
service.setup_auto_reminders(
    user_id=user_id,
    task_ids=[task1_id, task2_id],
    reminder_type="all"  # "exact", "before_deadline", or "all"
)
```

## API Endpoints

### 1. Daily Summary
```
GET /summary/day?user_id=<UUID>&target_date=<YYYY-MM-DD>
```

**Parameters:**
- `user_id` (required): User UUID
- `target_date` (optional): Target date in YYYY-MM-DD format. Defaults to today.

**Response:**
```json
{
  "date": "2026-04-26",
  "day_of_week": "Saturday",
  "tasks": [
    {
      "id": "...",
      "title": "Task title",
      "description": "Task description",
      "priority": "high",
      "status": "open",
      "due_at": "2026-04-26T14:00:00+05:00",
      "created_at": "2026-04-25T10:00:00+05:00"
    }
  ],
  "total_tasks": 5
}
```

### 2. Weekly Summary
```
GET /summary/week?user_id=<UUID>&pivot_date=<YYYY-MM-DD>
```

**Parameters:**
- `user_id` (required): User UUID
- `pivot_date` (optional): Pivot date in YYYY-MM-DD format. Defaults to today.

**Response:**
```json
{
  "week_start": "2026-04-26",
  "week_end": "2026-05-02",
  "total_tasks": 15,
  "days": {
    "2026-04-26": {
      "date": "2026-04-26",
      "day_of_week": "Saturday",
      "tasks": [...],
      "task_count": 3
    },
    "2026-04-27": {
      "date": "2026-04-27",
      "day_of_week": "Sunday",
      "tasks": [...],
      "task_count": 2
    }
  }
}
```

### 3. Monthly Summary
```
GET /summary/month?user_id=<UUID>&pivot_date=<YYYY-MM-DD>
```

**Parameters:**
- `user_id` (required): User UUID
- `pivot_date` (optional): Pivot date in YYYY-MM-DD format. Defaults to today.

**Response:**
```json
{
  "month": "2026-04",
  "total_tasks": 45,
  "weeks": {
    "week_1": {
      "period": {
        "start": "2026-04-01",
        "end": "2026-04-07"
      },
      "tasks": [...],
      "task_count": 12
    },
    "week_2": {
      "period": {
        "start": "2026-04-08",
        "end": "2026-04-14"
      },
      "tasks": [...],
      "task_count": 15
    }
  }
}
```

### 4. Send Summary via WhatsApp
```
POST /agenda/send-summary/{summary_type}?user_id=<UUID>&target_date=<YYYY-MM-DD>
```

**Parameters:**
- `user_id` (required): User UUID
- `summary_type` (required, path): "day", "week", or "month"
- `target_date` (optional): Target date in YYYY-MM-DD format. Defaults to today.

**Response:**
```json
{
  "success": true,
  "message": "day summary sent successfully"
}
```

### 5. Send Task Notification
```
POST /tasks/{task_id}/notify?custom_message=<optional>
```

Send WhatsApp notification about a specific task to the user.

### 6. Send Event Notification
```
POST /tasks/{task_id}/event-notify?reminder_minutes=30
```

Send WhatsApp notification about an upcoming calendar event.

### 7. Broadcast Message
```
POST /tasks/broadcast
```

**Body:**
```json
{
  "user_ids": ["uuid1", "uuid2"],
  "message": "Server maintenance tonight",
  "subject": "⚠️ Important"
}
```

### 8. Send Task Digest
```
POST /tasks/{user_id}/digest?digest_type=daily
```

Send daily/weekly/overdue task digest via WhatsApp.

### 9. Setup Auto Reminders
```
POST /tasks/{user_id}/auto-reminders
```

**Body:**
```json
{
  "task_ids": ["uuid1", "uuid2"],
  "reminder_type": "all"
}
```

## Python Usage

### Using User-Facing Functions (Recommended)

```python
from app.user_summary import get_my_day_summary, get_my_week_summary, get_my_month_summary

# Daily summary
day_summary = get_my_day_summary(user_id="user-uuid-here")
print(f"Today's tasks: {day_summary['total_tasks']}")

# Weekly summary
week_summary = get_my_week_summary(user_id="user-uuid-here")
for date_str, day_info in week_summary['days'].items():
    print(f"{date_str} ({day_info['day_of_week']}): {day_info['task_count']} tasks")

# Monthly summary
month_summary = get_my_month_summary(user_id="user-uuid-here")
print(f"Month {month_summary['month']}: {month_summary['total_tasks']} tasks")
for week_key, week_info in month_summary['weeks'].items():
    print(f"  {week_key}: {week_info['task_count']} tasks")
```

### Using Task Notifications

```python
from app.services.task_service import TaskService

service = TaskService(db)

# Send task notification
service.send_task_notification(task_id, "Don't forget!")

# Send event notification
service.send_event_notification(event_id, reminder_minutes=60)

# Broadcast to all users
results = service.broadcast_message(
    user_ids=[user1_id, user2_id],
    message="System update tonight",
    subject="⚠️ Notice"
)

# Send task digest
service.send_task_digest(user_id, "daily")

# Setup auto reminders
service.setup_auto_reminders(user_id, task_ids, "all")
```

### Using the Service Directly

```python
from app.services.agenda_service import AgendaService

service = AgendaService()

# Daily summary
day_summary = service.get_day_summary(user_id="user-uuid-here")

# Weekly summary
week_summary = service.get_week_summary(user_id="user-uuid-here")

# Monthly summary
month_summary = service.get_month_summary(user_id="user-uuid-here")
```

### Using the API with requests

```python
import requests

BASE_URL = "http://localhost:8000"

# Daily summary
response = requests.get(
    f"{BASE_URL}/summary/day",
    params={"user_id": "user-uuid-here"}
)
day_summary = response.json()

# Send task notification
response = requests.post(
    f"{BASE_URL}/tasks/{task_id}/notify",
    params={"custom_message": "Reminder!"}
)

# Send task digest
response = requests.post(
    f"{BASE_URL}/tasks/{user_id}/digest",
    params={"digest_type": "daily"}
)

# Broadcast message
response = requests.post(
    f"{BASE_URL}/tasks/broadcast",
    json={
        "user_ids": ["uuid1", "uuid2"],
        "message": "Hello everyone!",
        "subject": "Announcement"
    }
)
```

## Chat with the Bot

The bot can understand natural language messages and respond intelligently:

### Ask for Help
```
User: помощь
Bot: 🤖 Я ваш умный помощник по управлению задачами!
    
    📝 **УМЕЮ СОЗДАВАТЬ ЗАДАЧИ:**
    • Просто опишите задачу: 'Купить молоко завтра в 10 утра'
    • 'Встреча с клиентом в пятницу 15:00'
    
    📋 **УМЕЮ ПОКАЗЫВАТЬ ЗАДАЧИ:**
    • 'мои задачи' - список всех активных задач
    • 'повестка' или 'agenda' - расписание на сегодня
    • 'план на неделю' - обзор на ближайшие 7 дней
    
    ✅ **УМЕЮ ОТМЕЧАТЬ ВЫПОЛНЕНИЕ:**
    • 'выполнил [название задачи]'
    • 'готово [название задачи]'
    
    📅 **УМЕЮ ПОДКЛЮЧАТЬСЯ К КАЛЕНДАРЮ:**
    • Google Календарь для синхронизации встреч
    
    📊 **УМЕЮ ОТПРАВЛЯТЬ СВОДКИ В WHATSAPP:**
    • Сводка на день - задачи только на сегодня
    • Сводка на неделю - все задачи на 7 дней с разбивкой по дням
    • Сводка на месяц - все задачи, сгруппированные по неделям
    
    🔔 **АВТОМАТИЧЕСКИЕ НАПОМИНАНИЯ:**
    • За 1 час до дедлайна (для важных задач)
    • За 1 день до дедлайна (для критических задач)
    • Утренние и вечерние дайджесты
    
    💡 **ПРИМЕРЫ КОМАНД:**
    • 'Купить продукты завтра'
    • 'Выполнил отчет'
    • 'Покажи мои задачи'
    • 'Какая у меня повестка?'
    • 'Свободное время сегодня'
    
    🆘 **ПОМОЩЬ:**
    Напишите 'помощь' в любое время, чтобы увидеть это сообщение снова!
```

### Create Tasks
```
User: Купить молоко завтра в 10 утра
Bot: ✅ Отлично! Задача 'Купить молоко' создана.
    📅 Срок: 27.04 10:00
    🔄 Напомню за 30 минут
    💪 Вы всегда можете попросить список задач, сказав 'мои задачи'
```

### List Tasks
```
User: мои задачи
Bot: 📋 У вас 3 активных задачи:
    🔥 Высокий приоритет (1):
      • Подготовить отчет (до 26.04 15:00)
    ⚡ Средний приоритет (1):
      • Купить продукты (до 27.04 10:00)
    📝 Низкий приоритет (1):
      • Позвонить маме
    
    💡 Чтобы выполнить задачу, скажите 'выполнил [название]'
```

### Daily Agenda
```
User: повестка
Bot: 📋 Ваш день сегодня:
    
    🌅 Встречи:
    • 10:00-11:00: Совещание по проекту
    
    📝 Задачи на сегодня:
    🔥 Подготовить отчет (15:00)
    ⚡ Купить продукты (10:00)
    
    💡 Свободное время:
    • 11:00-15:00 (4h)
    
    ⚖️ Умеренная нагрузка
```

### Complete Tasks
```
User: выполнил отчет
Bot: ✅ Отлично! Задача 'Подготовить отчет' выполнена! 🎉
    💪 Молодец, продолжайте в том же духе!
```

## CLI Usage

A CLI tool is provided in `summary_cli.py`:

```bash
# Show all summaries (day, week, month)
python summary_cli.py <user-uuid>

# Show only daily summary
python summary_cli.py <user-uuid> --day

# Show only weekly summary
python summary_cli.py <user-uuid> --week

# Show only monthly summary
python summary_cli.py <user-uuid> --month

# Show summaries for a specific date
python summary_cli.py <user-uuid> --day --date 2026-04-26

# Show multiple summaries
python summary_cli.py <user-uuid> --day --week
```

## Key Features

### Daily Summary
- Shows tasks due on the specific day only
- Does not include tasks without due dates
- Includes task priority, status, and due time

### Weekly Summary
- Shows tasks for the next 7 days from the pivot date
- Tasks are grouped separately by day
- Each day shows: date, day of week, task list, and task count

### Monthly Summary
- Shows tasks for the entire month
- Tasks are grouped by 7-day weeks
- Each week shows its period (start/end dates) and tasks within that period
- Weeks are numbered (week_1, week_2, etc.)

### Task Notifications
- Send immediate WhatsApp notifications about specific tasks
- Send event reminders with countdown timers
- Broadcast messages to multiple users
- Send automated task digests (daily/weekly/overdue)
- Set up automatic reminders for multiple tasks at once

## Notes

- All times are stored in UTC and converted to the user's timezone for display
- Only incomplete (non-completed) tasks are included in summaries
- Tasks without due dates are excluded from summaries (except in agenda views)
- The pivot_date parameter defaults to today if not specified
- WhatsApp summaries require a valid WhatsApp phone number for the user
- All notification functions return True/False for success/failure tracking
