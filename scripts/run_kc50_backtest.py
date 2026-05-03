"""
部署和自动化脚本 - 科创板多因子回测
"""

import sys
import os
from pathlib import Path

# 设置工作目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from loguru import logger
from datetime import date, timedelta


def setup_environment():
    """环境检查和初始化"""
    logger.info("初始化 QuantLab 环境...")
    
    required_dirs = [
        "data/raw", "data/staging", "outputs/plots", "outputs/reports", "logs"
    ]
    for d in required_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
        
    logger.info("目录初始化完成")


def install_dependencies():
    """安装依赖包"""
    import subprocess
    packages = [
        "pandas", "numpy", "matplotlib", "seaborn",
        "loguru", "scipy", "scikit-learn", "pyarrow",
        "click", "pyyaml", "python-dotenv", "tqdm"
    ]
    
    logger.info("安装基础依赖...")
    for pkg in packages:
        subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], 
                       check=False)
    
    logger.info("依赖安装完成")


def run_kc50_backtest(
    data_dir: str = "E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407",
    start_date: str = "2020-01-01",
    end_date: str = None,
    output_dir: str = "outputs",
):
    """
    运行科创板多因子回测
    
    Args:
        data_dir: 数据目录
        start_date: 开始日期
        end_date: 结束日期
        output_dir: 输出目录
    """
    end_date = end_date or str(date.today())
    
    logger.info("="*60)
    logger.info("科创50 多因子量化策略回测")
    logger.info("="*60)
    
    from src.backtest.vbt_engine import VBTBacktestEngine
    from src.backtest.data_adapter import VBTDataAdapter
    from src.report.plotter import BacktestPlotter
    from src.report.html_report import HTMLReportGenerator
    
    # 加载科创板股票池
    adapter = VBTDataAdapter(data_dir, market="cn")
    kc_symbols = adapter.get_kc50_symbols()
    
    logger.info(f"科创板股票池: {len(kc_symbols)} 只")
    
    if len(kc_symbols) < 5:
        logger.warning("科创板股票数量不足，将使用沪深所有股票")
        kc_symbols = adapter.get_all_symbols()[:100]
    
    # 因子配置（多因子合成）
    factor_names = [
        "mom_20d",          # 20日动量
        "reversal_5d",      # 5日反转
        "realized_vol_20",  # 20日实现波动率
        "turnover_20",      # 20日换手率
        "earn_quality_60",  # 盈利质量
        "price_to_ma_60",   # 价格估值
    ]
    
    logger.info(f"使用因子: {factor_names}")
    
    # 运行回测
    engine = VBTBacktestEngine(data_dir, market="cn")
    
    result = engine.run_factor_strategy(
        symbols=kc_symbols[:50],  # 最多取50只
        factor_names=factor_names,
        start_date=start_date,
        end_date=end_date,
        rebalance_freq="M",       # 月度调仓
        max_positions=15,         # 最多15只
        top_pct=0.3,              # Top30%
        direction=1,              # 正向选股
        apply_filters=True,
    )
    
    # 生成图表
    logger.info("生成可视化图表...")
    plots_dir = f"{output_dir}/plots"
    plotter = BacktestPlotter(output_dir=plots_dir)
    plot_paths = plotter.generate_all(result, output_dir=plots_dir)
    
    # 生成HTML报告
    logger.info("生成HTML报告...")
    reporter = HTMLReportGenerator(output_dir=f"{output_dir}/reports")
    report_path = reporter.generate(
        result, 
        plot_paths,
        report_name="kc50_multifactor_report.html"
    )
    
    logger.info(f"报告已生成: {report_path}")
    
    # 保存结果
    timestamp = engine.save_results(result, output_dir)
    
    return result, report_path


if __name__ == "__main__":
    setup_environment()
    
    result, report_path = run_kc50_backtest(
        data_dir="E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407",
        start_date="2020-01-01",
        output_dir=str(PROJECT_ROOT / "outputs"),
    )
    
    metrics = result["metrics"]
    print(f"\n最终报告: {report_path}")
    print(f"年化收益: {metrics.get('annual_return',0)*100:.2f}%")
    print(f"夏普比率: {metrics.get('sharpe',0):.3f}")
    print(f"最大回撤: {abs(metrics.get('max_drawdown_pct',0)):.2f}%")
