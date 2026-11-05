"""Exercise the actual stdio protocol without an interactive Prism window."""
import asyncio,json,sys,tempfile
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
 root=Path(__file__).resolve().parents[1]
 with tempfile.TemporaryDirectory() as temp:
  d=Path(temp);xlsx=d/'sample.xlsx';wb=Workbook();s=wb.active;s.title='Raw';s.append(['group','sample','value']);mapping={}
  for i,diet in enumerate(('A','B','C')):
   for j,treat in enumerate(('yes','no')):
    label=f'{diet}-{treat}';mapping[label]=[diet,treat]
    for rep in range(3):s.append([label,str(rep+1),10+i+j*.5+rep*.25])
  wb.save(xlsx)
  config={'source_file':str(xlsx),'sheet':'Raw','first_row':2,'last_row':19,'group_column':1,'sample_column':2,
          'diets':['A','B','C'],'treatments':['yes','no'],'group_mapping':mapping,'independent_observations':True,
          'expected_n':3,'metrics':[{'name':'value','column':3}]}
  server=StdioServerParameters(command=sys.executable,args=['-X','utf8',str(root/'scripts'/'prism_mcp_server.py')],cwd=str(root/'scripts'))
  async with stdio_client(server) as (read,write):
   async with ClientSession(read,write) as client:
    await client.initialize();tools=await client.list_tools();names={t.name for t in tools.tools}
    required={'prism_prepare_factorial_data','prism_factorial_annotation_plan','prism_combine_factorial_audits','prism_build_factorial_script','prism_verify_factorial_project','prism_choose_workflow','prism_preview_version_route','prism_verify_factorial_export'}
    required.add('prism_prepare_coloured_plot_data')
    assert required <= names,(required-names)
    for row in range(2,20): s.cell(row,3).font=Font(color='FFFF0000')
    wb.save(xlsx)
    plotconfig={'source_file':str(xlsx),'row_levels':['A','B','C'],'column_levels':['yes','no'],'group_mapping':mapping,'colour_kind':'font','rgb':['FF0000'],'metrics':[{'name':'value','sheet':'Raw','first_row':2,'last_row':19,'group_column':1,'sample_column':2,'value_column':3}]}
    plot=await client.call_tool('prism_prepare_coloured_plot_data',{'output_dir':str(d/'plot'),'config':plotconfig})
    assert not plot.isError,plot
    plotted=plot.structuredContent or json.loads(plot.content[0].text); assert plotted['metrics']==1 and not plotted['graph_created']
    legacy=await client.call_tool('prism_preview_version_route',{'window_title':'example.pzf - GraphPad Prism 7.04','project_format':'legacy'})
    assert not legacy.isError,legacy
    route=legacy.structuredContent or json.loads(legacy.content[0].text)
    assert route['simulated'] and route['route']=='legacy_pre8' and not route['native_zip_batch_builder_available'],route
    modern=await client.call_tool('prism_preview_version_route',{'window_title':'example.prism - GraphPad Prism 11.0.0','project_format':'native_zip'})
    assert not modern.isError,modern
    route=modern.structuredContent or json.loads(modern.content[0].text);assert route['route']=='modern_cld_capable',route
    result=await client.call_tool('prism_prepare_factorial_data',{'output_dir':str(d/'out'),'config':config})
    assert not result.isError,result
    data=result.structuredContent or json.loads(result.content[0].text)
    assert data['metrics']==1 and data['n_per_cell']==[3] and Path(data['audit_file']).is_file(),data
    second=await client.call_tool('prism_prepare_factorial_data',{'output_dir':str(d/'out2'),'config':{**config,'metrics':[{'name':'other','column':3}]}})
    assert not second.isError,second
    data2=second.structuredContent or json.loads(second.content[0].text)
    combined=await client.call_tool('prism_combine_factorial_audits',{'output_dir':str(d/'merged'),'audit_files':[data['audit_file'],data2['audit_file']]})
    assert not combined.isError,combined
    combined_data=combined.structuredContent or json.loads(combined.content[0].text);assert combined_data['metric_count']==2
    planned=await client.call_tool('prism_factorial_annotation_plan',{'audit_file':combined_data['audit_file'],'metric':'value'})
    assert not planned.isError,planned
    assert 'Interaction' in (planned.structuredContent or json.loads(planned.content[0].text))['items'][0]['p_text']
    bad=await client.call_tool('prism_prepare_factorial_data',{'output_dir':str(d/'bad'),'config':{**config,'independent_observations':False}})
    assert bad.isError,'Invalid experimental design was not rejected'
    print(json.dumps({'protocol':'stdio','tools':len(names),'new_tools':sorted(required),'prepare':'passed','invalid_design':'rejected'}))

if __name__=='__main__':asyncio.run(main())
