from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .models import (
    AppConfig,
    HotSectorItem,
    HotSectorResponse,
    MomentumWatchItem,
    MomentumWatchResponse,
    ScoreBreakdown,
    ScreenResponse,
    ScreenResult,
    SectorLeader,
)
from .storage import utc_now_iso


NUMERIC_COLUMNS = [
    "market_cap",
    "turnover",
    "pct_change",
    "volume_ratio",
    "pe",
    "pb",
    "dividend_yield",
    "roe",
    "revenue_growth",
    "profit_growth",
    "cashflow_ratio",
    "dividend_payout_ratio",
    "revenue",
    "net_profit",
    "historical_pe_percentile",
    "sector_pct_change",
    "sector_turnover",
    "sector_turnover_growth",
    "main_net_inflow",
    "main_net_inflow_pct",
    "large_net_inflow",
    "large_net_inflow_pct",
    "sector_main_net_inflow",
    "sector_main_net_inflow_pct",
]


def _safe_float(value: Any, default: float = 0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _percent_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() <= 1:
        return pd.Series([50.0] * len(series), index=series.index)
    rank = numeric.rank(pct=True, ascending=higher_is_better)
    return (rank.fillna(0.5) * 100).clip(0, 100)


def _none_if_na(value: Any) -> Any:
    return None if pd.isna(value) else value


def _sum_min_count(series: pd.Series) -> float:
    return float(pd.to_numeric(series, errors="coerce").sum(min_count=1))


def _first_valid(series: pd.Series, default: float | None = None) -> float | None:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    if valid.empty:
        return default
    return float(valid.iloc[0])


def _prepare_numeric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column not in work.columns:
            work[column] = pd.NA
        work[column] = pd.to_numeric(work[column], errors="coerce")

    if "sector" not in work.columns:
        work["sector"] = ""
    if "industry" not in work.columns:
        work["industry"] = ""
    work["sector"] = work["sector"].fillna(work["industry"]).fillna("未分类")
    work["industry"] = work["industry"].fillna(work["sector"]).fillna("未分类")
    if "fund_flow_source" not in work.columns:
        work["fund_flow_source"] = ""
    if "fund_flow_note" not in work.columns:
        work["fund_flow_note"] = ""
    work["fund_flow_source"] = work["fund_flow_source"].fillna("").astype(str)
    work["fund_flow_note"] = work["fund_flow_note"].fillna("").astype(str)

    if "name" in work.columns:
        fresh_listing_mask = work["name"].astype(str).str.match(r"^[NC]", na=False) | (work["pct_change"].abs() > 100)
        work = work[~fresh_listing_mask].copy()
    return work


def _add_fund_validation_columns(work: pd.DataFrame) -> pd.DataFrame:
    if work.empty:
        work["derived_sector_main_net_inflow"] = pd.Series(dtype="float64")
        work["derived_sector_main_net_inflow_pct"] = pd.Series(dtype="float64")
        work["fund_validation_score"] = pd.Series(dtype="float64")
        work["fund_validation"] = pd.Series(dtype="object")
        return work

    sector_group = work.groupby("sector", dropna=False)
    sector_turnover = work["sector_turnover"].fillna(sector_group["turnover"].transform(_sum_min_count))
    sector_main_flow = work["sector_main_net_inflow"].fillna(sector_group["main_net_inflow"].transform(_sum_min_count))
    derived_pct = work["sector_main_net_inflow_pct"].copy()
    turnover_base = sector_turnover.replace(0, pd.NA)
    derived_pct = derived_pct.fillna(sector_main_flow / turnover_base * 100)

    work["derived_sector_main_net_inflow"] = sector_main_flow
    work["derived_sector_main_net_inflow_pct"] = derived_pct

    stock_pct = work["main_net_inflow_pct"].fillna(work["large_net_inflow_pct"])
    stock_flow = work["main_net_inflow"].fillna(work["large_net_inflow"])
    sector_pct = work["derived_sector_main_net_inflow_pct"]
    sector_flow = work["derived_sector_main_net_inflow"]

    def validation(row: pd.Series) -> tuple[float, str]:
        flow = _safe_float(row.get("main_net_inflow"), _safe_float(row.get("large_net_inflow"), float("nan")))
        flow_pct = _safe_float(
            row.get("main_net_inflow_pct"), _safe_float(row.get("large_net_inflow_pct"), float("nan"))
        )
        board_flow = _safe_float(row.get("derived_sector_main_net_inflow"), float("nan"))
        board_pct = _safe_float(row.get("derived_sector_main_net_inflow_pct"), float("nan"))
        pct_change = _safe_float(row.get("pct_change"))
        source = str(row.get("fund_flow_source") or "")
        is_proxy = "代理" in source or "同花顺" in source
        strong_label = "资金净额强验证" if is_proxy else "主力资金强验证"
        positive_label = "资金净额正向验证" if is_proxy else "主力资金正向验证"
        weak_label = "资金净额偏弱" if is_proxy else "主力资金偏弱"
        divergence_label = "价格走强但资金净额流出" if is_proxy else "价格走强但主力净流出"

        has_stock = pd.notna(flow) or pd.notna(flow_pct)
        has_board = pd.notna(board_flow) or pd.notna(board_pct)
        if not has_stock and not has_board:
            return 50, "暂无资金流字段"
        if (flow > 0 and flow_pct >= 3) or (board_flow > 0 and board_pct >= 3):
            return 88, strong_label
        if flow > 0 or board_flow > 0:
            return 72, positive_label
        if pct_change > 0 and (flow < 0 or board_flow < 0):
            return 32, divergence_label
        if flow < 0 or board_flow < 0:
            return 42, weak_label
        return 58, "资金验证中性"

    validation_pairs = work.apply(validation, axis=1)
    work["fund_validation_score"] = validation_pairs.map(lambda item: item[0])
    work["fund_validation"] = validation_pairs.map(lambda item: item[1])
    work["fund_flow_signal"] = (
        _percent_rank(stock_flow, higher_is_better=True) * 0.45
        + _percent_rank(stock_pct, higher_is_better=True) * 0.25
        + _percent_rank(sector_flow, higher_is_better=True) * 0.20
        + _percent_rank(sector_pct, higher_is_better=True) * 0.10
    ).clip(0, 100)
    return work


def _positive_score(value: Any, good: float, excellent: float) -> float:
    number = _safe_float(value)
    if number <= 0:
        return 20
    return _clamp(20 + (number / excellent) * 80 if number < excellent else 100)


def _valuation_score(pe: float, pb: float, industry_pe_rank: float, historical_pe_percentile: float) -> float:
    pe_score = 50
    if pe > 0:
        if pe <= 15:
            pe_score = 90
        elif pe <= 30:
            pe_score = 75
        elif pe <= 50:
            pe_score = 52
        elif pe <= 80:
            pe_score = 30
        else:
            pe_score = 15

    pb_score = 60
    if pb > 0:
        if pb <= 2:
            pb_score = 88
        elif pb <= 5:
            pb_score = 65
        elif pb <= 10:
            pb_score = 38
        else:
            pb_score = 20

    industry_score = 100 - industry_pe_rank
    history_score = 100 - historical_pe_percentile if historical_pe_percentile > 0 else 55
    return _clamp(pe_score * 0.30 + pb_score * 0.20 + industry_score * 0.25 + history_score * 0.25)


def _reason_for_result(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    if row["sector_heat_score"] >= 70:
        reasons.append("所属板块量价热度靠前，存在资金关注迹象")
    if _safe_float(row.get("fund_validation_score"), 50) >= 70:
        reasons.append(f"{row.get('fund_validation', '主力资金验证较好')}，资金流与板块热度相互印证")
    if row["leadership_score"] >= 70:
        reasons.append("板块内市值、成交活跃度或盈利规模具备龙头特征")
    if row["quality_score"] >= 70:
        reasons.append("ROE、增长或现金流质量较好，适合中期跟踪")
    if row["valuation_score"] >= 70:
        reasons.append("估值相对板块和历史区间未明显过热")
    if row["dividend_score"] >= 65:
        reasons.append("股息率或分红支付结构具备一定持续性")
    if not reasons:
        reasons.append("综合评分达到观察阈值，但需要进一步人工复核")
    return reasons


def _risks_for_result(row: pd.Series) -> list[str]:
    risks: list[str] = []
    if _safe_float(row.get("pe")) > 60 or _safe_float(row.get("historical_pe_percentile")) > 80:
        risks.append("估值处于偏高区间，需警惕泡沫")
    if row["sector_heat_score"] < 45:
        risks.append("板块资金热度不足")
    if _safe_float(row.get("fund_validation_score"), 50) < 45:
        risks.append(str(row.get("fund_validation") or "主力资金验证偏弱"))
    if row["quality_score"] < 45:
        risks.append("盈利质量或增长数据偏弱")
    payout = _safe_float(row.get("dividend_payout_ratio"))
    if payout > 85:
        risks.append("分红支付率偏高，持续性需复核")
    if row["industry_risk_score"] < 50:
        risks.append("行业被列入夕阳/谨慎清单")
    if not risks:
        risks.append("暂无明显量化风险，仍需结合公告和行业研究")
    return risks


def run_screen(frame: pd.DataFrame, config: AppConfig) -> ScreenResponse:
    if frame.empty:
        return ScreenResponse(generated_at=utc_now_iso(), total_candidates=0, results=[])

    work = _add_fund_validation_columns(_prepare_numeric_frame(frame))
    total_candidates = len(work)

    sector_group = work.groupby("sector", dropna=False)
    sector_heat_base = (
        sector_group["pct_change"].transform("mean").fillna(0) * 0.45
        + sector_group["turnover"].transform("sum").fillna(0).rank(pct=True) * 55
        + sector_group["volume_ratio"].transform("mean").fillna(1).rank(pct=True) * 25
    )
    if work["sector_pct_change"].notna().any():
        sector_heat_base = sector_heat_base + work["sector_pct_change"].fillna(0) * 1.5
    if work["sector_turnover_growth"].notna().any():
        sector_heat_base = sector_heat_base + work["sector_turnover_growth"].fillna(0) * 0.8
    if work["derived_sector_main_net_inflow"].notna().any():
        sector_heat_base = sector_heat_base + _percent_rank(work["derived_sector_main_net_inflow"], True) * 0.25
    if work["derived_sector_main_net_inflow_pct"].notna().any():
        sector_heat_base = sector_heat_base + work["derived_sector_main_net_inflow_pct"].fillna(0) * 1.5
    if work["fund_flow_signal"].notna().any():
        sector_heat_base = sector_heat_base + work["fund_flow_signal"].fillna(50) * 0.15
    work["sector_heat_score"] = _percent_rank(sector_heat_base, higher_is_better=True)

    work["market_cap_rank"] = sector_group["market_cap"].rank(pct=True, ascending=True).fillna(0.5) * 100
    work["turnover_rank"] = sector_group["turnover"].rank(pct=True, ascending=True).fillna(0.5) * 100
    work["revenue_rank"] = sector_group["revenue"].rank(pct=True, ascending=True).fillna(0.5) * 100
    work["profit_rank"] = sector_group["net_profit"].rank(pct=True, ascending=True).fillna(0.5) * 100
    work["roe_rank"] = sector_group["roe"].rank(pct=True, ascending=True).fillna(0.5) * 100
    work["leadership_score"] = (
        work["market_cap_rank"] * 0.30
        + work["turnover_rank"] * 0.25
        + work["revenue_rank"] * 0.15
        + work["profit_rank"] * 0.15
        + work["roe_rank"] * 0.15
    ).clip(0, 100)

    work["quality_score"] = (
        work["roe"].map(lambda value: _positive_score(value, good=10, excellent=22)) * 0.35
        + work["revenue_growth"].map(lambda value: _positive_score(value, good=8, excellent=30)) * 0.20
        + work["profit_growth"].map(lambda value: _positive_score(value, good=8, excellent=35)) * 0.25
        + work["cashflow_ratio"].map(lambda value: _positive_score(value, good=0.8, excellent=1.5)) * 0.20
    ).clip(0, 100)

    industry_pe_rank = sector_group["pe"].rank(pct=True, ascending=True).fillna(0.5) * 100
    work["valuation_score"] = [
        _valuation_score(
            _safe_float(pe),
            _safe_float(pb),
            _safe_float(rank, 50),
            _safe_float(hist, 50),
        )
        for pe, pb, rank, hist in zip(
            work["pe"], work["pb"], industry_pe_rank, work["historical_pe_percentile"], strict=False
        )
    ]

    def dividend_score(row: pd.Series) -> float:
        dy = _safe_float(row.get("dividend_yield"))
        payout = _safe_float(row.get("dividend_payout_ratio"))
        cashflow = _safe_float(row.get("cashflow_ratio"))
        dy_score = _clamp(dy / 5 * 100) if dy > 0 else 35
        payout_score = 80
        if payout > 0:
            payout_score = 90 if 20 <= payout <= 60 else 65 if payout <= 85 else 30
        cash_score = _clamp(cashflow / 1.2 * 100) if cashflow > 0 else 45
        return _clamp(dy_score * 0.45 + payout_score * 0.30 + cash_score * 0.25)

    work["dividend_score"] = work.apply(dividend_score, axis=1)

    sunset = [item.strip() for item in config.sunset_industries if item.strip()]
    if sunset:
        pattern = "|".join(re.escape(text) for text in sunset)
        sunset_mask = work["industry"].str.contains(pattern, na=False) | work["sector"].str.contains(pattern, na=False)
    else:
        sunset_mask = pd.Series([False] * len(work), index=work.index)
    work["industry_risk_score"] = sunset_mask.map(lambda value: 0 if value else 100)
    work = work[~sunset_mask].copy()

    weights = config.weights
    weight_total = sum(weights.model_dump().values()) or 1
    work["total_score"] = (
        work["sector_heat_score"] * weights.sector_heat
        + work["leadership_score"] * weights.leadership
        + work["quality_score"] * weights.quality
        + work["valuation_score"] * weights.valuation
        + work["dividend_score"] * weights.dividend
        + work["industry_risk_score"] * weights.industry_risk
    ) / weight_total

    thresholds = config.thresholds
    filtered = work[work["total_score"] >= thresholds.min_total_score].copy()
    if thresholds.min_turnover > 0:
        filtered = filtered[filtered["turnover"].fillna(0) >= thresholds.min_turnover]
    if thresholds.max_pe is not None:
        filtered = filtered[(filtered["pe"].fillna(0) <= thresholds.max_pe) | (filtered["pe"].isna())]
    filtered = filtered.sort_values("total_score", ascending=False).head(thresholds.max_results)

    results: list[ScreenResult] = []
    for _, row in filtered.iterrows():
        score = ScoreBreakdown(
            sector_heat=round(_safe_float(row["sector_heat_score"]), 1),
            leadership=round(_safe_float(row["leadership_score"]), 1),
            quality=round(_safe_float(row["quality_score"]), 1),
            valuation=round(_safe_float(row["valuation_score"]), 1),
            dividend=round(_safe_float(row["dividend_score"]), 1),
            industry_risk=round(_safe_float(row["industry_risk_score"]), 1),
        )
        metrics = {
            key: None if pd.isna(row.get(key)) else row.get(key)
            for key in [
                "market_cap",
                "turnover",
                "pct_change",
                "volume_ratio",
                "pe",
                "pb",
                "dividend_yield",
                "roe",
                "revenue_growth",
                "profit_growth",
                "cashflow_ratio",
                "dividend_payout_ratio",
                "revenue",
                "net_profit",
                "historical_pe_percentile",
                "sector_pct_change",
                "sector_turnover",
                "sector_turnover_growth",
                "main_net_inflow",
                "main_net_inflow_pct",
                "large_net_inflow",
                "large_net_inflow_pct",
                "sector_main_net_inflow",
                "sector_main_net_inflow_pct",
                "derived_sector_main_net_inflow",
                "derived_sector_main_net_inflow_pct",
                "fund_validation_score",
                "fund_flow_source",
                "fund_flow_note",
            ]
        }
        metrics["fund_validation"] = str(row.get("fund_validation") or "")
        results.append(
            ScreenResult(
                code=str(row["code"]),
                name=str(row["name"]),
                sector=str(row["sector"] or "未分类"),
                industry=str(row["industry"] or "未分类"),
                total_score=round(_safe_float(row["total_score"]), 1),
                score=score,
                reasons=_reason_for_result(row),
                risks=_risks_for_result(row),
                metrics=metrics,
            )
        )

    return ScreenResponse(generated_at=utc_now_iso(), total_candidates=total_candidates, results=results)


def _is_proxy_fund_source(source: str | None) -> bool:
    text = str(source or "")
    return "代理" in text or "同花顺" in text


def _sector_fund_validation(
    main_flow: float | None, main_pct: float | None, pct_change: float | None, source: str | None = None
) -> str:
    is_proxy = _is_proxy_fund_source(source)
    strong_label = "资金净额强验证" if is_proxy else "主力资金强验证"
    positive_label = "资金净额正向验证" if is_proxy else "主力资金正向验证"
    weak_label = "资金净额偏弱" if is_proxy else "主力资金偏弱"
    inflow_label = "资金净额流入但占比偏弱" if is_proxy else "主力净流入但占比偏弱"
    divergence_label = "价格热但资金净额流出" if is_proxy else "价格热但主力净流出"
    has_flow = main_flow is not None or main_pct is not None
    if not has_flow:
        return "暂无资金流字段"
    flow = main_flow if main_flow is not None else 0
    pct = main_pct if main_pct is not None else 0
    change = pct_change if pct_change is not None else 0
    if flow > 0 and pct >= 3:
        return strong_label
    if flow > 0 and pct >= 0:
        return positive_label
    if flow > 0:
        return inflow_label
    if change > 0 and flow < 0:
        return divergence_label
    if flow < 0:
        return weak_label
    return "资金验证中性"


def _leader_basis(row: pd.Series) -> str:
    parts = [
        f"成交额 {round(_safe_float(row.get('turnover')) / 100000000, 1)} 亿",
        f"涨跌幅 {round(_safe_float(row.get('pct_change')), 2)}%",
    ]
    main_flow = _safe_float(row.get("main_net_inflow"), float("nan"))
    if pd.notna(main_flow):
        flow_label = "资金净额" if _is_proxy_fund_source(str(row.get("fund_flow_source") or "")) else "主力净流入"
        parts.append(f"{flow_label} {round(main_flow / 100000000, 2)} 亿")
    elif pd.notna(row.get("market_cap")):
        parts.append(f"市值 {round(_safe_float(row.get('market_cap')) / 100000000, 1)} 亿")
    return "，".join(parts)


def _sector_fund_source(group: pd.DataFrame) -> tuple[str, str]:
    has_explicit_sector_flow = (
        group["sector_main_net_inflow"].notna().any() or group["sector_main_net_inflow_pct"].notna().any()
    )
    if has_explicit_sector_flow:
        return "东方财富板块主力资金", "东方财富板块资金流字段。"

    sources = [str(value).strip() for value in group["fund_flow_source"].dropna().tolist() if str(value).strip()]
    if not sources:
        return "", ""
    if any(_is_proxy_fund_source(source) for source in sources):
        return "同花顺资金净额代理汇总", "由同花顺个股资金净额按板块汇总，非东方财富板块主力口径。"
    first_source = sources[0]
    return f"{first_source}汇总", "由个股资金字段按板块汇总。"


def build_hot_sectors(frame: pd.DataFrame, limit: int = 30) -> HotSectorResponse:
    if frame.empty:
        return HotSectorResponse(generated_at=utc_now_iso(), total_sectors=0, sectors=[])

    work = _add_fund_validation_columns(_prepare_numeric_frame(frame))
    if work.empty:
        return HotSectorResponse(generated_at=utc_now_iso(), total_sectors=0, sectors=[])

    rows: list[dict[str, Any]] = []
    for sector, group in work.groupby("sector", dropna=False):
        sector_name = str(sector or "未分类")
        pct_change = _first_valid(group["sector_pct_change"], group["pct_change"].mean())
        turnover = _first_valid(group["sector_turnover"], _sum_min_count(group["turnover"]))
        main_flow = _first_valid(group["sector_main_net_inflow"], _sum_min_count(group["main_net_inflow"]))
        main_pct = _first_valid(group["sector_main_net_inflow_pct"])
        if main_pct is None and main_flow is not None and turnover:
            main_pct = main_flow / turnover * 100
        fund_source, fund_note = _sector_fund_source(group)
        active_stock_ratio = float((group["pct_change"].fillna(0) > 0).mean() * 100)
        rows.append(
            {
                "sector": sector_name,
                "stock_count": int(len(group)),
                "pct_change": pct_change,
                "turnover": turnover,
                "avg_volume_ratio": float(group["volume_ratio"].mean()) if group["volume_ratio"].notna().any() else None,
                "main_net_inflow": main_flow,
                "main_net_inflow_pct": main_pct,
                "active_stock_ratio": active_stock_ratio,
                "fund_flow_source": fund_source,
                "fund_flow_note": fund_note,
            }
        )

    sectors = pd.DataFrame(rows)
    sectors["heat_score"] = (
        _percent_rank(sectors["pct_change"], True) * 0.30
        + _percent_rank(sectors["turnover"], True) * 0.20
        + _percent_rank(sectors["avg_volume_ratio"], True) * 0.15
        + _percent_rank(sectors["active_stock_ratio"], True) * 0.15
        + _percent_rank(sectors["main_net_inflow"], True) * 0.15
        + _percent_rank(sectors["main_net_inflow_pct"], True) * 0.05
    ).clip(0, 100)

    items: list[HotSectorItem] = []
    for _, sector_row in sectors.sort_values("heat_score", ascending=False).head(max(1, limit)).iterrows():
        sector_name = str(sector_row["sector"])
        group = work[work["sector"].astype(str) == sector_name].copy()
        group["leader_proxy_score"] = (
            group.groupby("sector")["market_cap"].rank(pct=True, ascending=True).fillna(0.5) * 30
            + group.groupby("sector")["turnover"].rank(pct=True, ascending=True).fillna(0.5) * 30
            + group.groupby("sector")["main_net_inflow"].rank(pct=True, ascending=True).fillna(0.5) * 25
            + group.groupby("sector")["pct_change"].rank(pct=True, ascending=True).fillna(0.5) * 15
        )
        leaders = [
            SectorLeader(
                code=str(row["code"]),
                name=str(row["name"]),
                score=round(_safe_float(row.get("leader_proxy_score")), 1),
                basis=_leader_basis(row),
            )
            for _, row in group.sort_values("leader_proxy_score", ascending=False).head(3).iterrows()
        ]
        pct_change = _none_if_na(sector_row["pct_change"])
        turnover = _none_if_na(sector_row["turnover"])
        main_flow = _none_if_na(sector_row["main_net_inflow"])
        main_pct = _none_if_na(sector_row["main_net_inflow_pct"])
        active_ratio = _none_if_na(sector_row["active_stock_ratio"])
        fund_source = str(sector_row.get("fund_flow_source") or "")
        fund_note = str(sector_row.get("fund_flow_note") or "")
        flow_label = "资金净额" if _is_proxy_fund_source(fund_source) else "主力净流入"
        notes = [
            f"板块涨跌幅 {round(float(pct_change), 2)}%" if pct_change is not None else "板块涨跌幅暂无字段",
            f"上涨家数占比 {round(float(active_ratio), 1)}%" if active_ratio is not None else "上涨家数占比暂无字段",
        ]
        if main_flow is not None:
            notes.append(f"{flow_label} {round(float(main_flow) / 100000000, 2)} 亿")
        else:
            notes.append("资金流字段缺失，需用后续刷新或 CSV 补齐")
        if fund_source:
            notes.append(f"资金口径：{fund_source}")

        items.append(
            HotSectorItem(
                sector=sector_name,
                heat_score=round(_safe_float(sector_row["heat_score"]), 1),
                stock_count=int(sector_row["stock_count"]),
                pct_change=pct_change,
                turnover=turnover,
                avg_volume_ratio=_none_if_na(sector_row["avg_volume_ratio"]),
                main_net_inflow=main_flow,
                main_net_inflow_pct=main_pct,
                active_stock_ratio=active_ratio,
                fund_flow_source=fund_source or None,
                fund_flow_note=fund_note or None,
                fund_validation=_sector_fund_validation(main_flow, main_pct, pct_change, fund_source),
                notes=notes,
                leaders=leaders,
            )
        )

    return HotSectorResponse(generated_at=utc_now_iso(), total_sectors=len(sectors), sectors=items)


def _momentum_trigger_level(score: float) -> str:
    if score >= 82:
        return "强异动"
    if score >= 70:
        return "活跃跟踪"
    return "初步异动"


def _momentum_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    pct_change = _safe_float(row.get("pct_change"))
    volume_ratio = _safe_float(row.get("volume_ratio"))
    turnover = _safe_float(row.get("turnover"))
    fund_score = _safe_float(row.get("fund_validation_score"), 50)
    sector_heat = _safe_float(row.get("short_sector_heat_score"), 50)

    if _safe_float(row.get("pct_rank")) >= 75 or pct_change >= 3:
        reasons.append("当日涨跌幅排名靠前，价格出现短线异动")
    if _safe_float(row.get("turnover_rank")) >= 75 or turnover >= 1_000_000_000:
        reasons.append("成交额放大，市场关注度提升")
    if _safe_float(row.get("volume_rank")) >= 70 or volume_ratio >= 1.5:
        reasons.append("量比抬升，交易活跃度高于常态")
    if fund_score >= 70:
        reasons.append(f"{row.get('fund_validation', '资金验证较好')}，资金侧提供确认")
    if sector_heat >= 70:
        reasons.append("所属板块同步走强，个股异动具备板块配合")
    if not reasons:
        reasons.append("量价活跃度进入短线观察区，需等待资金与板块进一步确认")
    return reasons[:5]


def _momentum_risks(row: pd.Series) -> list[str]:
    risks: list[str] = []
    pct_change = _safe_float(row.get("pct_change"))
    main_flow = _safe_float(row.get("main_net_inflow"), _safe_float(row.get("large_net_inflow"), float("nan")))
    fund_score = _safe_float(row.get("fund_validation_score"), 50)
    turnover = _safe_float(row.get("turnover"))
    pe = _safe_float(row.get("pe"))
    volume_ratio = _safe_float(row.get("volume_ratio"))

    if pct_change >= 7:
        risks.append("当日涨幅较大，短线追高波动风险上升")
    if pct_change > 0 and pd.notna(main_flow) and main_flow < 0:
        risks.append("价格走强但资金净流出，存在量价背离")
    if fund_score < 45:
        risks.append(str(row.get("fund_validation") or "资金验证偏弱"))
    if turnover > 0 and turnover < 100_000_000:
        risks.append("成交额偏低，异动持续性需复核")
    if pe > 80:
        risks.append("PE 偏高，估值弹性与回撤风险并存")
    if volume_ratio >= 3 and pct_change < 1:
        risks.append("量比明显放大但价格响应有限，需警惕分歧")
    if not risks:
        risks.append("暂无明显短线量化风险，仍需结合公告和盘中盘口")
    return risks[:5]


def build_momentum_watchlist(frame: pd.DataFrame, limit: int = 60) -> MomentumWatchResponse:
    if frame.empty:
        return MomentumWatchResponse(generated_at=utc_now_iso(), total_candidates=0, results=[])

    work = _add_fund_validation_columns(_prepare_numeric_frame(frame))
    if work.empty:
        return MomentumWatchResponse(generated_at=utc_now_iso(), total_candidates=0, results=[])

    total_candidates = len(work)
    sector_group = work.groupby("sector", dropna=False)
    sector_pct = work["sector_pct_change"].fillna(sector_group["pct_change"].transform("mean"))
    sector_turnover = work["sector_turnover"].fillna(sector_group["turnover"].transform(_sum_min_count))
    sector_active_ratio = sector_group["pct_change"].transform(lambda values: (values.fillna(0) > 0).mean() * 100)
    sector_volume = sector_group["volume_ratio"].transform("mean")
    sector_flow = work["derived_sector_main_net_inflow"]
    sector_flow_pct = work["derived_sector_main_net_inflow_pct"]

    work["short_sector_heat_score"] = (
        _percent_rank(sector_pct, True) * 0.30
        + _percent_rank(sector_turnover, True) * 0.20
        + _percent_rank(sector_active_ratio, True) * 0.20
        + _percent_rank(sector_volume, True) * 0.10
        + _percent_rank(sector_flow, True) * 0.15
        + _percent_rank(sector_flow_pct, True) * 0.05
    ).clip(0, 100)

    stock_flow = work["main_net_inflow"].fillna(work["large_net_inflow"])
    stock_flow_pct = work["main_net_inflow_pct"].fillna(work["large_net_inflow_pct"])
    work["pct_rank"] = _percent_rank(work["pct_change"], True)
    work["turnover_rank"] = _percent_rank(work["turnover"], True)
    work["volume_rank"] = _percent_rank(work["volume_ratio"], True)
    work["stock_flow_rank"] = _percent_rank(stock_flow, True)
    work["stock_flow_pct_rank"] = _percent_rank(stock_flow_pct, True)
    work["flow_combo_rank"] = (work["stock_flow_rank"] * 0.65 + work["stock_flow_pct_rank"] * 0.35).clip(0, 100)

    has_any_fund_field = (
        work["main_net_inflow"].notna()
        | work["main_net_inflow_pct"].notna()
        | work["large_net_inflow"].notna()
        | work["large_net_inflow_pct"].notna()
        | work["derived_sector_main_net_inflow"].notna()
        | work["derived_sector_main_net_inflow_pct"].notna()
    )
    work["fund_component"] = work["flow_combo_rank"].where(has_any_fund_field, work["fund_validation_score"])

    work["momentum_score"] = (
        work["pct_rank"] * 0.25
        + work["turnover_rank"] * 0.20
        + work["volume_rank"] * 0.15
        + work["fund_component"] * 0.15
        + work["fund_validation_score"].fillna(50) * 0.10
        + work["short_sector_heat_score"] * 0.15
    ).clip(0, 100)

    active = work[
        (work["pct_change"].fillna(0) > 0)
        | (work["volume_ratio"].fillna(0) >= 1.2)
        | (work["turnover_rank"].fillna(0) >= 60)
        | (work["fund_validation_score"].fillna(50) >= 70)
        | (work["short_sector_heat_score"].fillna(50) >= 70)
    ].copy()
    if active.empty:
        active = work.copy()

    active = active.sort_values(
        ["momentum_score", "pct_change", "turnover"],
        ascending=[False, False, False],
    ).head(max(1, limit))

    metric_keys = [
        "pct_change",
        "turnover",
        "volume_ratio",
        "main_net_inflow",
        "main_net_inflow_pct",
        "large_net_inflow",
        "large_net_inflow_pct",
        "derived_sector_main_net_inflow",
        "derived_sector_main_net_inflow_pct",
        "sector_pct_change",
        "sector_turnover",
        "sector_turnover_growth",
        "fund_validation",
        "fund_validation_score",
        "fund_flow_source",
        "fund_flow_note",
        "pe",
        "pb",
        "market_cap",
        "pct_rank",
        "turnover_rank",
        "volume_rank",
        "flow_combo_rank",
        "short_sector_heat_score",
    ]

    results: list[MomentumWatchItem] = []
    for rank, (_, row) in enumerate(active.iterrows(), start=1):
        metrics = {key: _none_if_na(row.get(key)) for key in metric_keys}
        score = round(_safe_float(row.get("momentum_score")), 1)
        results.append(
            MomentumWatchItem(
                code=str(row.get("code") or ""),
                name=str(row.get("name") or ""),
                sector=str(row.get("sector") or "未分类"),
                industry=str(row.get("industry") or "未分类"),
                momentum_score=score,
                rank=rank,
                trigger_level=_momentum_trigger_level(score),
                reasons=_momentum_reasons(row),
                risks=_momentum_risks(row),
                metrics=metrics,
            )
        )

    return MomentumWatchResponse(generated_at=utc_now_iso(), total_candidates=total_candidates, results=results)
