# CS learning guide

This is an AI-assisted, vibe-coded computer science student project. AI tools
helped with implementation and iteration. The application itself uses conventional
Python code and mathematical rules; no model is trained or called at runtime.

This guide identifies concepts implemented in the repository. It is not a claim
that the author has independently mastered every topic, or that passing tests
proves the bot is profitable.

## Programming and software design

**Modularity and separation of concerns.** [main.py](../main.py) coordinates the
pipeline; marketplace access, calculations, search and Discord formatting live
in separate modules. This makes individual behavior easier to test and replace.

**Data modeling.** Dataclasses such as input items, outcomes, listings and
candidates give structured names to related values. Dictionaries index prices
and collections; sets prevent duplicate listing IDs; lists store candidates.
See [tradeup_calc.py](../src/tradeup_calc.py) and
[search.py](../src/search.py).

**Abstraction and dependency injection.** Discovery defines a price-provider
interface. Tests substitute fake transports and clocks, so calculations and
request limits can be checked without spending API requests or waiting in real
time. See [discovery.py](../src/discovery.py) and
[test_pipeline.py](../tests/test_pipeline.py).

**Input validation and exceptions.** Budgets, float ranges, eligibility and
complete output prices are checked before a result is accepted. Expected stop
conditions such as request exhaustion are represented explicitly.

## Algorithms and mathematics

**Combinatorial search.** The number of possible contracts grows rapidly as more
skins and listings become available. [search.py](../src/search.py) generates
single-type and two-type candidates, evaluates different quantity splits and
keeps a limited shortlist. It does not enumerate every possible ten-item mix.

**Heuristics and ranking.** Rules balance estimated return, profit probability,
downside and shortlist diversity. These hand-written scores are not learned by
an AI model. Qualification is separate from ranking; see
[strategy.py](../src/strategy.py).

**Bounded dynamic programming.** In [verifier.py](../src/verifier.py), partial
selections are grouped by item count. Adding a listing extends earlier states;
the algorithm prunes states while retaining low-cost and low-float alternatives.
Pruning keeps work manageable but sacrifices a guarantee of the global optimum.

**Normalization and floating-point arithmetic.** Input floats are mapped into a
common range before calculating output floats. Wear boundaries matter: a small
float change can move an outcome into a different price category. See
[rules.py](../src/rules.py) and [tradeup_calc.py](../src/tradeup_calc.py).

**Probability and expected value.** The calculator constructs outcome odds, then
weights prices by probability. Expected profit subtracts purchase cost and sale
fees. Chance of profit sums probabilities of profitable outcomes; it is different
from average expected profit. ROI expresses expected profit relative to cost.

## APIs and reliable automation

**REST APIs and HTTP.** The bot makes authenticated CSFloat requests and reads
JSON responses. [csfloat_client.py](../src/csfloat_client.py) centralizes that
transport so every attempt, including retries, counts toward the cap.

**Caching and TTL.** Cached data reduces repeated requests. A time-to-live (TTL)
defines how long data is considered fresh. Discovery estimates and live prices
have different freshness requirements.

**Rate limiting and backoff.** Request pacing, HTTP 429 handling, Retry-After,
jitter and persisted cooldowns prevent immediate repeated retries.

**Persistence and crash recovery.** [storage.py](../src/storage.py) writes JSON
using temporary files and replacement. [checkpoint.py](../src/checkpoint.py)
saves unfinished candidates, and [auto_resume.py](../src/auto_resume.py) controls
continuation. This is file-based state, not a SQL database or a distributed queue.
Resume does not guarantee exactly-once Discord delivery around a process crash.

**Webhooks and presentation limits.** [discord_webhook.py](../src/discord_webhook.py)
sends outbound HTTP reports. It groups inputs, formats floats, paginates embeds
and attaches full reports while respecting message limits.

## Testing and developer tooling

**Unit and regression testing.** Python's `unittest` checks calculations,
eligibility, request accounting, resume behavior and message formatting.
Regression cases preserve fixes for previously observed mistakes.

**Mocking.** Fake marketplace responses and clocks make tests repeatable without
live credentials. They establish behavior for the tested cases, not actual
market liquidity or provider availability.

**Environment configuration.** [config.py](../config.py) reads settings from
environment variables and `.env`. Credentials stay separate from source code.

**Containerization.** [Dockerfile](../Dockerfile) packages Python and dependencies;
[docker-compose.yml](../docker-compose.yml) supplies configuration and a volume
for persistent data. A container is a runtime environment, not an AI component.

**Version control and CI.** Git tracks revisions after repository initialization.
The [GitHub Actions workflow](../.github/workflows/tests.yml) runs tests on
Windows/Linux and checks a Docker build after pushes and pull requests. This is
continuous integration; there is no automatic production deployment configured.

## What this project does not implement

- RAG, embeddings, vector search or LLM inference.
- Machine learning, model training or reinforcement learning.
- An autonomous AI agent making trading decisions.
- Microservices, Kubernetes or a distributed task system.
- Automated purchases, sales or in-game trade-up execution.

Retrieving market prices alone is not RAG. Retrieval-augmented generation would
retrieve context for a generative model to produce an answer. Here, fetched
prices are inputs to explicit calculations.

## Suggested reading order

1. Follow a run through `main.py`.
2. Inspect `rules.py` and `tradeup_calc.py`; calculate a simple outcome by hand.
3. Read `strategy.py` to distinguish eligibility from ranking preferences.
4. Trace candidate generation in `search.py` and selection in `verifier.py`.
5. Study `csfloat_client.py`, `checkpoint.py` and `auto_resume.py` for failure handling.
6. Read the tests alongside `discord_webhook.py` to understand report guarantees.

To deepen understanding, explain why cheap inputs may need low floats, why a
winning outcome can coexist with negative EV, and why expired listings must be
checked again after resume. Make a small change and add a regression test.

## Portfolio description

> Built an AI-assisted Python project that discovers CS2 trade-up candidates,
> verifies marketplace listings through REST APIs, and sends structured Discord
> reports. The project applies probability calculations, heuristic search,
> bounded dynamic programming, caching, rate limiting and resumable processing,
> with Docker packaging and automated tests.

Use only claims you can demonstrate and explain. There are no measured profit,
accuracy or performance claims in this description. For coursework, follow your
institution's AI-assistance disclosure requirements.
