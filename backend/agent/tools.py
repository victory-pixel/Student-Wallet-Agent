from datetime import date

from strands import tool

from backend.database import SessionLocal
from backend.models import (
    AgentDecision,
    AllocationMode,
    Category,
    IncomeAllocation,
    IncomeEntry,
    IncomePattern,
    Semester,
    Transaction,
)


#Agent tool
@tool
def log_transaction(
    semester_id: int,
    category_id: int,
    amount: float,
    note: str | None = None,
    subcategory_id: int | None = None,
    reason: str | None = None,
) -> dict:
    session = SessionLocal()
    try:
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
    finally:
        session.close()


#Check Pacing
def _category_allocated_income(session, category_id: int) -> float:
    allocations = (
        session.query(IncomeAllocation).filter_by(category_id=category_id).all()
    )
    return sum(a.amount for a in allocations)


def _category_spent(session, category_id: int) -> float:
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
def check_pacing(category_id: int) -> dict:
    session = SessionLocal()
    try:
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
            is_ahead = spend_ratio > time_ratio + 0.15
            comparison_basis = "semester time elapsed"
            comparison_value = time_ratio
        else:
            is_ahead = spend_ratio > 0.9
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
    finally:
        session.close()


#Evaluating Transaction
@tool
def evaluate_transaction(transaction_id: int) -> dict:
    session = SessionLocal()
    try:
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
            pacing = check_pacing(category_id=category.id)
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
    finally:
        session.close()


#Reallocation Suggestion
@tool
def suggest_reallocation(category_id: int) -> dict:
    session = SessionLocal()
    try:
        target_category = session.get(Category, category_id)
        if target_category is None:
            return {"success": False, "error": "Category not found."}

        semester = session.get(Semester, target_category.semester_id)

        all_categories = (
            session.query(Category)
            .filter_by(semester_id=semester.id)
            .filter(Category.id != category_id)
            .filter(Category.type != "emergency")
            .all()
        )

        best_source = None
        best_slack_amount = 0.0

        for cat in all_categories:
            pacing = check_pacing(category_id=cat.id)
            if pacing.get("status") != "on_track" and pacing.get("status") != "no_data":
                continue

            allocated = pacing.get("allocated", 0)
            spent = pacing.get("spent", 0)
            slack = allocated - spent

            if slack > best_slack_amount:
                best_slack_amount = slack
                best_source = cat

        if best_source is None or best_slack_amount <= 0:
            return {
                "success": True,
                "suggestion_found": False,
                "message": (
                    f"No category currently has enough slack to safely cover "
                    f"'{target_category.name}'. This may need a direct conversation "
                    f"about cutting spend or expecting more income."
                ),
            }

        suggested_amount = round(best_slack_amount * 0.5, 2)

        message = (
            f"'{target_category.name}' is running ahead of pace. "
            f"'{best_source.name}' currently has {best_slack_amount:.0f} in unused "
            f"allocation — consider moving {suggested_amount:.0f} from "
            f"'{best_source.name}' to '{target_category.name}'."
        )

        decision = AgentDecision(
            semester_id=semester.id,
            kind="reallocation_suggestion",
            message=message,
            payload=(
                f'{{"from_category_id": {best_source.id}, '
                f'"to_category_id": {target_category.id}, '
                f'"amount": {suggested_amount}}}'
            ),
        )
        session.add(decision)
        session.commit()

        return {
            "success": True,
            "suggestion_found": True,
            "decision_id": decision.id,
            "from_category": best_source.name,
            "to_category": target_category.name,
            "suggested_amount": suggested_amount,
            "message": message,
            "reallocation_mode": semester.reallocation_mode.value,
        }
    finally:
        session.close()


#logging transactions
@tool
def log_income(
    semester_id: int,
    amount: float,
    source: str | None = None,
    allocation_mode: str = "auto_split",
    target_category_ids: list[int] | None = None,
    target_amounts: list[float] | None = None,
) -> dict:
    session = SessionLocal()
    try:
        semester = session.get(Semester, semester_id)
        if semester is None:
            return {"success": False, "error": "Semester not found."}

        mode = (
            AllocationMode.TARGETED
            if allocation_mode == "targeted"
            else AllocationMode.AUTO_SPLIT
        )

        income = IncomeEntry(
            semester_id=semester_id,
            amount=amount,
            source=source,
            allocation_mode=mode,
        )
        session.add(income)
        session.commit()

        allocations_made = []

        if mode == AllocationMode.TARGETED:
            if not target_category_ids or not target_amounts:
                return {
                    "success": False,
                    "error": "targeted_allocation_missing",
                    "message": (
                        "Targeted allocation needs target_category_ids and "
                        "target_amounts. Ask the user which category(ies) "
                        "this income is for and how much goes to each."
                    ),
                }
            if len(target_category_ids) != len(target_amounts):
                return {
                    "success": False,
                    "error": "mismatched_targets",
                    "message": "target_category_ids and target_amounts must be the same length.",
                }
            if sum(target_amounts) > amount:
                return {
                    "success": False,
                    "error": "over_allocated",
                    "message": (
                        f"Targeted amounts ({sum(target_amounts)}) exceed the "
                        f"income amount ({amount}). Ask the user to adjust."
                    ),
                }

            for cat_id, amt in zip(target_category_ids, target_amounts):
                category = session.get(Category, cat_id)
                if category is None:
                    continue
                allocation = IncomeAllocation(
                    income_entry_id=income.id,
                    category_id=cat_id,
                    amount=amt,
                )
                session.add(allocation)
                allocations_made.append({"category": category.name, "amount": amt})

        else:  # AUTO_SPLIT
            categories = session.query(Category).filter_by(semester_id=semester_id).all()
            total_percentage = sum(c.target_percentage for c in categories)

            if total_percentage <= 0:
                return {
                    "success": False,
                    "error": "no_percentages_set",
                    "message": (
                        "No category percentages have been set for this semester. "
                        "Ask the user to set target percentages before auto-splitting income."
                    ),
                }

            for category in categories:
                if category.target_percentage <= 0:
                    continue
                share = (category.target_percentage / total_percentage) * amount
                allocation = IncomeAllocation(
                    income_entry_id=income.id,
                    category_id=category.id,
                    amount=round(share, 2),
                )
                session.add(allocation)
                allocations_made.append({"category": category.name, "amount": round(share, 2)})

        session.commit()

        return {
            "success": True,
            "income_entry_id": income.id,
            "amount": amount,
            "allocation_mode": mode.value,
            "allocations": allocations_made,
        }
    finally:
        session.close()
