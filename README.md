# Portfolio Optimizer

Local, single-user, **single-account**, tax-aware investment recommendation app. Produces **ranked, small-batch, lot-specific sell and whole-share buy proposals** for a single managed E*TRADE brokerage account, targeting configurable portfolio allocations and gradual direct-indexing-to-ETF consolidation. **Orders require individual manual approval; nothing trades automatically.**

## Workspace prerequisites

The developer creates the project scaffold **before** running Codex, following `03_manual_project_startup.md` (kept outside the repository if desired):

- Linux with mise already installed and shell-activated.
- `mise.toml` selects **CPython 3.14** (fallback 3.13 if needed), **Node 24 LTS** and **uv via mise**.
- `backend/`: uv-managed Python project; SQLite, SQLAlchemy/Alembic, FastAPI, CVXPY/OSQP/CLARABEL.
- `frontend/`: Vue 3 + Vite and shadcn-vue, TypeScript, Pinia, Vue Router.
- `docs/`: `01_functional_specification.md`, `02_technical_specification.md`, `portfolio_tax_optimizer_reference.html`.

Do **not** regenerate existing projects or introduce Docker/PostgreSQL/React. SQLite requires no server. The mockup is a design reference, **not** an authoritative source of investment data.

## Local development (after initial implementation)

```bash
# Terminal 1
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# Optional: configure manual canonical ITOT look-through refresh (no startup fetch)
PORTFOLIO_ENABLE_ITOT_REFRESH=1 uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2
cd frontend
npm install
npm run dev
```

API: http://127.0.0.1:8000/docs. Use the URL printed by Vite for the web app.

```bash
# Autofix and format both projects (from repository root)
mise run format
# Or just one: mise run format:backend / mise run format:frontend

# Backend tests
cd backend && uv run pytest && uv run ruff check .

# Frontend build & tests
cd frontend && npm run build && npx vitest run
```

Backend formatting enables Ruff's unsafe fixes; review the diff because they can change behavior. Frontend formatting reuses `npm run lint` (Prettier + ESLint `--fix`); ESLint suggestions requiring manual review are not automatically applied.

Demo mode runs without E*TRADE credentials. Keep local `.env`, account data, tokens, and `backend/data/` out of Git. Live broker submission is implemented only as the **final phase (Phase 5)** and remains gated by exact per-order approval and E*TRADE terms/account permissions.

## Specifications and handoff

Read `AGENTS.md` for project rules and source precedence. Functional and technical requirements live in `docs/`. The separate kickoff document `04_codex_kickoff_prompt.md` specifies the phased implementation tasks (with Phase 1 split into Phase 1A Backend and Phase 1B Frontend for subagent execution).
