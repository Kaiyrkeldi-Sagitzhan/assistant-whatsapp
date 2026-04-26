from app.core.time import now_utc


class GoogleCalendarSync:
    def normalize_event_payload(self, payload: dict) -> dict:
        return {
            "external_event_id": payload.get("id", ""),
            "title": payload.get("summary", "Untitled"),
            "starts_at": payload.get("starts_at") or now_utc().isoformat(),
            "ends_at": payload.get("ends_at") or now_utc().isoformat(),
            "attendees_count": payload.get("attendees_count", 0),
        }
