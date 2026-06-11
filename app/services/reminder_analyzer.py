import re
from dataclasses import dataclass
from datetime import datetime as DateTime, timedelta, timezone
from typing import Union, Optional

from app.core.time import now_utc, resolve_timezone


@dataclass
class ReminderAnalysis:
    """Result of analyzing a reminder message."""
    reminder_text: str
    reminder_type: str  # "relative" or "absolute"
    notification_time: Optional[str]  # ISO format for absolute, relative format for relative
    offset_minutes: int
    confidence: float
    event_time: Optional[str] = None  # ISO format for the event time (when offset is used with absolute time)


class ReminderAnalyzer:
    """Analyzes user messages to extract reminder information."""
    
    # Time unit mappings to minutes
    TIME_UNITS = {
        'минута': 1, 'минуты': 1, 'минуту': 1, 'минут': 1,
        'час': 60, 'часа': 60, 'часов': 60,
        'день': 1440, 'дня': 1440, 'дней': 1440,
        'неделю': 10080, 'недели': 10080, 'недель': 10080,
    }
    
    # Fractional time mappings
    FRACTIONAL_TIME = {
        'полчаса': 30,
        'полтора часа': 90,
        'полдня': 720,
    }
    
    # Day names mapping
    DAYS_RU = {
        'понедельник': 0, 'вторник': 1, 'среда': 2, 'четверг': 3,
        'пятница': 4, 'суббота': 5, 'воскресенье': 6,
    }
    
    # Month names mapping
    MONTHS_RU = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
    }
    
    def analyze(self, text: str) -> ReminderAnalysis:
        """Analyze a reminder message and extract structured data."""
        text_lower = text.lower().strip()
        
        # Extract the reminder text (action/event)
        reminder_text = self._extract_reminder_text(text)
        
        # Check for two explicit times pattern first (e.g., "в 11 00 сходить в магазин, уведоми в 9 30")
        two_times_result = self._extract_two_times_pattern(text_lower)
        if two_times_result:
            return ReminderAnalysis(
                reminder_text=reminder_text,
                reminder_type="absolute",
                notification_time=two_times_result["notification_time"],
                offset_minutes=two_times_result["offset_minutes"],
                confidence=0.98,
                event_time=two_times_result["event_time"],
            )
        
        # Check for combined time+offset pattern (e.g., "в 8:30 сходить в магазин напомни за 15 минут")
        combined_result = self._extract_combined_time_and_offset(text_lower)
        if combined_result:
            return ReminderAnalysis(
                reminder_text=reminder_text,
                reminder_type="absolute",
                notification_time=combined_result["notification_time"],
                offset_minutes=combined_result["offset_minutes"],
                confidence=0.98,
                event_time=combined_result["event_time"],
            )
        
        # Check for "за X" pattern (offset before event)
        offset_result = self._extract_offset(text_lower)
        if offset_result:
            return ReminderAnalysis(
                reminder_text=reminder_text,
                reminder_type="relative",
                notification_time=None,
                offset_minutes=offset_result,
                confidence=0.95
            )
        
        # Check for "через X" or "спустя X" pattern (relative time from now)
        relative_result = self._extract_relative_time(text_lower)
        if relative_result:
            return ReminderAnalysis(
                reminder_text=reminder_text,
                reminder_type="relative",
                notification_time=relative_result,
                offset_minutes=0,
                confidence=0.99
            )
        
        # Check for absolute date/time
        absolute_result = self._extract_absolute_time(text_lower)
        if absolute_result:
            return ReminderAnalysis(
                reminder_text=reminder_text,
                reminder_type="absolute",
                notification_time=absolute_result,
                offset_minutes=0,
                confidence=0.97
            )
        
        # Default: no time found, use 30 minutes default
        return ReminderAnalysis(
            reminder_text=reminder_text,
            reminder_type="relative",
            notification_time="30m",
            offset_minutes=0,
            confidence=0.8
        )
    
    def _extract_reminder_text(self, text: str) -> str:
        """Extract the reminder text (action/event) from the message."""
        text_lower = text.lower()
        
        # Remove common prefixes
        prefixes = [
            'напомни', 'напомнить', 'уведоми', 'уведомить',
            'remind', 'notify', 'напоминание', 'уведомление'
        ]
        
        for prefix in prefixes:
            if text_lower.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        
        # Remove time patterns - more comprehensive
        time_patterns = [
            r'через\s+\d+\s*(минуту|минуты|минут|час|часа|часов|день|дня|дней|неделю|недели|недель)',
            r'через\s+(полчаса|полтора\s+часа|полдня)',
            r'за\s+\d+\s*(минуту|минуты|минут|час|часа|часов)',
            r'за\s+час',
            r'спустя\s+\d+\s*(минуту|минуты|минут|час|часа|часов|день|дня|дней)',
            r'завтра',
            r'послезавтра',
            r'через\s+\d+\s*дней?',
            r'через\s+\d+\s*недель?',
            r'через\s+неделю',
            r'через\s+две\s+недели',
            r'\d{1,2}\s*(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)',
            r'\d{1,2}\.\d{1,2}\.\d{4}',
            r'в\s+\d{1,2}:\d{2}',
            r'в\s+\d{1,2}\s+\d{2}',  # "в 11 00" pattern
            r'о\s+том',
            r'что\s+нужно\s+',
            r'до\s+',
        ]
        
        for pattern in time_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Remove reminder-related words from anywhere in the text (for combined patterns)
        reminder_words = [
            r'\bнапомни\b', r'\bнапомнить\b', r'\bуведоми\b', r'\bуведомить\b',
            r'\bremind\b', r'\bnotify\b', r'\bнапоминание\b', r'\bуведомление\b'
        ]
        for word in reminder_words:
            text = re.sub(word, '', text, flags=re.IGNORECASE)
        
        # Clean up the text
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove leading prepositions and conjunctions
        text = re.sub(r'^[\sо,чтоа]+', '', text)
        
        return text if text else "напоминание"
    
    def _extract_offset(self, text: str) -> Optional[int]:
        """Extract offset minutes from 'за X' pattern."""
        # Pattern: "за X минут/часов" before an event
        match = re.search(r'за\s+(\d+)\s*(минуту|минуты|минут|час|часа|часов)', text)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            return value * self.TIME_UNITS.get(unit, 1)
        
        # Pattern: "за час" (without number)
        if re.search(r'за\s+час', text):
            return 60
        
        return None
    
    def _extract_relative_time(self, text: str) -> Optional[str]:
        """Extract relative time from 'через X' or 'спустя X' pattern."""
        # Pattern: "через X минут/часов/дней/недель"
        match = re.search(r'через\s+(\d+)\s*(минуту|минуты|минут|час|часа|часов|день|дня|дней|неделю|недели|недель)', text)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            minutes = value * self.TIME_UNITS.get(unit, 1)
            return self._format_relative_time(minutes)
        
        # Pattern: "спустя X"
        match = re.search(r'спустя\s+(\d+)\s*(минуту|минуты|минут|час|часа|часов|день|дня|дней|неделю|недели|недель)', text)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            minutes = value * self.TIME_UNITS.get(unit, 1)
            return self._format_relative_time(minutes)
        
        # Pattern: "через полчаса"
        if 'через полчаса' in text:
            return "30m"
        
        # Pattern: "через полтора часа"
        if 'через полтора часа' in text:
            return "1.5h"
        
        # Pattern: "через час"
        if re.search(r'через\s+час', text):
            return "1h"
        
        # Pattern: "через 2 часа" etc.
        match = re.search(r'через\s+(\d+)\s*час', text)
        if match:
            return f"{match.group(1)}h"
        
        # Pattern: "через 5 минут"
        match = re.search(r'через\s+(\d+)\s*минут', text)
        if match:
            return f"{match.group(1)}m"
        
        # Pattern: "через неделю"
        if 'через неделю' in text:
            return "168h"  # 1 week = 168 hours
        
        # Pattern: "через две недели"
        if 'через две недели' in text:
            return "336h"  # 2 weeks = 336 hours
        
        return None
    
    def _extract_absolute_time(self, text: str) -> Optional[str]:
        """Extract absolute date/time in UTC."""
        now = now_utc().astimezone(resolve_timezone("Asia/Almaty"))
        
        # Pattern: "завтра в HH:MM"
        match = re.search(r'завтра\s+в\s+(\d{1,2}):(\d{2})', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            target = now + timedelta(days=1)
            target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        
        # Pattern: "завтра" (default to 9:00)
        if 'завтра' in text and not re.search(r'в\s+\d{1,2}:\d{2}', text):
            target = now + timedelta(days=1)
            target = target.replace(hour=9, minute=0, second=0, microsecond=0)
            return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        
        # Pattern: "послезавтра"
        if 'послезавтра' in text:
            target = now + timedelta(days=2)
            target = target.replace(hour=9, minute=0, second=0, microsecond=0)
            return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        
        # Pattern: "через N дней" - this is relative, not absolute
        # We should NOT return absolute time for this
        
        # Pattern: "через неделю" / "через две недели" - this is relative, not absolute
        # We should NOT return absolute time for this
        
        # Pattern: "DD month YYYY в HH:MM" or "DD month в HH:MM"
        for month_name, month_num in self.MONTHS_RU.items():
            match = re.search(rf'(\d{{1,2}})\s+{month_name}(?:\s+(\d{{4}}))?(?:\s+в\s+(\d{{1,2}}):(\d{{2}}))?', text)
            if match:
                day = int(match.group(1))
                year = int(match.group(2)) if match.group(2) else now.year
                hour = int(match.group(3)) if match.group(3) else 9
                minute = int(match.group(4)) if match.group(4) else 0
                
                try:
                    target = now.replace(year=year, month=month_num, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    pass
        
        # Pattern: "DD.MM.YYYY" or "DD.MM.YYYY в HH:MM"
        match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+в\s+(\d{1,2}):(\d{2}))?', text)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            hour = int(match.group(4)) if match.group(4) else 9
            minute = int(match.group(5)) if match.group(5) else 0
            
            try:
                target = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                return target.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass
        
        return None
    
    def _extract_combined_time_and_offset(self, text: str) -> Optional[dict]:
        """
        Extract combined time+offset pattern.
        Example: "в 8:30 сходить в магазин напомни за 15 минут"
        Returns notification_time (event_time - offset) and event_time in UTC.
        """
        now = now_utc().astimezone(resolve_timezone("Asia/Almaty"))
        
        # First, check if there's an offset pattern
        offset_minutes = self._extract_offset(text)
        if not offset_minutes:
            return None
        
        # Check for "DD.MM.YYYY в HH:MM" pattern with offset (most specific)
        match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})\s+в\s+(\d{1,2}):(\d{2})', text)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            hour = int(match.group(4))
            minute = int(match.group(5))
            
            try:
                event_time = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                notification_time = event_time - timedelta(minutes=offset_minutes)
                # Convert to UTC for consistent parsing
                return {
                    "notification_time": notification_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                    "offset_minutes": offset_minutes,
                    "event_time": event_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                }
            except ValueError:
                pass
        
        # Check for "DD month в HH:MM" pattern with offset
        for month_name, month_num in self.MONTHS_RU.items():
            match = re.search(rf'(\d{{1,2}})\s+{month_name}(?:\s+(\d{{4}}))?\s+в\s+(\d{{1,2}}):(\d{{2}})', text)
            if match:
                day = int(match.group(1))
                year = int(match.group(2)) if match.group(2) else now.year
                hour = int(match.group(3))
                minute = int(match.group(4))
                
                try:
                    event_time = now.replace(year=year, month=month_num, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    notification_time = event_time - timedelta(minutes=offset_minutes)
                    # Convert to UTC for consistent parsing
                    return {
                        "notification_time": notification_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                        "offset_minutes": offset_minutes,
                        "event_time": event_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                except ValueError:
                    pass
        
        # Check for "завтра в HH:MM" pattern with offset
        match = re.search(r'завтра\s+в\s+(\d{1,2}):(\d{2})', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            event_time = now + timedelta(days=1)
            event_time = event_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            notification_time = event_time - timedelta(minutes=offset_minutes)
            # Convert to UTC for consistent parsing
            return {
                "notification_time": notification_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "offset_minutes": offset_minutes,
                "event_time": event_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            }
        
        # Check for "в HH:MM" pattern (time today) - least specific
        match = re.search(r'в\s+(\d{1,2}):(\d{2})', text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            # Use today's date
            event_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # If the time has already passed today, assume it's for tomorrow
            if event_time < now:
                event_time = event_time + timedelta(days=1)
            
            notification_time = event_time - timedelta(minutes=offset_minutes)
            # Convert to UTC for consistent parsing
            return {
                "notification_time": notification_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "offset_minutes": offset_minutes,
                "event_time": event_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            }
        
        return None
    
    def _extract_two_times_pattern(self, text: str) -> Optional[dict]:
        """
        Extract pattern with two explicit times.
        Example: "в 11 00 сходить в магазин, уведоми в 9 30"
        Returns notification_time and event_time in UTC.
        """
        now = now_utc().astimezone(resolve_timezone("Asia/Almaty"))
        
        # Pattern: "в HH MM ... уведоми/напомни в HH MM"
        # This matches "в 11 00 ... уведоми в 9 30"
        match = re.search(r'в\s+(\d{1,2})\s+(\d{2}).*?(?:уведоми|напомни)\s+в\s+(\d{1,2})\s+(\d{2})', text)
        if match:
            event_hour, event_minute = int(match.group(1)), int(match.group(2))
            notify_hour, notify_minute = int(match.group(3)), int(match.group(4))
            
            # Create event time - use tomorrow if time has passed
            event_time = now.replace(hour=event_hour, minute=event_minute, second=0, microsecond=0)
            if event_time < now:
                event_time = event_time + timedelta(days=1)
            
            # Create notification time - should be on the same day as event
            # If notification time is before event time, use same day
            # If notification time is after event time, use previous day
            notification_time = now.replace(hour=notify_hour, minute=notify_minute, second=0, microsecond=0)
            
            # If notification time is after event time on the same day, 
            # the notification should be the day before
            if notification_time >= event_time:
                notification_time = notification_time - timedelta(days=1)
            elif notification_time < now and notification_time + timedelta(days=1) < event_time:
                # If notification time has passed and next day is still before event, use next day
                notification_time = notification_time + timedelta(days=1)
            
            # Calculate offset (should be positive)
            offset_minutes = int((event_time - notification_time).total_seconds() / 60)
            
            # Convert to UTC for consistent parsing
            return {
                "notification_time": notification_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                "offset_minutes": offset_minutes,
                "event_time": event_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            }
        
        return None
    
    def _format_relative_time(self, minutes: int) -> str:
        """Format minutes into relative time string."""
        if minutes < 60:
            return f"{minutes}m"
        elif minutes == 60:
            return "1h"
        elif minutes % 60 == 0:
            return f"{minutes // 60}h"
        else:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}h{mins}m"