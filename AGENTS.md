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

# Backlog

Use the backlog to plan substantial or multi-step work on this project, or when the user asks to work from it. Don't create backlog entries for every small fix.

Inspect relevant existing projects, milestones, and tasks before planning or structural changes. Running or completing the selected task does not require listing projects, milestones, or sibling tasks. Don't initialize or reset an existing database, delete work, promote Draft items, or mark tasks Done without a request or an agreed plan.

Common backlog commands (run from the repository root):

- `backlog task next --json` — find eligible work with task, milestone, and project context, including their instructions. No follow-up `task show` is required to start work.
- `backlog task show <id> --json` — inspect a specific task and its context when needed. (`task <id>` is not a command.)
- `backlog task list --milestone <id> --json` — inspect tasks and their order before changing a milestone.
- `backlog milestone list --json` — inspect milestones before adding or moving work.
- `backlog task create --milestone <id> --title TEXT --instructions TEXT --done-when TEXT --state Draft --json` — create a draft task and capture its ID.
- `backlog task move <id> --milestone <id> --position N` — move a task to a zero-based position.
- `backlog task done <id> [--handoff TEXT]` — complete eligible work; include a handoff for useful outcomes, decisions, deviations, or context for subsequent work. Omit it when there is nothing useful to pass on.
- `backlog --help` and `backlog <command> --help` — see all commands and flags.

When creating or editing backlog tasks, use well formatted human readable markdown.

For the agreed five-phase program, backlog is authoritative for task definitions, prerequisites, completion and handoffs. The program supervisor alone selects and completes tasks and milestones after their agreed verification gates pass. Phase orchestrators delegate only assigned work; implementation/review workers report results and do not select other tasks or mark work Done. Use explicit prerequisites, not milestone order alone, to enforce phase acceptance. Draft alternatives remain deferred. The CLI has no in-progress claim state: keep task selection centralized. Save active child run IDs, working directories/refs, checkpoint, partial work, retries and next action in the selected task's backlog handoff before interruption; preserve useful existing context.
