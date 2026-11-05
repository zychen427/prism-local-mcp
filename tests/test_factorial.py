import csv,json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from scipy.stats import f,tukey_hsd
from openpyxl import Workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prism_factorial import prepare, combine_audits, annotation_plan, verify_native_export

class FactorialTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.xlsx=self.root/'synthetic.xlsx'
  w=Workbook();s=w.active;s.title='Raw';s.append(['Group','Sample','Synthetic response'])
  self.cells=[];mapping={}
  for di,d in enumerate(('A','B','C')):
   for ti,t in enumerate(('yes','no')):
    label=f'{d}-{t}';mapping[label]=[d,t];cell=[]
    for r in range(4):
     value=10+di*.8+ti*.3+(di*ti)*.12+[-.8,-.1,.2,.7][r]*(1+.1*ti);s.append([label,str(r+1),value]);cell.append(value)
    self.cells.append(cell)
  w.save(self.xlsx)
  self.cfg={'source_file':str(self.xlsx),'sheet':'Raw','first_row':2,'last_row':25,'group_column':1,'sample_column':2,
            'diets':['A','B','C'],'treatments':['yes','no'],'group_mapping':mapping,'independent_observations':True,
            'expected_n':4,'metrics':[{'name':'response unit','column':3}]}
 def tearDown(self):self.tmp.cleanup()
 def test_statistics_against_ols_and_scipy_tukey(self):
  result=prepare(self.cfg,self.root/'out');a=json.loads(Path(result['audit_file']).read_text(encoding='utf8'));m=a['metrics'][0]
  y=np.array(self.cells).reshape(-1);X=[]
  for d in range(3):
   for t in range(2):
    a1=1 if d==0 else -1 if d==2 else 0;a2=1 if d==1 else -1 if d==2 else 0;b=1 if t==0 else -1
    X.extend([[1,a1,a2,b,a1*b,a2*b]]*4)
  X=np.asarray(X,float)
  def rss(mat):return np.sum((y-mat@np.linalg.lstsq(mat,y,rcond=None)[0])**2)
  full=rss(X);mse=full/18
  for cols,df,key in [([1,2],2,'diet'),([3],1,'treatment'),([4,5],2,'interaction')]:
   p=f.sf(((rss(np.delete(X,cols,axis=1))-full)/df)/mse,df,18);self.assertAlmostEqual(p,m['p_values'][key],places=10)
  tuk=tukey_hsd(*self.cells);p=iter(m['tukey'])
  for i in range(6):
   for j in range(i+1,6):self.assertAlmostEqual(next(p)['p_adjusted'],tuk.pvalue[i,j],places=10)
  with open(m['tsv'],encoding='utf-8-sig',newline='') as fobj: rows=list(csv.reader(fobj,delimiter='\t'))
  self.assertEqual((len(rows),len(rows[1])),(4,9));self.assertEqual(m['n'],4)
 def test_missing_or_unbalanced_is_atomic(self):
  bad={**self.cfg,'last_row':24};out=self.root/'bad'
  with self.assertRaisesRegex(ValueError,'Balanced'):prepare(bad,out)
  self.assertFalse(list(out.glob('metric_*.tsv')));self.assertFalse((out/'factorial_audit.json').exists())
 def test_explicit_exclusions_remain_starred_and_counts_are_verified(self):
  cfg={**self.cfg,'expected_n':3,'exclude_samples':[{'group':g,'sample':'4','reason':'documented'} for g in self.cfg['group_mapping']]}
  r=prepare(cfg,self.root/'excluded');a=json.loads(Path(r['audit_file']).read_text(encoding='utf8'));self.assertEqual(a['metrics'][0]['n'],3)
  self.assertEqual(Path(a['metrics'][0]['tsv']).read_text(encoding='utf-8-sig').count('*'),6)
 def test_never_overwrites_and_rejects_invalid_design(self):
  out=self.root/'out';prepare(self.cfg,out)
  with self.assertRaises(FileExistsError):prepare(self.cfg,out)
  with self.assertRaisesRegex(ValueError,'independent'):prepare({**self.cfg,'independent_observations':False},self.root/'other')
  with self.assertRaisesRegex(ValueError,'mapping'):prepare({**self.cfg,'group_mapping':{}},self.root/'third')
 def test_combine_and_annotation(self):
  a=prepare(self.cfg,self.root/'a');b=prepare({**self.cfg,'metrics':[{'name':'other','column':3}]},self.root/'b')
  merged=combine_audits([a['audit_file'],b['audit_file']],self.root/'merged.json')
  self.assertEqual(merged['metric_count'],2)
  plan=annotation_plan(merged['audit_file'],'response unit');self.assertEqual(len(plan['items']),1)
  self.assertIn('P (Interaction)',plan['items'][0]['p_text']);self.assertIn('static',plan['warning'])
  c=prepare({**self.cfg,'alpha':.01,'metrics':[{'name':'third','column':3}]},self.root/'c')
  with self.assertRaisesRegex(ValueError,'different factor'):combine_audits([a['audit_file'],c['audit_file']],self.root/'bad.json')
 def test_old_version_native_export_checks_headers_exclusions_and_precision(self):
  cfg={**self.cfg,'expected_n':3,'exclude_samples':[{'group':g,'sample':'4','reason':'documented'} for g in self.cfg['group_mapping']]}
  r=prepare(cfg,self.root/'prep');a=json.loads(Path(r['audit_file']).read_text(encoding='utf8'));tsv=Path(a['metrics'][0]['tsv'])
  report=verify_native_export(r['audit_file'],'response unit',tsv,self.root/'verify.json')
  self.assertTrue(report['passed'],report);self.assertEqual(report['raw_values_checked'],24);self.assertFalse(report['analysis_results_verified'])
  wrong=self.root/'wrong.tsv';wrong.write_text(tsv.read_text(encoding='utf-8-sig').replace('yes','swapped',1),encoding='utf-8-sig')
  self.assertFalse(verify_native_export(r['audit_file'],'response unit',wrong,self.root/'wrong.json')['passed'])
  wrong.write_text(tsv.read_text(encoding='utf-8-sig').replace('*','',1),encoding='utf-8-sig')
  self.assertFalse(verify_native_export(r['audit_file'],'response unit',wrong,self.root/'wrong2.json')['passed'])
  rows=list(csv.reader(tsv.read_text(encoding='utf-8-sig').splitlines(),delimiter='\t'));rows[1][1]='9.3'
  with wrong.open('w',encoding='utf-8-sig',newline='') as fobj:csv.writer(fobj,delimiter='\t',lineterminator='\n').writerows(rows)
  self.assertFalse(verify_native_export(r['audit_file'],'response unit',wrong,self.root/'wrong3.json')['passed'])

if __name__=='__main__':unittest.main()
