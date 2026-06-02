from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .models import (
    AiAnalysisResponse,
    AmbushBrief,
    AppConfig,
    DataStatus,
    HoldingAnalysisResponse,
    HoldingListResponse,
    ScreenResponse,
    WatchlistResponse,
)
from .paths import (
    AI_ANALYSIS_PATH,
    AMBUSH_BRIEF_PATH,
    AMBUSH_PIPELINE_PATH,
    AMBUSH_RESULTS_PATH,
    AMBUSH_SNAPSHOT_PATH,
    CONFIG_PATH,
    HOLDING_ANALYSIS_PATH,
    HOLDINGS_PATH,
    RESULTS_PATH,
    STATUS_PATH,
    WATCHLIST_PATH,
    ensure_data_dirs,
)


T = TypeVar("T", bound=BaseModel)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_data_dirs()
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def load_model(path: Path, model: type[T], default: T) -> T:
    try:
        return model.model_validate(read_json(path, default.model_dump()))
    except Exception:
        return default


def save_model(path: Path, model: BaseModel) -> None:
    write_json(path, model.model_dump(mode="json"))


def load_config() -> AppConfig:
    return load_model(CONFIG_PATH, AppConfig, AppConfig())


def save_config(config: AppConfig) -> None:
    save_model(CONFIG_PATH, config)


def load_status() -> DataStatus:
    return load_model(STATUS_PATH, DataStatus, DataStatus())


def save_status(status: DataStatus) -> None:
    save_model(STATUS_PATH, status)


def load_results() -> ScreenResponse | None:
    if not RESULTS_PATH.exists():
        return None
    return ScreenResponse.model_validate(read_json(RESULTS_PATH, {}))


def save_results(results: ScreenResponse) -> None:
    save_model(RESULTS_PATH, results)


def load_ai_analysis() -> AiAnalysisResponse | None:
    if not AI_ANALYSIS_PATH.exists():
        return None
    return AiAnalysisResponse.model_validate(read_json(AI_ANALYSIS_PATH, {}))


def save_ai_analysis(analysis: AiAnalysisResponse) -> None:
    save_model(AI_ANALYSIS_PATH, analysis)


def clear_ai_analysis() -> None:
    try:
        AI_ANALYSIS_PATH.unlink()
    except FileNotFoundError:
        pass


def load_holdings() -> HoldingListResponse:
    return load_model(HOLDINGS_PATH, HoldingListResponse, HoldingListResponse(generated_at=utc_now_iso()))


def save_holdings(holdings: HoldingListResponse) -> None:
    save_model(HOLDINGS_PATH, holdings)


def load_watchlist() -> WatchlistResponse:
    return load_model(WATCHLIST_PATH, WatchlistResponse, WatchlistResponse(generated_at=utc_now_iso()))


def save_watchlist(watchlist: WatchlistResponse) -> None:
    save_model(WATCHLIST_PATH, watchlist)


def load_holding_analysis() -> HoldingAnalysisResponse | None:
    if not HOLDING_ANALYSIS_PATH.exists():
        return None
    return HoldingAnalysisResponse.model_validate(read_json(HOLDING_ANALYSIS_PATH, {}))


def save_holding_analysis(analysis: HoldingAnalysisResponse) -> None:
    save_model(HOLDING_ANALYSIS_PATH, analysis)


def clear_holding_analysis() -> None:
    try:
        HOLDING_ANALYSIS_PATH.unlink()
    except FileNotFoundError:
        pass


def load_ambush_results() -> dict[str, Any] | None:
    if not AMBUSH_RESULTS_PATH.exists():
        return None
    return read_json(AMBUSH_RESULTS_PATH, {})


def save_ambush_results(data: dict[str, Any]) -> None:
    write_json(AMBUSH_RESULTS_PATH, data)


def load_ambush_brief() -> AmbushBrief | None:
    """加载简报"""
    if not AMBUSH_BRIEF_PATH.exists():
        return None
    try:
        return AmbushBrief.model_validate(read_json(AMBUSH_BRIEF_PATH, {}))
    except Exception:
        return None


def save_ambush_brief(brief: AmbushBrief) -> None:
    """保存简报"""
    save_model(AMBUSH_BRIEF_PATH, brief)


def load_ambush_snapshot() -> dict[str, Any] | None:
    """加载上次管道快照"""
    if not AMBUSH_SNAPSHOT_PATH.exists():
        return None
    return read_json(AMBUSH_SNAPSHOT_PATH, {})


def save_ambush_snapshot(data: dict[str, Any]) -> None:
    """保存管道快照"""
    write_json(AMBUSH_SNAPSHOT_PATH, data)
