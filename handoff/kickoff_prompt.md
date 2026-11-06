# Portfolio Optimizer — First Codex Kickoff Prompt

**Version:** 1.3 · **Date:** 2026-11-05

**How to use:** Complete the manual Linux startup guide first. Place `README.md` and `AGENTS.md` at repository root, and the functional/technical specs plus UI HTML under `docs/`. Start your primary orchestrator agent in `portfolio-optimizer/` and paste the prompt below. Phase 1 is explicitly structured into **Phase 1A (Backend & API Contract)** and **Phase 1B (Frontend Quasar App)** so it can be delegated cleanly across subagents.

## Paste this into Codex / Orchestrator Agent

```text
Implement Phase 1 (1A + 1B) of the existing Portfolio Optimizer project.

First read AGENTS.md and README.md, then:
- docs/01_functional_specification.md
- docs/02_technical_specification.md
- docs/portfolio_tax_optimizer_reference.html (visual reference only)

Inspect the existing mise/uv/backend and Quasar/frontend scaffold. Do not
regenerate either project, change runtimes, create a new repo or add a DB
server. Briefly report your implementation plan, then execute Phase 1A
followed by Phase 1B (using subagents where appropriate).

PHASE 1 DELIVERABLE: working, end-to-end offline single-account demo vertical slice.

PHASE 1A — BACKEND, SCHEMA & API CONTRACT:
1. Implement a modular Python/FastAPI backend with typed Pydantic v2 DTOs,
   the normalized single-account SQLite/SQLAlchemy 2 schema from the technical
   spec (§4.2), Alembic migrations, deterministic single-account fake-broker
   holdings/transactions/lots (assuming DRIP is off), and `/health` +
   `/api/v1/auth/etrade/*` status stubs. Keep fixture inputs clearly marked
   DEMO and broker writes unavailable.

2. Implement policy draft/save/activate with full sleeve CRUD (add, rename,
   reorder, disable, delete with `reassign_to_sleeve_key`), nested US ETF /
   direct-indexing target, default holding-to-sleeve resolution
   (`is_direct_index_container = true` on the US sleeve so all ~450 individual
   stocks + VB/VXF map automatically without 450 manual rows, plus
   `policy_security_override` for explicit overrides), allowed ETF pairs/triplets,
   tax profile (`short_term_tax_rate`, `long_term_tax_rate`, carryforwards,
   YTD realized ST/LT), configurable retained TLH target
   (`target_retained_net_loss_usd`, `ordinary_income_deduction_limit_usd`,
   `carryforward_loss_discount_factor`), gain/tax budgets, drift bands, and
   small-batch execution limits (`max_sell_tickers_per_batch`,
   `max_sell_lots_per_batch`, `max_total_orders_per_batch`,
   `max_batch_turnover_pct`). Validate allocation totals with Decimal and
   reject activation unless top-level and nested targets sum to EXACTLY 100%,
   with zero unassigned holdings. Use the example policy from the functional
   spec as editable seed data, not hard-coded domain logic.

3. Implement all `/api/v1/*` endpoints from §8 of the technical spec:
   portfolio, lots, active/draft policy, sync, optimizer runs
   (`POST /api/v1/optimizer/runs` returning HTTP 201 synchronously via worker
   thread/process with `SOLVER_TIMEOUT_SECONDS = 10.0`),
   `GET /api/v1/optimizer/runs/{id}/recommendations` (supporting multi-lot
   `selected_lots` consolidation per sold ticker), subset selection
   (`POST /api/v1/optimizer/runs/{id}/selection`), exports, single-account
   wash-sale view and activity. In Phase 1, recommendations may be
   DETERMINISTIC DEMO small-batch fixtures, clearly labeled. Ensure selection
   changes trigger fresh cash/tax/exposure recalculation rather than silently
   preserving stale totals.

4. Run backend `pytest` and `ruff check .`, and export/generate the matching
   TypeScript contract in `frontend/src/types/api.ts`.

PHASE 1B — FRONTEND QUASAR APPLICATION:
5. Build the Vue 3 + Quasar UI using real Quasar components and typed API
   calls through Pinia (`stores/{portfolio,policy,recommendations}.ts` and
   `services/api.ts`). All six navigation pages must render:
   - Overview: KPIs, 3-state US transition hierarchy (Current, Proposed
     Basket / Post-Selected-Trades, and Configured Policy Target—note that
     the HTML mockup only showed 2 columns; you must render all 3 states),
     allocation breakdown, and recommendations preview.
   - Recommendations: expandable ranked small-batch trade groups, exact-lot
     attribution (including small legacy/DRIP lot cleanup and multi-lot
     consolidation per ticker), group/sell-lot subset selection (disallowing
     orphaned replacement BUY unchecking) and a review dialog with clear
     "no order placed" messaging.
   - Tax Lots: searchable/filterable lot explorer with small-lot cleanup and
     wash flags.
   - Allocation Policy: full sleeve CRUD (`+ Add Sleeve`, rename, reorder,
     delete with reassignment), ETF pair/triplet editor, 3-state US transition
     target, and the complete Tax & Batch Settings panel (including retained
     TLH target and small-batch caps).
   - Wash Sales & Activity: single-account 30-day lookback/forward restriction
     queue and audit log.

6. Write and run frontend `vitest` tests and `npm run build` covering policy
   exact-sum activation, custom sleeves (including cash and deletion
   reassignment), editable ETF sets, 3-state US transition rendering,
   tax/batch settings persistence, grouped recommendations, subset selection
   and no-trade state.

Do not implement live E*TRADE order placement in this first milestone.
Later phases, after Phase 1 (1A + 1B) passes:
- Phase 2: real single-account 30-day wash-sale engine (aligned to E*TRADE
  with DRIP off), exact IRS ST/LT tax netting function T(S, L) with
  configurable retained TLH target, cached Vanguard/iShares look-through
  exposure engine, 2-pass small-batch CVXPY/OSQP optimizer (with non-worsening
  drift slack and small-lot cleanup reward), multi-lot order consolidation,
  whole-share repair, independent Decimal validation, subset re-solve, and
  ~460-security/2,500-lot <10s benchmark.
- Phase 3: E*TRADE OAuth 1.0a (`oob` verifier flow), single-account read-only
  complete portfolio/lot/transaction sync, live Vanguard JSON
  (`.../api/funds/{FUND_ID}/holdings/latest`) and iShares CSV (`ITOT` etc.)
  look-through sync, coverage checks and cash reconciliation.
- Phase 4: Security and reliability hardening: migration/restart/backup tests,
  exceptional-state UI, reconciliation diagnostics, stable API contracts and
  end-to-end manual QA.
- Phase 5: Manually approved E*TRADE order writes (last): exact preview and
  discrete affirmative approval per exact order, protected broker submission,
  safe partial-fill handling and audit trail, subject to current E*TRADE
  account permissions and API terms.

At the end: report files changed, migrations run, test/build commands and
results, a browser/API smoke-test result, any genuinely blocking issue and
how to launch the demo. Prefer a functioning vertical slice to a large
collection of placeholder files.
```

## Phase 1 (1A + 1B) success criteria

- Quasar + FastAPI + SQLite start locally without broker keys; all six pages load.
- Adjustable example portfolio targets sum **exactly 100%**; arbitrary added/renamed/reordered/deleted sleeves work (with holding reassignment); all ~450 US direct-index stocks + `VB`/`VXF` resolve to the US direct-indexing container sleeve automatically; invalid drafts are savable but cannot be activated.
- ETF pairs/triplets can be edited; `SCHD` is the dividend candidate in the example. Tax & Batch Settings (including `target_retained_net_loss_usd` and batch caps) persist in `policy_revision`.
- The US hierarchy displays all **three** states (**Current**, **Proposed Basket**, and **Policy Target**); recommendations are explicitly DEMO small-batch trade groups showing lot-specific sell and related buy legs.
- No automatic or live order placement; frontend build (`npm run build`), frontend tests (`vitest`), and backend tests (`pytest`, `ruff`) actually pass.
