# LearnSelfAI

A small student learning progress tracker with an integrated AI tutor. Built as a take
home evaluation covering: (1) a progress tracking feature, (2) an AI powered learning
assistant, and (3) this write up.

**Live demo:** _add Render URL here after deploying_
**Repo:** _add GitHub URL here_

## Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy, SQLite
- **Frontend**: plain HTML, CSS, vanilla JS (no build step, calls the JSON API directly)
- **AI**: pluggable provider layer. Google Gemini or Groq (both free tier) or Anthropic
  Claude (paid), with an offline mock fallback so the assistant works even with no API
  key configured, or if a configured provider's quota is exhausted
- **Tests**: pytest + FastAPI's `TestClient`
- **Deploy**: Render (`render.yaml`)

## Running locally

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# optional, without this the AI tutor uses an offline mock provider
cp ../.env.example ../.env
# edit .env and set GROQ_API_KEY=... (free, from console.groq.com/keys)

uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The SQLite database is created and seeded automatically on
first run with a demo student and a "Python Fundamentals" course (5 lessons).

Run tests:

```bash
cd backend
pytest
```

## Feature 1: Learning Progress

- `GET /api/courses` returns the course, its lessons, and per lesson completion status.
- `POST /api/progress/{lesson_id}/complete` toggles a lesson complete or incomplete.
- `GET /api/progress/summary` computes overall percent complete, per course percent, and
  a **day streak** (consecutive calendar days with at least one lesson completed).
- The frontend shows a progress bar, streak counter, and a checkable lesson list.

Progress is computed on read directly from the `progress` table rather than cached,
since the dataset is tiny. That's the simplest correct thing that could work.

## Feature 2: AI Learning Assistant

- `POST /api/assistant/chat` takes a message and an optional `lesson_id`. It loads
  recent chat history for that lesson plus the lesson's summary and the student's
  overall progress percent, builds a system prompt grounding the tutor in that context,
  and calls the configured AI provider.
- `GET /api/assistant/history` returns persisted chat history so conversations survive
  a page reload.
- **Provider abstraction** (`backend/app/ai/provider.py`): `get_provider()` checks env
  vars in priority order: `ANTHROPIC_API_KEY` (paid), then `GEMINI_API_KEY` (free,
  Google AI Studio), then `GROQ_API_KEY` (free, fast open model inference), otherwise a
  `MockProvider` that still produces context aware (not just canned) replies
  referencing the active lesson's title and summary, so the feature is fully demoable
  with zero configuration. Swapping in a real key requires no code change.
- **Resilient at request time**: if the configured provider's call fails (for example a
  free tier daily quota is exhausted), the chat endpoint catches the error and falls
  back to the mock provider for that reply instead of returning a 500, tagging the
  response `provider: "mock-fallback"` so it's visible in the API response which path
  was used.
- Selecting a lesson in the UI scopes the chat to that lesson, so the assistant can say
  things like "Since you're working through Loops...".

## Task 3: Approach, challenges, improvements

**Approach.** I treated this as two thin, well separated features sharing one data
model. Progress tracking is pure CRUD over a `Progress` table. The AI assistant reads
from that same model (current lesson, overall percent) to ground its replies, so it's
not a generic chatbot bolted onto the side. I prioritized a working vertical slice
(seeded data, real persistence, a UI you can click through) over auth, multi user
support, or visual polish, since the brief explicitly weights functional
implementation and reasoning over UI. FastAPI, SQLite, and vanilla JS were chosen
specifically to minimize setup friction (no build step, no external database) so the
reviewer can run it in one command.

**Key decisions worth explaining:**
- *No auth, single demo student.* Multi user auth is a solved, well understood problem
  that would have consumed a disproportionate share of the time budget for a demo, so
  I scoped it out explicitly rather than half implementing it.
- *Provider abstraction with a mock fallback, supporting free tier APIs.* I didn't have
  an API key on hand when I started, so I built the assistant against an interface
  (`AIProvider.reply(...)`) rather than any one vendor's SDK. When testing with a real
  key, Gemini's free tier quota was hit almost immediately, so beyond just supporting
  multiple providers, the chat endpoint catches provider errors at request time and
  transparently falls back to the mock for that single reply rather than surfacing a
  500 to the student. This mirrors a real product concern: free or cheap tier AI
  features need graceful degradation, not just a happy path integration.
- *Streak and percent computed on read, not stored.* At this scale (one student, a
  handful of lessons) a derived value recomputed per request is simpler and can't
  drift out of sync with the underlying `Progress` rows. A cached counter would be
  premature.

**Challenges.**
- Grounding the AI response in the *right* amount of context: too little and it's a
  generic chatbot, too much (for example dumping full lesson content) burns tokens and
  can drown the actual question. I settled on a short `content_summary` per lesson
  plus the running conversation and overall percent, enough for the tutor to sound
  situated without needing a retrieval layer.
- Making the mock provider actually useful rather than a stub. Since the assistant is
  one of two graded features, I wanted it to be evaluable even with no key, so the
  mock provider inspects the message and lesson context to produce a relevant sounding
  reply instead of a static string.

**What I'd improve with more time.**
- Real multi user auth (sessions or JWT) instead of a single hardcoded demo student.
- Streaming responses from the AI endpoint (SSE) instead of a single blocking call,
  for a more natural chat feel.
- Retrieval over actual lesson content (not just a one line summary) if lessons grew
  beyond toy sized text, for example embedding lesson content and retrieving relevant
  chunks.
- Richer progress analytics: time spent per lesson, quiz or check for understanding
  scores feeding back into what the AI tutor emphasizes, spaced repetition style
  nudges ("you haven't touched Loops in 5 days").
- Postgres instead of SQLite once there's more than one concurrent user. SQLite's
  single writer model is fine for a demo but not for production concurrency.

## AI tools & libraries used

- **Claude Code**: used as a development assistant while building this project
  (planning, implementation, and this write up).
- **Anthropic Claude API** (`anthropic` Python SDK): powers the AI Learning Assistant
  when `ANTHROPIC_API_KEY` is set.
- **FastAPI, SQLAlchemy, Pydantic, Uvicorn, pytest**: backend framework and tooling.
- Plain HTML, CSS, JS: no frontend framework or build tooling used.
