import unittest
import time
from unittest.mock import patch
from dataclasses import replace
from src.discovery import DiscoveryPrices, Quote
from src.search import Candidate, balanced_shortlist, float_scenarios, generate
from test_pipeline import skin, block, settings


class MechanismTests(unittest.TestCase):
    def test_small_contract_reserved_a_live_slot(self):
        expensive = [Candidate([(block(str(i), str(i)),10)], 150, 200, 24,16,1,24-i)
                     for i in range(20)]
        small = Candidate([(block("P90", "Nuke"),10)],1.5,2.29,.4923,32.82,.66,.5)
        self.assertIs(balanced_shortlist(expensive+[small], 12)[0], small)

    def test_equivalent_float_scenarios_use_one_live_slot(self):
        a = block()
        candidates = [Candidate([(replace(a,float_value=v),10)],10,20,7.4,74,1,8)
                      for v in [.15,.2,.3]]
        self.assertEqual(len(balanced_shortlist(candidates,12)),1)

    def test_samples_low_float_and_output_boundary(self):
        values = float_scenarios(skin("P90",0,.5),[skin("Glock",0,.7)],.15,.38,None,5)
        self.assertTrue(any(.15 < v < .17 for v in values))
        self.assertTrue(any(abs(v-(.38/.7*.5))<1e-7 for v in values))

    def test_low_float_profitable_scenario_survives_losing_midpoint(self):
        grouped = {"Nuke": {"Mil-Spec Grade":[skin("P90",0,.5)], "Restricted":[skin("Glock",0,1)]}}
        prices = DiscoveryPrices({"P90 (Field-Tested)": Quote(.15,time.time(),"test"),
            "Glock (Field-Tested)":Quote(2.65,time.time(),"test"),
            "Glock (Battle-Scarred)":Quote(.5,time.time(),"test")})
        with patch('requests.sessions.Session.request',side_effect=AssertionError('network')):
            candidates,stats=generate(grouped,prices,20,settings())
        self.assertTrue(candidates)
        self.assertTrue(any(c.parts[0][0].float_value < .19 for c in candidates))

    def test_near_miss_discovery_threshold_is_relaxed_only_locally(self):
        grouped = {"Nuke": {"Mil-Spec Grade":[skin("P90")], "Restricted":[skin("Output")]}}
        prices = DiscoveryPrices({"P90 (Field-Tested)":Quote(.19,time.time(),"test"),
                                  "Output (Field-Tested)":Quote(2.29,time.time(),"test")})
        candidates,stats=generate(grouped,prices,20,settings())
        self.assertTrue(candidates)
        self.assertAlmostEqual(candidates[0].profit,.0923)
        self.assertGreater(stats['near_misses_retained'],0)
        strict,_=generate(grouped,prices,20,settings(DISCOVERY_PRICE_TOLERANCE=0))
        self.assertFalse(strict)
