import requests
import json

BASE_URL = "http://localhost:8000"

def create_task_with_custom_reminder(user_id, title, due_at, reminder_time, description=None):
    payload = {
        "user_id": user_id,
        "title": title,
        "description": description,
        "due_at": due_at,
        "priority": "medium",
        "reminder_time": reminder_time
    }
    resp = requests.post(f"{BASE_URL}/tasks", json=payload)
    resp.raise_for_status()
    return resp.json()

def list_reminders(user_id):
    resp = requests.get(f"{BASE_URL}/reminders", params={"user_id": user_id})
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    # Example usage
    user_id = "11111111-1111-1111-1111-111111111111"
    task = create_task_with_custom_reminder(
        user_id=user_id,
        title="Тестовое задание",
        due_at="2026-05-12T10:00:00+05:00",
        reminder_time="2026-05-12T09:30:00+05:00",
        description="Проверка пользовательского времени напоминания"
    )
    print("Created task:", task["id"])

    reminders = list_reminders(user_id)
    print("Reminders for user:", reminders)