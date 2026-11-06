import unittest
from datetime import datetime, timezone, date
from bta_v05.sources import select_latest_official_nba_pdf, _csv
from bta_v05.models import (nba_injury_lookup, nfl_injury_lookup, nfl_snaps_lookup,
    nba_matchup_context, cfb_elo_progress, cfb_unvalidated_upcoming,
    bta_stress_gate, nfl_defense_context,historical_threshold)
from bta_v05.calibration import fit_evaluate

class V05Tests(unittest.TestCase):
    def test_nba_pdf_link_chooses_pm_over_am(self):
        html='''<a href="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-05_11_45AM.pdf">a</a>
        <a href="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-05_12_30PM.pdf">b</a>
        <a href="https://bad.example/steal.pdf">x</a>'''
        url,dt=select_latest_official_nba_pdf(html)
        self.assertIn('12_30PM.pdf',url)
        self.assertEqual(dt.hour,12)

    def test_nba_player_out_not_missing_clearance(self):
        t='Injury Report Current Status\n11/05/2026 ORL@PHX Orlando Magic Banchero, Paolo Out\nSprain\n'
        meta={'source':'https://ak-static.cms.nba.com/example.pdf','report_published_et_naive':'2026-11-05T07:30'}
        self.assertEqual(nba_injury_lookup(t,'Paolo Banchero',meta,now=datetime(2026,11,5,16,tzinfo=timezone.utc))['gate'],'BLOCKED')
        self.assertEqual(nba_injury_lookup(t,'Stephen Curry',meta,now=datetime(2026,11,5,16,tzinfo=timezone.utc))['gate'],'UNVERIFIED')
        wrapped='Injury Report Current Status\nBanchero, Paolo\nOut\nIsaac, Jonathan Questionable\n'
        self.assertEqual(nba_injury_lookup(wrapped,'Paolo Banchero',meta,now=datetime(2026,11,5,16,tzinfo=timezone.utc))['gate'],'BLOCKED')
        stale=nba_injury_lookup(t,'Paolo Banchero',meta,now=datetime(2026,11,10,16,tzinfo=timezone.utc))
        self.assertEqual(stale['gate'],'UNVERIFIED')

    def test_nfl_report_week_and_not_listed(self):
        rows=[{'week':'9','full_name':'Example Player','report_status':'Out','team':'BUF','date_modified':'2026-10-25T12:00:00Z'},
              {'week':'10','full_name':'Example Player','report_status':'Questionable','team':'BUF','date_modified':'2026-11-04T12:00:00Z'}]
        self.assertEqual(nfl_injury_lookup(rows,'Example Player',10,'BUF')['gate'],'REVIEW REQUIRED')
        self.assertEqual(nfl_injury_lookup(rows,'Example Player',9,'BUF')['gate'],'BLOCKED')
        self.assertEqual(nfl_injury_lookup(rows,'Unknown Player',10,'BUF')['gate'],'UNVERIFIED')

    def test_snap_trend_excludes_current_week(self):
        rows=[{'week':str(w),'player':'Test P','team':'BUF','opponent':'NYJ','offense_pct':str(p),'offense_snaps':'42'}
              for w,p in enumerate([.91,.92,.93,.90,.88,.70,.60],1)]
        d=nfl_snaps_lookup(rows,'Test P',before_week=7,team='BUF')
        self.assertEqual(len(d['sample']),6)
        self.assertTrue(all(v['week']<7 for v in d['sample']))
        self.assertEqual(d['gate'],'HISTORICAL CONTEXT ONLY')

    def test_nfl_opponent_ratio_no_future_weeks(self):
        snaps=[];stats=[]
        for wk in range(1,8):
            for team,opp in [('A','B'),('B','A'),('C','D'),('D','C'),('E','F'),('F','E')]:
                snaps.append({'week':str(wk),'team':team,'opponent':opp,'player':'x'})
                for i in range(3):
                    stats.append({'week':str(wk),'team':team,'player_id':str(i),
                                  'receiving_yards':str(50+(20 if opp=='B' else 0))})
        past=nfl_defense_context(stats,snaps,opponent='B',metric='Receiving yards',before_week=7)
        self.assertEqual(past['gate'],'RESEARCH ONLY')
        self.assertEqual(past['opponent_games'],6)
        future=nfl_defense_context(stats,snaps,opponent='B',metric='Receiving yards',before_week=2)
        self.assertEqual(future['gate'],'UNVERIFIED')

    def test_nba_matchup_uses_only_prior_dates(self):
        rows=[]
        for w in range(1,24):
            dt=f'2026-01-{w:02d}'
            for i in range(8):
                rows.append({'Date':dt,'Team':'AAA','Opp':'BBB','ID':str(i),
                            'Player':'T Player' if i==0 else f'Player {i}',
                            'Points':'15','Assists':'3','Rebounds':'4','Minutes':'25'})
        # Additional independent team games establish the league baseline.
        for w in range(1,24):
            for i in range(8):
                rows.append({'Date':f'2026-01-{w:02d}','Team':'CCC','Opp':'DDD',
                             'ID':f'other-{i}','Player':f'Other {i}',
                             'Points':'15','Assists':'2','Rebounds':'5','Minutes':'25'})
        before=date(2026,1,19)
        d=nba_matchup_context(rows,'T Player','BBB',before=before,stat='Points')
        self.assertEqual(d['gate'],'RESEARCH ONLY')
        self.assertEqual(d['opponent_games'],18)

    def test_college_no_future_scores_in_earlier_forecasts(self):
        games=[{'id':'a','homeTeam':'A','awayTeam':'B','homePoints':30,'awayPoints':10,
                'startDate':'2026-09-01T16:00:00Z','completed':True},
               {'id':'b','homeTeam':'A','awayTeam':'B','homePoints':10,'awayPoints':40,
                'startDate':'2026-09-08T16:00:00Z','completed':True}]
        ratings,pred=cfb_elo_progress(games)
        self.assertEqual(len(pred),2)
        first=pred[0]['p_home_raw']
        games[1]['homePoints']=300
        games[1]['awayPoints']=1
        _,pred2=cfb_elo_progress(games)
        self.assertAlmostEqual(first,pred2[0]['p_home_raw'])
        _,prior=cfb_elo_progress(games,cutoff=datetime(2026,9,8,tzinfo=timezone.utc))
        self.assertEqual(len(prior),1)
        self.assertEqual(cfb_unvalidated_upcoming('X','B',ratings)['gate'],'UNVERIFIED')

    def test_stress_gate_player_props_vs_moneyline(self):
        self.assertEqual(bta_stress_gate('NFL player props',['WORSE','WORSE','BETTER','SAME','BETTER'],blockers=[],sources_verified=True,independent_audit=True)['status'],'CUT')
        self.assertEqual(bta_stress_gate('College football moneyline',['WORSE','WORSE','BETTER','SAME','BETTER'],blockers=[],sources_verified=True,independent_audit=True)['status'],'PENDING / UPSET RISK')
        self.assertEqual(bta_stress_gate('NBA player props',['BETTER']*5,blockers=[],sources_verified=True,independent_audit=True)['status'],'MANUAL AUDIT REQUIRED')
        self.assertEqual(bta_stress_gate('NBA player props',['BETTER']*5,blockers=['Injury unknown'],sources_verified=True,independent_audit=True)['status'],'PENDING')

    def test_historical_threshold_3_for_3(self):
        z=historical_threshold([{'points':20},{'points':22},{'points':19}],field='points',line=18.5)
        self.assertTrue(z['three_for_three'])
        self.assertEqual(z['all_hits'],3)
        self.assertEqual(z['last10_games'],3)

    def test_calibration_is_chronological_and_benchmark_is_train_only(self):
        rows=[]
        for i in range(600):
            # 300 days, 2 independent markets each day. First 400 poor, rest better.
            day=date(2025,1,1).toordinal()+i//2
            eventday=date.fromordinal(day).isoformat()
            rows.append({'id':str(i),'date':eventday,'probability':.7 if i%2 else .3,
                         'outcome':int((i//7)%3==0)})
        o=fit_evaluate(rows,min_train=300,min_test=100)
        self.assertEqual(o['status'],'TESTED / NOT PROVEN BETTING EDGE')
        self.assertGreater(o['test'],99)
        self.assertGreater(o['train'],299)
        self.assertIn('brier',o['calibrated'])
        with self.assertRaises(ValueError):
            fit_evaluate([{'id':'x','date':'2026-01-01','probability':1.2,'outcome':1}])

    def test_calibration_small_n_rejected(self):
        o=fit_evaluate([{'date':'2026-11-01','probability':.7,'outcome':1}],min_train=2,min_test=1)
        self.assertEqual(o['status'],'NOT VALIDATED')

if __name__=='__main__':unittest.main()

class NFLGamesTests(unittest.TestCase):
    def test_nfl_elo_excludes_future_and_regresses_per_season(self):
        from bta_v05.models import nfl_game_elo_progress
        games=[{'game_id':'g1','season':'2025','week':'1','gameday':'2025-09-07','home_team':'A',
                'away_team':'B','home_score':'35','away_score':'10'},
               {'game_id':'g2','season':'2026','week':'1','gameday':'2026-09-07','home_team':'B',
                'away_team':'A','home_score':'42','away_score':'7'}]
        _,pred=nfl_game_elo_progress(games)
        self.assertEqual(len(pred),2)
        games[1]['home_score']='0';games[1]['away_score']='70'
        _,pred2=nfl_game_elo_progress(games)
        self.assertAlmostEqual(pred[0]['p_home_raw'],pred2[0]['p_home_raw'])
        _,hist=nfl_game_elo_progress(games,cutoff=date(2026,9,7))
        self.assertEqual(len(hist),1)
