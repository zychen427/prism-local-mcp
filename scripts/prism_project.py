"""Inspect and prepare native Prism projects. No binary graph-format edits."""
from __future__ import annotations
import argparse,json,re,zipfile
from pathlib import Path
from prism_data import load_json,write_json,sha

def inspect(path):
 path=Path(path).resolve()
 if not zipfile.is_zipfile(path):
  return {'project':str(path),'sha256':sha(path),'project_format':'legacy-or-other-native','native_zip_supported':False,'sheet_uids':{},'sheets':{},'next':'Use Prism GUI navigation and native ExportTable; record original sheet names/counts. Do not apply ZIP cleanup or assume Prism version.'}
 with zipfile.ZipFile(path) as z:
  if 'document.json' not in z.namelist():return {'project':str(path),'sha256':sha(path),'project_format':'unknown-zip','native_zip_supported':False,'sheet_uids':{},'sheets':{},'next':'Unsupported native ZIP layout; use Prism GUI and native ExportTable rather than assuming a file version.'}
  d=json.loads(z.read('document.json'));result={'project':str(path),'sha256':sha(path),'project_format':'prism-zip','native_zip_supported':True,'format_version':d.get('formatVersion'),'modified_by':d.get('modifiedBy'),'sheet_uids':d['sheets'],'sheets':{}}
  # Prism preallocates thousands of empty datasets. Keep only graph dependencies
  # in the discovery response; raw-value verification reads table metadata itself.
  used=set()
  for uid in d['sheets'].get('graphs',[]):
   g=json.loads(z.read(f'graphs/{uid}/sheet.json'));used.update(g.get('inputDataSets',[]))
  for category,uids in d['sheets'].items():
   result['sheets'][category]=[]
   for i,uid in enumerate(uids):
    title=d.get('sheetAttributesMap',{}).get(uid,{}).get('title','');item={'index':i+1,'uid':uid,'title':title}
    if category=='data':
     s=json.loads(z.read(f'data/sheets/{uid}/sheet.json'));t=s['table'];all_datasets=t.get('dataSets',[]);item.update(table_uid=t['uid'],format=t.get('format'),data_format=t.get('dataFormat'),replicates=t.get('replicatesCount'),dataset_count=len(all_datasets),dataset_uids=[u for u in all_datasets if u in used])
    elif category=='graphs':
     s=json.loads(z.read(f'graphs/{uid}/sheet.json'));item['input_datasets']=s.get('inputDataSets',[])
    result['sheets'][category].append(item)
 return result
def quote(value):
 value=str(value)
 if any(c in value for c in ['"','\r','\n']):raise ValueError('Prism argument contains a quote/newline.')
 return '"'+value+'"'
def write_script(path,commands):
 p=Path(path).resolve();p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text('\n'.join(commands).rstrip()+'\n',encoding='utf-8-sig');return str(p)
def build_script(baseline,reference,import_file,reps,data_title,graph_title,y_title,output_project,preview,script):
 b=load_json(baseline)
 if not b.get('native_zip_supported',True):raise ValueError('No ZIP baseline available: use GUI creation and native table export; do not infer graph/table indices from an unsupported file format.')
 graph=next((g for g in b['sheets']['graphs'] if g['index']==reference),None)
 if not graph:raise ValueError('Reference graph does not exist in baseline.')
 linked=[s for s in b['sheets']['data'] if set(graph['input_datasets']).intersection(s.get('dataset_uids',[]))]
 if len(linked)!=1 or linked[0].get('format')!='grouped' or linked[0].get('data_format')!='y_replicates':raise ValueError('Reference must directly use one simple grouped raw-replicate table; use GUI creation otherwise.')
 if b['sheet_uids'].get('analyses'):raise ValueError('Baseline has analyses: inspect family dependencies and create the table in GUI rather than assuming DuplicateFamily creates exactly one table.')
 if Path(output_project).resolve()==Path(b['project']).resolve():raise ValueError('Output must be a working copy, not the source project.')
 if Path(preview).exists():raise ValueError('Use a new preview name; ExportPNG does not overwrite reliably.')
 di=len(b['sheet_uids'].get('data',[]))+1;gi=len(b['sheet_uids'].get('graphs',[]))+1
 commands=[f'GoTo G {reference}',f'DuplicateFamily {quote(graph_title+"_")} CLEAR',f'GoTo D {di}',f'SetSheetTitle {quote(data_title)}',f'SetYReplicates {reps}',f'Import {quote(Path(import_file).resolve())}, 0, -1',f'GoTo G {gi}',f'SetSheetTitle {quote(graph_title)}',f'SetAxisTitle Y {quote(y_title)}',f'ExportPNG {quote(Path(preview).resolve())}',f'Save {quote(Path(output_project).resolve())}','CloseScriptDialog']
 return {'script':write_script(script,commands),'expected_new_data_index':di,'expected_new_graph_index':gi,'reference_uid':graph['uid'],'must_inspect_actual_delta':True}
def cleanup(project,baseline,remove_uids,output):
 before=load_json(baseline)
 if not before.get('native_zip_supported',True):raise ValueError('Legacy project cleanup requires GUI; ZIP cleanup is unavailable.')
 protected=set(before['sheet_uids'].get('graphs',[]));remove=set(remove_uids)
 if not remove or protected&remove:raise ValueError('Cleanup requires explicit new graph UIDs; original graph UIDs are protected.')
 source=Path(project).resolve();target=Path(output).resolve()
 if target==source or target.exists():raise ValueError('Cleanup must create a new, nonexistent output copy.')
 with zipfile.ZipFile(source) as z:
  d=json.loads(z.read('document.json'));current=set(d['sheets'].get('graphs',[]))
  if not remove.issubset(current) or not protected.issubset(current):raise ValueError('Graph UID mismatch or original graph missing; stop cleanup.')
  d['sheets']['graphs']=[u for u in d['sheets']['graphs'] if u not in remove]
  for uid in remove:d.get('sheetAttributesMap',{}).pop(uid,None)
  ui=d.get('uiSettings',{}).get('currentSheets',{})
  if ui.get('graph') in remove:ui['graph']=d['sheets']['graphs'][-1]
  target.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as out:
   for entry in z.infolist():
    if any(entry.filename.startswith(f'graphs/{u}/') for u in remove):continue
    data=json.dumps(d,ensure_ascii=False,indent=2).encode('utf8') if entry.filename=='document.json' else z.read(entry.filename);out.writestr(entry,data)
 return {'output':str(target),'removed_graph_uids':sorted(remove),'original_graphs_protected':len(protected),'reopen_and_visual_check_required':True}
def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 s=sub.add_parser('inspect');s.add_argument('--project',required=True);s.add_argument('--output')
 s=sub.add_parser('build-script')
 for key in ['baseline','import-file','data-title','graph-title','output-project','preview','script']:s.add_argument('--'+key,required=True)
 s.add_argument('--reference-graph-index',type=int,required=True);s.add_argument('--replicates',type=int,required=True);s.add_argument('--y-title',default='测定值')
 s=sub.add_parser('cleanup');s.add_argument('--project',required=True);s.add_argument('--baseline',required=True);s.add_argument('--remove-graph-uid',action='append',required=True);s.add_argument('--output',required=True)
 x=p.parse_args()
 if x.command=='inspect':r=inspect(x.project);write_json(x.output,r) if x.output else None
 elif x.command=='build-script':r=build_script(x.baseline,x.reference_graph_index,x.import_file,x.replicates,x.data_title,x.graph_title,x.y_title,x.output_project,x.preview,x.script)
 else:r=cleanup(x.project,x.baseline,x.remove_graph_uid,x.output)
 print(json.dumps(r,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
