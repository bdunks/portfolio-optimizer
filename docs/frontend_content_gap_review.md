# Frontend content gap review

**Status:** Content directions approved by the owner on 2026-11-11. Milestone `m-010` contains nine Ready tasks: `t-0067` first, followed by `t-0071`–`t-0078`. No frontend implementation was performed.

**Compared:** `docs/portfolio_tax_optimizer_reference.html` against the current working-tree frontend, including the in-progress shadcn migration. Reviewed all six routed pages and their content-bearing shared components on 2026-11-11.

## Scope and interpretation

This review concerns **what the user sees, what it means, and its information hierarchy**: headline metrics, sections, summaries, explanations, and review entry points. It excludes markup/component choices, pixel styling, illustrative numbers, missing API data, and broker integration.

The functional and technical specifications remain authoritative. The reference is not a reason to restore hard-coded holdings, simulated financial results, unsafe independent BUY selection, browser-only policy persistence, or premature order approval.

Classification:

- **Missing:** no equivalent content in the inspected page/components.
- **Displaced:** content exists, but not at the reference's level of prominence.
- **Partial:** some equivalent content exists, but an important explanation or summary is absent.
- **Existing backlog:** already substantially described by `t-0067`; do not create duplicate work.

**Important correction:** Overview already has **Portfolio Allocation** and **US Equities Transition**, including current/proposed/target views. They are below portfolio diagnostics and the latest-run summary. The gap is their prominence and surrounding explanatory content, not their complete absence.

## 1. Overview (`/`)

Reference: `docs/portfolio_tax_optimizer_reference.html:110–135`.
Actual: `frontend/src/pages/IndexPage.vue`; `frontend/src/components/RunSummary.vue:1–100`; `frontend/src/components/AllocationTargets.vue`; `frontend/src/components/USAllocationTransition.vue:1–100`.

### O1 — Optimization-oriented headline cards

**Classification: Partial / displaced.**

| Reference headline | Actual equivalent | Proposed content direction |
|---|---|---|
| Selected gross losses | No equivalent headline. Estimated tax benefit appears in Latest recommendations, but is a different measure. | Show selected-basket gross losses distinctly from estimated tax benefit. Never relabel one as the other. |
| ST / LT realized | Estimated ST and LT realized P/L exists in the lower run summary. | Promote the selected-basket ST/LT split to the headline summary. |
| Tracking error | Risk tracking — Not calculated already exists at the top. | Preserve honest unavailable risk content; there is no missing risk card to invent. Clarify current/post-trade context when supported. |
| Direct equities | Positions headline is an overall inventory count; lots sold/positions exited appear lower. | Surface direct-equity/consolidation context, retaining useful overall position/lot counts rather than assuming they are equivalent. |
| US ETF transition | Destination progress exists in the lower transition section. | Promote **current progress into the configured destination within US equities**, not a hard-coded ETF-only measure. |

Actual headline cards are **Portfolio value, Cash, Positions, Risk tracking**. Portfolio value and cash remain useful, but currently displace the tax/consolidation/transition story.

**Approval proposal:** make the top summary optimization-oriented. Retain estimated tax benefit because functional §4 requires it, even though the reference uses gross losses. Do not force an exact five-card limit or remove useful portfolio/cash context merely to match the prototype.

### O2 — Main page narrative

**Classification: Displaced.** Reference leads with US transition, then allocation and recommendations. Actual leads with Portfolio data and Latest recommendations; Portfolio Allocation and US Equities Transition follow.

**Proposal:** prioritize **headline outcomes → US transition → allocation + recommendations**, with source/sync/coverage and frozen-run details as supporting context. Keep blocking errors, stale-context warnings, and readiness visible; this is not approval to hide safety information.

### O3 — Explain the transition, not just its numbers

**Classification: Partial.** Actual transition shows US value, portfolio share, destination progress, and child values in three states. Reference additionally explains the purpose, current direct-index/completion holdings, and preferred replacements.

**Proposal:** add concise configured Legacy → New context, replacement investments/destination, and policy navigation. Explain default individual-equity + VB/VXF assignment subject to overrides; do not copy the reference's fictional stock count or 95/5 composition. Preserve within-US versus whole-portfolio units and unavailable/no-selection states.

**Overlap:** `t-0067` establishes the enhanced transition vocabulary, mappings, replacement destinations, and policy card. Reuse that content/model; only Overview integration/prominence is additional scope.

### O4 — Replacement sets summarized by allocation

**Classification: Partial.** Reference has Allowed ETF Sets grouped by sleeve with Edit policy. Actual Active allocation policy lists sleeve targets and individual allowed tickers with sleeve labels, not a concise pair/triplet/set summary or contextual edit entry point.

**Proposal:** show configured **Replacement sets**, grouped by allocation and preserving set identity/destination, with a link to the relevant policy editing context. Avoid repeating the entire target list already shown in allocation.

**Overlap:** `t-0067` covers contextual set editing on Policy, not this Overview summary.

### O5 — Transition rules summary

**Classification: Missing as an Overview section.** Reference explains preferred replacement purchases, gain-budget-constrained appreciated sales, configurable small batches/legacy-lot cleanup, and manual per-order authorization. Actual has policy data and general safety notices, but no equivalent concise strategy summary.

**Proposal:** add a short readable summary of the applicable policy preferences and invariant safeguards. Reflect configured values; do not display every reference rule as enabled regardless of policy.

### O6 — Actual top-level recommendations, not only a run summary

**Classification: Missing.** Reference includes a sleeve-filtered recommendation list with action, sleeve, security, lot/group, quantity, realized P/L, reason, selection count/net P/L, and Review Basket. Actual Latest recommendations is run metrics and frozen policy context, not a trade preview.

**Proposal:** add a compact, economically coherent trade-group preview with the key sell/replacement details and a clear route into Recommendations/selected-basket review. Reuse backend-confirmed selection and shared consolidated BUY presentation; do not recreate the prototype's unsafe independent leg toggles. Keep detailed filtering and editing on Recommendations if that avoids a second full review UI.

## 2. Recommendations (`/recommendations`)

Reference: `docs/portfolio_tax_optimizer_reference.html:139–144,256–258,274`.
Actual: `frontend/src/pages/RecommendationsPage.vue:173–535`; `frontend/src/components/TradeGroup.vue:1–148`; `frontend/src/components/RecommendationLegDetails.vue:1–40`; `frontend/src/components/RunSummary.vue`.

### R1 — Scan groups by investment purpose before expanding

**Classification: Partial / displaced.** Reference group headers show a readable intent title, explanation, realized P/L, and selection count. Actual collapsed headers show priority, raw group type, sleeve, and selected/rejected status; rationale, P/L, lots, and linked legs are inside the expansion. Run/context/effects sections also precede the list.

**Proposal:** make group intent, a short rationale, and concise financial/selection impact visible at list-summary level. Keep priority distinct from execution order. Bring the group list forward without losing the useful current/proposed effect summary or safety context.

### R2 — Concise selected-basket summary adjacent to the group list

**Classification: Partial.** Reference ends the list with selected line count, signed net realized P/L, and Review Selected Trades. Actual has extensive run metrics above, plus top-N/clear-and-re-solve controls, but no equivalent compact selected-basket footer beside the end of the list.

**Proposal:** provide an adjacent summary of confirmed selected groups, sell lots, consolidated order lines, and signed ST/LT/net realized P/L, with a review entry point. Clearly distinguish these counts and P/L from tax benefit. Reuse current metrics rather than creating a second source of truth.

### R3 — One focused selected-basket review view

**Classification: Missing as a dedicated content view.** Reference's Review Selected Trades opens a selected-orders summary: side/ticker, shares, exact sell lots, gross losses, signed net P/L, and explicit no-execution wording. Actual supplies those kinds of detail across expanded groups/shared legs/run summary, but has no focused review queue/dialog/page or Review Selected Trades action. Export is not the same content.

**Proposal:** a non-actionable consolidated review view, showing each canonical order leg once, exact lot attribution, execution sequence/dependencies, and basket totals. It must remain **review only**: no blanket approval, fake broker preview, or trading controls. Real individual-order authorization stays in Phase 5. The presentation need not be a modal.

**Already present; preserve:** ranked expandable groups, more filters than the reference, arbitrary group/sell-lot selection with re-solve, top-N, shared BUY handling, dependency information, notes/rejection, frozen saved runs, CSV/JSON export, and explicit demo/staleness protections. These are not gaps.

## 3. Tax Lots (`/lots`)

Reference: `docs/portfolio_tax_optimizer_reference.html:147–149,260`.
Actual: `frontend/src/pages/TaxLotsPage.vue:1–496`.

### L1 — Lot interpretation and constraints explainer

**Classification: Missing as a coherent help section.** Reference has Lot-Level Requirements explaining broker lot identity/basis/available shares, ST/LT tax treatment, account wash restrictions, and small-lot cleanup/consolidation. Actual has richer lot rows and a detailed Requested lot intent panel, but no equivalent financial interpretation panel.

**Proposal:** adapt this into user-facing **How to interpret these lots**, not a developer “implementation contract.” Briefly explain adjusted basis, ST/LT versus actual tax impact, wash eligibility, small legacy-lot cleanup, and same-ticker multi-lot consolidation. Link to Wash Sales and retain the existing distinction between requested intent, confirmed basket, and order approval.

### L2 — Financial review status versus data-quality flags

**Classification: Partial.** Reference labels lots Harvest candidate or Gain review. Actual labels quality/cleanup conditions and request/confirmation state; a user must interpret unrealized P/L separately.

**Proposal:** make the financial distinction between a loss opportunity and an appreciated-lot review legible, separately from quality/cleanup and selection. Do **not** copy the prototype's sign-only eligibility shortcut: a loss is not automatically harvestable, and a gain is not automatically authorized. If eligibility is unavailable, label the interpretation accordingly rather than adding invented statuses.

**Already present; preserve:** grouped security → lot rows, account-wide search/filter/sort/pagination, exact broker IDs, acquisition dates, available shares, adjusted basis, prices, dollar/% P/L, term, sleeve, cleanup flags, and explicit complete-set lot-intent application. Do not replace this with the reference's much smaller sample table.

## 4. Allocation Policy (`/policy`)

Reference: `docs/portfolio_tax_optimizer_reference.html:152–193,269–272`.
Actual: `frontend/src/pages/PolicyPage.vue:1–321`; `frontend/src/components/PolicySleevesEditor.vue`; `frontend/src/components/PolicyReplacementSetsEditor.vue`; `frontend/src/components/PolicyTaxBatchSettings.vue`.

### P1 — At-a-glance policy summary

**Classification: Missing as a top-level summary.** Reference has Total Sleeves, Default Drift Band, Gain Budget, Batch Cap. Actual starts with revision/draft management; those settings must be discovered in editors.

**Proposal:** add a compact policy summary with enabled allocation count, drift-band context, gain budget, and batch limits. Identify whether values describe the active policy or the edited draft. Do not invent a global default drift band when bands differ; summarize them honestly. Include ticker/lot/order limits rather than implying the ticker limit is the entire batch policy.

### P2 — Current allocation and status alongside target editing

**Classification: Missing from the allocation editor.** Reference compares Current / Target / Drift / Status (Within band, Outside band, Transitioning). Actual editor has target and drift-band inputs plus structural configuration, but not current allocation or readable allocation status.

**Proposal:** show current weight and a contextual target/drift status beside the configured target, with clear percentage bases. Keep allocation status distinct from policy activation validation. Missing/stale current weights stay unavailable; a zero target must not imply an immediate liquidation instruction.

### P3 — Visibly hierarchical allocations

**Classification: Existing backlog — `t-0067`.** Actual normal table exposes Parent and Designations columns; the enhanced agreed task makes parent/child structure readable, creates children from parents, labels percentage bases, and moves structural roles out of the normal workflow.

**Proposal:** retain the existing task as the owner. Do not create a second hierarchy task in the proposed milestone.

### P4 — Visible US Equities Transition Policy

**Classification: Missing / existing backlog — `t-0067`.** Reference has a dedicated transition policy card. Actual has role checkboxes, nested targets, and replacement candidates, but no always-readable transition-policy section.

**Proposal:** use `t-0067`'s enhanced current / after-selected / target card, guided explicit US/Legacy/New setup, destination replacements, and gradual tax-constrained transition explanation. Its configured-destination semantics supersede the reference's simplistic “ETF percentage.”

### P5 — Replacement sets in allocation context

**Classification: Partial / existing backlog — `t-0067`.** Reference summarizes candidates by sleeve/set strategy; actual exposes a standalone candidate-level configuration table with set IDs, priority, sleeve/sub-sleeve, suitability, and enabled state.

**Proposal:** follow `t-0067`: readable set chips and Edit replacements on the allocation, plus the same configuration in the transition card. Preserve all detailed configuration behind contextual editing; do not restore a second prominent standalone table just to match the reference.

### P6 — Policy behavior and invariant safeguards are discoverable

**Classification: Displaced / partial, not missing preference controls.** The reference has a separate Policy Rules section. Actual already has all four controls—prefer ETF buys, allow appreciated-gain sales, permit ETF harvesting, permit municipal-bond exit—near the end of Tax & Batch Settings. Manual per-order approval is communicated generically, not as an adjacent always-on policy invariant.

**Proposal:** make these behavioral preferences a clearly discoverable policy group/summary and state that individual order approval is an invariant, not an editable bypass. Reuse the existing controls; do not add duplicate state or an approval checkbox.

### P7 — Explain what targets do and do not require

**Classification: Partial.** Exact target validation and activation checks already exist. Reference also explains that targets are gradual constraints, with tax, wash, gain, batch, and risk limits determining the executable basket.

**Proposal:** retain that explanation near target editing/transition status, beyond mechanical activation errors. The transition-specific part overlaps `t-0067`; general target guidance belongs alongside the allocation editor.

**Already present; preserve:** draft/save/activate, immutable revisions, dirty-draft protections, allocation CRUD/reassignment, exact target-sum checks, holding overrides, replacement candidate configuration, and the reference's Tax & Batch fields (plus additional supported settings). Missing integration or risk-model fields are outside this review; no dummy controls are proposed.

## 5. Wash Sales (`/wash-sales`)

Reference: `docs/portfolio_tax_optimizer_reference.html:196–198`.
Actual: `frontend/src/pages/WashSalesPage.vue:139–403,574–587`.

### W1 — Restrictions and decisions before the history ledger

**Classification: Displaced.** Reference's primary content is Wash-Sale Restrictions and decisions. Actual leads with API coverage counts, then acquisition/transaction history, then Purchase restrictions.

**Proposal:** lead with current/proposed restriction decisions and relevant dates; make history supporting evidence. Preserve coverage warnings and the distinction between proposed versus executed triggers. This is information hierarchy, not a table/CSS redesign.

### W2 — Explain configured replacement assumptions here

**Classification: Missing on this page.** Reference lists approved distinct pairs/triplets and their relationship assumptions. Actual shows history/restrictions but not the configured replacement-set context; a related caveat exists only in the Policy replacement editor.

**Proposal:** show or link a compact policy-derived replacement-set summary, explicitly labeled **user policy assumption, not wash-sale clearance**. State that same-ticker repurchases remain restricted. Keep assumptions separate from actual restriction/eligibility rows; do not copy fictional pairs or the prototype's affirmative broker-alignment badge.

### W3 — Plain-language wash-sale safeguards

**Classification: Missing as a help section.** Reference has Production Risk Controls. Actual has good API coverage caveats, but not the equivalent rule explanation.

**Proposal:** explain managed-account-only scope, DRIP-disabled assumption, authoritative adjusted basis, the prior-30-calendar-day acquisition rule and its full recent-acquisition-sale exception, and forward no-buy restrictions through day +30 (eligible +31). Explain basket revalidation and eventual per-order checks without implying broker approval is available now. Describe safeguards as requirements/assumptions, not a certification that unavailable data passed them.

**Already present; preserve:** acquisition/transaction history, filters, current/proposed restriction distinction, trigger, loss-sale date, next eligible purchase date, validation, run/source, and explicit coverage limitations. Conflicting transaction/affected-lot API omissions are acknowledged, but are data-contract work, not new gaps in this content-only proposal.

## 6. Activity (`/activity`)

Reference: `docs/portfolio_tax_optimizer_reference.html:200–201`.
Actual: `frontend/src/pages/ActivityPage.vue:54–272`.

### A1 — A readable audit story rather than raw event codes

**Classification: Partial.** Reference labels recognizable categories—Policy revised, Portfolio snapshot, Optimizer run, Order-level authorization, Fill reconciliation—with descriptions. Actual event headings/statuses use returned API codes; filters ask for exact API event type/status.

**Proposal:** use friendly labels/categories for supported policy, sync, optimizer, and selection events, retaining raw codes as secondary detail and preserving unknown event types. Make common filters understandable without knowing API tokens.

### A2 — Human-readable event summaries before JSON

**Classification: Partial.** Actual shows timestamps, status, correlation/event IDs, and expandable JSON details, with useful saved-run reopening. It does not provide the reference's explanatory “what happened / what was affected” summary at event level.

**Proposal:** summarize returned policy revision/changed settings, sync context, run assumptions/outcome, or selection change as appropriate, with errors readable without parsing JSON. Preserve structured raw details and saved-run provenance. Do not fabricate details absent from an event.

**Not a current content defect:** the reference explicitly labels order authorization and fill reconciliation as future integration. Keep those event types in their existing later-phase scope; do not add sample “successful” authorizations/fills to make this screen look complete.

## 7. Shared workspace content

Reference: `docs/portfolio_tax_optimizer_reference.html:98–108,252`.
Actual: `frontend/src/layouts/MainLayout.vue:1–44`; `frontend/src/layouts/WorkspaceSidebar.vue`.

### C1 — Persistent portfolio structure summary

**Classification: Missing.** Reference sidebar summarizes sleeve count, allocation coverage, and stock/lot counts. Actual sidebar footer contains local-demo/safety messaging only.

**Proposal:** restore a compact portfolio-structure summary in shared navigation, using honest current/unavailable values. Do not hard-code five sleeves or confuse targets summing to 100% with verified holdings coverage. Keep the safety message.

### C2 — Consistent access to review

**Classification: Missing shared entry point.** Reference offers Run Optimizer and Review Trades across pages (Policy switches to Save Policy / Run What-If). Actual run actions are page-specific on Overview/Recommendations; navigation to Recommendations exists, but there is no named shared selected-basket review action.

**Proposal:** provide consistent access to the non-actionable review content in R3, with selection/context state. This need not duplicate Run/Sync/Save controls on every page. Do not port the reference's localStorage Save or pretend that Run What-If is a supported workflow.

## Approved boundary and backlog mapping

Approval covers the **content directions**, not particular markup, widgets, financial values, backend implementation, or execution of the implementation tasks.

1. **Overview:** optimization KPIs, transition-first narrative, contextual replacement/rule summaries, and a real recommendation preview (O1–O6).
2. **Recommendations:** scannable group intent, an adjacent confirmed basket summary, and focused review-only content (R1–R3).
3. **Tax Lots:** interpretation help and clearer financial-versus-quality status language (L1–L2).
4. **Policy:** at-a-glance summary, current-versus-target status, discoverable behavior rules, and target guidance (P1–P2, P6–P7). Reuse **existing `t-0067`** for P3–P5 and the overlapping transition/set content in O3–O4.
5. **Wash Sales:** restrictions-first narrative, replacement assumptions, and rule guidance (W1–W3).
6. **Activity:** friendly event categories and readable summaries, without manufacturing future broker events (A1–A2).
7. **Shared:** portfolio-structure context and a consistent review entry point (C1–C2).

**`m-010` — Frontend content alignment** now contains nine Ready tasks, ordered with `t-0067` before its dependents:

| Task | Scope | Gap IDs | Prerequisites |
|---|---|---|---|
| `t-0067` | Allocation hierarchy, transition policy and contextual replacements | P3–P5; shared configuration for O3–O4 | None |
| `t-0071` | Policy summaries, current/target status, rules and guidance | P1–P2, P6–P7 | `t-0067` |
| `t-0072` | Scannable recommendation groups and confirmed basket impact | R1–R2 | None |
| `t-0073` | Focused review-only basket and shared access | R3, C2 | `t-0072` |
| `t-0074` | Optimization-first Overview narrative and recommendation preview | O1–O6 | `t-0067`, `t-0073` |
| `t-0075` | Tax-lot interpretation and financial-review language | L1–L2 | None |
| `t-0076` | Restrictions-first Wash Sales and policy assumptions | W1–W3 | None |
| `t-0077` | Readable activity labels, summaries and filters | A1–A2 | None |
| `t-0078` | Shared portfolio-structure context | C1 | None |

At the owner's request, **`t-0067` moved from `m-004` to first position in `m-010`**, retaining its requirements and ownership of P3–P5 plus the overlapping transition/replacement configuration in O3–O4. All 25 gap IDs remain mapped without duplication. The milestone and all nine tasks are **Ready**, with existing prerequisites preserved. `t-0070` remains the in-progress migration owner; implementation must re-read current sources and coordinate rather than overwrite its work. No tasks were marked Done and no frontend implementation was performed.

## Evidence and limits

- Inspected route definitions and current page/shared-component source, including dynamically rendered reference recommendations, lot statuses, and review dialog content—not just static HTML headings.
- Consulted functional §4–5 and `t-0067`. The existing backlog was inspected for context, but this is not an exhaustive audit of every task's future implementation scope.
- Graph project: `home-quest-dev-portfolio-optimizer`, generation `2026-11-09T23:19:50Z`. Exact-path coverage reports current frontend files as changed/new relative to that index; findings therefore use direct current source, not stale graph absence. The reference's recorded partial ranges at lines 165 and 198 were directly read.
- This is a point-in-time **source content review**, not a rendered-browser acceptance test. No tests, build, backend/API verification, live data checks, or pixel/accessibility audit were run. Concurrent migration edits may change source line positions or close gaps before implementation starts.
