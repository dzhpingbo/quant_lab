"""
VectorBT 主回测引擎（封装完整回测流程）
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from loguru import logger
from datetime import datetime

from src.backtest.data_adapter import VBTDataAdapter
from src.backtest.signal_factory import SignalFactory
from src.backtest.portfolio_factory import PortfolioFactory
from src.backtest.metrics import BacktestMetrics
from src.strategies.factor_enhanced import (
    FactorBlendSpec,
    QuantilePortfolioSpec,
    TimeSeriesOverlaySpec,
    TopKDropoutSpec,
    alphalens_style_factor_weights,
    apply_time_series_overlay,
    combine_enhanced_factor_panels,
    ic_weighted_composite,
    quantile_weights_from_score,
    topk_dropout_weights,
    volatility_target_weights,
)


class VBTBacktestEngine:
    """VectorBT 主回测引擎"""
    
    def __init__(
        self,
        data_dir: str,
        market: str = "cn",
        initial_cash: float = 1_000_000,
    ):
        self.data_dir = data_dir
        self.market = market
        self.initial_cash = initial_cash
        
        self.adapter = VBTDataAdapter(data_dir, market)
        self.signal_factory = SignalFactory(market)
        self.portfolio_factory = PortfolioFactory(market, initial_cash)
        
    def run_factor_strategy(
        self,
        symbols: List[str],
        factor_names: List[str],
        start_date: str,
        end_date: str,
        rebalance_freq: str = "M",
        max_positions: int = 20,
        top_pct: float = 0.2,
        direction: int = 1,
        apply_filters: bool = True,
    ) -> Dict[str, Any]:
        """
        运行因子策略回测
        
        Args:
            symbols: 股票池
            factor_names: 因子名称列表
            start_date: 开始日期
            end_date: 结束日期
            rebalance_freq: 调仓频率
            max_positions: 最大持仓数
            top_pct: 选股比例
            direction: 因子方向
            apply_filters: 是否应用过滤器
            
        Returns:
            结果字典
        """
        logger.info(f"Loading data for {len(symbols)} stocks...")
        
        # 加载数据
        ohlcv = self.adapter.load_ohlcv(symbols, start_date, end_date)
        close = ohlcv.get("close", pd.DataFrame())
        volume = ohlcv.get("volume", pd.DataFrame(index=close.index, columns=close.columns))
        open_price = ohlcv.get("open", close)
        high = ohlcv.get("high", close)
        low = ohlcv.get("low", close)
        
        if close.empty:
            raise ValueError("No data loaded. Check symbols and data directory.")
        
        logger.info(f"Loaded {close.shape[1]} stocks, {close.shape[0]} trading days")
        
        # 计算因子
        logger.info("Computing factors...")
        factor_panel = self._compute_factor_panel(
            close,
            volume,
            factor_names,
            open_price=open_price,
            high=high,
            low=low,
        )
        
        # 生成信号
        logger.info("Generating signals...")
        signal = self.signal_factory.cross_section_rank(
            factor_panel, direction=direction, top_pct=top_pct
        )
        
        # 应用过滤器
        if apply_filters:
            signal = self.signal_factory.suspension_filter(signal, volume)
        
        # 计算基准
        logger.info("Computing benchmark...")
        bench_nav, bench_ret = self.portfolio_factory.run_benchmark(close)
        
        # 运行组合
        logger.info("Running portfolio...")
        nav, ret, holdings = self.portfolio_factory.run_portfolio_simple(
            signal, close, rebalance_freq, max_positions
        )
        
        # 计算指标
        logger.info("Computing metrics...")
        metrics = BacktestMetrics.compute(
            nav, ret, bench_nav, bench_ret
        )
        
        # 拼装结果
        result = {
            "nav": nav,
            "returns": ret,
            "holdings": holdings,
            "benchmark_nav": bench_nav,
            "benchmark_returns": bench_ret,
            "metrics": metrics,
            "factor_panel": factor_panel,
            "signal": signal,
            "config": {
                "symbols": symbols,
                "factor_names": factor_names,
                "start_date": start_date,
                "end_date": end_date,
                "rebalance_freq": rebalance_freq,
                "max_positions": max_positions,
                "top_pct": top_pct,
                "direction": direction,
            }
        }
        
        logger.info("Backtest complete.")
        self._print_summary(metrics)
        
        return result

    def run_enhanced_factor_strategy(
        self,
        symbols: List[str],
        factor_names: List[str],
        start_date: str,
        end_date: str,
        rebalance_freq: str = "M",
        portfolio_method: str = "quantile",
        factor_weights: Optional[Dict[str, float]] = None,
        factor_directions: Optional[Dict[str, object]] = None,
        normalize: str = "rank_zscore",
        long_quantile: float = 0.2,
        short_quantile: float = 0.0,
        weighting: str = "equal",
        top_k: int = 50,
        n_drop: int = 5,
        max_positions: Optional[int] = None,
        max_abs_weight: Optional[float] = None,
        use_ic_weights: bool = False,
        forward_return_horizon: int = 5,
        ic_lookback: int = 60,
        ic_min_periods: int = 20,
        ic_lag: Optional[int] = None,
        time_series_overlay: Optional[Dict[str, Any]] = None,
        target_annual_vol: Optional[float] = None,
        vol_target_window: int = 20,
        max_leverage: float = 1.0,
        apply_filters: bool = True,
    ) -> Dict[str, Any]:
        """Run an enhanced factor strategy with weight-aware portfolio construction."""

        logger.info(f"Loading data for {len(symbols)} stocks...")
        ohlcv = self.adapter.load_ohlcv(symbols, start_date, end_date)
        close = ohlcv.get("close", pd.DataFrame())
        volume = ohlcv.get("volume", pd.DataFrame(index=close.index, columns=close.columns))
        open_price = ohlcv.get("open", close)
        high = ohlcv.get("high", close)
        low = ohlcv.get("low", close)

        if close.empty:
            raise ValueError("No data loaded. Check symbols and data directory.")

        logger.info("Computing named factor panels...")
        factor_panels = self._compute_factor_panels_by_name(
            close,
            volume,
            factor_names,
            open_price=open_price,
            high=high,
            low=low,
        )
        if not factor_panels:
            raise ValueError("No factor panels were computed. Check factor_names.")

        blend_spec = FactorBlendSpec(
            weights=factor_weights,
            directions=factor_directions,
            normalize=normalize,
        )
        ic_weights = None
        if use_ic_weights:
            if forward_return_horizon <= 0:
                raise ValueError("forward_return_horizon must be positive")
            forward_returns = close.pct_change(
                forward_return_horizon,
                fill_method=None,
            ).shift(-forward_return_horizon)
            score, ic_weights = ic_weighted_composite(
                factor_panels,
                forward_returns=forward_returns,
                blend_spec=blend_spec,
                lookback=ic_lookback,
                min_periods=ic_min_periods,
                ic_lag=ic_lag if ic_lag is not None else forward_return_horizon,
            )
        else:
            score = combine_enhanced_factor_panels(factor_panels, blend_spec)

        logger.info(f"Building target weights with method={portfolio_method}...")
        if portfolio_method == "quantile":
            target_weights = quantile_weights_from_score(
                score,
                QuantilePortfolioSpec(
                    long_quantile=long_quantile,
                    short_quantile=short_quantile,
                    weighting=weighting,
                    market_neutral=short_quantile > 0,
                    max_abs_weight=max_abs_weight,
                ),
            )
        elif portfolio_method == "alphalens":
            target_weights = alphalens_style_factor_weights(
                score,
                demeaned=True,
                equal_weight=weighting == "equal",
            )
        elif portfolio_method == "topk_dropout":
            target_weights = topk_dropout_weights(
                score,
                TopKDropoutSpec(
                    top_k=top_k,
                    n_drop=n_drop,
                    rebalance_freq=rebalance_freq,
                ),
            )
        else:
            raise ValueError("portfolio_method must be quantile, alphalens, or topk_dropout")

        if apply_filters:
            tradable = volume.reindex(index=target_weights.index, columns=target_weights.columns).fillna(0) > 0
            target_weights = target_weights.where(tradable, 0.0)

        if time_series_overlay is not None:
            target_weights = apply_time_series_overlay(
                target_weights,
                close,
                TimeSeriesOverlaySpec(**time_series_overlay),
            )

        leverage = None
        if target_annual_vol is not None:
            target_weights, leverage = volatility_target_weights(
                target_weights,
                close,
                target_annual_vol=target_annual_vol,
                vol_window=vol_target_window,
                max_leverage=max_leverage,
            )

        bench_nav, bench_ret = self.portfolio_factory.run_benchmark(close)
        nav, ret, executed_weights = self.portfolio_factory.run_weighted_portfolio_simple(
            target_weights,
            close,
            rebalance_freq=rebalance_freq,
            max_positions=max_positions,
            max_abs_weight=max_abs_weight,
        )

        metrics = BacktestMetrics.compute(nav, ret, bench_nav, bench_ret)
        result = {
            "nav": nav,
            "returns": ret,
            "weights": executed_weights,
            "target_weights": target_weights,
            "benchmark_nav": bench_nav,
            "benchmark_returns": bench_ret,
            "metrics": metrics,
            "factor_panels": factor_panels,
            "factor_panel": score,
            "score": score,
            "ic_weights": ic_weights,
            "leverage": leverage,
            "config": {
                "symbols": symbols,
                "factor_names": factor_names,
                "start_date": start_date,
                "end_date": end_date,
                "rebalance_freq": rebalance_freq,
                "portfolio_method": portfolio_method,
                "use_ic_weights": use_ic_weights,
                "long_quantile": long_quantile,
                "short_quantile": short_quantile,
                "weighting": weighting,
                "top_k": top_k,
                "n_drop": n_drop,
            },
        }

        logger.info("Enhanced factor backtest complete.")
        self._print_summary(metrics)
        return result

    def _compute_factor_panels_by_name(
        self,
        close: pd.DataFrame,
        volume: pd.DataFrame,
        factor_names: List[str],
        open_price: Optional[pd.DataFrame] = None,
        high: Optional[pd.DataFrame] = None,
        low: Optional[pd.DataFrame] = None,
        amount: Optional[pd.DataFrame] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Compute one standardized date x asset panel per factor name."""

        from src.factors.momentum import MOMENTUM_FACTORS
        from src.factors.reversal import REVERSAL_FACTORS
        from src.factors.volatility import VOLATILITY_FACTORS
        from src.factors.liquidity import LIQUIDITY_FACTORS
        from src.factors.quality import QUALITY_FACTORS
        from src.factors.valuation import VALUATION_FACTORS
        from src.factors.external_adapters import (
            EXTERNAL_PANEL_FACTOR_SPECS,
            compute_external_price_volume_factor_panels,
        )

        all_factors = {
            **MOMENTUM_FACTORS,
            **REVERSAL_FACTORS,
            **VOLATILITY_FACTORS,
            **LIQUIDITY_FACTORS,
            **QUALITY_FACTORS,
            **VALUATION_FACTORS,
        }

        external_factor_names = [name for name in factor_names if name in EXTERNAL_PANEL_FACTOR_SPECS]
        local_factor_names = [name for name in factor_names if name not in EXTERNAL_PANEL_FACTOR_SPECS]
        factor_panels: Dict[str, pd.DataFrame] = {}

        def pick(frame: Optional[pd.DataFrame], sym: str, fallback: pd.Series) -> pd.Series:
            if frame is not None and sym in frame.columns:
                return frame[sym]
            return fallback

        for fname in local_factor_names:
            if fname not in all_factors:
                logger.warning(f"Unknown factor: {fname}")
                continue

            symbol_values = []
            for sym in close.columns:
                close_s = close[sym]
                volume_s = pick(volume, sym, pd.Series(index=close.index, dtype=float))
                stock_data = pd.DataFrame({
                    "close": close_s,
                    "volume": volume_s,
                    "open": pick(open_price, sym, close_s),
                    "high": pick(high, sym, close_s),
                    "low": pick(low, sym, close_s),
                    "amount": pick(amount, sym, close_s * volume_s),
                })

                try:
                    f = all_factors[fname].compute(stock_data, postprocess=False)
                    symbol_values.append(pd.Series(f, name=sym))
                except Exception as e:
                    logger.debug(f"Factor {fname} failed for {sym}: {e}")

            if not symbol_values:
                continue

            factor_df = pd.concat(symbol_values, axis=1).reindex(
                index=close.index,
                columns=close.columns,
            )
            row_mean = factor_df.mean(axis=1)
            row_std = factor_df.std(axis=1).replace(0, np.nan)
            factor_panels[fname] = factor_df.sub(row_mean, axis=0).div(row_std, axis=0)

        if external_factor_names:
            external_panels = compute_external_price_volume_factor_panels(
                {
                    "open": open_price if open_price is not None else close,
                    "high": high if high is not None else close,
                    "low": low if low is not None else close,
                    "close": close,
                    "volume": volume,
                    "amount": amount if amount is not None else close * volume,
                },
                external_factor_names,
            )
            for fname, factor_df in external_panels.items():
                factor_df = factor_df.reindex(index=close.index, columns=close.columns)
                row_mean = factor_df.mean(axis=1)
                row_std = factor_df.std(axis=1).replace(0, np.nan)
                factor_panels[fname] = factor_df.sub(row_mean, axis=0).div(row_std, axis=0)

        return factor_panels
    
    def _compute_factor_panel(
        self,
        close: pd.DataFrame,
        volume: pd.DataFrame,
        factor_names: List[str],
        open_price: Optional[pd.DataFrame] = None,
        high: Optional[pd.DataFrame] = None,
        low: Optional[pd.DataFrame] = None,
        amount: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        计算因子面板
        
        Returns:
            综合因子宽表（各因子等权合成）
        """
        named_panels = self._compute_factor_panels_by_name(
            close,
            volume,
            factor_names,
            open_price=open_price,
            high=high,
            low=low,
            amount=amount,
        )
        if not named_panels:
            return pd.DataFrame(index=close.index, columns=close.columns)

        factor_panel = pd.concat(named_panels.values(), axis=0).groupby(level=0).mean()
        return factor_panel.reindex(index=close.index, columns=close.columns)

        from src.factors.momentum import MOMENTUM_FACTORS
        from src.factors.reversal import REVERSAL_FACTORS
        from src.factors.volatility import VOLATILITY_FACTORS
        from src.factors.liquidity import LIQUIDITY_FACTORS
        from src.factors.quality import QUALITY_FACTORS
        from src.factors.valuation import VALUATION_FACTORS
        from src.factors.external_adapters import (
            EXTERNAL_PANEL_FACTOR_SPECS,
            compute_external_price_volume_factor_panels,
        )
        
        ALL_FACTORS = {
            **MOMENTUM_FACTORS,
            **REVERSAL_FACTORS,
            **VOLATILITY_FACTORS,
            **LIQUIDITY_FACTORS,
            **QUALITY_FACTORS,
            **VALUATION_FACTORS,
        }
        
        external_factor_names = [name for name in factor_names if name in EXTERNAL_PANEL_FACTOR_SPECS]
        local_factor_names = [name for name in factor_names if name not in EXTERNAL_PANEL_FACTOR_SPECS]
        factor_panels = []

        def pick(frame: Optional[pd.DataFrame], sym: str, fallback: pd.Series) -> pd.Series:
            if frame is not None and sym in frame.columns:
                return frame[sym]
            return fallback

        for fname in local_factor_names:
            if fname not in ALL_FACTORS:
                logger.warning(f"Unknown factor: {fname}")
                continue

            symbol_values = []
            for sym in close.columns:
                close_s = close[sym]
                volume_s = pick(volume, sym, pd.Series(index=close.index, dtype=float))
                stock_data = pd.DataFrame({
                    "close": close_s,
                    "volume": volume_s,
                    "open": pick(open_price, sym, close_s),
                    "high": pick(high, sym, close_s),
                    "low": pick(low, sym, close_s),
                    "amount": pick(amount, sym, close_s * volume_s),
                })

                try:
                    f = ALL_FACTORS[fname].compute(stock_data, postprocess=False)
                    symbol_values.append(pd.Series(f, name=sym))
                except Exception as e:
                    logger.debug(f"Factor {fname} failed for {sym}: {e}")

            if not symbol_values:
                continue

            factor_df = pd.concat(symbol_values, axis=1).reindex(
                index=close.index,
                columns=close.columns,
            )
            row_mean = factor_df.mean(axis=1)
            row_std = factor_df.std(axis=1).replace(0, np.nan)
            factor_std = factor_df.sub(row_mean, axis=0).div(row_std, axis=0)
            factor_panels.append(factor_std)

        if external_factor_names:
            external_panels = compute_external_price_volume_factor_panels(
                {
                    "open": open_price if open_price is not None else close,
                    "high": high if high is not None else close,
                    "low": low if low is not None else close,
                    "close": close,
                    "volume": volume,
                    "amount": amount if amount is not None else close * volume,
                },
                external_factor_names,
            )
            for fname, factor_df in external_panels.items():
                factor_df = factor_df.reindex(index=close.index, columns=close.columns)
                row_mean = factor_df.mean(axis=1)
                row_std = factor_df.std(axis=1).replace(0, np.nan)
                factor_std = factor_df.sub(row_mean, axis=0).div(row_std, axis=0)
                factor_panels.append(factor_std)

        if not factor_panels:
            return pd.DataFrame(index=close.index, columns=close.columns)

        factor_panel = pd.concat(factor_panels, axis=0).groupby(level=0).mean()
        factor_panel = factor_panel.reindex(close.index)

        return factor_panel
        
        for sym in close.columns:
            # 构建单股数据
            stock_data = pd.DataFrame({
                "close": close[sym],
                "volume": volume[sym] if sym in volume.columns else close[sym],
                "open": close[sym],  # 无开高低时用收盘代替
                "high": close[sym],
                "low": close[sym],
                "amount": close[sym] * volume.get(sym, close[sym]),
            })
            
            factor_values = {}
            
            for fname in factor_names:
                if fname in ALL_FACTORS:
                    try:
                        f = ALL_FACTORS[fname].compute(stock_data, postprocess=False)
                        factor_values[fname] = f
                    except Exception as e:
                        logger.debug(f"Factor {fname} failed for {sym}: {e}")
                        
            if factor_values:
                # 等权合成
                factor_df = pd.DataFrame(factor_values)
                # 标准化后等权平均
                factor_std = factor_df.apply(lambda c: (c - c.mean()) / (c.std() + 1e-8))
                composite = factor_std.mean(axis=1)
                factor_panels.append(pd.Series(composite, name=sym))
        
        if not factor_panels:
            return pd.DataFrame(index=close.index, columns=close.columns)
            
        factor_panel = pd.concat(factor_panels, axis=1)
        factor_panel = factor_panel.reindex(close.index)
        
        return factor_panel
    
    def _print_summary(self, metrics: Dict[str, float]):
        """打印回测摘要"""
        print("\n" + "="*50)
        print("回测结果摘要")
        print("="*50)
        print(f"总收益率:      {metrics.get('total_return', 0)*100:.2f}%")
        print(f"年化收益率:    {metrics.get('annual_return', 0)*100:.2f}%")
        print(f"年化波动率:    {metrics.get('annual_vol', 0)*100:.2f}%")
        print(f"夏普比率:      {metrics.get('sharpe', 0):.3f}")
        print(f"最大回撤:      {metrics.get('max_drawdown_pct', 0):.2f}%")
        print(f"卡玛比率:      {metrics.get('calmar', 0):.3f}")
        print(f"胜率:          {metrics.get('win_rate', 0)*100:.2f}%")
        if "alpha" in metrics:
            print(f"Alpha:         {metrics.get('alpha', 0)*100:.2f}%")
            print(f"Beta:          {metrics.get('beta', 0):.3f}")
            print(f"信息比率:      {metrics.get('information_ratio', 0):.3f}")
        print("="*50 + "\n")
        
    def save_results(self, result: Dict, output_dir: str):
        """保存回测结果"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存净值
        result["nav"].to_csv(out / f"nav_{timestamp}.csv", header=True)
        result["benchmark_nav"].to_csv(out / f"benchmark_nav_{timestamp}.csv", header=True)
        
        # 保存指标
        import json
        metrics_clean = {k: float(v) if not pd.isna(v) else None for k, v in result["metrics"].items()}
        with open(out / f"metrics_{timestamp}.json", "w", encoding="utf-8") as f:
            json.dump(metrics_clean, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Results saved to {out}")
        return timestamp
