"""
因子处理工具
"""

import pandas as pd
import numpy as np
from scipy import stats
from typing import Optional, List, Union
from sklearn.linear_model import LinearRegression


def winsorize(
    s: pd.Series,
    limits: tuple = (0.01, 0.99)
) -> pd.Series:
    """
    缩尾极值处理
    
    Args:
        s: 输入序列
        limits: 上下分位数限制
        
    Returns:
        处理后的序列
    """
    lower, upper = s.quantile(limits)
    return s.clip(lower, upper)


def standardize(
    s: pd.Series,
    method: str = "zscore"
) -> pd.Series:
    """
    标准化
    
    Args:
        s: 输入序列
        method: 标准化方法 (zscore/minmax/rank)
        
    Returns:
        标准化后的序列
    """
    if method == "zscore":
        mean = s.mean()
        std = s.std()
        return (s - mean) / std if std != 0 else s - mean
    elif method == "minmax":
        min_val = s.min()
        max_val = s.max()
        return (s - min_val) / (max_val - min_val) if max_val != min_val else s * 0
    elif method == "rank":
        return s.rank(pct=True)
    else:
        raise ValueError(f"Unknown method: {method}")


def neutralize(
    factor: pd.Series,
    industry: Optional[pd.Series] = None,
    market_cap: Optional[pd.Series] = None,
    log_cap: bool = True
) -> pd.Series:
    """
    中性化处理（行业+市值）
    
    Args:
        factor: 因子值
        industry: 行业分类
        market_cap: 市值
        log_cap: 是否对市值取对数
        
    Returns:
        中性化后的因子
    """
    df = pd.DataFrame({"factor": factor})
    
    if industry is not None:
        industry_dummies = pd.get_dummies(industry, prefix="ind")
        df = pd.concat([df, industry_dummies], axis=1)
        
    if market_cap is not None:
        cap = np.log(market_cap) if log_cap else market_cap
        df["market_cap"] = cap
        
    # 准备回归
    X_cols = [c for c in df.columns if c != "factor"]
    if not X_cols:
        return factor
        
    X = df[X_cols].fillna(0)
    y = df["factor"]
    
    # 线性回归取残差
    valid_idx = y.notna()
    if valid_idx.sum() < len(X_cols) + 1:
        return factor
        
    model = LinearRegression()
    model.fit(X[valid_idx], y[valid_idx])
    residual = y.copy()
    residual[valid_idx] = y[valid_idx] - model.predict(X[valid_idx])
    
    return residual


def orthogonalize(
    factor: pd.Series,
    other_factors: pd.DataFrame
) -> pd.Series:
    """
    正交化处理（去除与其他因子的相关性）
    
    Args:
        factor: 目标因子
        other_factors: 其他因子DataFrame
        
    Returns:
        正交化后的因子
    """
    df = other_factors.copy()
    df["factor"] = factor
    df = df.dropna()
    
    if len(df) < 2:
        return factor
        
    X = df.drop("factor", axis=1)
    y = df["factor"]
    
    model = LinearRegression()
    model.fit(X, y)
    residual = y - model.predict(X)
    
    result = factor.copy()
    result.loc[df.index] = residual
    return result


def rank(
    s: pd.Series,
    pct: bool = True
) -> pd.Series:
    """
    排名转换
    
    Args:
        s: 输入序列
        pct: 是否返回百分比排名
        
    Returns:
        排名序列
    """
    return s.rank(pct=pct)


def decay_linear(
    s: pd.Series,
    window: int = 10
) -> pd.Series:
    """
    线性衰减加权平均
    
    Args:
        s: 输入序列
        window: 窗口大小
        
    Returns:
        加权平均序列
    """
    weights = np.arange(1, window + 1)
    weights = weights / weights.sum()
    return s.rolling(window).apply(lambda x: np.dot(x, weights), raw=True)


def ts_rank(
    s: pd.Series,
    window: int = 20
) -> pd.Series:
    """
    时序排名
    
    Args:
        s: 输入序列
        window: 窗口大小
        
    Returns:
        时序排名序列
    """
    return s.rolling(window).rank(pct=True)


def ts_zscore(
    s: pd.Series,
    window: int = 20
) -> pd.Series:
    """
    时序Z-Score
    
    Args:
        s: 输入序列
        window: 窗口大小
        
    Returns:
        时序Z-Score序列
    """
    return (s - s.rolling(window).mean()) / s.rolling(window).std()


def ts_corr(
    x: pd.Series,
    y: pd.Series,
    window: int = 20
) -> pd.Series:
    """
    时序相关系数
    
    Args:
        x: 序列X
        y: 序列Y
        window: 窗口大小
        
    Returns:
        相关系数序列
    """
    return x.rolling(window).corr(y)


def ts_cov(
    x: pd.Series,
    y: pd.Series,
    window: int = 20
) -> pd.Series:
    """
    时序协方差
    
    Args:
        x: 序列X
        y: 序列Y
        window: 窗口大小
        
    Returns:
        协方差序列
    """
    return x.rolling(window).cov(y)
