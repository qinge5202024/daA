from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScoreWeights(BaseModel):
    sector_heat: float = 0.20
    leadership: float = 0.20
    quality: float = 0.20
    valuation: float = 0.20
    dividend: float = 0.10
    industry_risk: float = 0.10


class Thresholds(BaseModel):
    min_total_score: float = 55
    max_results: int = 80
    min_turnover: float = 0
    max_pe: float | None = None


class AppConfig(BaseModel):
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    sunset_industries: list[str] = Field(
        default_factory=lambda: ["煤炭开采", "纺织制造", "传统百货", "房地产开发"]
    )
    thresholds: Thresholds = Field(default_factory=Thresholds)
    ai_enabled: bool = False


class DataStatus(BaseModel):
    last_refresh_at: str | None = None
    last_success_at: str | None = None
    source: str = "none"
    ok: bool = False
    message: str = "尚未导入或刷新数据"
    rows: int = 0
    refresh_running: bool = False


class ImportResponse(BaseModel):
    rows: int
    columns: list[str]
    message: str


class RefreshResponse(BaseModel):
    ok: bool
    message: str
    rows: int = 0


class FundFlowRefreshResponse(BaseModel):
    ok: bool
    message: str
    rows: int = 0
    before_coverage: int = 0
    after_coverage: int = 0


class FinancialMetricsRefreshResponse(BaseModel):
    ok: bool
    message: str
    rows: int = 0
    before_complete_coverage: int = 0
    after_complete_coverage: int = 0


class ScoreBreakdown(BaseModel):
    sector_heat: float
    leadership: float
    quality: float
    valuation: float
    dividend: float
    industry_risk: float


class ScreenResult(BaseModel):
    code: str
    name: str
    sector: str
    industry: str
    total_score: float
    score: ScoreBreakdown
    reasons: list[str]
    risks: list[str]
    metrics: dict[str, Any]
    ai_remark: str | None = None


class ScreenResponse(BaseModel):
    generated_at: str
    total_candidates: int
    results: list[ScreenResult]


class SectorLeader(BaseModel):
    code: str
    name: str
    score: float | None = None
    basis: str


class HotSectorItem(BaseModel):
    sector: str
    heat_score: float
    stock_count: int
    pct_change: float | None = None
    turnover: float | None = None
    avg_volume_ratio: float | None = None
    main_net_inflow: float | None = None
    main_net_inflow_pct: float | None = None
    active_stock_ratio: float | None = None
    fund_flow_source: str | None = None
    fund_flow_note: str | None = None
    fund_validation: str
    notes: list[str]
    leaders: list[SectorLeader]


class HotSectorResponse(BaseModel):
    generated_at: str
    total_sectors: int
    sectors: list[HotSectorItem]


class MomentumWatchItem(BaseModel):
    code: str
    name: str
    sector: str
    industry: str
    momentum_score: float
    rank: int
    trigger_level: str
    reasons: list[str]
    risks: list[str]
    metrics: dict[str, Any]


class MomentumWatchResponse(BaseModel):
    generated_at: str
    total_candidates: int
    results: list[MomentumWatchItem]


class TechnicalLevel(BaseModel):
    key: str
    label: str
    price: float
    distance_pct: float
    basis: str
    position: str


class TechnicalLevelsResponse(BaseModel):
    code: str
    name: str
    generated_at: str
    trade_date: str | None = None
    last_close: float | None = None
    source: str = "baostock"
    levels: list[TechnicalLevel]


class CandlestickPattern(BaseModel):
    key: str
    label: str
    direction: str
    confidence: float
    description: str


class TechnicalSignal(BaseModel):
    label: str
    value: str
    direction: str
    weight: float


class TechnicalAnalysisResponse(BaseModel):
    code: str
    name: str
    generated_at: str
    trade_date: str | None = None
    last_close: float | None = None
    source: str = "baostock"
    trend_label: str
    trend_score: float
    upside_probability: float
    downside_probability: float
    sideways_probability: float
    summary: str
    support_levels: list[TechnicalLevel]
    resistance_levels: list[TechnicalLevel]
    patterns: list[CandlestickPattern]
    signals: list[TechnicalSignal]
    risks: list[str]


class AiRemarkRequest(BaseModel):
    limit: int = 20


class AiAnalysisRequest(BaseModel):
    limit: int = 30
    force_refresh: bool = True
    include_technical: bool = True
    technical_limit: int = 8


class AiKeyPriceLevel(BaseModel):
    label: str
    price: float | None = None
    reason: str


class AiStockAnalysis(BaseModel):
    code: str
    name: str
    ai_priority: str = "条件观察"
    confidence: float = 50
    summary: str = ""
    supporting_points: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    key_price_levels: list[AiKeyPriceLevel] = Field(default_factory=list)
    fund_flow_comment: str = ""
    valuation_comment: str = ""
    dividend_comment: str = ""
    sector_position_comment: str = ""
    data_gaps: list[str] = Field(default_factory=list)
    research_only_note: str = "仅用于研究观察，不构成投资建议。"


class AiAnalysisResponse(BaseModel):
    generated_at: str
    ok: bool = True
    message: str = ""
    total_analyzed: int = 0
    analyses: list[AiStockAnalysis] = Field(default_factory=list)


class HoldingItem(BaseModel):
    id: str = ""
    code: str = ""
    name: str = ""
    quantity: float = 0
    cost_price: float
    holding_period: str = "short"
    note: str = ""


class HoldingListResponse(BaseModel):
    generated_at: str
    holdings: list[HoldingItem] = Field(default_factory=list)


class HoldingSaveRequest(BaseModel):
    holdings: list[HoldingItem] = Field(default_factory=list)


class HoldingPlanLevel(BaseModel):
    label: str
    price: float | None = None
    zone: str = ""
    reason: str
    condition: str


class HoldingAnalysisItem(BaseModel):
    id: str
    code: str
    name: str
    holding_period: str
    cost_price: float
    quantity: float
    last_price: float | None = None
    position_value: float | None = None
    unrealized_profit: float | None = None
    unrealized_profit_pct: float | None = None
    priority: str = "复核观察"
    confidence: float = 50
    summary: str = ""
    plan_levels: list[HoldingPlanLevel] = Field(default_factory=list)
    action_points: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    short_term_view: str = ""
    long_term_view: str = ""
    data_gaps: list[str] = Field(default_factory=list)
    research_only_note: str = "仅用于持仓研究观察，不构成投资建议。"


class HoldingAnalysisResponse(BaseModel):
    generated_at: str
    ok: bool = True
    message: str = ""
    analyses: list[HoldingAnalysisItem] = Field(default_factory=list)
