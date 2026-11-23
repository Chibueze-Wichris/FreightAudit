from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True); email: Mapped[str]=mapped_column(String(320), unique=True, index=True); password_hash: Mapped[str]=mapped_column(String(255)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class Contract(Base):
    __tablename__='contracts'
    id: Mapped[int]=mapped_column(primary_key=True); carrier: Mapped[str]=mapped_column(String(200), index=True); status: Mapped[str]=mapped_column(String(20), default='draft'); terms: Mapped[dict]=mapped_column(JSON); source_name: Mapped[str]=mapped_column(String(255)); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class Invoice(Base):
    __tablename__='invoices'
    id: Mapped[int]=mapped_column(primary_key=True); reference: Mapped[str]=mapped_column(String(120), index=True); carrier: Mapped[str]=mapped_column(String(200), index=True); invoice_date: Mapped[str]=mapped_column(String(20)); billed_total: Mapped[float]=mapped_column(Float); linehaul: Mapped[float]=mapped_column(Float, default=0); fuel_amount: Mapped[float]=mapped_column(Float, default=0); fuel_percent: Mapped[float]=mapped_column(Float, default=0); lane: Mapped[str]=mapped_column(String(200), default=''); file_name: Mapped[str]=mapped_column(String(255)); source_page: Mapped[int]=mapped_column(Integer, default=1); fingerprint: Mapped[str]=mapped_column(String(64), index=True); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class Finding(Base):
    __tablename__='findings'
    id: Mapped[int]=mapped_column(primary_key=True); invoice_id: Mapped[int]=mapped_column(ForeignKey('invoices.id')); rule: Mapped[str]=mapped_column(String(40)); variance: Mapped[float]=mapped_column(Float); billed: Mapped[float]=mapped_column(Float); expected: Mapped[float]=mapped_column(Float); explanation: Mapped[str]=mapped_column(Text); evidence: Mapped[dict]=mapped_column(JSON); status: Mapped[str]=mapped_column(String(20), default='open'); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
class Claim(Base):
    __tablename__='claims'
    id: Mapped[int]=mapped_column(primary_key=True); finding_id: Mapped[int]=mapped_column(ForeignKey('findings.id')); body: Mapped[str]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now)
