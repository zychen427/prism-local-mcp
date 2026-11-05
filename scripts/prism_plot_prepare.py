"""Explicit colour-selected, plot-only grouped raw values; no Prism UI or tests."""
from pathlib import Path
from collections import Counter
import csv, hashlib, io, itertools, json, math, statistics
from openpyxl import load_workbook

def _colour(cell, kind):
    c = cell.font.color if kind == 'font' else cell.fill.fgColor
    if kind == 'fill' and cell.fill.patternType != 'solid': return None
    if c is None or c.type != 'rgb' or not isinstance(c.rgb, str): return None
    return c.rgb[-6:].upper()

def prepare_plot_data(config, output_dir):
    source=Path(config['source_file']).resolve(); blob=source.read_bytes()
    root=Path(output_dir).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()): raise FileExistsError('Use a new, empty output directory.')
    rows=config['row_levels']; cols=config['column_levels']; mapping=config['group_mapping']
    if len(rows)!=3 or len(cols)!=2 or len(set(rows))!=3 or len(set(cols))!=2: raise ValueError('Specify exactly 3 distinct row levels and 2 distinct column levels.')
    if any(not isinstance(v,str) or not v.strip() or any(c in v for c in '\t\r\n"') for v in rows+cols): raise ValueError('Invalid factor label.')
    cells=list(itertools.product(rows,cols))
    if len(mapping)!=6 or {tuple(v) for v in mapping.values()}!=set(cells): raise ValueError('Map exactly six source groups bijectively to factor cells.')
    kind=config['colour_kind']; colours={str(c).upper() for c in config['rgb']}
    if kind not in ('font','fill') or not colours or any(len(c)!=6 or any(x not in '0123456789ABCDEF' for x in c) for c in colours): raise ValueError('Choose font or fill and explicit six-digit RGB colours.')
    metrics=config['metrics']
    if not metrics or len({m['name'] for m in metrics})!=len(metrics): raise ValueError('Metrics must have unique names.')
    values=load_workbook(io.BytesIO(blob),data_only=True); styles=load_workbook(io.BytesIO(blob),data_only=False)
    audit={'source':str(source),'sha256':hashlib.sha256(blob).hexdigest(),'selection':{'meaning':'include selected colour','kind':kind,'rgb':sorted(colours)},'row_levels':rows,'column_levels':cols,'error_bars':'SEM (sample SD / sqrt(n))','statistical_tests':'not performed','metrics':[]}
    output=[]
    for idx,metric in enumerate(metrics,1):
        name=metric['name']; sheet=metric['sheet']; ws=values[sheet]; wf=styles[sheet]
        if len(wf.conditional_formatting): raise ValueError(f'{sheet}: conditional formatting exists; displayed colours cannot be inferred safely by openpyxl.')
        start=int(metric['first_row']); end=int(metric['last_row']); gc=int(metric['group_column']); vc=int(metric['value_column']); sc=int(metric['sample_column'])
        if not 1<=start<=end<=ws.max_row: raise ValueError(f'{name}: invalid row range.')
        selected={c:[] for c in cells}; records=[]; observed=Counter(); seen=set()
        for row in range(start,end+1):
            c=wf.cell(row,vc); colour=_colour(c,kind); observed[colour or 'non_rgb_or_unset']+=1
            if colour not in colours: continue
            group=ws.cell(row,gc).value; sample=ws.cell(row,sc).value
            if group is None or sample is None or str(group).strip() not in mapping: raise ValueError(f'{sheet}!{c.coordinate}: selected cell lacks a known group or sample.')
            group=str(group).strip(); sample=str(sample).strip(); key=(group,sample)
            if not sample or key in seen: raise ValueError(f'{sheet}!{c.coordinate}: duplicate or empty sample ID within group.')
            seen.add(key); value=ws.cell(row,vc).value
            if c.data_type=='f' and value is None: raise ValueError(f'{sheet}!{c.coordinate}: formula cache missing.')
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value): raise ValueError(f'{sheet}!{c.coordinate}: selected value is missing or not finite numeric.')
            cell=tuple(mapping[group]); selected[cell].append(float(value))
            records.append({'cell':c.coordinate,'group':group,'sample':sample,'factor_row':cell[0],'factor_column':cell[1],'value':float(value),'rgb':colour})
        if any(len(selected[c])<2 for c in cells): raise ValueError(f'{name}: SEM needs at least two selected values in every cell: '+str({str(c):len(selected[c]) for c in cells}))
        reps=max(len(v) for v in selected.values()); stream=io.StringIO(newline=''); w=csv.writer(stream,delimiter='\t',lineterminator='\n')
        w.writerow(['Factor']+sum(([c]+['']*(reps-1) for c in cols),[]))
        for a in rows:
            fields=[]
            for b in cols:
                vals=selected[(a,b)]; fields += [format(v,'.17g') for v in vals]+['']*(reps-len(vals))
            w.writerow([a]+fields)
        fname=f'metric_{idx:03}.tsv';output.append((fname,stream.getvalue()))
        summary=[{'row':a,'column':b,'n':len(selected[(a,b)]),'mean':statistics.mean(selected[(a,b)]),'sem':statistics.stdev(selected[(a,b)])/math.sqrt(len(selected[(a,b)]))} for a,b in cells]
        audit['metrics'].append({'name':name,'sheet':sheet,'file':fname,'replicates_columns':reps,'summary':summary,'selected':records,'observed_colour_counts':dict(observed)})
    # Validate the entire source and every metric before writing any output.
    for name,text in output: (root/name).write_text(text,encoding='utf-8-sig')
    (root/'plot_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    return {'audit_file':str(root/'plot_audit.json'),'tsv_files':[str(root/n) for n,_ in output],'metrics':len(output),'source_sha256':audit['sha256'],'prism_project_created':False,'graph_created':False,'conditional_formatting_supported':False,'statistics':audit['statistical_tests']}
