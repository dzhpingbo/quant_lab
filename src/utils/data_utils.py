"""
数据处理工具
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List, Union
from loguru import logger


def load_csv_data(
    file_path: Union[str, Path],
    date_col: str = "date",
    symbol_col: Optional[str] = None,
    parse_dates: bool = True
) -> pd.DataFrame:
    """
    加载CSV数据
    
    Args:
        file_path: CSV文件路径
        date_col: 日期列名
        symbol_col: 股票代码列名
        parse_dates: 是否解析日期
        
    Returns:
        DataFrame
    """
    df = pd.read_csv(file_path)
    
    if parse_dates and date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col])
        
    if symbol_col and symbol_col in df.columns:
        df[symbol_col] = df[symbol_col].astype(str)
        
    return df


def save_parquet(df: pd.DataFrame, file_path: Union[str, Path], compression: str = "zstd"):
    """
    保存为Parquet格式
    
    Args:
        df: DataFrame
        file_path: 输出路径
        compression: 压缩算法
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(file_path, compression=compression, engine="pyarrow")
    logger.info(f"Saved to {file_path}")


def load_parquet(file_path: Union[str, Path]) -> pd.DataFrame:
    """
    加载Parquet文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        DataFrame
    """
    return pd.read_parquet(file_path, engine="pyarrow")


def align_dates(
    df: pd.DataFrame,
    date_col: str = "date",
    freq: str = "D"
) -> pd.DataFrame:
    """
    对齐日期
    
    Args:
        df: DataFrame
        date_col: 日期列名
        freq: 频率
        
    Returns:
        对齐后的DataFrame
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    
    if freq == "D":
        # 只保留交易日
        df[date_col] = df[date_col].dt.normalize()
    elif freq == "W":
        df[date_col] = df[date_col].dt.to_period("W").dt.to_timestamp()
    elif freq == "M":
        df[date_col] = df[date_col].dt.to_period("M").dt.to_timestamp()
        
    return df


def detect_price_limits(
    df: pd.DataFrame,
    close_col: str = "close",
    pre_close_col: str = "pre_close",
    market: str = "cn"
) -> pd.DataFrame:
    """
    检测涨跌停
    
    Args:
        df: DataFrame
        close_col: 收盘价列
        pre_close_col: 昨收列
        market: 市场类型
        
    Returns:
        添加了涨跌停标记的DataFrame
    """
    if market != "cn":
        return df
        
    df = df.copy()
    df["return"] = (df[close_col] - df[pre_close_col]) / df[pre_close_col]
    
    # 科创板/创业板 20%
    df["is_kc"] = df.get("symbol", "").str.startswith("688") | df.get("symbol", "").str.startswith("300")
    
    df["up_limit"] = np.where(
        df["is_kc"],
        df["return"] >= 0.199,
        np.where(df.get("is_st", False), df["return"] >= 0.049, df["return"] >= 0.099)
    )
    
    df["down_limit"] = np.where(
        df["is_kc"],
        df["return"] <= -0.199,
        np.where(df.get("is_st", False), df["return"] <= -0.049, df["return"] <= -0.099)
    )
    
    return df


def fill_missing_dates(
    df: pd.DataFrame,
    date_col: str = "date",
    symbol_col: str = "symbol",
    fill_method: str = "ffill"
) -> pd.DataFrame:
    """
    填充缺失日期
    
    Args:
        df: DataFrame
        date_col: 日期列名
        symbol_col: 股票代码列名
        fill_method: 填充方法
        
    Returns:
        填充后的DataFrame
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    
    # 获取所有日期和股票
    all_dates = pd.date_range(df[date_col].min(), df[date_col].max(), freq="D")
    all_symbols = df[symbol_col].unique()
    
    # 创建完整的索引
    full_index = pd.MultiIndex.from_product(
        [all_dates, all_symbols],
        names=[date_col, symbol_col]
    )
    
    df_indexed = df.set_index([date_col, symbol_col])
    df_filled = df_indexed.reindex(full_index)
    
    # 前向填充
    if fill_method == "ffill":
        df_filled = df_filled.groupby(symbol_col).fillna(method="ffill")
        
    return df_filled.reset_index()
