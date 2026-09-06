from datetime import date, timedelta
from backend.database import init_db, SessionLocal
from backend.models import Category, CategoryType, IncomeAllocation, IncomeEntry, IncomePattern, Semester, ReallocationMode
from backend.agent.tools import log_transaction, evaluate_transaction, suggest_reallocation, check_pacing, execute_reallocation

init_db()
session = SessionLocal()

semester = Semester(
    name="Test", start_date=date.today()-timedelta(days=40), end_date=date.today()+timedelta(days=60),
    income_pattern=IncomePattern.LUMP_SUM, reallocation_mode=ReallocationMode.AGENT_EXECUTED,
)
session.add(semester)
session.commit()

food = Category(semester_id=semester.id, name="Food", type=CategoryType.LIVING)
fun = Category(semester_id=semester.id, name="Fun", type=CategoryType.FUN)
session.add_all([food, fun])
session.commit()

income = IncomeEntry(semester_id=semester.id, amount=100000, source="Test")
session.add(income)
session.commit()
session.add(IncomeAllocation(income_entry_id=income.id, category_id=food.id, amount=40000))
session.add(IncomeAllocation(income_entry_id=income.id, category_id=fun.id, amount=20000))
session.commit()

food_id, fun_id, semester_id = food.id, fun.id, semester.id
session.close()

print("--- BEFORE: Food pacing ---")
print(check_pacing(category_id=food_id))

log_transaction(semester_id=semester_id, category_id=fun_id, amount=1000, note="small")
result = log_transaction(semester_id=semester_id, category_id=food_id, amount=35000, note="overspend")
eval_result = evaluate_transaction(transaction_id=result["transaction_id"])
print("\n--- Evaluation ---")
print(eval_result)

suggestion = suggest_reallocation(category_id=food_id)
print("\n--- Suggestion ---")
print(suggestion)

print("\n--- Executing approval ---")
exec_result = execute_reallocation(decision_id=suggestion["decision_id"], approved=True)
print(exec_result)

print("\n--- AFTER: Food pacing (should show more allocated now) ---")
print(check_pacing(category_id=food_id))

print("\n--- AFTER: Fun pacing (should show less allocated now) ---")
print(check_pacing(category_id=fun_id))

print("\n--- Trying to execute the SAME decision again (should fail) ---")
print(execute_reallocation(decision_id=suggestion["decision_id"], approved=True))
