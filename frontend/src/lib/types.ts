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
