import re
from datetime import time

from sqlalchemy.orm import Session

from app.models import RoutineBlock
from app.schemas import OnboardingRequest
from app.services.normalization import normalize_routine_type


DAY_ALIASES = {
    "segunda": 0,
    "seg": 0,
    "terça": 1,
    "terca": 1,
    "ter": 1,
    "quarta": 2,
    "qua": 2,
    "quinta": 3,
    "qui": 3,
    "sexta": 4,
    "sex": 4,
    "sábado": 5,
    "sabado": 5,
    "sab": 5,
    "domingo": 6,
    "dom": 6,
}


def persist_onboarding_routine(user_id: int, payload: OnboardingRequest, db: Session) -> int:
    created = 0
    specs = [
        ("Escola", "school", payload.school_schedule),
        ("Cursinho", "course", payload.cursinho_schedule),
        ("Sono", "sleep", payload.sleep_schedule),
    ]
    for title, block_type, raw_text in specs:
        for block in parse_schedule_text(raw_text, title, block_type):
            db.add(RoutineBlock(user_id=user_id, **block))
            created += 1

    transport_minutes = _extract_minutes(payload.transport_time)
    if transport_minutes:
        for weekday in range(5):
            db.add(
                RoutineBlock(
                    user_id=user_id,
                    title="Transporte médio",
                    block_type="transport",
                    type="transport",
                    weekday=weekday,
                    day_of_week=weekday,
                    start_time=time(18, 0),
                    end_time=_add_minutes(time(18, 0), min(transport_minutes, 120)),
                    recurrence="weekly",
                    notes=payload.transport_time,
                    description=f"Tempo médio informado no onboarding: {payload.transport_time}",
                )
            )
            created += 1

    free_minutes = _extract_hours_as_minutes(payload.free_hours_per_day)
    if free_minutes:
        duration = min(max(free_minutes, 45), 120)
        for weekday in range(5):
            db.add(
                RoutineBlock(
                    user_id=user_id,
                    title="Janela livre de estudo",
                    block_type="study_window",
                    type="study_window",
                    weekday=weekday,
                    day_of_week=weekday,
                    start_time=time(19, 0),
                    end_time=_add_minutes(time(19, 0), duration),
                    recurrence="weekly",
                    notes=payload.free_hours_per_day,
                    description=f"Janela inicial estimada a partir do tempo livre informado: {payload.free_hours_per_day}",
                )
            )
            created += 1
    db.flush()
    return created


def parse_schedule_text(raw_text: str | None, title: str, block_type: str) -> list[dict[str, object]]:
    text = (raw_text or "").strip()
    if not text:
        return []
    normalized_type = normalize_routine_type(block_type)
    time_ranges = _extract_time_ranges(text)
    if not time_ranges:
        return []
    weekdays = _extract_weekdays(text) or list(range(5))
    blocks = []
    for weekday in weekdays:
        for start, end in time_ranges:
            if end <= start:
                end = time(23, 59)
            blocks.append(
                {
                    "title": title,
                    "block_type": normalized_type,
                    "type": normalized_type,
                    "weekday": weekday,
                    "day_of_week": weekday,
                    "start_time": start,
                    "end_time": end,
                    "recurrence": "weekly",
                    "notes": text,
                    "description": text,
                }
            )
    return blocks


def _extract_weekdays(text: str) -> list[int]:
    lower = text.lower()
    if "segunda a sexta" in lower or "seg a sex" in lower or "segunda à sexta" in lower:
        return list(range(5))
    found = []
    for alias, value in DAY_ALIASES.items():
        if alias in lower and value not in found:
            found.append(value)
    return sorted(found)


def _extract_time_ranges(text: str) -> list[tuple[time, time]]:
    ranges = []
    pattern = re.compile(r"(\d{1,2})(?::|h)?(\d{2})?\s*(?:-|às|as|a)\s*(\d{1,2})(?::|h)?(\d{2})?", re.IGNORECASE)
    for match in pattern.finditer(text):
        start = _time_from_match(match.group(1), match.group(2))
        end = _time_from_match(match.group(3), match.group(4))
        if start and end:
            ranges.append((start, end))
    return ranges[:4]


def _time_from_match(hour_text: str, minute_text: str | None) -> time | None:
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour, minute)
    return None


def _extract_minutes(text: str | None) -> int:
    value = (text or "").lower()
    if not value:
        return 0
    number = re.search(r"\d+", value)
    if not number:
        return 0
    amount = int(number.group())
    if "hora" in value or "h" in value:
        return amount * 60
    return amount


def _extract_hours_as_minutes(text: str | None) -> int:
    value = (text or "").lower()
    number = re.search(r"\d+(?:[,.]\d+)?", value)
    if not number:
        return 0
    hours = float(number.group().replace(",", "."))
    return int(hours * 60)


def _add_minutes(start: time, minutes: int) -> time:
    total = start.hour * 60 + start.minute + minutes
    total = min(total, 23 * 60 + 59)
    return time(total // 60, total % 60)
