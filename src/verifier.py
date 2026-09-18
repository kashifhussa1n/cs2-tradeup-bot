"""Bounded listing optimization followed by complete fresh output valuation."""
from dataclasses import asdict
from itertools import product
import math
from src.rules import normalize, wear_for_float
from src.search import priced_outcomes, metrics, score
from src.tradeup_calc import InputItem, enumerate_outcomes
from src.strategy import best_profit, qualifies


def trim(states, width):
    # Retain cheapest and lowest-float states, plus tradeoffs across float buckets.
    unique = {tuple(sorted(x.id for x in rows)): (cost, value, rows) for cost, value, rows in states}
    states = list(unique.values())
    if len(states) <= width:
        return states
    cheap = min(states, key=lambda x: x[0])
    low = min(states, key=lambda x: (x[1], x[0]))
    ordered = sorted(states, key=lambda x: x[1])
    buckets = []
    for i in range(width-2):
        segment = ordered[i*len(ordered)//(width-2):(i+1)*len(ordered)//(width-2)]
        if segment:
            buckets.append(min(segment, key=lambda x: x[0]))
    return [cheap, low] + buckets


def selections(listings, count, block, budget, width):
    states = {0: [(0, 0, [])]}
    seen = set()
    for listing in listings:
        if listing.id in seen or not block.min_float <= listing.float_value <= block.max_float:
            continue
        if wear_for_float(listing.float_value) != block.wear:
            continue
        seen.add(listing.id)
        for n in range(count, 0, -1):
            added = [(cost+listing.price, value+listing.float_value, rows+[listing])
                     for cost, value, rows in states.get(n-1, [])
                     if round(cost+listing.price, 2) <= budget]
            states[n] = trim(states.get(n, [])+added, max(3, width))
    return states.get(count, [])


def verify(candidate, grouped, prices, client, budget, settings):
    # Revalidate old/external candidates before spending any marketplace quota.
    try:
        enumerate_outcomes([InputItem(b.name, b.collection, b.float_value, b.price)
                            for b, count in candidate.parts for _ in range(count)], grouped)
    except ValueError as exc:
        return None, f"Invalid contract: {exc}"
    skin_index = {s["name"]: s for tiers in grouped.values() for skins in tiers.values() for s in skins}
    options = []
    for block, count in candidate.parts:
        listings = client.listings(f"{block.name} ({block.wear})")
        choices = selections(listings, count, block, budget, settings.OPTIMIZER_WIDTH)
        if not choices:
            return None, "Insufficient distinct usable input listings"
        options.append(choices)
    combined = []
    for choice in product(*options):
        rows = [row for _, _, selected in choice for row in selected]
        cost = round(math.fsum(row.price for row in rows), 2)
        if cost > budget or len({row.id for row in rows}) != 10:
            continue
        inputs = [InputItem(block.name, block.collection, row.float_value, row.price)
                  for (block, _), (_, _, selected) in zip(candidate.parts, choice) for row in selected]
        try:
            outcomes = priced_outcomes(inputs, grouped, prices)
            gross, net, profit, roi, chance, downside = metrics(outcomes, cost, settings.SELL_FEE_PERCENT)
            combined.append((score(profit, roi, downside, settings, chance,
                                   best_profit(outcomes, cost, settings.SELL_FEE_PERCENT), cost), inputs, rows, cost))
        except ValueError:
            continue
    # Deep local evaluation collapses equivalent output wear distributions.
    seen_distributions, best = set(), None
    for _, inputs, rows, cost in sorted(combined, key=lambda x: x[0], reverse=True):
        outcomes = enumerate_outcomes(inputs, grouped)
        signature = tuple((o.skin_name, o.wear) for o in outcomes)
        if signature in seen_distributions:
            continue
        seen_distributions.add(signature)
        if len(seen_distributions) > 3:
            break
        timestamps = [row.timestamp for row in rows]
        complete = True
        for output in outcomes:
            market = client.listings(f"{output.skin_name} ({output.wear})")
            skin = skin_index[output.skin_name]
            plain = [x for x in market if not x.decorated and wear_for_float(x.float_value) == output.wear
                     and skin["min_float"] <= x.float_value <= skin["max_float"]]
            if not plain:
                complete = False
                break
            output.price = min(x.price for x in plain)
            timestamps.append(min(x.timestamp for x in plain))
        if not complete:
            continue
        gross, net, profit, roi, chance, downside = metrics(outcomes, cost, settings.SELL_FEE_PERCENT)
        best_case = best_profit(outcomes, cost, settings.SELL_FEE_PERCENT)
        if not qualifies(profit, roi, chance, best_case, settings):
            continue
        oldest = min(timestamps)
        if client.clock()-oldest >= client.ttl:
            continue
        result = {"verified": True, "budget": budget, "cost": cost, "gross_ev": gross,
            "selling_fees": gross-net, "net_ev": net, "profit": profit, "roi": roi,
            "chance_profit": chance, "downside": downside,
            "search_mode": settings.SEARCH_MODE, "best_profit": best_case,
            "worst_profit": min(o.price*(1-settings.SELL_FEE_PERCENT/100)-cost for o in outcomes),
            "sell_fee_percent": settings.SELL_FEE_PERCENT,
            "min_win_chance_percent": settings.MIN_WIN_CHANCE_PERCENT,
            "min_win_profit_dollars": settings.MIN_WIN_PROFIT_DOLLARS,
            "score": score(profit, roi, downside, settings, chance, best_case, cost), "verified_at": client.clock(),
            "oldest_quote_at": oldest, "average_float": math.fsum(i.float_value for i in inputs)/10,
            "average_normalized_float": math.fsum(normalize(i.float_value, skin_index[i.skin_name]) for i in inputs)/10,
            "discovery_oldest_at": min(b.timestamp for b, _ in candidate.parts),
            "input_rarity": candidate.parts[0][0].rarity,
            "inputs": [dict(asdict(row), skin=item.skin_name, collection=item.collection) for row, item in zip(rows, inputs)],
            "outcomes": [asdict(o) for o in outcomes]}
        if best is None or result["score"] > best["score"]:
            best = result
    return best, "Verified" if best else "No fully priced selection met the search criteria"
