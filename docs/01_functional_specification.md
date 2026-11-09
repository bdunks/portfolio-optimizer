# Portfolio Optimizer — Functional Specification

**Version:** 1.3 · **Date:** 2026-11-05 · **Scope:** local, single-user, single-account application  
**UI reference:** `docs/portfolio_tax_optimizer_reference.html` (design and interaction reference; example figures only).

## 1. Purpose and boundaries

On demand, use the current portfolio in a **single managed E*TRADE brokerage account** to recommend a **priority-ranked, small-batch basket of specific tax-lot SELLs and whole-share BUYs**. Jointly:

1. Maintain configurable strategic allocations and appropriate risk/exposure constraints within the managed account.
2. Harvest economically worthwhile individual-security and ETF losses up to a configurable retained tax-loss target.
3. Permit appreciated-lot sales when losses offset gains or configured gain/tax budgets allow them, including shedding small legacy lots (e.g., prior DRIP lots) and full positions to simplify holdings.
4. Prefer progressive replacement of US direct indexing with VTI/ITOT in **manageable, configurable trade batches** without tax-inefficient or bulk forced liquidation.
5. Show tax, cash, exposure, lot-count and stock-count effects and why each recommendation is prioritized.

**No orders execute automatically.** A valid run can return **no beneficial trades** or a documented infeasible result. Multi-account aggregation, multi-year projections, unattended trading, tax-return preparation, outside-account data imports, public hosting and multiuser administration are out of scope.

## 2. Configurable allocation and tax policy

Asset-class **sleeves are data**, not hard-coded: users can add, rename, reorder, disable or delete them in a draft (after reassigning holdings), including a cash sleeve. Each holding in the managed account resolves to **exactly one policy sleeve** for allocation calculations:
- Approved ETFs resolve to their configured sleeve (`policy_allowed_security`), unless overridden.
- All individual US equities and designated mid/small-cap completion ETFs (`VB`, `VXF`) resolve by default to the sleeve designated as the **direct-indexing container** (`US equities — total market` -> `direct_indexing` sub-sleeve), without requiring per-ticker manual assignment across ~450 stocks.
- Explicit user overrides (`policy_security_override`) are supported when splitting, reassigning or deleting sleeves.
- Economic exposures (country, sector, style, size, factors) can overlap across sleeves; compute policy sleeve weights and economic exposures separately. Policy targets and replacement sets are saved as versioned, persistent configuration.

| Illustrative sleeve | Current example | Target example | Allowed ETF candidates |
|---|---:|---:|---|
| US equities — total market | 45% | 45% | VTI, ITOT |
| Dividend growth | 23% | **24%** | VIG, DGRO, SCHD |
| Foreign developed equities | 17% | 17% | VEA, SCHF |
| Emerging-market equities | 14% | 14% | VWO, IEMG |
| Municipal bonds | 1% | 0% | VTEB, MUB |
| **Total** | **100%** | **100%** | |

**Exact policy rule:** top-level targets must equal **100% exactly**, using decimal arithmetic. Every nested sleeve allocation must likewise total exactly 100% within its parent. There is **no tolerance, implicit cash sleeve or silent normalization**. Invalid drafts may be saved, but cannot be activated or used for optimization. Target bands are configurable separately from target-sum validity, with units shown in **percentage points**.

### 2.1 US total-market transition

The illustrative US total-market sleeve is 45% of total portfolio value, with this internal structure:

| Child of US sleeve | Example current, within sleeve | Example target, within sleeve | Assets |
|---|---:|---:|---|
| New / transition destination | 0% | 100% | VTI, ITOT (illustrative candidates only) |
| Direct indexing | 100% | 0% | Individual equities approximating S&P 500 plus VB/VXF completion |

The illustrative direct-index mix was ~95% individual stocks and ~5% VB/VXF. **Actual lots, weights and values always come from E*TRADE.** Measure the combined sleeve against a total-US-market benchmark comparable to VTI/ITOT, rather than S&P 500 alone. Account for VB/VXF overlap when evaluating actual size/sector exposure.

Display all three structures side-by-side in the UI: **current**, **post-selected-trades (proposed basket)**, and **configured policy target**, labeling whether percentages mean *of whole portfolio* or *within US sleeve*. Transition progress = value assigned to the explicitly designated New / transition-destination sub-sleeve and all its descendants ÷ total US-sleeve value, irrespective of underlying ticker or asset type. The designation must be an enabled strict descendant of the unique US direct-indexing container and must not overlap its legacy direct-indexing branch. If no destination is designated, progress is explicitly unavailable; never infer one from ETF membership, names, or sibling exclusion. Consolidation is a preference, **not** a liquidation deadline.

### 2.2 Editable tax, batching and trading settings

The Allocation Policy screen includes a persistent **Tax & Batch Settings** panel with:

- Configurable marginal **short-term** and **long-term** capital-gains tax rates (including applicable federal/state/NIIT assumptions).
- Short- and long-term capital-loss **carryforwards** and **YTD realized ST/LT gains/losses**. Show source/as-of for broker-derived YTD amounts; allow explicit manual tax-profile adjustments so amounts are not double-counted.
- Configurable **target retained net capital loss** (`target_retained_net_loss_usd`, e.g., `$3,000` for IRC §1211(b) ordinary-income deduction, or a higher/lower target for future carryforward), **ordinary-income deduction limit** (`ordinary_income_deduction_limit_usd`, default `$3,000`), and **carryforward loss discount factor** (`carryforward_loss_discount_factor`, default `0.50`) so the solver stops harvesting once the user's desired retained loss target is met.
- Incremental realized-gain budget, maximum incremental estimated tax cost, optional separate ST/LT limits and configurable budget period.
- **Small-batch execution limits** to prevent massive 1,000-lot liquidation runs and keep manual per-order review practical: `max_sell_tickers_per_batch` (default `10`), `max_sell_lots_per_batch` (default `20`), `max_total_orders_per_batch` (default `12`), and `max_batch_turnover_pct` (default `5.0%`).
- **Position and lot simplification:** Do **not** impose a minimum sell notional that blocks shedding small legacy lots (such as small historical DRIP lots) or exiting small positions; reward lot-count and position-count reduction so small lots can be cleaned up and consolidated into replacement ETF buys. Apply `min_buy_order_notional_usd` (default `$500`) only to replacement ETF buy legs.
- Per-sleeve drift bands (enforced as non-worsening hard bounds plus soft slack penalty so starting out-of-band never causes infeasibility), total-US-market tracking/exposure tolerances, cash reserve, liquidity limits and ETF-consolidation preference.

All policy/tax/batch inputs survive restarts and are associated with policy revisions. Distinguish **realized gains/losses** from **estimated incremental tax liability/benefit**. Missing tax-rate inputs make dollar tax-benefit estimates unavailable, not zero and not guessed.

### 2.3 Approved ETF sets

Users may add, remove, reorder, enable/disable and prioritize ETF candidates in each sleeve's replacement set (pairs or triplets). Record candidate preference and exposure suitability. **By user policy assumption**, approved distinct replacement members were chosen not to be substantially identical; this does **not** permit buying the **same** ticker during its wash-sale window. An allowed security may still be rejected for inadequate exposure equivalence or other portfolio constraints.

## 3. Wash-sale scope (single managed account, DRIP disabled)

- All holdings, lots, cash and wash-sale tracking are scoped strictly to the **single managed E*TRADE brokerage account**. DRIP is assumed disabled on the managed account.
- Honor E*TRADE-reported (GainsKeeper) adjusted cost basis and tacked acquisition dates on all existing open tax lots as authoritative.
- **30-calendar-day lookback rule (aligned to E*TRADE):** Before proposing a **loss** sale of security $X$, inspect acquisitions (BUYs) of security $X$ in the managed account during the preceding **30 calendar days** (`trade_date - 30 days`) and in the proposed basket. If any acquisition of $X$ occurred in the prior 30 calendar days, **block all loss sales of $X$** unless 100% of shares of $X$ acquired in the prior 30 days are also sold in full in the same trade group (leaving no retained replacement lot onto which disallowed basis would attach).
- **30-calendar-day forward restriction:** After an executed loss sale of security $X$ (or when a loss sale of $X$ is included in the proposed basket), enforce and display a **30-calendar-day no-buy restriction** (`loss_sale_date` through `loss_sale_date + 30 calendar days`, eligible on day `+31`) for security $X$. Show the trigger trade and next eligible purchase date; revalidate the full basket before any order.
- Different approved replacement tickers are assumed non-substantially-identical to each other. No general similarity classifier or identity graph is required.
- Assume no relevant substantially identical transactions in other or spouse accounts **outside the managed E*TRADE account**. No multi-account or outside-account import workflow is required. **Incomplete required E*TRADE history** for the managed account blocks affected recommendations, never silently passes them.

## 4. Application screens

| Screen | Required behavior |
|---|---|
| **Overview** | Current as-of/sync/coverage status; KPIs for tax benefit, realized ST/LT, post-trade risk, position/lot count and transition-destination progress; hierarchical US transition (**current**, **proposed basket**, and **target**); current/target/post-trade allocation breakdown; Run Optimizer / Review Trades. |
| **Recommendations** | Priority-ranked, expandable small-batch trade groups with exact sell lots and linked buys; filter/sort by sleeve, action, tax term, expected benefit, warnings and group type; choose a group subset (with automatic re-solve of consolidated replacement ETF buys), review group dependencies and current-vs-proposed effects. |
| **Tax Lots** | Server-driven account-wide search/filter/sort/group and pagination for security → lot rows; show broker lot ID, acquired date, remaining/available shares, adjusted basis, price, unrealized dollar/% P/L, ST/LT, cleanup, sleeve and restriction flags. Stage the complete desired lot-ID set against the observed source generation and explicitly submit it for backend validation/re-solving; an empty set clears only when explicitly applied. Do not merge a delta or create a run implicitly. Keep requested intent, backend-applied basket selection and order approval distinct. |
| **Allocation Policy** | Full sleeve CRUD (`+ Add Sleeve`, rename, reorder, disable, delete with holding reassignment), exact-100% targets, drift bands, approved ETF pair/triplet sets, US ETF/direct-index target, persistent Tax & Batch Settings, retained TLH targets, gain budgets and risk constraints; draft/save/activate with validation. |
| **Wash Sales** | Managed-account E*TRADE acquisition/loss history and current security-specific restrictions, conflicting transactions, affected lots and do-not-buy-through dates in a filterable list/calendar. |
| **Activity** | Reopen past optimizer runs and see their frozen assumptions; policy change, sync, recommendation selection, approval, order/fill and reconciliation events with timestamps and errors. |

The HTML mockup supplies visual guidance; all live values come from the API or are explicitly marked **DEMO**. Wide desktop is primary, with usable tablet layouts, keyboard navigation and meaningful empty/error states.

### 4.1 Recommendation detail, batching and review

Group by economic intent: individual-stock harvest plus ETF exposure, appreciated-lot / small-lot consolidation with tax offsets/budgets, ETF pair/triplet swap, asset-class drift correction or municipal bond exit. Each optimizer run produces a **small, self-contained batch** respecting the configured batch limits (`max_sell_tickers_per_batch`, `max_sell_lots_per_batch`, `max_total_orders_per_batch`) rather than attempting to liquidate hundreds of direct-index lots at once.

- **Sell leg:** ticker, exact broker lot ID(s) and per-lot share breakdown (multiple lots of the same ticker sold in a batch may be consolidated into a single ticker SELL order with explicit multi-lot attribution), acquired date, available/proposed *whole* shares (or full legacy lot cleanup), adjusted basis, estimated price/as-of, ST/LT term and estimated realized P/L.
- **Buy leg:** ticker, whole shares, estimated price/notional, assigned policy sleeve and exposure role.
- **Group:** priority and rationale, net expected tax impact, gain budget usage, turnover/spread cost, cash effects, current-vs-proposed sleeve drift, US tracking/factor impact, stock-position and tax-lot reduction, wash status and execution dependencies.

The UI allows toggling **trade groups** (and individual sell lots within a group, which triggers a backend re-solve of the consolidated replacement ETF buy leg; replacement BUY legs cannot be unchecked independently in a way that leaves orphaned legs), choosing **top N groups or an arbitrary small subset**, and exporting self-describing CSV/JSON recommendations (run/policy/as-of included). Recalculate selected-basket cash, gain budgets, retained TLH progress, wash restrictions, exposure and dependent legs after changes via a fast batch re-solve. Show a concise reason for priority, **not** a spurious precision score. Ranking by importance is separate from **dependency-aware execution order**. No orphaned sell/replacement buy may be presented as an executable coherent group.

## 5. Manual E*TRADE order placement (last phase)

- Running optimization, selecting a group or saving policy **cannot submit an order**. Orders are sent only after deliberate user action in the order-review workflow.
- Users review a small batch. Display planned **sequence**, linked sell/buy dependencies and exact pending order terms; keep a review queue without implicit authorization of future legs.
- **Each exact order** requires a fresh broker preview and a **separate discrete, contemporaneous affirmative authorization**, identifying the managed account, side, ticker, quantity, order terms and specific sell lot IDs. No unattended retry, blanket group approval or silent continuation.
- Recheck balances, quote age, available shares, lot IDs, wash rules and downstream dependencies immediately before submission. Reconcile fills, partial fills, rejects, cancellations and actual broker lot attribution; invalidate stale dependent recommendations and re-optimize as needed.
- Enable placement only when permitted by E*TRADE's applicable terms/account capabilities; recommendation/export-only remains fully functional.

## 6. Point-in-time workflow

1. **Sync** the managed E*TRADE account's holdings, lots, cash and relevant recent transactions, plus prices and cached Vanguard/iShares ETF look-through exposure data. Validate pagination, freshness and completeness; preserve broker-reported basis adjustments.
2. **Validate** active policy sums, holding-to-sleeve resolution, usable quotes, lot availability, target/ETF eligibility, required acquisition history, account cash and restrictions.
3. **Generate and rank candidates:** harvestable individual-stock and ETF lots, small-lot / full-position cleanup candidates, acceptable-gain exits, replacement ETF buys, sleeve repairs and optional municipal exits.
4. **Optimize small batch jointly:** select the top candidate batch within configured batch limits (`max_sell_tickers_per_batch`, `max_sell_lots_per_batch`, `max_total_orders_per_batch`) and solve for exact lot-sale and replacement-buy quantities subject to IRS tax netting, retained TLH target, allocation (with non-worsening drift slack), tracking/exposure, account cash, wash and turnover constraints.
5. **Integerize and independently validate:** whole-share sells/buys with explicit lots, exact `Decimal` tax netting and cash accounting, and hard risk constraints; return ranked explanatory groups or a no-trade/infeasible outcome.
6. **Review:** save run, inspect impact, select/reject a subset (re-solving replacement buys as needed) and revalidate, without executing anything.
7. **Optional final-phase submission:** approve specific orders one at a time, reconcile results, sync and refresh remaining recommendations for the next batch.

## 7. Failure behavior and acceptance

| Condition | Required behavior |
|---|---|
| Targets do not sum to exactly 100% | Save invalid draft with visible error; block activation and actionable optimizer run |
| Incomplete/malformed E*TRADE sync or stale/unknown quote | Do not publish partial state as complete; block affected candidate(s), report coverage and freshness |
| Missing acquired date, available quantity, or adjusted basis | Block actionable lot sale; show source/data-quality reason |
| Same-security wash conflict or missing required E*TRADE acquisition history | Block affected harvest, show conflicting transaction/restriction |
| Lot-intent source generation changes or a requested set is rejected | Clear stale staged intent when the observed generation changes; show a rejection without changing the backend-confirmed basket. Require explicit application of an empty set to clear it. |
| Deselecting sell lots/groups in a batch | Re-solve consolidated replacement ETF buy legs and reject incomplete/infeasible selected baskets |
| Insufficient settled funds, shares, or hard risk limits | Repair/re-optimize or refuse; never suggest infeasible executable orders |
| No attractive trades | Show **No beneficial trades identified**, with reason |
| Stale preview, changed order terms or partial fill | Require new exact approval and revalidation before dependent submission |
| Demo mode | Label all numbers hypothetical; never route live orders |

**Acceptance tests:** dynamic sleeves (including explicit cash and holding reassignment on delete), nested target sums exactly 100%, edited ETF pairs/triplets, 3-state US transition views (current / proposed basket / target), 460-security/2,500-lot fixture, small-batch constraints (capping tickers/lots/orders per run while allowing small-lot cleanup), exact IRS ST/LT netting with configurable retained TLH target, single-account E*TRADE wash restrictions, full-lot accounting, ranking and subset re-solve, valid whole shares/cash, no-trade result, exports, saved-run reopening, per-order approval and partial-fill reconciliation. Actual broker data always overrides illustrative examples.

## 8. References

- HTML reference: `docs/portfolio_tax_optimizer_reference.html` — visual/interaction example only.
- E*TRADE API: https://developer.etrade.com/getting-started/developer-guides
- E*TRADE terms: https://developer.etrade.com/support/terms-of-use
- IRS Publication 550: https://www.irs.gov/publications/p550
