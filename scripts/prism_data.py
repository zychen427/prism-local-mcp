"""Read-only Excel preparation and native Prism grouped-table verification."""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,re,statistics,zipfile
from pathlib import Path

def write_json(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
def load_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rgb(cell):
 f=cell.fill
 return f.fgColor.rgb[-6:].upper() if f.patternType=='solid' and f.fgColor.type=='rgb' else None
def survey(source,sheet=None):
 import openpyxl
 wb=openpyxl.load_workbook(source,data_only=True);formula=openpyxl.load_workbook(source,data_only=False)
 names=[sheet] if sheet else wb.sheetnames;result={'source':str(Path(source).resolve()),'sha256':sha(source),'sheets':[]}
 for name in names:
  ws=wb[name];fills={};examples=[];missing=[]
  if ws.max_row*ws.max_column>200000:raise ValueError('Worksheet too large for full survey; inspect a bounded range first.')
  for row in ws:
   for cell in row:
    color=rgb(cell)
    if color:fills[color]=fills.get(color,0)+1
    fc=formula[name][cell.coordinate]
    if fc.data_type=='f' and cell.value is None:missing.append(cell.coordinate)
   if any(c.value is not None for c in row) and (row[0].row<=8 or row[0].row>=ws.max_row-5):
    examples.append({'row':row[0].row,'values':[c.value for c in row],'fills':[rgb(c) for c in row]})
  result['sheets'].append({'name':name,'rows':ws.max_row,'columns':ws.max_column,'merged_ranges':[str(x) for x in ws.merged_cells.ranges],'solid_rgb_counts':fills,'formula_cache_missing':missing,'sample_rows':examples})
 return result

def prepare(config):
 import openpyxl
 source=Path(config['source']).resolve();out=Path(config['output_dir']).resolve();out.mkdir(parents=True,exist_ok=True)
 wb=openpyxl.load_workbook(source,data_only=True);fw=openpyxl.load_workbook(source,data_only=False);ws=wb[config['sheet']];fws=fw[config['sheet']]
 start,end=config['data_start_row'],config['data_end_row'];gc=config['group_column'];rc=config.get('replicate_column');metrics=config['metrics'];groups=config['groups'];rule=config['exclude']
 if start<1 or end<start or not metrics or not groups or len({m['label'] for m in metrics})!=len(metrics):raise ValueError('Use a valid record range and unique nonempty metric labels/groups.')
 if len({g['display_name'] for g in groups})!=len(groups):raise ValueError('Display group names must be unique.')
 if rule.get('apply','cell') not in ('row','cell'):raise ValueError('Exclusion apply must be row or cell.')
 if rule['mode'] not in ('none','cell_fill'):raise ValueError('Only explicitly configured none/cell_fill exclusion is supported.')
 if rule['mode']=='cell_fill' and not rule.get('reason'):raise ValueError('Record the source/user exclusion reason before applying color exclusions.')
 colors={x[-6:].upper() for x in rule.get('rgb',[])};rowcols=rule.get('color_columns',[m['column'] for m in metrics])
 if len({g['source_name'] for g in groups})!=len(groups):raise ValueError('Duplicate source group names.')
 bygroup={g['source_name']:[] for g in groups}
 for r in range(start,end+1):
  name=ws.cell(r,gc).value
  if name not in bygroup:raise ValueError(f'Unexpected or missing group at {ws.cell(r,gc).coordinate}: {name!r}')
  bygroup[name].append(r)
 if any(not v for v in bygroup.values()):raise ValueError('Configured group has no records.')
 reps=max(map(len,bygroup.values()));raw=[];summary=[];table=[]
 header=['']
 for g in groups:header.extend([g['display_name']]+['']*(reps-1))
 table.append(header)
 for metric in metrics:
  label=metric['label'];line=[label];stats=[]
  if '\t' in label or '\n' in label:raise ValueError('Metric label contains a tab/newline.')
  for gi,g in enumerate(groups):
   valid=[]
   for ri in range(reps):
    rows=bygroup[g['source_name']];r=rows[ri] if ri<len(rows) else None;cell=ws.cell(r,metric['column']) if r else None;value=cell.value if cell else None
    if cell and value is None and fws[cell.coordinate].data_type=='f':raise ValueError(f'Missing cached formula result: {cell.coordinate}; recalculate a separate Excel copy first.')
    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):raise ValueError(f'Nonfinite/nonnumeric measurement: {cell.coordinate}: {value!r}')
    excluded=False
    if cell and rule['mode']=='cell_fill':
     excluded=any(rgb(ws.cell(r,c)) in colors for c in rowcols) if rule.get('apply','cell')=='row' else rgb(cell) in colors
    text='' if value is None else format(value,'.17g')+('*' if excluded else '');line.append(text)
    raw.append({'metric':label,'group_index':gi,'group':g['source_name'],'replicate_index':ri,'replicate':ws.cell(r,rc).value if r and rc else ri+1,'source_cell':cell.coordinate if cell else None,'value':value,'excluded':excluded,'padding':r is None})
    if value is not None and not excluded:valid.append(value)
   mean=statistics.mean(valid) if valid else None;sd=statistics.stdev(valid) if len(valid)>1 else None
   stats.append({'group_index':gi,'group':g['source_name'],'n':len(valid),'mean':mean,'sd':sd,'sem':sd/math.sqrt(len(valid)) if sd is not None else None,'label':f'{mean:.2f}' if mean is not None else None})
  table.append(line);summary.append({'metric':label,'statistics':stats})
 for row in table:
  if any('\t' in s or '\n' in s or '\r' in s for s in row):raise ValueError('A label contains TSV control characters.')
 (out/'prism_import.tsv').write_text('\n'.join('\t'.join(r) for r in table)+'\n',encoding='utf-8-sig')
 audit={'schema_version':1,'source':str(source),'sha256':sha(source),'sheet':ws.title,'groups':groups,'replicates':reps,'metrics':metrics,'exclude':rule,'summary':summary,'raw':raw}
 write_json(out/'audit.json',audit)
 return {'audit':str(out/'audit.json'),'import':str(out/'prism_import.tsv'),'metrics':len(metrics),'groups':len(groups),'replicates':reps,'valid_n':[[s['n'] for s in m['statistics']] for m in summary]}

def indices(value):
 out=[]
 for part in re.split(r'[,; ]+',str(value).strip()):
  if not part:continue
  if not re.fullmatch(r'\d+(~\d+)?',part):raise ValueError(f'Unsupported Prism range: {value}')
  bounds=part.split('~');out.extend(range(int(bounds[0]),int(bounds[-1])+1))
 return out

def verify(audit_path,project,table_title=None,table_uid=None,baseline=None,new_graphs=1):
 a=load_json(audit_path);errors=[];verified=0;labels=[];maximum=0.0
 with zipfile.ZipFile(project) as z:
  d=json.loads(z.read('document.json'));tables=[json.loads(z.read(f'data/sheets/{u}/sheet.json')) for u in d['sheets'].get('data',[])]
  found=[s for s in tables if (s['uid']==table_uid if table_uid else s.get('title')==table_title)]
  if len(found)!=1:raise ValueError('Select exactly one data table by UID or a unique title.')
  s=found[0];t=s['table'];rows=list(csv.reader(io.StringIO(z.read(f"data/tables/{t['uid']}/data.csv").decode('utf-8-sig'))))
  if t.get('dataFormat')!='y_replicates':raise ValueError('Verification supports grouped raw y_replicates only.')
  if len(t['dataSets'])!=len(a['groups']) or t['replicatesCount']!=a['replicates'] or len(rows)!=len(a['metrics']):raise ValueError('Native table dimensions differ from audit.')
  masks=[]
  for uid,g in zip(t['dataSets'],a['groups']):
   ds=json.loads(z.read(f'data/sets/{uid}.json'));mask=set()
   if ds.get('title')!=g['display_name']:errors.append(f'Dataset title differs: {ds.get("title")}')
   for rr in ds.get('replicate ranges',[]):
    rep=rr['replicate'];cols=indices(rr['range'])
    if 'EXCLUDED' in rep.get('commonAttributes',[]):
     mask.update((r,c) for r in range(rep.get('firstRow',0),rep['lastRow']+1) for c in cols)
    for attrs in rep.get('cellAttributes',[]):
     if 'EXCLUDED' in attrs['attributes']:mask.update((r,c) for r in indices(attrs['rows']) for c in cols)
   masks.append(mask)
  raw={(r['metric'],r['group_index'],r['replicate_index']):r for r in a['raw']};nr=a['replicates']
  for mi,(row,metric) in enumerate(zip(rows,a['metrics'])):
   if row[0]!=metric['label']:errors.append(f'Row label differs at row {mi}: {row[0]}');continue
   cells=row[1:];cells+=['']*(len(a['groups'])*nr-len(cells))
   if len(cells)!=len(a['groups'])*nr:errors.append('Unexpected trailing columns');continue
   for gi,g in enumerate(a['groups']):
    valid=[]
    for ri in range(nr):
     original=raw[(metric['label'],gi,ri)];v=cells[gi*nr+ri];value=float(v) if v.strip() else None;expected=original['value']
     if expected is None:
      if value is not None:errors.append(f'Blank changed to a value: {original["source_cell"]}')
      continue
     if value is None:errors.append(f'Lost numeric value: {original["source_cell"]}');continue
     delta=abs(value-expected);maximum=max(maximum,delta)
     if not math.isclose(value,expected,rel_tol=1e-14,abs_tol=1e-14):errors.append(f'Numeric mismatch: {original["source_cell"]}')
     if ((mi,ri) in masks[gi])!=original['excluded']:errors.append(f'Exclusion mismatch: {original["source_cell"]}')
     if not original['excluded']:valid.append(value)
     verified+=1
    expected_stats=a['summary'][mi]['statistics'][gi];label=f'{statistics.mean(valid):.2f}' if valid else None
    if len(valid)!=expected_stats['n'] or label!=expected_stats['label']:errors.append(f'Statistical mismatch: {metric["label"]}, {g["display_name"]}')
    labels.append({'metric':metric['label'],'group':g['display_name'],'n':len(valid),'label':label})
  if baseline:
   before=load_json(baseline)['sheet_uids']
   for key in ['data','graphs']:
    if not set(before.get(key,[])).issubset(d['sheets'].get(key,[])):errors.append(f'Original {key} sheet missing')
   if len(d['sheets']['data'])!=len(before.get('data',[]))+1:errors.append('Expected exactly one new data table')
   if len(d['sheets']['graphs'])!=len(before.get('graphs',[]))+new_graphs:errors.append('Unexpected number of new graphs')
 source_ok=sha(a['source'])==a['sha256']
 if not source_ok:errors.append('Source workbook SHA256 changed')
 return {'passed':not errors,'source_unchanged':source_ok,'table_uid':s['uid'],'raw_values_verified':verified,'max_numeric_difference':maximum,'mean_labels_verified':len(labels),'labels':labels,'errors':errors,'visual_check_required':True}

def verify_export(audit_path,export_file):
 """Version-independent fallback for native tab-delimited ExportTable output."""
 a=load_json(audit_path);blob=Path(export_file).read_bytes();text=None
 for enc in (['utf-16'] if blob[:2] in (b'\xff\xfe',b'\xfe\xff') else ['utf-8-sig','gb18030']):
  try:text=blob.decode(enc);break
  except UnicodeError:pass
 if text is None:raise ValueError('Cannot decode native table export; inspect its actual encoding.')
 parsed=list(csv.reader(io.StringIO(text),delimiter='\t'));wanted=[m['label'] for m in a['metrics']];rows=[r for r in parsed if r and r[0] in wanted]
 if [r[0] for r in rows]!=wanted:raise ValueError('Native export metric rows differ; export the complete intended table.')
 errors=[];labels=[];nr=a['replicates'];raw={(r['metric'],r['group_index'],r['replicate_index']):r for r in a['raw']};maximum=0.;verified=0
 for mi,row in enumerate(rows):
  cells=row[1:];cells+=['']*(len(a['groups'])*nr-len(cells))
  if len(cells)!=len(a['groups'])*nr:errors.append('Export columns differ');continue
  for gi,g in enumerate(a['groups']):
   valid=[]
   for ri in range(nr):
    original=raw[(row[0],gi,ri)];v=cells[gi*nr+ri].strip();excluded=v.endswith('*');value=float(v.rstrip('*')) if v.rstrip('*') else None;expected=original['value']
    if expected is None:
     if value is not None:errors.append(f'Blank changed: {original["source_cell"]}')
     continue
    if value is None:errors.append(f'Lost value: {original["source_cell"]}');continue
    delta=abs(value-expected);maximum=max(maximum,delta)
    if not math.isclose(value,expected,rel_tol=1e-14,abs_tol=1e-14):errors.append(f'Value/precision mismatch: {original["source_cell"]}')
    if excluded!=original['excluded']:errors.append(f'Exclusion marker mismatch: {original["source_cell"]}')
    if not excluded:valid.append(value)
    verified+=1
   label=f'{statistics.mean(valid):.2f}' if valid else None;expected_stats=a['summary'][mi]['statistics'][gi]
   if label!=expected_stats['label'] or len(valid)!=expected_stats['n']:errors.append(f'Statistical mismatch: {row[0]}, {g["display_name"]}')
   labels.append({'metric':row[0],'group':g['display_name'],'n':len(valid),'label':label})
 source_ok=sha(a['source'])==a['sha256']
 if not source_ok:errors.append('Source SHA256 changed')
 return {'passed':not errors,'verification_mode':'native-tab-export','source_unchanged':source_ok,'raw_values_verified':verified,'mean_labels_verified':len(labels),'max_numeric_difference':maximum,'errors':errors,'labels':labels,'uid_preservation_verified':False,'visual_check_required':True,'precision_note':'If native export rounds values, increase export/display precision or use supported native raw format; matching labels alone does not prove unchanged raw values.'}

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 s=sub.add_parser('survey');s.add_argument('--source',required=True);s.add_argument('--sheet');s.add_argument('--output',required=True)
 s=sub.add_parser('prepare');s.add_argument('--config',required=True)
 s=sub.add_parser('verify');s.add_argument('--audit',required=True);s.add_argument('--project',required=True);s.add_argument('--table-title');s.add_argument('--table-uid');s.add_argument('--baseline');s.add_argument('--new-graphs',type=int,default=1);s.add_argument('--output',required=True)
 s=sub.add_parser('verify-export');s.add_argument('--audit',required=True);s.add_argument('--export-file',required=True);s.add_argument('--output',required=True)
 x=p.parse_args()
 if x.command=='survey':result=survey(x.source,x.sheet);write_json(x.output,result)
 elif x.command=='prepare':result=prepare(load_json(x.config))
 elif x.command=='verify-export':result=verify_export(x.audit,x.export_file);write_json(x.output,result)
 else:result=verify(x.audit,x.project,x.table_title,x.table_uid,x.baseline,x.new_graphs);write_json(x.output,result)
 print(json.dumps({k:v for k,v in result.items() if k not in ('labels','sheets')},ensure_ascii=False))
 if result.get('passed') is False:raise SystemExit(1)
if __name__=='__main__':main()
