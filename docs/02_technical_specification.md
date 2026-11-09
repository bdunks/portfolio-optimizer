# Portfolio Optimizer — Technical Specification

**Version:** 1.3 · **Date:** 2026-11-05  
**Authority:** `01_functional_specification.md` defines financial behavior; this specification defines implementation. `portfolio_tax_optimizer_reference.html` controls visual design only. `AGENTS.md` defines agent workflow.

## 1. Architecture decision record

| Concern      | Decision                                                                     | Reason                                                    |
| ------------ | ---------------------------------------------------------------------------- | --------------------------------------------------------- |
| Deployment   | Local-only, single-user, **single-account** Linux workstation (`127.0.0.1`)  | No online distribution, multi-account routing or admin    |
| Frontend     | Vue 3, TypeScript, Quasar CLI with Vite, Pinia, Vue Router                   | Responsive, data-dense trade review without React         |
| Backend      | Standard CPython **3.14** (fallback 3.13), FastAPI, Pydantic v2              | Typed, testable financial services and API                |
| Environment  | Existing mise; uv installed via mise; backend `.venv` managed by uv          | Reproducible setup                                        |
| Database     | **SQLite**, SQLAlchemy 2, Alembic                                            | Durable relational storage with minimal administration    |
| Computation  | NumPy, SciPy, Polars                                                         | Vectorized screening and numerical transforms             |
| Optimization | CVXPY + OSQP primary; CLARABEL fallback; HiGHS for limited discrete problems | Sparse convex solves and selective integrality            |
| Broker       | E*TRADE OAuth 1.0a (`oob`) adapter and deterministic fake adapter            | Single-account isolation, manual-order safety             |
| Testing      | Pytest/Hypothesis, Vitest/Vue Test Utils, browser smoke tests                | Finance/UX correctness and solver benchmarks              |

Use a **modular monolith** managing **one configured E*TRADE brokerage account**. No microservices, message queues, multi-year planner, PostgreSQL, Docker or DB-inspection product feature. Optimizer solves run off the FastAPI event loop in a bounded, supervised worker process with solver-native time limits and deadline enforcement (§6.5) with a **10.0-second timeout budget (`SOLVER_TIMEOUT_SECONDS = 10.0`)** and return synchronously in the HTTP response (see §8). Keep standard (GIL-enabled) Python 3.14; verify dependency installation via `uv sync` on the development Linux machine.

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
    │   ├── api/{health,auth,portfolio,policy,runs,recommendations,approval}.py
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
 E*TRADE API ──> validated broker adapter ──> atomic single-account state sync
                                                    │
                 current positions/lots/cash/quotes/transactions (SQLite)
                                                    │
 Vanguard JSON + iShares CSV ETF look-through ──────┤ [coverage + freshness]
                                                    ▼
 tax profile + allocation/batch policy ──> candidates + 30d wash-sale checks
                                                    │
                                                    ▼
                     2-pass small-batch optimizer + whole-share/lot repair
                                                    │
                                                    ▼
                         independent Decimal accounting/risk validation
                                                    │
                                                    ▼
                    immutable run inputs + ranked trade groups (SQLite)
                                                    │
                                      FastAPI DTOs ──> Quasar/Pinia UI
                                                    │
                         user selects group/lot subset; batch re-solve
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

Store single-account broker positions, lots, transactions, targets, approved securities, recommendation legs and executed orders in **typed, indexed relational rows**. Add tables as the corresponding features are implemented; choose schema boundaries from entity relationships and integrity requirements.

Maintain **one latest complete broker state** for the single managed account, refreshed atomically after a successful sync. Do not create time-series quote/position/lot snapshots on every sync. Preserve (a) broker transaction history needed for tax restrictions and fills and (b) a **frozen input bundle per actual optimization run** so saved recommendations can be explained and audited after the current state changes. A frozen run-input JSON bundle is appropriate for immutable provenance, not primary data access.

### 4.2 Core tables

| Table                       | Representative typed fields / responsibility                                                                                                                                                                                                                                                                                                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `account`                   | Single managed E*TRADE account (`broker_account_id_key`, display name, account type/tax treatment, latest cash/settled buying power, active flag)                                                                                                                                                                                                                                                                  |
| `security`                  | Stable internal ID, ticker, broker identifiers (CUSIP/ISIN when available), `asset_type` (`EQUITY` \| `ETF`), `is_completion_etf` (`true` for `VB`/`VXF`), `vanguard_fund_id`, `ishares_holdings_url`, tradability                                                                                                                                                                                                 |
| `current_position`          | `(account_id, security_id)` unique; shares, market value, as-of/sync generation                                                                                                                                                                                                                                                                                                                                    |
| `current_tax_lot`           | `(account_id, broker_lot_id)` unique; security FK, acquired date, remaining/available shares, adjusted basis, broker wash adjustments, sync generation                                                                                                                                                                                                                                                             |
| `current_quote`             | Security ID unique, bid/ask/last, source, timestamp, quote quality; includes candidate ETFs not held                                                                                                                                                                                                                                                                                                               |
| `broker_transaction`        | Stable broker transaction/order key, account, security, kind, timestamp, shares, amount, acquisition flag, lot attribution where present                                                                                                                                                                                                                                                                           |
| `sync_state`                | Current published generation, start/completion timestamps, account coverage, look-through freshness, last-error summary and completeness status                                                                                                                                                                                                                                                                    |
| `security_exposure`         | Security, dimension/key (constituent ticker/CUSIP, sector, country, cap/style, etc.), weight, `provider` (`vanguard` \| `ishares` \| `manual_csv`), `as_of_date`; caches ETF look-through weights                                                                                                                                                                                                                  |
| `policy_revision`           | Revision/status/effective date; **tax rates:** `short_term_tax_rate`, `long_term_tax_rate` (nullable `Decimal`); **carryforwards & YTD:** `st_loss_carryforward_usd`, `lt_loss_carryforward_usd`, `ytd_realized_st_usd`, `ytd_realized_lt_usd`, `ytd_source`, `ytd_as_of`; **TLH retention:** `target_retained_net_loss_usd` (default `3000.00`), `ordinary_income_deduction_limit_usd` (default `3000.00`), `carryforward_loss_discount_factor` (default `0.50`); **budgets:** `gain_budget_usd`, `max_incremental_tax_cost_usd`, `st_gain_limit_usd`, `lt_gain_limit_usd`, `budget_period`; **batch & trading limits:** `max_sell_tickers_per_batch` (default `10`), `max_sell_lots_per_batch` (default `20`), `max_total_orders_per_batch` (default `12`), `max_batch_turnover_pct` (default `5.0`), `min_buy_order_notional_usd` (default `500.00`), `cash_reserve_usd` (default `0.00`); **rule flags:** `prefer_etf_buys`, `allow_gain_sales`, `permit_etf_harvest`, `permit_muni_exit` |
| `policy_sleeve`             | Policy revision, stable `sleeve_key`, display name, sort order, optional `parent_sleeve_key` (for nested allocations), `target_pct`, `drift_band_pp`, `is_direct_index_container` (`true` for the US total-market sleeve), `is_transition_destination` (one explicitly designated New sub-sleeve), `is_cash_sleeve`, enabled flag                                                                                                                                                          |
| `policy_allowed_security`   | Policy revision + sleeve, security, replacement-set identifier, priority, enabled flag; ETF pairs/triplets are data                                                                                                                                                                                                                                                                                                |
| `policy_security_override`  | `(policy_revision_id, security_id)` unique; `sleeve_key`, optional `sub_sleeve_key`; only populated when a user explicitly overrides default holding-to-sleeve resolution or reassigns holdings during sleeve deletion                                                                                                                                                                                             |
| `optimizer_run`             | Run ID, policy revision, as-of, source generation, solver version/status, batch settings used, metrics/warnings, input fingerprint and frozen input bundle (JSON/blob only for reproducibility)                                                                                                                                                                                                                    |
| `recommendation_group`      | Run, group rank/type, sleeve key, rationale, estimated benefit, post-trade exposure impact, lot/position count delta, dependency/selection state                                                                                                                                                                                                                                                                   |
| `recommendation_leg`        | Group, account, security, `BUY`/`SELL`, total whole shares, estimated unit price, `selected_lots` (typed child rows or JSON array of `{broker_lot_id, shares, acquired_date, adjusted_basis, st_lt, realized_pl}` for `SELL` legs so multiple lots of the same ticker consolidate into one order), net ST/LT realized gain/loss, leg sequencing                                                                     |
| `order_record`              | One exact individually approved order; run/leg reference, order fingerprint, approval timestamp, preview/submit IDs, broker status and reconciliation outcome                                                                                                                                                                                                                                                      |
| `order_fill`                | Order FK, broker fill ID, partial/full quantity, price, timestamp and actual lot attribution where reported                                                                                                                                                                                                                                                                                                        |
| `activity_event`            | Append-only sync, policy, run, approval, order and reconciliation events; redacted metadata and correlation ID                                                                                                                                                                                                                                                                                                     |

**Holding-to-sleeve resolution precedence (`domain/allocation.py`):**
Every held security in `current_position` resolves to a single `policy_sleeve` in the active `policy_revision` via:
1. Explicit row in `policy_security_override(policy_revision_id, security_id)`.
2. Membership in `policy_allowed_security(policy_revision_id, security_id)` (e.g., `VTI`/`ITOT` -> `us` (`etf` sub-sleeve), `VIG`/`DGRO`/`SCHD` -> `div`, etc.).
3. Default direct-indexing rule: if `security.asset_type == 'EQUITY'` or `security.is_completion_etf == True` (`VB`, `VXF`), resolve to the sleeve with `is_direct_index_container == True` (`us` -> `direct_indexing` sub-sleeve). This maps all ~450 individual US stocks + `VB`/`VXF` automatically with zero manual configuration rows.
4. Settled cash maps to the `is_cash_sleeve == True` sleeve when enabled, or remains in unallocated account cash subject to `cash_reserve_usd`.



**US transition progress is explicit policy data, separate from holdings assignment:** exactly one enabled sleeve may be designated `is_transition_destination`. It must be a strict descendant of the unique enabled direct-index container and must be disjoint from (neither ancestor nor descendant of) the enabled `is_direct_index_sleeve` legacy branch. Progress is the value assigned to that sleeve plus all nested descendants, of any asset type or ticker, divided by the container value. Sibling ETF assets do not count. No designation means progress is unavailable (`null`), never inferred from ETFs, names, or sibling exclusion. Frozen historical policy provenance that lacks this field remains unconfigured; migrations do not infer designations.
**Implementation boundaries:** `security_exposure` is populated from the Vanguard JSON and iShares CSV look-through adapters (plus seed fixtures in demo mode); it is not a synthetic factor model. `order_record`/`order_fill` arrive in the last execution phase. Avoid historical `position_snapshot`, `tax_lot_snapshot`, `quote_snapshot`, `wash_sale_assessment`, `corporate_action` and `external_tax_event` subsystems. E*TRADE's adjusted basis/quantities are authoritative; material unexplained changes are surfaced as reconciliation errors, not silently manufactured corporate actions.

### 4.3 Integrity, units and lifecycle

- FKs, unique broker IDs, nonnegative available quantities, positive prices, `CHECK` constraints for enum-like states, and meaningful indexes on `(account_id, security_id)`, `(security_id, transaction_time)`, `(run_id, rank)`, and `(account_id, broker_lot_id)`.
- Persist monetary totals in **integer minor units** where valid and adjusted per-share basis/quantities as lossless canonical decimal strings or consistently scaled integers. SQLite `NUMERIC` affinity can store floating point: do **not** assume a SQLAlchemy `Numeric` declaration guarantees exact decimals. Use Python `Decimal` for tax/cash accounting; `float64` only in solver matrices and independently validate rounded trades.
- Current positions/lots/quotes are updated as one published generation on complete success; no half-updated portfolio. Keep transactions short and never hold SQLite writes during broker HTTP calls or optimizer execution.
- Policy revisions are immutable after activation; retain old revisions referenced by runs. Drafts may be edited. Exact top-level target sum **100%**, and each nested allocation sum **100%** within its parent; no epsilon, hidden cash, normalization or asset-class constants. Deleting or disabling a sleeve in a draft requires a `reassign_to_sleeve_key` target so no holdings are orphaned.
- A saved run's frozen input includes account/lot balances, quotes, policy version, risk/exposure metadata identity, wash-relevant transactions, solver settings and input checksums. Old runs are read-only; submitted orders always require fresh validation against current state.
- Use `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000` and SQLite's online backup API on local storage. No database exploration tool is an application deliverable.

## 5. E*TRADE adapter, OAuth 1.0a flow, and ETF look-through providers

**Single-account scope:** The backend manages **one configured E*TRADE brokerage account** (`ETRADE_ACCOUNT_ID_KEY` in `.env`, or bound on first sync). If `list_accounts` returns multiple accounts, only the configured account is synced and traded.

1. `POST /api/v1/auth/etrade/start`: Backend requests a temporary OAuth 1.0a token from E*TRADE (`GET /oauth/request_token` with `oauth_callback="oob"`), holds the request token secret in memory (never in SQLite or logs), and returns `{authorize_url: "https://us.etrade.com/e/t/etws/authorize?key=...&token=..."}`.
2. User opens `authorize_url` in their browser, logs in, approves access, and copies the 5–6 character `oauth_verifier` code displayed by E*TRADE.
3. `POST /api/v1/auth/etrade/verify`: Accepts `{verifier}`, exchanges it via `GET /oauth/access_token`, stores the active access token/secret in backend memory or OS keyring, and binds the configured account.
4. **Renewal & expiry:** E*TRADE access tokens go inactive after **2 hours** of idle time (automatically call `GET /oauth/renew_access_token` before sync/preview when idle $>90$ minutes) and hard-expire at **midnight US Eastern** daily. `GET /api/v1/auth/etrade/status` reports live authentication and expiry status.

**Read:** OAuth 1.0a; managed account portfolio with **`lotsRequired=true`**, balances/available cash, transaction history, quotes. Page until complete; validate IDs, timestamps and cost basis; preserve exact broker lot IDs. Never expose OAuth credentials/tokens to browser code, Git, or logs. Use `.env` (gitignored) or OS keyring, with `.env.example` placeholders only.

**ETF Look-Through Market Data (`services/market_data.py`):**
To evaluate US sleeve overlap (e.g., ~450 direct-indexed stocks + `VB`/`VXF` completion vs. `VTI`/`ITOT` benchmark) and ETF constituent/sector exposures without live network calls during optimization, `services/market_data.py` fetches and caches constituent holdings in `security_exposure`:
- **Vanguard ETFs (`VTI`, `VB`, `VXF`, `VIG`, `VEA`, `VWO`, `VTEB` — updated quarterly):**
  Fetch JSON from `https://advisors.vanguard.com/investments/products/api/funds/{FUND_ID}/holdings/latest` using the fund's Vanguard `FUND_ID`. Parse constituent tickers, CUSIPs, sector/size metadata, and percentage weights into `security_exposure` (`provider='vanguard'`).
- **iShares ETFs (`ITOT`, `DGRO`, `IEMG`, `MUB`):**
  Fetch CSV from `https://www.ishares.com/us/products/239724/ishares-core-s-p-total-u-s-stock-market-etf/latest-holdings.csv` (and configurable iShares CSV URLs for `DGRO`, `IEMG`, `MUB`). Skip preamble metadata rows until the tabular header (`Ticker,Name,Sector,Asset Class,...`), normalize weights, and store in `security_exposure` (`provider='ishares'`).
- **Local CSV fallback & caching:** Support local CSV import/seed fixtures for ETFs without public unauthenticated endpoints (e.g., Schwab `SCHD`, `SCHF` or offline demo mode). Cached look-through weights remain valid for up to 95 days unless manually refreshed.

**Write (final delivery phase):** A user reviews a small batch of ranked groups. Before **each** exact order, refresh relevant cash, quote, security and lots; build a broker preview and show account, side, ticker, whole-share count, order terms and exact sell lot IDs. Obtain **one discrete, contemporaneous, affirmative approval per order**, tied to an order fingerprint and preview; submit only that order with idempotency/retry protection, then reconcile fills and actual lot attribution. Never auto-route a full selected group or continue unattended after partial fills. Recompute dependent trades against refreshed state. Confirm production behavior and E*TRADE account permissions/terms before enabling write mode.

Required adapter methods: `list_accounts`, `fetch_portfolio_with_lots`, `fetch_transactions`, `fetch_balances`, `get_quotes`, then `preview_order`, `submit_approved_order`, `get_order_status`. `FakeBroker` implements the same read and deterministic order-test contract. Live writes fail closed behind a feature flag.

References: https://apisb.etrade.com/docs/api/account/api-portfolio-v1.html ; https://apisb.etrade.com/docs/api/order/api-order-v1.html ; https://developer.etrade.com/support/terms-of-use .

## 6. Tax-aware joint optimizer

### 6.1 Input state and candidate generation

Load current **available** tax-lot quantities, adjusted basis/acquisition date, single-account cash, prices with source/as-of, valid active policy (including holding-to-sleeve resolution and batch limits), approved ETF candidates, ST/LT tax rates, YTD realized values, loss carryforwards, retained TLH target, gain/tax budgets, cached Vanguard/iShares ETF look-through and sector/benchmark data, recent same-security acquisitions and existing 30-day no-buy restrictions. Exclude pending/reserved shares, stale data and ineligible candidates.

Generate four candidate types: individual-stock loss harvests, gain-aware stock and small-lot cleanup exits into VTI/ITOT, allowed ETF pair/triplet swaps, and allocation/municipal exit trades. **Do not apply a minimum notional filter to lot/stock sells:** small legacy lots (e.g., historical DRIP lots) and small positions are desirable cleanup candidates that reduce lot and position count when consolidated into replacement ETF buys. Apply `min_buy_order_notional_usd` only to replacement ETF buy legs. Brokerage data determines current values; configured sleeves/tickers are _illustrative defaults_, never hard-coded. Propose **no trades** if no basket beats transaction and tax costs.

### 6.2 Decisions, exact IRS tax netting, and drift slack accounting

Decision variables: `s_l` = shares sold from lot `l` (`0 <= s_l <= available_l`), `b_i` = shares bought of allowed security `i` (`b_i >= 0`). No short positions. For each security, `q'_i = q_i - sum_{l in lots(i)} s_l + b_i`.

Per-lot realized result: `g_l = s_l * (estimated_sale_price_i - adjusted_unit_basis_l) - allocated_fees_l`. Determine ST/LT by acquisition versus trade date.

#### Exact IRS ST/LT Netting and Retained TLH Valuation Equations (`domain/tax.py` & `optimizer/model.py`)

Let pre-trade baseline net ST and LT positions (in `Decimal` USD, where negative values represent net losses) be:
$$S_0 = \text{ytd\_realized\_st\_usd} - \text{st\_loss\_carryforward\_usd}, \qquad L_0 = \text{ytd\_realized\_lt\_usd} - \text{lt\_loss\_carryforward\_usd}$$

Let the proposed basket's realized ST and LT P/L be $\Delta S = \sum_{l \in \text{ST}} g_l$ and $\Delta L = \sum_{l \in \text{LT}} g_l$, giving post-trade positions:
$$S_1 = S_0 + \Delta S, \qquad L_1 = L_0 + \Delta L$$

With marginal rates $\tau_{\text{st}} \ge \tau_{\text{lt}} \ge 0$ and carryforward valuation rate $\tau_{\text{cf}} = \text{carryforward\_loss\_discount\_factor} \times \tau_{\text{lt}}$, define the piecewise-linear tax valuation function (not globally convex) $T(S, L)$:

1. **Both buckets net positive ($S \ge 0$ and $L \ge 0$):**
   $$T(S, L) = \tau_{\text{st}} S + \tau_{\text{lt}} L$$
2. **Opposite-sign buckets with net overall gain ($S + L \ge 0$, IRC §1222 cross-netting):**
   $$T(S, L) = \begin{cases} \tau_{\text{st}}(S + L) & \text{if } S > 0 \text{ and } L < 0 \text{ (LT loss offsets ST gain)} \\ \tau_{\text{lt}}(S + L) & \text{if } L > 0 \text{ and } S < 0 \text{ (ST loss offsets LT gain)} \end{cases}$$
3. **Net overall capital loss ($S + L < 0$, let net capital loss $N = -(S + L) > 0$):**
   $$N_{\text{ord}} = \min\big(N, \, \text{ordinary\_income\_deduction\_limit\_usd}\big)$$
   $$N_{\text{cf}} = \max\Big(0, \, \min\big(N, \, \text{target\_retained\_net\_loss\_usd}\big) - N_{\text{ord}}\Big)$$
   $$T(S, L) = -\big(\tau_{\text{st}} N_{\text{ord}} + \tau_{\text{cf}} N_{\text{cf}}\big)$$
   *(Any net capital loss beyond `target_retained_net_loss_usd` receives $0$ marginal tax credit in the objective, preventing unnecessary harvesting churn once the user's configured TLH target—such as `$3,000` for IRC §1211(b) or a custom carryforward buffer—is achieved.)*
4. **Incremental Tax Cost and Benefit of the Proposed Basket:**
   $$\text{IncrementalTaxCost} = T(S_1, L_1) - T(S_0, L_0), \qquad \text{EstimatedTaxBenefitUSD} = -\text{IncrementalTaxCost} = T(S_0, L_0) - T(S_1, L_1)$$

If either `short_term_tax_rate` or `long_term_tax_rate` is `null`, report realized ST/LT dollar gains and losses ($\Delta S, \Delta L$) and apply gain-budget caps, but return `estimated_tax_benefit_usd = null` (`status = "tax_profile_incomplete"`).

**Approved solver formulation:** Enumerate the bounded affine regions of the exact $T(S,L)$ above, including ST/LT sign, cross-netting, ordinary-deduction and retained-loss breakpoints. For each feasible region, impose its linear region constraints and affine tax expression in a convex small-batch subproblem; solve with CVXPY/OSQP (CLARABEL fallback) under one shared deadline. Compare independently `Decimal`-validated rounded baskets using the same configured objective, including the no-trade baseline. Do not replace the function with a globally convex approximation. Test region coverage, boundaries and agreement with the direct `Decimal` function. Rounding may cross a region boundary: recompute exact tax and all constraints afterward. Report incomplete region search/timeouts and do not claim global integer optimality; use HiGHS only for a compatible bounded discrete repair formulation. Benchmark the full enumeration, not just one subproblem.

#### Per-Sleeve Drift Bands (Non-Worsening Hard Bounds + Soft Slack)

For each policy sleeve $s$ with target weight $w_s^*$, drift band $\pm \delta_s$, and pre-trade weight $w_s^{\text{cur}}$:
- **Hard non-worsening bound:** Post-trade weight $w_s^{\text{post}}$ must satisfy:
  $$w_s^{\text{post}} \in \Big[\min\big(w_s^{\text{cur}}, \, w_s^* - \delta_s\big), \; \max\big(w_s^{\text{cur}}, \, w_s^* + \delta_s\big)\Big]$$
  This prevents the solver from ever pushing an in-band sleeve outside its band or worsening an already out-of-band sleeve, while guaranteeing feasibility when starting out-of-band under tight tax/batch budgets.
- **Soft band-violation slack $\xi_s \ge 0$:**
  $$\xi_s \ge |w_s^{\text{post}} - w_s^*| - \delta_s$$
  penalized heavily in the objective ($\lambda_{\text{band}} \sum_s \xi_s + \lambda_{\text{alloc}} \sum_s (w_s^{\text{post}} - w_s^*)^2$).

Enforce hard bounds for available lot shares, no prohibited wash-sale replacement, single-account settled funding (including `cash_reserve_usd`), allowed ETFs, gain/tax/turnover/batch budgets and suitable liquidity.

Conceptual objective (use consistently scaled terms):

`min λrisk × tracking_risk + λband × band_violation_slack + λalloc × drift_penalty + λtax × incremental_tax_cost + λcost × trading_cost + λturn × turnover − λtransition × justified_ETF_consolidation_and_lot_cleanup_reward`

The ETF consolidation and lot/position cleanup reward is modest and cannot override legal, tax, cash or exposure constraints. Report estimated incremental realized ST/LT and cash effects independently of any aggregate score.

### 6.3 Risk and exposure computation

- Top-level sleeve targets apply to **total managed-account portfolio value**; nested US ETF/direct-indexing targets apply **within the US sleeve**. Compute post-trade values using full economic portfolio including cash, not just shares traded.
- US transition progress uses only the explicitly designated destination sleeve and all assigned descendant value, regardless of ticker or asset type, divided by the direct-index container value; no destination returns `null` rather than inferring an ETF set.
- US sleeve benchmark is a **VTI/ITOT-style total US market**; legacy individual large-cap stocks and VB/VXF completion are modeled together using cached Vanguard/iShares look-through holdings (`security_exposure`). Do not assume VB/VXF has no overlap; model actual look-through/exposure data.
- Economic sector/country/factor exposures may overlap strategic sleeves (e.g., US dividend-growth ETF exposure). Calculate separately from exclusive policy sleeve assignments; never double-count for target totals.
- Prefer security-/factor-level covariance and ETF look-through or sector/cap/style bands, **not a 2,500-lot covariance matrix**. Map lots to security-level risk exposures. Track source, freshness, coverage and confidence.
- Where benchmark/factor inputs are unreliable, use explicit observable drift/sector constraints and **omit** a numerical tracking-error figure rather than invent precision.

### 6.4 Two-pass small-batch solve, integerization and ranking

To prevent the first optimizer run from proposing >1,000 lot sales across ~450 direct-indexed stocks, the optimizer uses a **Two-Pass Screen-Then-Solve-Batch** architecture:

1. **Pass 1 — Full-Portfolio Screening & Candidate Ranking (`< 0.5s`):**
   Vectorized pre-screen of all ~2,500 lots and eligible ETF substitutions. Run a fast continuous relaxation or marginal-utility ranking to score candidate security/lot sells by net tax savings, drift repair, and lot/position cleanup value (rewarding full-position exits and small legacy/DRIP lot cleanup).
2. **Pass 2 — Exact Joint Solve on Top-$K$ Batch (`< 2.5s`):**
   Select the top candidate securities/lots up to `max_sell_tickers_per_batch` (default `10`), `max_sell_lots_per_batch` (default `20`), and `max_total_orders_per_batch` (default `12`). Lock all unselected securities at zero trade ($s_l = 0$) and solve the sparse continuous CVXPY/OSQP model jointly with the replacement ETF buy variables (`VTI`/`ITOT`, sleeve ETFs) so the small batch is self-funding and exposure-balanced.
3. **Whole-Share Integerization & Multi-Lot Order Consolidation (`< 1.5s`):**
   Convert to whole-share buys and specific-lot sells; use a small HiGHS discrete subproblem if needed on the $K$-ticker batch. When multiple lots of the **same ticker** are sold in the batch, consolidate them into a **single `SELL` `recommendation_leg`** with `selected_lots` listing each exact `broker_lot_id` and share count so the user only previews/approves one order per sold ticker.
4. **Independent `Decimal` Validation:**
   Independently revalidate the whole rounded batch with `Decimal` accounting, exact IRS ST/LT netting, 30-day wash checks, lot availability, single-account cash and exposure constraints; refuse/repair invalid output rather than present infeasible orders.


**Shared accounting extension point:** `app.domain.portfolio_accounting.evaluate_portfolio(inputs: FinancialInputs, proposed_legs: Sequence[ConsolidatedLeg] = ())` computes current state and proposed effects from frozen inputs and canonical consolidated legs, including exact lot allocations, funding dependencies, cash, sleeve totals, transitions, and lot/position effects. It accepts no solver totals. The `/api/v1/portfolio` route and DEMO initial/subset accounting use this same calculation; deterministic candidate generation is separate from the service that builds legs, validates subsets, persists runs, and presents responses.

For Phase 2, the bounded worker receives an immutable input snapshot and a deadline, performs screening/Pass 2 plus whole-share rounding, and returns candidate canonical legs with solver metadata—not trusted account totals and not database writes. The request owner must re-evaluate those rounded legs from the original frozen `FinancialInputs` with this independent Decimal core, recheck every applicable hard constraint, reject stale/late/infeasible results, and only then persist. A subset change must re-solve Pass 2 and re-round only the selected sell-lot subset before the same independent validation; it is not a UI-only filter or blanket approval. Keep wash, market-look-through risk, solver execution, and broker-order capability outside this accounting core; none is claimed as implemented here.
5. **Coherent Priority Ranking:**
   Store **priority-ranked coherent groups** plus linked buy/sell legs, explanations, expected tax benefits and exposure/lot/position-count deltas. Rank economic importance separately from execution dependency order.
6. **Subset Selection & Fast Batch Re-Solve (`POST /api/v1/optimizer/runs/{id}/selection`):**
   When the user toggles trade groups or individual sell lots within the batch (or picks Top $N$ groups), re-run Pass 2 + rounding on only the selected sell lots to automatically resize the consolidated replacement ETF buy leg(s) and recompute exact cash, tax, and exposure effects. Disallow unchecking a replacement BUY leg independently of its funding SELL legs.

### 6.5 Performance targets and timeout budget

| Phase                                           | Target p95 with validated, cached input |
| ----------------------------------------------- | --------------------------------------: |
| Pass 1 candidate screening / wash checks        |                                   < 1 s |
| Pass 2 continuous solve                         |                                   < 3 s |
| Whole-share repair, Decimal validation, ranking |                                   < 2 s |
| Complete recommendation computation (`TIMEOUT`) |                                 < 10 s |

Enforce `SOLVER_TIMEOUT_SECONDS = 10.0` with a monotonic end-to-end computation deadline shared by screening, all tax-region subproblems, repair and independent validation. Reserve time for repair, validation and returning the result; record persistence and response overhead separately. Run computation outside the FastAPI event loop in a bounded, supervised worker process; pass remaining time to each solver's native time limit. Timing out an await, cancelling a future, `asyncio.to_thread`, or using `ProcessPoolExecutor` alone does not stop running computation. Terminate/reap an overrun worker and reclaim its capacity; bound concurrent jobs and reject excess work rather than accumulate an unbounded queue. Workers receive immutable inputs and return results only: the request owner alone may publish a run, and must reject late/stale results after a terminal timeout. If discrete HiGHS repair hits its sub-timeout, attempt greedy whole-share repair only within the remaining deadline, independently validated in `Decimal`, with warning `"used_greedy_rounding_fallback"`. If no fully validated result is ready by the deadline, return a persisted `timeout` outcome; never publish an unvalidated basket. Test forced hangs, repeated timeouts, worker cleanup, bounded concurrency and absence of late publication. Benchmark on synthetic ~460-security, 2,500-lot portfolios and actual risk dimensions. Record candidate and constraint count, memory, construction/solve/repair timing, solution feasibility, region-search completeness and integer gaps/timeouts. Broker/network sync is measured separately. Do not claim these targets were achieved until tested.

## 7. Wash-sale rules — single-account scope (DRIP disabled)

1. Track **each security** within the **single managed E*TRADE brokerage account** using stable IDs, current holdings (`current_tax_lot`), and retained E*TRADE transaction history (`broker_transaction`). Assume DRIP is disabled on the managed account and no relevant outside/spouse account trading occurs.
2. Honor E*TRADE's (GainsKeeper) reported adjusted cost basis and tacked acquisition dates on open lots as authoritative for historical wash sales.
3. By configured policy assumption, different approved ETF replacement members are **not substantially identical to one another**. The app does not classify equivalence or build a general identity graph. Same-security repurchases **are** checked; candidate approval never exempts the original ticker.
4. **30-calendar-day lookback rule (aligned to E*TRADE):** For a proposed loss sale of security $X$, inspect BUYs of security $X$ in the managed account in the **prior 30 calendar days** (`trade_date - 30 days`) and all proposed basket buys. If any BUY of $X$ occurred in the prior 30 calendar days, **block all loss sales of $X$** unless 100% of shares of $X$ acquired in the prior 30 days are also sold in full in the same trade group (leaving no retained replacement shares onto which a wash disallowance can attach). Incomplete required E*TRADE history blocks relevant harvesting.
5. **30-calendar-day forward restriction:** Record and show a **next-30-calendar-days do-not-buy** restriction (`loss_sale_date` through `loss_sale_date + 30 calendar days`, eligible on day `+31`) for securities with actual executed loss sales (or loss sales in the active proposed basket). Future optimization excludes incompatible buy candidates until expiry. Evaluate the entire proposed basket, including sequencing and reinvestment purchases; do not rely solely on a UI warning.
6. Wash-sale assessments are computed functions with verdict/reasons persisted in recommendation/run details; **no** `wash_sale_assessment`, `external_tax_event`, or general substantial-identity graph table.

## 8. Backend API contracts (JSON over localhost)

Use `/api/v1` for application routes, Pydantic DTOs and consistent errors `{code, message, details, correlation_id}`. Stable endpoints:

| Endpoint                                                       | Contract                                                                                                                       |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `GET /health`                                                  | API/schema readiness, fake vs real broker mode                                                                                 |
| `GET /api/v1/auth/etrade/status`                               | E*TRADE OAuth 1.0a session state, bound `account_id_key`, token renewal/expiry status                                          |
| `POST /api/v1/auth/etrade/start`                               | Request OAuth 1.0a temporary token (`oauth_callback="oob"`) and return `authorize_url`                                         |
| `POST /api/v1/auth/etrade/verify`                              | Exchange user-supplied `oauth_verifier` code for access token and bind managed account                                         |
| `POST /api/v1/portfolio/sync`                                  | Initiate read-only single-account sync + look-through cache check; publish atomic generation or return structured error        |
| `GET /api/v1/portfolio`                                        | Current positions, managed account cash, resolved sleeve totals, US 3-state transition summary, sync timestamps/coverage       |
| `GET /api/v1/lots`                                             | Paginated/filterable current lots with exact broker identifiers, resolved sleeve, and small-lot cleanup flags                  |
| `GET /api/v1/policy`                                           | Active/draft policies, sleeves, ETF sets, overrides, and tax/batch settings                                                    |
| `POST /api/v1/policy/drafts`                                   | Save an editable, versioned policy draft (including sleeve CRUD and `reassign_to_sleeve_key` when deleting a sleeve)           |
| `POST /api/v1/policy/{id}/activate`                            | Validate exact 100% sums (top level and nested), zero unassigned holdings, and other hard rules                                |
| `POST /api/v1/optimizer/runs`                                  | Execute 2-pass small-batch optimization via worker thread/process (`10.0s` timeout) and return completed run (`201 Created`)   |
| `GET /api/v1/optimizer/runs/{id}`                              | Run status, summary metrics, solver provenance, batch settings used, warnings/infeasibility                                    |
| `GET /api/v1/optimizer/runs/{id}/recommendations`              | Priority-ordered recommendation groups and consolidated BUY/SELL legs (with `selected_lots` array), dependencies, explanations |
| `POST /api/v1/optimizer/runs/{id}/selection`                   | Proposed group/sell-lot subset; re-solve Pass 2 replacement ETF buy quantities and revalidate against current data             |
| `PATCH /api/v1/optimizer/runs/{id}/recommendations/{group_id}` | Save a user note/rejection reason on a proposed group without executing anything                                               |
| `GET /api/v1/optimizer/runs/{id}/export`                       | CSV or JSON via `format` query; recommendations include run, policy, prices/as-of, exact lot IDs and warnings                  |
| `GET /api/v1/wash-sales`                                       | Single-account E*TRADE-derived purchase restrictions and next eligible dates                                                   |
| `GET /api/v1/activity`                                         | Filterable sync, policy, run, approval and reconciliation history                                                              |
| `POST /api/v1/orders/{leg_id}/preview`                         | Last phase: fresh exact-order preview (including multi-lot attribution) without submission                                     |
| `POST /api/v1/orders/{leg_id}/submit`                          | Last phase: separately approved **exact** order; guarded against duplicates                                                    |

**Synchronous Run Execution & Timeout Fallback (`POST /api/v1/optimizer/runs`):**
`POST /api/v1/optimizer/runs` runs the solver in the bounded, supervised worker process defined in §6.5 with `SOLVER_TIMEOUT_SECONDS = 10.0` so the FastAPI event loop never blocks, and returns HTTP `201 Created` directly with the completed `OptimizerRun` DTO (no frontend polling required for standard solves). If discrete repair reaches its sub-timeout, attempt greedy rounding only within the remaining overall deadline and validate in `Decimal`. If the overall deadline expires without a fully validated basket, persist and return `status = "timeout"`. Return `"infeasible"` only when the bounded model's infeasibility has been established, not when region search was merely interrupted; include structured diagnostics. `GET /api/v1/optimizer/runs/{id}` remains available to inspect any run.

Illustrative run POST (with optional per-run batch overrides):

```json
{
  "mode": "recommendations_only",
  "max_sell_tickers_per_batch": 10,
  "max_sell_lots_per_batch": 20,
  "max_total_orders_per_batch": 12
}
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
  "lots_sold_count": 6,
  "positions_exited_count": 4,
  "orders_count": 5,
  "constraints_satisfied": true,
  "warnings": []
}
```

## 9. Frontend design contract

- Recreate the HTML reference in real Quasar components (`QLayout`, `QDrawer`, `QHeader`, `QPage`, `QCard`, `QTable`, `QDialog`, `QBadge`, `QInput`, `QSelect`, `QToggle`, `QBtn`, `QBanner`, `QTooltip`); desktop-first, tablet-aware, keyboard-accessible.
- `components/` owns reusable transition hierarchy, allocation/tax/batch editors, trade-group panels, lots and order dialogs. `stores/` owns API-loaded state, drafts, run selection, loading/error modes. `services/api.ts` is the typed transport; do not reimplement financial math in Vue.
- All six screens: Overview, Recommendations, Tax Lots, Allocation Policy (including **Tax & Batch Settings**), Wash Sales, Activity.
- **3-State US Transition Widget (`USAllocationTransition.vue`):** Must display all **three** states—**Current**, **Proposed Basket (Post-Selected-Trades)**, and **Configured Policy Target**—clearly labeling whether each percentage is total-portfolio or within-US-sleeve.
- **Full Sleeve CRUD & Tax/Batch Editor (`PolicyPage.vue`):** Support adding (`+ Add Sleeve`), renaming, reordering, disabling, and deleting sleeves (with holding reassignment target selection), exact-100% validation, ETF pairs/triplets, drift bands, and all persisted `policy_revision` fields (ST/LT marginal rates, carryforwards, YTD realized amounts, `target_retained_net_loss_usd`, `ordinary_income_deduction_limit_usd`, `carryforward_loss_discount_factor`, gain/tax budgets, and small-batch limits).
- **Recommendations & Subset Selection (`RecommendationsPage.vue`):** Expandable **ranked small-batch groups** with multi-lot sell attribution, dependencies, estimated ST/LT effects and cash/exposure/lot-count deltas. Users can toggle whole groups or specific sell lots (triggering `POST /api/v1/optimizer/runs/{id}/selection` to re-solve the consolidated replacement ETF buy leg); replacement BUY legs cannot be unchecked independently to create orphaned legs. Show no-trade, stale-data, infeasible and incomplete-tax-profile states without fabricating figures.
- Demo values in the HTML reference are illustrative and must never be used as live investment results. Order review explicitly requires individual exact-order approval in the final phase.

## 10. Local security, persistence and operations

- Bind backend to `127.0.0.1`, restrict CORS to the local frontend dev origin; use session/origin checks for state-changing endpoints. Local-only is **not** permission to skip order authorization.
- Protect SQLite with OS user file permissions and disk encryption where available. SQLite is not encrypted by default. Keep DB, `.env`, credentials, tokens, account exports, sensitive logs and backups out of Git; `.env.example` contains placeholders only. Optionally use OS keyring.
- Apply SQLAlchemy/Alembic migrations; test migration from an existing DB. WAL, short write transactions, FK enforcement and busy timeout. Store DB on local disk; use SQLite online backup API, verify restores and periodically run integrity checks; don't blindly copy a live WAL file.
- Log structured request/job IDs, solver version, input fingerprint and reasons for rejected trades without logging tokens or raw account identifiers. Handle broker timeouts/rate limits and local process failures without partially publishing state.
- Optimizer runs are tied to policy revision and source-generation input; recheck quotes, lot availability, cash and restrictions before every approval/submit. Browser does not store secrets or directly call broker APIs.

## 11. Testing and acceptance

**Unit:** `Decimal` exact 100% top/nested policy validation, editable cash/custom sleeves and sleeve deletion reassignment, default holding-to-sleeve resolution (`is_direct_index_container`), tax-rate/carryforward/retained-TLH persistence, exact IRS ST/LT netting equations ($T(S, L)$), fees, lot-adjusted basis, single-account 30-day lookback and forward wash checks, eligibility and funding.

**Optimizer:** Deterministic and randomized ~460-security/2,500-lot fixtures; 2-pass small-batch enforcement (`max_sell_tickers_per_batch`, `max_sell_lots_per_batch`, `max_total_orders_per_batch`), small-lot / legacy DRIP lot cleanup without artificial sell-notional blocks, non-worsening drift slack when starting out of band, multi-lot same-ticker order consolidation, no oversells, shorts, cash deficits, invalid wash-sale rebuys, missing lot IDs or broken dependencies. Compare proposed full-basket accounting and risk deltas against independently computed `Decimal` output. Perturb lot ordering and solver conditions; test infeasible/timeout/no-trade cases and subset re-solve.

**Integration:** Fake-broker pagination, OAuth `oob` verifier flow, Vanguard JSON and iShares CSV look-through parsing and caching, incomplete lot/transaction pages, partial order fills and lot mismatches; atomic current-generation sync; policy migration/versioning; reproducible saved run inputs; explicit per-order approval and idempotency.

**UI:** Six routes; full sleeve CRUD and ETF sets; exact-100% activation validation; 45/24/17/14/0 example is _seed only_; SCHD dividend ticker; 3-state US transition view; tax & batch settings and reload persistence; trade-group filtering, annotations, exports, subset selection + re-solve; saved-run reopening; no-trade display and keyboard-accessible per-order dialog.

**Performance:** Capture p50/p95, memory, solver configuration, dimensions, candidate counts and optimality gap on development hardware within the `10.0s` budget. Never report a speed threshold as measured without a benchmark.

## 12. Sequenced delivery (5 phases, subagent-ready)

1. **Phase 1 — Foundation & offline demo vertical slice (split for subagents):**
   - **Phase 1A (Backend & API Contract):** Existing mise/uv scaffold; typed SQLite/SQLAlchemy schema & Alembic migrations, single-account `FakeBroker`, `Decimal` policy/sleeve validation, Phase 1 `/api/v1/*` contracts with deterministic, explicitly labeled demo fixtures (including demo runs/selection/exports); later-phase capabilities return explicit unavailable/disabled responses, never fabricated success; no live OAuth, real optimizer or broker-write completion is implied, `pytest` suite, and generated TypeScript API contract (`frontend/src/types/api.ts`).
   - **Phase 1B (Frontend Quasar App):** Existing Quasar/Vite scaffold; Pinia stores, typed `services/api.ts`, all six pages (including 3-state US transition, full sleeve CRUD, and Tax & Batch Settings) and `vitest` tests wired to the Phase 1A backend.
2. **Phase 2 — Real 2-pass small-batch optimizer:** E*TRADE-independent exact IRS tax netting ($T(S, L)$), single-account 30-day wash-sale logic, cached Vanguard/iShares look-through exposure engine, 2-pass small-batch CVXPY/OSQP solve with non-worsening drift slack, multi-lot order consolidation, whole-share repair, independent `Decimal` validation, subset re-solve, and ~460-security/2,500-lot `< 10s` benchmark.
3. **Phase 3 — E\*TRADE read integration & live look-through sync:** OAuth 1.0a `oob` flow (`/api/v1/auth/etrade/*`), single-account paginated holdings/lot/transaction sync, Vanguard JSON and iShares CSV look-through sync, cash reconciliation, market-data freshness and incomplete-data safeguards. Overnight acceptance uses deterministic broker/HTTP fixtures; interactive OAuth and real-account acceptance are deferred and do not block later offline phases. Do not connect to E*TRADE overnight.
4. **Phase 4 — Security and reliability hardening:** Migration/restart/backup tests, exceptional-state UI, reconciliation diagnostics, stable API contracts and automated end-to-end QA (including browser flows, keyboard behavior, error states and desktop/tablet layouts). No manual QA is a mandatory overnight gate. Human visual/usability review is a deferred follow-up, not a substitute for automated functional coverage; real OAuth/account validation and live-write release approval remain separate deferred gates.
5. **Phase 5 — Manually approved E\*TRADE order writes (last):** Exact preview and discrete affirmative approval for every order; protected broker submission, fills and lot reconciliation, safe stopping/re-solving after subsets; implement and test the complete workflow against `FakeBroker` and fake HTTP transport overnight, including broker payload construction, with no E*TRADE connection and live writes disabled. Confirm actual broker capabilities, current terms and permissions and obtain explicit live-write release approval later.

No separate multi-year projection subsystem, multi-account routing, external-tax event imports, or broker automation without individual user approval.

## 13. References

- SQLite: https://www.sqlite.org/whentouse.html ; WAL: https://www.sqlite.org/wal.html
- Quasar: https://quasar.dev/start/quick-start/
- uv: https://docs.astral.sh/uv/guides/projects/
- CVXPY: https://www.cvxpy.org/ ; OSQP: https://osqp.org/
- Vanguard Holdings API pattern: `https://advisors.vanguard.com/investments/products/api/funds/{FUND_ID}/holdings/latest`
- iShares ITOT Holdings CSV: https://www.ishares.com/us/products/239724/ishares-core-s-p-total-u-s-stock-market-etf/latest-holdings.csv
- PyPortfolioOpt postprocessing (considered, not core): https://pyportfolioopt.readthedocs.io/en/latest/Postprocessing.html
- E*TRADE broker and order docs, terms: links in §5
