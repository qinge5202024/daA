export type ScoreWeights = {
  sector_heat: number;
  leadership: number;
  quality: number;
  valuation: number;
  dividend: number;
  industry_risk: number;
};

export type Thresholds = {
  min_total_score: number;
  max_results: number;
  min_turnover: number;
  max_pe: number | null;
};

export type AppConfig = {
  weights: ScoreWeights;
  sunset_industries: string[];
  thresholds: Thresholds;
  ai_enabled: boolean;
};

export type DataStatus = {
  last_refresh_at: string | null;
  last_success_at: string | null;
  source: string;
  ok: boolean;
  message: string;
  rows: number;
  refresh_running: boolean;
};

export type FundFlowRefreshResponse = {
  ok: boolean;
  message: string;
  rows: number;
  before_coverage: number;
  after_coverage: number;
};

export type FinancialMetricsRefreshResponse = {
  ok: boolean;
  message: string;
  rows: number;
  before_complete_coverage: number;
  after_complete_coverage: number;
};

export type ScoreBreakdown = {
  sector_heat: number;
  leadership: number;
  quality: number;
  valuation: number;
  dividend: number;
  industry_risk: number;
};

export type ScreenResult = {
  code: string;
  name: string;
  sector: string;
  industry: string;
  total_score: number;
  score: ScoreBreakdown;
  reasons: string[];
  risks: string[];
  metrics: Record<string, number | string | null>;
  ai_remark: string | null;
};

export type ScreenResponse = {
  generated_at: string;
  total_candidates: number;
  results: ScreenResult[];
};

export type MomentumWatchItem = {
  code: string;
  name: string;
  sector: string;
  industry: string;
  momentum_score: number;
  rank: number;
  trigger_level: string;
  reasons: string[];
  risks: string[];
  metrics: Record<string, number | string | null>;
};

export type MomentumWatchResponse = {
  generated_at: string;
  total_candidates: number;
  results: MomentumWatchItem[];
};

export type AiKeyPriceLevel = {
  label: string;
  price: number | null;
  reason: string;
};

export type AiStockAnalysis = {
  code: string;
  name: string;
  ai_priority: "重点观察" | "条件观察" | "仅跟踪板块" | "暂不优先" | string;
  confidence: number;
  summary: string;
  supporting_points: string[];
  contradictions: string[];
  key_price_levels: AiKeyPriceLevel[];
  fund_flow_comment: string;
  valuation_comment: string;
  dividend_comment: string;
  sector_position_comment: string;
  data_gaps: string[];
  research_only_note: string;
};

export type AiAnalysisResponse = {
  generated_at: string;
  ok: boolean;
  message: string;
  total_analyzed: number;
  analyses: AiStockAnalysis[];
};

export type HoldingPeriod = "short" | "long" | string;

export type WatchlistItem = {
  id: string;
  code: string;
  name: string;
  group: string;
  note: string;
  added_at: string;
};

export type WatchlistResponse = {
  generated_at: string;
  watchlist: WatchlistItem[];
};

export type HoldingItem = {
  id: string;
  code: string;
  name: string;
  quantity: number;
  cost_price: number;
  holding_period: HoldingPeriod;
  note: string;
};

export type HoldingListResponse = {
  generated_at: string;
  holdings: HoldingItem[];
};

export type HoldingPlanLevel = {
  label: string;
  price: number | null;
  zone: string;
  reason: string;
  condition: string;
};

export type HoldingAnalysisItem = {
  id: string;
  code: string;
  name: string;
  holding_period: HoldingPeriod;
  cost_price: number;
  quantity: number;
  last_price: number | null;
  last_price_source: string | null;
  position_value: number | null;
  unrealized_profit: number | null;
  unrealized_profit_pct: number | null;
  priority: string;
  confidence: number;
  summary: string;
  plan_levels: HoldingPlanLevel[];
  action_points: string[];
  risk_flags: string[];
  short_term_view: string;
  long_term_view: string;
  data_gaps: string[];
  research_only_note: string;
};

export type HoldingAnalysisResponse = {
  generated_at: string;
  ok: boolean;
  message: string;
  analyses: HoldingAnalysisItem[];
};

export type AmbushStage = "观察池" | "蓄势中" | "待点火" | "触发条件" | "已失效";

export type AmbushSignalDetail = {
  signal_key: string;
  signal_name: string;
  group: string;
  confidence: number;
  details: string;
};

export type AmbushThematicScore = {
  matched_concepts: string[];
  concept_count: number;
  hot_concept_hits: number;
  sector_relevance: number;
  score: number;
};

export type AmbushConfirmCondition = {
  condition: string;
  trigger_price: number | null;
  price_basis: string;
  stop_loss: string;
  target: string;
  time_limit_days: number;
};

export type AmbushItem = {
  code: string;
  name: string;
  sector: string;
  industry: string;
  stage: AmbushStage;
  total_score: number;
  structure_score: number;
  quality_score: number;
  thematic_score: number;
  signals: AmbushSignalDetail[];
  thematic: AmbushThematicScore;
  conditions: AmbushConfirmCondition[];
  entered_at: string;
  last_signal_at: string;
  days_in_pipeline: number;
  expired_reason: string;
};

export type AmbushConfig = {
  max_watch_pool: number;
  max_brewing_pool: number;
  max_ignition_pool: number;
  structure_weight: number;
  quality_weight: number;
  thematic_weight: number;
  ambush_weight: number;
  structure_threshold: number;
  ignition_threshold: number;
  expire_days: number;
  hot_concept_list: string[];
};

export type AmbushPipelineResponse = {
  generated_at: string;
  watch_pool: AmbushItem[];
  brewing_pool: AmbushItem[];
  ignition_pool: AmbushItem[];
  triggered: AmbushItem[];
  expired: AmbushItem[];
  new_today: number;
  triggered_today: number;
  expired_today: number;
};

export type AmbushBriefItem = {
  code: string;
  name: string;
  sector: string;
  stage: string;
  total_score: number;
  change: string; // new/promoted/new_signal/expired
  detail: string;
};

export type AmbushBrief = {
  generated_at: string;
  pipeline_generated_at: string;
  new_items_count: number;
  promoted_count: number;
  expired_count: number;
  new_signal_count: number;
  new_items: AmbushBriefItem[];
  promoted_items: AmbushBriefItem[];
  expired_items: AmbushBriefItem[];
  new_signal_items: AmbushBriefItem[];
  top_watch: AmbushBriefItem[];
  top_brewing: AmbushBriefItem[];
  top_ignition: AmbushBriefItem[];
  seen_at: string | null;
  has_unseen: boolean;
};

export type SectorLeader = {
  code: string;
  name: string;
  score: number | null;
  basis: string;
};

export type HotSectorItem = {
  sector: string;
  heat_score: number;
  stock_count: number;
  pct_change: number | null;
  turnover: number | null;
  avg_volume_ratio: number | null;
  main_net_inflow: number | null;
  main_net_inflow_pct: number | null;
  active_stock_ratio: number | null;
  fund_flow_source?: string | null;
  fund_flow_note?: string | null;
  fund_validation: string;
  notes: string[];
  leaders: SectorLeader[];
};

export type HotSectorResponse = {
  generated_at: string;
  total_sectors: number;
  sectors: HotSectorItem[];
};

export type TechnicalLevel = {
  key: string;
  label: string;
  price: number;
  distance_pct: number;
  basis: string;
  position: string;
};

export type TechnicalLevelsResponse = {
  code: string;
  name: string;
  generated_at: string;
  trade_date: string | null;
  last_close: number | null;
  source: string;
  levels: TechnicalLevel[];
};

export type CandlestickPattern = {
  key: string;
  label: string;
  direction: "bullish" | "bearish" | "neutral" | string;
  confidence: number;
  description: string;
};

export type TechnicalSignal = {
  label: string;
  value: string;
  direction: "bullish" | "bearish" | "neutral" | string;
  weight: number;
};

export type TechnicalAnalysisResponse = {
  code: string;
  name: string;
  generated_at: string;
  trade_date: string | null;
  last_close: number | null;
  source: string;
  trend_label: string;
  trend_score: number;
  upside_probability: number;
  downside_probability: number;
  sideways_probability: number;
  summary: string;
  support_levels: TechnicalLevel[];
  resistance_levels: TechnicalLevel[];
  patterns: CandlestickPattern[];
  signals: TechnicalSignal[];
  risks: string[];
};

export type KlineScenarioBand = {
  horizon_days: number;
  label: string;
  downside_price: number | null;
  base_price: number | null;
  upside_price: number | null;
  downside_return_pct: number | null;
  base_return_pct: number | null;
  upside_return_pct: number | null;
  probability_note: string;
  basis: string;
};

export type KlineScenarioResponse = {
  code: string;
  name: string;
  generated_at: string;
  trade_date: string | null;
  last_close: number | null;
  source: string;
  lookback_days: number;
  trend_context: string;
  volatility_state: string;
  range_state: string;
  volume_state: string;
  summary: string;
  scenario_bands: KlineScenarioBand[];
  sequence_signals: TechnicalSignal[];
  support_levels: TechnicalLevel[];
  resistance_levels: TechnicalLevel[];
  data_gaps: string[];
  research_only_note: string;
};
