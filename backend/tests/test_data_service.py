from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.app import data_service
from backend.app.data_service import (
    _parse_ths_page_count,
    cache_quality,
    fetch_tencent_stock_pool,
    save_stock_pool,
    standardize_frame,
)


class DataServiceTests(unittest.TestCase):
    def test_cache_quality_rejects_low_field_market_data(self) -> None:
        frame = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["600000", "000001"],
                    "名称": ["浦发银行", "平安银行"],
                    "成交额": [1000000, 2000000],
                    "涨跌幅": [1.2, -0.4],
                }
            )
        )
        quality = cache_quality(frame)
        self.assertFalse(quality["is_scoring_quality"])

    def test_cache_quality_accepts_sector_data(self) -> None:
        frame = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["600000", "000001", "600036", "601398", "000333", "600519", "300750", "002594", "600887", "601012"],
                    "名称": ["浦发银行", "平安银行", "招商银行", "工商银行", "美的集团", "贵州茅台", "宁德时代", "比亚迪", "伊利股份", "隆基绿能"],
                    "行业": ["银行", "银行", "银行", "银行", "家电", "白酒", "电池", "汽车整车", "乳制品", "电力设备"],
                    "成交额": [1000000] * 10,
                    "涨跌幅": [1.0] * 10,
                }
            )
        )
        quality = cache_quality(frame)
        self.assertTrue(quality["is_scoring_quality"])

    def test_low_quality_refresh_does_not_overwrite_existing_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "stock_pool.csv"
            backup_path = Path(directory) / "stock_pool.last_good.csv"
            existing = standardize_frame(
                pd.DataFrame(
                    {
                        "代码": [f"6000{index:02d}" for index in range(10)],
                        "名称": [f"公司{index}" for index in range(10)],
                        "行业": ["银行"] * 10,
                    }
                )
            )
            existing.to_csv(cache_path, index=False, encoding="utf-8-sig")

            low_quality = pd.DataFrame({"代码": ["600000"], "名称": ["浦发银行"], "成交额": [1000000]})

            with patch.object(data_service, "STOCK_POOL_PATH", cache_path), patch.object(
                data_service, "STOCK_POOL_BACKUP_PATH", backup_path
            ):
                with self.assertRaises(RuntimeError):
                    save_stock_pool(low_quality)

                reloaded = pd.read_csv(cache_path, dtype={"code": str})
                self.assertEqual(len(reloaded), 10)
                self.assertEqual(reloaded.iloc[0]["sector"], "银行")

    def test_preserve_existing_enrichment_uses_backup_when_current_cache_is_low_quality(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "stock_pool.csv"
            backup_path = Path(directory) / "stock_pool.last_good.csv"

            current = standardize_frame(
                pd.DataFrame({"代码": ["600000", "000001"], "名称": ["浦发银行", "平安银行"], "成交额": [1, 2]})
            )
            current.to_csv(cache_path, index=False, encoding="utf-8-sig")

            backup = standardize_frame(
                pd.DataFrame(
                    {
                        "代码": [f"6000{index:02d}" for index in range(10)],
                        "名称": [f"公司{index}" for index in range(10)],
                        "行业": ["银行"] * 10,
                        "市盈率": [10 + index for index in range(10)],
                    }
                )
            )
            backup.loc[0, "code"] = "600000"
            backup.loc[0, "name"] = "浦发银行"
            backup.to_csv(backup_path, index=False, encoding="utf-8-sig")

            fresh = standardize_frame(pd.DataFrame({"代码": ["600000"], "名称": ["浦发银行"], "涨跌幅": [1.2]}))

            with patch.object(data_service, "STOCK_POOL_PATH", cache_path), patch.object(
                data_service, "STOCK_POOL_BACKUP_PATH", backup_path
            ):
                enriched = data_service.preserve_existing_enrichment(fresh)

            self.assertEqual(enriched.iloc[0]["sector"], "银行")
            self.assertEqual(enriched.iloc[0]["pe"], 10)

    def test_ths_fund_flow_fallback_fills_missing_without_overriding_existing(self) -> None:
        base = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["600000", "000001"],
                    "名称": ["浦发银行", "平安银行"],
                    "行业": ["银行", "银行"],
                    "成交额": [100_000_000, 200_000_000],
                    "主力净流入": [123_000_000, None],
                    "资金流来源": ["东方财富主力资金", ""],
                    "资金流说明": ["东方财富公开资金流排名字段。", ""],
                }
            )
        )
        ths = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["600000", "000001"],
                    "名称": ["浦发银行", "平安银行"],
                    "主力净流入": [999_000_000, 8_000_000],
                    "主力净占比": [9.9, 4.0],
                    "资金流来源": ["同花顺资金净额代理", "同花顺资金净额代理"],
                    "资金流说明": ["由同花顺个股资金流净额/成交额估算，非东方财富主力口径。"] * 2,
                }
            )
        )[["code", "main_net_inflow", "main_net_inflow_pct", "fund_flow_source", "fund_flow_note"]]

        with (
            patch.object(data_service, "_eastmoney_stock_fund_flow_rank", side_effect=RuntimeError("blocked")),
            patch.object(data_service, "_eastmoney_sector_fund_flow_rank", return_value=pd.DataFrame()),
            patch.object(data_service, "_akshare_ths_stock_fund_flow", return_value=ths),
        ):
            enriched = data_service.enrich_with_public_fund_flow(base)

        first = enriched[enriched["code"] == "600000"].iloc[0]
        second = enriched[enriched["code"] == "000001"].iloc[0]
        self.assertEqual(first["main_net_inflow"], 123_000_000)
        self.assertEqual(first["fund_flow_source"], "东方财富主力资金")
        self.assertEqual(second["main_net_inflow"], 8_000_000)
        self.assertEqual(second["main_net_inflow_pct"], 4.0)
        self.assertEqual(second["fund_flow_source"], "同花顺资金净额代理")

    def test_financial_enrichment_fills_quality_growth_and_dividend_fields(self) -> None:
        base = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["600519", "000001"],
                    "名称": ["贵州茅台", "平安银行"],
                    "行业": ["白酒", "银行"],
                    "市盈率": [20, 5],
                }
            )
        )
        performance = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["600519", "000001"],
                    "名称": ["贵州茅台", "平安银行"],
                    "ROE": [32.5, 11.2],
                    "营收增长": [15.1, 2.8],
                    "利润增长": [18.6, 4.2],
                    "现金流": [1.35, 0.95],
                    "营业收入": [150_000_000_000, 180_000_000_000],
                    "净利润": [80_000_000_000, 45_000_000_000],
                }
            )
        )[["code", "sector", "industry", "roe", "revenue_growth", "profit_growth", "cashflow_ratio", "revenue", "net_profit"]]
        dividend = standardize_frame(
            pd.DataFrame(
                {
                    "代码": ["600519"],
                    "名称": ["贵州茅台"],
                    "股息率": [2.2],
                    "分红支付率": [42],
                }
            )
        )[["code", "dividend_yield", "dividend_payout_ratio"]]

        with patch.object(data_service, "_performance_financial_metrics", return_value=performance), patch.object(
            data_service, "_dividend_financial_metrics", return_value=dividend
        ):
            enriched = data_service.enrich_with_public_financial_metrics(base)

        maotai = enriched[enriched["code"] == "600519"].iloc[0]
        bank = enriched[enriched["code"] == "000001"].iloc[0]
        self.assertEqual(maotai["roe"], 32.5)
        self.assertEqual(maotai["revenue_growth"], 15.1)
        self.assertEqual(maotai["profit_growth"], 18.6)
        self.assertEqual(maotai["dividend_yield"], 2.2)
        self.assertEqual(maotai["dividend_payout_ratio"], 42)
        self.assertEqual(bank["roe"], 11.2)
        self.assertTrue(pd.isna(bank["dividend_yield"]))

    def test_financial_enrichment_failure_keeps_original_frame(self) -> None:
        base = standardize_frame(
            pd.DataFrame({"代码": ["600519"], "名称": ["贵州茅台"], "行业": ["白酒"], "ROE": [30]})
        )

        with patch.object(data_service, "_performance_financial_metrics", side_effect=RuntimeError("blocked")), patch.object(
            data_service, "_dividend_financial_metrics", side_effect=RuntimeError("blocked")
        ):
            enriched = data_service.enrich_with_public_financial_metrics(base)

        self.assertEqual(enriched.iloc[0]["roe"], 30)
        self.assertEqual(enriched.iloc[0]["name"], "贵州茅台")

    def test_parse_ths_page_count_defaults_to_one(self) -> None:
        self.assertEqual(_parse_ths_page_count('<span class="page_info">1/9</span>'), 9)
        self.assertEqual(_parse_ths_page_count("<html></html>"), 1)

    def test_tencent_refresh_can_use_existing_sector_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "stock_pool.csv"
            backup_path = Path(directory) / "stock_pool.last_good.csv"
            existing = standardize_frame(
                pd.DataFrame(
                    {
                        "代码": [f"6000{index:02d}" for index in range(10)],
                        "名称": [f"公司{index}" for index in range(10)],
                        "行业": ["银行"] * 10,
                    }
                )
            )
            existing.to_csv(cache_path, index=False, encoding="utf-8-sig")

            payload = (
                [
                    {
                        "code": f"sh6000{index:02d}",
                        "name": f"公司{index}",
                        "zsz": str(100 + index),
                        "turnover": "123",
                        "zdf": "1.2",
                        "lb": "1.1",
                        "pe_ttm": "8.5",
                        "pn": "0.6",
                    }
                    for index in range(10)
                ],
                10,
            )

            with patch.object(data_service, "STOCK_POOL_PATH", cache_path), patch.object(
                data_service, "STOCK_POOL_BACKUP_PATH", backup_path
            ), patch.object(data_service, "_fetch_tencent_rank_page", return_value=payload), patch.object(
                data_service, "enrich_with_public_financial_metrics", side_effect=lambda frame, codes=None: standardize_frame(frame)
            ), patch.object(data_service, "enrich_with_public_fund_flow", side_effect=standardize_frame):
                frame = fetch_tencent_stock_pool()

            self.assertTrue(cache_quality(frame)["is_scoring_quality"])
            self.assertEqual(frame.iloc[0]["sector"], "银行")
            self.assertEqual(frame.iloc[0]["market_cap"], 10_000_000_000)


if __name__ == "__main__":
    unittest.main()
