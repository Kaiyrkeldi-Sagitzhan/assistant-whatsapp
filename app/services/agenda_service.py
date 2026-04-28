from datetime import datetime as DateTime, timedelta
from typing import List, Dict, Any, Union
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.time import now_utc, resolve_timezone
from app.db.models import Task, TaskPriority, CalendarEvent, User
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class AgendaService:
    def __init__(self) -> None:
        pass

    def generate_daily_agenda(self, user_id: str, date: Union[DateTime, None] = None) -> Dict[str, Any]:
        """Generate daily agenda for user."""
        if date is None:
            date = now_utc()

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user:
                return {"error": "User not found"}

            timezone = user.timezone
            user_tz = resolve_timezone(timezone)

            # Convert date to user's timezone for day boundaries
            day_start_local = date.astimezone(user_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end_local = day_start_local + timedelta(days=1)

            # Convert back to UTC for database queries (since tasks are stored in UTC)
            from app.core.time import to_utc
            day_start_utc = to_utc(day_start_local, timezone)
            day_end_utc = to_utc(day_end_local, timezone)

            # Get tasks for today
            tasks_today = db.query(Task).filter(
                and_(
                    Task.user_id == user_id,
                    Task.is_completed == False,
                    or_(
                        and_(Task.due_at >= day_start_utc, Task.due_at < day_end_utc),
                        Task.due_at.is_(None)  # Tasks without due date
                    )
                )
            ).order_by(Task.priority.desc(), Task.created_at).all()

            # Get overdue tasks
            overdue_tasks = db.query(Task).filter(
                and_(
                    Task.user_id == user_id,
                    Task.is_completed == False,
                    Task.due_at < day_start_utc
                )
            ).order_by(Task.due_at).all()

            # Get calendar events for today
            calendar_events = db.query(CalendarEvent).filter(
                and_(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.starts_at >= day_start_utc,
                    CalendarEvent.starts_at < day_end_utc
                )
            ).order_by(CalendarEvent.starts_at).all()

            # Get free time slots (simplified - just show gaps between meetings)
            free_slots = self._calculate_free_slots(calendar_events, day_start, day_end)

            return {
                "date": day_start_local.isoformat(),
                "meetings": [
                    {
                        "title": event.title,
                        "start": event.starts_at.astimezone(user_tz).strftime("%H:%M"),
                        "end": event.ends_at.astimezone(user_tz).strftime("%H:%M"),
                        "duration": f"{(event.ends_at - event.starts_at).seconds // 3600}h"
                    }
                    for event in calendar_events
                ],
                "tasks_today": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "priority": task.priority.value,
                        "due_time": task.due_at.astimezone(user_tz).strftime("%H:%M") if task.due_at else None,
                        "overdue": task.due_at and task.due_at < now_utc()
                    }
                    for task in tasks_today
                ],
                "overdue_tasks": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "days_overdue": (now_utc() - task.due_at).days if task.due_at else 0
                    }
                    for task in overdue_tasks[:5]  # Limit to 5
                ],
                "free_slots": free_slots,
                "workload_level": self._calculate_workload_level(len(tasks_today), len(calendar_events))
            }

        finally:
            db.close()

    def generate_weekly_plan(self, user_id: str, start_date: Union[DateTime, None] = None) -> Dict[str, Any]:
        """Generate weekly plan for user."""
        if start_date is None:
            start_date = now_utc()

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user:
                return {"error": "User not found"}

            timezone = user.timezone
            user_tz = resolve_timezone(timezone)

            # Get week boundaries in local timezone
            week_start_local = start_date.astimezone(user_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            # Find Monday of the week
            monday_offset = week_start_local.weekday()  # 0=Monday, 6=Sunday
            week_start_local = week_start_local - timedelta(days=monday_offset)
            week_end_local = week_start_local + timedelta(days=7)

            # Convert back to UTC for database queries
            from app.core.time import to_utc
            week_start_utc = to_utc(week_start_local, timezone)
            week_end_utc = to_utc(week_end_local, timezone)

            # Get all tasks for the week
            tasks_week = db.query(Task).filter(
                and_(
                    Task.user_id == user_id,
                    not Task.is_completed,
                    or_(
                        and_(Task.due_at >= week_start_utc, Task.due_at < week_end_utc),
                        Task.due_at.is_(None)
                    )
                )
            ).order_by(Task.priority.desc(), Task.due_at).all()

            # Get calendar events for the week
            calendar_events = db.query(CalendarEvent).filter(
                and_(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.starts_at >= week_start_utc,
                    CalendarEvent.starts_at < week_end_utc
                )
            ).order_by(CalendarEvent.starts_at).all()

            # Group by days (use local dates for grouping)
            daily_breakdown = {}
            for i in range(7):
                day_date_local = week_start_local + timedelta(days=i)
                day_name = day_date_local.strftime("%A")

                # Convert local date to UTC date for filtering
                day_start_utc = to_utc(day_date_local, timezone)
                day_end_utc = to_utc(day_date_local + timedelta(days=1), timezone)

                day_tasks = [t for t in tasks_week if t.due_at and day_start_utc <= t.due_at < day_end_utc]
                day_events = [e for e in calendar_events if e.starts_at and day_start_utc <= e.starts_at < day_end_utc]

                daily_breakdown[day_name] = {
                    "date": day_date_local.isoformat(),
                    "tasks_count": len(day_tasks),
                    "meetings_count": len(day_events),
                    "high_priority_tasks": len([t for t in day_tasks if t.priority == TaskPriority.HIGH]),
                    "overloaded": len(day_events) > 4  # More than 4 meetings = overloaded
                }

            # Calculate weekly metrics
            total_tasks = len(tasks_week)
            high_priority = len([t for t in tasks_week if t.priority == TaskPriority.HIGH])
            total_meetings = len(calendar_events)
            avg_daily_load = total_meetings / 7

            return {
                "week_start": week_start_local.isoformat(),
                "week_end": week_end_local.isoformat(),
                "summary": {
                    "total_tasks": total_tasks,
                    "high_priority_tasks": high_priority,
                    "total_meetings": total_meetings,
                    "avg_daily_meetings": round(avg_daily_load, 1),
                    "overloaded_days": len([d for d in daily_breakdown.values() if d["overloaded"]])
                },
                "daily_breakdown": daily_breakdown,
                "recommendations": self._generate_weekly_recommendations(daily_breakdown, total_tasks)
            }

        finally:
            db.close()

    def _calculate_free_slots(self, events: List[CalendarEvent], day_start: DateTime, day_end: DateTime) -> List[Dict[str, str]]:
        """Calculate free time slots between meetings."""
        if not events:
            return [{"start": "09:00", "end": "18:00", "duration": "9h"}]

        free_slots = []
        work_start = day_start.replace(hour=9, minute=0)
        work_end = day_start.replace(hour=18, minute=0)

        # Sort events by start time
        sorted_events = sorted(events, key=lambda e: e.starts_at)

        # Check morning free time
        if sorted_events and sorted_events[0].starts_at > work_start:
            duration = sorted_events[0].starts_at - work_start
            if duration.seconds >= 3600:  # At least 1 hour
                free_slots.append({
                    "start": work_start.strftime("%H:%M"),
                    "end": sorted_events[0].starts_at.strftime("%H:%M"),
                    "duration": f"{duration.seconds // 3600}h"
                })

        # Check gaps between meetings
        for i in range(len(sorted_events) - 1):
            gap_start = sorted_events[i].ends_at
            gap_end = sorted_events[i + 1].starts_at
            duration = gap_end - gap_start

            if duration.seconds >= 3600:  # At least 1 hour
                free_slots.append({
                    "start": gap_start.strftime("%H:%M"),
                    "end": gap_end.strftime("%H:%M"),
                    "duration": f"{duration.seconds // 3600}h"
                })

        # Check afternoon free time
        if sorted_events and sorted_events[-1].ends_at < work_end:
            duration = work_end - sorted_events[-1].ends_at
            if duration.seconds >= 3600:
                free_slots.append({
                    "start": sorted_events[-1].ends_at.strftime("%H:%M"),
                    "end": work_end.strftime("%H:%M"),
                    "duration": f"{duration.seconds // 3600}h"
                })

        return free_slots[:3]  # Limit to 3 slots

    def _calculate_workload_level(self, tasks_count: int, meetings_count: int) -> str:
        """Calculate workload level based on tasks and meetings."""
        total_load = tasks_count + (meetings_count * 2)  # Meetings count double

        if total_load <= 3:
            return "light"
        elif total_load <= 6:
            return "moderate"
        elif total_load <= 10:
            return "heavy"
        else:
            return "overloaded"

    def _generate_weekly_recommendations(self, daily_breakdown: Dict, total_tasks: int) -> List[str]:
        """Generate recommendations for the week."""
        recommendations = []

        overloaded_days = [day for day, data in daily_breakdown.items() if data["overloaded"]]
        if overloaded_days:
            recommendations.append(f"⚠️ Перегруженные дни: {', '.join(overloaded_days)}. Рассмотрите перенос встреч.")

        light_days = [day for day, data in daily_breakdown.items() if data["meetings_count"] <= 2]
        if light_days and total_tasks > 5:
            recommendations.append(f"💡 Легкие дни для работы над задачами: {', '.join(light_days[:2])}")

        if total_tasks > 10:
            recommendations.append("📋 Большое количество задач. Рекомендую фокус на 3-5 наиболее важных.")

        high_priority_days = [(day, data["high_priority_tasks"]) for day, data in daily_breakdown.items()
                            if data["high_priority_tasks"] > 0]
        if high_priority_days:
            priority_days = [day for day, count in high_priority_days if count > 0]
            recommendations.append(f"🔥 Дни с приоритетными задачами: {', '.join(priority_days)}")

        return recommendations

    def get_day_summary(self, user_id: str, target_date: Union[DateTime, None] = None) -> Dict[str, Any]:
        """Get daily summary - tasks only for today's date."""
        if target_date is None:
            target_date = now_utc()

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user:
                return {"error": "User not found"}

            timezone = user.timezone
            user_tz = resolve_timezone(timezone)

            # Convert date to user's timezone for day boundaries
            day_start_local = target_date.astimezone(user_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end_local = day_start_local + timedelta(days=1)

            from app.core.time import to_utc
            day_start_utc = to_utc(day_start_local, timezone)
            day_end_utc = to_utc(day_end_local, timezone)

            # Get tasks for today only (not including tasks without due date)
            tasks_today = db.query(Task).filter(
                and_(
                    Task.user_id == user_id,
                    Task.is_completed == False,
                    Task.due_at >= day_start_utc,
                    Task.due_at < day_end_utc
                )
            ).order_by(Task.priority.desc(), Task.due_at).all()

            day_name = day_start_local.strftime("%A")

            return {
                "date": day_start_local.strftime("%Y-%m-%d"),
                "day_of_week": day_name,
                "tasks": [
                    {
                        "id": str(task.id),
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority.value,
                        "status": task.status.value,
                        "due_at": task.due_at.astimezone(user_tz).isoformat() if task.due_at else None,
                        "created_at": task.created_at.astimezone(user_tz).isoformat() if task.created_at else None
                    }
                    for task in tasks_today
                ],
                "total_tasks": len(tasks_today)
            }
        finally:
            db.close()

    def get_week_summary(self, user_id: str, pivot_date: Union[DateTime, None] = None) -> Dict[str, Any]:
        """Get weekly summary - tasks for the next 7 days, grouped by day with date and day of week."""
        if pivot_date is None:
            pivot_date = now_utc()

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user:
                return {"error": "User not found"}

            timezone = user.timezone
            user_tz = resolve_timezone(timezone)

            # Get week boundaries in local timezone (starting from pivot_date)
            week_start_local = pivot_date.astimezone(user_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            week_end_local = week_start_local + timedelta(days=7)

            from app.core.time import to_utc
            week_start_utc = to_utc(week_start_local, timezone)
            week_end_utc = to_utc(week_end_local, timezone)

            # Get all tasks for the week (excluding completed tasks)
            tasks_week = db.query(Task).filter(
                and_(
                    Task.user_id == user_id,
                    Task.is_completed == False,
                    Task.due_at >= week_start_utc,
                    Task.due_at < week_end_utc
                )
            ).order_by(Task.priority.desc(), Task.due_at).all()

            # Group tasks by day
            daily_tasks = {}
            for i in range(7):
                day_date_local = week_start_local + timedelta(days=i)
                day_name = day_date_local.strftime("%A")
                date_str = day_date_local.strftime("%Y-%m-%d")

                day_start_utc = to_utc(day_date_local, timezone)
                day_end_utc = to_utc(day_date_local + timedelta(days=1), timezone)

                day_task_list = [
                    {
                        "id": str(task.id),
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority.value,
                        "status": task.status.value,
                        "due_at": task.due_at.astimezone(user_tz).isoformat() if task.due_at else None
                    }
                    for task in tasks_week
                    if day_start_utc <= task.due_at < day_end_utc
                ]

                daily_tasks[date_str] = {
                    "date": date_str,
                    "day_of_week": day_name,
                    "tasks": day_task_list,
                    "task_count": len(day_task_list)
                }

            total_tasks = len(tasks_week)

            return {
                "week_start": week_start_local.strftime("%Y-%m-%d"),
                "week_end": (week_end_local - timedelta(days=1)).strftime("%Y-%m-%d"),
                "total_tasks": total_tasks,
                "days": daily_tasks
            }
        finally:
            db.close()

    def get_month_summary(self, user_id: str, pivot_date: Union[DateTime, None] = None) -> Dict[str, Any]:
        """Get monthly summary - tasks grouped by 7-day weeks."""
        if pivot_date is None:
            pivot_date = now_utc()

        db = SessionLocal()
        try:
            user = db.get(User, user_id)
            if not user:
                return {"error": "User not found"}

            timezone = user.timezone
            user_tz = resolve_timezone(timezone)

            # Get month boundaries in local timezone
            month_start_local = pivot_date.astimezone(user_tz).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            # Calculate next month
            if month_start_local.month == 12:
                month_end_local = month_start_local.replace(year=month_start_local.year + 1, month=1)
            else:
                month_end_local = month_start_local.replace(month=month_start_local.month + 1)

            from app.core.time import to_utc
            month_start_utc = to_utc(month_start_local, timezone)
            month_end_utc = to_utc(month_end_local, timezone)

            # Get all tasks for the month (excluding completed tasks)
            tasks_month = db.query(Task).filter(
                and_(
                    Task.user_id == user_id,
                    Task.is_completed == False,
                    Task.due_at >= month_start_utc,
                    Task.due_at < month_end_utc
                )
            ).order_by(Task.priority.desc(), Task.due_at).all()

            # Group tasks by 7-day weeks
            weeks = {}
            current_week_start = month_start_local
            week_num = 1

            while current_week_start < month_end_local:
                week_end_local = current_week_start + timedelta(days=7)

                week_start_utc = to_utc(current_week_start, timezone)
                week_end_utc_calc = to_utc(week_end_local, timezone)

                week_tasks = [
                    {
                        "id": str(task.id),
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority.value,
                        "status": task.status.value,
                        "due_at": task.due_at.astimezone(user_tz).isoformat() if task.due_at else None,
                        "due_date": task.due_at.astimezone(user_tz).strftime("%Y-%m-%d") if task.due_at else None
                    }
                    for task in tasks_month
                    if week_start_utc <= task.due_at < week_end_utc_calc
                ]

                weeks[f"week_{week_num}"] = {
                    "period": {
                        "start": current_week_start.strftime("%Y-%m-%d"),
                        "end": (week_end_local - timedelta(days=1)).strftime("%Y-%m-%d")
                    },
                    "tasks": week_tasks,
                    "task_count": len(week_tasks)
                }

                current_week_start = week_end_local
                week_num += 1

            total_tasks = len(tasks_month)

            return {
                "month": month_start_local.strftime("%Y-%m"),
                "total_tasks": total_tasks,
                "weeks": weeks
            }
        finally:
            db.close()
