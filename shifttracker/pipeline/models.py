from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from uuid import UUID


@dataclass
class IdentificationResult:
    employee_id: UUID
    employee_name: str
    method: str  # "telegram_account", "caption_exact", "caption_keyword", "group_fallback"
    confidence: str  # "HIGH", "MEDIUM", "LOW"


@dataclass
class ProcessingContext:
    update_id: int
    message_id: int
    chat_id: int
    sender_user_id: Optional[int]
    caption: Optional[str]
    message_datetime: datetime
    group_id: Optional[UUID] = None
    group_timezone: str = "Europe/Moscow"
    shift_start_hour: int = 6
    shift_end_hour: int = 22
    identifications: list[IdentificationResult] = field(default_factory=list)
    resolved_shift_date: Optional[date] = None
    status: str = "RECEIVED"
    reason: Optional[str] = None
    source_link: Optional[str] = None
