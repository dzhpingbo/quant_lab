"""
信号工厂 - 基于因子生成交易信号
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any
from loguru import logger


class SignalFactory:
    """交易信号生成工厂"""
    
    def __init__(self, market: str = "cn"):
        self.market = market
    
    # ── 截面信号（多只股票，横截面排名）──
    
    def cross_section_rank(
        self,
        factor: pd.DataFrame,
        direction: int = 1,
        top_pct: float = 0.2,
    ) -> pd.DataFrame:
        """
        截面排名信号：每期选取因子值最高/最低的股票
        
        Args:
            factor: 因子宽表（行=日期，列=股票）
            direction: 1=因子值高→买入，-1=因子值低→买入
            top_pct: 选股比例
            
        Returns:
            布尔信号宽表
        """
        if direction == -1:
            factor = -factor
            
        # 每行横截面排名
        rank_pct = factor.rank(axis=1, pct=True)
        signal = (rank_pct >= (1 - top_pct)).astype(float)
        
        return signal
    
    def top_bottom_long_short(
        self,
        factor: pd.DataFrame,
        top_pct: float = 0.2,
        bottom_pct: float = 0.2,
    ) -> pd.DataFrame:
        """
        多空信号：Top做多，Bottom做空
        
        Returns:
            信号DataFrame，1=做多，-1=做空，0=不持仓
        """
        rank_pct = factor.rank(axis=1, pct=True)
        signal = pd.DataFrame(0, index=factor.index, columns=factor.columns, dtype=float)
        signal[rank_pct >= (1 - top_pct)] = 1
        signal[rank_pct <= bottom_pct] = -1
        
        return signal
    
    # ── 时序信号（单只股票时序动量/反转）──
    
    def momentum_signal(
        self,
        close: pd.DataFrame,
        window: int = 20,
        direction: int = 1,
    ) -> pd.DataFrame:
        """
        动量信号：过去N日收益率>0 → 做多
        
        Args:
            close: 收盘价宽表
            window: 动量窗口
            direction: 1=正动量做多，-1=负动量做多（反转）
            
        Returns:
            布尔信号宽表
        """
        ret = close.pct_change(window)
        
        if direction == 1:
            return (ret > 0).astype(float)
        else:
            return (ret < 0).astype(float)
    
    def breakout_signal(
        self,
        close: pd.DataFrame,
        window: int = 20,
    ) -> pd.DataFrame:
        """
        突破信号：收盘价突破N日高点
        
        Returns:
            布尔信号宽表
        """
        high_window = close.rolling(window).max().shift(1)
        return (close > high_window).astype(float)
    
    def ma_crossover_signal(
        self,
        close: pd.DataFrame,
        short_window: int = 5,
        long_window: int = 20,
    ) -> pd.DataFrame:
        """
        均线交叉信号：短期均线上穿长期均线
        
        Returns:
            信号宽表（1=买，-1=卖，0=不变）
        """
        short_ma = close.rolling(short_window).mean()
        long_ma = close.rolling(long_window).mean()
        
        # 当前状态
        above = (short_ma > long_ma).astype(float)
        prev_above = above.shift(1)
        
        # 金叉=1，死叉=-1
        signal = pd.DataFrame(0, index=close.index, columns=close.columns, dtype=float)
        signal[(above == 1) & (prev_above == 0)] = 1   # 金叉
        signal[(above == 0) & (prev_above == 1)] = -1  # 死叉
        
        return signal
    
    def rsi_signal(
        self,
        close: pd.DataFrame,
        window: int = 14,
        oversold: float = 30,
        overbought: float = 70,
    ) -> pd.DataFrame:
        """
        RSI超买超卖信号
        
        Returns:
            信号宽表（1=超卖买入，-1=超买卖出）
        """
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
        
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        signal = pd.DataFrame(0, index=close.index, columns=close.columns, dtype=float)
        signal[rsi < oversold] = 1
        signal[rsi > overbought] = -1
        
        return signal

    def time_series_momentum_signal(
        self,
        close: pd.DataFrame,
        lookback: int = 60,
        skip: int = 0,
        threshold: float = 0.0,
        direction: int = 1,
    ) -> pd.DataFrame:
        """Absolute momentum signal from each asset's own trailing return."""

        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if skip < 0:
            raise ValueError("skip must be non-negative")

        basis = close.shift(skip) if skip else close
        momentum = basis.pct_change(lookback, fill_method=None)
        if direction == 1:
            return (momentum > threshold).astype(float)
        if direction == -1:
            return (momentum < -threshold).astype(float)
        raise ValueError("direction must be 1 or -1")

    def dual_momentum_signal(
        self,
        close: pd.DataFrame,
        lookback: int = 60,
        top_k: int = 3,
        min_abs_momentum: float = 0.0,
    ) -> pd.DataFrame:
        """Relative-strength rotation gated by absolute momentum."""

        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        momentum = close.pct_change(lookback, fill_method=None)
        ranks = momentum.rank(axis=1, ascending=False, method="first")
        signal = (ranks <= top_k) & (momentum > min_abs_momentum)
        return signal.astype(float)

    def donchian_trend_signal(
        self,
        close: pd.DataFrame,
        high: Optional[pd.DataFrame] = None,
        low: Optional[pd.DataFrame] = None,
        entry_window: int = 20,
        exit_window: int = 10,
    ) -> pd.DataFrame:
        """Turtle-style Donchian breakout desired-position signal."""

        if entry_window <= 0 or exit_window <= 0:
            raise ValueError("entry_window and exit_window must be positive")
        high = close if high is None else high.reindex_like(close)
        low = close if low is None else low.reindex_like(close)

        entry_level = high.rolling(entry_window).max().shift(1)
        exit_level = low.rolling(exit_window).min().shift(1)
        out = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        held = pd.Series(False, index=close.columns)

        for date in close.index:
            enter = close.loc[date] > entry_level.loc[date]
            exit_ = close.loc[date] < exit_level.loc[date]
            held = (held | enter.fillna(False)) & ~exit_.fillna(False)
            out.loc[date] = held.astype(float)

        return out

    def zscore_mean_reversion_signal(
        self,
        close: pd.DataFrame,
        window: int = 20,
        entry_z: float = 2.0,
        exit_z: float = 0.0,
        allow_short: bool = False,
    ) -> pd.DataFrame:
        """Rolling z-score mean-reversion desired-position signal."""

        if window <= 1:
            raise ValueError("window must be greater than 1")
        mean = close.rolling(window).mean()
        std = close.rolling(window).std().replace(0.0, np.nan)
        z = close.sub(mean).div(std)

        out = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        position = pd.Series(0.0, index=close.columns)
        for date in close.index:
            row = z.loc[date]
            long_entry = row <= -entry_z
            long_exit = row >= -exit_z
            position[long_entry.fillna(False)] = 1.0
            position[long_exit.fillna(False) & (position > 0)] = 0.0
            if allow_short:
                short_entry = row >= entry_z
                short_exit = row <= exit_z
                position[short_entry.fillna(False)] = -1.0
                position[short_exit.fillna(False) & (position < 0)] = 0.0
            out.loc[date] = position

        return out

    def macd_trend_signal(
        self,
        close: pd.DataFrame,
        fast_window: int = 12,
        slow_window: int = 26,
        signal_window: int = 9,
    ) -> pd.DataFrame:
        """MACD trend signal: long when MACD is above its signal line."""

        if fast_window <= 0 or slow_window <= 0 or signal_window <= 0:
            raise ValueError("MACD windows must be positive")
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")

        fast = close.ewm(span=fast_window, adjust=False, min_periods=fast_window).mean()
        slow = close.ewm(span=slow_window, adjust=False, min_periods=slow_window).mean()
        macd = fast - slow
        signal_line = macd.ewm(span=signal_window, adjust=False, min_periods=signal_window).mean()
        return (macd > signal_line).astype(float)

    def dual_thrust_signal(
        self,
        open_price: pd.DataFrame,
        high: pd.DataFrame,
        low: pd.DataFrame,
        close: pd.DataFrame,
        window: int = 20,
        k1: float = 0.5,
        k2: float = 0.5,
        long_only: bool = True,
    ) -> pd.DataFrame:
        """Dual Thrust breakout signal using prior-window range."""

        if window <= 0:
            raise ValueError("window must be positive")
        high = high.reindex_like(close)
        low = low.reindex_like(close)
        open_price = open_price.reindex_like(close)

        hh = high.rolling(window).max()
        hc = close.rolling(window).max()
        lc = close.rolling(window).min()
        ll = low.rolling(window).min()
        range_ = pd.concat([hh - lc, hc - ll], axis=0).groupby(level=0).max().shift(1)
        upper = open_price + k1 * range_
        lower = open_price - k2 * range_

        signal = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        signal[close > upper] = 1.0
        signal[close < lower] = 0.0 if long_only else -1.0
        return signal.ffill().fillna(0.0)
    
    def volatility_filter(
        self,
        signal: pd.DataFrame,
        close: pd.DataFrame,
        window: int = 20,
        max_vol: float = 0.5,
    ) -> pd.DataFrame:
        """
        波动率过滤：过滤掉高波动股票
        
        Args:
            signal: 原始信号
            close: 收盘价
            window: 波动率窗口
            max_vol: 最大允许年化波动率
            
        Returns:
            过滤后的信号
        """
        daily_vol = close.pct_change().rolling(window).std()
        ann_vol = daily_vol * np.sqrt(252)
        
        # 高波动股票信号置0
        filtered = signal.copy()
        filtered[ann_vol > max_vol] = 0
        
        return filtered
    
    def suspension_filter(
        self,
        signal: pd.DataFrame,
        volume: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        停牌过滤（成交量为0的股票信号置0）
        
        Args:
            signal: 原始信号
            volume: 成交量宽表
            
        Returns:
            过滤后的信号
        """
        filtered = signal.copy()
        filtered[volume == 0] = 0
        return filtered
    
    def price_limit_filter(
        self,
        signal: pd.DataFrame,
        close: pd.DataFrame,
        prefix_688: bool = True,
    ) -> pd.DataFrame:
        """
        涨停过滤（涨停日不买入）
        
        Args:
            signal: 原始信号
            close: 收盘价
            prefix_688: 是否包含科创板
            
        Returns:
            过滤后的信号
        """
        ret = close.pct_change()
        
        # 涨停阈值（科创板20%，主板10%）
        if prefix_688:
            # 简化处理：所有股票都用20%判断是否涨停
            at_limit = ret >= 0.199
        else:
            at_limit = ret >= 0.099
            
        filtered = signal.copy()
        filtered[at_limit] = 0
        
        return filtered
    
    def combine_signals(
        self,
        signals: List[pd.DataFrame],
        weights: Optional[List[float]] = None,
        method: str = "mean",
    ) -> pd.DataFrame:
        """
        组合多个信号
        
        Args:
            signals: 信号列表
            weights: 权重列表
            method: 组合方式 (mean/vote/weighted)
            
        Returns:
            组合信号
        """
        if not signals:
            return pd.DataFrame()
            
        # 对齐索引
        combined = pd.concat(signals, keys=range(len(signals)), axis=0)
        
        if method == "mean":
            result = pd.concat(signals).groupby(level=0).mean()
        elif method == "vote":
            result = (pd.concat(signals) > 0).groupby(level=0).mean()
            result = (result > 0.5).astype(float)
        elif method == "weighted" and weights is not None:
            result = sum(w * s for w, s in zip(weights, signals)) / sum(weights)
        else:
            result = signals[0]
            
        return result
