"""Exercise the real stdio protocol. Read-only by default; optional PNG export/capture.

Run with the same venv Python used by prism_mcp_server.py. No project is saved.
"""
import argparse,asyncio,json,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def run(x):
 server=Path(x.server).resolve();out=Path(x.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
 params=StdioServerParameters(command=sys.executable,args=['-X','utf8',str(server)],cwd=str(server.parent),env={'PYTHONUTF8':'1'})
 report={'server':str(server),'checks':{}}
 async with stdio_client(params) as (reader,writer):
  async with ClientSession(reader,writer) as client:
   await client.initialize();ts=await client.list_tools();report['tools']=[t.name for t in ts.tools]
   async def call(name,args):
    r=await client.call_tool(name,args)
    if r.isError:raise RuntimeError(f'{name}: '+str(r.content))
    if r.structuredContent is not None:return r.structuredContent
    for item in r.content:
     if item.type=='text':return json.loads(item.text)
    return {'image_blocks':sum(i.type=='image' for i in r.content)}
   windows=await call('prism_list_sessions',{});report['checks']['discovery']=windows
   conn=await call('prism_connect',{'project_title':x.project_title,'output_dir':str(out)});sid=conn['session_id'];report['checks']['connect']=conn
   cap=await call('prism_get_capabilities',{'session_id':sid,'project_file':x.project_file});report['checks']['capabilities']=cap
   controls=await call('prism_get_controls',{'session_id':sid,'limit':10});report['checks']['control_count']=controls['total']
   if x.source:
    survey=await call('prism_survey_excel',{'source_file':x.source,'sheet':x.sheet});report['checks']['survey']={'sha256':survey['sha256'],'sheets':[{'name':s['name'],'rows':s['rows'],'columns':s['columns'],'formula_cache_missing':s['formula_cache_missing']} for s in survey['sheets']]}
   if x.audit:
    audit=await call('prism_read_audit',{'audit_file':x.audit});report['checks']['audit_counts']={'numeric_cells':audit['numeric_cells'],'excluded_numeric_cells':audit['excluded_numeric_cells']}
    args={'session_id':sid,'audit_file':x.audit,'project_file':x.project_file,'table_uid':x.table_uid,'table_title':x.table_title,'baseline_file':x.baseline}
    verification=await call('prism_verify_data',args);assert verification['passed'],verification['errors'];report['checks']['verification']={k:v for k,v in verification.items() if k!='labels'}
   if x.export_graph_index:
    preview=out/'mcp-export.png'
    if preview.exists():raise ValueError('Use a new output directory: mcp-export.png already exists.')
    script=await call('prism_run_script',{'session_id':sid,'commands':[f'GoTo G {x.export_graph_index}',f'ExportPNG "{preview}"','CloseScriptDialog'],'script_file':'smoke-export.pzc'})
    assert preview.exists() and preview.stat().st_size>0,'PNG export missing';report['checks']['export']=script;report['preview']=str(preview)
   if x.capture:
    image=await call('prism_capture_window',{'session_id':sid,'output_file':'mcp-window.png'});report['checks']['capture']=image
 report['passed']=True;(out/'mcp-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'passed':True,'tool_count':len(report['tools']),'report':str(out/'mcp-smoke.json'),'preview':report.get('preview')},ensure_ascii=False))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--server',default=str(Path(__file__).with_name('prism_mcp_server.py')))
 for key in ('project-title','project-file','output-dir'):p.add_argument('--'+key,required=True)
 for key in ('source','sheet','audit','table-uid','table-title','baseline'):p.add_argument('--'+key)
 p.add_argument('--export-graph-index',type=int);p.add_argument('--capture',action='store_true');asyncio.run(run(p.parse_args()))
if __name__=='__main__':main()
