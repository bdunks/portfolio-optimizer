# Portfolio Optimizer — Technical Specification

**Version:** 1.2 · **Date:** 2026-11-05  
**Authority:** `01_functional_specification.md` defines financial behavior; this specification defines implementation. `portfolio_tax_optimizer_reference.html` controls visual design only. `AGENTS.md` defines agent workflow.

## 1. Architecture decision record

| Concern      | Decision                                                                     | Reason                                                    |
| ------------ | ---------------------------------------------------------------------------- | --------------------------------------------------------- |
| Deployment   | Local-only, single-user Linux workstation, API on `127.0.0.1`                | No online distribution, accounts or server administration |
| Frontend     | Vue 3, TypeScript, Quasar CLI with Vite, Pinia, Vue Router                   | Responsive, data-dense trade review without React         |
| Backend      | Standard CPython **3.14**, FastAPI, Pydantic v2                              | Typed, testable financial services and API                |
| Environment  | Existing mise; uv installed via mise; backend `.venv` managed by uv          | Reproducible setup                                        |
| Database     | **SQLite**, SQLAlchemy 2, Alembic                                            | Durable relational storage with minimal administration    |
| Computation  | NumPy, SciPy, Polars                                                         | Vectorized screening and numerical transforms             |
| Optimization | CVXPY + OSQP primary; CLARABEL fallback; HiGHS for limited discrete problems | Sparse convex solves and selective integrality            |
| Broker       | E*TRADE OAuth 1.0a adapter and deterministic fake adapter                    | Broker isolation, manual-order safety                     |
| Testing      | Pytest/Hypothesis, Vitest/Vue Test Utils, browser smoke tests                | Finance/UX correctness and solver benchmarks              |

Use a **modular monolith**. No microservices, message queues, multi-year planner, PostgreSQL, Docker or DB-inspection product feature. Long solves may run in a local background _process_ invoked by FastAPI; they must never block the event loop. Keep standard (GIL-enabled) Python 3.14; verify dependency installation via `uv sync` on the development Linux machine.

**PyPortfolioOpt:** Do not make it a core dependency. Its discrete-allocation utilities target ticker weights; they do not model source tax lots, gains and losses, approval dependencies or wash-sale restrictions. Build tax-lot-aware integerization/repair in this application. It can be used as an optional comparison tool, not as the trade decision-maker.

## 2. Repository layout and module ownership

Illustrative responsibilities; Codex may split or combine files when useful, but should preserve these boundaries. Existing Quasar/uv scaffolding must not be regenerated.

```text
portfolio-optimizer/
├── README.md
├── AGENTS.md
├── mise.toml
├── docs/
│   ├── 01_functional_specification.md
│   ├── 02_technical_specification.md
│   └── portfolio_tax_optimizer_reference.html
├── frontend/
│   ├── package.json
│   └── src/
│       ├── layouts/MainLayout.vue
│       ├── pages/
│       │   ├── OverviewPage.vue
│       │   ├── RecommendationsPage.vue
│       │   ├── TaxLotsPage.vue
│       │   ├── PolicyPage.vue
│       │   ├── WashSalesPage.vue
│       │   └── ActivityPage.vue
│       ├── components/
│       │   ├── USAllocationTransition.vue
│       │   ├── AllocationTargets.vue
│       │   ├── TaxProfileEditor.vue
│       │   ├── TradeGroup.vue
│       │   ├── LotTable.vue
│       │   └── OrderReviewDialog.vue
│       ├── stores/{portfolio,policy,recommendations}.ts
│       ├── services/api.ts
│       └── types/api.ts
└── backend/
    ├── pyproject.toml
    ├── uv.lock
    ├── app/
    │   ├── main.py
    │   ├── api/{health,portfolio,policy,runs,recommendations,approval}.py
    │   ├── schemas/               # Pydantic transport DTOs
    │   ├── core/{config,logging,security}.py
    │   ├── domain/{allocation,tax,wash_sales,exposure,orders}.py
    │   ├── db/{models,session,repositories}.py
    │   ├── broker/{protocol,etrade,fake}.py
    │   ├── services/{sync,market_data,policy_validation,reconciliation}.py
    │   └── optimizer/{candidates,model,rounding,validation,ranking}.py
    ├── migrations/
    ├── tests/{unit,integration,optimization,fixtures}/
    └── data/                     # ignored local database and backups
```

API, SQLAlchemy, broker and optimizer concerns should not leak into Vue components. The finance core should be callable and testable without FastAPI: `optimize(portfolio_state, active_policy) -> ranked_trade_groups`.

## 3. Data flow and trust boundaries

```text
 E*TRADE API ──> validated broker adapter ──> atomic current-state sync
                                                    │
                 current positions/lots/cash/quotes/transactions (SQLite)
                                                    │
 historical market/exposure metadata ───────────────┤ [coverage + freshness]
                                                    ▼
 tax profile + allocation policy ──────> candidates + wash-sale checks
                                                    │
                                                    ▼
                             joint optimizer + whole-share/lot repair
                                                    │
                                                    ▼
                         independent accounting/risk validation
                                                    │
                                                    ▼
                    immutable run inputs + ranked trade groups (SQLite)
                                                    │
                                      FastAPI DTOs ──> Quasar/Pinia UI
                                                    │
                              user selects subset; revalidate/re-solve
                                                    │
                                exact order preview + manual approval
                                                    │
                                broker submit, fills, reconciliation
                                                    │
                         refresh current state; invalidate stale groups
```

Only the backend accesses E*TRADE and holds credentials. The UI presents proposals, never arbitrary broker order payloads. Validate untrusted response types, pagination, timestamps, IDs, quantities, cost bases and duplicates. A selection or optimizer run **cannot** place an order.

## 4. Relational persistence model

### 4.1 Principles

Store broker positions, lots, transactions, targets, approved securities, recommendation legs and executed orders in **typed, indexed relational rows**. Add tables as the corresponding features are implemented; choose schema boundaries from entity relationships and integrity requirements.

Maintain **one latest complete broker state**, refreshed atomically after a successful sync. Do not create time-series quote/position/lot snapshots on every sync. Preserve (a) broker transaction history needed for tax restrictions and fills and (b) a **frozen input bundle per actual optimization run** so saved recommendations can be explained and audited after the current state changes. A frozen run-input JSON bundle is appropriate for immutable provenance, not primary data access.

### 4.2 Core tables

| Table                     | Representative typed fields / responsibility                                                                                                                               |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `account`                 | Broker account key, account type/tax treatment, latest cash/settled buying power, enabled flag                                                                             |
| `security`                | Stable internal ID, ticker, broker identifiers (CUSIP/ISIN when available), asset type, tradability                                                                        |
| `current_position`        | `(account_id, security_id)` unique; shares, market value, as-of/sync generation                                                                                            |
| `current_tax_lot`         | `(account_id, broker_lot_id)` unique; security FK, acquired date, remaining/available shares, adjusted basis, broker wash adjustments, sync generation                     |
| `current_quote`           | Security ID unique, bid/ask/last, source, timestamp, quote quality; includes candidate ETFs not held                                                                       |
| `broker_transaction`      | Stable broker transaction/order key, account, security, kind, timestamp, shares, amount, DRIP/acquisition flag, lot attribution where present                              |
| `sync_state`              | Current published generation, start/completion timestamps, account coverage, last-error summary and completeness status                                                    |
| `security_exposure`       | Security, dimension/key (sector, country, factor, cap/style, etc.), weight, provider and as-of date; ETF look-through where available                                      |
| `policy_revision`         | Revision/status/effective date, **typed configurable** tax rates, ST/LT carryforwards, YTD realized values, gain and estimated tax budgets, turnover/risk/trading rules    |
| `policy_sleeve`           | Policy revision, stable sleeve key, optional parent sleeve (for nested allocations), target percent, drift bounds, benchmark/transition preferences                        |
| `policy_allowed_security` | Policy revision + sleeve, security, replacement-set identifier, priority, enabled flag; ETF pairs/triplets are data                                                        |
| `optimizer_run`           | Run ID, policy revision, as-of, source generation, solver version/status, metrics/warnings, input fingerprint and frozen input bundle (JSON/blob only for reproducibility) |
| `recommendation_group`    | Run, group rank/type, rationale, estimated benefit, post-trade exposure impact, dependency/selection state                                                                 |
| `recommendation_leg`      | Group, account, security, BUY/SELL, whole shares, estimated unit price, source broker **lot ID for SELL**, ST/LT classification, estimated gain/loss, leg sequencing       |
| `order_record`            | One exact individually approved order; run/leg reference, order fingerprint, approval timestamp, preview/submit IDs, broker status and reconciliation outcome              |
| `order_fill`              | Order FK, broker fill ID, partial/full quantity, price, timestamp and actual lot attribution where reported                                                                |
| `activity_event`          | Append-only sync, policy, run, approval, order and reconciliation events; redacted metadata and correlation ID                                                             |

**Implementation boundaries:** `security_exposure` is populated when real exposure data is integrated; it is not a synthetic factor model. `order_record`/`order_fill` arrive in the last execution phase. Avoid historical `position_snapshot`, `tax_lot_snapshot`, `quote_snapshot`, `wash_sale_assessment`, `corporate_action` and `external_tax_event` subsystems. E*TRADE's adjusted basis/quantities are authoritative; material unexplained changes are surfaced as reconciliation errors, not silently manufactured corporate actions.

### 4.3 Integrity, units and lifecycle

- FKs, unique broker IDs, nonnegative available quantities, positive prices, `CHECK` constraints for enum-like states, and meaningful indexes on `(account_id, security_id)`, `(security_id, transaction_time)`, `(run_id, rank)`, and `(account_id, broker_lot_id)`.
- Persist monetary totals in **integer minor units** where valid and adjusted per-share basis/quantities as lossless canonical decimal strings or consistently scaled integers. SQLite `NUMERIC` affinity can store floating point: do **not** assume a SQLAlchemy `Numeric` declaration guarantees exact decimals. Use Python `Decimal` for tax/cash accounting; `float64` only in solver matrices and independently validate rounded trades.
- Current positions/lots/quotes are updated as one published generation on complete success; no half-updated portfolio. Keep transactions short and never hold SQLite writes during broker HTTP calls or optimizer execution.
- Policy revisions are immutable after activation; retain old revisions referenced by runs. Drafts may be edited. Exact top-level target sum **100%**, and each nested allocation sum **100%** within its parent; no epsilon, hidden cash, normalization or asset-class constants.
- A saved run's frozen input includes account/lot balances, quotes, policy version, risk/exposure metadata identity, wash-relevant transactions, solver settings and input checksums. Old runs are read-only; submitted orders always require fresh validation against current state.
- Use `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000` and SQLite's online backup API on local storage. No database exploration tool is an application deliverable.

## 5. E*TRADE adapter and reconciliation

**Read:** OAuth 1.0a; accounts, portfolio **`lotsRequired=true`**, balances/available cash, transaction history, quotes. Page until complete; validate IDs, timestamps and cost basis; preserve exact broker lot IDs. Quote/exposure histories may need a separate provider if the broker data is incomplete. Never expose OAuth credentials/tokens to browser code, Git, or logs. Use `.env` (gitignored) or OS keyring, with `.env.example` placeholders only.

**Write (final delivery phase):** A user selects a small set of ranked groups. Before **each** exact order, refresh relevant cash, quote, security and lots; build a broker preview and show account, side, ticker, whole-share count, order terms and exact sell lot IDs. Obtain **one discrete, contemporaneous, affirmative approval per order**, tied to an order fingerprint and preview; submit only that order with idempotency/retry protection, then reconcile fills and actual lot attribution. Never auto-route a full selected group or continue unattended after partial fills. Recompute dependent trades against refreshed state. Confirm production behavior and E*TRADE account permissions/terms before enabling write mode.

Required adapter methods: `list_accounts`, `fetch_portfolio_with_lots`, `fetch_transactions`, `fetch_balances`, `get_quotes`, then `preview_order`, `submit_approved_order`, `get_order_status`. `FakeBroker` implements the same read and deterministic order-test contract. Live writes fail closed behind a feature flag.

References: https://apisb.etrade.com/docs/api/account/api-portfolio-v1.html ; https://apisb.etrade.com/docs/api/order/api-order-v1.html ; https://developer.etrade.com/support/terms-of-use .

## 6. Tax-aware joint optimizer

### 6.1 Input state and candidate generation

Load current **available** tax-lot quantities, adjusted basis/acquisition date, accounts/cash, prices with source/as-of, valid active policy, approved ETF candidates, ST/LT tax rates, YTD realized values, loss carryforwards, gain/tax budgets, sector/factor/benchmark data when available, recent same-security acquisitions and existing 30-day no-buy restrictions. Exclude pending/reserved shares, stale data and ineligible or uneconomical candidates.

Generate four candidate types: individual-stock loss harvests, gain-aware stock exits into VTI/ITOT, allowed ETF pair/triplet swaps, and allocation/municipal exit trades. Brokerage data determines current values; configured sleeves/tickers are _illustrative defaults_, never hard-coded. Propose **no trades** if no basket beats transaction and tax costs.

### 6.2 Decisions and tax/cash accounting

Decision variables: `s_l` = shares sold from lot `l` (`0 <= s_l <= available_l`), `b_i` = shares bought of allowed security `i` (`b_i >= 0`). No short positions. For each security, `q'_i = q_i - sum_{l in lots(i)} s_l + b_i`.

Per-lot realized result: `g_l = s_l * (estimated_sale_price_i - adjusted_unit_basis_l) - allocated_fees_l`. Determine ST/LT by acquisition versus trade date. Track ST and LT gross gains/losses separately; tax-benefit calculations must account for user-supplied realized results and carryforwards with documented tax netting logic. Do **not** assume each $1 loss offsets $1 of a chosen rate independent of tax status. If rates are missing, show gains/losses but label tax-dollar benefit unavailable.

Enforce hard bounds for available lot shares, no prohibited wash-sale replacement, per-account settled funding, allowed ETFs, exact/within-band allocation requirements, gain/tax/turnover budgets and suitable liquidity. A configured gain budget is **not** necessarily a dollar-for-dollar offset rule; realized gains can be accepted where permitted. Account for trading/market impact and fractional holdings; proposed orders are whole-share unless broker explicitly supports otherwise.

Conceptual objective (use consistently scaled terms):

`min λrisk × tracking_risk + λalloc × drift_penalty + λtax × incremental_tax_cost + λcost × trading_cost + λturn × turnover − λtransition × justified_ETF_consolidation_reward`

The ETF consolidation reward is deliberately modest and cannot override legal, tax, cash or exposure constraints. Report estimated incremental realized ST/LT and cash effects independently of any aggregate score.

### 6.3 Risk and exposure computation

- Top-level sleeve targets apply to **total portfolio value**; nested US ETF/direct-indexing targets apply **within the US sleeve**. Compute post-trade values using full economic portfolio including cash, not just shares traded.
- US sleeve benchmark is a **VTI/ITOT-style total US market**; legacy individual large-cap stocks and VB/VXF completion are modeled together. Do not assume VB/VXF has no overlap; model actual look-through/exposure data.
- Economic sector/country/factor exposures may overlap strategic sleeves (e.g., US dividend-growth ETF exposure). Calculate separately from exclusive policy sleeve assignments; never double-count for target totals.
- Prefer security-/factor-level covariance and ETF look-through or sector/cap/style bands, **not a 2,500-lot covariance matrix**. Map lots to security-level risk exposures. Track source, freshness, coverage and confidence.
- Where benchmark/factor inputs are unreliable, use explicit observable drift/sector constraints and **omit** a numerical tracking-error figure rather than invent precision.

### 6.4 Fast solve, integerization and ranking

1. Vectorized pre-screen lots and eligible ETF substitutions; assemble dependency groups.
2. Solve sparse continuous model with CVXPY/OSQP, exploiting cached parameters/warm starts as practical.
3. Convert to whole-share buys and specific-lot sells; choose lots, repair cash and risk/tax changes. Use a **small** HiGHS discrete subproblem for closed positions, minimum orders or one-of-N ETF swaps if necessary, not an all-binary 2,500-lot MIQP by default.
4. Independently revalidate whole basket with `Decimal` accounting, accurate ST/LT classification, wash checks, lot availability, cash and exposure constraints; refuse/repair invalid output rather than present infeasible orders.
5. Store **priority-ranked coherent groups** plus linked buy/sell legs, explanations, expected tax benefits and exposure/position-count deltas. Rank economic importance separately from execution dependency order; ranking never overrides hard constraints.
6. Support selecting a top-N or arbitrary small subset, recalculate post-selection consequences and re-solve if removing a leg invalidates group balance. Revalidate remaining proposals after an actual order/fill.

### 6.5 Performance targets (acceptance budgets, not measured results)

| Phase                                   | Target p95 with validated, cached input |
| --------------------------------------- | --------------------------------------: |
| Candidate generation / wash checks      |                                   < 1 s |
| Main continuous solve                   |                                   < 3 s |
| Whole-share repair, validation, ranking |                                   < 2 s |
| Complete recommendation computation     |                                  < 10 s |

Benchmark on synthetic ~460-security, 2,500-lot portfolios and actual risk dimensions. Record candidate and constraint count, memory, construction/solve/repair timing, solution feasibility, and integer gaps/timeouts. Broker/network sync is measured separately. Do not claim these targets were achieved until tested.

## 7. Wash-sale rules — project scope

1. Track **each security** across connected E*TRADE accounts using stable IDs and current holdings plus retained E*TRADE acquisition/DRIP transactions. No outside-account or spouse-account imports (user assumes no relevant outside trading).
2. By configured policy assumption, different approved ETF/equity replacement members are **not substantially identical to one another**. The app does not classify equivalence or build a general identity graph. Same-security repurchases **are** checked; candidate approval never exempts the original ticker.
3. For a proposed loss sale, examine acquisitions of the same security in the **prior 30 calendar days** across relevant connected accounts and all proposed buys. Track partial quantities and broker-reported adjusted basis; a known conflict blocks the affected lot/group, with explanation. Incomplete required E*TRADE history blocks relevant harvesting.
4. Record and show a **next-30-calendar-days do-not-buy** restriction for securities with actual executed loss sales. Future optimization excludes incompatible buy candidates until expiry. Evaluate the entire proposed basket, including sequencing and reinvestment purchases; do not rely solely on a UI warning.
5. Wash-sale assessments are computed functions with verdict/reasons persisted in recommendation/run details; **no** `wash_sale_assessment`, `external_tax_event`, or general substantial-identity graph table. Other tax rules and exact return accounting are outside the engine's promises.

## 8. Backend API contracts (JSON over localhost)

Use `/api/v1` for application routes, Pydantic DTOs and consistent errors `{code, message, details, correlation_id}`. Stable endpoints:

| Endpoint                                                       | Contract                                                                                                       |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `GET /health`                                                  | API/schema readiness, fake vs real broker mode                                                                 |
| `POST /api/v1/portfolio/sync`                                  | Initiate read-only sync; publish an atomic complete current generation or return structured error              |
| `GET /api/v1/portfolio`                                        | Current positions, accounts, cash, sleeve totals, sync timestamps/coverage                                     |
| `GET /api/v1/lots`                                             | Paginated/filterable current lots with exact broker identifiers                                                |
| `GET /api/v1/policy`                                           | Active/draft policies and tax-profile inputs                                                                   |
| `POST /api/v1/policy/drafts`                                   | Save an editable, versioned policy draft                                                                       |
| `POST /api/v1/policy/{id}/activate`                            | Validate exact 100% sums (top level and nested) and other hard rules                                           |
| `POST /api/v1/optimizer/runs`                                  | Generate recommendation run **only**, no orders                                                                |
| `GET /api/v1/optimizer/runs/{id}`                              | Run status, summary metrics, solver provenance, warnings/infeasibility                                         |
| `GET /api/v1/optimizer/runs/{id}/recommendations`              | Priority-ordered recommendation groups and lot-specific BUY/SELL legs, dependent trade IDs, trade explanations |
| `POST /api/v1/optimizer/runs/{id}/selection`                   | Proposed subset + selected basket version; revalidate/re-solve against current data                            |
| `PATCH /api/v1/optimizer/runs/{id}/recommendations/{group_id}` | Save a user note/rejection reason on a proposed group without executing anything                               |
| `GET /api/v1/optimizer/runs/{id}/export`                       | CSV or JSON via `format` query; recommendations include run, policy, prices/as-of and warnings                 |
| `GET /api/v1/wash-sales`                                       | E*TRADE-derived purchase restrictions and next eligible dates                                                  |
| `GET /api/v1/activity`                                         | Filterable sync, policy, run, approval and reconciliation history                                              |
| `POST /api/v1/orders/{leg_id}/preview`                         | Last phase: fresh exact-order preview without submission                                                       |
| `POST /api/v1/orders/{leg_id}/submit`                          | Last phase: separately approved **exact** order; guarded against duplicates                                    |

`GET /api/v1/optimizer/runs/{id}` returns compact run state; its `/recommendations` child route is the paginated/sortable detailed result. Selection updates produce a versioned projection; stale selections cannot be executed. All mutating routes validate local session/origin/request and order-specific approval. `POST /optimizer/runs` and policy changes can never call the broker write adapter.

Illustrative run POST:

```json
{ "mode": "recommendations_only", "minimum_benefit_usd": "50.00" }
```

Illustrative run summary (tax benefit is nullable when inputs are incomplete):

```json
{
  "run_id": "run-41",
  "status": "complete",
  "policy_revision_id": "policy-7",
  "source_generation": 35,
  "estimated_realized_st_usd": "-1300.00",
  "estimated_realized_lt_usd": "850.00",
  "estimated_tax_benefit_usd": null,
  "estimated_tax_benefit_status": "tax_profile_incomplete",
  "constraints_satisfied": true,
  "warnings": []
}
```

## 9. Frontend design contract

- Recreate the HTML reference in real Quasar components (`QLayout`, `QDrawer`, `QHeader`, `QPage`, `QCard`, `QTable`, `QDialog`, `QBadge`, `QInput`, `QSelect`, `QToggle`, `QBtn`, `QBanner`, `QTooltip`); desktop-first, tablet-aware, keyboard-accessible.
- `components/` owns reusable transition hierarchy, allocation/tax editors, trade-group panels, lots and order dialogs. `stores/` owns API-loaded state, drafts, run selection, loading/error modes. `services/api.ts` is the typed transport; do not reimplement financial math in Vue.
- All six screens: Overview, Recommendations, Tax Lots, Allocation Policy (including **Tax Settings**), Wash Sales, Activity.
- US transition shows **current, target and proposed** and clearly identifies whether each percentage is total-portfolio or within-US-sleeve. Policy editor supports arbitrarily named sleeves (including cash), target sums equal to **exactly 100%**, ETF pairs/triplets, drift bands and persisted ST/LT tax settings, carryforwards, YTD realized amounts, gain/tax budgets.
- Recommendations are expandable **ranked groups** with lot-specific legs, dependencies, estimated ST/LT effects and cash/exposure deltas; user can choose a subset. Show no-trade, stale-data, infeasible and incomplete-tax-profile states without fabricating figures.
- Demo values in the HTML reference are illustrative and must never be used as live investment results. Order review explicitly requires individual exact-order approval in the final phase.

## 10. Local security, persistence and operations

- Bind backend to `127.0.0.1`, restrict CORS to the local frontend dev origin; use session/origin checks for state-changing endpoints. Local-only is **not** permission to skip order authorization.
- Protect SQLite with OS user file permissions and disk encryption where available. SQLite is not encrypted by default. Keep DB, `.env`, credentials, tokens, account exports, sensitive logs and backups out of Git; `.env.example` contains placeholders only. Optionally use OS keyring.
- Apply SQLAlchemy/Alembic migrations; test migration from an existing DB. WAL, short write transactions, FK enforcement and busy timeout. Store DB on local disk; use SQLite online backup API, verify restores and periodically run integrity checks; don't blindly copy a live WAL file.
- Log structured request/job IDs, solver version, input fingerprint and reasons for rejected trades without logging tokens or raw account identifiers. Handle broker timeouts/rate limits and local process failures without partially publishing state.
- Optimizer runs are tied to policy revision and source-generation input; recheck quotes, lot availability, cash and restrictions before every approval/submit. Browser does not store secrets or directly call broker APIs.

## 11. Testing and acceptance

**Unit:** `Decimal` exact 100% top/nested policy validation, editable cash/custom sleeves, tax-rate/carryforward persistence, ST/LT boundaries and netting, fees, lot-adjusted basis, same-security wash checks across E*TRADE accounts (including DRIPs and post-sale buys), eligibility and funding.

**Optimizer:** Deterministic and randomized ~460-security/2,500-lot fixtures; no oversells, shorts, cash deficits, unwanted purchases, invalid wash-sale rebuys, missing lot IDs or broken dependencies. Compare proposed full-basket accounting and risk deltas against independently computed output. Perturb lot ordering and solver conditions; test infeasible/timeout/no-trade cases and whole-share repair.

**Integration:** Fake-broker pagination, stale auth, incomplete lot/transaction pages, incorrect totals, partial order fills and lot mismatches; atomic current-generation sync; policy migration/versioning; reproducible saved run inputs; explicit per-order approval and idempotency.

**UI:** Six routes; editable targets and ETF sets; exact-100% activation validation; 45/24/17/14/0 example is _seed only_; SCHD dividend ticker; tax settings and reload persistence; trade-group filtering, annotations, exports, expansion/selection/revalidation; saved-run reopening; no-trade display and keyboard-accessible per-order dialog.

**Performance:** Capture p50/p95, memory, solver configuration, dimensions, candidate counts and optimality gap on development hardware. Never report a speed threshold as measured without a benchmark.

## 12. Sequenced delivery

1. **Foundation/offline vertical slice:** Existing mise/uv/Quasar scaffolding; typed DB schema/migrations, fake broker, policy validation, API DTOs, all six pages and functioning demo flows.
2. **Real optimizer:** E*TRADE-independent tax, wash-sale and exposure logic; candidate generation, CVXPY/OSQP solve, integerization, independent validation, ranked groups; performance benchmark and no-trade behavior.
3. **E\*TRADE read integration:** OAuth, paginated holdings/lot/transaction sync, cash reconciliation, real market-data freshness, incomplete-data safeguards; read-only integration tests.
4. **Security and reliability hardening:** migration/restart/backup tests; exceptional-state UI, reconciliation, stable API contracts and end-to-end manual QA.
5. **Manually approved E\*TRADE order writes (last):** exact preview and discrete affirmative approval for every order; protected broker submission, fills and lot reconciliation, safe stopping/revalidation after subsets; confirm current terms and permissions before release.

No separate multi-year projection subsystem, external-tax event imports, or broker automation without individual user approval.

## 13. References

- SQLite: https://www.sqlite.org/whentouse.html ; WAL: https://www.sqlite.org/wal.html
- Quasar: https://quasar.dev/start/quick-start/
- uv: https://docs.astral.sh/uv/guides/projects/
- CVXPY: https://www.cvxpy.org/ ; OSQP: https://osqp.org/
- PyPortfolioOpt postprocessing (considered, not core): https://pyportfolioopt.readthedocs.io/en/latest/Postprocessing.html
- E*TRADE broker and order docs, terms: links in §5
