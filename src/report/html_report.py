"""
HTML回测报告生成器
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import base64


class HTMLReportGenerator:
    """HTML格式回测报告生成器"""
    
    def __init__(self, output_dir: str = "outputs/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _img_to_base64(self, img_path: str) -> str:
        """将图片转为base64"""
        if not img_path or not Path(img_path).exists():
            return ""
        with open(img_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/png;base64,{data}"
    
    def generate(
        self,
        result: Dict[str, Any],
        plot_paths: Dict[str, str],
        report_name: str = None,
    ) -> str:
        """
        生成HTML报告
        
        Args:
            result: 回测结果字典
            plot_paths: 图表路径字典
            report_name: 报告文件名
            
        Returns:
            报告文件路径
        """
        config = result.get("config", {})
        metrics = result.get("metrics", {})
        
        # 内嵌图片
        img_nav = self._img_to_base64(plot_paths.get("nav", ""))
        img_metrics = self._img_to_base64(plot_paths.get("metrics", ""))
        img_monthly = self._img_to_base64(plot_paths.get("monthly", ""))
        img_holdings = self._img_to_base64(plot_paths.get("holdings", ""))
        
        # 指标表格
        metrics_rows = self._build_metrics_rows(metrics)
        
        # 配置表格
        config_rows = self._build_config_rows(config)
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>量化回测报告 - 科创50策略</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Microsoft YaHei", Arial, sans-serif; background: #f5f6fa; color: #333; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  
  /* 头部 */
  .header {{ background: linear-gradient(135deg, #c0392b 0%, #922b21 100%); color: white; 
             padding: 30px; border-radius: 12px; margin-bottom: 24px; text-align: center; }}
  .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
  .header .subtitle {{ opacity: 0.9; font-size: 14px; }}
  
  /* 卡片 */
  .card {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px;
           box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .card h2 {{ font-size: 18px; margin-bottom: 16px; padding-bottom: 8px; 
              border-bottom: 2px solid #e74c3c; color: #c0392b; }}
  
  /* 指标卡片 */
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap: 16px; }}
  .metric-item {{ background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center;
                  border-left: 4px solid #e74c3c; }}
  .metric-label {{ font-size: 13px; color: #666; margin-bottom: 8px; }}
  .metric-value {{ font-size: 24px; font-weight: bold; color: #c0392b; }}
  .metric-value.positive {{ color: #e74c3c; }}
  .metric-value.negative {{ color: #27ae60; }}
  .metric-value.neutral {{ color: #2980b9; }}
  
  /* 表格 */
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #c0392b; color: white; padding: 10px 14px; text-align: left; font-size: 13px; }}
  td {{ padding: 9px 14px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }}
  tr:hover td {{ background: #fef5f5; }}
  
  /* 图表 */
  .chart-img {{ width: 100%; border-radius: 8px; box-shadow: 0 1px 6px rgba(0,0,0,0.1); }}
  
  /* 底部 */
  .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
  
  .tag {{ display: inline-block; padding: 3px 10px; border-radius: 20px; 
          font-size: 12px; font-weight: bold; }}
  .tag-red {{ background: #fde8e6; color: #c0392b; }}
  .tag-blue {{ background: #e6f0fd; color: #2980b9; }}
  .tag-green {{ background: #e6fde8; color: #27ae60; }}
</style>
</head>
<body>
<div class="container">
  <!-- 头部 -->
  <div class="header">
    <h1>📊 量化回测报告</h1>
    <div class="subtitle">
      策略名称：科创50多因子策略 &nbsp;|&nbsp; 
      回测区间：{config.get("start_date","--")} ~ {config.get("end_date","--")} &nbsp;|&nbsp; 
      生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    </div>
  </div>
  
  <!-- 核心指标概览 -->
  <div class="card">
    <h2>核心绩效指标</h2>
    <div class="metrics-grid">
      <div class="metric-item">
        <div class="metric-label">总收益率</div>
        <div class="metric-value positive">{metrics.get("total_return",0)*100:.2f}%</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">年化收益率</div>
        <div class="metric-value positive">{metrics.get("annual_return",0)*100:.2f}%</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">年化波动率</div>
        <div class="metric-value neutral">{metrics.get("annual_vol",0)*100:.2f}%</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">夏普比率</div>
        <div class="metric-value {'positive' if metrics.get('sharpe',0)>1 else 'neutral'}">{metrics.get("sharpe",0):.3f}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">最大回撤</div>
        <div class="metric-value negative">-{abs(metrics.get("max_drawdown_pct",0)):.2f}%</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">卡玛比率</div>
        <div class="metric-value neutral">{metrics.get("calmar",0):.3f}</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">胜率</div>
        <div class="metric-value neutral">{metrics.get("win_rate",0)*100:.2f}%</div>
      </div>
      <div class="metric-item">
        <div class="metric-label">Sortino比率</div>
        <div class="metric-value neutral">{metrics.get("sortino",0):.3f}</div>
      </div>
    </div>
  </div>
  
  <!-- 净值曲线 -->
  {'<div class="card"><h2>净值曲线</h2>' + f'<img src="{img_nav}" class="chart-img" alt="净值曲线"/>' + '</div>' if img_nav else ''}
  
  <!-- 绩效指标图 -->
  {'<div class="card"><h2>指标可视化</h2>' + f'<img src="{img_metrics}" class="chart-img" alt="绩效指标"/>' + '</div>' if img_metrics else ''}
  
  <!-- 月度热力图 -->
  {'<div class="card"><h2>月度收益热力图</h2>' + f'<img src="{img_monthly}" class="chart-img" alt="月度收益"/>' + '</div>' if img_monthly else ''}
  
  <!-- 持仓分析 -->
  {'<div class="card"><h2>持仓分析</h2>' + f'<img src="{img_holdings}" class="chart-img" alt="持仓"/>' + '</div>' if img_holdings else ''}
  
  <!-- 详细指标表 -->
  <div class="card">
    <h2>详细绩效指标</h2>
    <table>
      <tr><th>指标</th><th>数值</th></tr>
      {metrics_rows}
    </table>
  </div>
  
  <!-- 策略配置 -->
  <div class="card">
    <h2>策略配置</h2>
    <table>
      <tr><th>参数</th><th>值</th></tr>
      {config_rows}
    </table>
  </div>
  
  <div class="footer">
    QuantLab 双引擎量化研究平台 | 仅供研究使用，不构成投资建议
  </div>
</div>
</body>
</html>"""
        
        report_name = report_name or f"backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_path = self.output_dir / report_name
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        return str(report_path)
    
    def _build_metrics_rows(self, metrics: Dict) -> str:
        label_map = {
            "total_return": "总收益率",
            "annual_return": "年化收益率",
            "annual_vol": "年化波动率",
            "sharpe": "夏普比率",
            "max_drawdown": "最大回撤",
            "max_drawdown_pct": "最大回撤(%)",
            "calmar": "卡玛比率",
            "win_rate": "胜率",
            "profit_loss_ratio": "盈亏比",
            "sortino": "Sortino比率",
            "max_losing_streak": "最大连亏天数",
            "drawdown_duration_max": "最长回撤周期(日)",
            "alpha": "超额收益Alpha(年化)",
            "beta": "Beta",
            "r_squared": "R²",
            "information_ratio": "信息比率",
            "excess_total_return": "超额总收益",
        }
        
        pct_keys = {"total_return", "annual_return", "annual_vol", "max_drawdown", "win_rate", "alpha", "excess_total_return"}
        
        rows = []
        for key, label in label_map.items():
            if key in metrics and not pd.isna(metrics[key]):
                val = metrics[key]
                if key in pct_keys:
                    display = f"{val*100:.2f}%"
                elif key in {"max_losing_streak", "drawdown_duration_max"}:
                    display = f"{int(val)} 天"
                else:
                    display = f"{val:.4f}"
                rows.append(f"<tr><td>{label}</td><td><strong>{display}</strong></td></tr>")
                
        return "\n".join(rows)
    
    def _build_config_rows(self, config: Dict) -> str:
        label_map = {
            "start_date": "回测开始日期",
            "end_date": "回测结束日期",
            "factor_names": "使用因子",
            "rebalance_freq": "调仓频率",
            "max_positions": "最大持仓数",
            "top_pct": "选股比例(Top%)",
            "direction": "因子方向",
        }
        
        freq_map = {"D": "每日", "W": "每周", "M": "每月"}
        
        rows = []
        for key, label in label_map.items():
            if key in config:
                val = config[key]
                if key == "factor_names":
                    display = ", ".join(val) if isinstance(val, list) else str(val)
                elif key == "rebalance_freq":
                    display = freq_map.get(str(val), str(val))
                elif key == "top_pct":
                    display = f"{float(val)*100:.0f}%"
                elif key == "direction":
                    display = "正向(高值做多)" if val == 1 else "反向(低值做多)"
                else:
                    display = str(val)
                rows.append(f"<tr><td>{label}</td><td>{display}</td></tr>")
                
        return "\n".join(rows)
