#!/usr/bin/env python3
"""CLI tool for calling task summaries."""
import argparse
import json
import sys
from datetime import datetime, date

# Add parent directory to path
sys.path.insert(0, '/Users/kajyrkeldi_sagitzan/Downloads/Rustam 2')

from app.services.agenda_service import AgendaService


def print_day_summary(user_id: str, target_date: date = None):
    """Print daily summary to console."""
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


def print_week_summary(user_id: str, pivot_date: date = None):
    """Print weekly summary to console."""
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


def print_month_summary(user_id: str, pivot_date: date = None):
    """Print monthly summary to console."""
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task Summary CLI")
    parser.add_argument("user_id", help="User ID (UUID)")
    parser.add_argument("--day", action="store_true", help="Show daily summary")
    parser.add_argument("--week", action="store_true", help="Show weekly summary")
    parser.add_argument("--month", action="store_true", help="Show monthly summary")
    parser.add_argument("--date", help="Target date (YYYY-MM-DD), defaults to today")
    
    args = parser.parse_args()
    
    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    
    # If no flag specified, show all summaries
    if not (args.day or args.week or args.month):
        args.day = args.week = args.month = True
    
    if args.day:
        print_day_summary(args.user_id, target_date)
    if args.week:
        print_week_summary(args.user_id, target_date)
    if args.month:
        print_month_summary(args.user_id, target_date)
