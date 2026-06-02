import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { toPng } from "html-to-image";
import {
  Bot,
  Activity,
  BadgeCheck,
  BarChart3,
  Briefcase,
  CircleDollarSign,
  Copyright,
  Database,
  Download,
  ExternalLink,
  FileUp,
  Flame,
  FlaskConical,
  Gauge,
  Handshake,
  Info,
  Layers3,
  ListFilter,
  Mail,
  Plus,
  QrCode,
  RefreshCw,
  Save,
  Search,
  Settings2,
  Palette,
  ShieldCheck,
  ShieldAlert,
  Trash2,
  Target,
  SlidersHorizontal,
  TrendingUp
} from "lucide-react";
import { api } from "./lib/api";
import type {
  AmbushBrief,
  AmbushBriefItem,
  AmbushConfig,
  AmbushItem,
  AmbushPipelineResponse,
  AmbushSignalDetail,
  AppConfig,
  AiAnalysisResponse,
  AiStockAnalysis,
  DataStatus,
  HoldingAnalysisItem,
  HoldingAnalysisResponse,
  HoldingItem,
  HotSectorResponse,
  KlineScenarioResponse,
  MomentumWatchItem,
  MomentumWatchResponse,
  ScreenResponse,
  ScreenResult,
  ScoreWeights,
  TechnicalAnalysisResponse,
  TechnicalLevelsResponse,
  WatchlistItem
} from "./lib/types";

type View = "data" | "hot" | "momentum" | "ambush" | "strategy" | "results" | "watchlist" | "detail" | "holdings" | "about";
type CaptureMode = "single" | "long" | null;

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

function fileSafeTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}

function closestCaptureElement(target: EventTarget | null, selector: string) {
  return target instanceof Element ? (target.closest(selector) as HTMLElement | null) : null;
}

function scoreClass(score: number) {
  if (score >= 75) return "score strong";
  if (score >= 60) return "score steady";
  return "score weak";
}

function heatClass(score: number) {
  if (score >= 80) return "hot-80";
  if (score >= 60) return "hot-60";
  if (score >= 40) return "hot-40";
  return "hot-0";
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

function formatSignedPercent(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
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

function createWatchlistItem(): WatchlistItem {
  return {
    id: `watch-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`,
    code: "",
    name: "",
    group: "默认",
    note: "",
    added_at: ""
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

function triggerClass(level: string) {
  if (level === "强异动") return "trigger-pill strong";
  if (level === "活跃跟踪") return "trigger-pill steady";
  return "trigger-pill watch";
}

function detailFromMomentum(item: MomentumWatchItem): ScreenResult {
  return {
    code: item.code,
    name: item.name,
    sector: item.sector,
    industry: item.industry,
    total_score: item.momentum_score,
    score: {
      sector_heat: clampScore(item.metrics.short_sector_heat_score),
      leadership: clampScore(item.metrics.turnover_rank),
      quality: 50,
      valuation: 50,
      dividend: 50,
      industry_risk: clampScore(100 - item.momentum_score * 0.35)
    },
    reasons: item.reasons,
    risks: item.risks,
    metrics: {
      ...item.metrics,
      fund_validation: item.metrics.fund_validation ?? item.trigger_level,
      fund_validation_score: item.metrics.fund_validation_score ?? item.momentum_score
    },
    ai_remark: null
  };
}

function detailFromWatchlist(item: WatchlistItem): ScreenResult {
  return {
    code: item.code,
    name: item.name || item.code || "自选股",
    sector: "自选股池",
    industry: item.group || "默认",
    total_score: 0,
    score: {
      sector_heat: 0,
      leadership: 0,
      quality: 0,
      valuation: 0,
      dividend: 0,
      industry_risk: 0
    },
    reasons: ["用户手动加入自选股池，本地持久化保存。"],
    risks: ["未进入当前筛选结果时，详情页仅展示可获取的行情和技术参考数据。"],
    metrics: {},
    ai_remark: item.note || null
  };
}

function App() {
  const [view, setView] = useState<View>("data");
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [config, setConfig] = useState<AppConfig>(defaultConfig);
  const [results, setResults] = useState<ScreenResponse | null>(null);
  const [hotSectors, setHotSectors] = useState<HotSectorResponse | null>(null);
  const [momentumWatchlist, setMomentumWatchlist] = useState<MomentumWatchResponse | null>(null);
  const [ambushPipeline, setAmbushPipeline] = useState<AmbushPipelineResponse | null>(null);
  const [ambushBrief, setAmbushBrief] = useState<AmbushBrief | null>(null);
  const [aiAnalysis, setAiAnalysis] = useState<AiAnalysisResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [holdings, setHoldings] = useState<HoldingItem[]>([]);
  const [holdingAnalysis, setHoldingAnalysis] = useState<HoldingAnalysisResponse | null>(null);
  const [priorityFilter, setPriorityFilter] = useState("全部");
  const [selected, setSelected] = useState<ScreenResult | null>(null);
  const [message, setMessage] = useState("正在连接本地服务");
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [captureMode, setCaptureMode] = useState<CaptureMode>(null);
  const [captureTarget, setCaptureTarget] = useState<HTMLElement | null>(null);
  const [captureSelection, setCaptureSelection] = useState<HTMLElement[]>([]);
  const captureSelectionRef = useRef<HTMLElement[]>([]);
  const [theme, setTheme] = useState<"jade" | "amber">(() => {
    try { return (localStorage.getItem("gupiao-theme") as "jade" | "amber") ?? "jade"; }
    catch { return "jade"; }
  });
  const [ambushDetail, setAmbushDetail] = useState<AmbushItem | null>(null);

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
    const [
      statusData,
      configData,
      resultData,
      sectorData,
      momentumData,
      analysisData,
      watchlistData,
      holdingData,
      holdingReviewData,
      ambushData,
      briefData
    ] =
      await Promise.all([
        api.status(),
        api.config(),
        api.results(),
        api.hotSectors(),
        api.momentumWatchlist(),
        api.aiAnalysis(),
        api.watchlist(),
        api.holdings(),
        api.holdingAnalysis(),
        api.ambushPipeline().catch(() => null),
        api.ambushBrief().catch(() => null)
      ]);
    setStatus(statusData);
    setConfig(configData);
    setResults(resultData);
    setHotSectors(sectorData);
    setMomentumWatchlist(momentumData);
    setAmbushPipeline(ambushData);
    setAmbushBrief(briefData);
    setAiAnalysis(analysisData);
    setWatchlist(watchlistData.watchlist);
    setHoldings(holdingData.holdings);
    setHoldingAnalysis(holdingReviewData);
    syncSelected(resultData.results);
  }

  // 主题切换：同步 data-theme 到 html 元素
  useEffect(() => {
    if (theme === "amber") {
      document.documentElement.dataset.theme = "amber";
    } else {
      delete document.documentElement.dataset.theme;
    }
    try { localStorage.setItem("gupiao-theme", theme); }
    catch { /* noop */ }
  }, [theme]);

  useEffect(() => {
    loadAll()
      .then(() => setMessage("本地服务已连接"))
      .catch((error) => setMessage(error instanceof Error ? error.message : "本地服务连接失败"));
  }, []);

  // 进入潜伏视图时自动刷新简报
  useEffect(() => {
    if (view !== "ambush") return;
    api.ambushBrief()
      .then((data) => {
        // 如果缓存简报已阅或无简报，尝试重新计算
        if (!data.has_unseen) {
          return api.refreshBrief();
        }
        return data;
      })
      .then((data) => setAmbushBrief(data))
      .catch(() => {});
  }, [view]);

  function syncCaptureSelection(next: HTMLElement[]) {
    const current = captureSelectionRef.current;
    for (const element of current) {
      if (!next.includes(element)) {
        element.classList.remove("capture-selected");
        element.removeAttribute("data-capture-order");
      }
    }
    next.forEach((element, index) => {
      element.classList.add("capture-selected");
      element.setAttribute("data-capture-order", String(index + 1));
    });
    captureSelectionRef.current = next;
    setCaptureSelection(next);
  }

  function clearCaptureSelection() {
    syncCaptureSelection([]);
  }

  function switchCaptureMode(mode: Exclude<CaptureMode, null>) {
    clearCaptureSelection();
    setCaptureMode((current) => {
      const next = current === mode ? null : mode;
      setMessage(
        next === "single"
          ? "截图模式：移动到想保存的信息块，点击后自动导出 PNG，按 Esc 退出"
          : next === "long"
            ? "长图模式：按顺序点击多个信息块加入长图，再点导出长图"
            : "截图模式已退出"
      );
      return next;
    });
  }

  useEffect(() => {
    if (!captureMode) {
      setCaptureTarget(null);
      return;
    }

    const captureSelector =
      ".tool-panel, .ai-panel, .table-toolbar, .table-wrap, .dashboard-strip, .dashboard-card, .hot-pulse, .sector-card, .holding-card, .detail-head";

    function cleanupTarget() {
      setCaptureTarget((current) => {
        current?.classList.remove("capture-hover");
        return null;
      });
    }

    function handlePointerMove(event: PointerEvent) {
      const element = closestCaptureElement(event.target, captureSelector);
      setCaptureTarget((current) => {
        if (current === element) return current;
        current?.classList.remove("capture-hover");
        element?.classList.add("capture-hover");
        return element;
      });
    }

    async function handleClick(event: MouseEvent) {
      const element = closestCaptureElement(event.target, captureSelector);
      if (!element) return;
      event.preventDefault();
      event.stopPropagation();
      if (captureMode === "single") {
        await exportCapture(element);
        return;
      }

      const current = captureSelectionRef.current;
      const exists = current.includes(element);
      const next = exists ? current.filter((item) => item !== element) : [...current, element];
      syncCaptureSelection(next);
      setMessage(
        exists
          ? `已取消选择，当前 ${next.length} 个信息块`
          : `已加入长图队列：第 ${next.length} 个信息块`
      );
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        cleanupTarget();
        clearCaptureSelection();
        setCaptureMode(null);
        setMessage("截图模式已退出");
      }
    }

    document.body.classList.add("capture-mode");
    document.addEventListener("pointermove", handlePointerMove, true);
    document.addEventListener("click", handleClick, true);
    document.addEventListener("keydown", handleKeyDown, true);
    setMessage(
      captureMode === "single"
        ? "截图模式：移动到想保存的信息块，点击后自动导出 PNG，按 Esc 退出"
        : "长图模式：按顺序点击多个信息块加入长图，再点导出长图"
    );

    return () => {
      cleanupTarget();
      document.body.classList.remove("capture-mode");
      document.removeEventListener("pointermove", handlePointerMove, true);
      document.removeEventListener("click", handleClick, true);
      document.removeEventListener("keydown", handleKeyDown, true);
    };
  }, [captureMode, view]);

  async function renderCapture(element: HTMLElement) {
    return toPng(element, {
      cacheBust: true,
      pixelRatio: Math.min(2, window.devicePixelRatio || 1),
      backgroundColor: "#071015",
      filter: (node) => !(node instanceof HTMLElement && node.classList.contains("capture-hint"))
    });
  }

  function downloadImage(dataUrl: string, name: string) {
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = name;
    link.click();
  }

  function loadImage(dataUrl: string) {
    return new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("图片加载失败"));
      image.src = dataUrl;
    });
  }

  async function exportCapture(element: HTMLElement) {
    const name = `${view}-${fileSafeTimestamp()}.png`;
    setMessage("正在生成截图 PNG");
    element.classList.remove("capture-hover");
    element.classList.add("capture-exporting");
    try {
      const dataUrl = await renderCapture(element);
      downloadImage(dataUrl, name);
      setMessage(`截图已导出：${name}`);
    } catch (error) {
      setMessage(error instanceof Error ? `截图导出失败：${error.message}` : "截图导出失败");
    } finally {
      element.classList.remove("capture-exporting");
      setCaptureMode(null);
    }
  }

  async function exportLongCapture() {
    const selected = captureSelectionRef.current.filter((element) => document.body.contains(element));
    if (selected.length === 0) {
      setMessage("请先在长图模式中选择至少一个信息块");
      return;
    }

    const name = `${view}-long-${fileSafeTimestamp()}.png`;
    setMessage(`正在拼接长图：${selected.length} 个信息块`);
    setCaptureTarget(null);
    selected.forEach((element) => {
      element.classList.remove("capture-hover", "capture-selected");
      element.removeAttribute("data-capture-order");
      element.classList.add("capture-exporting");
    });

    try {
      const dataUrls = [];
      for (const element of selected) {
        dataUrls.push(await renderCapture(element));
      }
      const images = await Promise.all(dataUrls.map((dataUrl) => loadImage(dataUrl)));
      const gap = 18;
      const padding = 18;
      const width = Math.max(...images.map((image) => image.width)) + padding * 2;
      const height = images.reduce((sum, image) => sum + image.height, padding * 2 + gap * (images.length - 1));
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("浏览器不支持 Canvas 导出");

      context.fillStyle = "#071015";
      context.fillRect(0, 0, width, height);
      let y = padding;
      for (const image of images) {
        context.drawImage(image, padding, y);
        y += image.height + gap;
      }

      downloadImage(canvas.toDataURL("image/png"), name);
      setMessage(`长图已导出：${name}`);
      clearCaptureSelection();
      setCaptureMode(null);
    } catch (error) {
      syncCaptureSelection(selected);
      setMessage(error instanceof Error ? `长图导出失败：${error.message}` : "长图导出失败");
    } finally {
      selected.forEach((element) => element.classList.remove("capture-exporting"));
    }
  }

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

  function openMomentumDetail(item: MomentumWatchItem) {
    const detailItem = topResults.find((result) => result.code === item.code) ?? detailFromMomentum(item);
    setSelected(detailItem);
    setView("detail");
  }

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
      setMomentumWatchlist(await api.momentumWatchlist());
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
      setMomentumWatchlist(await api.momentumWatchlist());
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

  function handleAddWatchlistItem() {
    setWatchlist((current) => [...current, createWatchlistItem()]);
  }

  function handleUpdateWatchlistItem(index: number, patch: Partial<WatchlistItem>) {
    setWatchlist((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function handleRemoveWatchlistItem(index: number) {
    setWatchlist((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  async function handleSaveWatchlist() {
    await withBusy(async () => {
      const data = await api.saveWatchlist(watchlist);
      setWatchlist(data.watchlist);
      return `自选股已保存：${data.watchlist.length} 只`;
    }, "自选股已保存", "正在保存自选股池", "watchlistSave");
  }

  function openWatchlistDetail(item: WatchlistItem) {
    if (!item.code.trim()) return;
    const detailItem = topResults.find((result) => result.code === item.code.trim()) ?? detailFromWatchlist(item);
    setAmbushDetail(null);
    setSelected(detailItem);
    setView("detail");
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
          {navButton("momentum", "短线", <Activity size={18} />)}
          {navButton("ambush", "潜伏", <Target size={18} />)}
          {navButton("strategy", "策略", <SlidersHorizontal size={18} />)}
          {navButton("results", "结果", <ListFilter size={18} />)}
          {navButton("watchlist", "自选", <BadgeCheck size={18} />)}
          {navButton("holdings", "持仓", <Briefcase size={18} />)}
          {navButton("detail", "详情", <Search size={18} />)}
          {navButton("about", "关于", <Info size={18} />)}
        </nav>
        <div className="theme-switch">
          <button
            className={theme === "jade" ? "theme-btn active" : "theme-btn"}
            onClick={() => setTheme("jade")}
            type="button"
            title="翠晶主题"
          >
            <Palette size={16} />
            <span>翠晶</span>
          </button>
          <button
            className={theme === "amber" ? "theme-btn active" : "theme-btn"}
            onClick={() => setTheme("amber")}
            type="button"
            title="琥珀主题"
          >
            <Palette size={16} />
            <span>琥珀</span>
          </button>
        </div>
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
                  : view === "momentum"
                    ? "短线异动"
                    : view === "ambush"
                      ? "潜伏管道"
                      : view === "strategy"
                        ? "策略配置"
                        : view === "results"
                          ? "观察名单"
                          : view === "watchlist"
                            ? "自选股池"
                            : view === "holdings"
                              ? "持仓盯盘"
                              : view === "about"
                                ? "关于项目"
                                : "个股详情"}
            </h1>
            <p>{message}</p>
          </div>
          <div className="status-strip">
            <span className={status?.ok ? "dot ok" : "dot warn"} />
            <span>{status?.source ?? "none"}</span>
            <span>{formatNumber(status?.rows ?? 0)} 行</span>
            <span>{formatDate(status?.last_success_at ?? null)}</span>
            <button
              className={captureMode === "single" ? "capture-action active" : "capture-action"}
              type="button"
              onClick={() => switchCaptureMode("single")}
              title="点选页面信息块并导出 PNG"
            >
              <Download size={16} />
              <span>{captureMode === "single" ? "退出截图" : "截图"}</span>
            </button>
            <button
              className={captureMode === "long" ? "capture-action active" : "capture-action"}
              type="button"
              onClick={() => switchCaptureMode("long")}
              title="批量选择信息块并拼成长图"
            >
              <Layers3 size={16} />
              <span>{captureMode === "long" ? "退出长图" : "长图"}</span>
            </button>
          </div>
        </header>

        {captureMode && (
          <div className="capture-hint">
            <Download size={16} />
            <span>
              {captureMode === "single"
                ? captureTarget
                  ? "点击当前高亮区域导出 PNG"
                  : "移动到要保存的信息块"
                : captureTarget
                  ? `点击加入/取消，已选 ${captureSelection.length} 个`
                  : `长图模式，已选 ${captureSelection.length} 个信息块`}
            </span>
            {captureMode === "long" && (
              <>
                <button type="button" onClick={clearCaptureSelection} disabled={captureSelection.length === 0}>
                  清空
                </button>
                <button type="button" onClick={exportLongCapture} disabled={captureSelection.length === 0}>
                  导出长图
                </button>
              </>
            )}
          </div>
        )}

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

        {view === "momentum" && <MomentumWatchView data={momentumWatchlist} onSelect={openMomentumDetail} />}

        {view === "ambush" && (
          <AmbushPipelineView
            pipeline={ambushPipeline}
            brief={ambushBrief}
            busy={busy}
            busyAction={busyAction}
            onRefresh={async () => {
              await withBusy(
                async () => {
                  const data = await api.runAmbush();
                  setAmbushPipeline(data);
                  const briefData = await api.refreshBrief();
                  setAmbushBrief(briefData);
                },
                "潜伏评分已更新",
                "正在计算潜伏评分",
                "ambushRun"
              );
            }}
            onSelectDetail={(item) => {
              setAmbushDetail(item);
              setView("detail");
            }}
            onMarkSeen={async () => {
              const data = await api.markBriefSeen();
              setAmbushBrief(data);
            }}
          />
        )}

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

        {view === "watchlist" && (
          <WatchlistView
            watchlist={watchlist}
            busy={busy}
            busyAction={busyAction}
            onAdd={handleAddWatchlistItem}
            onChange={handleUpdateWatchlistItem}
            onOpenDetail={openWatchlistDetail}
            onRemove={handleRemoveWatchlistItem}
            onSave={handleSaveWatchlist}
          />
        )}

        {view === "detail" && ambushDetail ? (
          <AmbushDetailView item={ambushDetail} onBack={() => { setAmbushDetail(null); setView("ambush"); }} />
        ) : view === "detail" && (
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

        {view === "about" && <AboutView />}
      </main>
    </div>
  );
}

function AboutView() {
  return (
    <section className="about-layout">
      <div className="tool-panel about-hero">
        <div className="panel-title">
          <Info size={19} />
          <h2>作者介绍</h2>
        </div>
        <div className="about-hero-content">
          <div>
            <span className="about-kicker">qinge5202024 / A 股研究工具</span>
            <h3>把行情、资金、技术位和 AI 复核放进同一个观察台。</h3>
            <p>
              这个项目由 qinge5202024 发起，定位是给普通股民和个人研究者使用的 A 股观察名单工具。
              它不承诺神奇预测，也不输出买卖指令，只尽量把公开数据、筛选逻辑、风险标签和复核理由摆到台面上。
            </p>
          </div>
          <div className="about-contact-actions">
            <a className="about-link" href="mailto:haliqinge@gmail.com">
              <Mail size={18} />
              <span>邮件合作</span>
              <ExternalLink size={15} />
            </a>
            <a
              className="about-link secondary"
              href="https://github.com/qinge5202024/daA/issues"
              target="_blank"
              rel="noreferrer"
            >
              <Handshake size={18} />
              <span>GitHub Issues</span>
              <ExternalLink size={15} />
            </a>
          </div>
        </div>
      </div>

      <div className="about-grid">
        <div className="about-card">
          <Copyright size={22} />
          <h3>版权说明</h3>
          <p>
            Copyright © 2026 qinge5202024. 项目名称、界面设计、筛选逻辑、文档和源码版权归作者所有。
            公开源码不等于放弃版权，也不等于允许拿去包装转卖。
          </p>
        </div>
        <div className="about-card">
          <ShieldCheck size={22} />
          <h3>允许使用</h3>
          <p>
            允许个人学习、研究、自用部署、非商业内部试用，也欢迎提交 Issue、建议和改进 PR。
            二次开发时必须保留作者署名、版权声明、免责声明和禁止转售说明。
          </p>
        </div>
        <div className="about-card danger">
          <ShieldAlert size={22} />
          <h3>禁止二次出售</h3>
          <p>
            禁止将本项目或改名后的衍生版本作为软件、课程资料、训练营赠品、会员工具、SaaS 服务或源码包进行售卖、出租、转授权或付费分发。
          </p>
        </div>
        <div className="about-card">
          <Handshake size={22} />
          <h3>合作联系</h3>
          <ul className="about-contact-list">
            <li>
              <span>邮箱</span>
              <a href="mailto:haliqinge@gmail.com">haliqinge@gmail.com</a>
            </li>
            <li>
              <span>GitHub</span>
              <a href="https://github.com/qinge5202024/daA/issues" target="_blank" rel="noreferrer">
                Issues
              </a>
            </li>
          </ul>
          <p>功能共建、数据源适配、私有化部署、策略模块合作请先联系作者，商业合作必须获得书面授权。</p>
        </div>
        <div className="about-card qr-card">
          <QrCode size={22} />
          <h3>合作微信</h3>
          <img className="about-qr" src="/contact-wechat.jpg" alt="合作微信二维码，微信名黄金" />
          <p>微信名：黄金。扫码添加时请备注来意，例如“项目合作”或“私有化部署”。</p>
        </div>
        <div className="about-card wide">
          <CircleDollarSign size={22} />
          <h3>使用边界</h3>
          <p>
            本工具只用于研究观察，不构成投资建议，不提供买卖点、仓位管理或自动交易。公开免费数据可能延迟、缺失或失真，
            任何交易决策都应由使用者独立判断并自行承担风险。
          </p>
        </div>
      </div>
    </section>
  );
}

function WatchlistView({
  watchlist,
  busy,
  busyAction,
  onAdd,
  onChange,
  onOpenDetail,
  onRemove,
  onSave
}: {
  watchlist: WatchlistItem[];
  busy: boolean;
  busyAction: string | null;
  onAdd: () => void;
  onChange: (index: number, patch: Partial<WatchlistItem>) => void;
  onOpenDetail: (item: WatchlistItem) => void;
  onRemove: (index: number) => void;
  onSave: () => void;
}) {
  const validCount = watchlist.filter((item) => item.code.trim()).length;
  const groups = Array.from(new Set(watchlist.map((item) => item.group.trim()).filter(Boolean)));
  const notedCount = watchlist.filter((item) => item.note.trim()).length;

  return (
    <section className="holdings-layout">
      <div className="dashboard-strip holdings-strip">
        <div className="dashboard-card primary">
          <div>
            <span>自选数量</span>
            <strong>{validCount}</strong>
          </div>
          <BadgeCheck size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>分组数量</span>
            <strong>{groups.length}</strong>
          </div>
          <Layers3 size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>备注记录</span>
            <strong>{notedCount}</strong>
          </div>
          <ListFilter size={22} />
        </div>
        <div className="dashboard-card wide">
          <div>
            <span>本地保护</span>
            <strong>data/watchlist.json</strong>
          </div>
          <Save size={22} />
          <small>自选股单独保存，刷新行情、重新评分、导入 CSV 都不会覆盖。</small>
        </div>
      </div>

      <div className="tool-panel holdings-editor">
        <div className="holding-editor-head">
          <div className="panel-title">
            <BadgeCheck size={19} />
            <h2>自选股池</h2>
          </div>
          <div className="action-row compact">
            <button className="secondary-action" onClick={onAdd} disabled={busy} type="button">
              <Plus size={18} />
              新增自选
            </button>
            <button
              className={busyAction === "watchlistSave" ? "primary-action loading" : "primary-action"}
              onClick={onSave}
              disabled={busy}
              type="button"
            >
              <Save size={18} />
              {busyAction === "watchlistSave" ? "保存中" : "保存自选"}
            </button>
          </div>
        </div>

        {watchlist.length === 0 ? (
          <div className="holding-empty">
            <BadgeCheck size={28} />
            <strong>还没有自选股</strong>
            <span>添加代码和名称后点击保存，之后每次启动都会自动恢复。</span>
          </div>
        ) : (
          <div className="holding-form-grid">
            <div className="holding-form-header watchlist-form-header">
              <span>代码</span>
              <span>名称</span>
              <span>分组</span>
              <span>备注</span>
              <span />
            </div>
            {watchlist.map((item, index) => (
              <div className="holding-row watchlist-row" key={item.id || `watchlist-${index}`}>
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
                  <span>分组</span>
                  <input
                    value={item.group}
                    placeholder="默认"
                    onChange={(event) => onChange(index, { group: event.target.value })}
                  />
                </label>
                <label>
                  <span>备注</span>
                  <input
                    value={item.note}
                    placeholder="关注逻辑、题材、触发条件"
                    onChange={(event) => onChange(index, { note: event.target.value })}
                  />
                </label>
                <div className="watchlist-row-actions">
                  <button
                    className="icon-action"
                    onClick={() => onOpenDetail(item)}
                    disabled={busy || !item.code.trim()}
                    type="button"
                    title="查看详情"
                    aria-label="查看详情"
                  >
                    <Search size={17} />
                  </button>
                  <button
                    className="icon-action danger"
                    onClick={() => onRemove(index)}
                    disabled={busy}
                    type="button"
                    title="删除自选"
                    aria-label="删除自选"
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
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
    { label: "成本价", value: formatPrice(item.cost_price) },
    {
      label: "最新行情价",
      value: formatPrice(item.last_price),
      hint: item.last_price_source ?? "缺少真实行情价"
    },
    { label: "持仓市值", value: formatMoney(item.position_value) },
    { label: "浮盈亏", value: formatMoney(item.unrealized_profit) }
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
        {metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong className={metric.label === "浮盈亏" ? profitClass(item.unrealized_profit) : ""}>
              {metric.value}
            </strong>
            {metric.hint ? <small className="holding-metric-source">{metric.hint}</small> : null}
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

function MomentumWatchView({
  data,
  onSelect
}: {
  data: MomentumWatchResponse | null;
  onSelect: (item: MomentumWatchItem) => void;
}) {
  const items = data?.results ?? [];
  const strongCount = items.filter((item) => item.trigger_level === "强异动").length;
  const avgScore = averageScore(items.map((item) => item.momentum_score));
  const topSector = items.reduce<Record<string, number>>((counter, item) => {
    counter[item.sector] = (counter[item.sector] ?? 0) + 1;
    return counter;
  }, {});
  const leadingSector = Object.entries(topSector).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "-";

  if (items.length === 0) {
    return (
      <div className="empty-state">
        <Activity size={28} />
        <strong>暂无短线异动名单</strong>
        <span>刷新免费行情或导入带涨跌幅、成交额、量比字段的数据后查看。</span>
      </div>
    );
  }

  return (
    <section className="momentum-layout">
      <div className="dashboard-strip momentum-strip">
        <div className="dashboard-card primary">
          <div>
            <span>短线异动均分</span>
            <strong>{avgScore.toFixed(1)}</strong>
          </div>
          <Activity size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>入选数量</span>
            <strong>{items.length}</strong>
          </div>
          <Layers3 size={22} />
          <small>候选池 {data?.total_candidates ?? 0} 只</small>
        </div>
        <div className="dashboard-card">
          <div>
            <span>强异动</span>
            <strong>{strongCount}</strong>
          </div>
          <Flame size={22} />
        </div>
        <div className="dashboard-card wide">
          <div>
            <span>集中板块</span>
            <strong>{leadingSector}</strong>
          </div>
          <BarChart3 size={22} />
          <ScoreBar score={items[0]?.metrics.short_sector_heat_score as number | null | undefined} />
        </div>
      </div>

      <div className="table-toolbar">
        <div>
          <strong>{items.length}</strong>
          <span>只短线异动股票，按量价、资金验证和板块同步性排序</span>
        </div>
        <span>短线异动仅用于研究观察，不构成买卖建议。</span>
      </div>

      <div className="table-wrap momentum-table">
        <table>
          <thead>
            <tr>
              <th>排名</th>
              <th>股票</th>
              <th>异动分</th>
              <th>触发级别</th>
              <th>板块</th>
              <th>量价</th>
              <th>资金验证</th>
              <th>触发因素</th>
              <th>风险</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <MomentumRow item={item} key={item.code} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MomentumRow({ item, onSelect }: { item: MomentumWatchItem; onSelect: (item: MomentumWatchItem) => void }) {
  const labels = fundFlowLabels(item.metrics.fund_flow_source);
  return (
    <tr
      onClick={() => onSelect(item)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(item);
        }
      }}
      tabIndex={0}
    >
      <td>
        <strong>#{item.rank}</strong>
        <span>短线观察</span>
      </td>
      <td>
        <strong>{item.name}</strong>
        <span>{item.code}</span>
      </td>
      <td>
        <span className={scoreClass(item.momentum_score)}>{item.momentum_score}</span>
      </td>
      <td>
        <span className={triggerClass(item.trigger_level)}>{item.trigger_level}</span>
      </td>
      <td className="sector-cell">
        <strong>{item.sector}</strong>
        <span>{item.industry}</span>
      </td>
      <td>
        <div className="momentum-metrics">
          <span>涨跌 {formatPercent(item.metrics.pct_change)}</span>
          <span>量比 {formatNumber(item.metrics.volume_ratio)}</span>
          <span>成交 {formatMoney(item.metrics.turnover)}</span>
        </div>
      </td>
      <td>
        <span className="fund-tag">{item.metrics.fund_validation ?? "-"}</span>
        <span>{labels.flow} {formatMoney(item.metrics.main_net_inflow)}</span>
      </td>
      <td>
        <ul className="inline-list">
          {item.reasons.slice(0, 2).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </td>
      <td>
        <span className="risk-pill">{item.risks[0]}</span>
      </td>
    </tr>
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
            <article className={`sector-card ${heatClass(sector.heat_score)}`} key={sector.sector}>
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
  const [scenario, setScenario] = useState<KlineScenarioResponse | null>(null);
  const [scenarioMessage, setScenarioMessage] = useState("正在加载K线情景分析");

  useEffect(() => {
    if (!item) return;
    let alive = true;
    setLevels(null);
    setAnalysis(null);
    setScenario(null);
    setLevelMessage("正在加载技术参考价位");
    setAnalysisMessage("正在加载技术可能性分析");
    setScenarioMessage("正在加载K线情景分析");
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
    api
      .klineScenario(item.code)
      .then((data) => {
        if (!alive) return;
        setScenario(data);
        setScenarioMessage(data.scenario_bands.length > 0 ? "K线情景分析已更新" : "暂无足够历史样本");
      })
      .catch((error) => {
        if (!alive) return;
        setScenarioMessage(error instanceof Error ? error.message : "K线情景分析加载失败");
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

      <KlineScenarioPanel scenario={scenario} message={scenarioMessage} />

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

function KlineScenarioPanel({
  scenario,
  message
}: {
  scenario: KlineScenarioResponse | null;
  message: string;
}) {
  return (
    <div className="tool-panel scenario-panel">
      <div className="panel-title">
        <Layers3 size={19} />
        <h2>K线情景分析</h2>
      </div>
      {!scenario ? (
        <div className="inline-state">{message}</div>
      ) : (
        <>
          <div className="level-summary scenario-summary">
            <div>
              <span>最新收盘参考</span>
              <strong>{formatPrice(scenario.last_close)}</strong>
            </div>
            <div>
              <span>交易日</span>
              <strong>{scenario.trade_date ?? "-"}</strong>
            </div>
            <div>
              <span>样本窗口</span>
              <strong>{scenario.lookback_days}日</strong>
            </div>
          </div>

          <p className="analysis-summary">{scenario.summary}</p>

          <div className="scenario-context-grid">
            <div>
              <span>趋势语境</span>
              <strong>{scenario.trend_context}</strong>
            </div>
            <div>
              <span>波动状态</span>
              <strong>{scenario.volatility_state}</strong>
            </div>
            <div>
              <span>区间位置</span>
              <strong>{scenario.range_state}</strong>
            </div>
            <div>
              <span>量能状态</span>
              <strong>{scenario.volume_state}</strong>
            </div>
          </div>

          <div className="scenario-band-grid">
            {scenario.scenario_bands.map((band) => (
              <div key={band.horizon_days}>
                <div className="scenario-band-head">
                  <strong>{band.label}</strong>
                  <span>{band.probability_note}</span>
                </div>
                <div className="scenario-prices">
                  <div>
                    <span>上沿情景</span>
                    <strong>{formatPrice(band.upside_price)}</strong>
                    <em>{formatSignedPercent(band.upside_return_pct)}</em>
                  </div>
                  <div>
                    <span>中性情景</span>
                    <strong>{formatPrice(band.base_price)}</strong>
                    <em>{formatSignedPercent(band.base_return_pct)}</em>
                  </div>
                  <div>
                    <span>回撤情景</span>
                    <strong>{formatPrice(band.downside_price)}</strong>
                    <em>{formatSignedPercent(band.downside_return_pct)}</em>
                  </div>
                </div>
                <p>{band.basis}</p>
              </div>
            ))}
          </div>

          <div className="analysis-columns">
            <div>
              <h3>序列信号</h3>
              <div className="signal-list">
                {scenario.sequence_signals.map((signal) => (
                  <div className={directionClass(signal.direction)} key={`${signal.label}-${signal.value}`}>
                    <span>{signal.label}</span>
                    <strong>{signal.value}</strong>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3>数据缺口</h3>
              <ul className="text-list risk compact-list">
                {(scenario.data_gaps.length > 0 ? scenario.data_gaps : ["暂无明显缺口"]).map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </div>
          </div>

          <p className="research-note">{scenario.research_only_note}</p>
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

function BriefPanel({
  brief,
  onMarkSeen,
  onRefreshBrief
}: {
  brief: AmbushBrief | null;
  onMarkSeen: () => void;
  onRefreshBrief: () => void;
}) {
  const [collapsed, setCollapsed] = useState(!brief?.has_unseen);
  // 简报内容变化时自动展开/折叠
  useEffect(() => {
    setCollapsed(!brief?.has_unseen);
  }, [brief?.has_unseen]);

  if (!brief || !brief.has_unseen) {
    if (!brief) {
      return (
        <div className="ambush-brief ambush-brief-empty">
          <span>尚未生成每日简报</span>
          <button className="brief-refresh" onClick={onRefreshBrief} type="button">
            <RefreshCw size={14} />
            计算简报
          </button>
        </div>
      );
    }
    return (
      <div className="ambush-brief ambush-brief-seen">
        <span>今日简报已查阅</span>
        <button className="brief-refresh" onClick={() => setCollapsed(!collapsed)} type="button">
          {collapsed ? "展开查看" : "收起"}
        </button>
        <button className="brief-refresh" onClick={onRefreshBrief} type="button">
          <RefreshCw size={14} />
          刷新
        </button>
      </div>
    );
  }

  const hasItems = brief.new_items_count + brief.promoted_count + brief.expired_count > 0;
  const totalTop = brief.top_ignition.length + brief.top_brewing.length;

  return (
    <div className="ambush-brief">
      <div className="ambush-brief-head" onClick={() => setCollapsed(!collapsed)}>
        <div className="ambush-brief-title">
          <span className="brief-icon">📊</span>
          <h3>每日简报</h3>
          {brief.has_unseen && <span className="brief-unseen-dot" />}
        </div>
        <div className="ambush-brief-counts">
          {brief.new_items_count > 0 && (
            <span className="brief-count new">{brief.new_items_count} 只新发现</span>
          )}
          {brief.promoted_count > 0 && (
            <span className="brief-count promoted">{brief.promoted_count} 只晋升</span>
          )}
          {brief.expired_count > 0 && (
            <span className="brief-count expired">{brief.expired_count} 只失效</span>
          )}
          {!hasItems && <span className="brief-count steady">无变化</span>}
        </div>
        <div className="ambush-brief-actions">
          <button
            className="brief-mark-seen"
            onClick={(e) => { e.stopPropagation(); onMarkSeen(); }}
            type="button"
            title="标记为已读"
          >
            ✓ 已阅
          </button>
          <span className="brief-collapse-icon">{collapsed ? "▼" : "▲"}</span>
        </div>
      </div>

      {!collapsed && (
        <div className="ambush-brief-body">
          {/* 新发现 */}
          {brief.new_items.length > 0 && (
            <div className="brief-section">
              <h4>
                <span className="brief-section-icon new" />
                新发现
                <small>{brief.new_items.length} 只</small>
              </h4>
              <div className="brief-cards">
                {brief.new_items.map((item) => (
                  <BriefCard item={item} key={`new-${item.code}`} />
                ))}
              </div>
            </div>
          )}

          {/* 晋升 */}
          {brief.promoted_items.length > 0 && (
            <div className="brief-section">
              <h4>
                <span className="brief-section-icon promoted" />
                阶段晋升
                <small>{brief.promoted_items.length} 只</small>
              </h4>
              <div className="brief-cards">
                {brief.promoted_items.map((item) => (
                  <BriefCard item={item} key={`promoted-${item.code}`} />
                ))}
              </div>
            </div>
          )}

          {/* 阶段亮点 */}
          {(brief.top_ignition.length > 0 || brief.top_brewing.length > 0) && (
            <div className="brief-section">
              <h4>
                <span className="brief-section-icon highlight" />
                阶段亮点
                <small>各阶段评分最高</small>
              </h4>
              <div className="brief-cards">
                {brief.top_ignition.map((item) => (
                  <BriefCard item={item} key={`top-ig-${item.code}`} highlight />
                ))}
                {brief.top_brewing.map((item) => (
                  <BriefCard item={item} key={`top-br-${item.code}`} />
                ))}
              </div>
            </div>
          )}

          {/* 失效 */}
          {brief.expired_items.length > 0 && (
            <div className="brief-section">
              <h4>
                <span className="brief-section-icon expired" />
                已失效
                <small>{brief.expired_items.length} 只</small>
              </h4>
              <div className="brief-cards">
                {brief.expired_items.map((item) => (
                  <BriefCard item={item} key={`expired-${item.code}`} dimmed />
                ))}
              </div>
            </div>
          )}

          {!hasItems && !totalTop && (
            <div className="brief-empty-state">
              <span>管道数据已就绪，暂无阶段性变化</span>
              <span className="brief-empty-hint">运行刷新后会自动对比生成新发现</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BriefCard({ item, highlight, dimmed }: { item: AmbushBriefItem; highlight?: boolean; dimmed?: boolean }) {
  const stageLabel =
    item.change === "new" ? "新发现" :
    item.change === "promoted" ? "已晋升" :
    item.change === "expired" ? "已失效" :
    item.stage;

  return (
    <div className={"brief-card" + (highlight ? " highlight" : "") + (dimmed ? " dimmed" : "")}>
      <div className="brief-card-head">
        <strong>{item.name}</strong>
        <span className="brief-card-code">{item.code}</span>
        <span className={"brief-card-stage " + item.change}>{stageLabel}</span>
      </div>
      <div className="brief-card-body">
        <span className="brief-card-score">{item.total_score.toFixed(1)}</span>
        <span className="brief-card-sector">{item.sector}</span>
      </div>
      {item.detail && <div className="brief-card-detail">{item.detail}</div>}
    </div>
  );
}

function AmbushPipelineView({
  pipeline,
  brief,
  busy,
  busyAction,
  onRefresh,
  onSelectDetail,
  onMarkSeen
}: {
  pipeline: AmbushPipelineResponse | null;
  brief: AmbushBrief | null;
  busy: boolean;
  busyAction: string | null;
  onRefresh: () => void;
  onSelectDetail: (item: AmbushItem) => void;
  onMarkSeen: () => void;
}) {
  const watchPool = pipeline?.watch_pool ?? [];
  const brewingPool = pipeline?.brewing_pool ?? [];
  const ignitionPool = pipeline?.ignition_pool ?? [];
  const total = watchPool.length + brewingPool.length + ignitionPool.length;

  function stageBadge(stage: string) {
    return <span className={`ambush-stage ${stage === "待点火" ? "ignition" : stage === "蓄势中" ? "brewing" : "watch"}`}>{stage}</span>;
  }

  function signalMini(signals: AmbushSignalDetail[]) {
    return signals.slice(0, 3).map((sig) => (
      <span key={sig.signal_key} className="ambush-signal-pill" title={sig.details}>
        {sig.signal_name} {sig.confidence.toFixed(0)}
      </span>
    ));
  }

  function scoreColor(s: number) {
    if (s >= 70) return 'var(--accent)';
    if (s >= 50) return 'var(--amber)';
    return 'var(--red)';
  }

  function renderCard(item: AmbushItem) {
    const comps = [
      { label: '结构', score: item.structure_score, color: 'var(--blue)' },
      { label: '质地', score: item.quality_score, color: 'var(--violet)' },
      { label: '题材', score: item.thematic_score, color: 'var(--amber)' },
    ];
    const topSignals = item.signals.slice(0, 4);
    return (
      <article
        className="ambush-card"
        key={item.code}
        onClick={() => onSelectDetail(item)}
      >
        <header className="ambush-card-head">
          <div>
            <strong>{item.name}</strong>
            <span>{item.code}</span>
          </div>
          <div className="ambush-score-ring">
            <svg viewBox="0 0 36 36" width="36" height="36">
              <circle cx="18" cy="18" r="15.9" fill="none" stroke="rgba(var(--lr), var(--lg), var(--lb), 0.1)" strokeWidth="3" />
              <circle
                cx="18" cy="18" r="15.9"
                fill="none"
                stroke={scoreColor(item.total_score)}
                strokeWidth="3"
                strokeDasharray={`${item.total_score * 1.0} 100`}
                strokeLinecap="round"
                transform="rotate(-90 18 18)"
              />
            </svg>
            <span>{item.total_score.toFixed(0)}</span>
          </div>
        </header>
        <div className="ambush-card-body">
          <div className="ambush-card-meta">
            <span>{item.sector}</span>
            {stageBadge(item.stage)}
          </div>

          {/* 评分分量条形图 */}
          <div className="ambush-score-comps">
            {comps.map(c => (
              <div className="ambush-score-comp" key={c.label}>
                <span className="ambush-comp-label">{c.label}</span>
                <div className="ambush-comp-track">
                  <div className="ambush-comp-fill" style={{ width: `${c.score}%`, background: c.color }} />
                </div>
                <span className="ambush-comp-value" style={{ color: c.score >= 70 ? c.color : undefined }}>
                  {c.score.toFixed(0)}
                </span>
              </div>
            ))}
          </div>

          {/* 信号置信度条 */}
          <div className="ambush-signal-strip">
            {topSignals.length > 0 ? topSignals.map(s => (
              <div className="ambush-signal-bar" key={s.signal_key}>
                <div className="ambush-signal-bar-track">
                  <div
                    className="ambush-signal-bar-fill"
                    style={{ width: `${s.confidence}%` }}
                  />
                </div>
                <span className="ambush-signal-bar-label" title={s.details}>{s.signal_name}</span>
                <span className="ambush-signal-bar-val">{s.confidence.toFixed(0)}</span>
              </div>
            )) : (
              <span className="ambush-signal-pill muted">暂无信号</span>
            )}
          </div>

          {item.conditions.length > 0 && (
            <div className="ambush-condition-line">
              <Target size={12} />
              <span>{item.conditions[0].condition}</span>
            </div>
          )}
        </div>
      </article>
    );
  }

  return (
    <section className="ambush-layout">
      <div className="dashboard-strip">
        <div className="dashboard-card primary">
          <div>
            <span>管道总数</span>
            <strong>{total}</strong>
          </div>
          <Target size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>观察池</span>
            <strong>{watchPool.length}</strong>
          </div>
          <Flame size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>蓄势中</span>
            <strong>{brewingPool.length}</strong>
          </div>
          <BarChart3 size={22} />
        </div>
        <div className="dashboard-card">
          <div>
            <span>待点火</span>
            <strong>{ignitionPool.length}</strong>
          </div>
          <Activity size={22} />
          <small>{pipeline?.new_today ?? 0} 只新发现</small>
        </div>
        <div className="dashboard-card wide">
          <div>
            <span>操作建议</span>
            <strong>待点火区每日必看</strong>
          </div>
          <Target size={22} />
          <small>出现确认信号即可进入研究</small>
        </div>
      </div>

      {/* 每日简报 */}
      <BriefPanel
        brief={brief}
        onMarkSeen={onMarkSeen}
        onRefreshBrief={onRefresh}
      />

      <div className="table-toolbar">
        <div>
          <strong>{ignitionPool.length}</strong><span> 只待点火，</span>
          <strong>{brewingPool.length}</strong><span> 只蓄势中，</span>
          <strong>{watchPool.length}</strong><span> 只观察池</span>
        </div>
        <div className="action-row compact">
          <button
            className={busyAction === "ambushRun" ? "secondary-action loading" : "secondary-action"}
            onClick={onRefresh}
            disabled={busy}
            type="button"
          >
            <RefreshCw size={18} />
            {busyAction === "ambushRun" ? "评分中" : "刷新潜伏评分"}
          </button>
        </div>
      </div>

      <div className="ambush-kanban">
        <div className="ambush-column">
          <div className="ambush-column-head">
            <h3>观察池</h3>
            <span>{watchPool.length}</span>
          </div>
          <div className="ambush-column-body">
            {watchPool.map(renderCard)}
            {watchPool.length === 0 && <div className="ambush-empty">暂无符合条件的股票</div>}
          </div>
        </div>
        <div className="ambush-column">
          <div className="ambush-column-head brewing">
            <h3>蓄势中</h3>
            <span>{brewingPool.length}</span>
          </div>
          <div className="ambush-column-body">
            {brewingPool.map(renderCard)}
            {brewingPool.length === 0 && <div className="ambush-empty">暂无蓄势完成的股票</div>}
          </div>
        </div>
        <div className="ambush-column">
          <div className="ambush-column-head ignition">
            <h3>待点火</h3>
            <span>{ignitionPool.length}</span>
          </div>
          <div className="ambush-column-body">
            {ignitionPool.map(renderCard)}
            {ignitionPool.length === 0 && <div className="ambush-empty">暂无待点火股票</div>}
          </div>
        </div>
      </div>
    </section>
  );
}

function AmbushDetailView({
  item,
  onBack
}: {
  item: AmbushItem;
  onBack: () => void;
}) {
  const [techLevels, setTechLevels] = useState<TechnicalLevelsResponse | null>(null);
  const [klineScenario, setKlineScenario] = useState<KlineScenarioResponse | null>(null);

  useEffect(() => {
    api.technicalLevels(item.code).then(setTechLevels).catch(() => null);
    api.klineScenario(item.code).then(setKlineScenario).catch(() => null);
  }, [item.code]);

  return (
    <section className="ambush-detail-layout">
      <div className="tool-panel ambush-detail-head">
        <div className="ambush-detail-head-left">
          <button className="icon-action" onClick={onBack} type="button" title="返回潜伏管道">
            ← 返回
          </button>
          <h2>
            {item.name}
            <span>{item.code}</span>
          </h2>
          <span className={`ambush-stage ${item.stage === "待点火" ? "ignition" : item.stage === "蓄势中" ? "brewing" : "watch"}`}>
            {item.stage}
          </span>
        </div>
        <div className="ambush-score-ring large">
          <svg viewBox="0 0 48 48" width="48" height="48">
            <circle cx="24" cy="24" r="21.5" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
            <circle
              cx="24" cy="24" r="21.5"
              fill="none"
              stroke={item.total_score >= 70 ? "#38f0b0" : item.total_score >= 55 ? "#ffc24a" : "#ff6d5f"}
              strokeWidth="3"
              strokeDasharray={`${item.total_score * 0.96} 100`}
              strokeLinecap="round"
              transform="rotate(-90 24 24)"
            />
          </svg>
          <span>{item.total_score.toFixed(0)}</span>
        </div>
      </div>

      <div className="ambush-detail-grid">
        <div className="tool-panel">
          <div className="panel-title">
            <Activity size={19} />
            <h2>K线结构评分</h2>
            <strong>{item.structure_score.toFixed(0)}</strong>
          </div>
          <div className="ambush-signal-list">
            {item.signals.filter((s) => s.group === "蓄势组").map((sig) => (
              <div className="ambush-signal-row" key={sig.signal_key}>
                <div>
                  <strong>{sig.signal_name}</strong>
                  <p>{sig.details}</p>
                </div>
                <div className="ambush-signal-confidence">
                  <div className={`score-bar ${sig.confidence >= 65 ? "strong" : sig.confidence >= 40 ? "steady" : "weak"}`}>
                    <i style={{ width: `${sig.confidence}%` }} />
                  </div>
                  <span>{sig.confidence.toFixed(0)}</span>
                </div>
              </div>
            ))}
            {item.signals.filter((s) => s.group === "蓄势组").length === 0 && (
              <div className="ambush-empty">暂无蓄势信号</div>
            )}
          </div>
        </div>

        <div className="tool-panel">
          <div className="panel-title">
            <Activity size={19} />
            <h2>资金暗涌</h2>
            <strong>{item.signals.filter((s) => s.group === "吸筹组").reduce((max, s) => Math.max(max, s.confidence), 0).toFixed(0)}</strong>
          </div>
          <div className="ambush-signal-list">
            {item.signals.filter((s) => s.group === "吸筹组").map((sig) => (
              <div className="ambush-signal-row" key={sig.signal_key}>
                <div>
                  <strong>{sig.signal_name}</strong>
                  <p>{sig.details}</p>
                </div>
                <div className="ambush-signal-confidence">
                  <div className={`score-bar ${sig.confidence >= 65 ? "strong" : sig.confidence >= 40 ? "steady" : "weak"}`}>
                    <i style={{ width: `${sig.confidence}%` }} />
                  </div>
                  <span>{sig.confidence.toFixed(0)}</span>
                </div>
              </div>
            ))}
            {item.signals.filter((s) => s.group === "吸筹组").length === 0 && (
              <div className="ambush-empty">暂无资金暗涌信号</div>
            )}
          </div>
        </div>

        <div className="tool-panel">
          <div className="panel-title">
            <BarChart3 size={19} />
            <h2>题材匹配</h2>
            <strong>{item.thematic.score.toFixed(0)}</strong>
          </div>
          <div className="ambush-thematic-grid">
            <div>
              <span>概念数量</span>
              <strong>{item.thematic.concept_count}</strong>
            </div>
            <div>
              <span>热点命中</span>
              <strong>{item.thematic.hot_concept_hits}</strong>
            </div>
            <div>
              <span>板块相关度</span>
              <strong>{item.thematic.sector_relevance.toFixed(0)}</strong>
            </div>
            <div className="ambush-thematic-concepts">
              <span>匹配概念</span>
              <div>
                {item.thematic.matched_concepts.map((c) => (
                  <span className="ambush-concept-tag" key={c}>{c}</span>
                ))}
                {item.thematic.matched_concepts.length === 0 && <span className="muted">未命中热点</span>}
              </div>
            </div>
          </div>
        </div>

        <div className="tool-panel">
          <div className="panel-title">
            <BadgeCheck size={19} />
            <h2>基本面安全垫</h2>
            <strong>{item.quality_score.toFixed(0)}</strong>
          </div>
          <div className="ambush-score-bar-large">
            <div className={`score-bar ${item.quality_score >= 65 ? "strong" : item.quality_score >= 45 ? "steady" : "weak"}`}>
              <i style={{ width: `${item.quality_score}%` }} />
            </div>
          </div>
          <div className="ambush-score-legend">
            <span>基于ROE、营收增长、PE、现金流比</span>
          </div>
        </div>
      </div>

      {item.conditions.length > 0 && (
        <div className="tool-panel">
          <div className="panel-title">
            <Target size={19} />
            <h2>确认买入条件</h2>
          </div>
          <div className="ambush-condition-grid">
            {item.conditions.map((cond, i) => (
              <div className="ambush-condition-card" key={i}>
                <div className="ambush-condition-header">
                  <span>条件 #{i + 1}</span>
                  <strong>{cond.condition}</strong>
                </div>
                <div className="ambush-condition-meta">
                  {cond.trigger_price && (
                    <div>
                      <span>触发价</span>
                      <strong>{formatPrice(cond.trigger_price)}</strong>
                    </div>
                  )}
                  <div>
                    <span>依据</span>
                    <strong>{cond.price_basis}</strong>
                  </div>
                </div>
                <div className="ambush-condition-rules">
                  <div>
                    <Flame size={14} />
                    <span>{cond.stop_loss}</span>
                  </div>
                  <div>
                    <TrendingUp size={14} />
                    <span>{cond.target}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="ambush-detail-technical">
        <TechnicalLevelsPanel levels={techLevels} message="加载技术价位中..." />
        <KlineScenarioPanel scenario={klineScenario} message="加载K线情景中..." />
      </div>
    </section>
  );
}

export default App;
