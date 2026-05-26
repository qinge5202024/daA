from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from backend.app.ai_service import analyze_watchlist
from backend.app.models import AiAnalysisRequest, ScoreBreakdown, ScreenResponse, ScreenResult


def make_screen_response() -> ScreenResponse:
    return ScreenResponse(
        generated_at="2026-05-25T00:00:00+08:00",
        total_candidates=1,
        results=[
            ScreenResult(
                code="300001",
                name="测试科技",
                sector="科技",
                industry="软件",
                total_score=78,
                score=ScoreBreakdown(
                    sector_heat=82,
                    leadership=76,
                    quality=72,
                    valuation=66,
                    dividend=45,
                    industry_risk=70,
                ),
                reasons=["板块热度靠前", "龙头地位较好"],
                risks=["估值需要复核"],
                metrics={
                    "pct_change": 3.2,
                    "pe": 28,
                    "pb": 3.1,
                    "dividend_yield": 1.2,
                    "roe": 16,
                    "revenue_growth": 18,
                    "profit_growth": 20,
                    "cashflow_ratio": 1.1,
                    "historical_pe_percentile": 52,
                    "main_net_inflow": 80_000_000,
                    "main_net_inflow_pct": 4.2,
                    "fund_validation": "资金净额强验证",
                    "fund_validation_score": 88,
                    "fund_flow_source": "同花顺资金净额代理",
                    "fund_flow_note": "由同花顺个股资金流净额/成交额估算。",
                },
            )
        ],
    )


class AiServiceTests(unittest.TestCase):
    def test_analyze_watchlist_falls_back_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            response = asyncio.run(
                analyze_watchlist(
                    make_screen_response(),
                    AiAnalysisRequest(limit=1, include_technical=False),
                )
            )

        self.assertFalse(response.ok)
        self.assertEqual(response.total_analyzed, 1)
        self.assertIn(response.analyses[0].ai_priority, {"重点观察", "条件观察", "仅跟踪板块", "暂不优先"})
        self.assertIn("代理", response.analyses[0].fund_flow_comment)
        self.assertNotIn("买入", response.analyses[0].summary)

    def test_analyze_watchlist_uses_structured_ai_json(self) -> None:
        payload = {
            "analyses": [
                {
                    "code": "300001",
                    "name": "测试科技",
                    "ai_priority": "重点观察",
                    "confidence": 81,
                    "summary": "资金和板块热度较一致，但资金口径为代理，需继续复核。",
                    "supporting_points": ["板块热度靠前"],
                    "contradictions": ["资金为同花顺代理口径"],
                    "key_price_levels": [{"label": "观察确认位", "price": None, "reason": "暂无技术价位"}],
                    "fund_flow_comment": "同花顺资金净额代理，不等同真实主力资金。",
                    "valuation_comment": "估值未明显过热。",
                    "dividend_comment": "股息率一般。",
                    "sector_position_comment": "板块内龙头评分较高。",
                    "data_gaps": ["真实主力资金口径"],
                }
            ]
        }

        async def fake_chat(*_: object, **__: object) -> str:
            return json.dumps(payload, ensure_ascii=False)

        with patch.dict("os.environ", {"AI_API_KEY": "test-key"}, clear=True), patch(
            "backend.app.ai_service._chat_completion", side_effect=fake_chat
        ):
            response = asyncio.run(
                analyze_watchlist(
                    make_screen_response(),
                    AiAnalysisRequest(limit=1, include_technical=False),
                )
            )

        self.assertTrue(response.ok)
        self.assertEqual(response.analyses[0].ai_priority, "重点观察")
        self.assertEqual(response.analyses[0].confidence, 81)
        self.assertIn("真实主力资金口径", response.analyses[0].data_gaps)


if __name__ == "__main__":
    unittest.main()
