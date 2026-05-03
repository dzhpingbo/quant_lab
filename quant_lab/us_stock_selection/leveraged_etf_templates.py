"""Specialized signal helpers for leveraged ETF guardrail templates."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


UNDERLYING_BY_TICKER = {
    "TQQQ": "QQQ",
    "QLD": "QQQ",
    "UPRO": "SPY",
    "SSO": "SPY",
}


def infer_underlying(ticker: str, params: dict[str, Any]) -> str:
    raw = params.get("underlying")
    if raw:
        return str(raw)
    return UNDERLYING_BY_TICKER.get(str(ticker).upper(), "QQQ")


def leveraged_guardrail_signals(
    ticker: str,
    frame: pd.DataFrame,
    market_context: pd.DataFrame,
    params: dict[str, Any],
    atr: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Generate long/cash signals for leveraged ETFs with underlying-index risk controls."""
    close = frame["adj_close"].fillna(frame["close"]).astype(float)
    underlying = infer_underlying(ticker, params)
    ma_window = int(params.get("underlying_ma", 200))
    vol_window = int(params.get("vol_window", 20))
    max_underlying_vol = float(params.get("max_underlying_vol", 0.30))
    max_asset_vol = float(params.get("max_asset_vol", 0.65))
    drawdown_cut = float(params.get("drawdown_cut", 0.25))
    cooldown_days = int(params.get("cooldown_days", 10))
    atr_stop_mult = float(params.get("atr_stop_mult", 4.0))

    if market_context.empty:
        underlying_close = close
    else:
        underlying_close = market_context.get(f"{underlying}_close", pd.Series(index=close.index, dtype=float)).reindex(close.index).ffill()
        if underlying_close.isna().all():
            underlying_close = close

    underlying_ma = underlying_close.rolling(ma_window).mean()
    underlying_vol = underlying_close.pct_change(fill_method=None).rolling(vol_window).std() * np.sqrt(252)
    asset_vol = close.pct_change(fill_method=None).rolling(vol_window).std() * np.sqrt(252)
    allowed = (underlying_close > underlying_ma) & (underlying_vol < max_underlying_vol) & (asset_vol < max_asset_vol)
    allowed = allowed.fillna(False)

    entries = pd.Series(False, index=close.index)
    exits = pd.Series(False, index=close.index)
    position = pd.Series(0.0, index=close.index)
    in_pos = False
    peak = np.nan
    cooldown_until = -1

    for i, date in enumerate(close.index):
        px = float(close.loc[date]) if not pd.isna(close.loc[date]) else np.nan
        atr_value = float(atr.loc[date]) if date in atr.index and not pd.isna(atr.loc[date]) else np.nan
        can_enter = bool(allowed.loc[date]) and i >= cooldown_until

        if not in_pos and can_enter:
            entries.loc[date] = True
            in_pos = True
            peak = px
        elif in_pos:
            peak = np.nanmax([peak, px]) if not np.isnan(peak) else px
            dd_from_trade_peak = px / peak - 1.0 if peak and not np.isnan(peak) else 0.0
            atr_stop_hit = False
            if not np.isnan(atr_value) and not np.isnan(peak):
                atr_stop_hit = px < peak - atr_stop_mult * atr_value
            risk_exit = (not bool(allowed.loc[date])) or dd_from_trade_peak <= -drawdown_cut or atr_stop_hit
            if risk_exit:
                exits.loc[date] = True
                in_pos = False
                peak = np.nan
                cooldown_until = i + cooldown_days

        position.loc[date] = 1.0 if in_pos else 0.0

    return entries, exits, position
