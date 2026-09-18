"""
Pulls the static skin/collection/rarity/float database from the
community-maintained ByMykel CS2 API (free, no key required) and caches
it locally so we don't hit the network every run.

Source: https://github.com/ByMykel/CSGO-API
"""
import json
import os
import time
import requests
from src.rules import tradeup_eligible

SKINS_URL = "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/skins.json"
CACHE_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # refresh weekly, this data barely changes


def load_skin_data(cache_path: str, offline: bool = False) -> list:
    """Returns a list of skin dicts. Uses local cache if fresh enough."""
    if offline or _cache_is_fresh(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    try:
        resp = requests.get(SKINS_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        raise ValueError("Skin database refresh failed; use --offline for cached analysis") from None

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return data


def _cache_is_fresh(cache_path: str) -> bool:
    if not os.path.exists(cache_path):
        return False
    age = time.time() - os.path.getmtime(cache_path)
    return age < CACHE_MAX_AGE_SECONDS


def group_by_collection_and_rarity(skins: list) -> dict:
    """
    Returns: { collection_name: { rarity_name: [skin, skin, ...] } }
    Only includes skins that have collection + rarity + float range info.
    Note: the API's `stattrak`/`souvenir` booleans mean "this skin HAS that
    variant available," not "this record IS that variant" -- there are no
    separate StatTrak/Souvenir records to filter out here.
    """
    grouped = {}
    for skin in skins:
        if not tradeup_eligible(skin):
            continue
        rarity = (skin.get("rarity") or {}).get("name")
        collections = skin.get("collections") or []
        min_float = skin.get("min_float")
        max_float = skin.get("max_float")
        if (rarity not in RARITY_ORDER or not collections or min_float is None or max_float is None
                or not 0 <= min_float < max_float <= 1 or skin.get("name", "").startswith("★")):
            continue

        for coll in collections:
            coll_name = coll.get("name")
            if not coll_name:
                continue
            pool = grouped.setdefault(coll_name, {}).setdefault(rarity, [])
            existing = next((s for s in pool if s["name"] == skin["name"]), None)
            if existing:
                if (existing["min_float"], existing["max_float"]) != (min_float, max_float):
                    raise ValueError("Ambiguous float ranges for shared market name")
                # Pattern phases share the weapon outcome; do not multiply its odds.
                continue
            pool.append(skin)

    return grouped


RARITY_ORDER = [
    "Consumer Grade",
    "Industrial Grade",
    "Mil-Spec Grade",
    "Restricted",
    "Classified",
    "Covert",
]


def next_rarity(rarity: str) -> str | None:
    if rarity not in RARITY_ORDER:
        return None
    idx = RARITY_ORDER.index(rarity)
    if idx + 1 >= len(RARITY_ORDER):
        return None
    return RARITY_ORDER[idx + 1]
