"""Prospective graded selection audit and scan/selection-bias diagnostics."""
from __future__ import annotations
from collections import defaultdict
from math import log
from .common import utc,finite_number

VALID_GRADES=('TAIG','ELITE/CORE BTA+','STRONG BTA+','LOWER BTA+','BTA','CONDITIONAL','CUT')


def grade_report(records:list[dict],*,min_group:int=20)->dict:
    groups=defaultdict(list);excluded=0
    # Same exact settled market/event cannot count multiple times merely because
    # several forecasts or repeated API records exist. Ambiguous duplicates are
    # excluded entirely until a prospective locked-forecast policy is chosen.
    counts=defaultdict(int)
    for r in records:
        if r.get('market_id') and r.get('event_start_utc'):
            counts[(r['market_id'],r['event_start_utc'])]+=1
    for r in records:
        if counts[(r.get('market_id'),r.get('event_start_utc'))]>1:
            excluded+=1;continue
        p=finite_number(r.get('predicted_probability'))
        outcome=r.get('outcome')
        grade=r.get('grade');start=utc(r.get('event_start_utc'))
        at=utc(r.get('forecast_at_utc'))
        if grade not in VALID_GRADES or not start or not at or not at<start or type(outcome) is not int or outcome not in (0,1) or not r.get('verified_settlement') or not r.get('market_id'):
            excluded+=1;continue
        groups[(grade,str(r.get('league')),str(r.get('market_family')))].append((outcome,p))
    out=[]
    for (grade,sport,market),rows in sorted(groups.items()):
        n=len(rows);wins=sum(y for y,_ in rows)
        nums=[(y,p) for y,p in rows if p is not None and 0<p<1]
        brier=sum((p-y)**2 for y,p in nums)/len(nums) if nums else None
        ll=-sum(y*log(max(p,1e-12))+(1-y)*log(max(1-p,1e-12)) for y,p in nums)/len(nums) if nums else None
        out.append({'grade':grade,'sport':sport,'market':market,'n':n,'hits':wins,
                    'observed_success_rate':round(wins/n,5),
                    'brier':round(brier,5) if brier is not None else None,
                    'log_loss':round(ll,5) if ll is not None else None,
                    'status':'PRELIMINARY_SMALL_SAMPLE' if n<min_group else 'DESCRIPTIVE_ONLY'})
    return {'status':'PROSPECTIVE_AUDIT','groups':out,'excluded':excluded,
            'note':'Observed hit rates and scoring rules do not establish profitability or calibration without comparable holdout forecasts and prices.'}


def scan_audit(*, eligible_markets:int, scanned_markets:int,
               selection_ids:list[str], preregistered:bool=False)->dict:
    if scanned_markets<=0 or not 0<=eligible_markets<=scanned_markets:
        return {'status':'INVALID_COUNTS'}
    return {'status':'SELECTION_BIAS_REVIEW_REQUIRED' if not preregistered else 'SCAN_LOGGED',
            'scanned':scanned_markets,'eligible':eligible_markets,
            'selection_rate':round(eligible_markets/scanned_markets,6),
            'repeated_selection_ids':sorted({x for x in selection_ids if selection_ids.count(x)>1}),
            'note':'Deduplicate scans and lock model/threshold settings before chronological holdout; more candidate searches create a winner-selection bias.'}


def benjamini_hochberg(pvalues:list[float],q:float=.05)->dict:
    """Exploratory false-discovery control for genuine, valid test p-values.

    NOT a correction for improperly estimated betting probabilities or EV.
    """
    vals=[finite_number(p) for p in pvalues]
    if not 0<q<1 or any(p is None or not 0<=p<=1 for p in vals):
        return {'status':'INVALID_INPUT'}
    indexed=sorted(enumerate(vals),key=lambda x:x[1]);m=len(vals)
    k=0
    for rank,(_,p) in enumerate(indexed,start=1):
        if p<=q*rank/m:k=rank
    return {'status':'EXPLORATORY_ONLY','discoveries':[i for i,_ in indexed[:k]],
            'tests':m,'q':q,'note':'Requires properly designed hypothesis tests; does not certify bets.'}
