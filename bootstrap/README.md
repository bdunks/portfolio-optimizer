# Portfolio Optimizer

Local, single-user, tax-aware investment recommendation app. Produces **ranked, lot-specific sell and whole-share buy proposals** for E*TRADE holdings, targeting configurable portfolio allocations and gradual direct-indexing-to-ETF consolidation. **Orders require individual manual approval; nothing trades automatically.**

## Workspace prerequisites

The developer creates the project scaffold **before** running Codex, following `03_manual_project_startup.md` (kept outside the repository if desired):

- Linux with mise already installed and shell-activated.
- `mise.toml` selects **CPython 3.14**, **Node 24 LTS** and **uv via mise**.
- `backend/`: uv-managed Python project; SQLite, SQLAlchemy/Alembic, FastAPI, CVXPY/OSQP.
- `frontend/`: Vue 3 + Quasar CLI/Vite, TypeScript, Pinia, Vue Router.
- `docs/`: `01_functional_specification.md`, `02_technical_specification.md`, `portfolio_tax_optimizer_reference.html`.

Do **not** regenerate existing projects or introduce Docker/PostgreSQL/React. SQLite requires no server. The mockup is a design reference, **not** an authoritative source of investment data.

## Local development (after initial implementation)

```bash
# Terminal 1
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend
npm install
npm run dev
```

API: http://127.0.0.1:8000/docs. Use the URL printed by Quasar for the web app.

```bash
# Backend tests
cd backend && uv run pytest && uv run ruff check .

# Frontend build
cd frontend && npm run build
```

Demo mode runs without E*TRADE credentials. Keep local `.env`, account data, tokens, and `backend/data/` out of Git. Live broker submission is implemented only as the **final phase** and remains gated by exact per-order approval and E*TRADE terms/account permissions.

## Specifications and handoff

Read `AGENTS.md` for project rules and source precedence. Functional and technical requirements live in `docs/`. The separate kickoff document `04_codex_kickoff_prompt.md` specifies the first implementation task; it should not duplicate product policy.
