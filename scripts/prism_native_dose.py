"""Prism-native IC20 workflow using the verified Prism 11 template only."""
from pathlib import Path
import csv,hashlib,io,json,math,zipfile,tempfile,shutil,time
from prism_project import inspect,write_script,quote
from prism_dose_advanced import analyze
from prism_graph_preflight import preflight

VERIFIED_TEMPLATE_SHA256='d86403b27b774bc0c424b394f6f119ed4d50cd335dc08127a3fdb29ca240d777'

def file_hash(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()

def native_ic20(bridge,output_dir,template_file,points,name='IC20_native'):
 started=time.perf_counter()
 root=Path(output_dir).resolve();source=Path(template_file).resolve()
 asset=Path(__file__).resolve().parents[1]/'assets'/'ic20_template_prism11.prism'
 if not name or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for ch in name):raise ValueError('name must contain only ASCII letters, digits, hyphen or underscore')
 if not source.is_file() or not asset.is_file() or file_hash(source)!=VERIFIED_TEMPLATE_SHA256 or file_hash(asset)!=VERIFIED_TEMPLATE_SHA256:raise ValueError('The saved source and bundled template must match the verified Prism 11 IC20 template SHA-256.')
 if not bridge.validate().startswith(source.name+':') and not bridge.validate().startswith(source.name+' -'):raise ValueError('Connect to the open verified template project using its unique exact filename.')
 if bridge.dialogs():raise ValueError('Resolve current Prism dialogs before starting. No commands were run.')
 if bridge._script_windows():raise ValueError('Another Prism script dialog is open; no commands were run. Inspect its script and owning project before continuing.')
 fit=analyze(points,direction='decreasing',effect=20)
 if fit['effect_concentration'] is None or fit['jacobian_rank']<fit['free_parameters'] or fit['at_bound']:raise ValueError('Input does not support an identifiable IC20 fit; inspect data before native processing.')
 groups={}
 for p in points:groups.setdefault(float(p['concentration']),[]).append(float(p['response']))
 if any(len(v)!=3 for v in groups.values()):raise ValueError('This verified template requires exactly 3 independent raw Y values per concentration.')
 root.mkdir(parents=True,exist_ok=True)
 paths={'project':root/(name+'.prism'),'data':root/(name+'_input.tsv'),'graph':root/(name+'.png'),'audit':root/(name+'_audit.json'),'journal':root/(name+'_journal.json'),'copy_script':root/(name+'_copy.pzc'),'run_script':root/(name+'_fit.pzc')}
 if any(p.exists() for p in paths.values()):raise FileExistsError('Output already exists; choose a different name.')
 with paths['data'].open('x',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f,delimiter='\t');w.writerow(['Concentration (uM)','Response (%)']);
  for x in sorted(groups):w.writerow([format(x,'.17g'),*[format(y,'.17g') for y in groups[x]]])
 src_hash=file_hash(source)
 # Prism script import can fail on Unicode paths even when its editor displays
 # the correct text. Use a unique ASCII-only local staging path for native I/O.
 stage_base=Path(__file__).resolve().parents[3]/'work'/'prism_native_staging'
 if not str(stage_base).isascii():raise ValueError('An ASCII-only native staging directory is required on this host.')
 stage_base.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='ic20_',dir=stage_base))
 # Distinct temporary project titles prevent ambiguous reconnects when several
 # Prism projects remain open after previous runs.
 staged_project=stage/(stage.name+'.prism');staged_data=stage/'input.tsv';staged_graph=stage/'graph.png'
 journal={'state':'prepared','stage_dir':str(stage),'template':str(source),'outputs':{k:str(v) for k,v in paths.items()},'warning':'Do not retry a started workflow blindly; inspect the live Prism project and logs.'}
 def checkpoint(state,**extra):
  journal.update(state=state,elapsed_seconds=round(time.perf_counter()-started,3),**extra);tmp=paths['journal'].with_suffix('.tmp');tmp.write_text(json.dumps(journal,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(paths['journal'])
 checkpoint('prepared')
 shutil.copyfile(paths['data'],staged_data)
 commands=['GoTo G 1','Save '+quote(staged_project),'CloseScriptDialog']
 write_script(paths['copy_script'],commands)
 checkpoint('copy_started')
 try:bridge.run_script(write_script(stage/'copy.pzc',commands))
 except Exception as e:checkpoint('copy_failed_or_interrupted',error=str(e));raise RuntimeError(f'Copy stage failed; inspect journal {paths["journal"]} and live Prism before retrying. {e}') from e
 checkpoint('copy_completed')
 copied=inspect(staged_project);ds=copied.get('sheets',{}).get('data',[])
 if len(ds)!=1 or ds[0].get('format')!='xy' or ds[0].get('replicates')!=3 or len(copied.get('sheet_uids',{}).get('analyses',[]))!=1 or len(copied.get('sheet_uids',{}).get('graphs',[]))!=1:
  raise RuntimeError('Saved working copy does not match expected template structure; no input import was attempted.')
 with zipfile.ZipFile(staged_project) as z:
  result_tables=[z.read(p).decode('utf-8-sig') for p in z.namelist() if p.endswith('/data.csv')]
  if not any('Find ECanything' in t and 'F = 80' in t for t in result_tables):raise RuntimeError('Template does not show ECanything with F=80; import cancelled.')
 commands=['GoTo D 1','ClearTable',f'Import {quote(staged_data)}, 0, 0','GoTo G 1','SetGraphTitle "IC20 dose-response"',f'ExportPNG {quote(staged_graph)}',f'Save {quote(staged_project)}','CloseScriptDialog']
 write_script(paths['run_script'],commands)
 checkpoint('import_started')
 try:bridge.run_script(write_script(stage/'fit.pzc',commands))
 except Exception as e:checkpoint('import_failed_or_interrupted',error=str(e));raise RuntimeError(f'Import stage may have partially changed the working copy; inspect journal {paths["journal"]} and live Prism before retrying. {e}') from e
 checkpoint('import_completed')
 saved=inspect(staged_project);tableid=saved['sheets']['data'][0]['table_uid']
 with zipfile.ZipFile(staged_project) as z:
  raw=z.read(f'data/tables/{tableid}/data.csv').decode('utf-8-sig')
  rows=[[float(v) for v in row[1:]] for row in csv.reader(io.StringIO(raw)) if len(row)>1 and row[1]]
  results=[z.read(p).decode('utf-8-sig') for p in z.namelist() if p.endswith('/data.csv')]
 expected=[[x,*groups[x]] for x in sorted(groups)]
 if len(rows)!=len(expected) or any(len(a)!=len(b) or any(not math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-12) for x,y in zip(a,b)) for a,b in zip(rows,expected)):raise RuntimeError('Saved Prism data differ from the requested input; inspect the working copy, do not retry blindly.')
 ecf=[]
 for data in results:
  if 'Find ECanything' in data:
   for row in csv.reader(io.StringIO(data)):
    if len(row)>1 and row[0].strip()=='ECF':
     try:ecf.append(float(row[1]))
     except ValueError:pass
 if len(ecf)!=1 or not math.isclose(ecf[0],fit['effect_concentration'],rel_tol=.002,abs_tol=1e-9):raise RuntimeError('Native displayed ECF does not match independent check; inspect analysis, do not retry blindly.')
 if file_hash(source)!=src_hash:raise RuntimeError('Template source hash changed during operation; inspect before continuing.')
 # Exclusive creation prevents races or overwriting a user's file.
 for src,dst in [(staged_project,paths['project']),(staged_graph,paths['graph'])]:
  with src.open('rb') as reader,dst.open('xb') as writer:shutil.copyfileobj(reader,writer)
 audit={'status':'numerical_checks_passed','prism_displayed_relative_ic20_uM':ecf[0],'independent_relative_ic20_uM':fit['effect_concentration'],'effect_definition':'relative 20% inhibition; Prism ECanything F=80','input_concentrations':len(groups),'input_values':len(points),'raw_values_verified':True,'quality_warnings':fit['warnings'],'template_sha256':src_hash,'error_bars':'mean ± SD, as configured in template','zero_concentration':'included in fitting, absent from log-axis graph' if 0.0 in groups else 'not present in input','graph_preflight':preflight(points),'remaining':'Inspect exported graph and reopen the saved project before declaring complete.','files':{k:str(v) for k,v in paths.items()}}
 paths['audit'].write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');checkpoint('numerical_verified_visual_reopen_pending',audit=str(paths['audit']))
 try:
  reopened,_=open_project(bridge,paths['project']);reopened_graph=stage/'reopened.png'
  reopened.run_script(write_script(stage/'reopen_export.pzc',['GoTo G 1',f'ExportPNG {quote(reopened_graph)}','CloseScriptDialog']))
  from PIL import Image,ImageChops,ImageStat
  with Image.open(staged_graph) as original,Image.open(reopened_graph) as after:
   a=original.convert('RGB');b=after.convert('RGB')
   if a.size!=b.size:raise ValueError('Reopened graph dimensions differ from original export.')
   diff=ImageStat.Stat(ImageChops.difference(a,b)).rms;rms=math.sqrt(sum(v*v for v in diff)/len(diff))
  audit['reopen']={'opened':True,'reexported':True,'image_rms_pixel_difference':rms,'visual_match':rms<=2.0}
  if rms<=2.0:
   audit['status']='numeric_and_reopen_checks_passed';audit['remaining']='Review the exported graph visually for labels, error bars and layout.';checkpoint('reopened_image_verified')
  else:audit['remaining']='Reopened image differs; inspect both exports manually before use.';checkpoint('reopened_image_differs')
  try:
   audit['temporary_project_closed']=close_owned_staging_project(bridge,staged_project)
   audit['reopened_result_window_closed']=close_owned_reopened_project(reopened,paths['project'])
  except Exception as e:
   audit.setdefault('temporary_project_closed',False);audit['reopened_result_window_closed']=False;audit['quality_warnings'].append('Owned Prism window cleanup requires inspection: '+str(e))
 except Exception as e:
  audit['reopen']={'opened_and_verified':False,'error':str(e)};audit['remaining']='Reopen or export verification failed; inspect the working copy and Prism state before retrying.';checkpoint('reopen_failed',error=str(e))
 audit['workflow_elapsed_seconds']=round(time.perf_counter()-started,3)
 paths['audit'].write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 return audit

def workflow_status(output_dir,name):
 if not name or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for ch in name):raise ValueError('invalid workflow name')
 path=Path(output_dir).resolve()/(name+'_journal.json')
 if not path.is_file():raise FileNotFoundError('No workflow journal found for this output directory and name.')
 journal=json.loads(path.read_text(encoding='utf8'))
 return {'journal':str(path),'record':journal,'exists':{key:Path(value).exists() for key,value in journal.get('outputs',{}).items()},'resume_policy':'Inspect live Prism, staged copy and logs. Never repeat mutating commands automatically; start a new workflow only after resolving partial state.'}

def open_project(base_bridge,project,allow_existing=False):
 """Open a named saved project, refusing ambiguous project titles."""
 import ctypes as c,time,re
 from prism_ui import PrismBridge
 asset=Path(project).resolve()
 if not asset.is_file():raise FileNotFoundError('Prism project does not exist.')
 base_bridge.validate();frames=base_bridge.windows()
 matches=[x for x in frames if x['pid']==base_bridge.pid and x['title'].startswith(asset.name)]
 if len(matches)>1:raise RuntimeError('More than one template window is open; cannot select safely.')
 if matches and not allow_existing:raise RuntimeError('A project with the same filename is already open; cannot prove its path from its title.')
 if matches:return PrismBridge(asset.name,matches[0]['hwnd']),asset
 if base_bridge.dialogs() or base_bridge._script_windows():raise RuntimeError('A Prism dialog is open; inspect its ownership before opening the template.')
 choices=base_bridge.find_menu(r'^(?:打开\s*\(&[A-Za-z]\)|Open\s*(?:\(&[A-Za-z]\))?)\s*\.\.\.')
 if len(choices)!=1:raise RuntimeError(f'Cannot uniquely identify the Open Project menu: {choices}.')
 # Opening a modal file dialog can block SendMessage until the dialog closes.
 # Post the discovered command and then observe the new dialog instead.
 from ctypes import wintypes as w
 post=base_bridge.u.PostMessageW;post.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];post.restype=w.BOOL
 if not post(base_bridge.frame,0x111,choices[0]['id'],0):raise RuntimeError('Could not post the Open Project command.')
 deadline=time.monotonic()+10;dialog=None
 while time.monotonic()<deadline:
  found=[d for d in base_bridge.dialogs() if re.fullmatch(r'打开|Open',d['title'],re.I) and any(x['class']=='Edit' and x['id']==1148 for x in d['controls'])]
  if len(found)==1:dialog=found[0];break
  if len(found)>1:raise RuntimeError('Multiple Open Project dialogs appeared; refusing to choose.')
  time.sleep(.15)
 if dialog is None:raise RuntimeError('Open Project dialog not found; inspect Prism before continuing.')
 edit=base_bridge.control(dialog['hwnd'],1148,'Edit');buf=c.create_unicode_buffer(str(asset));base_bridge.send(edit,0xC,0,c.addressof(buf));base_bridge.button(base_bridge.control(dialog['hwnd'],1,'Button'))
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  matches=[x for x in base_bridge.windows() if x['pid']==base_bridge.pid and x['title'].startswith(asset.name)]
  if len(matches)==1 and base_bridge.u.IsWindowVisible(matches[0]['hwnd']) and base_bridge.u.IsWindowEnabled(matches[0]['hwnd']):return PrismBridge(asset.name,matches[0]['hwnd']),asset
  if len(matches)==1:
   opened=PrismBridge(asset.name,matches[0]['hwnd']);dialogs=opened.dialogs()
   if dialogs:raise RuntimeError(f'Opened project is blocked by dialogs: {[{"hwnd":d["hwnd"],"title":d["title"]} for d in dialogs]}; inspect the new working copy. No batch script was run.')
  if len(matches)>1:raise RuntimeError('More than one template window appeared; inspect Prism.')
  time.sleep(.2)
 raise RuntimeError('Template did not become ready; inspect Prism dialogs before retrying.')

def open_verified_template(base_bridge):
 asset=(Path(__file__).resolve().parents[1]/'assets'/'ic20_template_prism11.prism').resolve()
 if not asset.is_file() or file_hash(asset)!=VERIFIED_TEMPLATE_SHA256:raise ValueError('Bundled Prism 11 template is missing or differs from the verified template; no project was opened.')
 return open_project(base_bridge,asset,allow_existing=False)

def close_owned_staging_project(bridge,staged_project):
 """Close only this workflow's saved staging window; never dismiss save prompts."""
 import ctypes as c,time
 from ctypes import wintypes as w
 project=Path(staged_project).resolve()
 if not project.is_file() or not project.parent.name.startswith('ic20_') or not bridge.validate().startswith(project.name):
  raise RuntimeError('Staging project identity did not match; no window was closed.')
 if bridge.dialogs() or bridge._script_windows():raise RuntimeError('A dialog is open; no window was closed.')
 choices=bridge.find_menu(r'^(?:关闭\s*\(&[A-Za-z]\)|Close\s*(?:\(&[A-Za-z]\))?)(?:\s|\t|$)')
 if len(choices)!=1:raise RuntimeError('Could not uniquely identify Close Project; no window was closed.')
 post=bridge.u.PostMessageW;post.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];post.restype=w.BOOL
 if not post(bridge.frame,0x111,choices[0]['id'],0):raise RuntimeError('Could not post Close Project command.')
 deadline=time.monotonic()+10;handled_save_prompt=False
 while time.monotonic()<deadline:
  if not bridge.u.IsWindow(bridge.frame):return True
  if not handled_save_prompt:
   dialogs=bridge.dialogs()
   prompts=[d for d in dialogs if any(x['class']=='Static' and project.name.casefold() in x['text'].casefold() and ('保存' in x['text'] or 'save' in x['text'].casefold()) for x in d['controls']) and any(x['class']=='Button' and x['id']==6 for x in d['controls'])]
   if len(prompts)>1:raise RuntimeError('Multiple matching save prompts; no prompt was accepted.')
   if prompts:
    yes=bridge.control(prompts[0]['hwnd'],6,'Button')
    if not post(yes,0xF5,0,0):raise RuntimeError('Could not save the owned staging project.')
    handled_save_prompt=True
  time.sleep(.15)
 raise RuntimeError('Staging window did not close; inspect Prism for any save prompt.')

def close_owned_reopened_project(bridge,project_file):
 """Close only the uniquely reopened saved result created in this workflow; never answer prompts."""
 import re
 from ctypes import wintypes as w
 project=Path(project_file).resolve()
 if not project.is_file() or not bridge.validate().startswith(project.name+':'):raise RuntimeError('Result project identity is not unique; no window was closed.')
 if bridge.dialogs() or bridge._script_windows():raise RuntimeError('A Prism dialog is open; result window was not closed.')
 choices=bridge.find_menu(r'^(?:关闭\s*\(&[A-Za-z]\)|Close\s*(?:\(&[A-Za-z]\))?)(?:\s|\t|$)')
 if len(choices)!=1:raise RuntimeError('Close Project menu is ambiguous; result window was not closed.')
 post=bridge.u.PostMessageW;post.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];post.restype=w.BOOL
 if not post(bridge.frame,0x111,choices[0]['id'],0):raise RuntimeError('Could not post Close Project command.')
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  if not bridge.u.IsWindow(bridge.frame):return True
  # Prism can keep its last frame alive as an empty application window.
  if re.fullmatch(r'GraphPad Prism(?:\s+\d+(?:\.\d+)*(?:\s*\([^)]*\))?)?',bridge.text(bridge.frame).strip(),re.I):return True
  if bridge.dialogs():raise RuntimeError('A close prompt appeared; inspect it. No prompt was accepted.')
  time.sleep(.15)
 raise RuntimeError('Result window did not close; inspect Prism state.')
