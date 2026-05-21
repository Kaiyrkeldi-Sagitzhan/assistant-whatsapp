"""User-facing summary functions - easy to call for end users."""
from datetime import date
from typing import Optional

from app.services.agenda_service import AgendaService


def get_my_day_summary(user_id: str, target_date: Optional[date] = None) -> dict:
    """
    Get your daily summary - tasks only for today's date.
    
    Args:
        user_id: Your user ID (UUID string)
        target_date: Target date (defaults to today)
    
    Returns:
        Dictionary with date, day_of_week, tasks, and total_tasks
    
    Example:
        >>> summary = get_my_day_summary("user-uuid-here")
        >>> print(f"Today you have {summary['total_tasks']} tasks")
    """
    service = AgendaService()
    return service.get_day_summary(user_id, target_date)


def get_my_week_summary(user_id: str, pivot_date: Optional[date] = None) -> dict:
    """
    Get your weekly summary - tasks for the next 7 days, grouped by day.
    
    Each day shows: date, day_of_week, tasks list, and task_count.
    
    Args:
        user_id: Your user ID (UUID string)
        pivot_date: Start date (defaults to today)
    
    Returns:
        Dictionary with week_start, week_end, total_tasks, and days
    
    Example:
        >>> summary = get_my_week_summary("user-uuid-here")
        >>> for date_str, day in summary['days'].items():
        ...     print(f"{day['day_of_week']}: {day['task_count']} tasks")
    """
    service = AgendaService()
    return service.get_week_summary(user_id, pivot_date)


def get_my_month_summary(user_id: str, pivot_date: Optional[date] = None) -> dict:
    """
    Get your monthly summary - tasks grouped by 7-day weeks.
    
    Each week shows its period (start/end dates) and tasks within that period.
    
    Args:
        user_id: Your user ID (UUID string)
        pivot_date: Reference date to determine month (defaults to today)
    
    Returns:
        Dictionary with month, total_tasks, and weeks
    
    Example:
        >>> summary = get_my_month_summary("user-uuid-here")
        >>> print(f"This month: {summary['total_tasks']} tasks")
        >>> for week_name, week in summary['weeks'].items():
        ...     print(f"{week_name}: {week['task_count']} tasks")
    """
    service = AgendaService()
    return service.get_month_summary(user_id, pivot_date)


def print_my_day_summary(user_id: str, target_date: Optional[date] = None) -> None:
    """
    Print your daily summary in a readable format.
    
    Args:
        user_id: Your user ID (UUID string)
        target_date: Target date (defaults to today)
    """
    service = AgendaService()
    result = service.get_day_summary(user_id, target_date)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        return
    
    print(f"\n{'='*60}")
    print(f"📅 Daily Summary - {result['date']} ({result['day_of_week']})")
    print(f"{'='*60}")
    print(f"Total tasks: {result['total_tasks']}\n")
    
    for task in result['tasks']:
        print(f"  • [{task['priority'].upper()}] {task['title']}")
        if task['description']:
            print(f"    {task['description']}")
        if task['due_at']:
            print(f"    ⏰ Due: {task['due_at']}")
        print(f"    Status: {task['status']}")
        print()


def print_my_week_summary(user_id: str, pivot_date: Optional[date] = None) -> None:
    """
    Print your weekly summary in a readable format.
    
    Args:
        user_id: Your user ID (UUID string)
        pivot_date: Start date (defaults to today)
    """
    service = AgendaService()
    result = service.get_week_summary(user_id, pivot_date)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        return
    
    print(f"\n{'='*60}")
    print(f"📆 Weekly Summary - {result['week_start']} to {result['week_end']}")
    print(f"{'='*60}")
    print(f"Total tasks: {result['total_tasks']}\n")
    
    for date_str, day_info in result['days'].items():
        if day_info['task_count'] > 0:
            print(f"  {day_info['date']} - {day_info['day_of_week']} ({day_info['task_count']} tasks)")
            for task in day_info['tasks']:
                print(f"    • [{task['priority'].upper()}] {task['title']}")
                if task['description']:
                    print(f"      {task['description']}")
            print()


def print_my_month_summary(user_id: str, pivot_date: Optional[date] = None) -> None:
    """
    Print your monthly summary in a readable format.
    
    Args:
        user_id: Your user ID (UUID string)
        pivot_date: Reference date (defaults to today)
    """
    service = AgendaService()
    result = service.get_month_summary(user_id, pivot_date)
    
    if "error" in result:
        print(f"Error: {result['error']}")
        return
    
    print(f"\n{'='*60}")
    print(f"📅 Monthly Summary - {result['month']}")
    print(f"{'='*60}")
    print(f"Total tasks: {result['total_tasks']}\n")
    
    for week_key, week_info in result['weeks'].items():
        task_count = week_info['task_count']
        if task_count > 0:
            print(f"  {week_key}: {week_info['period']['start']} to {week_info['period']['end']} ({task_count} tasks)")
            for task in week_info['tasks']:
                print(f"    • [{task['priority'].upper()}] {task['title']} (Due: {task.get('due_date', 'N/A')})")
                if task['description']:
                    print(f"      {task['description']}")
            print()
