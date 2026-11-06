"""Odds math, line movement, bookmaker-vig diagnostics; no implied 'true' edge."""
from __future__ import annotations
from .common import finite_number, market_identity, utc


def break_even(american)->float|None:
    x=finite_number(american)
    if x is None or x==0 or abs(x)<100:return None
    return abs(x)/(abs(x)+100) if x<0 else 100/(x+100)


def fair_two_way(odds_a,odds_b)->dict:
    p=break_even(odds_a);q=break_even(odds_b)
    if p is None or q is None:return {'status':'INVALID'}
    total=p+q
    if total<=0:return {'status':'INVALID'}
    return {'status':'ILLUSTRATIVE_DEVIG','side_a_novig':round(p/total,6),
            'side_b_novig':round(q/total,6),'book_sum':round(total,6),
            'overround':round(total-1,6),
            'note':'Proportional vig-removal is a market benchmark, not independently calibrated truth.'}


def price_assessment(*, american_odds, model_probability, calibrated:bool,
                     quote_current:bool, market_verified:bool)->dict:
    implied=break_even(american_odds);p=finite_number(model_probability)
    if implied is None or p is None or not 0<=p<=1:return {'status':'INVALID'}
    if not calibrated or not quote_current or not market_verified:
        return {'status':'WITHHELD','break_even':round(implied,5),
                'reason':'An uncalibrated forecast or unverified quote cannot establish EV'}
    profit_per_unit=100/abs(float(american_odds)) if float(american_odds)<0 else float(american_odds)/100
    ev=p*profit_per_unit-(1-p)
    return {'status':'CALCULATED_CONDITIONAL','break_even':round(implied,5),
            'expected_profit_per_unit':round(ev,6),
            'note':'Conditional on probability calibration and market identity; does not guarantee positive realized returns.'}


def compare_quotes(first:dict,latest:dict,event:dict)->dict:
    a=market_identity(event,first);b=market_identity(event,latest)
    # Line changes intentionally alter market identity. Match underlying contract sans line
    basic=('bookmaker','market','player','selection','period','contract_id','rule_version')
    if any(first.get(k)!=latest.get(k) for k in basic):
        return {'status':'UNRELATED_MARKETS'}
    t1=utc(first.get('timestamp_utc'));t2=utc(latest.get('timestamp_utc'))
    if not t1 or not t2 or t2<=t1:return {'status':'BAD_TIMESTAMPS'}
    return {'status':'MOVED' if (a!=b or first.get('price')!=latest.get('price')) else 'UNCHANGED',
            'line_from':first.get('line'),'line_to':latest.get('line'),
            'price_from':first.get('price'),'price_to':latest.get('price'),
            'model_regrade_required':bool(a!=b),
            'note':'Line changes require fresh exact-threshold grading; movement alone does not establish informed money.'}
