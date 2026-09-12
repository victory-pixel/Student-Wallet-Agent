# Student Wallet Agent
 
An autonomous budgeting agent for students, built with the **Strands Agents SDK** on **Amazon Bedrock** for the **Agents for Humans Hackathon** (Everyday Agents track).
 
## The problem
 
Every day, students lose hours and money to small, repetitive budgeting tasks — tracking spending, splitting irregular income, remembering when rent or tuition is due, catching overspend before it becomes a real problem. On their own these are minor, but together they drain time and lead to semesters that run out of money before they run out of days.
 
## Who it's for
 
Students managing their own semester budget — especially those with irregular or unpredictable income (allowance sent in one lump sum, monthly transfers from parents, or ad-hoc contributions), who don't have time to manually track every shilling, dollar, or naira.
 
## Why it matters
 
Most budgeting apps are trackers: they show you what happened after the fact. Student Wallet is different — it's an **agent**, not a dashboard. It watches spending and income in the background, reasons about pace against the actual semester timeline, and only interrupts the student when there's a real decision to make: an overspend risk, an Emergency-fund withdrawal that needs justifying, a reallocation worth considering, or a bill coming due.
 
## How it works
 
Student Wallet runs on the **Strands Agents SDK**, connected to **Claude (via Amazon Bedrock)**. The agent has access to 13 tools that let it reason about a student's real financial situation and take action:
 
| Tool | What it does |
|---|---|
| `setup_semester` | Creates a new semester with the full category structure (Fixed, Living, Fun, Miscellaneous, Emergency) and their default subcategories |
| `add_custom_subcategory` | Lets the student add their own subcategories |
| `edit_semester` | Updates semester details (name, dates, income pattern, reallocation mode) |
| `log_transaction` | Logs a spend; enforces that Emergency-category spending always requires a reason |
| `log_income` | Logs income, either auto-split by the student's category percentages or targeted to specific categories |
| `check_pacing` | Compares spend against allocated income, using different logic depending on whether income arrives as a lump sum, recurring, or irregular deposits |
| `evaluate_transaction` | Runs after every spend to decide whether it needs to be silently logged or surfaced as a real decision |
| `suggest_reallocation` | Finds a category with unused budget and proposes moving funds to cover an overspending one |
| `execute_reallocation` | Carries out an approved reallocation, respecting the student's manual vs. agent-executed preference |
| `check_fixed_cost_reminders` | Reminds the student about upcoming Tuition/Rent/Internet payments (1 week before, 1 day before, day of) |
| `generate_digest` | Produces weekly, monthly, or full end-of-semester summaries |
| `resolve_semester_rollover` | Handles the student's choice to reset or carry over leftover funds into the next semester |
| `start_new_semester` | Transitions into a new semester once rollover has been resolved |
 
### The "only interrupt when it matters" design
 
Every category type behaves differently by design:
- **Fixed** (Tuition, Rent, Internet) — predictable costs with due-date reminders
- **Living** (Food, Transport, customizable) — day-to-day variable spend
- **Fun** (Shopping, customizable) — discretionary spend
- **Miscellaneous** (Contributions) — one-off spend
- **Emergency** — a protected category the agent flags and requires a reason to use
Income handling adapts to how a student actually gets paid — a single lump sum for the semester, a recurring monthly/weekly transfer, or irregular ad-hoc amounts — because "on pace" means something different for each.
 
## Architecture
 
See [`architecture-diagram.png`](./architecture-diagram.png) for the full system diagram.
 
- **Backend**: Python, SQLAlchemy, SQLite
- **Agent**: Strands Agents SDK, running on Claude via Amazon Bedrock (`eu.anthropic.claude-sonnet-4-5-20250929-v1:0`)
- **API**: FastAPI, exposing `/chat`, `/dashboard/{semester_id}`, and `/register`
- **Frontend**: Single-page HTML/CSS/JS dashboard with a floating chat bubble for freeform requests
## Try it
 
1. Clone the repo and set up a Python virtual environment
2. `pip install -r backend/requirements.txt`
3. Add your AWS credentials to a `.env` file (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`)
4. Start the backend: `uvicorn backend.api.main:app --reload`
5. Open `frontend/index.html` in your browser
6. Register with an email and name, then tap the chat bubble to set up your first semester
## What's next (roadmap)
 
- Full email verification for account security
- Bedrock AgentCore deployment
- Native mobile app (the agent backend is already designed with a clean API separation to support this)
- Mobile money / SMS-based transaction parsing for automatic logging
## License
 
Apache License 2.0 — see [LICENSE](./LICENSE).