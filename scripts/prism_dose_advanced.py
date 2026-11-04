"""Auditable independent 4PL analysis; never claims to be a Prism fit."""
from __future__ import annotations
import csv, json, math
from pathlib import Path

def analyze(points, direction='decreasing', effect=20, effect_definition='relative', control=None, full_effect=None,
            fixed_bottom=None, fixed_top=None, fixed_hill=None, weighting='none',
            bootstrap_samples=0, independent_replicates=False, seed=0):
 import numpy as np
 from scipy.optimize import least_squares
 from scipy.special import expit
 if direction not in ('decreasing','increasing'):raise ValueError('direction must be decreasing or increasing')
 if effect_definition not in ('relative','absolute'):raise ValueError('effect_definition must be relative or absolute')
 if weighting not in ('none','inverse_y_squared'):raise ValueError('weighting must be none or inverse_y_squared')
 if not math.isfinite(float(effect)) or not 0<float(effect)<100:raise ValueError('effect must be strictly between 0 and 100')
 for n,v in [('fixed_bottom',fixed_bottom),('fixed_top',fixed_top),('fixed_hill',fixed_hill),('control',control),('full_effect',full_effect)]:
  if v is not None and not math.isfinite(float(v)):raise ValueError(n+' must be finite')
 if fixed_hill is not None and not .02<=fixed_hill<=20:raise ValueError('fixed_hill must be a positive magnitude between 0.02 and 20')
 if fixed_top is not None and fixed_bottom is not None and fixed_top<=fixed_bottom:raise ValueError('fixed_top must exceed fixed_bottom')
 if effect_definition=='absolute':
  if control is None or full_effect is None or control==full_effect:raise ValueError('absolute effect requires distinct numeric control and full_effect reference responses')
  if (direction=='decreasing' and control<=full_effect) or (direction=='increasing' and control>=full_effect):raise ValueError('reference direction conflicts with curve direction')
 if isinstance(bootstrap_samples,bool) or not isinstance(bootstrap_samples,int) or not 0<=bootstrap_samples<=2000:raise ValueError('bootstrap_samples must be an integer between 0 and 2000')
 if bootstrap_samples and (bootstrap_samples<100 or independent_replicates is not True):raise ValueError('bootstrap requires at least 100 resamples and explicit independent_replicates=true; paired or clustered data need a different resampling design')
 try:x=np.array([float(p['concentration']) for p in points]);y=np.array([float(p['response']) for p in points])
 except (TypeError,ValueError,KeyError) as e:raise ValueError('each point needs numeric concentration and response') from e
 if len(x)<5 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or np.any(x<0):raise ValueError('need at least five finite observations and nonnegative concentrations')
 unique=np.unique(x[x>0]);rng=np.random.default_rng(seed)
 if len(unique)<4 or len(np.unique(y))<4:raise ValueError('need at least four distinct positive concentrations and four distinct responses')
 if weighting=='inverse_y_squared' and np.any(y<=0):raise ValueError('inverse_y_squared requires strictly positive individual responses')
 xmin,xmax=float(unique.min()),float(unique.max());span=float(np.ptp(y))
 if span<=0:raise ValueError('constant responses cannot identify a curve')
 lowy,highy=float(y.min()-20*span),float(y.max()+20*span)
 # Fit a positive plateau span, log midpoint, and positive Hill magnitude.
 def fit(xx,yy):
  names=[];p0=[];lo=[];hi=[]
  def add(name,val,a,b):names.append(name);p0.append(float(np.clip(val,a+1e-8,b-1e-8)));lo.append(a);hi.append(b)
  if fixed_top is None and fixed_bottom is None:
   add('bottom',float(yy.min()),lowy,highy);add('logspan',math.log(span),math.log(span)-20,math.log(span)+5)
  elif fixed_top is None or fixed_bottom is None:
   start=(fixed_top-float(yy.min())) if fixed_top is not None else (float(yy.max())-fixed_bottom)
   add('logspan',math.log(max(start,span*.01)),math.log(span)-20,math.log(span)+8)
  add('logmid',(math.log(xmin)+math.log(xmax))/2,math.log(xmin)-20,math.log(xmax)+20)
  if fixed_hill is None:add('loghill',0,math.log(.02),math.log(20))
  def unpack(p):
   q=dict(zip(names,p)); delta=math.exp(q['logspan']) if 'logspan' in q else float(fixed_top-fixed_bottom)
   bottom=float(fixed_bottom) if fixed_bottom is not None else (float(fixed_top)-delta if fixed_top is not None else q['bottom'])
   return bottom,bottom+delta,math.exp(q['logmid']),float(fixed_hill) if fixed_hill is not None else math.exp(q['loghill'])
  def pred(p,xx):
   bottom,top,mid,hill=unpack(p);z=np.zeros_like(xx,dtype=float);m=xx>0;z[m]=expit(hill*(np.log(xx[m])-math.log(mid)))
   return bottom+(top-bottom)*((1-z) if direction=='decreasing' else z)
  weights=np.ones_like(yy) if weighting=='none' else 1/np.abs(yy)
  res=least_squares(lambda p:(pred(p,xx)-yy)*weights,p0,bounds=(lo,hi),max_nfev=5000)
  if not res.success:raise ValueError('4PL optimizer did not converge: '+res.message)
  bottom,top,mid,hill=unpack(res.x)
  fraction=float(effect)/100
  target_y=(top-(top-bottom)*fraction if direction=='decreasing' else bottom+(top-bottom)*fraction) if effect_definition=='relative' else float(control)+(float(full_effect)-float(control))*fraction
  fraction_fit=(top-target_y)/(top-bottom) if direction=='decreasing' else (target_y-bottom)/(top-bottom)
  target=math.exp(math.log(mid)+(math.log(fraction_fit)-math.log1p(-fraction_fit))/hill) if 0<fraction_fit<1 else None
  norms=np.linalg.norm(res.jac,axis=0)
  condition=float(np.linalg.cond(res.jac/np.where(norms>0,norms,1)))
  return {'bottom':bottom,'top':top,'midpoint':mid,'hill_magnitude':hill,'target_response':target_y,'effect_concentration':target,'rss_unweighted':float(np.sum((pred(res.x,xx)-yy)**2)),'weighted_sum_squares':float(np.sum(res.fun**2)),'free_parameters':len(names),'jacobian_rank':int(np.linalg.matrix_rank(res.jac)),'jacobian_scaled_condition':condition if math.isfinite(condition) else None,'at_bound':bool(np.any(res.active_mask))}
 result=fit(x,y); warnings=[]
 counts=[int(np.sum(x==v)) for v in np.unique(x)]
 if min(counts)<2:warnings.append('At least one concentration has fewer than two replicates; its SD/SEM is not estimable.')
 if min(counts)<2 and bootstrap_samples:raise ValueError('stratified replicate bootstrap requires at least two independent observations at every concentration')
 if result['effect_concentration'] is None:warnings.append('The absolute target response is outside the fitted plateaus; no finite effect concentration exists for this fitted curve.')
 elif not xmin<=result['effect_concentration']<=xmax:warnings.append('Effect concentration is outside the observed positive concentration range (extrapolation).')
 if not xmin<=result['midpoint']<=xmax:warnings.append('Fitted midpoint is outside the observed positive range.')
 if result['jacobian_rank']<result['free_parameters']:warnings.append('Jacobian is rank deficient; parameters may be unidentifiable.')
 if result['jacobian_scaled_condition'] is None or result['jacobian_scaled_condition']>1e8:warnings.append('The scaled fit Jacobian is ill-conditioned; parameter estimates may be unstable.')
 if result['at_bound']:warnings.append('At least one fitted parameter reached a numerical bound.')
 if len(x)<=result['free_parameters']:warnings.append('No residual degrees of freedom remain for assessing model error.')
 if np.min(y)>result['bottom']+.15*(result['top']-result['bottom']) or np.max(y)<result['top']-.15*(result['top']-result['bottom']):warnings.append('Observed responses do not approach both fitted plateaus; plateau and effect estimates may be unstable.')
 sample_sds=[float(np.std(y[x==v],ddof=1)) for v in np.unique(x[x>0]) if np.sum(x==v)>1]
 if sample_sds and any(sd<.01*span for sd in sample_sds):warnings.append('Some SD error bars are below 1% of the observed response range and may be obscured by symbols; inspect the exported graph.')
 if np.any(x==0):warnings.append('Zero-concentration observations are fitted but omitted from log-axis graphs.')
 ci=None; valid=0
 if bootstrap_samples:
  grouped=[np.where(x==v)[0] for v in np.unique(x)];est=[]
  for _ in range(bootstrap_samples):
   indices=np.concatenate([rng.choice(ix,size=len(ix),replace=True) for ix in grouped])
   try:
    v=fit(x[indices],y[indices]);value=v['effect_concentration']
    if value is not None and math.isfinite(value) and not v['at_bound'] and v['jacobian_rank']==v['free_parameters']:est.append(value)
   except (ValueError,OverflowError,FloatingPointError):pass
  valid=len(est)
  if valid>=100 and valid/bootstrap_samples>=.8:ci=[float(v) for v in np.percentile(est,[2.5,97.5])]
  else:warnings.append('Too few valid independent-replicate bootstrap fits for a 95% percentile interval.')
 result.update({'engine':'SciPy independent 4PL; not Prism','direction':direction,'effect_percent':float(effect),'effect_definition':effect_definition,'absolute_references':{'control':control,'full_effect':full_effect} if effect_definition=='absolute' else None,'fixed_parameters':{'bottom':fixed_bottom,'top':fixed_top,'hill_magnitude':fixed_hill},'weighting':weighting,'n_observations':len(x),'n_by_concentration':[{'concentration':float(v),'n':int(np.sum(x==v))} for v in np.unique(x)],'positive_range':[xmin,xmax],'confidence_interval_95':ci,'confidence_method':'stratified independent-replicate percentile bootstrap' if bootstrap_samples else None,'bootstrap_requested':bootstrap_samples,'bootstrap_valid':valid,'seed':seed if bootstrap_samples else None,'warnings':warnings})
 return result

def batch(datasets,output_dir,common_options=None):
 import numpy as np
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 if not datasets or len(datasets)>50:raise ValueError('supply 1 to 50 datasets')
 dataset_names=[str(d.get('name','')).strip() for d in datasets]
 if any(not name for name in dataset_names) or len(set(dataset_names))!=len(dataset_names):raise ValueError('dataset names must be nonempty and unique')
 root=Path(output_dir).resolve()
 if root.exists() and any(root.iterdir()):raise FileExistsError('output directory must be new or empty')
 root.mkdir(parents=True,exist_ok=True)
 options=dict(common_options or {});results=[];names=set()
 fig,ax=plt.subplots(figsize=(7,5))
 for dataset in datasets:
  name=str(dataset.get('name','')).strip()
  names.add(name);points=dataset.get('points',[])
  try:
   r=analyze(points,**options);r['name']=name;results.append(r)
   x=np.array([float(p['concentration']) for p in points]);y=np.array([float(p['response']) for p in points]);u=np.unique(x[x>0]);t=np.geomspace(u.min(),u.max(),300)
   bottom,top,mid,hill=r['bottom'],r['top'],r['midpoint'],r['hill_magnitude'];z=1/(1+(t/mid)**hill);pred=bottom+(top-bottom)*(z if r['direction']=='decreasing' else 1-z)
   line=ax.plot(t,pred,label=name)[0]; color=line.get_color()
   groups=[(v,y[x==v]) for v in u]; means=[float(np.mean(a)) for _,a in groups]
   ax.scatter(u,means,s=18,color=color,zorder=3)
   for dose,values in groups:
    if len(values)>1:ax.errorbar([dose],[np.mean(values)],yerr=[np.std(values,ddof=1)],fmt='none',ecolor=color,capsize=2,alpha=.8)
  except (ValueError,ArithmeticError) as e:results.append({'name':name,'error':str(e)})
 ax.set_xscale('log');ax.set_xlabel('Concentration');ax.set_ylabel('Response');ax.set_title('Means ± SD; 4PL fits');
 if any('error' not in r for r in results):ax.legend()
 fig.tight_layout();fig.savefig(root/'overlay.png',dpi=180);fig.savefig(root/'overlay.svg');plt.close(fig)
 report={'datasets':results,'common_options':options,'batch_status':'complete' if all('error' not in r for r in results) else 'partial','note':'Independent 4PL fits; no statistical comparison of curves. Raw observations are retained in input.json.'}
 (root/'input.json').write_text(json.dumps(datasets,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
 (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
 with (root/'summary.csv').open('x',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['name','status','effect_concentration','ci_low','ci_high','bottom','top','midpoint','hill_magnitude','n','warnings_or_error'])
  for r in results:
   ci=r.get('confidence_interval_95') or [None,None];w.writerow([r['name'],'error' if 'error' in r else 'ok',r.get('effect_concentration'),*ci,r.get('bottom'),r.get('top'),r.get('midpoint'),r.get('hill_magnitude'),r.get('n_observations'),r.get('error','; '.join(r.get('warnings',[])))])
 return {**report,'output_dir':str(root),'files':{k:str(root/k) for k in ('overlay.png','overlay.svg','summary.csv','input.json','report.json')}}

def compare_independent(first,second,options=None,bootstrap_samples=200,independent_groups=False,seed=0):
 import numpy as np
 if independent_groups is not True:raise ValueError('Explicit independent_groups=true is required; paired or shared-control comparisons need a different design.')
 if isinstance(bootstrap_samples,bool) or not isinstance(bootstrap_samples,int) or not 100<=bootstrap_samples<=2000:raise ValueError('bootstrap_samples must be 100..2000')
 opts=dict(options or {})
 if opts.get('bootstrap_samples',0):raise ValueError('Pass bootstrap_samples only at comparison level.')
 a=analyze(first,**opts);b=analyze(second,**opts)
 if a['effect_concentration'] is None or b['effect_concentration'] is None:raise ValueError('Both fits must have finite effect concentrations.')
 rng=np.random.default_rng(seed)
 def groups(points):
  result={}
  for p in points:result.setdefault(float(p['concentration']),[]).append(p)
  if any(len(v)<2 for v in result.values()):raise ValueError('Each concentration must contain at least two independent replicates in each group.')
  return list(result.values())
 ga,gb=groups(first),groups(second);diff=[];ratio=[]
 def sample(group):return [group[i] for i in rng.integers(0,len(group),size=len(group))]
 for _ in range(bootstrap_samples):
  try:
   aa=analyze([p for g in ga for p in sample(g)],**opts);bb=analyze([p for g in gb for p in sample(g)],**opts)
   av,bv=aa['effect_concentration'],bb['effect_concentration']
   if av is not None and bv is not None and av>0 and bv>0 and not aa['at_bound'] and not bb['at_bound'] and aa['jacobian_rank']==aa['free_parameters'] and bb['jacobian_rank']==bb['free_parameters']:
    diff.append(bv-av);ratio.append(bv/av)
  except (ValueError,ArithmeticError):pass
 valid=len(diff);ok=valid>=100 and valid/bootstrap_samples>=.8
 return {'method':'independent groups, within-concentration percentile bootstrap; B minus A and B/A','first':a,'second':b,'difference_B_minus_A':b['effect_concentration']-a['effect_concentration'],'ratio_B_over_A':b['effect_concentration']/a['effect_concentration'],'difference_ci_95':[float(x) for x in np.percentile(diff,[2.5,97.5])] if ok else None,'ratio_ci_95':[float(x) for x in np.percentile(ratio,[2.5,97.5])] if ok else None,'bootstrap_requested':bootstrap_samples,'bootstrap_valid':valid,'seed':seed,'warnings':['No p-value or multiplicity adjustment is computed.']+([] if ok else ['Too few valid bootstrap fits for confidence intervals.'])}

def excel_points(source_file,sheet,concentration_column,response_column,first_row,last_row,group_column=None):
 import hashlib
 from openpyxl import load_workbook
 from openpyxl.utils import column_index_from_string
 p=Path(source_file).resolve()
 if not p.is_file() or p.suffix.lower() not in ('.xlsx','.xlsm'):raise ValueError('Provide an existing xlsx/xlsm file.')
 if not isinstance(first_row,int) or not isinstance(last_row,int) or first_row<1 or last_row<first_row or last_row-first_row>10000:raise ValueError('Specify valid bounded data rows (maximum 10001 rows).')
 cols=[column_index_from_string(c.upper()) for c in [concentration_column,response_column]+([group_column] if group_column else [])]
 if len(set(cols))!=len(cols):raise ValueError('The X, Y and group columns must be distinct.')
 if max(cols)-min(cols)>255:raise ValueError('Selected columns must span at most 256 columns.')
 raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
 import io
 wb=load_workbook(io.BytesIO(raw),data_only=True,read_only=True);wf=load_workbook(io.BytesIO(raw),data_only=False,read_only=True)
 try:
  if sheet not in wb.sheetnames:raise ValueError('Worksheet not found: '+sheet)
  ws=wb[sheet];formulas=wf[sheet];groups={};blank=0
  lo,hi=min(cols),max(cols)
  values_iter=ws.iter_rows(min_row=first_row,max_row=last_row,min_col=lo,max_col=hi,values_only=True)
  formula_iter=formulas.iter_rows(min_row=first_row,max_row=last_row,min_col=lo,max_col=hi,values_only=True)
  for row,(values,exprs) in enumerate(zip(values_iter,formula_iter),start=first_row):
   cells=[values[c-lo] for c in cols];formula=[exprs[c-lo] for c in cols]
   if any(v is None and isinstance(f,str) and f.startswith('=') for v,f in zip(cells,formula)):
    raise ValueError(f'Row {row} has formula(s) without cached values; recalculate in Excel.')
   if all(v is None for v in cells):
    blank+=1;continue
   if any(v is None for v in cells):raise ValueError(f'Incomplete data at worksheet row {row}; missing values are not treated as zero.')
   try:x=float(cells[0]);y=float(cells[1])
   except (TypeError,ValueError) as e:raise ValueError(f'Non-numeric X/Y at worksheet row {row}.') from e
   if not math.isfinite(x) or not math.isfinite(y) or x<0:raise ValueError(f'Invalid X/Y at worksheet row {row}.')
   name=str(cells[2]).strip() if group_column else 'dataset'
   if not name:raise ValueError(f'Blank dataset name at row {row}.')
   groups.setdefault(name,[]).append({'concentration':x,'response':y})
  if not groups:raise ValueError('No observations in selected rows.')
  if len(groups)>50:raise ValueError('More than 50 groups; narrow the selected rows.')
  return {'source_file':str(p),'source_sha256':digest,'sheet':sheet,'rows':[first_row,last_row],'columns':{'concentration':concentration_column,'response':response_column,'group':group_column},'blank_rows_skipped':blank,'exclusion_policy':'No exclusions or color rules applied. Specify only observations authorized for analysis.','datasets':[{'name':k,'points':v} for k,v in groups.items()]}
 finally:wb.close();wf.close()
