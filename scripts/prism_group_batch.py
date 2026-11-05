"""Prepare a conservative grouped graph batch plan; no implicit execution."""
import csv,hashlib,io,json,math,shutil,zipfile,time
from pathlib import Path
from prism_project import inspect,quote,write_script

def build(audit_file,template_file,graph_index,output_dir,name='grouped_batch'):
 audit_path=Path(audit_file).resolve();template=Path(template_file).resolve();root=Path(output_dir).resolve()
 if not root.is_dir() or any(root.iterdir()):raise ValueError('Use an existing empty output directory.')
 if not str(root).isascii():raise ValueError('Prism script import/export staging path must be ASCII on this validated Windows workflow.')
 if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name):raise ValueError('name must be ASCII letters, digits, hyphen or underscore.')
 audit=json.loads(audit_path.read_text(encoding='utf8'));source=Path(audit['source'])
 if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=audit['sha256']:raise ValueError('Source workbook is missing or changed since audit.')
 b=inspect(template)
 if not b.get('native_zip_supported'):raise ValueError('Batch builder needs a supported Prism ZIP template; check target version and native template.')
 if b['sheet_uids'].get('analyses'):raise ValueError('Template has analysis families. This batch builder supports simple unanalysed grouped graphs only.')
 ref=next((x for x in b['sheets']['graphs'] if x['index']==graph_index),None)
 if not ref:raise ValueError('Unknown reference graph index.')
 linked=[s for s in b['sheets']['data'] if set(ref['input_datasets']).intersection(s.get('dataset_uids',[]))]
 if len(linked)!=1 or linked[0].get('format')!='grouped' or linked[0].get('data_format')!='y_replicates':raise ValueError('Reference graph must directly use one simple grouped raw-replicate table.')
 metrics=audit['metrics'];rows=audit['row_levels'];cols=audit['column_levels']
 if not 1<=len(metrics)<=50:raise ValueError('Batch requires 1–50 metrics.')
 if linked[0]['dataset_count']!=len(cols):raise ValueError('Reference graph dataset count differs from audit column factor count.')
 commands=[];inputs=[]; outputs=[];d0=len(b['sheet_uids']['data']);g0=len(b['sheet_uids']['graphs'])
 for i,m in enumerate(metrics,1):
  source_tsv=(audit_path.parent/m['file']).resolve()
  if source_tsv.parent!=audit_path.parent or not source_tsv.is_file():raise ValueError('Audit TSV must reside alongside its audit file.')
  content=source_tsv.read_text(encoding='utf-8-sig');parsed=list(csv.reader(io.StringIO(content),delimiter='\t'));reps=int(m['replicates_columns'])
  if len(parsed)!=len(rows)+1 or parsed[0]!=['Factor']+sum(([c]+['']*(reps-1) for c in cols),[]):raise ValueError('TSV header or rows differ from audited factors.')
  for j,row in enumerate(parsed[1:]):
   if row[0]!=rows[j] or len(row)!=1+len(cols)*reps:raise ValueError('TSV shape or factor labels differ from audit.')
   for k,col in enumerate(cols):
    expected=[x['value'] for x in m['selected'] if x['factor_row']==rows[j] and x['factor_column']==col]
    vals=row[1+k*reps:1+(k+1)*reps]; actual=[float(v) for v in vals if v!='']
    if len(actual)!=len(expected) or any(not math.isclose(a,e,rel_tol=1e-14,abs_tol=1e-14) for a,e in zip(actual,expected)):raise ValueError('TSV values differ from audit.')
  target=root/f'{name}_data_{i:03}.tsv';inputs.append((source_tsv,target));png=root/f'{name}_graph_{i:03}.png';outputs.append(str(png))
  title=str(m['name']);commands += [f'GoTo G {graph_index}',f'DuplicateFamily {quote(name+str(i)+"_")} CLEAR',f'GoTo D {d0+i}',f'SetSheetTitle {quote(title)}',f'SetYReplicates {reps}',f'Import {quote(target)}, 0, -1',f'GoTo G {g0+i}',f'SetSheetTitle {quote(title)}',f'ExportPNG {quote(png)}']
 project=root/f'{name}.prism';commands += [f'Save {quote(project)}','CloseScriptDialog']
 for src,dst in inputs:shutil.copyfile(src,dst)
 script=write_script(root/f'{name}.pzc',commands)
 plan={'status':'planned_not_executed','commands':commands,'script':script,'project':str(project),'graphs':outputs,'template_file':str(template),'template_sha256':b['sha256'],'audit':str(audit_path),'expected_new_tables':len(metrics),'expected_new_graphs':len(metrics),'style':'copied from reference; user must verify graph type and SEM before execution','warning':'No automatic retry. Native data and every graph must be inspected, saved and reopened.'}
 (root/f'{name}_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
 return plan

def verify_saved(plan,audit_file):
 audit_path=Path(audit_file).resolve();audit=json.loads(audit_path.read_text(encoding='utf8'));path=Path(plan['project'])
 source=Path(audit['source'])
 if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=audit['sha256']:raise RuntimeError('Source workbook changed during batch execution.')
 if hashlib.sha256(Path(plan['template_file']).read_bytes()).hexdigest()!=plan['template_sha256']:raise RuntimeError('Template changed during batch execution.')
 if not path.is_file():raise RuntimeError('Saved project was not created.')
 saved=inspect(path); b=inspect(plan['template_file'])
 for category in ('data','graphs'):
  if not set(b['sheet_uids'][category]).issubset(saved['sheet_uids'][category]):raise RuntimeError('Original template sheets changed.')
  if len(saved['sheet_uids'][category])!=len(b['sheet_uids'][category])+len(audit['metrics']):raise RuntimeError(f'Unexpected {category} sheet count.')
 with zipfile.ZipFile(path) as z:
  for i,m in enumerate(audit['metrics']):
   table=saved['sheets']['data'][len(b['sheet_uids']['data'])+i]
   raw=list(csv.reader(io.StringIO(z.read('data/tables/'+table['table_uid']+'/data.csv').decode('utf-8-sig'))))
   expected=list(csv.reader(io.StringIO((audit_path.parent/m['file']).read_text(encoding='utf-8-sig')),delimiter='\t'))[1:]
   if len(raw)!=len(expected):raise RuntimeError('Saved table row count differs from audit.')
   for a,e in zip(raw,expected):
    a+=['']*(len(e)-len(a))
    if len(a)!=len(e) or a[0]!=e[0]:raise RuntimeError('Saved labels or table width differ from audit.')
    for av,ev in zip(a[1:],e[1:]):
     if (not av)!=(not ev) or (av and not math.isclose(float(av),float(ev),rel_tol=1e-13,abs_tol=1e-13)):raise RuntimeError('Saved raw values differ from audit.')
 for img in plan['graphs']:
  if not Path(img).is_file() or Path(img).stat().st_size==0:raise RuntimeError('Graph export missing or empty.')
 return {'raw_values_verified':True,'graph_files_exist':True,'visual_check_required':True,'reopen_required':True}
