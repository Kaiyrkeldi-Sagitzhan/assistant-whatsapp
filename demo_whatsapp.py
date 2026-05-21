#!/usr/bin/env python3
"""
WhatsApp Message Demo Script

This script allows you to simulate WhatsApp messages through the terminal.
It's useful for testing the WhatsApp integration without having to send
actual messages through the WhatsApp API.

Usage:
    python demo_whatsapp.py

The script will prompt you to enter messages to simulate.
"""

import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

# Add the app directory to the path (works both locally and in Docker)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.models import InboundChannel, InboundMessage, User, Task, TaskPriority, SourceType
from app.db.session import SessionLocal
from app.services.nlp_pipeline import NLPPipeline
from app.services.context_manager import ConversationContext
from app.services.task_service import TaskService
from app.services.reminder_service import ReminderService
from app.workers.jobs import _get_or_create_user, _store_inbound
from app.core.config import get_settings
from app.integrations.whatsapp_meta import WhatsAppMetaClient

# Test phone number for demo
TEST_PHONE = "77769707106"


def print_header():
    """Print a nice header."""
    print("\n" + "=" * 60)
    print("   WhatsApp Message Simulator")
    print("=" * 60)
    print("\nThis tool simulates WhatsApp messages for testing.")
    print(f"Test phone: {TEST_PHONE}")
    print("\nCommands:")
    print("  - Type a message to simulate receiving it")
    print("  - 'help' - Show available commands")
    print("  - 'clear' - Clear conversation context")
    print("  - 'remind' - Send due reminders now")
    print("  - 'quit' - Exit the demo")
    print("-" * 60 + "\n")


def print_message(text: str, sender: str = "User"):
    """Print a message in a chat-like format."""
    print(f"\n[{sender}] {text}")
    print("-" * 40)


def _normalize_recipient_phone(phone: str) -> str:
    """Normalize phone number to format for sending."""
    if phone.startswith('7777'):
        return '78777' + phone[4:]
    elif phone.startswith('777'):
        return '7877' + phone[3:]
    elif phone.startswith('77'):
        return '787' + phone[2:]
    return phone


async def _send_whatsapp_response(phone: str, message: str) -> bool:
    """Simulate sending a response message via WhatsApp API (demo mode).
    
    In demo mode, we print the message to console but don't send actual WhatsApp messages.
    This allows testing the assistant's responses without real API calls.
    """
    # In demo mode, print the message but don't send actual WhatsApp messages
    print(f"[Assistant] {message[:100]}{'...' if len(message) > 100 else ''}")
    return True


async def process_message(text: str, phone: str = TEST_PHONE, send_response: bool = False) -> dict:
    """
    Process a simulated WhatsApp message with full pipeline.
    
    Args:
        text: The message text
        phone: Sender's phone number
        send_response: Whether to send response via WhatsApp API (default: False for demo mode)
        
    Returns:
        Processing result dictionary
    """
    db = SessionLocal()
    try:
        # Get or create user
        user = _get_or_create_user(db, phone)
        
        # Store inbound message
        _store_inbound(
            db,
            channel=InboundChannel.WHATSAPP,
            external_message_id=f"demo_{uuid.uuid4()}",
            user_id=user.id,
            raw_text=text,
            parse_result={"phone": phone, "metadata": {"demo": True}},
        )
        
        # Parse message
        pipeline = NLPPipeline()
        parsed = await pipeline.parse_message(text, user.timezone, user_id=str(user.id))
        
        # Check for pending clarification
        context_mgr = ConversationContext()
        pending_context = await context_mgr.consume_clarification(str(user.id), text)
        
        # Generate confirmation (demo mode - no actual reminders sent)
        confirmation = await _generate_confirmation(parsed, user, pending_context, text, pipeline, db, send_reminders=False)
        
        # Send response via WhatsApp API
        if send_response and confirmation:
            await _send_whatsapp_response(phone, confirmation)
        
        return {
            "status": "processed",
            "user_id": str(user.id),
            "intent": parsed.intent,
            "title": parsed.title,
            "description": parsed.description,
            "datetime": str(parsed.datetime) if parsed.datetime else None,
            "needs_clarification": parsed.needs_clarification,
            "clarification_question": parsed.clarification_question,
            "confirmation": confirmation,
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


async def _generate_confirmation(parsed, user: User, pending_context: dict, text: str, pipeline, db, send_reminders: bool = False) -> str:
    """Generate a confirmation response based on the parsed message."""
    if pending_context:
        combined_text = pending_context["original_text"] + " " + text
        clarification_parsed = await pipeline.parse_message(combined_text, user.timezone)
        return f"✅ Задача обновлена: {clarification_parsed.title or text}"
    
    if parsed.intent == "create_task":
        if parsed.needs_clarification:
            context_mgr = ConversationContext()
            await context_mgr.set_pending_clarification(
                user_id=str(user.id),
                original_text=text,
                parsed_title=parsed.title,
                parsed_description=parsed.description,
                clarification_type=parsed.clarification_type,
                clarification_question=parsed.clarification_question,
            )
            return parsed.clarification_question
        else:
            # Create the task
            service = TaskService(db)
            task = service.create_task(
                type('TaskCreate', (), {
                    'user_id': user.id,
                    'title': parsed.title,
                    'description': parsed.description,
                    'due_at': parsed.datetime,
                    'priority': TaskPriority.MEDIUM,
                })(),
                parsed_intent=parsed.intent
            )
            
            # Update source info
            db.query(Task).filter(Task.id == task.id).update({
                Task.source_type: SourceType.WHATSAPP,
                Task.source_ref: f"demo_{uuid.uuid4()}",
            })
            db.commit()
            
            # Auto-create reminders (only if send_reminders is True)
            if send_reminders:
                reminder_service = ReminderService(db)
                reminder_service.auto_create_reminders(task)
                
                # Send first reminder immediately
                await reminder_service.send_first_reminder(task, template="default")
            
            # Format due date
            due_time_display = "не указан"
            if task.due_at:
                from app.core.time import resolve_timezone
                local_tz = resolve_timezone(user.timezone)
                local_due = task.due_at.replace(tzinfo=timezone.utc).astimezone(local_tz)
                due_time_display = local_due.strftime('%d.%m %H:%M')
            
            return (
                f"✅ Отлично! Задача '{task.title}' создана.\n"
                f"📅 Срок: {due_time_display}\n"
                f"🔄 Напомню за 30 минут"
            )
    
    elif parsed.intent == "list_tasks":
        service = TaskService(db)
        tasks = service.list_open_tasks(user.id)
        if not tasks:
            return "✅ У вас нет активных задач."
        lines = [f"📋 У вас {len(tasks)} активных задач:"]
        for task in tasks[:5]:
            lines.append(f"  • {task.title}")
        return "\n".join(lines)
    
    elif parsed.intent == "help":
        return (
            "🤖 Я ваш умный помощник по управлению задачами!\n\n"
            "📝 УМЕЮ СОЗДАВАТЬ ЗАДАЧИ:\n"
            "• 'Купить молоко завтра в 10 утра'\n"
            "• 'Встреча с клиентом в пятницу 15:00'\n\n"
            "📋 УМЕЮ ПОКАЗЫВАТЬ ЗАДАЧИ:\n"
            "• 'мои задачи' - список всех активных задач\n"
            "• 'повестка' - расписание на сегодня\n\n"
            "✅ УМЕЮ ОТМЕЧАТЬ ВЫПОЛНЕНИЕ:\n"
            "• 'выполнил [название задачи]'"
        )
    
    else:
        return f"🤖 Обработано: {parsed.intent}\n📝 {parsed.title or text}"


async def interactive_demo():
    """Run the interactive demo."""
    print_header()
    
    context_mgr = ConversationContext()
    
    while True:
        try:
            # Get user input with proper encoding handling
            try:
                text = input("\n[Enter message] ")
            except EOFError:
                print("\nGoodbye!")
                break
            
            text = text.strip()
            
            if not text:
                continue
            
            # Handle commands
            if text.lower() in ("quit", "exit", "q"):
                print("\nGoodbye!")
                break
            
            if text.lower() in ("help", "?"):
                print_header()
                continue
            
            if text.lower() == "clear":
                await context_mgr.clear_context(TEST_PHONE)
                print("Context cleared.")
                continue
            
            if text.lower() == "remind":
                # Manually send due reminders
                db = SessionLocal()
                try:
                    reminder_service = ReminderService(db)
                    count = reminder_service.send_due_reminders_now()
                    print(f"Sent {count} reminders.")
                finally:
                    db.close()
                continue
            
            # Check for pending clarification
            pending = await context_mgr.get_context(TEST_PHONE)
            if pending and pending.get("pending_clarification"):
                response = await _generate_confirmation(
                    type('Parsed', (), {'intent': 'create_task', 'title': '', 'description': ''})(),
                    type('User', (), {'id': TEST_PHONE, 'timezone': 'Asia/Almaty'})(),
                    pending, text,
                    NLPPipeline(),
                    SessionLocal(),
                    send_reminders=False
                )
                print_message(response, "Assistant")
                await _send_whatsapp_response(TEST_PHONE, response)
                await context_mgr.clear_context(TEST_PHONE)
                continue
            
            # Process the message
            print_message(text, "User")
            result = await process_message(text)
            
            # Print result
            if result["status"] == "error":
                print_message(f"❌ Error: {result['error']}", "Assistant")
            else:
                print_message(result.get("confirmation", f"Intent: {result['intent']}"), "Assistant")
                    
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


def main():
    """Main entry point."""
    asyncio.run(interactive_demo())


if __name__ == "__main__":
    main()