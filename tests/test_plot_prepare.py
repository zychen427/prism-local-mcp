import json, sys, tempfile, unittest
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.formatting.rule import CellIsRule
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prism_plot_prepare import prepare_plot_data

class PlotPreparation(unittest.TestCase):
 def test_red_font_selected_unequal_groups_and_conditional_formatting_guard(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); src=root/'input.xlsx'; wb=Workbook(); ws=wb.active;ws.title='synthetic';ws.append(['group','sample','value'])
   groups=[f'g{i}' for i in range(6)]
   for i,g in enumerate(groups):
    for j in range(3+(i==0)):
     ws.append([g,str(j),10+i+j]); ws.cell(ws.max_row,3).font=Font(color='FFFF0000')
    ws.append([g,'not_selected',999])
   wb.save(src)
   config={'source_file':str(src),'row_levels':['r1','r2','r3'],'column_levels':['c1','c2'],'group_mapping':dict(zip(groups,[[a,b] for a in ['r1','r2','r3'] for b in ['c1','c2']])), 'colour_kind':'font','rgb':['FF0000'],'metrics':[{'name':'x','sheet':'synthetic','first_row':2,'last_row':ws.max_row,'group_column':1,'sample_column':2,'value_column':3}]}
   result=prepare_plot_data(config,root/'out'); audit=json.loads(Path(result['audit_file']).read_text(encoding='utf8')); metric=audit['metrics'][0]
   self.assertEqual([x['n'] for x in metric['summary']],[4,3,3,3,3,3]);self.assertEqual(len(metric['selected']),19)
   self.assertAlmostEqual(metric['summary'][1]['sem'],1/3**.5);self.assertNotIn('999',Path(result['tsv_files'][0]).read_text(encoding='utf-8-sig'))
   self.assertFalse(result['graph_created']);self.assertEqual(result['statistics'],'not performed')
   ws.conditional_formatting.add('C2:C3',CellIsRule(operator='greaterThan',formula=['0'],fill=PatternFill('solid',fgColor='FFFF0000'))); wb.save(src)
   with self.assertRaisesRegex(ValueError,'conditional formatting'):prepare_plot_data(config,root/'guard')
   self.assertEqual(list((root/'guard').iterdir()),[])

if __name__=='__main__':unittest.main()
