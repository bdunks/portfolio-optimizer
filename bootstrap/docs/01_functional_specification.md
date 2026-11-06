# Portfolio Optimizer — Functional Specification

**Version:** 1.2 · **Date:** 2026-11-05 · **Scope:** local, single-user application  
**UI reference:** `docs/portfolio_tax_optimizer_reference.html` (design and interaction reference; example figures only).

## 1. Purpose and boundaries

On demand, use the current E*TRADE portfolio to recommend a **priority-ranked basket of specific tax-lot SELLs and whole-share BUYs**. Jointly:

1. Maintain configurable strategic allocations and appropriate risk/exposure constraints.
2. Harvest economically worthwhile individual-security and ETF losses.
3. Permit appreciated-lot sales when losses offset gains or configured gain/tax budgets allow them.
4. Prefer progressive replacement of US direct indexing with VTI/ITOT without tax-inefficient forced liquidation.
5. Show tax, cash, exposure and stock-count effects and why each recommendation is prioritized.

**No orders execute automatically.** A valid run can return **no beneficial trades** or a documented infeasible result. Multi-year projections, unattended trading, tax-return preparation, outside-account data imports, public hosting and multiuser administration are out of scope.

## 2. Configurable allocation and tax policy

Asset-class **sleeves are data**, not hard-coded: users can add, rename, reorder, disable or delete them in a draft (after reassigning holdings), including a cash sleeve. Each holding is assigned to exactly **one policy sleeve** for allocation calculations; economic exposures (country, sector, style, size, factors) can overlap across sleeves. Compute those two views separately. Policy targets and replacement sets are saved as versioned, persistent configuration.

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
| Broad-market ETFs | 0% | 100% | VTI, ITOT |
| Direct indexing | 100% | 0% | Individual equities approximating S&P 500 plus VB/VXF completion |

The illustrative direct-index mix was ~95% individual stocks and ~5% VB/VXF. **Actual lots, weights and values always come from E*TRADE.** Measure the combined sleeve against a total-US-market benchmark comparable to VTI/ITOT, rather than S&P 500 alone. Account for VB/VXF overlap when evaluating actual size/sector exposure.

Display **current**, **configured target**, and **post-selected-trades** structures, labeling whether percentages mean *of whole portfolio* or *within US sleeve*. ETF transition progress = value assigned to the US sleeve in VTI/ITOT ÷ total US-sleeve value; separately show expected progress after the recommended basket. Consolidation is a preference, **not** a liquidation deadline.

### 2.2 Editable tax and trading settings

The Allocation Policy screen includes a persistent **Tax Settings** panel with:

- Configurable marginal **short-term** and **long-term** capital-gains tax rates (including applicable federal/state/NIIT assumptions).
- Short- and long-term capital-loss **carryforwards** and **YTD realized ST/LT gains/losses**. Show source/as-of for broker-derived YTD amounts; allow explicit manual tax-profile adjustments so amounts are not double-counted.
- Incremental realized-gain budget, maximum incremental estimated tax cost, optional separate ST/LT limits and configurable budget period.
- Per-sleeve drift bands, total-US-market tracking/exposure tolerances, maximum turnover, minimum trade/tax benefit, cash reserve, liquidity limits and ETF-consolidation preference.

All policy/tax inputs survive restarts and are associated with policy revisions. Distinguish **realized gains/losses** from **estimated incremental tax liability/benefit**. Missing tax-rate inputs make dollar tax-benefit estimates unavailable, not zero and not guessed.

### 2.3 Approved ETF sets

Users may add, remove, reorder, enable/disable and prioritize ETF candidates in each sleeve's replacement set (pairs or triplets). Record candidate preference and exposure suitability. **By user policy assumption**, approved distinct replacement members were chosen not to be substantially identical; this does **not** permit buying the **same** ticker during its wash-sale window. An allowed security may still be rejected for inadequate exposure equivalence or other portfolio constraints.

## 3. Wash-sale scope

- Track each stock and ETF by stable security identity across **relevant connected E*TRADE accounts**, including purchases, sells, DRIPs, and other acquired shares where reported. Retain sufficient acquisition history and honor E*TRADE-reported adjusted cost basis/wash adjustments.
- Before proposing a **loss** sale, check same-security acquisitions in the preceding **30 calendar days**, including across relevant E*TRADE accounts, and proposed basket buys. Track quantities and partial conflicts; block affected harvesting where conflict exists.
- After an executed loss sale, enforce and display a **30-calendar-day no-buy restriction** for that security in future runs. Show the trigger trade and next eligible purchase date; revalidate the full basket before any order.
- Different approved replacement tickers are assumed non-substantially-identical to each other. No general similarity classifier or identity graph is required.
- Assume no relevant substantially identical transactions in other or spouse accounts **outside E*TRADE**. No outside-account import, manual upload or missing-external-coverage workflow is required. **Incomplete required E*TRADE history** blocks affected recommendations, never silently passes them.

## 4. Application screens

| Screen | Required behavior |
|---|---|
| **Overview** | Current as-of/sync/coverage status; KPIs for tax benefit, realized ST/LT, post-trade risk, position count and ETF progress; hierarchical US transition; current/target/post-trade allocation breakdown; Run Optimizer / Review Trades. |
| **Recommendations** | Priority-ranked, expandable trade groups with exact sell lots and linked buys; filter/sort by sleeve, action, tax term, expected benefit, warnings and group type; choose a group subset, review group dependencies and current-vs-proposed effects. |
| **Tax Lots** | Search/filter/sort/group security → lot rows; broker account/lot ID, acquired date, remaining/available shares, adjusted basis, current price, unrealized dollar/% P/L, ST/LT status, sleeve and data-quality/restriction flags; mark lots selected for trades. |
| **Allocation Policy** | Editable arbitrary sleeves, exact-100% targets, drift bands, approved ETF pair/triplet sets, US ETF/direct-index target, persistent Tax Settings, budgets and risk constraints; draft/save/activate with validation. |
| **Wash Sales** | E*TRADE acquisition/loss history and current security-specific restrictions, conflicting transactions, affected lots and do-not-buy-through dates in a filterable list/calendar. |
| **Activity** | Reopen past optimizer runs and see their frozen assumptions; policy change, sync, recommendation selection, approval, order/fill and reconciliation events with timestamps and errors. |

The HTML mockup supplies visual guidance; all live values come from the API or are explicitly marked **DEMO**. Wide desktop is primary, with usable tablet layouts, keyboard navigation and meaningful empty/error states.

### 4.1 Recommendation detail and review

Group by economic intent: individual-stock harvest plus ETF exposure, appreciated-lot consolidation with tax offsets/budgets, ETF pair/triplet swap, asset-class drift correction or municipal bond exit. A group can contain several sell-lot legs and dependent buy legs.

- **Sell leg:** account, ticker, exact broker lot ID, acquired date, available/proposed *whole* shares, adjusted basis, estimated price/as-of, ST/LT term and estimated realized P/L.
- **Buy leg:** account, ticker, whole shares, estimated price/notional, assigned policy sleeve and exposure role.
- **Group:** priority and rationale, net expected tax impact, gain budget usage, turnover/spread cost, cash effects, current-vs-proposed sleeve drift, US tracking/factor impact, stock-position reduction, wash status and execution dependencies.

The UI can filter, sort, annotate/reject groups, choose **top N or an arbitrary small subset**, and export self-describing CSV/JSON recommendations (run/policy/as-of included). Recalculate selected-basket cash, gain budgets, wash restrictions, exposure and dependent legs after changes; re-solve when needed. Show a concise reason for priority, **not** a spurious precision score. Ranking by importance is separate from **dependency-aware execution order**. No orphaned sell/replacement buy may be presented as an executable coherent group.

## 5. Manual E*TRADE order placement (last phase)

- Running optimization, selecting a group or saving policy **cannot submit an order**. Orders are sent only after deliberate user action in the order-review workflow.
- Users may choose a small high-priority subset. Display planned **sequence**, linked sell/buy dependencies and exact pending order terms; keep a review queue without implicit authorization of future legs.
- **Each exact order** requires a fresh broker preview and a **separate discrete, contemporaneous affirmative authorization**, identifying account, side, ticker, quantity, order terms and specific sell lot IDs. No unattended retry, blanket group approval or silent continuation.
- Recheck balances, quote age, available shares, lot IDs, wash rules and downstream dependencies immediately before submission. Reconcile fills, partial fills, rejects, cancellations and actual broker lot attribution; invalidate stale dependent recommendations and re-optimize as needed.
- Enable placement only when permitted by E*TRADE's applicable terms/account capabilities; recommendation/export-only remains fully functional.

## 6. Point-in-time workflow

1. **Sync** E*TRADE holdings, lots, accounts, cash and relevant recent transactions, prices and exposure data. Validate pagination, freshness and completeness; preserve broker-reported basis adjustments.
2. **Validate** active policy sums, usable quotes, lot availability, target/ETF eligibility, required acquisition history, account cash and restrictions.
3. **Generate candidates:** harvestable individual-stock and ETF lots, acceptable-gain exits, replacement ETF buys, sleeve repairs and optional municipal exits.
4. **Optimize jointly:** select precise lot-sale and buy quantities subject to tax, allocation, tracking/exposure, account cash, wash and turnover constraints.
5. **Integerize and independently validate:** whole-share sells/buys with explicit lots, net tax accounting, available cash and hard risk constraints; return ranked explanatory groups or a no-trade/infeasible outcome.
6. **Review:** save run, inspect impact, select/reject a subset and revalidate, without executing anything.
7. **Optional final-phase submission:** approve specific orders one at a time, reconcile results, sync and refresh remaining recommendations.

## 7. Failure behavior and acceptance

| Condition | Required behavior |
|---|---|
| Targets do not sum to exactly 100% | Save invalid draft with visible error; block activation and actionable optimizer run |
| Incomplete/malformed E*TRADE sync or stale/unknown quote | Do not publish partial state as complete; block affected candidate(s), report coverage and freshness |
| Missing acquired date, available quantity, or adjusted basis | Block actionable lot sale; show source/data-quality reason |
| Same-security wash conflict or missing required E*TRADE acquisition history | Block affected harvest, show conflicting transaction/restriction |
| Deselecting part of a linked trade group | Recompute and reject incomplete/infeasible selected baskets |
| Insufficient settled funds, shares, or hard risk limits | Repair/re-optimize or refuse; never suggest infeasible executable orders |
| No attractive trades | Show **No beneficial trades identified**, with reason |
| Stale preview, changed order terms or partial fill | Require new exact approval and revalidation before dependent submission |
| Demo mode | Label all numbers hypothetical; never route live orders |

**Acceptance tests:** dynamic sleeves (including explicit cash), nested target sums exactly 100%, edited ETF pairs/triplets, current/target/proposed US views, 460-security/2,500-lot fixture, ST/LT/carryforward/gain budgets, E*TRADE wash restrictions, full-lot accounting, ranking and subset dependencies, valid whole shares/cash, no-trade result, exports, saved-run reopening, per-order approval and partial-fill reconciliation. Actual broker data always overrides illustrative examples.

## 8. References

- HTML reference: `docs/portfolio_tax_optimizer_reference.html` — visual/interaction example only.
- E*TRADE API: https://developer.etrade.com/getting-started/developer-guides
- E*TRADE terms: https://developer.etrade.com/support/terms-of-use
- IRS Publication 550: https://www.irs.gov/publications/p550
