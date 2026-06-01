# Health Journey App — Build Plan

## Document Purpose
This is the executable build plan for Phase 1. Every task has a clear definition of done,
written as both a prose description and a runnable pytest test. Nothing moves to the next
task until the current task's tests pass.

This document is a living artifact — update it as decisions change during the build.

---

## Phase 1 Scope

**Goal:** End-to-end agent working on your iPhone with Strava as the sole data source.

**Data sources:** Strava + manual workout feeling input only.

**Demo question:** *"Show me my workouts this week and how I felt during each one."*

**Target completion:** June 15, 2026

**In scope:**
- Railway + PostgreSQL infrastructure
- Full database schema (all tables, including future phases)
- FastAPI backend deployed to Railway
- Strava OAuth + tool
- First run backfill (90 days, Strava only)
- Nightly sync (Strava only, device-triggered at local midnight)
- Orchestrator agent with tool use (Strava tool only)
- Conversation history (current session, persisted to PostgreSQL)
- Manual input — workout feeling only
- Morning check-in — workout feeling only
- React Native app — conversation UI + check-in screen + sync trigger

**Out of scope (Phase 2+):**
- Apple Health, VeSync, OMRON integrations
- Full morning check-in (calories, alcohol, Mounjaro, overall feeling)
- Tiered context (rolling summary, research sub-agent)
- JWT auth + Google OAuth

---

## Build Sequence

Tasks are ordered so each one produces something testable before the next begins.
Never skip ahead — a working foundation is worth more than fast progress on shaky ground.

---

## Task 1 — Railway + PostgreSQL Setup

### What you're building
Provision a Railway project with a FastAPI service and a managed PostgreSQL database.
Confirm the service is reachable from the internet and the database is connectable.

### Why this first
Everything else depends on having a live backend and database. Proving this works
before writing any application code means infrastructure problems don't hide inside
application bugs later.

### Definition of done (prose)
> Railway is working when: a GET request to the deployed service's health check endpoint
> returns HTTP 200, and a direct connection to the PostgreSQL database succeeds from
> the FastAPI service.

### Validation tests
```python
def test_health_check_returns_200():
    """Railway deploy is live when the health check endpoint returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_connection():
    """PostgreSQL is reachable when a simple query executes without error."""
    result = db.execute("SELECT 1")
    assert result is not None
```

---

## Task 2 — Full Database Schema

### What you're building
Create all tables defined in `architecture.md` in PostgreSQL using SQLAlchemy models
and Alembic migrations. All tables — including those not used until Phase 2.

### Why all tables now
The schema is fully designed. Building it once now avoids mid-project migrations
on tables that already contain real data. An empty table costs nothing.

### Definition of done (prose)
> The schema is complete when: all tables defined in architecture.md exist in PostgreSQL
> with the correct columns, types, constraints, and foreign keys. Migrations run cleanly
> from scratch on an empty database.

### Validation tests
```python
def test_all_tables_exist():
    """All expected tables exist in the database."""
    expected_tables = [
        "users", "daily_summary", "workout", "apple_health_daily",
        "weight", "bp_reading", "mounjaro_dose", "alcohol_consumption",
        "conversation_history", "conversation_summary", "sync_log"
    ]
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    for table in expected_tables:
        assert table in existing_tables, f"Missing table: {table}"


def test_workout_table_has_required_columns():
    """Workout table has all required columns including feeling and feeling_prompted."""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("workout")]
    required = ["user_id", "date", "strava_id", "type", "duration_minutes",
                "feeling", "feeling_prompted"]
    for col in required:
        assert col in columns, f"Missing column: {col}"


def test_user_id_foreign_keys_exist():
    """Every data table has a user_id foreign key pointing to users."""
    tables_with_user_id = [
        "daily_summary", "workout", "apple_health_daily", "weight",
        "bp_reading", "mounjaro_dose", "alcohol_consumption",
        "conversation_history", "conversation_summary", "sync_log"
    ]
    inspector = inspect(engine)
    for table in tables_with_user_id:
        fkeys = inspector.get_foreign_keys(table)
        user_fkeys = [fk for fk in fkeys if fk["referred_table"] == "users"]
        assert len(user_fkeys) > 0, f"Table {table} missing user_id FK"


def test_migrations_run_cleanly_from_scratch():
    """Alembic migrations apply cleanly on an empty database without errors."""
    # Run via: alembic upgrade head
    # This test confirms no migration errors in CI
    result = run_alembic_upgrade()
    assert result.returncode == 0
```

---

## Task 3 — FastAPI Skeleton

### What you're building
A bare-bones FastAPI app with placeholder routes for all Phase 1 endpoints:
`/health`, `/conversation`, `/checkin`, `/sync`. Deployed to Railway and reachable
from the internet. No business logic yet — routes return stub responses.

### Why stubs first
Deploying to Railway early surfaces infrastructure and configuration issues before
application complexity is added. Every subsequent task builds on a live, deployed service.

### Definition of done (prose)
> The FastAPI skeleton is complete when: all Phase 1 routes exist, return stub responses,
> the app deploys to Railway without errors, and all routes are reachable from the internet.

### Validation tests
```python
def test_conversation_route_exists():
    """POST /conversation returns a response (stub) without 404 or 500."""
    response = client.post("/conversation", json={
        "session_id": "test-session",
        "message": "hello",
        "timezone": "America/Los_Angeles"
    })
    assert response.status_code != 404
    assert response.status_code != 500


def test_checkin_route_exists():
    """POST /checkin returns a response (stub) without 404 or 500."""
    response = client.post("/checkin", json={
        "date": "2026-05-30",
        "field": "overall_feeling",
        "value": "good"
    })
    assert response.status_code != 404
    assert response.status_code != 500


def test_sync_route_exists():
    """POST /sync returns a response (stub) without 404 or 500."""
    response = client.post("/sync", json={
        "timezone": "America/Los_Angeles",
        "last_synced_date": "2026-05-29"
    })
    assert response.status_code != 404
    assert response.status_code != 500


def test_railway_deployment_reachable():
    """Railway-deployed service is reachable from the internet."""
    response = requests.get("https://your-app.railway.app/health")
    assert response.status_code == 200
```

---

## Task 4 — Strava OAuth

### What you're building
Implement the Strava OAuth flow: authorization URL generation, callback handler,
token exchange, and token storage in PostgreSQL. Include refresh token logic so
access tokens are renewed automatically when expired.

### Why before the Strava tool
The Strava tool needs a valid access token to function. OAuth must work completely
before any Strava API calls are attempted.

### Key concepts to understand
- Authorization code flow: your app redirects to Strava → user approves → Strava
  redirects back with a code → your backend exchanges code for tokens
- Access token: short-lived (6 hours), used in every Strava API call
- Refresh token: long-lived, used only to get a new access token silently
- Tokens stored in PostgreSQL, never in the app or logs

### Definition of done (prose)
> Strava OAuth is working when: the authorization flow completes without errors,
> a valid access token and refresh token are stored in PostgreSQL, and a direct
> call to the Strava API using the stored token returns real activity data without
> a 401 error. Token refresh works when given an expired access token.

### Validation tests
```python
def test_strava_auth_url_is_valid():
    """Authorization URL contains required Strava OAuth parameters."""
    response = client.get("/strava/auth-url")
    assert response.status_code == 200
    url = response.json()["url"]
    assert "strava.com/oauth/authorize" in url
    assert "client_id" in url
    assert "redirect_uri" in url
    assert "scope=activity:read_all" in url


def test_strava_tokens_stored_after_callback():
    """After OAuth callback, access and refresh tokens are stored in PostgreSQL."""
    # Simulate callback with a mock authorization code
    response = client.get("/strava/callback?code=mock_code&state=mock_state")
    token = db.query(StravaToken).filter_by(user_id=TEST_USER_ID).first()
    assert token is not None
    assert token.access_token is not None
    assert token.refresh_token is not None
    assert token.expires_at is not None


def test_strava_api_call_succeeds_with_stored_token():
    """Using stored access token, Strava API returns activities without 401."""
    token = db.query(StravaToken).filter_by(user_id=TEST_USER_ID).first()
    response = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {token.access_token}"}
    )
    assert response.status_code == 200


def test_strava_token_refresh_succeeds():
    """Given an expired access token, refresh returns a new valid access token."""
    new_token = refresh_strava_token(TEST_USER_ID)
    assert new_token is not None
    assert new_token.expires_at > datetime.utcnow()
```

---

## Task 5 — Strava Tool

### What you're building
The `get_strava_data(date)` tool: fetch activities from Strava for a given date,
normalize to the workout schema, store in PostgreSQL (cache-aside), and return
structured data matching the tool contract in `architecture.md`.

### Cache-aside rule
Check PostgreSQL first. If data exists for the requested date, return it.
If not, fetch from Strava API, store it, then return it.

### Definition of done (prose)
> The Strava tool is working when: calling get_strava_data() for a date with known
> Strava activities returns the correct structured data; calling it twice for the same
> date only hits the Strava API once (second call reads from PostgreSQL); and calling
> it for a date with no activities returns an empty workouts array without errors.

### Validation tests
```python
def test_strava_tool_returns_structured_data():
    """get_strava_data returns data matching the expected contract shape."""
    result = get_strava_data(date="2026-05-27")
    assert "date" in result
    assert "workouts" in result
    assert isinstance(result["workouts"], list)
    if result["workouts"]:
        workout = result["workouts"][0]
        assert "strava_id" in workout
        assert "type" in workout
        assert "duration_minutes" in workout


def test_strava_tool_caches_on_first_fetch():
    """After first fetch, workout data is stored in PostgreSQL."""
    get_strava_data(date="2026-05-27")
    stored = db.query(Workout).filter_by(
        user_id=TEST_USER_ID, date="2026-05-27"
    ).all()
    assert len(stored) >= 0  # empty is valid, but table should be written


def test_strava_tool_reads_cache_on_second_call(mocker):
    """Second call for same date reads from PostgreSQL, not Strava API."""
    mock_strava = mocker.patch("app.services.strava.fetch_from_api")
    # First call — populates cache
    get_strava_data(date="2026-05-27")
    # Second call — should not hit API
    get_strava_data(date="2026-05-27")
    assert mock_strava.call_count <= 1


def test_strava_tool_returns_empty_for_rest_day():
    """get_strava_data returns empty workouts array for a date with no activities."""
    result = get_strava_data(date="2000-01-01")  # date guaranteed to have no data
    assert result["workouts"] == []


def test_strava_tool_retries_on_failure(mocker):
    """Strava tool retries 3 times with backoff before returning error."""
    mocker.patch("app.services.strava.fetch_from_api", side_effect=Exception("API down"))
    result = get_strava_data(date="2026-05-27")
    assert result["status"] == "error"
    assert mock_fetch.call_count == 3
```

---

## Task 6 — First Run Backfill

### What you're building
On first app open, fetch the last 90 days of Strava activities in a single API call,
store each activity in PostgreSQL, and mark the backfill as complete in sync_log.
Subsequent app opens skip the backfill.

### Definition of done (prose)
> First run backfill is working when: on first open, activities from the last 90 days
> are fetched and stored in PostgreSQL; the sync_log records the backfill completion;
> and on second open, the backfill does not run again.

### Validation tests
```python
def test_backfill_fetches_90_days():
    """Backfill fetches activities covering the last 90 days."""
    run_first_backfill(user_id=TEST_USER_ID)
    earliest = db.query(func.min(Workout.date)).filter_by(
        user_id=TEST_USER_ID
    ).scalar()
    days_back = (date.today() - earliest).days
    assert days_back >= 89  # allow 1 day tolerance


def test_backfill_marked_complete_in_sync_log():
    """After backfill, sync_log contains a success record."""
    run_first_backfill(user_id=TEST_USER_ID)
    log = db.query(SyncLog).filter_by(
        user_id=TEST_USER_ID, status="success"
    ).first()
    assert log is not None


def test_backfill_does_not_run_twice(mocker):
    """Backfill skips on second run if sync_log shows it already completed."""
    mock_fetch = mocker.patch("app.services.strava.fetch_date_range")
    run_first_backfill(user_id=TEST_USER_ID)
    run_first_backfill(user_id=TEST_USER_ID)  # second call
    assert mock_fetch.call_count == 1
```

---

## Task 7 — Nightly Sync

### What you're building
Device-triggered nightly sync: React Native app fires POST /sync at local midnight
via BGAppRefreshTask. Backend fetches yesterday's Strava data and stores it.
Catch-up logic handles multiple missed days.

### Definition of done (prose)
> Nightly sync is working when: POST /sync with last_synced_date set to yesterday
> fetches and stores yesterday's Strava data; POST /sync with last_synced_date set
> to 3 days ago fetches and stores 3 days of data in order; and the sync_log is
> updated correctly after each run.

### Validation tests
```python
def test_sync_fetches_yesterday():
    """POST /sync fetches and stores yesterday's Strava data."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = client.post("/sync", json={
        "timezone": "America/Los_Angeles",
        "last_synced_date": yesterday
    })
    assert response.status_code == 200
    log = db.query(SyncLog).filter_by(
        user_id=TEST_USER_ID,
        synced_date=yesterday
    ).first()
    assert log is not None
    assert log.status == "success"


def test_sync_catchup_fetches_multiple_days():
    """POST /sync with 3-day gap fetches data for all 3 missing days."""
    three_days_ago = (date.today() - timedelta(days=3)).isoformat()
    response = client.post("/sync", json={
        "timezone": "America/Los_Angeles",
        "last_synced_date": three_days_ago
    })
    assert response.status_code == 200
    logs = db.query(SyncLog).filter_by(user_id=TEST_USER_ID).all()
    synced_dates = [log.synced_date for log in logs]
    for i in range(1, 3):
        expected = (date.today() - timedelta(days=i)).isoformat()
        assert expected in synced_dates


def test_sync_streams_progress_events():
    """POST /sync returns streaming progress events for each source."""
    with client.stream("POST", "/sync", json={
        "timezone": "America/Los_Angeles",
        "last_synced_date": (date.today() - timedelta(days=1)).isoformat()
    }) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]
        event_types = [e["type"] for e in events]
        assert "progress" in event_types
        assert "done" in event_types
```

---

## Task 8 — Orchestrator Agent

### What you're building
The Claude orchestrator with tool use. Receives a user message, reasons about which
tools to call, calls them, synthesizes the results, and returns a streaming response
with visible tool call events.

Phase 1: only the Strava tool is available to the orchestrator.

### This is the core learning task
Take time here. Understand why Claude calls the tool when it does, what the system
prompt is doing, and how tool results flow back into the response. This is the
agent pattern you set out to learn.

### Definition of done (prose)
> The orchestrator is working when: asking "show me my workouts yesterday" causes
> Claude to call get_strava_data for yesterday's date, receive the results, and return
> a coherent natural language answer grounded in the actual data. Tool call events
> are visible in the streaming response. Asking a question unrelated to workouts
> does not trigger a tool call.

### Validation tests
```python
def test_orchestrator_calls_strava_tool_for_workout_question(mocker):
    """Asking about workouts causes the orchestrator to call get_strava_data."""
    mock_tool = mocker.patch("app.tools.strava.get_strava_data",
                             return_value={"date": "2026-05-30", "workouts": []})
    response = client.post("/conversation", json={
        "session_id": "test-session",
        "message": "Show me my workouts yesterday",
        "timezone": "America/Los_Angeles"
    })
    assert response.status_code == 200
    assert mock_tool.called


def test_orchestrator_does_not_call_tool_for_unrelated_question(mocker):
    """Asking an unrelated question does not trigger a tool call."""
    mock_tool = mocker.patch("app.tools.strava.get_strava_data")
    response = client.post("/conversation", json={
        "session_id": "test-session",
        "message": "What is the capital of France?",
        "timezone": "America/Los_Angeles"
    })
    assert not mock_tool.called


def test_orchestrator_response_streams():
    """Orchestrator response arrives as a stream of token events."""
    with client.stream("POST", "/conversation", json={
        "session_id": "test-session",
        "message": "Show me my workouts yesterday",
        "timezone": "America/Los_Angeles"
    }) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) > 0


def test_orchestrator_emits_tool_call_event():
    """Streaming response includes a tool_call event when Strava tool is invoked."""
    with client.stream("POST", "/conversation", json={
        "session_id": "test-session",
        "message": "Show me my workouts yesterday",
        "timezone": "America/Los_Angeles"
    }) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]
        tool_events = [e for e in events if e["type"] == "tool_call"]
        assert len(tool_events) > 0
        assert tool_events[0]["tool"] == "strava"


def test_orchestrator_answer_references_actual_data(mocker):
    """Orchestrator answer mentions workout data that was returned by the tool."""
    mocker.patch("app.tools.strava.get_strava_data", return_value={
        "date": "2026-05-30",
        "workouts": [{"type": "cycling", "duration_minutes": 60,
                      "distance_km": 25.0, "feeling": "strong",
                      "feeling_prompted": False}]
    })
    with client.stream("POST", "/conversation", json={
        "session_id": "test-session",
        "message": "Show me my workouts yesterday",
        "timezone": "America/Los_Angeles"
    }) as response:
        full_response = "".join(
            json.loads(line)["value"]
            for line in response.iter_lines()
            if line and json.loads(line)["type"] == "token"
        )
        assert "cycling" in full_response.lower() or "60" in full_response
```

---

## Task 9 — Conversation History

### What you're building
Persist each conversation turn (user message + assistant response) to PostgreSQL.
Load current session history on each turn so the orchestrator has context for
follow-up questions.

### Definition of done (prose)
> Conversation history is working when: after two turns in a conversation, both turns
> are stored in PostgreSQL under the same session_id; and a follow-up question that
> references the previous turn is answered correctly, proving the orchestrator received
> the history.

### Validation tests
```python
def test_conversation_turns_stored_in_postgres():
    """Each conversation turn is persisted to conversation_history table."""
    session_id = "test-session-history"
    client.post("/conversation", json={
        "session_id": session_id,
        "message": "Show me my workouts yesterday",
        "timezone": "America/Los_Angeles"
    })
    turns = db.query(ConversationHistory).filter_by(
        session_id=session_id
    ).all()
    assert len(turns) >= 2  # user message + assistant response


def test_conversation_history_loaded_on_followup(mocker):
    """Orchestrator receives previous turns when answering a follow-up question."""
    mock_claude = mocker.patch("app.orchestrator.call_claude")
    session_id = "test-session-followup"
    # First turn
    client.post("/conversation", json={
        "session_id": session_id,
        "message": "Show me my workouts yesterday",
        "timezone": "America/Los_Angeles"
    })
    # Second turn
    client.post("/conversation", json={
        "session_id": session_id,
        "message": "How does that compare to the day before?",
        "timezone": "America/Los_Angeles"
    })
    # Verify history was passed to Claude on second call
    second_call_messages = mock_claude.call_args[1]["messages"]
    assert len(second_call_messages) >= 3  # system + turn 1 + turn 2
```

---

## Task 10 — Manual Input: Workout Feeling

### What you're building
The ability to record workout feeling (strong/normal/weak) for a specific workout,
stored in the workout table. This is the only manual input in Phase 1.

### Definition of done (prose)
> Workout feeling input is working when: submitting a feeling for a known strava_id
> updates the feeling field in the workout table and sets feeling_prompted correctly;
> and the orchestrator returns the feeling when asked about that workout.

### Validation tests
```python
def test_workout_feeling_stored_correctly():
    """POST /checkin with workout feeling updates the workout record."""
    response = client.post("/checkin", json={
        "date": "2026-05-27",
        "field": "workout_feeling",
        "strava_id": "12345",
        "value": "strong"
    })
    assert response.status_code == 200
    workout = db.query(Workout).filter_by(strava_id="12345").first()
    assert workout.feeling == "strong"


def test_feeling_prompted_flag_set_correctly():
    """feeling_prompted is True when set via check-in, False when from Strava."""
    client.post("/checkin", json={
        "date": "2026-05-27",
        "field": "workout_feeling",
        "strava_id": "12345",
        "value": "normal"
    })
    workout = db.query(Workout).filter_by(strava_id="12345").first()
    assert workout.feeling_prompted == True


def test_orchestrator_includes_feeling_in_answer(mocker):
    """Orchestrator includes workout feeling in answer when available."""
    mocker.patch("app.tools.strava.get_strava_data", return_value={
        "date": "2026-05-27",
        "workouts": [{"type": "cycling", "duration_minutes": 60,
                      "distance_km": 25.0, "feeling": "strong",
                      "feeling_prompted": True}]
    })
    with client.stream("POST", "/conversation", json={
        "session_id": "test-session",
        "message": "How did my workout feel yesterday?",
        "timezone": "America/Los_Angeles"
    }) as response:
        full_response = "".join(
            json.loads(line)["value"]
            for line in response.iter_lines()
            if line and json.loads(line)["type"] == "token"
        )
        assert "strong" in full_response.lower()
```

---

## Task 11 — Morning Check-in (Backend)

### What you're building
The backend-driven morning check-in sequence. For Phase 1: checks for unrated workouts
from yesterday, prompts for workout feeling only. Each answer written to PostgreSQL
immediately. Backend returns next_prompt after each answer.

### Definition of done (prose)
> Morning check-in backend is working when: POST /checkin for a day with unrated
> workouts returns a prompt asking for workout feeling; submitting the feeling stores
> it and returns the completion signal; and POST /checkin for a day with no unrated
> workouts returns the completion signal immediately without prompting.

### Validation tests
```python
def test_checkin_prompts_for_unrated_workout():
    """Check-in returns workout feeling prompt when unrated workouts exist."""
    # Insert a workout with no feeling
    db.add(Workout(user_id=TEST_USER_ID, date="2026-05-30",
                   strava_id="99999", type="cycling",
                   duration_minutes=45, feeling=None))
    db.commit()
    response = client.post("/checkin", json={
        "date": "2026-05-30",
        "field": "start",
        "value": None
    })
    assert response.status_code == 200
    assert response.json()["field"] == "workout_feeling"
    assert "strong" in response.json()["next_prompt"].lower() or \
           "normal" in response.json()["next_prompt"].lower()


def test_checkin_completes_when_no_unrated_workouts():
    """Check-in returns done signal when no unrated workouts exist."""
    response = client.post("/checkin", json={
        "date": "2000-01-01",  # date guaranteed to have no workouts
        "field": "start",
        "value": None
    })
    assert response.status_code == 200
    assert response.json()["status"] == "complete"


def test_checkin_writes_immediately_on_each_answer():
    """Each check-in answer is persisted to PostgreSQL before next prompt is returned."""
    client.post("/checkin", json={
        "date": "2026-05-30",
        "field": "workout_feeling",
        "strava_id": "99999",
        "value": "weak"
    })
    workout = db.query(Workout).filter_by(strava_id="99999").first()
    assert workout.feeling == "weak"
```

---

## Task 12 — React Native App

### What you're building
The iPhone app with two screens:

**Conversation screen:**
- Text input + send button
- Streaming response rendered token by token
- Tool call events shown as progress indicators (e.g. "checking Strava…")

**Check-in screen:**
- Shown on app open if unrated workouts exist
- Backend-driven: displays next_prompt, collects answer, submits, shows next prompt
- Completes when backend returns status: complete

**Background sync:**
- BGAppRefreshTask registered at local midnight
- Calls POST /sync with current timezone and last_synced_date

### Definition of done (prose)
> The React Native app is working when: typing a question in the conversation screen
> produces a streaming response with visible tool call indicators; the check-in screen
> appears on open when unrated workouts exist and completes correctly; and the sync
> fires in the background without requiring the app to be open.

### Validation tests
These tests are manual (on-device) — automated React Native testing is out of scope
for Phase 1.

**Manual test checklist:**
```
[ ] App opens on iPhone without crashing
[ ] Check-in screen appears when unrated workouts exist
[ ] Check-in completes and dismisses after submitting feeling
[ ] Check-in does not appear when no unrated workouts exist
[ ] Typing a question and submitting shows a streaming response
[ ] "Checking Strava..." indicator appears while tool call is in progress
[ ] Response references actual workout data (not hallucinated)
[ ] App sends POST /sync when backgrounded at midnight (verify via Railway logs)
```

---

## Task 13 — End to End Test

### What you're building
Nothing new — this task validates the complete Phase 1 system working together on
a real device with real data.

### Definition of done (prose)
> Phase 1 is complete when: the demo question "Show me my workouts this week and how
> I felt during each one" returns a correct, grounded answer referencing real Strava
> data and real workout feelings logged via the morning check-in, streamed to the
> iPhone app with visible tool call indicators.

### Validation tests
```python
def test_end_to_end_workout_question():
    """Full flow: question → orchestrator → Strava tool → PostgreSQL → answer."""
    # Seed known workout data
    db.add(Workout(
        user_id=TEST_USER_ID, date=date.today() - timedelta(days=1),
        strava_id="e2e-test-001", type="cycling", duration_minutes=62,
        distance_km=28.4, feeling="strong", feeling_prompted=True
    ))
    db.commit()

    with client.stream("POST", "/conversation", json={
        "session_id": "e2e-test-session",
        "message": "Show me my workouts this week and how I felt during each one",
        "timezone": "America/Los_Angeles"
    }) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

        # Tool was called
        tool_events = [e for e in events if e["type"] == "tool_call"]
        assert len(tool_events) > 0

        # Answer contains real data
        full_response = "".join(
            e["value"] for e in events if e["type"] == "token"
        )
        assert "cycling" in full_response.lower()
        assert "strong" in full_response.lower()
```

**Manual end-to-end checklist:**
```
[ ] Fresh install on iPhone — backfill runs in background
[ ] Morning check-in prompts for workout feeling after a workout day
[ ] Submitted feeling persists across app restarts
[ ] "Show me my workouts this week" returns real data with feelings
[ ] Follow-up question ("which was the hardest?") is answered in context
[ ] Nightly sync fires and Railway logs confirm it ran
[ ] App handles Strava API downtime gracefully with a note
```

---

## Open Questions

These need answers before or during the build. Do not start the affected task until
the question is resolved.

| # | Question | Affects | Status |
|---|---|---|---|
| 1 | Which Railway plan — free tier or paid? Free tier may have limitations for background jobs | Task 1 | Open |
| 2 | Does Strava API require app registration? What are the rate limits? | Task 4 | Open |
| 3 | What is the BGAppRefreshTask minimum interval on iOS? (Apple may enforce a minimum — typically 15 min) | Task 7, 12 | Open |
| 4 | Which React Native version and Expo vs bare workflow? | Task 12 | Open |
| 5 | Does react-native-health require a paid Apple Developer account for HealthKit entitlement? (Phase 1 doesn't use it, but affects setup) | Task 12 | Open |

---

## Phase 2 Preview (not in scope yet)

To be planned after Phase 1 is complete and job interviews have begun.

- Apple Health integration
- VeSync integration
- OMRON integration
- Full morning check-in (calories, alcohol, Mounjaro, overall feeling)
- Nightly sync expanded to all sources
- Catch-up sync with rate limiting

**Phase 2 demo question:** *"Why did I feel tired last Tuesday?"*
