# Agentic Blog App

A production-grade blog application built with **FastAPI**, featuring JWT authentication, PostgreSQL, AWS S3-backed media storage, server-rendered pages via Jinja2, and automated testing.

## Features

- **User authentication** — registration, login, and session handling via JWT (`pyjwt`) with Argon2 password hashing (`pwdlib`)
- **Password reset flow** — email-based reset links with expiring tokens
- **Blog posts** — create, view, and browse posts with pagination (`posts_per_page`), author info, and per-user post listings
- **Profile pictures / media uploads** — image handling via `Pillow`, stored on **AWS S3** (`boto3`), with configurable upload size limits
- **Server-rendered UI** — Jinja2 templates for home, post, login, register, account, and password reset pages, alongside a JSON API
- **Security hardening** — middleware enforcing `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, and HSTS (in production)
- **Health check endpoint** — `/health` verifies database connectivity
- **Database migrations** — schema versioning via `Alembic`
- **Async everything** — `SQLAlchemy` (async) + `psycopg` (async PostgreSQL driver)
- **Automated tests** — `pytest` with `moto` for mocking S3 in tests

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
| Testing | pytest, moto |
| Package management | uv |

## Project Structure

```
Agentic-Blog-App/
├── alembic/                # Database migration scripts
├── media/profile_pics/     # Local media storage (dev)
├── populate_images/        # Seed images for populate_db.py
├── routers/                # API route modules (users, posts)
├── static/                 # CSS/JS/static assets
├── templates/              # Jinja2 HTML templates
├── tests/                  # Test suite
├── auth.py                 # Authentication & JWT logic
├── check_s3.py              # S3 connectivity check script
├── config.py                # App settings (pydantic-settings)
├── database.py               # Async DB engine & session setup
├── email_utils.py            # Email sending helpers
├── image_utils.py            # Image processing/upload helpers
├── main.py                   # FastAPI app entrypoint & page routes
├── models.py                  # SQLAlchemy ORM models
├── populate_db.py              # DB seeding script
├── schemas.py                   # Pydantic schemas
├── alembic.ini                   # Alembic configuration
├── pyproject.toml                 # Project dependencies
└── uv.lock                         # Locked dependency versions
```

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL database
- AWS S3 bucket (or S3-compatible storage) for media uploads
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

S3 interactions are mocked using `moto`, so no live AWS credentials are needed for tests.

## API Overview

| Route prefix | Description |
|---|---|
| `/api/users` | User registration, login, profile, password reset |
| `/api/posts` | Create, read, and manage blog posts |
| `/health` | Database health check |
| `/`, `/posts`, `/posts/{id}`, `/users/{id}/posts` | Server-rendered pages |
| `/login`, `/register`, `/account`, `/forgot-password`, `/reset-password` | Auth-related pages |

Full interactive API documentation is available at `/docs` (Swagger UI) once the server is running.

## Security Notes

- All responses include `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy` headers.
- HSTS is enforced automatically outside of local development (`localhost`/`127.0.0.1`).
- Password reset pages set `Referrer-Policy: no-referrer` to avoid leaking reset tokens via the `Referer` header.

## License

Licensed under the [Apache License 2.0](LICENSE).

## Author

Built by [Akki](https://github.com/akkiyolo).
