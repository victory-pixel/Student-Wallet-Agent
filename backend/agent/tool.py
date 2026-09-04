
#Agent tool
from strands import tool
from sqlalchemy.orm import Session

from backend.models import Category, Transaction


@tool
def log_transaction(
    session: Session,
    semester_id: int,
    category_id: int,
    amount: float,
    note: str | None = None,
    subcategory_id: int | None = None,
    reason: str | None = None,
) -> dict:
    """
    Logs a new spending transaction.

    Returns a dict describing what happened, so the agent can decide
    whether to just confirm it silently or surface it as a decision.
    """
    category = session.get(Category, category_id)
    if category is None:
        return {"success": False, "error": "Category not found."}

    if category.requires_reason and not reason:
        return {
            "success": False,
            "error": "reason_required",
            "message": (
                f"'{category.name}' requires a reason before logging this "
                "spend. Please ask the user why they're spending from it."
            ),
        }

    txn = Transaction(
        semester_id=semester_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        amount=amount,
        note=note,
        reason=reason,
    )
    session.add(txn)
    session.commit()

    return {
        "success": True,
        "transaction_id": txn.id,
        "category": category.name,
        "amount": amount,
        "requires_followup_check": True,
    }

#Evaluating Transaction

from strands import tool
from sqlalchemy.orm import Session

from backend.models import AgentDecision, Category, Semester, Transaction

@tool
def evaluate_transaction(session: Session, transaction_id: int) -> dict:
    txn = session.get(Transaction, transaction_id)
    if txn is None:
        return {"success": False, "error": "Transaction not found."}

    category = session.get(Category, txn.category_id)
    semester = session.get(Semester, txn.semester_id)

    flagged = False
    flag_reason = None
    decision_kind = None

    if category.requires_reason:
        flagged = True
        flag_reason = f"Emergency category used: {txn.reason or 'no reason given'}"
        decision_kind = "emergency_flag"
    else:
        pacing = check_pacing(session=session, category_id=category.id)
        if pacing.get("status") == "ahead":
            flagged = True
            flag_reason = (
                f"'{category.name}' spending is running ahead of pace: "
                f"{pacing['spend_ratio'] * 100:.0f}% of allocated funds used, "
                f"compared to {pacing['comparison_value'] * 100:.0f}% "
                f"({pacing['comparison_basis']})."
            )
            decision_kind = "pace_warning"

    if flagged:
        txn.flagged = True
        txn.flag_reason = flag_reason
        decision = AgentDecision(
            semester_id=semester.id,
            kind=decision_kind,
            message=flag_reason,
        )
        session.add(decision)
        session.commit()

    return {
        "success": True,
        "flagged": flagged,
        "flag_reason": flag_reason,
        "category": category.name,
    }

#Check Pacing
#Calculates how much income has actually been allocated to a category,and compares that against how much has been spent
from datetime import date

from strands import tool
from sqlalchemy.orm import Session

from backend.models import (
    Category,
    IncomeAllocation,
    IncomeEntry,
    IncomePattern,
    Semester,
    Transaction,
)


def _category_allocated_income(session: Session, category_id: int) -> float:
    #Total income actually allocated to this category so far.
    allocations = (
        session.query(IncomeAllocation).filter_by(category_id=category_id).all()
    )
    return sum(a.amount for a in allocations)


def _category_spent(session: Session, category_id: int) -> float:
    txns = session.query(Transaction).filter_by(category_id=category_id).all()
    return sum(t.amount for t in txns)


def _semester_progress(semester: Semester) -> float:
    today = date.today()
    total_days = (semester.end_date - semester.start_date).days
    elapsed_days = (today - semester.start_date).days
    if total_days <= 0:
        return 1.0
    return max(0.0, min(1.0, elapsed_days / total_days))


@tool
def check_pacing(session: Session, category_id: int) -> dict:
    category = session.get(Category, category_id)
    if category is None:
        return {"success": False, "error": "Category not found."}

    semester = session.get(Semester, category.semester_id)
    allocated = _category_allocated_income(session, category_id)
    spent = _category_spent(session, category_id)

    if allocated <= 0:
        return {
            "success": True,
            "status": "no_data",
            "category": category.name,
            "spent": spent,
            "allocated": allocated,
        }

    spend_ratio = spent / allocated

    if semester.income_pattern == IncomePattern.LUMP_SUM:
        time_ratio = _semester_progress(semester)
        is_ahead = spend_ratio > time_ratio + 0.15  # 15% buffer before flagging
        comparison_basis = "semester time elapsed"
        comparison_value = time_ratio
    else:
        is_ahead = spend_ratio > 0.9  # spent over 90% of what's arrived so far
        comparison_basis = "income received so far"
        comparison_value = 1.0

    status = "ahead" if is_ahead else "on_track"

    return {
        "success": True,
        "status": status,
        "category": category.name,
        "spent": spent,
        "allocated": allocated,
        "spend_ratio": round(spend_ratio, 2),
        "comparison_basis": comparison_basis,
        "comparison_value": round(comparison_value, 2),
    }