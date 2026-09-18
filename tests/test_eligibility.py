"""Regression for the invalid Solitude -> Aphrodite alerts."""
import unittest
from unittest.mock import Mock
from src.rules import tradeup_eligible
from src.skin_data import group_by_collection_and_rarity
from src.tradeup_calc import InputItem, enumerate_outcomes
from src.search import generate
from src.discovery import DiscoveryPrices, Quote
from src.verifier import verify
from src.discord_webhook import format_result
from test_pipeline import skin, block, candidate, settings


def limited(name, rarity):
    return {**skin(name, 0, .7), "rarity": {"name": rarity}, "collections": [
        {"id": "collection-set-xpshop-wpn-01", "name": "Limited Edition Item"}]}


class EligibilityTests(unittest.TestCase):
    def test_category_excludes_future_items_by_id_and_name(self):
        for collection in [{"id": "collection-set-xpshop-wpn-01", "name": "Localized"},
                           {"name": "Limited Edition Item"}]:
            self.assertFalse(tradeup_eligible({"name": "Future Limited Skin", "collections": [collection]}))

    def test_all_current_limited_items_excluded(self):
        for name in ["M4A1-S | Solitude", "XM1014 | Solitude", "Desert Eagle | Heat Treated", "AK-47 | Aphrodite"]:
            self.assertFalse(tradeup_eligible({"name": name}))

    def test_normal_armory_collection_preserved(self):
        record = {**skin("M4A1-S | Fade"), "rarity": {"name": "Covert"},
                  "collections": [{"name": "The Sport & Field Collection"}]}
        self.assertIn("The Sport & Field Collection", group_by_collection_and_rarity([record]))

    def test_limited_category_not_generated(self):
        grouped = group_by_collection_and_rarity([limited("M4A1-S | Solitude", "Classified"),
                                                limited("AK-47 | Aphrodite", "Covert")])
        prices = DiscoveryPrices({"M4A1-S | Solitude (Factory New)": Quote(14, 1000, "test"),
                                  "AK-47 | Aphrodite (Factory New)": Quote(265, 1000, "test")})
        self.assertEqual(grouped, {})
        self.assertEqual(generate(grouped, prices, 200, settings())[0], [])

    def test_math_rejects_unfiltered_single_and_mixed_contracts(self):
        grouped = {"Limited Edition Item": {"Classified": [skin("M4A1-S | Solitude")],
                                           "Covert": [skin("AK-47 | Aphrodite")]},
                   "Normal": {"Classified": [skin("A")], "Covert": [skin("X")]}}
        for count in [1, 9, 10]:
            inputs = [InputItem("M4A1-S | Solitude", "Limited Edition Item", .05, 14)]*count
            inputs += [InputItem("A", "Normal", .05, 14)]*(10-count)
            with self.assertRaises(ValueError): enumerate_outcomes(inputs, grouped)

    def test_math_rejects_limited_output_even_in_wrong_collection(self):
        grouped = {"Normal": {"Classified": [skin("A")], "Covert": [skin("AK-47 | Aphrodite")]}}
        with self.assertRaises(ValueError):
            enumerate_outcomes([InputItem("A", "Normal", .05, 14)]*10, grouped)

    def test_verification_rejects_before_api_request(self):
        grouped = {"Limited Edition Item": {"Restricted": [skin("M4A1-S | Solitude")],
                                           "Classified": [skin("X")]}}
        client = Mock()
        result, reason = verify(candidate([(block("M4A1-S | Solitude", "Limited Edition Item"), 10)]),
                                grouped, DiscoveryPrices(), client, 200, settings())
        self.assertIsNone(result)
        self.assertIn("eligible", reason)
        client.listings.assert_not_called()

    def test_discord_rejects_previously_serialized_invalid_result(self):
        for field, row in [("inputs", {"skin": "M4A1-S | Solitude"}),
                           ("outcomes", {"skin_name": "AK-47 | Aphrodite"})]:
            with self.assertRaisesRegex(ValueError, "eligible"):
                format_result({"verified": True, field: [row]})
