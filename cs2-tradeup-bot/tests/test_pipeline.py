import copy
import tempfile
import unittest
from dataclasses import replace
from email.utils import formatdate
from types import SimpleNamespace
from unittest.mock import Mock, patch
import config
from src.csfloat_client import (CSFloatClient, Listing, CooldownActive,
    RequestBudgetExceeded, MarketUnavailable, retry_seconds)
from src.discovery import DiscoveryPrices, Quote
from src.discord_webhook import format_result, post_results
from src.rules import normalize, wear_for_float
from src.search import Block, Candidate, generate, metrics
from src.storage import read_json, write_json
from src.tradeup_calc import InputItem, enumerate_outcomes, expected_value
from src.verifier import selections, verify


def skin(name, lo=0, hi=1):
    return {"name": name, "min_float": lo, "max_float": hi}


GROUPED = {"A": {"Restricted": [skin("A")], "Classified": [skin("X"), skin("Y")]},
           "B": {"Restricted": [skin("B", .1, .6)], "Classified": [skin("Z")]}}


def settings(**kwargs):
    values = {key: getattr(config, key) for key in dir(config) if key.isupper()}
    values["SEARCH_MODE"] = "expected_value"
    values.update(kwargs)
    return SimpleNamespace(**values)


def block(name="A", collection="A", value=.2, wear="Field-Tested"):
    return Block(name, collection, "Restricted", wear, 1, value, .15, .38, 1000, "test")


def candidate(parts=None):
    return Candidate(parts or [(block(), 10)], 10, 20, 7.4, 74, 1, 8)


def row(index, name="A (Field-Tested)", cents=100, value=.2, **extra):
    return {"id": str(index), "state": "listed", "type": "buy_now", "price": cents,
            "item": {"market_hash_name": name, "float_value": value, **extra}}


def response(rows=None, status=200, retry=None):
    return SimpleNamespace(status_code=status, headers={"Retry-After": retry} if retry else {},
                           json=lambda: {"data": rows or []})


class Clock:
    def __init__(self): self.now = 1000
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class MathTests(unittest.TestCase):
    def test_positive_ev_can_have_mostly_losing_outcomes(self):
        outcomes = enumerate_outcomes([InputItem("A", "A", .2, 1)]*8 + [InputItem("B", "B", .2, 1)]*2, GROUPED)
        for output in outcomes:
            output.price = 100 if output.skin_name == "Z" else 1
        gross, net, profit, roi, chance, downside = metrics(outcomes, 10, 13)
        self.assertGreater(profit, 0)
        self.assertAlmostEqual(chance, .2)
        self.assertGreater(downside, 0)

    def test_phase_records_do_not_inflate_weapon_probability(self):
        from src.skin_data import group_by_collection_and_rarity
        records = []
        for name, rarity in [("A", "Restricted"), ("X", "Classified"), ("X", "Classified"), ("Y", "Classified")]:
            records.append({**skin(name), "rarity": {"name": rarity}, "collections": [{"name": "A"}]})
        grouped = group_by_collection_and_rarity(records)
        outcomes = enumerate_outcomes([InputItem("A", "A", .2, 1)]*10, grouped)
        self.assertEqual([o.probability for o in outcomes], [.5, .5])

    def test_mixed_normalized_odds(self):
        inputs = [InputItem("A", "A", .2, 1)]*6 + [InputItem("B", "B", .2, 1)]*4
        outcomes = enumerate_outcomes(inputs, GROUPED)
        self.assertEqual([o.probability for o in outcomes], [.3, .3, .4])
        for o in outcomes:
            self.assertAlmostEqual(o.output_float, .2)
            o.price = 20
        gross, net, profit, roi, chance, downside = metrics(outcomes, 10, 13)
        self.assertAlmostEqual(gross, 20)
        self.assertAlmostEqual(net, 17.4)
        self.assertAlmostEqual(profit, 7.4)
        self.assertAlmostEqual(roi, 74)
        self.assertEqual(chance, 1)

    def test_capped_inputs_regression(self):
        outcomes = enumerate_outcomes([InputItem("B", "B", .35, 1)]*10, GROUPED)
        self.assertAlmostEqual(outcomes[0].output_float, .5)
        self.assertNotAlmostEqual(outcomes[0].output_float, .35)  # old raw-average bug

    def test_full_range_old_formula_preserved(self):
        self.assertAlmostEqual(enumerate_outcomes([InputItem("A", "A", .2, 1)]*10, GROUPED)[0].output_float, .2)

    def test_wear_boundaries(self):
        for value, wear in [(0, "Factory New"), (.07, "Minimal Wear"), (.15, "Field-Tested"),
                            (.38, "Well-Worn"), (.45, "Battle-Scarred"), (1, "Battle-Scarred")]:
            self.assertEqual(wear_for_float(value), wear)
        for value in [-1, 1.01, float("nan")]:
            with self.assertRaises(ValueError): wear_for_float(value)

    def test_invalid_contracts(self):
        for inputs in [[InputItem("A", "A", .2, 1)]*9,
                       [InputItem("B", "B", .9, 1)]*10,
                       [InputItem("X", "A", .2, 1)] + [InputItem("A", "A", .2, 1)]*9]:
            with self.assertRaises(ValueError): enumerate_outcomes(inputs, GROUPED)
        grouped = copy.deepcopy(GROUPED)
        grouped["A"]["Classified"] = []
        with self.assertRaises(ValueError): enumerate_outcomes([InputItem("A", "A", .2, 1)]*10, grouped)

    def test_missing_price_rejected(self):
        outcomes = enumerate_outcomes([InputItem("A", "A", .2, 1)]*10, GROUPED)
        outcomes[0].price = 20
        with self.assertRaises(ValueError): expected_value(outcomes)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.session = Mock()

    def client(self, **kwargs):
        return CSFloatClient("fake", self.temp.name, session=self.session, clock=self.clock,
                             sleep=self.clock.sleep, delay=0, **kwargs)

    def test_cache_and_expiry_across_restart(self):
        self.session.get.return_value = response([row(1)])
        client = self.client(ttl=10)
        self.assertEqual(len(client.listings("A (Field-Tested)")), 1)
        client.listings("A (Field-Tested)")
        self.assertEqual(client.stats["requests"], 1)
        self.assertEqual(client.stats["cache_hits"], 1)
        restarted = self.client(ttl=10)
        restarted.listings("A (Field-Tested)")
        self.assertEqual(restarted.stats["requests"], 0)
        self.clock.sleep(11)
        restarted.listings("A (Field-Tested)")
        self.assertEqual(restarted.stats["requests"], 1)

    def test_global_cap_30(self):
        self.session.get.return_value = response()
        client = self.client(cap=30)
        for i in range(30): client.listings(str(i))
        with self.assertRaises(RequestBudgetExceeded): client.listings("31")
        self.assertEqual(self.session.get.call_count, 30)

    def test_retry_counts_and_respects_cap(self):
        self.session.get.side_effect = [response(status=429, retry="5"), response()]
        client = self.client(cap=2)
        client.listings("A")
        self.assertEqual(client.stats["requests"], 2)
        self.assertGreaterEqual(self.clock.now, 1005)
        with self.assertRaises(RequestBudgetExceeded): client.listings("B")

    def test_retry_cannot_exceed_one_request_cap(self):
        self.session.get.return_value = response(status=429, retry="1")
        client = self.client(cap=1)
        with self.assertRaises(RequestBudgetExceeded): client.listings("A")
        self.assertEqual(self.session.get.call_count, 1)

    def test_http_date_and_persistent_cooldown(self):
        date = formatdate(2000, usegmt=True)
        self.session.get.return_value = response(status=429, retry=date)
        with self.assertRaises(CooldownActive): self.client().listings("A")
        with self.assertRaises(CooldownActive): self.client().listings("A")
        self.assertEqual(self.session.get.call_count, 1)

    def test_repeated_429_stops(self):
        self.session.get.return_value = response(status=429, retry="1")
        client = self.client()
        with self.assertRaises(CooldownActive): client.listings("A")
        self.assertEqual(client.stats["requests"], 2)
        self.assertGreater(read_json(f"{self.temp.name}/csfloat_cooldown.json", {})["blocked_until"], self.clock())

    def test_retry_after_parsing(self):
        self.assertEqual(retry_seconds("5", 1000, 2), 5)
        self.assertEqual(retry_seconds(formatdate(1005, usegmt=True), 1000, 2), 5)
        self.assertEqual(retry_seconds("nonsense", 1000, 2), 2)
        self.assertEqual(retry_seconds("nan", 1000, 2), 2)

    def test_filters_bad_and_duplicate_listings(self):
        bad = row(2); bad["state"] = "sold"
        self.session.get.return_value = response([row(1), row(1), bad, row(3, is_stattrak=True),
            row(4, name="wrong"), row(5, cents=-1), row(6, value=float("nan")), row(7, is_souvenir=True)])
        self.assertEqual(len(self.client().listings("A (Field-Tested)")), 1)
        self.assertFalse(self.session.get.call_args.kwargs["allow_redirects"])

    def test_transport_errors_count(self):
        import requests
        self.session.get.side_effect = requests.ConnectionError("secret")
        client = self.client()
        with self.assertRaises(MarketUnavailable) as ctx: client.listings("A")
        self.assertNotIn("secret", str(ctx.exception))
        self.assertEqual(client.stats["requests"], 1)


class VerificationTests(unittest.TestCase):
    def test_real_input_price_decides_final_profit_not_discovery_tolerance(self):
        for cents, accepted in [(15, True), (19, False)]:
            with self.subTest(input_cents=cents):
                self.client.cache.clear()
                def market(url, **kwargs):
                    name = kwargs["params"]["market_hash_name"]
                    price = cents if name.startswith("A ") else 229
                    return response([row(f"{name}-{i}", name, price) for i in range(10)])
                self.session.get.side_effect = market
                result, _ = verify(candidate(), GROUPED, self.prices, self.client, 20, settings())
                self.assertEqual(result is not None, accepted)
                if result:
                    self.assertAlmostEqual(result["cost"], 1.5)
                    self.assertAlmostEqual(result["profit"], .4923)

    def test_more_expensive_low_float_listing_improves_actual_ev(self):
        grouped = {"A": {"Restricted": [skin("A")], "Classified": [skin("X", 0, .75)]}}
        prices = DiscoveryPrices({"X (Field-Tested)": Quote(5, 1000, "test"),
                                  "X (Minimal Wear)": Quote(20, 1000, "test")})
        def market(url, **kwargs):
            name = kwargs["params"]["market_hash_name"]
            if name.startswith("A "):
                return response([row(i, value=.201) for i in range(10)]+[row("low", cents=104, value=.15)])
            if name.endswith("(Minimal Wear)"):
                return response([row("mw", name, 2000, .14)])
            return response([row("ft", name, 500, .2)])
        self.session.get.side_effect = market
        result, _ = verify(candidate(), grouped, prices, self.client, 20, settings())
        self.assertEqual(result["cost"], 10.04)
        self.assertIn("low", [x["id"] for x in result["inputs"]])
        self.assertEqual(result["outcomes"][0]["wear"], "Minimal Wear")

    def test_missing_or_decorated_output_rejected(self):
        def market(url, **kwargs):
            name = kwargs["params"]["market_hash_name"]
            if name.startswith("A "):
                return response([row(i) for i in range(10)])
            return response([row(name, name, 2000, stickers=[{"id": 1}])])
        self.session.get.side_effect = market
        self.assertIsNone(verify(candidate(), GROUPED, self.prices, self.client, 20, settings())[0])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.session = Mock()
        self.client = CSFloatClient("fake", self.temp.name, session=self.session,
            clock=self.clock, sleep=self.clock.sleep, delay=0)
        self.prices = DiscoveryPrices({f"{name} (Field-Tested)": Quote(20, 1000, "test") for name in ["X", "Y", "Z"]})

    def respond(self, url, **kwargs):
        name = kwargs["params"]["market_hash_name"]
        return response([row(f"{name}-{i}", name, 100 if name.startswith(("A ", "B ")) else 2000) for i in range(10)])

    def test_end_to_end_mixed_distinct_quantity_and_outputs(self):
        self.session.get.side_effect = self.respond
        result, reason = verify(candidate([(block(), 6), (block("B", "B"), 4)]), GROUPED,
                                 self.prices, self.client, 20, settings())
        self.assertTrue(result["verified"])
        self.assertEqual(result["cost"], 10)
        self.assertEqual(len(result["inputs"]), 10)
        self.assertEqual(self.client.stats["requests"], 5)
        self.assertAlmostEqual(result["profit"], 7.4)
        self.assertTrue(all(len(x) <= 1900 for x in format_result(result, now=1000)))
        # Same candidate reuses inputs AND outputs within freshness window.
        verify(candidate([(block(), 6), (block("B", "B"), 4)]), GROUPED,
               self.prices, self.client, 20, settings())
        self.assertEqual(self.client.stats["requests"], 5)

    def test_nine_listings_rejected(self):
        self.session.get.return_value = response([row(i) for i in range(9)])
        result, _ = verify(candidate(), GROUPED, self.prices, self.client, 20, settings())
        self.assertIsNone(result)
        self.assertEqual(self.client.stats["requests"], 1)

    def test_budget_enforced(self):
        self.session.get.return_value = response([row(i, cents=201) for i in range(10)])
        self.assertIsNone(verify(candidate(), GROUPED, self.prices, self.client, 20, settings())[0])

    def test_output_price_collapse(self):
        def cheap(url, **kwargs):
            name = kwargs["params"]["market_hash_name"]
            return response([row(f"{name}-{i}", name, 100) for i in range(10)])
        self.session.get.side_effect = cheap
        self.assertIsNone(verify(candidate(), GROUPED, self.prices, self.client, 20, settings())[0])

    def test_float_constraint_and_duplicate_ids(self):
        listings = [Listing(str(i), "A", 1, .2, 1000) for i in range(10)]
        self.assertFalse(selections(listings, 10, replace(block(), max_float=.18), 20, 64))
        self.assertFalse(selections(listings[:9]+listings[:1], 10, block(), 20, 64))

    def test_optimizer_keeps_lower_float_alternative(self):
        listings = [Listing(str(i), "A", 1, .3, 1000) for i in range(10)]
        listings += [Listing("low", "A", 1.04, .15, 1000)]
        choices = selections(listings, 10, block(), 20, 64)
        self.assertTrue(any(any(x.id == "low" for x in rows) for _, _, rows in choices))
        self.assertTrue(any(abs(cost-10) < .001 for cost, _, _ in choices))

    def test_discord_rejects_unverified_negative_and_stale(self):
        self.session.get.side_effect = self.respond
        result, _ = verify(candidate(), GROUPED, self.prices, self.client, 20, settings())
        for change in [{"verified": False}, {"profit": -1}, {"budget": 9}, {"oldest_quote_at": 0}]:
            with self.assertRaises(ValueError): format_result({**result, **change}, now=1000)
        with patch("src.discord_webhook.requests.post") as post:
            with self.assertRaises(ValueError): post_results("fake", [{**result, "verified": False}])
            post.assert_not_called()


class DiscoveryTests(unittest.TestCase):
    def test_bulk_snapshot_one_request_and_disk_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            mock = Mock()
            mock.json.return_value = [{"market_hash_name": "A (Field-Tested)", "currency": "USD",
                                       "min_price": 1, "quantity": 10, "updated_at": 999}]
            with patch("src.discovery.requests.get", return_value=mock) as get:
                first = DiscoveryPrices.load(directory, ttl=300, now=1000)
                second = DiscoveryPrices.load(directory, ttl=300, now=1001)
                self.assertEqual(first.get("A", "Field-Tested"), second.get("A", "Field-Tested"))
                self.assertEqual(get.call_count, 1)
                self.assertEqual(get.call_args.kwargs["params"]["currency"], "USD")

    def test_cache_migration_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            write_json(f"{directory}/csfloat_price_cache.json", {"A||Field-Tested": {"ts": 990, "value": [1, .2]}})
            with patch("src.discovery.requests.get") as get:
                prices = DiscoveryPrices.load(directory, refresh=False, now=1000)
                self.assertEqual(prices.get("A", "Field-Tested").price, 1)
                get.assert_not_called()

    def test_all_wears_and_mixed_search_without_network(self):
        quotes = {}
        from src.rules import WEAR_RANGES
        for name in ["A", "B", "X", "Y", "Z"]:
            for wear, lo, hi in WEAR_RANGES:
                quotes[f"{name} ({wear})"] = Quote(1 if name in ["A", "B"] else 20, 1000, "test")
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected network")):
            candidates, stats = generate(GROUPED, DiscoveryPrices(quotes), 20,
                settings(BLOCKS_PER_COLLECTION=10, LOCAL_SHORTLIST=100, PAIR_POOL_SIZE=20))
        self.assertGreater(stats["evaluated"], 100)
        self.assertTrue(any(len(c.parts) == 2 for c in candidates))
        self.assertTrue(all(c.cost <= 20 for c in candidates))


class MainTests(unittest.TestCase):
    def test_partial_verification_budget_failure_reports_reason(self):
        import main
        with tempfile.TemporaryDirectory() as directory:
            clock = Clock()
            session = Mock()
            session.get.return_value = response([row(i) for i in range(10)])
            client = CSFloatClient("fake", directory, cap=1, delay=0, session=session, clock=clock, sleep=clock.sleep)
            prices = DiscoveryPrices({f"{name} (Field-Tested)": Quote(20, 1000, "test") for name in ["X", "Y"]})
            with patch.object(main.config, "DATA_DIR", directory), patch.object(main, "CSFloatClient", return_value=client), \
                 patch.object(main, "load_skin_data", return_value=[]), \
                 patch.object(main, "group_by_collection_and_rarity", return_value=GROUPED), \
                 patch.object(main.DiscoveryPrices, "load", return_value=prices), \
                 patch.object(main, "generate", return_value=([candidate()], {"evaluated": 1000})), \
                 patch.object(main, "post_results") as post:
                summary = main.main(["20", "--no-discord"])
            self.assertIn("budget exhausted", summary["status"])
            self.assertEqual(summary["verified"], 0)
            self.assertEqual(summary["csfloat"]["requests"], 1)
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
