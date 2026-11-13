# Offline optimizer quality-reference protocol

This protocol describes a future comparison, not a present production-quality result. The focused tiny fixtures in `backend/tests/test_optimizer_quality_reference.py` check the reference enumerator's mechanics only; they are synthetic and say nothing about production missed-basket rates.

## Reference boundary

`backend/tests/optimizer_quality_reference.py` enumerates every whole-share SELL allocation and BUY quantity in the caller-supplied finite `CandidateUniverse`, including the no-trade vector. It consolidates selected lots into one canonical SELL leg per ticker and records explicit assignment, canonical-basket, and feasible-basket counts. The assignment and time limits are mandatory; a cutoff means `complete: false`, and a best observed basket is not an optimum. An exact optimum is claimed only after every distinct basket in that finite universe was owner-validated.

The reference uses the owner's `validate_candidate` for feasibility and exact Decimal financial evaluation/objective scoring. This avoids production search reuse, but the validator is shared with production and therefore is not an independent proof that the tax, accounting, or other financial semantics are correct. The reference does not establish an optimum outside its explicit universe. Larger reference searches, if later added, must be labeled best-known unless complete enumeration proves otherwise.

## Comparison records

For every later production/reference comparison, retain the case ID and fixture version, input checksum, policy and validator/reference versions, explicit SELL-lot/BUY-ticker bounds, theoretical assignment count, assignments and canonical baskets examined, completion/stop reason, wall-time and assignment limits, and any source-generator seed (or explicitly record that the case is deterministic and has no random seed). Store the production candidate and its independently revalidated common-owner result. Keep synthetic fixtures distinct from captured user inputs; synthetic case frequencies are not estimates of user or market probabilities.

Only cases with a complete reference search and comparable frozen inputs enter exact small-case denominators. Report larger/incomplete reference runs separately as best-known evidence. Do not select or tune acceptance thresholds from the tiny hand-built fixtures.

## Planned measures

- **Missed feasibility:** numerator is comparable cases where production yields no owner-validated feasible basket in the comparison domain but complete reference enumeration finds at least one. Denominator is complete reference cases with at least one feasible basket. Also publish raw numerator and denominator; cases with no feasible reference basket are reported separately, not counted as misses.
- **Missed improvement:** among complete reference cases with a feasible optimum and an owner-validated feasible production basket in the same domain, numerator is cases where the production objective is strictly worse than the reference objective. Denominator is that comparable subset. Use exact Decimal comparison; equal objectives are ties. Report missed-feasibility cases separately rather than mixing them into this denominator.
- **Objective gap:** report the absolute Decimal difference `production_objective - reference_objective` (lower is better). Never publish an objective-gap percentage for a zero or negative reference objective; prefer absolute gaps for all cases and suppress the percentage when its denominator is nonpositive.
- **Economic gaps:** retain signed per-case deltas for incremental tax cost, estimated tax benefit, and estimated trading cost (production minus reference; positive cost deltas are worse, while benefit deltas must be interpreted with their sign). For allocation and sector dimensions, compare maximum absolute post-trade target drift in percentage points under the same frozen policy and denominator. Report raw per-case values plus the nearest-rank 95th percentile of absolute deltas and the worst absolute delta for each measure; state sample counts and the nearest-rank rule. Do not combine dollars and drift into an unlabelled score.

These are measurement definitions, not success thresholds. Publish actual data only after the broader, representative comparison harness has run and its inputs, bounds, versions, completion counts, and limitations have been reviewed.
