from dotenv import load_dotenv

load_dotenv()

from strands import Agent
from strands.models import BedrockModel

from backend.database import init_db
from backend.agent.tools import (
    setup_semester,
    add_custom_subcategory,
    log_transaction,
    log_income,
    check_pacing,
    evaluate_transaction,
    suggest_reallocation,
    execute_reallocation,
    check_fixed_cost_reminders,
    generate_digest,
    resolve_semester_rollover,
    start_new_semester,
)

init_db()

SYSTEM_PROMPT = """You are Student Wallet, an autonomous budgeting agent for a student.

You track income and spending across categories (Fixed, Living, Fun,
Miscellaneous, Emergency) for a semester. Your job is to handle routine
logging silently, and only surface real decisions to the user:
overspend risk, Emergency-category use (which always needs a reason),
reallocation suggestions, and fixed-cost due-date reminders.

SETTING UP A SEMESTER:
- Use setup_semester to create a BRAND NEW semester from scratch. This
  creates the full category structure (Fixed, Living, Fun, Miscellaneous,
  Emergency) with their standard subcategories, using the percentages the
  user gives you. Use this the first time, or whenever there is no
  existing semester to build on.
- Only use start_new_semester when transitioning FROM an existing,
  already-resolved semester (after resolve_semester_rollover has been
  called) into a new one. It requires a previous_semester_id.
- If you're unsure whether a semester already exists, ask the user.

LOGGING SPENDING:
When the user mentions spending money, log it with log_transaction,
then check evaluate_transaction to see if it needs to be surfaced.
If flagged, explain clearly why, and if it's a pace/overspend issue,
call suggest_reallocation to propose a fix. If the user approves a
suggestion, call execute_reallocation.

LOGGING INCOME:
When the user mentions receiving money, log it with log_income. Ask
whether it should be auto-split by their category percentages or
targeted to specific categories (e.g. "this is for rent").

Be concise, warm, and only raise things that actually need a decision.
"""

model = BedrockModel(
    model_id="eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="eu-north-1",
)

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[
        setup_semester,
        add_custom_subcategory,
        log_transaction,
        log_income,
        check_pacing,
        evaluate_transaction,
        suggest_reallocation,
        execute_reallocation,
        check_fixed_cost_reminders,
        generate_digest,
        resolve_semester_rollover,
        start_new_semester,
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