"""快速测试：50只SH股票批量下载速度和成功率"""
import sys, io, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
os.environ['HTTP_PROXY']  = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'

import yfinance as yf
import pandas as pd
from pathlib import Path

# 取现有SH股票前50只做测试
codes_raw = sorted(Path("E:/dzhwork/quant/quant_lab/data/external/legacy_quant/AStock/20100101_20260407").glob("*.SH.csv"))[:50]
yf_codes  = [f"{f.stem.split('.')[0]}.SS" for f in codes_raw]

print(f"测试下载 {len(yf_codes)} 只SH股票...")
print(f"代码样本: {yf_codes[:5]}")
t0 = time.time()

raw = yf.download(
    yf_codes,
    start="2010-01-01",
    end="2026-04-08",
    auto_adjust=False,
    progress=False,
    timeout=30,
    group_by='ticker',
)
t1 = time.time()

print(f"\n耗时: {t1-t0:.1f}秒 ({(t1-t0)/len(yf_codes):.2f}秒/只)")
print(f"数据shape: {raw.shape}")

# 统计成功/失败
ok_cnt, fail_cnt = 0, 0
for yfc in yf_codes:
    try:
        df = raw[yfc].dropna(how='all')
        if len(df) >= 10:
            ok_cnt += 1
        else:
            fail_cnt += 1
            print(f"  EMPTY: {yfc}")
    except Exception as e:
        fail_cnt += 1
        print(f"  FAIL: {yfc} -> {e}")

print(f"\n成功: {ok_cnt}  失败: {fail_cnt}")
years_per_ok = 3944 / 244  # 大约多少年
print(f"估算: {ok_cnt} 只SH老股, 大多~16年历史")
print(f"\n按此速度下载 1385 只 SH 股票:")
total_time = (1385 / 50) * (t1-t0) + (1385//50) * 2
print(f"  预计耗时: {total_time/60:.1f} 分钟 (含批间等待2秒)")
