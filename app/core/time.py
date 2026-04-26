from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def resolve_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def local_day_bounds_utc(target_date: date, timezone_name: str) -> tuple[datetime, datetime]:
    tz = resolve_timezone(timezone_name)
    local_start = datetime.combine(target_date, time.min, tzinfo=tz)
    local_end = datetime.combine(target_date, time.max, tzinfo=tz)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def to_utc(dt: datetime, default_timezone: str) -> datetime:
    if dt.tzinfo is None:
        local_tz = resolve_timezone(default_timezone)
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)