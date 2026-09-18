# CS2 trade-up discovery bot

Budget-only discovery runs locally, then a capped CSFloat client verifies the
shortlist. All five normal ten-item rarity progressions are searched. No purchases
or trade-ups are executed.

## Discord reports

Results are grouped into a ranked embed digest per verification batch, paginated
only when Discord's 6,000 combined embed characters or 10-embed limit requires it.
Cards show cost, budget, chance of profit, best/worst net profit, expected profit,
ROI, input quantities and outputs. Negative EV is explicitly highlighted.
Every selected input is displayed directly in the card with a clickable Buy link,
price and decimal float preserving the supplied precision. Inputs are grouped by
skin and wear; long groups split into fields without losing listings. Displayed
outputs include predicted floats. Buy links are masked links inside embeds, so
channel content does not generate repeated automatic marketplace previews.
A text attachment also retains all inputs and the complete output distribution.

Routine automatic-batch exhaustion and countdowns are console-only. Result
digests include queue status; final completion and actionable stop notices still
go to Discord. Existing chance-of-profit thresholds remain unchanged.

## Search objective

The default `SEARCH_MODE=upside` searches for **a chance of net profit**, including
contracts whose expected profit is negative. Defaults require at least a 20%
chance of any profitable outcome (`MIN_WIN_CHANCE_PERCENT`) and a best possible
net profit of $0.10 (`MIN_WIN_PROFIT_DOLLARS`). These are configurable heuristics,
not a guarantee of finding the globally best contract.

Ranking uses twice the profit probability plus expected profit/cost, subtracts
`SCORE_RISK_WEIGHT` times expected downside/cost, and adds a capped best-case
return contribution (at most 0.1). This prioritizes win probability while
penalizing losses and limiting the influence of rare jackpots. Live-checked
results are ranked using actual listings before sending the top configured
number. Expired results are withheld. Discord shows best/worst net profit,
profit probability, per-outcome net profit and expected profit, and explicitly
labels negative expected value.

For example, paying $6 for a 50/50 chance of an $8 or $2 output qualifies in
upside mode: at a 13% fee the winning outcome earns $0.96, but expected profit is
**-$1.65**. Those are different metrics. Actual proceeds remain uncertain.

`SEARCH_MODE=expected_value` restores strict positive-EV filtering with
`MIN_PROFIT_DOLLARS` and `MIN_ROI_PERCENT`. Strategy changes invalidate old resume
queues; use `--fresh`. Budget, eligibility, fresh full-output pricing, distinct
input quantities and the global API cap apply in both modes.

## Run

Copy `.env.example` to `.env`, add your CSFloat key and optional Discord webhook:

```sh
docker compose build
docker compose run --rm tradeup-bot
```

Enter a dollar amount such as `20` or `$20`. For unattended `docker compose up`,
set `BUDGET_OVERRIDE=20` in `.env`. Compose `up` does not reliably forward keyboard
input; `compose run` is the interactive command. An explicit budget also works:

```sh
docker compose run --rm tradeup-bot python main.py 20
python main.py 20 --offline --no-discord
python -m unittest discover -s tests -v
```

`--offline` makes **no network requests**, including skin database refresh,
Skinport, CSFloat and Discord. It requires `data/skins.json`. `--rarity Restricted`
is an optional advanced filter. No rarity/wear selection is normally required.

### Continue after the request cap

Automatic continuation is enabled by default (`AUTO_RESUME=1`). Leave the process
running: it waits `AUTO_RESUME_DELAY_SECONDS=300` seconds between batches, or until
a longer persisted CSFloat cooldown ends, then resumes the unfinished queue.
It stops on completion, non-rate-limit errors, three batches with no queue
progress, or `AUTO_MAX_BATCHES=10`. Each batch keeps the same 30-request cap;
the default automatic session can therefore make **up to 300 requests**, spaced
across batches. This delay is a local policy, not a documented CSFloat quota reset.
Ctrl+C stops the process with the queue saved. Set `AUTO_RESUME=0` for manual mode.
The continuation wait is also persisted in `data/auto_resume.json`.

```sh
docker compose run --rm tradeup-bot python main.py --resume
```

The queue persists in `data/verification_queue.json` on the mounted volume.
`--resume` restores its budget and rarity, skips completed candidates and retries
the interrupted candidate. Normal scans with matching budget/rarity/fee/profit
settings also resume automatically. `--fresh` starts a new search instead.
Each invocation has its own request cap; persisted CSFloat cooldowns still apply.
Fresh cached listings can be reused; expired quotes must be fetched again, so
resume is at candidate level, not an unconditional continuation of old prices.
If one candidate alone requires more requests than the per-run cap with expired
cache, resuming may hit the same cap again; the no-progress limit stops this loop.
Completed alerts are skipped during normal resume; a process crash between a
Discord send and the checkpoint write can still cause a duplicate alert.
Queues created before this feature cannot be recovered from `last_run.json`.

## Pipeline and storage

1. Load ByMykel skin data, refreshed weekly. Group valid normal weapon records by
   collection and rarity. Duplicate pattern-phase records share one weapon outcome.
   The `Limited Edition Item` store category is excluded from inputs and outputs;
   a database collection label alone does not establish trade-up eligibility.
   Normal Armory collections remain eligible. The calculator, live verifier and
   Discord formatter also reject limited items, including previously built candidates.
2. Before scanning, load historical CSFloat estimates and a Skinport bulk USD
   snapshot (one public request at most once per day by default). The original
   `csfloat_price_cache.json` is read without modification. Null/expired prices
   are unavailable, not zero. Disable bulk refresh with `USE_SKINPORT_SNAPSHOT=0`.
3. Search locally across applicable wears. Evaluate every priced skin/wear as a
   single-skin contract, with up to `FLOAT_SCENARIOS=5` floats: observed float,
   midpoint, low end and output-wear transitions. These are hypotheses at the
   snapshot price, not assertions that low-float copies cost the same. Restrict
   the pair pool after scoring singles; evaluate 1:9 through 9:1 mixes within and
   across collections. Search work never triggers network requests.
4. Keep 40 estimated candidates, group similar inputs/output pools, shortlist 12.
   A skin supplying at least five inputs gets at most four shortlist slots across
   all wears/fillers (at most two single-skin variants), so changing one filler
   cannot fill the entire shortlist with the same availability dependency.
   Interleave cost bands ($0–5, $5–20, $20–100, above $100), starting with the
   cheapest band, so smaller contracts receive live slots even on a large budget.
   Each band alternates single-skin and mixed contracts when both are available.
   Identical input queries/quantities across hypothetical floats get one slot.
   `DISCOVERY_PRICE_TOLERANCE=0.15` retains near-misses that could meet thresholds
   with inputs 15% cheaper than the snapshot. It does not change displayed EV or
   final thresholds, and does not invent a discount for verified listings.
   Ranking follows the selected strategy: upside mode balances profit chance,
   expected return and downside; expected-value mode uses dollar profit with
   ROI/downside weights. Estimate confidence also influences local ranking.
   These are heuristics, not exhaustive search.
5. Query normal buy-now listings sorted by price, up to 50 per exact market name.
   Bounded dynamic programming retains cost/float tradeoffs, then locally ranks
   actual selections. Verify at most three distinct resulting wear distributions
   per candidate; every output must have a fresh, plain listing ask.
6. Recompute normalized floats, probabilities, cost, gross/net EV, fees, profit,
   ROI and profit probability. Report contracts meeting the selected strategy
   with ten distinct listings and fresh input/output data.

The `./data:/app/data` volume persists `skinport_snapshot.json`,
`discovery_prices.json`, `live_listings.json`, `csfloat_cooldown.json`, skin data
and `last_run.json`. Writes to pricing/state files are atomic. Run only one bot
process against this directory at a time. The global request cap is per process,
not a shared allowance across simultaneous processes.

## Request behavior

Discovery uses **zero CSFloat requests**. All live input/output requests and
retries pass through `CSFloatClient`; cache hits do not count. Default hard cap:
30 actual attempts per run. Typical candidate verification needs one request per
distinct input market name plus one per output market name/wear, less cache reuse.
Roughly 10–30 requests can verify several simple candidates; 12 candidates with
large output pools may not fit. Reaching the cap stops with an explicit status.

Live query results expire after 120 seconds, including within a single run.
Results are ranked after verification; stale results are rejected. No automatic pagination
is performed: insufficient quantity in the first 50 listings rejects a candidate.
No undocumented endpoints, quota assumptions, parallel requests or bypasses.
HTTP 429 supports numeric/date Retry-After, increasing pacing, jitter and one
retry. Large/repeated waits are persisted and stop the run. Startup checks the
cooldown before making CSFloat requests. Automatic redirects are disabled so
hidden follow-up requests cannot bypass the counter.

## Economics and limits

The existing **13% fee assumption is preserved**, not presented as CSFloat's fee.
Set it for your intended sale venue. In `expected_value` mode defaults require
at least $0.10 expected profit and 1% ROI. `upside` mode instead uses the chance
and potential-profit thresholds described above; negative EV is explicitly allowed.
Prices are USD; purchase totals are summed from integer-cent listing prices.

Output prices are **asking prices, not executable bids or completed sales**.
Verified means observed listings and calculated floats, not guaranteed delivery,
sale proceeds, liquidity or profit. Listings may vanish. Separate reported
contracts can share listings and should be treated as alternatives. Pattern,
sticker and exceptional-float premiums are not modeled. Pattern phases with one
market name use a common conservative ask rather than speculative phase premiums.

Input float normalization is `(float-min)/(max-min)`, averaged across ten items,
then mapped into each output's float range. Odds are the input collection share
divided by the number of unique next-tier weapon outcomes in that collection.
Near exact wear boundaries, game floating-point behavior needs real-game
validation. Five-Covert knife/glove contracts, StatTrak and Souvenir are outside
this implementation's scope. Three-or-more input types are not searched yet.

Bulk Skinport prices are cross-market estimates without exact float premiums or
depth. Sparse snapshots limit coverage and can produce false positives that live
verification rejects. There is no guarantee that the global optimum is found.

## Sources checked

- [CSFloat API](https://docs.csfloat.com/): `/api/v1/listings`, Authorization key,
  cursor pagination, 50 maximum results, normal category, buy-now and sort filters.
  The public documentation does not specify an account quota or reliable
  Retry-After contract; the client handles standard HTTP headers defensively.
- [Skinport items](https://docs.skinport.com/items): public bulk endpoint, USD,
  required Brotli header, five-minute server cache. Daily refresh is conservative.
- [ByMykel game data](https://github.com/ByMykel/CSGO-API): existing database source.
- [SteamAnalyst calculator](https://www.steamanalyst.com/tradeup-calculator):
  normalized input floats and collection-share odds. Its prose contains a
  questionable update date; this project relies on the described formula, not
  that date. Controlled real-game validation remains desirable.

## Implementation audit

Previously `main.py` fetched inputs while visiting collections, then fetched
outputs inside combination scoring. Verification used uncached scalar prices
outside the scan's request cap, multiplied one listing by quantity and could
accept partially populated inputs after a failed lookup. Floats/output EV were
not recalculated. Discovery was restricted to Battle-Scarred and one building
block, thresholds allowed losses, and ranking used ROI alone. The 15-minute
persistent scalar cache discarded useful history; short repeated 429s did not
persist cooldown and HTTP-date Retry-After crashed parsing. Docker copied `.env`
into the image because there was no `.dockerignore`. There were no tests.

Reused: database source, collection grouping (with phase deduplication), output
float mapping, collection odds, basic data classes and the fee assumption.
Corrected: raw input averaging, contract validation and incomplete price handling.
The old direct CSFloat adapter was removed to ensure a single transport. Optional
Steam/Skinport/DMarket adapters remain available but are not the production scan.

New modules: `rules.py`, `storage.py`, `discovery.py`, `search.py`,
`csfloat_client.py`, `verifier.py`; tests are in `tests/test_pipeline.py`.
