import os
import unittest
from unittest.mock import patch
import app as bridge

KEY = 'local-test-fixture-not-a-production-secret-1234'
RAW = [{'matchId':'one','clubs':{'66712':{'goals':'1'},'2':{'goals':'0'}},'players':{'66712':{'p':{'playername':'Joueur','goals':'1','assists':'0','rating':'8.2'}}}}]
RECORDS = [{'matchId':'one','clubId':'66712','goals':1,'goalsAgainst':0}]

class FakeAPI:
    calls = []
    def get_club_matches(self, club_id, **kwargs):
        self.calls.append((club_id,kwargs))
        return RAW if kwargs.get('output')=='raw' else RECORDS

class FriendliesTests(unittest.TestCase):
    def setUp(self):
        self.client=bridge.app.test_client()
        bridge.cache.clear()
        FakeAPI.calls=[]
        self.env=patch.dict(os.environ,{'FC27_BRIDGE_SECRET':KEY})
        self.api=patch.object(bridge,'FC27API',FakeAPI)
        self.env.start();self.api.start()
    def tearDown(self):
        self.api.stop();self.env.stop()
    def get(self,suffix=''):
        return self.client.get('/api/club/66712/friendlies'+suffix,headers={'X-FC27-Bridge-Key':KEY})
    def test_legacy_records_remain_default(self):
        r=self.get();self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['data'],RECORDS)
        self.assertEqual(FakeAPI.calls[0][1]['output'],'records')
    def test_raw_has_players_and_separate_cache(self):
        self.get()
        r=self.get('?format=raw');self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['data'][0]['players']['66712']['p']['goals'],'1')
        self.assertEqual(len(FakeAPI.calls),2)
        self.assertEqual(FakeAPI.calls[1][1]['match_type'],'friendlyMatch')
        self.assertTrue(self.get('?format=raw').json['cached'])
        self.assertEqual(len(FakeAPI.calls),2)
        self.assertNotIn(KEY,r.get_data(as_text=True))
    def test_raw_still_requires_secret(self):
        r=self.client.get('/api/club/66712/friendlies?format=raw')
        self.assertEqual(r.status_code,401);self.assertEqual(FakeAPI.calls,[])
    def test_invalid_format_rejected_without_ea_call(self):
        self.assertEqual(self.get('?format=unknown').status_code,400)
        self.assertEqual(FakeAPI.calls,[])

if __name__=='__main__':unittest.main()
