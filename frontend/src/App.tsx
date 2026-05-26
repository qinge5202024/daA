import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Bot,
  Activity,
  BadgeCheck,
  BarChart3,
  Briefcase,
  CircleDollarSign,
  Database,
  FileUp,
  Flame,
  FlaskConical,
  Gauge,
  Layers3,
  ListFilter,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings2,
  ShieldAlert,
  Trash2,
  Target,
  SlidersHorizontal,
  TrendingUp
} from "lucide-react";
import { api } from "./lib/api";
import type {
  AppConfig,
  AiAnalysisResponse,
  AiStockAnalysis,
  DataStatus,
  HoldingAnalysisItem,
  HoldingAnalysisResponse,
  HoldingItem,
  HotSectorResponse,
  ScreenResponse,
  ScreenResult,
  ScoreWeights,
  TechnicalAnalysisResponse,
  TechnicalLevelsResponse
} from "./lib/types";

type View = "data" | "hot" | "strategy" | "results" | "detail" | "holdings";

const scoreLabels: Record<keyof ScoreWeights, string> = {
  sector_heat: "板块资金",
  leadership: "龙头地位",
  quality: "长期质量",
  valuation: "估值纪律",
  dividend: "分红持续",
  industry_risk: "行业风险"
};

const defaultConfig: AppConfig = {
  weights: {
    sector_heat: 0.2,
    leadership: 0.2,
    quality: 0.2,
    valuation: 0.2,
    dividend: 0.1,
    industry_risk: 0.1
  },
  sunset_industries: ["煤炭开采", "纺织制造", "传统百货", "房地产开发"],
  thresholds: {
    min_total_score: 55,
    max_results: 80,
    min_turnover: 0,
    max_pe: null
  },
  ai_enabled: false
};

function formatNumber(value: unknown, suffix = "") {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (Math.abs(number) >= 100_000_000) return `${(number / 100_000_000).toFixed(1)}亿${suffix}`;
  if (Math.abs(number) >= 10_000) return `${(number / 10_000).toFixed(1)}万${suffix}`;
  return `${number.toFixed(number % 1 === 0 ? 0 : 1)}${suffix}`;
}

function formatMoney(value: unknown) {
  return formatNumber(value);
}

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function scoreClass(score: number) {
  if (score >= 75) return "score strong";
  if (score >= 60) return "score steady";
  return "score weak";
}

function directionClass(direction: string) {
  if (direction === "bullish") return "direction bullish";
  if (direction === "bearish") return "direction bearish";
  return "direction neutral";
}

function formatPrice(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toFixed(number >= 100 ? 2 : 3).replace(/0+$/, "").replace(/\.$/, "");
}

function isProxyFundSource(source: unknown) {
  const text = String(source ?? "");
  return text.includes("代理") || text.includes("同花顺");
}

function fundFlowLabels(source: unknown) {
  const proxy = isProxyFundSource(source);
  return {
    flow: proxy ? "资金净额" : "主力净流入",
    flowPct: proxy ? "资金净占比" : "主力净占比",
    sectorFlow: proxy ? "板块资金净额" : "板块主力净流入",
    sectorFlowPct: proxy ? "板块资金净占比" : "板块主力净占比",
    panelTitle: proxy ? "资金净额验证" : "主力资金验证"
  };
}

const aiPriorityOptions = ["全部", "重点观察", "条件观察", "仅跟踪板块", "暂不优先"];
const scoreKeys = Object.keys(scoreLabels) as Array<keyof ScoreWeights>;
const holdingPeriodLabels: Record<string, string> = {
  short: "短线 30 天内",
  long: "长线 2-10 年"
};

function aiPriorityClass(priority: unknown) {
  if (priority === "重点观察") return "ai-priority focus";
  if (priority === "条件观察") return "ai-priority conditional";
  if (priority === "仅跟踪板块") return "ai-priority sector-only";
  if (priority === "暂不优先") return "ai-priority low";
  return "ai-priority muted";
}

function clampScore(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Math.max(0, Math.min(100, number));
}

function averageScore(values: number[]) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function scoreTone(score: number) {
  if (score >= 75) return "strong";
  if (score >= 60) return "steady";
  return "weak";
}

function createHolding(): HoldingItem {
  return {
    id: `local-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
    code: "",
    name: "",
    quantity: 0,
    cost_price: 0,
    holding_period: "short",
    note: ""
  };
}

function formatPercent(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function profitClass(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "profit neutral";
  return number > 0 ? "profit positive" : "profit negative";
}

function holdingPriorityClass(priority: unknown) {
  if (priority === "增强跟踪") return "holding-priority focus";
  if (priority === "继续观察") return "holding-priority steady";
  if (priority === "降低暴露") return "holding-priority risk";
  return "holding-priority muted";
}

function holdingLevelClass(label: string) {
  if (label.includes("加仓")) return "holding-level add";
  if (label.includes("减仓") || label.includes("获利")) return "holding-level trim";
  if (label.includes("风险")) return "holding-level risk";
  return "holding-level";
}

function App() {
  const [view, setView] = useState<View>("data");
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [config, setConfig] = useState<AppConfig>(defaultConfig);
  const [results, setResults] = useState<ScreenResponse | null>(null);
  const [hotSectors, setHotSectors] = useState<HotSectorResponse | null>(null);
  const [aiAnalysis, setAiAnalysis] = useState<AiAnalysisResponse | null>(null);
  const [holdings, setHoldings] = useState<HoldingItem[]>([]);
  const [holdingAnalysis, setHoldingAnalysis] = useState<HoldingAnalysisResponse | null>(null);
  const [priorityFilter, setPriorityFilter] = useState("全部");
  const [selected, setSelected] = useState<ScreenResult | null>(null);
  const [message, setMessage] = useState("正在连接本地服务");
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  function resetAiReview() {
    setAiAnalysis(null);
    setPriorityFilter("全部");
  }

  function syncSelected(nextResults: ScreenResult[]) {
    setSelected((current) => {
      if (!current) return nextResults[0] ?? null;
      return nextResults.find((item) => item.code === current.code) ?? nextResults[0] ?? null;
    });
  }

  async function loadAll() {
    const [statusData, configData, resultData, sectorData, analysisData, holdingData, holdingReviewData] =
      await Promise.all([
      api.status(),
      api.config(),
      api.results(),
      api.hotSectors(),
      api.aiAnalysis(),
      api.holdings(),
      api.holdingAnalysis()
    ]);
    setStatus(statusData);
    setConfig(configData);
    setResults(resultData);
    setHotSectors(sectorData);
    setAiAnalysis(analysisData);
    setHoldings(holdingData.holdings);
    setHoldingAnalysis(holdingReviewData);
    syncSelected(resultData.results);
  }

  useEffect(() => {
    loadAll()
      .then(() => setMessage("本地服务已连接"))
      .catch((error) => setMessage(error instanceof Error ? error.message : "本地服务连接失败"));
  }, []);

  const topResults = useMemo(() => results?.results ?? [], [results]);
  const aiByCode = useMemo(() => {
    const map = new Map<string, AiStockAnalysis>();
    for (const item of aiAnalysis?.analyses ?? []) map.set(item.code, item);
    return map;
  }, [aiAnalysis]);
  const displayedResults = useMemo(() => {
    if (priorityFilter === "全部") return topResults;
    return topResults.filter((item) => aiByCode.get(item.code)?.ai_priority === priorityFilter);
  }, [aiByCode, priorityFilter, topResults]);

  async function withBusy(
    task: () => Promise<string | void>,
    done: string,
    pending = "正在处理，请稍候",
    action = "work"
  ) {
    setBusy(true);
    setBusyAction(action);
    setMessage(pending);
    try {
      const taskMessage = await task();
      setMessage(taskMessage ?? done);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusy(false);
      setBusyAction(null);
    }
  }

  async function handleUpload(file: File | null) {
    if (!file) return;
    await withBusy(async () => {
      await api.uploadCsv(file);
      resetAiReview();
      await loadAll();
    }, "CSV 已导入并完成评分", "正在导入 CSV 并评分", "upload");
  }

  async function handleRefresh() {
    await withBusy(async () => {
      const started = await api.refreshData();
      setMessage(started.message);
      let latestStatus = await api.status();
      setStatus(latestStatus);
      const startedAt = Date.now();
      while (latestStatus.refresh_running && Date.now() - startedAt < 8 * 60 * 1000) {
        await new Promise((resolve) => window.setTimeout(resolve, 1800));
        latestStatus = await api.status();
        setStatus(latestStatus);
        setMessage(latestStatus.message || "刷新任务仍在运行");
      }
      if (latestStatus.refresh_running) {
        return "刷新任务仍在后台运行，可稍后查看状态";
      }
      resetAiReview();
      await loadAll();
      return latestStatus.message;
    }, "免费行情刷新流程已结束", "正在启动免费行情刷新任务", "refresh");
  }

  async function handleRefreshFundFlow() {
    await withBusy(async () => {
      const response = await api.refreshFundFlow();
      resetAiReview();
      await loadAll();
      return response.message;
    }, "资金流字段已补充", "正在补充免费资金流字段", "fundFlow");
  }

  async function handleRefreshFinancialMetrics() {
    await withBusy(async () => {
      const response = await api.refreshFinancialMetrics();
      resetAiReview();
      await loadAll();
      return response.message;
    }, "财务指标已补充", "正在补充 ROE、增长与分红字段", "financialMetrics");
  }

  async function handleRunScreen() {
    await withBusy(async () => {
      const saved = await api.saveConfig(config);
      setConfig(saved);
      const data = await api.runScreen();
      setResults(data);
      setHotSectors(await api.hotSectors());
      syncSelected(data.results);
      setStatus(await api.status());
      resetAiReview();
      return `观察名单已按当前策略重新生成：${data.results.length} 只，候选池 ${data.total_candidates} 只`;
    }, "观察名单已重新生成", "正在按当前策略重新评分", "screen");
  }

  async function handleSaveConfig() {
    await withBusy(async () => {
      const saved = await api.saveConfig(config);
      setConfig(saved);
      const data = await api.results();
      setResults(data);
      syncSelected(data.results);
      setHotSectors(await api.hotSectors());
      resetAiReview();
    }, "策略配置已保存", "正在保存策略并刷新评分结果", "save");
  }

  async function handleAiRemarks() {
    await withBusy(async () => {
      const data = await api.aiRemarks(20);
      setResults(data);
      const refreshedSelected = selected ? data.results.find((item) => item.code === selected.code) : data.results[0];
      setSelected(refreshedSelected ?? null);
    }, "AI 辅助备注已更新", "正在生成 AI 辅助备注", "ai");
  }

  async function handleAiAnalysis() {
    await withBusy(async () => {
      const data = await api.analyzeWatchlist(Math.min(30, Math.max(1, topResults.length)));
      setAiAnalysis(data);
      return data.message || `AI 研究复核完成：${data.total_analyzed} 只`;
    }, "AI 研究复核已更新", "正在进行 AI 研究复核", "aiAnalysis");
  }

  function handleAddHolding() {
    setHoldings((current) => [...current, createHolding()]);
  }

  function handleUpdateHolding(index: number, patch: Partial<HoldingItem>) {
    setHoldings((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function handleRemoveHolding(index: number) {
    setHoldings((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  async function handleSaveHoldings() {
    await withBusy(async () => {
      const data = await api.saveHoldings(holdings);
      setHoldings(data.holdings.length > 0 ? data.holdings : [createHolding()]);
      const review = await api.holdingAnalysis();
      setHoldingAnalysis(review);
      return `持仓已保存：${data.holdings.length} 条`;
    }, "持仓已保存", "正在保存持仓数据", "holdingsSave");
  }

  async function handleAnalyzeHoldings() {
    await withBusy(async () => {
      const saved = await api.saveHoldings(holdings);
      setHoldings(saved.holdings.length > 0 ? saved.holdings : [createHolding()]);
      const data = await api.analyzeHoldings();
      setHoldingAnalysis(data);
      return data.message || `持仓复核完成：${data.analyses.length} 条`;
    }, "持仓复核已更新", "正在生成持仓复核", "holdingsAnalyze");
  }

  function updateWeight(key: keyof ScoreWeights, value: number) {
    setConfig((current) => ({
      ...current,
      weights: { ...current.weights, [key]: value / 100 }
    }));
  }

  function updateThreshold<K extends keyof AppConfig["thresholds"]>(key: K, value: AppConfig["thresholds"][K]) {
    setConfig((current) => ({
      ...current,
      thresholds: { ...current.thresholds, [key]: value }
    }));
  }

  function navButton(id: View, label: string, icon: ReactNode) {
    return (
      <button className={view === id ? "nav active" : "nav"} onClick={() => setView(id)} type="button">
        {icon}
        <span>{label}</span>
      </button>
    );
  }

  return (
    <div className="app-shell" data-view={view}>
      <div className="market-chrome" aria-hidden="true" />
      <aside className="sidebar">
        <div className="brand">
          <TrendingUp size={24} />
          <div>
            <strong>A股观察名单</strong>
            <span>板块龙头筛选</span>
          </div>
        </div>
        <nav>
          {navButton("data", "数据", <Database size={18} />)}
          {navButton("hot", "热点", <Flame size={18} />)}
          {navButton("strategy", "策略", <SlidersHorizontal size={18} />)}
          {navButton("results", "结果", <ListFilter size={18} />)}
          {navButton("holdings", "持仓", <Briefcase size={18} />)}
          {navButton("detail", "详情", <Search size={18} />)}
        </nav>
        <div className="notice">
          <ShieldAlert size={17} />
          <span>仅用于研究观察，不构成投资建议。</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <h1>
              {view === "data"
                ? "数据工作台"
                : view === "hot"
                  ? "热点板块"
                  : view === "strategy"
                    ? "策略配置"
                    : view === "results"
                      ? "观察名单"
                      : view === "holdings"
                        ? "持仓盯盘"
                        : "个股详情"}
            </h1>
            <p>{message}</p>
          </div>
          <div className="status-strip">
            <span className={status?.ok ? "dot ok" : "dot warn"} />
            <span>{status?.source ?? "none"}</span>
            <span>{formatNumber(status?.rows ?? 0)} 行</span>
            <span>{formatDate(status?.last_success_at ?? null)}</span>
          </div>
        </header>

        {view === "data" && (
          <section className="page-grid">
            <div className="tool-panel">
              <div className="panel-title">
                <FileUp size={19} />
                <h2>CSV 导入</h2>
              </div>
              <label className="file-drop">
                <input type="file" accept=".csv" onChange={(event) => handleUpload(event.target.files?.[0] ?? null)} />
                <FileUp size={28} />
                <strong>选择股票池 CSV</strong>
                <span>支持代码、名称、行业/板块、市值、成交额、估值、ROE、增长、分红等字段</span>
              </label>
            </div>

            <div className="tool-panel">
              <div className="panel-title">
                <RefreshCw size={19} />
                <h2>免费行情刷新</h2>
              </div>
              <div className="metric-list">
                <div>
                  <span>数据源</span>
                  <strong>{status?.source ?? "none"}</strong>
                </div>
                <div>
                  <span>最近成功</span>
                  <strong>{formatDate(status?.last_success_at ?? null)}</strong>
                </div>
                <div>
                  <span>状态</span>
                  <strong>{status?.message ?? "-"}</strong>
                </div>
              </div>
              <div className="action-row">
                <button
                  className={busyAction === "refresh" ? "primary-action loading" : "primary-action"}
                  onClick={handleRefresh}
                  disabled={busy}
                  type="button"
                >
                  <RefreshCw size={18} />
                  {busyAction === "refresh" ? "刷新中" : "刷新免费行情"}
                </button>
                <button
                  className={busyAction === "fundFlow" ? "secondary-action loading" : "secondary-action"}
                  onClick={handleRefreshFundFlow}
                  disabled={busy}
                  type="button"
                >
                  <Activity size={18} />
                  {busyAction === "fundFlow" ? "补充中" : "补充资金流"}
                </button>
                <button
                  className={busyAction === "financialMetrics" ? "secondary-action loading" : "secondary-action"}
                  onClick={handleRefreshFinancialMetrics}
                  disabled={busy}
                  type="button"
                >
                  <BarChart3 size={18} />
                  {busyAction === "financialMetrics" ? "补充中" : "补充财务指标"}
                </button>
              </div>
            </div>
          </section>
        )}

        {view === "hot" && <HotSectorsView data={hotSectors} />}

        {view === "strategy" && (
          <section className="strategy-layout">
            <div className="tool-panel">
              <div className="panel-title">
                <Settings2 size={19} />
                <h2>评分权重</h2>
              </div>
              <div className="weight-list">
                {(Object.keys(scoreLabels) as Array<keyof ScoreWeights>).map((key) => (
                  <label key={key} className="slider-row">
                    <span>{scoreLabels[key]}</span>
                    <input
                      type="range"
                      min="0"
                      max="50"
                      step="1"
                      value={Math.round(config.weights[key] * 100)}
                      onChange={(event) => updateWeight(key, Number(event.target.value))}
                    />
                    <strong>{Math.round(config.weights[key] * 100)}%</strong>
                  </label>
                ))}
              </div>
            </div>

            <div className="tool-panel">
              <div className="panel-title">
                <FlaskConical size={19} />
                <h2>阈值与行业清单</h2>
              </div>
              <div className="form-grid">
                <label>
                  <span>最低综合评分</span>
                  <input
                    type="number"
                    value={config.thresholds.min_total_score}
                    onChange={(event) => updateThreshold("min_total_score", Number(event.target.value))}
                  />
                </label>
                <label>
                  <span>最多结果数</span>
                  <input
                    type="number"
                    value={config.thresholds.max_results}
                    onChange={(event) => updateThreshold("max_results", Number(event.target.value))}
                  />
                </label>
                <label>
                  <span>最低成交额</span>
                  <input
                    type="number"
                    value={config.thresholds.min_turnover}
                    onChange={(event) => updateThreshold("min_turnover", Number(event.target.value))}
                  />
                </label>
                <label>
                  <span>最高 PE</span>
                  <input
                    type="number"
                    value={config.thresholds.max_pe ?? ""}
                    onChange={(event) =>
                      updateThreshold("max_pe", event.target.value === "" ? null : Number(event.target.value))
                    }
                  />
                </label>
              </div>
              <label className="textarea-label">
                <span>夕阳/谨慎行业清单</span>
                <textarea
                  value={config.sunset_industries.join("\n")}
                  onChange={(event) =>
                    setConfig((current) => ({
                      ...current,
                      sunset_industries: event.target.value
                        .split(/\n|,/)
                        .map((item) => item.trim())
                        .filter(Boolean)
                    }))
                  }
                />
              </label>
              <div className="action-row">
                <button
                  className={busyAction === "save" ? "primary-action loading" : "primary-action"}
                  onClick={handleSaveConfig}
                  disabled={busy}
                  type="button"
                >
                  <Save size={18} />
                  {busyAction === "save" ? "保存中" : "保存策略"}
                </button>
                <button
                  className={busyAction === "screen" ? "secondary-action loading" : "secondary-action"}
                  onClick={handleRunScreen}
                  disabled={busy}
                  type="button"
                >
                  <ListFilter size={18} />
                  {busyAction === "screen" ? "评分中" : "重新评分"}
                </button>
              </div>
            </div>
          </section>
        )}

        {view === "results" && (
          <section className="results-layout">
            <ResultsDashboard
              results={topResults}
              displayedResults={displayedResults}
              aiByCode={aiByCode}
              hotSectors={hotSectors}
            />
            <div className="table-toolbar">
              <div>
                <strong>{displayedResults.length}</strong>
                <span>
                  只股票展示，观察名单 {topResults.length} 只，候选池 {results?.total_candidates ?? 0} 只
                </span>
              </div>
              <div className="action-row compact">
                <select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}>
                  {aiPriorityOptions.map((option) => (
                    <option value={option} key={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <button
                  className={busyAction === "screen" ? "secondary-action loading" : "secondary-action"}
                  onClick={handleRunScreen}
                  disabled={busy}
                  type="button"
                >
                  <RefreshCw size={18} />
                  {busyAction === "screen" ? "评分中" : "重新评分"}
                </button>
                <button
                  className={busyAction === "aiAnalysis" ? "secondary-action loading" : "secondary-action"}
                  onClick={handleAiAnalysis}
                  disabled={busy || topResults.length === 0}
                  type="button"
                >
                  <Bot size={18} />
                  {busyAction === "aiAnalysis" ? "复核中" : "AI 复核"}
                </button>
                <button
                  className={busyAction === "ai" ? "secondary-action loading" : "secondary-action"}
                  onClick={handleAiRemarks}
                  disabled={busy}
                  type="button"
                >
                  <Bot size={18} />
                  {busyAction === "ai" ? "生成中" : "AI 备注"}
                </button>
              </div>
            </div>
            <ResultTable
              results={displayedResults}
              selectedCode={selected?.code ?? null}
              aiByCode={aiByCode}
              onSelect={(item) => {
                setSelected(item);
                setView("detail");
              }}
            />
          </section>
        )}

        {view === "detail" && (
          <DetailView item={selected ?? topResults[0] ?? null} aiAnalysis={aiByCode.get((selected ?? topResults[0])?.code ?? "")} />
        )}

        {view === "holdings" && (
          <HoldingsView
            holdings={holdings}
            analysis={holdingAnalysis}
            busy={busy}
            busyAction={busyAction}
            onAdd={handleAddHolding}
            onAnalyze={handleAnalyzeHoldings}
            onChange={handleUpdateHolding}
            onRemove={handleRemoveHolding}
            onSave={handleSaveHoldings}
          />
        )}
      </main>
    </div>
  );
}

function HoldingsView({
  holdings,
  analysis,
  busy,
  busyAction,
  onAdd,
  onAnalyze,
  onChange,
  onRemove,
  onSave
}: {
  holdings: HoldingItem[];
  analysis: HoldingAnalysisResponse | null;
  busy: boolean;
  busyAction: string | null;
  onAdd: () => void;
  onAnalyze: () => void;
  onChange: (index: number, patch: Partial<HoldingItem>) => void;
  onRemove: (index: number) => void;
  onSave: () => void;
}) {
  const validCount = holdings.filter((item) => item.code.trim() && item.cost_price > 0).length;
  const totalCost = holdings.reduce((sum, item) => sum + item.cost_price * Math.max(0, item.quantity || 0), 0);
  const reviewedCount = analysis?.analyses.length ?? 0;

  return (
    <section className="holdings-layout">
      <div className="dashboard-strip holdings-strip">
        <div className="dashboard-card primary">
          <div>
            <span>有效持仓</span>
            <strong>{validCount}</strong>
          </div>
          <Briefcase size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>录入成本</span>
            <strong>{formatMoney(totalCost)}</strong>
          </div>
          <CircleDollarSign size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>已复核</span>
            <strong>{reviewedCount}</strong>
          </div>
          <Bot size={22} />
          <small>{analysis?.message ?? "尚未生成持仓复核"}</small>
        </div>
        <div className="dashboard-card wide">
          <div>
            <span>复核模式</span>
            <strong>条件观察区</strong>
          </div>
          <Target size={22} />
          <small>输出加仓观察、获利减仓、风险复核价位，不生成自动交易指令。</small>
        </div>
      </div>

      <div className="tool-panel holdings-editor">
        <div className="holding-editor-head">
          <div className="panel-title">
            <Briefcase size={19} />
            <h2>持仓录入</h2>
          </div>
          <div className="action-row compact">
            <button className="secondary-action" onClick={onAdd} disabled={busy} type="button">
              <Plus size={18} />
              新增持仓
            </button>
            <button
              className={busyAction === "holdingsSave" ? "secondary-action loading" : "secondary-action"}
              onClick={onSave}
              disabled={busy}
              type="button"
            >
              <Save size={18} />
              {busyAction === "holdingsSave" ? "保存中" : "保存持仓"}
            </button>
            <button
              className={busyAction === "holdingsAnalyze" ? "primary-action loading" : "primary-action"}
              onClick={onAnalyze}
              disabled={busy || validCount === 0}
              type="button"
            >
              <Bot size={18} />
              {busyAction === "holdingsAnalyze" ? "复核中" : "AI 复核持仓"}
            </button>
          </div>
        </div>

        {holdings.length === 0 ? (
          <div className="holding-empty">
            <Briefcase size={28} />
            <strong>还没有录入持仓</strong>
            <span>添加股票代码、成本价、数量和持仓周期后即可生成观察价位。</span>
          </div>
        ) : (
          <div className="holding-form-grid">
            <div className="holding-form-header">
              <span>代码</span>
              <span>名称</span>
              <span>成本价</span>
              <span>数量</span>
              <span>周期</span>
              <span>备注</span>
              <span />
            </div>
            {holdings.map((item, index) => (
              <div className="holding-row" key={item.id || `holding-${index}`}>
                <label>
                  <span>代码</span>
                  <input
                    value={item.code}
                    placeholder="600519"
                    onChange={(event) => onChange(index, { code: event.target.value.trim() })}
                  />
                </label>
                <label>
                  <span>名称</span>
                  <input
                    value={item.name}
                    placeholder="贵州茅台"
                    onChange={(event) => onChange(index, { name: event.target.value })}
                  />
                </label>
                <label>
                  <span>成本价</span>
                  <input
                    min="0"
                    step="0.01"
                    type="number"
                    value={item.cost_price || ""}
                    onChange={(event) => onChange(index, { cost_price: Number(event.target.value) || 0 })}
                  />
                </label>
                <label>
                  <span>数量</span>
                  <input
                    min="0"
                    step="1"
                    type="number"
                    value={item.quantity || ""}
                    onChange={(event) => onChange(index, { quantity: Number(event.target.value) || 0 })}
                  />
                </label>
                <label>
                  <span>周期</span>
                  <select
                    value={item.holding_period}
                    onChange={(event) => onChange(index, { holding_period: event.target.value })}
                  >
                    <option value="short">短线 30 天内</option>
                    <option value="long">长线 2-10 年</option>
                  </select>
                </label>
                <label>
                  <span>备注</span>
                  <input
                    value={item.note}
                    placeholder="原持仓逻辑、关注点"
                    onChange={(event) => onChange(index, { note: event.target.value })}
                  />
                </label>
                <button
                  className="icon-action danger"
                  onClick={() => onRemove(index)}
                  disabled={busy}
                  type="button"
                  title="删除持仓"
                  aria-label="删除持仓"
                >
                  <Trash2 size={17} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <HoldingAnalysisPanel analysis={analysis} />
    </section>
  );
}

function HoldingAnalysisPanel({ analysis }: { analysis: HoldingAnalysisResponse | null }) {
  const items = analysis?.analyses ?? [];

  if (items.length === 0) {
    return (
      <div className="empty-state">
        <Bot size={28} />
        <strong>暂无持仓复核</strong>
        <span>保存持仓后点击 AI 复核持仓，系统会先生成本地规则价位，再交给 AI 做条件化复核。</span>
      </div>
    );
  }

  return (
    <div className="holding-analysis-grid">
      {items.map((item) => (
        <HoldingAnalysisCard item={item} key={item.id} />
      ))}
    </div>
  );
}

function HoldingAnalysisCard({ item }: { item: HoldingAnalysisItem }) {
  const metrics = [
    ["成本价", formatPrice(item.cost_price)],
    ["最新参考", formatPrice(item.last_price)],
    ["持仓市值", formatMoney(item.position_value)],
    ["浮盈亏", formatMoney(item.unrealized_profit)]
  ];

  return (
    <article className="holding-card">
      <header className="holding-card-head">
        <div>
          <h2>
            {item.name}
            <span>{item.code}</span>
          </h2>
          <p>{holdingPeriodLabels[item.holding_period] ?? item.holding_period}</p>
        </div>
        <div className="holding-card-status">
          <span className={holdingPriorityClass(item.priority)}>{item.priority}</span>
          <strong>{item.confidence.toFixed(0)}%</strong>
        </div>
      </header>

      <p className="analysis-summary">{item.summary}</p>

      <div className="holding-metric-grid">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong className={label === "浮盈亏" ? profitClass(item.unrealized_profit) : ""}>{value}</strong>
          </div>
        ))}
        <div>
          <span>浮盈亏率</span>
          <strong className={profitClass(item.unrealized_profit_pct)}>{formatPercent(item.unrealized_profit_pct)}</strong>
        </div>
        <div>
          <span>数量</span>
          <strong>{formatNumber(item.quantity)}</strong>
        </div>
      </div>

      <div className="holding-level-grid">
        {item.plan_levels.map((level) => (
          <div className={holdingLevelClass(level.label)} key={`${item.id}-${level.label}`}>
            <span>{level.label}</span>
            <strong>{formatPrice(level.price)}</strong>
            <em>{level.zone || "待数据补齐"}</em>
            <p>{level.reason}</p>
            <small>{level.condition}</small>
          </div>
        ))}
      </div>

      <div className="analysis-columns">
        <div>
          <h3>短线观点</h3>
          <p className="holding-view-text">{item.short_term_view || "暂无短线观点。"}</p>
        </div>
        <div>
          <h3>长线观点</h3>
          <p className="holding-view-text">{item.long_term_view || "暂无长线观点。"}</p>
        </div>
      </div>

      <div className="analysis-columns">
        <div>
          <h3>执行观察点</h3>
          <ul className="text-list compact-list">
            {item.action_points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3>风险与缺口</h3>
          <ul className="text-list risk compact-list">
            {[...item.risk_flags, ...(item.data_gaps.length ? item.data_gaps.map((gap) => `缺少：${gap}`) : [])].map(
              (risk) => (
                <li key={risk}>{risk}</li>
              )
            )}
          </ul>
        </div>
      </div>

      <p className="research-note">{item.research_only_note}</p>
    </article>
  );
}

function ResultsDashboard({
  results,
  displayedResults,
  aiByCode,
  hotSectors
}: {
  results: ScreenResult[];
  displayedResults: ScreenResult[];
  aiByCode: Map<string, AiStockAnalysis>;
  hotSectors: HotSectorResponse | null;
}) {
  const reviewedCount = results.filter((item) => aiByCode.has(item.code)).length;
  const focusCount = results.filter((item) => aiByCode.get(item.code)?.ai_priority === "重点观察").length;
  const avgTotal = averageScore(results.map((item) => item.total_score));
  const avgSectorHeat = averageScore(results.map((item) => item.score.sector_heat));
  const fundReadyCount = results.filter((item) => String(item.metrics.fund_validation ?? "").includes("验证")).length;
  const topSector = hotSectors?.sectors[0];

  return (
    <div className="dashboard-strip">
      <div className="dashboard-card primary">
        <div>
          <span>观察名单均分</span>
          <strong>{avgTotal.toFixed(1)}</strong>
        </div>
        <Gauge size={22} />
      </div>
      <div className="dashboard-card">
        <div>
          <span>当前展示</span>
          <strong>{displayedResults.length}</strong>
        </div>
        <Layers3 size={22} />
      </div>
      <div className="dashboard-card">
        <div>
          <span>AI 重点观察</span>
          <strong>{focusCount}</strong>
        </div>
        <BadgeCheck size={22} />
        <small>{reviewedCount}/{results.length || 0} 已复核</small>
      </div>
      <div className="dashboard-card">
        <div>
          <span>资金验证覆盖</span>
          <strong>{fundReadyCount}</strong>
        </div>
        <CircleDollarSign size={22} />
      </div>
      <div className="dashboard-card wide">
        <div>
          <span>最热板块</span>
          <strong>{topSector?.sector ?? "-"}</strong>
        </div>
        <BarChart3 size={22} />
        <ScoreBar score={topSector?.heat_score ?? avgSectorHeat} />
      </div>
    </div>
  );
}

function ScoreBar({ score, label }: { score: number | null | undefined; label?: string }) {
  const value = clampScore(score);
  return (
    <div className={`score-bar ${scoreTone(value)}`} title={label}>
      <i style={{ width: `${value}%` }} />
    </div>
  );
}

function EvidenceStack({ item }: { item: ScreenResult }) {
  return (
    <div className="evidence-stack">
      {scoreKeys.map((key) => (
        <div key={key}>
          <span>{scoreLabels[key]}</span>
          <ScoreBar score={item.score[key]} />
          <strong>{item.score[key]}</strong>
        </div>
      ))}
    </div>
  );
}

function ResultTable({
  results,
  selectedCode,
  aiByCode,
  onSelect
}: {
  results: ScreenResult[];
  selectedCode: string | null;
  aiByCode: Map<string, AiStockAnalysis>;
  onSelect: (item: ScreenResult) => void;
}) {
  if (results.length === 0) {
    return (
      <div className="empty-state">
        <ListFilter size={28} />
        <strong>暂无观察名单</strong>
        <span>导入 CSV 或刷新免费行情后重新评分。</span>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>股票</th>
            <th>综合</th>
            <th>AI 复核</th>
            <th>板块</th>
            <th>评分拆解</th>
            <th>主力验证</th>
            <th>估值/分红</th>
            <th>风险</th>
          </tr>
        </thead>
        <tbody>
          {results.map((item) => (
            <tr
              key={item.code}
              className={selectedCode === item.code ? "selected-row" : ""}
              onClick={() => onSelect(item)}
            >
              <td>
                <strong>{item.name}</strong>
                <span>{item.code}</span>
              </td>
              <td>
                <span className={scoreClass(item.total_score)}>{item.total_score}</span>
              </td>
              <td>
                {aiByCode.has(item.code) ? (
                  <span className={aiPriorityClass(aiByCode.get(item.code)?.ai_priority)}>
                    {aiByCode.get(item.code)?.ai_priority}
                  </span>
                ) : (
                  <span className="ai-priority muted">未复核</span>
                )}
                {aiByCode.has(item.code) && <span>{aiByCode.get(item.code)?.confidence.toFixed(0)}%</span>}
              </td>
              <td className="sector-cell">
                <strong>{item.sector}</strong>
                <span>{item.industry}</span>
              </td>
              <td>
                <EvidenceStack item={item} />
              </td>
              <td>
                <span className="fund-tag">{item.metrics.fund_validation ?? "-"}</span>
              </td>
              <td>
                <div className="valuation-pair">
                  <span>PE {formatNumber(item.metrics.pe)}</span>
                  <span>息 {formatNumber(item.metrics.dividend_yield, "%")}</span>
                </div>
              </td>
              <td>
                <span className="risk-pill">{item.risks[0]}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HotSectorsView({ data }: { data: HotSectorResponse | null }) {
  const sectors = data?.sectors ?? [];
  if (sectors.length === 0) {
    return (
      <div className="empty-state">
        <Flame size={28} />
        <strong>暂无热点板块</strong>
        <span>刷新免费行情或导入带板块字段的 CSV 后查看。</span>
      </div>
    );
  }

  return (
    <section className="hot-layout">
      <HotSectorPulse sectors={sectors} />
      <div className="table-toolbar">
        <div>
          <strong>{sectors.length}</strong>
          <span>个热点板块，覆盖 {data?.total_sectors ?? 0} 个板块</span>
        </div>
        <span>公开资金流用于验证，不代表买卖建议。</span>
      </div>
      <div className="sector-grid">
        {sectors.map((sector) => {
          const labels = fundFlowLabels(sector.fund_flow_source);
          return (
            <article className="sector-card" key={sector.sector}>
              <header>
                <div>
                  <h2>{sector.sector}</h2>
                  <span>{sector.stock_count} 只成分股</span>
                </div>
                <span className={scoreClass(sector.heat_score)}>{sector.heat_score}</span>
              </header>
              <ScoreBar score={sector.heat_score} label={`${sector.sector} 热度`} />
              <div className="sector-metrics">
                <div>
                  <span>涨跌幅</span>
                  <strong>{formatNumber(sector.pct_change, "%")}</strong>
                </div>
                <div>
                  <span>成交额</span>
                  <strong>{formatMoney(sector.turnover)}</strong>
                </div>
                <div>
                  <span>{labels.sectorFlow}</span>
                  <strong>{formatMoney(sector.main_net_inflow)}</strong>
                </div>
                <div>
                  <span>{labels.sectorFlowPct}</span>
                  <strong>{formatNumber(sector.main_net_inflow_pct, "%")}</strong>
                </div>
                <div>
                  <span>上涨占比</span>
                  <strong>{formatNumber(sector.active_stock_ratio, "%")}</strong>
                </div>
                <div>
                  <span>资金口径</span>
                  <strong>{sector.fund_flow_source ?? "-"}</strong>
                </div>
                <div>
                  <span>资金验证</span>
                  <strong>{sector.fund_validation}</strong>
                </div>
              </div>
              <ul className="text-list compact-list">
                {sector.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
              <div className="leader-list">
                {sector.leaders.map((leader) => (
                  <div key={`${sector.sector}-${leader.code}`}>
                    <strong>
                      {leader.name}
                      <span>{leader.code}</span>
                    </strong>
                    <p>{leader.basis}</p>
                  </div>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function HotSectorPulse({ sectors }: { sectors: HotSectorResponse["sectors"] }) {
  const top = sectors.slice(0, 8);
  return (
    <div className="hot-pulse">
      <div>
        <Flame size={20} />
        <strong>板块热度分布</strong>
        <span>前 8 个热点板块</span>
      </div>
      <div className="pulse-bars">
        {top.map((sector) => (
          <div key={`pulse-${sector.sector}`}>
            <span>{sector.sector}</span>
            <ScoreBar score={sector.heat_score} />
            <strong>{sector.heat_score}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailView({ item, aiAnalysis }: { item: ScreenResult | null; aiAnalysis?: AiStockAnalysis }) {
  const [levels, setLevels] = useState<TechnicalLevelsResponse | null>(null);
  const [levelMessage, setLevelMessage] = useState("正在加载技术参考价位");
  const [analysis, setAnalysis] = useState<TechnicalAnalysisResponse | null>(null);
  const [analysisMessage, setAnalysisMessage] = useState("正在加载技术可能性分析");

  useEffect(() => {
    if (!item) return;
    let alive = true;
    setLevels(null);
    setAnalysis(null);
    setLevelMessage("正在加载技术参考价位");
    setAnalysisMessage("正在加载技术可能性分析");
    api
      .technicalLevels(item.code)
      .then((data) => {
        if (!alive) return;
        setLevels(data);
        setLevelMessage(data.levels.length > 0 ? "技术参考价位已更新" : "暂无足够历史数据");
      })
      .catch((error) => {
        if (!alive) return;
        setLevelMessage(error instanceof Error ? error.message : "技术参考价位加载失败");
      });
    api
      .technicalAnalysis(item.code)
      .then((data) => {
        if (!alive) return;
        setAnalysis(data);
        setAnalysisMessage("技术可能性分析已更新");
      })
      .catch((error) => {
        if (!alive) return;
        setAnalysisMessage(error instanceof Error ? error.message : "技术可能性分析加载失败");
      });
    return () => {
      alive = false;
    };
  }, [item?.code]);

  if (!item) {
    return (
      <div className="empty-state">
        <Search size={28} />
        <strong>未选择股票</strong>
        <span>先生成观察名单，再查看个股详情。</span>
      </div>
    );
  }

  const fundSource = String(item.metrics.fund_flow_source ?? "");
  const fundNote = String(item.metrics.fund_flow_note ?? "");
  const labels = fundFlowLabels(fundSource);
  const metrics = [
    ["总市值", formatNumber(item.metrics.market_cap)],
    ["成交额", formatNumber(item.metrics.turnover)],
    ["涨跌幅", formatNumber(item.metrics.pct_change, "%")],
    ["量比", formatNumber(item.metrics.volume_ratio)],
    ["PE", formatNumber(item.metrics.pe)],
    ["PB", formatNumber(item.metrics.pb)],
    ["股息率", formatNumber(item.metrics.dividend_yield, "%")],
    ["ROE", formatNumber(item.metrics.roe, "%")],
    ["营收增长", formatNumber(item.metrics.revenue_growth, "%")],
    ["利润增长", formatNumber(item.metrics.profit_growth, "%")],
    ["现金流比", formatNumber(item.metrics.cashflow_ratio)],
    ["历史PE分位", formatNumber(item.metrics.historical_pe_percentile, "%")],
    [labels.flow, formatMoney(item.metrics.main_net_inflow)],
    [labels.flowPct, formatNumber(item.metrics.main_net_inflow_pct, "%")],
    ["大单净流入", formatMoney(item.metrics.large_net_inflow)],
    [labels.sectorFlow, formatMoney(item.metrics.derived_sector_main_net_inflow)]
  ];

  return (
    <section className="detail-layout">
      <div className="detail-head">
        <div>
          <h2>
            {item.name}
            <span>{item.code}</span>
          </h2>
          <p>
            {item.sector} / {item.industry}
          </p>
        </div>
        <span className={scoreClass(item.total_score)}>{item.total_score}</span>
      </div>

      <div className="score-grid">
        {(Object.keys(scoreLabels) as Array<keyof ScoreWeights>).map((key) => (
          <div className="score-line" key={key}>
            <span>{scoreLabels[key]}</span>
            <div>
              <i style={{ width: `${item.score[key]}%` }} />
            </div>
            <strong>{item.score[key]}</strong>
          </div>
        ))}
      </div>

      <div className="detail-columns">
        <div className="tool-panel">
          <div className="panel-title">
            <ListFilter size={19} />
            <h2>入选理由</h2>
          </div>
          <ul className="text-list">
            {item.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
        <div className="tool-panel">
          <div className="panel-title">
            <ShieldAlert size={19} />
            <h2>风险提示</h2>
          </div>
          <ul className="text-list risk">
            {item.risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="metric-grid">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <div className="tool-panel">
        <div className="panel-title">
          <Activity size={19} />
          <h2>{labels.panelTitle}</h2>
        </div>
        <div className="fund-summary">
          <div>
            <span>验证结论</span>
            <strong>{item.metrics.fund_validation ?? "-"}</strong>
          </div>
          <div>
            <span>验证评分</span>
            <strong>{formatNumber(item.metrics.fund_validation_score)}</strong>
          </div>
          <div>
            <span>{labels.sectorFlowPct}</span>
            <strong>{formatNumber(item.metrics.derived_sector_main_net_inflow_pct, "%")}</strong>
          </div>
          <div>
            <span>资金口径</span>
            <strong>{fundSource || "未补充"}</strong>
          </div>
          <div>
            <span>口径说明</span>
            <strong>{fundNote || "暂无说明"}</strong>
          </div>
        </div>
      </div>

      <TechnicalLevelsPanel levels={levels} message={levelMessage} />

      <TechnicalAnalysisPanel analysis={analysis} message={analysisMessage} />

      <AiResearchPanel analysis={aiAnalysis ?? null} />

      <div className="ai-panel">
        <div className="panel-title">
          <Bot size={19} />
          <h2>AI 辅助备注</h2>
        </div>
        <p>{item.ai_remark ?? "尚未生成 AI 备注。"}</p>
      </div>
    </section>
  );
}

function AiResearchPanel({ analysis }: { analysis: AiStockAnalysis | null }) {
  return (
    <div className="tool-panel ai-research-panel">
      <div className="panel-title">
        <Bot size={19} />
        <h2>AI 研究复核</h2>
      </div>
      {!analysis ? (
        <div className="inline-state">尚未生成 AI 研究复核。</div>
      ) : (
        <>
          <div className="ai-research-head">
            <span className={aiPriorityClass(analysis.ai_priority)}>{analysis.ai_priority}</span>
            <strong>{analysis.confidence.toFixed(0)}%</strong>
          </div>
          <p className="analysis-summary">{analysis.summary}</p>

          <div className="analysis-columns">
            <div>
              <h3>支撑点</h3>
              <ul className="text-list compact-list">
                {analysis.supporting_points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>反证</h3>
              <ul className="text-list risk compact-list">
                {analysis.contradictions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>

          <div className="ai-level-grid">
            {analysis.key_price_levels.map((level) => (
              <div key={`${level.label}-${level.price ?? level.reason}`}>
                <span>{level.label}</span>
                <strong>{formatPrice(level.price)}</strong>
                <p>{level.reason}</p>
              </div>
            ))}
          </div>

          <div className="analysis-columns">
            <div>
              <h3>复核说明</h3>
              <ul className="text-list compact-list">
                <li>{analysis.fund_flow_comment}</li>
                <li>{analysis.valuation_comment}</li>
                <li>{analysis.dividend_comment}</li>
                <li>{analysis.sector_position_comment}</li>
              </ul>
            </div>
            <div>
              <h3>数据缺口</h3>
              <ul className="text-list risk compact-list">
                {(analysis.data_gaps.length > 0 ? analysis.data_gaps : ["暂无明显缺口"]).map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </div>
          </div>
          <p className="research-note">{analysis.research_only_note}</p>
        </>
      )}
    </div>
  );
}

function TechnicalAnalysisPanel({
  analysis,
  message
}: {
  analysis: TechnicalAnalysisResponse | null;
  message: string;
}) {
  const probabilityRows = [
    ["上涨", analysis?.upside_probability ?? 0, "bullish"],
    ["下跌", analysis?.downside_probability ?? 0, "bearish"],
    ["震荡", analysis?.sideways_probability ?? 0, "neutral"]
  ] as const;

  return (
    <div className="tool-panel analysis-panel">
      <div className="panel-title">
        <Activity size={19} />
        <h2>短期技术可能性</h2>
      </div>
      {!analysis ? (
        <div className="inline-state">{message}</div>
      ) : (
        <>
          <div className="analysis-head">
            <div>
              <span>短期倾向</span>
              <strong>{analysis.trend_label}</strong>
            </div>
            <span className={scoreClass(analysis.trend_score)}>{analysis.trend_score}</span>
          </div>
          <p className="analysis-summary">{analysis.summary}</p>
          <div className="probability-grid">
            {probabilityRows.map(([label, value, direction]) => (
              <div key={label} className={directionClass(direction)}>
                <span>{label}概率</span>
                <strong>{value.toFixed(1)}%</strong>
                <i style={{ width: `${Math.max(4, value)}%` }} />
              </div>
            ))}
          </div>

          <div className="analysis-columns">
            <LevelMiniList title="附近支撑" levels={analysis.support_levels} />
            <LevelMiniList title="附近压力" levels={analysis.resistance_levels} />
          </div>

          <div className="pattern-grid">
            {analysis.patterns.map((pattern) => (
              <div className={directionClass(pattern.direction)} key={pattern.key}>
                <div>
                  <strong>{pattern.label}</strong>
                  <span>{pattern.confidence.toFixed(0)}%</span>
                </div>
                <p>{pattern.description}</p>
              </div>
            ))}
          </div>

          <div className="analysis-columns">
            <div>
              <h3>量价信号</h3>
              <div className="signal-list">
                {analysis.signals.map((signal) => (
                  <div className={directionClass(signal.direction)} key={`${signal.label}-${signal.value}`}>
                    <span>{signal.label}</span>
                    <strong>{signal.value}</strong>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3>风险观察</h3>
              <ul className="text-list risk compact-list">
                {analysis.risks.map((risk) => (
                  <li key={risk}>{risk}</li>
                ))}
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function LevelMiniList({ title, levels }: { title: string; levels: TechnicalLevelsResponse["levels"] }) {
  return (
    <div>
      <h3>{title}</h3>
      <div className="level-mini-list">
        {levels.length === 0 && <span>暂无足够参考位</span>}
        {levels.map((level) => (
          <div key={`${title}-${level.key}`}>
            <strong>{level.label}</strong>
            <span>
              {formatPrice(level.price)} / {level.distance_pct > 0 ? "+" : ""}
              {level.distance_pct.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TechnicalLevelsPanel({
  levels,
  message
}: {
  levels: TechnicalLevelsResponse | null;
  message: string;
}) {
  return (
    <div className="tool-panel technical-panel">
      <div className="panel-title">
        <Target size={19} />
        <h2>技术参考价位</h2>
      </div>
      <div className="level-summary">
        <div>
          <span>最新收盘</span>
          <strong>{formatPrice(levels?.last_close)}</strong>
        </div>
        <div>
          <span>交易日</span>
          <strong>{levels?.trade_date ?? "-"}</strong>
        </div>
        <div>
          <span>数据源</span>
          <strong>{levels?.source ?? "baostock"}</strong>
        </div>
      </div>
      <div className="level-table">
        <table>
          <thead>
            <tr>
              <th>指标</th>
              <th>价位</th>
              <th>相对收盘</th>
              <th>位置</th>
              <th>依据</th>
            </tr>
          </thead>
          <tbody>
            {levels?.levels.map((level) => (
              <tr key={level.key}>
                <td>
                  <strong>{level.label}</strong>
                </td>
                <td>{formatPrice(level.price)}</td>
                <td className={level.distance_pct <= 0 ? "distance below" : "distance above"}>
                  {level.distance_pct > 0 ? "+" : ""}
                  {level.distance_pct.toFixed(2)}%
                </td>
                <td>{level.position}</td>
                <td>{level.basis}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(!levels || levels.levels.length === 0) && <div className="inline-state">{message}</div>}
      </div>
    </div>
  );
}

export default App;
