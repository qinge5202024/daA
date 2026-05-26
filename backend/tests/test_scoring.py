from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from backend.app.data_service import standardize_frame
from backend.app.models import AppConfig
from backend.app.scoring import _percent_rank, build_hot_sectors, run_screen


ROOT = Path(__file__).resolve().parents[2]


class ScoringTests(unittest.TestCase):
    def load_sample(self) -> pd.DataFrame:
        raw = pd.read_csv(ROOT / "data" / "sample_stocks.csv", dtype={"代码": str})
        return standardize_frame(raw)

    def test_csv_field_mapping_and_missing_values(self) -> None:
        frame = self.load_sample()
        self.assertIn("code", frame.columns)
        self.assertIn("market_cap", frame.columns)
        self.assertEqual(frame.iloc[0]["code"], "300750")
        self.assertGreater(frame.iloc[0]["market_cap"], 0)

    def test_screen_generates_ranked_results(self) -> None:
        results = run_screen(self.load_sample(), AppConfig())
        self.assertGreater(results.total_candidates, 0)
        self.assertGreater(len(results.results), 0)
        scores = [item.total_score for item in results.results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(results.results[0].reasons)

    def test_sunset_industry_exclusion_penalty(self) -> None:
        config = AppConfig(sunset_industries=["房地产开发"])
        results = run_screen(self.load_sample(), config)
        real_estate = [item for item in results.results if item.industry == "房地产开发"]
        self.assertFalse(real_estate)

    def test_valuation_bubble_flag(self) -> None:
        results = run_screen(self.load_sample(), AppConfig(thresholds={"min_total_score": 0, "max_results": 99}))
        smic = next(item for item in results.results if item.code == "688981")
        self.assertTrue(any("估值" in risk for risk in smic.risks))

    def test_percent_rank_rewards_larger_values(self) -> None:
        scores = _percent_rank(pd.Series([1, 2, 3]), higher_is_better=True)
        self.assertLess(scores.iloc[0], scores.iloc[2])

    def test_hot_sector_tracking_and_fund_validation(self) -> None:
        frame = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["300001", "300002", "600001", "600002"],
                    "名称": ["强势科技", "科技龙二", "弱势消费", "消费龙二"],
                    "板块": ["科技", "科技", "消费", "消费"],
                    "行业": ["科技", "科技", "消费", "消费"],
                    "总市值": [200_000_000_000, 90_000_000_000, 120_000_000_000, 80_000_000_000],
                    "成交额": [8_000_000_000, 5_000_000_000, 2_000_000_000, 1_500_000_000],
                    "涨跌幅": [6.5, 4.2, -0.6, 0.2],
                    "量比": [2.2, 1.8, 0.8, 0.7],
                    "主力净流入": [900_000_000, 500_000_000, -120_000_000, -80_000_000],
                    "主力净占比": [8.0, 5.4, -3.2, -2.1],
                    "板块主力净流入": [1_400_000_000, 1_400_000_000, -200_000_000, -200_000_000],
                    "板块主力净占比": [10.7, 10.7, -5.7, -5.7],
                }
            )
        )

        hot = build_hot_sectors(frame)

        self.assertEqual(hot.sectors[0].sector, "科技")
        self.assertEqual(hot.sectors[0].fund_validation, "主力资金强验证")
        self.assertGreater(hot.sectors[0].main_net_inflow or 0, 0)
        self.assertTrue(hot.sectors[0].leaders)

    def test_screen_includes_fund_validation_metrics(self) -> None:
        frame = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["300001", "300002", "600001", "600002"],
                    "名称": ["强势科技", "科技龙二", "弱势消费", "消费龙二"],
                    "板块": ["科技", "科技", "消费", "消费"],
                    "行业": ["科技", "科技", "消费", "消费"],
                    "总市值": [200_000_000_000, 90_000_000_000, 120_000_000_000, 80_000_000_000],
                    "成交额": [8_000_000_000, 5_000_000_000, 2_000_000_000, 1_500_000_000],
                    "涨跌幅": [6.5, 4.2, -0.6, 0.2],
                    "量比": [2.2, 1.8, 0.8, 0.7],
                    "市盈率": [22, 24, 18, 16],
                    "市净率": [3, 3.2, 2, 1.8],
                    "主力净流入": [900_000_000, 500_000_000, -120_000_000, -80_000_000],
                    "主力净占比": [8.0, 5.4, -3.2, -2.1],
                }
            )
        )

        results = run_screen(frame, AppConfig(thresholds={"min_total_score": 0, "max_results": 10}))
        first = next(item for item in results.results if item.code == "300001")

        self.assertIn("fund_validation", first.metrics)
        self.assertIn("fund_validation_score", first.metrics)
        self.assertGreater(float(first.metrics["fund_validation_score"] or 0), 70)

    def test_proxy_fund_flow_uses_net_amount_labels(self) -> None:
        frame = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["300001", "300002", "600001", "600002"],
                    "名称": ["强势科技", "科技龙二", "弱势消费", "消费龙二"],
                    "板块": ["科技", "科技", "消费", "消费"],
                    "行业": ["科技", "科技", "消费", "消费"],
                    "总市值": [200_000_000_000, 90_000_000_000, 120_000_000_000, 80_000_000_000],
                    "成交额": [8_000_000_000, 5_000_000_000, 2_000_000_000, 1_500_000_000],
                    "涨跌幅": [6.5, 4.2, -0.6, 0.2],
                    "量比": [2.2, 1.8, 0.8, 0.7],
                    "主力净流入": [900_000_000, 500_000_000, -120_000_000, -80_000_000],
                    "主力净占比": [8.0, 5.4, -3.2, -2.1],
                    "资金流来源": ["同花顺资金净额代理"] * 4,
                    "资金流说明": ["由同花顺个股资金流净额/成交额估算，非东方财富主力口径。"] * 4,
                }
            )
        )

        results = run_screen(frame, AppConfig(thresholds={"min_total_score": 0, "max_results": 10}))
        first = next(item for item in results.results if item.code == "300001")
        hot = build_hot_sectors(frame)

        self.assertIn("资金净额", str(first.metrics["fund_validation"]))
        self.assertEqual(first.metrics["fund_flow_source"], "同花顺资金净额代理")
        self.assertEqual(hot.sectors[0].fund_flow_source, "同花顺资金净额代理汇总")
        self.assertIn("资金净额", hot.sectors[0].fund_validation)


if __name__ == "__main__":
    unittest.main()
