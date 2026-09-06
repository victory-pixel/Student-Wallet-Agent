import json
from datetime import date, datetime, timedelta

from strands import tool

from backend.database import SessionLocal
from backend.models import (
    AgentDecision,
    AllocationMode,
    Category,
    CategoryType,
    FixedCost,
    IncomeAllocation,
    IncomeEntry,
    IncomePattern,
    ReallocationMode,
    ReallocationTransfer,
    RolloverChoice,
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
    base = sum(a.amount for a in allocations)

    incoming = (
        session.query(ReallocationTransfer).filter_by(to_category_id=category_id).all()
    )
    outgoing = (
        session.query(ReallocationTransfer).filter_by(from_category_id=category_id).all()
    )
    transferred_in = sum(t.amount for t in incoming)
    transferred_out = sum(t.amount for t in outgoing)

    return base + transferred_in - transferred_out


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


#Fixed Cost Reminders
@tool
def check_fixed_cost_reminders(semester_id: int) -> dict:
    session = SessionLocal()
    try:
        semester = session.get(Semester, semester_id)
        if semester is None:
            return {"success": False, "error": "Semester not found."}

        fixed_costs = (
            session.query(FixedCost)
            .filter_by(semester_id=semester_id, is_paid=False)
            .all()
        )

        today = date.today()
        reminders_fired = []

        for cost in fixed_costs:
            days_until_due = (cost.due_date - today).days

            if days_until_due < 0:
                continue

            if days_until_due == 7 and not cost.reminded_week_before:
                cost.reminded_week_before = True
                reminders_fired.append({
                    "fixed_cost": cost.name,
                    "amount": cost.amount,
                    "due_date": cost.due_date.isoformat(),
                    "milestone": "one_week_before",
                    "message": f"'{cost.name}' ({cost.amount:.0f}) is due in 1 week, on {cost.due_date.isoformat()}.",
                })

            elif days_until_due == 1 and not cost.reminded_day_before:
                cost.reminded_day_before = True
                reminders_fired.append({
                    "fixed_cost": cost.name,
                    "amount": cost.amount,
                    "due_date": cost.due_date.isoformat(),
                    "milestone": "one_day_before",
                    "message": f"'{cost.name}' ({cost.amount:.0f}) is due tomorrow.",
                })

            elif days_until_due == 0 and not cost.reminded_day_of:
                cost.reminded_day_of = True
                reminders_fired.append({
                    "fixed_cost": cost.name,
                    "amount": cost.amount,
                    "due_date": cost.due_date.isoformat(),
                    "milestone": "day_of",
                    "message": f"'{cost.name}' ({cost.amount:.0f}) is due today.",
                })

        for fired in reminders_fired:
            decision = AgentDecision(
                semester_id=semester_id,
                kind="fixed_cost_reminder",
                message=fired["message"],
            )
            session.add(decision)

        session.commit()

        return {
            "success": True,
            "reminders_fired": reminders_fired,
            "count": len(reminders_fired),
        }
    finally:
        session.close()


#Execute Reallocation
@tool
def execute_reallocation(decision_id: int, approved: bool) -> dict:
    session = SessionLocal()
    try:
        decision = session.get(AgentDecision, decision_id)
        if decision is None:
            return {"success": False, "error": "Decision not found."}

        if decision.kind != "reallocation_suggestion":
            return {"success": False, "error": "This decision is not a reallocation suggestion."}

        if decision.resolved:
            return {"success": False, "error": "This decision has already been resolved."}

        if not approved:
            decision.resolved = True
            decision.resolution = "declined"
            decision.resolved_at = datetime.utcnow()
            session.commit()
            return {"success": True, "executed": False, "message": "Reallocation declined."}

        semester = session.get(Semester, decision.semester_id)
        payload = json.loads(decision.payload)
        from_category_id = payload["from_category_id"]
        to_category_id = payload["to_category_id"]
        amount = payload["amount"]

        if semester.reallocation_mode == ReallocationMode.MANUAL:
            decision.resolved = True
            decision.resolution = "approved_manual"
            decision.resolved_at = datetime.utcnow()
            session.commit()
            return {
                "success": True,
                "executed": False,
                "message": (
                    f"Approved. Since reallocation mode is manual, please move "
                    f"{amount:.0f} from category {from_category_id} to "
                    f"category {to_category_id} yourself."
                ),
            }

        transfer = ReallocationTransfer(
            semester_id=semester.id,
            from_category_id=from_category_id,
            to_category_id=to_category_id,
            amount=amount,
            decision_id=decision.id,
        )
        session.add(transfer)

        decision.resolved = True
        decision.resolution = "approved_executed"
        decision.resolved_at = datetime.utcnow()
        session.commit()

        return {
            "success": True,
            "executed": True,
            "message": f"Moved {amount:.0f} from category {from_category_id} to category {to_category_id}.",
        }
    finally:
        session.close()

#Digest Generation
@tool
def generate_digest(semester_id: int, period: str = "weekly") -> dict:
    session = SessionLocal()
    try:
        semester = session.get(Semester, semester_id)
        if semester is None:
            return {"success": False, "error": "Semester not found."}

        today = date.today()

        if period == "weekly":
            window_start = today - timedelta(days=7)
        elif period == "monthly":
            window_start = today - timedelta(days=30)
        elif period == "semester":
            window_start = semester.start_date
        else:
            return {"success": False, "error": "period must be 'weekly', 'monthly', or 'semester'."}

        categories = session.query(Category).filter_by(semester_id=semester_id).all()

        category_summaries = []
        total_spent_period = 0.0
        for cat in categories:
            all_txns = session.query(Transaction).filter_by(category_id=cat.id).all()
            period_txns = [t for t in all_txns if t.timestamp.date() >= window_start]
            period_spent = sum(t.amount for t in period_txns)
            total_spent_period += period_spent

            pacing = check_pacing(category_id=cat.id)

            category_summaries.append({
                "category": cat.name,
                "spent_this_period": period_spent,
                "total_spent": pacing.get("spent", 0),
                "allocated": pacing.get("allocated", 0),
                "status": pacing.get("status", "no_data"),
            })

        income_entries = session.query(IncomeEntry).filter_by(semester_id=semester_id).all()
        period_income = [i for i in income_entries if i.timestamp.date() >= window_start]
        total_income_period = sum(i.amount for i in period_income)
        total_income_all_time = sum(i.amount for i in income_entries)

        decisions = (
            session.query(AgentDecision)
            .filter_by(semester_id=semester_id)
            .all()
        )
        period_decisions = [d for d in decisions if d.created_at.date() >= window_start]
        decisions_by_kind = {}
        for d in period_decisions:
            decisions_by_kind[d.kind] = decisions_by_kind.get(d.kind, 0) + 1

        resolved_count = sum(1 for d in period_decisions if d.resolved)
        pending_count = sum(1 for d in period_decisions if not d.resolved)

        emergency_uses = [d for d in period_decisions if d.kind == "emergency_flag"]

        summary = {
            "success": True,
            "period": period,
            "window_start": window_start.isoformat(),
            "window_end": today.isoformat(),
            "income_this_period": total_income_period,
            "income_all_time": total_income_all_time,
            "spent_this_period": total_spent_period,
            "categories": category_summaries,
            "decisions_surfaced": len(period_decisions),
            "decisions_by_kind": decisions_by_kind,
            "decisions_resolved": resolved_count,
            "decisions_pending": pending_count,
            "emergency_uses_this_period": len(emergency_uses),
        }

        if period == "semester":
            summary["semester_name"] = semester.name
            summary["semester_start"] = semester.start_date.isoformat()
            summary["semester_end"] = semester.end_date.isoformat()
            summary["rollover_choice"] = semester.rollover_choice.value

        return summary
    finally:
        session.close()

#Semester Rollover
@tool
def resolve_semester_rollover(semester_id: int, choice: str | None = None) -> dict:
    session = SessionLocal()
    try:
        semester = session.get(Semester, semester_id)
        if semester is None:
            return {"success": False, "error": "Semester not found."}

        if semester.rollover_choice != RolloverChoice.UNDECIDED:
            return {
                "success": False,
                "error": "already_resolved",
                "message": f"Rollover was already resolved as '{semester.rollover_choice.value}'.",
            }

        if choice is None:
            semester.rollover_choice = RolloverChoice.RESET
            semester.carried_over_amount = 0.0
            session.commit()
            return {
                "success": True,
                "choice_made": "reset",
                "defaulted": True,
                "message": "No response received, so defaulted to reset. Leftover funds will not carry over.",
            }

        if choice not in ("reset", "carryover"):
            return {"success": False, "error": "choice must be 'reset', 'carryover', or omitted."}

        if choice == "reset":
            semester.rollover_choice = RolloverChoice.RESET
            semester.carried_over_amount = 0.0
            session.commit()
            return {
                "success": True,
                "choice_made": "reset",
                "defaulted": False,
                "message": "Semester will reset fresh. No funds carried over.",
            }

        categories = session.query(Category).filter_by(semester_id=semester_id).all()
        total_leftover = 0.0
        for cat in categories:
            if cat.type == CategoryType.EMERGENCY:
                continue
            pacing = check_pacing(category_id=cat.id)
            allocated = pacing.get("allocated", 0)
            spent = pacing.get("spent", 0)
            leftover = allocated - spent
            if leftover > 0:
                total_leftover += leftover

        semester.rollover_choice = RolloverChoice.CARRYOVER
        semester.carried_over_amount = round(total_leftover, 2)
        session.commit()

        return {
            "success": True,
            "choice_made": "carryover",
            "defaulted": False,
            "carried_over_amount": round(total_leftover, 2),
            "message": f"{total_leftover:.0f} in leftover funds will carry over to the next semester.",
        }
    finally:
        session.close()


@tool
def start_new_semester(
    previous_semester_id: int,
    name: str,
    start_date_str: str,
    end_date_str: str,
    income_pattern: str,
) -> dict:
    session = SessionLocal()
    try:
        previous = session.get(Semester, previous_semester_id)
        if previous is None:
            return {"success": False, "error": "Previous semester not found."}

        if previous.rollover_choice == RolloverChoice.UNDECIDED:
            return {
                "success": False,
                "error": "rollover_undecided",
                "message": (
                    "The previous semester's rollover choice hasn't been resolved yet. "
                    "Call resolve_semester_rollover first."
                ),
            }

        try:
            pattern = IncomePattern(income_pattern)
        except ValueError:
            return {"success": False, "error": "Invalid income_pattern."}

        try:
            new_start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            new_end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            return {"success": False, "error": "Dates must be in YYYY-MM-DD format."}

        previous.is_active = False

        new_semester = Semester(
            name=name,
            start_date=new_start,
            end_date=new_end,
            income_pattern=pattern,
            carried_over_amount=previous.carried_over_amount,
        )
        session.add(new_semester)
        session.commit()

        return {
            "success": True,
            "new_semester_id": new_semester.id,
            "carried_over_amount": new_semester.carried_over_amount,
            "message": f"New semester '{name}' created, starting with {new_semester.carried_over_amount:.0f} carried over.",
        }
    finally:
        session.close()