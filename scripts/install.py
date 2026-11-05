"""Install this skill and register its stdio MCP server in Codex config.

Requires Python 3.11+ and Windows. No Prism executable/version/path is configured.
Only this skill folder, its isolated venv and one MCP table are written.
"""
import argparse,datetime,json,os,re,shutil,subprocess,sys,tomllib,copy
from pathlib import Path

def migrate_config(old_text,server):
 before=tomllib.loads(old_text);after=copy.deepcopy(before);servers=after.setdefault('mcp_servers',{});existing=servers.get('prism_local')
 if existing is not None and existing!=server:raise ValueError('prism_local already has different settings. Review that one table before replacing it; other configuration is preserved.')
 new=old_text
 if existing is None:
  q=lambda v:json.dumps(v,ensure_ascii=False)
  new=new.rstrip()+'\n\n[mcp_servers.prism_local]\n'+f'command = {q(server["command"])}\nargs = {q(server["args"])}\ncwd = {q(server["cwd"])}\nstartup_timeout_sec = 20\ntool_timeout_sec = 90\nenabled = true\n\n[mcp_servers.prism_local.env]\nPYTHONUTF8 = "1"\n'
  servers['prism_local']=server
 old=servers.get('prism_factorial_local')
 if old is not None and old.get('enabled',True) is not False:
  pattern=r'(?ms)^(\[mcp_servers\.prism_factorial_local\][^\r\n]*\r?\n)(.*?)(?=^\s*\[|\Z)'
  found=list(re.finditer(pattern,new))
  if len(found)!=1:raise ValueError('Cannot safely locate legacy factorial config section; nothing was written.')
  match=found[0];body=match.group(2);setting=r'(?m)^[ \t]*enabled[ \t]*=[ \t]*(?:true|false)[ \t]*(?:\#[^\r\n]*)?\r?$'
  if len(re.findall(setting,body))>1:raise ValueError('Duplicate enabled setting in legacy config.')
  body=re.sub(setting,'enabled = false',body) if re.search(setting,body) else 'enabled = false\n'+body
  new=new[:match.start()]+match.group(1)+body+new[match.end():];old['enabled']=False
 if tomllib.loads(new)!=after:raise ValueError('Configuration migration changed unintended settings; nothing was written.')
 return new, before!=after

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
 new_text,config_changed=migrate_config(old_text,server)
 skill_backup=None
 if source!=target:
  if target.exists():
   stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');skill_backup=root/'backups'/('prism-local-plotting-'+stamp);skill_backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(target,skill_backup)
  shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 if not exe.exists():subprocess.run([x.python,'-X','utf8','-m','venv',str(runtime)],check=True)
 if not x.skip_dependencies:subprocess.run([str(exe),'-X','utf8','-m','pip','install','-r',str(target/'requirements-mcp.txt')],check=True)
 subprocess.run([str(exe),'-X','utf8','-c','import mcp,openpyxl,PIL,scipy,matplotlib'],check=True)
 backup=None
 if config_changed:
  root.mkdir(parents=True,exist_ok=True)
  if config.exists():
   stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup=config.with_name('config.toml.prism-backup-'+stamp);shutil.copy2(config,backup)
  tmp=config.with_name('config.toml.prism-install.tmp')
  if tmp.exists():raise FileExistsError(f'Existing temp config: {tmp}')
  tmp.write_text(new_text,encoding='utf8');tmp.replace(config)
 print(json.dumps({'installed_skill':str(target),'skill_backup':str(skill_backup) if skill_backup else None,'python':str(exe),'config':str(config),'config_backup':str(backup) if backup else None,'legacy_factorial_disabled':bool(before.get('mcp_servers',{}).get('prism_factorial_local')),'other_settings_preserved':True,'requires_client_reload':True},ensure_ascii=False))
if __name__=='__main__':main()
