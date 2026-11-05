import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prism_graph_preflight import preflight
class GraphPreflight(unittest.TestCase):
 def test_zero_replicates_are_one_x_row_and_are_preserved(self):
  pts=[{'concentration':0,'response':y} for y in (97,100,103)]+[{'concentration':1,'response':80}]
  r=preflight(pts); self.assertEqual((r['zero_concentration_rows'],r['zero_concentration_observations']),(1,3))
  self.assertTrue(r['prism_warning_likely']);self.assertFalse(r['data_changed']);self.assertFalse(r['fit_run'])
  self.assertFalse(preflight(pts,'linear')['prism_warning_likely']);self.assertTrue(preflight(pts,'linear')['zero_eligible_for_axis'])
 def test_no_zero_and_invalid_inputs(self):
  r=preflight([{'concentration':2,'response':8}]);self.assertFalse(r['prism_warning_likely']);self.assertIsNone(r['zero_eligible_for_axis'])
  for pts in ([],[{'concentration':-1,'response':2}],[{'concentration':float('nan'),'response':2}]):
   with self.assertRaises(ValueError):preflight(pts)
if __name__=='__main__':unittest.main()
