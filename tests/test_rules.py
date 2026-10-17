import datetime as dt
import unittest
from unittest.mock import patch
from server import astronomy, destination, score, nearest, forecast, UTC
class RulesTests(unittest.TestCase):
    def test_equinox(self):
        a=astronomy(dt.date(2026,3,20),0,0,0)
        self.assertTrue(17<=dt.datetime.fromisoformat(a['sunset']).hour<=18)
        self.assertLess(abs(a['azimuth']-270),2)
    def test_polar_day(self):
        self.assertNotIn('sunset',astronomy(dt.date(2026,6,21),89,0,0))
    def test_destination(self):
        p=destination(0,0,90,111.195)
        self.assertAlmostEqual(p[0],0,places=3);self.assertAlmostEqual(p[1],1,places=3)
    def test_missing_visibility_not_faked(self):
        row=dict(cloud_cover_low=10,cloud_cover_mid=40,cloud_cover_high=60,visibility=None,precipitation=0)
        n,d=score(row,[row],None)
        self.assertIsNone(d[3]['value']);self.assertIsNone(d[4]['value']);self.assertTrue(0<=n<=100)
    def test_blocking_cloud_reduces_score(self):
        r=dict(cloud_cover_low=0,cloud_cover_mid=50,cloud_cover_high=50,visibility=20000,precipitation=0)
        self.assertGreater(score(r,[r],0)[0],score(r,[dict(r,cloud_cover_low=100)],0)[0])
    def test_out_of_range(self):
        with self.assertRaises(ValueError):nearest([{'time':'2026-10-17T00:00:00+00:00'}],dt.datetime(2026,10,20,tzinfo=UTC))
    def test_missing_layer_fails(self):
        with self.assertRaises(ValueError):score(dict(cloud_cover_low=10,cloud_cover_mid=None,cloud_cover_high=20),[],0)
if __name__=='__main__':unittest.main()
