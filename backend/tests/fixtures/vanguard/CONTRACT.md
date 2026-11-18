# Captured Vanguard holdings excerpts

These trimmed examples are copied from read-only GET responses to
`https://advisors.vanguard.com/investments/products/api/funds/{FUND_ID}/holdings/latest`.
Each response reported `latestEffectiveDate: 2026-10-31`; the configured request supplies
fund identity because the wire response has no fund ID or schema version. The selected date
section contains the direct `equity` and `fixedIncome` arrays.

| Fund | ID | Captured direct rows | Full observed direct array (rows; numeric weights; blanks; numeric total) |
| --- | --- | --- | --- |
| VTI | `0970` | 3 equity | 3,511; 3,418; 93; 99.47432% |
| VB | `0969` | 3 equity | 1,301; 1,297; 4; 98.47759% |
| VXF | `0965` | 3 equity | 3,355; 3,264; 91; 97.53700% |
| VIG | `0920` | 2 equity | 333; 333; 0; 99.22426% |
| VEA | `0936` | 6 equity | 3,890; 3,884; 6; 98.01278% |
| VWO | `0964` | 5 equity | 6,497; 6,445; 52; 95.33538% |
| VTEB | `4391` | 5 fixed income | 11,526; 11,524; 2; 99.65848% |

Only the listed representative rows are checked in; every excerpt is intentionally trimmed
and must not be treated as a full fund snapshot. All selected constituent values and source
field names are preserved, including blank `percentOfFunds`, `cusip`, and `sedol` values.
VTI also carries actual representative reserve, money-market reserve, alternate-allocation,
and derivative rows to verify those overlapping sections are not added to direct exposures.
No full provider payload is stored in the repository.

The excerpts include the observed VEA SAP SE/Saputo ticker collision and GFL CUSIP
`36168Q104` with distinct SEDOLs `BKDT649`/`BKDT650`; those are separate listing
identities, not duplicate weights. The VWO excerpt retains a repeated foreign ticker with
separate listing identities. VTEB preserves repeated issuer ticker `PUBGEN` across distinct
bond CUSIPs. Full observed totals above were replayed from the temporary local responses;
they are provenance notes, not fixture completeness claims.
