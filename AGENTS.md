# Agent instructions — Portfolio Optimizer

## Product & safety boundaries

Local, single-user, **single-account** tax-aware decision-support app for a single managed E*TRADE brokerage account. It produces ranked, explainable, small-batch tax-lot-level SELL and whole-share BUY recommendations.

- Never implement unattended trading, multi-account routing, or multi-year projection workflows.
- Live broker writes/order placement remain disabled without explicit owner release authorization (see Decision `D1` in `docs/decisions.md`).
- Keep credentials backend-only, bind locally (`127.0.0.1`), and keep no-credentials DEMO mode functional.
- Never commit or include `backend/.env`, `backend/data/`, real E*TRADE tokens, account IDs, or live account payloads in source, fixtures, or reports.

## Repo layout & verification

- `backend/`: Python 3.14 (`uv`), FastAPI, SQLite + SQLAlchemy/Alembic, CVXPY/OSQP/CLARABEL.
- `frontend/`: Node 24, Vue 3, Vite, TypeScript, Pinia, Vue Router, Tailwind/shadcn-vue.
- Toolchain is managed via `mise.toml`. Do not introduce Docker, PostgreSQL, or React.
- **Typecheck (strict):** `mise run typecheck` (`pyrefly` strict mode on backend + `vue-tsc` on frontend). Ruff also enforces `ANN` type annotations in tests.
- **Format / lint:** `mise run format` (note: `format:backend` runs `ruff check --fix-only --unsafe-fixes`—inspect diffs; use `cd backend && uv run ruff check .` and `cd frontend && npm run lint:check` for read-only checks).  Do not waste tokens fixing errors before running autofix.
- **Tests:** `cd backend && uv run pytest`; `cd frontend && npm test`, `npm run test:integration`, `npm run test:e2e`.
- **Migrations:** Schema changes go through Alembic (`backend/migrations/`, `cd backend && uv run alembic upgrade head`).
- **API contracts:** When FastAPI routes or schemas change, regenerate `backend/openapi.json` and `frontend/src/types/api.ts` via `cd backend && uv run python scripts/generate_api_contract.py` (verify with `--check`).

## Source precedence & decisions

1. `docs/01_functional_specification.md` — financial semantics, UX, and acceptance criteria.
2. `docs/02_technical_specification.md` — architecture, data model, tax netting equations, APIs, and solver design.
3. `docs/portfolio_tax_optimizer_reference.html` — appearance/interaction reference **only**; its demo numbers and comments never override specs.

- All sleeves, target percentages, ETF candidates, wash-sale rules, tax rates, carryforwards, TLH targets, gain budgets, and batch limits are configurable product data, not constants.
- Check `docs/decisions.md` before cross-cutting financial, lifecycle, API, or persistence work; log new decisions there following its header format and reference IDs in tasks/briefs.
- Resolve routine technical choices autonomously; ask the owner on business semantics, workflow restrictions, or material trade-offs. Stop affected work on unresolved or conflicting assumptions; never infer approval.
- Decisions cannot override specs—update affected specs for approved behavior changes and verify agreed behavior end to end.
- For optimizer quality/benchmark work, follow `docs/optimizer_quality_protocol.md`.

## Core invariants

- Use `Decimal` for money, tax, and cash checks; preserve the normalized current-state SQLite schema and specific broker lot IDs.
- Test broker/order flows with deterministic fakes unless the owner explicitly authorizes a live read check.
- Report actual test/build/benchmark outcomes; never claim a check or integration was verified without running it.

## Backlog

- Use `backlog` for substantial or multi-step work, or when asked; skip it for small fixes.
- Inspect relevant projects, milestones, and tasks before structural changes (`backlog task next --json` suffices to start eligible work).
- Never initialize/reset the backlog database, delete work, promote `Draft` items, or mark tasks `Done` without a request or agreed plan.
- When creating, editing, or completing backlog tasks, use the `backlog-authoring` skill (`.agents/skills/backlog-authoring/SKILL.md`).
