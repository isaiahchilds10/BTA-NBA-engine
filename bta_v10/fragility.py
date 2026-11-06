"""One-factor and simultaneous adverse perturbation checks on supplied model.
No model is invented. The callback must be a real validated model before use.
"""
from __future__ import annotations
from .common import finite_number


def sensitivity(predict, base:dict[str,float], shifts:dict[str,list[float]])->dict:
    if predict is None:return {'status':'MODEL_NOT_AVAILABLE'}
    original=finite_number(predict(dict(base)))
    if original is None or not 0<=original<=1:return {'status':'INVALID_MODEL_OUTPUT'}
    checks=[]
    for factor,deltas in shifts.items():
        if factor not in base:continue
        for delta in deltas:
            change=finite_number(delta)
            if change is None:continue
            state=dict(base);state[factor]=base[factor]*(1+change)
            candidate=finite_number(predict(state))
            if candidate is None or not 0<=candidate<=1:
                checks.append({'factor':factor,'change_fraction':change,'status':'INVALID_SCENARIO'})
            else:
                checks.append({'factor':factor,'change_fraction':change,'probability':round(candidate,6),
                               'delta_probability':round(candidate-original,6)})
    worst=min((x['probability'] for x in checks if 'probability' in x),default=original)
    return {'status':'SCENARIO_SENSITIVITY_ONLY','baseline_probability':round(original,6),
            'worst_one_factor_probability':round(worst,6),'absolute_max_loss':round(original-worst,6),
            'scenarios':checks,'note':'Assumed perturbations, not estimated scenario frequencies; robustness depends on model validity.'}
