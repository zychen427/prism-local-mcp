"""Install this skill and register its stdio MCP server in Codex config.

Requires Python 3.11+ and Windows. No Prism executable/version/path is configured.
Only this skill folder, its isolated venv and one MCP table are written.
"""
import argparse,datetime,json,os,shutil,subprocess,sys,tomllib
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--codex-home',default=os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
 p.add_argument('--python',default=sys._base_executable,help='Base Python 3.11+ executable for the isolated runtime')
 p.add_argument('--skip-dependencies',action='store_true',help='Use an already installed MCP runtime; import is still verified')
 x=p.parse_args()
 if os.name!='nt':raise RuntimeError('This connector requires Windows and an interactive desktop.')
 root=Path(x.codex_home).resolve();source=Path(__file__).resolve().parents[1];target=root/'skills'/'prism-local-plotting';runtime=root/'runtimes'/'prism-local-mcp';exe=runtime/'Scripts'/'python.exe';config=root/'config.toml'
 old_text=config.read_text(encoding='utf-8-sig') if config.exists() else '';before=tomllib.loads(old_text)
 server={'command':exe.as_posix(),'args':['-X','utf8',(target/'scripts'/'prism_mcp_server.py').as_posix()],'cwd':target.as_posix(),'startup_timeout_sec':20,'tool_timeout_sec':90,'enabled':True,'env':{'PYTHONUTF8':'1'}}
 existing=before.get('mcp_servers',{}).get('prism_local')
 if existing is not None and existing!=server:raise ValueError('prism_local already has different settings. Review that one table before replacing it; other configuration is preserved.')
 if source!=target:
  shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 if not exe.exists():subprocess.run([x.python,'-X','utf8','-m','venv',str(runtime)],check=True)
 if not x.skip_dependencies:subprocess.run([str(exe),'-X','utf8','-m','pip','install','-r',str(target/'requirements-mcp.txt')],check=True)
 subprocess.run([str(exe),'-X','utf8','-c','import mcp,openpyxl,PIL,scipy,matplotlib'],check=True)
 backup=None
 if existing is None:
  q=lambda v:json.dumps(v,ensure_ascii=False)
  block='\n[mcp_servers.prism_local]\n'+f'command = {q(server["command"])}\nargs = {q(server["args"])}\ncwd = {q(server["cwd"])}\nstartup_timeout_sec = 20\ntool_timeout_sec = 90\nenabled = true\n\n[mcp_servers.prism_local.env]\nPYTHONUTF8 = "1"\n'
  after=tomllib.loads(old_text.rstrip()+'\n'+block)
  expected={**before,'mcp_servers':{**before.get('mcp_servers',{}),'prism_local':server}}
  if after!=expected:raise ValueError('Unexpected TOML changes; registration cancelled.')
  root.mkdir(parents=True,exist_ok=True)
  if config.exists():
   stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup=config.with_name('config.toml.prism-backup-'+stamp);shutil.copy2(config,backup)
  config.write_text(old_text.rstrip()+'\n'+block,encoding='utf8')
 print(json.dumps({'installed_skill':str(target),'python':str(exe),'config':str(config),'config_backup':str(backup) if backup else None,'registered':True,'other_settings_preserved':True,'prism_version_fixed':False,'requires_client_reload':True},ensure_ascii=False))
if __name__=='__main__':main()
