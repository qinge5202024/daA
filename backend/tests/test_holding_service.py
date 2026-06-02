from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from backend.app.holding_service import analyze_holdings
from backend.app.models import DataStatus, HoldingItem, TechnicalAnalysisResponse, TechnicalLevel


def fake_technical() -> TechnicalAnalysisResponse:
    return TechnicalAnalysisResponse(
        code="600519",
        name="贵州茅台",
        generated_at="2026-05-26T00:00:00+08:00",
        trade_date="2026-05-25",
        last_close=1450,
        trend_label="短期震荡",
        trend_score=58,
        upside_probability=38,
        downside_probability=28,
        sideways_probability=34,
        summary="短期震荡，上下方均有关键位需要观察。",
        support_levels=[
            TechnicalLevel(key="ma60", label="MA60", price=1380, distance_pct=-4.8, basis="60日均线", position="下方")
        ],
        resistance_levels=[
            TechnicalLevel(key="high60", label="60日高点", price=1550, distance_pct=6.9, basis="60日高点", position="上方")
        ],
        patterns=[],
        signals=[],
        risks=["短期震荡风险"],
    )


class HoldingServiceTests(unittest.TestCase):
    def test_short_holding_generates_price_plan_without_ai(self) -> None:
        holding = HoldingItem(code="600519", name="贵州茅台", cost_price=1300, quantity=100, holding_period="short")
        with patch.dict("os.environ", {}, clear=True), patch(
            "backend.app.holding_service._technical_context", return_value=fake_technical()
        ), patch(
            "backend.app.holding_service._stock_row",
            return_value={"name": "贵州茅台", "pe": 28, "current_price": 1420},
        ), patch("backend.app.holding_service.load_status", return_value=DataStatus(source="test_quote")), patch(
            "backend.app.holding_service._screen_result_map", return_value={}
        ), patch("backend.app.holding_service.ensure_financial_metrics_for_codes") as ensure_metrics:
            response = asyncio.run(analyze_holdings([holding]))

        ensure_metrics.assert_called_once_with(["600519"])
        self.assertFalse(response.ok)
        self.assertEqual(len(response.analyses), 1)
        analysis = response.analyses[0]
        self.assertEqual(analysis.code, "600519")
        self.assertEqual(analysis.last_price, 1420)
        self.assertEqual(analysis.last_price_source, "test_quote 行情 current_price 字段")
        self.assertAlmostEqual(analysis.unrealized_profit_pct or 0, 9.23, places=2)
        labels = {level.label for level in analysis.plan_levels}
        self.assertIn("加仓观察区", labels)
        self.assertIn("获利减仓观察区", labels)
        self.assertIn("风险复核位", labels)
        self.assertIn("不构成投资建议", analysis.research_only_note)

    def test_technical_last_close_is_not_used_as_market_price(self) -> None:
        holding = HoldingItem(code="600519", name="贵州茅台", cost_price=1300, quantity=100, holding_period="short")
        with patch.dict("os.environ", {}, clear=True), patch(
            "backend.app.holding_service._technical_context", return_value=fake_technical()
        ), patch("backend.app.holding_service._stock_row", return_value={"name": "贵州茅台", "pe": 28}), patch(
            "backend.app.holding_service._screen_result_map", return_value={}
        ), patch("backend.app.holding_service.ensure_financial_metrics_for_codes"):
            response = asyncio.run(analyze_holdings([holding]))

        analysis = response.analyses[0]
        self.assertIsNone(analysis.last_price)
        self.assertIsNone(analysis.last_price_source)
        self.assertIsNone(analysis.position_value)
        self.assertIsNone(analysis.unrealized_profit)
        self.assertIsNone(analysis.unrealized_profit_pct)
        self.assertEqual(analysis.priority, "等待数据")
        self.assertIn("最新行情价", analysis.data_gaps)
        self.assertIn("缺少最新行情价", analysis.summary)
        self.assertTrue(any("缺少最新行情价" in flag for flag in analysis.risk_flags))


if __name__ == "__main__":
    unittest.main()
