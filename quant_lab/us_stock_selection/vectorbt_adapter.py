"""Single-asset strategy search backed by vectorbt when available."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.leveraged_etf_templates import leveraged_guardrail_signals
from quant_lab.us_stock_selection.strategy_templates import DEFAULT_TEMPLATES
from quant_lab.us_stock_selection.utils import (
    annualized_return,
    annualized_volatility,
    calmar_ratio,
    max_drawdown,
    nav_from_returns,
    sharpe_ratio,
    sortino_ratio,
)


@dataclass
class BacktestBundle:
    template_name: str
    params: dict[str, Any]
    nav: pd.Series
    returns: pd.Series
    benchmark_nav: pd.Series
    benchmark_returns: pd.Series
    position: pd.Series
    entries: pd.Series
    exits: pd.Series
    trades: pd.DataFrame
    metrics: dict[str, float]


class VectorbtStrategyAdapter:
    """Build signals, run vectorbt portfolios, and compute strategy metrics."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.vbt = None
        runtime_cfg = self.config.get("execution", {})
        self.enable_vectorbt_runtime = bool(runtime_cfg.get("enable_vectorbt_runtime", False))
        self.has_vectorbt = False if not self.enable_vectorbt_runtime else None

    def run_backtest(
        self,
        ticker: str,
        frame: pd.DataFrame,
        market_context: pd.DataFrame,
        template_name: str,
        params: dict[str, Any],
        asset_meta: dict[str, Any],
    ) -> BacktestBundle:
        if frame.empty:
            empty = pd.Series(dtype=float)
            return BacktestBundle(
                template_name=template_name,
                params=params,
                nav=empty,
                returns=empty,
                benchmark_nav=empty,
                benchmark_returns=empty,
                position=empty,
                entries=empty.astype(bool),
                exits=empty.astype(bool),
                trades=pd.DataFrame(),
                metrics={},
            )

        entries, exits, state = self._generate_signals(ticker, frame, market_context, template_name, params)
        fees, slippage = self._cost_profile(asset_meta)
        close = frame["adj_close"].fillna(frame["close"]).astype(float)
        benchmark_returns = close.pct_change(fill_method=None).fillna(0.0)
        benchmark_nav = nav_from_returns(benchmark_returns)

        if self._ensure_vectorbt():
            pf = self.vbt.Portfolio.from_signals(
                close,
                entries=entries.fillna(False),
                exits=exits.fillna(False),
                init_cash=float(self.config.get("portfolio", {}).get("initial_cash", 100_000.0)),
                fees=fees,
                slippage=slippage,
                direction="longonly",
                freq="1D",
            )
            portfolio_returns = pd.Series(pf.returns(), index=close.index).fillna(0.0)
            nav = pd.Series(pf.value(), index=close.index).div(float(self.config.get("portfolio", {}).get("initial_cash", 100_000.0)))
            position = pd.Series(pf.position_mask(), index=close.index).astype(float)
            trades = self._extract_trades_from_pf(pf)
        else:
            position = state["position"].astype(float)
            gross_turnover = position.diff().abs().fillna(position.abs())
            portfolio_returns = position.shift(1, fill_value=0.0) * benchmark_returns - gross_turnover * (fees + slippage)
            nav = nav_from_returns(portfolio_returns)
            trades = self._extract_trades_from_signals(close, entries, exits)

        metrics = self._compute_metrics(
            returns=portfolio_returns,
            nav=nav,
            benchmark_returns=benchmark_returns,
            benchmark_nav=benchmark_nav,
            trades=trades,
            position=position,
            template_name=template_name,
            params=params,
        )

        return BacktestBundle(
            template_name=template_name,
            params=params,
            nav=nav,
            returns=portfolio_returns,
            benchmark_nav=benchmark_nav,
            benchmark_returns=benchmark_returns,
            position=position,
            entries=entries,
            exits=exits,
            trades=trades,
            metrics=metrics,
        )

    def _ensure_vectorbt(self) -> bool:
        if not self.enable_vectorbt_runtime:
            return False
        if self.has_vectorbt is not None:
            return bool(self.has_vectorbt)
        try:
            import vectorbt as vbt  # type: ignore

            self.vbt = vbt
            self.has_vectorbt = True
        except Exception as exc:  # pragma: no cover - dependency varies by env
            self.vbt = None
            self.has_vectorbt = False
            self.logger.warning(f"vectorbt unavailable, falling back to custom signal execution: {exc}")
        return bool(self.has_vectorbt)

    def _generate_signals(
        self,
        ticker: str,
        frame: pd.DataFrame,
        market_context: pd.DataFrame,
        template_name: str,
        params: dict[str, Any],
    ) -> tuple[pd.Series, pd.Series, dict[str, pd.Series]]:
        close = frame["adj_close"].fillna(frame["close"]).astype(float)
        returns = close.pct_change(fill_method=None)
        atr = self._atr(frame, int(params.get("atr_window", 14) or 14))
        benchmark_filter = self._benchmark_filter(frame.index, market_context, params)
        vol_filter = self._volatility_filter(close, params)

        entries_raw = pd.Series(False, index=frame.index)
        exits_raw = pd.Series(False, index=frame.index)

        if template_name == "ma_trend":
            fast = int(params.get("ma_fast", 20))
            slow = int(params.get("ma_slow", 80))
            fast_ma = close.rolling(fast).mean()
            slow_ma = close.rolling(slow).mean()
            entries_raw = (close > fast_ma) & (fast_ma > slow_ma)
            exits_raw = (close < fast_ma) | (fast_ma < slow_ma)
        elif template_name == "breakout_atr":
            lookback = int(params.get("breakout_window", 55))
            exit_window = int(params.get("exit_window", 20))
            breakout = close > close.rolling(lookback).max().shift(1)
            channel_exit = close < close.rolling(exit_window).min().shift(1)
            entries_raw = breakout
            exits_raw = channel_exit
        elif template_name == "momentum_hold":
            lookback = int(params.get("momentum_window", 60))
            entry_threshold = float(params.get("entry_threshold", 0.05))
            exit_threshold = float(params.get("exit_threshold", 0.0))
            momentum = close.pct_change(lookback, fill_method=None)
            entries_raw = momentum > entry_threshold
            exits_raw = momentum < exit_threshold
        elif template_name == "rsi_trend":
            ma_window = int(params.get("ma_window", 50))
            rsi_entry = float(params.get("rsi_entry", 55))
            rsi_exit = float(params.get("rsi_exit", 45))
            rsi = self._rsi(close, 14)
            trend = close > close.rolling(ma_window).mean()
            entries_raw = (rsi > rsi_entry) & trend
            exits_raw = (rsi < rsi_exit) | (~trend)
        elif template_name == "combo_guardrail":
            fast = int(params.get("ma_fast", 20))
            slow = int(params.get("ma_slow", 100))
            vol_limit = float(params.get("max_realized_vol", 0.65))
            fast_ma = close.rolling(fast).mean()
            slow_ma = close.rolling(slow).mean()
            realized_vol = returns.rolling(20).std() * np.sqrt(252)
            trend = (close > fast_ma) & (fast_ma > slow_ma)
            entries_raw = trend & (realized_vol < vol_limit)
            exits_raw = (close < slow_ma) | (realized_vol > vol_limit)
        elif template_name == "aggressive_breakout":
            breakout_window = int(params.get("breakout_window", 60))
            ma_long = int(params.get("ma_long", 150))
            ma_short = int(params.get("ma_short", 20))
            volume_threshold = params.get("volume_z_threshold")
            max_realized_vol = params.get("max_realized_vol")
            long_ma = close.rolling(ma_long).mean()
            short_ma = close.rolling(ma_short).mean()
            breakout = close > close.rolling(breakout_window).max().shift(1)
            realized_vol = returns.rolling(20).std() * np.sqrt(252)
            volume = frame.get("volume", pd.Series(index=frame.index, dtype=float)).astype(float)
            volume_z = (volume - volume.rolling(20).mean()).div(volume.rolling(20).std().replace(0.0, np.nan))
            volume_ok = pd.Series(True, index=frame.index) if volume_threshold is None else volume_z > float(volume_threshold)
            vol_ok = pd.Series(True, index=frame.index) if max_realized_vol is None else realized_vol < float(max_realized_vol)
            entries_raw = (close > long_ma) & breakout & volume_ok & vol_ok
            exits_raw = (close < short_ma) | (~vol_ok)
        elif template_name == "trend_takeprofit":
            fast = int(params.get("ma_fast", 20))
            slow = int(params.get("ma_slow", 150))
            fast_ma = close.rolling(fast).mean()
            slow_ma = close.rolling(slow).mean()
            entries_raw = (fast_ma > slow_ma) & (close > slow_ma)
            exits_raw = (close < fast_ma) | (fast_ma < slow_ma)
            allow = benchmark_filter & vol_filter
            entries_raw = entries_raw & allow
            exits_raw = exits_raw | (~allow)
            entries, exits, position = self._stateful_takeprofit_signals(
                close=close,
                entries_raw=entries_raw,
                exits_raw=exits_raw,
                atr=atr,
                atr_stop_mult=float(params.get("atr_stop_mult", 3.0)),
                take_profit=float(params.get("take_profit", 0.35)),
                protective_line=fast_ma,
            )
            return entries, exits, {"position": position}
        elif template_name == "momentum_pullback_reentry":
            momentum_window = int(params.get("momentum_window", 120))
            momentum_threshold = float(params.get("momentum_threshold", 0.20))
            pullback_min = float(params.get("pullback_min", 0.08))
            pullback_max = float(params.get("pullback_max", 0.25))
            rsi_max = params.get("rsi_max")
            long_ma = close.rolling(150).mean()
            recent_high = close.rolling(60).max()
            pullback = close.div(recent_high).sub(1.0).abs()
            momentum = close.pct_change(momentum_window, fill_method=None)
            rsi = self._rsi(close, int(params.get("rsi_window", 14)))
            rsi_ok = pd.Series(True, index=frame.index) if rsi_max is None else rsi < float(rsi_max)
            entries_raw = (
                (momentum > momentum_threshold)
                & (close > long_ma)
                & (pullback >= pullback_min)
                & (pullback <= pullback_max)
                & rsi_ok
            )
            exits_raw = (close < long_ma) | (pullback > pullback_max)
        elif template_name == "leveraged_etf_guardrail":
            entries, exits, position = leveraged_guardrail_signals(
                ticker=ticker,
                frame=frame,
                market_context=market_context,
                params=params,
                atr=atr,
            )
            return entries, exits, {"position": position}
        elif template_name == "ml_signal":
            prediction_series = params.get("prediction_series")
            if prediction_series is None:
                raise ValueError("ml_signal requires prediction_series in params.")
            prediction = pd.Series(prediction_series).reindex(frame.index).astype(float)
            entry_threshold = float(params.get("prediction_entry_threshold", prediction.quantile(0.65)))
            exit_threshold = float(params.get("prediction_exit_threshold", prediction.quantile(0.35)))
            fast = int(params.get("ma_fast", 20))
            slow = int(params.get("ma_slow", 100))
            fast_ma = close.rolling(fast).mean()
            slow_ma = close.rolling(slow).mean()
            realized_vol = returns.rolling(20).std() * np.sqrt(252)
            trend = (close > fast_ma) & (fast_ma > slow_ma)
            entries_raw = (prediction > entry_threshold) & trend
            exits_raw = (prediction < exit_threshold) | (close < slow_ma) | (realized_vol > float(params.get("max_realized_vol", 0.65)))
        else:
            raise KeyError(f"Unknown strategy template '{template_name}'")

        allow = benchmark_filter & vol_filter
        entries_raw = entries_raw & allow
        exits_raw = exits_raw | (~allow)

        use_stop = DEFAULT_TEMPLATES[template_name].uses_atr_stop
        stop_mult = float(params.get("atr_stop_mult", 3.0))
        entries, exits, position = self._stateful_signals(
            close=close,
            entries_raw=entries_raw,
            exits_raw=exits_raw,
            atr=atr,
            atr_stop_mult=stop_mult if use_stop else None,
        )
        return entries, exits, {"position": position}

    def _compute_metrics(
        self,
        returns: pd.Series,
        nav: pd.Series,
        benchmark_returns: pd.Series,
        benchmark_nav: pd.Series,
        trades: pd.DataFrame,
        position: pd.Series,
        template_name: str,
        params: dict[str, Any],
    ) -> dict[str, float]:
        clean_returns = returns.fillna(0.0)
        clean_nav = nav.ffill().fillna(1.0)
        trade_returns = trades["return"] if not trades.empty and "return" in trades.columns else pd.Series(dtype=float)
        winning_returns = trade_returns[trade_returns > 0]
        losing_returns = trade_returns[trade_returns < 0]

        benchmark_cagr = annualized_return(benchmark_returns)
        benchmark_dd = max_drawdown(benchmark_nav)
        benchmark_calmar = benchmark_cagr / abs(benchmark_dd) if benchmark_dd != 0 else 0.0
        gross_turnover = position.diff().abs().fillna(position.abs())

        metrics = {
            "total_return": float(clean_nav.iloc[-1] - 1.0) if not clean_nav.empty else 0.0,
            "annualized_return": annualized_return(clean_returns),
            "cagr": annualized_return(clean_returns),
            "volatility": annualized_volatility(clean_returns),
            "max_drawdown": max_drawdown(clean_nav),
            "calmar": calmar_ratio(clean_returns),
            "sharpe": sharpe_ratio(clean_returns),
            "sortino": sortino_ratio(clean_returns),
            "win_rate": float((trade_returns > 0).mean()) if not trade_returns.empty else 0.0,
            "profit_factor": float(winning_returns.sum() / abs(losing_returns.sum())) if not losing_returns.empty and losing_returns.sum() != 0 else float("inf"),
            "number_of_trades": int(len(trades)),
            "average_trade_return": float(trade_returns.mean()) if not trade_returns.empty else 0.0,
            "best_trade": float(trade_returns.max()) if not trade_returns.empty else 0.0,
            "worst_trade": float(trade_returns.min()) if not trade_returns.empty else 0.0,
            "exposure": float(position.mean()) if not position.empty else 0.0,
            "turnover_proxy": float(gross_turnover.sum() / max(len(gross_turnover), 1)),
            "benchmark_cagr": benchmark_cagr,
            "benchmark_max_drawdown": benchmark_dd,
            "benchmark_calmar": benchmark_calmar,
            "excess_calmar": float(calmar_ratio(clean_returns) - benchmark_calmar),
            "beats_buy_and_hold": float(annualized_return(clean_returns) > benchmark_cagr),
            "strategy_complexity": float(DEFAULT_TEMPLATES[template_name].complexity),
        }
        metrics["profit_factor"] = float(metrics["profit_factor"]) if np.isfinite(metrics["profit_factor"]) else 0.0
        metrics["template_name"] = template_name  # type: ignore[assignment]
        metrics["param_count"] = float(len(params))
        return metrics

    @staticmethod
    def _benchmark_filter(index: pd.Index, market_context: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        if market_context.empty:
            return pd.Series(True, index=index)
        source = params.get("market_filter_source", params.get("market_filter", "QQQ_trend"))
        if source is None or str(source).lower() == "none":
            return pd.Series(True, index=index)
        threshold = float(params.get("market_filter_threshold", 0.0))
        if source not in market_context.columns:
            return pd.Series(True, index=index)
        return market_context[source].reindex(index).ffill().fillna(0.0) > threshold

    @staticmethod
    def _volatility_filter(close: pd.Series, params: dict[str, Any]) -> pd.Series:
        if "max_realized_vol" not in params or params.get("max_realized_vol") is None:
            return pd.Series(True, index=close.index)
        realized = close.pct_change(fill_method=None).rolling(20).std() * np.sqrt(252)
        return realized < float(params["max_realized_vol"])

    @staticmethod
    def _atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
        prev_close = frame["close"].shift(1)
        tr = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - prev_close).abs(),
                (frame["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.rolling(window).mean()

    @staticmethod
    def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean()
        rs = gain.div(loss.replace(0, np.nan))
        return 100.0 - 100.0 / (1.0 + rs)

    @staticmethod
    def _stateful_signals(
        close: pd.Series,
        entries_raw: pd.Series,
        exits_raw: pd.Series,
        atr: pd.Series,
        atr_stop_mult: float | None,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        entries = pd.Series(False, index=close.index)
        exits = pd.Series(False, index=close.index)
        position = pd.Series(0.0, index=close.index)
        in_pos = False
        peak = np.nan

        for idx, date in enumerate(close.index):
            px = float(close.loc[date]) if not pd.isna(close.loc[date]) else np.nan
            atr_value = float(atr.loc[date]) if date in atr.index and not pd.isna(atr.loc[date]) else np.nan
            raw_entry = bool(entries_raw.loc[date]) if date in entries_raw.index else False
            raw_exit = bool(exits_raw.loc[date]) if date in exits_raw.index else False

            if not in_pos and raw_entry:
                entries.loc[date] = True
                in_pos = True
                peak = px
            elif in_pos:
                peak = np.nanmax([peak, px]) if not np.isnan(peak) else px
                stop_hit = False
                if atr_stop_mult is not None and not np.isnan(atr_value) and not np.isnan(peak):
                    stop_hit = px < peak - atr_stop_mult * atr_value
                if raw_exit or stop_hit:
                    exits.loc[date] = True
                    in_pos = False
                    peak = np.nan

            position.loc[date] = 1.0 if in_pos else 0.0
        return entries, exits, position

    @staticmethod
    def _stateful_takeprofit_signals(
        close: pd.Series,
        entries_raw: pd.Series,
        exits_raw: pd.Series,
        atr: pd.Series,
        atr_stop_mult: float,
        take_profit: float,
        protective_line: pd.Series,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Simplified take-profit logic: after target is touched, ratchet stop to breakeven/protective line."""
        entries = pd.Series(False, index=close.index)
        exits = pd.Series(False, index=close.index)
        position = pd.Series(0.0, index=close.index)
        in_pos = False
        entry_px = np.nan
        peak = np.nan
        ratchet_on = False

        for date in close.index:
            px = float(close.loc[date]) if not pd.isna(close.loc[date]) else np.nan
            atr_value = float(atr.loc[date]) if date in atr.index and not pd.isna(atr.loc[date]) else np.nan
            raw_entry = bool(entries_raw.loc[date]) if date in entries_raw.index else False
            raw_exit = bool(exits_raw.loc[date]) if date in exits_raw.index else False

            if not in_pos and raw_entry:
                entries.loc[date] = True
                in_pos = True
                entry_px = px
                peak = px
                ratchet_on = False
            elif in_pos:
                peak = np.nanmax([peak, px]) if not np.isnan(peak) else px
                if not np.isnan(entry_px) and px >= entry_px * (1.0 + take_profit):
                    ratchet_on = True
                stop_level = peak - atr_stop_mult * atr_value if not np.isnan(atr_value) and not np.isnan(peak) else np.nan
                if ratchet_on:
                    line_value = float(protective_line.loc[date]) if date in protective_line.index and not pd.isna(protective_line.loc[date]) else np.nan
                    ratchet_level = np.nanmax([entry_px, line_value]) if not np.isnan(entry_px) else line_value
                    stop_level = np.nanmax([stop_level, ratchet_level]) if not np.isnan(stop_level) else ratchet_level
                stop_hit = not np.isnan(stop_level) and px < stop_level
                if raw_exit or stop_hit:
                    exits.loc[date] = True
                    in_pos = False
                    entry_px = np.nan
                    peak = np.nan
                    ratchet_on = False

            position.loc[date] = 1.0 if in_pos else 0.0
        return entries, exits, position

    @staticmethod
    def _extract_trades_from_signals(close: pd.Series, entries: pd.Series, exits: pd.Series) -> pd.DataFrame:
        open_idx = None
        trades: list[dict[str, Any]] = []
        for date in close.index:
            if bool(entries.loc[date]) and open_idx is None:
                open_idx = date
            if bool(exits.loc[date]) and open_idx is not None:
                entry_price = float(close.loc[open_idx])
                exit_price = float(close.loc[date])
                trades.append(
                    {
                        "entry_date": open_idx,
                        "exit_date": date,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "return": exit_price / entry_price - 1.0 if entry_price else 0.0,
                    }
                )
                open_idx = None
        return pd.DataFrame(trades)

    @staticmethod
    def _extract_trades_from_pf(pf) -> pd.DataFrame:  # pragma: no cover - depends on vectorbt runtime
        try:
            records = pf.trades.records.copy()
        except Exception:
            try:
                records = pf.trades.records_readable.copy()
            except Exception:
                return pd.DataFrame()
        if records.empty:
            return pd.DataFrame()
        columns = {col.lower().replace(" ", "_"): col for col in records.columns}
        renamed = records.rename(columns={orig: new for new, orig in columns.items()})
        if "return" not in renamed.columns and "return_[%]" in renamed.columns:
            renamed["return"] = renamed["return_[%]"] / 100.0
        return renamed

    def _cost_profile(self, asset_meta: dict[str, Any]) -> tuple[float, float]:
        cost_cfg = self.config.get("costs", {})
        if asset_meta.get("is_leveraged", False):
            return (
                float(cost_cfg.get("leveraged_etf_fee_bps", 5.0)) / 10_000.0,
                float(cost_cfg.get("leveraged_etf_slippage_bps", 7.0)) / 10_000.0,
            )
        if asset_meta.get("asset_type") == "etf":
            return (
                float(cost_cfg.get("etf_fee_bps", 3.0)) / 10_000.0,
                float(cost_cfg.get("etf_slippage_bps", 3.0)) / 10_000.0,
            )
        return (
            float(cost_cfg.get("stock_fee_bps", 5.0)) / 10_000.0,
            float(cost_cfg.get("stock_slippage_bps", 5.0)) / 10_000.0,
        )
