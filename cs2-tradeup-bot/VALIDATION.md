# Validation report

## Public repository preparation

Added public setup and publishing guides, an MIT license, contribution guidance,
Windows/Linux Python 3.12 CI, a Docker build check, and allowlisted source ZIP
packaging. Private environment files and runtime data are excluded. GitHub-hosted
CI and Docker builds require execution on their respective runners; local unit
test results do not establish that those remote builds have run.

Local release checks passed: all 70 tests also pass from the extracted 44-file
source archive without a private `.env` or market cache. CLI help, relative
documentation links, archive contents and Git ignore rules were checked. The
package scan found no copies of locally configured credential values. No live
marketplace requests or Discord deliveries were used for these checks.

## Inline listing links and floats

Restored all ten clickable listing links and individual prices/floats directly
inside Discord embed fields. Decimal formatting preserves supplied precision and
avoids scientific notation. Tests cover long real-style listing IDs, full float
precision, split fields, message size limits and absence of raw content links.
All 70 tests and syntax compilation passed after this change.

## Discord presentation and noise reduction

Added ranked embed digests, full-details text attachments, Discord size-aware
pagination and suppression of routine continuation notices. Tests verify all
listing links survive in attachments, negative EV remains visible, one normal
contract uses one multipart post and large batches obey embed limits. Marketplace
and Discord requests were mocked. The actual-versus-generic Ventilator float
regression also passes; no mathematical correction or tighter risk policy was
needed after the user clarified the screenshot mismatch.
All **68 tests passed** and syntax compilation passed. No live Discord messages
or CSFloat requests were sent during validation.

## Automatic continuation

Mocked clock tests cover the batch delay, persisted startup cooldown, budget and
rarity preservation, no-progress stop, offline/manual mode, non-retryable errors
and the session batch limit. No real sleeps or API calls are used by these tests.

## Chance-of-profit strategy

Added an upside strategy at the user's request, with strict positive-EV mode
retained. Regression tests cover negative-EV discovery, mocked live quantities
and all-output valuation, correct negative-EV Discord labeling, strict-mode
rejection, no profitable outcomes, jackpot chance thresholds, ranking and resume
strategy compatibility. No YouTube strategy was inferred: the supplied video
could not be retrieved. No live marketplace requests were made for this change.
All **55 tests passed**, and Python syntax compilation passed.

## Persistent verification queue

Added checkpoint round-trip/completion, interrupted-candidate resume, skipped
completed candidates, mismatched economics and missing-queue tests. Resume uses
the existing client cache TTL and cooldown checks, not stored verification results.

## Price/float discovery mechanism update

All **47 tests pass** after adding multi-float single-skin discovery, bounded
mixed search, cost-band live allocation and near-miss discovery tolerance.
New regressions cover low-float profitability hidden by midpoint assumptions,
output-wear boundaries, reserving a cheap contract alongside high-dollar
candidates, deduplicating equivalent queries and separate discovery thresholds.
Existing mocked tests still require strict final profit, full output valuation,
distinct quantities, budget compliance, eligibility and a global request cap.
No realized sale price was hardcoded into production pricing.

## Shortlist concentration regression fix

The saved run checked 12 candidates with no results. Reproducing its local search
showed all 12 relied on P90 Glacier Mesh; its saved live response contained zero
listings. Changing the one-item filler bypassed the previous diversity grouping.
The shortlist now caps repeated dominant-skin dependencies across fillers/wears,
while retaining room for mixed contracts. All **41 tests pass**; syntax checks
pass. Diagnostics and tests made no marketplace calls and did not overwrite the
user's last-run report.

The supplied Facility Negative screenshot uses $1.90 cost and $2.29 EV: after the
configured 13% fee that is $0.0923 expected profit, below the $0.10 threshold.
The local snapshot also has different output prices. Neither screenshot nor
snapshot establishes availability of ten actual low-float listings on CSFloat.

## Limited-edition eligibility regression fix

The reported Solitude -> Aphrodite alerts were invalid. `Limited Edition Item`
was incorrectly interpreted as an upgradeable collection. Central exclusions now
check its collection ID/name and known item names, with additional math,
pre-network verification and Discord checks. All **38 tests pass**, including
eight new eligibility regressions for single/mixed inputs, invalid outputs,
future items in the category, saved results and preserving normal Armory items.
Syntax compilation passed. No live CSFloat requests were used for this fix.

Validation performed locally on 2026-09-17 using Python 3.12 and the existing
requirements installed in `.venv`.

- Unit and mocked integration suite: **30 tests passed** with
  `python -m unittest discover -s tests -v`.
  Covers normalized/capped floats, unchanged full-range mapping, mixed collection
  odds, wear boundaries, phase deduplication, missing outcomes/prices, positive EV
  with low probability of profit, budget/quantity/exact-float rejection, cost/float
  optimization, fresh/expired persistent caches, bulk snapshots, counted retries,
  request #31 prevention, numeric/date Retry-After, repeated 429s, restart cooldown,
  transport failure accounting and Discord rejection of unverified/stale/losses.
- Syntax: `python -m compileall -q main.py config.py src tests`.
- Offline actual-cache run: 2,126 database records, 94 collections, 44 usable
  estimates, 4,427 contracts evaluated, two estimated candidates, zero CSFloat
  requests, zero Discord messages. These are **not verified opportunities**.
- Synthetic performance experiment: full database plus 6,801 fabricated wear
  prices; 224,611 local evaluations in 7.0 seconds; 40 shortlisted. Network calls
  were patched to fail. Synthetic prices were not saved as discovery market data.
- Docker build attempted: blocked because the `docker` executable is unavailable;
  the standard Windows Docker executable path is also absent. Docker build and
  container runtime checks remain required on a Docker-equipped host.
- No live CSFloat requests or Discord posts were made during development. Live
  response compatibility, achievable sale proceeds, and near-boundary in-game
  float rounding still require controlled real-market/game validation.

Recommended deployment check:

```sh
docker compose build
docker compose run --rm tradeup-bot python -m unittest discover -s tests -v
docker compose run --rm tradeup-bot python main.py 20 --offline --no-discord
```

For an explicitly controlled real API smoke test, set
`MAX_CSFLOAT_REQUESTS_PER_RUN=1` and use `--no-discord`. One request usually cannot
fully verify a contract; the expected outcome can be request-budget exhaustion.
Respect any persisted cooldown. Increase the cap only for an intentional scan.
