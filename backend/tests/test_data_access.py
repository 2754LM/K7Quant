import unittest

import pandas as pd

from backend.data import access


def make_df(dates):
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": [1.0] * len(dates),
        "high": [1.0] * len(dates),
        "low": [1.0] * len(dates),
        "close": [1.0] * len(dates),
        "volume": [1.0] * len(dates),
    })


class FakeCache:
    def __init__(self, df):
        self.df = df
        self.written = None

    def read(self, symbol, timeframe):
        return self.df

    def write(self, symbol, timeframe, df):
        self.written = df


class FakeFetcher:
    def __init__(self, df):
        self.df = df
        self.calls = []

    def fetch(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        return self.df


class DataAccessCacheCoverageTest(unittest.TestCase):
    def test_partial_cache_fetches_requested_missing_range(self):
        cached_dates = pd.date_range("2026-06-18 00:00:00", periods=12, freq="h")
        fetched_dates = pd.date_range("2026-06-18 00:00:00", periods=49, freq="h")
        cache = FakeCache(make_df(cached_dates))
        fetcher = FakeFetcher(make_df(fetched_dates))
        old_get_cache = access.get_cache
        old_get_fetcher = access.get_fetcher
        old_sleep = access.time.sleep
        access.get_cache = lambda: cache
        access.get_fetcher = lambda: fetcher
        access.time.sleep = lambda _seconds: None
        try:
            df = access.get_kline("BTCUSDT", "1h", "20260618", "20260620")
        finally:
            access.get_cache = old_get_cache
            access.get_fetcher = old_get_fetcher
            access.time.sleep = old_sleep

        self.assertEqual(fetcher.calls, [("BTCUSDT", "1h", "20260618", "20260620")])
        self.assertEqual(len(df), 49)
        self.assertEqual(str(df["date"].iloc[-1])[:10], "2026-06-20")


if __name__ == "__main__":
    unittest.main()
