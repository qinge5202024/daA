from __future__ import annotations

import enum
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


class KlineScenarioBand(BaseModel):
    horizon_days: int
    label: str
    downside_price: float | None = None
    base_price: float | None = None
    upside_price: float | None = None
    downside_return_pct: float | None = None
    base_return_pct: float | None = None
    upside_return_pct: float | None = None
    probability_note: str
    basis: str


class KlineScenarioResponse(BaseModel):
    code: str
    name: str
    generated_at: str
    trade_date: str | None = None
    last_close: float | None = None
    source: str = "baostock+local_sequence"
    lookback_days: int = 0
    trend_context: str = ""
    volatility_state: str = ""
    range_state: str = ""
    volume_state: str = ""
    summary: str = ""
    scenario_bands: list[KlineScenarioBand] = Field(default_factory=list)
    sequence_signals: list[TechnicalSignal] = Field(default_factory=list)
    support_levels: list[TechnicalLevel] = Field(default_factory=list)
    resistance_levels: list[TechnicalLevel] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    research_only_note: str = "K线情景参考仅用于研究观察，不构成预测或投资建议。"


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


class WatchlistItem(BaseModel):
    id: str = ""
    code: str = ""
    name: str = ""
    group: str = "默认"
    note: str = ""
    added_at: str = ""


class WatchlistResponse(BaseModel):
    generated_at: str
    watchlist: list[WatchlistItem] = Field(default_factory=list)


class WatchlistSaveRequest(BaseModel):
    watchlist: list[WatchlistItem] = Field(default_factory=list)


class HoldingItem(BaseModel):
    id: str = ""
    code: str = ""
    name: str = ""
    quantity: float = 0
    cost_price: float
    holding_period: str = "short"
    note: str = ""


class AmbushBriefItem(BaseModel):
    """简报中的一条项目"""
    code: str
    name: str
    sector: str
    stage: str = ""
    total_score: float = 0.0
    change: str = ""  # new/promoted/new_signal/expired
    detail: str = ""


class AmbushBrief(BaseModel):
    """每日简报

    通过对比当前管道快照与上次快照，提取变化信息。
    """
    generated_at: str
    pipeline_generated_at: str = ""
    
    # 变化概览
    new_items_count: int = 0
    promoted_count: int = 0
    expired_count: int = 0
    new_signal_count: int = 0
    
    # 变化明细
    new_items: list[AmbushBriefItem] = Field(default_factory=list)
    promoted_items: list[AmbushBriefItem] = Field(default_factory=list)
    expired_items: list[AmbushBriefItem] = Field(default_factory=list)
    new_signal_items: list[AmbushBriefItem] = Field(default_factory=list)
    
    # 各阶段亮点（当前管道中评分最高的几只）
    top_watch: list[AmbushBriefItem] = Field(default_factory=list)
    top_brewing: list[AmbushBriefItem] = Field(default_factory=list)
    top_ignition: list[AmbushBriefItem] = Field(default_factory=list)
    
    # 用户标记
    seen_at: str | None = None
    has_unseen: bool = True


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
    last_price_source: str | None = None
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


class AmbushStage(str, enum.Enum):
    WATCH = "观察池"
    BREWING = "蓄势中"
    IGNITION = "待点火"
    TRIGGERED = "触发条件"
    EXPIRED = "已失效"


class AmbushSignalDetail(BaseModel):
    signal_key: str
    signal_name: str
    group: str  # 蓄势组/吸筹组/背离组
    confidence: float = 0.0
    details: str = ""


class AmbushThematicScore(BaseModel):
    matched_concepts: list[str] = Field(default_factory=list)
    concept_count: int = 0
    hot_concept_hits: int = 0
    sector_relevance: float = 0.0
    score: float = 0.0


class AmbushConfirmCondition(BaseModel):
    condition: str = ""
    trigger_price: float | None = None
    price_basis: str = ""
    stop_loss: str = ""
    target: str = ""
    time_limit_days: int = 30


class AmbushItem(BaseModel):
    code: str
    name: str
    sector: str
    industry: str
    stage: AmbushStage = AmbushStage.WATCH
    
    # 综合评分
    total_score: float = 0.0
    structure_score: float = 0.0     # K线结构组
    quality_score: float = 0.0       # 基本面安全垫
    thematic_score: float = 0.0      # 题材预期
    
    # 信号明细
    signals: list[AmbushSignalDetail] = Field(default_factory=list)
    thematic: AmbushThematicScore = Field(default_factory=AmbushThematicScore)
    
    # 确认条件（待点火阶段才有）
    conditions: list[AmbushConfirmCondition] = Field(default_factory=list)
    
    # 进管道时间
    entered_at: str = ""
    last_signal_at: str = ""
    days_in_pipeline: int = 0
    
    # 降级原因
    expired_reason: str = ""


class AmbushConfig(BaseModel):
    max_watch_pool: int = 300
    max_brewing_pool: int = 80
    max_ignition_pool: int = 30
    structure_weight: float = 0.35
    quality_weight: float = 0.25
    thematic_weight: float = 0.25
    ambush_weight: float = 0.15
    structure_threshold: float = 55.0
    ignition_threshold: float = 60.0
    expire_days: int = 45
    hot_concept_list: list[str] = Field(default_factory=lambda: [
        "人工智能", "AI", "芯片", "半导体", "新能源", "光伏",
        "低空经济", "机器人", "消费电子", "汽车", "医药",
    ])


class AmbushResponse(BaseModel):
    generated_at: str
    total_analyzed: int = 0
    results: list[AmbushItem] = Field(default_factory=list)
    pipeline_summary: dict[str, int] = Field(default_factory=dict)


class AmbushPipelineResponse(BaseModel):
    generated_at: str
    watch_pool: list[AmbushItem] = Field(default_factory=list)
    brewing_pool: list[AmbushItem] = Field(default_factory=list)
    ignition_pool: list[AmbushItem] = Field(default_factory=list)
    triggered: list[AmbushItem] = Field(default_factory=list)
    expired: list[AmbushItem] = Field(default_factory=list)
    new_today: int = 0
    triggered_today: int = 0
    expired_today: int = 0
