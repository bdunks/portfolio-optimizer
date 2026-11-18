# Vanguard synthetic JSON contract v1

These fixtures define a deterministic adapter test format, **not** a verified live Vanguard API response. The adapter receives an explicitly configured URL and fund ID and an injected HTTP client.

The UTF-8 JSON root has exactly `schema_version: "vanguard.holdings.v1"`, `fund: {"ticker": string, "id": string}`, `as_of_date: "YYYY-MM-DD"`, and `holdings: [...]`. Each holding has an optional `ticker`, optional `cusip`, required `weight_pct` (decimal percentage from 0 through 100), and optional `sector` and `size` labels. At least one of ticker or CUSIP is required. No other keys are accepted. Tickers/CUSIPs are retained as identifiers; only tickers enter the existing `security` exposure dimension. `sector` and `size` rows use the holding's supplied weight. Missing labels produce missing rows, not inferred categories, and no dimension is renormalized.

The adapter reports observed/total holding counts and a boolean completeness value independently for `security`, `sector`, and `size`; empty holdings never imply complete coverage. Duplicate tickers or CUSIPs and invalid weights reject the response. The `source_url`, configured fund ID, and source date accompany the output. No request in this fixture suite contacts a provider.
