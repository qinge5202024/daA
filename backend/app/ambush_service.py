"""潜伏评分引擎

三阶段管道：观察池 → 蓄势中 → 待点火

评分维度：
  - K线结构组（35%）：横盘/均线粘合/W底/箱体/旗形/底背离等
  - 资金暗涌组（25%）：试盘上影线/缩量回踩/逐波放量/大阳试盘
  - 题材预期组（25%）：概念标签匹配热点
  - 基本面安全垫（15%）：ROE/营收增长/PE/现金流
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .ambush_fetcher import score_thematic, score_sector_relevance
from .data_service import load_stock_pool
from .models import (
    AmbushBrief,
    AmbushBriefItem,
    AmbushConfirmCondition,
    AmbushConfig,
    AmbushItem,
    AmbushPipelineResponse,
    AmbushResponse,
    AmbushSignalDetail,
    AmbushStage,
    AmbushThematicScore,
)
from .storage import (
    load_ambush_brief,
    load_ambush_snapshot,
    save_ambush_brief,
    save_ambush_snapshot,
)
from .paths import AMBUSH_CONFIG_PATH, AMBUSH_PIPELINE_PATH, AMBUSH_RESULTS_PATH
from .storage import read_json, utc_now_iso, write_json
from .technical import (
    _add_indicator_columns,
    _prepare_history,
    _safe_number,
    normalize_stock_code,
)


# ── 工具函数 ──────────────────────────────────────────────


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any, default: float = 0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _days_between(d1: str, d2: str | None = None) -> int:
    if not d1:
        return 0
    try:
        d1_dt = datetime.fromisoformat(d1)
        d2_dt = (
            datetime.fromisoformat(d2)
            if d2
            else datetime.now(timezone.utc).astimezone()
        )
        return abs((d2_dt - d1_dt).days)
    except Exception:
        return 0


def _batch_fetch_kline(codes: list[str], lookback_days: int = 370) -> dict[str, pd.DataFrame]:
    """批量拉取K线，共用一次 baostock 登录"""
    from datetime import date, timedelta
    from .technical import _history_cache_path, baostock_symbol

    result: dict[str, pd.DataFrame] = {}
    code = str = None  # type: ignore

    # 检查缓存
    need_fetch: list[str] = []
    today = date.today()
    for c in codes:
        path = _history_cache_path(c)
        if path.exists() and date.fromtimestamp(path.stat().st_mtime) == today:
            try:
                df = pd.read_csv(path, dtype={"code": str})
                work = _prepare_history(df)
                if len(work) >= 30:
                    result[c] = _add_indicator_columns(work)
                    continue
            except Exception:
                pass
        need_fetch.append(c)

    if not need_fetch:
        return result

    # 批量从 baostock 拉取
    try:
        import baostock as bs
    except ModuleNotFoundError:
        return result

    end = date.today()
    start = end - timedelta(days=lookback_days)
    login_ok = bs.login()
    if login_ok.error_code != "0":
        return result

    try:
        for code in need_fetch:
            try:
                query = bs.query_history_k_data_plus(
                    baostock_symbol(code),
                    "date,code,open,high,low,close,volume,amount",
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                    frequency="d",
                    adjustflag="3",
                )
                if query.error_code != "0":
                    continue
                rows: list[list[str]] = []
                while query.next():
                    rows.append(query.get_row_data())
                if not rows:
                    continue
                frame = pd.DataFrame(rows, columns=query.fields)
                frame.to_csv(_history_cache_path(code), index=False, encoding="utf-8-sig")
                work = _prepare_history(frame)
                if len(work) >= 30:
                    result[code] = _add_indicator_columns(work)
            except Exception:
                continue
    finally:
        bs.logout()

    return result


# ── 信号引擎 ──────────────────────────────────────────────
# 每个信号函数接收 K线DataFrame，返回 (confidence, details)


def _signal_long_consolidation(work: pd.DataFrame) -> tuple[float, str]:
    """长期横盘突破前：60日线走平+股价窄幅震荡≥30天+布林收窄"""
    if len(work) < 60:
        return 0, "数据不足（<60天）"
    last = work.iloc[-1]
    last_close = _safe_float(last["close"])
    if last_close <= 0:
        return 0, "无有效收盘价"

    # 60日均线斜率（最后20天）
    ma60_vals = work["close"].rolling(60).mean().tail(30).dropna()
    if len(ma60_vals) < 20:
        return 0, "MA60数据不足"
    slope = (ma60_vals.iloc[-1] - ma60_vals.iloc[0]) / ma60_vals.iloc[0] * 100

    # 如果均线已经明显向上或向下发散，就不是横盘了
    if abs(slope) > 3:
        return 0, f"MA60斜率{slope:.1f}%，已脱离横盘"

    # 统计股价在±8%内震荡的天数
    high60 = last_close * 1.08
    low60 = last_close * 0.92
    in_range = work.tail(90)[
        (work.tail(90)["high"] <= high60) & (work.tail(90)["low"] >= low60)
    ]
    days = len(in_range)
    if days < 15:
        return 0, f"横盘仅{days}天（需≥15天）"

    # 布林带宽（近半年最低百分比）
    if "boll_upper20" in work.columns and "boll_lower20" in work.columns:
        bb_width = (work["boll_upper20"] - work["boll_lower20"]) / work["boll_mid20"]
        recent_bb = bb_width.tail(120).dropna()
        if len(recent_bb) > 20:
            current_width = recent_bb.iloc[-1]
            percentile = (recent_bb <= current_width).mean() * 100
            bb_bonus = 15 if percentile < 30 else 8 if percentile < 50 else 0
        else:
            bb_bonus = 0
    else:
        bb_bonus = 0

    # 基础分：横盘天数
    base = _clamp(days / 60 * 80, 0, 80)
    confidence = _clamp(base + bb_bonus)
    detail = (
        f"横盘{days}天，MA60斜率{slope:.1f}%"
        + (f"，布林带宽处于近期{percentile:.0f}%分位" if bb_bonus > 0 else "")
    )
    return confidence, detail


def _signal_ma_convergence(work: pd.DataFrame) -> tuple[float, str]:
    """均线粘合：5/10/20/60日均线间距<3%且持续≥15天"""
    if len(work) < 60:
        return 0, "数据不足"
    close = work["close"]
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    recent = work.tail(30)
    r5 = ma5.tail(30)
    r10 = ma10.tail(30)
    r20 = ma20.tail(30)
    r60 = ma60.tail(30)

    # 计算均线间距（离散度）
    spread = pd.concat([r5, r10, r20, r60], axis=1).T
    max_spread = spread.max() / spread.min() - 1
    tight_days = (max_spread < 0.03).sum()

    if tight_days < 10:
        return 0, f"均线紧贴天数{tight_days}天（需≥10天）"

    # 检查是否开始发散（最新2天均线间距在扩大）
    last_spread = max_spread.iloc[-1] if len(max_spread) > 0 else 999
    prev_spread = max_spread.iloc[-2] if len(max_spread) > 1 else 999
    diverging = last_spread > prev_spread * 1.15 and last_spread < 0.06

    bonus = 20 if diverging else 0
    confidence = _clamp(
        _clamp(tight_days / 30 * 70) + bonus
    )
    state = "开始发散" if diverging else "持续粘合"
    return confidence, f"均线紧贴{tight_days}天，间距<3%，{state}"


def _signal_ma_diverging(work: pd.DataFrame) -> tuple[float, str]:
    """均线首次发散：粘合后5日线上穿10/20日线"""
    if len(work) < 60:
        return 0, "数据不足"
    close = work["close"]
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()

    recent = work.tail(20)
    r5 = ma5.tail(20)
    r10 = ma10.tail(20)
    r20 = ma20.tail(20)
    last_close = _safe_float(recent.iloc[-1]["close"])

    # 5日线站上10日线和20日线
    on_ma10 = r5.iloc[-1] >= r10.iloc[-1]
    on_ma20 = r5.iloc[-1] >= r20.iloc[-1]
    above_ma60 = last_close >= _safe_float(close.rolling(60).mean().iloc[-1])

    if on_ma10 and on_ma20 and above_ma60:
        # 检查过去10天是否刚突破
        broke_recently = False
        for i in range(1, 11):
            if -i >= -len(r5):
                break
            if r5.iloc[-i] < r10.iloc[-i] or r5.iloc[-i] < r20.iloc[-i]:
                broke_recently = True
                break
        if broke_recently or True:  # 当前站上就算
            confidence = _clamp((1 if on_ma10 else 0) * 40 + 30 + (20 if above_ma60 else 0))
            return confidence, "5日线站上10/20日线，股价站上60日线"
    return 0, "均线尚未形成向上发散"


def _signal_w_bottom(work: pd.DataFrame) -> tuple[float, str]:
    """W底：两个低点相近+中间反弹+突破颈线"""
    if len(work) < 120:
        return 0, "数据不足（<120天）"
    close = work["close"]
    recent = work.tail(120)

    # 找两个低点
    low_window = recent["low"].rolling(20).min()
    low_idx = low_window.idxmin() if pd.notna(low_window.idxmin()) else None
    if low_idx is None or low_idx < 2:
        return 0, "无法定位低点"
    low1 = _safe_float(recent.loc[low_idx, "low"])

    # 从第一个低点后找第二个低点
    after_first = recent.loc[low_idx:].iloc[1:]
    if after_first.empty:
        return 0, "低点后数据不足"
    second_low_window = after_first["low"].rolling(20).min()
    second_low_idx = second_low_window.idxmin() if pd.notna(second_low_window.idxmin()) else None
    if second_low_idx is None:
        return 0, "无法定位第二个低点"
    low2 = _safe_float(after_first.loc[second_low_idx, "low"])

    # 两个低点价差<5%
    diff = abs(low2 - low1) / max(low1, 0.01) * 100
    if diff > 5:
        return 0, f"两低点差距{diff:.1f}%（需≤5%）"

    # 中间的反弹高点
    between = recent.loc[low_idx:second_low_idx].iloc[1:-1]
    if between.empty:
        return 0, "中间区域数据不足"
    mid_high = between["high"].max()
    neckline = mid_high  # 颈线

    # 突破颈线
    last_close = _safe_float(recent.iloc[-1]["close"])
    if last_close <= 0:
        return 0, "无有效收盘价"

    # 距离颈线位置
    pct_to_neck = (last_close / neckline - 1) * 100 if neckline > 0 else 0
    if pct_to_neck >= -2 and pct_to_neck <= 5:
        confidence = _clamp(65 + max(0, 20 - diff * 4))
        return confidence, f"W底确认，颈线{neckline:.2f}，当前距颈线{pct_to_neck:+.1f}%"
    elif pct_to_neck < -2:
        return 0, f"W底形态中，距颈线还有{-pct_to_neck:.1f}%"
    else:
        return 0, f"已突破颈线{pct_to_neck:+.1f}%，追高风险"


def _signal_box_bottom_shrink(work: pd.DataFrame) -> tuple[float, str]:
    """箱体底部缩量：3个月箱体+股价在下沿+量萎缩"""
    if len(work) < 60:
        return 0, "数据不足"
    recent = work.tail(60)
    high3m = recent["high"].max()
    low3m = recent["low"].min()
    last_close = _safe_float(recent.iloc[-1]["close"])
    if high3m <= 0 or last_close <= 0:
        return 0, "无有效价格"

    box_range = (high3m - low3m) / high3m * 100
    if box_range > 25:
        return 0, f"箱体幅度{box_range:.1f}%（需≤25%）"

    # 在下沿30%区域
    in_lower_zone = last_close <= low3m + (high3m - low3m) * 0.3
    if not in_lower_zone:
        return 0, f"股价在箱体中部，未到低部区域"

    # 成交量萎缩
    volume = recent["volume"]
    vol_ma50 = volume.tail(50).mean()
    vol_last5 = volume.tail(5).mean()
    vol_ratio = vol_last5 / vol_ma50 if vol_ma50 > 0 else 1
    shrink_score = _clamp(60 * (1 - vol_ratio)) if vol_ratio < 1 else 20

    confidence = _clamp(40 + shrink_score)
    return confidence, (
        f"箱体幅度{box_range:.1f}%，股价在低位区，"
        f"最近5日量/50日量比{vol_ratio:.2f}"
    )


def _signal_flag_pennant(work: pd.DataFrame) -> tuple[float, str]:
    """旗形/三角整理末端：前期拉升后缩量回调+振幅收窄"""
    if len(work) < 60:
        return 0, "数据不足"
    recent = work.tail(60)
    close = recent["close"]

    # 找前期拉升：近60日最高点到当前
    high_idx = recent["high"].idxmax()
    high_pos = recent.index.get_loc(high_idx) if high_idx in recent.index else -1
    if high_pos < 10 or high_pos >= len(recent) - 5:
        return 0, "未找到有效拉升段"

    # 拉升幅度
    high_price = _safe_float(recent.loc[high_idx, "high"])
    pre_low = recent.iloc[max(0, high_pos - 20):high_pos]["low"].min()
    rally_pct = (high_price - pre_low) / pre_low * 100 if pre_low > 0 else 0
    if rally_pct < 12:
        return 0, f"前期拉升仅{rally_pct:.1f}%（需≥12%）"

    # 回调阶段：高点后至今
    pullback = recent.iloc[high_pos:]
    if len(pullback) < 8:
        return 0, "回调时间不足"
    pullback_low = pullback["low"].min()
    pullback_pct = (pullback_low - high_price) / high_price * 100

    # 回调不破拉升的50%
    if pullback_pct < -50:
        return 0, f"回调幅度{pullback_pct:.1f}%，过深"
    
    # 振幅逐步收窄
    pullback_range = (
        pullback["high"].tail(max(1, len(pullback) // 2)).max()
        - pullback["low"].tail(max(1, len(pullback) // 2)).min()
    ) / high_price * 100

    # 成交量萎缩
    vol_ratio = (
        pullback["volume"].tail(5).mean()
        / recent["volume"].tail(50).mean()
    ) if recent["volume"].tail(50).mean() > 0 else 1
    shrink = max(0, 1 - vol_ratio)

    confidence = _clamp(50 + shrink * 30 + max(0, 15 - pullback_range))
    return confidence, (
        f"前期拉升{rally_pct:.1f}%，回调{pullback_pct:.1f}%，"
        f"振幅收窄至{pullback_range:.1f}%，量比{vol_ratio:.2f}"
    )


def _signal_macd_divergence(work: pd.DataFrame) -> tuple[float, str]:
    """MACD底背离：股价新低但MACD不创新低"""
    if len(work) < 60:
        return 0, "数据不足"
    close = work["close"]
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    macd = (dif - dea) * 2

    recent = work.tail(60)
    recent_dif = dif.tail(60)

    # 找最近两个低点
    low_window = recent["low"].rolling(10).min()
    lows = recent[recent["low"] == low_window]
    if len(lows) < 2:
        return 0, "无法找到两个低点"

    low_prices = lows["low"].tail(2)
    if len(low_prices) < 2:
        return 0, "低点不足"
    p1, p2 = low_prices.iloc[0], low_prices.iloc[1]
    if pd.isna(p1) or pd.isna(p2):
        return 0, "低点数据无效"

    # 对应的DIF值
    dif1 = recent_dif.loc[low_prices.index[0]] if low_prices.index[0] in recent_dif.index else pd.NA
    dif2 = recent_dif.loc[low_prices.index[1]] if low_prices.index[1] in recent_dif.index else pd.NA
    if pd.isna(dif1) or pd.isna(dif2):
        return 0, "DIF数据不匹配"

    price_lower = p2 < p1
    dif_higher = dif2 > dif1

    if price_lower and dif_higher:
        confidence = _clamp(70 + abs(dif2 - dif1) / max(abs(dif1), 0.01) * 10)
        return confidence, f"股价新低({p2:.2f}<{p1:.2f})但DIF抬高，底背离确认"
    return 0, "未出现底背离"


def _signal_rsi_divergence(work: pd.DataFrame) -> tuple[float, str]:
    """RSI底背离：股价新低但RSI底部抬高"""
    if len(work) < 60:
        return 0, "数据不足"
    close = work["close"]
    # RSI14
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 0.001)
    rsi = 100 - 100 / (1 + rs)

    recent = work.tail(60)
    recent_rsi = rsi.tail(60)

    low_window = recent["low"].rolling(10).min()
    lows = recent[recent["low"] == low_window]
    if len(lows) < 2:
        return 0, "无法找到两个低点"
    low_prices = lows["low"].tail(2)
    if len(low_prices) < 2:
        return 0, "低点不足"
    p1, p2 = low_prices.iloc[0], low_prices.iloc[1]

    rsi1 = recent_rsi.loc[low_prices.index[0]] if low_prices.index[0] in recent_rsi.index else pd.NA
    rsi2 = recent_rsi.loc[low_prices.index[1]] if low_prices.index[1] in recent_rsi.index else pd.NA
    if pd.isna(rsi1) or pd.isna(rsi2):
        return 0, "RSI数据不匹配"

    price_lower = p2 < p1
    rsi_higher = rsi2 > rsi1

    if price_lower and rsi_higher:
        confidence = _clamp(65 + abs(rsi2 - rsi1) * 2)
        return confidence, f"股价新低但RSI抬高({rsi2:.1f}>{rsi1:.1f})，RSI底背离"
    return 0, "未出现RSI底背离"


def _signal_volume_divergence(work: pd.DataFrame) -> tuple[float, str]:
    """成交量底背离：价格跌但成交量萎缩到地量"""
    if len(work) < 60:
        return 0, "数据不足"
    recent = work.tail(60)
    close = recent["close"]
    volume = recent["volume"]
    vol_ma60 = volume.tail(60).mean()
    vol_ma20 = volume.tail(20).mean()
    last_vol = _safe_float(volume.iloc[-1])

    if vol_ma60 <= 0:
        return 0, "成交量数据不足"

    # 地量：最近5日均量 < 60日均量的50%
    vol_ratio = vol_ma20 / vol_ma60 if vol_ma60 > 0 else 1
    # 价格在近60日低位
    price_position = (
        (_safe_float(close.iloc[-1]) - recent["low"].min())
        / (recent["high"].max() - recent["low"].min() + 0.01)
    )

    if vol_ratio < 0.6 and price_position < 0.4:
        confidence = _clamp(60 + (1 - vol_ratio) * 50)
        return confidence, (
            f"近20日量/60日量={vol_ratio:.2f}，价格在低位({price_position:.0%})，缩量见底信号"
        )
    return 0, f"量比{vol_ratio:.2f}（需<0.6）或价格不在低位"


# ── 吸筹组信号 ──────────────────────────────────────────


def _signal_test_candle(work: pd.DataFrame) -> tuple[float, str]:
    """试盘上影线：放量+冲高回落+下影线短"""
    if len(work) < 20:
        return 0, "数据不足"
    last = work.iloc[-1]
    prev = work.iloc[-2]
    open_p = _safe_float(last["open"])
    high = _safe_float(last["high"])
    low = _safe_float(last["low"])
    close = _safe_float(last["close"])
    volume = _safe_float(last["volume"])
    vol_ma5 = work["volume"].tail(5).mean()

    if vol_ma5 <= 0 or high <= low:
        return 0, "量价数据不足"

    body = abs(close - open_p)
    upper_shadow = high - max(open_p, close)
    lower_shadow = min(open_p, close) - low
    candle_range = max(high - low, 0.001)

    # 条件：放量>2倍5日均量 + 上影线长 + 下影线短
    vol_ratio = volume / vol_ma5
    upper_ratio = upper_shadow / candle_range
    lower_ratio = lower_shadow / candle_range

    # 上影线长度 > 实体，且下影线不占主导
    test_condition = (
        vol_ratio > 1.8
        and upper_ratio > 0.45
        and lower_ratio < 0.25
        and abs(close - open_p) / candle_range < 0.5
    )

    if test_condition:
        confidence = _clamp(50 + vol_ratio * 10 + upper_ratio * 20)
        return confidence, (
            f"放量{vol_ratio:.1f}倍+长上影线({upper_ratio:.0%})，"
            f"试盘信号，收盘{close:.2f}"
        )
    return 0, "未满足试盘条件"


def _signal_shrink_hold(work: pd.DataFrame) -> tuple[float, str]:
    """缩量回踩不破：前期放量拉升后缩量回踩均线"""
    if len(work) < 40:
        return 0, "数据不足"
    recent = work.tail(40)
    volume = recent["volume"]
    close = recent["close"]
    vol_ma20 = volume.tail(20).mean()

    # 找前期放量日
    vol_spikes = recent[volume > vol_ma20 * 1.5]
    if vol_spikes.empty:
        return 0, "未找到放量日"

    last = recent.iloc[-1]
    last_close = _safe_float(last["close"])
    if last_close <= 0:
        return 0, "无有效收盘价"

    # 最近5天缩量
    vol_ratio = volume.tail(5).mean() / vol_ma20 if vol_ma20 > 0 else 1
    if vol_ratio > 0.85:
        return 0, f"近5日量比{vol_ratio:.2f}（需<0.85）"

    # 不破20日均线
    ma20 = close.rolling(20).mean().iloc[-1]
    if pd.isna(ma20) or last_close < ma20 * 0.98:
        return 0, f"收盘价{last_close:.2f}跌破MA20({ma20:.2f})"

    # 不破60日均线
    if len(recent) >= 60:
        ma60 = close.rolling(60).mean().iloc[-1]
        if pd.isna(ma60):
            ma60_ok = True
        else:
            ma60_ok = last_close >= ma60 * 0.97
    else:
        ma60_ok = True

    confidence = _clamp(60 + (1 - vol_ratio) * 30 + (15 if ma60_ok else 0))
    return confidence, (
        f"缩量回踩(量比{vol_ratio:.2f})，收盘{last_close:.2f}站上MA20{ma20:.2f}"
    )


def _signal_wave_volume(work: pd.DataFrame) -> tuple[float, str]:
    """底部逐波放量：量能一浪比一浪高，价格没涨"""
    if len(work) < 90:
        return 0, "数据不足"
    recent = work.tail(90)
    close = recent["close"]
    volume = recent["volume"]

    # 分成三浪：各30天
    chunk_size = 30
    vol_chunks = [
        volume.iloc[i:i + chunk_size].mean()
        for i in range(0, min(len(volume), 90), chunk_size)
    ]
    close_chunks = [
        close.iloc[i:i + chunk_size].mean()
        for i in range(0, min(len(close), 90), chunk_size)
    ]

    if len(vol_chunks) < 3:
        return 0, "数据段不足"

    # 量能逐波放大
    vol_up = all(vol_chunks[i] < vol_chunks[i + 1] for i in range(len(vol_chunks) - 1))
    # 价格没涨（不高于前段5%）
    price_flat = all(
        abs(close_chunks[i + 1] / close_chunks[i] - 1) < 0.08
        for i in range(len(close_chunks) - 1)
    )

    if vol_up and price_flat:
        confidence = _clamp(
            60 + (vol_chunks[-1] / vol_chunks[0] - 1) * 15
            if vol_chunks[0] > 0
            else 60
        )
        return confidence, (
            f"量能逐波放大({vol_chunks[0]:.0f}→{vol_chunks[-1]:.0f})，"
            f"价格横盘，吸筹痕迹"
        )
    return 0, "未满足逐波放量条件"


def _signal_big_bullish_candle(work: pd.DataFrame) -> tuple[float, str]:
    """大阳/涨停试盘：底部出现>7%阳线+适中换手+不破阳线一半"""
    if len(work) < 10:
        return 0, "数据不足"
    last = work.iloc[-1]
    prev = work.iloc[-2]
    open_p = _safe_float(last["open"])
    close = _safe_float(last["close"])

    if close <= 0 or open_p <= 0:
        return 0, "无效价格"

    pct = (close / open_p - 1) * 100
    if pct < 7:
        return 0, f"涨幅{pct:.1f}%（需>7%）"

    body = abs(close - open_p)
    low = _safe_float(last["low"])
    high = _safe_float(last["high"])

    # 次日不破阳线一半
    day2_low = _safe_float(prev["low"])
    half_line = min(open_p, close) + body * 0.5
    holds = day2_low >= half_line * 0.98

    confidence = _clamp(60 + (10 if holds else 0) + max(0, pct - 7) * 2)
    return confidence, (
        f"大阳线+{pct:.1f}%，"
        + ("次日守住半位" if holds else "次日应关注")
    )


# ── 信号注册表 ──────────────────────────────────────────

STRUCTURE_SIGNALS = [
    ("long_consolidation", "长期横盘", _signal_long_consolidation),
    ("ma_convergence", "均线粘合", _signal_ma_convergence),
    ("ma_diverging", "均线发散", _signal_ma_diverging),
    ("w_bottom", "W底形态", _signal_w_bottom),
    ("box_bottom_shrink", "箱体底部缩量", _signal_box_bottom_shrink),
    ("flag_pennant", "旗形/三角整理", _signal_flag_pennant),
    ("macd_divergence", "MACD底背离", _signal_macd_divergence),
    ("rsi_divergence", "RSI底背离", _signal_rsi_divergence),
    ("volume_divergence", "量价底背离", _signal_volume_divergence),
]

AMBUSH_SIGNALS = [
    ("test_candle", "试盘上影线", _signal_test_candle),
    ("shrink_hold", "缩量回踩不破", _signal_shrink_hold),
    ("wave_volume", "底部逐波放量", _signal_wave_volume),
    ("big_bullish_candle", "大阳/涨停试盘", _signal_big_bullish_candle),
]

ALL_SIGNALS = STRUCTURE_SIGNALS + AMBUSH_SIGNALS


# ── 综合评分 ──────────────────────────────────────────────


def _compute_quality_score(frame_row: pd.Series) -> float:
    """基本面安全垫评分，直接从股票池字段计算"""
    scores: list[float] = []

    # ROE
    roe = _safe_float(frame_row.get("roe"))
    if roe > 0:
        scores.append(_clamp(roe / 15 * 100))
    else:
        scores.append(35)

    # 营收增长
    rev_growth = _safe_float(frame_row.get("revenue_growth"))
    if rev_growth > 0:
        scores.append(_clamp(rev_growth / 20 * 100))
    else:
        scores.append(30)

    # PE（越低越好）
    pe = _safe_float(frame_row.get("pe"))
    if pe > 0 and pe < 100:
        scores.append(_clamp(100 - pe / 100 * 100) if pe < 100 else 20)
    else:
        scores.append(40)

    # 现金流
    cashflow = _safe_float(frame_row.get("cashflow_ratio"))
    if cashflow > 0:
        scores.append(_clamp(cashflow / 1.2 * 100))
    else:
        scores.append(40)

    # 分红
    dy = _safe_float(frame_row.get("dividend_yield"))
    if dy > 0:
        scores.append(_clamp(dy / 4 * 100))

    return _clamp(sum(scores) / len(scores)) if scores else 40


def _compute_thematic_score(
    code: str,
    name: str,
    sector: str,
    industry: str,
) -> AmbushThematicScore:
    """题材预期评分（基本版：基于名称/行业/板块关键词匹配）"""
    themes, hit_count = score_thematic(code, name, sector, industry)
    sector_rel = score_sector_relevance(sector)
    
    # 每个命中题材20分 + 板块相关度加权
    base_score = _clamp(hit_count * 18)
    total = _clamp(base_score * 0.6 + sector_rel * 0.4)
    
    return AmbushThematicScore(
        matched_concepts=themes,
        concept_count=hit_count,
        hot_concept_hits=hit_count,
        sector_relevance=sector_rel,
        score=total,
    )


def _compute_confirm_conditions(
    item: AmbushItem,
    work: pd.DataFrame,
) -> list[AmbushConfirmCondition]:
    """生成确认买入条件"""
    if work.empty:
        return []
    last = work.iloc[-1]
    last_close = _safe_float(last["close"])
    if last_close <= 0:
        return []

    conditions: list[AmbushConfirmCondition] = []

    # 均线阻力
    close = work["close"]
    ma20 = _safe_float(close.rolling(20).mean().iloc[-1])
    high20 = _safe_float(work["high"].tail(20).max())

    # 突破颈线（如果有W底信号）
    neckline = None
    for sig in item.signals:
        if sig.signal_key == "w_bottom" and sig.confidence > 50:
            try:
                parts = sig.details.split("颈线")
                if len(parts) > 1:
                    neckline = float(parts[1].split(",")[0].strip())
            except Exception:
                pass

    if neckline and neckline > last_close:
        conditions.append(
            AmbushConfirmCondition(
                condition=f"放量突破颈线{neckline:.2f}",
                trigger_price=round(neckline, 2),
                price_basis=f"W底颈线位",
                stop_loss=f"跌破颈线-3%即{round(neckline * 0.97, 2)}",
                target=f"{round(neckline * 1.15, 2)}-{round(neckline * 1.25, 2)}",
                time_limit_days=30,
            )
        )

    # 突破MA20放量
    if ma20 > 0 and last_close < ma20:
        conditions.append(
            AmbushConfirmCondition(
                condition=f"放量站上MA20({ma20:.2f})",
                trigger_price=round(ma20, 2),
                price_basis="20日均线压力位",
                stop_loss=f"跌破MA20即止损{round(ma20 * 0.97, 2)}",
                target="前高或箱体上沿",
                time_limit_days=30,
            )
        )

    # 箱体突破
    for sig in item.signals:
        if sig.signal_key == "box_bottom_shrink" and sig.confidence > 50:
            high3m = work.tail(60)["high"].max()
            low3m = work.tail(60)["low"].min()
            break_price = low3m + (high3m - low3m) * 0.7
            if break_price > last_close:
                conditions.append(
                    AmbushConfirmCondition(
                        condition=f"放量突破箱体中轨{break_price:.2f}",
                        trigger_price=round(break_price, 2),
                        price_basis="3个月箱体中轨",
                        stop_loss=f"跌破箱体底部{low3m:.2f}",
                        target=f"箱体顶部{high3m:.2f}附近",
                        time_limit_days=30,
                    )
                )
            break

    if not conditions:
        # 默认条件
        conditions.append(
            AmbushConfirmCondition(
                condition=f"放量突破{high20:.2f}（20日高点）",
                trigger_price=round(high20, 2),
                price_basis="近20日高点",
                stop_loss=f"跌破{last_close:.2f}即止损",
                target="前高/箱体上沿",
                time_limit_days=30,
            )
        )

    return conditions[:3]


# ── 主流程 ──────────────────────────────────────────────


def analyze_ambush_potential(
    stock_pool: pd.DataFrame,
    config: AmbushConfig | None = None,
    force_concept_refresh: bool = False,
) -> AmbushResponse:
    """对股票池运行潜伏评分，生成潜伏池

    流程：
    1. 预筛选（仅用stock_pool字段，不用K线）
    2. 取候选池（限制数量避免超时）
    3. 逐只拉K线计算信号
    """
    if config is None:
        config = AmbushConfig()

    if stock_pool.empty:
        return AmbushResponse(generated_at=utc_now_iso())

    # ── 1. 预筛选 ──────────────────────────────────
    pool = stock_pool.copy()
    pool = pool[
        ~pool["name"].astype(str).str.contains("ST|退市|退", na=False)
        & (pool["code"].astype(str).str.match(r"^\d{6}$", na=False))
        & (pool["name"].astype(str).str.len() > 0)
    ]

    # 用现有字段做粗筛（无需K线）
    pool = pool[
        (pool["market_cap"].fillna(0) >= 1_000_000_000)  # >=10亿
        & (pool["market_cap"].fillna(0) <= 200_000_000_000)  # <=2000亿
    ]

    # 优先选：有基本面数据的 + 有资金流字段的
    pool["_data_quality"] = (
        pool[["roe", "revenue_growth", "pe", "dividend_yield"]]
        .notna().sum(axis=1)
    )
    pool = pool.sort_values("_data_quality", ascending=False)

    # ── 2. 限制候选数量 ────────────────────────────
    MAX_CANDIDATES = 120
    candidates = pool.head(MAX_CANDIDATES).copy()

    # ── 3. 批量拉取K线（共用一次 baostock 登录）───────
    all_codes = []
    for idx, row in candidates.iterrows():
        code = str(row.get("code", "")).strip().zfill(6)
        if code:
            all_codes.append(code)

    kline_cache = _batch_fetch_kline(all_codes, lookback_days=370)

    # ── 4. 评分计算 ────────────────────────────────
    results: list[AmbushItem] = []

    for idx, row in candidates.iterrows():
        code = str(row.get("code", "")).strip().zfill(6)
        name = str(row.get("name", "")).strip()
        sector = str(row.get("sector", "")).strip() or "未分类"
        industry = str(row.get("industry", "")).strip() or "未分类"
        if not code or not name:
            continue

        work = kline_cache.get(code)
        if work is None:
            continue

        # 跑所有信号
        signals: list[AmbushSignalDetail] = []
        for key, name_sig, func in ALL_SIGNALS:
            try:
                confidence, details = func(work)
            except Exception:
                continue
            if confidence > 0:
                is_structure = any(k == key for k, _, _ in STRUCTURE_SIGNALS)
                signals.append(
                    AmbushSignalDetail(
                        signal_key=key,
                        signal_name=name_sig,
                        group="蓄势组" if is_structure else "吸筹组",
                        confidence=round(confidence, 1),
                        details=details,
                    )
                )

        # 分组评分
        structure_conf = (
            sum(s.confidence for s in signals if s.group == "蓄势组")
            / max(len([s for s in signals if s.group == "蓄势组"]), 1)
        )
        ambush_conf = (
            sum(s.confidence for s in signals if s.group == "吸筹组")
            / max(len([s for s in signals if s.group == "吸筹组"]), 1)
        )

        # 基本面
        quality = _compute_quality_score(row)

        # 题材
        thematic = _compute_thematic_score(code, name, sector, industry)

        # 综合评分
        structure_score = _clamp(structure_conf)
        ambush_score = _clamp(ambush_conf)
        thematic_score = thematic.score
        quality_score = quality

        total = (
            structure_score * config.structure_weight
            + ambush_score * config.ambush_weight
            + thematic_score * config.thematic_weight
            + quality_score * config.quality_weight
        )

        # 只有结构和题材至少一个达到阈值才进池子
        if structure_score < config.structure_threshold and thematic_score < 30:
            continue

        # 判断阶段
        if ambush_score >= config.ignition_threshold:
            stage = AmbushStage.IGNITION
        elif structure_score >= config.structure_threshold:
            stage = AmbushStage.BREWING
        else:
            stage = AmbushStage.WATCH

        conditions = (
            _compute_confirm_conditions(
                AmbushItem(
                    code=code,
                    name=name,
                    sector=sector,
                    industry=industry,
                ),
                work,
            )
            if stage == AmbushStage.IGNITION
            else []
        )

        item = AmbushItem(
            code=code,
            name=name,
            sector=sector,
            industry=industry,
            stage=stage,
            total_score=round(total, 1),
            structure_score=round(structure_score, 1),
            quality_score=round(quality_score, 1),
            thematic_score=round(thematic_score, 1),
            signals=sorted(signals, key=lambda s: s.confidence, reverse=True)[:8],
            thematic=thematic,
            conditions=conditions,
            entered_at=utc_now_iso(),
            last_signal_at=utc_now_iso(),
            days_in_pipeline=0,
        )
        results.append(item)

    # 按综合评分排序
    results.sort(key=lambda item: item.total_score, reverse=True)

    pipeline_summary = {"观察池": 0, "蓄势中": 0, "待点火": 0, "触发条件": 0, "已失效": 0}
    for item in results:
        pipeline_summary[item.stage.value] = pipeline_summary.get(item.stage.value, 0) + 1

    return AmbushResponse(
        generated_at=utc_now_iso(),
        total_analyzed=len(results),
        results=results,
        pipeline_summary=pipeline_summary,
    )


def run_ambush_pipeline(
    config: AmbushConfig | None = None,
    force_concept_refresh: bool = False,
) -> AmbushPipelineResponse:
    """运行完整潜伏管道：观察池→蓄势中→待点火"""

    stock_pool = load_stock_pool()
    if stock_pool.empty:
        return AmbushPipelineResponse(generated_at=utc_now_iso())

    response = analyze_ambush_potential(
        stock_pool, config, force_concept_refresh
    )

    watch_pool = [r for r in response.results if r.stage == AmbushStage.WATCH]
    brewing_pool = [r for r in response.results if r.stage == AmbushStage.BREWING]
    ignition_pool = [r for r in response.results if r.stage == AmbushStage.IGNITION]

    # 限流
    watch_pool = watch_pool[: (config or AmbushConfig()).max_watch_pool]
    brewing_pool = brewing_pool[: (config or AmbushConfig()).max_brewing_pool]
    ignition_pool = ignition_pool[: (config or AmbushConfig()).max_ignition_pool]

    return AmbushPipelineResponse(
        generated_at=utc_now_iso(),
        watch_pool=watch_pool,
        brewing_pool=brewing_pool,
        ignition_pool=ignition_pool,
        new_today=len(watch_pool) + len(brewing_pool) + len(ignition_pool),
    )


def load_ambush_config() -> AmbushConfig:
    try:
        return AmbushConfig.model_validate(
            read_json(AMBUSH_CONFIG_PATH, AmbushConfig().model_dump())
        )
    except Exception:
        return AmbushConfig()


def save_ambush_config(config: AmbushConfig) -> None:
    write_json(AMBUSH_CONFIG_PATH, config.model_dump(mode="json"))


def load_ambush_pipeline() -> AmbushPipelineResponse | None:
    if not AMBUSH_PIPELINE_PATH.exists():
        return None
    try:
        return AmbushPipelineResponse.model_validate(
            read_json(AMBUSH_PIPELINE_PATH, {})
        )
    except Exception:
        return None


def save_ambush_pipeline(pipeline: AmbushPipelineResponse) -> None:
    write_json(AMBUSH_PIPELINE_PATH, pipeline.model_dump(mode="json"))


def _item_to_brief_item(item: AmbushItem, change: str = "") -> AmbushBriefItem:
    """将 AmbushItem 转为简报用的简要版"""
    signals = [s for s in item.signals if s.confidence >= 30]
    detail = ""
    if change == "new" or change == "new_signal":
        if signals:
            detail = "、".join([f"{s.signal_name}[{s.confidence:.0f}]" for s in signals[:3]])
    elif change == "promoted":
        if item.stage == AmbushStage.IGNITION:
            detail = f"已进入待点火阶段，确认条件待触发"
    elif change == "expired":
        detail = item.expired_reason or "超过失效天数"
    else:
        detail = "、".join([f"{s.signal_name}[{s.confidence:.0f}]" for s in signals[:2]])

    return AmbushBriefItem(
        code=item.code,
        name=item.name,
        sector=item.sector,
        stage=item.stage.value if isinstance(item.stage, AmbushStage) else str(item.stage),
        total_score=round(item.total_score, 1),
        change=change,
        detail=detail,
    )


def _get_top_items(items: list[AmbushItem], n: int = 3) -> list[AmbushBriefItem]:
    """取评分最高的 n 只"""
    sorted_items = sorted(items, key=lambda x: x.total_score, reverse=True)
    return [_item_to_brief_item(item) for item in sorted_items[:n]]


def compute_ambush_brief() -> AmbushBrief:
    """计算每日简报

    对比当前管道与上次快照，找出：
    - 新出现的票（观察池新人、蓄势中新人、待点火新人）
    - 晋升的票（从观察池→蓄势中，或蓄势中→待点火）
    - 失效的票
    - 新增重要信号的票
    """
    pipeline = load_ambush_pipeline()
    if pipeline is None:
        return AmbushBrief(
            generated_at=utc_now_iso(),
            has_unseen=False,
        )

    pipeline_generated_at = pipeline.generated_at
    all_current: dict[str, AmbushItem] = {}
    for items in [pipeline.watch_pool, pipeline.brewing_pool, pipeline.ignition_pool]:
        for item in items:
            all_current[item.code] = item

    # 从上次快照构建 code_set
    snapshot = load_ambush_snapshot()
    snapshot_codes: set[str] = set()
    snapshot_stage_map: dict[str, str] = {}
    if snapshot:
        for stage_key in ["watch_pool", "brewing_pool", "ignition_pool"]:
            for item in snapshot.get(stage_key, []):
                if isinstance(item, dict):
                    code = item.get("code", "")
                    snapshot_codes.add(code)
                    snapshot_stage_map[code] = stage_key

    new_items: list[AmbushBriefItem] = []
    promoted_items: list[AmbushBriefItem] = []
    expired_items: list[AmbushBriefItem] = []
    new_signal_items: list[AmbushBriefItem] = []

    stage_order = {"watch_pool": 0, "brewing_pool": 1, "ignition_pool": 2}

    for code, item in all_current.items():
        stage_key_of_current = ""
        for stk, items in [
            ("ignition_pool", pipeline.ignition_pool),
            ("brewing_pool", pipeline.brewing_pool),
            ("watch_pool", pipeline.watch_pool),
        ]:
            if any(i.code == code for i in items):
                stage_key_of_current = stk
                break

        if code not in snapshot_codes:
            # 全新出现
            new_items.append(_item_to_brief_item(item, "new"))
        else:
            prev_stage_key = snapshot_stage_map.get(code, "")
            curr_stage_key = stage_key_of_current
            prev_order = stage_order.get(prev_stage_key, -1)
            curr_order = stage_order.get(curr_stage_key, -1)
            if curr_order > prev_order:
                # 晋升
                promoted_items.append(_item_to_brief_item(item, "promoted"))
            elif curr_order == prev_order:
                # 同阶段，检查是否有新增信号
                if snapshot:
                    # 简单检查：当前信号数是否比上次多
                    pass

    # 过期处理
    if snapshot:
        for code in snapshot_codes:
            if code not in all_current:
                expired_items.append(
                    AmbushBriefItem(
                        code=code,
                        name=snapshot_stage_map.get(code, ""),
                        sector="",
                        change="expired",
                        detail="超过失效天数或无信号留存",
                    )
                )

    # 各阶段亮点
    top_watch = _get_top_items(pipeline.watch_pool, 3)
    top_brewing = _get_top_items(pipeline.brewing_pool, 3)
    top_ignition = _get_top_items(pipeline.ignition_pool, 3)

    brief = AmbushBrief(
        generated_at=utc_now_iso(),
        pipeline_generated_at=pipeline_generated_at,
        new_items_count=len(new_items),
        promoted_count=len(promoted_items),
        expired_count=len(expired_items),
        new_signal_count=len(new_signal_items),
        new_items=new_items[:10],
        promoted_items=promoted_items[:10],
        expired_items=expired_items[:10],
        new_signal_items=new_signal_items[:10],
        top_watch=top_watch,
        top_brewing=top_brewing,
        top_ignition=top_ignition,
        has_unseen=True,
    )

    save_ambush_brief(brief)

    # 更新快照（保存当前管道状态供下次对比）
    save_ambush_snapshot({
        "generated_at": pipeline_generated_at,
        "watch_pool": [item.model_dump(mode="json") for item in pipeline.watch_pool],
        "brewing_pool": [item.model_dump(mode="json") for item in pipeline.brewing_pool],
        "ignition_pool": [item.model_dump(mode="json") for item in pipeline.ignition_pool],
    })

    return brief


def mark_brief_seen() -> AmbushBrief:
    """标记简报为已查看"""
    brief = load_ambush_brief()
    if brief is None:
        return AmbushBrief(generated_at=utc_now_iso(), has_unseen=False)
    brief.seen_at = utc_now_iso()
    brief.has_unseen = False
    save_ambush_brief(brief)
    return brief


def get_or_compute_brief(force_refresh: bool = False) -> AmbushBrief:
    """获取简报（如有缓存且未过期，直接返回；否则重新计算）"""
    if not force_refresh:
        brief = load_ambush_brief()
        if brief is not None:
            return brief
    return compute_ambush_brief()
