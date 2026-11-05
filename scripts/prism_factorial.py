"""Balanced two-factor data preparation and native Prism validation.

This module never controls Prism or changes the source workbook/project.
"""
from __future__ import annotations
import csv, hashlib, io, itertools, json, math, re, tempfile, zipfile
from pathlib import Path
import numpy as np
from scipy.stats import f, studentized_range
from openpyxl import load_workbook
from prism_project import inspect, quote, write_script


def _write(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def _safe_name(value):
    value = re.sub(r'[\\/:*?"<>|\[\]%]', '_', str(value)).strip(' ._')
    return value[:80] or 'metric'


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as fobj:
        for block in iter(lambda: fobj.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def prepare(config, output_dir):
    """Stage all results before publishing; never leave partial output after validation failure."""
    root=Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=True)
    names=['factorial_audit.json']+[f'metric_{i:03d}.tsv' for i in range(1,len(config['metrics'])+1)]
    for name in names:
        if (root/name).exists():raise FileExistsError(f'Output already exists: {root/name}; use a new directory.')
    with tempfile.TemporaryDirectory(prefix='.prism-stage-',dir=root) as tmp:
        staged=Path(tmp); result=_prepare(config,staged)
        audit=json.loads((staged/'factorial_audit.json').read_text(encoding='utf-8'))
        for item in audit['metrics']:item['tsv']=str(root/Path(item['tsv']).name)
        _write(staged/'factorial_audit.json',audit)
        published=[]
        try:
            for name in names:
                dest=root/name
                if dest.exists():raise FileExistsError(f'Output appeared during processing: {dest}')
                (staged/name).replace(dest);published.append(dest)
        except Exception:
            for path in published:path.unlink(missing_ok=True)
            raise
    result['audit_file']=str(root/'factorial_audit.json')
    result['tsv_files']=[str(root/Path(p).name) for p in result['tsv_files']]
    return result


def _prepare(config, output_dir):
    """Explicit group mapping, independent balanced 3 x 2 design; no implicit exclusions."""
    root = Path(output_dir).resolve(); root.mkdir(parents=True, exist_ok=True)
    source = Path(config['source_file']).resolve()
    if not source.is_file(): raise ValueError(f'Excel file not found: {source}')
    diets = config['diets']; treatments = config['treatments']; mapping = config['group_mapping']
    if len(diets) != 3 or len(set(diets)) != 3 or len(treatments) != 2 or len(set(treatments)) != 2:
        raise ValueError('This workflow requires three distinct diet levels and two distinct treatment levels.')
    if any(not isinstance(v,str) or not v.strip() or any(ch in v for ch in '\t\r\n"') for v in diets+treatments):
        raise ValueError('Factor labels must be nonempty strings without tabs, newlines or quotes.')
    if config.get('independent_observations') is not True:
        raise ValueError('Explicit independent_observations=true is required. Matched/repeated observations need another model.')
    cells = list(itertools.product(diets, treatments))
    mapped = [tuple(v) for v in mapping.values()]
    if len(mapped) != 6 or set(mapped) != set(cells):
        raise ValueError('group_mapping must map exactly six labels bijectively to the 3 x 2 factor cells.')
    alpha = float(config.get('alpha', 0.05))
    if not 0 < alpha < 1: raise ValueError('alpha must lie strictly between 0 and 1.')
    # Use one immutable in-memory snapshot for both formula and cached values.
    # This also avoids holding the user's workbook open on Windows.
    source_bytes=source.read_bytes()
    data = load_workbook(io.BytesIO(source_bytes), data_only=True, read_only=True)
    formulas = load_workbook(io.BytesIO(source_bytes), data_only=False, read_only=True)
    sheet = config['sheet']; ws = data[sheet]; wf = formulas[sheet]
    start = int(config['first_row']); end = int(config['last_row'])
    if not 1 <= start <= end <= ws.max_row: raise ValueError('Invalid explicit row range.')
    gc = int(config['group_column']); sc = int(config['sample_column'])
    metrics = config['metrics']
    if not metrics or len({m['name'] for m in metrics}) != len(metrics): raise ValueError('Metric names must be nonempty and unique.')
    if len({_safe_name(m['name']) for m in metrics}) != len(metrics): raise ValueError('Metric names collide after Prism-safe sanitization.')
    targets=[root/'factorial_audit.json']+[root/f'metric_{i:03d}.tsv' for i in range(1,len(metrics)+1)]
    existing=[str(p) for p in targets if p.exists()]
    if existing: raise FileExistsError(f'Output already exists; choose a new output directory: {existing[0]}')
    exclusions = config.get('exclude_samples', [])
    excluded = {}
    for x in exclusions:
        k = (str(x['group']), str(x['sample']))
        if k in excluded or not str(x.get('reason','')).strip(): raise ValueError('Each exclusion needs a unique group/sample and a reason.')
        if k[0] not in mapping: raise ValueError(f'Exclusion references unknown group: {k}')
        excluded[k] = x['reason']
    rows = []; seen = set()
    for row in range(start, end + 1):
        label = ws.cell(row, gc).value; sample = ws.cell(row, sc).value
        if label is None and sample is None: continue
        if label is None or sample is None: raise ValueError(f'Incomplete group/sample at row {row}.')
        label, sample = str(label).strip(), str(sample).strip()
        if label not in mapping: raise ValueError(f'Unknown group label {label!r} at row {row}; specify the mapping explicitly.')
        if (label, sample) in seen: raise ValueError(f'Duplicate sample ID within group: {label}, {sample}')
        seen.add((label,sample)); rows.append((row,label,sample,tuple(mapping[label])))
    unknown_exclusions = set(excluded) - seen
    if unknown_exclusions: raise ValueError(f'Exclusions not found in the specified rows: {sorted(unknown_exclusions)}')
    factor_names=config.get('factor_names',['Diet','Treatment'])
    if len(factor_names)!=2 or any(not isinstance(v,str) or not v.strip() or any(c in v for c in '\r\n\t') for v in factor_names):
        raise ValueError('factor_names must contain two nonempty single-line strings.')
    result = {'version':1, 'source_file':str(source), 'source_sha256':hashlib.sha256(source_bytes).hexdigest(), 'sheet':sheet,
              'factor_rows':diets, 'factor_columns':treatments, 'group_mapping':mapping,
              'factor_names':factor_names,
              'independent_observations':True, 'alpha':alpha, 'error_bars':'SEM',
              'method':'ordinary two-way ANOVA with interaction; all six cell means Tukey HSD',
              'excluded_samples':exclusions, 'metrics':[]}
    for number, metric in enumerate(metrics, 1):
        col = int(metric['column']); groups={cell:[] for cell in cells}; records=[]
        for row,label,sample,cell in rows:
            val = ws.cell(row,col).value; formula=wf.cell(row,col).value
            if isinstance(formula,str) and formula.startswith('=') and val is None:
                raise ValueError(f'Missing cached formula value at {sheet}!{ws.cell(row,col).coordinate}; recalculate workbook first.')
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(float(val)):
                raise ValueError(f'Non-numeric/missing value at {sheet}!{ws.cell(row,col).coordinate}: {val!r}')
            is_excluded=(label,sample) in excluded
            records.append({'row':row,'cell':ws.cell(row,col).coordinate,'group':label,'sample':sample,
                            'diet':cell[0],'treatment':cell[1],'value':float(val),'excluded':is_excluded})
            if not is_excluded: groups[cell].append(float(val))
        counts = {str(k):len(v) for k,v in groups.items()}
        if len(set(counts.values())) != 1 or not counts or min(counts.values()) < 2:
            raise ValueError(f'Balanced design with >=2 valid repeats per cell required for {metric["name"]}: {counts}')
        n = len(groups[cells[0]])
        if 'expected_n' in config and n != int(config['expected_n']): raise ValueError(f'{metric["name"]}: expected n={config["expected_n"]}, actual n={n}.')
        arr = np.array([[groups[(d,t)] for t in treatments] for d in diets],dtype=float)
        gm=arr.mean(); dm=arr.mean(axis=(1,2)); tm=arr.mean(axis=(0,2)); cm=arr.mean(axis=2)
        ss_d=2*n*np.sum((dm-gm)**2); ss_t=3*n*np.sum((tm-gm)**2)
        ss_i=n*np.sum((cm-dm[:,None]-tm[None,:]+gm)**2); sse=np.sum((arr-cm[:,:,None])**2)
        df=6*(n-1); mse=float(sse/df)
        if mse <= 0: raise ValueError(f'{metric["name"]}: zero residual variance; ANOVA/Tukey undefined.')
        ps={'diet':float(f.sf((ss_d/2)/mse,2,df)), 'treatment':float(f.sf(ss_t/mse,1,df)),
            'interaction':float(f.sf((ss_i/2)/mse,2,df))}
        means={c:float(np.mean(groups[c])) for c in cells}; sem={c:float(np.std(groups[c],ddof=1)/math.sqrt(n)) for c in cells}
        pairs=[]; nonsig={}
        for a,b in itertools.combinations(cells,2):
            q=abs(means[a]-means[b])/math.sqrt(mse/n); p=float(studentized_range.sf(q,6,df))
            nonsig[frozenset((a,b))]=p>=alpha; pairs.append({'a':list(a),'b':list(b),'p_adjusted':p})
        cliques=[set(comb) for size in range(1,7) for comb in itertools.combinations(cells,size)
                 if all(nonsig[frozenset((a,b))] for a,b in itertools.combinations(comb,2))]
        cliques=[c for c in cliques if not any(c < other for other in cliques)]
        cliques.sort(key=lambda c:(-max(means[k] for k in c), sorted(c)))
        letters={str(k):''.join(chr(97+i) for i,c in enumerate(cliques) if k in c) for k in cells}
        filename=f'metric_{number:03d}.tsv'; path=root/filename
        if path.exists(): raise FileExistsError(f'Output exists: {path}; use an empty output directory.')
        # Retain excluded raw observations with Prism's exclusion star, pad as needed.
        all_cells={c:[r for r in records if (r['diet'],r['treatment'])==c] for c in cells}
        reps=max(len(v) for v in all_cells.values())
        with path.open('w',encoding='utf-8-sig',newline='') as fh:
            w=csv.writer(fh,delimiter='\t',lineterminator='\n');w.writerow(['Factor']+sum(([t]+['']*(reps-1) for t in treatments),[]))
            for diet in diets:
                values=[]
                for treatment in treatments:
                    rr=all_cells[(diet,treatment)];values += [format(r['value'],'.17g')+('*' if r['excluded'] else '') for r in rr]+['']*(reps-len(rr))
                w.writerow([diet]+values)
        result['metrics'].append({'index':number,'name':metric['name'],'safe_name':_safe_name(metric['name']),
             'source_column':col,'tsv':str(path),'replicates':reps,'n':n,'records':records,
             'mean':{str(k):v for k,v in means.items()},'sem':{str(k):v for k,v in sem.items()},
             'p_values':ps,'tukey':pairs,'letters':letters})
    audit=root/'factorial_audit.json'
    if audit.exists(): raise FileExistsError(f'Output exists: {audit}')
    _write(audit,result)
    return {'audit_file':str(audit),'source_sha256':result['source_sha256'],'metrics':len(metrics),
            'n_per_cell':[x['n'] for x in result['metrics']], 'analysis':result['method'],
            'tsv_files':[x['tsv'] for x in result['metrics']], 'exclusions':len(exclusions)}


def annotation_plan(audit_file, metric=None):
    audit=json.loads(Path(audit_file).read_text(encoding='utf-8')); names=audit.get('factor_names',['Diet','Treatment'])
    items=[m for m in audit['metrics'] if metric is None or m['name']==metric]
    if not items:raise ValueError('Metric not found in audit; use its exact recorded name.')
    def fmt(v): return '< 0.0001' if v<0.0001 else '= '+format(v,'.4f')
    return {'items':[{'name':m['name'],'p_text':f"P ({names[0]}) {fmt(m['p_values']['diet'])}\nP ({names[1]}) {fmt(m['p_values']['treatment'])}\nP (Interaction) {fmt(m['p_values']['interaction'])}",
                      'letters':m['letters'],'n_per_cell':m['n']} for m in items],
            'warning':'P text is a static copy; it must be visually placed and rechecked after data changes. CLD must be linked in Prism.'}


def combine_audits(audit_files, output_file):
    if len(audit_files)<2:raise ValueError('Supply at least two prepared audits to combine.')
    out=Path(output_file).resolve()
    if out.exists():raise FileExistsError(f'Output exists: {out}')
    audits=[json.loads(Path(p).read_text(encoding='utf-8')) for p in audit_files]
    first=audits[0];keys=('factor_rows','factor_columns','group_mapping','independent_observations','alpha','factor_names')
    for item in audits[1:]:
        if any(first.get(k)!=item.get(k) for k in keys):raise ValueError('Audits have different factor mappings, independence, alpha or factor names; do not merge.')
    metrics=[dict(m) for a in audits for m in a['metrics']]
    if len({m['name'] for m in metrics})!=len(metrics) or len({m['safe_name'] for m in metrics})!=len(metrics):
        raise ValueError('Duplicate metric titles across audits; rename explicitly before preparation.')
    for i,m in enumerate(metrics,1):m['index']=i
    sources=[{'source_file':a['source_file'],'source_sha256':a['source_sha256'],'sheet':a['sheet']} for a in audits]
    merged={**first,'metrics':metrics,'sources':sources,'combined':True,
            'excluded_samples':[{'sheet':a['sheet'],**x} for a in audits for x in a.get('excluded_samples',[])]}
    out.parent.mkdir(parents=True,exist_ok=True);_write(out,merged)
    return {'audit_file':str(out),'sources':sources,'metric_count':len(metrics),
            'note':'TSV files remain in the original preparation directories; keep them available.'}


def verify_native_export(audit_file, metric, export_file, output_file):
    """Verify a Prism-exported raw grouped TSV, independent of Prism project format."""
    if Path(output_file).exists():raise FileExistsError(f'Output exists: {output_file}; choose a new verification file.')
    audit=json.loads(Path(audit_file).read_text(encoding='utf-8'));found=[m for m in audit['metrics'] if m['name']==metric]
    if len(found)!=1:raise ValueError('Metric must exactly match one indicator name in the audit.')
    m=found[0];blob=Path(export_file).read_bytes();decoded=None
    encodings=['utf-16'] if blob.startswith((b'\xff\xfe',b'\xfe\xff')) else ['utf-8-sig','gb18030']
    for encoding in encodings:
        try:decoded=blob.decode(encoding);break
        except UnicodeDecodeError:pass
    if decoded is None:raise ValueError('Cannot decode exported TSV; check its encoding and export again.')
    rows=list(csv.reader(io.StringIO(decoded),delimiter='\t'));diets=audit['factor_rows'];treat=audit['factor_columns'];nr=m['replicates'];issues=[]
    matched=[(i,row) for i,row in enumerate(rows) if row and row[0].strip() in diets]
    if [row[0].strip() for _,row in matched]!=diets:
        raise ValueError('Export must contain exactly the three expected row labels in their recorded order.')
    # Accept Prism's repeated column labels and sparse imported TSV headers.
    headers=[]
    for row in rows[:matched[0][0]]:
        values=(row[1:]+['']*(2*nr))[:2*nr];expanded=[];last=None
        for val in values:
            if val.strip():last=val.strip()
            expanded.append(last)
        if expanded==[treat[0]]*nr+[treat[1]]*nr:headers.append(row)
    if len(headers)!=1:issues.append('Treatment header was not uniquely verified; export the full grouped table with dataset names.')
    checked=0;maximum=0.0
    for (_,row),diet in zip(matched,diets):
        actual=row[1:]
        if len(actual)>2*nr and any(x.strip() for x in actual[2*nr:]):issues.append(f'Unexpected extra columns: {diet}');continue
        actual=(actual+['']*(2*nr))[:2*nr];expected=[]
        for tr in treat:
            records=[r for r in m['records'] if r['diet']==diet and r['treatment']==tr]
            expected.extend(records+[None]*(nr-len(records)))
        for cell,rec in zip(actual,expected):
            raw=cell.strip();is_excluded=raw.endswith('*');number=raw[:-1].strip() if is_excluded else raw
            if rec is None:
                if raw:issues.append(f'Expected empty padded cell for {diet}.')
                continue
            if not number:issues.append(f'Missing value: {rec["cell"]}');continue
            try:value=float(number)
            except ValueError:issues.append(f'Invalid numeric value or exclusion marker: {rec["cell"]}');continue
            if not math.isfinite(value):issues.append(f'Nonfinite exported value: {rec["cell"]}');continue
            delta=abs(value-rec['value']);maximum=max(maximum,delta);checked+=1
            if not math.isclose(value,rec['value'],rel_tol=1e-12,abs_tol=1e-12):issues.append(f'Value or export precision mismatch: {rec["cell"]}')
            if is_excluded!=rec['excluded']:issues.append(f'Exclusion marker mismatch: {rec["cell"]}')
    sources=audit.get('sources',[{'source_file':audit['source_file'],'source_sha256':audit['source_sha256']}])
    for entry in sources:
        source=Path(entry['source_file'])
        if not source.is_file() or _hash(source)!=entry['source_sha256']:issues.append(f'Source missing or changed: {source}')
    report={'passed':not issues,'metric':metric,'verification_mode':'native_grouped_tsv',
            'raw_values_checked':checked,'max_numeric_difference':maximum,'errors':issues,
            'header_verified':len(headers)==1,'analysis_results_verified':False,'uid_preservation_verified':False,
            'visual_check_required':True,'precision_note':'A rounded native export may fail; increase precision before claiming raw-value equality.'}
    _write(output_file,report);return report


def build(audit_file, template_file, output_project, script_file):
    """Build commands only for a validated one-family native Prism template."""
    audit=json.loads(Path(audit_file).read_text(encoding='utf-8'));template=Path(template_file).resolve();out=Path(output_project).resolve()
    sources=audit.get('sources',[{'source_file':audit['source_file'],'source_sha256':audit['source_sha256']}])
    for entry in sources:
        source=Path(entry['source_file'])
        if not source.is_file() or _hash(source)!=entry['source_sha256']:
            raise ValueError('Excel source is missing or changed since preparation; review and regenerate the audit.')
    if out==template or out.exists(): raise ValueError('Output project must be a new path, distinct from the template.')
    inf=inspect(template)
    if not inf.get('native_zip_supported'): raise ValueError('Automatic template checks require a supported Prism ZIP; use manual native fallback.')
    if any(len(inf['sheets'].get(k,[]))!=1 for k in ('data','graphs','analyses')):
        raise ValueError('Template must contain exactly one data table, one graph and one two-way analysis.')
    table=inf['sheets']['data'][0];graph=inf['sheets']['graphs'][0];auid=inf['sheets']['analyses'][0]['uid']
    if table['format']!='grouped' or table['data_format']!='y_replicates' or table['dataset_count']!=2 or set(table['dataset_uids'])!=set(graph['input_datasets']):
        raise ValueError('Template must link one grouped raw-replicate table with two data sets to the graph.')
    with zipfile.ZipFile(template) as z:
        analysis=json.loads(z.read(f'analyses/{auid}/sheet.json'))
        parameters=json.loads(z.read(f'analyses/{auid}/parameters.json'))['content']
        res=json.loads(z.read(f'analyses/{auid}/results.json'))['content']['ordinaryAnovaModel']
        if analysis['analysisClass']!='TWO_WAY_ANOVA' or analysis['inputSheets'][0]['uid']!=table['uid'] or res['multipleComparisons']['method']!='Tukey' or res['multipleComparisons']['comparisonPerFamilyCount']!=15 or res['compactLetterDisplay']['status']!='VALID':
            raise ValueError('Template must have linked ordinary two-way ANOVA, all 15 Tukey comparisons and valid CLD.')
        if parameters.get('experimentalDesign')!='ORDINARY_ANOVA' or not math.isclose(res['anovaTable']['rowFactor']['fTest']['pValue']['level'],audit['alpha']):
            raise ValueError('Template must be ordinary independent ANOVA with the same alpha as the audit.')
        if res['dataSummary']['rowCount']!=3 or res['dataSummary']['colCount']!=2 or res['compactLetterDisplay']['sampleCount']!=6:
            raise ValueError('Template must have exactly three row levels, two column levels and six CLD groups.')
    if any(not Path(m['tsv']).is_file() for m in audit['metrics']): raise ValueError('Prepared TSV file missing.')
    commands=[f'Save {quote(out)}']
    for i,m in enumerate(audit['metrics'],1):
        if i>1: commands += ['GoTo G 1',f'DuplicateFamily {quote("batch_"+str(i)+"_")} CLEAR']
        commands += [f'GoTo D {i}','ClearTable',f'SetYReplicates {m["replicates"]}',f'Import {quote(m["tsv"])}, 0, -1',
                     f'SetSheetTitle {quote(m["safe_name"]+" data")}',f'GoTo G {i}',f'SetSheetTitle {quote(m["safe_name"])}',
                     f'SetAxisTitle Y {quote(m["name"].replace("%","%%"))}']
    commands += [f'Save {quote(out)}','CloseScriptDialog']
    write_script(script_file,commands)
    return {'commands':commands,'script_file':str(Path(script_file).resolve()),'output_project':str(out),
            'expected_data_graph_analysis_count':len(audit['metrics']),'template_sha256':inf['sha256'],
            'warning':'P values are NOT automatically placed on graphs; add and verify explicitly. Verify SEM, colors, font and labels visually.'}


def verify(audit_file, project_file, output_file):
    """Compare raw numeric cells, graph/analysis links, ANOVA and all Tukey P values."""
    audit=json.loads(Path(audit_file).read_text(encoding='utf-8')); inf=inspect(project_file); issues=[];nvalues=npairs=0
    if not inf.get('native_zip_supported'): raise ValueError('Unsupported project; use Prism native high-precision TSV/results export for verification.')
    k=len(audit['metrics']);s=inf['sheets']
    if any(len(s.get(x,[]))!=k for x in ('data','graphs','analyses')): raise ValueError('Unexpected data/graph/analysis counts; inspect before verification.')
    maxp=maxq=0.0
    with zipfile.ZipFile(project_file) as z:
        d=json.loads(z.read('document.json'))
        for i,m in enumerate(audit['metrics']):
            t=s['data'][i];g=s['graphs'][i];auid=s['analyses'][i]['uid'];a=json.loads(z.read(f'analyses/{auid}/sheet.json'))
            if a['inputSheets'][0]['uid']!=t['uid'] or set(g['input_datasets'])!=set(t['dataset_uids']):issues.append([m['name'],'links'])
            raw=list(csv.reader(io.StringIO(z.read(f"data/tables/{t['table_uid']}/data.csv").decode('utf-8-sig'))))
            for j,diet in enumerate(audit['factor_rows']):
                expected=[r for treatment in audit['factor_columns'] for r in m['records'] if r['diet']==diet and r['treatment']==treatment]
                # To keep exclusion/padding verification exact, require equal physical counts per cell here.
                sizes=[sum(r['diet']==diet and r['treatment']==tr for r in m['records']) for tr in audit['factor_columns']]
                if sizes!=[m['replicates']]*2:issues.append([m['name'],'padded physical replicates need native export exclusion verification']);continue
                if raw[j][0]!=diet or len(raw[j])!=1+len(expected):issues.append([m['name'],diet,'shape']);continue
                for actual,record in zip(raw[j][1:],expected):
                    nvalues+=1
                    if not math.isclose(float(actual),record['value'],rel_tol=1e-12,abs_tol=1e-12):issues.append([m['name'],record['cell'],'value'])
            if audit['excluded_samples']:issues.append([m['name'],'excluded flags require native export verification'])
            model=json.loads(z.read(f'analyses/{auid}/results.json'))['content']['ordinaryAnovaModel']
            for k1,k2 in [('rowFactor','diet'),('colFactor','treatment'),('rowFactorVsColFactor','interaction')]:
                delta=abs(model['anovaTable'][k1]['fTest']['pValue']['value']-m['p_values'][k2]);maxp=max(maxp,delta)
                if delta>1e-8:issues.append([m['name'],k2,delta])
            mc=model['multipleComparisons']; expected={frozenset((tuple(x['a']),tuple(x['b']))):x['p_adjusted'] for x in m['tukey']}
            if mc['method']!='Tukey' or mc['comparisonPerFamilyCount']!=15 or model['compactLetterDisplay']['status']!='VALID':issues.append([m['name'],'analysis'])
            found=0
            for first in mc['tests'].values():
                for entry in first['value'].values():
                    v=entry['value'];pair=[]
                    for key in ('sample1','sample2'):
                        identity=v[key]['id'];pair.append((identity['row']['title'],identity['col']['title']))
                    delta=abs(v['pValueAdjusted']['value']-expected[frozenset(pair)]);maxq=max(maxq,delta);found+=1;npairs+=1
                    if delta>1e-8:issues.append([m['name'],'tukey',pair,delta])
            if found!=15:issues.append([m['name'],'pair count',found])
    report={'passed':not issues,'metrics':k,'values_checked':nvalues,'tukey_pairs_checked':npairs,'max_anova_p_difference':maxp,
            'max_tukey_p_difference':maxq,'issues':issues,'visual_check_required':True,'graph_p_text_verified':False}
    _write(output_file,report);return report
