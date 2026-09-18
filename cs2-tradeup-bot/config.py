"""Environment-configurable controls. USD prices, percentage fee and ROI."""
import os
import math
from dotenv import load_dotenv
from src.skin_data import RARITY_ORDER

load_dotenv()


def number(name, default, minimum=0):
    value = float(os.getenv(name, default))
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"Invalid {name}")
    return value


DATA_DIR = os.getenv("DATA_DIR", "data")
MAX_TOTAL_COST = number("BUDGET_OVERRIDE", 20, .01)
MIN_PROFIT_DOLLARS = number("MIN_PROFIT_DOLLARS", .10)
MIN_ROI_PERCENT = number("MIN_ROI_PERCENT", 1)
SEARCH_MODE = os.getenv("SEARCH_MODE", "upside")
if SEARCH_MODE not in {"upside", "expected_value"}:
    raise ValueError("SEARCH_MODE must be upside or expected_value")
MIN_WIN_CHANCE_PERCENT = number("MIN_WIN_CHANCE_PERCENT", 20)
MIN_WIN_PROFIT_DOLLARS = number("MIN_WIN_PROFIT_DOLLARS", .10)
if MIN_WIN_CHANCE_PERCENT > 100:
    raise ValueError("MIN_WIN_CHANCE_PERCENT must not exceed 100")
SELL_FEE_PERCENT = number("SELL_FEE_PERCENT", 13)
if SELL_FEE_PERCENT >= 100:
    raise ValueError("SELL_FEE_PERCENT must be below 100")
RARITY_TIERS = RARITY_ORDER[:-1]
MAX_CSFLOAT_REQUESTS_PER_RUN = int(number("MAX_CSFLOAT_REQUESTS_PER_RUN", 30))
CSFLOAT_REQUEST_DELAY = number("CSFLOAT_REQUEST_DELAY", 3)
LIVE_TTL = number("LIVE_TTL", 120, 1)
DISCOVERY_TTL = number("DISCOVERY_TTL", 86400, 300)
DISCOVERY_MAX_AGE = number("DISCOVERY_MAX_AGE", 604800, 300)
USE_SKINPORT_SNAPSHOT = os.getenv("USE_SKINPORT_SNAPSHOT", "1") == "1"
LOCAL_SHORTLIST = int(number("LOCAL_SHORTLIST", 40, 1))
LIVE_SHORTLIST = int(number("LIVE_SHORTLIST", 12, 1))
BLOCKS_PER_COLLECTION = int(number("BLOCKS_PER_COLLECTION", 6, 1))
PAIR_POOL_SIZE = int(number("PAIR_POOL_SIZE", 100, 2))
FLOAT_SCENARIOS = int(number("FLOAT_SCENARIOS", 5, 2))
# Discovery may retain near-misses; final verification still uses strict thresholds.
DISCOVERY_PRICE_TOLERANCE = number("DISCOVERY_PRICE_TOLERANCE", .15)
if DISCOVERY_PRICE_TOLERANCE >= 1:
    raise ValueError("DISCOVERY_PRICE_TOLERANCE must be below 1")
OPTIMIZER_WIDTH = int(number("OPTIMIZER_WIDTH", 64, 2))
MAX_RESULTS_TO_SHOW = int(number("MAX_RESULTS_TO_SHOW", 5, 1))
SCORE_ROI_WEIGHT = number("SCORE_ROI_WEIGHT", .01)
SCORE_RISK_WEIGHT = number("SCORE_RISK_WEIGHT", .15)
SKIN_DATA_CACHE_PATH = f"{DATA_DIR}/skins.json"
AUTO_RESUME = os.getenv("AUTO_RESUME", "1") == "1"
AUTO_RESUME_DELAY_SECONDS = number("AUTO_RESUME_DELAY_SECONDS", 300, 1)
AUTO_MAX_BATCHES = int(number("AUTO_MAX_BATCHES", 10, 1))
