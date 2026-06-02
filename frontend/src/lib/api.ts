import type {
  AmbushBrief,
  AmbushConfig,
  AmbushPipelineResponse,
  AppConfig,
  AiAnalysisResponse,
  DataStatus,
  FinancialMetricsRefreshResponse,
  FundFlowRefreshResponse,
  HoldingAnalysisResponse,
  HoldingItem,
  HoldingListResponse,
  HotSectorResponse,
  KlineScenarioResponse,
  MomentumWatchResponse,
  ScreenResponse,
  TechnicalAnalysisResponse,
  TechnicalLevelsResponse,
  WatchlistItem,
  WatchlistResponse
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function apiUrl(url: string) {
  if (/^https?:\/\//.test(url)) return url;
  return `${API_BASE_URL}${url}`;
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(url), options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; time: string }>("/api/health"),
  status: () => request<DataStatus>("/api/data/status"),
  config: () => request<AppConfig>("/api/config"),
  saveConfig: (config: AppConfig) =>
    request<AppConfig>("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    }),
  uploadCsv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ rows: number; columns: string[]; message: string }>("/api/import/csv", {
      method: "POST",
      body: form
    });
  },
  refreshData: () => request<{ ok: boolean; message: string; rows: number }>("/api/data/refresh", { method: "POST" }),
  refreshFundFlow: () =>
    request<FundFlowRefreshResponse>("/api/data/fund-flow/refresh", {
      method: "POST"
    }),
  refreshFinancialMetrics: () =>
    request<FinancialMetricsRefreshResponse>("/api/data/financial-metrics/refresh", {
      method: "POST"
    }),
  runScreen: () => request<ScreenResponse>("/api/screen/run", { method: "POST" }),
  results: () => request<ScreenResponse>("/api/screen/results"),
  hotSectors: (limit = 30) => request<HotSectorResponse>(`/api/sectors/hot?limit=${limit}`),
  momentumWatchlist: (limit = 60) => request<MomentumWatchResponse>(`/api/momentum/watchlist?limit=${limit}`),
  technicalLevels: (code: string) => request<TechnicalLevelsResponse>(`/api/stocks/${code}/technical-levels`),
  technicalAnalysis: (code: string) => request<TechnicalAnalysisResponse>(`/api/stocks/${code}/technical-analysis`),
  klineScenario: (code: string) => request<KlineScenarioResponse>(`/api/stocks/${code}/kline-scenario`),
  aiRemarks: (limit: number) =>
    request<ScreenResponse>("/api/ai/remarks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit })
    }),
  aiAnalysis: () => request<AiAnalysisResponse>("/api/ai/analysis"),
  analyzeWatchlist: (limit = 30) =>
    request<AiAnalysisResponse>("/api/ai/analyze-watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit, include_technical: true, technical_limit: 8 })
    }),
  holdings: () => request<HoldingListResponse>("/api/holdings"),
  saveHoldings: (holdings: HoldingItem[]) =>
    request<HoldingListResponse>("/api/holdings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holdings })
    }),
  holdingAnalysis: () => request<HoldingAnalysisResponse>("/api/holdings/analysis"),
  analyzeHoldings: () => request<HoldingAnalysisResponse>("/api/holdings/analyze", { method: "POST" }),
  watchlist: () => request<WatchlistResponse>("/api/watchlist"),
  saveWatchlist: (watchlist: WatchlistItem[]) =>
    request<WatchlistResponse>("/api/watchlist", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ watchlist })
    }),
  ambushPipeline: () => request<AmbushPipelineResponse>("/api/ambush/pipeline"),
  runAmbush: () => request<AmbushPipelineResponse>("/api/ambush/run", { method: "POST" }),
  ambushConfig: () => request<AmbushConfig>("/api/ambush/config"),
  saveAmbushConfig: (config: AmbushConfig) =>
    request<AmbushConfig>("/api/ambush/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    }),
  refreshConcepts: () =>
    request<{ message: string }>("/api/ambush/refresh-concepts", { method: "POST" }),
  ambushBrief: () =>
    request<AmbushBrief>("/api/ambush/brief"),
  markBriefSeen: () =>
    request<AmbushBrief>("/api/ambush/brief/seen", { method: "POST" }),
  refreshBrief: () =>
    request<AmbushBrief>("/api/ambush/brief/refresh", { method: "POST" })
};
