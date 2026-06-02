from __future__ import annotations

import unittest

import pandas as pd

from backend.app.technical import (
    baostock_symbol,
    build_kline_scenario,
    build_technical_analysis,
    build_technical_levels,
    normalize_stock_code,
)


def make_history(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(closes), freq="D").strftime("%Y-%m-%d"),
            "code": ["sh.600000"] * len(closes),
            "open": [value - 0.05 for value in closes],
            "high": [value + 0.2 for value in closes],
            "low": [value - 0.2 for value in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
            "amount": [value * 1_000_000 for value in closes],
        }
    )


class TechnicalLevelTests(unittest.TestCase):
    def test_code_normalization_and_baostock_symbol(self) -> None:
        self.assertEqual(normalize_stock_code("sh.600000"), "600000")
        self.assertEqual(normalize_stock_code("1.0"), "000001")
        self.assertEqual(baostock_symbol("600000"), "sh.600000")
        self.assertEqual(baostock_symbol("000001"), "sz.000001")
        self.assertEqual(baostock_symbol("300750"), "sz.300750")

    def test_build_technical_levels_from_history(self) -> None:
        closes = [10 + index * 0.1 for index in range(130)]
        frame = make_history(closes)

        response = build_technical_levels(frame, "600000", "测试银行")
        keys = {level.key for level in response.levels}

        self.assertEqual(response.code, "600000")
        self.assertEqual(response.name, "测试银行")
        self.assertAlmostEqual(response.last_close or 0, closes[-1], places=2)
        self.assertIn("ma20", keys)
        self.assertIn("low60", keys)
        self.assertIn("boll_lower20", keys)
        self.assertIn("atr14_lower", keys)
        self.assertTrue(all(level.price > 0 for level in response.levels))

    def test_build_technical_analysis_upward_probability(self) -> None:
        closes = [10 + index * 0.08 for index in range(90)]
        frame = make_history(closes)

        response = build_technical_analysis(frame, "600000", "测试银行")
        probability_total = (
            response.upside_probability + response.downside_probability + response.sideways_probability
        )

        self.assertEqual(response.code, "600000")
        self.assertEqual(response.trend_label, "短期偏上")
        self.assertGreater(response.trend_score, 65)
        self.assertGreater(response.upside_probability, response.downside_probability)
        self.assertAlmostEqual(probability_total, 100, delta=0.2)
        self.assertGreater(len(response.support_levels), 0)
        self.assertGreater(len(response.resistance_levels), 0)
        self.assertGreater(len(response.signals), 0)
        self.assertNotIn("买入", response.summary)
        self.assertNotIn("卖出", response.summary)

    def test_build_technical_analysis_detects_bullish_engulfing(self) -> None:
        closes = [10 + index * 0.05 for index in range(70)]
        frame = make_history(closes)
        frame.loc[68, ["open", "high", "low", "close", "volume", "amount"]] = [
            13.8,
            14.0,
            13.1,
            13.3,
            1_000_000,
            13.3 * 1_000_000,
        ]
        frame.loc[69, ["open", "high", "low", "close", "volume", "amount"]] = [
            13.2,
            14.2,
            13.0,
            14.05,
            1_600_000,
            14.05 * 1_600_000,
        ]

        response = build_technical_analysis(frame, "600000", "测试银行")
        pattern_keys = {pattern.key for pattern in response.patterns}

        self.assertIn("bullish_engulfing", pattern_keys)
        self.assertTrue(any(pattern.direction == "bullish" for pattern in response.patterns))

    def test_build_kline_scenario_uses_historical_bands(self) -> None:
        closes = [10 + index * 0.03 for index in range(180)]
        frame = make_history(closes)

        response = build_kline_scenario(frame, "600000", "测试银行")
        horizons = {band.horizon_days for band in response.scenario_bands}

        self.assertEqual(response.code, "600000")
        self.assertEqual(response.lookback_days, 180)
        self.assertIn(5, horizons)
        self.assertIn(20, horizons)
        self.assertGreater(len(response.sequence_signals), 0)
        self.assertGreater(len(response.support_levels), 0)
        self.assertNotIn("买入", response.summary)
        self.assertNotIn("卖出", response.summary)
        self.assertIn("历史K线分位", response.summary)

    def test_build_kline_scenario_short_history_reports_gap(self) -> None:
        frame = make_history([10, 10.1, 10.2, 10.15, 10.3])

        response = build_kline_scenario(frame, "600000", "测试银行")

        self.assertEqual(response.lookback_days, 5)
        self.assertEqual(response.scenario_bands, [])
        self.assertIn("历史K线少于30个交易日", response.data_gaps)
        self.assertEqual(response.last_close, 10.3)


if __name__ == "__main__":
    unittest.main()
