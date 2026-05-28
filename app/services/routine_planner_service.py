import re
from datetime import datetime, timedelta, time


DAY_MAP = {
    "segunda": 0,
    "seg": 0,
    "terca": 1,
    "terça": 1,
    "ter": 1,
    "quarta": 2,
    "qua": 2,
    "quinta": 3,
    "qui": 3,
    "sexta": 4,
    "sex": 4,
    "sabado": 5,
    "sábado": 5,
    "sab": 5,
    "domingo": 6,
    "dom": 6,
}

PERIOD_HINTS = {
    "manha": time(7, 0),
    "manhã": time(7, 0),
    "tarde": time(14, 0),
    "noite": time(19, 0),
    "madrugada": time(5, 30),
}


def suggest_routine_blocks(message: str) -> list[dict[str, object]]:
    text = " ".join((message or "").strip().split())
    if len(text) < 3:
        return []

    weekdays = _extract_weekdays(text)
    if not weekdays:
        weekdays = [0, 2, 4]

    duration = _extract_duration_minutes(text)
    start = _extract_start_time(text)

    suggestions = []
    for weekday in weekdays:
        end = _add_minutes(start, duration)
        suggestions.append(
            {
                "title": "Estudo guiado",
                "block_type": "study_window",
                "weekday": weekday,
                "start_time": start.strftime("%H:%M"),
                "end_time": end.strftime("%H:%M"),
                "recurrence": "weekly",
                "description": f"Sugestão automática a partir da frase: {text}",
            }
        )
    return suggestions


def _extract_weekdays(text: str) -> list[int]:
    normalized = text.lower()
    matches = []
    for token, weekday in DAY_MAP.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized) and weekday not in matches:
            matches.append(weekday)

    if "segunda a sexta" in normalized or "seg a sex" in normalized or "seg/ter/qua/qui/sex" in normalized:
        return [0, 1, 2, 3, 4]

    return sorted(matches)


def _extract_duration_minutes(text: str) -> int:
    normalized = text.lower().replace(",", ".")
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*h", normalized)
    if hour_match:
        hours = float(hour_match.group(1))
        return int(max(30, min(hours * 60, 240)))

    minute_match = re.search(r"(\d+)\s*min", normalized)
    if minute_match:
        return int(max(30, min(int(minute_match.group(1)), 240)))

    return 120


def _extract_start_time(text: str) -> time:
    normalized = text.lower().replace("às", "as")
    hour_match = re.search(r"as\s*(\d{1,2})(?::(\d{2}))?", normalized)
    if hour_match:
        hour = int(hour_match.group(1))
        minute = int(hour_match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)

    for hint, start in PERIOD_HINTS.items():
        if hint in normalized:
            return start

    return time(19, 0)


def _add_minutes(start: time, minutes: int) -> time:
    dt = datetime(2000, 1, 1, start.hour, start.minute) + timedelta(minutes=minutes)
    return dt.time()
