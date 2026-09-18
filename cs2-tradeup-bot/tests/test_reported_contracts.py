"""The screenshot and alert use different floats; do not 'fix' correct math."""
import unittest
from src.tradeup_calc import InputItem, enumerate_outcomes
from src.strategy import qualifies
from test_pipeline import skin, settings


class ReportedContractTests(unittest.TestCase):
    def test_actual_ventilator_floats_cross_factory_new_boundary(self):
        grouped={'Gamma 2':{'Mil-Spec Grade':[skin('G3SG1 | Ventilator',0,.45)],
                            'Restricted':[skin('Glock-18 | Weasel',0,1)]}}
        values=[.050448548,.045604650,.043176427,.036480926,.037517551,
                .037690099,.021832336,.028855754,.004643262,.008336562]
        actual=enumerate_outcomes([InputItem('G3SG1 | Ventilator','Gamma 2',f,1.25) for f in values],grouped)
        screenshot=enumerate_outcomes([InputItem('G3SG1 | Ventilator','Gamma 2',.05,.8)]*10,grouped)
        self.assertEqual(actual[0].wear,'Factory New')
        self.assertAlmostEqual(actual[0].output_float,.069908026,places=8)
        self.assertEqual(screenshot[0].wear,'Minimal Wear')
        self.assertAlmostEqual(screenshot[0].output_float,.111111111,places=8)
