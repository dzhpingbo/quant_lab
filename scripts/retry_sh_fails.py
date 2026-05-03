"""
补充下载SH失败股票（单只逐一重试，避免批量失败）
+ 扫描最终所有SH股票10年+数量
"""
import sys, io, os, time, json, threading
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
os.environ['HTTP_PROXY']  = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'

import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

SAVE_DIR   = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/SH")
RESULT_FILE= Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/result_SH.json")
LOG_FILE   = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/yf_data/retry_sh.log")

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(line + '\n')

# 读取失败列表
with open(RESULT_FILE, encoding='utf-8') as f:
    result = json.load(f)

fail_codes = result.get('fail_codes', [])
print(f"失败股票总数: {len(fail_codes)}")
print(f"开始单只重试...\n")

recovered, still_fail = [], []
start = time.time()

# 心跳
stop_hb = threading.Event()
stats = {"done": 0, "total": len(fail_codes), "ok": 0}

def hb():
    while not stop_hb.wait(30):
        e = time.time() - start
        d = stats["done"]
        t = stats["total"]
        speed = d / max(e, 1)
        eta   = (t - d) / max(speed, 0.001)
        log(f"HEARTBEAT 进度 {d}/{t} ({100*d/max(t,1):.0f}%) | "
            f"恢复 {stats['ok']} | 已耗时 {e/60:.1f}min | 剩余 {eta/60:.1f}min")

threading.Thread(target=hb, daemon=True).start()

for yfc in tqdm(fail_codes, desc="重试SH", unit="只"):
    num = yfc.split('.')[0]
    fp  = SAVE_DIR / f"{num}.SH.csv"
    if fp.exists() and fp.stat().st_size > 500:
        stats["done"] += 1
        stats["ok"]   += 1
        recovered.append(yfc)
        continue
    try:
        t_ = yf.Ticker(yfc)
        df = t_.history(start='2010-01-01', end='2026-04-08', timeout=20)
        if len(df) > 10:
            df.index.name = 'date'
            df.columns    = [c.lower() for c in df.columns]
            df.to_csv(fp, encoding='utf-8')
            recovered.append(yfc)
            stats["ok"] += 1
        else:
            still_fail.append(yfc)
    except Exception as e:
        tqdm.write(f"  [FAIL] {yfc}: {e}")
        still_fail.append(yfc)
    stats["done"] += 1
    time.sleep(0.5)  # 单只请求间隔0.5秒

stop_hb.set()
elapsed = time.time() - start

print(f"\n{'='*50}")
print(f"重试完成！耗时: {elapsed/60:.1f}分钟")
print(f"  恢复成功: {len(recovered)} 只")
print(f"  仍然失败: {len(still_fail)} 只（真正无数据/退市）")

# 更新结果JSON
result['retry_recovered'] = len(recovered)
result['still_fail']      = still_fail
result['final_success']   = result['success'] + len(recovered)
with open(RESULT_FILE, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# 最终扫描10年+
print("\n--- 最终扫描 SH 目录 10年+股票 ---")
long_stocks = []
for fp in sorted(SAVE_DIR.glob("*.csv")):
    try:
        df = pd.read_csv(fp, usecols=[0], parse_dates=[0])
        col = df.columns[0]
        df[col] = pd.to_datetime(df[col], errors='coerce')
        years = (df[col].max() - df[col].min()).days / 365.25
        if years >= 10:
            long_stocks.append((fp.stem, round(years, 1)))
    except:
        pass

print(f"SH 目录 CSV 总数: {len(list(SAVE_DIR.glob('*.csv')))}")
print(f"10年以上股票: {len(long_stocks)} 只")
