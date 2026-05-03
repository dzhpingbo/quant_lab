"""
因子基类和注册表
"""

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class FactorMeta:
    """因子元数据"""
    name: str
    category: str
    description: str
    version: str = "1.0.0"
    market: str = "cn"
    neutralize: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)


class BaseFactor(ABC):
    """因子基类"""
    
    def __init__(self, **params):
        self.params = params
        for key, value in params.items():
            setattr(self, key, value)
        self.meta = self._get_meta()
        
    @abstractmethod
    def _get_meta(self) -> FactorMeta:
        """返回因子元数据"""
        pass
    
    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        计算因子值
        
        Args:
            data: 输入数据，包含OHLCV等列
            
        Returns:
            因子值Series
        """
        pass
    
    def preprocess(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        数据预处理
        
        Args:
            data: 原始数据
            
        Returns:
            预处理后的数据
        """
        return data
    
    def postprocess(
        self,
        factor: pd.Series,
        winsorize: bool = True,
        standardize: bool = True,
        neutralize_fields: Optional[List[str]] = None,
        data: Optional[pd.DataFrame] = None
    ) -> pd.Series:
        """
        因子后处理
        
        Args:
            factor: 原始因子值
            winsorize: 是否缩尾
            standardize: 是否标准化
            neutralize_fields: 中性化字段
            data: 原始数据（用于中性化）
            
        Returns:
            处理后的因子值
        """
        from src.utils.factor_utils import winsorize as winsorize_fn
        from src.utils.factor_utils import standardize as standardize_fn
        from src.utils.factor_utils import neutralize as neutralize_fn
        
        result = factor.copy()
        
        # 缩尾
        if winsorize:
            result = winsorize_fn(result)
            
        # 标准化
        if standardize:
            result = standardize_fn(result, method="zscore")
            
        # 中性化
        if neutralize_fields and data is not None:
            industry = data.get("industry") if "industry" in neutralize_fields else None
            market_cap = data.get("market_cap") if "market_cap" in neutralize_fields else None
            result = neutralize_fn(result, industry=industry, market_cap=market_cap)
            
        return result
    
    def compute(self, data: pd.DataFrame, postprocess: bool = True, **kwargs) -> pd.Series:
        """
        完整的因子计算流程
        
        Args:
            data: 输入数据
            postprocess: 是否进行后处理
            **kwargs: 后处理参数
            
        Returns:
            因子值
        """
        # 预处理
        data = self.preprocess(data)
        
        # 计算因子
        factor = self.calculate(data)
        
        # 后处理
        if postprocess:
            factor = self.postprocess(factor, data=data, **kwargs)
            
        return factor


class FactorRegistry:
    """因子注册表"""
    
    def __init__(self):
        self._factors: Dict[str, BaseFactor] = {}
        self._categories: Dict[str, List[str]] = {}
        
    def register(self, factor: BaseFactor):
        """注册因子"""
        name = factor.meta.name
        category = factor.meta.category
        
        self._factors[name] = factor
        
        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)
            
        logger.info(f"Registered factor: {name} ({category})")
        
    def get(self, name: str) -> Optional[BaseFactor]:
        """获取因子"""
        return self._factors.get(name)
        
    def list_factors(self, category: Optional[str] = None) -> List[str]:
        """列出所有因子"""
        if category:
            return self._categories.get(category, [])
        return list(self._factors.keys())
        
    def list_categories(self) -> List[str]:
        """列出所有类别"""
        return list(self._categories.keys())
        
    def get_factors_by_category(self, category: str) -> Dict[str, BaseFactor]:
        """获取某类别的所有因子"""
        names = self._categories.get(category, [])
        return {name: self._factors[name] for name in names if name in self._factors}
        
    def compute_factor(
        self,
        name: str,
        data: pd.DataFrame,
        **kwargs
    ) -> pd.Series:
        """计算指定因子"""
        factor = self.get(name)
        if factor is None:
            raise ValueError(f"Factor not found: {name}")
        return factor.compute(data, **kwargs)
