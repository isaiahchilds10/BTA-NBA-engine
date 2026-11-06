"""Offline deterministic tests. No live API accesses or synthetic accuracy claims."""
import json
import unittest
from datetime import date,datetime,timezone
from bta_v08.schedule import parse_scoreboard,collect,game_counts,parse_instant,next_days,augment_nba_official_score
from bta_v08.markets import parse_offers,match_offers,book_quote_status
from bta_v08.research import descriptive_screen,research_priority,pregame_gate,queue_for_event
from bta_v08.snapshots import make_snapshot,serialize_snapshot
from bta_v08.snapshot_job import build_snapshot

EVENT_ID='401888777'
SOURCE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261107'
STAMP='2026-11-06T12:00:00+00:00'
TEST_NOW=datetime(2026,11,6,12,tzinfo=timezone.utc)


def fixture():
    return {'events':[{'id':EVENT_ID,'date':'2026-11-07T00:30:00Z','status':{'type':{'state':'pre','shortDetail':'7:30 PM ET'}},
         'competitions':[{'competitors':[{'homeAway':'home','score':'0','team':{'id':'10','displayName':'Boston Celtics','abbreviation':'BOS'}},
                                      {'homeAway':'away','score':'0','team':{'id':'11','displayName':'Los Angeles Lakers','abbreviation':'LAL'}}]}]}]}


def slate():
    return parse_scoreboard(fixture(),'NBA',request_day=date(2026,11,6),source=SOURCE,retrieved_at_utc=STAMP)


def odds_example():
    return [{'event_id':'book-7','start_time':'2026-11-07T00:30:00Z','home_team':'Boston Celtics','away_team':'Los Angeles Lakers',
             'books':[{'book':'fanduel','market':'h2h','updated_at':'2026-11-06T13:00:00Z',
                       'outcomes':[{'name':'Boston Celtics','price':-120},{'name':'Los Angeles Lakers','price':100}]},
                       {'book':'fanduel','market':'player_points','updated_at':'2026-11-06T13:00:00Z',
                        'outcomes':[{'name':'Under','description':'LeBron James','point':20.5,'price':-110}]},
                       {'book':'draftkings','market':'h2h','updated_at':'2026-11-06T13:00:00Z',
                        'outcomes':[{'name':'Boston Celtics','price':-125}]}]}]


class TestV08(unittest.TestCase):
    def test_parse_upcoming(self):
        s=slate();self.assertEqual(s[0]['event_key'],f'espn:NBA:{EVENT_ID}')
        self.assertEqual(s[0]['home']['abbr'],'BOS');self.assertEqual(s[0]['status'],'UPCOMING')
    def test_no_fake_roster(self):
        self.assertFalse(slate()[0]['roster_verified'])
    def test_missing_teams_not_invented(self):
        self.assertEqual(parse_scoreboard({'events':[{'id':'12'}]},'NBA',request_day=date(2026,11,7),source=SOURCE,retrieved_at_utc=STAMP),[])
    def test_bad_json_schema_fail(self):
        with self.assertRaises(ValueError):parse_scoreboard({},'NBA',request_day=date(2026,11,7),source=SOURCE,retrieved_at_utc=STAMP)
    def test_bad_date_not_event(self):
        x=fixture();x['events'][0]['date']='no-date'
        self.assertEqual(parse_scoreboard(x,'NBA',request_day=date(2026,11,7),source=SOURCE,retrieved_at_utc=STAMP),[])
    def test_count(self):
        self.assertEqual(game_counts(slate())['UPCOMING'],1)
    def test_day_range(self):
        self.assertEqual(len(next_days(date(2026,11,7),horizon=7)),7)
    def test_nba_official_score_overrides_only_verified_match(self):
        o={'status':'OK','date':'2026-11-06',
           'games':[{'home':'BOS','away':'LAL','status_code':2,'home_score':81,'away_score':80,'state':'Q3'}],
           'retrieved_at_utc':'2026-11-07T01:00:00Z'}
        row, n=augment_nba_official_score(slate(),o,local_day=date(2026,11,6))
        self.assertEqual(n,1);self.assertEqual(row[0]['status'],'LIVE');self.assertEqual(row[0]['home']['score'],'81')
        self.assertEqual(row[0]['score_authority'],'NBA OFFICIAL LIVE CDN')

    def test_nba_official_mismatch_must_not_override(self):
        o={'status':'OK','date':'2026-11-06',
           'games':[{'home':'NYK','away':'LAL','status_code':3,'home_score':81,'away_score':80}]}
        row,n=augment_nba_official_score(slate(),o,local_day=date(2026,11,6))
        self.assertEqual(n,0);self.assertEqual(row[0]['status'],'UPCOMING')

    def test_nba_official_rejects_ambiguous_doubleheader(self):
        o={'status':'OK','date':'2026-11-06',
           'games':[{'home':'BOS','away':'LAL','status_code':3,'home_score':81,'away_score':80}]}
        row,n=augment_nba_official_score(slate()+slate(),o,local_day=date(2026,11,6))
        self.assertEqual(n,0)

    def test_data_provider_h2h(self):
        o=parse_offers(odds_example(),league='NBA',props=False)
        self.assertEqual(len(o),2);self.assertEqual(o[0]['american_odds'],-120)
    def test_no_wrong_book(self):
        self.assertNotIn('draftkings',[x['bookmaker'] for x in parse_offers(odds_example(),league='NBA')])
    def test_prop_exact_line(self):
        o=parse_offers(odds_example(),league='NBA',props=True)
        self.assertEqual((o[0]['player'],o[0]['line'],o[0]['selection']),('LeBron James',20.5,'Under'))
    def test_prohibit_cfb_player_props(self):
        self.assertEqual(parse_offers(odds_example(),league='College football',props=True),[])
    def test_no_bad_odds(self):
        f=odds_example();f[0]['books'][0]['outcomes'][0]['price']='bad'
        self.assertEqual(len(parse_offers(f,league='NBA',props=False)),1)
    def test_match_by_both_teams_start(self):
        m,b=match_offers(slate(),parse_offers(odds_example(),league='NBA'))
        self.assertEqual(len(b),0);self.assertEqual(len(m[slate()[0]['event_key']]),2)
    def test_no_false_match_when_away_wrong(self):
        f=odds_example();f[0]['away_team']='New York Knicks'
        m,b=match_offers(slate(),parse_offers(f,league='NBA'))
        self.assertEqual(len(b),2);self.assertEqual(len(m[slate()[0]['event_key']]),0)
    def test_no_future_price_claim(self):
        q=parse_offers(odds_example(),league='NBA')[0]
        self.assertEqual(book_quote_status(q,now=datetime(2026,11,6,12,tzinfo=timezone.utc)),'INVALID FUTURE QUOTE')
    def test_nba_no_lookahead(self):
        event=slate()[0]
        offer=parse_offers(odds_example(),league='NBA',props=True)[0]
        old=[{'Date':f'2026-10-{i:02d}','Player':'LeBron James','Team':'LAL','Minutes':'32','Points':22+i%3,'Opp':'BOS'} for i in range(1,6)]
        future=[{'Date':'2026-11-08','Player':'LeBron James','Team':'LAL','Minutes':'38','Points':300,'Opp':'BOS'}]
        s=descriptive_screen('NBA',old+future,offer,event,now=TEST_NOW)
        self.assertEqual(s['n'],5);self.assertEqual(s['hits'],0) # under 20.5 loses all five
    def test_exact_threshold_not_guaranteed(self):
        event=slate()[0]
        offer=parse_offers(odds_example(),league='NBA',props=True)[0]
        rows=[{'Date':f'2026-10-{i:02d}','Player':'LeBron James','Team':'LAL','Minutes':'30','Points':i+9,'Opp':'BOS'} for i in range(1,7)]
        s=descriptive_screen('NBA',rows,offer,event,now=TEST_NOW)
        self.assertEqual(s['status'],'HISTORICAL CONTEXT ONLY')
        self.assertNotIn('calibrated_probability',s)
    def test_live_pregame_block(self):
        e=slate()[0];e['status']='LIVE'
        o=parse_offers(odds_example(),league='NBA',props=True)[0]
        self.assertEqual(descriptive_screen('NBA',[],o,e,now=TEST_NOW)['status'],'BLOCKED')
    def test_pending_no_bta_plus(self):
        e=slate()[0];o=parse_offers(odds_example(),league='NBA',props=True)[0]
        self.assertFalse(pregame_gate(e,o,{'status':'HISTORICAL CONTEXT ONLY'},now=TEST_NOW)['strict_ticket_eligible'])
    def test_three_queue_top(self):
        e=slate()[0];o=parse_offers(odds_example(),league='NBA',props=True)[0]
        q=queue_for_event(e,[o,o,o,o],[],max_items=3,now=TEST_NOW)
        self.assertEqual(len(q),1)
    def test_cutoff_prevents_snapshot_from_live(self):
        e=slate()[0];e['status']='LIVE'
        with self.assertRaises(ValueError):make_snapshot(e,[],observed_at_utc='2026-11-06T12:00:00Z')
    def test_cutoff_prevents_after_start(self):
        e=slate()[0]
        with self.assertRaises(ValueError):make_snapshot(e,[],observed_at_utc='2026-11-08T12:00:00Z')
    def test_snapshot_no_calibrated_probability(self):
        e=slate()[0];o=parse_offers(odds_example(),league='NBA',props=True)[0]
        s=make_snapshot(e,[{'offer':o,'screen':{'n':4,'hit_rate_observed':.75}}],observed_at_utc=STAMP)
        self.assertTrue(s['not_a_forecast']);self.assertIsNone(s['markets'][0]['calibrated_p'])
        self.assertIn('sha256',json.loads(serialize_snapshot(s)))
    def test_collect_distinct_ids(self):
        def fetch(l,d):return slate(),{'retrieved_at_utc':STAMP}
        s=collect('NBA',[date(2026,11,6),date(2026,11,7)],fetcher=fetch)
        self.assertEqual(len(s['games']),1)
    def test_collect_errors_not_zero_games(self):
        def broken(l,d):raise OSError('unavailable')
        s=collect('NBA',[date(2026,11,7)],fetcher=broken)
        self.assertFalse(s['complete']);self.assertEqual(len(s['errors']),1)
    def test_job_no_predictions(self):
        def fetch(l,d):return slate(),{'retrieved_at_utc':STAMP}
        s=build_snapshot(datetime(2026,11,6,tzinfo=timezone.utc),fetcher=fetch)
        self.assertFalse(s['includes_model_forecasts']);self.assertEqual(len(s['leagues']),3)
    def test_missing_nfl_week_current_season_excluded(self):
        e=slate()[0];e['league']='NFL';e['season_year']=2026;e['week']=None
        o={'market':'player_rush_yds','player':'John Smith','line':40.5,'selection':'OVER'}
        rows=[{'player_display_name':'John Smith','recent_team':'LAL','season':2026,'week':9,'rushing_yards':100}]
        self.assertEqual(descriptive_screen('NFL',rows,o,e,now=TEST_NOW)['status'],'INSUFFICIENT')
    def test_stale_future_status_not_actionable_after_kickoff(self):
        e=slate()[0]
        o=parse_offers(odds_example(),league='NBA',props=True)[0]
        later=datetime(2026,11,8,12,tzinfo=timezone.utc)
        self.assertEqual(descriptive_screen('NBA',[],o,e,now=later)['status'],'BLOCKED')
        self.assertEqual(pregame_gate(e,o,{},now=later)['grade'],'NOT ACTIONABLE')

    def test_market_freshness_not_model(self):
        o=parse_offers(odds_example(),league='NBA')[0]
        self.assertEqual(o['research_label'],'MARKET OFFER ONLY')

if __name__=='__main__':unittest.main()
