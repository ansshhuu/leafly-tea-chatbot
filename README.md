# Smart Cafe Assistant

An AI-powered cafe chat assistant: menu search, personalized recommendations,
order taking, table reservations, FAQ answers, sentiment-driven escalation,
multilingual replies (English/Hindi/Marathi), voice input/output, and photo-based
menu matching - built on FastAPI + PostgreSQL + a React chat UI, powered by
Gemini (`gemini-3.1-flash-lite`).


## Feature checklist

| Feature | Where it lives |
|---|---|
| Context-aware chat (last 10 messages) | `backend/app/services/ai_service.py` |
| Menu search + filters (veg/vegan/gluten-free/spice/price/category) | `menu_context.py` |
| Personalized recommendations (time-of-day, weather keyword, budget combos) | `recommendation_service.py` |
| "No exact match" fallback (closest available item, never a dead end) | `menu_context.get_closest_items` |
| Order assistant (add/remove/modify/checkout, Python-computed totals) | `order_service.py` |
| Reservation assistant (availability, alternatives, `dateparser` date resolution) | `reservation_service.py` |
| Dynamic FAQ (keyword-matched, grounded, never invented) | `faq_service.py`, `app/data/faq_knowledge.json` |
| Sentiment detection + escalation logging | `escalation_service.py` |
| Multilingual (English/Hindi/Marathi), incl. order/reservation confirmations | `app/prompts/system_prompt.py`, `app/prompts/templates.py` |
| Image understanding (photo → matching menu items) | `vision_service.py`, `POST /api/chat/image` |
| Rate limiting + in-memory response caching | `rate_limiter.py`, `cache_service.py` |
| Email notifications - order/reservation confirmation, reservation reminder, birthday wish, cart-abandonment nudge (Brevo) | `email_service.py`, `POST /api/email/cart-reminder` |

## Project structure

```
smart-cafe-assistant/
├── frontend/     # Vite + React chat UI
├── backend/      # FastAPI + SQLAlchemy (async) + Alembic
└── docker-compose.yml
```

## Prerequisites

- Docker + Docker Compose (for the containerized quick start)
- Node.js 20+ (for running the frontend outside Docker)
- Python 3.11+ (for running the backend outside Docker)
- A Gemini API key (free tier) - https://aistudio.google.com/apikey

## Environment variables

All backend config lives in `backend/.env` (copy from `backend/.env.example`).

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | yes | - | Async (asyncpg) connection string, used by the running app |
| `SYNC_DATABASE_URL` | yes | - | Sync (psycopg2) connection string, used only by Alembic |
| `APP_NAME` | no | `Smart Cafe Assistant` | |
| `ENV` | no | `development` | |
| `GEMINI_API_KEY` | yes | - | Required for any AI feature (chat, order, reservation, FAQ, vision) |
| `GEMINI_MODEL` | no | `gemini-3.1-flash-lite` | |
| `GEMINI_RPM_LIMIT` / `GEMINI_RPD_LIMIT` | no | `12` / `450` | Soft caps kept under the free-tier hard limits (15 RPM / 500 RPD) - once hit, the app returns a graceful "high demand" fallback instead of calling the API |
| `BREVO_API_KEY` | no | - | Free tier (300 emails/day, no card needed, sends to any recipient without a verified domain) - https://brevo.com. If unset, `email_service.py` logs a warning and skips sending; every other feature keeps working normally |

Cafe operating parameters (`TAX_RATE`, per-weekday `CAFE_HOURS`,
`MAX_CAPACITY_PER_SLOT`, `SLOT_DURATION_MINUTES`) are **not** env vars -
per-weekday hours don't map cleanly to a flat env var, so they're finalized
constants directly in `backend/app/core/config.py`. Edit that file if the
real cafe's values differ.

Frontend config: `frontend/.env` (optional) or Vercel project settings -
`VITE_API_BASE_URL` (defaults to `http://localhost:8000` if unset).

## Quick start (Docker)

1. Copy the backend env file and fill in `GEMINI_API_KEY`:
   ```
   cp backend/.env.example backend/.env
   ```
2. From the project root, start all services:
   ```
   docker-compose up --build
   ```
   This starts:
   - `postgres` on port 5432 (data persisted in a named volume)
   - `backend` (FastAPI, with `--reload` for local dev) on http://localhost:8000
   - `frontend` (Vite dev server) on http://localhost:5173

3. Run migrations (once Postgres is up):
   ```
   docker-compose exec backend alembic upgrade head
   ```
4. Seed the menu:
   ```
   docker-compose exec backend python -m app.seed.seed_menu
   ```
5. Check backend health: http://localhost:8000/health — should report `"database": "ok"`.
6. Open http://localhost:5173 and start chatting.

## Running locally without Docker

### Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # fill in GEMINI_API_KEY and point DATABASE_URL at your Postgres
alembic upgrade head
python -m app.seed.seed_menu
uvicorn app.main:app --reload
```

### Frontend

```
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173.

`npm install` automatically runs `scripts/fetch-models.sh` via its
`postinstall` hook, which downloads the self-hosted Whisper-WASM model files
(~43MB, used as the voice-input fallback when the browser's native
`SpeechRecognition` is unavailable/blocked - see `frontend/src/services/speech.js`)
into `frontend/public/models/`. That folder is gitignored, so a fresh clone
always needs this to run once - if it fails (offline install, `bash`
unavailable, etc.) `npm install` still succeeds with a warning; run
`bash scripts/fetch-models.sh` manually before relying on the Whisper
fallback.

### Running tests

```
cd backend
pytest
```

All tests mock the Gemini API - no network calls, no quota spent. Real
end-to-end verification against the live API is done manually/ad hoc, never
in the automated suite.

## Deployment

This project targets **Vercel** (frontend) + **Render** (backend) +
**Neon** (Postgres), but any static host / container host / managed Postgres
works equivalently.

### Database (Neon or any managed Postgres)

1. Create a Postgres instance. Grab both connection strings (pooled/direct as
   needed) - you'll need an asyncpg-flavored one (`postgresql+asyncpg://...`)
   for `DATABASE_URL` and a psycopg2-flavored one
   (`postgresql+psycopg2://...`) for `SYNC_DATABASE_URL`.
2. If using Neon specifically: the async URL needs `?ssl=require` (not
   `sslmode`, which asyncpg doesn't understand); the sync URL uses
   `?sslmode=require`.
3. Run migrations once against the deployed database:
   ```
   alembic upgrade head
   ```
   (from a machine/CI job with `SYNC_DATABASE_URL` pointed at it), then seed:
   ```
   python -m app.seed.seed_menu
   ```

### Backend (Render, or any Docker-capable host)

1. New Web Service, pointed at `backend/` with `backend/Dockerfile`
   (no `--reload` in the image - it's production-ready as committed).
2. Set environment variables per the table above (`DATABASE_URL`,
   `SYNC_DATABASE_URL`, `GEMINI_API_KEY`, plus any non-default overrides).
3. Health check path: `/health`.
4. Note the deployed URL (e.g. `https://your-backend.onrender.com`) for the
   frontend's `VITE_API_BASE_URL`.

### Frontend (Vercel)

1. Import the repo, set the project root to `frontend/`.
2. `vercel.json` already configures the build (`npm run build`, output
   `dist/`, SPA rewrites) - no extra config needed.
3. Set the environment variable `VITE_API_BASE_URL` to your deployed backend
   URL (step above), then redeploy (Vite bakes env vars in at build time, so
   changing this requires a rebuild, not just a restart).
4. Verify CORS: the backend's `CORSMiddleware` currently allows all origins
   (`allow_origins=["*"]`) - fine for this project's scope, but tighten to
   your actual frontend origin before treating this as production-hardened.
5. Vercel's default build runs `npm install` before `npm run build`, which
   triggers `postinstall` → `scripts/fetch-models.sh` automatically - no
   extra build-step config needed. Check the build log for
   `[fetch-models]` lines to confirm the Whisper model files downloaded
   successfully; a failure there won't fail the whole build (see the
   frontend setup section above), so it's easy to miss otherwise.

