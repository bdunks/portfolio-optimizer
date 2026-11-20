# iShares ITOT fixture provenance

`itot_excerpt.csv` is a trimmed excerpt of the public ITOT response fetched from
`https://www.ishares.com/us/products/239724/ishares-core-s-p-total-u-s-stock-market-etf/latest-holdings.csv`
at `2026-11-18T14:08:29Z`, dated `Nov 17, 2026`. The complete response was
388,208 bytes with SHA-256 `5d77262eb72a5d2a538829aeceab4fd2f8aa412babbf9d49512849b4b4b10c6a`.
It retains observed AAPL, NVDA, XTSLA money market, USD Cash, ESZ6 futures, two
SOC listings, BOWL America escrow, and TGLS. The TGLS row is captured verbatim
from physical row 1763 of the response; it is an actual positive-equity foreign
listing whose provider `Weight (%)` is `0.00`. The fixture omits other source
rows, preserves one shortened quoted BlackRock footer record, and is not a
complete provider file.

`itot_signed_cash_2026-11-16.csv` contains two verbatim rows from the separate
reference capture `itot-2026-11-16-84f30bdae499.csv`: AAPL and the signed USD Cash
row at physical row 2447. That capture was fetched at
`2026-11-18T13:54:39.747338Z` from the same URL; SHA-256
`84f30bdae499a2d10940e83d9dc6d8014ddff991b18bff863326df238aa1dab4`. The parser
test composes these two same-date rows into an in-memory fake response; it does
not commit a mixed-date or complete raw capture.

The signed-cash parser test composes those captured rows and supplies the shortened
terminal BlackRock record from `itot_excerpt.csv` solely to satisfy the observed
response structure; that footer is not part of the signed-row capture. The full-capture
offline replay remains the evidence for the actual Nov 16 terminal record.
Other parser edge cases are generated as explicit test mutations; they are not
represented as provider records. No raw full holdings capture is committed.
