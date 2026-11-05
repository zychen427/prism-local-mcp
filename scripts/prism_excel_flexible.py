"""Bounded, provenance-preserving Excel discovery and grouped raw-value normalization."""
from pathlib import Path
from collections import Counter
import csv, hashlib, io, itertools, json, math, re, statistics
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from prism_plot_prepare import _colour

_NUM=re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')

def _number(value):
    if isinstance(value,bool): raise ValueError('boolean is not an observation')
    if isinstance(value,(int,float)):
        number=float(value); conversion='numeric'
    elif isinstance(value,str) and _NUM.fullmatch(value.strip()):
        number=float(value.strip()); conversion='numeric_text'
    else: raise ValueError('not a plain number; units, commas, censoring and other text need review')
    if not math.isfinite(number): raise ValueError('number is not finite')
    return number,conversion

def _merged_value(ws,row,col):
    cell=ws.cell(row,col)
    if cell.value is not None:return cell.value,cell.coordinate
    for m in ws.merged_cells.ranges:
        if m.min_row<=row<=m.max_row and m.min_col<=col<=m.max_col:
            anchor=ws.cell(m.min_row,m.min_col)
            return anchor.value,anchor.coordinate
    return None,cell.coordinate

def discover(source_file,max_rows=1000,max_columns=100):
    path=Path(source_file).resolve();blob=path.read_bytes()
    if path.suffix.lower() not in ('.xlsx','.xlsm'):raise ValueError('Only .xlsx and .xlsm are supported; convert other formats to a copy first.')
    if not 1<=max_rows<=5000 or not 1<=max_columns<=200:raise ValueError('Discovery bounds must be within 1-5000 rows and 1-200 columns.')
    wb=load_workbook(io.BytesIO(blob),data_only=False); result=[]
    for ws in wb:
        nr=min(ws.max_row,max_rows);nc=min(ws.max_column,max_columns);cols=[]
        for c in range(1,nc+1):
            examples=[];counts=Counter();colors=Counter()
            for row in range(1,nr+1):
                cell=ws.cell(row,c);v=cell.value
                if v is None:continue
                if len(examples)<8:examples.append({'cell':cell.coordinate,'value':str(v)[:120]})
                if cell.data_type=='f':counts['formula']+=1
                else:
                    try:_,kind=_number(v);counts[kind]+=1
                    except ValueError:counts['other']+=1
                for kind in ('font','fill'):
                    col=_colour(cell,kind)
                    if col:colors[kind+':'+col]+=1
            if examples:cols.append({'column':c,'letter':get_column_letter(c),'examples':examples,'counts':dict(counts),'rgb_counts':dict(colors)})
        result.append({'sheet':ws.title,'dimensions':[ws.max_row,ws.max_column],'scanned':[nr,nc],'truncated':nr<ws.max_row or nc<ws.max_column,'merged_ranges':[str(x) for x in ws.merged_cells.ranges],'conditional_formatting':len(ws.conditional_formatting)>0,'columns':cols})
    return {'source':str(path),'sha256':hashlib.sha256(blob).hexdigest(),'sheets':result,'interpretation':'Column examples are candidates, not inferred factor or metric assignments.'}

def prepare(config,output_dir):
    path=Path(config['source_file']).resolve();blob=path.read_bytes();digest=hashlib.sha256(blob).hexdigest()
    if config.get('expected_sha256')!=digest:raise ValueError('Source SHA-256 must match the discovery result; rescan if changed.')
    root=Path(output_dir).resolve()
    if not root.is_dir() or any(root.iterdir()):raise ValueError('Use an existing empty output directory.')
    rows=config['row_levels'];cols=config['column_levels'];cells=list(itertools.product(rows,cols))
    if len(rows)!=3 or len(cols)!=2 or len(set(rows))!=3 or len(set(cols))!=2 or any(not isinstance(x,str) or not x.strip() or any(c in x for c in '\t\r\n') for x in rows+cols):raise ValueError('Specify distinct nonempty 3 x 2 factor labels.')
    mapping=config.get('group_mapping',{})
    if mapping and (len(mapping)!=6 or {tuple(v) for v in mapping.values()}!=set(cells)):raise ValueError('group_mapping must map six source labels bijectively onto six cells.')
    selection=config.get('selection',{'mode':'all'});mode=selection.get('mode')
    if mode not in ('all','font','fill'):raise ValueError('Selection must explicitly be all, font or fill.')
    colours={str(x).upper().removeprefix('#') for x in selection.get('rgb',[])}
    if mode!='all' and (not colours or any(not re.fullmatch('[0-9A-F]{6}',c) for c in colours)):raise ValueError('Explicit RGB colours are required.')
    values=load_workbook(io.BytesIO(blob),data_only=True);styles=load_workbook(io.BytesIO(blob),data_only=False)
    specs=config['metrics'];names=[x['name'] for x in specs]
    if not names or any(not isinstance(n,str) or not n.strip() or any(ch in n for ch in '\t\r\n') for n in names) or len(set(names))!=len(names):raise ValueError('Metric names must be nonempty and unique.')
    audit={'source':str(path),'sha256':digest,'selection':selection,'row_levels':rows,'column_levels':cols,'error_bars':'SEM (sample SD / sqrt(n))','statistical_tests':'not performed','metrics':[]};outputs=[]
    for idx,spec in enumerate(specs,1):
        ws=values[spec['sheet']];wf=styles[spec['sheet']];start=int(spec['first_row']);end=int(spec['last_row'])
        if not 1<=start<=end<=ws.max_row or end-start>100000:raise ValueError('Invalid or excessive data range.')
        if mode!='all' and len(wf.conditional_formatting):raise ValueError('Conditional formatting colours cannot be reliably resolved; inspect before using colour selection.')
        selected={cell:[] for cell in cells};records=[];seen=set();layout=spec['layout']
        if layout=='wide':
            fields=spec['columns']; pairs=[tuple(f['factor']) for f in fields]
            if set(pairs)!=set(cells):raise ValueError('Wide columns must explicitly cover all six factor cells.')
            numbers=[int(f['column']) for f in fields]
            if any(c<1 or c>ws.max_column for c in numbers) or len(numbers)!=len(set(numbers)):raise ValueError('Wide columns must be unique and inside the worksheet.')
        elif layout=='long':fields=[{'column':spec['value_column']}]
        else:raise ValueError('Layout must be long or wide.')
        def label(row,col):
            value,source=_merged_value(ws,row,int(col));return (str(value).strip() if value is not None else None),source
        for row in range(start,end+1):
            for field in fields:
                col=int(field['column'])
                if not 1<=col<=ws.max_column:raise ValueError('Value column is outside the worksheet.')
                fc=wf.cell(row,col);value=ws.cell(row,col).value
                if value is None:
                    if fc.data_type=='f':raise ValueError(f'{ws.title}!{fc.coordinate}: formula has no cached result.')
                    continue
                color=_colour(fc,mode) if mode!='all' else None
                if mode!='all' and color not in colours:continue
                if layout=='wide':factor=tuple(field['factor']);label_sources=[]
                elif mapping:
                    g,src=label(row,spec['group_column']);label_sources=[src]
                    if g not in mapping:raise ValueError(f'{ws.title}!{fc.coordinate}: unknown or missing group {g!r}.')
                    factor=tuple(mapping[g])
                else:
                    a,sa=label(row,spec['row_factor_column']);b,sb=label(row,spec['column_factor_column']);factor=(a,b);label_sources=[sa,sb]
                    if factor not in selected:raise ValueError(f'{ws.title}!{fc.coordinate}: unmapped factor labels {factor!r}.')
                try:number,conversion=_number(value)
                except ValueError as exc:raise ValueError(f'{ws.title}!{fc.coordinate}: {exc}; observed {value!r}') from exc
                sample=None
                if spec.get('sample_column'):
                    sample,_=label(row,spec['sample_column']);key=(factor,sample)
                    if not sample or key in seen:raise ValueError(f'{ws.title}!{fc.coordinate}: empty or duplicate sample identifier within factor cell.')
                    seen.add(key)
                selected[factor].append(number);records.append({'cell':fc.coordinate,'sample':sample,'factor_row':factor[0],'factor_column':factor[1],'value':number,'source_type':conversion,'original_value':str(value),'factor_source_cells':label_sources,'rgb':color})
        counts={str(c):len(selected[c]) for c in cells}
        if any(len(selected[c])<2 for c in cells):raise ValueError(f"{spec['name']}: SEM requires at least two observations per cell: {counts}")
        reps=max(map(len,selected.values()));out=io.StringIO(newline='');writer=csv.writer(out,delimiter='\t',lineterminator='\n')
        writer.writerow(['Factor']+sum(([x]+['']*(reps-1) for x in cols),[]))
        for a in rows:
            line=[a]
            for b in cols:
                vals=selected[(a,b)];line += [format(v,'.17g') for v in vals]+['']*(reps-len(vals))
            writer.writerow(line)
        filename=f'metric_{idx:03}.tsv';outputs.append((filename,out.getvalue()))
        audit['metrics'].append({'name':spec['name'],'sheet':ws.title,'file':filename,'replicates_columns':reps,'selected':records,'summary':[{'row':a,'column':b,'n':len(selected[(a,b)]),'mean':statistics.mean(selected[(a,b)]),'sem':statistics.stdev(selected[(a,b)])/math.sqrt(len(selected[(a,b)]))} for a,b in cells]})
    for filename,data in outputs:(root/filename).write_text(data,encoding='utf-8-sig')
    (root/'plot_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    return {'audit_file':str(root/'plot_audit.json'),'tsv_files':[str(root/x[0]) for x in outputs],'source_sha256':digest,'metric_count':len(outputs),'prism_project_created':False,'graph_created':False}
