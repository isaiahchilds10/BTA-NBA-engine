"""Offline fixtures intentionally synthetic; not betting accuracy tests."""
import unittest
from datetime import datetime,timezone
from bta_v10.common import utc,finite_number,market_identity,before_event
from bta_v10.reconcile import reconcile,evidence_gate
from bta_v10.regrade import compare,freshness_veto
from bta_v10.opportunity import nba_rotation,nfl_role,college_continuity,opponent_adjusted
from bta_v10.market import break_even,fair_two_way,price_assessment,compare_quotes
from bta_v10.fragility import sensitivity
from bta_v10.redteam import challenge,REQUIRED
from bta_v10.portfolio import shared_risk,joint_bounds,paired_history
from bta_v10.performance import grade_report,scan_audit,benjamini_hochberg
from bta_v10.settlement import reconcile_settlement,diagnose_miss
from bta_v10.engine import evaluate,evaluate_slip
from bta_v10.pipeline import audit_auto_snapshot,changes_between
from bta_v10.refresh_job import run
from bta_v10.adapters import nba_team_observations,nfl_team_observations

NOW=datetime(2026,11,5,20,0,tzinfo=timezone.utc)
ISO='2026-11-05T20:00:00+00:00'
EV={'event_key':'espn:NFL:1','start_utc':'2026-11-06T20:00:00+00:00','status':'UPCOMING'}
OFFER={'bookmaker':'fanduel','market':'player_receiving_yards','player':'Sample Player',
       'selection':'OVER','line':20.5,'price':-110}

def fact(value,origin='nba.com',at='2026-11-05T19:00:00+00:00'):
 return {'event_key':'g','entity_id':'p','field':'injury_designation','value':value,
         'source_url':'https://'+origin+'/src','origin_id':origin,'source_class':'official',
         'source_asof_utc':at,'retrieved_at_utc':ISO}

class CoreTests(unittest.TestCase):
 def test_utc_z(self):self.assertEqual(utc('2026-11-05T20:00:00Z'),NOW)
 def test_utc_naive_rejected(self):self.assertIsNone(utc('2026-11-05T20:00:00'))
 def test_finite_bool_rejected(self):self.assertIsNone(finite_number(True))
 def test_finite_nan_rejected(self):self.assertIsNone(finite_number(float('nan')))
 def test_exact_market_changes_line(self):
  a=market_identity(EV,OFFER);self.assertNotEqual(a,market_identity(EV,{**OFFER,'line':30.5}))
 def test_no_market_without_line(self):self.assertIsNone(market_identity(EV,{**OFFER,'line':None}))
 def test_before_start(self):self.assertTrue(before_event(event_start=EV['start_utc'],created_at=ISO,data_asof='2026-11-05T19:00:00Z'))
 def test_lookahead_rejected(self):self.assertFalse(before_event(event_start=EV['start_utc'],created_at='2026-11-07T00:00:00Z',data_asof=ISO))
 def test_reconcile_missing(self):self.assertEqual(reconcile([],now=NOW)['status'],'MISSING')
 def test_single_source_not_corroborated(self):
  r=reconcile([fact('QUESTIONABLE')],now=NOW);self.assertEqual(r['status'],'CURRENT_SINGLE_SOURCE');self.assertFalse(r['verified'])
 def test_two_corroborated(self):self.assertTrue(reconcile([fact('OUT'),fact('OUT','espn.com')],now=NOW)['verified'])
 def test_same_origin_mirrors_not_independent(self):
  self.assertFalse(reconcile([fact('OUT'),fact('OUT')],now=NOW)['verified'])
 def test_conflicting_reports_not_averaged(self):
  self.assertEqual(reconcile([fact('OUT'),fact('ACTIVE','espn.com')],now=NOW)['status'],'CONFLICT')
 def test_untrusted_stale_evidence_rejected(self):
  self.assertEqual(reconcile([fact('OUT',at='2026-10-01T19:00:00Z')],now=NOW)['status'],'STALE_OR_INVALID')
 def test_reject_ambiguous_entities(self):
  f=fact('OUT');self.assertEqual(reconcile([f,{**f,'entity_id':'other'}],now=NOW)['status'],'IDENTITY_CONFLICT')
 def test_evidence_gate_conflict(self):
  r=evidence_gate({'inj':[fact('OUT'),fact('ACTIVE','espn.com')]},['inj'],now=NOW);self.assertIn('inj',r['conflicts'])
 def test_change_injury_invalidates(self):
  r=compare({'injury_status':'QUESTIONABLE'},{'injury_status':'OUT'},observed_at=ISO);self.assertTrue(r['veto_existing_grade'])
 def test_change_odds_regrade(self):self.assertTrue(compare({'sportsbook_line':21.5},{'sportsbook_line':25.5},observed_at=ISO)['requires_regrade'])
 def test_unchanged(self):self.assertFalse(compare({'injury_status':'OUT'},{'injury_status':'OUT'},observed_at=ISO)['requires_regrade'])
 def test_missing_timestamp_veto(self):self.assertTrue(freshness_veto(evidence_asof=None,now=ISO,maximum_minutes=15)['veto'])
 def test_stale_veto(self):self.assertTrue(freshness_veto(evidence_asof='2026-11-05T19:00:00Z',now=ISO,maximum_minutes=15)['veto'])
 def test_nba_minutes_no_future(self):
  rows=[{'played_at_utc':f'2026-10-{i:02d}T01:00:00Z','minutes':30+i/10,'points':20+i/10} for i in range(1,11)]
  rows.append({'played_at_utc':'2026-11-07T01:00:00Z','minutes':1,'points':9999})
  result=nba_rotation(rows,event_start_utc=EV['start_utc']);self.assertEqual(result['status'],'RESEARCH_ONLY');self.assertLess(result['illustrative_points_projection'],30)
 def test_nba_insufficient(self):self.assertEqual(nba_rotation([],event_start_utc=EV['start_utc'])['status'],'INSUFFICIENT')
 def test_nfl_role_trend(self):
  rows=[{'played_at_utc':f'2026-10-{i:02d}T00:00:00Z','routes':20+i,'targets':4,'snaps':50} for i in range(1,11)]
  self.assertEqual(nfl_role(rows,event_start_utc=EV['start_utc'],role='receiver')['status'],'RESEARCH_ONLY')
 def test_nfl_role_no_route_info(self):
  self.assertEqual(nfl_role([{'played_at_utc':ISO,'targets':4}],event_start_utc=EV['start_utc'],role='receiver')['status'],'INSUFFICIENT')
 def test_college_continuity_missing(self):self.assertEqual(college_continuity({}, {})['status'],'PENDING')
 def test_college_continuity_qb_change(self):
  a={'starting_qb_id':'a','head_coach_id':'h','returning_offensive_starters':6,'returning_defensive_starters':7};b={**a,'starting_qb_id':'b'}
  self.assertTrue(college_continuity(a,b)['qb_changed'])
 def test_opponent_adjusted_not_validated(self):self.assertEqual(opponent_adjusted(20,10,baseline_strength=8,sample_size=5)['status'],'EXPERIMENTAL')
 def test_break_even(self):self.assertAlmostEqual(break_even(-110),110/210)
 def test_invalid_odds(self):self.assertIsNone(break_even(99))
 def test_two_way_devig(self):self.assertAlmostEqual(fair_two_way(-110,-110)['side_a_novig'],.5)
 def test_market_ev_withheld(self):self.assertEqual(price_assessment(american_odds=-110,model_probability=.7,calibrated=False,quote_current=True,market_verified=True)['status'],'WITHHELD')
 def test_market_ev_conditional(self):self.assertEqual(price_assessment(american_odds=-110,model_probability=.7,calibrated=True,quote_current=True,market_verified=True)['status'],'CALCULATED_CONDITIONAL')
 def test_changed_line_needs_regrade(self):
  a={**OFFER,'timestamp_utc':'2026-11-05T16:00:00Z'};b={**OFFER,'line':25.5,'timestamp_utc':ISO};self.assertTrue(compare_quotes(a,b,EV)['model_regrade_required'])
 def test_sensitivity_no_model(self):self.assertEqual(sensitivity(None,{'minutes':30},{'minutes':[-.1]})['status'],'MODEL_NOT_AVAILABLE')
 def test_sensitivity_with_model(self):
  f=lambda x:min(1,max(0,x['minutes']/40));res=sensitivity(f,{'minutes':30},{'minutes':[-.1,.1]});self.assertAlmostEqual(res['worst_one_factor_probability'],.675)
 def test_redteam_two_worse_cut(self):
  scripts=[{'scenario':str(i),'verdict':v,'mechanism':'usage','evidence_urls':['https://nba.com']} for i,v in enumerate(('WORSE','WORSE','SAME','MIXED','BETTER'))]
  self.assertEqual(challenge(evidence={x:True for x in REQUIRED},scripts=scripts)['status'],'CUT')
 def test_redteam_unknown_scripts_pending(self):self.assertEqual(challenge(evidence={x:True for x in REQUIRED},scripts=[])['status'],'PENDING')
 def test_redteam_never_certifies(self):
  scripts=[{'scenario':str(i),'verdict':v,'mechanism':'something','evidence_urls':['https://x.example']} for i,v in enumerate(('BETTER','BETTER','MIXED','SAME','SAME'))]
  r=challenge(evidence={x:True for x in REQUIRED},scripts=scripts);self.assertFalse(r['eligible']);self.assertEqual(r['status'],'RED_TEAM_REVIEW_ONLY')
 def test_cfb_does_not_use_prop_two_worse_rule(self):
  scripts=[{'scenario':str(i),'verdict':v,'mechanism':'efficiency','evidence_urls':['https://sports.example']} for i,v in enumerate(('VULNERABLE','VULNERABLE','RESILIENT','RESILIENT','MIXED'))]
  result=challenge(evidence={x:True for x in REQUIRED},scripts=scripts,family='CFB_MONEYLINE')
  self.assertNotEqual(result['status'],'CUT')
 def test_duplicate_scenarios_not_valid(self):
  scripts=[{'scenario':'same','verdict':'SAME','mechanism':'usage','evidence_urls':['https://sports.example']}] *5
  self.assertEqual(challenge(evidence={x:True for x in REQUIRED},scripts=scripts)['status'],'PENDING')
 def test_parlay_overlap_same_game(self):
  self.assertIn('same_game',shared_risk([{'event_key':'g'},{'event_key':'g'}])['pairs'][0]['reasons'])
 def test_parlay_bounds_not_prediction(self):self.assertEqual(joint_bounds([.8,.7,.9])['status'],'INPUT_NOT_CALIBRATED')
 def test_parlay_bounds_math(self):
  b=joint_bounds([.8,.7,.9],calibrated=True);self.assertAlmostEqual(b['lower'],.4);self.assertAlmostEqual(b['upper'],.7)
 def test_no_fake_joint_when_few(self):self.assertEqual(paired_history([],['a','b'])['status'],'INSUFFICIENT_PAIRED_HISTORY')
 def test_paired_history_only_verified(self):
  row={'event_start_utc':'2026-11-06T20:00:00Z','forecast_at_utc':ISO,'outcomes':{'a':1,'b':1},'verified_settlement':True,'settlement_source':'https://official.example/'}
  result=paired_history([{**row,'observation_id':str(i),'paired_event_ids':[f'a_{i}',f'b_{i}']} for i in range(100)],['a','b']);self.assertEqual(result['status'],'HISTORICAL_JOINT_FREQUENCY_ONLY')
 def test_paired_history_leakage(self):
  row={'event_start_utc':ISO,'forecast_at_utc':'2026-11-07T00:00:00Z','outcomes':{'a':1},'verified_settlement':True,'settlement_source':'https://official.example/'}
  self.assertEqual(paired_history([{**row,'observation_id':str(i),'paired_event_ids':[f'event_{i}']} for i in range(200)],['a'])['status'],'INSUFFICIENT_PAIRED_HISTORY')
 def test_duplicate_paired_rows_do_not_count_as_independent(self):
  row={'observation_id':'same','paired_event_ids':['g1'],'event_start_utc':'2026-11-06T20:00:00Z','forecast_at_utc':ISO,'outcomes':{'a':1},'verified_settlement':True,'settlement_source':'https://official.example/'}
  self.assertEqual(paired_history([row]*100,['a'])['n'],1)
 def test_paired_events_not_double_counted_under_fresh_record_ids(self):
  row={'paired_event_ids':['same_game'],'event_start_utc':'2026-11-06T20:00:00Z','forecast_at_utc':ISO,'outcomes':{'a':1},'verified_settlement':True,'settlement_source':'https://official.example/'}
  self.assertEqual(paired_history([{**row,'observation_id':str(i)} for i in range(100)],['a'])['n'],1)
 def test_performance_excludes_after_game(self):
  r={'grade':'TAIG','league':'NBA','market_family':'points','predicted_probability':.8,'outcome':1,'verified_settlement':True,'market_id':'o', 'event_start_utc':ISO,'forecast_at_utc':'2026-11-06T00:00:00Z'}
  self.assertEqual(grade_report([r])['excluded'],1)
 def test_performance_valid(self):
  r={'grade':'BTA','league':'NBA','market_family':'points','predicted_probability':.8,'outcome':1,'verified_settlement':True,'market_id':'o','event_start_utc':EV['start_utc'],'forecast_at_utc':ISO}
  self.assertEqual(grade_report([r])['groups'][0]['n'],1)
 def test_performance_duplicate_settlement_excluded(self):
  row={'grade':'TAIG','league':'NBA','market_family':'points','predicted_probability':.8,
       'outcome':1,'verified_settlement':True,'market_id':'same_market',
       'event_start_utc':EV['start_utc'],'forecast_at_utc':ISO}
  out=grade_report([row,row])
  self.assertEqual(out['groups'],[]);self.assertEqual(out['excluded'],2)
 def test_scan_bias(self):self.assertEqual(scan_audit(eligible_markets=2,scanned_markets=200,selection_ids=['x'])['status'],'SELECTION_BIAS_REVIEW_REQUIRED')
 def test_bh(self):self.assertEqual(benjamini_hochberg([.001,.03,.8])['discoveries'],[0,1])
 def test_settle_requires_verified_source(self):
  i=market_identity(EV,OFFER);r={'market_identity':i,'event_key':EV['event_key'],'platform':'fanduel','settled_at_utc':'2026-11-07T00:00:00Z','outcome':'WIN'}
  self.assertFalse(reconcile_settlement(EV,OFFER,r)['verified'])
 def test_settle_exact_identity(self):
  i=market_identity(EV,{**OFFER,'line':21.5});r={'market_identity':i,'event_key':EV['event_key'],'platform':'fanduel','settled_at_utc':'2026-11-07T00:00:00Z','outcome':'WIN','source_url':'https://fan.example','source_confirmed':True}
  self.assertEqual(reconcile_settlement(EV,OFFER,r)['status'],'IDENTITY_MISMATCH')
 def test_miss_unknown_without_source(self):self.assertEqual(diagnose_miss(outcome='LOSS',evidence=[])['status'],'CAUSE_UNKNOWN')
 def test_miss_documented(self):
  result=diagnose_miss(outcome='LOSS',evidence=[{'verified':True,'category':'structural','source_url':'https://s.example'}]);self.assertEqual(result['category'],'structural')
 def test_engine_never_automatic_bta_plus(self):
  f={'prediction_at_utc':ISO,'features_asof_utc':'2026-11-05T19:00:00Z','status':'EXPERIMENTAL'}
  self.assertFalse(evaluate(event=EV,offer=OFFER,forecast=f,evidences={},scripts=[],calibrated=False)['strict_eligible'])
 def test_engine_lookahead_blocks(self):
  f={'prediction_at_utc':'2026-11-07T20:00:00Z','features_asof_utc':'2026-11-07T19:00:00Z'}
  r=evaluate(event=EV,offer=OFFER,forecast=f,evidences={},calibrated=True);self.assertIn('model_holdout_validated',r['red_team']['blockers'])
 def test_engine_slip_no_auto_approval(self):self.assertEqual(evaluate_slip([{'event_key':'x','strict_eligible':False}])['status'],'NOT_APPROVED')
 def test_snapshot_audit_pending(self):
  snap={'built_at_utc':ISO,'leagues':{'NBA':{'games':[{'event_key':'g','start_utc':EV['start_utc'],'status':'UPCOMING','candidate_count':0}], 'complete':True,'injury_source':{'status':'RETRIEVED'}}}}
  self.assertEqual(audit_auto_snapshot(snap)['games'][0]['bta_grade'],'NO CERTIFIED GRADE')
 def test_snapshot_change(self):
  old={'leagues':{'NBA':{'games':[{'event_key':'g','start_utc':ISO,'status':'UPCOMING'}]}}};new={'leagues':{'NBA':{'games':[{'event_key':'g','start_utc':ISO,'status':'LIVE'}]}}}
  self.assertTrue(changes_between(old,new)['changed'][0]['invalidate_old_grade'])
 def test_nba_auto_adapter_only_past_days(self):
  e={**EV,'league':'NBA','home':{'abbr':'LAL'},'away':{'abbr':'GSW'}}
  rows=[{'Date':f'2026-10-{i:02d}','Team':'LAL','Player':'Person A','ID':'ID1','Minutes':'32:30','Points':20,'Rebounds':5,'Assists':4} for i in range(1,7)]
  rows.append({'Date':'2026-11-06','Team':'LAL','Player':'Person A','Minutes':'30:00','Points':999})
  out=nba_team_observations(e,rows);self.assertEqual(out['status'],'HISTORICAL_ROLE_RESEARCH');self.assertEqual(out['players'][0]['median_points'],20)
 def test_nba_auto_adapter_missing(self):
  self.assertEqual(nba_team_observations({**EV,'league':'NBA','home':{'abbr':'LAL'},'away':{'abbr':'GSW'}},[])['players'],[])
 def test_nfl_auto_adapter_requires_week(self):self.assertEqual(nfl_team_observations({**EV,'league':'NFL'},[])['status'],'NO_VERIFIED_WEEK_CUTOFF')
 def test_nfl_auto_adapter_cutoff(self):
  e={**EV,'league':'NFL','home':{'abbr':'KC'},'away':{'abbr':'BUF'},'week':5,'season_year':2026}
  rows=[{'season':2026,'week':i,'recent_team':'KC','player_display_name':'A B','targets':5,'carries':0,'passing_yards':0,'receiving_yards':50,'rushing_yards':0,'attempts':0} for i in range(1,5)]
  rows.append({**rows[-1],'week':5,'targets':100})
  res=nfl_team_observations(e,rows);self.assertEqual(res['players'][0]['median_targets'],5)
 def test_refresh_job_provider_failure(self):
  def broken(league,days):raise ValueError('Provider unavailable')
  result=run(collector=broken,now=NOW);self.assertEqual(len(result['leagues']),3)
 def test_refresh_job_no_secrets(self):
  def mock(league,days):
   return {'games':[{'event_key':'e'+league,'start_utc':EV['start_utc'],'status':'UPCOMING','home':{'name':'A'},'away':{'name':'B'},'retrieved_at_utc':ISO}], 'errors':[], 'complete':True}
  r=run(collector=mock,now=NOW);self.assertTrue(r['leagues']['NBA']['source_ok']);self.assertNotIn('api_key',str(r))

if __name__=='__main__':unittest.main()
