# Leafly Tea Assistant

An AI-powered chat assistant for **Leafly**, a whole-leaf, single-origin tea
brand ("Better Tea. Better World. Better You."). It handles tea catalog
search, personalized recommendations, FAQ answers, and sentiment-driven
escalation, replying in whichever language the customer used (English,
Hindi, or Hinglish) - built on FastAPI + PostgreSQL + a React chat UI,
powered by Gemini (`gemini-3.1-flash-lite`).

> The order/checkout system is being rebuilt from scratch and isn't wired up
> yet - `POST /api/email` is currently a bare scaffold with no active
> endpoints (see `backend/app/api/routes/email.py`).

## Feature checklist

| Feature | Where it lives |
|---|---|
| Context-aware chat (last 10 messages) | `backend/app/services/ai_service.py` |
| Tea catalog search + filters (tea type/origin/caffeine level/badge/price/gifting) | `product_context.py` |
| Personalized recommendations (keyword-based tea type bias, budget combos) | `recommendation_service.py` |
| "No exact match" fallback (closest available product, never a dead end) | `product_context.get_closest_items` |
| Dynamic FAQ (keyword-matched, grounded, never invented - some entries still TODO pending real answers from the team) | `faq_service.py`, `app/data/faq_knowledge.json` |
| Sentiment detection + escalation logging | `escalation_service.py` |
| Multilingual (English/Hindi/Hinglish), incl. product-name translation | `app/prompts/system_prompt.py`, `app/prompts/product_translations.py` |
| Rate limiting + in-memory response caching | `rate_limiter.py`, `cache_service.py` |

## Project structure

```
leafly-tea-chatbot/
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
| `APP_NAME` | no | `Leafly Tea Assistant` | |
| `ENV` | no | `development` | |
| `GEMINI_API_KEY` | yes | - | Required for any AI feature (chat, recommendations, FAQ) |
| `GEMINI_MODEL` | no | `gemini-3.1-flash-lite` | |
| `GEMINI_RPM_LIMIT` / `GEMINI_RPD_LIMIT` | no | `12` / `450` | Soft caps kept under the free-tier hard limits (15 RPM / 500 RPD) - once hit, the app returns a graceful "high demand" fallback instead of calling the API |
| `BREVO_API_KEY` | no | - | Free tier (300 emails/day, no card needed, sends to any recipient without a verified domain) - https://brevo.com. If unset, `email_service.py` logs a warning and skips sending; every other feature keeps working normally |

Brand constants (`BRAND_NAME`, `TAGLINES`, `BRAND_PILLARS`, `CONTACT_EMAIL`)
are **not** env vars - they're finalized directly in
`backend/app/core/config.py`. Edit that file if the real brand copy changes.

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
4. Seed the tea catalog:
   ```
   docker-compose exec backend python -m app.seed.seed_products
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
python -m app.seed.seed_products
uvicorn app.main:app --reload
```

### Frontend

```
cd frontend
npm install
npm run dev
```

Visit http://localhost:5173.

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
   python -m app.seed.seed_products
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
4. Verify CORS: the backend's `CORSMiddleware` allows the origins listed in
   `CORS_ORIGINS` (`backend/.env`) - update it to include your actual
   deployed frontend origin.
