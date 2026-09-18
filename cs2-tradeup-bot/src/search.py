"""Bounded local search. No transport or API client is accessible here."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
import math
import time
from src.rules import WEAR_RANGES, wear_for_float, normalize
from src.skin_data import next_rarity
from src.tradeup_calc import InputItem, enumerate_outcomes, expected_value
from src.strategy import best_profit, qualifies


@dataclass(frozen=True)
class Block:
    name: str
    collection: str
    rarity: str
    wear: str
    price: float
    float_value: float
    min_float: float
    max_float: float
    timestamp: float
    source: str


@dataclass
class Candidate:
    parts: list  # (Block, count)
    cost: float
    gross: float
    profit: float
    roi: float
    chance_profit: float
    score: float


def metrics(outcomes, cost, fee):
    gross = expected_value(outcomes)
    net = gross * (1-fee/100)
    profit = net-cost
    chance = sum(o.probability for o in outcomes if o.price*(1-fee/100) > cost)
    downside = sum(o.probability * max(0, cost-o.price*(1-fee/100)) for o in outcomes)
    return gross, net, profit, profit/cost*100, chance, downside


def score(profit, roi, downside, settings, chance=0, best=0, cost=1):
    if settings.SEARCH_MODE == "upside":
        # Chance is primary; expected return and downside penalize lottery-like
        # contracts. Best-case return is capped so a jackpot cannot dominate.
        return 2*chance + profit/cost - settings.SCORE_RISK_WEIGHT*downside/cost + .1*min(max(best/cost,0),1)
    return profit + settings.SCORE_ROI_WEIGHT * min(roi, 100) - settings.SCORE_RISK_WEIGHT*downside


def priced_outcomes(inputs, grouped, prices):
    outcomes = enumerate_outcomes(inputs, grouped)
    for output in outcomes:
        quote = prices.get(output.skin_name, output.wear)
        if quote is None:
            raise ValueError("Missing output price")
        output.price = quote.price
    return outcomes


def float_scenarios(skin, outputs, lo, hi, observed, limit):
    """Probe achievable output-wear transitions without claiming listing depth."""
    middle = (lo + hi) / 2
    # Avoid assuming that ten listings exist exactly at a skin's minimum float.
    values = [observed, middle, lo + (hi-lo)*.05]
    transitions = []
    for output in outputs:
        for _, boundary, _ in WEAR_RANGES[1:]:
            normalized = (boundary-output["min_float"]) / (output["max_float"]-output["min_float"])
            raw = skin["min_float"] + normalized*(skin["max_float"]-skin["min_float"])
            # Stay just below the wear boundary despite floating-point rounding.
            target = raw - 1e-8
            if lo <= target < hi:
                transitions.append(target)
    values += sorted(set(transitions))
    chosen = []
    for value in values:
        if value is not None and lo <= value < hi and value not in chosen:
            chosen.append(value)
    return chosen[:limit]


def generate(grouped, prices, budget, settings, tiers=None):
    stats = Counter()
    pools = defaultdict(list)
    # Retain alternatives across wears, prices and normalized floats in every collection.
    for collection, by_rarity in grouped.items():
        for rarity in tiers or settings.RARITY_TIERS:
            if not by_rarity.get(next_rarity(rarity)):
                continue
            blocks = []
            for skin in by_rarity.get(rarity, []):
                for wear, low, high in WEAR_RANGES:
                    lo, hi = max(low, skin["min_float"]), min(high, skin["max_float"])
                    if lo >= hi:
                        continue
                    quote = prices.get(skin["name"], wear)
                    if quote is None:
                        stats["missing_input_prices"] += 1
                        continue
                    for value in float_scenarios(skin, by_rarity[next_rarity(rarity)],
                                                 lo, hi, quote.float_value, settings.FLOAT_SCENARIOS):
                        blocks.append(Block(skin["name"], collection, rarity, wear, quote.price,
                            value, lo, hi, quote.timestamp, quote.source))
            # Singles are cheap: evaluate every priced skin/wear/float scenario.
            # Restrict only the combinatorial pair pool, after scoring singles.
            pools[rarity].extend(blocks)

    finalists = []
    output_cache = {}

    def evaluate(parts):
        stats["evaluated"] += 1
        cost = math.fsum(b.price*n for b, n in parts)
        if cost > budget:
            stats["rejected_budget"] += 1
            return None
        inputs = [InputItem(b.name, b.collection, b.float_value, b.price) for b, n in parts for _ in range(n)]
        try:
            # Reuse equivalent collection/float output distributions locally.
            key = tuple((b.collection, b.name, b.float_value, n) for b, n in parts)
            outcomes = output_cache.get(key)
            if outcomes is None:
                outcomes = priced_outcomes(inputs, grouped, prices)
                if len(output_cache) < 10000:
                    output_cache[key] = outcomes
            gross, net, profit, roi, chance, downside = metrics(outcomes, cost, settings.SELL_FEE_PERCENT)
        except ValueError:
            stats["rejected_missing_or_invalid"] += 1
            return None
        best = best_profit(outcomes, cost, settings.SELL_FEE_PERCENT)
        rank = score(profit, roi, downside, settings, chance, best, cost)
        # Older and cross-market estimates rank lower, with no invented liquidity claim.
        confidence = min(1/(1+max(0, time.time()-b.timestamp)/86400) *
                         (1 if b.source.startswith("csfloat") else .75) for b, _ in parts)
        rank *= confidence if rank > 0 else 1
        candidate = Candidate(parts, cost, gross, profit, roi, chance, rank)
        possible_cost = cost * (1-settings.DISCOVERY_PRICE_TOLERANCE)
        possible_profit = net - possible_cost
        accepted = qualifies(profit, roi, chance, best, settings)
        if settings.SEARCH_MODE == "expected_value":
            accepted = qualifies(possible_profit, possible_profit/possible_cost*100, chance, best, settings)
        if accepted:
            if profit < settings.MIN_PROFIT_DOLLARS or roi < settings.MIN_ROI_PERCENT:
                stats["near_misses_retained"] += 1
            stats["preliminary"] += 1
            finalists.append(candidate)
            if len(finalists) > settings.LOCAL_SHORTLIST*10:
                finalists[:] = balanced_shortlist(finalists, settings.LOCAL_SHORTLIST*3)
        else:
            stats["rejected_profit"] += 1
        return candidate

    for rarity, blocks in pools.items():
        # All retained single blocks are evaluated; a diverse, bounded pool supplies pairs.
        single_scores = {}
        for block in blocks:
            candidate = evaluate([(block, 10)])
            single_scores[block] = candidate.score if candidate else -math.inf
        ranked = sorted(blocks, key=lambda b: single_scores[b], reverse=True)
        cheap = sorted(blocks, key=lambda b: b.price)
        pool = []
        collection_count = Counter()
        for a, b in zip(ranked, cheap):
            for block in (a, b):
                if block not in pool and collection_count[block.collection] < settings.BLOCKS_PER_COLLECTION:
                    pool.append(block)
                    collection_count[block.collection] += 1
            if len(pool) >= settings.PAIR_POOL_SIZE:
                break
        for a, b in combinations(pool[:settings.PAIR_POOL_SIZE], 2):
            if (a.name, a.collection, a.wear) == (b.name, b.collection, b.wear):
                continue  # the live optimizer already explores this query's floats
            for count in range(1, 10):
                evaluate([(a, count), (b, 10-count)])
    return balanced_shortlist(finalists, settings.LOCAL_SHORTLIST), stats


def balanced_shortlist(candidates, limit):
    """Reserve opportunities across dollar-cost bands, then apply dependency caps.

    Cheap contracts get early verification slots even with a large user budget.
    Within each band prefer estimated profitable candidates over near misses.
    """
    bands = defaultdict(list)
    seen = set()
    for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
        # The verifier optimizes exact floats itself: identical quantities and
        # market queries need only one live slot, however many local scenarios.
        identity = tuple(sorted((b.name, b.collection, b.wear, n) for b,n in candidate.parts))
        if identity in seen:
            continue
        seen.add(identity)
        band = next((i for i, ceiling in enumerate((5, 20, 100)) if candidate.cost <= ceiling), 3)
        bands[band].append(candidate)
    # Select diverse queues before interleaving so one input cannot fill a band.
    queues = []
    for i in sorted(bands):
        singles = [c for c in bands[i] if len(c.parts) == 1]
        mixes = [c for c in bands[i] if len(c.parts) > 1]
        combined = []
        for index in range(max(len(singles), len(mixes))):
            combined.extend(q[index] for q in (singles, mixes) if index < len(q))
        queues.append(diverse(combined, limit, presorted=True))
    ordered = []
    for index in range(max((len(q) for q in queues), default=0)):
        ordered.extend(q[index] for q in queues if index < len(q))
    return diverse(ordered, limit, presorted=True)


def diverse(candidates, limit, presorted=False):
    selected, groups, dominant_counts, single_counts = [], Counter(), Counter(), Counter()
    for candidate in (candidates if presorted else sorted(candidates, key=lambda c: c.score, reverse=True)):
        # At most two compositions for the same input query set and output collections.
        key = tuple(sorted((b.name, b.collection, b.wear) for b, _ in candidate.parts))
        pool_key = tuple(sorted(set((b.collection, b.rarity) for b, _ in candidate.parts)))
        # Changing a one-item filler must not let the same nine-item dependency
        # monopolize verification. Aggregate wears of the same skin as well.
        input_counts = Counter()
        for block, count in candidate.parts:
            input_counts[(block.name, block.collection, block.rarity)] += count
        dominant = [identity for identity, count in input_counts.items() if count >= 5]
        single = next(iter(input_counts)) if len(input_counts) == 1 else None
        if (groups[key] >= 2 or groups[("pool", pool_key)] >= 4
                or any(dominant_counts[identity] >= 4 for identity in dominant)
                or (single is not None and single_counts[single] >= 2)):
            continue
        groups[key] += 1
        groups[("pool", pool_key)] += 1
        dominant_counts.update(dominant)
        if single is not None:
            single_counts[single] += 1
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected
