"""
A股数据下载脚本 - yfinance版（通过7897代理，稳定高速）
- 支持沪市(SS)和深市(SZ)全量下载
- 批量请求，每批50只，约15~25分钟跑完全部
- 断点续传：已存在文件自动跳过
- 全程心跳日志 + tqdm进度条
"""
import sys, io, os, time, json, threading
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 设置代理（必须在 import yfinance 之前）
os.environ['HTTP_PROXY']  = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'

import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

# ── 配置 ────────────────────────────────────────────
START_DATE   = "2010-01-01"
END_DATE     = "2026-04-08"
BATCH_SIZE   = 50        # 每批只数
BATCH_DELAY  = 2.0       # 批间等待(秒)
TIMEOUT      = 30        # 单次请求超时(秒)

# 输出目录
OUT_SH = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SH")
OUT_SZ = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SZ")
OUT_SH.mkdir(parents=True, exist_ok=True)
OUT_SZ.mkdir(parents=True, exist_ok=True)

LOG_FILE = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/download.log")

# ── 生成股票列表 ─────────────────────────────────────
def gen_sh_codes():
    """沪市：600000-603999, 688000-688999(科创板)"""
    codes = []
    # 现有数据目录里的所有SH股票
    existing = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407")
    if existing.exists():
        for f in sorted(existing.glob("*.SH.csv")):
            num = f.stem.split('.')[0]
            codes.append(f"{num}.SS")
    if not codes:
        # fallback: 常见范围
        for i in range(600000, 604000):
            codes.append(f"{i:06d}.SS")
        for i in range(688000, 689000):
            codes.append(f"{i:06d}.SS")
    return codes

def gen_sz_codes():
    """深市：000001-002999(主板/中小板), 300000-300999(创业板), 002001-003000"""
    codes = []
    for i in range(1, 2000):
        codes.append(f"{i:06d}.SZ")
    for i in range(2001, 3000):
        codes.append(f"{i:06d}.SZ")
    for i in range(300001, 301000):
        codes.append(f"{i:06d}.SZ")
    return codes

# ── 心跳线程 ─────────────────────────────────────────
_heartbeat_stop = threading.Event()
_heartbeat_stats = {"done": 0, "total": 0, "success": 0, "fail": 0, "start": time.time()}

def heartbeat_thread():
    while not _heartbeat_stop.wait(30):
        elapsed = time.time() - _heartbeat_stats["start"]
        done    = _heartbeat_stats["done"]
        total   = _heartbeat_stats["total"]
        pct     = 100 * done / max(total, 1)
        speed   = done / max(elapsed, 1)
        eta     = (total - done) / max(speed, 0.001)
        msg = (f"[HEARTBEAT {datetime.now().strftime('%H:%M:%S')}] "
               f"进度 {done}/{total} ({pct:.1f}%) | "
               f"成功 {_heartbeat_stats['success']} | "
               f"失败 {_heartbeat_stats['fail']} | "
               f"已耗时 {elapsed/60:.1f}min | "
               f"预计剩余 {eta/60:.1f}min")
        print(msg, flush=True)
        LOG_FILE.open('a', encoding='utf-8').write(msg + '\n')

# ── 单批下载 ─────────────────────────────────────────
def download_batch(batch_yf_codes, out_dir, market_suffix):
    """
    批量下载一组股票，保存为 CSV
    返回: {code: ('ok'|'skip'|'fail', rows)}
    """
    results = {}
    # 先过滤已存在的
    to_dl = []
    for yfc in batch_yf_codes:
        num = yfc.split('.')[0]
        fp  = out_dir / f"{num}.{market_suffix}.csv"
        if fp.exists() and fp.stat().st_size > 1000:
            results[yfc] = ('skip', 0)
        else:
            to_dl.append(yfc)

    if not to_dl:
        return results

    try:
        raw = yf.download(
            to_dl,
            start=START_DATE,
            end=END_DATE,
            auto_adjust=False,
            progress=False,
            timeout=TIMEOUT,
            group_by='ticker',
        )
        # 兼容单只 ticker 和多只 ticker 的返回格式
        for yfc in to_dl:
            num = yfc.split('.')[0]
            fp  = out_dir / f"{num}.{market_suffix}.csv"
            try:
                if len(to_dl) == 1:
                    df = raw.copy()
                else:
                    df = raw[yfc].copy()
                df = df.dropna(how='all')
                if len(df) < 10:
                    results[yfc] = ('fail_empty', 0)
                    continue
                df.index.name = 'date'
                df.columns    = [c.lower() for c in df.columns]
                # 保留需要的列
                keep = [c for c in ['open','high','low','close','adj close','volume'] if c in df.columns]
                df   = df[keep].rename(columns={'adj close': 'adj_close'})
                df.to_csv(fp, encoding='utf-8')
                results[yfc] = ('ok', len(df))
            except Exception as e:
                results[yfc] = (f'fail:{e}', 0)
    except Exception as e:
        for yfc in to_dl:
            results[yfc] = (f'fail_batch:{e}', 0)

    return results

# ── 主流程 ────────────────────────────────────────────
def run(market='SH'):
    if market == 'SH':
        codes   = gen_sh_codes()
        out_dir = OUT_SH
        suffix  = 'SH'
    else:
        codes   = gen_sz_codes()
        out_dir = OUT_SZ
        suffix  = 'SZ'

    total = len(codes)
    _heartbeat_stats.update({"done": 0, "total": total, "success": 0, "fail": 0,
                              "start": time.time()})

    print(f"\n{'='*60}")
    print(f"开始下载 {market} 股票，共 {total} 只")
    print(f"代理: http://127.0.0.1:7897 | 批大小: {BATCH_SIZE}")
    print(f"输出目录: {out_dir}")
    print(f"{'='*60}\n")

    # 启动心跳
    hb = threading.Thread(target=heartbeat_thread, daemon=True)
    hb.start()

    success_list = []
    fail_list    = []
    skip_count   = 0

    batches = [codes[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

    with tqdm(total=total, desc=f"{market}", unit='只', dynamic_ncols=True) as pbar:
        for bi, batch in enumerate(batches):
            results = download_batch(batch, out_dir, suffix)

            for yfc, (status, rows) in results.items():
                if status == 'skip':
                    skip_count += 1
                elif status == 'ok':
                    success_list.append((yfc, rows))
                    _heartbeat_stats['success'] += 1
                else:
                    fail_list.append((yfc, status))
                    _heartbeat_stats['fail'] += 1
                    tqdm.write(f"  [FAIL] {yfc}: {status}")

            batch_done = len(results)
            _heartbeat_stats['done'] += batch_done
            pbar.update(batch_done)

            # 批间等待（最后一批不等）
            if bi < len(batches) - 1:
                time.sleep(BATCH_DELAY)

    _heartbeat_stop.set()

    # 汇总
    elapsed = time.time() - _heartbeat_stats['start']
    print(f"\n{'='*60}")
    print(f"[完成] {market} 下载结束")
    print(f"  成功: {len(success_list)} 只")
    print(f"  已有(跳过): {skip_count} 只")
    print(f"  失败: {len(fail_list)} 只")
    print(f"  总耗时: {elapsed/60:.1f} 分钟")

    if fail_list:
        print(f"\n失败列表（前30）:")
        for c, e in fail_list[:30]:
            print(f"  {c}: {e}")

    # 保存结果JSON
    result = {
        "market": market,
        "total": total,
        "success": len(success_list),
        "skip": skip_count,
        "fail": len(fail_list),
        "elapsed_min": round(elapsed/60, 1),
        "fail_codes": [c for c, _ in fail_list],
        "finish_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    rf = out_dir.parent / f"result_{market}.json"
    rf.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n结果已保存: {rf}")

    # 扫描10年+数据
    print(f"\n--- 扫描 10 年以上数据 ---")
    long_stocks = []
    for fp in sorted(out_dir.glob("*.csv")):
        try:
            df = pd.read_csv(fp, usecols=[0], parse_dates=[0])
            col = df.columns[0]
            df[col] = pd.to_datetime(df[col], errors='coerce')
            start_date = df[col].min()
            end_date   = df[col].max()
            years = (end_date - start_date).days / 365.25
            if years >= 10:
                long_stocks.append((fp.stem, start_date.date(), end_date.date(), round(years, 1)))
        except:
            pass
    print(f"10年+股票: {len(long_stocks)} 只")
    for s in long_stocks[:10]:
        print(f"  {s[0]}: {s[1]}~{s[2]} ({s[3]}年)")

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', choices=['SH','SZ','ALL'], default='SH',
                        help='下载市场: SH/SZ/ALL')
    args = parser.parse_args()

    if args.market == 'ALL':
        run('SH')
        print("\n等待 5 秒后开始 SZ...")
        time.sleep(5)
        run('SZ')
    else:
        run(args.market)
