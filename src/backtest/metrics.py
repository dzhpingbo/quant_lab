"""
回测指标计算
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from scipy import stats


class BacktestMetrics:
    """回测绩效指标"""
    
    @staticmethod
    def compute(
        nav: pd.Series,
        ret: pd.Series,
        benchmark_nav: Optional[pd.Series] = None,
        benchmark_ret: Optional[pd.Series] = None,
        risk_free: float = 0.02,
        periods_per_year: int = 252,
    ) -> Dict[str, float]:
        """
        计算完整回测指标
        
        Args:
            nav: 策略净值序列
            ret: 策略收益率序列
            benchmark_nav: 基准净值
            benchmark_ret: 基准收益率
            risk_free: 无风险年化收益率
            periods_per_year: 每年交易日数
            
        Returns:
            指标字典
        """
        metrics = {}
        
        # 总收益率
        metrics["total_return"] = nav.iloc[-1] / nav.iloc[0] - 1
        
        # 年化收益率
        n_years = len(ret) / periods_per_year
        metrics["annual_return"] = (1 + metrics["total_return"]) ** (1 / n_years) - 1
        
        # 年化波动率
        metrics["annual_vol"] = ret.std() * np.sqrt(periods_per_year)
        
        # 夏普比率
        excess_ret = metrics["annual_return"] - risk_free
        metrics["sharpe"] = excess_ret / metrics["annual_vol"] if metrics["annual_vol"] > 0 else 0
        
        # 最大回撤
        rolling_max = nav.cummax()
        drawdown = (nav - rolling_max) / rolling_max
        metrics["max_drawdown"] = drawdown.min()
        metrics["max_drawdown_pct"] = abs(metrics["max_drawdown"]) * 100
        
        # 卡玛比率
        metrics["calmar"] = metrics["annual_return"] / abs(metrics["max_drawdown"]) if metrics["max_drawdown"] != 0 else 0
        
        # 胜率
        metrics["win_rate"] = (ret > 0).mean()
        
        # 盈亏比
        wins = ret[ret > 0]
        losses = ret[ret < 0]
        metrics["profit_loss_ratio"] = wins.mean() / abs(losses.mean()) if len(losses) > 0 and losses.mean() != 0 else np.inf
        
        # Sortino比率
        downside_ret = ret[ret < 0]
        downside_std = downside_ret.std() * np.sqrt(periods_per_year) if len(downside_ret) > 0 else 0
        metrics["sortino"] = excess_ret / downside_std if downside_std > 0 else 0
        
        # 信息比率（对基准）
        if benchmark_ret is not None:
            active_ret = ret - benchmark_ret.reindex(ret.index).fillna(0)
            te = active_ret.std() * np.sqrt(periods_per_year)
            metrics["information_ratio"] = (active_ret.mean() * periods_per_year) / te if te > 0 else 0
            
            # Alpha和Beta
            y = ret.values
            x = benchmark_ret.reindex(ret.index).fillna(0).values
            
            if len(y) > 1:
                beta, alpha, r_value, p_value, std_err = stats.linregress(x, y)
                metrics["alpha"] = alpha * periods_per_year
                metrics["beta"] = beta
                metrics["r_squared"] = r_value ** 2
            
            # 超额收益
            if benchmark_nav is not None:
                metrics["excess_total_return"] = (nav.iloc[-1] / nav.iloc[0]) - (benchmark_nav.iloc[-1] / benchmark_nav.iloc[0])
        
        # 最大连续亏损天数
        losing_streak = BacktestMetrics._max_consecutive(ret < 0)
        metrics["max_losing_streak"] = losing_streak
        
        # 回撤时间统计
        metrics["drawdown_duration_max"] = BacktestMetrics._max_drawdown_duration(nav)
        
        return metrics
    
    @staticmethod
    def factor_ic(
        factor: pd.Series,
        forward_ret: pd.Series,
        method: str = "rank",
    ) -> float:
        """
        计算因子IC
        
        Args:
            factor: 因子值
            forward_ret: 前向收益率
            method: 计算方法 (pearson/rank)
            
        Returns:
            IC值
        """
        common_idx = factor.index.intersection(forward_ret.index)
        f = factor.loc[common_idx].dropna()
        r = forward_ret.loc[common_idx].dropna()
        
        common = f.index.intersection(r.index)
        if len(common) < 2:
            return np.nan
            
        f = f.loc[common]
        r = r.loc[common]
        
        if method == "rank":
            ic = f.rank().corr(r.rank())
        else:
            ic = f.corr(r)
            
        return ic
    
    @staticmethod
    def factor_ic_series(
        factor_panel: pd.DataFrame,
        forward_ret_panel: pd.DataFrame,
        method: str = "rank",
    ) -> pd.Series:
        """
        计算时序IC序列
        
        Args:
            factor_panel: 因子宽表（行=日期，列=股票）
            forward_ret_panel: 前向收益率宽表
            method: 计算方法
            
        Returns:
            IC时序序列
        """
        ic_series = {}
        
        common_dates = factor_panel.index.intersection(forward_ret_panel.index)
        
        for date in common_dates:
            f = factor_panel.loc[date].dropna()
            r = forward_ret_panel.loc[date].dropna()
            
            common_syms = f.index.intersection(r.index)
            if len(common_syms) < 5:
                continue
                
            f = f.loc[common_syms]
            r = r.loc[common_syms]
            
            if method == "rank":
                ic = f.rank().corr(r.rank())
            else:
                ic = f.corr(r)
                
            ic_series[date] = ic
            
        return pd.Series(ic_series)
    
    @staticmethod
    def factor_ic_stats(ic_series: pd.Series) -> Dict[str, float]:
        """
        计算IC统计指标
        
        Returns:
            {IC均值, IC标准差, IC_IR, IC>0比率}
        """
        ic_clean = ic_series.dropna()
        
        if len(ic_clean) == 0:
            return {}
            
        return {
            "ic_mean": ic_clean.mean(),
            "ic_std": ic_clean.std(),
            "ic_ir": ic_clean.mean() / ic_clean.std() if ic_clean.std() > 0 else 0,
            "ic_positive_rate": (ic_clean > 0).mean(),
            "ic_abs_mean": ic_clean.abs().mean(),
        }
    
    @staticmethod
    def _max_consecutive(condition: pd.Series) -> int:
        """计算最大连续True天数"""
        max_streak = 0
        current = 0
        for val in condition:
            if val:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak
    
    @staticmethod
    def _max_drawdown_duration(nav: pd.Series) -> int:
        """计算最长回撤持续天数"""
        peak = nav.cummax()
        in_drawdown = nav < peak
        
        max_dur = 0
        current = 0
        for val in in_drawdown:
            if val:
                current += 1
                max_dur = max(max_dur, current)
            else:
                current = 0
        return max_dur
