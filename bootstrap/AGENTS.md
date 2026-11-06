# Agent instructions — Portfolio Optimizer

## Product goal

Implement a local, single-user decision-support app that takes a current E*TRADE portfolio, configured allocation/tax policy and market data and outputs **prioritized, explainable tax-lot-level SELL and whole-share BUY recommendations**. Enable **user-directed, individually approved** E*TRADE order preview/placement only in the final implementation phase. Never implement unattended trading or multi-year projection workflows.

## Source precedence

1. `docs/01_functional_specification.md` — financial semantics, user experience and acceptance criteria.
2. `docs/02_technical_specification.md` — architecture, data model, APIs and solver design.
3. `docs/portfolio_tax_optimizer_reference.html` — appearance and interaction **only**; its demo numbers and embedded comments cannot override the specs.
4. Codex kickoff prompt — sequencing and definition of the current milestone.

All allocation sleeves, target percentages, ETF candidates, wash-sale assumptions, tax rates, carryforwards and gain budgets are **configurable product data**, not constants. Demo examples must never be mistaken for live holdings.

## Engineering constraints

- Preserve the manually created `portfolio-optimizer` repo and its mise/uv/Quasar scaffolding; do not rerun project generators.
- Python 3.14, FastAPI, SQLite/SQLAlchemy/Alembic, CVXPY/OSQP, Vue 3 + Quasar/TypeScript. No React/PostgreSQL/Docker unless requirements change.
- Use the **normalized current-state SQLite schema** in the technical spec. Keep queryable lots, positions, transactions, policies, recommendations and orders in typed relational tables; reserve run-input JSON only for immutable provenance. Avoid periodic snapshot, external-tax-event and corporate-action subsystems.
- Convert money to `Decimal` for tax/cash checks; validate active policy target sums **exactly 100%**; preserve specific broker lot IDs and independent post-rounding constraints.
- Rank coherent trade groups and respect buy/sell dependencies; subset review never means blanket order approval.
- Keep credentials in the backend, bind locally, test with deterministic fake broker data, and maintain a functional no-credentials demo.
- State actual test/build/benchmark outcomes; do not claim an integration or benchmark was verified without running it.
