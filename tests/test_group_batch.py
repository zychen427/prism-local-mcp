import csv,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prism_group_batch import build
class GroupBatch(unittest.TestCase):
 def test_plan_and_input_tamper_guard(self):
  with tempfile.TemporaryDirectory(prefix='prism-test-') as d:
   p=Path(d);src=p/'source.xlsx';src.write_bytes(b'synthetic'); template=p/'test.prism';template.write_bytes(b'fixture')
   rows=['a','b','c'];cols=['one','two'];records=[]
   tsv='Factor\tone\t\ttwo\t\n'
   for i,a in enumerate(rows):
    vals=[]
    for j,b in enumerate(cols):
     v=[i+j+1,i+j+2];vals+=list(map(str,v));records += [{'factor_row':a,'factor_column':b,'value':x} for x in v]
    tsv+=a+'\t'+'\t'.join(vals)+'\n'
   (p/'metric.tsv').write_text(tsv,encoding='utf8')
   audit={'source':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'row_levels':rows,'column_levels':cols,'metrics':[{'name':'measure','file':'metric.tsv','replicates_columns':2,'selected':records}]}
   (p/'audit.json').write_text(json.dumps(audit),encoding='utf8');out=p/'out';out.mkdir()
   baseline={'native_zip_supported':True,'sha256':'abc','sheet_uids':{'data':['d'],'graphs':['g']},'sheets':{'graphs':[{'index':1,'input_datasets':['s']}],'data':[{'format':'grouped','data_format':'y_replicates','dataset_uids':['s'],'dataset_count':2}]}}
   with patch('prism_group_batch.inspect',return_value=baseline):
    r=build(p/'audit.json',template,1,out);self.assertEqual(r['status'],'planned_not_executed');self.assertEqual(r['expected_new_graphs'],1)
    (p/'metric.tsv').write_text(tsv.replace('\t1\t','\t99\t',1),encoding='utf8');bad=p/'bad';bad.mkdir()
    with self.assertRaisesRegex(ValueError,'differ from audit'):build(p/'audit.json',template,1,bad)
    self.assertFalse(any(bad.iterdir()))
if __name__=='__main__':unittest.main()
