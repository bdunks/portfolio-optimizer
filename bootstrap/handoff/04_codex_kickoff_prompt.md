# Portfolio Optimizer — First Codex Kickoff Prompt

**Version:** 1.2 · **Date:** 2026-11-05

**How to use:** Complete the manual Linux startup guide first. Place `README.md` and `AGENTS.md` at repository root, and the functional/technical specs plus UI HTML under `docs/`. Start Codex in `portfolio-optimizer/` and paste the prompt below.

## Paste this into Codex

```text
Implement Phase 1 of the existing Portfolio Optimizer project.

First read AGENTS.md and README.md, then:
- docs/01_functional_specification.md
- docs/02_technical_specification.md
- docs/portfolio_tax_optimizer_reference.html (visual reference only)

Inspect the existing mise/uv/backend and Quasar/frontend scaffold. Do not
regenerate either project, change runtimes, create a new repo or add a DB
server. Briefly report your implementation plan, then implement it.

PHASE 1 DELIVERABLE: working, end-to-end offline demo vertical slice.

1. Implement a modular Python/FastAPI backend with typed DTOs, the normalized current-state
   SQLite/SQLAlchemy schema from the technical spec, Alembic migrations,
   deterministic fake-broker holdings/transactions/lots, and health checks.
   Keep fixture inputs clearly marked DEMO and broker writes unavailable.

2. Implement policy draft/save/activate with user-defined sleeves, nested
   US ETF/direct-indexing target, allowed ETF pairs/triplets, tax profile,
   loss carryforwards, gain budgets and drift bands. Validate allocation
   totals with Decimal and reject any active policy unless its top-level
   and nested targets add up to EXACTLY 100%, with no tolerance.
   Use the example policy from the functional spec as editable seed data,
   not hard-coded domain logic.

3. Implement APIs for current portfolio, lots, active/draft policy, sync,
   optimizer runs, `GET /api/v1/optimizer/runs/{id}/recommendations`,
   selections, wash-sale view and activity as specified.
   Fake-broker mode should behave as if a complete current snapshot was
   imported; do not fabricate real quote timestamps or actual tax benefits.

4. Build the Vue 3 + Quasar UI using real Quasar components and typed API
   calls through Pinia. All six navigation pages must render. Prioritize
   a visually faithful Overview and Allocation Policy (including current /
   target / proposed US ETF transition hierarchy and editable sleeves).
   Implement expandable ranked trade groups, exact-lot detail, subset
   selection and a review screen with clear "no order placed" messaging.

5. In Phase 1, recommendations may be DETERMINISTIC DEMO fixtures, clearly
   labeled. Do not pretend an optimizer is calculating them. Build clean
   domain and UI interfaces for the real optimizer in Phase 2. Ensure
   selection changes trigger or request fresh cash/tax/exposure validation
   rather than silently preserving stale totals.

6. Write backend and frontend tests for policy exact-sum activation,
   user-created sleeves (including cash), editable ETF sets, demo sync,
   lot IDs, grouped recommendations, selection behavior and no-trade state.
   Add useful run commands to README.md without duplicating setup steps.

Do not implement live E*TRADE order placement in this first milestone.
Later phases, after Phase 1 passes:
- Phase 2: real wash-sale/tax engine, candidate generation, CVXPY/OSQP
  optimizer, whole-share lot selection, independent Decimal validation,
  coherent priority ranking, ~460-security/2,500-lot benchmark.
- Phase 3: E*TRADE OAuth and read-only complete portfolio/lot/transaction
  sync, coverage checks and reconciliation.
- Phase 4: E*TRADE order preview/placement with explicit distinct approval
  per exact order, safe partial-fill handling and audit trail, subject to
  current E*TRADE account permissions and API terms.

At the end: report files changed, migrations run, test/build commands and
results, a browser/API smoke-test result, any genuinely blocking issue and
how to launch the demo. Prefer a functioning vertical slice to a large
collection of placeholder files.
```

## Phase 1 success criteria

- Quasar + FastAPI + SQLite start locally without broker keys; all six pages load.
- Adjustable example portfolio targets sum **exactly 100%**; arbitrary added/removed sleeves work; invalid drafts are savable but cannot be activated.
- ETF pairs/triplets can be edited; `SCHD` is the dividend candidate in the example. Broker values are authoritative when connected; no fabricated live data.
- The US hierarchy displays current vs target vs recommended; recommendations are explicitly DEMO and show lot-specific sell and related buy legs.
- No automatic or live order placement; frontend build and relevant backend/frontend tests actually pass.
