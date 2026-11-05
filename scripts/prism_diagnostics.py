"""Read-only runtime diagnostics and explicit, reproducible timing probes."""
import importlib.metadata,os,platform,sys,time,tomllib
from pathlib import Path
from prism_version import choose_workflow, executable_version
from prism_project import inspect
from prism_ui import PrismBridge

def doctor(project_file=None,codex_home=None):
 packages={}
 for name in ('mcp','openpyxl','Pillow','numpy','scipy','matplotlib'):
  try: packages[name]=importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:packages[name]=None
 incompatible=[]
 if packages['mcp']:
  try:
   if int(packages['mcp'].split('.')[0])>=2:incompatible.append('mcp 2.x is incompatible with this FastMCP server; use the dedicated environment with mcp>=1.29,<2')
  except ValueError:incompatible.append('Could not determine the MCP SDK major version')
 windows=PrismBridge.discover();result={'platform':platform.platform(),'python_version':platform.python_version(),'python_executable':sys.executable,'dependencies':packages,'missing_dependencies':[k for k,v in packages.items() if v is None],'windows':windows,'window_count':len(windows),'project':None,'safe_to_write_unverified':True,'discovery_not_gui_write_test':True,'scope':'read-only; no projects opened, saved or closed'}
 result['incompatible_dependencies']=incompatible
 cfg=Path(codex_home or os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
 result['config']={'location':str(cfg),'selection':'explicit' if codex_home else 'environment' if os.environ.get('CODEX_HOME') else 'default_unverified','active_client_config_verified':False,'exists':cfg.exists(),'server_registered':None,'server_enabled':None,'legacy_factorial_enabled':None}
 if cfg.is_file():
  try:
   data=tomllib.loads(cfg.read_text(encoding='utf-8-sig')); servers=data.get('mcp_servers',{}); local=servers.get('prism_local');old=servers.get('prism_factorial_local')
   result['config'].update(server_registered=local is not None,server_enabled=local.get('enabled',True) if local else None,legacy_factorial_enabled=old.get('enabled',True) if old else None)
  except (OSError,ValueError) as exc:result['config']['error']=str(exc)
 if project_file:
  result['project']=inspect(project_file)
  if len(windows)==1:result['version_route']=choose_workflow(windows[0]['title'],executable_version(windows[0]['pid']),result['project'])
 elif len(windows)==1:result['version_route']=choose_workflow(windows[0]['title'],executable_version(windows[0]['pid']))
 if not windows:result['next']='No accessible project window was discovered in this desktop session; this does not prove Prism is absent.'
 elif len(windows)>1:result['next']='Connect explicitly to one uniquely identified project.'
 else:result['next']='Connect to this project and check dialogs, permissions and version before writing.'
 return result

def benchmark_discovery(iterations=3):
 if not 1<=iterations<=10:raise ValueError('iterations must be from 1 to 10.')
 samples=[];counts=[]
 for _ in range(iterations):
  start=time.perf_counter(); windows=PrismBridge.discover();samples.append(round((time.perf_counter()-start)*1000,3));counts.append(len(windows))
 return {'operation':'read-only Prism window discovery','iterations':iterations,'times_ms':samples,'minimum_ms':min(samples),'maximum_ms':max(samples),'mean_ms':round(sum(samples)/len(samples),3),'window_counts':counts,'startup_import_export_not_measured':True,'scope':'current host and current session only'}
