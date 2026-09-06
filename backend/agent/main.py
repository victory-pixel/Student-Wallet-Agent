from strands import Agent

from backend.agent.tools import (
    log_transaction,
    log_income,
    check_pacing,
    evaluate_transaction,
    suggest_reallocation,
    check_fixed_cost_reminders,
)

SYSTEM_PROMPT = """You are Student Wallet, an autonomous budgeting agent for a student.

You track income and spending across categories (Fixed, Living, Fun,
Miscellaneous, Emergency) for a semester. Your job is to handle routine
logging silently, and only surface real decisions to the user:
overspend risk, Emergency-category use (which always needs a reason),
reallocation suggestions, and fixed-cost due-date reminders.

When the user mentions spending money, log it with log_transaction,
then check evaluate_transaction to see if it needs to be surfaced.
If flagged, explain clearly why, and if it's a pace/overspend issue,
call suggest_reallocation to propose a fix.

When the user mentions receiving money, log it with log_income. Ask
whether it should be auto-split by their category percentages or
targeted to specific categories (e.g. "this is for rent").

Be concise, warm, and only raise things that actually need a decision.
"""

agent = Agent(
    system_prompt=SYSTEM_PROMPT,
    tools=[
        log_transaction,
        log_income,
        check_pacing,
        evaluate_transaction,
        suggest_reallocation,
        check_fixed_cost_reminders,
    ],
)

if __name__ == "__main__":
    print("Student Wallet agent ready. Type 'exit' to quit.\n")
    while True:
        user_input = input("You: ")
        if user_input.strip().lower() == "exit":
            break
        response = agent(user_input)
        print("\nAgent:", response, "\n")
