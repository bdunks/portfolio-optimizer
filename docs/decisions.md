# Decisions and Acceptance Boundaries

This is the canonical decision record; specifications retain precedence. See `AGENTS.md` for recording and escalation rules.

New or revised records state: stable ID, status (`Open`, `Provisional`, `Accepted`, `Superseded`), decision/rationale, authority (owner approval or spec reference), and affected contracts/tests. Preserve existing IDs (`A`–`H`); link replacement records when superseding.

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


## G. US transition destination sleeve — owner clarification

The transition tracks the explicitly designated New sub-sleeve within the US direct-indexing container, not particular securities. Its progress numerator is the value assigned to the designated sleeve plus every nested descendant, regardless of ticker or asset type; values in other sibling sub-sleeves do not count. The denominator is the enabled direct-index container value.

The `is_transition_destination` role is singular when enabled, must be a strict descendant of the unique enabled direct-index container, and cannot overlap the legacy `is_direct_index_sleeve` branch. A policy with no enabled designation is explicitly unconfigured: progress is unavailable (`null`), never inferred from ETF membership, names, or sibling exclusion. This supersedes the VTI/ITOT-only wording in the illustrative examples and any ETF-membership test expectation.

Do not infer or backfill this role from ticker names or old frozen run inputs. Existing saved policy revisions remain unconfigured through migration unless a future owner-approved, defensible migration identifies an authoritative designation; the packaged DEMO policy explicitly designates its New sleeve.

## H. Shared accounting and future Pass 2 boundary

For t-0059, current portfolio presentation and DEMO initial/subset effects share the pure Decimal `evaluate_portfolio` core; the core consumes frozen typed inputs and canonical legs, not a web request, database session, broker, or solver totals. Deterministic DEMO candidate generation is separate from reusable leg construction, subset orchestration, persistence, and response presentation.

The future bounded Pass 2 worker must receive immutable inputs and a deadline, then return a rounded candidate basket and solver metadata without writing saved results. The request owner independently evaluates the rounded legs from source inputs, checks constraints and staleness/deadline, and alone publishes a valid result. Subset selection re-solves and re-rounds the selected lots before that validation. This boundary documents an extension point; it does not claim a production solver, wash/risk validation, broker order handling, or worker process is implemented.

## I. Exact-lot review ownership across component-key collisions

- **ID:** I. **Status:** Accepted (2026-11-14).
- **Decision:** Saved review opportunities own exact broker-lot restoration universes. A solver component label such as `sale:AAPL` is not an opportunity identity and cannot transfer ownership, rejection, notes or public IDs between disjoint lot universes. Reconcile active components to saved opportunities by actual lot lineage; an unmatched emitted component whose label collides with a disjoint saved opportunity must receive a distinct deterministic internal ownership key. Keep the disjoint saved opportunity and its public ID, rejection, reason, note and lot universe intact. Do not merely remove its rejection or let it own an active SELL.
- **Restoration and identities:** A valid explicit selection of the original opportunity's omitted lots must succeed even when a rejected disjoint opportunity has the same ticker/component label. Preserve the original public identity on its matching descendant; on splits, inherit an old identity at most once and allocate distinct deterministic identities to other descendants, independent of economic rank. Retain omitted lots under exactly one restorable opportunity. Annotation inheritance follows matching lineage, never label equality alone; do not duplicate unrelated notes/rejections onto new descendants.
- **Exclusion and intent:** Rejected opportunities exclude their owned exact lot universe, not every lot sharing the ticker or solver label. Both group selection and complete lot-review intent must reject attempts to select those rejected lots until explicitly restored. Restoration of rejection still clears the reason without selecting the opportunity (technical §8). Successful review publishes exactly the requested positive whole-share SELL lot set, with no extra/rejected lots and only selected, non-rejected active owners.
- **Atomicity:** Existing currentness, source generation, exact intent, independent financial validation, compare-and-swap and full transactional rollback remain mandatory. Keep the fail-closed ownership guard for genuinely inconsistent output. No API/schema change, solver redesign or order approval is authorized.
- **Rationale/authority:** Technical §8 generation-bound complete lot intent and annotation semantics; functional §4.1 arbitrary subset/sell-lot review; decisions E/H; owner-authorized t-0045 restoration closure. This resolves an internal identity collision without restricting valid workflows or changing financial semantics.
- **Affected contracts/tests:** `backend/app/services/optimizer_service.py` persistence reconciliation, selection and lot-intent validation/readback; `backend/tests/test_optimizer_coherent_groups.py` real SQLite/FK restoration, rejected-disjoint exclusion, omitted-lot lineage, both split rank orders and stable IDs; service exact-intent, CAS and rollback regressions. No new quality/performance acceptance.

## J. Persist owner-validated net realized results

- **ID:** J. **Status:** Accepted.
- **Decision:** Production recommendation publication must preserve the independent Decimal evaluation's fee-adjusted per-lot realized P/L and holding term. Aggregate those validated lot effects into persisted SELL leg net ST/LT and group realized ST/LT; do not recompute gross price gains in persistence or allocate the same consolidated SELL fee again. BUY fees affect cash/cost, not SELL realized P/L. Preserve exact Decimal aggregation, broker-lot intent and existing API/schema.
- **Rationale/authority:** Technical §§4.2/6.2 define net leg ST/LT and per-lot realized gains after allocated fees; decisions E/H require canonical consolidated orders and independent owner accounting. Owner-authorized t-0090 explicitly permits the smallest confirmed emitted-basket correctness fix. Source inspection found `_persist_candidate` recomputes gross results while `evaluate_portfolio` subtracts allocated SELL fees. This is a contract-alignment fix, not a new financial assumption.
- **Affected contracts/tests:** `backend/app/services/optimizer_service.py` production publication/persistence and summary/recommendation readback; focused native positive-fee, mixed-term multi-lot consolidation and real SQLite round-trip regressions. Invalid fee/funding candidates remain independently rejected. No schema migration, rewrite of historical immutable runs, search-quality claim or Phase 2 acceptance is authorized.

## K. Measurement-only performance checkpoint

- **ID:** K / M005-PERF-03. **Status:** Accepted.
- **Decision:** Record current bounded synthetic measurements and explicit deltas or unknowns against required specification targets in t-0046; do not optimize until targets pass. Finish the existing lint correction, scenario checks and fresh change-scoped review. Reuse the existing benchmark harness with only minimum scenario selection. Defer profiling expansion, missing fine-grained instrumentation and tuning until separately authorized work with owner-supplied real-data fixtures; no new benchmark system or synthetic tuning loop.
- **Authority/rationale:** Owner explicitly approved do-now measurement versus later real-data optimization and instructed: record current performance and delta to required targets, do not optimize, YAGNI. This supersedes t-0046 task closure wording that required all performance targets to pass. It does not change specification targets or claim compliance with unmet requirements.
- **Safety/acceptance:** A/C/H remain mandatory: absolute 10-second deadline, kill/reap overruns, bounded capacity, independent Decimal validation and no late/invalid publication. Reliability or financial failures still block. Performance misses and unmeasured reporting fields remain explicit residual requirements for t-0047 and deferred work, not silently waived or labeled full specification/Phase 2 acceptance. Controlled BUY/recent-loss cases restrict eligible lots and provide targeted full-dimension path coverage, not broad-candidate or worst-case evidence. Synthetic timings do not predict live performance.
- **Affected contracts/tests:** t-0046 instructions/criteria and measurements; t-0047 residual-gate review; deferred real-data performance task; existing benchmark fixture/harness tests and reports. Financial semantics, APIs/schema, production solver and target values remain unchanged. No real-data loading, broker traffic or orders authorized now.

## L. Offline OAuth lifecycle and credential boundary

- **ID:** L / M006-OAUTH-01. **Status:** Accepted.
- **Decision:** For t-0048 implement the technical §5 OAuth lifecycle through an explicitly injected fake HTTP transport and clock. Default application construction has no live OAuth transport and remains disabled even when consumer credentials exist. Keep request and access token secrets only in backend memory; restart requires reauthorization. Do not add keyring infrastructure or account binding/data reads in this slice. Authentication means valid OAuth tokens, not verified account selection or synchronized holdings; `account_id_key` stays null until the subsequent account task.
- **Credential contract:** One gitignored `backend/.env` contains `ETRADE_CONSUMER_KEY` and `ETRADE_CONSUMER_SECRET`; tracked `backend/.env.example` contains placeholders only. Document explicit environment loading, never inspect the owner's file, and never expose credentials through frontend variables. Saving credentials does not authorize live access.
- **Lifecycle:** Renew before a future authenticated read when idle strictly more than 90 minutes but less than 2 hours; reject at 2 hours or at the next America/New_York midnight. Status checks do not count as broker activity. Pending request state is one-use, bounded in memory, and replaced by a new start. Define and test its short local TTL as a technical safety limit, not broker policy. Serialize lifecycle mutations to prevent stale exchanges/renewals from restoring invalidated state.
- **Authority/rationale:** Technical §5, decisions B/D and owner-authorized t-0048 under M006-DECOMP-01. This records implementation/lifecycle boundaries without authorizing live traffic or changing financial semantics.
- **Affected contracts/tests:** Backend auth service, `create_app` injection and start/verify/status DTOs; generated OpenAPI/TypeScript; deterministic fake-HTTP signing, error, replay, renewal, expiry and secret-leakage regressions; missing-credentials and no-credentials DEMO compatibility. No new browser auth screen, schema migration, order workflow or live acceptance is authorized.

### L1. Reuse the validated PoC OAuth stack

- **ID:** L1 / M006-OAUTH-02. **Status:** Accepted.
- **Decision:** Owner-directed repair of t-0048 reuses `../etrade-poc` revision `ee74d5debbc0ee69d6066e3a42fd1e8dc77473d7`: `requests-oauthlib` / `OAuth1Session`, explicit HMAC-SHA1 Authorization-header signing, `oob`, the proven request/access URLs, bounded timeouts and disabled redirects. Use an injected fake requests transport/adapter and port the PoC signing assertions. Do not maintain a second custom signing implementation or a cross-library HTTPX/Authlib compatibility bridge. Keep the existing t-0048 memory/clock/expiry and public API contracts; adapt the unconsumed future-read signing boundary and its tests consistently. Declare and lock required PoC dependencies rather than relying on incidental installation.
- **Authority/rationale:** Owner explicitly requested inspecting PoC flow/libraries and fixing this implementation after the failed recovery. Parent read current PoC client/request/access functions and full signing regression, plus its dependency declarations. The prior alternative Authlib integration fails before transport dispatch. Reusing the validated stack minimizes protocol rediscovery; it does not import the PoC explorer architecture, session TTL or account-data features.
- **Affected contracts/tests:** OAuth service transport/signing boundary and fake fixtures, backend dependency declarations/lockfile, exact request/access/read-query signing regressions, existing lifecycle/API/DEMO checks and fresh change-scoped review. L/B/D offline, secret and account boundaries remain unchanged. No live requests or credential-file inspection.

## M. Strict backend typing repair

- **ID:** M / TYPECHECK-01. **Status:** Accepted.
- **Decision:** Preserve strict backend type checking, including tests. Fix shared annotations and typed boundaries in bounded, sequential, reviewed increments; do not exclude tests, relax diagnostics, or add suppressions to hide failures. Preserve existing financial, lifecycle, API and persistence contracts under A–L1; ask before material behavior changes.
- **Authority/rationale:** Owner requested `mise run typecheck:backend` fixes grouped for impact, and explicitly selected strict test fixes and a separate baseline commit preserving all existing uncommitted edits before implementation.
- **Affected contracts/tests:** Backend application, migrations, scripts and test fixture/caller typing; exact command must pass, with affected runtime regressions, compatibility and persistence checks. Existing edits are a preserved, unvalidated baseline, not accepted implementation. No broker traffic, credential access, schema redesign or new financial semantics are authorized.
- **Precision boundary clarification:** Preserve failure for non-finite inputs to exact-sum precision sizing; explicitly reject special Decimal exponents with `ValueError` rather than introduce NaN/infinity propagation. This replaces an incidental precision-arithmetic failure, not supported finite-input behavior. Apply local narrowing in historical migration code without importing mutable application helpers; cover special-value rejection and unchanged finite/empty sums. Authority: orchestrator's routine technical resolution under M; no financial-policy change.
