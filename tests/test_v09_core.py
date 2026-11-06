"""v0.9 deterministic offline checks (NO claims of live provider accuracy)."""
import unittest,tempfile,json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from bta_v09.evidence import freshness,valid_pregame,coverage_report
from bta_v09.forecast import historical_values,exact_line_baseline
from bta_v09.parlay import uncertainty_bounds,historical_joint,wilson_interval,overlap_warnings
from bta_v09.calibration import validate_archive
from bta_v09.grade import audit_candidate
from bta_v09.scripts import mechanisms,reverse_failure
from bta_v09.settlements import observed_game_outcome
from bta_v09.pipeline import collect_research,append_forecasts,write_snapshot

T=datetime(2026,11,5,16,0,tzinfo=timezone.utc)
GAME={'event_key':'espn:NBA:99999','provider_event_id':'99999','league':'NBA','start_utc':'2026-11-07T00:00:00+00:00',
      'status':'UPCOMING','retrieved_at_utc':T.isoformat(),'week':None,'season_year':2026,
      'home':{'name':'Boston Celtics','abbr':'BOS'},'away':{'name':'Los Angeles Lakers','abbr':'LAL'},
      'source':'https://site.api.espn.com/example'}
PROP={'market':'player_points','player':'LeBron James','line':20.5,'selection':'Over',
      'book_updated_utc':T.isoformat(),'bookmaker':'fanduel','american_odds':-110,
      'start_utc':GAME['start_utc'],'provider_event_id':'offer1','league':'NBA',
      'home_name':'Boston Celtics','away_name':'Los Angeles Lakers','player_props':True}


def hist(n=20):
    from datetime import date
    from datetime import timedelta
    return [{'Player':'LeBron James','Team':'LAL','Date':(date(2026,10,1)+timedelta(days=i)).isoformat(),
             'Minutes':'34','Points':str(19+i%7),'Rebounds':'7','Assists':'5',
             'ID':'123','Opp':'BOS','game_id':f'a{i}'} for i in range(n)]


class EvidenceTest(unittest.TestCase):
    def test_freshness_ok(self):
        self.assertEqual(freshness(timestamp=(T-timedelta(minutes=4)).isoformat(),kind='schedule',now=T)['status'],'CURRENT')
    def test_freshness_stale(self):
        self.assertEqual(freshness(timestamp=(T-timedelta(hours=2)).isoformat(),kind='odds',now=T)['status'],'STALE')
    def test_future_source(self):
        self.assertEqual(freshness(timestamp=(T+timedelta(hours=1)).isoformat(),kind='schedule',now=T)['status'],'INVALID')
    def test_missing_timestamp(self):
        self.assertEqual(freshness(timestamp=None,kind='injury',now=T)['status'],'UNVERIFIED')
    def test_bad_kind(self):
        with self.assertRaises(ValueError):freshness(timestamp=T.isoformat(),kind='fantasy',now=T)
    def test_pregame_safe(self):
        self.assertTrue(valid_pregame(GAME,T.isoformat(),now=T)[0])
    def test_no_future_research(self):
        self.assertFalse(valid_pregame(GAME,'2026-11-07T01:00:00Z',now=T)[0])
    def test_game_started(self):
        self.assertFalse(valid_pregame({**GAME,'status':'LIVE'},T.isoformat(),now=T)[0])
    def test_coverage(self):
        x=coverage_report({'injury':False,'market':True},[{'api_key':'SECRET','source':'abc'}])
        self.assertEqual(x['missing'],['injury']);self.assertNotIn('api_key',x['sources'][0])


class ModelTest(unittest.TestCase):
    def test_pregame_samples_only(self):
        rows=hist()+[{'Player':'LeBron James','Team':'LAL','Date':'2026-11-08',
                      'Minutes':'34','Points':'99','game_id':'future'}]
        results=historical_values(GAME,PROP,rows)
        self.assertEqual(results['n'],20)
    def test_exact_margin(self):
        f=exact_line_baseline(GAME,PROP,hist())
        self.assertEqual(f['n'],20)
        self.assertEqual(f['wins']+f['losses']+f['pushes'],20)
        self.assertEqual(f['status'],'EXPERIMENTAL_UNCALIBRATED')
        self.assertIn('NOT-CALIBRATED',f['model_version'])
    def test_model_unsupported(self):
        self.assertEqual(exact_line_baseline(GAME,{**PROP,'market':'player_steals'},hist())['status'],'UNSUPPORTED')
    def test_market_missing_side(self):
        self.assertEqual(exact_line_baseline(GAME,{**PROP,'selection':'YES'},hist())['status'],'UNSUPPORTED')
    def test_future_nba_row(self):
        self.assertEqual(historical_values(GAME,PROP,[{**hist()[0],'Date':'2026-11-07'}])['n'],0)
    def test_nfl_missing_week(self):
        event={**GAME,'league':'NFL','week':None}
        offer={**PROP,'market':'player_rush_yds'}
        self.assertEqual(historical_values(event,offer,[])['status'],'INSUFFICIENT')
    def test_nfl_prior_week(self):
        event={**GAME,'league':'NFL','season_year':2026,'week':9,
               'home':{'name':'Denver Broncos','abbr':'DEN'},'away':{'name':'Kansas City Chiefs','abbr':'KC'}}
        offer={**PROP,'market':'player_rush_yds','player':'John Test'}
        rows=[{'player_display_name':'John Test','recent_team':'KC','season':2026,'week':i,
               'season_type':'REG','rushing_yards':20+i} for i in range(1,11)]
        result=historical_values(event,offer,rows)
        self.assertEqual(result['n'],8)
        self.assertNotIn('2026:9:KC',str(result))
    def test_reverse_miss(self):
        f=exact_line_baseline(GAME,PROP,hist())
        out=reverse_failure(f)
        self.assertEqual(out['status'],'OBSERVED MISSES, CAUSE NOT VERIFIED')
    def test_scenario_not_fabricated(self):
        s=mechanisms('NFL','player_rush_yds','OVER','Any Player')
        self.assertEqual(len(s['scenarios']),5)
        self.assertTrue(all(x['verdict']=='UNKNOWN' for x in s['scenarios']))
    def test_cfb_different_scripts(self):
        s=mechanisms('College football','h2h','YES')
        self.assertIn('favorite_minus_two_turnovers',[x['scenario'] for x in s['scenarios']])
    def test_no_fake_auto_grade(self):
        report=audit_candidate(GAME,PROP,exact_line_baseline(GAME,PROP,hist()),now=T)
        self.assertFalse(report['strict_ticket_eligible']);self.assertEqual(report['grade'],'PENDING EVIDENCE')
    def test_old_offer_pending(self):
        report=audit_candidate(GAME,{**PROP,'book_updated_utc':(T-timedelta(hours=4)).isoformat()},
                               exact_line_baseline(GAME,PROP,hist()),now=T)
        self.assertIn('Offer age/status: STALE QUOTE',report['missing'])


class ParlayTest(unittest.TestCase):
    def test_unverified_leg_no_joint(self):
        self.assertEqual(uncertainty_bounds([{'event':'e','probability':0.9}])['status'],'NO JOINT ESTIMATE')
    def test_frechet(self):
        legs=[{'event':str(i),'probability':0.8,'calibrated':True,'verified_market':True} for i in range(2)]
        r=uncertainty_bounds(legs)
        self.assertAlmostEqual(r['valid_joint_lower'],0.6)
        self.assertAlmostEqual(r['valid_joint_upper'],0.8)
        self.assertAlmostEqual(r['independence_hypothesis_only'],0.64)
    def test_twenty_ninety_nines(self):
        legs=[{'event':str(i),'probability':0.99,'calibrated':True,'verified_market':True} for i in range(20)]
        r=uncertainty_bounds(legs)
        self.assertAlmostEqual(r['valid_joint_lower'],0.8)
        self.assertAlmostEqual(r['independence_hypothesis_only'],0.99**20)
    def test_shared_game_warning(self):
        self.assertTrue(overlap_warnings([{'event':'a'},{'event':'a'}]))
    def test_no_history_fabricated(self):
        self.assertEqual(historical_joint([])['status'],'INSUFFICIENT PAIRED HISTORY')
    def test_wilson(self):
        self.assertTrue(wilson_interval(8,10)[0]<0.8<wilson_interval(8,10)[1])
    def test_invalid_sample(self):
        with self.assertRaises(ValueError):wilson_interval(11,10)
    def test_bool_not_probability(self):
        self.assertEqual(uncertainty_bounds([{'probability':True,'calibrated':True,'verified_market':True}])['status'],'NO JOINT ESTIMATE')


class SettlementTest(unittest.TestCase):
    def setUp(self):
        self.event={**GAME,'status':'FINAL','home':{**GAME['home'],'score':'100'},'away':{**GAME['away'],'score':'90'}}
    def test_h2h(self):
        self.assertEqual(observed_game_outcome(self.event,{'market':'h2h','selection':'Boston Celtics'})['raw_result'],'WIN')
    def test_total(self):
        self.assertEqual(observed_game_outcome(self.event,{'market':'totals','selection':'Over','line':180.5})['raw_result'],'WIN')
    def test_spread(self):
        self.assertEqual(observed_game_outcome(self.event,{'market':'spreads','selection':'Los Angeles Lakers','line':12})['raw_result'],'WIN')
    def test_not_verified(self):
        self.assertFalse(observed_game_outcome(self.event,{'market':'h2h','selection':'Boston Celtics'})['verified_settlement'])
    def test_invalid_team(self):
        self.assertEqual(observed_game_outcome(self.event,{'market':'h2h','selection':'Unknown'})['status'],'AMBIGUOUS TEAM SELECTION')


class ArchiveTest(unittest.TestCase):
    def test_no_fake_verified_settlements(self):
        f={'forecast_id':'a','event_id':'e','market_id':'m','model_id':'historical-beta(2,2)-v09-NOT-CALIBRATED',
           'event_start_utc':'2026-11-09T16:00:00+00:00',
           'prediction_at_utc':'2026-11-09T12:00:00+00:00',
           'features_asof_utc':'2026-11-09T12:00:00+00:00','league':'NBA','market':'player_points',
           'experimental_probability':.75}
        x=validate_archive([f],[{'forecast_id':'a','outcome':1,'verified_settlement':False}])
        self.assertEqual(x['verified_matched'],0)
    def test_live_futures_cannot_be_logged(self):
        row={'forecast_id':'a','prediction_at_utc':'2026-11-09T17:00:00Z',
             'event_start_utc':'2026-11-09T16:00:00Z'}
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'test.jsonl'
            self.assertEqual(append_forecasts(file,[row]),0)
    def test_journal_idempotent(self):
        row={'forecast_id':'a','prediction_at_utc':'2026-11-09T12:00:00Z',
             'event_start_utc':'2026-11-09T16:00:00Z'}
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'test.jsonl'
            self.assertEqual(append_forecasts(file,[row]),1)
            self.assertEqual(append_forecasts(file,[row]),0)
            self.assertEqual(len(file.read_text().splitlines()),1)
    def test_public_snapshot_no_markets(self):
        def schedule(league,day):
            return ([{**GAME,'league':league,'event_key':f'espn:{league}:123',
                      'start_utc':'2026-11-07T00:00:00Z'}],{'retrieved_at_utc':T.isoformat()})
        def loader(league,when):return hist(),[{'status':'RETRIEVED','rows':len(hist())}]
        snap,archive=collect_research(now=T,horizon=1, schedule_fetcher=schedule,
                                       history_loader=loader,nba_official_fetcher=lambda:{'status':'OFF'},
                                       injury_loader=lambda league,now:([],{'source':'fixture://injuries'}))
        self.assertFalse(snap['market_details_persisted']);self.assertEqual(archive,[])
        self.assertEqual(snap['leagues']['NBA']['historical_rows_loaded'],20)
        self.assertNotIn('research_leads_snapshot',snap)
    def test_matched_odds_produce_only_pending(self):
        def schedule(league,day):
            if league!='NBA':return [],{'retrieved_at_utc':T.isoformat()}
            return ([GAME],{'retrieved_at_utc':T.isoformat()})
        def odds(league,key,**kwargs):
            if league!='NBA' or not kwargs.get('props'):return [],{'source':'fixture://markets'}
            return [PROP],{'source':'fixture://markets'}
        def loader(league,when):return hist(),[{'status':'RETRIEVED'}]
        snap,forecasts=collect_research(now=T,horizon=1,odds_key='fake-fixture',include_props=True,
            save_market_details=True,schedule_fetcher=schedule,odds_fetcher=odds,
            history_loader=loader,nba_official_fetcher=lambda:{'status':'OFF'},
            injury_loader=lambda league,now:([],{'source':'fixture://injuries'}))
        self.assertEqual(len(forecasts),1)
        self.assertEqual(snap['auto_ticket'],[])
        self.assertEqual(snap['leagues']['NBA']['games'][0]['research_leads'][0]['grade'],'PENDING EVIDENCE')
        self.assertFalse(snap['leagues']['NBA']['games'][0]['research_leads'][0]['strict_ticket_eligible'])
    def test_write_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'meta.json'
            write_snapshot({'version':'test'},path)
            self.assertEqual(json.loads(path.read_text())['version'],'test')



class CollegeAndSafetyTest(unittest.TestCase):
    def test_cfb_elo_cutoff_and_matching(self):
        from bta_v09.college import research
        event={**GAME,'league':'College football','home':{'name':'Ohio State Buckeyes'},
               'away':{'name':'Oregon Ducks'}}
        games=[{'id':'g1','startDate':'2026-10-01T17:00:00Z','homeTeam':'Ohio State',
                'awayTeam':'Oregon','homePoints':21,'awayPoints':20,'completed':True},
               {'id':'future','startDate':'2026-11-08T17:00:00Z','homeTeam':'Ohio State',
                'awayTeam':'Oregon','homePoints':0,'awayPoints':100,'completed':True}]
        result=research(event,games)
        self.assertEqual(result['status'],'EXPERIMENTAL ONLY')
        self.assertEqual(result['prior_games_processed'],1)
    def test_cfb_ambiguous_or_unmatched_school(self):
        from bta_v09.college import research
        event={**GAME,'league':'College football','home':{'name':'Unknown University Athletics'},
               'away':{'name':'Oregon Ducks'}}
        self.assertEqual(research(event,[{'homeTeam':'Ohio State','awayTeam':'Oregon','completed':True}])['status'],'UNVERIFIED')
    def test_historical_minutes_string(self):
        rows=[{**r,'Minutes':'31:42'} for r in hist()]
        self.assertEqual(historical_values(GAME,PROP,rows)['n'],20)
    def test_multiple_same_request_forecasts_not_duplicated(self):
        record={'forecast_id':'a','prediction_at_utc':'2026-11-09T12:00:00Z',
                'event_start_utc':'2026-11-09T16:00:00Z'}
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'test.jsonl'
            self.assertEqual(append_forecasts(file,[record,record]),1)
            self.assertEqual(len(file.read_text().splitlines()),1)
    def test_large_archive_grouping_is_not_automatically_verified(self):
        from datetime import timedelta
        fs=[];ss=[]
        start=datetime(2024,1,1,tzinfo=timezone.utc)
        for i in range(440):
            kickoff=start+timedelta(days=i)
            fid=f'forecast{i}'
            made=kickoff-timedelta(hours=12)
            fs.append({'forecast_id':fid,'event_id':f'e{i}', 'market_id':f'm{i}',
                       'model_id':'historical-beta(2,2)-v09-NOT-CALIBRATED',
                       'event_start_utc':kickoff.isoformat(),
                       'prediction_at_utc':made.isoformat(), 'features_asof_utc':made.isoformat(),
                       'league':'NBA','market':'player_points','experimental_probability':0.75})
            ss.append({'forecast_id':fid,'event_id':f'e{i}','market_id':f'm{i}',
                       'event_start_utc':kickoff.isoformat(),'outcome':int(i%4>0),
                       'verified_settlement':True,'settlement_source':'https://official.example/test'})
        report=validate_archive(fs,ss)
        self.assertEqual(report['verified_matched'],440)
        self.assertEqual(report['groups']['NBA:player_points']['train']+report['groups']['NBA:player_points']['test'],440)
        # Synthetic data cannot count as real model validation in any user-facing product.

if __name__=='__main__':unittest.main()

class SourceAgeTest(unittest.TestCase):
    def test_nba_old_file_not_made_current_by_download(self):
        from bta_v09.health import source_age
        x=source_age('NBA',[{'snapshot':'2026-10-01','retrieved_at_utc':T.isoformat()}],[],now=T)
        self.assertEqual(x['status'],'STALE PUBLICATION')
        self.assertEqual(x['as_of'],'2026-10-01')
    def test_nba_recent_file(self):
        from bta_v09.health import source_age
        self.assertEqual(source_age('NBA',[{'snapshot':'2026-11-04'}],[],now=T)['status'],'RECENT PUBLICATION')
    def test_no_invented_nfl_publication(self):
        from bta_v09.health import source_age
        x=source_age('NFL',[{'retrieved_at_utc':T.isoformat()}],
                     [{'season':'2026','week':'8'}],now=T)
        self.assertEqual(x['status'],'WEEKLY HISTORY ONLY')
        self.assertEqual(x['latest_season_week'],'2026 W8')
    def test_collection_timestamp_not_underlying_pubdate(self):
        from bta_v09.health import snapshot_age
        x=snapshot_age((T-timedelta(hours=5)).isoformat(),now=T)
        self.assertEqual(x['status'],'STALE COLLECTION')
    def test_future_collection_rejected(self):
        from bta_v09.health import snapshot_age
        self.assertEqual(snapshot_age((T+timedelta(hours=2)).isoformat(),now=T)['status'],'INVALID FUTURE SNAPSHOT')
    def test_no_dates_hardcoded_for_future_openings(self):
        from bta_v08.schedule import next_days
        from zoneinfo import ZoneInfo
        # The schedule window depends on now, not build date.
        t1=datetime(2026,11,5,16,tzinfo=timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
        t2=datetime(2026,11,19,16,tzinfo=timezone.utc).astimezone(ZoneInfo('America/New_York')).date()
        self.assertNotEqual(next_days(t1,horizon=3),next_days(t2,horizon=3))
        self.assertEqual(next_days(t2,horizon=3)[0].isoformat(),'2026-11-19')
