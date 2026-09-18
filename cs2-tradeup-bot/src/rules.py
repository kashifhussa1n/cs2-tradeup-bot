"""Normal ten-item contracts; normalized input floats (post-Retakes rules)."""
import math

WEAR_RANGES = [("Factory New", 0, .07), ("Minimal Wear", .07, .15),
               ("Field-Tested", .15, .38), ("Well-Worn", .38, .45),
               ("Battle-Scarred", .45, 1)]
WEAR_TIERS = [w[0] for w in WEAR_RANGES]

# ByMykel exposes this store category in `collections`, but it is not an
# upgradeable drop collection. Names also protect older serialized candidates.
# Source: https://tradeupx.app/skin/m4a1-s-solitude (eligibility section).
NON_TRADEUP_COLLECTION_IDS = {"collection-set-xpshop-wpn-01", "set_xpshop_wpn_01"}
NON_TRADEUP_COLLECTION_NAMES = {"limited edition item", "limited edition items"}
NON_TRADEUP_SKINS = {"M4A1-S | Solitude", "XM1014 | Solitude",
                     "Desert Eagle | Heat Treated", "AK-47 | Aphrodite"}


def tradeup_eligible(skin, collection=None):
    """Central exclusion rule; collection membership alone is not eligibility.

    This supplements rarity/range/output validation, not a full game schema.
    Do not exclude all Armory items: ordinary Armory collections are eligible.
    """
    if skin.get("name", "").split(" (")[0] in NON_TRADEUP_SKINS:
        return False
    collections = list(skin.get("collections") or [])
    if collection:
        collections.append({"name": collection})
    return not any(c.get("id") in NON_TRADEUP_COLLECTION_IDS or
                   c.get("name", "").strip().casefold() in NON_TRADEUP_COLLECTION_NAMES
                   for c in collections)


def wear_for_float(value):
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid float")
    return next(name for name, lo, hi in WEAR_RANGES
                if lo <= value < hi or value == hi == 1)


def normalize(value, skin):
    lo, hi = skin["min_float"], skin["max_float"]
    if not 0 <= lo < hi <= 1 or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("Float outside skin range")
    return (value - lo) / (hi - lo)
