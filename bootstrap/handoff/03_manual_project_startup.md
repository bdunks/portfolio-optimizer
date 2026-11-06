# Portfolio Optimizer — Manual Linux Project Startup

**Version:** 1.1 · **Date:** 2026-11-05  
**Audience:** developer, **before** starting Codex. Keep this guide outside the repository if preferred; scaffolding is manual and not an agent task.

## 1. Decisions and prerequisites

- Linux workstation; **mise is already installed** and activated in your shell.
- **Project name:** `portfolio-optimizer`.
- **CPython 3.14**, **Node.js 24 LTS**, **uv installed through mise** (no separate uv installer or manual `venv`).
- Vue 3 + Quasar CLI/Vite + TypeScript + Pinia; npm package manager.
- SQLite is embedded in Python; **no PostgreSQL, Docker, or database-exploration tooling** required.

Check mise is ready:

```bash
mise --version
```

If mise is installed but not activated in this terminal, follow your existing shell activation configuration or run `eval "$(mise activate bash)"` for bash.

## 2. Initialize repo and install toolchains

```bash
mkdir portfolio-optimizer
cd portfolio-optimizer
git init

mise use python@3.14 node@24 uv@latest
mise install
python --version     # 3.14.x
node --version       # 24.x
uv --version
```

Commit the generated `mise.toml`. Standard CPython 3.14 is intended; no free-threaded runtime is needed. Packages are resolved/locked by uv inside the backend.

## 3. Initialize Python backend (manually)

From the repo root:

```bash
uv init --bare backend
cd backend
uv python pin 3.14

uv add "fastapi[standard]" pydantic-settings sqlalchemy alembic \
  httpx authlib keyring
uv add numpy scipy polars cvxpy osqp
uv add --dev pytest pytest-cov pytest-asyncio hypothesis ruff mypy
# Later, only if the optimizer needs discrete selection:
# uv add highspy

uv sync
uv run python --version
uv run python -c "import cvxpy, osqp, scipy, polars; print('Optimization dependencies OK')"
cd ..
```

`uv add` creates/manages `backend/.venv` automatically. Do not create another venv or use system `pip` in this project. Do not install PyPortfolioOpt for v1. If dependencies fail on your Linux architecture, inspect `uv`'s resolver/wheel error before making changes to the pinned runtime.

## 4. Scaffold Vue 3 + Quasar (manually)

From the repo root:

```bash
npm init quasar@latest
```

Choose the current wizard's equivalent of:

| Question | Selection |
|---|---|
| App kind | **App with Quasar CLI** |
| Generated directory | **`frontend`** |
| Build | **Vite** |
| Script | **TypeScript** |
| Routing/state | Vue Router / **Pinia** |
| Target | **SPA** |
| Package manager | **npm** |
| Lint | ESLint (recommended) |

Then:

```bash
cd frontend
npm install
npm install pinia
npm install -D vitest @vue/test-utils jsdom
npm run dev
```

Verify the Quasar welcome page, then Ctrl-C. Quasar's prompt labels may change; choose the equivalent rather than forcing an older CLI syntax.

## 5. Prepare local SQLite location

From the repo root:

```bash
mkdir -p backend/data
```

SQLite is created by SQLAlchemy/Alembic **when Codex implements the backend**. No separate initialization daemon or database GUI is needed. Backend runtime config:

```text
DATABASE_URL=sqlite:///./data/portfolio.sqlite3
DEMO_MODE=true
ETRADE_ORDER_SUBMISSION_ENABLED=false
```

Relative DB path assumes launching from `backend/`. Store live local settings in an ignored `backend/.env` (or use defaults), not in Git. Codex will configure WAL, per-connection foreign keys and short write transactions. **Do not generate migrations before SQLAlchemy models exist.**

## 6. Add handoff documents and commit scaffold

Download the accompanying `README.md` and `AGENTS.md` into the **repo root**. Put the functional and technical specifications plus existing visual reference in `docs/`:

```text
portfolio-optimizer/
├── README.md
├── AGENTS.md
├── mise.toml
├── docs/
│   ├── 01_functional_specification.md
│   ├── 02_technical_specification.md
│   └── portfolio_tax_optimizer_reference.html
├── backend/
└── frontend/
```

Keep `03_manual_project_startup.md` and `04_codex_kickoff_prompt.md` outside the repo if you prefer. The HTML mockup is a **visual reference only**; sample allocations and financial figures do not override the specifications.

From repo root:

```bash
cat >> .gitignore <<'IGNORE'
backend/.venv/
backend/data/
backend/.env
frontend/.env.local
**/__pycache__/
**/.pytest_cache/
**/.mypy_cache/
.DS_Store
IGNORE

git status
git add .gitignore mise.toml README.md AGENTS.md docs/ backend/pyproject.toml \
  backend/uv.lock backend/.python-version frontend/
git commit -m "Initialize portfolio-optimizer scaffold and specifications"
```

Review `git status` and staged files to ensure no tokens, `.env`, SQLite data or real holdings are included. If the frontend generator created a nested Git repository, remove only the generated `frontend/.git` after verifying it is not intended.

## 7. Start Codex

Open Codex at repository root and paste the body of **`04_codex_kickoff_prompt.md`**. The agent should read `AGENTS.md`, `README.md` and both specs first. **Do not ask it to rerun mise/uv/Quasar generators.**

After Codex's initial implementation:

**Terminal A**
```bash
cd portfolio-optimizer/backend
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal B**
```bash
cd portfolio-optimizer/frontend
npm run dev
```

Check `http://127.0.0.1:8000/health`, `http://127.0.0.1:8000/docs`, and Quasar's printed local dev URL.

**Verification:**
```bash
cd portfolio-optimizer/backend
uv run pytest
uv run ruff check .
cd ../frontend
npm run build
```

Do not attempt live broker writes during initial setup. The final manual-approval order integration is a later milestone, not part of scaffolding.

## References

- mise: https://mise.jdx.dev/
- uv: https://docs.astral.sh/uv/guides/projects/
- Quasar: https://quasar.dev/start/quick-start/
- SQLite: https://www.sqlite.org/whentouse.html
