"""Entirely SYNTHETIC examples; never represent real NBA player history."""
from datetime import date,timedelta
import pytest
from nba_model import normalize_logs,group_players,estimate,historical_brier,expected_roi,automatic_baselines


def fake_logs(n=42):
    start=date(2025,10,1)
    rows=[]
    for i in range(n):
        rows.append({'PLAYER_ID':'123','PLAYER_NAME':'Fixture Player (FAKE)',
          'GAME_ID':str(2000000+i),'GAME_DATE':(start+timedelta(days=i*2)).isoformat(),
          'MIN':'30','PTS':str(18+(i%9)), 'REB':str(3+(i%6)), 'AST':str(2+(i%4))})
    return normalize_logs(rows)


def test_normalizer_and_grouping():
    logs=fake_logs(); grouped,names=group_players(logs)
    assert len(grouped['123'])==42
    assert names['123']=='Fixture Player (FAKE)'
    assert logs[0]['game_date']<logs[-1]['game_date']


def test_nba_probability_normalized():
    logs=fake_logs()
    r=estimate(logs,'points',21.5)
    assert r['status']=='BASELINE ONLY'
    assert 0 < r['p_over'] < 1
    assert abs(r['p_over']+r['p_under']+r['p_push']-1)<1e-10
    assert 18 <= r['projection'] <= 26


def test_risk_of_small_sample():
    assert estimate(fake_logs(8),'points',21.5)['status']=='INSUFFICIENT HISTORY'


def test_chronological_brier_has_no_future_rows():
    logs=fake_logs()
    baseline=historical_brier(logs,'points',22.5)
    assert baseline['count']>0
    assert 0 <= baseline['brier'] <=1
    logs[-1]['points']=0  # flips last outcome; future result cannot change its prediction
    changed=historical_brier(logs,'points',22.5)
    assert changed['avg_predicted_over']==baseline['avg_predicted_over']
    assert changed['actual_over_rate']!=baseline['actual_over_rate']


def test_expected_roi_pushes():
    assert expected_roi(.55,0,-110)>0
    assert expected_roi(.5,.1,-110)>expected_roi(.5,0,-110)


def test_bad_data_fails_closed():
    with pytest.raises(ValueError,match='Row 2'):
        normalize_logs([{'PLAYER_ID':'123','PLAYER_NAME':'X','GAME_ID':'1','GAME_DATE':'bad','MIN':30,'PTS':12,'REB':5,'AST':3}])
    with pytest.raises(ValueError):estimate(fake_logs(),'steals',4.5)


def test_pushed_integer_line():
    r=estimate(fake_logs(),'rebounds',5.0)
    assert r['p_push']>0


def test_autoscan_is_unpriced():
    a=automatic_baselines(fake_logs())
    assert len(a)==3
    assert all('NOT A PICK' in x['status'] for x in a)
