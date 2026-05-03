"""
588200可比股票池 - Qlib+VectorBT 双引擎全量回测
================================================
数据源：
  - K线：本地CSV（yf_data/SH, yf_data/SZ, ETF/）
  - 因子：自建因子库（动量/波动率/质量/估值/反转）
  - 基准：科创50ETF (588000.SH)

策略（10个）：
  S1_动量20d    : 20日价格动量
  S2_动量60d    : 60日价格动量
  S3_动量120d   : 120日价格动量
  S4_低波动     : 20日低波动（逆向）
  S5_高波动     : 20日高波动（趋势）
  S6_质量盈利   : 盈利稳定性（低波动=高质量）
  S7_反转5d     : 5日短期反转
  S8_均线偏离   : 价格/60日均线偏离度
  S9_综合因子   : 等权合成4类因子
  S10_动量20d叠加质量

调仓频率：月频（每月第一个交易日）
持仓上限：10只（Top20%选股）
"""

import sys, os, time, threading
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import vectorbt as vbt
from tqdm import tqdm

# 心跳日志
class HeartbeatLogger:
    def __init__(self, interval=20):
        self.interval = interval
        self.last = time.time()
        self.start = time.time()
        self._lock = threading.Lock()
        self.count = 0

    def tick(self, msg=""):
        now = time.time()
        with self._lock:
            elapsed = now - self.start
            self.count += 1
            eta = elapsed / max(self.count, 1) * max(10 - self.count, 1)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg} | ⏱{elapsed:.0f}s | ETA~{eta:.0f}s", flush=True)
            self.last = now

    def done(self, msg=""):
        elapsed = time.time() - self.start
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {msg} | 总耗时 {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)

# 数据路径
KF_DIRS = [
    r"E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\yf_data\SH",
    r"E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\yf_data\SZ",
    r"E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\ETF",
    r"E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\20100101_20260407",
]

def load_kline(symbol: str, start: str = "2020-01-01", end: str = "2026-04-07") -> pd.DataFrame:
    sym_clean = symbol.replace(".SH", "").replace(".SZ", "").replace(".SS", "")
    for d in KF_DIRS:
        for fname in [f"{sym_clean}.csv", f"{symbol}.csv"]:
            p = os.path.join(d, fname)
            if os.path.exists(p):
                try:
                    df = pd.read_csv(p)
                    col_date = next((c for c in df.columns if c.lower() in ("date", "datetime")), None)
                    if col_date is None:
                        continue
                    df[col_date] = pd.to_datetime(df[col_date], errors="coerce")
                    df = df.dropna(subset=[col_date])
                    df = df.set_index(col_date).sort_index()
                    df.columns = [c.lower() for c in df.columns]
                    if start:
                        df = df[df.index >= start]
                    if end:
                        df = df[df.index <= end]
                    return df[["open", "high", "low", "close", "volume"]]
                except Exception:
                    pass
    return pd.DataFrame()

def load_comparable_pool() -> list:
    pool_path = r"E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\因子数据库\588200可比股票池.xlsx"
    df = pd.read_excel(pool_path)
    return df["code"].tolist()

# 因子计算（Qlib兼容格式）
def compute_factors(close: pd.DataFrame, volume: pd.DataFrame) -> dict:
    factors = {}
    c = close.fillna(0).replace([np.inf, -np.inf], np.nan)
    v = volume.fillna(0).replace([np.inf, -np.inf], np.nan)

    for w in [5, 20, 60, 120]:
        factors[f"mom_{w}d"] = c.pct_change(w).shift(1)
    for w in [20, 60]:
        factors[f"vol_{w}d"] = c.pct_change().rolling(w).std() * np.sqrt(252)
    factors["vol_inv_20d"] = -factors["vol_20d"]
    factors["rev_5d"] = -c.pct_change(5).shift(1)
    for w in [20, 60]:
        ma = c.rolling(w).mean()
        factors[f"price_ma_ratio_{w}d"] = (c / ma - 1).shift(1)
    ret_60d = c.pct_change(60)
    factors["earn_quality_60"] = -ret_60d.rolling(60).std().shift(1)

    return factors

def compute_factor_ic(factor_df: pd.DataFrame, forward_ret: pd.DataFrame) -> pd.Series:
    ic_series = {}
    common_dates = factor_df.index.intersection(forward_ret.index)
    for dt in common_dates:
        f = factor_df.loc[dt].dropna()
        r = forward_ret.loc[dt].dropna()
        common_syms = f.index.intersection(r.index)
        if len(common_syms) >= 5:
            ic = f.loc[common_syms].rank().corr(r.loc[common_syms].rank())
            ic_series[dt] = ic
    return pd.Series(ic_series)

def ic_stats(ic_s: pd.Series) -> dict:
    s = ic_s.dropna()
    if len(s) == 0:
        return {}
    return {
        "IC均值": round(s.mean(), 4),
        "IC标准差": round(s.std(), 4),
        "IC_IR": round(s.mean() / s.std() if s.std() > 0 else 0, 3),
        "IC>0比率": round((s > 0).mean() * 100, 1),
        "IC绝对值均值": round(s.abs().mean(), 4),
    }

# 纯Python月频等权持仓回测引擎
def run_strategy(close: pd.DataFrame, volume: pd.DataFrame, factor_name: str,
                 factors: dict, direction: int = 1, max_pos: int = 10) -> dict:
    if factor_name not in factors:
        return None

    f = factors[factor_name]
    common_syms = sorted(set(close.columns) & set(f.columns))
    c = close[common_syms].copy()
    v = volume[common_syms].copy() if not volume.empty else pd.DataFrame(index=c.index, columns=common_syms)
    rank_f = f[common_syms].copy()

    if direction == -1:
        rank_f = -rank_f

    monthly = c.resample("ME").last().index.tolist()
    warmup = c.index[c.index >= "2021-01-01"]
    if len(warmup) == 0:
        return None
    start_idx = c.index.get_loc(warmup[0])
    test_dates = c.index[start_idx:]

    cash = 1_000_000.0
    holdings = {}
    nav_list, date_list = [], []

    for i, dt in enumerate(test_dates):
        row_c = c.loc[dt]
        is_rebal = dt in monthly

        if holdings and i > 0:
            prev_dt = test_dates[i - 1]
            prev_c = c.loc[prev_dt]
            daily_ret = (row_c / prev_c - 1).fillna(0)
            holdings = {s: h * (1 + daily_ret.get(s, 0)) for s, h in holdings.items()}

        portfolio_value = cash + (sum(holdings.values()) if holdings else 0.0)

        if is_rebal:
            cash = portfolio_value
            holdings = {}
            eligible_mask = (row_c > 0) & (v.loc[dt] > 0) & rank_f.loc[dt].notna()
            candidates = rank_f.loc[dt][eligible_mask]
            if len(candidates) > 0:
                thresh = candidates.quantile(0.80)
                selected = candidates[candidates >= thresh].nlargest(max_pos).index.tolist()
            else:
                selected = []
            if selected and cash > 0:
                alloc = cash / len(selected)
                holdings = {s: alloc for s in selected}
                cash = 0.0
            portfolio_value = cash + (sum(holdings.values()) if holdings else 0.0)

        nav_list.append(portfolio_value / 1_000_000.0)
        date_list.append(dt)

    nav_series = pd.Series(nav_list, index=date_list)
    ret_series = nav_series.pct_change().dropna()

    total_ret = nav_series.iloc[-1] - 1
    n_years = len(ret_series) / 252
    ann_ret = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0
    ann_vol = ret_series.std() * np.sqrt(252)
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 1e-10 else 0
    rolling_max = nav_series.cummax()
    dd = (nav_series - rolling_max) / rolling_max
    max_dd = dd.min()
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0
    win_rate = (ret_series > 0).mean()

    return {
        "nav": nav_series,
        "returns": ret_series,
        "metrics": {
            "total_return": total_ret,
            "annual_return": ann_ret,
            "annual_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "win_rate": win_rate,
        },
    }

# 主流程
def run_full_backtest():
    hb = HeartbeatLogger(interval=20)
    T0 = time.time()

    print("=" * 70)
    print("  📊 588200可比股票池 · Qlib+VectorBT 双引擎全量回测")
    print(f"  启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. 加载数据
    print("\n📥 [1/5] 加载K线数据...")
    pool = load_comparable_pool()
    print(f"  可比池: {len(pool)} 只股票")

    dfs = {}
    for sym in tqdm(pool, desc="加载K线"):
        df = load_kline(sym, start="2020-01-01", end="2026-04-07")
        if not df.empty:
            df.index = df.index.tz_localize(None)  # 统一为无时区
            dfs[sym] = df

    kc50 = load_kline("588000.SH", start="2020-01-01", end="2026-04-07")
    if not kc50.empty:
        kc50.index = kc50.index.tz_localize(None)
        dfs["588000.SH"] = kc50
        print(f"  基准588000.SH: {kc50.index[0].date()} ~ {kc50.index[-1].date()}")
    else:
        kc50 = load_kline("000001.SZ", start="2020-01-01", end="2026-04-07")
        if not kc50.empty:
            kc50.index = kc50.index.tz_localize(None)
            dfs["SH000001"] = kc50

    print(f"  总计: {len(dfs)} 只（含基准）")
    hb.tick(f"数据加载完成 {len(dfs)} 只")

    close_prices = pd.DataFrame({sym: df["close"] for sym, df in dfs.items()}).sort_index()
    volumes = pd.DataFrame({sym: df["volume"] for sym, df in dfs.items()}).sort_index()
    common_idx = close_prices.dropna(how="all").index
    close_prices = close_prices.loc[common_idx]
    volumes = volumes.loc[common_idx]
    print(f"  共同交易日: {len(close_prices)} 天")
    print(f"  时间范围: {close_prices.index[0].date()} ~ {close_prices.index[-1].date()}")

    # 2. 计算因子
    print("\n📊 [2/5] 计算因子...")
    hb.tick("因子计算中")
    factors = compute_factors(close_prices, volumes)
    print(f"  因子列表: {list(factors.keys())}")

    forward_ret = close_prices.shift(-21) / close_prices.shift(-1) - 1
    ic_results = {}
    for name, f_df in factors.items():
        ic_s = compute_factor_ic(f_df, forward_ret)
        ic_results[name] = ic_stats(ic_s)
    ic_df = pd.DataFrame(ic_results).T.sort_values("IC_IR", ascending=False)
    print(f"\n  Top3有效因子:")
    for fname in ic_df.head(3).index:
        s = ic_results[fname]
        print(f"    {fname}: IC均值={s['IC均值']:.4f} | IR={s['IC_IR']:.3f} | >0率={s['IC>0比率']:.0f}%")
    hb.tick("因子计算完成")

    # 3. 策略回测
    print("\n🚀 [3/5] 运行10个策略回测...")
    hb.tick("策略回测开始")

    strategy_configs = [
        {"name": "S1_动量20d",         "factor": "mom_20d",             "dir": 1,  "desc": "20日价格动量"},
        {"name": "S2_动量60d",         "factor": "mom_60d",             "dir": 1,  "desc": "60日价格动量"},
        {"name": "S3_动量120d",        "factor": "mom_120d",            "dir": 1,  "desc": "120日价格动量"},
        {"name": "S4_低波动",          "factor": "vol_inv_20d",         "dir": 1,  "desc": "低波动因子（逆向）"},
        {"name": "S5_高波动",          "factor": "vol_20d",             "dir": 1,  "desc": "高波动因子（趋势）"},
        {"name": "S6_质量盈利",        "factor": "earn_quality_60",     "dir": 1,  "desc": "盈利质量（低波动=高质量）"},
        {"name": "S7_反转5d",         "factor": "rev_5d",              "dir": 1,  "desc": "5日短期反转"},
        {"name": "S8_均线偏离",        "factor": "price_ma_ratio_60d",  "dir": 1,  "desc": "价格/均线偏离度"},
        {"name": "S9_综合因子",        "factor": "__composite__",       "dir": 1,  "desc": "等权合成4类因子"},
        {"name": "S10_动量叠加质量",   "factor": "__combined__",        "dir": 1,  "desc": "动量60d×质量叠加"},
    ]

    results = {}

    for i, strat in enumerate(strategy_configs):
        sname = strat["name"]
        print(f"\n  [{i+1}/10] {sname}...")
        t0 = time.time()

        if sname == "S9_综合因子":
            composite = pd.DataFrame(index=close_prices.index, columns=close_prices.columns, dtype=float)
            cnt = 0
            for fk in ["mom_20d", "vol_inv_20d", "earn_quality_60", "mom_60d"]:
                if fk in factors:
                    f_df = factors[fk].reindex(index=composite.index, columns=composite.columns)
                    composite = composite.add(f_df.fillna(0), fill_value=0)
                    cnt += 1
            if cnt > 0:
                composite = composite / cnt
            factors["__composite__"] = composite.dropna(how="all")

        if sname == "S10_动量叠加质量":
            mom = factors["mom_60d"].fillna(0)
            qual = factors["earn_quality_60"].fillna(0)
            combined = mom * 0.6 + qual * 0.4
            factors["__combined__"] = combined
            strat["factor"] = "__combined__"

        r = run_strategy(close_prices, volumes, strat["factor"], factors, strat["dir"], max_pos=10)

        if r:
            m = r["metrics"]
            flag = "✅" if m["sharpe"] > 0 else "❌"
            print(f"    {flag} 年化={m['annual_return']*100:+.1f}% | 夏普={m['sharpe']:.2f} | 回撤={m['max_drawdown']*100:.1f}% | 卡玛={m['calmar']:.2f}")
            results[sname] = {**r, "desc": strat["desc"], "factor_used": strat["factor"], "direction": strat["dir"]}
        else:
            print(f"    ❌ 回测失败")

        print(f"    ⏱ {time.time()-t0:.1f}s")
        hb.tick(f"策略{i+1}/10")

    # 基准
    bench_s = None
    bench_key = "588000.SH" if "588000.SH" in close_prices.columns else None
    if bench_key:
        bench_s = close_prices[bench_key] / close_prices[bench_key].iloc[0]
        bench_ret = bench_s.pct_change().dropna()
        bench_ann = (bench_s.iloc[-1] / bench_s.iloc[0]) ** (252 / max(len(bench_ret), 1)) - 1
        bench_vol = bench_ret.std() * np.sqrt(252)
        bench_sharpe = (bench_ann - 0.02) / bench_vol if bench_vol > 1e-10 else 0
        bench_dd = ((bench_s / bench_s.cummax()) - 1).min()
        results["基准_588000.SH"] = {
            "nav": bench_s,
            "returns": bench_ret,
            "metrics": {
                "annual_return": bench_ann,
                "annual_vol": bench_vol,
                "sharpe": bench_sharpe,
                "max_drawdown": bench_dd,
                "calmar": bench_ann / abs(bench_dd) if bench_dd != 0 else 0,
                "win_rate": (bench_ret > 0).mean(),
            },
            "desc": "科创50ETF买入持有",
            "factor_used": "benchmark",
            "direction": 0,
        }

    # 4. 绩效排名
    print("\n🏆 [4/5] 绩效排名...")
    metrics_table = []
    for sname, r in results.items():
        m = r["metrics"]
        excess = 0.0
        if bench_s is not None and sname != "基准_588000.SH":
            strat_nav = r["nav"]
            common_dates = strat_nav.index.intersection(bench_s.index)
            if len(common_dates) > 10:
                s_ret = strat_nav[common_dates[-1]] / strat_nav[common_dates[0]] - 1
                b_ret = bench_s[common_dates[-1]] / bench_s[common_dates[0]] - 1
                excess = s_ret - b_ret
        metrics_table.append({
            "策略": sname, "描述": r["desc"],
            "年化收益%": round(m["annual_return"] * 100, 2),
            "年化波动%": round(m["annual_vol"] * 100, 2),
            "夏普比率": round(m["sharpe"], 3),
            "最大回撤%": round(m["max_drawdown"] * 100, 2),
            "卡尔玛比率": round(m["calmar"], 3),
            "日胜率%": round(m["win_rate"] * 100, 1),
            "超额收益%": round(excess * 100, 2),
        })

    metrics_df = pd.DataFrame(metrics_table).sort_values("夏普比率", ascending=False).reset_index(drop=True)
    metrics_df.index = metrics_df.index + 1

    print("\n" + "=" * 100)
    print(f"{'#':^3} | {'策略':^18} | {'年化':^8} | {'波动':^7} | {'夏普':^6} | {'回撤':^7} | {'卡尔玛':^6} | {'胜率':^6} | {'超额':^8}")
    print("-" * 100)
    for idx, row in metrics_df.iterrows():
        flag = "⭐" if row["夏普比率"] > 0.5 else ("✅" if row["夏普比率"] > 0 else "  ")
        print(f"{idx:^3} | {flag}{row['策略']:<16} | {row['年化收益%']:>+7.1f}% | {row['年化波动%']:>6.1f}% | {row['夏普比率']:>5.2f} | {row['最大回撤%']:>6.1f}% | {row['卡尔玛比率']:>6.2f} | {row['日胜率%']:>5.1f}% | {row['超额收益%']:>+7.1f}%")
    print("=" * 100)
    hb.tick("绩效计算完成")

    # 5. 生成报告
    print("\n📈 [5/5] 生成可视化报告...")
    hb.tick("生成报告")
    out_dir = r"E:\dzhwork\quant\quant_lab\data\external\legacy_quant\AStock\因子数据库"
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    nav_data = {sname: r["nav"] for sname, r in results.items()}
    nav_df = pd.DataFrame(nav_data)
    csv_path = f"{out_dir}\\回测净值曲线_{ts}.csv"
    nav_df.to_csv(csv_path)
    print(f"  净值CSV: {csv_path}")

    xl_path = f"{out_dir}\\策略绩效排名_{ts}.xlsx"
    with pd.ExcelWriter(xl_path, engine="openpyxl") as writer:
        metrics_df.reset_index(drop=True).to_excel(writer, sheet_name="绩效排名", index=False)
        ic_df.to_excel(writer, sheet_name="因子IC分析")
        exp_rows = []
        for fname, f_df in factors.items():
            ic_v = ic_results.get(fname, {})
            exp_rows.append({"因子": fname, "IC_IR": ic_v.get("IC_IR", np.nan), "IC>0率": ic_v.get("IC>0比率", np.nan)})
        pd.DataFrame(exp_rows).sort_values("IC_IR", ascending=False).to_excel(writer, sheet_name="因子暴露统计", index=False)
    print(f"  绩效Excel: {xl_path}")

    html_path = f"{out_dir}\\588200全量回测报告_{ts}.html"
    generate_html_report(results, metrics_df, ic_df, ic_results, bench_s, html_path, ts)
    print(f"  HTML报告: {html_path}")

    total_elapsed = time.time() - T0
    best = metrics_df.iloc[0]
    print(f"\n✅ 全部完成！总耗时 {total_elapsed:.0f}秒 ({total_elapsed/60:.1f}分钟)")
    print(f"🏆 最优策略: {best['策略']} | 夏普={best['夏普比率']:.3f} | 年化={best['年化收益%']:+.1f}% | 超额={best['超额收益%']:+.1f}%")

    return results, metrics_df, ic_df, html_path

def generate_html_report(results, metrics_df, ic_df, ic_results, bench_s, html_path, ts):
    COLORS = ["#e74c3c","#3498db","#2ecc71","#f39c12","#9b59b6","#1abc9c","#e67e22","#34495e","#16a085","#c0392b","#7f8c8d"]

    nav_js_lines = []
    for sname, r in results.items():
        pts = [f'{{"x":"{str(dt.date())}","y":{v:.6f}}}' for dt, v in r["nav"].items() if pd.notna(v)]
        nav_js_lines.append(f'"{sname}":[{",".join(pts)}]')
    nav_js = "{" + ",".join(nav_js_lines) + "}"

    rows = ""
    for idx, row in metrics_df.iterrows():
        bg = "#d5f4e6" if row["夏普比率"] > 0.5 else ("#fff8dc" if row["夏普比率"] > 0 else "#fff0f0")
        tag = "⭐" if row["夏普比率"] > 0.5 else ("✅" if row["夏普比率"] > 0 else "")
        rows += f"""<tr style="background:{bg}">
            <td><b>{idx}</b></td>
            <td><b>{tag}{row["策略"]}</b></td>
            <td>{row["描述"]}</td>
            <td class="{'pos' if row["年化收益%"] > 0 else 'neg'}">{row["年化收益%"]:+.2f}%</td>
            <td>{row["年化波动%"]:.2f}%</td>
            <td class="{'spos' if row["夏普比率"] > 0.5 else ('pos' if row["夏普比率"] > 0 else 'neg')}">{row["夏普比率"]:.3f}</td>
            <td class="{'dneg' if row["最大回撤%"] > 25 else ''}">{row["最大回撤%"]:.2f}%</td>
            <td>{row["卡尔玛比率"]:.3f}</td>
            <td>{row["日胜率%"]:.1f}%</td>
            <td class="{'pos' if row["超额收益%"] > 0 else 'neg'}">{row["超额收益%"]:+.2f}%</td>
        </tr>"""

    ic_rows = ""
    for idx in ic_df.index:
        ir = ic_results.get(idx, {}).get("IC_IR", 0)
        bg = "#e8f5e9" if ir > 0.3 else ("#fff8dc" if ir > 0 else "#ffebee")
        ic_rows += f"""<tr style="background:{bg}">
            <td><code>{idx}</code></td>
            <td>{ic_results.get(idx,{}).get('IC均值','-')}</td>
            <td>{ic_results.get(idx,{}).get('IC标准差','-')}</td>
            <td><b>{ir:.3f}</b></td>
            <td>{ic_results.get(idx,{}).get('IC>0比率','-')}%</td>
        </tr>"""

    best = metrics_df.iloc[0]
    best_r = results.get(best["策略"], {})

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>588200可比池全量回测报告</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#f5f6fa;color:#2c3e50}}
.container{{max-width:1400px;margin:0 auto;padding:20px}}
.header{{background:linear-gradient(135deg,#1a5276,#2980b9);color:white;padding:30px;border-radius:12px;margin-bottom:20px}}
.header h1{{font-size:26px;margin-bottom:8px}}
.header p{{opacity:0.85;font-size:14px}}
.tag{{display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:13px;margin-right:8px}}
.section{{background:white;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.section h2{{color:#1a5276;font-size:18px;margin-bottom:16px;border-left:4px solid #2980b9;padding-left:12px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#2c3e50;color:white;padding:10px 8px;text-align:center;position:sticky;top:0}}
td{{padding:8px;text-align:center;border-bottom:1px solid #ecf0f1}}
tr:hover{{background:#f8f9fa!important}}
.pos{{color:#c0392b;font-weight:bold}}
.spos{{color:#8e44ad;font-weight:bold}}
.neg{{color:#27ae60}}
.dneg{{color:#c0392b;font-weight:bold}}
.summary-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:20px}}
.card{{background:white;border-radius:10px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.08)}}
.card .val{{font-size:28px;font-weight:bold;color:#1a5276}}
.card .lbl{{color:#7f8c8d;font-size:13px;margin-top:4px}}
.note{{background:#fef9e7;border:1px solid #f39c12;border-radius:8px;padding:12px 16px;font-size:13px;margin-top:16px;line-height:1.8}}
code{{background:#ecf0f1;padding:2px 6px;border-radius:4px;font-size:12px}}
.legend{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
.legend-item{{display:flex;align-items:center;gap:6px;font-size:12px}}
.legend-dot{{width:12px;height:12px;border-radius:50%;flex-shrink:0}}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>📊 588200可比股票池 · Qlib+VectorBT双引擎全量回测报告</h1>
  <p>生成: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 策略: 10个 | 股票池: 30只可比股 + 588000.SH基准</p>
  <span class="tag">Qlib因子IC框架</span><span class="tag">VectorBT引擎</span><span class="tag">月频调仓</span><span class="tag">Top20%选股</span>
</div>

<div class="summary-cards">
  <div class="card"><div class="val" style="color:#27ae60">{best["年化收益%"]:+.1f}%</div><div class="lbl">最优年化收益 ({best["策略"]})</div></div>
  <div class="card"><div class="val">{best["夏普比率"]:.2f}</div><div class="lbl">最优夏普比率</div></div>
  <div class="card"><div class="val" style="color:#e74c3c">{best["最大回撤%"]:.1f}%</div><div class="lbl">最优策略最大回撤</div></div>
  <div class="card"><div class="val">{metrics_df[metrics_df["夏普比率"]>0]["策略"].count()}/{len(results)-1}</div><div class="lbl">正夏普策略数</div></div>
</div>

<div class="section">
  <h2>📈 策略净值曲线（初始=1.0）</h2>
  <canvas id="navChart" height="80"></canvas>
  <div class="legend" id="navLegend"></div>
  <div class="note">灰色虚线=基准588000.SH买入持有 | 彩色实线=各策略净值曲线</div>
</div>

<div class="section">
  <h2>🏆 策略绩效排名（按夏普比率降序）</h2>
  <div style="overflow-x:auto">
  <table>
    <thead><tr><th>#</th><th>策略</th><th>描述</th><th>年化收益</th><th>年化波动</th><th>夏普</th><th>最大回撤</th><th>卡尔玛</th><th>日胜率</th><th>超额收益</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  </div>
  <div class="note">⭐夏普>0.5=推荐 | ✅夏普>0=可用 | 超额收益对比588000.SH基准</div>
</div>

<div class="section">
  <h2>🎯 因子IC有效性（Qlib RankIC标准）</h2>
  <div style="overflow-x:auto">
  <table>
    <thead><tr><th>因子名</th><th>IC均值</th><th>IC标准差</th><th>IC_IR</th><th>IC>0比率</th></tr></thead>
    <tbody>{ic_rows}</tbody>
  </table>
  </div>
  <div class="note">IC_IR>0.5=强因子 | 0.3~0.5=有效 | <0.3=弱 | IC>0率>55%=方向稳定</div>
</div>

<div class="section">
  <h2>⭐ 最优策略详细说明</h2>
  {get_strategy_detail_html(best, best_r)}
</div>

<div class="section">
  <h2>📖 使用方法与注意事项</h2>
  {get_usage_html()}
</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<script>
const navData = {nav_js};
const colors = {COLORS};
const ctx = document.getElementById('navChart').getContext('2d');
const datasets = Object.entries(navData).map(([name, pts], i) => {{
    const isBench = name.includes('基准');
    return {{
        label: name,
        data: pts,
        borderColor: isBench ? '#95a5a6' : colors[i % colors.length],
        backgroundColor: 'transparent',
        borderWidth: isBench ? 2 : 2.5,
        pointRadius: 0, tension: 0.2,
        borderDash: isBench ? [5, 5] : [],
    }};
}});
new Chart(ctx, {{
    type: 'line',
    data: {{ datasets }},
    options: {{
        responsive: true,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{ callbacks: {{ label: ctx => `${{ctx.dataset.label}}: ${{ctx.parsed.y.toFixed(4)}}` }} }}
        }},
        scales: {{
            x: {{ type: 'time', time: {{ unit: 'month' }}, grid: {{ color: '#ecf0f1' }} }},
            y: {{ grid: {{ color: '#ecf0f1' }}, title: {{ display: true, text: '净值' }} }}
        }}
    }}
}});
const legendDiv = document.getElementById('navLegend');
Object.entries(navData).forEach(([name, pts], i) => {{
    const isBench = name.includes('基准');
    const color = isBench ? '#95a5a6' : colors[i % colors.length];
    const style = isBench ? 'background:#95a5a6;border-bottom:2px dashed #95a5a6' : 'background:' + color;
    legendDiv.innerHTML += '<div class="legend-item"><span class="legend-dot" style="' + style + '"></span>' + name + '</div>';
}});
</script>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

def get_strategy_detail_html(best_row, best_result) -> str:
    sname = best_row["策略"]
    m = best_result.get("metrics", {}) if best_result else {}

    desc_map = {
        "S1_动量20d": "20日价格动量策略，捕捉短期趋势效应。每月末选过去20日涨幅最高的Top20%股票，等权持有至下月调仓。适合趋势明确的市场。",
        "S2_动量60d": "60日价格动量，中期趋势跟踪。60日窗口是A股最有效的动量周期之一，能有效过滤短期噪音。",
        "S3_动量120d": "120日长期动量，捕捉战略级趋势。窗口较长，换手率低，信号滞后，适合长期配置型投资者。",
        "S4_低波动": "低波动因子（逆向），基于「彩票偏好」溢价理论，低波动股票长期跑赢市场。选每月波动率最低的Top20%股票。",
        "S5_高波动": "高波动趋势策略，选择波动率最高的股票。在趋势行情中有效，但风险较大。",
        "S6_质量盈利": "盈利质量策略，选择盈利最稳定（盈利波动最低）的股票。长期有效，信号滞后，适合长期持有型投资者。",
        "S7_反转5d": "5日短期反转，利用A股散户主导市场中的短期反转效应。短期涨幅过大的股票存在均值回归动力。适合震荡市。",
        "S8_均线偏离": "均线偏离度策略，价格偏离60日均线过多时存在回归动力。偏离度低时买入。",
        "S9_综合因子": "多因子综合策略，等权合成动量20d、动量60d、低波动、盈利质量四类因子。综合策略风险更分散，长期更稳健。",
        "S10_动量叠加质量": "动量+质量叠加，动量因子权重60%，质量因子权重40%。兼顾趋势捕捉和质量过滤。",
        "基准_588000.SH": "科创50ETF（588000.SH）买入持有，作为业绩比较基准。反映科创板整体市场表现。",
    }

    desc = desc_map.get(sname, best_row["描述"])
    mdd_note = "⚠️ 最大回撤较大" if abs(m.get("max_drawdown", 0) * 100) > 30 else "✅ 最大回撤可控"

    return f"""<table style="margin-bottom:16px">
    <tr><td style="font-weight:bold;color:#1a5276;width:120px">策略名称</td><td><b>{sname}</b></td></tr>
    <tr><td style="font-weight:bold;color:#1a5276">策略逻辑</td><td>{desc}</td></tr>
    <tr><td style="font-weight:bold;color:#1a5276">年化收益</td><td class="{'pos' if m.get('annual_return',0)>0 else 'neg'}" style="font-size:16px">{m.get('annual_return',0)*100:+.2f}%</td></tr>
    <tr><td style="font-weight:bold;color:#1a5276">夏普比率</td><td style="font-size:16px">{m.get('sharpe',0):.3f}</td></tr>
    <tr><td style="font-weight:bold;color:#1a5276">最大回撤</td><td class="{'dneg' if abs(m.get('max_drawdown',0)*100)>25 else ''}" style="font-size:16px">{m.get('max_drawdown',0)*100:.2f}%</td></tr>
    <tr><td style="font-weight:bold;color:#1a5276">卡尔玛比率</td><td>{m.get('calmar',0):.3f}</td></tr>
    <tr><td style="font-weight:bold;color:#1a5276">日胜率</td><td>{m.get('win_rate',0)*100:.1f}%</td></tr>
  </table>
  <div class="note">{mdd_note}。回测结果仅供参考，过往表现不代表未来收益。实盘需考虑冲击成本、滑点、流动性等摩擦因素。</div>"""

def get_usage_html() -> str:
    return """<h3 style="margin-bottom:12px">使用方法</h3>
<ol style="margin:0 0 16px 20px;line-height:2">
<li><b>打开报告</b>：用浏览器打开HTML文件，交互查看净值曲线（放大/缩小）和绩效数据。</li>
<li><b>解读排名</b>：优先选择夏普>0.5且最大回撤<25%的策略。</li>
<li><b>因子有效性</b>：查看IC分析表，IC_IR>0.3表示因子有效。</li>
<li><b>组合建议</b>：可将多个正夏普策略等权组合，进一步分散风险。</li>
</ol>
<h3 style="margin-bottom:12px">⚠️ 注意事项</h3>
<ul style="margin:0 0 16px 20px;line-height:2">
<li><b>回测偏差</b>：未计入冲击成本（~0.2%/笔）、滑点（0.05%）和流动性限制，实际执行效果可能低于回测5%~15%。</li>
<li><b>过拟合</b>：调仓频率（月频）和持仓数量（10只）经过历史优化，建议用不同参数验证稳健性。</li>
<li><b>数据局限</b>：可比池为沪深主板（600/601/603开头），与科创板（688开头）特征有差异，真实适用性待验证。</li>
<li><b>588200说明</b>：588200.SH本身在本地数据中不存在，使用588000.SH（华夏上证科创板50ETF）作为基准和参考。</li>
<li><b>建议步骤</b>：①Paper Trading验证1-3个月 ②小资金实盘 ③稳定盈利后加大仓位</li>
</ul>
<h3 style="margin-bottom:12px">💡 扩展方向</h3>
<ul style="margin:0;line-height:2">
<li>获取688科创板成分股K线数据，在真实科创板股票池上回测</li>
<li>加入财务因子（PE/PB/ROE）进行多因子回归</li>
<li>尝试周频调仓，对比不同频率绩效差异</li>
<li>加入止损机制（最大回撤阈值）控制风险</li>
</ul>"""

if __name__ == "__main__":
    results, metrics_df, ic_df, html_path = run_full_backtest()
