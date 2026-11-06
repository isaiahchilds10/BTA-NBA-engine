"""Market rule / settlement verification, explicitly distinguishing reported from official.

A third-party data vendor's graded edge is not proof of the customer's
FanDuel/Polymarket account settlement. Unknown voids, pushes and amendments
are never converted into wins/losses.
"""
from __future__ import annotations
from .common import fingerprint,parse_time,number
from .provider import read_json

RESULTS={'WIN','LOSS','PUSH','VOID'}


def contract_id(*,event_id:str,bookmaker:str,market:str,selection:str,line=None,
                period='GAME',rule_version=''):
    if not event_id or not bookmaker or not market or not selection or not rule_version:
        return None
    if line is None and market not in ('moneyline','h2h'):return None
    return fingerprint({'event_id':event_id,'bookmaker':bookmaker.lower(),
                        'market':market,'selection':selection,'line':line,
                        'period':period,'rule_version':rule_version})


def verify_settlement(*,contract:dict,report:dict,source_tier:str):
    """SOURCE_TIERS: THIRD_PARTY, VERIFIED_MARKET_PROVIDER, AUTHENTICATED_BOOKMAKER.
    Source tiers must be established by the configured network adapter, not UI.
    """
    c=contract_id(event_id=contract.get('event_id',''),bookmaker=contract.get('bookmaker',''),
                  market=contract.get('market',''),selection=contract.get('selection',''),
                  line=contract.get('line'),period=contract.get('period','GAME'),
                  rule_version=contract.get('rule_version',''))
    if not c:return {'status':'INVALID_CONTRACT','verified':False}
    if report.get('contract_id')!=c or report.get('event_id')!=contract.get('event_id'):
        return {'status':'CONTRACT_MISMATCH','verified':False}
    started=parse_time(contract.get('start_utc'));settled=parse_time(report.get('settled_utc'))
    if not started or not settled or settled<=started:
        return {'status':'BAD_SETTLEMENT_TIME','verified':False}
    result=str(report.get('outcome') or '').upper()
    if result not in RESULTS:
        return {'status':'RESULT_UNRESOLVED','verified':False}
    if not report.get('rule_url','').startswith('https://'):
        return {'status':'RULES_UNVERIFIED','verified':False}
    if source_tier not in ('THIRD_PARTY','VERIFIED_MARKET_PROVIDER','AUTHENTICATED_BOOKMAKER'):
        return {'status':'UNKNOWN_PROVENANCE','verified':False}
    if source_tier!='AUTHENTICATED_BOOKMAKER':
        return {'status':'EXTERNAL_RESULT_ONLY','verified':False,'reported_outcome':result,
                'note':'Third-party grading is not bookmaker-authenticated settlement.'}
    if report.get('market_rule_version')!=contract.get('rule_version'):
        return {'status':'RULE_VERSION_MISMATCH','verified':False}
    return {'status':'BOOKMAKER_REPORTED_SETTLEMENT','verified':True,'outcome':result,
            'contract_id':c,'settled_utc':report['settled_utc'],
            'note':'Verification is contingent on the adapter authenticating the bookmaker feed and its documented settlement contract.'}


def fetch_report(*,url,token,allowed_hosts,event_id,fetcher=read_json):
    if not token or not url or not allowed_hosts:return {'status':'NOT_CONFIGURED'}
    try: obj=fetcher(url,token=token,allowed_hosts=allowed_hosts,params={'event_id':event_id})
    except (ValueError,OSError,TypeError,KeyError) as exc:
        return {'status':'SOURCE_ERROR','error_type':type(exc).__name__}
    if not isinstance(obj,dict) or obj.get('event_id')!=event_id:
        return {'status':'SOURCE_MISMATCH'}
    return {'status':'RETRIEVED','data':obj}
