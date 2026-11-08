# Decisions and Acceptance Boundaries

These decisions record owner approvals from planning. The specifications remain authoritative for financial semantics; do not use this file to override them silently.

## A. Tax formulation — approved

Preserve the exact piecewise-linear T(S,L) in technical §6.2. It is not globally convex. Enumerate its bounded affine regions (sign/cross-netting and deduction/retained-loss breakpoints), solve each feasible convex subproblem using CVXPY/OSQP with CLARABEL fallback under one deadline, and compare independently Decimal-validated rounded baskets with the same objective and no-trade baseline. Include boundary/coverage tests. Rounding can cross regions: recompute exact tax afterward. Do not claim global integer optimality or complete search after interruption. Benchmark the full search, not one region.

The owner approved this option explicitly. An alternative MILP solver is deferred as Draft backlog task `t-0057`; it is not an overnight gate. Screening and integer repair may sacrifice quality and must be disclosed. Comparable MILP benchmarking remains deferred, not a mandatory new overnight solver implementation.

## B. Phase 1 endpoint scope — approved

Working offline/demo contracts cover portfolio, lots, policy, sync, run/recommendations, subset recalculation, export, wash view and activity. Deterministic recommendations must be labeled DEMO. Future-phase OAuth/optimizer/order capabilities return explicit unavailable/disabled responses until implemented; never fabricate real success. Order tables and implementation arrive in Phase 5.

## C. Deadline enforcement — requested fix incorporated in technical §§1/6.5/8

Use a monotonic shared 10-second computation deadline, solver-native time limits, reserved repair/validation time, bounded worker processes/concurrency, overrun termination/reaping and request-owner-only result publication. Await cancellation alone is insufficient. No worker writes results after timeout. Test hangs, repeated timeouts, resource reclamation and late-result rejection. Persistence/response overhead is measured separately. This is a specification fix, not a claim that runtime code is implemented.

## D. Offline acceptance — owner-directed

- Phase 3: implement and fixture-test the simple OAuth flow; defer actual interactive OAuth/account acceptance. The owner previously POC'd OAuth in Luna; no live test of this build is implied.
- Phase 4: automate functional browser flows, keyboard behavior, desktop/tablet layout assertions, error handling, migration/backup/restart, security and reconciliation checks. No manual QA is a mandatory overnight gate. Human aesthetic/usability judgment and exploratory checks are deferred follow-up; automated checks cannot prove subjective quality or complete accessibility.
- Phase 5: implement the complete individually approved order workflow and broker adapter payloads, tested against FakeBroker/fake transport only. No broker connection overnight, including reads, OAuth, preview and submission. Live writes remain disabled.
- Before live enablement, separately validate actual OAuth/account/lot capabilities, current terms/permissions, and explicit release authorization. Deferral does not waive these release requirements.

## Fractional legacy cleanup — explanation, not a new approved trading rule

“Small lot” can mean a small dollar amount or a small whole-share holding; both work with whole-share orders and no minimum sell notional. The ambiguity concerns an actual fractional remainder such as a 0.37-share historical DRIP lot. Selling that lot in full differs from requiring every sell/order quantity to be an integer; summing fractional lot allocations into an integer order also depends on broker attribution capabilities.

No owner-approved resolution of that broker capability is recorded. Preserve quantities losslessly, never round up/truncate, and explicitly flag unsupported fractional cleanup instead of presenting it as executable. Do not block unrelated whole-share recommendations or the offline program on this capability. Before enabling such cleanup, verify broker support for fractional disposal and lot attribution and obtain any necessary financial-semantics clarification. Do not claim all fractional legacy lots can be closed by whole-share-only orders.

## E. Consolidated recommendation leg API — approved during Phase 1A review

The owner selected a canonical run-level collection of consolidated legs with group references to leg IDs. Persist one replacement BUY per ticker, with explicit dependencies on its funding SELLs; count and export each unique leg once. Do not make duplicated nested BUY objects the canonical consumer representation. Update Pydantic/OpenAPI/generated TypeScript and regression tests before frontend consumers. Subset recalculation must resize the shared BUY without orphaning dependencies; group selection is never order approval.


## F. Proposed trade-date assumptions — approved for t-0058

Live defaults use the current calendar date in `America/New_York`; weekends and holidays are not advanced. A caller-supplied date takes precedence. Deterministic DEMO runs default to fixture date `2026-11-05`, independent of wall-clock and source timestamps, and also accept an explicit date.

A saved run retains its proposed trade date separately from account, quote, and run-creation timestamps. Reopening and selection re-solving use that stored assumption; a later preview or submission must revalidate the intended execution date. No Phase 5 preview or submission behavior is implemented. The trade-date migration copies an explicit date from saved provenance, or for legacy `demo-run-input-v1` runs derives the date from that run's frozen account `as_of` timestamp because the prior DEMO classifier used that date. If immutable provenance cannot establish the date, it remains null and reopening must report it as unavailable rather than substitute today's date.