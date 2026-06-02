from __future__ import annotations

import io
import math
import re
import time
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from .models import DataStatus
from .paths import CACHE_DIR, STOCK_POOL_BACKUP_PATH, STOCK_POOL_PATH, ensure_data_dirs
from .storage import save_status, utc_now_iso


EASTMONEY_HEADERS = {
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

EASTMONEY_STOCK_URLS = [
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://83.push2.eastmoney.com/api/qt/clist/get",
]
EASTMONEY_INDUSTRY_URLS = [
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://17.push2.eastmoney.com/api/qt/clist/get",
    "https://29.push2.eastmoney.com/api/qt/clist/get",
]
EASTMONEY_FUND_FLOW_URLS = [
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://push2his.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
]

THS_HEADERS = {
    "Referer": "http://q.10jqka.com.cn/thshy/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

TENCENT_HEADERS = {
    "Referer": "https://stockapp.finance.qq.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


STANDARD_COLUMNS = [
    "code",
    "name",
    "sector",
    "industry",
    "current_price",
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
    "fund_flow_source",
    "fund_flow_note",
]


COLUMN_ALIASES: dict[str, str] = {
    "股票代码": "code",
    "代码": "code",
    "证券代码": "code",
    "code": "code",
    "股票简称": "name",
    "名称": "name",
    "证券简称": "name",
    "name": "name",
    "板块": "sector",
    "概念": "sector",
    "行业": "industry",
    "所属行业": "industry",
    "sector": "sector",
    "industry": "industry",
    "最新价": "current_price",
    "最新": "current_price",
    "现价": "current_price",
    "当前价": "current_price",
    "current_price": "current_price",
    "last_price": "current_price",
    "price": "current_price",
    "总市值": "market_cap",
    "市值": "market_cap",
    "流通市值": "market_cap",
    "market_cap": "market_cap",
    "成交额": "turnover",
    "成交金额": "turnover",
    "turnover": "turnover",
    "涨跌幅": "pct_change",
    "涨幅": "pct_change",
    "pct_change": "pct_change",
    "量比": "volume_ratio",
    "volume_ratio": "volume_ratio",
    "市盈率": "pe",
    "pe": "pe",
    "PE": "pe",
    "动态市盈率": "pe",
    "市净率": "pb",
    "pb": "pb",
    "PB": "pb",
    "股息率": "dividend_yield",
    "分红率": "dividend_yield",
    "dividend_yield": "dividend_yield",
    "ROE": "roe",
    "净资产收益率": "roe",
    "roe": "roe",
    "营收增长": "revenue_growth",
    "营收同比": "revenue_growth",
    "营业收入同比增长": "revenue_growth",
    "revenue_growth": "revenue_growth",
    "利润增长": "profit_growth",
    "净利润同比": "profit_growth",
    "净利润增长": "profit_growth",
    "profit_growth": "profit_growth",
    "现金流": "cashflow_ratio",
    "经营现金流净利润比": "cashflow_ratio",
    "cashflow_ratio": "cashflow_ratio",
    "分红支付率": "dividend_payout_ratio",
    "派息率": "dividend_payout_ratio",
    "dividend_payout_ratio": "dividend_payout_ratio",
    "营业收入": "revenue",
    "营收": "revenue",
    "revenue": "revenue",
    "净利润": "net_profit",
    "net_profit": "net_profit",
    "历史PE分位": "historical_pe_percentile",
    "历史估值分位": "historical_pe_percentile",
    "historical_pe_percentile": "historical_pe_percentile",
    "板块涨跌幅": "sector_pct_change",
    "sector_pct_change": "sector_pct_change",
    "板块成交额": "sector_turnover",
    "sector_turnover": "sector_turnover",
    "板块成交额增速": "sector_turnover_growth",
    "sector_turnover_growth": "sector_turnover_growth",
    "主力净流入": "main_net_inflow",
    "主力净额": "main_net_inflow",
    "主力资金净流入": "main_net_inflow",
    "main_net_inflow": "main_net_inflow",
    "主力净占比": "main_net_inflow_pct",
    "主力净流入占比": "main_net_inflow_pct",
    "主力净流入-净占比": "main_net_inflow_pct",
    "main_net_inflow_pct": "main_net_inflow_pct",
    "大单净流入": "large_net_inflow",
    "大单净额": "large_net_inflow",
    "large_net_inflow": "large_net_inflow",
    "大单净占比": "large_net_inflow_pct",
    "large_net_inflow_pct": "large_net_inflow_pct",
    "板块主力净流入": "sector_main_net_inflow",
    "sector_main_net_inflow": "sector_main_net_inflow",
    "板块主力净占比": "sector_main_net_inflow_pct",
    "sector_main_net_inflow_pct": "sector_main_net_inflow_pct",
    "资金流来源": "fund_flow_source",
    "fund_flow_source": "fund_flow_source",
    "资金流说明": "fund_flow_note",
    "fund_flow_note": "fund_flow_note",
}


TEXT_COLUMNS = {"code", "name", "sector", "industry", "fund_flow_source", "fund_flow_note"}
NUMERIC_COLUMNS = [column for column in STANDARD_COLUMNS if column not in TEXT_COLUMNS]

PRESERVE_IF_MISSING_COLUMNS = [
    "sector",
    "industry",
    "market_cap",
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
    "fund_flow_source",
    "fund_flow_note",
]

FINANCIAL_METRIC_COLUMNS = [
    "dividend_yield",
    "roe",
    "revenue_growth",
    "profit_growth",
    "cashflow_ratio",
    "dividend_payout_ratio",
    "revenue",
    "net_profit",
]

CORE_FINANCIAL_METRIC_COLUMNS = [
    "dividend_yield",
    "roe",
    "revenue_growth",
    "profit_growth",
]


def _clean_column_name(column: Any) -> str:
    return str(column).strip().replace("\ufeff", "")


def _normalize_code(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else text


def _to_number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if text in {"", "-", "--", "nan", "None"}:
        return None
    multiplier = 1.0
    if text.endswith("万亿"):
        multiplier = 1_000_000_000_000
        text = text[:-2]
    elif text.endswith("亿"):
        multiplier = 100_000_000
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10_000
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def standardize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[str, str] = {}
    for column in frame.columns:
        clean = _clean_column_name(column)
        renamed[column] = COLUMN_ALIASES.get(clean, COLUMN_ALIASES.get(clean.lower(), clean))
    frame = frame.rename(columns=renamed).copy()

    for column in STANDARD_COLUMNS:
        if column not in frame.columns:
            frame[column] = None

    frame = frame[STANDARD_COLUMNS]
    frame["code"] = frame["code"].map(_normalize_code)
    frame["name"] = frame["name"].fillna("").astype(str).str.strip()
    frame["sector"] = frame["sector"].fillna("").astype(str).str.strip()
    frame["industry"] = frame["industry"].fillna("").astype(str).str.strip()
    frame["fund_flow_source"] = frame["fund_flow_source"].fillna("").astype(str).str.strip()
    frame["fund_flow_note"] = frame["fund_flow_note"].fillna("").astype(str).str.strip()
    frame.loc[frame["sector"] == "", "sector"] = frame.loc[frame["sector"] == "", "industry"]
    frame.loc[frame["industry"] == "", "industry"] = frame.loc[frame["industry"] == "", "sector"]

    for column in NUMERIC_COLUMNS:
        frame[column] = frame[column].map(_to_number)

    return frame[(frame["code"] != "") & (frame["name"] != "")].drop_duplicates("code", keep="last")


def read_csv_bytes(content: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"无法读取 CSV 文件：{last_error}")


def cache_quality(frame: pd.DataFrame) -> dict[str, float | int | bool]:
    standardized = standardize_frame(frame)
    rows = len(standardized)
    if rows == 0:
        return {
            "rows": 0,
            "sector_ratio": 0.0,
            "market_cap_ratio": 0.0,
            "valuation_ratio": 0.0,
            "is_full_quality": False,
            "is_scoring_quality": False,
        }
    sector_ratio = (standardized["sector"].astype(str).str.strip() != "").mean()
    market_cap_ratio = standardized["market_cap"].notna().mean()
    valuation_ratio = (standardized["pe"].notna() | standardized["pb"].notna()).mean()
    return {
        "rows": rows,
        "sector_ratio": float(sector_ratio),
        "market_cap_ratio": float(market_cap_ratio),
        "valuation_ratio": float(valuation_ratio),
        "is_full_quality": rows >= 1000 and sector_ratio >= 0.55 and market_cap_ratio >= 0.55,
        "is_scoring_quality": rows >= 10 and sector_ratio >= 0.20,
    }


def _load_standardized_stock_pool(path: Any) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=STANDARD_COLUMNS)
    return standardize_frame(pd.read_csv(path, dtype={"code": str}))


def _load_enrichment_stock_pool() -> pd.DataFrame:
    current = _load_standardized_stock_pool(STOCK_POOL_PATH)
    if cache_quality(current)["is_scoring_quality"]:
        return current

    backup = _load_standardized_stock_pool(STOCK_POOL_BACKUP_PATH)
    if cache_quality(backup)["is_scoring_quality"]:
        return backup

    return current if not current.empty else backup


def save_stock_pool(frame: pd.DataFrame, *, require_scoring_quality: bool = True) -> None:
    ensure_data_dirs()
    frame = standardize_frame(frame)
    quality = cache_quality(frame)
    if require_scoring_quality and not quality["is_scoring_quality"]:
        raise RuntimeError(
            "刷新数据字段不足，拒绝覆盖本地缓存："
            f"rows={quality['rows']}, sector_ratio={quality['sector_ratio']:.2f}, "
            f"market_cap_ratio={quality['market_cap_ratio']:.2f}"
        )
    if STOCK_POOL_PATH.exists():
        existing = _load_standardized_stock_pool(STOCK_POOL_PATH)
        if cache_quality(existing)["is_scoring_quality"]:
            existing.to_csv(STOCK_POOL_BACKUP_PATH, index=False, encoding="utf-8-sig")
    frame.to_csv(STOCK_POOL_PATH, index=False, encoding="utf-8-sig")


def load_stock_pool() -> pd.DataFrame:
    return _load_standardized_stock_pool(STOCK_POOL_PATH)


def fund_flow_coverage(frame: pd.DataFrame) -> int:
    standardized = standardize_frame(frame)
    fields = [
        "main_net_inflow",
        "main_net_inflow_pct",
        "large_net_inflow",
        "large_net_inflow_pct",
        "sector_main_net_inflow",
        "sector_main_net_inflow_pct",
    ]
    return int(standardized[fields].notna().any(axis=1).sum())


def refresh_public_fund_flow_cache() -> tuple[pd.DataFrame, int, int]:
    frame = load_stock_pool()
    if frame.empty:
        raise RuntimeError("本地股票池为空，请先刷新行情或导入 CSV")

    before = fund_flow_coverage(frame)
    enriched = enrich_with_public_fund_flow(frame)
    after = fund_flow_coverage(enriched)
    if after == 0:
        raise RuntimeError("免费资金流接口暂未返回可用字段，请稍后重试或使用带资金字段的 CSV")

    save_stock_pool(enriched, require_scoring_quality=True)
    return enriched, before, after


def preserve_existing_enrichment(frame: pd.DataFrame) -> pd.DataFrame:
    frame = standardize_frame(frame)
    existing = _load_enrichment_stock_pool()
    if existing.empty:
        return frame

    enriched = frame.merge(
        existing[["code", *PRESERVE_IF_MISSING_COLUMNS]],
        how="left",
        on="code",
        suffixes=("", "_existing"),
    )
    for column in PRESERVE_IF_MISSING_COLUMNS:
        existing_column = f"{column}_existing"
        if existing_column in enriched.columns:
            if column in {"sector", "industry", "fund_flow_source", "fund_flow_note"}:
                enriched[column] = enriched[column].replace("", pd.NA)
            enriched[column] = enriched[column].fillna(enriched[existing_column])
            enriched = enriched.drop(columns=[existing_column])
    return enriched


def import_csv(content: bytes, filename: str) -> pd.DataFrame:
    ensure_data_dirs()
    raw = read_csv_bytes(content)
    frame = standardize_frame(raw)
    save_stock_pool(frame, require_scoring_quality=False)
    safe_name = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]", "_", filename)
    (CACHE_DIR.parent / "imports" / safe_name).write_bytes(content)
    status = DataStatus(
        last_refresh_at=utc_now_iso(),
        last_success_at=utc_now_iso(),
        source="csv",
        ok=True,
        message=f"已导入 {filename}",
        rows=len(frame),
    )
    save_status(status)
    return frame


def _request_eastmoney_json(urls: list[str], params: dict[str, str]) -> dict[str, Any]:
    errors: list[str] = []
    for attempt in range(3):
        for url in urls:
            try:
                response = requests.get(url, params=params, headers=EASTMONEY_HEADERS, timeout=20, trust_env=False)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                errors.append(f"{url}: {exc}")
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError("；".join(errors[-6:]))


def _fetch_eastmoney_pages(urls: list[str], params: dict[str, str], page_size: int = 100) -> list[dict[str, Any]]:
    first_params = {**params, "pn": "1", "pz": str(page_size)}
    payload = _request_eastmoney_json(urls, first_params)
    if payload.get("rc") != 0 or not payload.get("data"):
        raise RuntimeError(f"东方财富接口返回异常：{payload}")

    data = payload["data"]
    total = int(data.get("total") or 0)
    records = list(data.get("diff") or [])
    if total <= len(records):
        return records

    pages = math.ceil(total / page_size)
    for page in range(2, pages + 1):
        page_params = {**params, "pn": str(page), "pz": str(page_size)}
        page_payload = _request_eastmoney_json(urls, page_params)
        if page_payload.get("rc") != 0 or not page_payload.get("data"):
            raise RuntimeError(f"东方财富第 {page} 页返回异常：{page_payload}")
        records.extend(page_payload["data"].get("diff") or [])
    return records


def _eastmoney_stock_spot() -> pd.DataFrame:
    records = _fetch_eastmoney_pages(
        EASTMONEY_STOCK_URLS,
        {
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": (
                "f2,f3,f5,f6,f8,f9,f10,f12,f14,f20,f21,f23,f24,f25,"
                "f62,f66,f69,f72,f75,f100,f102,f103,f109,f115,f184"
            ),
        },
    )
    frame = pd.DataFrame(records)
    if frame.empty:
        raise RuntimeError("东方财富全 A 股行情为空")
    return pd.DataFrame(
        {
            "code": frame.get("f12"),
            "name": frame.get("f14"),
            "sector": frame.get("f100"),
            "industry": frame.get("f100"),
            "current_price": frame.get("f2"),
            "market_cap": frame.get("f20"),
            "turnover": frame.get("f6"),
            "pct_change": frame.get("f3"),
            "volume_ratio": frame.get("f10"),
            "pe": frame.get("f9"),
            "pb": frame.get("f23"),
            "historical_pe_percentile": None,
            "main_net_inflow": frame.get("f62"),
            "main_net_inflow_pct": frame.get("f184"),
            "large_net_inflow": frame.get("f72"),
            "large_net_inflow_pct": frame.get("f75"),
        }
    )


def _eastmoney_industry_boards() -> pd.DataFrame:
    records = _fetch_eastmoney_pages(
        EASTMONEY_INDUSTRY_URLS,
        {
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:90 t:2 f:!50",
            "fields": "f3,f6,f8,f12,f14,f20,f62,f104,f105,f128,f136,f140,f184",
        },
    )
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=["sector", "sector_pct_change", "sector_turnover_growth"])
    return pd.DataFrame(
        {
            "sector": frame.get("f14"),
            "sector_pct_change": frame.get("f3"),
            "sector_turnover": frame.get("f6"),
            "sector_turnover_growth": frame.get("f8"),
            "sector_main_net_inflow": frame.get("f62"),
            "sector_main_net_inflow_pct": frame.get("f184"),
        }
    )


def _merge_sector_stats(stocks: pd.DataFrame, sectors: pd.DataFrame) -> pd.DataFrame:
    if sectors.empty:
        return stocks
    merged = stocks.merge(sectors, how="left", on="sector", suffixes=("", "_sector"))
    for column in (
        "sector_pct_change",
        "sector_turnover",
        "sector_turnover_growth",
        "sector_main_net_inflow",
        "sector_main_net_inflow_pct",
    ):
        sector_column = f"{column}_sector"
        if sector_column in merged.columns:
            merged[column] = merged[column].fillna(merged[sector_column])
            merged = merged.drop(columns=[sector_column])
    return merged


def _eastmoney_stock_fund_flow_rank() -> pd.DataFrame:
    records = _fetch_eastmoney_pages(
        EASTMONEY_FUND_FLOW_URLS,
        {
            "fid": "f62",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "fs": "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2",
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f124",
        },
    )
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=["code", "main_net_inflow", "main_net_inflow_pct", "large_net_inflow", "large_net_inflow_pct"])
    return standardize_frame(
        pd.DataFrame(
            {
                "code": frame.get("f12"),
                "name": frame.get("f14"),
                "main_net_inflow": frame.get("f62"),
                "main_net_inflow_pct": frame.get("f184"),
                "large_net_inflow": frame.get("f72"),
                "large_net_inflow_pct": frame.get("f75"),
            }
        )
    )[["code", "main_net_inflow", "main_net_inflow_pct", "large_net_inflow", "large_net_inflow_pct"]]


def _eastmoney_sector_fund_flow_rank() -> pd.DataFrame:
    records = _fetch_eastmoney_pages(
        EASTMONEY_FUND_FLOW_URLS,
        {
            "po": "1",
            "np": "1",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "fltt": "2",
            "invt": "2",
            "fid0": "f62",
            "fs": "m:90 t:2",
            "stat": "1",
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f124",
        },
    )
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=["sector", "sector_pct_change", "sector_main_net_inflow", "sector_main_net_inflow_pct"])
    return pd.DataFrame(
        {
            "sector": frame.get("f14"),
            "sector_pct_change": frame.get("f3"),
            "sector_main_net_inflow": frame.get("f62"),
            "sector_main_net_inflow_pct": frame.get("f184"),
        }
    )


def _fill_from_new_data(merged: pd.DataFrame, columns: list[str], *, prefer_new: bool = True) -> pd.DataFrame:
    for column in columns:
        new_column = f"{column}_new"
        if new_column in merged.columns:
            if column in {"fund_flow_source", "fund_flow_note"}:
                merged[column] = merged[column].replace("", pd.NA)
                merged[new_column] = merged[new_column].replace("", pd.NA)
            if prefer_new:
                merged[column] = merged[new_column].combine_first(merged[column])
            else:
                merged[column] = merged[column].combine_first(merged[new_column])
            merged = merged.drop(columns=[new_column])
    return merged


def _recent_report_dates(*, annual_only: bool = False, years_back: int = 4) -> list[str]:
    today = datetime.now().date()
    quarters = [(3, 31), (6, 30), (9, 30), (12, 31)]
    dates: list[str] = []
    for year in range(today.year, today.year - years_back - 1, -1):
        for month, day in reversed(quarters):
            if annual_only and month != 12:
                continue
            try:
                period_date = datetime(year, month, day).date()
            except ValueError:
                continue
            if period_date <= today:
                dates.append(f"{year}{month:02d}{day:02d}")
    return dates


def _select_codes(frame: pd.DataFrame, codes: list[str] | None) -> set[str] | None:
    if codes:
        selected = {_normalize_code(code) for code in codes if _normalize_code(code)}
        return selected or None
    if frame.empty:
        return None
    return set(frame["code"].dropna().astype(str))


def _filter_metric_codes(frame: pd.DataFrame, codes: set[str] | None) -> pd.DataFrame:
    if codes is None or frame.empty:
        return frame
    return frame[frame["code"].isin(codes)].copy()


def _first_available_akshare_frame(fetcher: Any, dates: list[str], *, min_rows: int = 1) -> pd.DataFrame:
    last_error: Exception | None = None
    for report_date in dates:
        try:
            raw = fetcher(date=report_date)
            if raw is not None and not raw.empty and len(raw) >= min_rows:
                return raw
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def _performance_financial_metrics(codes: set[str] | None = None) -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 AkShare，无法补充财务指标。") from exc

    raw = _first_available_akshare_frame(ak.stock_yjbb_em, _recent_report_dates(), min_rows=100)
    if raw.empty:
        return pd.DataFrame(columns=["code", *FINANCIAL_METRIC_COLUMNS, "sector", "industry"])

    eps = raw.get("每股收益", pd.Series([None] * len(raw))).map(_to_number)
    cashflow_per_share = raw.get("每股经营现金流量", pd.Series([None] * len(raw))).map(_to_number)
    eps_base = pd.to_numeric(eps, errors="coerce").replace(0, pd.NA)
    cashflow_ratio = pd.to_numeric(cashflow_per_share, errors="coerce") / eps_base

    metrics = standardize_frame(
        pd.DataFrame(
            {
                "code": raw.get("股票代码"),
                "name": raw.get("股票简称"),
                "sector": raw.get("所处行业"),
                "industry": raw.get("所处行业"),
                "roe": raw.get("净资产收益率"),
                "revenue_growth": raw.get("营业总收入-同比增长"),
                "profit_growth": raw.get("净利润-同比增长"),
                "cashflow_ratio": cashflow_ratio,
                "revenue": raw.get("营业总收入-营业总收入"),
                "net_profit": raw.get("净利润-净利润"),
            }
        )
    )
    return _filter_metric_codes(
        metrics[["code", "sector", "industry", "roe", "revenue_growth", "profit_growth", "cashflow_ratio", "revenue", "net_profit"]],
        codes,
    )


def _dividend_financial_metrics(codes: set[str] | None = None) -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 AkShare，无法补充分红指标。") from exc

    raw = _first_available_akshare_frame(ak.stock_fhps_em, _recent_report_dates(annual_only=True), min_rows=100)
    if raw.empty:
        return pd.DataFrame(columns=["code", "dividend_yield", "dividend_payout_ratio"])

    dividend_yield = raw.get("现金分红-股息率", pd.Series([None] * len(raw))).map(_to_number)
    dividend_yield_numeric = pd.to_numeric(dividend_yield, errors="coerce")
    if dividend_yield_numeric.notna().any() and dividend_yield_numeric.quantile(0.95) <= 1.5:
        dividend_yield_numeric = dividend_yield_numeric * 100

    cash_per_ten = raw.get("现金分红-现金分红比例", pd.Series([None] * len(raw))).map(_to_number)
    eps = raw.get("每股收益", pd.Series([None] * len(raw))).map(_to_number)
    eps_base = pd.to_numeric(eps, errors="coerce").replace(0, pd.NA)
    payout_ratio = pd.to_numeric(cash_per_ten, errors="coerce") / 10 / eps_base * 100

    metrics = standardize_frame(
        pd.DataFrame(
            {
                "code": raw.get("代码"),
                "name": raw.get("名称"),
                "dividend_yield": dividend_yield_numeric,
                "dividend_payout_ratio": payout_ratio,
            }
        )
    )
    return _filter_metric_codes(metrics[["code", "dividend_yield", "dividend_payout_ratio"]], codes)


def _fill_text_from_new_data(merged: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        new_column = f"{column}_new"
        if new_column in merged.columns:
            merged[column] = merged[column].replace("", pd.NA)
            merged[new_column] = merged[new_column].replace("", pd.NA)
            merged[column] = merged[column].fillna(merged[new_column])
            merged = merged.drop(columns=[new_column])
    return merged


def enrich_with_public_financial_metrics(frame: pd.DataFrame, codes: list[str] | None = None) -> pd.DataFrame:
    enriched = standardize_frame(frame)
    selected_codes = _select_codes(enriched, codes)

    try:
        performance = _performance_financial_metrics(selected_codes)
        if not performance.empty:
            enriched = enriched.merge(performance, how="left", on="code", suffixes=("", "_new"))
            enriched = _fill_from_new_data(
                enriched,
                ["roe", "revenue_growth", "profit_growth", "cashflow_ratio", "revenue", "net_profit"],
            )
            enriched = _fill_text_from_new_data(enriched, ["sector", "industry"])
    except Exception:
        pass

    try:
        dividend = _dividend_financial_metrics(selected_codes)
        if not dividend.empty:
            enriched = enriched.merge(dividend, how="left", on="code", suffixes=("", "_new"))
            enriched = _fill_from_new_data(enriched, ["dividend_yield", "dividend_payout_ratio"])
    except Exception:
        pass

    return standardize_frame(enriched)


def financial_metric_coverage(frame: pd.DataFrame, codes: list[str] | None = None) -> int:
    standardized = standardize_frame(frame)
    selected_codes = _select_codes(standardized, codes)
    checked = _filter_metric_codes(standardized, selected_codes)
    if checked.empty:
        return 0
    return int(checked[CORE_FINANCIAL_METRIC_COLUMNS].notna().any(axis=1).sum())


def financial_metric_complete_coverage(frame: pd.DataFrame, codes: list[str] | None = None) -> int:
    standardized = standardize_frame(frame)
    selected_codes = _select_codes(standardized, codes)
    checked = _filter_metric_codes(standardized, selected_codes)
    if checked.empty:
        return 0
    return int(checked[CORE_FINANCIAL_METRIC_COLUMNS].notna().all(axis=1).sum())


def financial_metric_missing_cells(frame: pd.DataFrame, codes: list[str] | None = None) -> int:
    standardized = standardize_frame(frame)
    selected_codes = _select_codes(standardized, codes)
    checked = _filter_metric_codes(standardized, selected_codes)
    if checked.empty:
        return len(set(codes or [])) * len(CORE_FINANCIAL_METRIC_COLUMNS)
    return int(checked[CORE_FINANCIAL_METRIC_COLUMNS].isna().sum().sum())


def refresh_public_financial_metrics_cache(codes: list[str] | None = None) -> tuple[pd.DataFrame, int, int]:
    frame = load_stock_pool()
    if frame.empty:
        raise RuntimeError("本地股票池为空，请先刷新行情或导入 CSV")

    before = financial_metric_complete_coverage(frame, codes)
    enriched = enrich_with_public_financial_metrics(frame, codes)
    after = financial_metric_complete_coverage(enriched, codes)
    any_coverage = financial_metric_coverage(enriched, codes)
    if any_coverage == 0:
        raise RuntimeError("免费财务接口暂未返回可用字段，请稍后重试或使用带财务字段的 CSV")

    save_stock_pool(enriched, require_scoring_quality=True)
    return enriched, before, after


def ensure_financial_metrics_for_codes(codes: list[str]) -> pd.DataFrame:
    frame = load_stock_pool()
    if frame.empty or not codes:
        return frame

    selected = [_normalize_code(code) for code in codes if _normalize_code(code)]
    if not selected:
        return frame

    before_missing = financial_metric_missing_cells(frame, selected)
    if before_missing <= 0:
        return frame

    try:
        enriched = enrich_with_public_financial_metrics(frame, selected)
        after_missing = financial_metric_missing_cells(enriched, selected)
        if after_missing < before_missing:
            save_stock_pool(enriched, require_scoring_quality=True)
            return enriched
        return frame
    except Exception:
        return frame


def _finalize_public_stock_pool(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = preserve_existing_enrichment(frame)
    enriched = enrich_with_public_financial_metrics(enriched)
    enriched = enrich_with_public_fund_flow(enriched)
    return standardize_frame(enriched)


def _akshare_ths_stock_fund_flow() -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 AkShare，无法使用同花顺资金流备用源。") from exc

    raw = ak.stock_fund_flow_individual(symbol="即时")
    if raw is None or raw.empty:
        return pd.DataFrame(
            columns=["code", "main_net_inflow", "main_net_inflow_pct", "fund_flow_source", "fund_flow_note"]
        )

    net_flow = raw.get("净额", pd.Series([None] * len(raw))).map(_to_number)
    turnover = raw.get("成交额", pd.Series([None] * len(raw))).map(_to_number)
    turnover_base = pd.to_numeric(turnover, errors="coerce").replace(0, pd.NA)
    net_pct = pd.to_numeric(net_flow, errors="coerce") / turnover_base * 100

    return standardize_frame(
        pd.DataFrame(
            {
                "code": raw.get("股票代码"),
                "name": raw.get("股票简称"),
                "main_net_inflow": net_flow,
                "main_net_inflow_pct": net_pct,
                "fund_flow_source": "同花顺资金净额代理",
                "fund_flow_note": "由同花顺个股资金流净额/成交额估算，非东方财富主力口径。",
            }
        )
    )[["code", "main_net_inflow", "main_net_inflow_pct", "fund_flow_source", "fund_flow_note"]]


def enrich_with_public_fund_flow(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = standardize_frame(frame)

    try:
        stock_flow = _eastmoney_stock_fund_flow_rank()
        if not stock_flow.empty:
            enriched = enriched.merge(stock_flow, how="left", on="code", suffixes=("", "_new"))
            has_eastmoney_flow = enriched[
                ["main_net_inflow_new", "main_net_inflow_pct_new", "large_net_inflow_new", "large_net_inflow_pct_new"]
            ].notna().any(axis=1)
            enriched = _fill_from_new_data(
                enriched,
                ["main_net_inflow", "main_net_inflow_pct", "large_net_inflow", "large_net_inflow_pct"],
            )
            enriched.loc[has_eastmoney_flow, "fund_flow_source"] = "东方财富主力资金"
            enriched.loc[has_eastmoney_flow, "fund_flow_note"] = "东方财富公开资金流排名字段。"
    except Exception:
        pass

    try:
        ths_flow = _akshare_ths_stock_fund_flow()
        if not ths_flow.empty:
            existing_flow = enriched[
                ["main_net_inflow", "main_net_inflow_pct", "large_net_inflow", "large_net_inflow_pct"]
            ].notna().any(axis=1)
            enriched = enriched.merge(ths_flow, how="left", on="code", suffixes=("", "_new"))
            has_ths_flow = enriched[["main_net_inflow_new", "main_net_inflow_pct_new"]].notna().any(axis=1)
            enriched = _fill_from_new_data(
                enriched,
                ["main_net_inflow", "main_net_inflow_pct"],
                prefer_new=False,
            )
            source_mask = (~existing_flow.to_numpy()) & has_ths_flow.to_numpy()
            for column in ("fund_flow_source", "fund_flow_note"):
                new_column = f"{column}_new"
                if new_column in enriched.columns:
                    enriched.loc[source_mask, column] = enriched.loc[source_mask, new_column]
                    enriched = enriched.drop(columns=[new_column])
    except Exception:
        pass

    try:
        sector_flow = _eastmoney_sector_fund_flow_rank()
        if not sector_flow.empty:
            enriched = enriched.merge(sector_flow, how="left", on="sector", suffixes=("", "_new"))
            enriched = _fill_from_new_data(
                enriched,
                ["sector_pct_change", "sector_main_net_inflow", "sector_main_net_inflow_pct"],
            )
    except Exception:
        pass

    return standardize_frame(enriched)


def _optional_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series([None] * len(frame), index=frame.index)


def _scale_numeric(value: Any, multiplier: float) -> float | None:
    number = _to_number(value)
    return number * multiplier if number is not None else None


def fetch_eastmoney_stock_pool() -> pd.DataFrame:
    stocks = _eastmoney_stock_spot()
    sectors = _eastmoney_industry_boards()
    frame = _finalize_public_stock_pool(_merge_sector_stats(stocks, sectors))
    save_stock_pool(frame)
    return frame


def fetch_akshare_stock_pool() -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 AkShare。请运行 pip install akshare，或先使用 CSV 导入。") from exc

    spot = ak.stock_zh_a_spot_em()
    industry = None
    try:
        industry = ak.stock_board_industry_name_em()
    except Exception:
        industry = None

    rename_map = {
        "代码": "code",
        "名称": "name",
        "最新价": "current_price",
        "总市值": "market_cap",
        "成交额": "turnover",
        "涨跌幅": "pct_change",
        "量比": "volume_ratio",
        "市盈率-动态": "pe",
        "市净率": "pb",
        "主力净流入": "main_net_inflow",
        "主力净占比": "main_net_inflow_pct",
        "大单净流入": "large_net_inflow",
        "大单净占比": "large_net_inflow_pct",
    }
    spot = spot.rename(columns=rename_map)
    if "industry" not in spot.columns:
        spot["industry"] = ""
    if "sector" not in spot.columns:
        spot["sector"] = spot.get("industry", "")

    frame = standardize_frame(spot)

    if industry is not None and not industry.empty:
        industry = industry.rename(
            columns={
                "板块名称": "sector",
                "涨跌幅": "sector_pct_change",
                "成交额": "sector_turnover",
                "主力净流入": "sector_main_net_inflow",
                "主力净占比": "sector_main_net_inflow_pct",
            }
        )
        sector_columns = [
            column
            for column in [
                "sector",
                "sector_pct_change",
                "sector_turnover",
                "sector_main_net_inflow",
                "sector_main_net_inflow_pct",
            ]
            if column in industry.columns
        ]
        sector_stats = industry[sector_columns].copy()
        frame = _merge_sector_stats(frame, sector_stats)

    frame = _finalize_public_stock_pool(frame)
    save_stock_pool(frame)
    return frame


def _parse_ths_page_count(html: str) -> int:
    match = re.search(r'class=["\']page_info["\']>\s*\d+\s*/\s*(\d+)', html)
    if not match:
        return 1
    return max(1, int(match.group(1)))


def _fetch_ths_industry_page(code: str, page: int) -> tuple[pd.DataFrame, int]:
    suffix = "" if page == 1 else f"page/{page}/"
    url = f"http://q.10jqka.com.cn/thshy/detail/code/{code}/{suffix}"
    response = requests.get(url, headers=THS_HEADERS, timeout=20, trust_env=False)
    response.raise_for_status()
    response.encoding = "gbk"
    tables = pd.read_html(io.StringIO(response.text))
    if not tables:
        raise RuntimeError(f"同花顺行业 {code} 第 {page} 页没有成分股表格")
    return tables[0], _parse_ths_page_count(response.text)


def fetch_ths_sector_stock_pool() -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 AkShare，无法使用同花顺行业备用源。") from exc

    industries = ak.stock_board_industry_name_ths()
    if industries is None or industries.empty:
        raise RuntimeError("同花顺行业列表为空")

    summary = pd.DataFrame()
    try:
        summary = ak.stock_board_industry_summary_ths().rename(
            columns={"板块": "sector", "涨跌幅": "sector_pct_change"}
        )
    except Exception:
        summary = pd.DataFrame(columns=["sector", "sector_pct_change"])
    sector_pct = {
        str(row["sector"]).strip(): row.get("sector_pct_change")
        for _, row in summary.iterrows()
        if str(row.get("sector") or "").strip()
    }

    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for _, industry in industries.iterrows():
        sector = str(industry.get("name") or "").strip()
        code = str(industry.get("code") or "").strip()
        if not sector or not code:
            continue

        try:
            first_page, page_count = _fetch_ths_industry_page(code, 1)
            pages = [first_page]
            for page in range(2, page_count + 1):
                page_frame, _ = _fetch_ths_industry_page(code, page)
                pages.append(page_frame)
                time.sleep(0.03)
        except Exception as exc:
            errors.append(f"{sector}: {exc}")
            continue

        detail = pd.concat(pages, ignore_index=True)
        detail["sector"] = sector
        detail["industry"] = sector
        detail["sector_pct_change"] = sector_pct.get(sector)
        detail = detail.rename(
            columns={
                "代码": "code",
                "名称": "name",
                "涨跌幅(%)": "pct_change",
                "成交额": "turnover",
                "流通市值": "market_cap",
                "量比": "volume_ratio",
                "市盈率": "pe",
            }
        )
        frames.append(detail)
        time.sleep(0.05)

    if not frames:
        detail = f"；部分错误：{'；'.join(errors[:5])}" if errors else ""
        raise RuntimeError(f"同花顺行业成分股为空{detail}")

    frame = _finalize_public_stock_pool(pd.concat(frames, ignore_index=True))
    quality = cache_quality(frame)
    if not quality["is_scoring_quality"]:
        raise RuntimeError(
            "同花顺行业备用源字段不足："
            f"rows={quality['rows']}, sector_ratio={quality['sector_ratio']:.2f}, "
            f"market_cap_ratio={quality['market_cap_ratio']:.2f}"
        )
    save_stock_pool(frame)
    return frame


def _fetch_tencent_rank_page(offset: int, count: int = 200) -> tuple[list[dict[str, Any]], int]:
    url = "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
    params = {
        "_appver": "11.17.0",
        "board_code": "aStock",
        "sort_type": "price",
        "direct": "down",
        "offset": str(offset),
        "count": str(count),
    }
    response = requests.get(url, params=params, headers=TENCENT_HEADERS, timeout=20, trust_env=False)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"腾讯行情接口返回异常：{payload}")
    data = payload.get("data") or {}
    return list(data.get("rank_list") or []), int(data.get("total") or 0)


def fetch_tencent_stock_pool() -> pd.DataFrame:
    frame = _fetch_tencent_market_frame()
    frame = _finalize_public_stock_pool(frame)
    if not cache_quality(frame)["is_scoring_quality"]:
        raise RuntimeError("腾讯行情字段不足，且没有可合并的高质量本地缓存")
    save_stock_pool(frame)
    return frame


def _fetch_tencent_market_frame() -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    offset = 0
    total = 1
    page_size = 200
    while offset < total:
        page_records, total = _fetch_tencent_rank_page(offset, page_size)
        if not page_records:
            break
        records.extend(page_records)
        offset += page_size
        time.sleep(0.05)

    raw = pd.DataFrame(records)
    if raw.empty:
        raise RuntimeError("腾讯全 A 股行情为空")

    return pd.DataFrame(
        {
            "code": raw.get("code"),
            "name": raw.get("name"),
            "current_price": raw.get("zxj"),
            "market_cap": raw.get("zsz").map(lambda value: _scale_numeric(value, 100_000_000)),
            "turnover": raw.get("turnover").map(lambda value: _scale_numeric(value, 10_000)),
            "pct_change": raw.get("zdf"),
            "volume_ratio": raw.get("lb"),
            "pe": raw.get("pe_ttm"),
            "pb": raw.get("pn"),
        }
    )


def fetch_baostock_industry_map() -> pd.DataFrame:
    try:
        import baostock as bs  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 Baostock，无法使用免费行业映射。请运行 pip install baostock。") from exc

    login_result = bs.login()
    try:
        if login_result.error_code != "0":
            raise RuntimeError(f"Baostock 登录失败：{login_result.error_msg}")
        result = bs.query_stock_industry()
        if result.error_code != "0":
            raise RuntimeError(f"Baostock 行业查询失败：{result.error_msg}")

        rows: list[list[str]] = []
        while result.next():
            rows.append(result.get_row_data())
        raw = pd.DataFrame(rows, columns=result.fields)
    finally:
        bs.logout()

    if raw.empty:
        raise RuntimeError("Baostock 行业映射为空")

    industry = raw["industry"].fillna("").astype(str).str.strip()
    industry = industry.str.replace(r"^[A-Z]\d{2}", "", regex=True).str.strip()
    return standardize_frame(
        pd.DataFrame(
            {
                "code": raw.get("code"),
                "name": raw.get("code_name"),
                "sector": industry,
                "industry": industry,
            }
        )
    )


def _merge_industry_map(frame: pd.DataFrame, industry_map: pd.DataFrame) -> pd.DataFrame:
    stocks = standardize_frame(frame)
    sectors = standardize_frame(industry_map)
    if sectors.empty:
        return stocks
    merged = stocks.merge(
        sectors[["code", "sector", "industry"]],
        how="left",
        on="code",
        suffixes=("", "_mapped"),
    )
    for column in ("sector", "industry"):
        mapped = f"{column}_mapped"
        merged[column] = merged[column].replace("", pd.NA).fillna(merged[mapped])
        merged = merged.drop(columns=[mapped])
    return merged


def fetch_tencent_baostock_stock_pool() -> pd.DataFrame:
    frame = _merge_industry_map(_fetch_tencent_market_frame(), fetch_baostock_industry_map())
    frame = _finalize_public_stock_pool(frame)
    quality = cache_quality(frame)
    if not quality["is_scoring_quality"]:
        raise RuntimeError(
            "腾讯行情 + Baostock 行业映射字段不足："
            f"rows={quality['rows']}, sector_ratio={quality['sector_ratio']:.2f}, "
            f"market_cap_ratio={quality['market_cap_ratio']:.2f}"
        )
    save_stock_pool(frame)
    return frame


def has_scoring_cache() -> bool:
    return bool(cache_quality(_load_enrichment_stock_pool())["is_scoring_quality"])


def fetch_sina_stock_pool() -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 AkShare，无法使用新浪行情备用源。") from exc

    spot = ak.stock_zh_a_spot()
    rename_map = {
        "代码": "code",
        "名称": "name",
        "最新价": "current_price",
        "成交额": "turnover",
        "涨跌幅": "pct_change",
    }
    frame = spot.rename(columns=rename_map)
    frame = _finalize_public_stock_pool(frame)
    if not cache_quality(frame)["is_scoring_quality"]:
        raise RuntimeError("新浪行情字段不足，且没有可合并的高质量本地缓存")
    save_stock_pool(frame)
    return frame


def fetch_sina_sector_stock_pool() -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 AkShare，无法使用新浪行业备用源。") from exc

    boards = ak.stock_sector_spot(indicator="新浪行业")
    if boards is None or boards.empty:
        raise RuntimeError("新浪行业板块列表为空")

    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for _, board in boards.iterrows():
        label = str(board.get("label") or "").strip()
        sector = str(board.get("板块") or label).strip()
        if not label:
            continue
        try:
            detail = ak.stock_sector_detail(sector=label)
        except Exception as exc:
            errors.append(f"{sector}: {exc}")
            continue

        if detail is None or detail.empty:
            continue

        mktcap = pd.to_numeric(_optional_series(detail, "mktcap"), errors="coerce") * 10_000
        frames.append(
            pd.DataFrame(
                {
                    "code": _optional_series(detail, "code"),
                    "name": _optional_series(detail, "name"),
                    "sector": sector,
                    "industry": sector,
                    "current_price": _optional_series(detail, "trade"),
                    "market_cap": mktcap,
                    "turnover": _optional_series(detail, "amount"),
                    "pct_change": _optional_series(detail, "changepercent"),
                    "pe": _optional_series(detail, "per"),
                    "pb": _optional_series(detail, "pb"),
                    "sector_pct_change": board.get("涨跌幅"),
                }
            )
        )
        time.sleep(0.05)

    if not frames:
        detail = f"；部分错误：{'；'.join(errors[:5])}" if errors else ""
        raise RuntimeError(f"新浪行业板块成分股为空{detail}")

    frame = _finalize_public_stock_pool(pd.concat(frames, ignore_index=True))
    quality = cache_quality(frame)
    if not quality["is_scoring_quality"]:
        raise RuntimeError(
            "新浪行业备用源字段不足："
            f"rows={quality['rows']}, sector_ratio={quality['sector_ratio']:.2f}, "
            f"market_cap_ratio={quality['market_cap_ratio']:.2f}"
        )
    save_stock_pool(frame)
    return frame


def fetch_public_stock_pool() -> tuple[pd.DataFrame, str]:
    try:
        return fetch_eastmoney_stock_pool(), "eastmoney"
    except Exception as eastmoney_error:
        try:
            return fetch_akshare_stock_pool(), "akshare"
        except Exception as akshare_error:
            tencent_error: Exception | None = None
            tencent_baostock_error: Exception | None = None
            if has_scoring_cache():
                try:
                    return fetch_tencent_stock_pool(), "tencent_basic"
                except Exception as exc:
                    tencent_error = exc
            try:
                return fetch_tencent_baostock_stock_pool(), "tencent_baostock"
            except Exception as exc:
                tencent_baostock_error = exc
            try:
                return fetch_ths_sector_stock_pool(), "ths_sector"
            except Exception as ths_error:
                try:
                    return fetch_sina_sector_stock_pool(), "sina_sector"
                except Exception as sina_sector_error:
                    if tencent_error is None:
                        try:
                            return fetch_tencent_stock_pool(), "tencent_basic"
                        except Exception as exc:
                            tencent_error = exc
                    try:
                        return fetch_sina_stock_pool(), "sina_basic"
                    except Exception as sina_error:
                        raise RuntimeError(
                            "东方财富公开接口失败："
                            f"{eastmoney_error}；AkShare 东方财富备用接口失败：{akshare_error}；"
                            f"腾讯+Baostock 备用接口失败：{tencent_baostock_error}；"
                            f"同花顺行业备用接口失败：{ths_error}；"
                            f"新浪行业备用接口失败：{sina_sector_error}；"
                            f"腾讯行情备用接口失败：{tencent_error}；"
                            f"新浪基础行情备用接口也失败：{sina_error}"
                        ) from sina_error
