# CS2 Trade-Up Bot

Discover CS2 trade-up candidates within a USD budget, verify actual CSFloat
listings, and receive ranked Discord reports with purchase links and individual
floats. Runs locally with Python or Docker. No purchases or contracts are executed.

An **AI-assisted (vibe-coded) computer science student project**: a practical
exploration of API integration, search, probability and reliable automation.
AI assisted development; the running bot uses explicit algorithms and calculations.

**Default behavior:** searches for a chance of profit, including negative expected
value contracts. A profitable possible outcome does not mean a profitable average
return. Output valuations use listing asks, not guaranteed sale proceeds.

## Contents

- [Features](#features)
- [Quick start with Docker](#quick-start-with-docker)
- [Run without Docker](#run-without-docker)
- [Commands](#commands)
- [Configuration](#configuration)
- [Discord reports](#discord-reports)
- [How it works](#how-it-works)
- [Concepts demonstrated](#concepts-demonstrated)
- [Troubleshooting](#troubleshooting)
- [Development and publishing](#development-and-publishing)

## Features

- Budget-based search across normal ten-item rarity progressions and wear grades.
- Single-input-type and two-input-type mixed contracts across collections.
- Live verification of ten distinct input listings and all possible outputs.
- Individual listing links, prices and decimal floats in Discord cards.
- Fee-adjusted expected profit, profit probability and best/worst outcomes.
- Persistent price caches, request limits, cooldowns and automatic queue resume.
- Local unit tests with mocked marketplace and Discord requests.

## Quick start with Docker

Install Docker with Compose (Docker Desktop on Windows/macOS), and have a CSFloat
API key ready. A Discord webhook is optional. Download this repository as a ZIP
and extract it, or clone your fork, then open a terminal in the project folder.

### 1. Create your private configuration

PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

macOS/Linux:

```sh
cp .env.example .env
# Open .env in your text editor.
```

Fill in these fields in `.env`:

```dotenv
CSFLOAT_API_KEY=your_csfloat_api_key
DISCORD_WEBHOOK_URL=
```

Use your CSFloat account's API/developer settings to obtain a key. For Discord,
create a webhook for your chosen server channel and paste its URL into
`DISCORD_WEBHOOK_URL`. Leave it blank to disable delivery. Keep `.env` private;
only the blank `.env.example` belongs in GitHub.

### 2. Build and choose your budget

```sh
docker compose build
docker compose run --rm tradeup-bot python main.py --fresh
```

Enter a maximum total input cost such as `20`. All prices and budgets are USD.
Alternatively, specify the budget directly:

```sh
docker compose run --rm tradeup-bot python main.py 20 --fresh
```

The first online run downloads metadata and discovery prices. Verification may
continue across several batches. Leave the terminal running for automatic resume.
Reports go to Discord if configured; detailed run results are saved under `data/`.

## Run without Docker

Use **Python 3.12**. Create a virtual environment and install dependencies:

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env before running.
.\.venv\Scripts\python.exe main.py 20 --fresh
```

macOS/Linux:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env before running.
.venv/bin/python main.py 20 --fresh
```

For the shorter `python` commands below, activate your virtual environment or
substitute its Python executable as shown above.

## Commands

Start a new search and enter a budget:

```sh
docker compose run --rm tradeup-bot python main.py --fresh
```

Resume the saved queue with its original budget:

```sh
docker compose run --rm tradeup-bot python main.py --resume
```

Search with a $10 budget without Discord delivery:

```sh
docker compose run --rm tradeup-bot python main.py 10 --no-discord
```

Restrict inputs to one rarity:

```sh
docker compose run --rm tradeup-bot python main.py 20 --rarity Restricted --fresh
```

Run discovery using existing local data only:

```sh
docker compose run --rm tradeup-bot python main.py 20 --offline
```

Offline mode needs previously downloaded metadata and discovery prices. It makes
no network calls and does not produce live-verified results.

After a source update, run `docker compose build` again. Ctrl+C stops the process;
use `--resume` to continue unfinished candidates. `--fresh` replaces the previous
queue when new live verification begins. Changed strategy/fee settings require a
fresh search. A matching normal run can also resume automatically.

For unattended use, set `BUDGET_OVERRIDE=20` in `.env`, then use
`docker compose up`. Use `compose run` for interactive budget input. The bot exits
when its queue finishes; it is not an endless market-monitoring service.

## Configuration

All settings and defaults are in [.env.example](.env.example).

### Search and economics

- `SEARCH_MODE=upside`: allows negative EV if profitable outcomes meet the limits.
- `MIN_WIN_CHANCE_PERCENT=20`: minimum chance of any net-profitable outcome.
- `MIN_WIN_PROFIT_DOLLARS=0.10`: minimum best-case net gain in upside mode.
- `SEARCH_MODE=expected_value`: instead requires positive expected profit.
- `MIN_PROFIT_DOLLARS=0.10` and `MIN_ROI_PERCENT=1`: expected-value mode thresholds.
- `SELL_FEE_PERCENT=13`: assumed sale fee; set this for your sale venue. It is not
  a claim about CSFloat's current fee.
- `MAX_RESULTS_TO_SHOW=5`: maximum ranked results reported per batch.

For example, a $6 contract with equally likely $8 and $2 outcomes has a 50% chance
of profit at a 13% fee. Its best net profit is $0.96, but its expected profit is
**-$1.65**. The bot distinguishes those metrics.

### Requests and automatic continuation

- `MAX_CSFLOAT_REQUESTS_PER_RUN=30`: actual API attempts per batch, including retries.
- `CSFLOAT_REQUEST_DELAY=3`: request pacing in seconds.
- `LIVE_TTL=120`: how long live quotes remain usable, in seconds.
- `AUTO_RESUME=1`: automatically continue unfinished work while the process runs.
- `AUTO_RESUME_DELAY_SECONDS=300`: wait between batches; longer API cooldowns win.
- `AUTO_MAX_BATCHES=10`: session limit, allowing up to 300 attempts at defaults.

Automatic continuation stops on completion, errors, its batch limit or three
batches without queue progress. The delay is a local policy, not an assertion
about CSFloat quota reset timing. Resume rechecks expired prices.

### Data storage

Compose mounts `./data` into `/app/data`. This preserves metadata, prices,
cooldowns, the verification queue and `last_run.json` across container runs.
Runtime data is excluded from Git and release archives. Run only one bot process
against a given data directory. Keep `DATA_DIR=data` for the supplied Compose mount.

## Discord reports

Reports are grouped into ranked cards and paginated to respect Discord limits.
Each contract includes:

- Actual total input cost and budget.
- Profit probability, expected return and best/worst net profit.
- All ten input listing links, individual prices and full supplied float precision.
- Predicted output floats, probabilities and output valuations.
- An explicit negative-EV label when applicable.
- A text attachment with the full report.

Routine continuation countdowns stay in the console; results and actionable stop
notices appear in Discord. Separate contracts may share listings: treat them as
alternatives, not a combined shopping list.

## How it works

1. Load weapon metadata and bulk/historical discovery prices.
2. Generate and rank candidate contracts locally without CSFloat search requests.
3. Select a diverse shortlist and fetch actual CSFloat buy-now listings.
4. Compare bounded combinations of input costs and floats.
5. Recalculate output wears, probabilities, fees and economics using fresh quotes.
6. Send qualifying results and checkpoint unfinished candidates.

The project uses Python, REST APIs, JSON persistence, caching, bounded search,
probability calculations and Discord webhooks. **It does not use an AI model,
machine learning, a vector database or RAG.** Docker provides a reproducible
runtime; GitHub Actions runs automated tests and Docker build checks.

See [architecture and detailed limitations](docs/ARCHITECTURE.md) for the search,
normalization formula, eligibility checks and API behavior.

### Limitations

The search is heuristic, not exhaustive. It currently considers one or two input
types, the first 50 listings per market-name query, and bounded float selections.
It excludes StatTrak, Souvenir, limited-edition store items and knife/glove
contracts. Estimated prices may miss low-float premiums. Live asks may disappear
or fail to represent achievable sale prices. No profit is guaranteed.

## Concepts demonstrated

- **Modular Python:** separate data access, search, calculation and reporting.
- **Data structures:** dataclasses, dictionaries, sets, lists and candidate queues.
- **Algorithms:** combinatorial search, heuristic ranking and bounded dynamic
  programming for cost/float tradeoffs.
- **Probability:** outcome distributions, expected value, ROI and sale fees.
- **Backend integration:** REST requests, authentication, JSON and Discord webhooks.
- **Reliability:** cache expiration, rate limits, retries, cooldowns and checkpoints.
- **Developer tooling:** environment variables, Docker/Compose, unit tests,
  API mocking and GitHub Actions continuous integration.

Read the [CS learning guide](docs/LEARNING.md) for explanations linked to actual
source files, a suggested code-reading order, and portfolio wording. This is an
AI-assisted development project; it does not implement RAG, ML or an AI agent.

## Troubleshooting

**Local candidates found, none survived verification:** estimates may differ from
live prices, quantities or floats; output quotes can be missing or stale. Check
console rejection reasons. This message does not prove all possible contracts
are unprofitable.

**API budget exhausted:** leave automatic continuation running, or use `--resume`
after the saved wait. If the session limit has been reached, another resume starts
a new session while respecting persisted cooldowns.

**No unfinished saved queue:** use `--fresh` to start a new search.

**Missing API key:** edit `.env` in the project folder. Never paste it into an issue.

**No Discord message:** check the webhook locally and console status. Results must
pass verification and remain fresh; routine empty continuation batches stay quiet.

**No offline data:** run online first; a clean checkout has no bundled market cache.

**Budget prompt not shown:** use `docker compose run`, or supply the budget as an
argument. A configured `BUDGET_OVERRIDE` also suppresses the prompt.

## Development and publishing

Run the unit suite (no live API credentials required):

```sh
python -m unittest discover -s tests -v
python -m compileall -q main.py config.py src tests scripts
```

- [Push this project to GitHub](docs/PUBLISHING.md): first push and future updates.
- [Contributing](CONTRIBUTING.md): development and bug-report guidance.
- [Validation history](VALIDATION.md): implementation checks and their limits.

Create a clean source archive with `python scripts/package_release.py`.
GitHub Actions checks Python 3.12 on Windows/Linux and builds the Docker image.
The workflow needs no marketplace or Discord secrets.

## Data sources and license

Metadata comes from [ByMykel/CSGO-API](https://github.com/ByMykel/CSGO-API), discovery
estimates from [Skinport](https://docs.skinport.com/items), and live listings from
[CSFloat](https://docs.csfloat.com/). Respect each provider's access conditions.
This project is not affiliated with Valve, CSFloat, Skinport or Discord.

Code is distributed under the [MIT license](LICENSE). External data and trademarks
remain subject to their respective owners' terms.
