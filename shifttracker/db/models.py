import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group_bindings: Mapped[list["GroupEmployee"]] = relationship(back_populates="employee")
    caption_rules: Mapped[list["CaptionRule"]] = relationship(back_populates="employee")


class TelegramGroup(Base):
    __tablename__ = "telegram_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    shift_start_hour: Mapped[int] = mapped_column(Integer, default=6)
    shift_end_hour: Mapped[int] = mapped_column(Integer, default=22)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sheet_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sheet_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, default="Sheet1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group_employees: Mapped[list["GroupEmployee"]] = relationship(back_populates="group")
    caption_rules: Mapped[list["CaptionRule"]] = relationship(back_populates="group")


class GroupEmployee(Base):
    __tablename__ = "group_employees"
    __table_args__ = (UniqueConstraint("group_id", "employee_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("telegram_groups.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    sheet_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    group: Mapped["TelegramGroup"] = relationship(back_populates="group_employees")
    employee: Mapped["Employee"] = relationship(back_populates="group_bindings")


class CaptionRule(Base):
    __tablename__ = "caption_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("telegram_groups.id"))
    pattern: Mapped[str] = mapped_column(String(255))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))

    group: Mapped["TelegramGroup"] = relationship(back_populates="caption_rules")
    employee: Mapped["Employee"] = relationship(back_populates="caption_rules")


class ShiftRecord(Base):
    __tablename__ = "shift_records"
    __table_args__ = (UniqueConstraint("employee_id", "shift_date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    shift_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))  # CONFIRMED, NEEDS_REVIEW, REJECTED
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    source_link: Mapped[str] = mapped_column(String(500))
    sheet_write_status: Mapped[str] = mapped_column(String(20), default="NOT_NEEDED")  # PENDING, WRITTEN, ERROR, NOT_NEEDED
    written_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingLog(Base):
    __tablename__ = "processing_log"
    __table_args__ = (
        Index("ix_processing_log_employee_date", "employee_id", "shift_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    update_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    shift_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30))  # RECEIVED, ACCEPTED, DUPLICATE_SAME_SHIFT, NEEDS_REVIEW, SKIPPED, ERROR
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
