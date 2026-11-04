"""Independent 4PL dose-response analysis, not a native Prism analysis."""
from pathlib import Path
import csv, json, math

def fit_dose_response(points, output_dir, response_kind, effect_percent=20.0, unit='', name='dose_response', error_bars='sd'):
    import numpy as np
    from scipy.optimize import least_squares
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    if response_kind not in ('decreasing', 'increasing'):
        raise ValueError('response_kind must be decreasing or increasing; define effect relative to fitted plateaus.')
    if error_bars not in ('sd','sem','none'):
        raise ValueError('error_bars must be sd, sem, or none.')
    if not 0 < effect_percent < 100:
        raise ValueError('effect_percent must be between 0 and 100, exclusive.')
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name):
        raise ValueError('name must contain only ASCII letters, digits, underscore or hyphen.')
    if len(points) < 5:
        raise ValueError('At least five observations and four distinct positive concentrations are required.')
    try:
        x = np.array([float(p['concentration']) for p in points]); y = np.array([float(p['response']) for p in points])
    except (ValueError, TypeError, KeyError) as e:
        raise ValueError('Each point must contain finite numeric concentration and response.') from e
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or np.any(x < 0):
        raise ValueError('Concentrations must be finite and nonnegative, responses finite; missing data must be omitted explicitly.')
    positive=x[x>0]; unique=np.unique(positive)
    if len(unique)<4 or len(np.unique(y))<4:
        raise ValueError('Need at least four distinct positive concentrations and four distinct responses.')
    span=float(np.ptp(y)); xmin=float(unique.min()); xmax=float(unique.max())
    if span<=0: raise ValueError('Responses have no variation.')
    # Log midpoint and positive Hill coefficient enforce monotonicity and positive EC50.
    def predict(p, xx):
        bottom, delta, logmid, loghill = p
        z=np.zeros_like(xx, dtype=float); mask=xx>0
        from scipy.special import expit
        z[mask]=expit(np.exp(loghill)*(np.log(xx[mask])-logmid))
        return bottom+delta*(1-z if response_kind=='decreasing' else z)
    lo=[float(y.min()-10*span), 1e-12, math.log(xmin)-20, math.log(.02)]
    hi=[float(y.max()+10*span), 20*span, math.log(xmax)+20, math.log(20)]
    p0=[float(y.min()),span,math.log(math.sqrt(xmin*xmax)),0.0]
    result=least_squares(lambda p:predict(p,x)-y,p0,bounds=(lo,hi),max_nfev=20000)
    if not result.success: raise ValueError('4PL optimization failed: '+result.message)
    bottom,delta,lmid,lhill=result.x; mid=math.exp(lmid); hill=math.exp(lhill)
    fraction=effect_percent/100; target=mid*(fraction/(1-fraction))**(1/hill)
    if not math.isfinite(target): raise ValueError('Effect concentration is not finite; data do not support this fit.')
    rss=float(np.sum(result.fun**2)); dof=len(x)-4
    warnings=[]
    if target<xmin or target>xmax: warnings.append('Effect concentration is outside measured positive concentrations; it is extrapolated.')
    if mid<xmin or mid>xmax: warnings.append('Midpoint is outside measured positive concentrations; plateaus may be poorly constrained.')
    if np.linalg.matrix_rank(result.jac)<4: warnings.append('Fit is rank-deficient; parameters are not identifiable.')
    if np.any(result.active_mask): warnings.append('At least one parameter reached an optimization bound.')
    if dof<=0: warnings.append('No residual degrees of freedom.')
    summary=[]
    for dose in np.unique(x):
        values=y[x==dose]; n=int(len(values)); mean=float(np.mean(values))
        sd=float(np.std(values,ddof=1)) if n>1 else None
        sem=sd/math.sqrt(n) if sd is not None else None
        summary.append({'concentration':float(dose),'n':n,'mean':mean,'sd':sd,'sem':sem})
    if error_bars!='none' and any(s['n']==1 for s in summary):
        warnings.append('Concentrations with n=1 have no estimable SD or SEM; their means are shown without error bars.')
    out=Path(output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    files={k:out/(name+'.'+k) for k in ('json','csv','png','svg')}
    files['summary_csv']=out/(name+'_summary.csv')
    if any(p.exists() for p in files.values()): raise FileExistsError('Output exists; choose a new name to avoid overwriting.')
    curve=np.geomspace(xmin,xmax,300); pred=predict(result.x,curve)
    with files['csv'].open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['concentration','fitted_response']); w.writerows(zip(curve,pred))
    with files['summary_csv'].open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['concentration','n','mean','sd','sem']); w.writeheader(); w.writerows(summary)
    fig,ax=plt.subplots(figsize=(6.4,4.6)); positive_summary=[s for s in summary if s['concentration']>0]
    ax.plot(curve,pred,label='4PL fit',color='#2468a0',zorder=1)
    with_error=[s for s in positive_summary if error_bars!='none' and s[error_bars] is not None]
    without_error=[s for s in positive_summary if error_bars=='none' or s[error_bars] is None]
    if with_error:
        ax.errorbar([s['concentration'] for s in with_error],[s['mean'] for s in with_error],yerr=[s[error_bars] for s in with_error],fmt='o',markersize=4,markerfacecolor='white',markeredgecolor='#1b4d6c',ecolor='#1b4d6c',elinewidth=1.2,capsize=3,capthick=1.2,zorder=3,label='Mean ± '+error_bars.upper())
    if without_error:
        ax.scatter([s['concentration'] for s in without_error],[s['mean'] for s in without_error],s=24,facecolors='white',edgecolors='#1b4d6c',zorder=3,label='Mean' if error_bars=='none' else 'Mean (n=1)')
    if xmin<=target<=xmax:
        yt=bottom+delta*((1-fraction) if response_kind=='decreasing' else fraction)
        ax.scatter([target],[yt],marker='x',s=60,label=f'{effect_percent:g}% effect = {target:.4g}')
    ax.set_xscale('log'); ax.set_xlabel('Concentration'+(' ('+unit+')' if unit else '')); ax.set_ylabel('Response'); ax.legend(); fig.tight_layout()
    fig.savefig(files['png'],dpi=200); fig.savefig(files['svg']); plt.close(fig)
    if np.any(x==0): warnings.append('Zero concentration observations were fitted but cannot be displayed on the logarithmic x axis.')
    result_data={'engine':'SciPy least_squares; independent of Prism','model':'4PL, unweighted individual observations','direction':response_kind,'error_bars':error_bars,'error_bar_definition':'sample SD (n-1) or SEM=sample SD/sqrt(n); unavailable for n<2','concentration_summary':summary,'effect_definition':'fraction of fitted plateau-to-plateau response change from zero-dose baseline','effect_percent':effect_percent,'effect_concentration':target,'unit':unit,'bottom':float(bottom),'top':float(bottom+delta),'midpoint':mid,'hill_slope_magnitude':hill,'n':len(x),'observations':[{'concentration':float(a),'response':float(b)} for a,b in zip(x,y)],'distinct_positive_concentrations':len(unique),'range_positive':[xmin,xmax],'rss':rss,'residual_degrees_of_freedom':dof,'confidence_intervals':None,'warnings':warnings,'files':{k:str(v) for k,v in files.items()}}
    files['json'].write_text(json.dumps(result_data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    return result_data
