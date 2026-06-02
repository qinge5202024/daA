from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", ROOT_DIR / "data")).expanduser()
IMPORTS_DIR = DATA_DIR / "imports"
CACHE_DIR = DATA_DIR / "cache"
HISTORY_DIR = CACHE_DIR / "history"
RESULTS_DIR = DATA_DIR / "results"
CONFIG_PATH = DATA_DIR / "config.json"
STATUS_PATH = DATA_DIR / "status.json"
STOCK_POOL_PATH = CACHE_DIR / "stock_pool.csv"
STOCK_POOL_BACKUP_PATH = CACHE_DIR / "stock_pool.last_good.csv"
RESULTS_PATH = RESULTS_DIR / "screen_results.json"
AI_ANALYSIS_PATH = RESULTS_DIR / "ai_analysis.json"
HOLDINGS_PATH = DATA_DIR / "holdings.json"
WATCHLIST_PATH = DATA_DIR / "watchlist.json"
HOLDING_ANALYSIS_PATH = RESULTS_DIR / "holding_analysis.json"
AMBUSH_RESULTS_PATH = RESULTS_DIR / "ambush_results.json"
AMBUSH_CONFIG_PATH = DATA_DIR / "ambush_config.json"
AMBUSH_PIPELINE_PATH = DATA_DIR / "ambush_pipeline.json"
AMBUSH_BRIEF_PATH = RESULTS_DIR / "ambush_brief.json"
AMBUSH_SNAPSHOT_PATH = DATA_DIR / "ambush_snapshot.json"
CONCEPT_CACHE_PATH = CACHE_DIR / "concept_cache.json"


def ensure_data_dirs() -> None:
    for path in (DATA_DIR, IMPORTS_DIR, CACHE_DIR, HISTORY_DIR, RESULTS_DIR):
        path.mkdir(parents=True, exist_ok=True)
