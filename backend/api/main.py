
#FastAPI layer.

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.models import User
from backend.state import set_current_user, get_current_user

from backend.agent.main import agent
from backend.database import SessionLocal
from backend.models import IncomeEntry, Semester, Transaction

from datetime import date, timedelta

app = FastAPI(title="Student Wallet Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatMessage):
    response = agent(payload.message)
    return ChatResponse(reply=str(response))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dashboard/{semester_id}")
def get_dashboard(semester_id: int):
    session = SessionLocal()
    try:
        semester = session.get(Semester, semester_id)
        if semester is None:
            raise HTTPException(status_code=404, detail="Semester not found")

        today = date.today()

        income_entries = session.query(IncomeEntry).filter_by(semester_id=semester_id).all()
        total_income = sum(i.amount for i in income_entries) + (semester.carried_over_amount or 0)

        transactions = session.query(Transaction).filter_by(semester_id=semester_id).all()
        total_spent = sum(t.amount for t in transactions)

        balance = total_income - total_spent

        total_days = (semester.end_date - semester.start_date).days
        total_weeks = max(1, round(total_days / 7))
        elapsed_days = (today - semester.start_date).days
        current_week = max(1, min(total_weeks, (elapsed_days // 7) + 1))
        weeks_remaining = max(0, total_weeks - current_week + 1)

        weekly_target = balance / weeks_remaining if weeks_remaining > 0 else 0

        this_week_start = today - timedelta(days=7)
        last_week_start = today - timedelta(days=14)

        this_week_spent = sum(t.amount for t in transactions if t.timestamp.date() >= this_week_start)
        last_week_spent = sum(t.amount for t in transactions if last_week_start <= t.timestamp.date() < this_week_start)

        over_under = this_week_spent - weekly_target
        trend = "down" if this_week_spent < last_week_spent else "up"

        return {
            "semester_name": semester.name,
            "balance": round(balance, 2),
            "money_in": round(total_income, 2),
            "money_out": round(total_spent, 2),
            "current_week": current_week,
            "total_weeks": total_weeks,
            "weeks_remaining": weeks_remaining,
            "weekly_target": round(weekly_target, 2),
            "this_week_spent": round(this_week_spent, 2),
            "last_week_spent": round(last_week_spent, 2),
            "over_under_amount": round(abs(over_under), 2),
            "is_over_budget": over_under > 0,
            "trend": trend,
        }
    finally:
        session.close()


class RegisterRequest(BaseModel):
    email: str
    preferred_name: str


@app.post("/register")
def register(payload: RegisterRequest):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(email=payload.email).first()
        is_new = False
        if user is None:
            user = User(email=payload.email, preferred_name=payload.preferred_name)
            session.add(user)
            session.commit()
            is_new = True

        set_current_user(user.id)

        semester = (
            session.query(Semester)
            .filter_by(user_id=user.id, is_active=True)
            .order_by(Semester.id.desc())
            .first()
        )

        return {
            "user_id": user.id,
            "preferred_name": user.preferred_name,
            "is_new_user": is_new,
            "existing_semester_id": semester.id if semester else None,
        }
    finally:
        session.close()