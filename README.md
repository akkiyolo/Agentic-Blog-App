# Agentic Blog App

A production-grade blog application built with **FastAPI**, extended into an **agentic
platform**: posts are auto-tagged and summarized on publish, a **LangGraph** multi-step
agent drafts new posts by researching the author's own blog and the live web, and readers
can ask questions directly against a post's content — all backed by JWT auth, PostgreSQL,
AWS S3 media storage, server-rendered Jinja2 pages, and a real test suite.

## Features

### Core blogging platform
- **User authentication** — registration, login, and session handling via JWT (`pyjwt`) with Argon2 password hashing (`pwdlib`)
- **Password reset flow** — email-based reset links with expiring tokens
- **Blog posts** — create, view, and browse posts with pagination (`posts_per_page`), author info, and per-user post listings
- **Profile pictures / media uploads** — image handling via `Pillow`, stored on **AWS S3** (`boto3`), with configurable upload size limits
- **Server-rendered UI** — Jinja2 templates for home, post, login, register, account, and password reset pages, alongside a JSON API
- **Security hardening** — middleware enforcing `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and HSTS (in production)
- **Health check endpoint** — `/health` verifies database connectivity
- **Database migrations** — schema versioning via `Alembic`
- **Async everything** — `SQLAlchemy` (async) + `psycopg` (async PostgreSQL driver)
- **Automated tests** — `pytest` with `moto` for mocking S3, and mocked LLMs for deterministic agent tests

### Agentic features
- **Auto-tagging agent** — on every post create/update, a background job generates tags, a summary, and an SEO meta description via Gemini (`gemini-2.5-flash`), with retry + rate limiting, crash-recovery (stuck jobs are requeued on startup), and a manual retry endpoint for the post owner.
- **Draft-assist agent** — a multi-step **LangGraph** agent: give it a topic, and it fans out to research your own past posts (keyword search) *and* the live web (Tavily) in parallel, merges the findings, generates an outline, and drafts a full post. Supports feedback-driven revision (skips re-research on revise) and is fully human-in-the-loop — nothing is published until you review and hit **Publish**, which reuses the normal post-creation flow (and triggers auto-tagging).
- **Reader Q&A agent** — any reader can ask a question about a specific post and get an answer grounded strictly in that post's content, with short conversational memory and a per-IP rate limiter since the endpoint is unauthenticated.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI |
| Database | PostgreSQL (via async SQLAlchemy 2.x + psycopg3) |
| Migrations | Alembic |
| Auth | JWT (PyJWT) + Argon2 (pwdlib) |
| Storage | AWS S3 (boto3) |
| Templating | Jinja2 |
| Image processing | Pillow |
| Email | aiosmtplib |
| Config | pydantic-settings |
| Agent orchestration | LangGraph |
| LLM | Google Gemini (`langchain-google-genai`) |
| Web research | Tavily (`tavily-python`) |
| Resilience | tenacity (retry + backoff) |
| Testing | pytest, moto, mocked LLMs |
| Package management | uv |

## Project Structure

```
Agentic-Blog-App/
├── agents/                 # LangGraph / LLM agents
│   ├── tagging_agent.py    # Auto-tagging: tags, summary, meta description
│   ├── draft_agent.py      # Draft-assist: research -> outline -> draft (LangGraph)
│   └── qa_agent.py         # Reader Q&A: single-post grounded answering
├── alembic/                # Database migration scripts
├── media/profile_pics/     # Local media storage (dev)
├── populate_images/        # Seed images for populate_db.py
├── routers/                # API route modules (users, posts, drafts)
├── static/                 # CSS/JS/static assets
├── templates/              # Jinja2 HTML templates (incl. draft_assist.html)
├── tests/                  # Test suite (incl. agent unit + router tests)
├── auth.py                 # Authentication & JWT logic
├── check_s3.py              # S3 connectivity check script
├── config.py                # App settings (pydantic-settings)
├── database.py               # Async DB engine & session setup
├── email_utils.py            # Email sending helpers
├── image_utils.py            # Image processing/upload helpers
├── main.py                   # FastAPI app entrypoint, page routes, startup sweep
├── models.py                  # SQLAlchemy ORM models
├── populate_db.py              # DB seeding script
├── rate_limit.py                # In-memory sliding-window rate limiter (Q&A agent)
├── schemas.py                    # Pydantic schemas
├── alembic.ini                    # Alembic configuration
├── pyproject.toml                  # Project dependencies
└── uv.lock                          # Locked dependency versions
```

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL database
- AWS S3 bucket (or S3-compatible storage) for media uploads
- A Google AI Studio API key (for Gemini) — required for all three agents
- A Tavily API key — required only for the draft-assist agent's web research step
- [uv](https://docs.astral.sh/uv/) package manager

### 1. Clone the repository

```bash
git clone https://github.com/akkiyolo/Agentic-Blog-App.git
cd Agentic-Blog-App
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/blogdb
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

S3_BUCKET_NAME=your-bucket-name
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=your-access-key-id
S3_SECRET_ACCESS_KEY=your-secret-access-key
S3_ENDPOINT_URL=

MAX_UPLOAD_SIZE_BYTES=5242880
POSTS_PER_PAGE=10
RESET_TOKEN_EXPIRE_MINUTES=60

MAIL_SERVER=localhost
MAIL_PORT=587
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=noreply@example.com
MAIL_USE_TLS=true

FRONTEND_URL=http://localhost:8000

# --- Agentic features ---
# Both are optional at startup — the app boots fine without them, but the
# relevant agent endpoints will raise a clear "not configured" error until set.
GOOGLE_API_KEY=your-gemini-api-key
TAVILY_API_KEY=your-tavily-api-key
```

### 4. Run database migrations

```bash
uv run alembic upgrade head
```

### 5. (Optional) Seed sample data

```bash
uv run python populate_db.py
```

### 6. Start the development server

```bash
uv run fastapi dev main.py
```

The app will be available at `http://localhost:8000`, with interactive API docs at `http://localhost:8000/docs`.

## Testing

Run the test suite with:

```bash
uv run pytest
```

- S3 interactions are mocked using `moto`, so no live AWS credentials are needed.
- All three agents' LLM calls are mocked by default via an autouse fixture, so the suite runs without a real `GOOGLE_API_KEY`/`TAVILY_API_KEY` and without network access. Tests that need to exercise the *real* "not configured" code paths opt out explicitly with `@pytest.mark.no_mock_llm`.
- Retry/backoff behavior is tested directly (transient failure → recovery, and exhausted-retries → propagated error) with `tenacity`'s wait strategy patched to zero so the suite stays fast.

## API Overview

| Route prefix | Description |
|---|---|
| `/api/users` | User registration, login, profile, password reset |
| `/api/posts` | Create, read, update, delete posts; retag; ask a question about a post |
| `/api/drafts` | Generate and revise AI-assisted post drafts |
| `/health` | Database health check |
| `/`, `/posts`, `/posts/{id}`, `/users/{id}/posts`, `/draft-assist` | Server-rendered pages |
| `/login`, `/register`, `/account`, `/forgot-password`, `/reset-password` | Auth-related pages |

Full interactive API documentation is available at `/docs` (Swagger UI) once the server is running.

### Agent endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `POST /api/posts/{id}/retag` | Post owner | Manually re-run the auto-tagging agent |
| `POST /api/drafts/generate` | Logged in | `{topic}` → researched, outlined, drafted post |
| `POST /api/drafts/revise` | Logged in | `{topic, feedback, previous_*}` → revised draft (skips re-research) |
| `POST /api/posts/{id}/ask` | Public, rate-limited | `{question, chat_history}` → answer grounded in that post |

## How the agents work

### Auto-tagging agent
Runs as a `BackgroundTask` after every post create/update, calling Gemini with structured output (`PostMetadata`) to produce tags, a summary, and a meta description. Wrapped in `tenacity` retry with exponential backoff and a concurrency-limiting semaphore. Since `BackgroundTasks` don't survive a crash or redeploy mid-generation, the app's `lifespan` startup hook requeues any post left in `pending`/`failed` state — see `requeue_stuck_tagging_jobs()` in `main.py`.

### Draft-assist agent (LangGraph)
```
START ─┬─→ research_posts ─┐
       └─→ research_web  ──┴─→ merge_research → outline → draft → END
```
- `research_posts` and `research_web` run as parallel graph nodes — the former does a keyword search over the author's own posts (a placeholder for real semantic retrieval, see Roadmap), the latter calls Tavily.
- On a **revision** request (feedback on an existing draft), the graph takes a conditional shortcut straight to `draft`, skipping research and outline regeneration — cheaper and faster, and preserves what the author already approved.
- Nothing is auto-published: the frontend (`/draft-assist`) shows an editable review panel, and the existing `POST /api/posts` endpoint is reused to actually publish — which in turn kicks off the auto-tagging agent automatically.

### Reader Q&A agent
A single grounded LLM call per question — no retrieval needed since the context is one post. Answers are constrained to the post's own content via the system prompt, with a short rolling chat history for follow-ups. Public and unauthenticated by design (readers shouldn't need an account to ask a question), which is exactly why it's the one agent with an explicit rate limiter (`rate_limit.py`, in-memory sliding window, documented as needing to move to Redis if the app ever runs multi-instance).

## Design decisions

- **BackgroundTasks over Celery/Redis, for now.** At this scale, a task queue would add operational surface area without a corresponding benefit — the startup-sweep pattern already gives crash recovery. This is a call I'd revisit the moment tagging volume or latency requirements changed.
- **Keyword search before vector search.** `research_posts` uses `ILIKE` matching rather than embeddings — correct for a handful of posts, and deliberately structured so it can be swapped for a pgvector similarity search as a drop-in replacement for that one graph node once a full RAG pipeline exists, without touching the rest of the graph.
- **Revision skips research.** Re-running Tavily/DB search on every small wording tweak would be slower and more expensive for no quality gain — the graph's conditional entry point routes revisions straight to the `draft` node with the existing outline.
- **Optional API keys, not required ones.** `GOOGLE_API_KEY`/`TAVILY_API_KEY` are optional in `config.py` so the app (and the rest of the test suite) doesn't fail to boot just because one agent's credentials aren't configured yet — each agent raises a specific, catchable error only when actually invoked without its key.

## Security Notes

- All responses include `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy` headers.
- HSTS is enforced automatically outside of local development (`localhost`/`127.0.0.1`).
- Password reset pages set `Referrer-Policy: no-referrer` to avoid leaking reset tokens via the `Referer` header.
- The public, unauthenticated Q&A endpoint is rate-limited per IP to bound LLM API cost exposure.

## Roadmap

- Replace `research_posts`' keyword search with pgvector-backed semantic retrieval, shared as a corpus-wide "chat with the blog" RAG feature.
- LangSmith tracing across all three agents (latency, token usage, retrieval quality).
- A small eval set (question/answer or topic/draft pairs) with a scored rubric for regression-testing agent quality over time.

## License

Licensed under the [Apache License 2.0](LICENSE).

## Author

Built by [Akki](https://github.com/akkiyolo).
