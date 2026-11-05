"""Read-only XY graph diagnostics; never changes measurements or fits."""
import math

def preflight(points, x_scale='log'):
    if x_scale not in ('log','linear'): raise ValueError('x_scale must be log or linear.')
    if not points: raise ValueError('At least one observation is required.')
    zero=[]; negative=[]; positive=[]
    for idx,p in enumerate(points):
        try: x=float(p['concentration']);y=float(p['response'])
        except (KeyError,TypeError,ValueError): raise ValueError(f'Observation {idx+1} must contain numeric concentration and response.') from None
        if not math.isfinite(x) or not math.isfinite(y):raise ValueError(f'Observation {idx+1} must be finite.')
        (zero if x==0 else negative if x<0 else positive).append(x)
    if negative:raise ValueError('Negative concentrations are unsupported; inspect input before fitting.')
    graph_omits_zero=x_scale=='log' and bool(zero)
    return {'x_scale':x_scale,'observations':len(points),'zero_concentration_rows':int(bool(zero)),
            'zero_concentration_observations':len(zero),'positive_concentration_rows':len(set(positive)),
            'zero_eligible_for_axis':not graph_omits_zero if zero else None,
            'zero_retained_in_input':True,'data_changed':False,'fit_run':False,
            'prism_warning_likely':graph_omits_zero,
            'explanation':('Zero cannot be shown on a logarithmic X axis; Prism may report one X value cannot be plotted. Raw zero-control repeats can still be fitted by a concentration-based model. Do not replace or exclude them without a documented choice.' if graph_omits_zero else 'No zero-concentration log-axis conflict detected.'),
            'source':'https://www.graphpad.com/support/faqid/2056/'}
