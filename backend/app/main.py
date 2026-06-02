from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .ai_service import analyze_watchlist, generate_remark
from .ambush_service import (
    compute_ambush_brief,
    get_or_compute_brief,
    load_ambush_config,
    load_ambush_pipeline,
    mark_brief_seen,
    run_ambush_pipeline,
    save_ambush_config,
    save_ambush_pipeline,
    analyze_ambush_potential,
)
from .data_service import (
    cache_quality,
    fetch_public_stock_pool,
    import_csv,
    load_stock_pool,
    refresh_public_financial_metrics_cache,
    refresh_public_fund_flow_cache,
)
from .holding_service import analyze_holdings, normalize_holding
from .models import (
    AiRemarkRequest,
    AiAnalysisRequest,
    AiAnalysisResponse,
    AmbushBrief,
    AmbushConfig,
    AmbushPipelineResponse,
    AmbushResponse,
    AppConfig,
    DataStatus,
    FinancialMetricsRefreshResponse,
    FundFlowRefreshResponse,
    HoldingAnalysisResponse,
    HoldingListResponse,
    HoldingSaveRequest,
    HotSectorResponse,
    KlineScenarioResponse,
    ImportResponse,
    MomentumWatchResponse,
    RefreshResponse,
    ScreenResponse,
    TechnicalAnalysisResponse,
    TechnicalLevelsResponse,
    WatchlistItem,
    WatchlistResponse,
    WatchlistSaveRequest,
)
from .paths import CONFIG_PATH, ensure_data_dirs
from .scoring import build_hot_sectors, build_momentum_watchlist, run_screen
from .storage import (
    clear_ai_analysis,
    clear_holding_analysis,
    load_config,
    load_ai_analysis,
    load_holding_analysis,
    load_holdings,
    load_results,
    load_status,
    load_watchlist,
    save_config,
    save_ai_analysis,
    save_holding_analysis,
    save_holdings,
    save_results,
    save_status,
    save_watchlist,
    utc_now_iso,
)
from .technical import calculate_kline_scenario, calculate_technical_analysis, calculate_technical_levels, normalize_stock_code


refresh_lock = asyncio.Lock()
daily_refresh_task: asyncio.Task[None] | None = None
manual_refresh_task: asyncio.Task[RefreshResponse] | None = None


def _cors_origins() -> list[str]:
    defaults = ["http://localhost:5173", "http://127.0.0.1:5173"]
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    configured = [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]
    return list(dict.fromkeys([*defaults, *configured]))


def _results_include_current_metrics(results: ScreenResponse) -> bool:
    if not results.results:
        return True
    metrics = results.results[0].metrics
    return "fund_validation" in metrics and "fund_validation_score" in metrics


def _fresh_screen_results() -> ScreenResponse:
    results = run_screen(load_stock_pool(), load_config())
    _save_screen_results(results)
    return results


def _save_screen_results(results: ScreenResponse) -> None:
    save_results(results)
    clear_ai_analysis()
    clear_holding_analysis()


def _save_holdings(request: HoldingSaveRequest) -> HoldingListResponse:
    holdings = [normalize_holding(item) for item in request.holdings if item.code and item.cost_price > 0]
    response = HoldingListResponse(generated_at=utc_now_iso(), holdings=holdings)
    save_holdings(response)
    clear_holding_analysis()
    return response


def _stock_name_lookup() -> dict[str, str]:
    try:
        frame = load_stock_pool()
    except Exception:
        return {}
    if frame.empty or "code" not in frame.columns or "name" not in frame.columns:
        return {}
    return {
        normalize_stock_code(row["code"]): str(row["name"]).strip()
        for _, row in frame[["code", "name"]].dropna(subset=["code"]).iterrows()
        if str(row.get("name", "")).strip()
    }


def _save_watchlist(request: WatchlistSaveRequest) -> WatchlistResponse:
    existing_by_code = {item.code: item for item in load_watchlist().watchlist if item.code}
    name_by_code = _stock_name_lookup()
    normalized_items: list[WatchlistItem] = []
    seen: set[str] = set()
    now = utc_now_iso()

    for item in request.watchlist:
        code = normalize_stock_code(item.code)
        if not code or code in seen:
            continue
        previous = existing_by_code.get(code)
        name = item.name.strip() or (previous.name if previous else "") or name_by_code.get(code, "")
        normalized_items.append(
            WatchlistItem(
                id=item.id or (previous.id if previous else "") or f"watch-{code}",
                code=code,
                name=name,
                group=item.group.strip() or (previous.group if previous else "") or "默认",
                note=item.note.strip(),
                added_at=item.added_at or (previous.added_at if previous else "") or now,
            )
        )
        seen.add(code)

    response = WatchlistResponse(generated_at=now, watchlist=normalized_items)
    save_watchlist(response)
    return response


async def refresh_public_data(*, update_results: bool = False) -> RefreshResponse:
    async with refresh_lock:
        previous_status = load_status()
        status = previous_status.model_copy()
        status.refresh_running = True
        status.last_refresh_at = utc_now_iso()
        status.message = "正在拉取免费公开行情数据"
        save_status(status)
        try:
            frame, source = await asyncio.to_thread(fetch_public_stock_pool)
            if update_results:
                status = DataStatus(
                    last_refresh_at=utc_now_iso(),
                    last_success_at=previous_status.last_success_at,
                    source=source,
                    ok=True,
                    message=f"{source} 免费行情已拉取，正在重新评分",
                    rows=len(frame),
                    refresh_running=True,
                )
                save_status(status)
                results = await asyncio.to_thread(run_screen, frame, load_config())
                await asyncio.to_thread(_save_screen_results, results)
            now = utc_now_iso()
            status = DataStatus(
                last_refresh_at=now,
                last_success_at=now,
                source=source,
                ok=True,
                message=f"{source} 免费行情数据刷新成功，观察名单已更新" if update_results else f"{source} 免费行情数据刷新成功",
                rows=len(frame),
                refresh_running=False,
            )
            save_status(status)
            return RefreshResponse(ok=True, message=status.message, rows=len(frame))
        except Exception as exc:
            cached_frame = load_stock_pool()
            cached_quality = cache_quality(cached_frame)
            cached_rows = int(cached_quality["rows"])
            has_usable_cache = bool(cached_quality["is_scoring_quality"])
            status = DataStatus(
                last_refresh_at=utc_now_iso(),
                last_success_at=previous_status.last_success_at,
                source=previous_status.source if has_usable_cache else "public_api",
                ok=has_usable_cache,
                message=(
                    f"公开行情刷新失败，继续使用本地缓存：{exc}"
                    if has_usable_cache
                    else f"公开行情刷新失败：{exc}"
                ),
                rows=cached_rows,
                refresh_running=False,
            )
            save_status(status)
            return RefreshResponse(ok=False, message=status.message, rows=cached_rows)


def _same_local_day(left: str | None, right: str) -> bool:
    if not left:
        return False
    return left[:10] == right[:10]


async def daily_refresh_loop() -> None:
    while True:
        try:
            status = load_status()
            now = utc_now_iso()
            if not _same_local_day(status.last_refresh_at, now):
                await refresh_public_data(update_results=True)
        except Exception:
            pass
        await asyncio.sleep(60 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global daily_refresh_task
    ensure_data_dirs()
    if not CONFIG_PATH.exists():
        save_config(AppConfig())
    status = load_status()
    if status.refresh_running:
        save_status(
            status.model_copy(
                update={
                    "refresh_running": False,
                    "message": "上次刷新未正常结束，已恢复空闲，可重新刷新",
                }
            )
        )
    daily_refresh_task = asyncio.create_task(daily_refresh_loop())
    try:
        yield
    finally:
        if daily_refresh_task:
            daily_refresh_task.cancel()
            try:
                await daily_refresh_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="A 股板块龙头观察名单工具", version="1.0.0", lifespan=lifespan)
cors_origins = _cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": utc_now_iso()}


@app.post("/api/import/csv", response_model=ImportResponse)
async def import_csv_api(file: UploadFile = File(...)) -> ImportResponse:
    filename = file.filename or "stock_pool.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 文件")
    content = await file.read()
    frame = await asyncio.to_thread(import_csv, content, filename)
    results = run_screen(frame, load_config())
    _save_screen_results(results)
    return ImportResponse(rows=len(frame), columns=list(frame.columns), message="CSV 导入并评分完成")


@app.post("/api/data/refresh", response_model=RefreshResponse)
async def refresh_data_api() -> RefreshResponse:
    global manual_refresh_task
    status = load_status()
    if refresh_lock.locked() or (manual_refresh_task is not None and not manual_refresh_task.done()):
        return RefreshResponse(ok=True, message=status.message or "已有刷新任务正在运行", rows=status.rows)

    status = status.model_copy(
        update={
            "last_refresh_at": utc_now_iso(),
            "refresh_running": True,
            "message": "刷新任务已启动，正在拉取免费公开行情数据",
        }
    )
    save_status(status)
    manual_refresh_task = asyncio.create_task(refresh_public_data(update_results=True))
    return RefreshResponse(ok=True, message=status.message, rows=status.rows)


@app.post("/api/data/fund-flow/refresh", response_model=FundFlowRefreshResponse)
async def refresh_fund_flow_api() -> FundFlowRefreshResponse:
    async with refresh_lock:
        try:
            frame, before, after = await asyncio.to_thread(refresh_public_fund_flow_cache)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        results = run_screen(frame, load_config())
        _save_screen_results(results)
        added = max(0, after - before)
        message = f"资金流字段补充完成：覆盖 {after} 只，新增 {added} 只"
        status = load_status().model_copy(
            update={
                "last_refresh_at": utc_now_iso(),
                "ok": True,
                "message": message,
                "rows": len(frame),
                "refresh_running": False,
            }
        )
        if status.last_success_at is None:
            status.last_success_at = status.last_refresh_at
        save_status(status)
        return FundFlowRefreshResponse(
            ok=True,
            message=message,
            rows=len(frame),
            before_coverage=before,
            after_coverage=after,
        )


@app.post("/api/data/financial-metrics/refresh", response_model=FinancialMetricsRefreshResponse)
async def refresh_financial_metrics_api() -> FinancialMetricsRefreshResponse:
    async with refresh_lock:
        try:
            frame, before, after = await asyncio.to_thread(refresh_public_financial_metrics_cache)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        results = run_screen(frame, load_config())
        _save_screen_results(results)
        added = max(0, after - before)
        message = f"财务指标补充完成：核心字段完整覆盖 {after} 只，新增完整覆盖 {added} 只"
        status = load_status().model_copy(
            update={
                "last_refresh_at": utc_now_iso(),
                "ok": True,
                "message": message,
                "rows": len(frame),
                "refresh_running": False,
            }
        )
        if status.last_success_at is None:
            status.last_success_at = status.last_refresh_at
        save_status(status)
        return FinancialMetricsRefreshResponse(
            ok=True,
            message=message,
            rows=len(frame),
            before_complete_coverage=before,
            after_complete_coverage=after,
        )


@app.get("/api/data/status", response_model=DataStatus)
async def data_status_api() -> DataStatus:
    return load_status()


@app.get("/api/config", response_model=AppConfig)
async def get_config_api() -> AppConfig:
    return load_config()


@app.put("/api/config", response_model=AppConfig)
async def put_config_api(config: AppConfig) -> AppConfig:
    save_config(config)
    frame = load_stock_pool()
    if not frame.empty:
        _save_screen_results(run_screen(frame, config))
    return config


@app.post("/api/screen/run", response_model=ScreenResponse)
async def run_screen_api() -> ScreenResponse:
    frame = load_stock_pool()
    results = run_screen(frame, load_config())
    _save_screen_results(results)
    return results


@app.get("/api/screen/results", response_model=ScreenResponse)
async def get_results_api() -> ScreenResponse:
    results = load_results()
    if results is not None and _results_include_current_metrics(results):
        return results
    return _fresh_screen_results()


@app.get("/api/sectors/hot", response_model=HotSectorResponse)
@app.get("/api/sector/hot", response_model=HotSectorResponse)
async def hot_sectors_api(limit: int = 30) -> HotSectorResponse:
    capped_limit = max(1, min(limit, 100))
    return build_hot_sectors(load_stock_pool(), capped_limit)


@app.get("/api/momentum/watchlist", response_model=MomentumWatchResponse)
async def momentum_watchlist_api(limit: int = 60) -> MomentumWatchResponse:
    capped_limit = max(1, min(limit, 200))
    return build_momentum_watchlist(load_stock_pool(), capped_limit)


@app.get("/api/stocks/{code}/technical-levels", response_model=TechnicalLevelsResponse)
async def technical_levels_api(code: str) -> TechnicalLevelsResponse:
    normalized = normalize_stock_code(code)
    frame = load_stock_pool()
    matched = frame[frame["code"] == normalized]
    name = str(matched.iloc[0]["name"]) if not matched.empty else normalized
    try:
        return await asyncio.to_thread(calculate_technical_levels, normalized, name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stocks/{code}/technical-analysis", response_model=TechnicalAnalysisResponse)
async def technical_analysis_api(code: str) -> TechnicalAnalysisResponse:
    normalized = normalize_stock_code(code)
    frame = load_stock_pool()
    matched = frame[frame["code"] == normalized]
    name = str(matched.iloc[0]["name"]) if not matched.empty else normalized
    try:
        return await asyncio.to_thread(calculate_technical_analysis, normalized, name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stocks/{code}/kline-scenario", response_model=KlineScenarioResponse)
async def kline_scenario_api(code: str) -> KlineScenarioResponse:
    normalized = normalize_stock_code(code)
    frame = load_stock_pool()
    matched = frame[frame["code"] == normalized]
    name = str(matched.iloc[0]["name"]) if not matched.empty else normalized
    try:
        return await asyncio.to_thread(calculate_kline_scenario, normalized, name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ai/remarks", response_model=ScreenResponse)
async def ai_remarks_api(request: AiRemarkRequest) -> ScreenResponse:
    results = load_results()
    if results is None or not _results_include_current_metrics(results):
        results = _fresh_screen_results()

    limit = max(1, min(request.limit, len(results.results)))
    for item in results.results[:limit]:
        item.ai_remark = await generate_remark(item)
    save_results(results)
    return results


@app.get("/api/ai/analysis", response_model=AiAnalysisResponse)
async def get_ai_analysis_api() -> AiAnalysisResponse:
    analysis = load_ai_analysis()
    if analysis is not None:
        return analysis
    return AiAnalysisResponse(generated_at=utc_now_iso(), ok=True, message="尚未生成 AI 研究复核")


@app.post("/api/ai/analyze-watchlist", response_model=AiAnalysisResponse)
async def ai_analyze_watchlist_api(request: AiAnalysisRequest) -> AiAnalysisResponse:
    results = load_results()
    if results is None or not _results_include_current_metrics(results):
        results = _fresh_screen_results()

    analysis = await analyze_watchlist(results, request)
    save_ai_analysis(analysis)
    return analysis


@app.post("/api/ambush/run", response_model=AmbushPipelineResponse)
async def run_ambush_api() -> AmbushPipelineResponse:
    config = load_ambush_config()
    pipeline = run_ambush_pipeline(config)
    save_ambush_pipeline(pipeline)
    return pipeline


@app.get("/api/ambush/pipeline", response_model=AmbushPipelineResponse)
async def get_ambush_pipeline_api() -> AmbushPipelineResponse:
    pipeline = load_ambush_pipeline()
    if pipeline is not None:
        return pipeline
    config = load_ambush_config()
    pipeline = run_ambush_pipeline(config)
    save_ambush_pipeline(pipeline)
    return pipeline


@app.get("/api/ambush/config", response_model=AmbushConfig)
async def get_ambush_config_api() -> AmbushConfig:
    return load_ambush_config()


@app.put("/api/ambush/config", response_model=AmbushConfig)
async def put_ambush_config_api(config: AmbushConfig) -> AmbushConfig:
    save_ambush_config(config)
    return config


@app.post("/api/ambush/refresh-concepts")
async def refresh_concepts_api() -> dict[str, str]:
    from .ambush_fetcher import load_or_build_concept_map
    load_or_build_concept_map(force_refresh=True)
    return {"message": "概念板块缓存已刷新"}


@app.get("/api/ambush/brief", response_model=AmbushBrief)
async def get_ambush_brief_api() -> AmbushBrief:
    brief = get_or_compute_brief()
    return brief


@app.post("/api/ambush/brief/seen", response_model=AmbushBrief)
async def mark_ambush_brief_seen_api() -> AmbushBrief:
    return mark_brief_seen()


@app.post("/api/ambush/brief/refresh", response_model=AmbushBrief)
async def refresh_ambush_brief_api() -> AmbushBrief:
    return compute_ambush_brief()


@app.get("/api/watchlist", response_model=WatchlistResponse)
async def get_watchlist_api() -> WatchlistResponse:
    return load_watchlist()


@app.put("/api/watchlist", response_model=WatchlistResponse)
async def put_watchlist_api(request: WatchlistSaveRequest) -> WatchlistResponse:
    return _save_watchlist(request)


@app.get("/api/holdings", response_model=HoldingListResponse)
async def get_holdings_api() -> HoldingListResponse:
    return load_holdings()


@app.put("/api/holdings", response_model=HoldingListResponse)
async def put_holdings_api(request: HoldingSaveRequest) -> HoldingListResponse:
    return _save_holdings(request)


@app.get("/api/holdings/analysis", response_model=HoldingAnalysisResponse)
async def get_holding_analysis_api() -> HoldingAnalysisResponse:
    analysis = load_holding_analysis()
    if analysis is not None:
        return analysis
    return HoldingAnalysisResponse(generated_at=utc_now_iso(), ok=True, message="尚未生成持仓复核")


@app.post("/api/holdings/analyze", response_model=HoldingAnalysisResponse)
async def analyze_holdings_api() -> HoldingAnalysisResponse:
    holdings = load_holdings()
    analysis = await analyze_holdings(holdings.holdings)
    save_holding_analysis(analysis)
    return analysis
