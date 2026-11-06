# Agent instructions — Portfolio Optimizer

## Product goal

Implement a local, single-user, **single-account** decision-support app that takes a current E*TRADE brokerage account portfolio, configured allocation/tax/batch policy and market data (including Vanguard JSON and iShares CSV ETF look-through holdings) and outputs **prioritized, explainable, small-batch tax-lot-level SELL and whole-share BUY recommendations**. Enable **user-directed, individually approved** E*TRADE order preview/placement only in the final implementation phase (Phase 5). Never implement unattended trading, multi-account routing or multi-year projection workflows.

## Source precedence

1. `docs/01_functional_specification.md` — financial semantics, user experience and acceptance criteria.
2. `docs/02_technical_specification.md` — architecture, data model, exact tax netting equations, APIs and 2-pass small-batch solver design.
3. `docs/portfolio_tax_optimizer_reference.html` — appearance and interaction **only**; its demo numbers and embedded comments cannot override the specs.

All allocation sleeves, target percentages, ETF candidates, wash-sale assumptions, tax rates, carryforwards, retained TLH targets, gain budgets and small-batch limits are **configurable product data**, not constants. Demo examples must never be mistaken for live holdings.

## Engineering constraints

- Use the **normalized current-state SQLite schema** in the technical spec for the **single managed E*TRADE account**. Keep queryable lots, positions, transactions, policies, overrides, cached look-through exposures, recommendations and orders in typed relational tables; reserve run-input JSON only for immutable provenance. Avoid periodic snapshot, multi-account, external-tax-event and corporate-action subsystems.
- Convert money to `Decimal` for tax/cash checks; implement the exact IRS ST/LT netting function $T(S, L)$ with configurable `target_retained_net_loss_usd`; validate active policy target sums **exactly 100%**; resolve all individual equities + `VB`/`VXF` to the US direct-indexing container sleeve by default; preserve specific broker lot IDs and independent post-rounding constraints.
- Enforce **small-batch execution limits** (`max_sell_tickers_per_batch`, `max_sell_lots_per_batch`, `max_total_orders_per_batch`) via the 2-pass screen-then-solve-batch architecture (`10.0s` timeout budget). Do **not** block small legacy/DRIP lot sales with a minimum sell notional—reward lot and position cleanup and consolidate multi-lot sales of the same ticker into a single SELL order.
- Rank coherent trade groups and respect buy/sell dependencies; subset changes trigger a fast Pass 2 re-solve of replacement ETF buys; subset review never means blanket order approval.
- Keep credentials in the backend, bind locally (`127.0.0.1`), test with deterministic fake broker data, and maintain a functional no-credentials demo.
- State actual test/build/benchmark outcomes; do not claim an integration or benchmark was verified without running it.

