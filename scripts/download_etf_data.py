"""
ETF基金数据下载脚本 V2（防封IP版）
- 分批下载，每批之间强制等待
- 失败自动重试（最多3次）
- 全程心跳日志+进度汇报
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import akshare as ak
import pandas as pd
import time
import json
import random
from pathlib import Path
from datetime import datetime
import sys

# ========== 配置 ==========
OUTPUT_DIR = Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/ETF")
START_DATE = "20100101"
END_DATE = "20260407"
BATCH_SIZE = 50          # 每批下载50只
BATCH_DELAY = 10         # 每批之间等待10秒
REQUEST_DELAY = 2.0      # 每次请求间隔2秒
MAX_RETRIES = 3          # 失败最多重试3次
RETRY_DELAY = 15         # 重试前等待15秒
HEARTBEAT_INTERVAL = 60   # 每60秒心跳汇报

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("ETF基金数据下载工具 V2（防封IP版）")
print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"输出目录: {OUTPUT_DIR}")
print(f"数据区间: {START_DATE} ~ {END_DATE}")
print("=" * 60)

# ========== Step 1: 获取ETF列表 ==========
print("\n[Step 1/3] 获取场内ETF全量列表 ...")
for attempt in range(3):
    try:
        df_etf = ak.fund_etf_spot_em()
        print(f"  获取成功，共 {len(df_etf)} 只ETF")
        break
    except Exception as e:
        print(f"  获取失败(尝试{attempt+1}/3): {e}")
        if attempt < 2:
            print(f"  等待{RETRY_DELAY}秒后重试...")
            time.sleep(RETRY_DELAY)
        else:
            print("  3次失败，退出")
            sys.exit(1)

# 找到代码列和名称列
code_col = name_col = None
for col in df_etf.columns:
    cl = str(col).lower()
    if code_col is None and ('code' in cl or col in ['代码']):
        code_col = col
    if name_col is None and ('name' in cl or '简称' in col or col in ['名称']):
        name_col = col

if code_col is None:
    code_col = df_etf.columns[0]
if name_col is None:
    name_col = df_etf.columns[1]

all_codes = df_etf[code_col].astype(str).str.zfill(6).tolist()
etf_names = {str(r[code_col]).zfill(6): str(r.get(name_col, '')) for _, r in df_etf.iterrows()}

print(f"  代码列: {code_col}, 名称列: {name_col}")

# ========== Step 2: 核心下载函数 ==========
def download_one_etf(code, name=""):
    """下载单只ETF，带重试机制"""
    save_path = OUTPUT_DIR / f"{code}.SH.csv"
    if save_path.exists():
        return "已存在", 0

    for retry in range(MAX_RETRIES):
        try:
            time.sleep(REQUEST_DELAY + random.uniform(0, 0.5))  # 加随机抖动防封
            
            df = ak.fund_etf_hist_em(
                symbol=code,
                period="daily",
                start_date=START_DATE,
                end_date=END_DATE,
                adjust=""
            )
            
            if df is None or len(df) < 100:
                return "数据不足", 0
            
            # 列名标准化
            col_map = {}
            for c in df.columns:
                cs = str(c)
                if '日期' in cs: col_map[c] = 'date'
                elif '开盘' in cs: col_map[c] = 'open'
                elif '收盘' in cs: col_map[c] = 'close'
                elif '最高' in cs: col_map[c] = 'high'
                elif '最低' in cs: col_map[c] = 'low'
                elif '成交量' in cs: col_map[c] = 'volume'
                elif '成交额' in cs: col_map[c] = 'amount'
            
            df = df.rename(columns=col_map)
            keep = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']
            keep = [c for c in keep if c in df.columns]
            df = df[keep]
            df.to_csv(save_path, index=False, encoding='utf-8')
            
            return "成功", len(df)
            
        except Exception as e:
            err = str(e)
            if retry < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (retry + 1))
            else:
                return f"失败:{err[:80]}", 0
    return "未知错误", 0

# ========== Step 3: 分批下载 + 心跳日志 ==========
print(f"\n[Step 2/3] 开始分批下载，共 {len(all_codes)} 只ETF ...")
print("  每50只一批，每批间隔10秒，带失败重试\n")

success = []
failed = []
already_done = []
total = len(all_codes)

batch_start = time.time()
last_heartbeat = time.time()

for batch_idx in range(0, total, BATCH_SIZE):
    batch_codes = all_codes[batch_idx: batch_idx + BATCH_SIZE]
    batch_num = batch_idx // BATCH_SIZE + 1
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    
    print(f"\n--- 批次 {batch_num}/{total_batches} ({batch_idx+1}~{min(batch_idx+BATCH_SIZE, total)}) ---")
    
    for i, code in enumerate(batch_codes):
        global_idx = batch_idx + i
        name = etf_names.get(code, "")
        
        status, rows = download_one_etf(code, name)
        
        if status == "已存在":
            already_done.append((code, name, status))
        elif status == "成功":
            success.append((code, name, rows))
            print(f"  [{global_idx+1}/{total}] {code} {name:<18} -> {rows} rows OK")
        else:
            failed.append((code, name, status))
            print(f"  [{global_idx+1}/{total}] {code} {name:<18} -> {status} FAIL")
    
    # 批间等待
    if batch_idx + BATCH_SIZE < total:
        wait = BATCH_DELAY
        print(f"\n  本批完成，等待 {wait} 秒后继续下一批...")
        time.sleep(wait)
    
    # 心跳汇报
    now = time.time()
    if now - last_heartbeat >= HEARTBEAT_INTERVAL:
        elapsed = now - batch_start
        rate = (batch_idx + BATCH_SIZE) / elapsed
        eta = (total - batch_idx - BATCH_SIZE) / max(rate, 0.1)
        print(f"\n[HEARTBEAT {datetime.now().strftime('%H:%M:%S')}]"
              f" 进度 {batch_idx+BATCH_SIZE}/{total} ({100*(batch_idx+BATCH_SIZE)/total:.1f}%) |"
              f" 成功 {len(success)} | 已有 {len(already_done)} | 失败 {len(failed)} |"
              f" 已耗时 {elapsed/60:.1f}min | 预计剩余 {eta/60:.1f}min")
        last_heartbeat = now

# ========== Step 4: 汇总 ==========
total_elapsed = time.time() - batch_start

# 合并结果
all_success = success + [(c, n, "已存在") for c, n, _ in already_done]

# 统计10年以上数据
print("\n[Step 3/3] 汇总结果 ...")
print("=" * 60)
print(f"总耗时: {total_elapsed/60:.1f} 分钟")
print(f"成功下载: {len(success)} 只")
print(f"已有文件: {len(already_done)} 只")
print(f"下载失败: {len(failed)} 只")

print(f"\n成功下载的ETF:")
for code, name, rows in sorted(success, key=lambda x: -x[2])[:20]:
    print(f"  {code} {name or '':<22} {rows:>5} 行")

# 检查哪些有10年+数据
print(f"\n检查有10年+数据的ETF（>2400行）:")
ten_plus = [(c, n, r) for c, n, r in success if isinstance(r, int) and r > 2400]
if ten_plus:
    for code, name, rows in sorted(ten_plus, key=lambda x: -x[2]):
        years = rows / 244  # 约244交易日/年
        print(f"  {code} {name or '':<22} {rows:>5}行 ~{years:.1f}年")
else:
    print("  无10年以上数据，检查已有文件...")
    for fp in sorted(OUTPUT_DIR.glob("*.csv")):
        df = pd.read_csv(fp, usecols=['date'])
        rows = len(df)
        if rows > 100:
            years = rows / 244
            print(f"  {fp.stem:<12} {rows:>5}行 ~{years:.1f}年")

print(f"\n失败原因统计（前5）:")
from collections import Counter
fail_reasons = Counter([f[2] for f in failed])
for reason, count in fail_reasons.most_common(5):
    print(f"  {count:>4} 只: {reason[:60]}")

# 保存结果清单
result = {
    "download_time": datetime.now().isoformat(),
    "total": total,
    "success_new": len(success),
    "already_exists": len(already_done),
    "failed": len(failed),
    "success_detail": [(c, n, str(r)) for c, n, r in success],
    "failed_detail": [(c, n, r) for c, n, r in failed],
}
with open(OUTPUT_DIR / "download_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存: {OUTPUT_DIR / 'download_result.json'}")
print(f"数据目录: {OUTPUT_DIR}")
print("=" * 60)
print("全部完成！")
