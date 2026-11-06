"""Synthetic/fixture tests only. Never interpret passing tests as sportsbook accuracy."""
import sys, os, unittest
from datetime import date, datetime, timedelta, timezone
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from bta_v07.history import market_result,historical_audit,nba_logs_for_player
from bta_v07.injuries import safety_verdict,college_availability
from bta_v07.failures import classify_miss,reverse_failure_audit
from bta_v07.opponents import opponent_rate_context,reverse_matchup_context
from bta_v07.playbyplay import audit_nfl_player_plays
from bta_v07.calibration import calibrated_holdout
from bta_v07.scenarios import validate_scenarios,SCRIPT_FAMILIES,scenario_analogs
from bta_v07.grading import automatic_candidate_review,REQUIRED_BASE,REQUIRED_NBA_PROP

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.games=[{'date':f'2026-01-{i:02}','game_id':f'g{i}','Points':v,'eligible':True,'opponent':'BOS'}
                    for i,v in enumerate([32,34,29,28,19,33,30,26,18,32],1)]
    def test_exact_over(self):
        self.assertEqual(market_result(21,20.5,'OVER'),'WIN')
        self.assertEqual(market_result(20,20.5,'UNDER'),'WIN')
    def test_push(self):self.assertEqual(market_result(20,20,'UNDER'),'PUSH')
    def test_yes_no_inclusive(self):
        self.assertEqual(market_result(20,20,'YES',market_kind='YES_NO_THRESHOLD'),'WIN')
        self.assertEqual(market_result(20,20,'NO',market_kind='YES_NO_THRESHOLD'),'LOSS')
    def test_3_for_3_margins(self):
        r=historical_audit(self.games,field='Points',line=20.5,side='OVER',before=date(2026,2,1))
        self.assertTrue(r['first_three_three_for_three'])
        self.assertEqual(r['n_games'],10)
        self.assertEqual(r['wins'],8)
        self.assertAlmostEqual(r['historical_hit_rate'],.8)
        self.assertEqual(len(r['losses_for_review']),2)
    def test_no_future_leakage(self):
        r=historical_audit(self.games,field='Points',line=25.5,side='OVER',before=date(2026,1,4))
        self.assertEqual(r['n_games'],3)
    def test_missing_participation_not_zero(self):
        g=self.games+[{'date':'2026-01-11','game_id':'g11','Points':0,'eligible':None}]
        r=historical_audit(g,field='Points',line=20.5,side='OVER',before=date(2026,2,1))
        self.assertEqual(r['n_games'],10)
        self.assertEqual(len(r['skipped']),1)
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            historical_audit(self.games+self.games[:1],field='Points',line=20,side='OVER',before=date(2026,2,1))
    def test_nba_import(self):
        r=nba_logs_for_player([{'Date':'2026-01-01','Player':'Example Name','ID':'123','Team':'MIN','Opp':'BOS',
                                'Minutes':'34','Points':'23','Rebounds':'6','Assists':'2'}],
                                'Example Name',stat='Points',before=date(2026,1,2))
        self.assertEqual(r[0]['Points'],23.)
        self.assertTrue(r[0]['eligible'])

class InjuryTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,5,15,tzinfo=timezone.utc)
    def test_out(self):
        r=safety_verdict({'status':'OUT','published_at_utc':'2026-11-05T12:00:00Z'},checked_at=self.now)
        self.assertEqual(r['gate'],'BLOCKED')
    def test_available_not_confirmed_active(self):
        r=safety_verdict({'status':'AVAILABLE','published_at_utc':'2026-11-05T12:00:00Z'},checked_at=self.now)
        self.assertEqual(r['gate'],'REVIEW REQUIRED')
    def test_unlisted(self):
        r=safety_verdict({'status':'NOT LISTED','published_at_utc':'2026-11-05T12:00:00Z'},checked_at=self.now)
        self.assertEqual(r['gate'],'UNVERIFIED')
    def test_stale(self):
        r=safety_verdict({'status':'OUT','published_at_utc':'2026-10-01T12:00:00Z'},checked_at=self.now)
        self.assertEqual(r['gate'],'UNVERIFIED')
    def test_no_posttip(self):
        r=safety_verdict({'status':'OUT','published_at_utc':'2026-11-05T12:00:00Z'},checked_at=self.now,
                         requested_game_utc=datetime(2026,11,5,11,tzinfo=timezone.utc))
        self.assertEqual(r['gate'],'UNVERIFIED')
    def test_college_unverified(self):self.assertEqual(college_availability('OSU')['gate'],'UNVERIFIED')

class OpponentsTests(unittest.TestCase):
    def test_shrunk_and_only_past(self):
        rows=[{'date':'2026-01-01','defense_team':'BOS' if i<15 else 'CLE','x':100+i,'opportunities':30} for i in range(65)]
        rows.append({'date':'2027-01-01','defense_team':'BOS','x':999999,'opportunities':1})
        r=opponent_rate_context(rows,opponent='BOS',stat_key='x',cutoff=date(2026,11,1))
        self.assertEqual(r['status'],'DESCRIPTIVE ONLY')
        self.assertEqual(r['target_n'],15)
        self.assertLess(r['shrunken_context_factor'],1.1)
    def test_insufficient(self):
        r=opponent_rate_context([],opponent='BOS',stat_key='x',cutoff=date(2026,11,1))
        self.assertEqual(r['status'],'INSUFFICIENT')
    def test_reverse_matchup(self):
        games=[{'date':'2026-01-01','opponent':'B','pts':20} for _ in range(6)]
        r=reverse_matchup_context(games,opponent_quality={'B':50,'C':70},next_opponent='C',cutoff=date(2026,2,1),field='pts')
        self.assertTrue(r['potentially_tougher_than_history'])

class FailureTests(unittest.TestCase):
    def test_unknown_never_contextual(self):
        self.assertEqual(classify_miss(outcome='LOSS')['category'],'UNEXPLAINED')
    def test_source_linked(self):
        x=classify_miss(outcome='LOSS',incident={'source_url':'https://nfl.com/report','verified_at':'2026-01-01',
                                               'incident_type':'early_injury'})
        self.assertEqual(x['category'],'CONTEXTUAL')
    def test_structural_requires_multiple(self):
        x=classify_miss(outcome='LOSS',incident={'source_url':'https://nfl.com/report','verified_at':'2026-01-01',
                                               'incident_type':'role_reduction_multiple_games','observed_games':1})
        self.assertEqual(x['category'],'UNEXPLAINED')
    def test_reverse_preserves_unknown(self):
        r=reverse_failure_audit(losses=[{'game_id':'g1','miss_category':'UNEXPLAINED'}])
        self.assertEqual(r['unresolved_failures'],1)

class PlayTests(unittest.TestCase):
    def test_qtr_goal_td_explosive(self):
        plays=[{'game_id':'g1','season_type':'REG','qtr':'1','posteam':'NYG','rusher_player_id':'p1','rush_attempt':'1',
                'rushing_yards':'8','yardline_100':'4','rush_touchdown':'1'},
               {'game_id':'g1','season_type':'REG','qtr':'2','posteam':'NYG','rusher_player_id':'p1','rush_attempt':'1',
                'rushing_yards':'3','yardline_100':'60','rush_touchdown':'0'},
               {'game_id':'g1','season_type':'REG','qtr':'2','posteam':'NYG','receiver_player_id':'p1',
                'receiving_yards':'9','yardline_100':'4','pass_touchdown':'1'},
               {'game_id':'g1','season_type':'REG','qtr':'4','posteam':'NYG','rusher_player_id':'p1',
                'rush_attempt':'1','rushing_yards':'99','no_play':'1'},
               {'game_id':'g1','season_type':'REG','qtr':'5','posteam':'NYG','rusher_player_id':'p1',
                'rush_attempt':'1','rushing_yards':'99'}]
        r=audit_nfl_player_plays(plays,player_id='p1')
        g=r['games'][0]
        self.assertEqual(g['rushing_yards'],11)
        self.assertEqual(g['rush_without_longest'],3)
        self.assertEqual(g['inside_5_rushes'],1)
        self.assertEqual(g['rushing_tds'],1)
        self.assertEqual(g['receiving_tds'],1)
        self.assertTrue(g['met_any_regulation_quarter'])
    def test_player_filter(self):
        self.assertEqual(audit_nfl_player_plays([{'game_id':'1','rusher_player_id':'other','rush_attempt':'1','qtr':1,
                                                 'rushing_yards':50}],player_id='p1')['games_with_recorded_relevant_plays'],0)
    def test_pregame_week_filter(self):
        plays=[{'game_id':'g1','week':'2','season_type':'REG','qtr':'1','rusher_player_id':'p1',
                'rush_attempt':'1','rushing_yards':'10'},
               {'game_id':'g2','week':'5','season_type':'REG','qtr':'1','rusher_player_id':'p1',
                'rush_attempt':'1','rushing_yards':'200'}]
        r=audit_nfl_player_plays(plays,player_id='p1',before_week=5)
        self.assertEqual(r['games_with_recorded_relevant_plays'],1)
        self.assertEqual(r['games'][0]['rushing_yards'],10)

class ScenarioTests(unittest.TestCase):
    def test_two_worse_cut(self):
        scenarios=[{'scenario':k,'verdict':'WORSE' if i<2 else 'SAME','mechanism':'measurable playing-time shift',
                   'evidence_source':'https://nfl.com'} for i,k in enumerate(SCRIPT_FAMILIES['NFL_PROP'])]
        self.assertEqual(validate_scenarios('NFL_PROP',scenarios)['status'],'CUT')
    def test_different_families(self):
        self.assertNotEqual(set(SCRIPT_FAMILIES['NFL_PROP']),set(SCRIPT_FAMILIES['CFB_MONEYLINE']))
    def test_analogs_do_not_fabricate_mechanism(self):
        games=[{'date':f'2026-01-{i+1:02}','value':5+i%7,'game_margin':i%17-8,'game_total':100+i%12} for i in range(30)]
        r=scenario_analogs(games,line=5.5,side='OVER',before=date(2026,2,1))
        self.assertTrue(all(a['verdict']=='UNKNOWN' for a in r['scenarios'].values()))

class CalibrationTests(unittest.TestCase):
    def _forecasts(self):
        records=[]
        for i in range(70):
            kickoff=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=i)
            records.append({'event_id':f'g{i}','market_id':'m1','event_start_utc':kickoff.isoformat(),
                 'prediction_at_utc':(kickoff-timedelta(hours=2)).isoformat(),
                 'features_asof_utc':(kickoff-timedelta(hours=5)).isoformat(),
                 'probability':.45 if i%3 else .70,'outcome':int(i%4<2)})
        return records
    def test_not_enough(self):
        self.assertEqual(calibrated_holdout(self._forecasts()[:10])['status'],'INSUFFICIENT')
    def test_heldout_split(self):
        r=calibrated_holdout(self._forecasts(),min_train=30,min_test=10,min_distinct_test_dates=5)
        self.assertTrue(r['status'].startswith('FORECAST_CHECKS'))
        self.assertEqual(r['train']+r['test'],70)
    def test_postgame_forecast_rejected(self):
        rec=self._forecasts()
        rec[0]['prediction_at_utc']=rec[0]['event_start_utc']
        r=calibrated_holdout(rec,min_train=30,min_test=10,min_distinct_test_dates=5)
        self.assertEqual(r['rejected_rows'],1)
    def test_no_future_features(self):
        rec=self._forecasts()
        rec[0]['features_asof_utc']=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=3)).isoformat()
        r=calibrated_holdout(rec,min_train=30,min_test=10,min_distinct_test_dates=5)
        self.assertEqual(r['rejected_rows'],1)

class GradingTests(unittest.TestCase):
    def test_fail_closed(self):
        r=automatic_candidate_review({'family':'NBA_PROP','event_id':'e',
             'event_start_utc':'2026-11-07T00:00:00Z','scenarios':[]})
        self.assertEqual(r['grade'],'PENDING')
    def test_worse_cut_no_data(self):
        scripts=[{'scenario':k,'verdict':'WORSE' if i<2 else 'SAME','mechanism':'valid specific reason',
                  'evidence_source':'https://nba.com'} for i,k in enumerate(SCRIPT_FAMILIES['NBA_PROP'])]
        r=automatic_candidate_review({'family':'NBA_PROP','event_id':'e','event_start_utc':'2026-11-07T00:00:00Z',
                                      'scenarios':scripts})
        self.assertEqual(r['grade'],'CUT')
    def test_no_final_ticket_even_with_all_records(self):
        kickoff='2026-11-07T00:00:00Z'
        facets={k:{'status':'VERIFIED','event_id':'e','source_url':'https://nba.com/report',
                   'observed_at_utc':'2026-11-06T23:00:00Z'} for k in REQUIRED_BASE|REQUIRED_NBA_PROP}
        scripts=[{'scenario':k,'verdict':'SAME','mechanism':'observed stable role','evidence_source':'https://nba.com'} for k in SCRIPT_FAMILIES['NBA_PROP']]
        r=automatic_candidate_review({'family':'NBA_PROP','event_id':'e','event_start_utc':kickoff,
          'facets':facets,'scenarios':scripts,'injury_gate':'VERIFIED_ACTIVE','calibration_status':'FORECAST_CHECKS_PASS',
          'history':{'status':'RESEARCH ONLY','n_games':25,'historical_hit_rate':.96,'last_ten_win_rate':1.,'median_clearance_margin':10},
          'exact_market_offer_verified':True,'independent_audit':{'result':'PASSED','source_url':'https://nba.com',
                                                                   'reviewer_id':'other','original_reviewer_id':'original'},
          'calibrated_probability':.86,'confirmed_ordinary_failure_count':0})
        self.assertEqual(r['tier'],'TAIG CANDIDATE')
        self.assertFalse(r['final_ticket_eligible'])

if __name__=='__main__':unittest.main()
