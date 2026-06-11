# Health Journey App — Architecture

## Document Purpose
This is the authoritative system design document for the Health Journey iPhone app.
Every decision recorded here was made deliberately, with rationale and tradeoffs documented.
Nothing gets built that contradicts this document without updating it first.

---

## System Overview

A personal health tracking app that aggregates data from multiple sources and enables
intelligent, multi-source conversation about health trends and patterns. Built to learn
agent architecture — specifically orchestrator agents, tool use, and context management.

### Core user experience
- Morning check-in: log yesterday's feeling, calories, alcohol, Mounjaro, workout feelings
- Conversational interface: ask questions like "why did I feel tired last Tuesday?"
- Orchestrator reasons across all data sources to synthesize answers

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Mobile front-end | React Native (iOS) | HealthKit bridge via react-native-health. Cross-platform foundation enables future Android version — only the HealthKit bridge needs replacing with Health Connect; all other code is reusable. |
| Backend | FastAPI (Python) | Lightweight, async, excellent Claude SDK support |
| Database | PostgreSQL | Relational, multi-user ready, managed on Railway |
| Cloud platform | Railway | No cold starts, managed PostgreSQL included, simple deploy |
| AI | Claude API (claude-sonnet-4-6) | Orchestrator agent + 2 true sub-agents |
| HealthKit bridge | react-native-health | Wraps HealthKit in JS API, no Swift required |

---

## Data Sources

| Source | Data type | Integration |
|---|---|---|
| Strava | Workouts | REST API + OAuth |
| Apple Health | Steps, sleep, HRV, heart rate | HealthKit via react-native-health |
| VeSync | Daily weight | REST API |
| OMRON Connect | Blood pressure readings | REST API |
| Manual input | Feeling, calories, alcohol, Mounjaro, workout feeling | App UI → FastAPI → PostgreSQL |

**Key rule**: Strava is the single source of truth for workouts. All workouts must be
logged in Strava. Apple Health does not contribute workout data.

---

## Data Model

### `users`
| Field | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `email` | string | |
| `created_at` | timestamp | |

---

### `daily_summary`
One record per day. The primary organizing unit.

| Field | Type | Source |
|---|---|---|
| `user_id` | uuid (FK → users) | system |
| `date` | date | system |
| `overall_feeling` | enum: great/good/neutral/bad/terrible | manual input |
| `calories_previous_day` | int (nullable) | manual input |
| `notes` | text (nullable) | manual input |

---

### `workout`
Multiple per day allowed.

| Field | Type | Source |
|---|---|---|
| `user_id` | uuid (FK → users) | system |
| `date` | date | Strava |
| `strava_id` | string | Strava |
| `type` | string (run, cycle, F45, etc.) | Strava |
| `duration_minutes` | int | Strava |
| `distance_km` | float (nullable) | Strava |
| `avg_heart_rate` | int (nullable) | Strava |
| `calories` | int (nullable) | Strava |
| `feeling` | enum: strong/normal/weak (nullable) | manual input |
| `feeling_prompted` | bool | system |

---

### `apple_health_daily`
One record per day.

| Field | Type | Source |
|---|---|---|
| `user_id` | uuid (FK → users) | system |
| `date` | date | Apple Health |
| `timezone` | string (nullable) | device |
| `steps` | int | Apple Health |
| `sleep_hours` | float | Apple Health |
| `sleep_deep_minutes` | int | Apple Health |
| `sleep_rem_minutes` | int | Apple Health |
| `sleep_awake_minutes` | int | Apple Health |
| `hrv_ms` | float (nullable) | Apple Health |
| `resting_heart_rate` | int (nullable) | Apple Health |

---

### `weight`
One record per day.

| Field | Type | Source |
|---|---|---|
| `user_id` | uuid (FK → users) | system |
| `date` | date | VeSync |
| `weight_kg` | float | VeSync |

---

### `bp_reading`
Multiple per day allowed.

| Field | Type | Source |
|---|---|---|
| `user_id` | uuid (FK → users) | system |
| `date` | date | OMRON |
| `systolic` | int | OMRON |
| `diastolic` | int | OMRON |
| `pulse` | int | OMRON |
| `time_of_day` | time (nullable) | OMRON |

---

### `mounjaro_dose`
One record per day (injected once weekly).

| Field | Type | Source |
|---|---|---|
| `user_id` | uuid (FK → users) | system |
| `date` | date | manual input |
| `dose_mg` | float | manual input |

---

### `alcohol_consumption`
Multiple entries per day allowed (e.g. beer + wine same night).

| Field | Type | Source |
|---|---|---|
| `user_id` | uuid (FK → users) | system |
| `date` | date | manual input |
| `type` | enum: beer/wine/hard_liquor | manual input |
| `drinks` | int | manual input |

---

### `conversation_history`
| Field | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `user_id` | uuid (FK → users) | scoped per user |
| `session_id` | uuid | groups messages in one conversation |
| `role` | enum: user/assistant | who sent the message |
| `content` | text | message content |
| `created_at` | timestamp | for ordering |

---

### `conversation_summary`
AI-generated rolling summary of conversation history.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `user_id` | uuid (FK → users) | scoped per user |
| `summary` | text | AI-generated rolling summary |
| `covers_from` | date | earliest date this summary covers |
| `covers_to` | date | latest date this summary covers |
| `created_at` | timestamp | when this summary was generated |

---

### `sync_log`
Tracks nightly sync status per date and source. A `success` row also serves as
the per-date fetch coverage marker: it means that date was fetched from the
source, so the cache can be trusted even when the date has no workouts (rest
days). The first run backfill writes one coverage row per date in its range
(flagged `is_backfill`). Today is never marked covered — the day isn't over,
so tools keep fetching it fresh.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | primary key |
| `user_id` | uuid (FK → users) | scoped per user |
| `synced_date` | date | the data date that was synced |
| `synced_at` | timestamp | when the sync ran |
| `source` | enum: strava/apple_health/vesync/omron | which source this row covers — coverage is per source |
| `status` | enum: success/partial/failed | per-source outcome |

---

## System Architecture

```
React Native App (iOS)
        ↓ HTTPS / REST
  FastAPI Backend
  (Auth middleware + API routes + sync handler)
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

**Tools vs sub-agents distinction:**
- Tools (no LLM): Strava, Apple Health, VeSync, OMRON, Manual log — fetch and return data
- Sub-agents (LLM): Summarization, Research — require intelligence to do their job
- Orchestrator (LLM): Claude — decides which tools to call based on the question

---

## Agent Architecture

### Orchestrator
- Model: claude-sonnet-4
- Receives: user message + current session history + rolling summary
- Decides: which tools to call, in what order, for which dates
- Returns: streaming response with visible tool call events
- Context strategy: tiered (see below)

### Tiered context strategy
The orchestrator never loads all conversation history — context is a finite resource.

| Layer | What it is | Always loaded? |
|---|---|---|
| Current session | Messages in this conversation | Yes |
| Rolling summary | AI-compressed summary of last 30 days | Yes |
| Full history | Complete historical conversations | No — research sub-agent fetches on demand |

### Summarization sub-agent
- Triggered: periodically (nightly, after sync completes)
- Job: compress recent conversation history into a rolling summary
- Output: stored in `conversation_summary` table

### Research sub-agent
- Triggered: by orchestrator when question requires historical context
- Job: search conversation history for relevant entries
- Example trigger: "how do I compare to 3 months ago?"
- Output: relevant excerpts returned to orchestrator, not stored

---

## Data Flow

### Nightly sync (primary flow)
```
Device local midnight
        ↓
BGAppRefreshTask fires on iPhone
        ↓
App reads HealthKit → POST /sync to backend (with timezone)
        ↓
Backend fetches: Strava, VeSync, OMRON for yesterday
Backend receives: Apple Health data from device
        ↓
All stored in PostgreSQL
sync_log updated
```

### Catch-up sync (device was off)
```
App open → check sync_log for last synced date
        ↓
If gap > 1 day → fetch external data for each missing date (rate-limited)
        ↓
Manual input NOT requested for missed days (user may not remember accurately)
Missing manual fields remain null permanently
```

### First run backfill
```
On first open → fetch last 90 days from Strava in a single API call →
store each activity in PostgreSQL → write one coverage row per day in the range (through yesterday, flagged is_backfill).
Rate-limiting only applies to sources without date-range support (VeSync,
OMRON) — those fetch one day at a time with a short delay between requests.
Strava, which supports date-range queries, completes in a single call.
```

### Morning check-in flow
```
App open → orchestrator checks for unrated workouts from yesterday
        ↓
Fixed check-in sequence (backend-driven):
  1. Overall feeling
  2. Calories (yesterday)
  3. Alcohol
  4. Mounjaro dose
  5. Workout feelings (conditional — only if unrated workouts exist)
        ↓
Each answer written to PostgreSQL immediately as given
```

### Conversation flow
```
User types question
        ↓
POST /conversation → FastAPI → Orchestrator
        ↓
Orchestrator reasons → calls tools as needed → synthesizes answer
        ↓
Streaming response: token events + tool call events
        ↓
App renders answer + visible tool call progress
```

---

## Sleep Data Rules

Apple Health sleep data requires special handling due to sync timing.

**Sleep fetch window:**
Fetch sleep sessions that started between **8pm two days ago** and ended by
**noon yesterday**, in the user's current timezone.

**Rationale:**
- Handles late sleepers (past midnight)
- Handles timezone changes (Brazil, Europe travel)
- Avoids capturing partial sleep sessions mid-night

**Implementation:** Device sends current timezone with every sync request.
Timezone stored alongside sleep record in `apple_health_daily.timezone`.

---

## API Contracts

### POST /conversation
Main conversational endpoint.

**Request:**
```json
{
  "session_id": "uuid",
  "message": "Why did I feel tired last Tuesday?",
  "timezone": "America/Sao_Paulo"
}
```

**Response (streaming):**
```
data: {"type": "token", "value": "Looking"}
data: {"type": "tool_call", "tool": "strava", "date": "2026-05-26"}
data: {"type": "tool_result", "tool": "strava", "status": "success"}
data: {"type": "token", "value": "Your"}
data: {"type": "done", "session_id": "uuid"}
```

---

### POST /checkin
Morning check-in — one call per answer.

**Request:**
```json
{
  "date": "2026-05-30",
  "field": "overall_feeling",
  "value": "good"
}
```

**Response:**
```json
{
  "status": "saved",
  "next_prompt": "How many calories did you consume yesterday?",
  "field": "calories_previous_day"
}
```

---

### POST /sync
Device-triggered nightly sync.

**Request:**
```json
{
  "timezone": "America/Los_Angeles",
  "last_synced_date": "2026-05-28"
}
```

**Response (streaming):**
```
data: {"type": "progress", "date": "2026-05-29", "source": "strava", "status": "success"}
data: {"type": "progress", "date": "2026-05-29", "source": "vesync", "status": "retrying"}
data: {"type": "progress", "date": "2026-05-29", "source": "vesync", "status": "success"}
data: {"type": "done", "synced_through": "2026-05-29"}
```

---

## Internal Tool Contracts

Tools are Python functions, not HTTP endpoints. Called by the orchestrator via Claude tool use.

### `get_strava_data(date: str) → dict`
```json
{
  "date": "2026-05-27",
  "workouts": [
    {
      "strava_id": "12345",
      "type": "cycling",
      "duration_minutes": 62,
      "distance_km": 28.4,
      "avg_heart_rate": 143,
      "calories": 680,
      "feeling": "strong",
      "feeling_prompted": false
    }
  ]
}
```

### `get_apple_health_data(date: str) → dict`
```json
{
  "date": "2026-05-27",
  "timezone": "America/Los_Angeles",
  "steps": 9832,
  "sleep_hours": 7.2,
  "sleep_deep_minutes": 84,
  "sleep_rem_minutes": 102,
  "sleep_awake_minutes": 18,
  "hrv_ms": 52.4,
  "resting_heart_rate": 58
}
```

### `get_vesync_data(date: str) → dict`
```json
{
  "date": "2026-05-27",
  "weight_kg": 84.2
}
```

### `get_omron_data(date: str) → dict`
```json
{
  "date": "2026-05-27",
  "readings": [
    {
      "systolic": 118,
      "diastolic": 76,
      "pulse": 62,
      "time_of_day": "07:42"
    }
  ]
}
```

### `get_manual_log(date: str) → dict`
```json
{
  "date": "2026-05-27",
  "overall_feeling": "good",
  "calories_previous_day": 2100,
  "notes": "Felt sluggish in the morning",
  "alcohol": [
    {"type": "wine", "drinks": 2}
  ],
  "mounjaro_dose_mg": null
}
```

### `summarize_history(user_id: str, from_date: str, to_date: str) → dict`
```json
{
  "covers_from": "2026-04-01",
  "covers_to": "2026-05-30",
  "summary": "User has been focused on cycling performance and weight loss..."
}
```

### `research_history(user_id: str, query: str) → dict`
```json
{
  "query": "energy levels after Mounjaro injection",
  "relevant_entries": [
    {
      "date": "2026-04-14",
      "excerpt": "User reported low energy day after injection..."
    }
  ]
}
```

---

## Error Handling

**Retry policy:** 3 retries with exponential backoff — 1s, 2s, 4s.

**On final failure:** Silent skip with note to user. Example orchestrator message:
> "Strava data was unavailable for this date. The analysis below is based on
> the remaining sources."

**Missing data:** Tools return null or empty arrays — never errors — for dates
with no data. Orchestrator acknowledges gaps explicitly rather than silently ignoring them.

---

## Authentication

### Phase 1 (current)
- Hardcoded single user — no login required
- `user_id` is a constant in the backend config
- All endpoints unprotected

### Phase 2 (future)
- JWT-based auth
- Google OAuth via authlib
- Login screen in React Native
- All endpoints protected by auth middleware

---

## Multi-user Readiness

`user_id` (FK → users) is present on every data table from day one.
Adding multi-user support requires:
1. Adding authentication (Phase 2)
2. Row-level security in PostgreSQL
3. Scoping all queries by `user_id` (already the pattern)

No data model migrations required.

---

## Key Decisions Log

| Decision | Choice | Rationale |
|---|---|---|
| Primary organizing unit | Day | Questions are day-centric; events within a day aggregate naturally |
| Workout source of truth | Strava only | Eliminates Apple Health deduplication problem |
| Apple Health fields | Steps, sleep stages, HRV, resting HR | Derived from actual questions user will ask |
| Sleep quality | Raw stage data, not enum | Apple's sensor calibration is better than derived scoring |
| Database | PostgreSQL | Multi-user ready, relational, managed on Railway |
| user_id from day one | Yes | Cheap now, expensive to add later |
| Data fetching | Nightly sync job | Proactive, consistent, no cold-start latency on questions |
| Sync trigger | Device local midnight via BGAppRefreshTask | Timezone-aware, consistent with other sources |
| Catch-up sync | Yes, rate-limited | Handles device-off edge case cheaply |
| Manual data for missed days | Not collected | User cannot reliably recall past feelings |
| Morning check-in reference date | Yesterday | User reflects on yesterday during morning check-in |
| Apple Health sync | BGAppRefreshTask (approximate midnight) | Consistent with other sources; exact timing not critical |
| Sleep fetch window | 8pm two days ago → noon yesterday, local TZ | Handles late sleepers and timezone changes |
| Conversation history | Persists forever in PostgreSQL | Needed for longitudinal health questions |
| Context strategy | Tiered: session + summary + on-demand research | Avoids context window overflow on long history |
| Streaming | Yes — conversation and sync | Responsive UX, visible tool call progress |
| Check-in sequence | Fixed, backend-driven | Simpler, consistent, no unnecessary LLM calls |
| Manual inputs write timing | Immediately on each answer | Resilient to interrupted check-ins |
| Error handling | 3 retries + silent skip with note | Resilient for daily-use app |
| Cloud platform | Railway | No cold starts, managed PostgreSQL, simple deploy |
| Auth Phase 1 | Hardcoded single user | Keeps Phase 1 focused on agent learning |
| Cache strategy | Lazy — write on first fetch, never re-fetch past dates | Cache-aside pattern; sync_log success rows mark per-date fetch coverage so empty (rest) days are cached too; today is always fetched fresh |
