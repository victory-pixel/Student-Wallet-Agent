from datetime import date, timedelta
from backend.database import init_db, SessionLocal
from backend.models import Category, CategoryType, IncomeAllocation, IncomeEntry, IncomePattern, Semester
from backend.agent.tools import log_transaction, evaluate_transaction, suggest_reallocation

init_db()
session = SessionLocal()

semester = Semester(
    name="Test Semester",
    start_date=date.today() - timedelta(days=40),
    end_date=date.today() + timedelta(days=60),
    income_pattern=IncomePattern.LUMP_SUM,
)
session.add(semester)
session.commit()

food = Category(semester_id=semester.id, name="Food", type=CategoryType.LIVING, target_percentage=20)
fun = Category(semester_id=semester.id, name="Fun", type=CategoryType.FUN, target_percentage=10)
session.add_all([food, fun])
session.commit()

income = IncomeEntry(semester_id=semester.id, amount=100000, source="Test")
session.add(income)
session.commit()

session.add(IncomeAllocation(income_entry_id=income.id, category_id=food.id, amount=40000))
session.add(IncomeAllocation(income_entry_id=income.id, category_id=fun.id, amount=20000))
session.commit()

# Grab the plain IDs we need before closing this session
food_id = food.id
fun_id = fun.id
semester_id = semester.id
session.close()

result = log_transaction(semester_id=semester_id, category_id=fun_id, amount=2000, note="movie")
print("Logged Fun transaction:", result)

result = log_transaction(semester_id=semester_id, category_id=food_id, amount=35000, note="big grocery run")
print("Logged Food transaction:", result)

eval_result = evaluate_transaction(transaction_id=result["transaction_id"])
print("\nEvaluation result:", eval_result)

if eval_result["flagged"]:
    suggestion = suggest_reallocation(category_id=food_id)
    print("\nReallocation suggestion:", suggestion)