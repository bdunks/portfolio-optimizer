# Backend foundation (Phase 1A)

This backend is local-only and currently uses a deterministic, read-only `FakeBroker`. It has no E*TRADE HTTP/OAuth integration, order preview, order submission, or live trading path. Fake holdings and policy seed data are explicitly labeled `DEMO`; they are not account data or investment guidance.

## Run locally

From `backend/`:

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The application also applies pending Alembic migrations at startup. Migrations are additive and never reset the database. The default SQLite database is `backend/data/portfolio.sqlite3` (created with private directory/file permissions and excluded from Git). Existing database contents are retained. The Alembic CLI uses `PORTFOLIO_DATABASE_URL` when set, otherwise the URL in `alembic.ini`. To use an isolated database or broker fixture in tests, call `app.main:create_app(database_url="sqlite:///...", broker=FakeBroker(...))`.

The app starts without credentials. `POST /api/v1/portfolio/sync` explicitly fetches and atomically publishes the offline demo snapshot. Policy and portfolio data are not seeded automatically. To opt into the packaged hypothetical seed policy and initial fake portfolio, set `PORTFOLIO_DEMO_SEED=1`; the seed policy lives in `app/seeds/demo_policy.json` and is labeled `DEMO`.

The policy draft endpoint accepts `settings`, `sleeves`, `allowed_securities`, `overrides`, and optional `reassignments` (`{old_sleeve_key: enabled_target_sleeve_key}`). Targets are exact decimal strings; top-level targets and each enabled nested allocation must total exactly `100`. Drafts are saved even when target sums are invalid, but activation rejects invalid sums and unassigned holdings. Posting a new draft creates a new immutable revision; an activated revision cannot be edited or reactivated.

Phase 1 has no browser login/session authentication. Writes accept local CLI requests without an `Origin` header. Browser writes require a loopback `Host` and a supplied `Origin` matching either an explicitly configured CORS origin or the request's actual same origin (normalized scheme/host/port); an arbitrary loopback origin is not sufficient. Remote hosts, remote/malformed/null origins, and unconfigured cross-origin origins are rejected. Cross-origin CORS is limited to the explicit Vite development origins `http://localhost:9000`, `http://127.0.0.1:9000`, `http://localhost:5173`, and `http://127.0.0.1:5173`; credentials are disabled.

## Tests and lint

```bash
uv run pytest
uv run ruff check .
```


## Seeded DEMO workflow (no credentials)

For a clean local demo, stop any existing backend first, then start from `backend/` with the opt-in seed flag:

```bash
PORTFOLIO_DEMO_SEED=1 uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This seeds the deterministic hypothetical account and policy; it makes no broker requests. With the server running, the API serves `GET /health`, then submit a recommendations-only demo run:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS -X POST http://127.0.0.1:8000/api/v1/optimizer/runs \
  -H 'Content-Type: application/json' \
  -d '{"mode":"recommendations_only"}'
```

The POST returns the saved run summary, priority-ranked groups with `leg_ids`, and each unique order once in run-level `consolidated_legs`; the packaged deterministic seed includes a non-empty hypothetical VB-to-VTI replacement group. Use the returned `run_id`, `group_id`, and exact selected broker-lot IDs to ask the service to resize the dependent buy (selection does not approve or place orders):

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/optimizer/runs/<run_id>/selection \
  -H 'Content-Type: application/json' \
  -d '{"selected_group_ids":["<group_id>"],"selected_sell_lots":{"<group_id>":["DEMO-VB-LOT-1"]}}'
```

For a deterministic fixture that splits VB into two separately attributed sell lots and asserts the non-empty group, consolidated SELL, resized BUY, no-trade subset, saved-run reopening, and CSV/JSON exports, run:

```bash
cd backend && uv run --offline pytest -q tests/test_demo_api.py::test_demo_run_persistence_selection_arithmetic_and_restart
```

All values, lot IDs, group IDs and results are hypothetical. `mode: "real_optimizer"`, OAuth start/verify and both order preview/submit routes fail explicitly with the documented `503` error envelope. OAuth/account integration and order tables/workflows are not implemented. Do not use these responses as actionable trades.

## Generated API contract

Pydantic response DTOs on every Phase 1 route generate the canonical `backend/openapi.json`; the same artifact generates `frontend/src/types/api.ts`, including route request/query/path/response mappings (`ApiRequest`, `ApiQuery`, `ApiPath`, and `ApiResponse`). Monetary/share values are exact decimal strings; arbitrary provenance/details are represented as JSON values. Exact-decimal request fields are documented as strings, though the current validator also accepts integers and rejects floats.

From `backend/`, regenerate or verify without network access:

```bash
uv run --offline python scripts/generate_api_contract.py
uv run --offline python scripts/generate_api_contract.py --check
```

The check fails if either generated file has drifted. Contract regression tests also inspect named OpenAPI schemas, error envelopes, seeded/unseeded DTO validation, and CSV/JSON export content types.

## Deferred work and local boundary

Phase 2 remains responsible for the real tax-aware optimizer, exact IRS ST/LT netting and Decimal basket validation, complete wash-sale blocking, market-data/look-through coverage, independent risk constraints, solver deadlines/timeout handling, whole-share repair, and the synthetic 460-security/2,500-lot benchmark. The current DEMO heuristic does not perform those checks and reports `actionable: false`; seed/demo fixtures are not their substitute.

There is no browser session/login layer yet. Same-origin calls need no CORS permission; cross-origin development writes are accepted only from the explicit origins listed above. State-changing requests require a loopback `Host`; if an `Origin` is supplied it must match an explicitly configured CORS origin or the request's actual same origin. A different loopback origin is rejected even when CORS would hide the response. The backend must continue binding only to `127.0.0.1`.
