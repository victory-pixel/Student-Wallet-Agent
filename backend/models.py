#semester
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, String, Boolean, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IncomePattern(str, enum.Enum):
    LUMP_SUM = "lump_sum"
    RECURRING = "recurring"
    IRREGULAR = "irregular"


class ReallocationMode(str, enum.Enum):
    MANUAL = "manual"
    AGENT_EXECUTED = "agent_executed"


class RolloverChoice(str, enum.Enum):
    RESET = "reset"
    CARRYOVER = "carryover"
    UNDECIDED = "undecided"


class Semester(Base):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    income_pattern: Mapped[IncomePattern] = mapped_column(Enum(IncomePattern), nullable=False)
    reallocation_mode: Mapped[ReallocationMode] = mapped_column(
        Enum(ReallocationMode), default=ReallocationMode.MANUAL
    )
    rollover_choice: Mapped[RolloverChoice] = mapped_column(
        Enum(RolloverChoice), default=RolloverChoice.UNDECIDED
    )
    carried_over_amount: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

#Category and sub category
class CategoryType(str, enum.Enum):
    FIXED = "fixed"
    LIVING = "living"
    FUN = "fun"
    MISCELLANEOUS = "miscellaneous"
    EMERGENCY = "emergency"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))

    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[CategoryType] = mapped_column(Enum(CategoryType), nullable=False)

    target_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    requires_reason: Mapped[bool] = mapped_column(Boolean, default=False)

    subcategories: Mapped[list["Subcategory"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )

class Subcategory(Base):
    __tablename__ = "subcategories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)

    category: Mapped["Category"] = relationship(back_populates="subcategories")


#Transactions
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    subcategory_id: Mapped[int | None] = mapped_column(
        ForeignKey("subcategories.id"), nullable=True
    )

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    category: Mapped["Category"] = relationship()
    subcategory: Mapped["Subcategory | None"] = relationship()


#Income and income allocation
class AllocationMode(str, enum.Enum):
    AUTO_SPLIT = "auto_split"
    TARGETED = "targeted"


class IncomeEntry(Base):
    __tablename__ = "income_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "Mom", "Dad", "Scholarship"
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    allocation_mode: Mapped[AllocationMode] = mapped_column(
        Enum(AllocationMode), default=AllocationMode.AUTO_SPLIT
    )

    allocations: Mapped[list["IncomeAllocation"]] = relationship(
        back_populates="income_entry", cascade="all, delete-orphan"
    )


class IncomeAllocation(Base):                      #Records exactly how one income entry's amount was split across categories
    __tablename__ = "income_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    income_entry_id: Mapped[int] = mapped_column(ForeignKey("income_entries.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[float] = mapped_column(Float, nullable=False)

    income_entry: Mapped["IncomeEntry"] = relationship(back_populates="allocations")
    category: Mapped["Category"] = relationship()


#Fixed cost
class FixedCost(Base):
    """
    Represents a recurring, predictable cost like Tuition, Rent, Internet.
    Tracks its own due date and reminder state so the agent knows
    exactly when to nudge (1 week before, 1 day before, day of) and
    doesn't repeat the same reminder twice.
    """
    __tablename__ = "fixed_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    name: Mapped[str] = mapped_column(String, nullable=False)  # "Tuition", "Rent", "Internet"
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)

    # One flag per reminder milestone, so each only ever fires once
    reminded_week_before: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_day_before: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded_day_of: Mapped[bool] = mapped_column(Boolean, default=False)

    category: Mapped["Category"] = relationship()

#Agent Decision
class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))

    kind: Mapped[str] = mapped_column(String, nullable=False)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON string holding structured details, like suggested transfer amounts

    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    # e.g. "approved", "declined", "deferred"

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

#Record of funds transfer
class ReallocationTransfer(Base):
    __tablename__ = "reallocation_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id"))
    from_category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    to_category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    decision_id: Mapped[int] = mapped_column(ForeignKey("agent_decisions.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)