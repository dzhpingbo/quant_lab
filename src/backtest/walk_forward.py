"""
Walk-Forward 引擎（滚动窗口/扩展窗口回测）
"""

import pandas as pd
import numpy as np
from typing import Callable, Dict, List, Optional, Any, Tuple
from loguru import logger
from src.backtest.metrics import BacktestMetrics


class WalkForwardEngine:
    """Walk-Forward 回测引擎"""
    
    def __init__(
        self,
        train_window: int = 252,
        test_window: int = 63,
        expanding: bool = False,
        n_jobs: int = 1,
    ):
        """
        Args:
            train_window: 训练窗口（交易日数）
            test_window: 测试窗口（交易日数）
            expanding: True=扩展窗口，False=滚动窗口
            n_jobs: 并行数
        """
        self.train_window = train_window
        self.test_window = test_window
        self.expanding = expanding
        self.n_jobs = n_jobs
    
    def split_dates(
        self,
        dates: pd.DatetimeIndex,
    ) -> List[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
        """
        划分训练/测试时间段
        
        Returns:
            List of (train_dates, test_dates)
        """
        splits = []
        n = len(dates)
        start = 0
        
        while start + self.train_window + self.test_window <= n:
            if self.expanding:
                train_start = 0
            else:
                train_start = start
                
            train_end = start + self.train_window
            test_end = train_end + self.test_window
            
            train_dates = dates[train_start:train_end]
            test_dates = dates[train_end:test_end]
            
            splits.append((train_dates, test_dates))
            start += self.test_window
            
        return splits
    
    def run(
        self,
        factor_fn: Callable,
        portfolio_fn: Callable,
        close: pd.DataFrame,
        factor_params: Optional[Dict] = None,
        portfolio_params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        运行Walk-Forward回测
        
        Args:
            factor_fn: 因子计算函数 fn(close, train_dates, **params) -> factor_panel
            portfolio_fn: 组合构建函数 fn(factor, close, **params) -> (nav, ret)
            close: 收盘价宽表
            factor_params: 因子参数
            portfolio_params: 组合参数
            
        Returns:
            结果字典
        """
        factor_params = factor_params or {}
        portfolio_params = portfolio_params or {}
        
        splits = self.split_dates(close.index)
        logger.info(f"Walk-forward splits: {len(splits)}")
        
        all_navs = []
        all_rets = []
        split_results = []
        
        for i, (train_dates, test_dates) in enumerate(splits):
            logger.info(
                f"Split {i+1}/{len(splits)}: "
                f"train={train_dates[0].date()}~{train_dates[-1].date()}, "
                f"test={test_dates[0].date()}~{test_dates[-1].date()}"
            )
            
            try:
                # 训练期计算因子参数（这里直接计算全样本因子）
                train_close = close.loc[train_dates]
                test_close = close.loc[test_dates]
                
                # 计算测试期因子
                factor = factor_fn(close.loc[:test_dates[-1]], **factor_params)
                test_factor = factor.loc[test_dates]
                
                # 构建组合
                nav, ret, _ = portfolio_fn(test_factor, test_close, **portfolio_params)
                
                all_navs.append(nav)
                all_rets.append(ret)
                split_results.append({
                    "split": i + 1,
                    "train_start": str(train_dates[0].date()),
                    "train_end": str(train_dates[-1].date()),
                    "test_start": str(test_dates[0].date()),
                    "test_end": str(test_dates[-1].date()),
                    "period_return": nav.iloc[-1] / nav.iloc[0] - 1,
                })
                
            except Exception as e:
                logger.error(f"Split {i+1} failed: {e}")
                continue
        
        # 拼接所有测试期结果
        if all_rets:
            combined_ret = pd.concat(all_rets)
            combined_ret = combined_ret[~combined_ret.index.duplicated(keep="first")]
            
            combined_nav = (1 + combined_ret).cumprod()
            combined_nav.iloc[0] = 1.0
            
            metrics = BacktestMetrics.compute(combined_nav, combined_ret)
        else:
            combined_nav = pd.Series()
            combined_ret = pd.Series()
            metrics = {}
        
        return {
            "nav": combined_nav,
            "returns": combined_ret,
            "metrics": metrics,
            "splits": split_results,
            "n_splits": len(splits),
        }
    
    def batch_param_scan(
        self,
        param_grid: Dict[str, List],
        factor_fn: Callable,
        portfolio_fn: Callable,
        close: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        批量参数扫描
        
        Args:
            param_grid: 参数网格 {参数名: 值列表}
            factor_fn: 因子函数
            portfolio_fn: 组合函数
            close: 收盘价
            
        Returns:
            参数扫描结果DataFrame
        """
        from itertools import product
        
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        
        results = []
        
        for combo in product(*param_values):
            params = dict(zip(param_names, combo))
            
            try:
                result = self.run(
                    factor_fn=factor_fn,
                    portfolio_fn=portfolio_fn,
                    close=close,
                    factor_params=params,
                )
                
                row = {**params, **result["metrics"]}
                results.append(row)
                
            except Exception as e:
                logger.warning(f"Params {params} failed: {e}")
                
        return pd.DataFrame(results)
