"""Offline synthetic fixtures only, never evidence of a profitable forecast."""
import os,sys,unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bta_v11.common import parse_time,asof_gate,fingerprint
from bta_v11.provider import read_json,cfbd_roster
from bta_v11.availability import evaluate as availability_gate,fetch_availability
from bta_v11.nfl_usage import historical_usage,fetch_snap_counts
from bta_v11.roster import continuity
from bta_v11.settlement import contract_id,verify_settlement
from bta_v11.validation import validate
from bta_v11.parlay import joint_historical,conditional_scenarios
from bta_v11.certification import assess,REQUIRED_GATES
from bta_v11.orchestrator import gather

T='2026-11-08T18:00:00+00:00'; NOW='2026-11-08T14:00:00+00:00'; RET='2026-11-08T13:50:00+00:00'; ASOF='2026-11-08T13:30:00+00:00'

def sample_response(status='ACTIVE',kind='CONFIRMED_LINEUP',unrestricted=True):
    return {'status':'FETCHED_PROVIDER_RESPONSE','event_id':'g1','source_url':'https://trusted.example/api',
            'asof_utc':ASOF,'retrieved_utc':RET,'records':[{'event_id':'g1','player_id':'p1','status':status,
                                                            'report_type':kind,'confirmed_starter':True,
                                                            'unrestricted_workload':unrestricted}]}

class TestCommon(unittest.TestCase):
    def test_tz(self):self.assertIsNone(parse_time('2026-11-08T12:00:00'))
    def test_fresh(self):self.assertTrue(asof_gate(asof=ASOF,retrieved=RET,event_start=T,max_age_hours=3,now=NOW)['ok'])
    def test_stale(self):self.assertFalse(asof_gate(asof='2026-11-07T00:00:00Z',retrieved=RET,event_start=T,max_age_hours=3,now=NOW)['ok'])
    def test_future_data(self):self.assertFalse(asof_gate(asof='2026-11-08T14:10:00Z',retrieved=RET,event_start=T,max_age_hours=3,now=NOW)['ok'])
    def test_postkickoff(self):self.assertFalse(asof_gate(asof=ASOF,retrieved=RET,event_start=T,max_age_hours=10,now='2026-11-08T18:01:00Z')['ok'])
    def test_fingerprint_stable(self):self.assertEqual(fingerprint({'a':1,'b':2}),fingerprint({'b':2,'a':1}))

class TestProvider(unittest.TestCase):
    def test_reject_http(self):
        with self.assertRaises(ValueError):read_json('http://api.example/x',allowed_hosts={'api.example'})
    def test_reject_unknown_host(self):
        with self.assertRaises(ValueError):read_json('https://bad.example/x',allowed_hosts={'api.example'})
    def test_reject_secret_query(self):
        with self.assertRaises(ValueError):read_json('https://api.example/x',allowed_hosts={'api.example'},params={'apiKey':'xxx'})
    def test_roster_missing_key(self):self.assertEqual(cfbd_roster(year=2026,team='Ohio State',api_key='')['status'],'CONFIGURATION_REQUIRED')
    def test_roster_parse(self):
        fn=lambda *args,**kw:[{'id':123,'name':'Player A','position':'QB'}]
        o=cfbd_roster(year=2026,team='Ohio State',api_key='fake',fetcher=fn)
        self.assertEqual(o['status'],'ROSTER_LIST_ONLY');self.assertEqual(o['players'][0]['player_id'],'123')
    def test_roster_error(self):
        def boom(*a,**k):raise OSError('unavailable')
        self.assertEqual(cfbd_roster(year=2026,team='Ohio State',api_key='fake',fetcher=boom)['status'],'PROVIDER_ERROR')
    def test_fetch_availability_missing_key(self):
        self.assertEqual(fetch_availability(url='https://api.example/v',token='',allowed_hosts={'api.example'},event_id='g1')['status'],'PROVIDER_NOT_CONFIGURED')
    def test_fetch_availability_event_mismatch(self):
        fn=lambda *args,**kw:{'event_id':'other','records':[]}
        self.assertEqual(fetch_availability(url='https://api.example/v',token='fake',allowed_hosts={'api.example'},event_id='g1',fetcher=fn)['status'],'IDENTITY_OR_SCHEMA_ERROR')

class TestAvailability(unittest.TestCase):
    def ev(self,response,**kw):return availability_gate(league='NFL',event_id='g1',player_id='p1',event_start_utc=T,response=response,now_utc=NOW,**kw)
    def test_active(self):self.assertTrue(self.ev(sample_response())['eligible'])
    def test_questionable(self):self.assertFalse(self.ev(sample_response('QUESTIONABLE'))['eligible'])
    def test_out(self):self.assertEqual(self.ev(sample_response('OUT'))['status'],'BLOCKED')
    def test_not_reported(self):self.assertFalse(self.ev(sample_response('NOT_REPORTED'))['eligible'])
    def test_roster_is_not_active(self):self.assertFalse(self.ev(sample_response(kind='SEASON_ROSTER'))['eligible'])
    def test_limited_workload(self):self.assertEqual(self.ev(sample_response(unrestricted=False))['status'],'ELIGIBLE_WORKLOAD_UNKNOWN')
    def test_game_mismatch(self):
        r=sample_response();r['event_id']='g2';self.assertFalse(self.ev(r)['eligible'])
    def test_duplicated_player(self):
        r=sample_response();r['records'].append(deepcopy(r['records'][0]));self.assertFalse(self.ev(r)['eligible'])
    def test_stale(self):
        r=sample_response();r['asof_utc']='2026-11-07T03:00:00Z';self.assertFalse(self.ev(r,max_age_hours=8)['eligible'])
    def test_starter(self):self.assertTrue(self.ev(sample_response(),needs_starter=True)['eligible'])
    def test_inactive_list_not_starter(self):self.assertFalse(self.ev(sample_response(kind='FINAL_INACTIVES_PLUS_ACTIVE_ROSTER'),needs_starter=True)['eligible'])

class TestNflUsage(unittest.TestCase):
    def snaps(self):return [{'season':2026,'week':w,'team':'NYJ','player_id':'p1','offense_pct':.5+w*.02,'offense_snaps':30+w} for w in range(1,5)]
    def routes(self):return [{'season':2026,'week':w,'team':'NYJ','player_id':'p1','method':'CHARTED_ROUTES','routes_run':12+w,'team_dropbacks':24} for w in range(1,5)]
    def test_snap_only_not_routes(self):
        o=historical_usage(player_id='p1',team='NYJ',season=2026,week=5,snap_rows=self.snaps())
        self.assertTrue(o['snaps_supported']);self.assertFalse(o['routes_supported'])
    def test_charts(self):
        o=historical_usage(player_id='p1',team='NYJ',season=2026,week=5,snap_rows=self.snaps(),route_rows=self.routes())
        self.assertTrue(o['routes_supported']);self.assertEqual(o['charted_route_games'],4)
    def test_proxy_excluded(self):
        rs=self.routes()
        for r in rs:r['method']='ON_FIELD_DROPBACK_PROXY'
        self.assertFalse(historical_usage(player_id='p1',team='NYJ',season=2026,week=5,snap_rows=self.snaps(),route_rows=rs)['routes_supported'])
    def test_current_week_excluded(self):
        rows=self.snaps();rows[0]['week']=5
        self.assertEqual(historical_usage(player_id='p1',team='NYJ',season=2026,week=5,snap_rows=rows)['snap_games'],3)
    def test_missing_player_id(self):
        rs=self.snaps()
        for r in rs:r.pop('player_id')
        self.assertFalse(historical_usage(player_id='p1',team='NYJ',season=2026,week=5,snap_rows=rs)['snaps_supported'])
    def test_fetch_snap_loader(self):
        o=fetch_snap_counts(2026,loader=lambda yr:(self.snaps(),{'url':'example'}))
        self.assertEqual(o['status'],'SOURCE_ROWS_NEED_PLAYER_ID_LINKAGE')

class TestRoster(unittest.TestCase):
    def test_continuity(self):
        pre={'status':'ROSTER_LIST_ONLY','team':'Ohio State','players':[{'player_id':str(i),'name':f'P{i}','position':'QB' if i==1 else 'OL'} for i in range(20)]}
        cur={'status':'ROSTER_LIST_ONLY','team':'Ohio State','players':[{'player_id':str(i),'name':f'P{i}','position':'QB' if i==1 else 'OL'} for i in range(10,30)]}
        o=continuity(pre,cur);self.assertEqual(o['returning_n'],10)
        self.assertEqual(o['status'],'DESCRIPTIVE_ROSTER_CONTINUITY')
    def test_empty_roster(self):self.assertEqual(continuity({}, {})['status'],'INSUFFICIENT_COMPARABLE_ROSTERS')

class TestSettlement(unittest.TestCase):
    def contract(self):return {'event_id':'g1','bookmaker':'fanduel','market':'player_points','selection':'OVER','line':20.5,'period':'GAME','rule_version':'v1','start_utc':T}
    def report(self):
        c=self.contract();return {'contract_id':contract_id(**{k:c[k] for k in ('event_id','bookmaker','market','selection','line','period','rule_version')}),
                  'event_id':'g1','settled_utc':'2026-11-08T22:00:00Z','outcome':'WIN','rule_url':'https://fanduel.com/rules','market_rule_version':'v1'}
    def test_thirdparty_not_bookmaker(self):self.assertFalse(verify_settlement(contract=self.contract(),report=self.report(),source_tier='THIRD_PARTY')['verified'])
    def test_provider_not_bookmaker(self):self.assertFalse(verify_settlement(contract=self.contract(),report=self.report(),source_tier='VERIFIED_MARKET_PROVIDER')['verified'])
    def test_authenticated_book(self):self.assertTrue(verify_settlement(contract=self.contract(),report=self.report(),source_tier='AUTHENTICATED_BOOKMAKER')['verified'])
    def test_rule_change(self):
        rep=self.report();rep['market_rule_version']='v2';self.assertFalse(verify_settlement(contract=self.contract(),report=rep,source_tier='AUTHENTICATED_BOOKMAKER')['verified'])
    def test_wrong_line(self):
        c=self.contract();c['line']=21.5;self.assertEqual(verify_settlement(contract=c,report=self.report(),source_tier='AUTHENTICATED_BOOKMAKER')['status'],'CONTRACT_MISMATCH')
    def test_void_is_not_a_win(self):
        rep=self.report();rep['outcome']='VOID';self.assertEqual(verify_settlement(contract=self.contract(),report=rep,source_tier='AUTHENTICATED_BOOKMAKER')['outcome'],'VOID')

class TestValidation(unittest.TestCase):
    def rows(self,n=400):
        first=datetime(2026,1,1,tzinfo=timezone.utc)
        rows=[]
        for i in range(n):
            kick=first+timedelta(days=i)
            p=.10 if i%2==0 else .90
            y=0 if i%2==0 else 1
            rows.append({'event_id':f'game{i}','market_id':f'mkt{i}','model_id':'v11a','market_family':'NBA_PROP',
                         'event_start_utc':kick.isoformat(),'forecast_utc':(kick-timedelta(hours=4)).isoformat(),
                         'features_asof_utc':(kick-timedelta(hours=5)).isoformat(),
                         'settled_utc':(kick+timedelta(hours=6)).isoformat(),
                         'outcome':y,'probability':p,'authenticated_settlement':True})
        return rows
    def test_good_out_of_time_diagnostic(self):
        o=validate(self.rows(),model_id='v11a',market_family='NBA_PROP',evaluation_now='2028-01-01T00:00:00Z')
        self.assertEqual(o['status'],'OUT_OF_TIME_DIAGNOSTICS_PASS')
        self.assertGreaterEqual(o['test'],100)
    def test_postgame_leak_rejected(self):
        rows=self.rows();rows[0]['features_asof_utc']=rows[0]['settled_utc']
        o=validate(rows,model_id='v11a',market_family='NBA_PROP',evaluation_now='2028-01-01T00:00:00Z')
        self.assertEqual(o['rejected'],1)
    def test_duplicate_market_rejected_entirely(self):
        rows=self.rows();rows.append(deepcopy(rows[0]));o=validate(rows,model_id='v11a',market_family='NBA_PROP',evaluation_now='2028-01-01T00:00:00Z')
        self.assertEqual(o['rejected'],2)
    def test_small_holdout(self):self.assertEqual(validate(self.rows(40),model_id='v11a',market_family='NBA_PROP',evaluation_now='2028-01-01T00:00:00Z')['status'],'INSUFFICIENT_PROSPECTIVE_DATA')
    def test_wrong_model(self):self.assertEqual(validate(self.rows(),model_id='other',market_family='NBA_PROP',evaluation_now='2028-01-01T00:00:00Z')['status'],'INSUFFICIENT_PROSPECTIVE_DATA')
    def test_no_auth_settlements(self):
        rows=self.rows()
        for r in rows:r['authenticated_settlement']=False
        self.assertEqual(validate(rows,model_id='v11a',market_family='NBA_PROP',evaluation_now='2028-01-01T00:00:00Z')['accepted'],0)

class TestParlay(unittest.TestCase):
    def test_paired_history(self):
        a=[{'independent_slate_id':f's{i}','source_verified':True,'pregame_archived':True,'forecast_utc':'2026-01-01T00:00:00Z','earliest_event_start_utc':'2026-01-02T00:00:00Z','settled_at_utc':'2026-01-03T00:00:00Z','outcomes':{'a':i%2,'b':1}} for i in range(160)]
        r=joint_historical(a,['a','b'])
        self.assertEqual(r['n'],160);self.assertAlmostEqual(r['rate'],.5)
    def test_no_pairings(self):self.assertEqual(joint_historical([],['a','b'])['status'],'INSUFFICIENT_COMPARABLE_JOINT_HISTORY')
    def test_duplicate_slate_rejected(self):
        a=[{'independent_slate_id':'s1','source_verified':True,'pregame_archived':True,'forecast_utc':'2026-01-01T00:00:00Z','earliest_event_start_utc':'2026-01-02T00:00:00Z','settled_at_utc':'2026-01-03T00:00:00Z','outcomes':{'a':1,'b':1}}]*200
        self.assertEqual(joint_historical(a,['a','b'])['n'],0)
    def test_scenarios_unvalidated_no_future_probability(self):
        s=[{'distinct_scenario':'A','weight':.6,'empirical_joint_p':.4,'leg_ids':['a','b'],'data_asof_utc':ASOF,'event_start_utc':T,'joint_model_id':'joint-v2','validated_joint_source':True,'training_pair_count':150},
           {'distinct_scenario':'B','weight':.4,'empirical_joint_p':.1,'leg_ids':['a','b'],'data_asof_utc':ASOF,'event_start_utc':T,'joint_model_id':'joint-v2','validated_joint_source':True,'training_pair_count':150}]
        x=conditional_scenarios(s,['a','b'])
        self.assertIsNone(x['probability_estimate']);self.assertAlmostEqual(x['hypothetical_estimate'],.28)
        y=conditional_scenarios(s,['a','b'],model_validation={'status':'OUT_OF_TIME_DIAGNOSTICS_PASS','market_family':'JOINT_PARLAY','model_id':'joint-v2','test':120,'test_event_count':100})
        self.assertAlmostEqual(y['probability_estimate'],.28)
    def test_wrong_joint_model(self):
        s=[{'distinct_scenario':'A','weight':1,'empirical_joint_p':.4,'leg_ids':['a','b'],'data_asof_utc':ASOF,'event_start_utc':T,'joint_model_id':'v3','validated_joint_source':True,'training_pair_count':150}]
        self.assertIsNone(conditional_scenarios(s,['a','b'],model_validation={'status':'OUT_OF_TIME_DIAGNOSTICS_PASS','market_family':'JOINT_PARLAY','model_id':'v2','test':120,'test_event_count':100})['probability_estimate'])

class TestCertification(unittest.TestCase):
    def params(self):
        return {'family':'NBA_PROP','evidence':{k:True for k in REQUIRED_GATES},
                'scripts':[{'scenario':scenario,'verdict':'SAME','mechanism':'Stable minutes and role expected','evidence_urls':['https://nba.com/games']} for scenario in ['PLAYER_TEAM_BLOWOUT','OPPONENT_BLOWOUT','CLOSE','LOW_PACE','HIGH_PACE']],
                'proposed_grade':'BTA+','ordinary_failure_severity':'LOW',
                'model_diagnostics':{'status':'OUT_OF_TIME_DIAGNOSTICS_PASS','model_id':'v11-prop','market_family':'NBA_PROP'},'forecast_model_id':'v11-prop',
                'availability':{'eligible':True},'market_identity':'exact-ID'}
    def test_complete_research_qualifies(self):
        self.assertEqual(assess(**self.params())['status'],'RULE_QUALIFIED_RESEARCH')
    def test_bad_news_veto(self):
        p=self.params();p['evidence']['no_material_new_information']=False
        self.assertFalse(assess(**p)['qualified'])
    def test_two_worse_cuts(self):
        p=self.params();p['scripts'][0]['verdict']='WORSE';p['scripts'][1]['verdict']='WORSE'
        self.assertEqual(assess(**p)['grade'],'CUT')
    def test_one_worse_review(self):
        p=self.params();p['scripts'][0]['verdict']='WORSE'
        self.assertFalse(assess(**p)['qualified'])
    def test_one_worse_bta_allowed(self):
        p=self.params();p['scripts'][0]['verdict']='WORSE';p['proposed_grade']='BTA'
        self.assertTrue(assess(**p)['qualified'])
    def test_taig_extra_review(self):
        p=self.params();p['proposed_grade']='TAIG'
        self.assertEqual(assess(**p)['status'],'EXCEPTIONAL_AUDIT_REQUIRED')
    def test_nfl_requires_charted_routes(self):
        p=self.params();p['family']='NFL_PROP';p['model_diagnostics']['market_family']='NFL_PROP'
        for script,scenario in zip(p['scripts'],['FAVORITE_BLOWOUT','UNDERDOG_BLOWOUT','CLOSE','LOW_SCORING','SHOOTOUT']):script['scenario']=scenario
        self.assertFalse(assess(**p)['qualified'])
        p['nfl_route_evidence']={'routes_supported':True}
        self.assertTrue(assess(**p)['qualified'])
    def test_college_moneyline_not_two_worse(self):
        p=self.params();p['family']='CFB_MONEYLINE';p['model_diagnostics']['market_family']='CFB_MONEYLINE'
        for script,scenario in zip(p['scripts'],['NORMAL_EXPECTED','UNDERDOG_FAST_START','NEGATIVE_TWO_TURNOVERS','PRIMARY_STRENGTH_NEUTRALIZED','ONE_SCORE_Q4']):
            script['scenario']=scenario;script['verdict']='VULNERABLE'
        self.assertEqual(assess(**p)['status'],'PENDING_VERIFICATION')
        self.assertNotEqual(assess(**p)['status'],'CUT_TWO_WORSE_SCRIPTS')
    def test_holdout_required(self):
        p=self.params();p['model_diagnostics']={}
        self.assertFalse(assess(**p)['qualified'])

class TestOrchestrator(unittest.TestCase):
    def test_no_secrets_fails_closed(self):
        with patch.dict(os.environ,{'CFBD_API_KEY':'','BTA_AVAILABILITY_TOKEN':'','BTA_AVAILABILITY_URL':''}):
            o=gather(league='College football',event={'event_id':'g1','start_utc':T,'season_year':2026},team='Ohio State',now=NOW)
        self.assertIn('CFBD_API_KEY missing: current roster cannot be fetched',o['blockers'])
        self.assertFalse(o['certified'])
    def test_fetch_auth_response_unavailable(self):
        o=gather(league='NBA',event={'event_id':'g1','start_utc':T},player_id='p1',now=NOW,
                 availability_fetcher=lambda e:{'status':'PROVIDER_NOT_CONFIGURED','records':[]})
        self.assertFalse(o['certified'])

if __name__=='__main__':unittest.main()

class TestIdsAndRoutes(unittest.TestCase):
    def test_pfr_to_gsis_join(self):
        from bta_v11.nfl_usage import link_pfr_snap_ids
        player=[{'pfr_id':'X1','gsis_id':'0001'}]
        snap=[{'season':'2026','week':'7','pfr_player_id':'X1','team':'NYJ','offense_snaps':'40','offense_pct':'0.65'}]
        found=link_pfr_snap_ids(snap,player)
        self.assertEqual(found['rows'][0]['player_id'],'0001')
        self.assertEqual(found['unmatched'],0)
    def test_ambiguous_link_rejected(self):
        from bta_v11.nfl_usage import link_pfr_snap_ids
        player=[{'pfr_id':'X1','gsis_id':'0001'},{'pfr_id':'X1','gsis_id':'0002'}]
        snap=[{'pfr_player_id':'X1'}]
        o=link_pfr_snap_ids(snap,player)
        self.assertEqual(o['mapped'],0);self.assertEqual(o['ambiguous_player_ids'],1)
    def test_no_invented_routes(self):
        from bta_v11.nfl_usage import fetch_charted_routes
        self.assertEqual(fetch_charted_routes(season=2026,token='',url='',allowed_hosts=set())['status'],'ROUTE_PROVIDER_NOT_CONFIGURED')
    def test_fetch_charted_routes(self):
        from bta_v11.nfl_usage import fetch_charted_routes
        f=lambda *a,**kw:{'season':2026,'observations':[
             {'season':2026,'week':5,'team':'NYJ','player_id':'gsis','method':'CHARTED_ROUTES','routes_run':20,'team_dropbacks':25},
             {'season':2026,'week':5,'team':'NYJ','player_id':'other','method':'ON_FIELD_DROPBACK_PROXY','routes_run':30,'team_dropbacks':30}]}
        x=fetch_charted_routes(season=2026,token='fake',url='https://licensed.example/routes',allowed_hosts={'licensed.example'},fetcher=f)
        self.assertEqual(len(x['rows']),1)
    def test_future_settlement_blocked(self):
        rows=TestValidation().rows()
        x=validate(rows,model_id='v11a',market_family='NBA_PROP',evaluation_now='2025-12-31T00:00:00Z')
        self.assertEqual(x['accepted'],0)
    def test_lookahead_settlement_to_holdout(self):
        rows=TestValidation().rows()
        # All training outcomes are magically delayed until after the test period.
        for r in rows[:280]:r['settled_utc']='2027-06-01T00:00:00Z'
        x=validate(rows,model_id='v11a',market_family='NBA_PROP',evaluation_now='2028-01-01T00:00:00Z')
        self.assertNotEqual(x['status'],'OUT_OF_TIME_DIAGNOSTICS_PASS')

class TestProviderCrosswalk(unittest.TestCase):
    def example(self):return {'event_key':'espn:CFB:1','league':'College football',
             'home':{'name':'Oregon Ducks'},'away':{'name':'Ohio State Buckeyes'},'start_utc':T}
    def candidate(self):return {'event_id':'vendor-abc','league':'College football','home':'Oregon Ducks',
                                'away':'Ohio State Buckeyes','start_utc':'2026-11-08T18:02:00Z'}
    def test_exact_match(self):
        from bta_v11.event_crosswalk import resolve
        self.assertEqual(resolve(self.example(),[self.candidate()])['status'],'EXACT_CROSSWALK')
    def test_no_name_guessing(self):
        from bta_v11.event_crosswalk import resolve
        c=self.candidate();c['away']='Ohio State'
        self.assertEqual(resolve(self.example(),[c])['status'],'NO_EXACT_MATCH')
    def test_wrong_start_rejected(self):
        from bta_v11.event_crosswalk import resolve
        c=self.candidate();c['start_utc']='2026-11-08T20:00:00Z'
        self.assertEqual(resolve(self.example(),[c])['status'],'NO_EXACT_MATCH')
    def test_multiple_matches_block(self):
        from bta_v11.event_crosswalk import resolve
        c=self.candidate();d={**c,'event_id':'other'}
        self.assertEqual(resolve(self.example(),[c,d])['status'],'AMBIGUOUS_PROVIDER_EVENT')
