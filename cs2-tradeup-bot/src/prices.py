"""Optional legacy marketplace adapters. CSFloat transport lives in csfloat_client."""
import time
import requests
from src.rules import WEAR_RANGES, WEAR_TIERS, wear_for_float
from src.csfloat_client import CSFloatClient


class PriceSource:
    def get_price(self, skin_name, wear, float_value=None):
        raise NotImplementedError

class SteamMarketSource(PriceSource):
    """Fallback ONLY if CSFloat is unavailable. Wear-tier price only, no float data."""

    name = "steam"

    def __init__(self):
        self._last_call = 0
        self._min_interval = 2.0

    def get_price(self, skin_name: str, wear: str, float_value: float | None = None):
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        market_hash_name = f"{skin_name} ({wear})"
        resp = requests.get(
            "https://steamcommunity.com/market/priceoverview/",
            params={"appid": 730, "currency": 1, "market_hash_name": market_hash_name},
            timeout=15,
        )
        self._last_call = time.time()

        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("success"):
            return None
        price_str = data.get("lowest_price") or data.get("median_price")
        if not price_str:
            return None
        try:
            return float(price_str.replace("$", "").replace(",", ""))
        except ValueError:
            return None


class SkinportSource(PriceSource):
    """No longer used by default -- kept for reference only."""

    name = "skinport"

    def __init__(self, base_url: str = "https://api.skinport.com/v1/"):
        self.base_url = base_url.rstrip("/")
        self._cache = None
        self._cache_time = 0
        self._cache_ttl = 60 * 15

    def _load_items(self):
        if self._cache is not None and (time.time() - self._cache_time) < self._cache_ttl:
            return self._cache
        resp = requests.get(
            f"{self.base_url}/items",
            params={"app_id": 730, "currency": "USD"},
            headers={"Accept-Encoding": "br", "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        self._cache = resp.json()
        self._cache_time = time.time()
        return self._cache

    def get_price(self, skin_name: str, wear: str, float_value: float | None = None):
        items = self._load_items()
        market_hash_name = f"{skin_name} ({wear})"
        for item in items:
            if item.get("market_hash_name") == market_hash_name:
                return item.get("min_price")
        return None


class DMarketSource(PriceSource):
    """
    No longer used by default -- your feedback was that DMarket returned
    prices that didn't match real current listings. Kept here in case you
    want it back as a cross-check later.
    """

    name = "dmarket"

    _WEAR_TO_DMARKET = {
        "Factory New": "factory new",
        "Minimal Wear": "minimal wear",
        "Field-Tested": "field-tested",
        "Well-Worn": "well-worn",
        "Battle-Scarred": "battle-scarred",
    }

    def __init__(self, public_key: str, secret_key: str):
        from src.dmarket_client import DMarketClient
        self.client = DMarketClient(public_key, secret_key)
        self._cache = {}

    def get_price(self, skin_name: str, wear: str, float_value: float | None = None):
        result = self.get_price_and_float(skin_name, wear)
        return result[0] if result else None

    def get_price_and_float(self, skin_name: str, wear: str):
        cache_key = (skin_name, wear)
        if cache_key in self._cache:
            return self._cache[cache_key]

        dmarket_wear = self._WEAR_TO_DMARKET.get(wear)
        payload = {
            "gameId": "a8db",
            "title": skin_name,
            "orderBy": "price",
            "orderDir": "asc",
            "limit": 10,
        }
        if dmarket_wear:
            payload["treeFilters"] = f"exterior={dmarket_wear}"

        result, err = self.client.call("GET", "/marketplace-api/v2/offers", payload)
        if err or not result:
            self._cache[cache_key] = None
            return None

        items = result.get("items", [])
        target_title = f"{skin_name} ({wear})"
        matching = [i for i in items if i.get("title") == target_title]
        pool = matching if matching else items
        if not pool:
            self._cache[cache_key] = None
            return None

        cheapest = min(pool, key=lambda i: float(i.get("priceCents", "inf")))
        price = float(cheapest["priceCents"]) / 100

        actual_float = None
        cs2_attrs = (cheapest.get("attributes") or {}).get("cs2") or {}
        if cs2_attrs.get("float") is not None:
            try:
                actual_float = float(cs2_attrs["float"])
            except (TypeError, ValueError):
                actual_float = None

        out = (price, actual_float)
        self._cache[cache_key] = out
        return out

