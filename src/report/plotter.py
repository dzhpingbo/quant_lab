"""
回测绩效可视化
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # 非交互模式
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from pathlib import Path
from typing import Dict, Optional, List, Any


# 中文字体设置
plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.dpi": 150,
    "figure.facecolor": "white",
})

# 颜色主题
COLORS = {
    "strategy": "#E74C3C",   # 策略 - 红色
    "benchmark": "#3498DB",  # 基准 - 蓝色
    "positive": "#E74C3C",   # 正收益 - 红
    "negative": "#2ECC71",   # 负收益 - 绿
    "neutral": "#95A5A6",
    "drawdown": "#E74C3C",
}


class BacktestPlotter:
    """回测绩效可视化"""
    
    def __init__(self, output_dir: str = "outputs/plots"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def plot_nav(
        self,
        nav: pd.Series,
        benchmark_nav: Optional[pd.Series] = None,
        title: str = "策略净值曲线",
        save_path: Optional[str] = None,
    ) -> str:
        """
        净值曲线图
        
        Returns:
            保存路径
        """
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), 
                                  gridspec_kw={"height_ratios": [3, 1, 1]})
        fig.suptitle(title, fontsize=16, fontweight="bold", y=0.98)
        
        # ── 子图1：净值曲线 ──
        ax1 = axes[0]
        ax1.plot(nav.index, nav.values, color=COLORS["strategy"], 
                 linewidth=2, label="策略净值", zorder=3)
        
        if benchmark_nav is not None:
            bench_aligned = benchmark_nav.reindex(nav.index).ffill()
            ax1.plot(bench_aligned.index, bench_aligned.values, 
                     color=COLORS["benchmark"], linewidth=1.5, 
                     linestyle="--", label="基准净值", alpha=0.8)
        
        ax1.axhline(y=1.0, color="gray", linestyle=":", linewidth=1, alpha=0.7)
        ax1.fill_between(nav.index, 1.0, nav.values, 
                          where=(nav.values >= 1), alpha=0.1, 
                          color=COLORS["positive"])
        ax1.fill_between(nav.index, 1.0, nav.values, 
                          where=(nav.values < 1), alpha=0.1, 
                          color=COLORS["negative"])
        
        ax1.set_ylabel("净值", fontsize=11)
        ax1.legend(loc="upper left", fontsize=10)
        ax1.grid(True, alpha=0.3)
        ax1.yaxis.set_major_formatter(plt.FormatStrFormatter("%.2f"))
        
        # ── 子图2：回撤 ──
        ax2 = axes[1]
        drawdown = (nav - nav.cummax()) / nav.cummax() * 100
        ax2.fill_between(drawdown.index, 0, drawdown.values, 
                          color=COLORS["drawdown"], alpha=0.6)
        ax2.set_ylabel("回撤 (%)", fontsize=11)
        ax2.set_ylim(top=0)
        ax2.grid(True, alpha=0.3)
        
        # ── 子图3：日收益 ──
        ax3 = axes[2]
        daily_ret = nav.pct_change() * 100
        colors = [COLORS["positive"] if r >= 0 else COLORS["negative"] 
                  for r in daily_ret.values]
        ax3.bar(daily_ret.index, daily_ret.values, color=colors, alpha=0.7, width=1)
        ax3.axhline(0, color="gray", linewidth=0.8)
        ax3.set_ylabel("日收益率 (%)", fontsize=11)
        ax3.grid(True, alpha=0.3, axis="y")
        
        # 统一日期格式
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
            
        plt.tight_layout()
        
        path = save_path or str(self.output_dir / "nav_curve.png")
        plt.savefig(path, bbox_inches="tight", dpi=150)
        plt.close()
        
        return path
    
    def plot_metrics_bar(
        self,
        metrics: Dict[str, float],
        title: str = "回测指标",
        save_path: Optional[str] = None,
    ) -> str:
        """绩效指标条形图"""
        
        # 选取关键指标
        key_metrics = {
            "年化收益率(%)": metrics.get("annual_return", 0) * 100,
            "年化波动率(%)": metrics.get("annual_vol", 0) * 100,
            "夏普比率": metrics.get("sharpe", 0),
            "最大回撤(%)": abs(metrics.get("max_drawdown_pct", 0)),
            "卡玛比率": metrics.get("calmar", 0),
            "胜率(%)": metrics.get("win_rate", 0) * 100,
        }
        
        if "alpha" in metrics:
            key_metrics["Alpha(%)"] = metrics["alpha"] * 100
            key_metrics["信息比率"] = metrics.get("information_ratio", 0)
        
        labels = list(key_metrics.keys())
        values = list(key_metrics.values())
        colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in values]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.barh(labels, values, color=colors, alpha=0.8, edgecolor="white")
        
        # 数值标签
        for bar, val in zip(bars, values):
            ax.text(
                val + (max(values) - min(values)) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.2f}",
                va="center", fontsize=10
            )
        
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.axvline(0, color="gray", linewidth=0.8)
        ax.grid(True, alpha=0.3, axis="x")
        
        plt.tight_layout()
        path = save_path or str(self.output_dir / "metrics_bar.png")
        plt.savefig(path, bbox_inches="tight", dpi=150)
        plt.close()
        
        return path
    
    def plot_monthly_returns_heatmap(
        self,
        returns: pd.Series,
        title: str = "月度收益热力图",
        save_path: Optional[str] = None,
    ) -> str:
        """月度收益热力图"""
        
        returns = returns.copy()
        returns.index = pd.to_datetime(returns.index)
        
        monthly = returns.resample("M").apply(lambda x: (1 + x).prod() - 1) * 100
        
        # 重塑为年份×月份
        df = pd.DataFrame({
            "year": monthly.index.year,
            "month": monthly.index.month,
            "return": monthly.values
        })
        
        if df.empty:
            return ""
        
        pivot = df.pivot_table(index="year", columns="month", values="return")
        pivot.columns = ["Jan","Feb","Mar","Apr","May","Jun",
                          "Jul","Aug","Sep","Oct","Nov","Dec"][:len(pivot.columns)]
        
        fig, ax = plt.subplots(figsize=(14, max(4, len(pivot) * 0.6)))
        
        # 颜色：红涨绿跌（A股惯例）
        cmap = sns.diverging_palette(145, 10, as_cmap=True)  # green=neg, red=pos
        
        sns.heatmap(
            pivot, annot=True, fmt=".1f", cmap=cmap, center=0,
            linewidths=0.5, linecolor="white",
            cbar_kws={"label": "月收益率(%)"},
            ax=ax
        )
        
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("月份", fontsize=11)
        ax.set_ylabel("年份", fontsize=11)
        
        plt.tight_layout()
        path = save_path or str(self.output_dir / "monthly_heatmap.png")
        plt.savefig(path, bbox_inches="tight", dpi=150)
        plt.close()
        
        return path
    
    def plot_factor_ic(
        self,
        ic_series: pd.Series,
        title: str = "因子IC时序",
        save_path: Optional[str] = None,
    ) -> str:
        """因子IC时序图"""
        
        fig, axes = plt.subplots(2, 1, figsize=(14, 8))
        fig.suptitle(title, fontsize=14, fontweight="bold")
        
        # ── IC时序 ──
        ax1 = axes[0]
        ic_clean = ic_series.dropna()
        
        colors = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in ic_clean.values]
        ax1.bar(ic_clean.index, ic_clean.values, color=colors, alpha=0.6, width=5)
        
        ic_ma = ic_clean.rolling(20).mean()
        ax1.plot(ic_ma.index, ic_ma.values, color="navy", linewidth=2, label="20日均值")
        ax1.axhline(0, color="gray", linewidth=0.8)
        ax1.axhline(ic_clean.mean(), color="orange", linewidth=1.5, 
                    linestyle="--", label=f"均值={ic_clean.mean():.3f}")
        
        ax1.set_ylabel("IC值", fontsize=11)
        ax1.legend(loc="upper right", fontsize=9)
        ax1.grid(True, alpha=0.3, axis="y")
        
        # ── IC累计值 ──
        ax2 = axes[1]
        cumic = ic_clean.cumsum()
        ax2.plot(cumic.index, cumic.values, color=COLORS["strategy"], linewidth=2)
        ax2.fill_between(cumic.index, 0, cumic.values, alpha=0.15, color=COLORS["strategy"])
        ax2.axhline(0, color="gray", linewidth=0.8)
        ax2.set_ylabel("累计IC", fontsize=11)
        ax2.grid(True, alpha=0.3)
        
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
            
        plt.tight_layout()
        path = save_path or str(self.output_dir / "factor_ic.png")
        plt.savefig(path, bbox_inches="tight", dpi=150)
        plt.close()
        
        return path
    
    def plot_layered_returns(
        self,
        factor_panel: pd.DataFrame,
        close: pd.DataFrame,
        n_layers: int = 5,
        forward_period: int = 20,
        title: str = "因子分层收益",
        save_path: Optional[str] = None,
    ) -> str:
        """因子分层收益图"""
        
        forward_ret = close.pct_change(forward_period).shift(-forward_period)
        
        layer_rets = {}
        
        for date in factor_panel.index:
            if date not in forward_ret.index:
                continue
                
            f = factor_panel.loc[date].dropna()
            r = forward_ret.loc[date].reindex(f.index).dropna()
            
            common = f.index.intersection(r.index)
            if len(common) < n_layers:
                continue
                
            f = f.loc[common]
            r = r.loc[common]
            
            labels, bins = pd.qcut(f, n_layers, labels=False, retbins=True, duplicates="drop")
            
            for layer in range(n_layers):
                mask = labels == layer
                if mask.sum() > 0:
                    layer_ret = r[mask].mean()
                    if layer not in layer_rets:
                        layer_rets[layer] = []
                    layer_rets[layer].append(layer_ret)
        
        if not layer_rets:
            return ""
        
        avg_layer_rets = {k: np.mean(v) * 100 for k, v in layer_rets.items()}
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        layers = sorted(avg_layer_rets.keys())
        rets = [avg_layer_rets[l] for l in layers]
        colors = [COLORS["positive"] if r >= 0 else COLORS["negative"] for r in rets]
        
        bars = ax.bar(
            [f"Q{l+1}" for l in layers], rets, 
            color=colors, alpha=0.8, edgecolor="white"
        )
        
        for bar, ret in zip(bars, rets):
            ax.text(
                bar.get_x() + bar.get_width() / 2, 
                bar.get_height() + 0.01,
                f"{ret:.2f}%", ha="center", va="bottom", fontsize=10
            )
        
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.set_title(f"{title} (前向{forward_period}日)", fontsize=14, fontweight="bold")
        ax.set_xlabel("因子分层", fontsize=11)
        ax.set_ylabel(f"平均{forward_period}日收益率 (%)", fontsize=11)
        ax.grid(True, alpha=0.3, axis="y")
        
        plt.tight_layout()
        path = save_path or str(self.output_dir / "layered_returns.png")
        plt.savefig(path, bbox_inches="tight", dpi=150)
        plt.close()
        
        return path
    
    def plot_holdings(
        self,
        holdings: pd.DataFrame,
        title: str = "持仓股票数",
        save_path: Optional[str] = None,
    ) -> str:
        """持仓数量时序图"""
        
        n_holdings = holdings.sum(axis=1)
        
        fig, ax = plt.subplots(figsize=(14, 5))
        
        ax.fill_between(n_holdings.index, 0, n_holdings.values, alpha=0.5, color=COLORS["strategy"])
        ax.plot(n_holdings.index, n_holdings.values, color=COLORS["strategy"], linewidth=1.5)
        ax.axhline(n_holdings.mean(), color="orange", linestyle="--", 
                   linewidth=1.5, label=f"平均={n_holdings.mean():.1f}")
        
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_ylabel("持仓数", fontsize=11)
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        
        plt.tight_layout()
        path = save_path or str(self.output_dir / "holdings.png")
        plt.savefig(path, bbox_inches="tight", dpi=150)
        plt.close()
        
        return path
    
    def generate_all(
        self,
        result: Dict[str, Any],
        output_dir: Optional[str] = None,
    ) -> Dict[str, str]:
        """生成所有图表，返回路径字典"""
        
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        
        paths = {}
        
        paths["nav"] = self.plot_nav(
            result["nav"],
            result.get("benchmark_nav"),
            title="科创50策略净值",
        )
        
        paths["metrics"] = self.plot_metrics_bar(
            result["metrics"],
            title="策略绩效指标",
        )
        
        paths["monthly"] = self.plot_monthly_returns_heatmap(
            result["returns"],
            title="月度收益热力图",
        )
        
        if "holdings" in result:
            paths["holdings"] = self.plot_holdings(
                result["holdings"],
                title="持仓数量",
            )
        
        return paths
