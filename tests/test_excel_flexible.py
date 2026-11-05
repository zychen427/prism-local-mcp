import json,sys,tempfile,unittest
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prism_excel_flexible import discover,prepare
from prism_group_batch import build

class FlexibleExcelTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'input.xlsx';w=Workbook();s=w.active;s.title='long';s.append(['Row factor','Col factor','Sample','value'])
  for a in ['A','B','C']:
   for b in ['L','H']:
    for k in range(3):
     s.append([a,b,f'{a}{b}{k}',str(10+len(s._cells)%5) if k==0 else 10+k]);s.cell(s.max_row,4).font=Font(color='FFFF0000')
  t=w.create_sheet('wide');t.append(['sample','AL','AH','BL','BH','CL','CH'])
  for k in range(3):t.append([f'id{k}',1+k,2+k,3+k,4+k,5+k,6+k])
  w.save(self.source);self.hash=discover(self.source)['sha256']
 def tearDown(self):self.tmp.cleanup()
 def base(self):return {'source_file':str(self.source),'expected_sha256':self.hash,'row_levels':['A','B','C'],'column_levels':['L','H']}
 def out(self):p=self.root/'out';p.mkdir();return p
 def test_long_numeric_text_and_colour(self):
  c=self.base();c.update(selection={'mode':'font','rgb':['FF0000']},metrics=[{'name':'m','sheet':'long','layout':'long','first_row':2,'last_row':19,'row_factor_column':1,'column_factor_column':2,'sample_column':3,'value_column':4}]);result=prepare(c,self.out());a=json.loads(Path(result['audit_file']).read_text(encoding='utf8'));self.assertEqual(len(a['metrics'][0]['selected']),18);self.assertEqual(sum(x['source_type']=='numeric_text' for x in a['metrics'][0]['selected']),6)
 def test_wide_unequal_n(self):
  from openpyxl import load_workbook
  w=load_workbook(self.source);w['wide']['B4']=None;w.save(self.source);self.hash=discover(self.source)['sha256']
  c=self.base();cells=[(a,b) for a in ['A','B','C'] for b in ['L','H']];c.update(metrics=[{'name':'m','sheet':'wide','layout':'wide','first_row':2,'last_row':4,'sample_column':1,'columns':[{'column':i+2,'factor':list(x)} for i,x in enumerate(cells)]}]);r=prepare(c,self.out());a=json.loads(Path(r['audit_file']).read_text());self.assertEqual([x['n'] for x in a['metrics'][0]['summary']],[2,3,3,3,3,3])
 def test_merged_factor_labels(self):
  from openpyxl import load_workbook
  w=load_workbook(self.source);w['long'].merge_cells('A2:A7');w.save(self.source);self.hash=discover(self.source)['sha256'];c=self.base();c.update(metrics=[{'name':'m','sheet':'long','layout':'long','first_row':2,'last_row':19,'row_factor_column':1,'column_factor_column':2,'sample_column':3,'value_column':4}]);r=prepare(c,self.out());a=json.loads(Path(r['audit_file']).read_text());self.assertEqual(a['metrics'][0]['selected'][5]['factor_source_cells'][0],'A2')
 def test_source_change_rejected(self):
  c=self.base();c['expected_sha256']='bad';c['metrics']=[]
  with self.assertRaisesRegex(ValueError,'SHA-256'):prepare(c,self.out())
 def test_ambiguous_unit_rejected(self):
  from openpyxl import load_workbook
  w=load_workbook(self.source);w['wide']['B2']='5 mg';w.save(self.source);self.hash=discover(self.source)['sha256'];c=self.base();cells=[(a,b) for a in ['A','B','C'] for b in ['L','H']];c.update(metrics=[{'name':'m','sheet':'wide','layout':'wide','first_row':2,'last_row':4,'columns':[{'column':i+2,'factor':list(x)} for i,x in enumerate(cells)]}]);o=self.out()
  with self.assertRaisesRegex(ValueError,'units'):prepare(c,o)
  self.assertEqual(list(o.iterdir()),[])
if __name__=='__main__':unittest.main()
