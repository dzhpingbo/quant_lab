"""
组合工厂 - 基于信号构建投资组合
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from loguru import logger


class PortfolioFactory:
    """投资组合构建工厂"""
    
    def __init__(
        self,
        market: str = "cn",
        initial_cash: float = 1_000_000,
        commission_pct: float = 0.00025,
        stamp_tax_pct: float = 0.001,
        min_size: float = 100,
    ):
        """
        Args:
            market: 市场 (cn/us)
            initial_cash: 初始资金
            commission_pct: 佣金率
            stamp_tax_pct: 印花税（A股卖出）
            min_size: 最小交易单位（A股100股）
        """
        self.market = market
        self.initial_cash = initial_cash
        self.commission_pct = commission_pct
        self.stamp_tax_pct = stamp_tax_pct
        self.min_size = min_size
    
    def equal_weight_portfolio(
        self,
        signal: pd.DataFrame,
        close: pd.DataFrame,
        rebalance_freq: str = "M",
        max_positions: int = 20,
    ) -> Dict[str, Any]:
        """
        等权组合

        Args:
            signal: 信号宽表（1=持有，0=不持有）
            close: 收盘价宽表
            rebalance_freq: 调仓频率 (D/W/M)
            max_positions: 最大持仓数

        Returns:
            组合参数字典（可传入 vbt.Portfolio.from_signals）
        """
        # 提取调仓日期
        if rebalance_freq == "M":
            rebalance_mask = close.index.to_series().dt.is_month_end
        elif rebalance_freq == "W":
            rebalance_mask = close.index.to_series().dt.dayofweek == 4
        else:
            rebalance_mask = pd.Series(True, index=close.index)
        
        # 调仓日的信号
        entries = pd.DataFrame(False, index=close.index, columns=close.columns)
        exits = pd.DataFrame(False, index=close.index, columns=close.columns)
        
        prev_holdings = pd.Series(False, index=close.columns)
        
        dates = close.index
        for i, date in enumerate(dates):
            if rebalance_mask.get(date, False):
                if i + 1 >= len(dates):
                    break

                trade_date = dates[i + 1]
                curr_signal = signal.loc[date].fillna(0).astype(bool)
                
                # 限制最大持仓数
                if curr_signal.sum() > max_positions:
                    # 按因子值随机选取（此处直接取前N）
                    top_n = curr_signal[curr_signal > 0].index[:max_positions]
                    curr_signal = pd.Series(False, index=close.columns)
                    curr_signal[top_n] = True
                
                # 新增持仓
                entries.loc[trade_date] = curr_signal & ~prev_holdings
                # 退出持仓
                exits.loc[trade_date] = prev_holdings & ~curr_signal
                
                prev_holdings = curr_signal.astype(bool)
        
        return {
            "entries": entries,
            "exits": exits,
            "close": close,
            "init_cash": self.initial_cash,
            "fees": self.commission_pct,
            "size_granularity": self.min_size,
        }
    
    def run_portfolio_simple(
        self,
        signal: pd.DataFrame,
        close: pd.DataFrame,
        rebalance_freq: str = "M",
        max_positions: int = 20,
    ) -> Any:
        """
        运行等权组合（无需安装vectorbt，使用自实现逻辑）
        
        Returns:
            组合净值序列
        """
        pf_params = self.equal_weight_portfolio(
            signal, close, rebalance_freq, max_positions
        )
        
        # 模拟组合收益
        holdings = pd.DataFrame(False, index=close.index, columns=close.columns)
        prev_holdings = pd.Series(False, index=close.columns)
        
        if rebalance_freq == "M":
            rebalance_mask = close.index.to_series().dt.is_month_end
        elif rebalance_freq == "W":
            rebalance_mask = close.index.to_series().dt.dayofweek == 4
        else:
            rebalance_mask = pd.Series(True, index=close.index)
        
        for date in close.index:
            if rebalance_mask.get(date, False):
                curr_signal = signal.loc[date].fillna(0).astype(bool)
                n_signals = curr_signal.sum()
                
                if n_signals > max_positions:
                    top_idx = signal.loc[date].nlargest(max_positions).index
                    curr_signal = pd.Series(False, index=close.columns)
                    curr_signal[top_idx] = True
                
                prev_holdings = curr_signal
                
            holdings.loc[date] = prev_holdings
        
        # 计算每日收益
        daily_ret = close.pct_change()
        
        # 持仓权重（等权）
        # Signals formed on date t can only earn returns from the next bar.
        executed_holdings = holdings.shift(1, fill_value=False).astype(bool)

        n_holdings = executed_holdings.sum(axis=1).replace(0, np.nan)
        weights = executed_holdings.divide(n_holdings, axis=0).fillna(0)
        
        # 组合收益
        portfolio_ret = (weights * daily_ret).sum(axis=1)
        
        # 扣除交易成本（简化：每次调仓扣除0.1%）
        prev_target = holdings.shift(1, fill_value=False).astype(bool)
        turnover_dates = holdings.ne(prev_target).any(axis=1).shift(1, fill_value=False).astype(bool)

        cost = pd.Series(0.0, index=close.index)
        cost[turnover_dates] = self.commission_pct + self.stamp_tax_pct / 2
        
        portfolio_ret = portfolio_ret - cost
        
        # 净值序列
        nav = (1 + portfolio_ret).cumprod()
        nav.iloc[0] = 1.0
        
        return nav, portfolio_ret, executed_holdings

    def _rebalance_mask(self, index: pd.Index, rebalance_freq: str) -> pd.Series:
        """Return a boolean mask that marks close-time rebalance decision dates."""

        if rebalance_freq == "D":
            return pd.Series(True, index=index)

        dates = pd.DatetimeIndex(index)
        if rebalance_freq == "W":
            periods = dates.to_period("W")
        elif rebalance_freq == "M":
            periods = dates.to_period("M")
        else:
            raise ValueError("rebalance_freq must be one of 'D', 'W', or 'M'")

        period_series = pd.Series(periods, index=index)
        mask = period_series.ne(period_series.shift(-1))
        if len(mask) > 0:
            mask.iloc[-1] = True
        return mask

    @staticmethod
    def _prepare_target_weight_row(
        row: pd.Series,
        max_positions: Optional[int],
        max_abs_weight: Optional[float],
        gross_exposure: Optional[float],
    ) -> pd.Series:
        """Clean, cap, and optionally gross-normalize one target-weight row."""

        clean = row.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
        if max_positions is not None and max_positions > 0:
            keep = clean.abs().nlargest(max_positions).index
            clean = clean.where(clean.index.isin(keep), 0.0)

        if max_abs_weight is not None and max_abs_weight > 0:
            clean = clean.clip(lower=-max_abs_weight, upper=max_abs_weight)

        if gross_exposure is not None:
            gross = clean.abs().sum()
            if gross > 0:
                clean = clean / gross * gross_exposure

        return clean

    def run_weighted_portfolio_simple(
        self,
        target_weights: pd.DataFrame,
        close: pd.DataFrame,
        rebalance_freq: str = "M",
        max_positions: Optional[int] = None,
        max_abs_weight: Optional[float] = None,
        gross_exposure: Optional[float] = None,
        cost_per_turnover: Optional[float] = None,
    ) -> Any:
        """Run a close-signal, next-bar-execution portfolio from target weights.

        `target_weights` is a date x asset matrix. Values can be long-only or
        long/short. The method samples weights on rebalance dates, shifts them
        by one bar before applying returns, and subtracts turnover-proportional
        costs. This keeps the execution convention aligned with
        `run_portfolio_simple`.
        """

        aligned = target_weights.reindex(index=close.index, columns=close.columns).fillna(0.0)
        rebalance_mask = self._rebalance_mask(close.index, rebalance_freq)

        desired_weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        prev_target = pd.Series(0.0, index=close.columns)
        for date in close.index:
            if bool(rebalance_mask.loc[date]):
                prev_target = self._prepare_target_weight_row(
                    aligned.loc[date],
                    max_positions=max_positions,
                    max_abs_weight=max_abs_weight,
                    gross_exposure=gross_exposure,
                )
            desired_weights.loc[date] = prev_target

        daily_ret = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        executed_weights = desired_weights.shift(1, fill_value=0.0)
        portfolio_ret = (executed_weights * daily_ret).sum(axis=1)

        turnover = executed_weights.diff().abs().sum(axis=1)
        if len(turnover) > 0:
            turnover.iloc[0] = executed_weights.iloc[0].abs().sum()

        if cost_per_turnover is None:
            cost_per_turnover = self.commission_pct + self.stamp_tax_pct / 2
        portfolio_ret = portfolio_ret - turnover * float(cost_per_turnover)

        nav = (1 + portfolio_ret).cumprod()
        if len(nav) > 0:
            nav.iloc[0] = 1.0

        return nav, portfolio_ret, executed_weights

    def run_benchmark(
        self,
        close: pd.DataFrame,
        weights: Optional[pd.Series] = None,
    ) -> pd.Series:
        """
        计算基准组合（等权持有所有股票）
        
        Args:
            close: 收盘价宽表
            weights: 各股票权重
            
        Returns:
            基准净值序列
        """
        daily_ret = close.pct_change()
        
        if weights is None:
            bench_ret = daily_ret.mean(axis=1)
        else:
            bench_ret = (daily_ret * weights).sum(axis=1)
            
        nav = (1 + bench_ret).cumprod()
        nav.iloc[0] = 1.0
        
        return nav, bench_ret
