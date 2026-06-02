"""潜伏模块 - 题材概念匹配器（基本版）

不需要额外网络请求，直接利用 stock_pool 中已有的 sector/industry 字段，
加上股票名称的关键词匹配，实现题材预期评分。

扩展版可接入 akshare 的概念板块数据，但基本版优先零依赖零延迟。
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .paths import CONCEPT_CACHE_PATH, ensure_data_dirs


# 内置热点题材关键词表（可扩展）
# 格式：{ "题材类别": ["关键词1", "关键词2", ...] }
BUILTIN_THEMES: dict[str, list[str]] = {
    "人工智能": ["人工智能", "AI", "智能", "算法", "大模型", "机器学习"],
    "芯片半导体": ["芯片", "半导体", "集成电路", "封测", "光刻", "元器件", "晶圆"],
    "新能源": ["新能源", "光伏", "锂电", "电池", "储能", "氢能", "风电", "太阳能"],
    "低空经济": ["低空", "飞行汽车", "无人机", "航空装备", "航天"],
    "机器人": ["机器人", "人形机器人", "自动化", "工业机器", "机器视觉"],
    "消费电子": ["消费电子", "手机", "耳机", "智能穿戴", "VR", "AR"],
    "汽车": ["汽车", "新能源车", "整车", "汽车零部件", "自动驾驶"],
    "医药医疗": ["医药", "医疗", "药", "生物", "医美", "CXO", "创新药"],
    "数字经济": ["数据", "算力", "云计算", "信创", "软件", "数字经济", "数字"],
    "军工": ["军工", "国防", "航天", "航空", "兵工", "船舶"],
    "电力电网": ["电力", "电网", "特高压", "充电桩", "智能电网"],
    "金融科技": ["金融科技", "数字货币", "区块链", "支付", "FinTech"],
    "国企改革": ["国企", "央企", "国资", "混改", "中字头"],
    "消费复苏": ["消费", "白酒", "食品", "零售", "旅游", "免税", "餐饮"],
    "新材料": ["新材料", "碳纤维", "稀土", "永磁", "超导", "石墨烯"],
    "AI应用": ["AI应用", "AIGC", "ChatGPT", "Sora", "多模态", "GPT"],
}

# 股票名称中的常见行业关键词映射
NAME_KEYWORDS: dict[str, str] = {
    "科技": "数字经济",
    "智能": "人工智能",
    "电子": "消费电子",
    "微电": "芯片半导体",
    "光电": "芯片半导体",
    "生物": "医药医疗",
    "药": "医药医疗",
    "医": "医药医疗",
    "汽车": "汽车",
    "车": "汽车",
    "能源": "新能源",
    "光伏": "新能源",
    "电力": "电力电网",
    "电气": "电力电网",
    "机器": "机器人",
    "军工": "军工",
    "航": "军工",
    "数据": "数字经济",
    "软件": "数字经济",
    "信息": "数字经济",
    "通信": "数字经济",
}


def _match_keywords(text: str, keywords: list[str]) -> bool:
    """检查文本是否包含任意关键词"""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def score_thematic(
    code: str,
    name: str,
    sector: str,
    industry: str,
) -> tuple[list[str], int]:
    """基于股票基本信息匹配题材

    Args:
        code: 股票代码
        name: 股票名称
        sector: 板块/概念
        industry: 行业

    Returns:
        (matched_themes_list, hit_count)
    """
    matched_themes: list[str] = []
    
    # 组合待匹配文本
    search_text = f"{name} {sector} {industry}"
    
    for theme, keywords in BUILTIN_THEMES.items():
        if _match_keywords(search_text, keywords):
            if theme not in matched_themes:
                matched_themes.append(theme)

    return matched_themes, len(matched_themes)


def score_sector_relevance(sector: str) -> float:
    """计算板块相关度分数（基于sector中关键词密度）"""
    if not sector or sector == "未分类":
        return 0
    hits = 0
    for keywords in BUILTIN_THEMES.values():
        if _match_keywords(sector, keywords):
            hits += 1
    return min(hits * 20, 100)


def build_stock_thematic_map(
    stock_pool: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """对股票池中所有股票计算题材匹配结果并缓存"""
    result: dict[str, dict[str, Any]] = {}
    for _, row in stock_pool.iterrows():
        code = str(row.get("code", "")).strip()
        name = str(row.get("name", "")).strip()
        sector = str(row.get("sector", "")).strip()
        industry = str(row.get("industry", "")).strip()

        themes, count = score_thematic(code, name, sector, industry)
        result[code] = {
            "matched_themes": themes,
            "theme_count": count,
            "sector_relevance": score_sector_relevance(sector),
        }
    return result


def load_or_build_thematic_map(
    stock_pool: pd.DataFrame | None = None,
    force_refresh: bool = False,
) -> dict[str, dict[str, Any]]:
    """加载或生成题材匹配缓存"""
    ensure_data_dirs()
    if not force_refresh and CONCEPT_CACHE_PATH.exists():
        try:
            cached = json.loads(CONCEPT_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and len(cached) > 100:
                return cached
        except Exception:
            pass

    if stock_pool is None or stock_pool.empty:
        return {}

    result = build_stock_thematic_map(stock_pool)
    CONCEPT_CACHE_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result
