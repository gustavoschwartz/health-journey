# Health Journey

A personal health tracking iPhone app that aggregates data from multiple sources and
enables AI-powered conversation about health trends and patterns.

Ask questions like *"Why did I feel tired last Tuesday?"* and get answers grounded in
your actual data — workouts, sleep, weight, blood pressure, medication, and more.

---

## What It Does

- **Morning check-in**: log yesterday's feeling, calories, alcohol, Mounjaro dose, and
  workout feelings in a conversational flow
- **Conversational interface**: ask open-ended questions about your health data
- **Multi-source intelligence**: the AI reasons across all your data sources simultaneously
  to synthesize answers
- **Nightly sync**: data is fetched automatically at midnight so it's ready when you need it

---

## Tech Stack

| Layer | Technology |
|---|---|
| Mobile | React Native (iOS) |
| Backend | FastAPI (Python) |
| Database | PostgreSQL |
| Cloud | Railway |
| AI | Claude API (claude-sonnet-4) |
| HealthKit bridge | react-native-health |

---

## Data Sources

| Source | Data |
|---|---|
| Strava | Workouts (single source of truth) |
| Apple Health | Steps, sleep stages, HRV, resting heart rate |
| VeSync | Daily weight |
| OMRON Connect | Blood pressure readings |
| Manual input | Overall feeling, calories, alcohol, Mounjaro dose, workout feeling |

---

## Architecture

```
React Native App (iOS)
        ↓ HTTPS / REST
  FastAPI Backend (Railway)
        ↓
  Orchestrator Agent          ← Claude — plans tool calls, synthesizes answers
        ↓
  ┌──────────┬──────────┬──────────┬──────────┬──────────┐
  ↓          ↓          ↓          ↓          ↓          ↓
Strava    Apple      VeSync    OMRON     Manual    Summarization  Research
tool      Health     tool      tool      log       sub-agent      sub-agent
          tool                           tool      (LLM)          (LLM)
  └──────────┴──────────┴──────────┴──────────┴──────────┘
                                ↓
                          PostgreSQL
```

**Tools** (no LLM): fetch and return data from each source.
**Sub-agents** (LLM-powered): Summarization compresses conversation history;
Research retrieves historical context on demand.
**Orchestrator**: Claude decides which tools to call based on your question.

---

## Agent Pattern

This app is built around an **orchestrator agent** — Claude reasons about what data
it needs to answer your question, calls the right tools, and synthesizes the results.

When you ask *"Why did I feel tired last Tuesday?"*, the orchestrator:
1. Identifies which data sources are relevant
2. Calls each tool for that date
3. Synthesizes the results into a grounded answer
4. Streams the response token by token with visible tool call progress

This is the core learning goal of the project: building real agent-driven orchestration
across multiple data sources.

---

## Running Locally

### Prerequisites
- Python 3.11+
- PostgreSQL (or use Railway's managed instance)
- Node.js 18+ (for React Native, Phase 2)

### Backend setup

```bash
# Clone the repo
git clone https://github.com/gustavoschwartz/health-journey.git
cd health-journey

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL and other secrets

# Run database migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

### Verify it's running

```bash
curl http://localhost:8000/health
# {"status": "ok"}

curl http://localhost:8000/health/db
# {"status": "ok", "database": "connected"}
```

---

## Project Structure

```
health-journey/
├── app/
│   ├── main.py          ← FastAPI routes
│   ├── models.py        ← SQLAlchemy models (all tables)
│   ├── tools/           ← Data source tools (Strava, Apple Health, etc.)
│   ├── agents/          ← Orchestrator + sub-agents
│   └── services/        ← OAuth, sync, check-in logic
├── alembic/             ← Database migrations
├── architecture.md      ← Full system design with decision rationale
├── plan.md              ← Phased build plan with validation tests
└── requirements.txt
```

---

## Build Phases

| Phase | Scope | Demo question |
|---|---|---|
| 1 *(current)* | Strava + manual workout feeling | *"Show me my workouts this week and how I felt during each one"* |
| 2 | All data sources + full check-in | *"Why did I feel tired last Tuesday?"* |
| 3 | Tiered context + auth | *"Can you see a pattern in my feel-good vs feel-bad days?"* |
| 4 | Polish + portfolio | — |
| Future | Explicit planner/executor pattern | *"What should I focus on this month to maximize my feel-good days?"* |

---

## Learning Goals

This project is explicitly built to learn:

- **Orchestrator agents** — LLM-driven planning across multiple tools
- **Tool use / function calling** — defining tools and letting Claude choose when to invoke them
- **Multi-source data orchestration** — normalizing data from APIs with different shapes and auth flows
- **Context window management** — tiered context strategy: current session + rolling summary + on-demand research
- **Sub-agent patterns** — scoped agents for summarization and historical research
- **Explicit planner/executor pattern** *(future)* — a dedicated planner agent produces a structured plan, then an executor agent carries it out step by step. Added when the base orchestrator demonstrably struggles with complex multi-step queries.

---

## Author

Gustavo Varejao
Senior Technical Program Manager
[LinkedIn](https://linkedin.com/in/gustavovarejao)
