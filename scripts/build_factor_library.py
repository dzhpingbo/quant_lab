"""
A股量化因子库构建脚本
====================
数据源：baostock（财务）+ akshare THS（同比增速）+ 本地 yfinance CSV（价格）
并行：多线程并发抓取
心跳：每30秒输出进度

因子分类：
  动量因子 - ret_5d/20d/60d/120d, sr_120d(收益/波动率), maxdd_120d
  价值因子 - pe, pb, ps, dividend_yield, peg
  质量因子 - roe_ttm, roa_ttm, net_margin, gross_margin, asset_turnover, debt_ratio
  流动性因子 - turnover_rate, amihud, volume_std
  风险因子 - vol_20d/60d/120d, beta

输出：
  data/features_cache/factors_{date}.parquet   - 因子矩阵（qlib格式兼容）
  data/features_cache/factors_summary.json   - 当日因子覆盖统计
"""

from __future__ import annotations
import os, sys, time, json, logging, datetime, warnings, threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent  # scripts/
_QUANT_LAB = _HERE.parent       # quant_lab/
DATA_DIR = _QUANT_LAB / "data"
RAW_CN_DIR = DATA_DIR / "raw" / "cn"
FEATURES_DIR = DATA_DIR / "features_cache"
STAGING_DIR = DATA_DIR / "staging" / "cn"

for _d in [RAW_CN_DIR, FEATURES_DIR, STAGING_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# 本地 yfinance 数据（已有）
YF_SH_DIR = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SH")
YF_SZ_DIR = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SZ")

# ─────────────────────────────────────────────────────────────────
# 心跳日志
# ─────────────────────────────────────────────────────────────────
_log_lines: List[str] = []
_log_lock = threading.Lock()
_start_time = time.time()

def heartbeat(msg: str = ""):
    """线程安全的打印（避免多线程输出乱序）"""
    elapsed = time.time() - _start_time
    m, s = divmod(int(elapsed), 60)
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}][{m}m{s}s] {msg}"
    with _log_lock:
        _log_lines.append(line)
        print(line, flush=True)

def log(msg: str):
    heartbeat(msg)

# ─────────────────────────────────────────────────────────────────
# Step 1: 加载候选股票列表
# ─────────────────────────────────────────────────────────────────
def load_stock_universe() -> List[str]:
    """
    从七类池子 + 因子数据库 + 本地CSV文件名 加载候选股票列表
    优先用已有质量池子（共140只），再补充本地有数据的其他股票
    """
    candidates = set()

    def _clean_code(v) -> str:
        """清理代码：去掉 SH/SZ/.SH/.SZ/后缀，转6位"""
        s = str(v).upper().strip()
        for suf in [".SH", ".SZ", ".SS", ".HK", "SH", "SZ"]:
            s = s.replace(suf, "")
        return s.split(".")[0].zfill(6)

    # 1. 七类池子（已知140只优质股）
    pool_file = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/因子数据库/七类池子筛选结果.xlsx")
    if pool_file.exists():
        try:
            df_pool = pd.read_excel(pool_file, sheet_name="全部池子")
            codes = df_pool["代码"].dropna().apply(_clean_code).unique().tolist()
            candidates.update(codes)
            log(f"从七类池子加载: {len(codes)} 只")
        except Exception as e:
            log(f"七类池子读取失败: {e}")

    # 2. 588200 可比池
    comp_file = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/因子数据库/588200可比股票池.xlsx")
    if comp_file.exists():
        try:
            df_comp = pd.read_excel(comp_file)
            codes = df_comp["代码"].dropna().apply(_clean_code).unique().tolist()
            candidates.update(codes)
            log(f"从可比池加载: +{len(codes)} 只")
        except Exception as e:
            log(f"可比池读取失败: {e}")

    # 3. 本地 yfinance 有数据的股票（补充200只有长期数据的）
    extra = []
    for yf_dir in [YF_SH_DIR, YF_SZ_DIR]:
        if yf_dir.exists():
            for f in os.listdir(yf_dir):
                if f.endswith(".csv"):
                    code = f.replace(".SS", "").replace(".SZ", "").replace(".csv", "")
                    if code not in candidates and code.isdigit():
                        extra.append(code)

    np.random.seed(42)
    extra = list(set(extra))
    np.random.shuffle(extra)
    candidates.update(extra[:200])
    log(f"本地数据补充: +{min(200, len(extra))} 只")

    result = sorted(candidates)
    log(f"候选股票总数: {len(result)} 只")
    return result

# ─────────────────────────────────────────────────────────────────
# Step 2: 单股数据抓取（baostock + akshare + 本地CSV）
# ─────────────────────────────────────────────────────────────────
_FETCH_CACHE: Dict[str, Dict[str, Any]] = {}

# baostock 不支持高并发，用信号量限制同时只有1个线程访问
# K线来自本地CSV（无网络），所以并发只影响baostock
_baostock_sem = threading.BoundedSemaphore(1)

def _ensure_baostock():
    """主进程预登录（仅在主线程调用一次，用于预热）"""
    import baostock as bs
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")
    bs.logout()
    return True

def fetch_single_stock_data(symbol: str) -> Dict[str, Any]:
    """
    并行安全的单股数据抓取

    Returns:
        {
            'code': str,
            'kline': DataFrame,       # 价格K线（本地yfinance）
            'financial': DataFrame,   # 财务数据（baostock）
            'success': bool,
            'error': str or None,
        }
    """
    result = {
        "code": symbol,
        "kline": pd.DataFrame(),
        "financial": pd.DataFrame(),
        "success": False,
        "error": None,
    }
    yf_sym = _norm_yf(symbol)
    bs_sym = _norm_bs(symbol)

    # ── K线：本地yfinance CSV（无网络，毫秒级）─────────────────
    # yf_sym = "600007.SS"，列名是 lowercase date/low/high/close/vol
    try:
        for csv_dir in [YF_SH_DIR, YF_SZ_DIR]:
            csv_path = csv_dir / f"{yf_sym}.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path)  # 不用 parse_dates，列名是小写
                df.columns = [c.lower() for c in df.columns]
                # 确保 date 列存在
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"], errors="coerce")
                    df = df.dropna(subset=["date"])
                    result["kline"] = df.sort_values("date").tail(500)
                break
            # 备选：直接从 code6 查找
            code6 = _norm_code6(symbol)
            for ext in [".SS.csv", ".SZ.csv"]:
                alt_path = csv_dir / f"{code6}{ext}"
                if alt_path.exists():
                    df = pd.read_csv(alt_path)
                    df.columns = [c.lower() for c in df.columns]
                    if "date" in df.columns:
                        df["date"] = pd.to_datetime(df["date"], errors="coerce")
                        df = df.dropna(subset=["date"])
                        result["kline"] = df.sort_values("date").tail(500)
                    break
    except Exception as e:
        result["error"] = f"K线:{e}"

    # ── 财务数据：baostock（信号量限流，最多2并发，带重试）──────
    import baostock as bs

    def _fetch_bs():
        """在信号量保护下执行 baostock 查询（最多重试3次）"""
        for attempt in range(3):
            with _baostock_sem:
                try:
                    lg = bs.login()
                    if lg.error_code != "0":
                        return [], f"登录失败:{lg.error_msg}"

                    records = []
                    today = datetime.date.today()
                    for year in range(today.year, today.year - 4, -1):
                        for q in [4, 3, 2, 1]:
                            rs = bs.query_profit_data(code=bs_sym, year=year, quarter=q)
                            while rs.error_code == "0" and rs.next():
                                row = rs.get_row_data()
                                d = dict(zip(rs.fields, row))
                                records.append({
                                    "report_date": d.get("statDate", ""),
                                    "pub_date": d.get("pubDate", ""),
                                    "roe": _safe_float_pct(d.get("roeAvg")),
                                    "net_margin": _safe_float_pct(d.get("npMargin")),
                                    "gross_margin": _safe_float_pct(d.get("gpMargin")),
                                    "net_profit": _safe_float(d.get("netProfit")),
                                    "eps": _safe_float(d.get("epsTTM")),
                                    "revenue": _safe_float(d.get("MBRevenue")),
                                })
                            if len(records) >= 8:
                                break
                        if len(records) >= 8:
                            break

                    bs.logout()
                    return records, None

                except Exception as e:
                    err_str = str(e)
                    try:
                        bs.logout()
                    except Exception:
                        pass
                    # WinError 10053/10054 = 网络断开，重试
                    if attempt < 2 and ("10053" in err_str or "10054" in err_str or "已中止" in err_str or "已拒绝" in err_str):
                        time.sleep(2 * (attempt + 1))  # 2s, 4s 退避
                        continue
                    return [], err_str

        return [], "超过最大重试次数"

    records, err = _fetch_bs()
    if err:
        result["error"] = err
        return result

    df_bs = pd.DataFrame(records[:8])
    if len(df_bs) > 0:
        df_bs = df_bs[df_bs["report_date"] != ""].sort_values(
            "report_date", ascending=False
        ).reset_index(drop=True)

    result["financial"] = df_bs
    result["success"] = True

    # ── akshare THS 同比增速（独立线程，5秒超时）──────────────
    # akshare是线程安全的，可以在主流程外单独拉取
    # 由于它慢（~5s），改为后置批量处理，不阻塞因子计算主路径
    # 同比增速为可选字段，不影响核心因子
    # 已在上面移除此处调用

    return result


# ─────────────────────────────────────────────────────────────────
# Step 3: 计算因子
# ─────────────────────────────────────────────────────────────────
def compute_factors(code: str, kline: pd.DataFrame, financial: pd.DataFrame) -> Dict[str, Any]:
    """
    从K线和财务数据计算三大类因子

    动量因子（6个）
    ──────────────
    ret_5d    : 5日收益率
    ret_20d   : 20日收益率
    ret_60d   : 60日收益率
    ret_120d  : 120日收益率
    sr_120d   : 120日收益/波动率（夏普代理）
    maxdd_120d: 120日最大回撤

    价值因子（5个）
    ──────────────
    pe        : PE(TTM)，来自K线数据或财务
    pb        : PB，来自K线
    dividend_yield : 股息率，来自K线
    peg       : PEG = pe / (profit_growth*100)
    asset_to_book : 资产/账面价值比

    质量因子（6个）
    ──────────────
    roe_ttm   : TTM ROE（近4季度加权）
    roa_ttm   : TTM ROA
    net_margin: 净利率 TTM
    gross_margin: 毛利率 TTM
    asset_turnover: 资产周转率
    debt_ratio: 资产负债率

    流动性因子（3个）
    ──────────────
    turnover_rate: 平均日换手率（%）
    amihud      : Amihud 非流动性代理
    vol_std_20d : 20日成交量标准差（z-score）

    风险因子（3个）
    ──────────────
    vol_20d/60d/120d: 历史波动率
    """
    factors = {"code": code}

    if len(kline) == 0 and len(financial) == 0:
        return factors

    # ── 动量因子 ────────────────────────────────────────────────
    if len(kline) >= 5:
        k = kline.copy()
        k.columns = [c.lower() for c in k.columns]
        if "close" not in k.columns and "adj_close" in k.columns:
            k["close"] = k["adj_close"]  # 用复权收盘价

        closes = k["close"].values
        volumes = k["volume"].values if "volume" in k.columns else np.zeros(len(k))

        # 各周期收益率
        factors["ret_5d"]   = _safe_ret(closes, 5)
        factors["ret_20d"]  = _safe_ret(closes, 20)
        factors["ret_60d"]  = _safe_ret(closes, 60)
        factors["ret_120d"] = _safe_ret(closes, 120)

        # 夏普代理（120日）
        if len(closes) >= 120:
            ret_series = pd.Series(closes).pct_change().dropna()
            ret_120 = ret_series.tail(120)
            mean_ret = ret_120.mean() * 252
            vol = ret_120.std() * np.sqrt(252)
            factors["sr_120d"] = mean_ret / vol if vol > 0 else None
            factors["maxdd_120d"] = _max_drawdown(closes[-120:])

        # 波动率
        if len(closes) >= 20:
            ret20 = pd.Series(closes[-20:]).pct_change().dropna()
            factors["vol_20d"] = ret20.std() * np.sqrt(252) if len(ret20) >= 10 else None
        if len(closes) >= 60:
            ret60 = pd.Series(closes[-60:]).pct_change().dropna()
            factors["vol_60d"] = ret60.std() * np.sqrt(252) if len(ret60) >= 30 else None
        if len(closes) >= 120:
            ret120 = pd.Series(closes[-120:]).pct_change().dropna()
            factors["vol_120d"] = ret120.std() * np.sqrt(252) if len(ret120) >= 60 else None

        # 换手率代理（成交量/总股本 proxy）
        if "volume" in k.columns and len(volumes) > 0:
            avg_vol = np.mean(volumes[-20:])
            factors["turnover_rate"] = avg_vol / (1e6) if avg_vol > 0 else None  # 简化代理
            vol_std = np.std(volumes[-20:]) if len(volumes) >= 20 else 0
            factors["vol_std_20d"] = (vol_std / (avg_vol + 1e-9)) if avg_vol > 0 else None

            # Amihud 非流动性
            if len(ret20) > 0:
                avg_ret_abs = np.mean(np.abs(ret20))
                factors["amihud"] = avg_ret_abs / (avg_vol + 1) if avg_vol > 0 else None

        # PE/PB（如果有）
        if "pe" in k.columns:
            factors["pe"] = k["pe"].iloc[-1] if pd.notna(k["pe"].iloc[-1]) else None
        if "pb" in k.columns:
            factors["pb"] = k["pb"].iloc[-1] if pd.notna(k["pb"].iloc[-1]) else None
        if "dividendYield" in k.columns:
            factors["dividend_yield"] = k["dividendYield"].iloc[-1]

    # ── 价值 + 质量因子 ─────────────────────────────────────────
    if len(financial) > 0:
        fin = financial.copy()

        # TTM ROE（加权4季度）
        roe_vals = fin.get("roe", pd.Series(dtype=float)).dropna().head(4).values
        factors["roe_ttm"] = float(np.mean(roe_vals)) if len(roe_vals) > 0 else None

        # 净利率、毛利率
        net_m = fin.get("net_margin", pd.Series(dtype=float)).dropna().head(4).values
        factors["net_margin"] = float(np.mean(net_m)) if len(net_m) > 0 else None

        gm_vals = fin.get("gross_margin", pd.Series(dtype=float)).dropna().head(4).values
        factors["gross_margin"] = float(np.mean(gm_vals)) if len(gm_vals) > 0 else None

        # 同比增速：从 revenue 自己计算（年报 YoY）
        if len(fin) >= 2:
            rev = fin["revenue"].dropna()
            if len(rev) >= 2:
                cur = rev.iloc[0]
                prev = rev.iloc[1]
                if prev and prev > 0 and cur:
                    factors["profit_growth"] = round((cur - prev) / prev * 100, 2)

        # PEG
        if factors.get("pe") and factors.get("profit_growth") and factors["profit_growth"] > 0:
            factors["peg"] = factors["pe"] / factors["profit_growth"]

    return factors


# ─────────────────────────────────────────────────────────────────
# Step 4: 主流程
# ─────────────────────────────────────────────────────────────────
def build_factor_library(
    max_stocks: Optional[int] = None,
    n_workers: int = 8,
    write_interval: int = 100,
) -> pd.DataFrame:
    """
    构建因子库主流程

    Args:
        max_stocks: 最多处理多少只股票（None=全部）
        n_workers: 并发线程数（baostock可承受，建议8-12）
        write_interval: 每处理多少只写一次中间结果

    Returns:
        DataFrame: 因子矩阵
    """
    log("=" * 60)
    log("A股量化因子库构建开始")
    log("=" * 60)

    # ── 加载候选列表 ─────────────────────────────────────────────
    stocks = load_stock_universe()
    if max_stocks:
        stocks = stocks[:max_stocks]
    total = len(stocks)
    log(f"待处理: {total} 只 | 并发: {n_workers} 线程")

    # ── 多线程抓取 + 心跳 ────────────────────────────────────────
    results: Dict[str, Dict] = {}
    success_count = 0
    fail_count = 0
    last_heartbeat = time.time()
    heartbeat_interval = 30  # 每30秒一次心跳

    def _do_work(sym: str) -> tuple:
        try:
            data = fetch_single_stock_data(sym)
            return sym, data, None
        except Exception as e:
            return sym, None, str(e)

    # ── 预热：登录 baostock（提前做，不占用线程时间）─────────────
    log("正在连接数据源（baostock 登录中，请稍候 ~5s）...")
    _ensure_baostock()
    log("数据源就绪，开始抓取...")

    heartbeat_interval = 15  # 每15秒一次心跳

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_do_work, sym): sym for sym in stocks}

        for future in as_completed(futures):
            sym = futures[future]
            try:
                _, data, err = future.result()
                if data:
                    results[sym] = data
                    if data["success"]:
                        success_count += 1
                    else:
                        fail_count += 1
                else:
                    results[sym] = {"code": sym, "success": False, "error": err}
                    fail_count += 1
            except Exception as e:
                results[sym] = {"code": sym, "success": False, "error": str(e)}
                fail_count += 1

            # ── 心跳：每完成1只或每15秒触发一次 ───────────────────
            now = time.time()
            done = success_count + fail_count
            if now - last_heartbeat >= heartbeat_interval or done == total:
                pct = done / total * 100
                eta_min = (now - _start_time) / done * (total - done) / 60 if done > 0 else 0
                log(
                    f"  [>] 已完成 {done}/{total} ({pct:.1f}%) | "
                    f"OK成功 {success_count} | X失败 {fail_count} | "
                    f"ETA ~{eta_min:.0f}分钟"
                )
                last_heartbeat = now

    log(f"数据抓取完成！成功 {success_count} | 失败 {fail_count}")

    # ── 计算因子 ─────────────────────────────────────────────────
    log("开始计算因子...")
    factor_rows = []
    for i, (code, data) in enumerate(results.items()):
        f = compute_factors(code, data.get("kline", pd.DataFrame()), data.get("financial", pd.DataFrame()))
        factor_rows.append(f)

        if (i + 1) % 200 == 0:
            log(f"  因子计算: {i+1}/{len(results)} 完成")

    df_factors = pd.DataFrame(factor_rows)
    log(f"因子计算完成: {len(df_factors)} 只 × {len(df_factors.columns)-1} 个因子")

    # ── 保存 ─────────────────────────────────────────────────────
    today_str = datetime.date.today().strftime("%Y%m%d")
    out_parquet = FEATURES_DIR / f"factors_{today_str}.parquet"
    out_csv = FEATURES_DIR / f"factors_{today_str}.csv"

    # CSV 为主格式（兼容性最好）
    df_factors.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # Parquet 为辅（需要 pyarrow>=13）
    parquet_ok = False
    try:
        df_factors.to_parquet(out_parquet, index=False)
        log(f"Parquet OK: {out_parquet.name} ({out_parquet.stat().st_size/1024/1024:.1f} MB)")
        parquet_ok = True
    except Exception as e:
        log(f"Parquet skip (pyarrow too old): {e}")

    csv_size_mb = out_csv.stat().st_size / 1024 / 1024
    log(f"CSV saved: factors_{today_str}.csv ({csv_size_mb:.1f} MB)")

    # 保存摘要
    summary = {
        "date": today_str,
        "total_stocks": len(df_factors),
        "success_count": success_count,
        "fail_count": fail_count,
        "factor_columns": df_factors.columns.tolist(),
        "factor_coverage": {
            c: int(df_factors[c].notna().sum()) for c in df_factors.columns if c != "code"
        },
    }
    with open(FEATURES_DIR / f"factors_summary_{today_str}.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    log("=" * 60)
    log("Factor library build complete!")
    log("=" * 60)

    return df_factors


# ─────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────
def _norm_yf(symbol: str) -> str:
    """转为 yfinance 格式: 600007.SS / 000786.SZ"""
    s = symbol.upper().strip()
    # 去掉 .SH / .SZ / .SS / .SZ 后缀
    for suffix in [".SH", ".SZ", ".SS", ".HK"]:
        s = s.replace(suffix, "")
    code = s.split(".")[0].zfill(6)
    if code.startswith(("6", "5", "9", "8")):
        return f"{code}.SS"
    return f"{code}.SZ"

def _norm_bs(symbol: str) -> str:
    """转为 baostock 格式: sh.600007 / sz.000786"""
    s = symbol.upper().strip()
    # 去掉 .SH / .SZ 后缀
    for suffix in [".SH", ".SZ"]:
        s = s.replace(suffix, "")
    code = s.split(".")[0].zfill(6)
    if code.startswith(("6", "5", "9", "8")):
        return f"sh.{code}"
    return f"sz.{code}"

def _norm_code6(symbol: str) -> str:
    """转为6位纯代码"""
    s = symbol.upper().strip()
    for suffix in [".SH", ".SZ", ".SS", ".HK"]:
        s = s.replace(suffix, "")
    return s.split(".")[0].zfill(6)

def _safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (f != f) else f
    except (TypeError, ValueError):
        return None

def _safe_float_pct(v) -> Optional[float]:
    """小数转百分比，或直接返回百分比数值"""
    if v is None:
        return None
    try:
        f = float(v)
        return round(f * 100, 4) if abs(f) < 1 else f
    except (TypeError, ValueError):
        return None

def _parse_pct_str(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        s = str(v).replace("%", "").replace(",", "").strip()
        return float(s)
    except ValueError:
        return None

def _safe_ret(closes: np.ndarray, period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    try:
        return (closes[-1] / closes[-period]) - 1
    except Exception:
        return None

def _max_drawdown(closes: np.ndarray) -> Optional[float]:
    if len(closes) < 2:
        return None
    try:
        peak = np.maximum.accumulate(closes)
        drawdown = (closes - peak) / peak
        return float(np.min(drawdown))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="构建A股量化因子库")
    parser.add_argument("--max", type=int, default=300, help="最多处理股票数（默认300，测试用）")
    parser.add_argument("--workers", type=int, default=8, help="并发线程数（默认8）")
    parser.add_argument("--all", action="store_true", help="处理全部股票（可能需要数小时）")
    args = parser.parse_args()

    max_stocks = None if args.all else args.max
    n_workers = args.workers

    print("+==================================================╗")
    print("|     A股量化因子库构建  |  心跳式进度监控         |")
    print("+==================================================╝")
    print(f"模式: {'全部股票' if args.all else f'前{max_stocks}只'} | 并发: {n_workers}线程")
    print()

    df = build_factor_library(max_stocks=max_stocks, n_workers=n_workers)

    # 打印因子覆盖统计
    print("\n因子覆盖统计:")
    for col in df.columns:
        if col == "code":
            continue
        cov = df[col].notna().sum()
        pct = cov / len(df) * 100
        print(f"  {col:<20s}: {cov:>5} / {len(df)} ({pct:.1f}%)")
