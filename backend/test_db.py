from backend.database import init_db, SessionLocal
from backend.models import Semester, IncomePattern
from datetime import date

init_db()

session = SessionLocal()
new_semester = Semester(
    name="Year 3 Semester 1",
    start_date=date(2026, 9, 1),
    end_date=date(2027, 1, 15),
    income_pattern=IncomePattern.IRREGULAR,
)
session.add(new_semester)
session.commit()

print("Saved semester with id:", new_semester.id)
session.close()
