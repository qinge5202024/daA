from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .models import (
    AiAnalysisRequest,
    AiAnalysisResponse,
    AiKeyPriceLevel,
    AiStockAnalysis,
    ScreenResponse,
    ScreenResult,
    TechnicalAnalysisResponse,
)
from .storage import utc_now_iso
from .technical import calculate_technical_analysis


DEFAULT_AI_BASE_URL = "https://api.deepseek.com"
DEFAULT_AI_MODEL = "deepseek-v4-flash"
PRIORITY_ORDER = {"重点观察": 0, "条件观察": 1, "仅跟踪板块": 2, "暂不优先": 3}
ALLOWED_PRIORITIES = set(PRIORITY_ORDER)


def ai_configured() -> bool:
    return bool(os.getenv("AI_API_KEY"))


def _ai_base_url() -> str:
    return os.getenv("AI_BASE_URL", DEFAULT_AI_BASE_URL).rstrip("/")


def _ai_model() -> str:
    return os.getenv("AI_MODEL", DEFAULT_AI_MODEL)


def _is_deepseek_v4_request(model: str) -> bool:
    return "deepseek.com" in _ai_base_url() or model.startswith("deepseek-v4")


def _fallback_remark(result: ScreenResult, reason: str) -> str:
    return f"AI 备注暂不可用：{reason}。当前量化理由：{'；'.join(result.reasons)}。"


def _request_payload(messages: list[dict[str, str]], *, json_mode: bool = False) -> dict[str, Any]:
    model = _ai_model()
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": 8192 if json_mode else 900,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
        if _is_deepseek_v4_request(model):
            payload["thinking"] = {"type": "disabled"}
    return payload


async def _chat_completion(messages: list[dict[str, str]], *, json_mode: bool = False, timeout: int = 60) -> str:
    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        raise RuntimeError("未配置 AI_API_KEY")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{_ai_base_url()}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=_request_payload(messages, json_mode=json_mode),
        )
        response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()


async def generate_remark(result: ScreenResult) -> str:
    if not ai_configured():
        return _fallback_remark(result, "未配置 AI_API_KEY")

    prompt = f"""
你是一个谨慎的 A 股研究助理。请基于下面的量化筛选结果，生成一段简洁中文备注。
要求：
1. 只做研究观察，不给买入、卖出、仓位建议。
2. 包含入选理由、主要风险、估值泡沫提醒、分红持续性判断、行业趋势提示。
3. 不超过 180 字。

股票：{result.code} {result.name}
行业/板块：{result.industry} / {result.sector}
综合评分：{result.total_score}
分项评分：{result.score.model_dump()}
指标：{result.metrics}
量化理由：{result.reasons}
风险：{result.risks}
"""

    try:
        return await _chat_completion(
            [
                {"role": "system", "content": "你是谨慎、客观、避免投资建议的股票研究摘要助手。"},
                {"role": "user", "content": prompt},
            ],
            timeout=30,
        )
    except Exception as exc:
        return _fallback_remark(result, str(exc))


def _safe_float(value: Any, default: float = 0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _missing_metrics(result: ScreenResult) -> list[str]:
    required = {
        "pe": "PE",
        "pb": "PB",
        "dividend_yield": "股息率",
        "roe": "ROE",
        "revenue_growth": "营收增长",
        "profit_growth": "利润增长",
        "cashflow_ratio": "现金流比",
        "main_net_inflow": "资金流",
        "historical_pe_percentile": "历史PE分位",
    }
    gaps = [label for key, label in required.items() if result.metrics.get(key) in (None, "")]
    if str(result.metrics.get("fund_flow_source") or "").find("代理") >= 0:
        gaps.append("真实主力资金口径")
    return gaps[:8]


def _local_priority(result: ScreenResult, contradictions: list[str]) -> str:
    fund_score = _safe_float(result.metrics.get("fund_validation_score"), 50)
    valuation = result.score.valuation
    sector_heat = result.score.sector_heat
    leadership = result.score.leadership
    quality = result.score.quality

    if result.total_score >= 75 and fund_score >= 70 and valuation >= 55 and len(contradictions) <= 1:
        return "重点观察"
    if result.total_score >= 62 and leadership >= 55 and quality >= 50 and valuation >= 40:
        return "条件观察"
    if sector_heat >= 70 and (leadership < 55 or quality < 50):
        return "仅跟踪板块"
    return "暂不优先"


def _local_contradictions(result: ScreenResult) -> list[str]:
    contradictions: list[str] = []
    metrics = result.metrics
    fund_score = _safe_float(metrics.get("fund_validation_score"), 50)
    pct_change = _safe_float(metrics.get("pct_change"))
    flow = _safe_float(metrics.get("main_net_inflow"), 0)
    pe = _safe_float(metrics.get("pe"))
    historical_pe = _safe_float(metrics.get("historical_pe_percentile"))
    cashflow = _safe_float(metrics.get("cashflow_ratio"))
    dividend = _safe_float(metrics.get("dividend_yield"))
    profit_growth = _safe_float(metrics.get("profit_growth"))

    if result.score.sector_heat >= 70 and fund_score < 50:
        contradictions.append("板块热度较高，但资金验证偏弱，需要确认热度是否只停留在板块层面。")
    if pct_change > 2 and flow < 0:
        contradictions.append("价格上涨但资金净额流出，存在量价资金背离。")
    if result.score.valuation < 45 or pe >= 60 or historical_pe >= 80:
        contradictions.append("估值纪律评分偏低，可能存在估值过热或历史分位偏高。")
    if dividend >= 3 and (cashflow <= 0 or profit_growth < 0):
        contradictions.append("股息率有吸引力，但现金流或利润增长不足，分红持续性需复核。")
    if result.score.leadership < 55:
        contradictions.append("板块内龙头地位不够突出，可能只是跟随板块波动。")
    if not contradictions:
        contradictions.append("暂未发现明显量化反证，但仍需结合公告、财报和行业变化人工复核。")
    return contradictions[:5]


def _local_supporting_points(result: ScreenResult) -> list[str]:
    points = list(result.reasons[:4])
    fund_validation = str(result.metrics.get("fund_validation") or "")
    if fund_validation and fund_validation != "暂无资金流字段":
        points.append(f"资金验证结论为“{fund_validation}”。")
    if result.score.leadership >= 70:
        points.append("板块内龙头地位评分靠前。")
    if result.score.valuation >= 70:
        points.append("估值纪律评分较好，暂未显示明显过热。")
    return points[:6]


def _local_key_levels(technical: TechnicalAnalysisResponse | None) -> list[AiKeyPriceLevel]:
    if technical is None:
        return [
            AiKeyPriceLevel(label="观察确认位", price=None, reason="暂无技术价位数据，需先打开个股详情加载技术分析。"),
            AiKeyPriceLevel(label="失效观察位", price=None, reason="暂无技术价位数据，暂不生成具体价格。"),
        ]

    levels: list[AiKeyPriceLevel] = []
    if technical.support_levels:
        support = technical.support_levels[0]
        levels.append(AiKeyPriceLevel(label="支撑位", price=support.price, reason=support.basis))
        levels.append(
            AiKeyPriceLevel(label="失效观察位", price=support.price, reason=f"跌破{support.label}后需重新评估短线结构。")
        )
    if technical.resistance_levels:
        resistance = technical.resistance_levels[0]
        levels.append(AiKeyPriceLevel(label="压力位", price=resistance.price, reason=resistance.basis))
        levels.append(
            AiKeyPriceLevel(label="观察确认位", price=resistance.price, reason=f"放量站上{resistance.label}可作为强弱验证。")
        )
    return levels[:4]


def _local_analysis(result: ScreenResult, technical: TechnicalAnalysisResponse | None = None) -> AiStockAnalysis:
    contradictions = _local_contradictions(result)
    data_gaps = _missing_metrics(result)
    priority = _local_priority(result, contradictions)
    fund_score = _safe_float(result.metrics.get("fund_validation_score"), 50)
    data_quality = max(20, 100 - len(data_gaps) * 8)
    consensus = (result.total_score * 0.45 + fund_score * 0.20 + result.score.valuation * 0.15 + result.score.quality * 0.20)
    confidence = max(20, min(92, consensus * 0.72 + data_quality * 0.28 - max(0, len(contradictions) - 1) * 6))
    fund_source = str(result.metrics.get("fund_flow_source") or "未补充")
    proxy_note = "该资金字段为代理口径，不等同真实主力资金。" if "代理" in fund_source or "同花顺" in fund_source else ""
    technical_text = f"技术面显示{technical.trend_label}。" if technical else "技术价位尚未纳入本次复核。"

    return AiStockAnalysis(
        code=result.code,
        name=result.name,
        ai_priority=priority,
        confidence=round(confidence, 1),
        summary=f"{result.name}当前归为“{priority}”。综合评分 {result.total_score}，{technical_text} {proxy_note}".strip(),
        supporting_points=_local_supporting_points(result),
        contradictions=contradictions,
        key_price_levels=_local_key_levels(technical),
        fund_flow_comment=f"资金口径：{fund_source}；资金验证：{result.metrics.get('fund_validation') or '暂无'}。",
        valuation_comment=f"估值纪律评分 {result.score.valuation}，PE {result.metrics.get('pe') if result.metrics.get('pe') is not None else '缺失'}。",
        dividend_comment=f"股息率 {result.metrics.get('dividend_yield') if result.metrics.get('dividend_yield') is not None else '缺失'}，分红持续性仍需结合现金流复核。",
        sector_position_comment=f"所属板块 {result.sector}，板块热度评分 {result.score.sector_heat}，龙头地位评分 {result.score.leadership}。",
        data_gaps=data_gaps,
    )


def _technical_context(result: ScreenResult) -> TechnicalAnalysisResponse | None:
    try:
        return calculate_technical_analysis(result.code, result.name)
    except Exception:
        return None


def _result_payload(result: ScreenResult, fallback: AiStockAnalysis, technical: TechnicalAnalysisResponse | None) -> dict[str, Any]:
    metrics = result.metrics
    return {
        "code": result.code,
        "name": result.name,
        "sector": result.sector,
        "industry": result.industry,
        "total_score": result.total_score,
        "scores": result.score.model_dump(),
        "reasons": result.reasons,
        "risks": result.risks,
        "metrics": {
            "market_cap": metrics.get("market_cap"),
            "turnover": metrics.get("turnover"),
            "pct_change": metrics.get("pct_change"),
            "pe": metrics.get("pe"),
            "pb": metrics.get("pb"),
            "dividend_yield": metrics.get("dividend_yield"),
            "roe": metrics.get("roe"),
            "revenue_growth": metrics.get("revenue_growth"),
            "profit_growth": metrics.get("profit_growth"),
            "cashflow_ratio": metrics.get("cashflow_ratio"),
            "historical_pe_percentile": metrics.get("historical_pe_percentile"),
            "main_net_inflow": metrics.get("main_net_inflow"),
            "main_net_inflow_pct": metrics.get("main_net_inflow_pct"),
            "fund_validation": metrics.get("fund_validation"),
            "fund_validation_score": metrics.get("fund_validation_score"),
            "fund_flow_source": metrics.get("fund_flow_source"),
            "fund_flow_note": metrics.get("fund_flow_note"),
        },
        "technical": None
        if technical is None
        else {
            "trend_label": technical.trend_label,
            "trend_score": technical.trend_score,
            "upside_probability": technical.upside_probability,
            "downside_probability": technical.downside_probability,
            "sideways_probability": technical.sideways_probability,
            "summary": technical.summary,
            "support_levels": [level.model_dump(mode="json") for level in technical.support_levels[:3]],
            "resistance_levels": [level.model_dump(mode="json") for level in technical.resistance_levels[:3]],
            "patterns": [pattern.model_dump(mode="json") for pattern in technical.patterns[:3]],
            "risks": technical.risks[:3],
        },
        "local_baseline": fallback.model_dump(mode="json"),
    }


def _analysis_prompt(payload: list[dict[str, Any]]) -> str:
    return f"""
请对下面 A 股观察名单做“研究复核”。你只能基于输入 JSON 分析，不得编造新闻、公告、财报或价格。

硬性规则：
1. 不得输出买入、卖出、加仓、减仓、仓位、目标价、止盈止损等交易建议。
2. 只能给研究观察优先级：重点观察、条件观察、仅跟踪板块、暂不优先。
3. 如果资金来源包含“同花顺”或“代理”，必须说明这是资金净额代理，不等同东方财富主力资金。
4. 如果数据缺失，要降低 confidence 并写入 data_gaps。
5. key_price_levels 只能使用输入 technical 中已有价位；没有价位时 price 用 null。
6. 输出必须是严格 JSON，不要 Markdown，不要解释。

输出格式：
{{
  "analyses": [
    {{
      "code": "000001",
      "name": "示例",
      "ai_priority": "重点观察|条件观察|仅跟踪板块|暂不优先",
      "confidence": 0-100,
      "summary": "80字以内研究摘要",
      "supporting_points": ["支撑点"],
      "contradictions": ["反证或矛盾"],
      "key_price_levels": [{{"label": "支撑位|压力位|观察确认位|失效观察位", "price": 0|null, "reason": "依据"}}],
      "fund_flow_comment": "资金验证说明",
      "valuation_comment": "估值说明",
      "dividend_comment": "分红说明",
      "sector_position_comment": "板块地位说明",
      "data_gaps": ["缺失字段"],
      "research_only_note": "仅用于研究观察，不构成投资建议。"
    }}
  ]
}}

输入 JSON：
{json.dumps(payload, ensure_ascii=False)}
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _validated_ai_analyses(raw: dict[str, Any], fallbacks: dict[str, AiStockAnalysis]) -> list[AiStockAnalysis]:
    raw_items = raw if isinstance(raw, list) else raw.get("analyses", [])
    if not isinstance(raw_items, list):
        return list(fallbacks.values())

    analyses: dict[str, AiStockAnalysis] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").zfill(6)
        fallback = fallbacks.get(code)
        if fallback is None:
            continue
        merged = {**fallback.model_dump(mode="json"), **item, "code": code, "name": item.get("name") or fallback.name}
        if merged.get("ai_priority") not in ALLOWED_PRIORITIES:
            merged["ai_priority"] = fallback.ai_priority
        try:
            analysis = AiStockAnalysis.model_validate(merged)
        except Exception:
            analysis = fallback
        analyses[code] = analysis

    for code, fallback in fallbacks.items():
        analyses.setdefault(code, fallback)
    return sorted(analyses.values(), key=lambda item: (PRIORITY_ORDER.get(item.ai_priority, 9), -item.confidence))


async def analyze_watchlist(results: ScreenResponse, request: AiAnalysisRequest) -> AiAnalysisResponse:
    limit = max(1, min(request.limit, len(results.results)))
    candidates = results.results[:limit]
    technical_limit = max(0, min(request.technical_limit, limit)) if request.include_technical else 0

    technical_by_code: dict[str, TechnicalAnalysisResponse | None] = {}
    fallbacks: dict[str, AiStockAnalysis] = {}
    for index, result in enumerate(candidates):
        technical = _technical_context(result) if index < technical_limit else None
        technical_by_code[result.code] = technical
        fallbacks[result.code] = _local_analysis(result, technical)

    if not candidates:
        return AiAnalysisResponse(generated_at=utc_now_iso(), ok=True, message="暂无观察名单可分析", total_analyzed=0)

    if not ai_configured():
        return AiAnalysisResponse(
            generated_at=utc_now_iso(),
            ok=False,
            message="未配置 AI_API_KEY，已返回本地规则复核结果",
            total_analyzed=len(fallbacks),
            analyses=list(fallbacks.values()),
        )

    payload = [_result_payload(result, fallbacks[result.code], technical_by_code[result.code]) for result in candidates]
    messages = [
        {
            "role": "system",
            "content": "你是谨慎、客观的 A 股研究复核助手。你只做观察名单研究，不给交易建议，并且只输出严格 json。",
        },
        {"role": "user", "content": _analysis_prompt(payload)},
    ]

    try:
        content = await _chat_completion(messages, json_mode=True, timeout=90)
        raw = _extract_json_object(content)
        analyses = _validated_ai_analyses(raw, fallbacks)
        return AiAnalysisResponse(
            generated_at=utc_now_iso(),
            ok=True,
            message=f"AI 研究复核完成：{len(analyses)} 只",
            total_analyzed=len(analyses),
            analyses=analyses,
        )
    except Exception as exc:
        return AiAnalysisResponse(
            generated_at=utc_now_iso(),
            ok=False,
            message=f"AI 接口暂不可用，已返回本地规则复核结果：{exc}",
            total_analyzed=len(fallbacks),
            analyses=list(fallbacks.values()),
        )
