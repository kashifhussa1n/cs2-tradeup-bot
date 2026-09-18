"""The only CSFloat transport: budget, pacing, cache and persistent cooldown."""
from dataclasses import dataclass, asdict
from email.utils import parsedate_to_datetime
import logging
import math
import random
import time
import requests
from src.storage import read_json, write_json


class VerificationStopped(RuntimeError): pass
class RequestBudgetExceeded(VerificationStopped): pass
class CooldownActive(VerificationStopped): pass
class MarketUnavailable(VerificationStopped): pass


@dataclass(frozen=True)
class Listing:
    id: str
    name: str
    price: float
    float_value: float
    timestamp: float
    decorated: bool = False


def retry_seconds(value, now, fallback):
    try:
        seconds = float(value)
        if math.isfinite(seconds):
            return max(0, seconds)
    except (ValueError, TypeError):
        pass
    try:
        return max(0, parsedate_to_datetime(value).timestamp() - now)
    except (ValueError, TypeError, OverflowError):
        return fallback


class CSFloatClient:
    def __init__(self, key, directory="data", cap=30, delay=3, ttl=120,
                 session=None, clock=time.time, sleep=time.sleep, retries=1):
        self.key, self.directory = key, directory
        self.cap, self.delay, self.base_delay, self.ttl = cap, delay, delay, ttl
        self.session, self.clock, self.sleep = session or requests.Session(), clock, sleep
        self.retries = retries
        self.last_call = None
        self.stats = {"requests": 0, "cache_hits": 0, "rate_limited": 0}
        self.cache = read_json(f"{directory}/live_listings.json", {})

    def check_cooldown(self):
        until = read_json(f"{self.directory}/csfloat_cooldown.json", {}).get("blocked_until", 0)
        if not math.isfinite(until):
            raise MarketUnavailable("Invalid cooldown state")
        if until > self.clock():
            raise CooldownActive(f"CSFloat cooldown: {until-self.clock():.0f} seconds remaining")

    def listings(self, name):
        self.check_cooldown()
        cached = self.cache.get(name)
        if cached and 0 <= self.clock()-cached["timestamp"] < self.ttl:
            self.stats["cache_hits"] += 1
            return [Listing(**row) for row in cached["listings"]]
        for attempt in range(self.retries + 1):
            self.check_cooldown()
            if self.stats["requests"] >= self.cap:
                raise RequestBudgetExceeded("API request budget exhausted before all candidates could be verified")
            if self.last_call is not None:
                self.sleep(max(0, self.delay-(self.clock()-self.last_call)))
            self.last_call = self.clock()
            self.stats["requests"] += 1
            logging.info("CSFloat network requests: %s/%s", self.stats["requests"], self.cap)
            try:
                response = self.session.get("https://csfloat.com/api/v1/listings",
                    headers={"Authorization": self.key},
                    params={"market_hash_name": name, "type": "buy_now", "category": 1,
                            "sort_by": "lowest_price", "limit": 50},
                    timeout=(5, 20), allow_redirects=False)
            except requests.RequestException:
                raise MarketUnavailable("CSFloat transport failed") from None
            if response.status_code == 429:
                self.stats["rate_limited"] += 1
                self.delay = min(15, max(1, self.delay * 1.6))
                wait = retry_seconds(response.headers.get("Retry-After"), self.clock(), 2**(attempt+1))
                wait = max(wait, 2**(attempt+1)) + random.uniform(0, .5)
                if attempt == self.retries:
                    wait = max(wait, 60)
                write_json(f"{self.directory}/csfloat_cooldown.json", {"blocked_until": self.clock()+wait})
                if wait > 15 or attempt == self.retries:
                    raise CooldownActive(f"CSFloat rate-limited verification; cooldown {wait:.0f}s persisted")
                self.sleep(wait)
                continue
            if response.status_code != 200:
                raise MarketUnavailable(f"CSFloat returned HTTP {response.status_code}")
            try:
                body = response.json()
                rows = body if isinstance(body, list) else body["data"]
                if not isinstance(rows, list):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise MarketUnavailable("Malformed CSFloat response") from None
            timestamp = self.clock()
            result = {}
            for row in rows:
                try:
                    item = row["item"]
                    price, value = row["price"], item["float_value"]
                    if (row.get("state") != "listed" or row.get("type") != "buy_now"
                        or item.get("market_hash_name") != name or item.get("is_stattrak")
                        or item.get("is_souvenir") or not isinstance(price, int) or price <= 0
                        or not math.isfinite(value) or not 0 <= value <= 1 or not row.get("id")):
                        continue
                    result[str(row["id"])] = Listing(str(row["id"]), name, price/100, value, timestamp,
                                                     bool(item.get("stickers")))
                except (TypeError, KeyError):
                    continue
            listings = sorted(result.values(), key=lambda x: x.price)
            self.cache[name] = {"timestamp": timestamp, "listings": [asdict(x) for x in listings]}
            write_json(f"{self.directory}/live_listings.json", self.cache)
            if listings:
                history_path = f"{self.directory}/discovery_prices.json"
                history = read_json(history_path, {})
                first = listings[0]
                history[name] = {"price": first.price, "timestamp": timestamp,
                    "source": "csfloat-history", "float_value": first.float_value, "quantity": len(listings)}
                write_json(history_path, history)
            self.delay = max(self.base_delay, self.delay*.98)
            return listings
        raise MarketUnavailable("Verification stopped")
