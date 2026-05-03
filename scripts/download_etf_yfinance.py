"""
ETF全量下载脚本 - 通过yfinance（走7897代理）
从新浪获取1476只ETF代码，然后用yfinance批量下载历史K线
"""
import os, sys, io, time, json, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import akshare as ak
import yfinance as yf

# ========== 配置 ==========
PROXY = "http://127.0.0.1:7897"
os.environ["HTTP_PROXY"] = PROXY
os.environ["HTTPS_PROXY"] = PROXY
os.environ["http_proxy"] = PROXY
os.environ["https_proxy"] = PROXY

OUTPUT_DIR = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/ETF/yf_etf_data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUTPUT_DIR / "download_etf.log"
START_DATE = "2005-01-01"
END_DATE = "2026-04-09"
BATCH_SIZE = 30
MAX_WORKERS = 10

# ========== 心跳锁 ==========
heartbeat_lock = threading.Lock()
last_heartbeat = time.time()

def heartbeat(msg):
    global last_heartbeat
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with heartbeat_lock:
        last_heartbeat = time.time()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)

# ========== Step 1: 获取新浪ETF列表 ==========
def get_sina_etf_list():
    heartbeat("📡 正在从新浪获取ETF列表...")
    df = ak.fund_etf_category_sina(symbol="ETF基金")
    # 代码格式: sz159998, sh510050
    codes = []
    for _, row in df.iterrows():
        c = str(row.iloc[0]).strip().lower()
        if c.startswith("sh"):
            yf_code = c[2:] + ".SS"
        elif c.startswith("sz"):
            yf_code = c[2:] + ".SZ"
        else:
            continue
        codes.append((c.upper(), yf_code, row.iloc[1] if len(row) > 1 else c))
    heartbeat(f"✅ 找到 {len(codes)} 只ETF（去重前 {len(df)}）")
    return codes

# ========== Step 2: 单只下载 ==========
def download_one(args):
    sina_code, yf_code, name = args
    out_file = OUTPUT_DIR / f"{yf_code}.csv"
    # 跳过已存在的（断点续传）
    if out_file.exists():
        return {"sina": sina_code, "yf": yf_code, "status": "skip", "rows": -1}
    try:
        ticker = yf.Ticker(yf_code)
        df = ticker.history(start=START_DATE, end=END_DATE, timeout=15)
        if df is None or len(df) == 0:
            return {"sina": sina_code, "yf": yf_code, "status": "fail", "reason": "no_data"}
        # 整理格式
        df = df.reset_index()
        if "Dividends" in df.columns:
            df = df.drop(columns=["Dividends", "Stock Splits"], errors="ignore")
        if "Capital Gains" in df.columns:
            df = df.drop(columns=["Capital Gains"], errors="ignore")
        # 转中文列名
        col_map = {
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        }
        df = df.rename(columns=col_map)
        # 确保 date 列格式正确
        df["date"] = df["date"].astype(str).str[:10]
        # 只保留有用列
        keep_cols = ["date", "open", "high", "low", "close", "volume"]
        available = [c for c in keep_cols if c in df.columns]
        df = df[available]
        df.to_csv(out_file, index=False, encoding="utf-8")
        return {"sina": sina_code, "yf": yf_code, "status": "ok", "rows": len(df), "name": name}
    except Exception as e:
        return {"sina": sina_code, "yf": yf_code, "status": "fail", "reason": str(e)[:50]}

# ========== Step 3: 主流程 ==========
def main():
    global last_heartbeat
    start_time = time.time()

    heartbeat("=" * 50)
    heartbeat("ETF全量下载开始")
    heartbeat("=" * 50)

    # 获取列表
    all_etfs = get_sina_etf_list()

    # 去重（同一ETF可能出现在多个分类）
    seen = set()
    unique_etfs = []
    for item in all_etfs:
        if item[1] not in seen:
            seen.add(item[1])
            unique_etfs.append(item)
    heartbeat(f"去重后: {len(unique_etfs)} 只ETF")

    total = len(unique_etfs)
    results = {"ok": [], "fail": [], "skip": []}

    # 分批下载
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    heartbeat(f"分 {n_batches} 批，每批 {BATCH_SIZE} 只，并发 {MAX_WORKERS}")

    for batch_idx in range(n_batches):
        batch_start = batch_idx * BATCH_SIZE
        batch = unique_etfs[batch_start: batch_start + BATCH_SIZE]
        batch_num = batch_idx + 1

        t0 = time.time()
        ok_c, fail_c, skip_c = 0, 0, 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(download_one, item): item for item in batch}
            for fut in as_completed(futures):
                r = fut.result()
                if r["status"] == "ok":
                    results["ok"].append(r)
                    ok_c += 1
                elif r["status"] == "skip":
                    results["skip"].append(r)
                    skip_c += 1
                else:
                    results["fail"].append(r)
                    fail_c += 1

        elapsed = time.time() - t0

        # 汇总本批
        processed = batch_num * BATCH_SIZE if batch_num < n_batches else total
        speed = len(batch) / elapsed if elapsed > 0 else 0
        heartbeat(
            f"[{batch_num}/{n_batches}] ✅{ok_c} ❌{fail_c} ⏭{skip_c} | "
            f"进度 {processed}/{total} ({processed*100//total}%) | "
            f"耗时 {elapsed:.1f}s | 速度 {speed:.1f}只/秒"
        )

    # ========== 最终报告 ==========
    total_elapsed = time.time() - start_time
    m, s = divmod(int(total_elapsed), 60)
    h, m = divmod(m, 60)

    heartbeat("")
    heartbeat("=" * 50)
    heartbeat("📊 ETF下载完成！最终报告")
    heartbeat("=" * 50)
    heartbeat(f"  总计扫描: {total} 只ETF")
    heartbeat(f"  ✅ 下载成功: {len(results['ok'])} 只")
    heartbeat(f"  ⏭ 跳过(已存在): {len(results['skip'])} 只")
    heartbeat(f"  ❌ 失败: {len(results['fail'])} 只")
    heartbeat(f"  总耗时: {h}h {m}m {s}s")

    # 列出成功样本
    if results["ok"]:
        ok_sorted = sorted(results["ok"], key=lambda x: x["rows"], reverse=True)
        heartbeat(f"\n成功样本（前10，按行数排序）:")
        for r in ok_sorted[:10]:
            heartbeat(f"  {r['yf']:12s} | {r.get('name', r['sina']):20s} | {r['rows']:5d} 行")

    # 保存失败列表（可重试）
    fail_file = OUTPUT_DIR / "failed_etfs.json"
    with open(fail_file, "w", encoding="utf-8") as f:
        json.dump(results["fail"], f, ensure_ascii=False, indent=2)
    heartbeat(f"\n失败列表已保存: {fail_file}")

    # 保存结果
    result_file = OUTPUT_DIR / "result_etf.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "total": total,
            "ok": len(results["ok"]),
            "skip": len(results["skip"]),
            "fail": len(results["fail"]),
            "elapsed_seconds": total_elapsed,
            "ok_list": results["ok"]
        }, f, ensure_ascii=False, indent=2)
    heartbeat(f"结果JSON: {result_file}")

if __name__ == "__main__":
    main()
