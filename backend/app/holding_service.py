from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pandas as pd

from .ai_service import _chat_completion, _extract_json_object, ai_configured
from .data_service import ensure_financial_metrics_for_codes, load_stock_pool
from .models import (
    HoldingAnalysisItem,
    HoldingAnalysisResponse,
    HoldingItem,
    HoldingPlanLevel,
    ScreenResponse,
    TechnicalAnalysisResponse,
)
from .scoring import run_screen
from .storage import load_config, load_status, utc_now_iso
from .technical import calculate_technical_analysis, normalize_stock_code


ALLOWED_HOLDING_PRIORITIES = {"增强跟踪", "继续观察", "降低暴露", "等待数据"}
FACTUAL_HOLDING_FIELDS = {
    "code",
    "name",
    "holding_period",
    "cost_price",
    "quantity",
    "last_price",
    "last_price_source",
    "position_value",
    "unrealized_profit",
    "unrealized_profit_pct",
}


def normalize_holding(item: HoldingItem) -> HoldingItem:
    code = normalize_stock_code(item.code)
    holding_id = item.id or f"{code}-{uuid.uuid4().hex[:8]}"
    period = item.holding_period if item.holding_period in {"short", "long"} else "short"
    return item.model_copy(update={"id": holding_id, "code": code, "holding_period": period})


def _safe_float(value: Any, default: float = 0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _market_price(row: dict[str, Any]) -> float | None:
    price = _safe_float(row.get("current_price"), float("nan"))
    return round(price, 3) if pd.notna(price) and price > 0 else None


def _market_price_source(row: dict[str, Any]) -> str | None:
    if _market_price(row) is None:
        return None
    try:
        source = load_status().source
    except Exception:
        source = ""
    if source and source != "none":
        return f"{source} 行情 current_price 字段"
    return "本地股票池 current_price 字段"


def _stock_row(code: str) -> dict[str, Any]:
    frame = load_stock_pool()
    if frame.empty:
        return {}
    matched = frame[frame["code"] == normalize_stock_code(code)]
    if matched.empty:
        return {}
    return matched.iloc[0].to_dict()


def _screen_result_map() -> dict[str, Any]:
    try:
        results = run_screen(load_stock_pool(), load_config())
    except Exception:
        return {}
    return {item.code: item for item in results.results}


def _technical_context(code: str, name: str) -> TechnicalAnalysisResponse | None:
    try:
        return calculate_technical_analysis(code, name)
    except Exception:
        return None


def _nearest_support(technical: TechnicalAnalysisResponse | None, current_price: float | None) -> float | None:
    if technical and technical.support_levels:
        return technical.support_levels[0].price
    return None


def _nearest_resistance(technical: TechnicalAnalysisResponse | None, current_price: float | None) -> float | None:
    if technical and technical.resistance_levels:
        return technical.resistance_levels[0].price
    return None


def _price_zone(price: float | None, pct: float = 0.012) -> str:
    if price is None:
        return ""
    low = price * (1 - pct)
    high = price * (1 + pct)
    return f"{low:.2f}-{high:.2f}"


def _holding_data_gaps(row: dict[str, Any], technical: TechnicalAnalysisResponse | None) -> list[str]:
    gaps: list[str] = []
    if _market_price(row) is None:
        gaps.append("最新行情价")
    for key, label in {
        "pe": "PE",
        "pb": "PB",
        "dividend_yield": "股息率",
        "roe": "ROE",
        "revenue_growth": "营收增长",
        "profit_growth": "利润增长",
        "cashflow_ratio": "现金流比",
        "main_net_inflow": "资金流",
    }.items():
        if row.get(key) in (None, "") or pd.isna(row.get(key)):
            gaps.append(label)
    if technical is None:
        gaps.append("技术价位")
    return gaps[:8]


def _local_holding_analysis(holding: HoldingItem, screen_result: Any | None = None) -> HoldingAnalysisItem:
    row = _stock_row(holding.code)
    name = holding.name or str(row.get("name") or holding.code)
    technical = _technical_context(holding.code, name)
    last_price = _market_price(row)
    last_price_source = _market_price_source(row)
    quantity = max(0, _safe_float(holding.quantity))
    cost_price = max(0.01, _safe_float(holding.cost_price))
    position_value = round(last_price * quantity, 2) if last_price is not None and quantity > 0 else None
    unrealized_profit = round((last_price - cost_price) * quantity, 2) if last_price is not None and quantity > 0 else None
    unrealized_profit_pct = round((last_price - cost_price) / cost_price * 100, 2) if last_price is not None else None
    support = _nearest_support(technical, last_price)
    resistance = _nearest_resistance(technical, last_price)
    trend_score = technical.trend_score if technical else 50
    upside = technical.upside_probability if technical else 33.3
    downside = technical.downside_probability if technical else 33.3
    valuation_score = screen_result.score.valuation if screen_result else 50
    quality_score = screen_result.score.quality if screen_result else 50
    sector_heat = screen_result.score.sector_heat if screen_result else 50
    fund_score = _safe_float(row.get("fund_validation_score"), 50)
    profit_pct = unrealized_profit_pct

    if holding.holding_period == "short":
        if trend_score >= 65 and downside < 30:
            priority = "增强跟踪"
        elif trend_score <= 35 or downside >= 42:
            priority = "降低暴露"
        else:
            priority = "继续观察"
        add_price = support
        trim_price = resistance
        invalid_price = support
        action_points = [
            "短线以技术结构为主，关注 30 天内是否能维持在关键支撑上方。",
            "若靠近支撑区后止跌并放量修复，可作为加仓观察条件；若跌破支撑区，应重新评估短线计划。",
            "若接近压力区且量能衰减，可作为获利减仓观察条件。",
        ]
        short_view = technical.summary if technical else "暂无足够技术数据，短线只做观察。"
        long_view = "短线持仓暂不以 2-10 年逻辑决策，仍需看长期质量和估值是否匹配。"
    else:
        profit_control_score = 50 if profit_pct is None else max(0, 100 - max(0, profit_pct))
        long_score = quality_score * 0.35 + valuation_score * 0.25 + sector_heat * 0.15 + fund_score * 0.10 + profit_control_score * 0.15
        if long_score >= 68 and valuation_score >= 45:
            priority = "增强跟踪"
        elif valuation_score < 35 or quality_score < 35:
            priority = "降低暴露"
        else:
            priority = "继续观察"
        add_price = min(filter(None, [support, cost_price * 0.92]), default=None)
        trim_price = max(filter(None, [resistance, cost_price * 1.35]), default=None)
        invalid_price = min(filter(None, [support, cost_price * 0.82]), default=None)
        action_points = [
            "长线以商业质量、估值纪律和分红/现金流持续性为主，短期波动只作为执行参考。",
            "若估值回到可接受区间且基本面评分未恶化，可作为长期加仓观察条件。",
            "若价格远高于成本且估值纪律转弱，可考虑分批兑现部分浮盈以控制回撤。",
        ]
        short_view = technical.summary if technical else "短线技术数据不足，暂不做 30 天强判断。"
        long_view = (
            f"长期复核分位：质量 {quality_score:.1f}、估值纪律 {valuation_score:.1f}、板块热度 {sector_heat:.1f}。"
            "适合继续跟踪基本面兑现与估值是否匹配。"
        )
    if last_price is None:
        priority = "等待数据"

    plan_levels = [
        HoldingPlanLevel(
            label="加仓观察区",
            price=round(add_price, 2) if add_price else None,
            zone=_price_zone(add_price),
            reason="参考成本、支撑位、估值纪律和持仓周期生成。",
            condition="仅在趋势/基本面没有恶化且风险可承受时复核，不是自动加仓指令。",
        ),
        HoldingPlanLevel(
            label="获利减仓观察区",
            price=round(trim_price, 2) if trim_price else None,
            zone=_price_zone(trim_price),
            reason="参考上方压力、成本收益比和估值风险生成。",
            condition="若靠近该区间且量能转弱、估值偏热或浮盈回撤压力增大，可复核减仓计划。",
        ),
        HoldingPlanLevel(
            label="风险复核位",
            price=round(invalid_price, 2) if invalid_price else None,
            zone=_price_zone(invalid_price),
            reason="参考关键支撑和持仓周期的失效阈值生成。",
            condition="跌破后不代表立即卖出，但应重新评估原持仓理由是否仍成立。",
        ),
    ]

    risk_flags = []
    if profit_pct is not None and profit_pct >= 25:
        risk_flags.append("已有较高浮盈，需防止盈利回撤吞噬计划收益。")
    if profit_pct is not None and profit_pct <= -12:
        risk_flags.append("浮亏较明显，需确认原持仓逻辑是否被破坏。")
    if last_price is None:
        risk_flags.append("缺少最新行情价，暂不计算浮盈亏和持仓市值。")
    if valuation_score < 45:
        risk_flags.append("估值纪律偏弱，不宜只因下跌而机械加仓。")
    if fund_score < 45:
        risk_flags.append("资金验证偏弱，短线需警惕反弹持续性。")
    if not risk_flags:
        risk_flags.append("未发现单一极端风险，仍需结合公告、财报和市场环境复核。")

    confidence_base = 42 + (trend_score - 50) * 0.15 + (valuation_score - 50) * 0.12 + (quality_score - 50) * 0.1
    confidence = max(20, min(88, confidence_base + max(0, 6 - len(_holding_data_gaps(row, technical))) * 4))
    if last_price is None:
        confidence = min(confidence, 52)
    period_text = "短线30天内" if holding.holding_period == "short" else "长线2-10年"
    if profit_pct is None:
        summary = (
            f"{name}缺少最新行情价，暂不计算浮盈亏，周期为{period_text}。"
            f"当前归为“{priority}”，需先补齐真实行情价，再复核支撑/压力、估值纪律和原持仓理由。"
        )
    else:
        summary = (
            f"{name}当前浮盈亏 {profit_pct:.2f}%，周期为{period_text}。"
            f"当前归为“{priority}”，核心看支撑/压力、估值纪律和原持仓理由是否继续成立。"
        )

    return HoldingAnalysisItem(
        id=holding.id,
        code=holding.code,
        name=name,
        holding_period=holding.holding_period,
        cost_price=cost_price,
        quantity=quantity,
        last_price=last_price,
        last_price_source=last_price_source,
        position_value=position_value,
        unrealized_profit=unrealized_profit,
        unrealized_profit_pct=unrealized_profit_pct,
        priority=priority,
        confidence=round(confidence, 1),
        summary=summary,
        plan_levels=plan_levels,
        action_points=action_points,
        risk_flags=risk_flags[:5],
        short_term_view=short_view,
        long_term_view=long_view,
        data_gaps=_holding_data_gaps(row, technical),
    )


def _holding_prompt(payload: list[dict[str, Any]]) -> str:
    return f"""
你是谨慎的 A 股持仓研究复核助手。请基于输入 JSON 对持仓做条件化盯盘计划复核。

硬性规则：
1. 不得输出“必须买入/卖出/加仓/减仓”、不得给仓位比例、不得承诺收益。
2. 可以输出条件化观察区：加仓观察区、获利减仓观察区、风险复核位、继续持有条件。
3. 短线周期只讨论 30 天内技术结构和风险；长线周期只讨论 2-10 年质量、估值、分红和回撤管理。
4. last_price/current_price 只代表输入中的真实行情价；如果为 null，必须写入 data_gaps，不得用 technical.last_close、支撑压力或估算值替代市价/浮盈亏。
5. technical.kline_last_close_reference 只是 K 线收盘参考，可用于技术结构语境，不能当作当前市价。
6. local_baseline.plan_levels 的价格、区间、理由和条件由本地规则生成，不要改写；如需补充，只能写入 action_points 或 risk_flags。
7. 价格只能使用输入中的 cost_price、last_price/current_price、technical/support/resistance 或 local_baseline.plan_levels，不得编造新闻和财报。
8. 输出必须是严格 JSON，不要 Markdown。

输出格式：
{{
  "analyses": [
    {{
      "id": "id",
      "code": "600519",
      "name": "贵州茅台",
      "priority": "增强跟踪|继续观察|降低暴露|等待数据",
      "confidence": 0-100,
      "summary": "100字以内",
      "plan_levels": [
        {{"label": "加仓观察区|获利减仓观察区|风险复核位", "price": 0|null, "zone": "0-0", "reason": "依据", "condition": "触发条件"}}
      ],
      "action_points": ["条件化观察点"],
      "risk_flags": ["风险"],
      "short_term_view": "短线观点",
      "long_term_view": "长线观点",
      "data_gaps": ["缺失字段"],
      "research_only_note": "仅用于持仓研究观察，不构成投资建议。"
    }}
  ]
}}

输入 JSON：
{json.dumps(payload, ensure_ascii=False)}
"""


def _holding_payload(holding: HoldingItem, fallback: HoldingAnalysisItem, screen_result: Any | None) -> dict[str, Any]:
    row = _stock_row(holding.code)
    technical = _technical_context(holding.code, fallback.name)
    return {
        "holding": holding.model_dump(mode="json"),
        "market": {
            "name": fallback.name,
            "last_price": fallback.last_price,
            "current_price": fallback.last_price,
            "current_price_source": fallback.last_price_source,
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "pct_change": row.get("pct_change"),
            "pe": row.get("pe"),
            "pb": row.get("pb"),
            "dividend_yield": row.get("dividend_yield"),
            "roe": row.get("roe"),
            "revenue_growth": row.get("revenue_growth"),
            "profit_growth": row.get("profit_growth"),
            "cashflow_ratio": row.get("cashflow_ratio"),
            "dividend_payout_ratio": row.get("dividend_payout_ratio"),
            "revenue": row.get("revenue"),
            "net_profit": row.get("net_profit"),
            "main_net_inflow": row.get("main_net_inflow"),
            "fund_flow_source": row.get("fund_flow_source"),
        },
        "screen": None
        if screen_result is None
        else {
            "total_score": screen_result.total_score,
            "scores": screen_result.score.model_dump(),
            "reasons": screen_result.reasons,
            "risks": screen_result.risks,
        },
        "technical": None
        if technical is None
        else {
            "trend_label": technical.trend_label,
            "kline_last_close_reference": technical.last_close,
            "kline_trade_date": technical.trade_date,
            "kline_price_note": "K 线最后收盘价不是当前行情价，不可用于市价或浮盈亏计算。",
            "trend_score": technical.trend_score,
            "upside_probability": technical.upside_probability,
            "downside_probability": technical.downside_probability,
            "support_levels": [level.model_dump(mode="json") for level in technical.support_levels[:4]],
            "resistance_levels": [level.model_dump(mode="json") for level in technical.resistance_levels[:4]],
            "patterns": [pattern.model_dump(mode="json") for pattern in technical.patterns[:3]],
        },
        "local_baseline": fallback.model_dump(mode="json"),
}


def _merge_unique_gaps(fallback: HoldingAnalysisItem, raw_gaps: Any) -> list[str]:
    merged: list[str] = []
    for gap in fallback.data_gaps:
        if gap and gap not in merged:
            merged.append(gap)
    if isinstance(raw_gaps, list):
        for gap in raw_gaps:
            text = str(gap).strip()
            if text and text not in merged:
                merged.append(text)
    return merged[:10]


def _merge_ai_holding(raw: dict[str, Any], fallbacks: dict[str, HoldingAnalysisItem]) -> list[HoldingAnalysisItem]:
    raw_items = raw if isinstance(raw, list) else raw.get("analyses", [])
    if not isinstance(raw_items, list):
        return list(fallbacks.values())
    merged_items: dict[str, HoldingAnalysisItem] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        holding_id = str(item.get("id") or "")
        fallback = fallbacks.get(holding_id)
        if fallback is None:
            continue
        merged = {**fallback.model_dump(mode="json"), **item, "id": holding_id}
        for field in FACTUAL_HOLDING_FIELDS:
            merged[field] = getattr(fallback, field)
        merged["data_gaps"] = _merge_unique_gaps(fallback, item.get("data_gaps"))
        merged["plan_levels"] = [level.model_dump(mode="json") for level in fallback.plan_levels]
        if merged.get("priority") not in ALLOWED_HOLDING_PRIORITIES:
            merged["priority"] = fallback.priority
        try:
            merged_items[holding_id] = HoldingAnalysisItem.model_validate(merged)
        except Exception:
            merged_items[holding_id] = fallback
    for holding_id, fallback in fallbacks.items():
        merged_items.setdefault(holding_id, fallback)
    return list(merged_items.values())


async def analyze_holdings(holdings: list[HoldingItem]) -> HoldingAnalysisResponse:
    normalized = [normalize_holding(item) for item in holdings if item.code and item.cost_price > 0]
    if normalized:
        await asyncio.to_thread(ensure_financial_metrics_for_codes, [holding.code for holding in normalized])

    screen_map = _screen_result_map()
    fallbacks: dict[str, HoldingAnalysisItem] = {}
    for holding in normalized:
        fallbacks[holding.id] = _local_holding_analysis(holding, screen_map.get(holding.code))

    if not normalized:
        return HoldingAnalysisResponse(generated_at=utc_now_iso(), ok=True, message="暂无持仓可分析")

    if not ai_configured():
        return HoldingAnalysisResponse(
            generated_at=utc_now_iso(),
            ok=False,
            message="未配置 AI_API_KEY，已返回本地规则持仓复核结果",
            analyses=list(fallbacks.values()),
        )

    payload = [_holding_payload(holding, fallbacks[holding.id], screen_map.get(holding.code)) for holding in normalized]
    messages = [
        {
            "role": "system",
            "content": "你是谨慎、客观的持仓研究复核助手，只输出严格 json，不输出交易指令。",
        },
        {"role": "user", "content": _holding_prompt(payload)},
    ]
    try:
        content = await _chat_completion(messages, json_mode=True, timeout=90)
        raw = _extract_json_object(content)
        analyses = _merge_ai_holding(raw, fallbacks)
        return HoldingAnalysisResponse(
            generated_at=utc_now_iso(),
            ok=True,
            message=f"持仓 AI 复核完成：{len(analyses)} 条",
            analyses=analyses,
        )
    except Exception as exc:
        return HoldingAnalysisResponse(
            generated_at=utc_now_iso(),
            ok=False,
            message=f"AI 接口暂不可用，已返回本地规则持仓复核结果：{exc}",
            analyses=list(fallbacks.values()),
        )
