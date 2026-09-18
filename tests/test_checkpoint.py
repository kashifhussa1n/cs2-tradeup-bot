import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
from src import checkpoint
from src.csfloat_client import RequestBudgetExceeded
from src.discovery import DiscoveryPrices, Quote
from test_pipeline import candidate, block, settings, GROUPED


class CheckpointTests(unittest.TestCase):
    def test_round_trip_and_empty_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/queue.json'
            ctx = checkpoint.context(20, None, settings())
            checkpoint.save(path, ctx, [candidate()])
            self.assertEqual(checkpoint.load(path), (ctx, [candidate()]))
            checkpoint.save(path, ctx, [])
            self.assertEqual(checkpoint.load(path), (ctx, []))

    def test_resume_skips_completed_and_retries_interrupted_candidate(self):
        import main
        first, second = candidate(), candidate([(block('B','B'),10)])
        prices = DiscoveryPrices({'X (Field-Tested)': Quote(20,1000,'test')})
        client = Mock(key='fake', stats={'requests': 1}, ttl=120)
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch.object(main.config,'DATA_DIR',directory))
            stack.enter_context(patch.object(main,'CSFloatClient',return_value=client))
            stack.enter_context(patch.object(main,'load_skin_data',return_value=[]))
            stack.enter_context(patch.object(main,'group_by_collection_and_rarity',return_value=GROUPED))
            stack.enter_context(patch.object(main.DiscoveryPrices,'load',return_value=prices))
            generate = stack.enter_context(patch.object(main,'generate',return_value=([first,second],{})))
            verify = stack.enter_context(patch.object(main,'verify',side_effect=[(None,'rejected'),RequestBudgetExceeded('cap')]))
            summary = main.main(['20','--no-discord'])
            self.assertEqual(summary['pending_candidates'],1)
            self.assertEqual(checkpoint.load(directory+'/verification_queue.json')[1],[second])
            generate.reset_mock()
            verify.reset_mock(side_effect=True)
            verify.return_value = (None,'rejected')
            summary = main.main(['--resume','--no-discord'])
            generate.assert_not_called()
            self.assertEqual(verify.call_args.args[0],second)
            self.assertEqual(summary['budget'],20)
            self.assertEqual(summary['pending_candidates'],0)
            self.assertEqual(checkpoint.load(directory+'/verification_queue.json')[1],[])

    def test_changed_economic_settings_are_incompatible(self):
        self.assertNotEqual(checkpoint.context(20,None,settings()),
                            checkpoint.context(20,None,settings(SELL_FEE_PERCENT=2)))

    def test_explicit_resume_without_queue_does_not_scan(self):
        import main
        with tempfile.TemporaryDirectory() as directory, patch.object(main.config,'DATA_DIR',directory), \
             patch.object(main,'generate') as generate, patch('sys.stderr'):
            with self.assertRaises(SystemExit): main.main(['--resume'])
            generate.assert_not_called()
