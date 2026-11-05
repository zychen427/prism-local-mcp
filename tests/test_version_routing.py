import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prism_version import parse_title,choose_workflow

class VersionRoutingTests(unittest.TestCase):
 def test_version_titles(self):
  self.assertEqual(parse_title('x.pzf:Data - GraphPad Prism 7.04'),(7,4,None))
  self.assertEqual(parse_title('a.prism - GraphPad Prism 11.0.0 (84)'),(11,0,0))
  self.assertEqual(parse_title('Prism v10.2.0'),(10,2,0))
  self.assertIsNone(parse_title('Prism 7 experiment.xlsx - GraphPad Prism'))
 def test_old_and_new_routes(self):
  r=choose_workflow('Project - GraphPad Prism 7.05',project_format={'native_zip_supported':False})
  self.assertEqual(r['route'],'legacy_pre8');self.assertEqual(r['native_cld'],'not_available_by_version');self.assertFalse(r['native_zip_batch_builder_available'])
  self.assertEqual(choose_workflow('Project - GraphPad Prism 8.4')['route'],'classic_8_9')
  self.assertEqual(choose_workflow('Project - GraphPad Prism 10.1')['route'],'modern_before_cld')
  self.assertEqual(choose_workflow('Project - GraphPad Prism 10')['route'],'prism10_minor_unknown')
  self.assertEqual(choose_workflow('Project - GraphPad Prism 10.2')['route'],'modern_cld_capable')
  self.assertEqual(choose_workflow('Project - GraphPad Prism 11.0')['route'],'modern_cld_capable')
  self.assertFalse(choose_workflow('Project - GraphPad Prism 11.0',project_format={'native_zip_supported':False})['native_zip_batch_builder_available'])
 def test_conflicting_or_unknown_evidence_stops(self):
  self.assertEqual(choose_workflow('GraphPad Prism 7.0',{'version':[11,0,0]})['route'],'version_conflict')
  self.assertEqual(choose_workflow('GraphPad Prism 10.1',{'version':[10,2,0]})['route'],'version_conflict')
  self.assertEqual(choose_workflow('GraphPad Prism')['route'],'version_unknown')
  self.assertEqual(choose_workflow('GraphPad Prism 10',{'version':[10,2,0]})['route'],'modern_cld_capable')

if __name__=='__main__':unittest.main()
