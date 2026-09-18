"""Network-free price lookup, populated before search from bulk/local snapshots."""
from dataclasses import dataclass
from typing import Protocol
import logging
import math
import time
import requests
from src.storage import read_json, write_json


@dataclass(frozen=True)
class Quote:
    price: float
    timestamp: float
    source: str
    float_value: float | None = None
    quantity: int | None = None


class PriceProvider(Protocol):
    def get(self, name: str, wear: str) -> Quote | None: ...


class DiscoveryPrices:
    def __init__(self, quotes=None):
        self.quotes = quotes or {}

    def get(self, name, wear):
        return self.quotes.get(f"{name} ({wear})")

    @classmethod
    def load(cls, directory, ttl=86400, max_age=604800, refresh=True, now=None):
        now = time.time() if now is None else now
        path = f"{directory}/skinport_snapshot.json"
        snapshot = read_json(path, {})
        if refresh and now - snapshot.get("fetched_at", 0) >= ttl:
            try:
                response = requests.get("https://api.skinport.com/v1/items",
                    params={"app_id": 730, "currency": "USD"},
                    headers={"Accept-Encoding": "br"}, timeout=30)
                response.raise_for_status()
                rows = response.json()
                if not isinstance(rows, list):
                    raise ValueError("Invalid bulk snapshot")
                snapshot = {"fetched_at": now, "items": rows}
                write_json(path, snapshot)
            except (requests.RequestException, ValueError):
                logging.warning("Bulk price refresh failed; using available local data")
        quotes = {}
        for row in snapshot.get("items", []):
            price = row.get("min_price")
            ts = min(snapshot.get("fetched_at", 0), row.get("updated_at", 0))
            if row.get("currency") == "USD" and price and math.isfinite(price) and price > 0 and 0 <= now-ts <= max_age:
                quotes[row["market_hash_name"]] = Quote(price, ts, "skinport", quantity=row.get("quantity"))
        # Migrate the old scalar CSFloat cache as estimates only, never live listings.
        for key, entry in read_json(f"{directory}/csfloat_price_cache.json", {}).items():
            value, ts = entry.get("value"), entry.get("ts", 0)
            if value and 0 <= now-ts <= max_age and "||" in key:
                name, wear = key.rsplit("||", 1)
                if math.isfinite(value[0]) and value[0] > 0:
                    quotes[f"{name} ({wear})"] = Quote(value[0], ts, "csfloat-history", value[1])
        for name, entry in read_json(f"{directory}/discovery_prices.json", {}).items():
            if 0 <= now-entry["timestamp"] <= max_age:
                quotes[name] = Quote(**entry)
        return cls(quotes)
