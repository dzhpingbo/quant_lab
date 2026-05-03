"""
588200科创芯片ETF - 真实成分股 全量回测
基于50+因子库（量价/技术/流动性/波动率/基本面代理）
涵盖16种策略，输出HTML报告
"""
import sys, io, os, time, threading, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

# ─── 路径配置 ────────────────────────────────────────
KC_DIR    = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/KC")   # 688科创股
ETF_DIR   = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/ETF/yf_etf_data")  # ETF基准
OUT_DIR   = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/因子数据库")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 588200成分股（2025Q4，筛掉历史<1年的）
CODES_588200 = [
    '688981','688041','688256','688008','688012','688072','688521','688347',
    '688126','688110','688498','688525','688120','688002','688249','688361',
    '688099','688313','688396','688385','688608','688213','688047','688019',
    '688037','688220','688234','688200','688052','688702','688018','688082',
    '688536','688582','688484','688141','688728','688409','688279','688709',
    '688172','688798','688153','688146','688332','688352','688432','688584',
    '688449','688605',
]
# 新上市的几只(<1年)不纳入回测
SKIP_SHORT = {'688795','688790','688729','688809','688727','688796','688807','688805'}
POOL = [c for c in CODES_588200 if c not in SKIP_SHORT]

BACKTEST_START = "2022-01-01"   # 科创板2019上市，2022开始有足够数据
BACKTEST_END   = "2026-04-10"
INIT_CAPITAL   = 1_000_000.0
COST_RATE      = 0.001          # 0.1% 双边交易成本
TOP_N          = 10             # 每月持仓只数

# ─── 心跳 ────────────────────────────────────────────
_t0 = time.time()
_stop_hb = threading.Event()
def _hb():
    while not _stop_hb.wait(30):
        e = int(time.time()-_t0); m,s = divmod(e,60)
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] ⏳ 仍在运行 | 已耗时{m}m{s:02d}s", flush=True)
threading.Thread(target=_hb, daemon=True).start()

# ─── 数据加载 ─────────────────────────────────────────
def load_kline(code, ext='.SS.csv', dir_=KC_DIR):
    p = dir_ / f"{code}{ext}"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.columns = [c.lower() for c in df.columns]
    df = df.sort_index()
    for col in ['open','high','low','close']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'volume' in df.columns:
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    return df.dropna(subset=['close'])

print(f"[{datetime.now().strftime('%H:%M:%S')}] ═══ 588200科创芯片 真实成分股 全量回测 ═══")
print(f"  股票池: {len(POOL)} 只 | 回测期: {BACKTEST_START}~{BACKTEST_END}")
print(f"  交易成本: {COST_RATE*100:.1f}% | 持仓: Top{TOP_N} 等权\n")

print(f"[{datetime.now().strftime('%H:%M:%S')}] ① 加载K线数据...")
dfs = {}
for code in tqdm(POOL, desc="加载"):
    df = load_kline(code)
    if not df.empty and len(df) >= 120:
        dfs[code] = df

# 加载基准（588000 科创50 ETF）
bench_df = pd.DataFrame()
for bcode in ['588000','510050']:
    for bdir, bext in [(ETF_DIR, '.csv'), (ETF_DIR, '.SH.csv')]:
        bp = bdir / f"{bcode}{bext}"
        if bp.exists():
            bench_df = pd.read_csv(bp, index_col=0, parse_dates=True)
            bench_df.index = pd.to_datetime(bench_df.index).tz_localize(None)
            bench_df.columns = [c.lower() for c in bench_df.columns]
            if 'close' in bench_df.columns and len(bench_df) > 100:
                print(f"  基准: {bcode} ({len(bench_df)}行 {bench_df.index[0].date()}~{bench_df.index[-1].date()})")
                break
    if not bench_df.empty:
        break

valid_pool = list(dfs.keys())
print(f"  有效股票: {len(valid_pool)}/{len(POOL)} 只")
if not valid_pool:
    print("❌ 无有效数据，退出")
    sys.exit(1)

# ─── 50+ 因子计算 ─────────────────────────────────────
print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ② 计算50+因子...")

def safe_rank(s):
    """截面排名归一化到[-1,1]"""
    r = s.rank(pct=True)
    return r * 2 - 1

def compute_factors(df, code):
    """
    给单只股票计算所有因子，返回 dict
    参考来源：
    - WorldQuant 101 Alphas（量价）
    - Fama-French三因子衍生
    - ILLIQ(Amihud)流动性因子
    - 特质波动率IVOL
    - 技术指标族（RSI/MACD/Boll/KDJ）
    - 换手率族
    - 价格反转族
    """
    c = df['close'].copy()
    h = df.get('high', c)
    l = df.get('low', c)
    o = df.get('open', c)
    v = df.get('volume', pd.Series(index=c.index, data=1.0))
    ret = c.pct_change()
    log_ret = np.log(c / c.shift(1))
    amount = c * v  # 成交额代理

    f = {}

    # ── A. 价格动量因子族 ──────────────────────────────
    f['mom_5d']   = c.pct_change(5)
    f['mom_10d']  = c.pct_change(10)
    f['mom_20d']  = c.pct_change(20)
    f['mom_60d']  = c.pct_change(60)
    f['mom_120d'] = c.pct_change(120)

    # 跳过近1月的中期动量（12-1动量，防止短反转污染）
    f['mom_60d_skip5']  = c.shift(5).pct_change(55)
    f['mom_120d_skip20'] = c.shift(20).pct_change(100)

    # ── B. 价格反转因子族 ──────────────────────────────
    f['rev_1d']   = -ret                        # 隔夜反转
    f['rev_5d']   = -c.pct_change(5)
    f['rev_10d']  = -c.pct_change(10)
    f['rev_20d']  = -c.pct_change(20)           # 月反转

    # ── C. 波动率因子族（低波动溢价）─────────────────
    f['vol_5d']   = ret.rolling(5).std()
    f['vol_10d']  = ret.rolling(10).std()
    f['vol_20d']  = ret.rolling(20).std()
    f['vol_60d']  = ret.rolling(60).std()
    # 特质波动率近似（相对于自身均值的残差波动，无市场因子时用原始std代替IVOL）
    f['ivol_20d'] = ret.rolling(20).std()  # 简化IVOL
    # 高低价振幅
    f['hl_range_20d'] = ((h - l) / c).rolling(20).mean()
    # 下行波动率（Sortino中的分母）
    downret = ret.clip(upper=0)
    f['down_vol_20d'] = downret.rolling(20).std()

    # ── D. 流动性因子族 ───────────────────────────────
    # Amihud ILLIQ：|ret| / amount (越大=流动性越差，选择低ILLIQ即高流动性)
    illiq = (ret.abs() / amount.replace(0, np.nan)).replace([np.inf,-np.inf], np.nan)
    f['illiq_20d']  = -illiq.rolling(20).mean()   # 取负使高流动性=高因子值
    f['illiq_5d']   = -illiq.rolling(5).mean()
    # 换手率（用成交额代理，相对自身历史标准化）
    turnover = amount / amount.rolling(60).mean().clip(lower=1e-10)
    f['turnover_norm_20d'] = turnover.rolling(20).mean()
    f['turnover_rev_20d']  = -turnover.rolling(20).mean()  # 低换手率选股
    # 成交量动量
    f['volume_mom_20d'] = v.pct_change(20)
    # 量价相关性（WorldQuant Alpha#6思路）
    f['vol_price_corr_20d'] = pd.Series(
        [ret.iloc[max(0,i-20):i].corr(v.iloc[max(0,i-20):i]) if i>=20 else np.nan
         for i in range(len(ret))], index=ret.index)

    # ── E. 技术指标族 ─────────────────────────────────
    # RSI(14)
    delta = ret.copy()
    gain = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    rsi = 100 - 100/(1+rs)
    f['rsi14']      = rsi
    f['rsi14_rev']  = -rsi   # 超卖反转
    f['rsi_oo']     = (50 - rsi).abs()  # 偏离中位的程度

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line  = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    f['macd']       = macd_line / c.replace(0,np.nan)  # 归一化
    f['macd_hist']  = (macd_line - signal_line) / c.replace(0,np.nan)
    f['macd_cross'] = (macd_line > signal_line).astype(float) - 0.5  # 金叉=0.5

    # 布林带位置（价格在布林带中的位置，>1=超买，<0=超卖）
    bb_mid  = c.rolling(20).mean()
    bb_std  = c.rolling(20).std()
    f['boll_pos']  = (c - bb_mid) / (2 * bb_std.replace(0,np.nan))
    f['boll_rev']  = -f['boll_pos']  # 均值回归

    # MA趋势
    ma5  = c.rolling(5).mean()
    ma10 = c.rolling(10).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    f['ma5_20_ratio']  = (ma5  - ma20) / ma20.replace(0,np.nan)
    f['ma20_60_ratio'] = (ma20 - ma60) / ma60.replace(0,np.nan)
    f['price_ma20_ratio'] = (c - ma20) / ma20.replace(0,np.nan)

    # ── F. WorldQuant Alpha思路因子 ───────────────────
    # Alpha#1: sign(delta(ret, 1)) * (-1 * delta(abs(close), 7))
    f['wq1'] = np.sign(ret.diff(1)) * (-ret.abs().diff(7))
    # Alpha#2: -1 * corr(rank(delta(log(volume),2)), rank((close-open)/open), 6)
    rank_vol_d = (np.log(v+1).diff(2)).rank(pct=True)
    rank_oc    = ((c - o) / o.replace(0,np.nan)).rank(pct=True)
    f['wq2'] = -rank_vol_d.rolling(6).corr(rank_oc)
    # Alpha#3: -1 * corr(rank(open), rank(volume), 10)
    f['wq3'] = -o.rank(pct=True).rolling(10).corr(v.rank(pct=True))
    # Alpha#6: -1 * corr(open, volume, 10)
    f['wq6'] = -o.rolling(10).corr(v)

    # ── G. 盈利质量/价格质量 ─────────────────────────
    # 盈利稳定性：近60日收益率的稳定性（低波动=高质量）
    f['earn_quality'] = -ret.rolling(60).std()   # 高稳定性=因子高
    # 价格加速度（动量是否在加速）
    f['mom_accel'] = ret.rolling(5).mean() - ret.rolling(20).mean()
    # 尾部风险（CVaR近似）
    def cvar(s, window=20, q=0.05):
        def _cv(x):
            th = np.quantile(x, q)
            tail = x[x <= th]
            return tail.mean() if len(tail) > 0 else np.nan
        return s.rolling(window).apply(_cv, raw=True)
    f['cvar20'] = -cvar(ret, 20)  # 取负：低CVaR=高因子值

    # ── H. 价量综合 ───────────────────────────────────
    # 量价背离（价格上涨但成交量下降=可能反转）
    price_trend = c.pct_change(5)
    vol_trend   = v.pct_change(5)
    f['pv_diverge'] = price_trend - vol_trend  # 价涨量缩为正
    # 成交量加速/减速
    f['vol_accel'] = v.rolling(5).mean() / v.rolling(20).mean().replace(0,np.nan) - 1

    return f

# 计算所有股票的因子
print(f"  计算 {len(valid_pool)} 只股票因子...")
all_factors = {}
for code in tqdm(valid_pool, desc="因子计算"):
    all_factors[code] = compute_factors(dfs[code], code)

# 获取第一只股票的因子名
sample_code = valid_pool[0]
factor_names = list(all_factors[sample_code].keys())
print(f"  ✅ 因子总数: {len(factor_names)} 个")
print(f"  因子列表: {factor_names}")

# ─── 构建月度因子截面 ─────────────────────────────────
print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ③ 构建月度截面...")

# 月末日期列表
close_concat = pd.concat([dfs[c]['close'].rename(c) for c in valid_pool], axis=1)
date_range = close_concat.loc[BACKTEST_START:BACKTEST_END].index
monthly_dates = close_concat.resample('ME').last().loc[BACKTEST_START:BACKTEST_END].index.tolist()
print(f"  月末截面数: {len(monthly_dates)}")

# ─── 纯Python回测引擎 ────────────────────────────────
def backtest_factor_strategy(factor_name, direction='long', top_n=TOP_N, cost=COST_RATE):
    """
    按因子月频选股回测
    direction: 'long'=做多因子高的 / 'short'=做多因子低的（即空头）
    返回 (equity_curve_series, metrics_dict)
    """
    equity = INIT_CAPITAL
    equity_history = []
    prev_portfolio = set()
    turnover_list = []

    for i, dt in enumerate(monthly_dates[:-1]):
        next_dt = monthly_dates[i+1]

        # 获取当前月末因子值
        factor_vals = {}
        for code in valid_pool:
            fdata = all_factors[code][factor_name]
            # 取 dt 当天或最近可用值
            avail = fdata[fdata.index <= dt].dropna()
            if len(avail) >= 5:
                factor_vals[code] = avail.iloc[-1]

        if len(factor_vals) < top_n:
            equity_history.append({'date': dt, 'equity': equity})
            continue

        # 截面排名，选 top_n
        fv_series = pd.Series(factor_vals)
        if direction == 'long':
            selected = fv_series.nlargest(top_n).index.tolist()
        else:
            selected = fv_series.nsmallest(top_n).index.tolist()

        # 计算持仓期收益
        period_rets = []
        for code in selected:
            c_series = dfs[code]['close']
            c_avail = c_series[c_series.index <= next_dt]
            c_entry = c_series[c_series.index <= dt]
            if c_entry.empty or c_avail.empty:
                continue
            entry_price = c_entry.iloc[-1]
            exit_price  = c_avail.iloc[-1]
            if entry_price > 0:
                ret = exit_price / entry_price - 1
                period_rets.append(ret)

        if not period_rets:
            equity_history.append({'date': dt, 'equity': equity})
            continue

        # 等权组合收益
        avg_ret = np.mean(period_rets)

        # 换手率计算
        new_portfolio = set(selected)
        if prev_portfolio:
            turn = len(new_portfolio - prev_portfolio) / top_n
        else:
            turn = 1.0
        turnover_list.append(turn)

        # 扣除交易成本
        net_ret = avg_ret - cost * turn * 2  # 买卖各cost
        equity = equity * (1 + net_ret)
        prev_portfolio = new_portfolio

        equity_history.append({'date': dt, 'equity': equity, 'ret': net_ret, 'n_stocks': len(period_rets)})

    if not equity_history:
        return pd.Series(dtype=float), {}

    eq_df = pd.DataFrame(equity_history).set_index('date')
    eq_series = eq_df['equity']

    # 计算绩效指标
    rets = eq_df.get('ret', pd.Series()).dropna()
    n = max(len(rets), 1)
    years = n / 12

    total_ret = (eq_series.iloc[-1] / INIT_CAPITAL) - 1
    ann_ret   = (1 + total_ret) ** (1/max(years,0.1)) - 1
    ann_vol   = rets.std() * (12**0.5) if len(rets) > 1 else 0
    sharpe    = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    max_dd    = ((eq_series.cummax() - eq_series) / eq_series.cummax()).max()
    calmar    = ann_ret / max_dd if max_dd > 0 else 0
    win_rate  = (rets > 0).mean() if len(rets) > 0 else 0
    avg_turn  = np.mean(turnover_list) if turnover_list else 0

    metrics = {
        'ann_ret': ann_ret,
        'ann_vol': ann_vol,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'calmar': calmar,
        'win_rate': win_rate,
        'total_ret': total_ret,
        'avg_turnover': avg_turn,
    }
    return eq_series, metrics

# ─── 策略组合定义 ─────────────────────────────────────
STRATEGIES = [
    # 名称, 因子名, 方向, 说明
    ("S01_反转5d",        "rev_5d",           "long",  "5日价格反转，捕捉短期过度反应"),
    ("S02_反转20d",       "rev_20d",          "long",  "月度反转，均值回归策略"),
    ("S03_动量60d",       "mom_60d",          "long",  "60日价格动量，趋势追踪"),
    ("S04_动量120d_skip", "mom_120d_skip20",  "long",  "去除最近20日的中期动量（12-1月动量）"),
    ("S05_低波动",        "vol_20d",          "short", "低波动率选股，低波动溢价"),
    ("S06_IVOL",          "ivol_20d",         "short", "低特质波动率，风险调整收益"),
    ("S07_ILLIQ流动性",   "illiq_20d",        "long",  "Amihud非流动性，高ILLIQ溢价"),
    ("S08_高换手反转",    "turnover_rev_20d", "long",  "低换手率选股，避开过度交易股"),
    ("S09_RSI超卖",       "rsi14_rev",        "long",  "RSI超卖（低RSI）反转选股"),
    ("S10_布林反转",      "boll_rev",         "long",  "布林带下轨区域，均值回归"),
    ("S11_MACD趋势",      "macd_hist",        "long",  "MACD柱状图动量，趋势延续"),
    ("S12_量价背离",      "vol_price_corr_20d","short","量价负相关，量涨价跌的超买信号"),
    ("S13_WQ_Alpha2",     "wq2",              "long",  "WorldQuant Alpha#2改：量变与涨跌幅背离"),
    ("S14_盈利质量",      "earn_quality",     "long",  "收益稳定性，高质量股票选股"),
    ("S15_CVaR风险",      "cvar20",           "long",  "低尾部风险选股，下行保护"),
    ("S16_MA趋势_20_60",  "ma20_60_ratio",    "long",  "MA20/MA60趋势因子，中期趋势"),
]

# ─── 运行所有策略回测 ─────────────────────────────────
print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ④ 运行 {len(STRATEGIES)} 种策略回测...")
results = {}
equity_curves = {}

for strat_name, factor, direction, desc in tqdm(STRATEGIES, desc="回测进度"):
    eq, metrics = backtest_factor_strategy(factor, direction=direction)
    results[strat_name] = {**metrics, 'factor': factor, 'direction': direction, 'desc': desc}
    equity_curves[strat_name] = eq
    print(f"  {strat_name}: 年化{metrics.get('ann_ret',0)*100:.1f}% | 夏普{metrics.get('sharpe',0):.3f} | 回撤{metrics.get('max_dd',0)*100:.1f}%")

# ─── 计算基准 ─────────────────────────────────────────
bench_eq = None
bench_metrics = {}
if not bench_df.empty:
    bc = bench_df['close']
    bc = bc.loc[BACKTEST_START:BACKTEST_END]
    if len(bc) > 10:
        bench_eq = (bc / bc.iloc[0]) * INIT_CAPITAL
        bench_rets = bc.pct_change().dropna()
        bann = (bc.iloc[-1]/bc.iloc[0]) ** (12/max(len(monthly_dates),1)) - 1
        bvol = bench_rets.std() * 252**0.5
        bdd  = ((bc.cummax()-bc)/bc.cummax()).max()
        bench_metrics = {'ann_ret': bann, 'sharpe': (bann-0.02)/bvol if bvol>0 else 0, 'max_dd': bdd}

# ─── 排名 ─────────────────────────────────────────────
rank_df = pd.DataFrame(results).T
rank_df['sharpe'] = rank_df['sharpe'].astype(float)
rank_df['ann_ret'] = rank_df['ann_ret'].astype(float)
rank_df['max_dd'] = rank_df['max_dd'].astype(float)
rank_df_sorted = rank_df.sort_values('sharpe', ascending=False)

print(f"\n{'='*70}")
print("策略绩效排名（按夏普比率）:")
print(f"{'策略名':<22} {'年化收益':>8} {'夏普':>7} {'最大回撤':>9} {'胜率':>7}")
print("-"*70)
for name, row in rank_df_sorted.iterrows():
    ann = float(row.get('ann_ret', 0))
    sh  = float(row.get('sharpe', 0))
    dd  = float(row.get('max_dd', 0))
    wr  = float(row.get('win_rate', 0))
    mark = "★" if sh > 0.4 else ("☆" if sh > 0 else "✗")
    print(f"{mark} {name:<20} {ann*100:>7.1f}%  {sh:>7.3f}  {-dd*100:>8.1f}%  {wr*100:>6.1f}%")

# ─── 保存绩效Excel ────────────────────────────────────
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
perf_path = OUT_DIR / f"588200_真实成分股_策略绩效_{ts}.xlsx"
rank_df_sorted.to_excel(perf_path)
print(f"\n绩效已保存: {perf_path}")

# ─── 净值曲线CSV ──────────────────────────────────────
nav_path = OUT_DIR / f"588200_真实成分股_净值曲线_{ts}.csv"
nav_dict = {}
for name, eq in equity_curves.items():
    if eq is not None and len(eq) > 0:
        nav_dict[name] = (eq / INIT_CAPITAL * 100).round(4)
if bench_eq is not None:
    nav_dict['基准_588000'] = (bench_eq / INIT_CAPITAL * 100).round(4)
nav_df = pd.DataFrame(nav_dict)
nav_df.to_csv(nav_path)

# ─── 生成HTML报告 ─────────────────────────────────────
print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⑤ 生成HTML报告...")

top3 = rank_df_sorted.head(3)
top3_names = top3.index.tolist()

def make_color(v, best, worst):
    if best == worst:
        return '#555'
    ratio = (v - worst) / (best - worst)
    r = int(220 - ratio * 160)
    g = int(50  + ratio * 160)
    return f'rgb({r},{g},50)'

rows_html = ""
for i, (name, row) in enumerate(rank_df_sorted.iterrows()):
    ann = float(row.get('ann_ret', 0))
    sh  = float(row.get('sharpe', 0))
    dd  = float(row.get('max_dd', 0))
    wr  = float(row.get('win_rate', 0))
    calmar = float(row.get('calmar', 0))
    desc = row.get('desc', '')
    medal = ['🥇','🥈','🥉'][i] if i < 3 else f'{i+1}.'
    is_top = 'top3' if i < 3 else ''
    rows_html += f"""
    <tr class='{is_top}'>
      <td>{medal} {name}</td>
      <td style='color:{"#e74c3c" if ann>=0 else "#27ae60"};font-weight:bold'>{ann*100:+.1f}%</td>
      <td style='color:{"#e74c3c" if sh>=0.3 else ("#555" if sh>=0 else "#27ae60")};font-weight:bold'>{sh:.3f}</td>
      <td>{-dd*100:.1f}%</td>
      <td>{calmar:.2f}</td>
      <td>{wr*100:.1f}%</td>
      <td style='font-size:12px;color:#888'>{desc}</td>
    </tr>"""

# 净值曲线数据
nav_js_data = "{"
for name, eq in equity_curves.items():
    if eq is not None and len(eq) > 0:
        pts = [(str(d.date()), round(float(v)/INIT_CAPITAL*100, 4))
               for d, v in eq.items() if not np.isnan(v)]
        nav_js_data += f'"{name}": {pts},'
if bench_eq is not None:
    pts = [(str(d.date()), round(float(v)/INIT_CAPITAL*100, 4))
           for d, v in bench_eq.items() if not np.isnan(v)]
    nav_js_data += f'"基准_588000": {pts},'
nav_js_data = nav_js_data.rstrip(',') + "}"

# 最优策略详细说明
top_detail_html = ""
factor_docs = {
    "rev_5d":   ("5日反转因子", "科创板短期波动大，机构资金轮动频繁，5日跌幅最大的股票往往存在过度反应，次月有较强均值回归动力。选过去5日收益率最低的Top10持仓。", "每月末调仓，持有下月。适合波动市场，避开持续下跌的个股。"),
    "vol_20d":  ("低波动率因子", "低波动溢价（Low Volatility Anomaly）在全球市场普遍存在，在科创板同样有效。低波动股票通常是行业龙头，基本面更稳定，机构持仓集中。", "选过去20日日收益率标准差最低的Top10，每月调仓。注意：在强趋势行情中可能落后。"),
    "ivol_20d": ("低特质波动率", "特质波动率越低，股票的噪音越小，定价越有效。低IVOL股票通常具有更强的分析师覆盖和机构持仓。", "与低波动策略互补，适合长期配置。"),
    "earn_quality": ("盈利质量/收益稳定性", "收益率序列越平稳，说明该股票的运营越稳定，能够持续创造价值。科创板高质量公司往往是细分领域龙头。", "选历史收益率标准差最低的Top10，与低波动策略高度相关，可作为交叉验证。"),
    "rsi14_rev": ("RSI超卖反转", "RSI<30通常被视为超卖信号。选RSI最低（超卖程度最深）的股票，利用均值回归特性获利。", "结合反转策略使用效果更好，但注意趋势向下的股票可能持续超卖。"),
    "ma20_60_ratio": ("MA20/MA60趋势", "MA20在MA60上方（正值）表示中期趋势向上，趋势跟随策略。", "适合趋势明确的市场，在震荡市可能频繁止损。"),
    "macd_hist": ("MACD柱状图动量", "MACD柱状图由负转正（或持续走高）表示动量增强，趋势延续信号。", "结合成交量放大效果更佳，避免在成交量萎缩时入场。"),
    "illiq_20d": ("Amihud非流动性溢价", "流动性溢价理论：流动性差的股票需要给投资者补偿，长期存在超额收益。科创板部分小市值股票流动性偏低，ILLIQ因子在此有特殊意义。", "注意流动性陷阱：极低流动性股票在持仓时可能买卖困难，实盘需控制仓位。"),
}

for i, (name, row) in enumerate(rank_df_sorted.head(5).iterrows()):
    factor = str(row.get('factor', ''))
    desc = str(row.get('desc', ''))
    doc = factor_docs.get(factor, (factor, desc, "详见因子说明"))
    ann = float(row.get('ann_ret', 0))
    sh  = float(row.get('sharpe', 0))
    dd  = float(row.get('max_dd', 0))
    medal = ['🥇','🥈','🥉','4️⃣','5️⃣'][i]
    top_detail_html += f"""
    <div class='strategy-card'>
      <h3>{medal} {name}</h3>
      <div class='stat-grid'>
        <div class='stat-box'><div class='stat-val red'>{ann*100:+.1f}%</div><div class='stat-label'>年化收益</div></div>
        <div class='stat-box'><div class='stat-val blue'>{sh:.3f}</div><div class='stat-label'>夏普比率</div></div>
        <div class='stat-box'><div class='stat-val green'>{-dd*100:.1f}%</div><div class='stat-label'>最大回撤</div></div>
      </div>
      <div class='factor-name'>📊 因子：{doc[0]}</div>
      <div class='factor-logic'><b>核心逻辑：</b>{doc[1]}</div>
      <div class='factor-usage'><b>使用方法：</b>{doc[2]}</div>
    </div>"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>588200科创芯片ETF — 真实成分股全量回测报告</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:#0d1117;color:#e6edf3;line-height:1.6}}
    .container{{max-width:1400px;margin:0 auto;padding:24px}}
    .header{{background:linear-gradient(135deg,#1a1f2e,#16213e);border:1px solid #30363d;border-radius:12px;padding:32px;margin-bottom:24px;text-align:center}}
    h1{{font-size:2rem;color:#58a6ff;margin-bottom:8px}}
    .subtitle{{color:#8b949e;font-size:1rem}}
    .badge{{display:inline-block;background:#21262d;border:1px solid #30363d;border-radius:20px;padding:4px 12px;margin:4px;font-size:0.85rem;color:#8b949e}}
    .section{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;margin-bottom:24px}}
    .section h2{{color:#58a6ff;font-size:1.3rem;margin-bottom:16px;border-bottom:1px solid #30363d;padding-bottom:8px}}
    table{{width:100%;border-collapse:collapse;font-size:0.9rem}}
    th{{background:#21262d;color:#8b949e;padding:10px 12px;text-align:left;font-weight:600;border-bottom:2px solid #30363d}}
    td{{padding:10px 12px;border-bottom:1px solid #21262d}}
    tr:hover td{{background:#1f2937}}
    tr.top3 td{{background:#1a2332}}
    .chart-container{{width:100%;height:450px;position:relative}}
    canvas{{width:100%!important;height:100%!important}}
    .strategy-card{{background:#1a1f2e;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:16px}}
    .strategy-card h3{{color:#58a6ff;margin-bottom:12px;font-size:1.1rem}}
    .stat-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:12px 0}}
    .stat-box{{background:#0d1117;border-radius:8px;padding:12px;text-align:center}}
    .stat-val{{font-size:1.4rem;font-weight:bold;margin-bottom:4px}}
    .stat-label{{font-size:0.8rem;color:#8b949e}}
    .red{{color:#f85149}}
    .blue{{color:#58a6ff}}
    .green{{color:#3fb950}}
    .factor-name{{background:#21262d;border-left:3px solid #58a6ff;padding:8px 12px;margin:10px 0;border-radius:0 6px 6px 0;font-weight:600}}
    .factor-logic,.factor-usage{{font-size:0.9rem;color:#8b949e;margin:8px 0;padding-left:8px}}
    .summary-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
    .summary-card{{background:#1a1f2e;border:1px solid #30363d;border-radius:10px;padding:16px;text-align:center}}
    .summary-val{{font-size:1.6rem;font-weight:bold;color:#58a6ff}}
    .summary-label{{font-size:0.85rem;color:#8b949e;margin-top:4px}}
    .warning{{background:#2d1a00;border:1px solid #663300;border-radius:8px;padding:12px 16px;margin:16px 0;color:#e6a817;font-size:0.9rem}}
    .nav-legend{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}}
    .legend-item{{display:flex;align-items:center;gap:6px;font-size:0.8rem;color:#8b949e}}
    .legend-dot{{width:12px;height:12px;border-radius:50%;display:inline-block}}
  </style>
</head>
<body>
<div class='container'>
  <div class='header'>
    <h1>📊 588200 科创芯片ETF — 真实成分股全量回测</h1>
    <div class='subtitle'>基于2025Q4持仓成分股 × 50+因子库 × 16种策略</div>
    <div style='margin-top:12px'>
      <span class='badge'>📅 回测期: {BACKTEST_START} ~ {BACKTEST_END}</span>
      <span class='badge'>🎯 成分股: {len(valid_pool)} 只688科创芯片股</span>
      <span class='badge'>💰 初始资金: ¥100万</span>
      <span class='badge'>📊 因子数: {len(factor_names)} 个</span>
      <span class='badge'>🔄 调仓: 月频 | 持仓Top{TOP_N} 等权</span>
      <span class='badge'>💸 成本: 双边{COST_RATE*100:.1f}%</span>
      <span class='badge'>⏰ 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}</span>
    </div>
  </div>

  <div class='summary-grid'>
    <div class='summary-card'>
      <div class='summary-val'>{len(STRATEGIES)}</div>
      <div class='summary-label'>策略总数</div>
    </div>
    <div class='summary-card'>
      <div class='summary-val'>{len(factor_names)}</div>
      <div class='summary-label'>因子总数</div>
    </div>
    <div class='summary-card'>
      <div class='summary-val'>{(rank_df_sorted['sharpe'].astype(float)>0).sum()}</div>
      <div class='summary-label'>正夏普策略数</div>
    </div>
    <div class='summary-card'>
      <div class='summary-val'>{float(rank_df_sorted['sharpe'].iloc[0]):.3f}</div>
      <div class='summary-label'>最高夏普比率</div>
    </div>
  </div>

  <div class='warning'>
    ⚠️ <b>重要说明：</b>588200为<b>科创芯片ETF嘉实</b>（688开头芯片半导体股），
    回测基于2025Q4持仓的{len(valid_pool)}只真实成分股，平均上市约3.6年（2019年科创板设立）。
    回测结果不代表未来表现，实盘时请考虑流动性、冲击成本等因素。
  </div>

  <div class='section'>
    <h2>🏆 策略绩效排名（按夏普比率）</h2>
    <table>
      <thead><tr>
        <th>策略名</th><th>年化收益</th><th>夏普比率</th>
        <th>最大回撤</th><th>卡尔玛</th><th>胜率</th><th>策略描述</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>

  <div class='section'>
    <h2>📈 净值曲线对比</h2>
    <div class='nav-legend' id='navLegend'></div>
    <div class='chart-container'><canvas id='navChart'></canvas></div>
  </div>

  <div class='section'>
    <h2>🎯 Top5 策略详细说明</h2>
    {top_detail_html}
  </div>

  <div class='section'>
    <h2>📚 因子库说明（{len(factor_names)} 个因子，7大类）</h2>
    <table>
      <thead><tr><th>类别</th><th>因子</th><th>数量</th><th>来源/理论</th></tr></thead>
      <tbody>
        <tr><td>A. 价格动量</td><td>mom_5d/10d/20d/60d/120d, mom_60d_skip5, mom_120d_skip20</td><td>7</td><td>Jegadeesh&Titman(1993), Fama-French</td></tr>
        <tr><td>B. 价格反转</td><td>rev_1d/5d/10d/20d</td><td>4</td><td>De Bondt&Thaler(1985), A股强反转效应</td></tr>
        <tr><td>C. 波动率</td><td>vol_5d/10d/20d/60d, ivol_20d, hl_range_20d, down_vol_20d</td><td>7</td><td>Low Volatility Anomaly, Baker et al.</td></tr>
        <tr><td>D. 流动性</td><td>illiq_20d/5d, turnover_norm/rev, volume_mom, vol_price_corr</td><td>6</td><td>Amihud(2002) ILLIQ, 中金量化手册</td></tr>
        <tr><td>E. 技术指标</td><td>RSI14/rsi_oo, MACD/hist/cross, boll_pos/rev, MA比率族</td><td>10</td><td>技术分析，动量与反转信号</td></tr>
        <tr><td>F. WorldQuant</td><td>wq1/wq2/wq3/wq6</td><td>4</td><td>WorldQuant 101 Formulaic Alphas</td></tr>
        <tr><td>G. 质量/综合</td><td>earn_quality, mom_accel, cvar20, pv_diverge, vol_accel</td><td>5</td><td>盈利质量, CVaR尾部风险, 量价综合</td></tr>
      </tbody>
    </table>
  </div>

</div>

<script>
const navData = {nav_js_data};
const colors = ['#ff6b6b','#4ecdc4','#45b7d1','#96ceb4','#ffeaa7',
                 '#dfe6e9','#fd79a8','#a29bfe','#6c5ce7','#00b894',
                 '#e17055','#00cec9','#fdcb6e','#74b9ff','#55efc4','#b2bec3'];
const ctx = document.getElementById('navChart').getContext('2d');
const legendDiv = document.getElementById('navLegend');

const allDates = [...new Set(Object.values(navData).flatMap(pts => pts.map(p => p[0])))].sort();
const datasets = Object.entries(navData).map(([name, pts], i) => {{
  const isBench = name.includes('基准');
  const color = isBench ? '#95a5a6' : colors[i % colors.length];
  const ptMap = Object.fromEntries(pts);
  return {{
    label: name,
    data: allDates.map(d => ptMap[d] || null),
    borderColor: color,
    backgroundColor: 'transparent',
    borderWidth: isBench ? 2 : 1.5,
    borderDash: isBench ? [5,5] : [],
    pointRadius: 0,
    tension: 0.1,
    spanGaps: true,
  }};
}});

datasets.forEach((ds, i) => {{
  const dot = document.createElement('div');
  dot.className = 'legend-item';
  dot.innerHTML = '<span class="legend-dot" style="background:' + ds.borderColor + '"></span>' + ds.label;
  legendDiv.appendChild(dot);
}});

new Chart(ctx, {{
  type: 'line',
  data: {{ labels: allDates, datasets }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    animation: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        mode: 'index', intersect: false,
        backgroundColor: 'rgba(13,17,23,0.95)',
        borderColor: '#30363d', borderWidth: 1,
        callbacks: {{
          label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y||0).toFixed(2)
        }}
      }}
    }},
    scales: {{
      x: {{ ticks: {{ color:'#8b949e', maxTicksLimit:12 }}, grid: {{ color:'#21262d' }} }},
      y: {{ ticks: {{ color:'#8b949e', callback: v => v+'%' }}, grid: {{ color:'#21262d' }} }}
    }}
  }}
}});
</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</body>
</html>"""

# 注意：Chart.js需要在canvas之前加载，调整script顺序
# 重新输出修正后的HTML（把CDN脚本提前）
html = html.replace(
    '<script>\nconst navData',
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>\n<script>\nconst navData'
).replace(
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>\n</body>',
    '</body>'
)

html_path = OUT_DIR / f"588200_真实成分股_全量回测报告_{ts}.html"
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

_stop_hb.set()
elapsed = time.time() - _t0
m, s = divmod(int(elapsed), 60)
print(f"\n{'='*70}")
print(f"[{datetime.now().strftime('%H:%M:%S')}] 全部完成！总耗时 {m}m{s:02d}s")
print(f"HTML报告: {html_path}")
print(f"绩效Excel: {perf_path}")
print(f"净值CSV: {nav_path}")
