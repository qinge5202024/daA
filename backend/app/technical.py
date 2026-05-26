from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
from typing import Any

import pandas as pd

from .models import (
    CandlestickPattern,
    TechnicalAnalysisResponse,
    TechnicalLevel,
    TechnicalLevelsResponse,
    TechnicalSignal,
)
from .paths import HISTORY_DIR, ensure_data_dirs
from .storage import utc_now_iso


def normalize_stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6) if digits else text


def baostock_symbol(code: str) -> str:
    normalized = normalize_stock_code(code)
    if normalized.startswith(("6", "9")):
        return f"sh.{normalized}"
    if normalized.startswith(("0", "2", "3")):
        return f"sz.{normalized}"
    return f"bj.{normalized}"


def _history_cache_path(code: str) -> Any:
    return HISTORY_DIR / f"{normalize_stock_code(code)}.csv"


def _read_cached_history(code: str) -> pd.DataFrame:
    path = _history_cache_path(code)
    if not path.exists():
        return pd.DataFrame()
    modified_day = date.fromtimestamp(path.stat().st_mtime)
    if modified_day != date.today():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"code": str})


def fetch_price_history(code: str, lookback_days: int = 430) -> pd.DataFrame:
    ensure_data_dirs()
    cached = _read_cached_history(code)
    if len(cached) >= 30:
        return cached

    try:
        import baostock as bs  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("未安装 Baostock，无法计算技术参考价位。") from exc

    end = date.today()
    start = end - timedelta(days=lookback_days)
    login_result = bs.login()
    try:
        if login_result.error_code != "0":
            raise RuntimeError(f"Baostock 登录失败：{login_result.error_msg}")
        query = bs.query_history_k_data_plus(
            baostock_symbol(code),
            "date,code,open,high,low,close,volume,amount",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            frequency="d",
            adjustflag="3",
        )
        if query.error_code != "0":
            raise RuntimeError(f"Baostock 日线查询失败：{query.error_msg}")
        rows: list[list[str]] = []
        while query.next():
            rows.append(query.get_row_data())
        frame = pd.DataFrame(rows, columns=query.fields)
    finally:
        bs.logout()

    if frame.empty:
        raise ValueError(f"没有找到 {normalize_stock_code(code)} 的日线数据")
    frame.to_csv(_history_cache_path(code), index=False, encoding="utf-8-sig")
    return frame


def _prepare_history(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    for column in ("open", "high", "low", "close", "volume", "amount"):
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date", "high", "low", "close"])
    work = work[work["close"] > 0].sort_values("date").reset_index(drop=True)
    return work


def _position(price: float, last_close: float) -> str:
    distance = (price - last_close) / last_close * 100
    if abs(distance) <= 1:
        return "附近"
    return "下方" if distance < 0 else "上方"


def _add_level(
    levels: list[TechnicalLevel],
    key: str,
    label: str,
    price: Any,
    last_close: float,
    basis: str,
) -> None:
    try:
        number = float(price)
    except Exception:
        return
    if not isfinite(number) or number <= 0 or last_close <= 0:
        return
    levels.append(
        TechnicalLevel(
            key=key,
            label=label,
            price=round(number, 2),
            distance_pct=round((number - last_close) / last_close * 100, 2),
            basis=basis,
            position=_position(number, last_close),
        )
    )


def _true_range(work: pd.DataFrame) -> pd.Series:
    close = work["close"]
    high = work["high"]
    low = work["low"]
    previous_close = close.shift(1)
    return pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)


def _add_indicator_columns(work: pd.DataFrame) -> pd.DataFrame:
    close = work["close"]
    true_range = _true_range(work)
    work = work.copy()
    work["ma5"] = close.rolling(5).mean()
    work["ma10"] = close.rolling(10).mean()
    work["ma20"] = close.rolling(20).mean()
    work["ma60"] = close.rolling(60).mean()
    work["ma120"] = close.rolling(120).mean()
    work["high20"] = work["high"].rolling(20).max()
    work["high60"] = work["high"].rolling(60).max()
    work["high120"] = work["high"].rolling(120).max()
    work["low20"] = work["low"].rolling(20).min()
    work["low60"] = work["low"].rolling(60).min()
    work["low120"] = work["low"].rolling(120).min()
    work["boll_mid20"] = work["ma20"]
    work["boll_upper20"] = work["ma20"] + close.rolling(20).std() * 2
    work["boll_lower20"] = work["ma20"] - close.rolling(20).std() * 2
    work["atr14"] = true_range.rolling(14).mean()
    work["volume_ma20"] = work["volume"].rolling(20).mean()
    volume60 = work["volume"].rolling(60).sum()
    amount60 = work["amount"].rolling(60).sum()
    work["vwap60"] = amount60 / volume60
    work["return5"] = close.pct_change(5) * 100
    work["return20"] = close.pct_change(20) * 100
    work["ma20_slope5"] = work["ma20"].pct_change(5) * 100
    return work


def build_technical_levels(frame: pd.DataFrame, code: str, name: str = "") -> TechnicalLevelsResponse:
    work = _prepare_history(frame)
    if len(work) < 20:
        raise ValueError(f"{normalize_stock_code(code)} 的历史行情不足，无法计算技术参考价位")

    work = _add_indicator_columns(work)
    last = work.iloc[-1]
    last_close = float(last["close"])
    levels: list[TechnicalLevel] = []
    _add_level(levels, "ma20", "MA20", last.get("ma20"), last_close, "最近20个交易日收盘价均值")
    _add_level(levels, "ma60", "MA60", last.get("ma60"), last_close, "最近60个交易日收盘价均值")
    _add_level(levels, "ma120", "MA120", last.get("ma120"), last_close, "最近120个交易日收盘价均值")
    _add_level(levels, "low20", "20日低点", last.get("low20"), last_close, "最近20个交易日最低价")
    _add_level(levels, "low60", "60日低点", last.get("low60"), last_close, "最近60个交易日最低价")
    _add_level(levels, "low120", "120日低点", last.get("low120"), last_close, "最近120个交易日最低价")
    _add_level(levels, "boll_lower20", "布林下轨", last.get("boll_lower20"), last_close, "20日均线减2倍标准差")
    _add_level(
        levels,
        "atr14_lower",
        "ATR下沿",
        last_close - float(last.get("atr14") or 0) * 1.5,
        last_close,
        "最新收盘价减1.5倍ATR14",
    )
    _add_level(levels, "vwap60", "60日成交均价", last.get("vwap60"), last_close, "最近60个交易日成交额/成交量")

    return TechnicalLevelsResponse(
        code=normalize_stock_code(code),
        name=name,
        generated_at=utc_now_iso(),
        trade_date=last["date"].date().isoformat(),
        last_close=round(last_close, 2),
        levels=levels,
    )


def calculate_technical_levels(code: str, name: str = "") -> TechnicalLevelsResponse:
    return build_technical_levels(fetch_price_history(code), code, name)


def _safe_number(value: Any, default: float = 0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return number if isfinite(number) else default


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _direction_label(score: float) -> str:
    if score >= 65:
        return "短期偏上"
    if score <= 35:
        return "短期偏下"
    return "短期震荡"


def _probabilities(score: float, pattern_bias: float, volatility: float) -> tuple[float, float, float]:
    centered = (score - 50) / 50
    upside = 34 + centered * 24 + pattern_bias * 0.18
    downside = 34 - centered * 24 - pattern_bias * 0.18
    sideways = 32 + max(0, 9 - abs(centered) * 14) + min(8, max(0, volatility - 3) * 1.5)
    upside = max(8, upside)
    downside = max(8, downside)
    sideways = max(8, sideways)
    total = upside + downside + sideways
    return (round(upside / total * 100, 1), round(downside / total * 100, 1), round(sideways / total * 100, 1))


def _latest_candle_patterns(work: pd.DataFrame) -> tuple[list[CandlestickPattern], float]:
    patterns: list[CandlestickPattern] = []
    if len(work) < 2:
        return patterns, 0

    last = work.iloc[-1]
    prev = work.iloc[-2]
    open_price = _safe_number(last["open"])
    high = _safe_number(last["high"])
    low = _safe_number(last["low"])
    close = _safe_number(last["close"])
    prev_open = _safe_number(prev["open"])
    prev_close = _safe_number(prev["close"])
    candle_range = max(high - low, 0.0001)
    body = abs(close - open_price)
    upper_shadow = high - max(open_price, close)
    lower_shadow = min(open_price, close) - low
    body_ratio = body / candle_range
    bias = 0.0

    if body_ratio <= 0.12:
        patterns.append(
            CandlestickPattern(
                key="doji",
                label="十字星",
                direction="neutral",
                confidence=58,
                description="实体很小，多空短线分歧较强，后续需要结合量能和突破方向。",
            )
        )

    if lower_shadow >= body * 2 and upper_shadow <= body * 1.1 and close >= low + candle_range * 0.55:
        patterns.append(
            CandlestickPattern(
                key="hammer",
                label="锤头线",
                direction="bullish",
                confidence=64,
                description="下影线较长，盘中承接较明显，若出现在回调后更具参考意义。",
            )
        )
        bias += 8

    if upper_shadow >= body * 2 and lower_shadow <= body * 1.1 and close <= low + candle_range * 0.45:
        patterns.append(
            CandlestickPattern(
                key="shooting_star",
                label="射击之星",
                direction="bearish",
                confidence=63,
                description="上影线较长，短线冲高回落压力较明显。",
            )
        )
        bias -= 8

    bullish_engulfing = close > open_price and prev_close < prev_open and close >= prev_open and open_price <= prev_close
    bearish_engulfing = close < open_price and prev_close > prev_open and close <= prev_open and open_price >= prev_close
    if bullish_engulfing:
        patterns.append(
            CandlestickPattern(
                key="bullish_engulfing",
                label="看涨吞没",
                direction="bullish",
                confidence=70,
                description="最新阳线覆盖前一日阴线实体，短线承接修复力度较强。",
            )
        )
        bias += 12
    if bearish_engulfing:
        patterns.append(
            CandlestickPattern(
                key="bearish_engulfing",
                label="看跌吞没",
                direction="bearish",
                confidence=70,
                description="最新阴线覆盖前一日阳线实体，短线抛压增强。",
            )
        )
        bias -= 12

    if len(work) >= 3:
        day1 = work.iloc[-3]
        day2 = work.iloc[-2]
        day3 = work.iloc[-1]
        d1_body = abs(_safe_number(day1["close"]) - _safe_number(day1["open"]))
        d2_body = abs(_safe_number(day2["close"]) - _safe_number(day2["open"]))
        d3_body = abs(_safe_number(day3["close"]) - _safe_number(day3["open"]))
        if (
            _safe_number(day1["close"]) < _safe_number(day1["open"])
            and d2_body < d1_body * 0.45
            and _safe_number(day3["close"]) > _safe_number(day3["open"])
            and _safe_number(day3["close"]) > (_safe_number(day1["open"]) + _safe_number(day1["close"])) / 2
        ):
            patterns.append(
                CandlestickPattern(
                    key="morning_star",
                    label="早晨之星",
                    direction="bullish",
                    confidence=68,
                    description="三日结构出现弱转强迹象，短线止跌修复概率上升。",
                )
            )
            bias += 10
        if (
            _safe_number(day1["close"]) > _safe_number(day1["open"])
            and d2_body < d1_body * 0.45
            and _safe_number(day3["close"]) < _safe_number(day3["open"])
            and _safe_number(day3["close"]) < (_safe_number(day1["open"]) + _safe_number(day1["close"])) / 2
            and d3_body > 0
        ):
            patterns.append(
                CandlestickPattern(
                    key="evening_star",
                    label="黄昏之星",
                    direction="bearish",
                    confidence=68,
                    description="三日结构出现强转弱迹象，短线回落风险上升。",
                )
            )
            bias -= 10

    if not patterns:
        patterns.append(
            CandlestickPattern(
                key="none",
                label="未命中典型反转形态",
                direction="neutral",
                confidence=50,
                description="最新 K 线未触发内置的典型形态规则，更多依赖趋势和量价位置判断。",
            )
        )

    return patterns, bias


def _nearest_levels(levels: list[TechnicalLevel], last_close: float, above: bool) -> list[TechnicalLevel]:
    filtered = [level for level in levels if (level.price >= last_close if above else level.price <= last_close)]
    return sorted(filtered, key=lambda level: abs(level.price - last_close))[:5]


def build_technical_analysis(frame: pd.DataFrame, code: str, name: str = "") -> TechnicalAnalysisResponse:
    work = _prepare_history(frame)
    if len(work) < 30:
        raise ValueError(f"{normalize_stock_code(code)} 的历史行情不足，无法计算技术分析")

    work = _add_indicator_columns(work)
    last = work.iloc[-1]
    last_close = _safe_number(last["close"])
    atr14 = _safe_number(last.get("atr14"))
    volatility = atr14 / last_close * 100 if last_close > 0 and atr14 > 0 else 0

    ma5 = _safe_number(last.get("ma5"))
    ma10 = _safe_number(last.get("ma10"))
    ma20 = _safe_number(last.get("ma20"))
    ma60 = _safe_number(last.get("ma60"))
    ma120 = _safe_number(last.get("ma120"))
    return5 = _safe_number(last.get("return5"))
    return20 = _safe_number(last.get("return20"))
    ma20_slope = _safe_number(last.get("ma20_slope5"))
    volume_ma20 = _safe_number(last.get("volume_ma20"))
    volume_ratio = _safe_number(last.get("volume")) / volume_ma20 if volume_ma20 > 0 else 1
    boll_upper = _safe_number(last.get("boll_upper20"))
    boll_lower = _safe_number(last.get("boll_lower20"))

    score = 50.0
    signals: list[TechnicalSignal] = []

    if ma20 > 0:
        above_ma20 = last_close >= ma20
        score += 10 if above_ma20 else -10
        signals.append(
            TechnicalSignal(
                label="MA20位置",
                value=f"收盘价{'站上' if above_ma20 else '跌破'}MA20",
                direction="bullish" if above_ma20 else "bearish",
                weight=10,
            )
        )
    if ma60 > 0:
        above_ma60 = last_close >= ma60
        score += 8 if above_ma60 else -8
        signals.append(
            TechnicalSignal(
                label="MA60位置",
                value=f"收盘价{'站上' if above_ma60 else '跌破'}MA60",
                direction="bullish" if above_ma60 else "bearish",
                weight=8,
            )
        )
    if ma5 > 0 and ma10 > 0 and ma20 > 0:
        aligned_up = ma5 >= ma10 >= ma20
        aligned_down = ma5 <= ma10 <= ma20
        if aligned_up:
            score += 12
            signals.append(TechnicalSignal(label="均线排列", value="MA5/MA10/MA20多头排列", direction="bullish", weight=12))
        elif aligned_down:
            score -= 12
            signals.append(TechnicalSignal(label="均线排列", value="MA5/MA10/MA20空头排列", direction="bearish", weight=12))
        else:
            signals.append(TechnicalSignal(label="均线排列", value="短期均线交织", direction="neutral", weight=4))
    if ma20_slope:
        score += max(-8, min(8, ma20_slope * 2.5))
        signals.append(
            TechnicalSignal(
                label="MA20斜率",
                value=f"{ma20_slope:.2f}%",
                direction="bullish" if ma20_slope > 0 else "bearish",
                weight=abs(round(max(-8, min(8, ma20_slope * 2.5)), 1)),
            )
        )
    if return5:
        score += max(-8, min(8, return5 * 0.9))
        signals.append(
            TechnicalSignal(
                label="5日涨跌",
                value=f"{return5:.2f}%",
                direction="bullish" if return5 > 0 else "bearish",
                weight=abs(round(max(-8, min(8, return5 * 0.9)), 1)),
            )
        )
    if return20:
        score += max(-7, min(7, return20 * 0.35))
        signals.append(
            TechnicalSignal(
                label="20日涨跌",
                value=f"{return20:.2f}%",
                direction="bullish" if return20 > 0 else "bearish",
                weight=abs(round(max(-7, min(7, return20 * 0.35)), 1)),
            )
        )
    if boll_upper > 0 and boll_lower > 0:
        if last_close > boll_upper:
            score += 4
            signals.append(TechnicalSignal(label="布林位置", value="收盘价位于布林上轨上方", direction="bullish", weight=4))
        elif last_close < boll_lower:
            score -= 6
            signals.append(TechnicalSignal(label="布林位置", value="收盘价跌破布林下轨", direction="bearish", weight=6))
        else:
            signals.append(TechnicalSignal(label="布林位置", value="收盘价位于布林通道内", direction="neutral", weight=3))
    if volume_ratio >= 1.4 and return5 > 0:
        score += 6
        signals.append(TechnicalSignal(label="量能", value=f"20日量比 {volume_ratio:.2f}，放量上行", direction="bullish", weight=6))
    elif volume_ratio >= 1.4 and return5 < 0:
        score -= 6
        signals.append(TechnicalSignal(label="量能", value=f"20日量比 {volume_ratio:.2f}，放量回落", direction="bearish", weight=6))
    elif volume_ratio < 0.75:
        signals.append(TechnicalSignal(label="量能", value=f"20日量比 {volume_ratio:.2f}，量能偏低", direction="neutral", weight=3))

    patterns, pattern_bias = _latest_candle_patterns(work)
    score = _clamp(score + pattern_bias, 0, 100)
    upside, downside, sideways = _probabilities(score, pattern_bias, volatility)

    all_levels: list[TechnicalLevel] = []
    for key, label, price, basis in [
        ("ma20", "MA20", ma20, "最近20个交易日收盘价均值"),
        ("ma60", "MA60", ma60, "最近60个交易日收盘价均值"),
        ("ma120", "MA120", ma120, "最近120个交易日收盘价均值"),
        ("low20", "20日低点", last.get("low20"), "最近20个交易日最低价"),
        ("low60", "60日低点", last.get("low60"), "最近60个交易日最低价"),
        ("high20", "20日高点", last.get("high20"), "最近20个交易日最高价"),
        ("high60", "60日高点", last.get("high60"), "最近60个交易日最高价"),
        ("boll_lower20", "布林下轨", boll_lower, "20日均线减2倍标准差"),
        ("boll_upper20", "布林上轨", boll_upper, "20日均线加2倍标准差"),
        ("atr14_lower", "ATR下沿", last_close - atr14 * 1.5, "最新收盘价减1.5倍ATR14"),
        ("atr14_upper", "ATR上沿", last_close + atr14 * 1.5, "最新收盘价加1.5倍ATR14"),
        ("vwap60", "60日成交均价", last.get("vwap60"), "最近60个交易日成交额/成交量"),
    ]:
        _add_level(all_levels, key, label, price, last_close, basis)

    support_levels = _nearest_levels(all_levels, last_close, above=False)
    resistance_levels = _nearest_levels(all_levels, last_close, above=True)
    trend_label = _direction_label(score)
    risks: list[str] = []
    if volatility >= 5:
        risks.append("ATR波动率偏高，短线判断的不确定性较大")
    if downside >= 38:
        risks.append("下跌概率权重较高，需留意关键支撑是否失守")
    if not resistance_levels:
        risks.append("上方压力位缺少足够历史参考，需结合更长周期复核")
    if not support_levels:
        risks.append("下方支撑位缺少足够历史参考，需结合更长周期复核")
    if not risks:
        risks.append("技术面未见单一极端风险，但仍需结合市场环境和公告信息")

    summary = (
        f"{trend_label}：上涨概率 {upside:.1f}%，下跌概率 {downside:.1f}%，震荡概率 {sideways:.1f}%。"
        f"该判断基于均线位置、量能、ATR波动、支撑压力和最近K线形态的规则化打分。"
    )

    return TechnicalAnalysisResponse(
        code=normalize_stock_code(code),
        name=name,
        generated_at=utc_now_iso(),
        trade_date=last["date"].date().isoformat(),
        last_close=round(last_close, 2),
        trend_label=trend_label,
        trend_score=round(score, 1),
        upside_probability=upside,
        downside_probability=downside,
        sideways_probability=sideways,
        summary=summary,
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        patterns=patterns,
        signals=signals,
        risks=risks,
    )


def calculate_technical_analysis(code: str, name: str = "") -> TechnicalAnalysisResponse:
    return build_technical_analysis(fetch_price_history(code), code, name)
