import os
import unittest
from unittest.mock import patch
import app as bridge
KEY='local-fixture-secret-for-testing-only-12345'
class FakeAPI:
    calls=[]
    fail=set()
    def get_club_matches(self,club_id,**kwargs):
        kind=kwargs['match_type'];self.calls.append(kind)
        if kind in self.fail:raise RuntimeError('EA unavailable')
        return [{'matchId':kind,'timestamp':{'friendlyMatch':1,'leagueMatch':3,'playoffMatch':2}[kind],
                 'clubs':{'66712':{},'2':{}},'players':{'66712':{'p':{'goals':'1'}}}}]
class RecentTests(unittest.TestCase):
    def setUp(self):
        bridge.cache.clear();FakeAPI.calls=[];FakeAPI.fail=set();self.client=bridge.app.test_client()
    def request(self):
        with patch.dict(os.environ,{'FC27_BRIDGE_SECRET':KEY}),patch.object(bridge,'FC27API',FakeAPI):
            return self.client.get('/api/club/66712/matches',headers={'X-FC27-Bridge-Key':KEY})
    def test_categories_sorted_players_retained_cached(self):
        r=self.request();self.assertEqual(r.status_code,200)
        self.assertEqual([m['relMatchType'] for m in r.json['data']],['leagueMatch','playoffMatch','friendlyMatch'])
        self.assertEqual(r.json['data'][0]['players']['66712']['p']['goals'],'1')
        self.assertTrue(self.request().json['cached']);self.assertEqual(len(FakeAPI.calls),3)
    def test_partial_and_total_outage(self):
        FakeAPI.fail={'playoffMatch'};r=self.request();self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['unavailableTypes'],['playoffMatch'])
        bridge.cache.clear();FakeAPI.fail={'leagueMatch','playoffMatch','friendlyMatch'}
        self.assertEqual(self.request().status_code,502)
    def test_auth_required(self):
        self.assertEqual(self.client.get('/api/club/66712/matches').status_code,401)
