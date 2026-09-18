"""
The trade-up math itself.
"""
from dataclasses import dataclass
from src.rules import wear_for_float, normalize, tradeup_eligible
import math
from src.skin_data import next_rarity


@dataclass
class InputItem:
    skin_name: str
    collection: str
    float_value: float
    cost: float


@dataclass
class OutcomeSkin:
    skin_name: str
    collection: str
    probability: float
    output_float: float
    wear: str
    price: float | None


def compute_output_float(avg_input_float: float, min_float_out: float, max_float_out: float) -> float:
    return min_float_out + avg_input_float * (max_float_out - min_float_out)


def enumerate_outcomes(inputs: list[InputItem], grouped_skins: dict) -> list[OutcomeSkin]:
    if len(inputs) != 10:
        raise ValueError("Trade-up requires exactly 10 input items")

    normalized = []
    rarities = set()
    for item in inputs:
        rarity = _find_rarity_of(item, grouped_skins)
        if rarity is None or item.skin_name.startswith(("StatTrak", "Souvenir", "★")):
            raise ValueError("Unknown or unsupported input")
        skin = next(s for s in grouped_skins[item.collection][rarity] if s["name"] == item.skin_name)
        if not tradeup_eligible(skin, item.collection):
            raise ValueError("Input is not trade-up eligible")
        normalized.append(normalize(item.float_value, skin))
        rarities.add(rarity)
        if not math.isfinite(item.cost) or item.cost <= 0:
            raise ValueError("Invalid input cost")
    if len(rarities) != 1:
        raise ValueError("All inputs must have the same rarity")
    avg_float = math.fsum(normalized) / 10

    collection_counts: dict[str, int] = {}
    for item in inputs:
        collection_counts[item.collection] = collection_counts.get(item.collection, 0) + 1

    input_rarity = _find_rarity_of(inputs[0], grouped_skins)
    if input_rarity is None:
        raise ValueError(f"Could not determine rarity for {inputs[0].skin_name}")
    out_rarity = next_rarity(input_rarity)
    if out_rarity is None:
        raise ValueError(f"{input_rarity} has no next rarity tier (already top tier)")

    outcomes = []
    for collection, count in collection_counts.items():
        candidates = grouped_skins.get(collection, {}).get(out_rarity, [])
        if not candidates:
            raise ValueError("Input collection has no next-tier outputs")

        chance_this_collection = count / 10
        chance_per_skin = chance_this_collection / len(candidates)

        for skin in candidates:
            if not tradeup_eligible(skin, collection):
                raise ValueError("Output is not trade-up eligible")
            output_float = compute_output_float(avg_float, skin["min_float"], skin["max_float"])
            wear = wear_for_float(output_float)
            outcomes.append(
                OutcomeSkin(
                    skin_name=skin["name"],
                    collection=collection,
                    probability=chance_per_skin,
                    output_float=output_float,
                    wear=wear,
                    price=None,
                )
            )

    return outcomes


def _find_rarity_of(item: InputItem, grouped_skins: dict) -> str | None:
    coll = grouped_skins.get(item.collection, {})
    for rarity, skins in coll.items():
        for skin in skins:
            if skin["name"] == item.skin_name:
                return rarity
    return None


def expected_value(outcomes: list[OutcomeSkin]) -> float:
    if not outcomes or not math.isclose(sum(o.probability for o in outcomes), 1):
        raise ValueError("Incomplete output distribution")
    if any(o.price is None or not math.isfinite(o.price) or o.price <= 0 for o in outcomes):
        raise ValueError("Every output needs a valid price")
    return math.fsum(o.probability * o.price for o in outcomes)


def total_input_cost(inputs: list[InputItem]) -> float:
    return sum(i.cost for i in inputs)


def profit_margin_percent(ev: float, cost: float) -> float:
    if cost == 0:
        return 0.0
    return ((ev - cost) / cost) * 100
