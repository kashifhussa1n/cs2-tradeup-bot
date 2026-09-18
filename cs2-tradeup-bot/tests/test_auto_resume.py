import tempfile
import unittest
from unittest.mock import Mock
from src.auto_resume import run
from src.storage import write_json, read_json
from test_pipeline import Clock, settings


def result(reason=None, pending=0):
    return {'budget':20,'stop_reason':reason,'pending_candidates':pending}


class AutoResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock=Clock()
        self.cfg=settings(DATA_DIR=self.temp.name,AUTO_RESUME=True,
                          AUTO_RESUME_DELAY_SECONDS=300,AUTO_MAX_BATCHES=10)

    def test_cap_wait_then_resume_without_new_scan(self):
        batch=Mock(side_effect=[result('RequestBudgetExceeded',2),result()])
        run(batch,self.cfg,['20','--no-discord'],self.clock,self.clock.sleep)
        self.assertEqual(batch.call_args_list[1].args[0],['--resume','--no-discord'])
        self.assertEqual(self.clock(),1300)
        self.assertEqual(read_json(self.temp.name+'/auto_resume.json',{})['next_run_at'],0)

    def test_persisted_cooldown_before_first_batch(self):
        write_json(self.temp.name+'/csfloat_cooldown.json',{'blocked_until':1800})
        times=[]
        def batch(args): times.append(self.clock());return result()
        run(batch,self.cfg,['--resume','--no-discord'],self.clock,self.clock.sleep)
        self.assertEqual(times,[1800])

    def test_startup_cooldown_keeps_budget_and_rarity(self):
        batch=Mock(side_effect=[result('CooldownActive'),result()])
        run(batch,self.cfg,['--rarity','Restricted','--no-discord'],self.clock,self.clock.sleep)
        self.assertEqual(batch.call_args_list[1].args[0],['20','--no-discord','--rarity','Restricted'])

    def test_no_progress_stops_with_queue_saved(self):
        batch=Mock(return_value=result('RequestBudgetExceeded',2))
        out=run(batch,self.cfg,['--no-discord'],self.clock,self.clock.sleep)
        self.assertEqual(batch.call_count,3)
        self.assertIn('no queue progress',out['auto_stop'])

    def test_offline_and_disabled_never_loop(self):
        for enabled,args in [(False,['--no-discord']),(True,['--offline'])]:
            self.cfg.AUTO_RESUME=enabled
            batch=Mock(return_value=result('RequestBudgetExceeded',2))
            run(batch,self.cfg,args,self.clock,self.clock.sleep)
            self.assertEqual(batch.call_count,1)
            self.assertEqual(self.clock(),1000)

    def test_auth_or_transport_errors_do_not_loop(self):
        batch=Mock(return_value=result('MarketUnavailable',2))
        run(batch,self.cfg,['--no-discord'],self.clock,self.clock.sleep)
        self.assertEqual(batch.call_count,1)

    def test_batch_limit(self):
        self.cfg.AUTO_MAX_BATCHES=2
        batch=Mock(side_effect=[result('RequestBudgetExceeded',3),result('RequestBudgetExceeded',2)])
        out=run(batch,self.cfg,['--no-discord'],self.clock,self.clock.sleep)
        self.assertIn('batch limit',out['auto_stop'])
