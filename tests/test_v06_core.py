"""Offline fixture checks. These do NOT establish live provider or betting accuracy."""
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bta_v06.live import parse_nba_scoreboard, parse_nba_boxscore, parse_espn_scoreboard, gate_freshness, fetch_json, nba_monitor
from bta_v06.refresh import capture,write_atomic
from bta_v06.gates import evaluate_candidate, SCRIPT_FAMILIES
from bta_v06.requirements import REQUIREMENTS

class TestNBA(unittest.TestCase):
    def test_official_scoreboard_extract(self):
        payload={'scoreboard': {'gameDate':'2026-11-05', 'games':[
            {'gameId':'0022600099','gameStatus':2,'gameStatusText':'Q2 06:01',
             'homeTeam':{'teamTricode':'BOS','score':53},'awayTeam':{'teamTricode':'MIL','score':50},
             'gameTimeUTC':'2026-11-05T00:30:00Z'}]}}
        r=parse_nba_scoreboard(payload)
        self.assertEqual(r['games_count'],1)
        self.assertEqual(r['games'][0]['home'],'BOS')
    def test_missing_scoreboard_fails(self):
        with self.assertRaises(ValueError):parse_nba_scoreboard({'scoreboard':{'gameDate':'2026-11-05'}})
    def test_boxscore_players(self):
        payload={'game':{'gameId':'0022600099','gameStatus':2,
            'homeTeam':{'teamTricode':'BOS','players':[{'personId':7,'name':'Test Player','statistics':{'points':21,'reboundsTotal':4,'assists':3,'minutes':'18:22'}}]},
            'awayTeam':{'teamTricode':'MIL','players':[]}}}
        r=parse_nba_boxscore(payload,'0022600099')
        self.assertEqual(r['players'][0]['points'],21)
        with self.assertRaises(ValueError):parse_nba_boxscore(payload,'0022600088')
    def test_nonallowlisted(self):
        with self.assertRaises(ValueError):fetch_json('http://example.org/evil')
    def test_nba_fallback_is_explicitly_unofficial(self):
        def fail():raise TimeoutError('blocked')
        def espn(league,day):
            return {'status':'OK','source':'https://site.api.espn.com/fake','date':day,
                    'retrieved_at_utc':'2026-11-05T10:00:00+00:00','games':[], 'games_count':0}
        r=nba_monitor(official_fetch=fail,espn_fetch=espn)
        self.assertEqual(r['provider_quality'],'UNOFFICIAL ESPN FALLBACK')
        self.assertEqual(r['official_error_type'],'TimeoutError')

    def test_freshness(self):
        now=datetime(2026,11,5,12,0,tzinfo=timezone.utc)
        self.assertEqual(gate_freshness('2026-11-05T11:59:30+00:00',now,5),'CURRENT SNAPSHOT')
        self.assertEqual(gate_freshness('2026-11-05T10:00:00+00:00',now,5),'STALE / UNVERIFIED')
        self.assertEqual(gate_freshness('',now,5),'UNVERIFIED')

class TestOtherFeeds(unittest.TestCase):
    def test_espn(self):
        r=parse_espn_scoreboard({'events':[{'id':'42','date':'2026-11-05T20:00Z',
           'status':{'type':{'description':'Scheduled'}},
           'competitions':[{'competitors':[{'homeAway':'home','team':{'displayName':'A'}},
                                         {'homeAway':'away','team':{'displayName':'B'}}]}]}]})
        self.assertEqual(r['games_count'],1)
        self.assertEqual(r['games'][0]['away'],'B')
    def test_missing_espn_events_fails(self):
        with self.assertRaises(ValueError):parse_espn_scoreboard({})
    def test_fail_closed_snapshot(self):
        def nba_fail():raise TimeoutError('provider timed out')
        def espn_ok(league,day):
            return {'status':'OK','source':f'https://example/{league}','retrieved_at_utc':'2026-11-05T00:00:00+00:00',
                    'date':day,'games':[],'games_count':0}
        r=capture(datetime(2026,11,5,tzinfo=timezone.utc),nba_fetch=nba_fail,espn_fetch=espn_ok)
        self.assertEqual(r['sources']['NBA official scoreboard']['status'],'UNVERIFIED')
        self.assertEqual(r['sources']['NFL schedule / score']['status'],'OK')
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'current.json'
            write_atomic(r,path)
            self.assertEqual(json.loads(path.read_text())['schema_version'],1)

class TestResearchGate(unittest.TestCase):
    def setUp(self):
        self.scripts={k:'SAME' for k in SCRIPT_FAMILIES['NFL_PROP']}
        self.reasons={k:'Documented test mechanism' for k in self.scripts}
        self.sources={k:True for k in ('matchup','participation','role','opponent','market_price','publication_time')}
    def check(self,**overrides):
        params=dict(family='NFL_PROP',scripts=self.scripts,source_attestations=self.sources,
                    evidence_reasons=self.reasons, independent_review=True,settlement_verified=True)
        params.update(overrides)
        return evaluate_candidate(**params)
    def test_two_worse_cuts_prop(self):
        changed=dict(self.scripts);changed['close']='WORSE';changed['low_scoring']='WORSE'
        self.assertEqual(self.check(scripts=changed)['gate'],'CUT')
    def test_one_worse_not_auto_taig(self):
        changed=dict(self.scripts);changed['close']='WORSE'
        self.assertEqual(self.check(scripts=changed)['gate'],'FURTHER REVIEW')
    def test_not_verified_blocks(self):
        sources=dict(self.sources);sources['participation']=False
        self.assertEqual(self.check(source_attestations=sources)['gate'],'PENDING')
    def test_no_reason_blocks(self):
        reasons=dict(self.reasons);reasons['close']=''
        self.assertEqual(self.check(evidence_reasons=reasons)['gate'],'PENDING')
    def test_no_auto_grade(self):
        self.assertEqual(self.check()['gate'],'READY FOR MANUAL GRADING')
    def test_cfb_no_misapplied_two_worse_cut(self):
        scripts={k:'WORSE' for k in SCRIPT_FAMILIES['CFB_MONEYLINE']}
        reasons={k:'Reason' for k in scripts}
        result=evaluate_candidate(family='CFB_MONEYLINE',scripts=scripts,source_attestations=self.sources,
                       evidence_reasons=reasons, independent_review=True,settlement_verified=True)
        self.assertNotEqual(result['gate'],'CUT')
    def test_audit_has_40_unique_sections(self):
        self.assertEqual([a[0] for a in REQUIREMENTS],list(range(1,41)))
        self.assertTrue(all(a[2] in {'Partial','Manual','Pending'} for a in REQUIREMENTS))

if __name__=='__main__':unittest.main()
