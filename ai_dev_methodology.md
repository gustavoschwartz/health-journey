# AI Development Methodology & Learning Goals

## Why This File Exists
This is a living document capturing how to build AI projects well, and what I want to learn.
It grows as my understanding deepens. It is separate from personal context — this is about
craft, not biography.

---

## Agentic Development Methodology

### Principle 1: Plan Before You Code
- Produce `plan.md` and `architecture.md` before writing a single line of code
- Use AI as a collaborative planning partner — iterative back-and-forth until ambiguities
  are resolved, not just acknowledged
- The output should be specific enough that coding becomes execution, not exploration
- Key artifacts: architecture diagram, data models, API contracts, phasing, open questions

### Principle 2: Grilling Until Questions Are Answered
- Don't accept vague plans — AI should push back until edge cases and unknowns are surfaced
- Every major decision should have a documented rationale and tradeoffs
- If you can't explain *why* a decision was made, the planning isn't done

### Principle 3: Validation Tests First
- Define what "working" looks like before writing implementation
- Write tests that cover common cases AND edge cases
- Tests enable closed-loop agentic iteration: agent runs → tests catch failures →
  agent self-corrects, without human intervention on every cycle

### Principle 4: Context Management Strategy
- The orchestrator agent must know when to delegate vs. handle in main context
- Use sub-agents for scoped, single-responsibility tasks to avoid context pollution
- Use dedicated research agents to gather information independently and report findings —
  they inform decisions without bloating the main agent's context
- Main context should stay clean and focused on orchestration

### Principle 5: Mix of Interactive and Automated Tasks
- **Interactive tasks**: when human judgment and iteration matter (design decisions,
  ambiguous requirements, course corrections)
- **Automated tasks**: well-defined tasks in the plan that the agent can execute
  deterministically
- **Autonomous loops**: agent iterates until a specific goal is reached, without
  human intervention at each step
- Knowing which mode to use for which task is itself a key skill

---

## What I Want to Learn (In Order of Priority)

### Core Concepts
- **Agents & sub-agents** — how an LLM decides what to do next, which tools to call,
  and in what order; how to delegate to scoped sub-agents
- **Tool use / function calling** — defining tools and letting Claude choose when to
  invoke them
- **Planning at the LLM level** — the model reasoning about steps before taking them,
  not just executing a fixed pipeline
- **Multi-source data orchestration** — normalizing and synthesizing data from multiple
  APIs with different shapes and auth flows
- **Context window management** — knowing what to keep, what to delegate, what to discard

### Architectural Patterns
- Workflow (deterministic, sequential) vs. agent (LLM-driven, dynamic) — when to use each
- Orchestrator + sub-agent pattern
- Research agents that produce input without polluting main context
- Closed-loop agentic iteration with validation tests
- Explicit planner/executor pattern (future — post this project)

### Technical Skills
- React Native for mobile front-end
- FastAPI for Python backend
- OAuth flows and third-party API integration
- HealthKit bridge via react-native-health
- Streaming responses from Claude API

---

## Current Project: Health Journey iPhone App

### What It Is
A personal health tracking app that aggregates data from multiple sources and enables
intelligent, multi-source conversation about health trends and patterns.

### Data Sources
| Source | Data Type | Integration |
|--------|-----------|-------------|
| Strava | Exercise / workouts | REST API + OAuth |
| Apple Health (iPhone) | Fitness data, steps, HRV | react-native-health (HealthKit bridge) |
| VeSync | Daily weight measurements | REST API |
| OMRON Connect | Blood pressure readings | REST API |
| Manual input | Mounjaro injection date, dosage | App UI → own DB |
| Manual input | Daily energy level, overall feeling | App UI → own DB |

### Why This Project (Learning Rationale)
- More complex than previous projects: multiple data sources, dynamic retrieval,
  agent-driven orchestration
- Real personal utility: will actually use it daily
- Forces agent thinking: questions like "why was my energy low Tuesday?" require
  the orchestrator to reason across sources, not just execute a fixed query
- Introduces React Native: first mobile front-end project
- Natural path to explicit planning agents in a future iteration

### Architecture (Draft)
```
React Native App (iOS)
        ↓
  FastAPI Backend
        ↓
  Orchestrator Agent          ← Claude with tool use; plans which tools to call
        ↓
  ┌──────────┬──────────┬──────────┬──────────┬──────────┐
  ↓          ↓          ↓          ↓          ↓          ↓
Strava   Apple Health  VeSync    OMRON     Manual Log  Research
Agent    Agent         Agent     Agent     (own DB)    Agent(s)
```

### Phasing Strategy
- **Phase 1**: Orchestrator + Strava + Manual Log — get agent pattern working end to end
- **Phase 2**: Add Apple Health, VeSync, OMRON one source at a time
- **Phase 3**: Refine context management, add research agents, close the test loop
- **Future**: Explicit planner/executor pattern, confidence scoring, anomaly detection

---

## Key Principles to Carry Forward
- Plan first, code second — always
- Understand the *why* behind every decision, not just the *what*
- Tests define done — if there's no test, it's not finished
- Context is a resource — spend it deliberately
- Start narrow, add complexity only after the core pattern works
