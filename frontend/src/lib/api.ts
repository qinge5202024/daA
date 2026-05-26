import type {
  AppConfig,
  AiAnalysisResponse,
  DataStatus,
  FinancialMetricsRefreshResponse,
  FundFlowRefreshResponse,
  HoldingAnalysisResponse,
  HoldingItem,
  HoldingListResponse,
  HotSectorResponse,
  ScreenResponse,
  TechnicalAnalysisResponse,
  TechnicalLevelsResponse
} from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
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
  technicalLevels: (code: string) => request<TechnicalLevelsResponse>(`/api/stocks/${code}/technical-levels`),
  technicalAnalysis: (code: string) => request<TechnicalAnalysisResponse>(`/api/stocks/${code}/technical-analysis`),
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
  analyzeHoldings: () => request<HoldingAnalysisResponse>("/api/holdings/analyze", { method: "POST" })
};
