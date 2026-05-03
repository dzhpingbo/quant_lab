"""
配置管理工具
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv


def load_dotenv_file():
    """加载环境变量"""
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)


def load_config(config_path: str) -> Dict[str, Any]:
    """
    加载YAML配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def get_config_path(config_name: str, config_type: str = "env") -> str:
    """
    获取配置文件路径
    
    Args:
        config_name: 配置名称
        config_type: 配置类型 (env/markets/universe/labels)
        
    Returns:
        配置文件完整路径
    """
    base_path = Path("configs")
    config_path = base_path / config_type / f"{config_name}.yaml"
    return str(config_path)


def merge_configs(base_config: Dict, override_config: Dict) -> Dict:
    """
    合并配置，override_config优先级更高
    
    Args:
        base_config: 基础配置
        override_config: 覆盖配置
        
    Returns:
        合并后的配置
    """
    result = base_config.copy()
    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def get_data_path(path_type: str = "raw") -> Path:
    """
    获取数据目录路径
    
    Args:
        path_type: 路径类型 (raw/staging/qlib_bin/vectorbt)
        
    Returns:
        数据目录Path对象
    """
    base_path = Path(os.getenv("QUANT_DATA_PATH", "data"))
    path_map = {
        "raw": base_path / "raw",
        "staging": base_path / "staging",
        "qlib_bin": base_path / "qlib_bin",
        "vectorbt": base_path / "vectorbt",
    }
    return path_map.get(path_type, base_path)
