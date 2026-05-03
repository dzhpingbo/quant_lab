"""
CLI 入口
"""

import click
import sys
from pathlib import Path


@click.group()
@click.version_option(version="0.1.0", prog_name="quantlab")
def cli():
    """QuantLab - 双引擎量化研究平台"""
    pass


@cli.command("backtest")
@click.option("--market", default="cn", help="市场 (cn/us)")
@click.option("--universe", default="kc50", help="股票池 (kc50/all/csi300)")
@click.option("--factors", "-f", multiple=True, help="因子名称（可多个）")
@click.option("--start", default="2020-01-01", help="开始日期")
@click.option("--end", default=None, help="结束日期（默认今天）")
@click.option("--rebalance", default="M", help="调仓频率 D/W/M")
@click.option("--max-pos", default=20, type=int, help="最大持仓数")
@click.option("--top-pct", default=0.2, type=float, help="选股比例")
@click.option("--data-dir", default="E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407", help="数据目录")
@click.option("--output-dir", default="outputs", help="输出目录")
def run_backtest(market, universe, factors, start, end, rebalance, max_pos, top_pct, data_dir, output_dir):
    """运行因子策略回测"""
    from src.backtest.vbt_engine import VBTBacktestEngine
    from src.backtest.data_adapter import VBTDataAdapter
    from src.report.plotter import BacktestPlotter
    from src.report.html_report import HTMLReportGenerator
    from datetime import date
    
    end = end or str(date.today())
    
    # 加载股票池
    adapter = VBTDataAdapter(data_dir, market)
    
    if universe == "kc50":
        symbols = adapter.get_kc50_symbols()[:60]  # 取前60只科创板
    else:
        symbols = adapter.get_all_symbols()[:100]
    
    click.echo(f"股票池: {len(symbols)} 只 ({universe})")
    
    # 默认因子
    if not factors:
        factors = ["mom_20d", "realized_vol_20", "turnover_20", "reversal_5d"]
    
    factor_names = list(factors)
    click.echo(f"因子: {factor_names}")
    
    # 运行回测
    engine = VBTBacktestEngine(data_dir, market)
    result = engine.run_factor_strategy(
        symbols=symbols,
        factor_names=factor_names,
        start_date=start,
        end_date=end,
        rebalance_freq=rebalance,
        max_positions=max_pos,
        top_pct=top_pct,
    )
    
    # 生成图表
    plotter = BacktestPlotter(output_dir=f"{output_dir}/plots")
    plot_paths = plotter.generate_all(result, output_dir=f"{output_dir}/plots")
    
    # 生成HTML报告
    reporter = HTMLReportGenerator(output_dir=f"{output_dir}/reports")
    report_path = reporter.generate(result, plot_paths)
    
    click.echo(f"\n✅ 报告生成：{report_path}")


@cli.command("list-factors")
@click.option("--category", default=None, help="因子类别")
def list_factors(category):
    """列出所有可用因子"""
    from src.factors.momentum import MOMENTUM_FACTORS
    from src.factors.reversal import REVERSAL_FACTORS
    from src.factors.volatility import VOLATILITY_FACTORS
    from src.factors.liquidity import LIQUIDITY_FACTORS
    from src.factors.quality import QUALITY_FACTORS
    from src.factors.valuation import VALUATION_FACTORS
    from src.factors.safety import SAFETY_FACTORS
    
    ALL = {
        "momentum": MOMENTUM_FACTORS,
        "reversal": REVERSAL_FACTORS,
        "volatility": VOLATILITY_FACTORS,
        "liquidity": LIQUIDITY_FACTORS,
        "quality": QUALITY_FACTORS,
        "valuation": VALUATION_FACTORS,
        "safety": SAFETY_FACTORS,
    }
    
    click.echo("\n可用因子列表:")
    click.echo("-" * 50)
    
    for cat, factors in ALL.items():
        if category and cat != category:
            continue
        click.echo(f"\n[{cat}]")
        for name, f in factors.items():
            click.echo(f"  {name:35s} - {f.meta.description}")


@cli.command("data-info")
@click.option("--data-dir", default="E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407", help="数据目录")
def data_info(data_dir):
    """显示数据目录信息"""
    from src.backtest.data_adapter import VBTDataAdapter
    adapter = VBTDataAdapter(data_dir)
    
    all_syms = adapter.get_all_symbols()
    kc_syms = adapter.get_kc50_symbols()
    
    click.echo(f"\n数据目录: {data_dir}")
    click.echo(f"总股票数: {len(all_syms)}")
    click.echo(f"科创板(688):  {len(kc_syms)}")
    click.echo(f"\n科创板代码示例:")
    for s in kc_syms[:10]:
        click.echo(f"  {s}")


if __name__ == "__main__":
    cli()
