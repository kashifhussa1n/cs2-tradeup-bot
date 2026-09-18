import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from src.csfloat_client import CSFloatClient
from src.discovery import DiscoveryPrices, Quote
from src.discord_webhook import format_result
from src.search import generate, score
from src.strategy import qualifies
from src.verifier import verify
from src import checkpoint
from test_pipeline import GROUPED, Clock, candidate, response, row, settings


class UpsideTests(unittest.TestCase):
    def test_negative_ev_contract_generated_and_verified_with_upside_label(self):
        prices = DiscoveryPrices({f'{name} (Field-Tested)': Quote(price,time.time(),'test')
                                  for name,price in [('A',.6),('X',8),('Y',2)]})
        mode = settings(SEARCH_MODE='upside')
        with patch('requests.sessions.Session.request',side_effect=AssertionError('network')):
            candidates,_ = generate(GROUPED,prices,6,mode)
        self.assertTrue(candidates)
        self.assertTrue(all(c.profit < 0 for c in candidates))
        with tempfile.TemporaryDirectory() as directory:
            clock,session=Clock(),Mock()
            def market(url,**kwargs):
                name=kwargs['params']['market_hash_name']
                cents=60 if name.startswith('A ') else 800 if name.startswith('X ') else 200
                return response([row(f'{name}-{i}',name,cents) for i in range(10)])
            session.get.side_effect=market
            client=CSFloatClient('fake',directory,session=session,clock=clock,sleep=clock.sleep,delay=0)
            result,_=verify(candidates[0],GROUPED,prices,client,6,mode)
            self.assertIsNotNone(result)
            self.assertAlmostEqual(result['profit'],-1.65)
            self.assertAlmostEqual(result['best_profit'],.96)
            self.assertAlmostEqual(result['chance_profit'],.5)
            message='\n'.join(format_result(result,now=clock()))
            self.assertIn('CHANCE-OF-PROFIT',message)
            self.assertIn('Negative expected value',message)
            self.assertIn('50.00%',message)
            strict,_=verify(candidates[0],GROUPED,prices,client,6,settings())
            self.assertIsNone(strict)
            with self.assertRaises(ValueError):
                format_result({**result,'search_mode':'expected_value'},now=clock())

    def test_no_winning_outcome_and_tiny_jackpot_chance_rejected(self):
        mode=settings(SEARCH_MODE='upside')
        self.assertFalse(qualifies(-2,-30,0,-1,mode))
        self.assertFalse(qualifies(-2,-30,.01,100,mode))
        self.assertTrue(qualifies(-.5,-10,.5,2,mode))

    def test_likely_modest_win_beats_unlikely_jackpot(self):
        mode=settings(SEARCH_MODE='upside')
        balanced=score(-1.65,-27.5,2.13,mode,.5,.96,6)
        jackpot=score(-4,-66.7,5,mode,.01,100,6)
        self.assertGreater(balanced,jackpot)

    def test_checkpoint_cannot_resume_old_strategy_silently(self):
        self.assertNotEqual(checkpoint.context(6,None,settings()),
                            checkpoint.context(6,None,settings(SEARCH_MODE='upside')))
