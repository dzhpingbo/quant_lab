"""
VectorBT 数据适配器

将 CSV/Parquet 数据转换为 VectorBT 所需的格式
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Union, Tuple
from loguru import logger


class VBTDataAdapter:
    """VectorBT 数据适配器"""
    
    def __init__(
        self,
        data_dir: str,
        market: str = "cn",
        date_col: str = "date",
        symbol_suffix: str = ".SH",
    ):
        """
        Args:
            data_dir: 原始数据目录
            market: 市场 (cn/us)
            date_col: 日期列名
            symbol_suffix: 股票代码后缀 (.SH/.SZ)
        """
        self.data_dir = Path(data_dir)
        self.market = market
        self.date_col = date_col
        self.symbol_suffix = symbol_suffix
        
    def load_single_stock(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        加载单只股票数据
        
        Args:
            symbol: 股票代码（如 600000 或 600000.SH）
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            OHLCV DataFrame，date为索引
        """
        # 清理股票代码
        clean_symbol = symbol.replace(".SH", "").replace(".SZ", "").replace(".SS", "")
        
        # 尝试不同文件命名方式
        candidates = [
            self.data_dir / f"{clean_symbol}.SH.csv",
            self.data_dir / f"{clean_symbol}.SZ.csv",
            self.data_dir / f"{symbol}.csv",
            self.data_dir / f"{clean_symbol}.csv",
        ]
        
        file_path = None
        for cand in candidates:
            if cand.exists():
                file_path = cand
                break
                
        if file_path is None:
            logger.warning(f"File not found for symbol: {symbol}")
            return pd.DataFrame()
            
        df = pd.read_csv(file_path, parse_dates=[self.date_col])
        df = df.set_index(self.date_col).sort_index()
        
        # 列名统一小写
        df.columns = df.columns.str.lower()
        
        # 日期过滤
        if start_date:
            df = df[df.index >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df.index <= pd.to_datetime(end_date)]
            
        return df
    
    def load_multi_stock(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        col: str = "close",
    ) -> pd.DataFrame:
        """
        加载多只股票指定列，返回宽表
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            col: 目标列名
            
        Returns:
            宽表 DataFrame，行为日期，列为股票代码
        """
        dfs = {}
        for sym in symbols:
            df = self.load_single_stock(sym, start_date, end_date)
            if not df.empty and col in df.columns:
                dfs[sym] = df[col]
                
        if not dfs:
            return pd.DataFrame()
            
        wide = pd.DataFrame(dfs)
        wide.index.name = "date"
        return wide
    
    def load_ohlcv(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        加载多只股票的OHLCV数据，返回dict
        
        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            {列名: 宽表DataFrame}
        """
        cols = ["open", "high", "low", "close", "volume"]
        result = {}
        
        for col in cols:
            wide = self.load_multi_stock(symbols, start_date, end_date, col=col)
            if not wide.empty:
                result[col] = wide
                
        return result
    
    def get_kc50_symbols(self) -> List[str]:
        """
        获取科创板股票列表（688开头）
        """
        symbols = []
        for f in self.data_dir.glob("688*.csv"):
            sym = f.stem
            symbols.append(sym)
        return sorted(symbols)
    
    def get_all_symbols(self, prefix: Optional[str] = None) -> List[str]:
        """
        获取所有股票代码
        
        Args:
            prefix: 代码前缀过滤，如 "688"
            
        Returns:
            股票代码列表
        """
        symbols = []
        for f in self.data_dir.glob("*.csv"):
            sym = f.stem
            if prefix:
                if sym.startswith(prefix):
                    symbols.append(sym)
            else:
                symbols.append(sym)
        return sorted(symbols)
    
    def prepare_vbt_data(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        准备VectorBT格式数据：close和volume宽表
        
        Returns:
            (close_wide, volume_wide)
        """
        close = self.load_multi_stock(symbols, start_date, end_date, "close")
        volume = self.load_multi_stock(symbols, start_date, end_date, "volume")
        
        # 对齐索引
        if not close.empty and not volume.empty:
            common_idx = close.index.intersection(volume.index)
            close = close.loc[common_idx]
            volume = volume.loc[common_idx]
            
        # 向前填充
        close = close.ffill()
        volume = volume.ffill()
        
        return close, volume
